from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from threading import Barrier
from types import SimpleNamespace

import pytest
from flask import Flask

from models.canonical_impact import CanonicalImpactPlan
from models.derived_intelligence import (
    DerivedCohortInput,
    DerivedCohortSnapshot,
    DerivedIntelligenceCohort,
    DerivedIntelligenceCohortDomain,
)
from models.final_game_reconciliation import FinalGameVersion, FinalPitchingAppearanceVersion
from models.pitcher import Pitcher
from models.pregame_context import GamePregameContextVersion
from models.source_observation import SourceObservation, SourceSubject
from models.sync_job import SyncJob
from services.derived_intelligence import (
    COHORT_SCHEMA_VERSION,
    CohortStatus,
    _DefaultDomainExecutor,
    dependency_closure,
    execute_derived_intelligence_plan,
    run_derived_intelligence_worker_once,
)
from services.sync_jobs import JobScopeType, JobType, enqueue_job
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


GAME_DATE = date(2026, 9, 8)


def _canonical_pair():
    """Persist V1 and a noncurrent correction without changing V1 history."""
    first, _, pitcher = _final_authority(_observation('reference-version'), version=1)
    db.session.commit()
    values = {column.name: getattr(first, column.name)
              for column in FinalGameVersion.__table__.columns if column.name != 'id'}
    values.update(version_number=2, predecessor_version_id=first.id,
                  is_current=False, fact_fingerprint='correction'.ljust(64, '0'))
    with db.engine.begin() as writer:
        second = writer.execute(FinalGameVersion.__table__.insert().values(**values)
                                .returning(FinalGameVersion.id)).scalar_one()
    return first.id, second, pitcher.id


def _advance_final(connection, first, second):
    connection.execute(FinalGameVersion.__table__.update()
                       .where(FinalGameVersion.id == first).values(is_current=False))
    connection.execute(FinalGameVersion.__table__.update()
                       .where(FinalGameVersion.id == second).values(is_current=True))


def test_canonical_reader_first_orders_correction_after_completion(app, monkeypatch):
    from threading import Event
    from sqlalchemy import text
    from services import derived_intelligence as derived
    from services.semantic_write_fencing import GAME_LOCK_NAMESPACE
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL cross-session canonical fence')
    first, second, pitcher = _canonical_pair()
    plan = _plan(domains=('game_context',), pitchers=(pitcher,))
    engine = db.engine
    entered, committed = Event(), Event()

    def correct():
        with engine.begin() as writer:
            entered.set()
            writer.execute(text('SELECT pg_advisory_xact_lock(:key)'),
                           {'key': GAME_LOCK_NAMESPACE + 777123})
            _advance_final(writer, first, second)
        committed.set()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = None
        persist = derived._persist_snapshots

        def boundary(cohort, snapshots):
            nonlocal future
            assert snapshots['game']['777123']['game_context']['final_game_version_id'] == first
            future = pool.submit(correct)
            assert entered.wait(5)
            assert not committed.wait(0.1)
            persist(cohort, snapshots)

        monkeypatch.setattr(derived, '_persist_snapshots', boundary)
        try:
            result = execute_derived_intelligence_plan(plan.id, publication_candidate_enabled=False,
                                                      commit=False)
            assert not committed.is_set()
            db.session.commit()
        finally:
            db.session.rollback()
        future.result(timeout=5)
    assert result.cohort.status == 'complete'
    manifest = result.cohort.input_manifest_json
    assert manifest[-1]['context']['selectors']['canonical_versions']['final']['777123']['id'] == first
    assert not derived.cohort_inputs_are_current(result.cohort, plan)
    assert result.cohort.status == 'complete'
    assert result.cohort.input_manifest_json == manifest


def test_canonical_writer_first_stales_and_retry_uses_correction(app):
    from services import derived_intelligence as derived
    first, second, pitcher = _canonical_pair()
    cached = db.session.get(FinalGameVersion, first)
    plan = _plan(domains=('game_context',), pitchers=(pitcher,))

    def correct():
        with db.engine.begin() as writer:
            _advance_final(writer, first, second)
        assert cached.is_current  # Deliberately stale identity-map instance.

    stale = execute_derived_intelligence_plan(plan.id, publication_candidate_enabled=False,
                                             before_revalidate=correct).cohort
    assert stale.status == 'stale'
    old = stale.input_manifest_json
    rebuilt = execute_derived_intelligence_plan(plan.id, publication_candidate_enabled=False).cohort
    assert rebuilt.id != stale.id and rebuilt.status == 'complete'
    assert rebuilt.input_manifest_json[-1]['context']['selectors']['canonical_versions']['final']['777123']['id'] == second
    assert derived.cohort_inputs_are_current(rebuilt, plan)
    assert stale.input_manifest_json == old


def test_canonical_direct_writer_cannot_bypass_shared_completion(app):
    from sqlalchemy.exc import DBAPIError
    from services.derived_intelligence import _capture_cohort_context
    from services.selector_generation_fencing import acquire_completion_fences
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL direct writer guard')
    first, second, pitcher = _canonical_pair()
    context = _capture_cohort_context(_plan(domains=('game_context',), pitchers=(pitcher,)))
    acquire_completion_fences(context, 'final')
    with pytest.raises(DBAPIError) as rejected:
        with db.engine.begin() as writer:
            _advance_final(writer, first, second)
    assert rejected.value.orig.pgcode == '40001'
    db.session.rollback()
    with db.engine.begin() as writer:
        _advance_final(writer, first, second)


def test_reference_midnight_is_frozen_and_new_capture_advances(app, monkeypatch):
    from datetime import timezone
    from services import availability_reference_date as dates, derived_intelligence as derived
    from services.public_pitcher_current import _reference_date
    resolve = dates.resolve_product_day
    monkeypatch.setattr(dates, 'resolve_product_day', lambda: resolve(
        datetime(2026, 9, 9, 3, 59, 59, tzinfo=timezone.utc)))
    plan = _plan(domains=('game_context',))
    first = derived._capture_cohort_context(plan)
    assert first.product_date == date(2026, 9, 8)
    monkeypatch.setattr(dates, 'resolve_product_day', lambda: resolve(
        datetime(2026, 9, 9, 4, 0, 1, tzinfo=timezone.utc)))
    assert _reference_date({}, first.product_date) == date(2026, 9, 8)
    revalidated = derived._capture_cohort_context(plan, recorded_context=first.manifest_value())
    assert revalidated.fingerprint == first.fingerprint
    second = derived._capture_cohort_context(plan)
    assert second.product_date == date(2026, 9, 9)
    assert second.fingerprint != first.fingerprint


def test_canonical_capture_is_copy_safe_and_scoped(app):
    from services.derived_intelligence import _capture_cohort_context, _DefaultDomainExecutor
    first, second, pitcher = _canonical_pair()
    plan = _plan(domains=('game_context',), games=(777123, 777124), pitchers=(pitcher,))
    context = _capture_cohort_context(plan)
    original = context.fingerprint
    private_copy = context.canonical_versions()
    private_copy['final']['777123']['id'] = -1
    assert context.fingerprint == original
    assert context.canonical_versions()['final']['777124'] is None
    with db.engine.begin() as writer:
        _advance_final(writer, first, second)
    # The builder consumes the selected V1 value even before final revalidation.
    executor = _DefaultDomainExecutor(plan)
    executor.build_context = context
    with pytest.raises(RuntimeError, match='final_game_context_unavailable:777124'):
        executor._final_context('game_context')
    changed = _capture_cohort_context(plan)
    assert changed.canonical_versions()['final']['777123']['id'] == second
    assert changed.canonical_versions()['final']['777124'] is None
    assert context.canonical_versions()['final']['777123']['id'] == first


def test_canonical_unrelated_game_does_not_contend(app):
    from time import perf_counter
    from sqlalchemy import text
    from services.derived_intelligence import _capture_cohort_context
    from services.selector_generation_fencing import acquire_completion_fences
    from services.semantic_write_fencing import GAME_LOCK_NAMESPACE
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL semantic key independence')
    first, second, pitcher = _canonical_pair()
    plan = _plan(domains=('game_context',), pitchers=(pitcher,))
    context = _capture_cohort_context(plan)
    acquire_completion_fences(context, 'final')
    with db.engine.begin() as writer:
        started = perf_counter()
        assert writer.execute(text('SELECT pg_try_advisory_xact_lock(:key)'),
                              {'key': GAME_LOCK_NAMESPACE + 777124}).scalar_one()
        elapsed = (perf_counter() - started) * 1000
    assert elapsed < 1000
    print(f'unrelated canonical game lock: {elapsed:.3f} ms')


def test_reference_midnight_does_not_stale_completed_generation(app, monkeypatch):
    from datetime import timezone
    from services import availability_reference_date as dates, derived_intelligence as derived
    resolve = dates.resolve_product_day
    first, _, pitcher = _canonical_pair()
    plan = _plan(domains=('game_context',), pitchers=(pitcher,))
    monkeypatch.setattr(dates, 'resolve_product_day', lambda: resolve(
        datetime(2026, 9, 9, 3, 59, 59, tzinfo=timezone.utc)))

    def midnight():
        monkeypatch.setattr(dates, 'resolve_product_day', lambda: resolve(
            datetime(2026, 9, 9, 4, 0, 1, tzinfo=timezone.utc)))

    result = execute_derived_intelligence_plan(plan.id, publication_candidate_enabled=False,
                                              before_revalidate=midnight)
    assert result.cohort.status == 'complete'
    assert derived.cohort_inputs_are_current(result.cohort, plan)
    receipt = result.cohort.input_manifest_json[-1]['context']
    assert receipt['reference']['product_date'] == '2026-09-08'
    assert receipt['selectors']['canonical_versions']['final']['777123']['id'] == first


def test_context_v1_receipt_remains_v1(app):
    from services.derived_intelligence import _capture_cohort_context
    plan = _plan(domains=('game_context',))
    legacy = _capture_cohort_context(plan, recorded_context={'schema_version': 'cohort-build-context-v1'})
    assert legacy.manifest_value()['schema_version'] == 'cohort-build-context-v1'
    assert 'reference' not in legacy.manifest_value()
    assert 'canonical_versions' not in legacy.manifest_value()['selectors']
    assert legacy.product_date is None


def test_canonical_capture_query_bound_and_determinism(app):
    import json
    from time import perf_counter
    from sqlalchemy import event
    from services.cohort_canonical_selectors import capture_canonical_selectors
    from services.cohort_build_context import _json
    first, second, pitcher = _canonical_pair()
    first_row = db.session.get(FinalGameVersion, first)
    values = {column.name: getattr(first_row, column.name)
              for column in FinalGameVersion.__table__.columns if column.name != 'id'}
    with db.engine.begin() as writer:
        writer.execute(FinalGameVersion.__table__.insert(), [
            {**values, 'game_pk': game} for game in range(777124, 777138)
        ])
    plan = _plan(domains=('game_context',), games=tuple(range(777123, 777138)), pitchers=(pitcher,))
    # Resolve ORM plan state before measuring collector-only SQL.
    games = list(plan.affected_game_ids_json)
    statements = []
    def record(*args):
        statements.append(args[2])
    event.listen(db.engine, 'before_cursor_execute', record)
    try:
        started = perf_counter()
        captured = capture_canonical_selectors(plan)
        elapsed = (perf_counter() - started) * 1000
    finally:
        event.remove(db.engine, 'before_cursor_execute', record)
    assert len(statements) == 2
    assert len(captured['final']) == 15
    assert all(captured['final'].values())
    plan.affected_game_ids_json = list(reversed(games))
    assert _json(capture_canonical_selectors(plan)) == _json(captured)
    print(json.dumps({'canonical_games': 15, 'queries': len(statements),
                      'capture_ms': round(elapsed, 3), 'selector_bytes': len(_json(captured).encode())}))
    db.session.rollback()
    from services.derived_intelligence import _capture_cohort_context
    statements.clear()
    event.listen(db.engine, 'before_cursor_execute', record)
    try:
        started = perf_counter()
        context = _capture_cohort_context(plan)
        context_ms = (perf_counter() - started) * 1000
        context_queries = len(statements)
        statements.clear()
        started = perf_counter()
        result = execute_derived_intelligence_plan(plan.id, publication_candidate_enabled=False)
        build_ms = (perf_counter() - started) * 1000
        build_queries = len(statements)
    finally:
        event.remove(db.engine, 'before_cursor_execute', record)
    assert result.cohort.status == 'complete'
    print(json.dumps({'fixture': '15 current Final games; game_context domain',
                      'context_queries': context_queries, 'context_ms': round(context_ms, 3),
                      'context_bytes': len(_json(context.manifest_value()).encode()),
                      'canonical_completion_locks': 15,
                      'cohort_queries': build_queries, 'cohort_ms': round(build_ms, 3)}))


def test_two_current_games_advance_only_one_canonical_identity(app):
    from services.derived_intelligence import _capture_cohort_context
    first, second, pitcher = _canonical_pair()
    row = db.session.get(FinalGameVersion, first)
    values = {column.name: getattr(row, column.name)
              for column in FinalGameVersion.__table__.columns if column.name != 'id'}
    with db.engine.begin() as writer:
        other = writer.execute(FinalGameVersion.__table__.insert().values(
            **{**values, 'game_pk': 777124, 'version_number': 4}
        ).returning(FinalGameVersion.id)).scalar_one()
    plan = _plan(domains=('game_context',), games=(777124, 777123), pitchers=(pitcher,))
    captured = _capture_cohort_context(plan)
    with db.engine.begin() as writer:
        _advance_final(writer, first, second)
    changed = _capture_cohort_context(plan)
    before = captured.canonical_versions()['final']
    after = changed.canonical_versions()['final']
    assert before['777124'] == after['777124']
    assert after['777124']['id'] == other
    assert before['777123']['id'] == first and after['777123']['id'] == second
    assert after['777123']['predecessor_version_id'] == first


def test_canonical_guard_upgrade_downgrade_preserves_versions(app):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL guard migration')
    first, second, _ = _canonical_pair()
    db.session.rollback()
    path = Path(__file__).resolve().parents[1] / 'migrations/versions/a5b8c1d4e7f0_fence_canonical_game_selectors.py'
    spec = importlib.util.spec_from_file_location('canonical_guard_roundtrip', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with db.engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        before = connection.execute(text('SELECT * FROM final_game_versions ORDER BY id')).all()
        migration.downgrade()
        migration.upgrade()
        after = connection.execute(text('SELECT * FROM final_game_versions ORDER BY id')).all()
        assert before == after
        count = connection.execute(text("SELECT count(*) FROM pg_trigger WHERE tgname='canonical_selector_write' AND tgenabled='O'" )).scalar_one()
        assert count == 5


def test_live_selector_cannot_override_captured_final(app):
    from services.derived_intelligence import _capture_cohort_context
    first, second, pitcher = _canonical_pair()
    plan = _plan(authority='live', domains=('game_context',), pitchers=(pitcher,))
    executor = _DefaultDomainExecutor(plan)
    executor.build_context = _capture_cohort_context(plan)
    assert executor.build_context.canonical_versions()['final']['777123']['id'] == first
    with pytest.raises(RuntimeError, match='superseded_by_final'):
        executor._live('game_context')


def test_captured_reference_drives_roster_snapshot_age_check(app, monkeypatch):
    from api import bullpen
    from services import dashboard_snapshot
    calls = []
    def selected(**kwargs):
        calls.append(kwargs['reference_date'])
        return SimpleNamespace(snapshot_generated_at=datetime(2026, 9, 8))
    monkeypatch.setattr(dashboard_snapshot, 'get_latest_valid_dashboard_snapshot', selected)
    cutoff = bullpen._served_score_cutoff(semantic_reference_date=GAME_DATE)
    assert cutoff == datetime(2026, 9, 8)
    assert calls == [GAME_DATE]


def test_pregame_insert_cannot_replace_captured_version_during_completion(app):
    from sqlalchemy.exc import DBAPIError
    from services.derived_intelligence import _capture_cohort_context
    from services.selector_generation_fencing import acquire_completion_fences
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL insert selector guard')
    first_source, second_source = _observation('pregame-v1'), _observation('pregame-v2')
    first = GamePregameContextVersion(
        game_pk=777123, version_number=1, baseball_date=GAME_DATE,
        home_team_id=110, away_team_id=111, scheduled_at=datetime(2026, 9, 8, 20),
        context_fingerprint='pregame-v1'.ljust(64, '0'), fingerprint_version='test-v1',
        source_observation_id=first_source.id, completeness='complete',
        observed_at=first_source.observed_at,
    )
    db.session.add(first)
    db.session.commit()
    values = {column.name: getattr(first, column.name)
              for column in GamePregameContextVersion.__table__.columns if column.name != 'id'}
    values.update(version_number=2, predecessor_version_id=first.id,
                  source_observation_id=second_source.id, scheduled_at=datetime(2026, 9, 8, 21),
                  context_fingerprint='pregame-v2'.ljust(64, '0'))
    plan = _plan(authority='pregame_authoritative', domains=('game_context',), pitchers=())
    captured = _capture_cohort_context(plan)
    acquire_completion_fences(captured, plan.authority_class)
    with pytest.raises(DBAPIError) as rejected:
        with db.engine.begin() as writer:
            writer.execute(GamePregameContextVersion.__table__.insert().values(**values))
    assert rejected.value.orig.pgcode == '40001'
    db.session.rollback()

    def advance():
        with db.engine.begin() as writer:
            writer.execute(GamePregameContextVersion.__table__.insert().values(**values))
    stale = execute_derived_intelligence_plan(plan.id, publication_candidate_enabled=False,
                                             before_revalidate=advance).cohort
    assert stale.status == 'stale'
    executor = _DefaultDomainExecutor(plan)
    executor.build_context = captured
    assert executor._pregame('game_context')['game']['777123']['game_context']['scheduled_at'] == '2026-09-08T20:00:00'
    rebuilt = execute_derived_intelligence_plan(plan.id, publication_candidate_enabled=False).cohort
    assert rebuilt.status == 'complete'
    assert rebuilt.input_manifest_json[-1]['context']['selectors']['canonical_versions']['pregame']['777123']['version_number'] == 2


@pytest.mark.parametrize('scope', ['team', 'pitcher'])
def test_roster_version_predicate_is_fenced_and_revalidated(app, monkeypatch, scope):
    from models.roster_membership import RosterMembershipInterval
    from sqlalchemy.exc import DBAPIError
    from services import derived_intelligence as derived
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL canonical roster selector fence')
    first, _, pitcher = _canonical_pair()
    observation_id = db.session.get(FinalGameVersion, first).boxscore_observation_id
    plan = _plan(authority='roster_authoritative', domains=('roster_composition',), games=(),
                 teams=(110,) if scope == 'team' else (), pitchers=(pitcher,))
    values = dict(pitcher_id=pitcher, player_mlb_id=9001, team_id=110, organization_id=110,
                  membership_type='forty_man_roster', effective_start_date=GAME_DATE,
                  authority_type='mlb_roster_endpoint', opened_by_observation_id=observation_id)
    # Isolate the real manifest/completion owner from the deferred compatibility
    # population recipe. No roster-status content closure is asserted here.
    monkeypatch.setattr(_DefaultDomainExecutor, '_roster', lambda self, domain: {'summary': {}})
    persist = derived._persist_snapshots
    def boundary(cohort, snapshots):
        with pytest.raises(DBAPIError) as rejected:
            with db.engine.begin() as writer:
                writer.execute(RosterMembershipInterval.__table__.insert().values(**values))
        assert rejected.value.orig.pgcode == '40001'
        persist(cohort, snapshots)
    monkeypatch.setattr(derived, '_persist_snapshots', boundary)
    completed = execute_derived_intelligence_plan(plan.id, publication_candidate_enabled=False).cohort
    assert completed.status == 'complete'
    old = completed.input_manifest_json
    with db.engine.begin() as writer:
        writer.execute(RosterMembershipInterval.__table__.insert().values(**values))
    assert not derived.cohort_inputs_are_current(completed, plan)
    assert completed.input_manifest_json == old
    monkeypatch.setattr(derived, '_persist_snapshots', persist)
    rebuilt = execute_derived_intelligence_plan(plan.id, publication_candidate_enabled=False).cohort
    assert rebuilt.status == 'complete'
    assert rebuilt.input_manifest_json[-1]['context']['selectors']['canonical_versions']['roster_versions']


def test_unbounded_canonical_predicates_fail_closed(app):
    from services.derived_intelligence import _capture_cohort_context
    plan = _plan(domains=('game_context',), games=(), teams=(), pitchers=())
    with pytest.raises(ValueError, match='requires_bounded_scope'):
        _capture_cohort_context(plan)
    with pytest.raises(ValueError, match='requires_bounded_scope'):
        execute_derived_intelligence_plan(plan.id, publication_candidate_enabled=False)


def test_pitcher_only_final_appearance_selector_blocks_new_generation(app):
    from sqlalchemy.exc import DBAPIError
    from services.derived_intelligence import _capture_cohort_context
    from services.selector_generation_fencing import acquire_completion_fences
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL bounded appearance predicate')
    _, _, pitcher = _canonical_pair()
    plan = _plan(domains=('game_context',), games=(), pitchers=(pitcher,))
    captured = _capture_cohort_context(plan)
    assert captured.canonical_versions()['appearance_versions']
    acquire_completion_fences(captured, 'final')
    with pytest.raises(DBAPIError) as rejected:
        with db.engine.begin() as writer:
            writer.execute(FinalPitchingAppearanceVersion.__table__.update()
                           .where(FinalPitchingAppearanceVersion.pitcher_id == pitcher)
                           .values(is_current=False))
    assert rejected.value.orig.pgcode == '40001'
    db.session.rollback()


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _plan(*, fingerprint='a' * 64, authority='final', domains=None,
          games=(777123,), teams=(110,), pitchers=(10,)):
    row = CanonicalImpactPlan(
        plan_fingerprint=fingerprint, rules_version='canonical-impact-v1',
        authority_class=authority, baseball_date=GAME_DATE,
        correlation_id='cohort-test', affected_game_ids_json=list(games),
        affected_team_ids_json=list(teams), affected_pitcher_ids_json=list(pitchers),
        affected_domains_json=list(domains or ('workload', 'rest', 'arm_read', 'team_state',
                                               'pitcher_snapshot', 'team_snapshot')),
        source_observation_ids_json=[], status='dispatched', supersedes_live=False,
    )
    db.session.add(row)
    db.session.commit()
    return row


def _observation(suffix):
    subject = SourceSubject(
        identity_key=(suffix + '-subject').ljust(64, '0')[:64],
        provider='mlb_stats_api', source_domain='boxscore', endpoint='/test',
        subject_type='game', subject_key='game:777123',
        request_identity=(suffix + '-request').ljust(64, '0')[:64],
        request_schema_version=1, request_parameters={}, baseball_date=GAME_DATE,
    )
    db.session.add(subject)
    db.session.flush()
    observation = SourceObservation(
        source_subject_id=subject.id, version_number=1,
        dedupe_key=(suffix + '-dedupe').ljust(64, '0')[:64],
        fingerprint=(suffix + '-fingerprint').ljust(64, '0')[:64],
        fingerprint_algorithm='sha256', fingerprint_version='test-v1',
        payload_schema_version=1, completeness='complete', outcome='new',
        is_change=True, is_authoritative=True, record_count=1,
        observed_at=datetime(2026, 9, 8, 23, 0),
    )
    db.session.add(observation)
    db.session.flush()
    return observation


def test_default_executor_captures_selection_before_first_domain_and_reuses_it(app, monkeypatch):
    from services import dashboard_snapshot, derived_intelligence

    with app.app_context():
        plan = _plan(domains=('workload', 'pitcher_snapshot'))
        source = SimpleNamespace(id=41, payload={'generation': 'first'})
        selected = []

        def select_source(**kwargs):
            selected.append(source.id)
            return source

        monkeypatch.setattr(dashboard_snapshot, 'get_latest_valid_dashboard_snapshot', select_source)
        monkeypatch.setattr(
            derived_intelligence, '_latest_comparable_cohort',
            lambda _: pytest.fail('Candidate generation reselected its predecessor'),
        )
        executor = _DefaultDomainExecutor(plan, predecessor_cohort_id=17)
        executor.cache['publication_baseline_required'] = False
        monkeypatch.setattr(executor, '_workload', lambda _: {})
        executor('workload', {})
        captured = executor.build_context
        source.id = 42
        source.payload = {'generation': 'second'}
        executor.cache['publication_baseline_required'] = True
        received = []

        def rebuild(_team_result, **kwargs):
            received.append(kwargs['build_context'])
            return SimpleNamespace(status='complete')

        monkeypatch.setattr(derived_intelligence, 'rebuild_read_model_impact', rebuild)
        monkeypatch.setattr(executor, '_team_result', lambda: None)
        executor._read_result()
        executor._read_result()
        assert selected == [41]
        assert received == [captured]
        assert captured.source_snapshot().id == 41
        assert captured.source_snapshot().payload == {'generation': 'first'}
        assert captured.predecessor_cohort_id == 17
        assert captured.publication_artifact_baseline is False


def test_plan_capture_and_completion_revalidation_share_one_historical_payload_scope(
    app, monkeypatch,
):
    from services import dashboard_snapshot, team_board_delta_substrate as delta

    plan = _plan(domains=('read_models',))
    source = SimpleNamespace(id=41, payload={'generation': 'stable'})
    monkeypatch.setattr(
        dashboard_snapshot, 'get_latest_valid_dashboard_snapshot', lambda **_kwargs: source,
    )
    monkeypatch.setattr(
        _DefaultDomainExecutor,
        '__call__',
        lambda _executor, _domain, _snapshots: {'team': {}},
    )
    created_scopes = []
    real_scope = delta.HistoricalDashboardPayloadReuse

    def capture_scope(**kwargs):
        scope = real_scope(**kwargs)
        created_scopes.append(scope)
        return scope

    seen = []

    def resolve(*, team_id, current_source_snapshot_id, historical_payload_reuse, **_kwargs):
        seen.append((
            historical_payload_reuse.capture_identifier,
            id(historical_payload_reuse.cache),
            team_id,
            current_source_snapshot_id,
        ))
        return delta.compare_snapshots(None, None)

    monkeypatch.setattr(delta, 'HistoricalDashboardPayloadReuse', capture_scope)
    monkeypatch.setattr(delta, 'resolve_latest_team_state_comparison', resolve)

    result = execute_derived_intelligence_plan(
        plan.id, publication_candidate_enabled=False,
    )

    assert result.cohort.status == 'complete'
    assert len(created_scopes) == 1
    scope = created_scopes[0]
    assert [row['pass_identifier'] for row in scope.pass_metrics] == [
        'baseline_capture', 'completion_revalidation',
    ]
    assert {cache_id for _capture, cache_id, _team, _source in seen} == {id(scope)}
    assert {capture for capture, _cache, _team, _source in seen} == {
        'baseline_capture', 'completion_revalidation',
    }
    assert {source_id for _capture, _cache, _team, source_id in seen} == {41}


@pytest.mark.parametrize('advance', ['none', 'dashboard', 'baseline', 'predecessor'])
def test_persisted_selector_lifecycle_rejects_drift_and_retries_postgresql(app, monkeypatch, advance):
    """Exercise the real completion guard with separate selector writer commits.

    Payload computation is replaced to isolate the selector lifecycle from B2.
    The trusted-source provider uses local unpublished fixture snapshots.
    """
    import json
    from models.dashboard_snapshot import DashboardSnapshot
    from models.atomic_publication import AtomicPublication, AtomicPublicationCurrent
    from services import dashboard_snapshot, atomic_publication_reads
    from services.atomic_publication import validate_publication_cohort, PublicationValidationError
    from tests.test_atomic_publication import _cohort

    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('Requires separate PostgreSQL connections')
        source_plan, source_cohort = _cohort(marker='selector-source')
        pending_plan, pending = _cohort(marker='selector-next', status='running')
        plan = _plan(fingerprint='selector-target'.ljust(64, '0'), domains=('read_models',))
        source = DashboardSnapshot(
            snapshot_type='bullpen_dashboard', payload={'generation': 'one'},
            status='ready', is_published=False, data_through=GAME_DATE,
            snapshot_generated_at=datetime(2026, 9, 9, 4),
        )
        db.session.add(source)
        db.session.commit()
        monkeypatch.setattr(
            dashboard_snapshot, 'get_latest_valid_dashboard_snapshot',
            lambda **kwargs: DashboardSnapshot.query.filter_by(snapshot_type='bullpen_dashboard')
                .order_by(DashboardSnapshot.id.desc()).first(),
        )
        monkeypatch.setattr(atomic_publication_reads, 'publication_reader_coverage',
                            lambda _: {'complete': False})

        consumed = []

        def build(executor, domain, snapshots):
            context = executor.build_context
            consumed.append(context.manifest_value())
            return {'team': {'110': {'selection_fixture': context.manifest_value()}}}

        monkeypatch.setattr(_DefaultDomainExecutor, '__call__', build)

        def advance_selector():
            with db.engine.begin() as writer:
                if advance == 'dashboard':
                    writer.execute(DashboardSnapshot.__table__.insert().values(
                        snapshot_type='bullpen_dashboard', payload={'generation': 'two'},
                        status='ready', is_published=False, data_through=GAME_DATE,
                        snapshot_generated_at=datetime(2026, 9, 9, 5),
                    ))
                elif advance == 'predecessor':
                    writer.execute(DerivedIntelligenceCohort.__table__.update()
                                   .where(DerivedIntelligenceCohort.id == pending.id)
                                   .values(status='complete'))
                elif advance == 'baseline':
                    publication_id = writer.execute(AtomicPublication.__table__.insert().values(
                        publication_fingerprint='selector-publication'.ljust(64, '0'),
                        schema_version='atomic-publication-v1', cohort_id=source_cohort.id,
                        impact_plan_id=source_plan.id, baseball_date=GAME_DATE,
                        authority_class='final', status='published', completeness='complete',
                        source_data_through=datetime(2026, 9, 9, 4),
                        input_manifest_fingerprint='fixture'.ljust(64, '0'),
                    ).returning(AtomicPublication.id)).scalar_one()
                    writer.execute(AtomicPublicationCurrent.__table__.insert().values(
                        singleton_id=1, publication_id=publication_id,
                    ))

        first = execute_derived_intelligence_plan(
            plan.id, before_revalidate=advance_selector,
            publication_candidate_enabled=False,
        ).cohort
        old_manifest = json.dumps(first.input_manifest_json, sort_keys=True)
        context_input = DerivedCohortInput.query.filter_by(
            cohort_id=first.id, input_type='build_context',
        ).one()
        assert context_input.input_version == 'cohort-build-context-v2'
        assert context_input.input_fingerprint == first.input_manifest_json[-1]['input_fingerprint']
        assert first.input_manifest_json[-1]['context'] == consumed[0]
        if advance == 'none':
            assert first.status == 'complete'
            validate_publication_cohort(first, plan)
            duplicate = execute_derived_intelligence_plan(plan.id, publication_candidate_enabled=False)
            assert duplicate.created is False
            assert duplicate.cohort.id == first.id
            return

        assert first.status == 'stale'
        assert first.publication_job_id is None
        assert DerivedCohortSnapshot.query.filter_by(cohort_id=first.id).count() == 0
        with pytest.raises(PublicationValidationError, match='cohort_not_complete'):
            validate_publication_cohort(first, plan)
        second = execute_derived_intelligence_plan(plan.id, publication_candidate_enabled=False).cohort
        assert second.id != first.id
        assert second.status == 'complete'
        validate_publication_cohort(second, plan)
        assert consumed[0] != consumed[1]
        assert json.dumps(first.input_manifest_json, sort_keys=True) == old_manifest
        assert first.status == 'stale'


def test_two_workers_with_different_snapshot_generations_cannot_both_complete(app, monkeypatch):
    from threading import Event
    from models.dashboard_snapshot import DashboardSnapshot
    from services import dashboard_snapshot

    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('Requires separate PostgreSQL connections')
        plan = _plan(domains=('read_models',))
        plan_id = plan.id
        source = DashboardSnapshot(
            snapshot_type='bullpen_dashboard', status='ready', is_published=False,
            payload={'generation': 1}, data_through=GAME_DATE,
        )
        db.session.add(source)
        db.session.commit()
        first_source_id = source.id
        engine = db.engine

    captured_a, release_a = Event(), Event()
    monkeypatch.setattr(
        dashboard_snapshot, 'get_latest_valid_dashboard_snapshot',
        lambda **kwargs: DashboardSnapshot.query.filter_by(snapshot_type='bullpen_dashboard')
            .order_by(DashboardSnapshot.id.desc()).first(),
    )

    def build(executor, domain, snapshots):
        selected = executor.build_context.source_snapshot().id
        if selected == first_source_id:
            captured_a.set()
            assert release_a.wait(20), 'Worker A was not released'
        return {'team': {'110': {'source_snapshot_id': selected}}}

    monkeypatch.setattr(_DefaultDomainExecutor, '__call__', build)

    def worker():
        with app.app_context():
            cohort = execute_derived_intelligence_plan(
                plan_id, publication_candidate_enabled=False,
            ).cohort
            return cohort.id, cohort.status

    with ThreadPoolExecutor(max_workers=2) as workers:
        a = workers.submit(worker)
        try:
            assert captured_a.wait(20), 'Worker A did not capture S1'
            with engine.begin() as writer:
                writer.execute(DashboardSnapshot.__table__.insert().values(
                    snapshot_type='bullpen_dashboard', status='ready',
                    is_published=False, payload={'generation': 2}, data_through=GAME_DATE,
                ))
            b = workers.submit(worker)
            b_id, b_status = b.result(timeout=20)
        finally:
            release_a.set()
        a_id, a_status = a.result(timeout=20)
    assert a_id != b_id
    assert a_status == 'stale'
    assert b_status == 'complete'


def _final_authority(observation, *, version, predecessor=None):
    pitcher = Pitcher.query.filter_by(mlb_id=9001).one_or_none()
    if pitcher is None:
        pitcher = Pitcher(
            mlb_id=9001, full_name='Test Pitcher', team_id=110,
            team_name='Team', team_abbreviation='T', active=True,
        )
        db.session.add(pitcher)
        db.session.flush()
    game = FinalGameVersion(
        game_pk=777123, version_number=version,
        predecessor_version_id=predecessor[0].id if predecessor else None,
        baseball_date=GAME_DATE, home_team_id=110, away_team_id=111,
        fact_fingerprint=f'game-{version}'.ljust(64, '0'),
        fingerprint_version='test-v1', core_completeness='complete',
        pbp_completeness='unknown', finality_observation_id=observation.id,
        boxscore_observation_id=observation.id, observed_at=observation.observed_at,
        is_current=True,
    )
    db.session.add(game)
    db.session.flush()
    appearance = FinalPitchingAppearanceVersion(
        final_game_version_id=game.id, game_pk=777123, baseball_date=GAME_DATE,
        pitcher_id=pitcher.id, pitcher_mlb_id=pitcher.mlb_id,
        team_id_at_appearance=110, side='home', appearance_role='reliever',
        version_number=version,
        predecessor_version_id=predecessor[1].id if predecessor else None,
        outs_recorded=3, pitches_thrown=10 + version,
        context_completeness='unknown',
        fact_fingerprint=f'appearance-{version}'.ljust(64, '0'),
        fingerprint_version='test-v1', boxscore_observation_id=observation.id,
        is_current=True,
    )
    db.session.add(appearance)
    db.session.flush()
    return game, appearance, pitcher


class RecordingExecutor:
    def __init__(self, *, fail=()):
        self.calls = []
        self.fail = set(fail)

    def __call__(self, domain, _snapshots):
        self.calls.append(domain)
        if domain in self.fail:
            raise RuntimeError(f'{domain} unavailable')
        return {
            'pitcher': {'10': {domain: {'value': domain}}},
            'team': {'110': {domain: {'value': domain}}},
            'game': {'777123': {domain: {'value': domain}}},
            'summary': {'domain': domain},
        }


def test_dependency_closure_is_ordered_and_pregame_does_not_expand_to_team_state():
    assert dependency_closure(['team_state']) == (
        'roster_composition', 'workload', 'rest', 'concentration',
        'arm_read', 'clean_options', 'team_state',
    )
    assert dependency_closure(['game_context', 'matchup_context', 'read_models']) == (
        'game_context', 'matchup_context', 'read_models',
    )


def test_final_plan_creates_one_coherent_candidate_cohort(app):
    plan = _plan()
    executor = RecordingExecutor()
    result = execute_derived_intelligence_plan(plan.id, domain_executor=executor)

    assert result.created is True
    assert result.cohort.status == CohortStatus.COMPLETE.value
    assert result.cohort.schema_version == COHORT_SCHEMA_VERSION
    assert result.cohort.requested_domains_json == sorted(plan.affected_domains_json)
    assert result.cohort.execution_domains_json == list(dependency_closure(plan.affected_domains_json))
    assert result.cohort.completed_domains_json == list(dependency_closure(plan.affected_domains_json))
    assert result.cohort.withheld_domains_json == []
    assert DerivedIntelligenceCohortDomain.query.filter_by(cohort_id=result.cohort.id).count() == len(executor.calls)
    assert DerivedCohortSnapshot.query.filter_by(cohort_id=result.cohort.id).count() == 3
    assert result.publication_job.job_name == 'publish_derived_cohort'
    assert result.publication_job.details_json['cohort_id'] == result.cohort.id
    assert result.publication_job.details_json['input_manifest'] == result.cohort.input_manifest_json


def test_public_read_families_are_separate_immutable_candidate_artifacts(app):
    plan = _plan(domains=(
        'pitcher_snapshot', 'team_snapshot', 'read_models', 'what_changed',
    ))

    class PublicArtifactExecutor(RecordingExecutor):
        def __call__(self, domain, snapshots):
            self.calls.append(domain)
            if domain == 'read_models':
                return {
                    'team': {'110': {'read_models': {
                        'team_board': {'team_id': 110},
                        'league_row': {'team_id': 110},
                        'team_board_v2': {
                            'full': {'active_bullpen': {'arms': [{'pitcher_id': 10}]}},
                            'core': {}, 'details': {},
                        },
                    }}},
                    'pitcher': {'10': {'read_models': {
                        'pitcher_current': {'pitcher': {'id': 10}},
                    }}},
                    'summary': {},
                }
            if domain == 'what_changed':
                return {
                    'team': {'110': {'what_changed': {'team_id': 110}}},
                    'summary': {},
                }
            return super().__call__(domain, snapshots)

    result = execute_derived_intelligence_plan(
        plan.id, domain_executor=PublicArtifactExecutor(),
    )
    rows = DerivedCohortSnapshot.query.filter_by(cohort_id=result.cohort.id).all()
    by_type = {row.snapshot_type: row for row in rows}

    assert 'team_board_v2_publication' in by_type
    assert 'pitcher_current_publication' in by_type
    assert 'what_changed_publication' in by_type
    assert 'team_board_v2' not in by_type['team_intelligence'].payload_json['read_models']
    assert 'pitcher_current' not in by_type['pitcher_intelligence'].payload_json['read_models']
    assert 'what_changed' not in by_type['team_intelligence'].payload_json


def test_first_reader_baseline_persists_public_artifacts_from_team_snapshot(app):
    plan = _plan(domains=('team_snapshot',))
    executor = _DefaultDomainExecutor(plan)
    executor.cache['publication_baseline_required'] = True
    executor.cache['read_result'] = SimpleNamespace(
        team_package_results={110: {'team_id': 110}},
        team_board_results={110: {'team_id': 110}},
        team_board_v2_results={110: {'full': {'team_id': 110}}},
        pitcher_current_results={10: {'pitcher': {'id': 10}}},
        what_changed_results={110: {'team_id': 110, 'changes': []}},
        league_row_results={110: {'team_id': 110}},
        matchup_results={},
        tonight_results={},
    )

    result = executor._read_models('team_snapshot')

    assert result['team']['110']['read_models']['team_board_v2']['full']['team_id'] == 110
    assert result['team']['110']['what_changed']['team_id'] == 110
    assert result['pitcher']['10']['read_models']['pitcher_current']['pitcher']['id'] == 10

    read_models = executor._read_models('read_models')
    assert read_models['team']['110']['what_changed']['team_id'] == 110


def test_post_baseline_team_snapshot_stays_bounded_to_requested_artifact(app):
    plan = _plan(domains=('team_snapshot',))
    executor = _DefaultDomainExecutor(plan)
    executor.cache['publication_baseline_required'] = False
    executor.cache['read_result'] = SimpleNamespace(
        team_package_results={110: {'team_id': 110}},
        team_board_results={110: {'team_id': 110}},
        team_board_v2_results={110: {'full': {'team_id': 110}}},
        pitcher_current_results={10: {'pitcher': {'id': 10}}},
        what_changed_results={110: {'team_id': 110, 'changes': []}},
        league_row_results={110: {'team_id': 110}},
        matchup_results={},
        tonight_results={},
    )

    result = executor._read_models('team_snapshot')

    assert result['team'] == {'110': {'team_snapshot': {'team_id': 110}}}
    assert 'pitcher' not in result


def test_shadow_execution_can_complete_cohort_without_publication_candidate(app):
    plan = _plan()
    result = execute_derived_intelligence_plan(
        plan.id,
        domain_executor=RecordingExecutor(),
        publication_candidate_enabled=False,
    )

    assert result.cohort.status == CohortStatus.COMPLETE.value
    assert result.publication_job is None
    assert result.cohort.publication_job_id is None
    assert SyncJob.query.filter_by(job_name='publish_derived_cohort').count() == 0


def test_duplicate_exact_plan_input_and_methods_reuses_cohort_and_job(app):
    plan = _plan()
    first = execute_derived_intelligence_plan(plan.id, domain_executor=RecordingExecutor())
    second = execute_derived_intelligence_plan(plan.id, domain_executor=RecordingExecutor())
    assert second.created is False
    assert second.cohort.id == first.cohort.id
    assert second.publication_job.id == first.publication_job.id
    assert DerivedIntelligenceCohort.query.count() == 1
    assert SyncJob.query.filter_by(job_name='publish_derived_cohort').count() == 1


def test_optional_failure_is_isolated_and_dependents_are_withheld(app):
    plan = _plan(domains=('performance', 'team_snapshot', 'what_changed'))
    result = execute_derived_intelligence_plan(
        plan.id, domain_executor=RecordingExecutor(fail=('performance', 'team_snapshot')),
    )
    statuses = {
        row.domain: row.status
        for row in DerivedIntelligenceCohortDomain.query.filter_by(cohort_id=result.cohort.id)
    }
    assert result.cohort.status == CohortStatus.PARTIAL.value
    assert statuses['performance'] == 'failed'
    assert statuses['team_snapshot'] == 'failed'
    assert statuses['what_changed'] == 'withheld'
    assert result.publication_job is None


def test_live_cohort_is_provisional_and_never_dispatched_for_publication(app):
    plan = _plan(
        authority='live', domains=('workload_current', 'team_workload_current', 'game_context'),
    )
    result = execute_derived_intelligence_plan(plan.id, domain_executor=RecordingExecutor())
    assert result.cohort.status == 'complete'
    assert result.cohort.authority_class == 'live'
    assert result.publication_job is None


def test_final_cohort_supersedes_matching_live_and_not_unrelated_live(app):
    live = _plan(
        fingerprint='b' * 64, authority='live', domains=('game_context',), games=(777123,),
    )
    live_result = execute_derived_intelligence_plan(live.id, domain_executor=RecordingExecutor())
    unrelated = _plan(
        fingerprint='c' * 64, authority='live', domains=('game_context',), games=(888888,),
    )
    unrelated_result = execute_derived_intelligence_plan(unrelated.id, domain_executor=RecordingExecutor())
    final = _plan(fingerprint='d' * 64, games=(777123,))
    final_result = execute_derived_intelligence_plan(final.id, domain_executor=RecordingExecutor())
    assert final_result.cohort.supersedes_cohort_id == live_result.cohort.id
    assert final_result.cohort.supersedes_cohort_id != unrelated_result.cohort.id


def test_input_drift_marks_cohort_stale_and_withholds_dispatch(app):
    plan = _plan()

    def supersede_plan():
        plan.status = 'superseded'

    result = execute_derived_intelligence_plan(
        plan.id, domain_executor=RecordingExecutor(), before_revalidate=supersede_plan,
    )
    assert result.cohort.status == 'stale'
    assert result.publication_job is None
    assert {
        row.status for row in DerivedIntelligenceCohortDomain.query.filter_by(cohort_id=result.cohort.id)
    } == {'stale'}


def test_lease_fence_failure_prevents_snapshot_and_publication(app):
    plan = _plan()
    calls = {'count': 0}

    def fence():
        calls['count'] += 1
        if calls['count'] == 2:
            raise RuntimeError('lease lost')

    with pytest.raises(RuntimeError, match='lease lost'):
        execute_derived_intelligence_plan(
            plan.id, domain_executor=RecordingExecutor(), lease_fence=fence,
        )
    db.session.rollback()
    assert DerivedCohortSnapshot.query.count() == 0
    assert SyncJob.query.filter_by(job_name='publish_derived_cohort').count() == 0


def test_zero_work_and_superseded_plan_are_successful_no_ops(app):
    plan = _plan(domains=[])
    plan.affected_domains_json = []
    db.session.commit()
    result = execute_derived_intelligence_plan(plan.id)
    assert result.zero_work is True
    assert result.cohort is None
    plan.status = 'superseded'
    plan.affected_domains_json = ['workload']
    db.session.commit()
    result = execute_derived_intelligence_plan(plan.id)
    assert result.zero_work is True
    assert DerivedIntelligenceCohort.query.count() == 0


def test_manifest_rows_are_queryable_and_scope_stays_bounded(app):
    plan = _plan(teams=(110,), pitchers=(10,))
    result = execute_derived_intelligence_plan(plan.id, domain_executor=RecordingExecutor())
    assert result.cohort.affected_team_ids_json == [110]
    assert result.cohort.affected_pitcher_ids_json == [10]
    assert DerivedCohortInput.query.filter_by(cohort_id=result.cohort.id).count() == 0
    assert all(row.entity_key in {'10', '110', '777123'} for row in DerivedCohortSnapshot.query.all())


def test_final_manifest_pins_current_versions_and_detects_real_version_drift(app):
    observation_v1 = _observation('v1')
    game_v1, appearance_v1, pitcher = _final_authority(observation_v1, version=1)
    plan = _plan(
        fingerprint='e' * 64, domains=('workload',), pitchers=(pitcher.id,),
    )
    plan.source_observation_ids_json = [observation_v1.id]
    db.session.commit()

    corrected = {}

    def correct_final():
        game_v1.is_current = False
        appearance_v1.is_current = False
        observation_v2 = _observation('v2')
        game_v2, appearance_v2, _ = _final_authority(
            observation_v2, version=2,
            predecessor=(game_v1, appearance_v1),
        )
        corrected.update(
            observation=observation_v2, game=game_v2, appearance=appearance_v2,
        )

    result = execute_derived_intelligence_plan(
        plan.id, domain_executor=RecordingExecutor(), before_revalidate=correct_final,
    )
    assert result.cohort.status == 'stale'
    assert result.publication_job is None
    inputs = DerivedCohortInput.query.filter_by(cohort_id=result.cohort.id).all()
    assert {(row.input_type, row.input_version) for row in inputs} == {
        ('final_game', str(game_v1.id)),
        ('final_appearance', str(appearance_v1.id)),
        ('source_observation', str(observation_v1.id)),
    }

    replacement = _plan(
        fingerprint='g' * 64, domains=('workload',), pitchers=(pitcher.id,),
    )
    replacement.source_observation_ids_json = [corrected['observation'].id]
    db.session.commit()
    replacement_result = execute_derived_intelligence_plan(
        replacement.id, domain_executor=RecordingExecutor(),
    )

    assert replacement_result.cohort.status == 'complete'
    replacement_inputs = DerivedCohortInput.query.filter_by(
        cohort_id=replacement_result.cohort.id,
    ).all()
    assert {(row.input_type, row.input_version) for row in replacement_inputs} == {
        ('final_game', str(corrected['game'].id)),
        ('final_appearance', str(corrected['appearance'].id)),
        ('source_observation', str(corrected['observation'].id)),
    }


def test_unrelated_source_advance_does_not_invalidate_bounded_manifest(app):
    observation = _observation('bounded-v1')
    game, appearance, pitcher = _final_authority(observation, version=1)
    plan = _plan(
        fingerprint='h' * 64, domains=('workload',), pitchers=(pitcher.id,),
    )
    plan.source_observation_ids_json = [observation.id]
    db.session.commit()

    def add_unrelated_evidence():
        _observation('unrelated')
        pitcher.full_name = 'Derived compatibility output changed'

    result = execute_derived_intelligence_plan(
        plan.id,
        domain_executor=RecordingExecutor(),
        before_revalidate=add_unrelated_evidence,
    )

    assert result.cohort.status == 'complete'
    assert result.publication_job is not None
    assert game.is_current is True
    assert appearance.is_current is True


def test_concurrent_exact_cohort_creates_one_candidate_and_job_postgresql(app):
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL derived-cohort concurrency contract')
    plan = _plan()
    plan_id = plan.id
    barrier = Barrier(2)

    def execute(_index):
        with app.app_context():
            barrier.wait(timeout=10)
            result = execute_derived_intelligence_plan(
                plan_id, domain_executor=RecordingExecutor(),
            )
            cohort_id = result.cohort.id
            db.session.remove()
            return cohort_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        cohort_ids = list(pool.map(execute, (0, 1)))
    with app.app_context():
        assert cohort_ids[0] == cohort_ids[1]
        assert DerivedIntelligenceCohort.query.count() == 1
        assert SyncJob.query.filter_by(job_name='publish_derived_cohort').count() == 1


def test_one_shot_worker_consumes_sp09_job_and_only_enqueues_sp11_handoff(app):
    observation = _observation('pregame-worker')
    context = GamePregameContextVersion(
        game_pk=777123, version_number=1, baseball_date=GAME_DATE,
        home_team_id=110, away_team_id=111,
        context_fingerprint='pregame-worker'.ljust(64, '0'),
        fingerprint_version='test-v1', source_observation_id=observation.id,
        completeness='complete', observed_at=observation.observed_at,
    )
    db.session.add(context)
    db.session.flush()
    plan = _plan(
        fingerprint='f' * 64, authority='pregame_authoritative',
        domains=('game_context', 'matchup_context', 'read_models'), pitchers=(),
    )
    plan.source_observation_ids_json = [observation.id]
    db.session.commit()
    enqueue_job(
        job_type=JobType.PROCESS_DERIVED_INTELLIGENCE,
        scope_type=JobScopeType.GAME, scope_key='777123', product_date=GAME_DATE,
        dedupe_key='sp10-worker-test', payload_schema_version=1,
        payload={
            'impact_plan_id': plan.id, 'rules_version': plan.rules_version,
            'authority_class': plan.authority_class,
            'baseball_date': GAME_DATE.isoformat(),
        },
    )
    settled = run_derived_intelligence_worker_once('sp10-worker')
    assert settled.status == 'succeeded'
    assert settled.result_json['cohort_status'] == 'complete'
    cohort = db.session.get(DerivedIntelligenceCohort, settled.result_json['cohort_id'])
    assert cohort.sync_run_id is not None
    assert cohort.publication_job_id is not None
    assert SyncJob.query.filter_by(job_name='publish_derived_cohort').count() == 1


def _fenced_selector_fixture(monkeypatch):
    from models.dashboard_snapshot import DashboardSnapshot
    from services import dashboard_snapshot
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL selector generation fence')
    source = DashboardSnapshot(snapshot_type='bullpen_dashboard', status='ready',
                               is_published=False, payload={'generation': 1},
                               data_through=GAME_DATE)
    db.session.add(source)
    db.session.commit()
    monkeypatch.setattr(dashboard_snapshot, 'get_latest_valid_dashboard_snapshot',
                        lambda **kwargs: DashboardSnapshot.query.filter_by(snapshot_type='bullpen_dashboard')
                        .order_by(DashboardSnapshot.id.desc()).first())
    monkeypatch.setattr(_DefaultDomainExecutor, '__call__',
                        lambda executor, domain, snapshots: {'team': {'110': {
                            'captured_source': executor.build_context.source_snapshot().id}}})
    return source.id


def _insert_selector(connection):
    from models.dashboard_snapshot import DashboardSnapshot
    return connection.execute(DashboardSnapshot.__table__.insert().values(
        snapshot_type='bullpen_dashboard', status='ready', is_published=False,
        payload={'generation': 2}, data_through=GAME_DATE,
    ).returning(DashboardSnapshot.id)).scalar_one()


def test_completion_reader_first_holds_fence_until_outer_commit(app, monkeypatch):
    """Permanent version of the retained commit-window counterexample."""
    from threading import Event
    from time import perf_counter
    from sqlalchemy.orm import Session
    from services import derived_intelligence as derived
    from services.selector_generation_fencing import acquire_selector_fences, DASHBOARD
    first = _fenced_selector_fixture(monkeypatch)
    plan = _plan(domains=('read_models',))
    entered, committed = Event(), Event()
    engine = db.engine

    def writer():
        with Session(engine) as session:
            entered.set()
            started = perf_counter()
            # This writer starts before any row or R2 lock; waiting is legal.
            acquire_selector_fences(((DASHBOARD, 0),), wait=True, session=session)
            second = _insert_selector(session.connection())
            session.commit()
            committed.set()
            return second, (perf_counter() - started) * 1000

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = None
        original = derived._persist_snapshots

        def after_validation(cohort, snapshots):
            nonlocal future
            future = pool.submit(writer)
            assert entered.wait(5)
            assert not committed.wait(0.15)
            original(cohort, snapshots)

        monkeypatch.setattr(derived, '_persist_snapshots', after_validation)
        try:
            result = execute_derived_intelligence_plan(
                plan.id, publication_candidate_enabled=False, commit=False)
            assert not committed.is_set()
            db.session.commit()  # Fence must survive the executor's flush/return.
        finally:
            db.session.rollback()
        second, waited = future.result(timeout=5)
    assert second > first
    assert result.cohort.status == 'complete'
    manifest = result.cohort.input_manifest_json
    assert manifest[-1]['context']['selectors']['dashboard_snapshot_id'] == first
    assert not derived.cohort_inputs_are_current(result.cohort, plan)
    assert result.cohort.status == 'complete'  # Historical, never rewritten.
    assert result.cohort.input_manifest_json == manifest
    print(f'reader-first writer wait including deliberate hold: {waited:.3f} ms')


def test_completion_writer_first_refreshes_cached_source_and_retries(app, monkeypatch):
    from models.dashboard_snapshot import DashboardSnapshot
    first = _fenced_selector_fixture(monkeypatch)
    cached = db.session.get(DashboardSnapshot, first)
    plan = _plan(domains=('read_models',))

    def advance():
        with db.engine.begin() as writer:
            _insert_selector(writer)
            writer.execute(DashboardSnapshot.__table__.update()
                           .where(DashboardSnapshot.id == first)
                           .values(payload={'generation': 'corrected'}))
        assert cached.payload == {'generation': 1}

    result = execute_derived_intelligence_plan(plan.id, before_revalidate=advance,
                                              publication_candidate_enabled=False)
    assert result.cohort.status == 'stale'
    old_id, old_manifest = result.cohort.id, result.cohort.input_manifest_json
    retry = execute_derived_intelligence_plan(plan.id, publication_candidate_enabled=False)
    assert retry.cohort.status == 'complete'
    assert retry.cohort.id != old_id
    assert db.session.get(DerivedIntelligenceCohort, old_id).input_manifest_json == old_manifest
    assert db.session.get(DerivedIntelligenceCohort, old_id).status == 'stale'


@pytest.mark.parametrize('reader_shared,writer_shared,same_scope,allowed', [
    (True, True, True, True), (True, False, True, False),
    (False, False, True, False), (False, True, True, False),
    (True, False, False, True), (False, False, False, True),
])
def test_selector_lock_compatibility_postgresql(app, reader_shared, writer_shared, same_scope, allowed):
    from sqlalchemy.orm import Session
    from time import perf_counter
    from services.selector_generation_fencing import (
        acquire_selector_fences, SelectorFenceConflict, COMPARISON,
    )
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL shared/exclusive compatibility')
    with Session(db.engine) as first, Session(db.engine) as second:
        acquire_selector_fences(((COMPARISON, 110),), shared=reader_shared, session=first)
        started = perf_counter()
        if allowed:
            acquire_selector_fences(((COMPARISON, 110 if same_scope else 111),),
                                    shared=writer_shared, session=second)
            second.commit()
            elapsed = (perf_counter() - started) * 1000
            assert elapsed < 1000
            print(f'compatible acquisition plus commit: {elapsed:.3f} ms')
        else:
            with pytest.raises(SelectorFenceConflict):
                acquire_selector_fences(((COMPARISON, 110),), shared=writer_shared, session=second)
        first.rollback()
        second.rollback()


def test_selector_database_backstop_rejects_old_binary_insert(app, monkeypatch):
    from sqlalchemy.exc import DBAPIError
    from services.selector_generation_fencing import acquire_selector_fences, DASHBOARD
    _fenced_selector_fixture(monkeypatch)
    acquire_selector_fences(((DASHBOARD, 0),), shared=True)
    with pytest.raises(DBAPIError) as error:
        with db.engine.begin() as writer:
            _insert_selector(writer)  # No Python fence: simulate deployed old binary.
    assert error.value.orig.pgcode == '40001'
    db.session.rollback()
    with db.engine.begin() as writer:
        _insert_selector(writer)


@pytest.mark.parametrize('boundary', ['validation', 'persist', 'flush'])
def test_selector_completion_crash_rolls_back(app, monkeypatch, boundary):
    from services import derived_intelligence as derived
    _fenced_selector_fixture(monkeypatch)
    plan = _plan(domains=('read_models',))
    original = derived._persist_snapshots

    def crash(cohort, snapshots):
        if boundary == 'persist':
            original(cohort, snapshots)
        raise RuntimeError('injected completion crash')

    if boundary != 'flush':
        monkeypatch.setattr(derived, '_persist_snapshots', crash)
        with pytest.raises(RuntimeError, match='injected completion crash'):
            execute_derived_intelligence_plan(plan.id, publication_candidate_enabled=False)
    else:
        result = execute_derived_intelligence_plan(plan.id, publication_candidate_enabled=False, commit=False)
        assert result.cohort.status == 'complete'
    db.session.rollback()
    assert DerivedIntelligenceCohort.query.filter_by(status='complete').count() == 0
    with db.engine.begin() as writer:
        _insert_selector(writer)  # Rollback released every completion fence.


def test_selector_writer_rollback_does_not_advance_generation(app, monkeypatch):
    from models.dashboard_snapshot import DashboardSnapshot
    first = _fenced_selector_fixture(monkeypatch)
    with db.engine.connect() as writer:
        transaction = writer.begin()
        _insert_selector(writer)
        transaction.rollback()
    assert DashboardSnapshot.query.order_by(DashboardSnapshot.id.desc()).first().id == first
    result = execute_derived_intelligence_plan(_plan(domains=('read_models',)).id,
                                              publication_candidate_enabled=False)
    assert result.cohort.status == 'complete'


def test_predecessor_scope_precedes_limit_postgresql(app):
    from services.derived_intelligence import _latest_comparable_cohort
    from tests.test_atomic_publication import _cohort
    _, predecessor = _cohort(marker='bounded-first')
    target = _plan(fingerprint='target'.ljust(64, '0'))
    assert _latest_comparable_cohort(target).id == predecessor.id
    other = _plan(fingerprint='other'.ljust(64, '0'), teams=(999,), pitchers=(999,), games=(999,))
    values = [dict(
        impact_plan_id=other.id, cohort_fingerprint=f'unrelated-{index:03d}'.ljust(64, 'x'),
        schema_version='derived-cohort-v1', authority_class='final', baseball_date=GAME_DATE,
        status='complete', requested_domains_json=[], execution_domains_json=[],
        completed_domains_json=[], withheld_domains_json=[], affected_game_ids_json=[999],
        affected_team_ids_json=[999], affected_pitcher_ids_json=[999],
        input_manifest_json=[], method_versions_json={},
    ) for index in range(105)]
    with db.engine.begin() as writer:
        writer.execute(DerivedIntelligenceCohort.__table__.insert(), values)
    assert _latest_comparable_cohort(target).id == predecessor.id
    _, newer = _cohort(marker='bounded-next')
    assert _latest_comparable_cohort(target).id == newer.id


def test_reclaimed_worker_cannot_complete_under_selector_fence(app, monkeypatch):
    from sqlalchemy import text
    from services.semantic_write_fencing import worker_claim
    from services.sync_jobs import LeaseOwnershipError
    from tests.test_final_game_reconciliation import _claimed_job
    _fenced_selector_fixture(monkeypatch)
    plan = _plan(domains=('read_models',))
    job = _claimed_job()
    job_id, token = job.id, job.claim_token

    def replace_claim():
        with db.engine.begin() as writer:
            writer.execute(text("UPDATE sync_jobs SET worker_id='replacement', claim_token='replacement' WHERE id=:id"),
                           {'id': job_id})

    with worker_claim(job_id, 'sp07-test', token):
        with pytest.raises(LeaseOwnershipError):
            execute_derived_intelligence_plan(plan.id, before_revalidate=replace_claim,
                                              publication_candidate_enabled=False)
        db.session.rollback()
    assert DerivedIntelligenceCohort.query.filter_by(status='complete').count() == 0


def test_completion_rejects_hidden_transaction_restart(app, monkeypatch):
    from services import derived_intelligence as derived
    from services.selector_generation_fencing import SelectorFenceConflict
    _fenced_selector_fixture(monkeypatch)
    plan = _plan(domains=('read_models',))
    original = derived.cohort_inputs_are_current

    def restarted(cohort, plan, **kwargs):
        answer = original(cohort, plan, **kwargs)
        db.session.rollback()  # Simulate a reader helper swallowing a DB error.
        return answer

    monkeypatch.setattr(derived, 'cohort_inputs_are_current', restarted)
    with pytest.raises(SelectorFenceConflict, match='transaction ended'):
        execute_derived_intelligence_plan(plan.id, publication_candidate_enabled=False)
    db.session.rollback()
    assert DerivedIntelligenceCohort.query.filter_by(status='complete').count() == 0


def test_overlapping_completion_upgrade_never_waits_backwards(app):
    from sqlalchemy.orm import Session
    from services.selector_generation_fencing import acquire_selector_fences, SelectorFenceConflict, predecessor_resources
    resources = predecessor_resources('final', teams=(110,), games=(777123,))
    with Session(db.engine) as first, Session(db.engine) as second:
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('PostgreSQL transaction upgrade')
        acquire_selector_fences(resources, shared=True, session=first)
        acquire_selector_fences(tuple(reversed(resources)), shared=True, session=second)
        with pytest.raises(SelectorFenceConflict):
            acquire_selector_fences(resources, session=first)
        first.rollback()
        acquire_selector_fences(resources, session=second)
        second.commit()


def test_selector_writer_inventory_and_database_guards(app):
    """Named owners plus the DB backstop cover bulk SQL and older binaries."""
    import inspect
    from sqlalchemy import text
    from services import dashboard_snapshot, share_artifacts, team_board_delta_substrate, atomic_publication
    owners = {
        dashboard_snapshot.store_dashboard_snapshot: 'fence_dashboard_writer',
        dashboard_snapshot.publish_dashboard_snapshot: 'fence_dashboard_writer',
        dashboard_snapshot.mark_dashboard_snapshot_failed: 'fence_dashboard_writer',
        team_board_delta_substrate.stamp_prospective_snapshot: 'fence_comparison_writer',
        share_artifacts.publish_share_artifact: 'fence_comparison_writer',
        share_artifacts.supersede_share_artifact: 'fence_comparison_writer',
        share_artifacts.withdraw_share_artifact: 'fence_comparison_writer',
        share_artifacts.publish_new_share_artifact: 'publish_share_artifact',
        atomic_publication.publish_derived_cohort: 'acquire_selector_fences',
        execute_derived_intelligence_plan: 'acquire_selector_fences',
    }
    for owner, call in owners.items():
        assert call in inspect.getsource(owner), owner.__name__
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL deployed-binary trigger inventory')
    tables = set(db.session.execute(text('''
        SELECT c.relname FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
        WHERE t.tgname='selector_generation_write' AND t.tgenabled='O'
    ''')).scalars())
    assert tables == {'dashboard_snapshots', 'share_artifacts', 'atomic_publications',
                      'atomic_publication_current', 'atomic_publication_artifacts',
                      'derived_cohort_snapshots', 'derived_intelligence_cohorts'}


@pytest.mark.parametrize('authority', ['live', 'final', 'corrected_final', 'roster_authoritative', 'pregame_authoritative'])
def test_predecessor_resource_keys_match_database_protocol(app, authority):
    import json
    from sqlalchemy import text
    from services.selector_generation_fencing import predecessor_resources
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL namespace parity')
    row = dict(status='complete', authority_class=authority,
               affected_game_ids_json=[777123, 777124], affected_team_ids_json=[110],
               affected_pitcher_ids_json=[10])
    resources = db.session.execute(text('''
        SELECT * FROM baseballos_selector_resources('derived_intelligence_cohorts',
                                                     CAST(:row AS jsonb)) ORDER BY 1,2
    '''), {'row': json.dumps(row)}).all()
    assert tuple(map(tuple, resources)) == predecessor_resources(
        authority, games=(777124, 777123), teams=(110,), pitchers=(10,))


def test_completion_fence_cost_postgresql(app, monkeypatch):
    from time import perf_counter
    from sqlalchemy import event
    from services.selector_generation_fencing import acquire_completion_fences, acquire_selector_fences, COMPARISON
    from services.derived_intelligence import _capture_cohort_context
    _fenced_selector_fixture(monkeypatch)
    plan = _plan(domains=('read_models',))
    context = _capture_cohort_context(plan)
    db.session.rollback()
    statements = []

    def count(_connection, _cursor, statement, *_args):
        statements.append(statement)

    event.listen(db.engine, 'before_cursor_execute', count)
    try:
        started = perf_counter()
        acquire_completion_fences(context, 'final')
        shared_ms = (perf_counter() - started) * 1000
        shared_sql = len(statements)
        db.session.rollback()
        started = perf_counter()
        acquire_selector_fences(((COMPARISON, 110),))
        exclusive_ms = (perf_counter() - started) * 1000
        db.session.rollback()
    finally:
        event.remove(db.engine, 'before_cursor_execute', count)
    assert shared_sql <= 40  # Baseline may capture all 30 comparison selectors.
    print(f'completion capture fence: {shared_sql} SQL / {shared_ms:.3f} ms; '
          f'uncontended exclusive: {exclusive_ms:.3f} ms')


def test_completion_rejects_repeatable_read_snapshot(app, monkeypatch):
    from sqlalchemy.orm import Session
    from services.selector_generation_fencing import acquire_completion_fences, SelectorFenceConflict
    from services.derived_intelligence import _capture_cohort_context
    _fenced_selector_fixture(monkeypatch)
    context = _capture_cohort_context(_plan(domains=('read_models',)))
    db.session.rollback()
    with db.engine.connect().execution_options(isolation_level='REPEATABLE READ') as connection:
        with Session(connection) as session:
            with pytest.raises(SelectorFenceConflict, match='READ COMMITTED'):
                acquire_completion_fences(context, 'final', session=session)


def test_selector_guard_migration_round_trip_preserves_history(app, monkeypatch):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text
    from models.dashboard_snapshot import DashboardSnapshot
    from services.selector_generation_fencing import acquire_completion_fences, SelectorFenceConflict
    from services.derived_intelligence import _capture_cohort_context
    first = _fenced_selector_fixture(monkeypatch)
    context = _capture_cohort_context(_plan(domains=('read_models',)))
    original = db.session.get(DashboardSnapshot, first).to_dict()
    path = Path(__file__).resolve().parents[1] / 'migrations/versions/f4a7b0c3d6e9_fence_selector_generations.py'
    spec = importlib.util.spec_from_file_location('selector_round_trip', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.down_revision == 'e3f6a9b2c5d8'
    db.session.rollback()
    with db.engine.begin() as connection:
        module.op = Operations(MigrationContext.configure(connection))
        module.downgrade()
    with pytest.raises(SelectorFenceConflict, match='not installed'):
        acquire_completion_fences(context, 'final')
    db.session.rollback()
    with db.engine.begin() as connection:
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        assert connection.execute(text('''SELECT count(*) FROM pg_trigger
            WHERE tgname='selector_generation_write' AND tgenabled='O'
        ''')).scalar_one() == 7
    assert db.session.get(DashboardSnapshot, first).to_dict() == original
    acquire_completion_fences(context, 'final')
    db.session.rollback()


def test_unrelated_cohort_completes_while_first_holds_completion_fences(app, monkeypatch):
    from time import perf_counter
    from services import derived_intelligence as derived
    _fenced_selector_fixture(monkeypatch)
    first = _plan(fingerprint='parallel-first'.ljust(64, '0'), domains=('read_models',))
    other = _plan(fingerprint='parallel-other'.ljust(64, '0'), domains=('read_models',),
                  teams=(111,), pitchers=(20,), games=(888888,))
    first_id, other_id = first.id, other.id
    original = derived._persist_snapshots
    outcome = {}

    def second_worker():
        started = perf_counter()
        with app.app_context():
            try:
                result = execute_derived_intelligence_plan(other_id, publication_candidate_enabled=False)
                return result.cohort.id, result.cohort.status, (perf_counter() - started) * 1000
            finally:
                db.session.remove()

    with ThreadPoolExecutor(max_workers=1) as pool:
        def while_fenced(cohort, snapshots):
            if cohort.impact_plan_id == first_id:
                outcome['other'] = pool.submit(second_worker).result(timeout=10)
            original(cohort, snapshots)

        monkeypatch.setattr(derived, '_persist_snapshots', while_fenced)
        try:
            result = execute_derived_intelligence_plan(first_id, publication_candidate_enabled=False)
        finally:
            db.session.rollback()
    assert result.cohort.status == outcome['other'][1] == 'complete'
    assert result.cohort.id != outcome['other'][0]
    assert outcome['other'][2] < 2000
    print(f'unrelated full cohort completed during protected first completion: {outcome["other"][2]:.3f} ms')
