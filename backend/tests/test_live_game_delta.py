from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
import importlib.util
from pathlib import Path
from threading import Barrier

import pytest
from flask import Flask
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from models.game_observation_state import GameObservationState
from models.live_game_delta import LiveGameMutation, ProvisionalPitchingAppearanceState
from models.scheduled_game import ScheduledGame
from models.source_observation import SourceFetchAttempt, SourceObservation
from models.sync_job import SyncJob
from services.live_game_delta import (
    LIVE_POLICY_VERSION, LiveMutationType, enqueue_live_poll, live_poll_decision,
    plan_live_game_polls, run_next_live_game_delta,
)
from services.mlb_api import MlbApiFetchError
from services.sync_jobs import (
    STATUS_SUCCEEDED, JobType, LeaseOwnershipError, claim_next_job, succeed_job,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.test_game_change_detection import GAME_PK, _feed
from utils.db import db


GAME_DATE = date(2026, 8, 25)


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


class FeedClient:
    def __init__(self, payload):
        self.payload = payload

    def get_game_live_feed(self, game_pk):
        assert game_pk == GAME_PK
        return deepcopy(self.payload)


class FailedClient:
    def get_game_live_feed(self, game_pk):
        raise MlbApiFetchError('live feed unavailable', endpoint=f'/game/{game_pk}')


def _stats(innings, pitches, *, started=0, strikes=None, bf=3):
    return {
        'inningsPitched': innings, 'gamesStarted': started,
        'numberOfPitches': pitches, 'strikes': strikes if strikes is not None else pitches // 2,
        'balls': pitches - (strikes if strikes is not None else pitches // 2),
        'battersFaced': bf, 'hits': 0, 'runs': 0, 'earnedRuns': 0,
        'baseOnBalls': 0, 'strikeOuts': 1, 'homeRuns': 0,
    }


def _live_feed(*, timestamp='20260826_010000', reliever_pitches=8,
               reliever_outs='1.0', inning=7, status='Live', code='I'):
    payload = _feed(timestamp=timestamp, status=status, code=code, inning=inning,
                    pitcher=303, pitches=reliever_pitches)
    payload['liveData']['boxscore'] = {'teams': {
        'away': {
            'team': {'id': 111}, 'pitchers': [202],
            'players': {'ID202': {'person': {'id': 202, 'fullName': 'Away Starter'},
                                   'stats': {'pitching': _stats('6.0', 85, started=1, bf=24)}}},
        },
        'home': {
            'team': {'id': 146}, 'pitchers': [101, 303],
            'players': {
                'ID101': {'person': {'id': 101, 'fullName': 'Home Starter'},
                          'stats': {'pitching': _stats('6.0', 90, started=1, bf=25)}},
                'ID303': {'person': {'id': 303, 'fullName': 'Home Reliever'},
                          'stats': {'pitching': _stats(reliever_outs, reliever_pitches, bf=4)}},
            },
        },
    }}
    payload['liveData']['plays']['allPlays'] = [
        {'about': {'inning': 1, 'halfInning': 'top', 'outs': 3},
         'result': {'homeScore': 0, 'awayScore': 0}, 'matchup': {'pitcher': {'id': 101}}},
        {'about': {'inning': 1, 'halfInning': 'bottom', 'outs': 3},
         'result': {'homeScore': 0, 'awayScore': 0}, 'matchup': {'pitcher': {'id': 202}}},
        {'about': {'inning': inning, 'halfInning': 'top', 'outs': 1},
         'result': {'homeScore': 3, 'awayScore': 2}, 'matchup': {'pitcher': {'id': 303}}},
    ]
    payload['liveData']['plays']['currentPlay'] = payload['liveData']['plays']['allPlays'][-1]
    return payload


def _schedule(state='live', *, game_pk=GAME_PK):
    for team_id, opponent, side in ((111, 146, 'away'), (146, 111, 'home')):
        db.session.add(ScheduledGame(
            team_id=team_id, game_pk=game_pk, game_date=GAME_DATE,
            opponent_team_id=opponent, home_away=side,
            status_state='other', operational_state=state,
        ))
    db.session.commit()


def _run(payload, worker='live-a'):
    enqueue_live_poll(GAME_PK, GAME_DATE)
    return run_next_live_game_delta(worker, client=FeedClient(payload))


def test_poll_policy_and_planner_dedupe(app):
    now = datetime(2026, 8, 26, 1, 0)
    assert live_poll_decision('live', now=now)['interval_seconds'] == 90
    assert live_poll_decision('delayed', now=now)['interval_seconds'] == 150
    assert live_poll_decision('suspended', now=now) is None
    assert live_poll_decision('live', now=now, resumed=True)['priority'] == 5
    assert live_poll_decision('live', now=now)['policy_version'] == LIVE_POLICY_VERSION
    _schedule()
    first = plan_live_game_polls(now=now)
    second = plan_live_game_polls(now=now)
    assert len(first) == len(second) == 1
    assert first[0].id == second[0].id


def test_first_live_delta_is_durable_and_exactly_scoped(app):
    _schedule()
    result = _run(_live_feed())
    rows = ProvisionalPitchingAppearanceState.query.order_by(
        ProvisionalPitchingAppearanceState.pitcher_mlb_id
    ).all()
    reliever = next(row for row in rows if row.pitcher_mlb_id == 303)
    assert len(rows) == 3
    assert reliever.team_id_at_appearance == 146
    assert reliever.appearance_role == 'reliever'
    assert reliever.outing_status == 'active'
    assert reliever.pitches_thrown == 8
    assert reliever.first_observation_id == reliever.latest_observation_id
    assert result.result_json['mutations'] == 3
    assert LiveGameMutation.query.filter_by(
        mutation_type=LiveMutationType.LIVE_RELIEVER_ENTERED.value,
        pitcher_mlb_id=303,
    ).count() == 1
    assert LiveGameMutation.query.filter_by(
        mutation_type=LiveMutationType.LIVE_STARTER_EXITED.value,
        pitcher_mlb_id=101,
    ).count() == 1
    assert SyncJob.query.filter_by(job_name='process_canonical_impact').count() == 1


def test_unchanged_poll_is_zero_mutation_and_update_closes_starter(app):
    _schedule()
    _run(_live_feed())
    follow_up = SyncJob.query.filter_by(job_name='fetch_live_game_delta', status='pending').one()
    follow_up.available_at = datetime.now() - timedelta(seconds=1)
    db.session.commit()
    unchanged = run_next_live_game_delta('live-b', client=FeedClient(_live_feed()))
    assert unchanged.status == STATUS_SUCCEEDED
    assert unchanged.result_json['mutations'] == 0

    next_job = SyncJob.query.filter_by(job_name='fetch_live_game_delta', status='pending').one()
    next_job.available_at = datetime.now() - timedelta(seconds=1)
    db.session.commit()
    updated = _live_feed(timestamp='20260826_010200', reliever_pitches=14, reliever_outs='2.0', inning=8)
    run_next_live_game_delta('live-c', client=FeedClient(updated))
    reliever = ProvisionalPitchingAppearanceState.query.filter_by(pitcher_mlb_id=303).one()
    starter = ProvisionalPitchingAppearanceState.query.filter_by(pitcher_mlb_id=101).one()
    assert reliever.pitches_thrown == 14
    assert reliever.current_inning == 8
    assert starter.outing_status == 'closed'
    assert LiveGameMutation.query.filter_by(
        mutation_type=LiveMutationType.LIVE_MULTI_INNING_REACHED.value,
        pitcher_mlb_id=303,
    ).count() == 1


def test_partial_and_older_observation_do_not_regress_current_state(app):
    _schedule()
    _run(_live_feed(timestamp='20260826_010200', reliever_pitches=14, reliever_outs='2.0'))
    first_count = LiveGameMutation.query.count()
    pending = SyncJob.query.filter_by(job_name='fetch_live_game_delta', status='pending').one()
    pending.available_at = datetime.now() - timedelta(seconds=1)
    db.session.commit()
    partial = _feed(timestamp='20260826_010300', pitcher=303)
    run_next_live_game_delta('live-b', client=FeedClient(partial))
    assert ProvisionalPitchingAppearanceState.query.filter_by(pitcher_mlb_id=303).one().pitches_thrown == 14
    assert LiveGameMutation.query.count() == first_count
    assert SourceObservation.query.order_by(SourceObservation.id.desc()).first().completeness == 'partial'

    pending = SyncJob.query.filter_by(job_name='fetch_live_game_delta', status='pending').one()
    pending.available_at = datetime.now() - timedelta(seconds=1)
    db.session.commit()
    older = _live_feed(timestamp='20260826_010100', reliever_pitches=4, reliever_outs='1.0')
    run_next_live_game_delta('live-c', client=FeedClient(older))
    row = ProvisionalPitchingAppearanceState.query.filter_by(pitcher_mlb_id=303).one()
    assert row.pitches_thrown == 14
    assert LiveGameMutation.query.count() == first_count


def test_newer_counter_regression_is_preserved_as_live_correction(app):
    _schedule()
    _run(_live_feed(timestamp='20260826_010000', reliever_pitches=14, reliever_outs='2.0'))
    pending = SyncJob.query.filter_by(job_name='fetch_live_game_delta', status='pending').one()
    pending.available_at = datetime.now() - timedelta(seconds=1)
    db.session.commit()
    corrected = _live_feed(timestamp='20260826_010200', reliever_pitches=13, reliever_outs='1.2')
    run_next_live_game_delta('live-b', client=FeedClient(corrected))
    row = ProvisionalPitchingAppearanceState.query.filter_by(pitcher_mlb_id=303).one()
    mutation = LiveGameMutation.query.filter_by(
        mutation_type=LiveMutationType.LIVE_APPEARANCE_CORRECTED.value,
        pitcher_mlb_id=303,
    ).one()
    assert row.pitches_thrown == 13
    assert mutation.old_state_json['pitches_thrown'] == 14
    assert mutation.new_state_json['pitches_thrown'] == 13
    assert mutation.is_correction is True


def test_fetch_failure_preserves_current_state_and_records_attempt(app):
    _schedule()
    _run(_live_feed(reliever_pitches=11))
    prior = ProvisionalPitchingAppearanceState.query.filter_by(pitcher_mlb_id=303).one()
    pending = SyncJob.query.filter_by(job_name='fetch_live_game_delta', status='pending').one()
    pending.available_at = datetime.now() - timedelta(seconds=1)
    db.session.commit()
    with pytest.raises(RuntimeError, match='live feed unavailable'):
        run_next_live_game_delta('live-failure', client=FailedClient())
    db.session.expire_all()
    assert ProvisionalPitchingAppearanceState.query.filter_by(pitcher_mlb_id=303).one().pitches_thrown == prior.pitches_thrown
    assert SourceFetchAttempt.query.filter_by(outcome='failed').count() == 1
    assert SyncJob.query.filter_by(id=pending.id).one().status == 'retry_wait'


def test_doubleheader_game_identity_is_game_pk_not_team_date(app):
    _schedule(game_pk=GAME_PK)
    _schedule(game_pk=GAME_PK + 1)
    jobs = plan_live_game_polls(now=datetime(2026, 8, 26, 1, 0))
    assert {job.scope_key for job in jobs} == {str(GAME_PK), str(GAME_PK + 1)}


def test_migration_round_trip_preserves_existing_observation_state():
    engine = sa.create_engine('sqlite:///:memory:')
    metadata = sa.MetaData()
    sa.Table(
        'game_observation_states', metadata,
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('mlb_game_pk', sa.Integer(), nullable=False),
    )
    for name in ('source_observations', 'pitchers', 'final_game_versions', 'sync_runs'):
        sa.Table(name, metadata, sa.Column('id', sa.Integer(), primary_key=True))
    metadata.create_all(engine)
    path = Path(__file__).resolve().parents[1] / 'migrations' / 'versions' / 'f9c2a7e4b1d6_add_live_game_delta.py'
    spec = importlib.util.spec_from_file_location('sp08_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        connection.execute(sa.text('INSERT INTO game_observation_states (id, mlb_game_pk) VALUES (1, 99)'))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        tables = sa.inspect(connection).get_table_names()
        assert 'provisional_pitching_appearance_states' in tables
        assert 'live_game_mutations' in tables
        assert connection.execute(sa.text('SELECT mlb_game_pk FROM game_observation_states')).scalar_one() == 99
        migration.downgrade()
        assert 'live_game_mutations' not in sa.inspect(connection).get_table_names()
        assert connection.execute(sa.text('SELECT mlb_game_pk FROM game_observation_states')).scalar_one() == 99


def test_stale_live_worker_cannot_settle_reclaimed_job(app):
    start = datetime(2026, 8, 26, 1, 0)
    enqueue_live_poll(GAME_PK, GAME_DATE, available_at=start)
    first = claim_next_job('worker-a', job_types=[JobType.FETCH_LIVE_GAME_DELTA],
                           lease_seconds=1, now=start)
    stale_token = first.claim_token
    second = claim_next_job('worker-b', job_types=[JobType.FETCH_LIVE_GAME_DELTA],
                            lease_seconds=30, now=start + timedelta(seconds=2))
    assert first.id == second.id
    with pytest.raises(LeaseOwnershipError):
        succeed_job(first.id, worker_id='worker-a', claim_token=stale_token,
                    now=start + timedelta(seconds=3))


def test_same_game_concurrent_workers_create_one_delta_set_on_postgresql(app):
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL live-game concurrency contract')
    _schedule()
    first = enqueue_live_poll(GAME_PK, GAME_DATE, available_at=datetime.now())
    second = enqueue_live_poll(
        GAME_PK, GAME_DATE, available_at=datetime.now() + timedelta(minutes=1),
        parent_job_id=first.id,
    )
    second.available_at = datetime.now() - timedelta(seconds=1)
    db.session.commit()
    claimed_a = claim_next_job('concurrent-a', job_types=[JobType.FETCH_LIVE_GAME_DELTA])
    claimed_b = claim_next_job('concurrent-b', job_types=[JobType.FETCH_LIVE_GAME_DELTA])
    ids = (claimed_a.id, claimed_b.id)
    barrier = Barrier(2)

    def execute(index):
        with app.app_context():
            job = db.session.get(SyncJob, ids[index])
            barrier.wait(timeout=10)
            from services.live_game_delta import execute_live_game_delta
            result = execute_live_game_delta(job, client=FeedClient(_live_feed()))
            db.session.remove()
            return result['mutations']

    with ThreadPoolExecutor(max_workers=2) as pool:
        counts = list(pool.map(execute, (0, 1)))
    with app.app_context():
        assert sorted(counts) == [0, 3]
        assert ProvisionalPitchingAppearanceState.query.count() == 3
        assert LiveGameMutation.query.count() == 3
