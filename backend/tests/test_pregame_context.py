from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
import importlib.util
from pathlib import Path
from threading import Barrier

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import Flask

from models.pitcher import Pitcher
from models.pregame_context import GamePregameContextVersion, PregameContextMutation
from models.roster_membership import RosterMembershipInterval
from models.scheduled_game import ScheduledGame
from models.source_observation import SourceFetchAttempt, SourceObservation
from models.sync_job import SyncJob
from models.sync_run import SyncRun
from services import pregame_context as pregame
from services.mlb_api import MLBApiClient
from services.pregame_context import (
    PregameContextChange,
    classify_pregame_changes,
    current_pregame_context,
    execute_pregame_context_job,
    observe_pregame_context,
    persist_pregame_context,
    plan_pregame_context_polls,
    pregame_context_at,
    pregame_polling_decision,
    pregame_source_identity,
    project_pregame_context,
    run_next_pregame_context_job,
)
from services.schedule_ingestion import ingest_games
from services.source_observations import (
    ObservationCompleteness,
    PayloadKind,
    record_source_observation,
)
from services.sync_jobs import JobScopeType, JobType, enqueue_job, run_next_job
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


SLATE = date(2026, 9, 8)
NOW = datetime(2026, 9, 8, 18, 0)
GAME_PK = 824792
HOME = 110
AWAY = 114


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


def _game(
    game_pk=GAME_PK,
    *,
    home_probable=687064,
    away_probable=676440,
    home_name='Brandon Young',
    away_name='Tanner Bibee',
    when='2026-09-08T22:35:00Z',
    state='scheduled',
    game_number=1,
):
    statuses = {
        'scheduled': ('S', 'Scheduled', 'Preview'),
        'pregame': ('P', 'Pre-Game', 'Preview'),
        'live': ('I', 'In Progress', 'Live'),
        'delayed': ('I', 'Delayed Start', 'Preview'),
        'postponed': ('DR', 'Postponed', 'Preview'),
        'suspended': ('U', 'Suspended', 'Live'),
        'final': ('F', 'Final', 'Final'),
    }
    code, detailed, abstract = statuses[state]
    value = {
        'gamePk': game_pk,
        'officialDate': SLATE.isoformat(),
        'gameDate': when,
        'gameType': 'R',
        'gameNumber': game_number,
        'doubleHeader': 'Y' if game_number > 1 else 'N',
        'status': {
            'statusCode': code,
            'detailedState': detailed,
            'abstractGameState': abstract,
        },
        'venue': {'id': 2, 'name': 'Oriole Park at Camden Yards'},
        'teams': {
            'home': {'team': {'id': HOME}},
            'away': {'team': {'id': AWAY}},
        },
    }
    if home_probable is not None:
        value['teams']['home']['probablePitcher'] = {
            'id': home_probable, 'fullName': home_name,
        }
    if away_probable is not None:
        value['teams']['away']['probablePitcher'] = {
            'id': away_probable, 'fullName': away_name,
        }
    return value


def _seed_game(game=None, *, operational_state='scheduled'):
    game = game or _game()
    ingest_games([game])
    for row in ScheduledGame.query.filter_by(game_pk=game['gamePk']).all():
        row.operational_state = operational_state
        row.next_pregame_poll_at = NOW
    db.session.commit()


def _observation(game, *, observed_at=NOW, completeness=ObservationCompleteness.COMPLETE):
    identity = pregame_source_identity(game['gamePk'], SLATE)
    return record_source_observation(
        identity=identity,
        payload=[game],
        fingerprint_payload=[game],
        completeness=completeness,
        payload_kind=PayloadKind.NORMALIZED_JSON,
        record_count=1,
        observed_at=observed_at,
    ).observation


def _enqueue(*, game_pk=GAME_PK, suffix='a', available_at=NOW):
    return enqueue_job(
        job_type=JobType.FETCH_PREGAME_CONTEXT,
        scope_type=JobScopeType.GAME,
        scope_key=str(game_pk),
        product_date=SLATE,
        dedupe_key=f'test-pregame:{game_pk}:{suffix}',
        available_at=available_at,
        priority=pregame.PRIORITY_HIGH,
        payload_schema_version=pregame.PREGAME_PAYLOAD_SCHEMA_VERSION,
        payload={'game_pk': game_pk, 'baseball_date': SLATE.isoformat()},
    )


def test_source_identity_is_game_grain_and_parameter_stable():
    first = pregame_source_identity(GAME_PK, SLATE)
    second = pregame_source_identity(GAME_PK, SLATE)
    other = pregame_source_identity(GAME_PK + 1, SLATE)
    assert first.identity_key == second.identity_key
    assert first.identity_key != other.identity_key
    assert first.source_domain == 'pregame'
    assert first.subject_key == f'game:{GAME_PK}'
    assert first.request_parameters['hydrate'] == 'team,probablePitcher,venue'


def test_mlb_client_supports_bounded_game_pregame_schedule_request(monkeypatch):
    client = MLBApiClient()
    captured = {}

    def fake_get(endpoint, params=None):
        captured.update({'endpoint': endpoint, 'params': params})
        return {'dates': [{'games': [_game()]}]}

    monkeypatch.setattr(client, '_get', fake_get)
    games = client.get_schedule(
        game_pk=GAME_PK, hydrate='team,probablePitcher,venue',
    )
    assert [item['gamePk'] for item in games] == [GAME_PK]
    assert captured == {
        'endpoint': '/schedule',
        'params': {
            'sportId': 1,
            'hydrate': 'team,probablePitcher,venue',
            'gamePk': GAME_PK,
        },
    }


@pytest.mark.parametrize('home_probable,away_probable', [
    (687064, 676440),
    (687064, None),
    (None, None),
])
def test_complete_official_context_preserves_unknown_as_unknown(
    app, monkeypatch, home_probable, away_probable,
):
    with app.app_context():
        game = _game(home_probable=home_probable, away_probable=away_probable)
        monkeypatch.setattr(
            'services.pregame_context.mlb_client.get_schedule',
            lambda **_kwargs: [game],
        )
        returned, result = observe_pregame_context(GAME_PK, SLATE)
        projection = project_pregame_context(returned)
        assert result.observation.completeness == 'complete'
        assert projection.home_probable_pitcher_mlb_id == home_probable
        assert projection.away_probable_pitcher_mlb_id == away_probable


def test_missing_game_is_unknown_and_malformed_probable_is_partial(app, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(
            'services.pregame_context.mlb_client.get_schedule',
            lambda **_kwargs: [],
        )
        game, result = observe_pregame_context(GAME_PK, SLATE)
        assert game is None
        assert result.observation.completeness == 'unknown'

        malformed = _game()
        malformed['teams']['home']['probablePitcher'] = {'fullName': 'Unknown ID'}
        monkeypatch.setattr(
            'services.pregame_context.mlb_client.get_schedule',
            lambda **_kwargs: [malformed],
        )
        _, result = observe_pregame_context(GAME_PK + 1, SLATE)
        assert result.observation.completeness == 'unknown'  # requested game absent

        malformed['gamePk'] = GAME_PK + 1
        _, result = observe_pregame_context(GAME_PK + 1, SLATE)
        assert result.observation.completeness == 'partial'


def test_meaningful_fingerprint_ignores_irrelevant_metadata():
    first = _game()
    second = _game()
    first['description'] = 'transport note one'
    second['description'] = 'transport note two'
    assert project_pregame_context(first).fingerprint == project_pregame_context(second).fingerprint
    second['teams']['home']['probablePitcher']['id'] = 999001
    assert project_pregame_context(first).fingerprint != project_pregame_context(second).fingerprint


def test_v1_v2_history_current_projection_and_historical_lookup(app):
    with app.app_context():
        _seed_game()
        first_game = _game(home_probable=None, away_probable=None)
        first_obs = _observation(first_game, observed_at=NOW)
        first = persist_pregame_context(
            project_pregame_context(first_game), source_observation=first_obs,
            observed_at=NOW,
        )
        assert first.created is True
        assert first.version.version_number == 1
        assert [item.mutation_type for item in first.mutations] == [
            PregameContextChange.PREGAME_CONTEXT_DISCOVERED.value,
        ]

        second_game = _game(home_probable=687064, away_probable=None)
        second_obs = _observation(second_game, observed_at=NOW + timedelta(hours=1))
        second = persist_pregame_context(
            project_pregame_context(second_game), source_observation=second_obs,
            observed_at=NOW + timedelta(hours=1),
        )
        assert second.version.version_number == 2
        assert second.version.predecessor_version_id == first.version.id
        assert [item.mutation_type for item in second.mutations] == ['probable_starter_added']
        assert current_pregame_context(GAME_PK).id == second.version.id
        assert pregame_context_at(GAME_PK, NOW + timedelta(minutes=30)).id == first.version.id
        rows = ScheduledGame.query.filter_by(game_pk=GAME_PK).all()
        assert len(rows) == 2
        assert {row.pregame_context_version_id for row in rows} == {second.version.id}
        assert {row.home_probable_pitcher_mlb_id for row in rows} == {687064}


def test_starter_change_removal_both_sides_and_unchanged(app):
    with app.app_context():
        _seed_game()
        first_game = _game()
        first = persist_pregame_context(
            project_pregame_context(first_game), source_observation=_observation(first_game),
        )
        unchanged = persist_pregame_context(
            project_pregame_context(first_game), source_observation=first.version.source_observation,
        )
        assert unchanged.created is False
        assert GamePregameContextVersion.query.count() == 1

        changed_game = _game(
            home_probable=999001,
            away_probable=None,
            home_name='Replacement Starter',
        )
        changed = persist_pregame_context(
            project_pregame_context(changed_game),
            source_observation=_observation(changed_game, observed_at=NOW + timedelta(hours=1)),
        )
        assert {(m.side, m.mutation_type) for m in changed.mutations} == {
            ('home', 'probable_starter_changed'),
            ('away', 'probable_starter_removed'),
        }
        assert first.version.id != changed.version.id
        assert GamePregameContextVersion.query.count() == 2


def test_older_source_revision_cannot_regress_current_context(app):
    with app.app_context():
        _seed_game()
        old_game = _game(home_probable=687064)
        old_observation = _observation(old_game, observed_at=NOW)
        new_game = _game(home_probable=999001, home_name='Replacement Starter')
        new_observation = _observation(new_game, observed_at=NOW + timedelta(hours=1))

        current = persist_pregame_context(
            project_pregame_context(new_game), source_observation=new_observation,
        )
        stale = persist_pregame_context(
            project_pregame_context(old_game), source_observation=old_observation,
        )
        assert stale.created is False
        assert stale.version.id == current.version.id
        assert GamePregameContextVersion.query.count() == 1
        assert current_pregame_context(GAME_PK).home_probable_pitcher_mlb_id == 999001


def test_canonical_pitcher_resolution_does_not_assign_roster_or_role(app):
    with app.app_context():
        _seed_game()
        pitcher = Pitcher(
            mlb_id=687064, full_name='Brandon Young', team_id=None,
            position='P', active=False,
        )
        db.session.add(pitcher)
        db.session.commit()
        game = _game()
        result = persist_pregame_context(
            project_pregame_context(game), source_observation=_observation(game),
        )
        assert result.version.home_probable_pitcher_id == pitcher.id
        assert pitcher.team_id is None
        assert pitcher.active is False
        assert pitcher.position == 'P'


def test_roster_discrepancy_is_reported_without_mutating_membership(app):
    with app.app_context():
        _seed_game()
        pitcher = Pitcher(mlb_id=700001, full_name='Roster Pitcher', team_id=HOME)
        db.session.add(pitcher)
        db.session.flush()
        observation = _observation(_game())
        db.session.add(RosterMembershipInterval(
            pitcher_id=pitcher.id,
            player_mlb_id=pitcher.mlb_id,
            team_id=HOME,
            membership_type='active_roster',
            effective_start_date=SLATE,
            authority_type='mlb_roster_complete',
            opened_by_observation_id=observation.id,
        ))
        db.session.commit()
        before = RosterMembershipInterval.query.count()
        result = persist_pregame_context(
            project_pregame_context(_game()), source_observation=observation,
        )
        assert result.roster_discrepancies == ({
            'side': 'home', 'team_id': HOME,
            'probable_pitcher_mlb_id': 687064,
            'action': 'roster_confirmation_deferred',
        },)
        assert RosterMembershipInterval.query.count() == before
        assert SyncJob.query.filter_by(job_name='fetch_roster').count() == 0


@pytest.mark.parametrize('state,scheduled_at,seconds,priority', [
    ('scheduled', NOW + timedelta(hours=7), 21600, pregame.PRIORITY_LOW),
    ('scheduled', NOW + timedelta(hours=4), 1800, pregame.PRIORITY_NORMAL),
    ('scheduled', NOW + timedelta(minutes=90), 600, pregame.PRIORITY_NORMAL),
    ('scheduled', NOW + timedelta(minutes=20), 120, pregame.PRIORITY_HIGH),
    ('pregame', NOW, 90, pregame.PRIORITY_HIGH),
    ('delayed', NOW, 180, pregame.PRIORITY_HIGH),
    ('postponed', NOW, 21600, pregame.PRIORITY_LOW),
])
def test_pregame_polling_policy(state, scheduled_at, seconds, priority):
    decision = pregame_polling_decision(state, scheduled_at, now=NOW)
    assert decision.interval_seconds == seconds
    assert decision.next_poll_at == NOW + timedelta(seconds=seconds)
    assert decision.priority == priority
    assert decision.policy_version == pregame.PREGAME_POLICY_VERSION


@pytest.mark.parametrize('state', ['live', 'suspended', 'final', 'cancelled'])
def test_live_or_closed_game_stops_pregame_polling(state):
    decision = pregame_polling_decision(state, NOW, now=NOW)
    assert decision.next_poll_at is None
    assert decision.priority is None


def test_planner_uses_game_pk_identity_and_dedupes(app):
    with app.app_context():
        _seed_game()
        second = _game(game_pk=GAME_PK + 1, game_number=2)
        _seed_game(second)
        first = plan_pregame_context_polls(now=NOW, baseball_dates=[SLATE])
        second_call = plan_pregame_context_polls(now=NOW, baseball_dates=[SLATE])
        assert len(first) == 2
        assert second_call == []
        assert {item.scope_key for item in first} == {str(GAME_PK), str(GAME_PK + 1)}
        assert all(item.job_name == 'fetch_pregame_context' for item in first)
        assert all(item.payload_schema_version == 1 for item in first)
        assert SyncJob.query.filter_by(job_name='fetch_pregame_context').count() == 2
        assert all(row.next_pregame_poll_at is not None for row in ScheduledGame.query.all())


def test_worker_persists_complete_context_and_unchanged_creates_no_v2(app, monkeypatch):
    with app.app_context():
        _seed_game()
        first_job = _enqueue(suffix='first')
        monkeypatch.setattr(
            'services.pregame_context.mlb_client.get_schedule',
            lambda **_kwargs: [_game()],
        )
        result = run_next_pregame_context_job('pregame-worker', now=NOW)
        assert result.status == 'succeeded'
        assert GamePregameContextVersion.query.count() == 1
        run = db.session.get(SyncRun, first_job.sync_run_id)
        assert run.run_type == 'pregame_context'
        assert run.canonical_mutations == 1

        second_job = _enqueue(suffix='unchanged')
        run_next_pregame_context_job('pregame-worker-2', now=NOW)
        assert GamePregameContextVersion.query.count() == 1
        second_run = db.session.get(SyncRun, second_job.sync_run_id)
        assert second_run.canonical_mutations == 0
        assert second_run.zero_mutation is True


def test_partial_does_not_clear_current_context(app):
    with app.app_context():
        _seed_game()
        game = _game()
        first = persist_pregame_context(
            project_pregame_context(game), source_observation=_observation(game),
        )
        job = _enqueue(suffix='partial')

        def partial_observer(*_args, **_kwargs):
            malformed = _game(home_probable=None)
            malformed['teams']['home'].pop('team')
            identity = pregame_source_identity(GAME_PK, SLATE)
            result = record_source_observation(
                identity=identity,
                payload=[malformed],
                completeness=ObservationCompleteness.PARTIAL,
                payload_kind=PayloadKind.NORMALIZED_JSON,
                record_count=1,
                sync_run_id=_kwargs.get('sync_run_id'),
                sync_job_id=_kwargs.get('sync_job_id'),
            )
            return malformed, result

        run_next_job(
            'partial-worker',
            {'fetch_pregame_context': lambda claimed: execute_pregame_context_job(
                claimed, now=NOW, observer=partial_observer,
            )},
            job_types=['fetch_pregame_context'],
        )
        assert current_pregame_context(GAME_PK).id == first.version.id
        assert ScheduledGame.query.filter_by(game_pk=GAME_PK).first().home_probable_pitcher_mlb_id == 687064
        assert GamePregameContextVersion.query.count() == 1
        assert db.session.get(SyncRun, job.sync_run_id).warnings_count == 1


def test_source_failure_keeps_current_context_and_job_retries(app, monkeypatch):
    with app.app_context():
        _seed_game()
        game = _game()
        first = persist_pregame_context(
            project_pregame_context(game), source_observation=_observation(game),
        )
        job = _enqueue(suffix='failure')

        def fail(**_kwargs):
            raise TimeoutError('pregame source unavailable')

        monkeypatch.setattr('services.pregame_context.mlb_client.get_schedule', fail)
        with pytest.raises(TimeoutError):
            run_next_pregame_context_job('failure-worker', now=NOW)
        db.session.expire_all()
        assert current_pregame_context(GAME_PK).id == first.version.id
        assert db.session.get(SyncJob, job.id).status == 'retry_wait'
        assert SourceFetchAttempt.query.filter_by(status='failed').count() == 1


def test_closed_job_does_not_fetch_or_clear_history(app):
    with app.app_context():
        _seed_game(operational_state='live')
        game = _game()
        first = persist_pregame_context(
            project_pregame_context(game), source_observation=_observation(game),
        )
        _enqueue(suffix='closed')

        def forbidden(*_args, **_kwargs):
            raise AssertionError('closed pregame worker must not fetch')

        result = run_next_pregame_context_job('closed-worker', now=NOW, observer=forbidden)
        assert result.status == 'succeeded'
        assert current_pregame_context(GAME_PK).id == first.version.id
        assert SourceFetchAttempt.query.count() == 1  # seed observation only
        assert {row.next_pregame_poll_at for row in ScheduledGame.query.all()} == {None}


def test_aware_time_is_normalized_to_utc():
    aware = datetime(2026, 9, 8, 14, 0, tzinfo=timezone(timedelta(hours=-4)))
    decision = pregame_polling_decision('pregame', None, now=aware)
    assert decision.next_poll_at == NOW + timedelta(seconds=90)


def test_concurrent_same_context_creates_one_version_on_postgresql(app):
    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('PostgreSQL pregame context concurrency contract')
        _seed_game()
        game = _game()
        observation_id = _observation(game).id

    barrier = Barrier(2)

    def persist():
        with app.app_context():
            projection = project_pregame_context(game)
            observation = db.session.get(SourceObservation, observation_id)
            barrier.wait(timeout=10)
            result = persist_pregame_context(
                projection, source_observation=observation,
            )
            version_id = result.version.id
            db.session.remove()
            return version_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _index: persist(), range(2)))

    with app.app_context():
        assert ids[0] == ids[1]
        assert GamePregameContextVersion.query.count() == 1
        assert PregameContextMutation.query.count() == 1
        assert {
            row.pregame_context_version_id
            for row in ScheduledGame.query.filter_by(game_pk=GAME_PK).all()
        } == {ids[0]}


def test_concurrent_planners_create_one_active_game_job_on_postgresql(app):
    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('PostgreSQL pregame planner dedupe contract')
        _seed_game()

    barrier = Barrier(2)

    def plan():
        with app.app_context():
            barrier.wait(timeout=10)
            jobs = plan_pregame_context_polls(
                now=NOW, baseball_dates=[SLATE],
            )
            job_id = jobs[0].id if jobs else None
            db.session.remove()
            return job_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _index: plan(), range(2)))

    with app.app_context():
        assert len({job_id for job_id in ids if job_id is not None}) == 1
        assert SyncJob.query.filter_by(job_name='fetch_pregame_context').count() == 1


def test_migration_round_trip_preserves_existing_schedule_row():
    engine = sa.create_engine('sqlite:///:memory:')
    metadata = sa.MetaData()
    for name in ('source_observations', 'pitchers', 'sync_runs'):
        sa.Table(name, metadata, sa.Column('id', sa.Integer(), primary_key=True))
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
        / 'a6d2e8f4b1c7_add_pregame_context_authority.py'
    )
    spec = importlib.util.spec_from_file_location('sp06_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        connection.execute(scheduled.insert().values(
            id=1, team_id=HOME, game_pk=GAME_PK,
            game_date=SLATE, status_state='scheduled',
        ))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        columns = {item['name'] for item in sa.inspect(connection).get_columns('scheduled_games')}
        assert 'pregame_context_version_id' in columns
        assert 'next_pregame_poll_at' in columns
        assert connection.execute(sa.text(
            'SELECT game_pk FROM scheduled_games WHERE id = 1'
        )).scalar_one() == GAME_PK
        migration.downgrade()
        columns = {item['name'] for item in sa.inspect(connection).get_columns('scheduled_games')}
        assert 'pregame_context_version_id' not in columns
        assert connection.execute(sa.text(
            'SELECT status_state FROM scheduled_games WHERE id = 1'
        )).scalar_one() == 'scheduled'
