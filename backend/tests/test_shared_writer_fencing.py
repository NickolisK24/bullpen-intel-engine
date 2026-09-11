"""Real PostgreSQL statements exercise the older-binary compatibility boundary."""

import importlib.util
import json
import subprocess
import sys
from types import ModuleType
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from datetime import date, timedelta

import pytest
from sqlalchemy import text
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from models.compatibility_write_event import CompatibilityWriteEvent
from models.pitcher import Pitcher
from models.roster_status_snapshot import RosterStatusSnapshot
from services.roster_transaction_authority import reconcile_team_roster
from tests.test_roster_transaction_authority import app, RosterClient, _entry, SLATE
from tests.test_final_game_reconciliation import _seed_schedule, _bundle, _boxscore, _game, _pbp, _claimed_job, GAME_PK, GAME_DATE
from services.final_game_reconciliation import reconcile_final_game
from models.game_log import GameLog
from utils.db import db
from utils.time import utc_now_naive
from tests.test_transaction_ingestion import FakeTransactionClient, _tx, _pitcher as transaction_pitcher
from services.transaction_ingestion import sync_transactions
from models.player_transaction import PlayerTransaction
from models.roster_membership import PlayerTransactionVersion


@pytest.fixture
def guarded(app):
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('Database triggers require PostgreSQL')
    path = Path(__file__).resolve().parents[1] / 'migrations/versions/e3f6a9b2c5d8_fence_compatibility_writers.py'
    spec = importlib.util.spec_from_file_location('writer_fence_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    db.session.rollback()
    with db.engine.begin() as connection:
        connection.execute(text(migration.POSTGRES_GUARDS))
    try:
        yield app
    finally:
        db.session.remove()
        with db.engine.begin() as connection:
            for name in ('pitcher_projection', 'roster_snapshot', 'final_compatibility', 'game_observation', 'transaction_projection', 'schedule_projection'):
                connection.execute(text(f'DROP FUNCTION baseballos_guard_{name}() CASCADE'))


def test_old_binary_cannot_overwrite_governed_pitcher_projection(guarded):
    entry = {**_entry(681895, 'Evan Sisk'), 'parentTeamId': 134}
    reconcile_team_roster(134, SLATE, client=RosterClient({'40Man': [entry]}))
    pitcher_id = Pitcher.query.one().id
    db.session.rollback()
    # Raw SQL deliberately bypasses every changed Python function, just as
    # an existing deployed process would.
    with db.engine.begin() as connection:
        connection.execute(text("""
            UPDATE pitchers SET team_id=484, active=false,
              team_assignment_source='mlb_stats_api:team_assignment_sync:active'
            WHERE id=:id
        """), {'id': pitcher_id})
    pitcher = db.session.get(Pitcher, pitcher_id)
    assert pitcher.team_id == 134
    assert pitcher.active is True
    assert CompatibilityWriteEvent.query.filter_by(outcome='stale_suppressed').count() == 1


def test_old_binary_cannot_revise_sp_roster_snapshot(guarded):
    entry = {**_entry(681895, 'Evan Sisk'), 'parentTeamId': 134}
    reconcile_team_roster(134, SLATE, client=RosterClient({'40Man': [entry]}))
    snapshot = RosterStatusSnapshot.query.one()
    snapshot_id, status = snapshot.id, snapshot.roster_status
    db.session.rollback()
    with db.engine.begin() as connection:
        connection.execute(text("UPDATE roster_status_snapshots SET roster_status='unknown' WHERE id=:id"),
                           {'id': snapshot_id})
    assert db.session.get(RosterStatusSnapshot, snapshot_id).roster_status == status
    assert CompatibilityWriteEvent.query.filter_by(resource_type='roster_snapshot').count() == 1


def test_delayed_legacy_assignment_cannot_undo_mlb_projection(guarded):
    pitcher = Pitcher(mlb_id=681895, full_name='Evan Sisk', team_id=134, active=True)
    db.session.add(pitcher)
    db.session.commit()
    pitcher_id = pitcher.id
    db.session.rollback()
    captured, reconciled = Event(), Event()
    engine = db.engine

    def legacy():
        with engine.begin() as connection:
            connection.execute(text('SELECT team_id FROM pitchers WHERE id=:id'), {'id': pitcher_id})
            captured.set()
            assert reconciled.wait(10)
            connection.execute(text("UPDATE pitchers SET team_id=484, team_assignment_source='legacy' WHERE id=:id"),
                               {'id': pitcher_id})

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(legacy)
        assert captured.wait(10)
        reconcile_team_roster(134, SLATE, client=RosterClient({'40Man': [
            {**_entry(681895, 'Evan Sisk'), 'parentTeamId': 134},
        ]}))
        reconciled.set()
        future.result(timeout=10)
    assert db.session.get(Pitcher, pitcher_id).team_id == 134


def test_historical_roster_cannot_replace_newer_current_pitcher_projection(guarded):
    player = _entry(681895, 'Evan Sisk')
    reconcile_team_roster(134, SLATE, client=RosterClient({'40Man': [player]}))
    reconcile_team_roster(134, SLATE + timedelta(days=1), client=RosterClient())
    reconcile_team_roster(147, SLATE + timedelta(days=1), client=RosterClient({'40Man': [player]}))
    # A changed older source is still meaningful dated evidence. Its current
    # pitcher compatibility projection must not undo the later club source.
    corrected_old = {**player, 'jerseyNumber': '99'}
    result = reconcile_team_roster(134, SLATE, client=RosterClient({'40Man': [corrected_old]}))
    db.session.expire_all()
    assert result['write_outcome'] == 'stale_suppressed'
    assert Pitcher.query.one().team_id == 147
    from services.roster_transaction_authority import current_memberships
    assert current_memberships(134, 'forty_man_roster') == []


def test_same_club_acquisition_is_ordered_without_blocking_other_clubs(guarded):
    from services.roster_transaction_authority import _lock_team

    same_started, same_fetched, other_fetched = Event(), Event(), Event()

    class RecordingClient(RosterClient):
        def get_team_roster_with_completeness(self, team_id, **kwargs):
            (same_fetched if team_id == 134 else other_fetched).set()
            return super().get_team_roster_with_completeness(team_id, **kwargs)

    def reconcile(team):
        with guarded.app_context():
            if team == 134:
                same_started.set()
            return reconcile_team_roster(team, SLATE, client=RecordingClient())

    _lock_team(134)
    with ThreadPoolExecutor(max_workers=2) as pool:
        same = pool.submit(reconcile, 134)
        other = pool.submit(reconcile, 147)
        try:
            assert same_started.wait(5)
            assert other_fetched.wait(5)
            assert other.result(timeout=5)['authoritative']
            assert not same_fetched.is_set()
        finally:
            db.session.rollback()
        assert same.result(timeout=10)['authoritative']
        assert same_fetched.is_set()


def test_expected_suppression_does_not_hide_real_ownership_conflict(guarded):
    from services.compatibility_writer_health import compatibility_writer_health

    reconcile_team_roster(134, SLATE, client=RosterClient({'40Man': [_entry(681895, 'Evan Sisk')]}))
    pitcher_id = Pitcher.query.one().id
    db.session.rollback()
    with db.engine.begin() as connection:
        connection.execute(text('UPDATE pitchers SET team_id=484 WHERE id=:id'), {'id': pitcher_id})
    healthy = compatibility_writer_health()
    assert healthy['recent_suppressions']['stale_suppressed'] == 1
    assert healthy['unresolved_ownership_conflicts'] == 0
    # Two independently retained club claims are an unresolved source conflict,
    # even though the current pitcher projection happens to match one of them.
    reconcile_team_roster(147, SLATE, client=RosterClient({'40Man': [_entry(681895, 'Evan Sisk')]}))
    assert compatibility_writer_health()['conflicting_mlb_memberships'] == 1


def test_delayed_legacy_gamelog_update_cannot_replace_corrected_final(guarded):
    _seed_schedule()
    reconcile_final_game(_bundle())
    row = GameLog.query.join(Pitcher).filter(Pitcher.mlb_id == 303).one()
    row_id = row.id
    db.session.rollback()
    read_old, correction_committed = Event(), Event()
    engine = db.engine

    def old_binary():
        with engine.begin() as connection:
            prior = connection.execute(text('SELECT pitches_thrown FROM game_logs WHERE id=:id'),
                                       {'id': row_id}).scalar_one()
            read_old.set()
            assert correction_committed.wait(10)
            connection.execute(text('UPDATE game_logs SET pitches_thrown=:pitches WHERE id=:id'),
                               {'id': row_id, 'pitches': prior})

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(old_binary)
        assert read_old.wait(10)
        reconcile_final_game(_bundle(box=_boxscore(home_reliever_pitches=19), correction=True))
        correction_committed.set()
        future.result(timeout=10)
    db.session.expire_all()
    assert db.session.get(GameLog, row_id).pitches_thrown == 19
    assert GameLog.query.filter_by(mlb_game_pk=GAME_PK).count() == 4
    assert CompatibilityWriteEvent.query.filter_by(outcome='final_superseded').count() == 1


def test_unrelated_game_locks_proceed_concurrently(guarded):
    from services.semantic_write_fencing import lock_game

    first_locked, second_locked, release = Event(), Event(), Event()

    def hold_first():
        with guarded.app_context():
            lock_game(823413)
            first_locked.set()
            assert release.wait(10)
            db.session.rollback()

    def hold_second():
        with guarded.app_context():
            lock_game(823414)
            second_locked.set()
            db.session.rollback()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(hold_first)
        assert first_locked.wait(10)
        second = pool.submit(hold_second)
        try:
            assert second_locked.wait(5), 'unrelated game was serialized behind first game'
        finally:
            release.set()
        first.result(timeout=10)
        second.result(timeout=10)


def test_delayed_final_owner_cannot_replace_corrected_final(guarded):
    _seed_schedule()
    original = _bundle()
    reconcile_final_game(original)
    # The delayed worker holds the original retained evidence, not a freshly
    # manufactured later observation of the old payload.
    for observation in (original.finality_observation, original.boxscore_observation,
                        original.play_by_play_observation):
        _ = observation.id, observation.version_number, observation.source_subject_id
        db.session.expunge(observation)
    db.session.rollback()
    started, corrected = Event(), Event()

    def delayed():
        with guarded.app_context():
            started.set()
            assert corrected.wait(10)
            result = reconcile_final_game(original)
            return result.write_outcome

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(delayed)
        assert started.wait(10)
        reconcile_final_game(_bundle(box=_boxscore(home_reliever_pitches=19), correction=True))
        corrected.set()
        assert future.result(timeout=10) == 'corrected_final_superseded'
    db.session.expire_all()
    assert GameLog.query.join(Pitcher).filter(Pitcher.mlb_id == 303).one().pitches_thrown == 19


def test_final_change_during_fetch_requires_reacquisition_not_arrival_order(guarded):
    from dataclasses import replace
    from models.final_game_reconciliation import FinalGameVersion
    from models.sync_job import SyncJob
    from services.final_game_reconciliation import execute_final_game_job

    _seed_schedule()
    prior = reconcile_final_game(_bundle()).game_version.id
    reconcile_final_game(_bundle(box=_boxscore(home_reliever_pitches=19), correction=True))
    # The old HTTP response is retained after the correction. Its observation
    # number is later, but the captured canonical predecessor is now stale.
    delayed = replace(_bundle(correction=True), expected_final_version_id=prior,
                      has_acquisition_fence=True)
    job = _claimed_job()
    result = execute_final_game_job(job, acquirer=lambda *args, **kwargs: delayed)
    assert result['write_outcome'] == 'source_reacquisition_required'
    replacement = db.session.get(SyncJob, result['downstream_job_id'])
    assert replacement.details_json['reason'] == 'authority_changed_during_acquisition'
    assert FinalGameVersion.query.count() == 2
    assert GameLog.query.join(Pitcher).filter(Pitcher.mlb_id == 303).one().pitches_thrown == 19


def test_delayed_live_owner_cannot_recreate_current_after_final(guarded):
    from services.live_game_delta import _reconcile_projection
    from models.live_game_delta import ProvisionalPitchingAppearanceState

    _seed_schedule()
    started, finalized = Event(), Event()

    def delayed():
        with guarded.app_context():
            # Captured live work enters its mutation boundary after Final.
            state = SimpleNamespace(mlb_game_pk=GAME_PK)
            started.set()
            assert finalized.wait(10)
            result = _reconcile_projection(
                state, [{'pitcher_mlb_id': 303}], SLATE, None, None, utc_now_naive(),
            )
            db.session.commit()
            return result

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(delayed)
        assert started.wait(10)
        reconcile_final_game(_bundle())
        finalized.set()
        assert future.result(timeout=10) == ([], set(), set())
    assert ProvisionalPitchingAppearanceState.query.filter_by(is_current=True).count() == 0
    assert GameLog.query.filter_by(mlb_game_pk=GAME_PK).count() == 4


def test_old_binary_game_row_lock_never_waits_in_reverse_order(guarded):
    from services.semantic_write_fencing import lock_game
    from sqlalchemy.exc import OperationalError

    _seed_schedule()
    reconcile_final_game(_bundle())
    row_id = GameLog.query.first().id
    db.session.rollback()
    lock_game(GAME_PK)
    engine = db.engine

    def old_binary():
        with engine.begin() as connection:
            connection.execute(text('UPDATE game_logs SET pitches_thrown=1 WHERE id=:id'), {'id': row_id})

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(old_binary)
        try:
            with pytest.raises(OperationalError, match='semantic fence busy'):
                future.result(timeout=5)
        finally:
            db.session.rollback()


def test_accepted_legacy_revision_cannot_keep_prior_source_identity(guarded):
    from services import game_change_detection as detection
    from models.game_observation_state import GameObservationState
    from tests.test_game_change_detection import _feed, GAME_PK as observed_game

    first = detection.observe_game_change(observed_game, payload=_feed())
    changed = _feed(timestamp='20260826_010100', outs=2)
    facts = detection.canonicalize_game_observation(changed, expected_game_pk=observed_game)
    db.session.rollback()
    with db.engine.begin() as connection:
        connection.execute(text('''
            UPDATE game_observation_states
            SET previous_observation_fingerprint=observation_fingerprint,
                observation_fingerprint=:fingerprint, observation=CAST(:facts AS json),
                source_observed_at='2026-08-26 01:01:00'
            WHERE mlb_game_pk=:game
        '''), {'fingerprint': detection.observation_fingerprint(facts),
               'facts': json.dumps(facts), 'game': observed_game})
    assert GameObservationState.query.one().source_observation_id is None
    replay = detection.observe_game_change(observed_game, payload=changed)
    assert replay.classification == detection.UNCHANGED
    assert replay.source_observation_id != first.source_observation_id
    assert GameObservationState.query.one().source_observation_id == replay.source_observation_id
    from services.compatibility_writer_health import compatibility_writer_health
    assert compatibility_writer_health()['observation_lineage_conflicts'] == 0
    # Pre-deployment rows can already contain the inherited wrong link.
    row = GameObservationState.query.one()
    row.source_observation_id = first.source_observation_id
    db.session.commit()
    assert compatibility_writer_health()['observation_lineage_conflict_game_pks'] == [observed_game]
    detection.observe_game_change(observed_game, payload=changed)
    assert compatibility_writer_health()['observation_lineage_conflicts'] == 0


def test_overlapping_transaction_windows_cannot_restore_stale_event(guarded):
    transaction_pitcher()
    start, end = date(2026, 6, 27), date(2026, 7, 4)
    sync_transactions(client=FakeTransactionClient([_tx()]), start_date=start, end_date=end)
    waiting, corrected = Event(), Event()

    class DelayedClient(FakeTransactionClient):
        def get_transactions(self, **kwargs):
            waiting.set()
            assert corrected.wait(10)
            return super().get_transactions(**kwargs)

    def delayed():
        with guarded.app_context():
            return sync_transactions(client=DelayedClient([_tx()]),
                                     start_date=date(2026, 7, 1), end_date=end)

    db.session.rollback()
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(delayed)
        assert waiting.wait(10)
        sync_transactions(client=FakeTransactionClient([_tx(transaction_type_code='OPT')]),
                          start_date=start, end_date=end)
        corrected.set()
        result = future.result(timeout=10)
    db.session.expire_all()
    assert result['records_stale_suppressed'] == 1
    assert PlayerTransaction.query.one().transaction_type_code == 'OPT'
    assert PlayerTransaction.query.one().current_version_number == 2
    assert PlayerTransactionVersion.query.count() == 2


def test_old_binary_transaction_update_cannot_replace_owned_event(guarded):
    transaction_pitcher()
    sync_transactions(client=FakeTransactionClient([_tx()]),
                      start_date=date(2026, 6, 27), end_date=date(2026, 7, 4))
    row_id = PlayerTransaction.query.one().id
    db.session.rollback()
    with db.engine.begin() as connection:
        connection.execute(text("UPDATE player_transactions SET transaction_type_code='OPT' WHERE id=:id"),
                           {'id': row_id})
    assert db.session.get(PlayerTransaction, row_id).transaction_type_code == 'RECALL'
    assert CompatibilityWriteEvent.query.filter_by(resource_type='transaction').count() == 1


def test_health_detects_unique_transaction_with_wrong_current_facts(guarded):
    from services.compatibility_writer_health import compatibility_writer_health
    from services.semantic_write_fencing import lock_transaction, authorize_transaction_projection

    transaction_pitcher()
    sync_transactions(client=FakeTransactionClient([_tx()]),
                      start_date=date(2026, 6, 27), end_date=date(2026, 7, 4))
    assert compatibility_writer_health()['transaction_projection_conflicts'] == 0
    transaction = PlayerTransaction.query.one()
    lock_transaction(transaction.transaction_key)
    authorize_transaction_projection(transaction.transaction_key)
    # Model an owner defect: the row was changed without recording a version.
    transaction.transaction_type_code = 'OPT'
    db.session.commit()
    report = compatibility_writer_health()
    assert report['transaction_projection_conflict_ids'] == [transaction.id]
    assert report['unresolved_ownership_conflicts'] == 1


def test_legacy_event_change_during_first_sp_acquisition_is_not_overwritten(guarded):
    from services.transaction_ingestion import read_transaction_values

    transaction_pitcher()
    start, end = date(2026, 6, 27), date(2026, 7, 4)
    values, error = read_transaction_values(_tx(), start_date=start, end_date=end)
    assert error is None
    row = PlayerTransaction(**values)
    db.session.add(row)
    db.session.commit()
    row_id = row.id
    db.session.rollback()
    waiting, corrected = Event(), Event()

    class DelayedClient(FakeTransactionClient):
        def get_transactions(self, **kwargs):
            waiting.set()
            assert corrected.wait(10)
            return super().get_transactions(**kwargs)

    def delayed():
        with guarded.app_context():
            return sync_transactions(client=DelayedClient([_tx()]), start_date=start, end_date=end)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(delayed)
        assert waiting.wait(10)
        with db.engine.begin() as connection:
            connection.execute(text("UPDATE player_transactions SET transaction_type_code='OPT' WHERE id=:id"),
                               {'id': row_id})
        corrected.set()
        assert future.result(timeout=10)['records_stale_suppressed'] == 1
    assert db.session.get(PlayerTransaction, row_id).transaction_type_code == 'OPT'
    assert PlayerTransactionVersion.query.count() == 0


def test_legacy_postgame_and_pbp_consume_sp_owner_without_false_correction(guarded):
    from services.sync import process_completed_game_for_postgame_refresh
    from services.play_by_play_foundation import process_final_play_by_play_foundation
    from models.final_game_reconciliation import FinalGameVersion
    from models.sync_failure import SyncFailure

    _seed_schedule()
    reconcile_final_game(_bundle())
    reconcile_final_game(_bundle(box=_boxscore(home_reliever_pitches=19), correction=True))
    core = process_completed_game_for_postgame_refresh(
        _game(), schedule_date=GAME_DATE, boxscore=_boxscore(), force=True,
    )
    pbp = process_final_play_by_play_foundation(
        _game(), boxscore=_boxscore(), play_by_play=_pbp(), game_date=GAME_DATE,
    )
    db.session.commit()
    assert core['logs_corrected'] == 0
    assert core['correction_attempts_failed'] == 0
    assert pbp['write_outcome'] == 'final_superseded'
    assert SyncFailure.query.count() == 0
    assert FinalGameVersion.query.filter_by(is_current=True).one().version_number == 2
    assert GameLog.query.join(Pitcher).filter(Pitcher.mlb_id == 303).one().pitches_thrown == 19


def test_deployed_legacy_code_cannot_restore_prior_final(guarded, monkeypatch):
    from models.final_game_reconciliation import FinalGameVersion
    from models.sync_failure import SyncFailure

    legacy_sha = 'aabe4b988fbfa4b5fedcf5da9dcecafa9142ed65'
    root = Path(__file__).resolve().parents[2]

    def load(relative, name):
        source = subprocess.run(['git', 'show', f'{legacy_sha}:{relative}'], cwd=root,
                                check=True, capture_output=True, text=True, encoding='utf-8').stdout
        module = ModuleType(name)
        module.__file__ = str(root / relative)
        monkeypatch.setitem(sys.modules, name, module)
        exec(compile(source, module.__file__, 'exec'), module.__dict__)
        return module

    legacy_sync = load('backend/services/sync.py', 'deployed_legacy_sync')
    legacy_pbp = load('backend/services/play_by_play_foundation.py', 'deployed_legacy_pbp')
    _seed_schedule()
    reconcile_final_game(_bundle())
    reconcile_final_game(_bundle(box=_boxscore(home_reliever_pitches=19),
                                pbp=_pbp(pitch_speed=96), correction=True))
    legacy_sync.process_completed_game_for_postgame_refresh(
        _game(), schedule_date=GAME_DATE, boxscore=_boxscore(), force=True,
    )
    pbp = legacy_pbp.process_final_play_by_play_foundation(
        _game(), boxscore=_boxscore(), play_by_play=_pbp(), game_date=GAME_DATE,
    )
    db.session.commit()
    assert pbp['observation_rejected'] is True
    assert SyncFailure.query.count() == 0
    assert FinalGameVersion.query.filter_by(is_current=True).one().version_number == 2
    assert GameLog.query.join(Pitcher).filter(Pitcher.mlb_id == 303).one().pitches_thrown == 19


def test_repeated_transaction_facts_have_monotonic_correction_versions(guarded):
    transaction_pitcher()
    for code in ('RECALL', 'OPT', 'RECALL'):
        sync_transactions(client=FakeTransactionClient([_tx(transaction_type_code=code)]),
                          start_date=date(2026, 6, 27), end_date=date(2026, 7, 4))
    versions = PlayerTransactionVersion.query.order_by(PlayerTransactionVersion.version_number).all()
    assert [row.version_number for row in versions] == [1, 2, 3]
    assert versions[0].fact_fingerprint == versions[2].fact_fingerprint
    assert versions[2].predecessor_version_id == versions[1].id
    assert PlayerTransaction.query.one().current_version_number == 3


def test_migration_upgrade_empty_downgrade_and_history_guard(app):
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL ownership migration')
    path = Path(__file__).resolve().parents[1] / 'migrations/versions/e3f6a9b2c5d8_fence_compatibility_writers.py'
    spec = importlib.util.spec_from_file_location('writer_migration_rehearsal', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    db.session.rollback()
    try:
        with db.engine.begin() as connection:
            migration.op = Operations(MigrationContext.configure(connection))
            CompatibilityWriteEvent.__table__.drop(connection)
            with migration.op.batch_alter_table('player_transaction_versions') as batch:
                batch.drop_index('ix_player_transaction_versions_transaction_fingerprint')
                batch.create_unique_constraint('uq_player_transaction_versions_transaction_fingerprint',
                                                ['player_transaction_id', 'fact_fingerprint'])
                batch.alter_column('source_observation_id', existing_type=sa.Integer(), nullable=False)
            migration.upgrade()
            assert next(column for column in sa.inspect(connection).get_columns('player_transaction_versions')
                        if column['name'] == 'source_observation_id')['nullable']
            migration.downgrade()
            migration.upgrade()
            with connection.begin_nested() as savepoint:
                connection.execute(CompatibilityWriteEvent.__table__.insert().values(
                    resource_type='game', resource_key='823413', outcome='stale_suppressed',
                    details_json={}, created_at=utc_now_naive(),
                ))
                with pytest.raises(RuntimeError, match='discard retained history'):
                    migration.downgrade()
                savepoint.rollback()
    finally:
        db.session.remove()
        with db.engine.begin() as connection:
            for name in ('pitcher_projection', 'roster_snapshot', 'final_compatibility', 'game_observation',
                         'transaction_projection', 'schedule_projection'):
                connection.execute(text(f'DROP FUNCTION IF EXISTS baseballos_guard_{name}() CASCADE'))


def test_natural_game_823413_preserves_final_lines_and_single_counted_workload(guarded):
    from services.final_game_reconciliation import acquire_final_game_sources
    from services.schedule_ingestion import ingest_games
    from services.incremental_workload_rest import _compute_pitcher_workload_rest
    from services.source_observations import build_source_identity, record_source_observation
    from models.live_game_delta import ProvisionalPitchingAppearanceState

    receipt = json.loads((Path(__file__).parent / 'fixtures/audit_r2_game_823413.json').read_text(encoding='utf-8'))
    core = receipt['retained_core_sources'][0]
    through = date.fromisoformat(receipt['through_date'])
    for pitcher_id in sorted({row['pitcher_id'] for row in receipt['game_logs']}):
        row = next(row for row in receipt['game_logs'] if row['pitcher_id'] == pitcher_id)
        db.session.add(Pitcher(id=pitcher_id, mlb_id=row['pitcher_mlb_id'], full_name=row['full_name'],
                              team_id=row['appearance_team_id'], active=True, position='P'))
    db.session.flush()
    for row in receipt['game_logs']:
        if row['mlb_game_pk'] == 823413:
            continue
        outs = row['innings_pitched_outs']
        db.session.add(GameLog(
            pitcher_id=row['pitcher_id'], mlb_game_pk=row['mlb_game_pk'],
            game_date=date.fromisoformat(row['game_date']), game_type='R',
            appearance_team_id=row['appearance_team_id'], games_started=row['games_started'],
            pitches_thrown=row['pitches_thrown'], innings_pitched_outs=outs,
            innings_pitched=outs / 3, batters_faced=row['batters_faced'],
        ))
    db.session.commit()
    ingest_games(core['finality'])

    class RetainedClient:
        def get_schedule(self, **kwargs):
            return core['finality']

        def get_game_boxscore(self, game_pk):
            return core['boxscore']

        def get_game_play_by_play(self, game_pk):
            # Optional PBP is deliberately withheld; this fixture certifies
            # retained numerical core authority, not manufactured event detail.
            return {}

    observation = record_source_observation(
        identity=build_source_identity(provider='mlb_stats_api', source_domain='live_feed',
            endpoint='/game/823413/feed/live', subject_type='game', subject_key='823413',
            request_parameters={'gamePk': 823413}, baseball_date=through),
        payload=receipt['provisional'], completeness='complete', payload_schema_version=1,
        payload_kind='normalized_json', record_count=7,
    ).observation
    for value in receipt['provisional']:
        db.session.add(ProvisionalPitchingAppearanceState(
            game_pk=823413, baseball_date=through, pitcher_id=value['pitcher_id'],
            pitcher_mlb_id=value['pitcher_mlb_id'], team_id_at_appearance=value['team_id_at_appearance'],
            side=value['side'], appearance_role=value['appearance_role'], outing_status=value['outing_status'],
            pitches_thrown=value['pitches_thrown'], outs_recorded=value['outs_recorded'],
            batters_faced=value['batters_faced'], first_observation_id=observation.id,
            latest_observation_id=observation.id, fact_fingerprint=f"fixture:{value['id']}",
            fingerprint_version='live-appearance-v1', completeness='complete',
            first_seen_at=utc_now_naive(), latest_seen_at=utc_now_naive(),
        ))
    db.session.commit()
    bundle = acquire_final_game_sources(823413, through, client=RetainedClient())
    reconcile_final_game(bundle)
    assert ProvisionalPitchingAppearanceState.query.filter_by(is_current=True).count() == 0
    assert GameLog.query.filter_by(mlb_game_pk=823413).count() == 7
    expected = {row['pitcher_id']: row for row in receipt['game_logs'] if row['mlb_game_pk'] == 823413}
    for row in GameLog.query.filter_by(mlb_game_pk=823413):
        assert (row.pitches_thrown, row.innings_pitched_outs, row.batters_faced) == tuple(
            expected[row.pitcher_id][key] for key in ('pitches_thrown', 'innings_pitched_outs', 'batters_faced'))
    reconcile_final_game(bundle)
    for pitcher_id, (pitches, appearances) in {
        230: (47, 3), 232: (62, 4), 241: (51, 4), 615: (55, 4), 617: (50, 3),
    }.items():
        workload = _compute_pitcher_workload_rest(
            pitcher_id, data_through=through, availability_reference_date=through + timedelta(days=1),
        )['fatigue_workload']
        assert workload['pitches_last_7_days'] == pitches
        assert workload['appearances_last_7'] == appearances
