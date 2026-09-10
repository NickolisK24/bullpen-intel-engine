from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import json
import multiprocessing

import pytest
from flask import Flask
from sqlalchemy import text

from models.game_observation_state import GameObservationState
from models.pitcher import Pitcher
from models.slate_game import SlateGame
from models.sync_job import SyncJob
from services import continuous_execution as continuous
from services import game_change_detection as detection
from services import game_driven_ingestion
from services import incremental_arm_read_team_state as cu05
from services import incremental_read_model_rebuild as cu06
from services import sync as sync_service
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.game_driven_fixtures import schedule_final_game
from tests.test_continuous_reliever_ingestion import (
    AWAY_TEAM,
    GAME_DATE,
    GAME_PK as REAL_GAME_PK,
    HOME_TEAM,
    _boxscore,
    _play_by_play,
    _seed_pitchers,
)
from tests.test_game_change_detection import _feed
from tests.test_incremental_arm_read_team_state import _fake_provider
from tests.test_incremental_read_model_rebuild import (
    _builders as cu06_builders,
    _snapshot as cu06_snapshot,
)
from utils.db import db
from utils.time import utc_now_naive


GAME_PK = 822690
OTHER_GAME_PK = 822691
PLAN = 'a' * 64
NOW = datetime(2026, 8, 29, 22, 0, tzinfo=timezone.utc)


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


class Lock:
    def __init__(self, acquired=True):
        self.acquired = acquired

    def acquire(self):
        return self.acquired

    def release(self):
        return None


class Client:
    class Metrics:
        @staticmethod
        def snapshot():
            return {'api_calls': 0, 'retries': 0}

    metrics = Metrics()


def _postgres_replay_worker(hold, started, release, output):
    """Independent-process replay claimant used only by the PostgreSQL proof."""
    flask_app = Flask('cu08s-postgres-worker')
    configure_test_database(flask_app)
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(flask_app)
    with flask_app.app_context():
        continuous.sync_metadata.acquire_sync_writer_guard = (
            lambda **_kwargs: type(
                'Guard', (), {'release': lambda self: None},
            )()
        )
        continuous.sync_metadata.start_sync_run = lambda **_kwargs: None
        continuous.sync_metadata.finish_sync_run = lambda *_args, **_kwargs: None
        continuous._game_data_through = lambda _game_pk: NOW.date()

        def orchestrator(_change, **_kwargs):
            if hold:
                started.set()
                release.wait(timeout=20)
            return _impact(mutated=False)

        result = continuous.run_continuous_cycle(
            config=_config(), represented_time=NOW, client=Client(),
            detector=_detector(), orchestrator=orchestrator,
            workload_service=lambda *_args, **_kwargs: None,
            team_state_service=lambda *_args, **_kwargs: None,
            read_model_service=lambda *_args, **_kwargs: None,
        )
        output.put({
            'status': result.status,
            'reason_code': result.reason_code,
            'replay_results': list(result.replay_results),
            'canonical_actions': result.canonical_actions,
        })
        db.session.remove()


def _config(**changes):
    values = {
        'mode': continuous.ActivationMode.SHADOW_FULL_CHAIN,
        'enabled': True,
        'production_publication_enabled': False,
        'allowlist_game_pks': (GAME_PK,),
        'expected_plan_fingerprints': {GAME_PK: PLAN},
        'replay_game_pks': (GAME_PK,),
    }
    values.update(changes)
    return continuous.ContinuousExecutionConfig(**values)


def _stored_observation(
    *, game_pk=GAME_PK, classification=detection.FINALIZED,
    finality='final_pending_data', authority=detection.SOURCE_AUTHORITY,
):
    row = GameObservationState(
        mlb_game_pk=game_pk,
        observation_fingerprint='b' * 64,
        previous_observation_fingerprint='c' * 64,
        observation={
            'game_pk': game_pk,
            'identity': {'official_date': '2026-08-29'},
            'finality': {'state': finality},
        },
        source_authority=authority,
        source_endpoint=detection.SOURCE_ENDPOINT.format(game_pk=game_pk),
        source_observed_at=datetime(2026, 8, 29, 21, 0),
        finality_state=finality,
        last_classification=classification,
        last_change_summary={
            'finality.state': {'previous': 'live', 'current': finality},
        },
        accepted_at=datetime(2026, 8, 29, 21, 0),
    )
    db.session.add(row)
    db.session.commit()
    return row


def _detector(results=()):
    def detect(**_kwargs):
        return {
            'candidate_game_pks': [], 'games_checked': len(results),
            'unchanged_games': sum(
                item.get('classification') == detection.UNCHANGED for item in results
            ),
            'changed_games': sum(bool(item.get('changed')) for item in results),
            'source_failures': 0, 'requests_expected': 1,
            'results': list(results),
        }
    return detect


def _patch_metadata(monkeypatch):
    monkeypatch.setattr(
        continuous.sync_metadata, 'acquire_sync_writer_guard',
        lambda **_kwargs: type('Guard', (), {'release': lambda self: None})(),
    )
    monkeypatch.setattr(
        continuous.sync_metadata, 'start_sync_run', lambda **_kwargs: None,
    )
    monkeypatch.setattr(
        continuous.sync_metadata, 'finish_sync_run', lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        continuous, '_game_data_through', lambda _game_pk: NOW.date(),
    )


def _run(app, monkeypatch, cfg, orchestrator, *, lock=True, services=None):
    _patch_metadata(monkeypatch)
    calls = []

    def workload(impact, **_kwargs):
        calls.append(('cu04', impact['game_pk']))
        return {'game_pk': impact['game_pk'], 'pitchers_recomputed': [11],
                'teams_recomputed': [21]}

    def team_state(result, **_kwargs):
        calls.append(('cu05', result['game_pk']))
        return {'game_pk': result['game_pk'], 'arm_reads_recomputed': [11],
                'teams_recomputed': [21]}

    def read_models(result, **_kwargs):
        calls.append(('cu06', result['game_pk']))
        return {'game_pk': result['game_pk'], 'team_boards_rebuilt': [21]}

    selected = services or (workload, team_state, read_models)
    with app.app_context():
        result = continuous.run_continuous_cycle(
            config=cfg, represented_time=NOW, client=Client(),
            detector=_detector(), orchestrator=orchestrator,
            workload_service=selected[0], team_state_service=selected[1],
            read_model_service=selected[2],
            cycle_lock_factory=lambda: Lock(lock),
        )
        return result, calls


def _impact(*, mutated):
    return {
        'game_pk': GAME_PK,
        'orchestration_status': 'reconciled',
        'canonical_action_attempted': True,
        'cu01_invocations': 1,
        'canonical_mutation_performed': mutated,
        'affected_pitcher_ids': [11] if mutated else [],
        'affected_team_ids': [21] if mutated else [],
    }


def test_governed_replay_mutates_once_then_is_consumed(app, monkeypatch):
    seen = []
    with app.app_context():
        _stored_observation()

    def orchestrator(change, **kwargs):
        seen.append((change, kwargs))
        return _impact(mutated=True)

    first, downstream = _run(app, monkeypatch, _config(), orchestrator)
    assert len(seen) == 1
    assert seen[0][0]['current_observation_identity'] == 'b' * 64
    assert seen[0][1] == {
        'allow_canonical_write': True,
        'expected_plan_fingerprint': PLAN,
    }
    assert first.replay_results[0]['outcome'] == 'mutated'
    assert first.replay_results[0]['status'] == 'consumed'
    assert downstream == [('cu04', GAME_PK), ('cu05', GAME_PK), ('cu06', GAME_PK)]

    second, second_downstream = _run(app, monkeypatch, _config(), orchestrator)
    assert len(seen) == 1
    assert second.replay_results[0]['reason_code'] == 'replay_already_consumed'
    assert second_downstream == []
    with app.app_context():
        assert SyncJob.query.one().attempts == 1


def test_authorized_no_op_is_consumed_without_downstream(app, monkeypatch):
    with app.app_context():
        _stored_observation()
    result, downstream = _run(
        app, monkeypatch, _config(), lambda *_args, **_kwargs: _impact(mutated=False),
    )
    assert result.replay_results[0]['outcome'] == 'authorized_no_op'
    assert result.canonical_mutation_games == 0
    assert result.affected_pitcher_ids == ()
    assert result.affected_team_ids == ()
    assert downstream == []


@pytest.mark.parametrize(
    ('config_changes', 'row_changes', 'reason'),
    (
        ({'allowlist_game_pks': ()}, {}, 'game_not_allowlisted'),
        ({'expected_plan_fingerprints': {}}, {}, 'missing_fingerprint'),
        ({'expected_plan_fingerprints': {GAME_PK: 'bad'}}, {}, 'malformed_fingerprint'),
        ({}, {'classification': detection.STALE_OBSERVATION}, 'stale_observation'),
        ({}, {'classification': detection.AMBIGUOUS_OBSERVATION}, 'ambiguous_observation'),
        ({}, {'finality': 'live'}, 'observation_not_final'),
        ({}, {'authority': 'weaker'}, 'weaker_authority'),
    ),
)
def test_replay_refuses_invalid_authorization_or_observation(
    app, monkeypatch, config_changes, row_changes, reason,
):
    with app.app_context():
        _stored_observation(**row_changes)
    result, calls = _run(
        app, monkeypatch, _config(**config_changes),
        lambda *_args, **_kwargs: pytest.fail('CU-03 must not run'),
    )
    assert result.replay_results[0]['status'] == 'refused'
    assert result.replay_results[0]['reason_code'] == reason
    assert calls == []
    with app.app_context():
        assert SyncJob.query.count() == 0


def test_no_replay_request_preserves_normal_unchanged_behavior(app, monkeypatch):
    with app.app_context():
        _stored_observation()
    result, calls = _run(
        app, monkeypatch, _config(replay_game_pks=()),
        lambda *_args, **_kwargs: pytest.fail('CU-03 must not run'),
    )
    assert result.replay_results == ()
    assert calls == []


def test_failed_replay_retries_at_most_twice(app, monkeypatch):
    with app.app_context():
        _stored_observation()

    def fail(*_args, **_kwargs):
        raise RuntimeError('controlled failure before canonical commit')

    first, _ = _run(app, monkeypatch, _config(), fail)
    second, _ = _run(app, monkeypatch, _config(), fail)
    third, _ = _run(app, monkeypatch, _config(), fail)
    assert first.replay_results[0]['status'] == 'failed'
    assert second.replay_results[0]['status'] == 'failed'
    assert third.replay_results[0]['status'] == 'inert'
    assert third.replay_results[0]['reason_code'] == 'replay_attempts_exhausted'
    with app.app_context():
        assert SyncJob.query.one().attempts == 2


def test_restart_keeps_consumed_replay_inert(app, monkeypatch):
    with app.app_context():
        _stored_observation()
    _run(app, monkeypatch, _config(), lambda *_args, **_kwargs: _impact(mutated=False))
    with app.app_context():
        db.session.remove()
    result, _ = _run(
        app, monkeypatch, _config(),
        lambda *_args, **_kwargs: pytest.fail('consumed replay must remain inert'),
    )
    assert result.replay_results[0]['reason_code'] == 'replay_already_consumed'


def test_cycle_lock_allows_no_second_replay_claim(app, monkeypatch):
    with app.app_context():
        _stored_observation()
    result, _ = _run(
        app, monkeypatch, _config(),
        lambda *_args, **_kwargs: pytest.fail('blocked cycle must not run'),
        lock=False,
    )
    assert result.reason_code == 'cycle_already_running'
    with app.app_context():
        assert SyncJob.query.count() == 0


def test_replay_requires_publication_disabled_shadow_full_chain(app, monkeypatch):
    with app.app_context():
        _stored_observation()
    result, _ = _run(
        app, monkeypatch,
        _config(production_publication_enabled=True),
        lambda *_args, **_kwargs: pytest.fail('CU-03 must not run'),
    )
    assert result.replay_results[0]['reason_code'] == 'publication_gate_invalid'
    assert result.live_publications == 0
    assert result.cache_handoffs == 0
    assert result.production_authority_affected is False


def test_malformed_replay_environment_fails_closed():
    cfg, errors = continuous.ContinuousExecutionConfig.from_environment({
        'BASEBALLOS_CONTINUOUS_MODE': 'shadow_full_chain',
        'BASEBALLOS_CONTINUOUS_ENABLED': 'true',
        'BASEBALLOS_CONTINUOUS_REPLAY_GAME_PKS': 'not-a-game',
    })
    assert cfg.replay_game_pks == ()
    assert 'invalid_replay_game_allowlist' in errors


def test_render_shaped_environment_and_cli_mode_discover_stored_final_replay(
    app, monkeypatch,
):
    game_pk = 823665
    fingerprint = (
        '53c269913f3ccaaabca551e8a5d16f0ace42cb11b3ac72ff8532c0ddc424a043'
    )
    monkeypatch.setenv('BASEBALLOS_CONTINUOUS_MODE', 'off')
    monkeypatch.setenv('BASEBALLOS_CONTINUOUS_ENABLED', 'true')
    monkeypatch.setenv('BASEBALLOS_CONTINUOUS_ALLOWLIST_GAME_PKS', str(game_pk))
    monkeypatch.setenv(
        'BASEBALLOS_CONTINUOUS_PLAN_FINGERPRINTS',
        json.dumps({str(game_pk): fingerprint}, separators=(',', ':')),
    )
    monkeypatch.setenv('BASEBALLOS_CONTINUOUS_REPLAY_GAME_PKS', str(game_pk))
    monkeypatch.setenv('BASEBALLOS_CONTINUOUS_PUBLICATION_ENABLED', 'false')
    _patch_metadata(monkeypatch)
    with app.app_context():
        _stored_observation(game_pk=game_pk)

        calls = []

        def orchestrator(change, **kwargs):
            calls.append((change['game_pk'], kwargs))
            return {
                **_impact(mutated=False),
                'game_pk': game_pk,
            }

        first = continuous.run_continuous_cycle(
            mode='shadow_full_chain', represented_time=NOW,
            client=Client(), detector=_detector(), orchestrator=orchestrator,
            workload_service=lambda *_args, **_kwargs: None,
            team_state_service=lambda *_args, **_kwargs: None,
            read_model_service=lambda *_args, **_kwargs: None,
            cycle_lock_factory=Lock,
        )
        second = continuous.run_continuous_cycle(
            mode='shadow_full_chain', represented_time=NOW,
            client=Client(), detector=_detector(), orchestrator=orchestrator,
            workload_service=lambda *_args, **_kwargs: None,
            team_state_service=lambda *_args, **_kwargs: None,
            read_model_service=lambda *_args, **_kwargs: None,
            cycle_lock_factory=Lock,
        )

    assert calls == [(
        game_pk,
        {
            'allow_canonical_write': True,
            'expected_plan_fingerprint': fingerprint,
        },
    )]
    assert first.replay_results[0]['outcome'] == 'authorized_no_op'
    assert [event['event'] for event in first.replay_results[0]['events']] == [
        'game_replay_requested',
        'game_replay_authorized',
        'game_replay_completed',
    ]
    assert second.replay_results[0]['reason_code'] == 'replay_already_consumed'
    assert [event['event'] for event in second.replay_results[0]['events']] == [
        'game_replay_requested',
        'game_replay_refused',
    ]


def test_crash_like_stale_claim_recovers_once_then_consumes(app, monkeypatch):
    with app.app_context():
        _stored_observation()
        changes, results = continuous._prepare_governed_replays(
            _config(), [], sync_run_id=None,
        )
        assert len(changes) == 1
        assert results[0]['status'] == 'authorized'
        job = SyncJob.query.one()
        assert job.status == 'running'
        assert job.attempts == 1
        db.session.remove()

    immediate, _ = _run(
        app, monkeypatch, _config(),
        lambda *_args, **_kwargs: pytest.fail('active claim must not execute'),
    )
    assert immediate.replay_results[0]['reason_code'] == 'replay_claimed_elsewhere'

    with app.app_context():
        job = SyncJob.query.one()
        job.last_heartbeat_at = utc_now_naive() - timedelta(minutes=61)
        db.session.commit()
        db.session.remove()

    recovered, _ = _run(
        app, monkeypatch, _config(),
        lambda *_args, **_kwargs: _impact(mutated=False),
    )
    assert recovered.replay_results[0]['outcome'] == 'authorized_no_op'
    with app.app_context():
        job = SyncJob.query.one()
        assert job.status == 'succeeded'
        assert job.attempts == 2


def test_database_failure_rolls_back_then_bounded_retry_succeeds(app, monkeypatch):
    with app.app_context():
        _stored_observation()

    def database_failure(*_args, **_kwargs):
        db.session.execute(text('SELECT * FROM cu08s_table_that_does_not_exist'))

    first, first_downstream = _run(
        app, monkeypatch, _config(), database_failure,
    )
    assert first.replay_results[0]['status'] == 'failed'
    assert first_downstream == []
    with app.app_context():
        failed = SyncJob.query.one()
        assert failed.status == 'failed'
        assert failed.attempts == 1

    retry, retry_downstream = _run(
        app, monkeypatch, _config(),
        lambda *_args, **_kwargs: _impact(mutated=False),
    )
    assert retry.replay_results[0]['outcome'] == 'authorized_no_op'
    assert retry_downstream == []
    with app.app_context():
        completed = SyncJob.query.one()
        assert completed.status == 'succeeded'
        assert completed.attempts == 2


def test_revoked_request_and_cross_game_fingerprint_cannot_execute(app, monkeypatch):
    with app.app_context():
        _stored_observation()
        _stored_observation(game_pk=OTHER_GAME_PK)

    revoked, _ = _run(
        app, monkeypatch, _config(replay_game_pks=()),
        lambda *_args, **_kwargs: pytest.fail('revoked request must not execute'),
    )
    assert revoked.replay_results == ()

    wrong_game, _ = _run(
        app, monkeypatch,
        _config(
            replay_game_pks=(OTHER_GAME_PK,),
            allowlist_game_pks=(OTHER_GAME_PK,),
            expected_plan_fingerprints={GAME_PK: PLAN},
        ),
        lambda *_args, **_kwargs: pytest.fail('wrong-game fingerprint must refuse'),
    )
    assert wrong_game.replay_results[0]['reason_code'] == 'missing_fingerprint'


def test_four_recurring_cycles_execute_replay_only_once(app, monkeypatch):
    with app.app_context():
        _stored_observation()
    calls = []

    def orchestrator(*_args, **_kwargs):
        calls.append('cu03')
        return _impact(mutated=False)

    results = [
        _run(app, monkeypatch, _config(), orchestrator)[0]
        for _index in range(4)
    ]
    assert calls == ['cu03']
    assert results[0].replay_results[0]['outcome'] == 'authorized_no_op'
    assert [
        result.replay_results[0]['reason_code'] for result in results[1:]
    ] == ['replay_already_consumed'] * 3


def test_real_shape_replay_mutates_cu01_then_runs_bounded_cu04_to_cu06(
    app, monkeypatch,
):
    class SourceClient:
        def get_game_boxscore(self, game_pk):
            assert game_pk == REAL_GAME_PK
            return _boxscore()

        def get_game_play_by_play(self, game_pk):
            assert game_pk == REAL_GAME_PK
            return _play_by_play()

    def observation(*, timestamp, status='Live', code='I', inning=8, outs=1):
        payload = deepcopy(_feed(
            timestamp=timestamp, status=status, code=code,
            inning=inning, outs=outs,
        ))
        payload['gamePk'] = REAL_GAME_PK
        payload['gameData']['datetime'].update({
            'dateTime': f'{GAME_DATE.isoformat()}T19:00:00Z',
            'originalDate': GAME_DATE.isoformat(),
            'officialDate': GAME_DATE.isoformat(),
        })
        payload['gameData']['teams'] = {
            'away': {'id': AWAY_TEAM}, 'home': {'id': HOME_TEAM},
        }
        return payload

    with app.app_context():
        _seed_pitchers()
        schedule_final_game(REAL_GAME_PK, game_date=GAME_DATE)
        monkeypatch.setattr(sync_service, 'mlb_client', SourceClient())
        detection.observe_game_change(
            REAL_GAME_PK, payload=observation(timestamp='20260827_220000'),
        )
        accepted = detection.observe_game_change(
            REAL_GAME_PK,
            payload=observation(
                timestamp='20260827_230000', status='Final', code='F',
                inning=9, outs=3,
            ),
        )
        assert accepted.classification == detection.FINALIZED
        reviewed = game_driven_ingestion.run_game_driven_ingestion(
            GAME_DATE, mode=game_driven_ingestion.MODE_SHADOW,
            only_game_pks=[REAL_GAME_PK],
        )
        plan = reviewed['complete_reconciliation_fingerprint']
        snapshot = cu06_snapshot(team_ids=(AWAY_TEAM, HOME_TEAM, 30))
        snapshot.data_through = GAME_DATE
        snapshot.availability_reference_date = GAME_DATE
        snapshot.payload['freshness']['data_through'] = GAME_DATE.isoformat()
        snapshot.payload['trusted_team_boards']['data_through'] = GAME_DATE.isoformat()
        snapshot.payload['trusted_team_boards']['availability_reference_date'] = (
            GAME_DATE.isoformat()
        )
        db.session.merge(SlateGame(
            game_pk=REAL_GAME_PK, game_date_et=GAME_DATE,
            game_time_utc=datetime.combine(GAME_DATE, datetime.min.time()),
            home_team_id=HOME_TEAM, away_team_id=AWAY_TEAM,
            normalized_state=SlateGame.STATE_COMPLETED,
        ))
        db.session.commit()

        def state_service(workload, **_kwargs):
            membership = lambda team_id, _date: (
                frozenset(
                    row.id for row in Pitcher.query.filter_by(team_id=team_id).all()
                ),
                True,
            )
            return cu05.recompute_arm_reads_team_state(
                workload, readiness_provider=_fake_provider(),
                membership_provider=membership,
            )

        builders = cu06_builders([])

        def read_service(state, **_kwargs):
            snapshot.availability_reference_date = date.fromisoformat(
                state.availability_reference_date
            )
            snapshot.payload['trusted_team_boards']['availability_reference_date'] = (
                state.availability_reference_date
            )
            return cu06.rebuild_read_model_impact(
                state, source_snapshot=snapshot,
                team_board_builder=builders[0], league_listing_builder=builders[1],
                matchup_builder=builders[2], tonight_builder=builders[3],
            )

        _patch_metadata(monkeypatch)
        config = _config(
            allowlist_game_pks=(REAL_GAME_PK,),
            expected_plan_fingerprints={REAL_GAME_PK: plan},
            replay_game_pks=(REAL_GAME_PK,),
        )
        first = continuous.run_continuous_cycle(
            config=config,
            represented_time=datetime.combine(
                GAME_DATE, datetime.min.time(), tzinfo=timezone.utc,
            ),
            detector=_detector(), team_state_service=state_service,
            read_model_service=read_service, client=Client(),
            cycle_lock_factory=Lock,
        )
        assert first.replay_results[0]['outcome'] == 'mutated'
        assert first.canonical_actions == 1
        assert first.canonical_mutation_games == 1
        assert len(first.affected_pitcher_ids) == 2
        assert first.affected_team_ids == tuple(sorted((AWAY_TEAM, HOME_TEAM)))
        assert first.cu04_pitchers_recomputed == 2
        assert first.cu05_arm_reads_recomputed == 2
        assert first.cu06_models_rebuilt > 0
        assert first.live_publications == 0
        assert first.cache_handoffs == 0
        assert first.production_authority_affected is False

        db.session.remove()
        replay = continuous.run_continuous_cycle(
            config=config,
            represented_time=datetime.combine(
                GAME_DATE, datetime.min.time(), tzinfo=timezone.utc,
            ),
            detector=_detector(),
            orchestrator=lambda *_args, **_kwargs: pytest.fail(
                'consumed real replay must not invoke CU-03'
            ),
            client=Client(), cycle_lock_factory=Lock,
        )
        assert replay.replay_results[0]['reason_code'] == 'replay_already_consumed'
        assert replay.canonical_actions == 0
        assert replay.live_publications == 0
        assert replay.cache_handoffs == 0


def test_postgresql_two_processes_have_one_replay_winner(app):
    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('PostgreSQL independent-process replay proof')
        _stored_observation()
        db.session.remove()

    context = multiprocessing.get_context('spawn')
    started = context.Event()
    release = context.Event()
    output = context.Queue()
    first = context.Process(
        target=_postgres_replay_worker,
        args=(True, started, release, output),
    )
    second = context.Process(
        target=_postgres_replay_worker,
        args=(False, started, release, output),
    )
    first.start()
    assert started.wait(timeout=20), 'first claimant did not reach CU-03'
    second.start()
    second.join(timeout=20)
    assert second.exitcode == 0
    release.set()
    first.join(timeout=20)
    assert first.exitcode == 0

    outcomes = [output.get(timeout=5), output.get(timeout=5)]
    assert sorted(item['status'] for item in outcomes) == ['complete', 'skipped']
    winner = next(item for item in outcomes if item['status'] == 'complete')
    loser = next(item for item in outcomes if item['status'] == 'skipped')
    assert winner['canonical_actions'] == 1
    assert winner['replay_results'][0]['outcome'] == 'authorized_no_op'
    assert loser['reason_code'] == 'cycle_already_running'
    assert loser['canonical_actions'] == 0

    with app.app_context():
        job = SyncJob.query.one()
        assert job.status == 'succeeded'
        assert job.attempts == 1
