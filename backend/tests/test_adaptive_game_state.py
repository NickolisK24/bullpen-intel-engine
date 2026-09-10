from datetime import date, datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import Flask

from models.scheduled_game import ScheduledGame
from models.source_observation import SourceFetchAttempt, SourceObservation
from models.sync_job import SyncJob
from models.sync_run import SyncRun
from services import adaptive_game_state as adaptive
from services.adaptive_game_state import (
    GameState,
    GameStateTransition,
    classify_game_state_transition,
    empty_schedule_poll_decision,
    execute_game_state_poll,
    normalize_game_state,
    plan_game_state_polls,
    polling_decision,
    run_next_game_state_poll,
    snapshot_from_source_game,
)
from services.source_observations import (
    ObservationCompleteness,
    PayloadKind,
    SourceProvider,
    SourceSubjectType,
    build_source_identity,
    canonical_record_collection,
    record_source_observation,
)
from services.sync_control_plane import SourceDomain
from services.sync_jobs import (
    JobScopeType,
    JobType,
    enqueue_job,
    run_next_job,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db

import models.prospect  # noqa: F401
import models.dashboard_snapshot  # noqa: F401


SLATE = date(2026, 9, 5)
NOW = datetime(2026, 9, 5, 20, 0)


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _game(game_pk=777123, *, when='2026-09-05T23:10:00Z', code='S',
          detailed='Scheduled', abstract='Preview', home=110, away=111,
          home_score=None, away_score=None, game_number=1):
    game = {
        'gamePk': game_pk,
        'officialDate': '2026-09-05',
        'gameDate': when,
        'gameType': 'R',
        'gameNumber': game_number,
        'doubleHeader': 'Y' if game_number > 1 else 'N',
        'status': {
            'statusCode': code,
            'detailedState': detailed,
            'abstractGameState': abstract,
        },
        'teams': {
            'home': {'team': {'id': home}},
            'away': {'team': {'id': away}},
        },
    }
    if home_score is not None:
        game['teams']['home']['score'] = home_score
    if away_score is not None:
        game['teams']['away']['score'] = away_score
    return game


@pytest.mark.parametrize('code,detailed,abstract,expected', [
    ('S', 'Scheduled', 'Preview', GameState.SCHEDULED.value),
    ('P', 'Pre-Game', 'Preview', GameState.PREGAME.value),
    ('PW', 'Warmup', 'Preview', GameState.PREGAME.value),
    ('I', 'In Progress', 'Live', GameState.LIVE.value),
    ('I', 'Delayed', 'Live', GameState.DELAYED.value),
    ('U', 'Suspended', 'Live', GameState.SUSPENDED.value),
    ('DR', 'Postponed', 'Preview', GameState.POSTPONED.value),
    ('C', 'Cancelled', 'Final', GameState.CANCELLED.value),
    ('F', 'Final', 'Final', GameState.FINAL.value),
    ('O', 'Game Over', 'Final', GameState.FINAL.value),
    ('?', 'Novel State', 'Other', GameState.UNKNOWN.value),
])
def test_game_state_normalization(code, detailed, abstract, expected):
    assert normalize_game_state({
        'statusCode': code,
        'detailedState': detailed,
        'abstractGameState': abstract,
    }) == expected


def test_transition_vocabulary_and_irrelevant_change():
    scheduled = snapshot_from_source_game(_game())
    assert classify_game_state_transition(None, scheduled) == 'game_discovered'
    assert classify_game_state_transition(scheduled, scheduled) is None
    assert classify_game_state_transition(
        scheduled, snapshot_from_source_game(_game(code='P', detailed='Pre-Game'))
    ) == GameStateTransition.GAME_PREGAME.value
    live = snapshot_from_source_game(_game(code='I', detailed='In Progress', abstract='Live'))
    assert classify_game_state_transition(scheduled, live) == 'game_started'
    delayed = snapshot_from_source_game(_game(code='I', detailed='Delayed', abstract='Live'))
    assert classify_game_state_transition(live, delayed) == 'game_delayed'
    assert classify_game_state_transition(delayed, live) == 'game_resumed'
    suspended = snapshot_from_source_game(_game(code='U', detailed='Suspended', abstract='Live'))
    assert classify_game_state_transition(live, suspended) == 'game_suspended'
    assert classify_game_state_transition(suspended, live) == 'game_resumed'
    postponed = snapshot_from_source_game(_game(code='DR', detailed='Postponed'))
    assert classify_game_state_transition(scheduled, postponed) == 'game_postponed'
    final = snapshot_from_source_game(_game(code='F', detailed='Final', abstract='Final'))
    assert classify_game_state_transition(live, final) == 'game_final'
    corrected = snapshot_from_source_game(_game(
        code='F', detailed='Final', abstract='Final', home_score=5, away_score=4,
    ))
    assert classify_game_state_transition(final, corrected) == 'game_final_corrected'
    moved = snapshot_from_source_game(_game(when='2026-09-06T00:10:00Z'))
    assert classify_game_state_transition(scheduled, moved) == 'game_time_changed'


@pytest.mark.parametrize('state,scheduled_at,seconds,priority', [
    ('live', None, 90, adaptive.PRIORITY_ACTIVE),
    ('delayed', None, 120, adaptive.PRIORITY_ACTIVE),
    ('pregame', None, 150, adaptive.PRIORITY_PREGAME),
    ('suspended', None, 1800, adaptive.PRIORITY_COLD),
    ('postponed', None, 21600, adaptive.PRIORITY_COLD),
    ('final', None, 900, adaptive.PRIORITY_NEAR_START),
    ('scheduled', NOW + timedelta(days=2), 21600, adaptive.PRIORITY_COLD),
    ('scheduled', NOW + timedelta(hours=5), 1800, adaptive.PRIORITY_NORMAL),
    ('scheduled', NOW + timedelta(hours=2), 900, adaptive.PRIORITY_NORMAL),
    ('scheduled', NOW + timedelta(minutes=30), 300, adaptive.PRIORITY_NEAR_START),
])
def test_polling_policy(state, scheduled_at, seconds, priority):
    decision = polling_decision(state, scheduled_at, now=NOW)
    assert decision.interval_seconds == seconds
    assert decision.priority == priority
    assert decision.next_poll_at == NOW + timedelta(seconds=seconds)
    assert decision.policy_version == adaptive.POLLING_POLICY_VERSION


def test_final_reconciled_and_empty_policy():
    assert polling_decision('final', None, now=NOW, final_reconciled=True).interval_seconds == 86400
    assert empty_schedule_poll_decision(SLATE, now=NOW).interval_seconds == 21600
    assert empty_schedule_poll_decision(SLATE + timedelta(days=1), now=NOW).interval_seconds == 43200
    assert empty_schedule_poll_decision(SLATE - timedelta(days=1), now=NOW).interval_seconds == 86400


def _enqueue_poll(*, available_at=NOW, suffix='a'):
    return enqueue_job(
        job_type=JobType.FETCH_SCHEDULE,
        scope_type=JobScopeType.BASEBALL_DATE,
        scope_key=SLATE.isoformat(),
        product_date=SLATE,
        dedupe_key=f'test-game-state:{suffix}',
        available_at=available_at,
        priority=0,
        payload_schema_version=adaptive.POLL_PAYLOAD_SCHEMA_VERSION,
        payload={'baseball_date': SLATE.isoformat()},
    )


def _run(job, monkeypatch, games):
    monkeypatch.setattr('services.schedule_ingestion.mlb_client.get_schedule', lambda **_kw: games)
    # ``observe_schedule`` captured the same client object, so the method patch
    # covers the real SP-03 evidence path.
    return run_next_game_state_poll('sp04-test-worker', now=NOW)


def test_first_final_poll_records_authority_and_enqueues_one_handoff(app, monkeypatch):
    with app.app_context():
        job = _enqueue_poll()
        result = _run(job, monkeypatch, [_game(
            code='F', detailed='Final', abstract='Final', home_score=3, away_score=2,
        )])
        assert result.status == 'succeeded'
        rows = ScheduledGame.query.filter_by(game_pk=777123).all()
        assert len(rows) == 2
        assert {row.operational_state for row in rows} == {'final'}
        assert {row.last_transition for row in rows} == {'game_discovered'}
        assert all(row.source_observation_id for row in rows)
        # Discovery of an already-final game is not replayed as a transition to
        # final. Bootstrap reconciliation remains SP-07/SP-12 ownership.
        assert SyncJob.query.filter_by(job_name='reconcile_final_game').count() == 0
        run = db.session.get(SyncRun, job.sync_run_id)
        assert run.status == 'success'
        assert run.source_reads == 1
        assert run.canonical_mutations == 1


def test_live_to_final_enqueues_once_and_unchanged_final_does_not_repeat(app, monkeypatch):
    with app.app_context():
        first = _enqueue_poll(suffix='live')
        _run(first, monkeypatch, [_game(code='I', detailed='In Progress', abstract='Live')])
        second = _enqueue_poll(suffix='final')
        _run(second, monkeypatch, [_game(code='F', detailed='Final', abstract='Final', home_score=4, away_score=1)])
        handoffs = SyncJob.query.filter_by(job_name='reconcile_final_game').all()
        assert len(handoffs) == 1
        assert handoffs[0].priority == adaptive.PRIORITY_ACTIVE
        assert handoffs[0].details_json['transition'] == 'game_final'
        assert handoffs[0].details_json['game_pk'] == 777123
        assert handoffs[0].details_json['source_observation_id']

        third = _enqueue_poll(suffix='unchanged-final')
        _run(third, monkeypatch, [_game(code='F', detailed='Final', abstract='Final', home_score=4, away_score=1)])
        assert SyncJob.query.filter_by(job_name='reconcile_final_game').count() == 1
        third_run = db.session.get(SyncRun, third.sync_run_id)
        assert third_run.zero_mutation is True
        assert third_run.source_changes == 0
        assert third_run.downstream_work_created == 0


def test_final_correction_is_separate_reconciliation_generation(app, monkeypatch):
    with app.app_context():
        _run(_enqueue_poll(suffix='live'), monkeypatch, [_game(code='I', detailed='In Progress', abstract='Live')])
        _run(_enqueue_poll(suffix='final'), monkeypatch, [_game(code='F', detailed='Final', abstract='Final', home_score=4, away_score=1)])
        _run(_enqueue_poll(suffix='correction'), monkeypatch, [_game(code='F', detailed='Final', abstract='Final', home_score=5, away_score=1)])
        handoffs = SyncJob.query.filter_by(job_name='reconcile_final_game').order_by(SyncJob.id).all()
        assert [item.details_json['transition'] for item in handoffs] == [
            'game_final', 'game_final_corrected',
        ]
        assert handoffs[0].dedupe_key != handoffs[1].dedupe_key
        assert SourceObservation.query.count() == 3


def test_empty_valid_is_success_and_schedules_cold_follow_up(app, monkeypatch):
    with app.app_context():
        job = _enqueue_poll(suffix='empty')
        _run(job, monkeypatch, [])
        run = db.session.get(SyncRun, job.sync_run_id)
        assert run.status == 'success'
        assert run.zero_mutation is True
        assert run.outcome_json['source_observation_outcome'] == 'empty_valid'
        assert ScheduledGame.query.count() == 0
        future = SyncJob.query.filter(
            SyncJob.job_name == 'fetch_schedule', SyncJob.status == 'pending'
        ).one()
        assert future.available_at == NOW + timedelta(hours=6)


def test_partial_observation_does_not_mutate_known_good(app):
    with app.app_context():
        from services.schedule_ingestion import ingest_games
        ingest_games([_game(code='I', detailed='In Progress', abstract='Live')])
        before = ScheduledGame.query.filter_by(game_pk=777123).first().status_code
        job = _enqueue_poll(suffix='partial')

        def partial_observer(start, end, **kwargs):
            games = [_game(code='F', detailed='Final', abstract='Final')]
            identity = build_source_identity(
                provider=SourceProvider.MLB_STATS_API,
                source_domain=SourceDomain.SCHEDULE,
                endpoint='/schedule',
                subject_type=SourceSubjectType.DATE_RANGE,
                subject_key=f'{start}:{end}',
                request_parameters={'startDate': start, 'endDate': end, 'sportId': 1},
                range_start=start, range_end=end,
            )
            result = record_source_observation(
                identity=identity,
                payload=games,
                fingerprint_payload=canonical_record_collection(games),
                completeness=ObservationCompleteness.PARTIAL,
                payload_kind=PayloadKind.NORMALIZED_JSON,
                record_count=1,
                sync_run_id=kwargs.get('sync_run_id'), sync_job_id=kwargs.get('sync_job_id'),
            )
            return games, result

        run_next_job(
            'partial-worker',
            {'fetch_schedule': lambda claimed: execute_game_state_poll(
                claimed, now=NOW, observer=partial_observer,
            )},
            job_types=['fetch_schedule'],
        )
        row = ScheduledGame.query.filter_by(game_pk=777123).first()
        assert row.status_code == before
        run = db.session.get(SyncRun, job.sync_run_id)
        assert run.canonical_mutations == 0
        assert run.warnings_count == 1


def test_failed_fetch_preserves_known_good_and_job_retries(app):
    with app.app_context():
        from services.schedule_ingestion import ingest_games
        ingest_games([_game(code='I', detailed='In Progress', abstract='Live')])
        job = _enqueue_poll(suffix='failure')

        def fail(*_args, **_kwargs):
            raise TimeoutError('schedule unavailable')

        with pytest.raises(TimeoutError):
            run_next_job(
                'failure-worker',
                {'fetch_schedule': lambda claimed: execute_game_state_poll(
                    claimed, now=NOW, observer=fail,
                )},
                job_types=['fetch_schedule'],
            )
        db.session.expire_all()
        assert ScheduledGame.query.filter_by(game_pk=777123).first().status_code == 'I'
        assert db.session.get(SyncJob, job.id).status == 'retry_wait'
        assert db.session.get(SyncRun, job.sync_run_id).status == 'failed'


def test_real_schedule_failure_records_sp03_attempt_without_observation(app, monkeypatch):
    with app.app_context():
        job = _enqueue_poll(suffix='source-failure')

        def fail(**_kwargs):
            raise TimeoutError('schedule unavailable')

        monkeypatch.setattr('services.schedule_ingestion.mlb_client.get_schedule', fail)
        with pytest.raises(TimeoutError):
            run_next_game_state_poll('source-failure-worker', now=NOW)
        attempt = SourceFetchAttempt.query.one()
        assert attempt.status == 'failed'
        assert attempt.outcome == 'failed'
        assert attempt.sync_job_id == job.id
        assert SourceObservation.query.count() == 0
        assert ScheduledGame.query.count() == 0


def test_doubleheaders_and_baseball_date_survive_utc_midnight(app, monkeypatch):
    with app.app_context():
        job = _enqueue_poll(suffix='doubleheader')
        games = [
            _game(700001, when='2026-09-06T00:10:00Z', game_number=1),
            _game(700002, when='2026-09-06T03:40:00Z', game_number=2),
        ]
        _run(job, monkeypatch, games)
        assert {row.game_pk for row in ScheduledGame.query.all()} == {700001, 700002}
        assert {row.game_date for row in ScheduledGame.query.all()} == {SLATE}
        assert {item.game_pk for item in map(snapshot_from_source_game, games)} == {700001, 700002}


def test_planner_dedupes_repeated_calls_and_uses_active_priority(app):
    with app.app_context():
        db.session.add_all([
            ScheduledGame(
                team_id=110, opponent_team_id=111, home_away='home',
                game_pk=777123, game_date=SLATE, game_datetime=NOW,
                status_state='other', operational_state='live', next_poll_at=NOW,
            ),
            ScheduledGame(
                team_id=111, opponent_team_id=110, home_away='away',
                game_pk=777123, game_date=SLATE, game_datetime=NOW,
                status_state='other', operational_state='live', next_poll_at=NOW,
            ),
        ])
        db.session.commit()
        first = plan_game_state_polls(now=NOW)
        second = plan_game_state_polls(now=NOW)
        assert len(first) == len(second) == 1
        assert first[0].id == second[0].id
        assert first[0].priority == adaptive.PRIORITY_ACTIVE
        assert first[0].details_json['game_pks'] == [777123]


def test_timezone_aware_now_is_normalized_to_utc():
    aware = datetime(2026, 9, 5, 16, 0, tzinfo=timezone(timedelta(hours=-4)))
    decision = polling_decision('live', None, now=aware)
    assert decision.next_poll_at == NOW + timedelta(seconds=90)


def test_concurrent_planners_create_one_active_poll_on_postgresql(app):
    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('PostgreSQL adaptive planner concurrency contract')
        db.session.add(ScheduledGame(
            team_id=110, opponent_team_id=111, home_away='home',
            game_pk=777123, game_date=SLATE, game_datetime=NOW,
            status_state='other', operational_state='live', next_poll_at=NOW,
        ))
        db.session.commit()

    barrier = Barrier(2)

    def plan():
        with app.app_context():
            barrier.wait(timeout=10)
            job_id = plan_game_state_polls(now=NOW)[0].id
            db.session.remove()
            return job_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _index: plan(), range(2)))

    with app.app_context():
        assert ids[0] == ids[1]
        assert SyncJob.query.filter_by(job_name='fetch_schedule').count() == 1


def test_migration_round_trip_preserves_existing_schedule_row():
    engine = sa.create_engine('sqlite:///:memory:')
    metadata = sa.MetaData()
    sa.Table(
        'source_observations', metadata,
        sa.Column('id', sa.Integer(), primary_key=True),
    )
    scheduled = sa.Table(
        'scheduled_games', metadata,
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('game_pk', sa.Integer(), nullable=False),
        sa.Column('game_date', sa.Date(), nullable=False),
        sa.Column('status_state', sa.String(20), nullable=False),
    )
    metadata.create_all(engine)
    path = (
        Path(__file__).resolve().parents[1] / 'migrations' / 'versions'
        / 'e8b4f1a2c6d9_add_adaptive_game_state_fields.py'
    )
    spec = importlib.util.spec_from_file_location('sp04_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    with engine.begin() as connection:
        connection.execute(scheduled.insert().values(
            id=1, team_id=110, game_pk=777123,
            game_date=SLATE, status_state='scheduled',
        ))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        columns = {item['name']: item for item in sa.inspect(connection).get_columns('scheduled_games')}
        assert columns['operational_state']['nullable'] is True
        assert columns['next_poll_at']['nullable'] is True
        assert connection.execute(sa.text(
            'SELECT game_pk FROM scheduled_games WHERE id = 1'
        )).scalar_one() == 777123

        migration.downgrade()
        columns = {item['name'] for item in sa.inspect(connection).get_columns('scheduled_games')}
        assert 'operational_state' not in columns
        assert connection.execute(sa.text(
            'SELECT status_state FROM scheduled_games WHERE id = 1'
        )).scalar_one() == 'scheduled'
