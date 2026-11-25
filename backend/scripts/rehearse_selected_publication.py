"""Bind one immutable v3 Team State selection to a disposable trusted publication.

Called by a fixture with a fresh target session and a transaction-idle source
owner connection supplied by isolated_cluster. No deployed caller or scheduler.
"""
from collections import Counter
from datetime import date, datetime
import re

from flask import current_app
from sqlalchemy import text

from models.dashboard_snapshot import DashboardSnapshot
from models.sync_run import SyncRun
from models.team_state_publication_proof import TeamStatePublicationProof
from scripts.rehearse_selected_schedule import pinned_schedule, reconcile_schedule
from scripts.rehearse_trusted_publication import assert_rehearsal_target
from services import dashboard_snapshot
from services.mlb_club_directory import MLB_TEAM_IDS
from sync_v3.acquisition_receipt import played_day_evidence
from sync_v3.evidence import replay
from sync_v3.generation import _inspect
from sync_v3.product_reads import _league
from utils.db import db


def selection_receipt(league, revision, generation):
    if (league['status'] != 'represented' or league['current_serving_eligible'] is not False
            or league['selection_revision'] != revision or league['generation'] != generation):
        raise ValueError('The requested generation is no longer selected')
    teams = {}
    for row in league['teams']:
        team = row['team_id']
        state = row['team_state']
        citation = league['citations'][team]['readiness']
        if (team in teams or state['available'] is not True or state['data_through'] != league['data_through']
                or not citation or not all(re.fullmatch('[0-9a-f]{64}', citation[key])
                                          for key in ('input_digest', 'facts_digest'))):
            raise ValueError(f'Missing or ambiguous played-day evidence for {team}')
        teams[team] = dict(state=state, readiness=citation)
    if set(teams) != set(MLB_TEAM_IDS):
        raise ValueError('The played-day handoff requires all 30 clubs')
    return dict(contract='isolated_selected_team_state_v1', revision=revision, generation=generation,
                data_through=league['data_through'], availability_reference=league['availability_reference'],
                teams={str(team): value for team, value in teams.items()})


def verify_frozen_states(snapshot, binding):
    dates = (snapshot.data_through.isoformat(), snapshot.availability_reference_date.isoformat())
    if dates != (binding['data_through'], binding['availability_reference']):
        raise ValueError('Selected and published dates disagree')
    receipts = snapshot.payload['trusted_team_boards']['frozen_team_state_by_team_id']
    if receipts.keys() != binding['teams'].keys():
        raise ValueError('Selected and published populations disagree')
    for team, expected in binding['teams'].items():
        actual = receipts[team]
        if (actual['dashboard_snapshot_id'] != snapshot.id or actual['team_id'] != int(team)
                or actual['value'] != expected['state']):
            raise ValueError(f'Selected and published Team State disagree for {team}')


def _verify_final_lines(cur, finals):
    for game, source in finals:
        pk = game['gamePk']
        cur.execute("""SELECT r.facts FROM candidate.confirmations c
                       JOIN candidate.revisions r ON r.id=c.revision_id
                       WHERE c.domain='final' AND c.identity=%s AND c.source_id=%s""", (str(pk), source))
        facts, = cur.fetchone()
        expected = Counter((a['pitcher_mlb_id'], a['team_id'], a['outs_recorded'], int(a['is_starter']),
                            date.fromisoformat(game['officialDate'])) for a in facts)
        rows = db.session.execute(text("""SELECT p.mlb_id,l.appearance_team_id,l.innings_pitched_outs,
                                                 l.games_started,l.game_date
                                          FROM game_logs l LEFT JOIN pitchers p ON p.id=l.pitcher_id
                                          WHERE l.mlb_game_pk=:pk"""), {'pk': pk})
        if Counter(tuple(row) for row in rows) != expected:
            raise ValueError(f'Final {pk} target appearances differ from the credited canonical lines')


def _reconcile_confirmed_finals(cur, finals, represented, run_id):
    from services.sync import POSTGAME_MARKER_STATUS_FULLY_PROCESSED, process_completed_game_for_postgame_refresh

    for game, source_id in finals:
        box = replay(cur, source_id).body

        def process(plan_only):
            return process_completed_game_for_postgame_refresh(
                game, schedule_date=represented, sync_run_id=run_id, boxscore=box,
                plan_only=plan_only, force=True,
            )

        plan = process(True)
        summary = plan.get('reconciliation_summary') or {}
        if (not summary.get('rows_planned') or summary['rows_blocked'] or plan['incomplete_reason']
                or summary['pitcher_identity_unchanged'] != summary['rows_planned']):
            raise ValueError(f"Final {game['gamePk']} requires a resolved, unchanged pitcher identity for every line")
        applied = process(False)
        if (applied['incomplete_reason'] or applied['processing_status'] != POSTGAME_MARKER_STATUS_FULLY_PROCESSED
                or applied['reconciliation_summary']['complete_reconciliation_fingerprint']
                != summary['complete_reconciliation_fingerprint']):
            raise ValueError(f"Final {game['gamePk']} did not apply the governed pitching-line plan")
        repeated = process(True)
        if (repeated['incomplete_reason'] or repeated['reconciliation_summary']['rows_unchanged'] != summary['rows_planned']):
            raise ValueError(f"Final {game['gamePk']} did not converge on its retained pitching lines")


def rehearse_handoff(owner, *, revision, generation, predecessor, sync_run_id, reconcile_finals=False,
                     reconcile_schedules=False):
    """Keep the selector pinned until the independent target transaction commits."""
    assert_rehearsal_target()
    if (reconcile_finals or reconcile_schedules) and sync_run_id is not None:
        raise ValueError('Source reconciliation requires the selected v3 acquisition')
    if (not current_app.testing or not current_app.config.get('TEAM_STATE_PUBLICATION_PROOF_REQUIRED')
            or not current_app.config.get('DAILY_EDITION_PUBLICATION_REQUIRED')):
        raise RuntimeError('A rehearsal with both publication gates enabled is required')
    if (type(revision) is not int or revision <= 0 or not re.fullmatch('[0-9a-f]{64}', generation)
            or type(predecessor) is not int or predecessor <= 0):
        raise ValueError('Expected a pinned selection and predecessor')
    with owner, owner.cursor() as cur:
        cur.execute("SELECT current_database(),current_user,inet_server_addr(),current_setting('listen_addresses')")
        if cur.fetchone() != ('sync_v3_rehearsal', 'rehearsal_owner', None, ''):
            raise RuntimeError('Source must be the isolated rehearsal cluster')
    with owner, owner.cursor() as cur, db.session.begin():
        target = db.session.execute(text(
            "SELECT current_database(),inet_server_addr(),current_setting('listen_addresses')"
        )).one()
        if not target[0].endswith('_rehearsal_test') or tuple(target[1:]) != (None, ''):
            raise RuntimeError('Destination must be a socket-only rehearsal database')
        # SHARE blocks selector inserts across databases through the target commit.
        # The sandbox owner only holds the table lock. Read as the existing reviewer.
        cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
        cur.execute('LOCK TABLE candidate.core_selections IN SHARE MODE NOWAIT')
        if sync_run_id is None:
            cur.execute('LOCK TABLE candidate.jobs IN SHARE MODE NOWAIT')
        cur.execute('SET LOCAL ROLE sync_v3_reviewer')
        league = _league(cur, None, None)
        binding = selection_receipt(league, revision, generation)
        review = _inspect(cur, generation, compare_latest=True)['selection_review']
        if review['status'] != 'core_comparison_complete' or review['latest_inventory_digest'] != generation:
            raise ValueError('Selected generation no longer passes review')
        db.session.execute(text('LOCK TABLE dashboard_snapshots IN SHARE ROW EXCLUSIVE MODE NOWAIT'))
        prior = DashboardSnapshot.query.filter_by(
            snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD, is_published=True
        ).one()
        receipt = dict(binding, predecessor=predecessor)
        if sync_run_id is None:
            represented = date.fromisoformat(binding['data_through'])
            receipt['acquisition'], finals = played_day_evidence(cur, represented)
            if reconcile_finals:
                receipt['reconciled_final_sources'] = {str(game['gamePk']): source for game, source in finals}
        schedules = {}
        if reconcile_schedules:
            receipt['reconciled_schedules'] = {}
            for day in sorted({represented, date.fromisoformat(binding['availability_reference'])}):
                identity, observation = pinned_schedule(cur, generation, day)
                receipt['reconciled_schedules'][str(day)] = identity
                schedules[day] = observation
        previous_binding = prior.payload.get('v3_rehearsal_selection') or {}
        if previous_binding.get('generation') == generation:
            if previous_binding != receipt or (sync_run_id is not None and prior.sync_run_id != sync_run_id):
                raise ValueError('The selected generation already has a different publication receipt')
            if reconcile_finals:
                _verify_final_lines(cur, finals)
            for day, observation in schedules.items():
                reconcile_schedule(day, observation, verify_only=True)
            verify_frozen_states(prior, receipt)
            return prior.id
        if prior.id != predecessor:
            raise ValueError('Trusted publication predecessor changed')
        if sync_run_id is None:
            acquisition = receipt['acquisition']
            run = SyncRun(job_name='sync_v3_acquisition_rehearsal', source='sync_v3_rehearsal', status='success',
                          stage='acquired', latest_workload_date=date.fromisoformat(acquisition['represented']),
                          started_at=datetime.fromisoformat(acquisition['started_at']).replace(tzinfo=None),
                          completed_at=datetime.fromisoformat(acquisition['completed_at']).replace(tzinfo=None),
                          records_processed=acquisition['jobs'])
            db.session.add(run)
            db.session.flush()
            sync_run_id = run.id
        else:
            run = db.session.get(SyncRun, sync_run_id)
        if (run is None or run.status != 'success' or run.published_dashboard_snapshot_id is not None
                or str(run.latest_workload_date) != receipt['data_through']
                or str(prior.data_through) > receipt['data_through']):
            raise ValueError('An unused, successful sync run for the selected workload date is required')
        if reconcile_finals:
            _reconcile_confirmed_finals(cur, finals, represented, sync_run_id)
            _verify_final_lines(cur, finals)
        for day, observation in schedules.items():
            reconcile_schedule(day, observation)
        snapshot = dashboard_snapshot.build_bullpen_dashboard_snapshot(
            sync_run_id=sync_run_id, source='v3_team_state_rehearsal', publish=False,
            commit=False, raise_errors=True,
        )
        snapshot.payload = dict(snapshot.payload, v3_rehearsal_selection=receipt)
        dashboard_snapshot.publish_dashboard_snapshot(snapshot, commit=False)
        if not snapshot.is_published:
            raise ValueError(f'Governed publication withheld: {snapshot.error_message}')
        proof = TeamStatePublicationProof.query.filter_by(snapshot_id=snapshot.id, sync_run_id=sync_run_id).one()
        inconclusive = {key for key, item in proof.proof['invariants'].items()
                        if item['result'] == 'INCONCLUSIVE'}
        if (proof.captured_team_count != 30 or proof.overall_verdict not in ('PASS', 'PASS_WITH_INCONCLUSIVE')
                or inconclusive - {'no_false_cross_version_change'}):
            raise ValueError('Incomplete independent publication proof')
        verify_frozen_states(snapshot, receipt)
        return snapshot.id


def main():
    import argparse
    import json
    from contextlib import closing
    import os
    from pathlib import Path
    import socket
    import sys
    from urllib.parse import parse_qs, urlparse

    import psycopg2
    from freezegun import freeze_time

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-socket', type=Path, required=True)
    parser.add_argument('--revision', type=int, required=True)
    parser.add_argument('--generation', required=True)
    parser.add_argument('--predecessor', type=int, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--sync-run', type=int)
    source.add_argument('--source-acquisition', action='store_true',
                        help='Use the selected date’s settled v3 acquisition in the disposable target')
    parser.add_argument('--reconcile-finals', action='store_true',
                        help='Reconcile retained official final lines before the isolated publication')
    parser.add_argument('--reconcile-schedule', action='store_true',
                        help='Populate empty target dates using selected schedule receipts with their acquisition times')
    parser.add_argument('--product-day', type=date.fromisoformat, required=True)
    args = parser.parse_args()
    url = urlparse(assert_rehearsal_target())
    params = parse_qs(url.query)
    hosts = params.get('host', [])
    if (not args.source_socket.is_absolute() or len(hosts) != 1 or not Path(hosts[0]).is_absolute()
            or set(params) != {'host'} or os.environ.get('PGHOSTADDR') or os.environ.get('PGSERVICE')
            or os.environ.get('AUTO_SYNC') != 'false' or os.environ.get('APP_ENV') != 'test'):
        parser.error('Use absolute Unix sockets, APP_ENV=test and AUTO_SYNC=false')

    def local_only(event, arguments):
        if event == 'socket.connect' and arguments[0].family != socket.AF_UNIX:
            raise RuntimeError('Network unavailable during publication rehearsal')

    sys.addaudithook(local_only)
    from app import create_app
    from services.public_serving_authority import install_public_serving_authority

    app = create_app('test')
    app.config.update(TRUSTED_PUBLIC_SERVING_ENABLED=True, TEAM_STATE_PUBLICATION_PROOF_REQUIRED=True,
                      DAILY_EDITION_PUBLICATION_REQUIRED=True, SHARE_ARTIFACT_AUTOGENERATION_ENABLED=True,
                      TONIGHT_V1_PROJECTION_ENABLED=True)
    if not install_public_serving_authority(app):
        raise RuntimeError('Trusted publication serving was not installed')
    with closing(psycopg2.connect(host=str(args.source_socket), port=5432, dbname='sync_v3_rehearsal',
                                  user='rehearsal_owner', connect_timeout=5)) as owner:
        with app.app_context(), freeze_time(f'{args.product_day} 12:00:00', real_asyncio=True):
            snapshot = rehearse_handoff(owner, revision=args.revision, generation=args.generation,
                                        predecessor=args.predecessor, sync_run_id=args.sync_run,
                                        reconcile_finals=args.reconcile_finals, reconcile_schedules=args.reconcile_schedule)
            # The production hooks recover independently after the trust transaction.
            # Recheck durable rows and public reads because hook failures are nonfatal.
            from scripts.verify_selected_delivery import verify_delivery
            from sync_v3.product_reads import read_game_cards

            committed = db.session.get(DashboardSnapshot, snapshot)
            dashboard_snapshot.run_post_commit_snapshot_publication(committed)
            db.session.remove()
            with closing(psycopg2.connect(host=str(args.source_socket), port=5432, dbname='sync_v3_rehearsal',
                                          user='sync_v3_reviewer', connect_timeout=5)) as reviewer:
                cards = read_game_cards(reviewer, revision=args.revision)
            result = verify_delivery(app.test_client(), db.session.get(DashboardSnapshot, snapshot), cards,
                                     product_day=args.product_day)
            print(json.dumps(result))
            if not result['supporting_fields_match']:
                raise SystemExit('Post-commit delivery verified; Tonight supporting fields differ')


if __name__ == '__main__':
    main()
