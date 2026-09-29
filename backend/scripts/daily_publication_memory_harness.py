"""Production-shaped memory harness for the Daily Primary publication phase.

Seeds a disposable Postgres test database with a league-sized fixture (30 MLB
teams, ~32 pitchers per organization, two seasons of appearances, a week of
fatigue history) and runs the real Daily Primary completion path twice: the
first run creates the prior trusted publication, the second is measured.

It records peak RSS at the publication checkpoints, total SQL statements,
``stale_history`` reads, source-snapshot lookups, and the final published
content identity, so the same fixture can be compared before and after a
memory change. It refuses any non-disposable database.

Usage (test databases only):
    APP_ENV=test DATABASE_URL=postgresql://.../baseballos_ci_tests_N \
        python scripts/daily_publication_memory_harness.py --json out.json
"""

from __future__ import annotations

import argparse
from datetime import timedelta
import gc
import hashlib
import importlib
import json
import logging
import os
import sys
from time import perf_counter

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

TEAM_IDS = (
    108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121,
    133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146,
    147, 158,
)
# Production shape: ~960 pitchers (30 x 32), two seasons of appearances.
PRODUCTION_SHAPE = {
    'starters_per_team': 5,
    'relievers_per_team': 9,
    'depth_per_team': 18,
    'season_days': 150,
    'seasons': 2,
}


def _status_kb(field):
    try:
        with open('/proc/self/status', encoding='ascii') as handle:
            for line in handle:
                if line.startswith(field + ':'):
                    return int(line.split()[1])
    except OSError:
        return None
    return None


def rss_mb():
    value = _status_kb('VmRSS')
    return None if value is None else round(value / 1024, 1)


def peak_rss_mb():
    value = _status_kb('VmHWM')
    return None if value is None else round(value / 1024, 1)


def reset_peak_rss():
    """Reset VmHWM so each measured run reports its own peak (Linux only)."""
    try:
        with open('/proc/self/clear_refs', 'w', encoding='ascii') as handle:
            handle.write('5')
        return True
    except OSError:
        return False


def _seed(reference_date, shape=None):
    from models.fatigue_score import FatigueScore
    from models.game_log import GameLog
    from models.pitcher import Pitcher
    from models.postgame_processed_game import PostgameProcessedGame
    from models.scheduled_game import ScheduledGame
    from models.team_game_pitching_split import TeamGamePitchingSplit
    from services.roster_status import STATUS_IL_15
    from tests.roster_readiness_fixture import seed_roster_readiness_snapshots
    from utils.db import db
    from utils.time import utc_now_naive

    shape = {**PRODUCTION_SHAPE, **(shape or {})}
    starters_per_team = shape['starters_per_team']
    relievers_per_team = shape['relievers_per_team']
    depth_per_team = shape['depth_per_team']
    season_days = shape['season_days']
    now = utc_now_naive()
    pitchers_by_team = {}
    mlb_id = 8100000
    for team_index, team_id in enumerate(TEAM_IDS):
        team = {'starters': [], 'relievers': [], 'depth': []}
        for role, count in (
            ('starters', starters_per_team),
            ('relievers', relievers_per_team),
            ('depth', depth_per_team),
        ):
            for slot in range(count):
                mlb_id += 1
                if role == 'depth':
                    roster_status = STATUS_IL_15 if slot % 6 == 0 else 'minors'
                else:
                    roster_status = 'active'
                pitcher = Pitcher(
                    mlb_id=mlb_id,
                    full_name=f'Stress {team_id} {role[:-1]} {slot:02d}',
                    team_id=team_id,
                    team_name=f'Stress Team {team_index:02d}',
                    team_abbreviation=f'S{team_index:02d}',
                    position='P', active=True, roster_status=roster_status,
                    roster_status_source='test_fixture',
                    roster_status_updated_at=now,
                )
                db.session.add(pitcher)
                team[role].append(pitcher)
        pitchers_by_team[team_id] = team
    db.session.flush()

    game_logs = []
    scheduled = []
    processed = []
    splits = []
    game_pk = 8500000
    season_offsets = tuple(365 * index for index in range(shape['seasons'] - 1, -1, -1))
    for season_offset in season_offsets:
        for day in range(season_days, 0, -1):
            game_date = reference_date - timedelta(days=day + season_offset)
            for pair in range(0, len(TEAM_IDS), 2):
                home, away = TEAM_IDS[pair], TEAM_IDS[pair + 1]
                if (day + pair) % 7 == 0:
                    continue  # off day for this pair
                game_pk += 1
                for side_index, team_id in enumerate((home, away)):
                    team = pitchers_by_team[team_id]
                    starter = team['starters'][day % starters_per_team]
                    relievers = [
                        team['relievers'][(day + k + side_index) % relievers_per_team]
                        for k in range(min(3 + (day % 2), relievers_per_team))
                    ]
                    if day % 5 == 0 and depth_per_team:
                        relievers.append(team['depth'][(day // 5) % depth_per_team])
                    starter_outs = 15 + (day % 4) * 1
                    game_logs.append(dict(
                        pitcher_id=starter.id, mlb_game_pk=game_pk,
                        game_date=game_date, game_type='R', games_started=1,
                        innings_pitched=starter_outs / 3,
                        innings_pitched_outs=starter_outs,
                        pitches_thrown=85 + day % 15,
                        appearance_team_id=team_id,
                        appearance_team_status=GameLog.APPEARANCE_TEAM_RESOLVED,
                    ))
                    bullpen_outs = 0
                    for order, reliever in enumerate(relievers):
                        outs = 3 if order < 3 else 2
                        bullpen_outs += outs
                        game_logs.append(dict(
                            pitcher_id=reliever.id, mlb_game_pk=game_pk,
                            game_date=game_date, game_type='R', games_started=0,
                            innings_pitched=outs / 3, innings_pitched_outs=outs,
                            pitches_thrown=12 + (day + order) % 14,
                            appearance_team_id=team_id,
                            appearance_team_status=GameLog.APPEARANCE_TEAM_RESOLVED,
                            leverage_index=1.0 + (order % 3) * 0.4,
                        ))
                    if season_offset == 0:
                        scheduled.append(dict(
                            team_id=team_id, game_pk=game_pk, game_date=game_date,
                            game_type='R', status_code='F',
                            status_state=ScheduledGame.STATE_FINAL,
                            game_number=1,
                            home_away='home' if side_index == 0 else 'away',
                        ))
                        splits.append(dict(
                            team_id=team_id, mlb_game_pk=game_pk,
                            game_date=game_date, game_type='R',
                            starter_pitcher_id=starter.id,
                            starter_mlb_id=starter.mlb_id,
                            starter_identity_status=TeamGamePitchingSplit.STARTER_KNOWN,
                            starter_outs_recorded=starter_outs,
                            bullpen_outs_recorded=bullpen_outs,
                            total_team_outs=starter_outs + bullpen_outs,
                            split_completeness_status=TeamGamePitchingSplit.STATUS_COMPLETE,
                            split_reason_codes=[],
                            suspended_resumed_linkage_status=TeamGamePitchingSplit.LINKAGE_NONE,
                            calendar_context_status=TeamGamePitchingSplit.STATUS_COMPLETE,
                            calendar_reason_codes=[], source='test_fixture',
                        ))
                if season_offset == 0:
                    processed.append(dict(
                        mlb_game_pk=game_pk, game_date=game_date, game_type='R',
                        home_team_id=home, away_team_id=away,
                        final_state='Final', pitching_lines_seen=1,
                        processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
                    ))
    db.session.bulk_insert_mappings(GameLog, game_logs)
    db.session.bulk_insert_mappings(ScheduledGame, scheduled)
    db.session.bulk_insert_mappings(PostgameProcessedGame, processed)
    db.session.bulk_insert_mappings(TeamGamePitchingSplit, splits)

    fatigue = []
    for team in pitchers_by_team.values():
        for index, pitcher in enumerate(team['starters'] + team['relievers'] + team['depth']):
            for day in range(7, 0, -1):
                fatigue.append(dict(
                    pitcher_id=pitcher.id,
                    calculated_at=now - timedelta(days=day - 1, minutes=5),
                    raw_score=10.0 + index % 40,
                    pitch_count_score=5.0, rest_days_score=5.0,
                    appearances_score=5.0, leverage_score=5.0, innings_score=5.0,
                    days_since_last_appearance=1 + index % 4,
                    appearances_last_7=index % 4,
                    appearances_last_14=index % 7,
                    pitches_last_7_days=10 * (index % 6),
                    innings_last_7_days=float(index % 4),
                    risk_level='LOW' if index % 3 else 'MODERATE',
                ))
    db.session.bulk_insert_mappings(FatigueScore, fatigue)
    db.session.commit()
    seed_roster_readiness_snapshots([reference_date])
    return {
        'pitchers': sum(len(v) for t in pitchers_by_team.values() for v in t.values()),
        'game_logs': len(game_logs),
        'scheduled_games': len(scheduled),
        'fatigue_scores': len(fatigue),
    }


class _Counters(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.INFO)
        self.stale_history_calls = 0
        self.stale_history_rows = 0
        self.stale_history_max_rows = 0
        self.source_snapshot_lookups = 0
        self.source_snapshot_ids = {}
        self.stale_history_by_size = {}
        self.memory_lines = []

    def emit(self, record):
        message = record.getMessage()
        if message.startswith('stale_history '):
            self.stale_history_calls += 1
            try:
                rows = int(message.rsplit('returned_rows=', 1)[1].split()[0])
            except (IndexError, ValueError):
                rows = 0
            self.stale_history_rows += rows
            try:
                requested = int(message.split('requested_pitchers=', 1)[1].split()[0])
            except (IndexError, ValueError):
                requested = 0
            bucket = 'league(>=300 pitchers)' if requested >= 300 else 'team(<300 pitchers)'
            self.stale_history_by_size[bucket] = self.stale_history_by_size.get(bucket, 0) + 1
            self.stale_history_max_rows = max(self.stale_history_max_rows, rows)
        elif message.startswith('source_score_cutoff '):
            self.source_snapshot_lookups += 1
            source_id = message.split('source_snapshot_id=', 1)[1].split()[0]
            self.source_snapshot_ids[source_id] = self.source_snapshot_ids.get(source_id, 0) + 1
        elif 'memory checkpoint' in message:
            self.memory_lines.append(message)


def _digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, default=str, separators=(',', ':')).encode()
    ).hexdigest()


_VOLATILE_KEYS = frozenset({
    'generated_at', 'snapshot_generated_at', 'published_at', 'created_at',
    'updated_at', 'calculated_at', 'captured_at', 'observed_at',
    'snapshot_id', 'source_snapshot_id', 'dashboard_snapshot_id', 'sync_run_id',
    'id', 'content_digest', 'payload_digest', 'digest', 'fingerprint',
    'duration_ms', 'build_ms', 'elapsed_ms', 'timings', 'timing_ms',
})


def _normalize(value):
    """Drop identity/timestamp fields that legitimately differ per run."""
    if isinstance(value, dict):
        return {
            key: _normalize(item) for key, item in value.items()
            if key not in _VOLATILE_KEYS and not key.endswith('_at')
            and not key.endswith('_ms')
            and not (key.startswith('last_') and key.endswith('sync'))
            and not key.startswith('inventory_digest_')
        }
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def _run_once(app, run_label, counters, checkpoints):
    from models.sync_run import SyncRun
    from services import sync
    from services.tonight_read_model import read_tonight_v1
    from utils.db import db
    from utils.time import utc_now_naive
    from sqlalchemy import event

    reference_date = checkpoints['reference_date']
    run = SyncRun(
        job_name='daily_sync', started_at=utc_now_naive() - timedelta(minutes=2),
        status='running', stage='dashboard_snapshot', source='test',
        latest_game_date=reference_date - timedelta(days=1),
        latest_workload_date=reference_date - timedelta(days=1),
        latest_fatigue_calculated_at=utc_now_naive(),
    )
    db.session.add(run)
    db.session.commit()
    run_id = run.id
    db.session.expunge_all()
    gc.collect()

    statements = {
        'all': 0, 'full_payload_selects': 0, 'large_payload_writes': 0,
        'dashboard_payload_writes': 0,
    }

    def count(_conn, _cursor, statement, params, _context, _many):
        statements['all'] += 1
        lowered = statement.lower()
        if lowered.startswith('select') and 'dashboard_snapshots.payload as ' in lowered:
            statements['full_payload_selects'] += 1
        mapping = params if isinstance(params, dict) else {}
        if (
            lowered.startswith('insert into dashboard_snapshots')
            and mapping.get('snapshot_type') == 'bullpen_dashboard'
        ) or lowered.startswith('update dashboard_snapshots set payload'):
            statements['dashboard_payload_writes'] += 1
        values = mapping.values() if mapping else (params or ())
        try:
            if any(isinstance(value, str) and len(value) > 1_000_000 for value in values):
                statements['large_payload_writes'] += 1
        except TypeError:
            pass

    counters.stale_history_calls = 0
    counters.stale_history_rows = 0
    counters.stale_history_max_rows = 0
    counters.source_snapshot_lookups = 0
    counters.source_snapshot_ids = {}
    counters.stale_history_by_size = {}
    reset_peak_rss()
    start_rss = rss_mb()
    event.listen(db.engine, 'before_cursor_execute', count)
    started = perf_counter()
    fatigue_seconds = None
    try:
        # Production order: fatigue recalculation immediately precedes the
        # publication in the same process (sync_completion_snapshot_publish).
        fatigue_started = perf_counter()
        sync.recalculate_all_fatigue()
        fatigue_seconds = round(perf_counter() - fatigue_started, 1)
        _run, snapshot = sync.complete_sync_run_with_snapshot(
            run_id, final_status='success', publication_critical_complete=True,
            source='manual', snapshot_source='scheduled_sync',
        )
    finally:
        seconds = perf_counter() - started
        event.remove(db.engine, 'before_cursor_execute', count)
    peak = peak_rss_mb()
    snapshot_id = snapshot.id
    payload = snapshot.payload
    tonight = read_tonight_v1(snapshot.availability_reference_date, snapshot_id)
    result = {
        'label': run_label,
        'snapshot_id': snapshot_id,
        'published': bool(snapshot.is_published),
        'status': snapshot.status,
        'seconds': round(seconds, 1),
        'fatigue_seconds': fatigue_seconds,
        'rss_start_mb': start_rss,
        'rss_peak_mb': peak,
        'rss_end_mb': rss_mb(),
        'sql_statements': statements['all'],
        'full_payload_selects': statements['full_payload_selects'],
        'large_payload_writes': statements['large_payload_writes'],
        'dashboard_payload_writes': statements['dashboard_payload_writes'],
        'stale_history_calls': counters.stale_history_calls,
        'stale_history_rows': counters.stale_history_rows,
        'stale_history_max_rows': counters.stale_history_max_rows,
        'source_snapshot_lookups': counters.source_snapshot_lookups,
        'source_snapshot_lookup_results': dict(counters.source_snapshot_ids),
        'stale_history_by_size': dict(counters.stale_history_by_size),
        'payload_bytes': len(json.dumps(payload, default=str)),
        'identity_map_after': len(db.session.identity_map),
    }
    result['parity'] = _parity(snapshot, payload, tonight)
    dump_dir = os.environ.get('MEMORY_HARNESS_DUMP_DIR')
    if dump_dir:
        from services.public_serving_authority import TEAM_BOARD_PACKAGE_KEY
        from models.team_state_publication_proof import TeamStatePublicationProof
        proof = TeamStatePublicationProof.query.filter_by(snapshot_id=snapshot_id).one_or_none()
        with open(os.path.join(dump_dir, f'{run_label}_payload.json'), 'w', encoding='utf-8') as handle:
            json.dump(_normalize({k: v for k, v in payload.items() if k != TEAM_BOARD_PACKAGE_KEY}),
                      handle, sort_keys=True, indent=1, default=str)
        with open(os.path.join(dump_dir, f'{run_label}_proof.json'), 'w', encoding='utf-8') as handle:
            json.dump(_normalize(proof.proof if proof else None), handle, sort_keys=True, indent=1, default=str)
    db.session.expunge_all()
    return result


def _parity(snapshot, payload, tonight):
    from models.share_artifact import ShareArtifact
    from models.team_state_publication_proof import TeamStatePublicationProof
    from services.public_serving_authority import TEAM_BOARD_PACKAGE_KEY
    from utils.db import db

    package = payload.get(TEAM_BOARD_PACKAGE_KEY) or {}
    by_team = package.get('by_team_id') or {}
    team_states = {
        team_id: (item.get('team_state') or {}).get('state')
        if isinstance(item.get('team_state'), dict) else item.get('team_state')
        for team_id, item in (
            (entry.get('team_id'), entry)
            for entry in (payload.get('landscape') or {}).get('teams', [])
            if isinstance(entry, dict)
        )
    }
    artifacts = (
        db.session.query(ShareArtifact.team_id, ShareArtifact.artifact_type, ShareArtifact.payload)
        .filter(ShareArtifact.source_snapshot_id == snapshot.id)
        .order_by(ShareArtifact.artifact_type, ShareArtifact.team_id)
        .all()
    )
    proof = (
        db.session.query(TeamStatePublicationProof)
        .filter_by(snapshot_id=snapshot.id)
        .one_or_none()
    )
    tonight_payload = getattr(tonight, 'payload', None) if tonight is not None else None
    if tonight_payload is None and isinstance(tonight, dict):
        tonight_payload = tonight.get('payload', tonight)
    return {
        'data_through': str(snapshot.data_through),
        'dashboard_payload_digest': _digest(_normalize(
            {k: v for k, v in payload.items() if k != TEAM_BOARD_PACKAGE_KEY}
        )),
        'team_board_package_digest': _digest(_normalize(package)),
        'team_board_teams': len(by_team),
        'per_team_board_digests': {
            str(team_id): _digest(_normalize(item)) for team_id, item in sorted(by_team.items())
        },
        'what_changed_digest': _digest(_normalize({
            'league': payload.get('what_changed_since_yesterday'),
            'teams': {
                team_id: item.get('frozen_what_changed') for team_id, item in by_team.items()
            },
        })),
        'team_state_by_team_digest': _digest(_normalize({
            'landscape': team_states,
            'receipts': package.get('frozen_team_state_by_team_id'),
        })),
        'rest_status_digest': _digest(_normalize({
            team_id: [item.get('rest_status'), item.get('recent_usage_rest')]
            for team_id, item in by_team.items()
        })),
        'rotation_context_digest': _digest(_normalize({
            team_id: [item.get('frozen_rotation_impact'), item.get('rotation_support_pressure')]
            for team_id, item in by_team.items()
        })),
        'artifact_count': len(artifacts),
        'artifact_digest': _digest(_normalize([
            [row.team_id, row.artifact_type, row.payload] for row in artifacts
        ])),
        'proof_present': proof is not None,
        'proof_digest': _digest(_normalize(
            proof.proof
        )) if proof is not None else None,
        'tonight_v1_digest': _digest(_normalize(tonight_payload)) if tonight_payload else None,
    }


def configure_harness_app(app):
    """Production publication settings on a disposable test app."""
    app.config['TRUSTED_PUBLIC_SERVING_ENABLED'] = True
    app.config['SHARE_ARTIFACT_AUTOGENERATION_ENABLED'] = True
    app.config['TONIGHT_V1_PROJECTION_ENABLED'] = True
    app.config['TEAM_STATE_PUBLICATION_PROOF_REQUIRED'] = True
    return app


def run_harness(app, *, shape=None):
    """Seed, then publish twice (prior + measured) inside ``app``'s context.

    The caller owns the app context and a disposable, freshly created schema.
    """
    from services import public_serving_authority
    from services.availability_reference_date import product_current_date
    from utils.db import db

    counters = _Counters()
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(counters)
    root.setLevel(logging.INFO)
    for noisy in ('sqlalchemy', 'urllib3', 'werkzeug'):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    try:
        results = {}
        reference_date = product_current_date()
        started = perf_counter()
        results['fixture'] = _seed(reference_date, shape)
        results['fixture']['seed_seconds'] = round(perf_counter() - started, 1)
        db.session.expunge_all()
        assert public_serving_authority.install_public_serving_authority(app)
        checkpoints = {'reference_date': reference_date}
        results['prior'] = _run_once(app, 'prior', counters, checkpoints)
        gc.collect()
        results['measured'] = _run_once(app, 'measured', counters, checkpoints)
        results['memory_telemetry'] = list(counters.memory_lines)
        return results
    finally:
        root.removeHandler(counters)
        root.setLevel(previous_level)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--json', help='write results to this path')
    parser.add_argument(
        '--no-allocator-policy', action='store_true',
        help='skip the production allocator policy (for comparison runs)',
    )
    args = parser.parse_args(argv)
    allocator = {'configured': False, 'reason': 'not_requested'}
    if not args.no_allocator_policy:
        try:
            from services.process_memory import configure_allocator_for_large_buffers
            allocator = configure_allocator_for_large_buffers()
        except ImportError:
            allocator = {'configured': False, 'reason': 'unavailable_in_this_tree'}

    url = os.environ.get('DATABASE_URL', '')
    from tests.db_config import assert_disposable_test_target, create_test_schema

    assert_disposable_test_target(url, operation='daily publication memory harness')
    os.environ['APP_ENV'] = 'test'
    app = configure_harness_app(importlib.import_module('app').create_app('test'))
    from utils.db import db

    results = {'baseline_rss_mb': rss_mb(), 'allocator_policy': allocator}
    with app.app_context():
        assert_disposable_test_target(
            db.engine.url.render_as_string(hide_password=False),
            operation='daily publication memory harness engine',
        )
        create_test_schema(app)
        results.update(run_harness(app))
        db.session.remove()
    text = json.dumps(results, indent=2, sort_keys=True, default=str)
    if args.json:
        with open(args.json, 'w', encoding='utf-8') as handle:
            handle.write(text)
    print(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
