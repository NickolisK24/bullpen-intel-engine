from datetime import datetime, timezone

import pytest
from flask import Flask

from models.game_observation_state import GameObservationState
from models.sync_job import SyncJob
from services import continuous_execution as continuous
from services import game_change_detection as detection
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


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
