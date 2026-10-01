"""WP-1: a withheld publication leaves durable, structured proof of failure.

Daily Primary SyncRun 93108 built candidate 4132, the Team State proof found
team 118 ineligible, and the publication transaction rolled back. The
candidate and every piece of evidence went with it; the run kept one string.

These tests drive the real sync-completion path, the real publication
transaction and the real Team State proof (with a governed readiness resolver
standing in for the live classifier) and prove that after the rollback:

* the candidate is not published and not stored;
* the serving snapshot and its lineage are untouched;
* ``sync_runs.publication_outcome`` names every failing team, its reasons,
  coverage counts and unresolved-arm causes;
* nothing else from the publication transaction committed.
"""

from datetime import date, timedelta

import sys

import pytest
from sqlalchemy import event

from models.dashboard_snapshot import DashboardSnapshot
from models.pitcher import Pitcher
from models.sync_failure import SyncFailure
from models.sync_run import SyncRun
from models.team_state_publication_proof import TeamStatePublicationProof
from services import active_bullpen_coverage_diagnostic as diagnostic
from services import dashboard_snapshot, publication_outcome, sync as sync_service
from services import sync_metadata
from services import team_state_source
from services import team_state_vnext_production_proof as proof_service
from services.mlb_club_directory import MLB_TEAM_IDS
from services.team_board_snapshot_team_state import build_team_accounting
from tests.test_dashboard_snapshot import (  # noqa: F401
    _create_sync_run,
    _minimal_dashboard_payload,
    _team_state_proof_readiness,
    app,
)
from utils.db import db
from utils.time import utc_now_naive


FAILING = (118, 133, 140)
DATA_THROUGH = date(2026, 9, 29)
AVAILABILITY = date(2026, 9, 30)


def _candidate_payload():
    payload = _minimal_dashboard_payload()
    payload['freshness']['data_through'] = DATA_THROUGH.isoformat()
    payload['freshness']['availability_reference_date'] = AVAILABILITY.isoformat()
    payload['freshness']['slate_coverage']['slate_date'] = DATA_THROUGH.isoformat()
    payload['trusted_team_boards'] = {
        'contract': 'trusted_team_board_publication_v1',
        'data_through': DATA_THROUGH.isoformat(),
        'team_accounting': build_team_accounting(MLB_TEAM_IDS, MLB_TEAM_IDS),
        'by_team_id': {
            str(team_id): {'team': {'team_id': team_id}} for team_id in MLB_TEAM_IDS
        },
    }
    return payload


def _readiness(team_id, reference_dates_out, snapshot):
    readiness = _team_state_proof_readiness(reference_dates_out, snapshot)
    readiness['freshness'] = {
        'data_through': DATA_THROUGH.isoformat(), 'freshness_state': 'current',
    }
    readiness['team'] = {
        'team_id': team_id, 'team_name': f'Team {team_id}',
        'team_abbreviation': f'T{team_id}',
    }
    readiness['readiness']['summary'] = 'Current bullpen state.'
    readiness['trust_metadata'] = {'confidence': 'high', 'data_state': 'fresh'}
    if team_id in FAILING:
        readiness['readiness']['status_code'] = 'data_limited'
        readiness['trust_metadata'] = {
            'confidence': 'low', 'data_state': 'incomplete',
            'confidence_reasons': ['insufficient_active_bullpen_coverage'],
            'active_bullpen_coverage': {
                'active_bullpen_count': 16, 'usable_record_count': 13,
                'unresolved_record_count': 3,
            },
        }
    return readiness


def _serving_snapshot(run):
    previous = DashboardSnapshot(
        snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
        sync_run_id=run.id,
        status=dashboard_snapshot.SNAPSHOT_STATUS_READY,
        is_published=True,
        published_at=utc_now_naive() - timedelta(days=2),
        payload={**_minimal_dashboard_payload(), 'name': 'serving'},
        payload_version=dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION,
        data_through=date(2026, 9, 27),
        availability_reference_date=date(2026, 9, 28),
        snapshot_generated_at=utc_now_naive() - timedelta(days=2),
        source='external_schedule',
    )
    db.session.add(previous)
    run.published_dashboard_snapshot_id = None
    db.session.flush()
    run.published_dashboard_snapshot_id = previous.id
    return previous


def _kc_unresolved_arms():
    """Three KC arms whose open fetch failures keep them unresolved."""
    ids = []
    for index in range(3):
        pitcher = Pitcher(
            mlb_id=880000 + index, full_name=f'KC arm {index}', team_id=118,
            active=True, team_abbreviation='KC', position='P',
            team_assignment_status='ASSIGNED',
        )
        db.session.add(pitcher)
        db.session.flush()
        db.session.add(SyncFailure(
            job_name='daily_sync', entity_type='pitcher_game_logs',
            entity_ref=str(pitcher.mlb_id), error='ReadTimeout: https://x?token=y',
            resolved=False,
        ))
        ids.append(pitcher.id)
    return frozenset(ids)


@pytest.fixture
def daily_candidate(app, monkeypatch):  # noqa: F811
    """Wire the real publication path to a governed readiness resolver."""
    with app.app_context():
        serving_run = _create_sync_run()
        serving = _serving_snapshot(serving_run)
        run = _create_sync_run(stage='started')
        members = _kc_unresolved_arms()
        db.session.commit()

        app.config['TEAM_STATE_PUBLICATION_PROOF_REQUIRED'] = True
        monkeypatch.setattr(dashboard_snapshot, 'product_current_date', lambda: AVAILABILITY)
        monkeypatch.setattr(team_state_source, 'is_valid_team_id', lambda _team_id: True)
        monkeypatch.setattr(
            diagnostic, 'resolve_active_bullpen_membership',
            lambda team_id, _date: (members, True) if team_id == 118 else (frozenset(), False),
        )
        resolved = []
        real_requirement = proof_service.require_transactional_publication_proof

        def resolver(team_id, **kwargs):
            resolved.append(team_id)
            return _readiness(team_id, kwargs['reference_dates_out'], kwargs['source_snapshot'])

        monkeypatch.setattr(
            proof_service, 'require_transactional_publication_proof',
            lambda snapshot: real_requirement(
                snapshot, team_ids=MLB_TEAM_IDS, readiness_resolver=resolver,
            ),
        )
        allocated = []

        def remember(_mapper, _connection, target):
            allocated.append(target.id)

        event.listen(DashboardSnapshot, 'after_insert', remember)

        def build_candidate(**kwargs):
            return dashboard_snapshot.build_dashboard_snapshot(
                _candidate_payload, sync_run_id=kwargs['sync_run_id'],
                source=kwargs['source'], publish=True, commit=False, raise_errors=True,
            )

        monkeypatch.setattr(
            dashboard_snapshot, 'build_bullpen_dashboard_snapshot', build_candidate,
        )
        yield {
            'run_id': run.id, 'serving_id': serving.id,
            'serving_run_id': serving_run.id, 'resolved': resolved,
            'allocated': allocated, 'members': members,
        }
        event.remove(DashboardSnapshot, 'after_insert', remember)


def _complete(run_id):
    return sync_service.complete_sync_run_with_snapshot(
        run_id, final_status=sync_metadata.STATUS_SUCCESS,
        job_name=sync_metadata.JOB_DAILY_SYNC,
    )


def test_team_state_failure_evidence_survives_the_rollback(app, daily_candidate):
    with app.app_context():
        with pytest.raises(proof_service.TeamStatePublicationIneligible) as raised:
            _complete(daily_candidate['run_id'])

        # The historical one-line reason is unchanged, first failing team.
        assert str(raised.value).startswith('snapshot_team_state_ineligible:118:')
        db.session.expire_all()

        # Every team was evaluated before withholding.
        assert sorted(daily_candidate['resolved']) == sorted(MLB_TEAM_IDS)

        # The invalid candidate is gone, the serving snapshot is untouched.
        assert daily_candidate['allocated'], 'the candidate was never built'
        candidate_id = daily_candidate['allocated'][0]
        assert db.session.get(DashboardSnapshot, candidate_id) is None
        published = DashboardSnapshot.query.filter_by(is_published=True).all()
        assert [row.id for row in published] == [daily_candidate['serving_id']]
        assert TeamStatePublicationProof.query.count() == 0
        serving_run = db.session.get(SyncRun, daily_candidate['serving_run_id'])
        assert serving_run.published_dashboard_snapshot_id == daily_candidate['serving_id']

        run = db.session.get(SyncRun, daily_candidate['run_id'])
        assert run.status == sync_metadata.STATUS_FAILED
        assert run.published_dashboard_snapshot_id is None
        assert run.error_message.startswith('snapshot_team_state_ineligible:118:')

        outcome = run.publication_outcome
        assert outcome['schema_version'] == publication_outcome.SCHEMA_VERSION
        assert outcome['status'] == 'failed'
        assert outcome['stop_reason'] == 'TeamStatePublicationIneligible'
        assert outcome['failed_authority'] == 'team_state_eligibility'
        assert outcome['candidate_snapshot_id'] == candidate_id
        assert outcome['candidate_persisted'] is False
        assert outcome['published_snapshot_id'] is None
        assert outcome['serving_snapshot_id'] == daily_candidate['serving_id']
        assert outcome['affected_team_ids'] == list(FAILING)
        assert outcome['recovery_attempted'] is False
        assert outcome['recovery_result'] is None
        assert outcome['reference_dates'] == {
            'membership_reference_date': DATA_THROUGH.isoformat(),
            'availability_reference_date': AVAILABILITY.isoformat(),
        }

        teams = {team['team_id']: team for team in outcome['teams']}
        assert set(teams) == set(FAILING)
        kc = teams[118]
        assert 'confidence:low' in kc['reasons']
        assert 'status_code_unsupported:data_limited' in kc['reasons']
        assert (kc['active_bullpen_count'], kc['usable_record_count'],
                kc['unresolved_record_count']) == (16, 13, 3)
        assert kc['membership_reference_date'] == DATA_THROUGH.isoformat()
        assert kc['availability_reference_date'] == AVAILABILITY.isoformat()

        # Arm-level causes are queryable without re-running anything.
        assert kc['arm_causes_available'] is True
        assert kc['cause_counts'] == {'unresolved_fetch_failure': 3}
        assert {arm['pitcher_id'] for arm in kc['unresolved_arms']} == set(
            daily_candidate['members'],
        )
        assert all(arm['open_fetch_failure_count'] == 1 for arm in kc['unresolved_arms'])
        # A team without roster authority is still reported, with its reasons.
        assert teams[133]['authority_complete'] is False
        assert teams[133]['reasons']


def test_the_outcome_is_queryable_as_data(app, daily_candidate):
    with app.app_context():
        with pytest.raises(ValueError):
            _complete(daily_candidate['run_id'])
        db.session.expire_all()
        failed = [
            row for row in SyncRun.query.order_by(SyncRun.id).all()
            if (row.publication_outcome or {}).get('failed_authority')
            == 'team_state_eligibility'
        ]
        assert [row.id for row in failed] == [daily_candidate['run_id']]


def test_the_outcome_stores_no_source_payloads_or_secrets(app, daily_candidate):
    with app.app_context():
        with pytest.raises(ValueError):
            _complete(daily_candidate['run_id'])
        db.session.expire_all()
        text = str(db.session.get(SyncRun, daily_candidate['run_id']).publication_outcome)
        assert 'token=' not in text and 'https://' not in text
        assert 'payload' not in text


def test_without_wp1_the_evidence_is_lost(app, daily_candidate, monkeypatch):
    """The regression: remove the outcome write and only the string remains."""
    with app.app_context():
        monkeypatch.setattr(
            sync_service, '_publication_failure_outcome', lambda *_args, **_kwargs: None,
        )
        with pytest.raises(ValueError):
            _complete(daily_candidate['run_id'])
        db.session.expire_all()
        run = db.session.get(SyncRun, daily_candidate['run_id'])
        assert run.error_message.startswith('snapshot_team_state_ineligible:118:')
        assert run.publication_outcome is None


def test_an_unshapeable_failure_still_records_a_minimal_outcome(app, daily_candidate, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(
            publication_outcome, 'outcome_failed',
            lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError('shaping failed')),
        )
        with pytest.raises(proof_service.TeamStatePublicationIneligible):
            _complete(daily_candidate['run_id'])
        db.session.expire_all()
        outcome = db.session.get(SyncRun, daily_candidate['run_id']).publication_outcome
        assert outcome['status'] == 'failed'
        assert outcome['evidence_error'] == 'outcome_shaping_failed'
        assert outcome['candidate_persisted'] is False


def test_an_arm_diagnostic_error_never_masks_the_withholding(app, daily_candidate, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(
            diagnostic, 'diagnose_active_bullpen_coverage',
            lambda *args, **kwargs: (_ for _ in ()).throw(LookupError('boom')),
        )
        with pytest.raises(proof_service.TeamStatePublicationIneligible):
            _complete(daily_candidate['run_id'])
        db.session.expire_all()
        outcome = db.session.get(SyncRun, daily_candidate['run_id']).publication_outcome
        kc = next(team for team in outcome['teams'] if team['team_id'] == 118)
        assert kc['arm_causes_available'] is False
        assert kc['arm_causes_error'] == 'LookupError'
        assert DashboardSnapshot.query.filter_by(is_published=True).count() == 1


def test_a_gate_withheld_candidate_records_a_withheld_outcome(app, daily_candidate, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(
            dashboard_snapshot, '_payload_slate_coverage_unavailable_reason',
            lambda _payload: 'slate_coverage_incomplete',
        )
        run, snapshot = sync_service.complete_sync_run_with_snapshot(
            daily_candidate['run_id'], final_status=sync_metadata.STATUS_SUCCESS,
            raise_on_withheld=False,
        )
        db.session.expire_all()
        outcome = db.session.get(SyncRun, daily_candidate['run_id']).publication_outcome
        assert outcome['status'] == 'withheld'
        assert outcome['stop_reason'] == 'publication_gate'
        assert outcome['failed_authority'] == 'slate_coverage'
        assert outcome['candidate_persisted'] is True
        assert outcome['candidate_snapshot_id'] == snapshot.id
        assert outcome['serving_snapshot_id'] == daily_candidate['serving_id']


def test_a_published_candidate_records_a_published_outcome(app, daily_candidate, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(sys.modules[__name__], 'FAILING', ())
        monkeypatch.setattr(
            dashboard_snapshot, 'run_post_commit_snapshot_publication', lambda _s: None,
        )
        run, snapshot = _complete(daily_candidate['run_id'])
        db.session.expire_all()
        outcome = db.session.get(SyncRun, daily_candidate['run_id']).publication_outcome
        assert outcome['status'] == 'published'
        assert outcome['published_snapshot_id'] == snapshot.id
        assert outcome['serving_snapshot_id'] == snapshot.id
        assert outcome['candidate_persisted'] is True


def test_failure_outcome_shape_for_a_plain_exception():
    outcome = publication_outcome.outcome_failed(RuntimeError('x' * 5000))
    assert outcome['status'] == 'failed'
    assert outcome['stop_reason'] == 'RuntimeError'
    assert outcome['failed_authority'] == 'publication'
    assert len(outcome['withheld_reason']) <= publication_outcome.MAX_REASON_LENGTH + 3
    assert outcome['teams'] == [] and outcome['affected_team_ids'] == []


@pytest.mark.parametrize('reason, authority', [
    ('snapshot_team_state_ineligible:118:confidence:low', 'team_state_eligibility'),
    ('team_state_publication_proof_invariant_failed:x', 'team_state_proof'),
    ('dashboard_snapshot_appearance_ledger_incomplete', 'appearance_ledger'),
    ('slate_coverage_incomplete', 'slate_coverage'),
    ('', None),
])
def test_failed_authority_classification(reason, authority):
    assert publication_outcome.failed_authority_for_reason(reason) == authority


# ---------------------------------------------------------------------------
# Gate evidence (SyncRun 93211: slate_coverage with affected_game_pks=[]).
# ---------------------------------------------------------------------------

from models.postgame_processed_game import PostgameProcessedGame  # noqa: E402
from models.scheduled_game import ScheduledGame  # noqa: E402


def _game(game_pk, state, game_date=DATA_THROUGH, *, marker=None, teams=(141, 147)):
    for team_id, side, opponent in ((teams[0], 'home', teams[1]), (teams[1], 'away', teams[0])):
        db.session.add(ScheduledGame(
            team_id=team_id, game_pk=game_pk, game_date=game_date, status_state=state,
            home_away=side, opponent_team_id=opponent,
        ))
    if marker is not None:
        db.session.add(PostgameProcessedGame(
            mlb_game_pk=game_pk, game_date=game_date, processing_status=marker,
        ))


def _withhold_for_slate(monkeypatch):
    monkeypatch.setattr(
        dashboard_snapshot, '_payload_slate_coverage_unavailable_reason',
        lambda _payload: dashboard_snapshot.DASHBOARD_SNAPSHOT_SLATE_COVERAGE_INCOMPLETE,
    )


def test_a_raised_withhold_keeps_its_withheld_outcome(app, daily_candidate, monkeypatch):
    """SyncRun 93211: the withheld outcome was overwritten as failed/not persisted."""
    with app.app_context():
        _withhold_for_slate(monkeypatch)
        with pytest.raises(sync_service.DashboardSnapshotPublicationWithheld):
            _complete(daily_candidate['run_id'])
        db.session.expire_all()
        run = db.session.get(SyncRun, daily_candidate['run_id'])
        outcome = run.publication_outcome
        assert run.status == sync_metadata.STATUS_FAILED
        assert outcome['status'] == 'withheld'
        assert outcome['failed_authority'] == 'slate_coverage'
        assert outcome['candidate_persisted'] is True
        candidate = db.session.get(DashboardSnapshot, outcome['candidate_snapshot_id'])
        assert candidate is not None and candidate.is_published is False
        assert outcome['serving_snapshot_id'] == daily_candidate['serving_id']


def test_slate_withholding_names_every_blocking_game(app, daily_candidate, monkeypatch):
    with app.app_context():
        _game(9001, ScheduledGame.STATE_FINAL, marker=PostgameProcessedGame.STATUS_FULLY_PROCESSED)
        _game(9002, ScheduledGame.STATE_FINAL)
        _game(9003, ScheduledGame.STATE_SCHEDULED, teams=(108, 109))
        _game(9004, ScheduledGame.STATE_SUSPENDED, teams=(110, 111))
        _game(9005, ScheduledGame.STATE_POSTPONED, teams=(112, 113))
        _game(9006, ScheduledGame.STATE_FINAL, teams=(114, 115),
              marker=PostgameProcessedGame.STATUS_FAILED)
        db.session.commit()
        _withhold_for_slate(monkeypatch)
        with pytest.raises(sync_service.DashboardSnapshotPublicationWithheld):
            _complete(daily_candidate['run_id'])
        db.session.expire_all()
        outcome = db.session.get(SyncRun, daily_candidate['run_id']).publication_outcome

        assert outcome['affected_game_pks'] == [9002, 9003, 9004, 9006]
        games = {game['game_pk']: game for game in outcome['gate_evidence']['games']}
        assert games[9002]['blocker'] == 'final_marker_missing'
        assert games[9003]['blocker'] == 'not_final'
        assert games[9004]['blocker'] == 'suspended'
        assert games[9006]['blocker'] == 'final_marker_failed'
        assert games[9002]['game_date'] == DATA_THROUGH.isoformat()
        assert outcome['gate_evidence']['slate_date'] == DATA_THROUGH.isoformat()


def test_run_failures_name_roster_conflicts_without_raw_payloads(app, daily_candidate, monkeypatch):
    with app.app_context():
        db.session.add(SyncFailure(
            job_name='daily_sync', entity_type='roster_status_snapshot_conflict',
            entity_ref='687924', error='Roster snapshot team conflict for same pitcher/date',
            payload={'pitcher_id': 7, 'mlb_id': 687924, 'snapshot_date': '2026-10-01',
                     'existing_team_id': 141, 'incoming_team_id': 147},
            sync_run_id=daily_candidate['run_id'], resolved=False,
        ))
        db.session.commit()
        _withhold_for_slate(monkeypatch)
        with pytest.raises(sync_service.DashboardSnapshotPublicationWithheld):
            sync_service.complete_sync_run_with_snapshot(
                daily_candidate['run_id'], final_status=sync_metadata.STATUS_PARTIAL,
                publication_critical_complete=False,
            )
        db.session.expire_all()
        outcome = db.session.get(SyncRun, daily_candidate['run_id']).publication_outcome
        failures = outcome['run_failures']
        assert failures['unresolved_by_entity_type']['roster_status_snapshot_conflict'] == 1
        assert failures['roster_conflicts'] == [{
            'mlb_id': 687924, 'pitcher_id': 7, 'snapshot_date': '2026-10-01',
            'existing_team_id': 141, 'incoming_team_id': 147,
        }]
        assert outcome['publication_critical_complete'] is False


def test_ledger_withholding_names_the_deficient_games(app, daily_candidate):
    with app.app_context():
        _game(9101, ScheduledGame.STATE_FINAL, game_date=date(2026, 9, 28),
              marker=PostgameProcessedGame.STATUS_FULLY_PROCESSED)
        db.session.commit()
        with pytest.raises(sync_service.DashboardSnapshotPublicationWithheld):
            _complete(daily_candidate['run_id'])
        db.session.expire_all()
        outcome = db.session.get(SyncRun, daily_candidate['run_id']).publication_outcome
        assert outcome['status'] == 'withheld'
        assert outcome['failed_authority'] == 'appearance_ledger'
        assert outcome['affected_game_pks'] == [9101]
        assert outcome['gate_evidence']['games'][0]['blocker'] == (
            'final_game_without_appearance_rows'
        )
