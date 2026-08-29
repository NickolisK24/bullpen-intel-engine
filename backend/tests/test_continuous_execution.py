from copy import deepcopy
from datetime import date, datetime, timezone
import pytest
from flask import Flask

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
from tests.test_incremental_publication import ProofCache, _sync_run
from tests.test_incremental_read_model_rebuild import (
    _builders as cu06_builders,
    _snapshot as cu06_snapshot,
)
from models.pitcher import Pitcher
from models.slate_game import SlateGame
from models.sync_run import SyncRun
from utils.db import db


NOW = datetime(2026, 8, 29, 22, 0, tzinfo=timezone.utc)
GAME_PK = 777001


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


class Guard:
    def release(self):
        return None


class Lock:
    acquired = True

    def acquire(self):
        return self.acquired

    def release(self):
        return None


class Metrics:
    def snapshot(self):
        return {'api_calls': 0, 'retries': 0}


class Client:
    metrics = Metrics()


def config(mode, **kwargs):
    values = {
        'mode': mode,
        'enabled': True,
        'expected_plan_fingerprints': {GAME_PK: 'reviewed'},
    }
    values.update(kwargs)
    return continuous.ContinuousExecutionConfig(**values)


def change(*, classification='finalized', changed=True, game_pk=GAME_PK):
    return {
        'game_pk': game_pk,
        'classification': classification,
        'changed': changed,
        'accepted': True,
        'finality_state': 'final_and_usable',
        'current_observation_identity': f'identity-{game_pk}',
        'source_observed_at': '2026-08-29T22:00:00',
        'differences': {'finality.state': {'previous': 'live', 'current': 'final'}},
        'reason': 'newer_upstream_observation',
    }


def detector_for(results, candidates=None):
    candidates = candidates if candidates is not None else [item['game_pk'] for item in results]

    def detector(**kwargs):
        detector.kwargs = kwargs
        return {
            'candidate_game_pks': candidates,
            'games_checked': len([item for item in results if item.get('game_pk')]),
            'unchanged_games': sum(item['classification'] == 'unchanged' for item in results),
            'changed_games': sum(bool(item['changed']) for item in results),
            'source_failures': sum(item['classification'] == 'source_failure' for item in results),
            'requests_expected': 1 + len(candidates),
            'results': results,
        }

    return detector


def patch_run_metadata(monkeypatch):
    monkeypatch.setattr(
        continuous.sync_metadata, 'acquire_sync_writer_guard', lambda **kwargs: Guard(),
    )
    monkeypatch.setattr(
        continuous.sync_metadata, 'start_sync_run', lambda **kwargs: 91,
    )
    monkeypatch.setattr(
        continuous.sync_metadata, 'finish_sync_run', lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(continuous, '_game_data_through', lambda game_pk: date(2026, 8, 29))


def chain_services(calls):
    def orchestrator(value, **kwargs):
        calls.append(('cu03', value['game_pk'], kwargs))
        return {
            'game_pk': value['game_pk'], 'orchestration_status': 'reconciled',
            'cu01_invocations': 1, 'canonical_mutation_performed': True,
            'affected_pitcher_ids': [11, 12], 'affected_team_ids': [21, 22],
        }

    def workload(impact, **kwargs):
        calls.append(('cu04', impact['game_pk'], kwargs))
        return {
            'game_pk': impact['game_pk'], 'status': 'complete', 'parity_status': 'match',
            'recomputation_performed': True, 'data_through': '2026-08-29',
            'availability_reference_date': '2026-08-30',
            'pitchers_recomputed': [11, 12], 'teams_recomputed': [21, 22],
        }

    def team_state(workload_result, **kwargs):
        calls.append(('cu05', workload_result['game_pk'], kwargs))
        return {
            'game_pk': workload_result['game_pk'], 'status': 'complete',
            'parity_status': 'match', 'recomputation_performed': True,
            'data_through': '2026-08-29', 'arm_reads_recomputed': [11, 12],
            'teams_recomputed': [21, 22],
        }

    def read_models(state, **kwargs):
        calls.append(('cu06', state['game_pk'], kwargs))
        return {
            'game_pk': state['game_pk'], 'represented_date': '2026-08-29',
            'status': 'complete', 'parity_status': 'match', 'rebuild_performed': True,
            'requested_team_ids': [21, 22], 'team_boards_rebuilt': [21, 22],
            'league_rows_rebuilt': [21, 22], 'matchups_rebuilt': [GAME_PK],
            'tonight_entries_rebuilt': [GAME_PK], 'pitcher_models_rebuilt': [],
        }

    return orchestrator, workload, team_state, read_models


def run(app, monkeypatch, cfg, *, results=None, **kwargs):
    patch_run_metadata(monkeypatch)
    calls = []
    services = chain_services(calls)
    orchestrator = kwargs.pop('orchestrator', services[0])
    workload_service = kwargs.pop('workload_service', services[1])
    team_state_service = kwargs.pop('team_state_service', services[2])
    read_model_service = kwargs.pop('read_model_service', services[3])
    with app.app_context():
        result = continuous.run_continuous_cycle(
            config=cfg, represented_time=NOW,
            detector=detector_for(results if results is not None else [change()]),
            orchestrator=orchestrator, workload_service=workload_service,
            team_state_service=team_state_service,
            read_model_service=read_model_service,
            client=Client(), cycle_lock_factory=Lock, **kwargs,
        )
    return result, calls


def test_missing_configuration_defaults_off_and_fail_closed():
    cfg, errors = continuous.ContinuousExecutionConfig.from_environment({})
    assert cfg.mode == continuous.ActivationMode.OFF
    assert cfg.enabled is False
    assert errors == ()


def test_invalid_configuration_fails_closed(app):
    cfg, errors = continuous.ContinuousExecutionConfig.from_environment({
        'BASEBALLOS_CONTINUOUS_MODE': 'limited_live',
        'BASEBALLOS_CONTINUOUS_ENABLED': 'true',
    })
    assert set(errors) == {
        'limited_live_allowlist_required', 'production_publication_disabled',
    }
    with app.app_context():
        result = continuous.run_continuous_cycle(
            config=cfg, represented_time=NOW,
        )
    assert result.status == continuous.RESULT_BLOCKED
    assert result.games_checked == 0


def test_off_kill_switch_performs_no_source_work(app):
    with app.app_context():
        result = continuous.run_continuous_cycle(
            config=continuous.ContinuousExecutionConfig(), represented_time=NOW,
            detector=lambda **kwargs: pytest.fail('detector must not run'),
        )
    assert result.status == continuous.RESULT_OFF
    assert result.reason_code == 'mode_off'


def test_shadow_detect_stops_after_cu02(app, monkeypatch):
    result, calls = run(
        app, monkeypatch, config(continuous.ActivationMode.SHADOW_DETECT),
    )
    assert result.status == continuous.RESULT_COMPLETE
    assert result.changed_games == 1
    assert result.skipped_by_mode == 1
    assert result.canonical_actions == 0
    assert calls == []
    assert result.publication_target == 'none'
    assert result.detection_results[0]['game_pk'] == GAME_PK


def test_shadow_detect_persists_non_public_cycle_metadata(app):
    with app.app_context():
        result = continuous.run_continuous_cycle(
            config=config(continuous.ActivationMode.SHADOW_DETECT),
            represented_time=NOW, detector=detector_for([]),
            client=Client(), cycle_lock_factory=Lock,
        )
        row = db.session.get(SyncRun, result.sync_run_id)
        assert row.job_name == continuous.JOB_CONTINUOUS_CYCLE
        assert row.status == 'success'
        assert row.stage == 'continuous_complete'
        assert row.published_dashboard_snapshot_id is None
        assert '"mode": "shadow_detect"' in row.error_message


def test_unchanged_full_chain_performs_no_downstream_work(app, monkeypatch):
    result, calls = run(
        app, monkeypatch, config(continuous.ActivationMode.SHADOW_FULL_CHAIN),
        results=[change(classification='unchanged', changed=False)],
        orchestrator=lambda *_args, **_kwargs: pytest.fail('CU-03 should not be called'),
    )
    assert result.unchanged_games == 1
    assert result.canonical_actions == 0
    assert calls == []


def test_shadow_full_chain_is_bounded_and_nonpublishing(app, monkeypatch):
    result, calls = run(
        app, monkeypatch, config(continuous.ActivationMode.SHADOW_FULL_CHAIN),
    )
    assert [item[0] for item in calls] == ['cu03', 'cu04', 'cu05', 'cu06']
    assert result.canonical_actions == 1
    assert result.canonical_mutation_games == 1
    assert result.affected_pitcher_ids == (11, 12)
    assert result.affected_team_ids == (21, 22)
    assert result.cu04_pitchers_recomputed == 2
    assert result.cu05_arm_reads_recomputed == 2
    assert result.cu06_models_rebuilt == 6
    assert result.publication_candidates == 0
    assert result.production_authority_affected is False


def test_proof_publication_targets_isolated_namespace_once(app, monkeypatch):
    published = []

    def publisher(read_models, **kwargs):
        published.append((read_models, kwargs))
        return {
            'status': 'committed', 'committed': True,
            'production_authority_affected': False,
            'cache_handoff_status': 'complete',
        }

    monkeypatch.setattr(continuous.cu07, 'get_current_publication', lambda: None)
    result, calls = run(
        app, monkeypatch, config(continuous.ActivationMode.PROOF_PUBLICATION),
        proof_publisher=publisher,
    )
    assert len(published) == 1
    assert result.publication_target == 'cu07_incremental_proof'
    assert result.proof_publications == 1
    assert result.live_publications == 0
    assert result.cache_handoffs == 1
    assert result.production_authority_affected is False


def test_limited_live_requires_allowlisted_scope(app, monkeypatch):
    cfg = config(
        continuous.ActivationMode.LIMITED_LIVE,
        production_publication_enabled=True,
        allowlist_game_pks=(999999,),
    )
    result, calls = run(app, monkeypatch, cfg)
    assert result.skipped_by_allowlist == 1
    assert result.canonical_actions == 0
    assert calls == []
    assert result.live_publications == 0


def test_limited_live_simulation_uses_explicit_production_publisher(app, monkeypatch):
    cfg = config(
        continuous.ActivationMode.LIMITED_LIVE,
        production_publication_enabled=True,
        allowlist_game_pks=(GAME_PK,),
    )
    publications = []

    def publisher(read_models, **kwargs):
        publications.append(kwargs)
        return {'committed': True, 'cache_handoff_status': 'complete'}

    result, _calls = run(
        app, monkeypatch, cfg, production_publisher=publisher,
        production_current_id_provider=lambda: 44,
    )
    assert len(publications) == 1
    assert publications[0]['expected_current_id'] == 44
    assert result.live_publications == 1
    assert result.production_authority_affected is True


def test_limited_live_without_publisher_fails_closed(app, monkeypatch):
    cfg = config(
        continuous.ActivationMode.LIMITED_LIVE,
        production_publication_enabled=True,
        allowlist_game_pks=(GAME_PK,),
    )
    result, _calls = run(app, monkeypatch, cfg)
    assert result.status == continuous.RESULT_PARTIAL
    assert result.live_publications == 0
    assert result.failures[0]['error'] == 'production_publisher_unavailable'


def test_full_live_requires_explicit_acknowledgement():
    cfg = config(
        continuous.ActivationMode.FULL_LIVE,
        production_publication_enabled=True,
    )
    assert cfg.validation_errors() == ('full_live_acknowledgement_required',)


def test_source_budget_caps_candidates_before_feed_requests(app, monkeypatch):
    captured = {}

    def detector(**kwargs):
        captured.update(kwargs)
        return {
            'candidate_game_pks': [], 'games_checked': 0, 'unchanged_games': 0,
            'changed_games': 0, 'source_failures': 0, 'requests_expected': 1,
            'results': [],
        }

    patch_run_metadata(monkeypatch)
    with app.app_context():
        result = continuous.run_continuous_cycle(
            config=config(
                continuous.ActivationMode.SHADOW_DETECT,
                source_request_budget=4, max_games=15,
            ),
            represented_time=NOW, detector=detector, client=Client(),
            cycle_lock_factory=Lock,
        )
    assert captured['max_games'] == 3
    assert result.source_requests == 1


def test_core_source_failure_breaker_stops_chain(app, monkeypatch):
    failures = [
        change(classification='source_failure', changed=False, game_pk=GAME_PK + index)
        for index in range(3)
    ]
    result, calls = run(
        app, monkeypatch,
        config(continuous.ActivationMode.SHADOW_FULL_CHAIN, core_failure_breaker=2),
        results=failures,
    )
    assert result.circuit_breaker_open is True
    assert result.status == continuous.RESULT_PARTIAL
    assert calls == []


def test_one_game_failure_does_not_block_independent_game(app, monkeypatch):
    second = GAME_PK + 1
    patch_run_metadata(monkeypatch)
    monkeypatch.setattr(continuous, '_game_data_through', lambda game_pk: date(2026, 8, 29))
    calls = []
    services = chain_services(calls)

    def orchestrator(value, **kwargs):
        if value['game_pk'] == GAME_PK:
            raise RuntimeError('controlled failure')
        result = services[0](value, **kwargs)
        result['affected_pitcher_ids'] = [13]
        result['affected_team_ids'] = [23]
        return result

    cfg = config(
        continuous.ActivationMode.SHADOW_FULL_CHAIN,
        expected_plan_fingerprints={GAME_PK: 'a', second: 'b'},
    )
    with app.app_context():
        result = continuous.run_continuous_cycle(
            config=cfg, represented_time=NOW,
            detector=detector_for([change(), change(game_pk=second)]),
            orchestrator=orchestrator, workload_service=services[1],
            team_state_service=services[2], read_model_service=services[3],
            client=Client(), cycle_lock_factory=Lock,
        )
    assert result.status == continuous.RESULT_PARTIAL
    assert result.failures[0]['scope'] == 'orchestration'
    assert result.canonical_mutation_games == 1
    assert result.affected_pitcher_ids == (13,)
    assert result.affected_team_ids == (23,)


def test_second_overlapping_cycle_skips_cleanly(app):
    class BusyLock(Lock):
        acquired = False

    with app.app_context():
        result = continuous.run_continuous_cycle(
            config=config(continuous.ActivationMode.SHADOW_DETECT),
            represented_time=NOW, cycle_lock_factory=BusyLock,
        )
    assert result.status == continuous.RESULT_SKIPPED
    assert result.reason_code == 'cycle_already_running'
    assert result.games_checked == 0


def test_postgresql_cycle_advisory_lock_has_one_winner(app):
    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('PostgreSQL advisory-lock proof')
        first = continuous.ContinuousCycleLock()
        second = continuous.ContinuousCycleLock()
        assert first.acquire() is True
        try:
            assert second.acquire() is False
        finally:
            first.release()
        third = continuous.ContinuousCycleLock()
        assert third.acquire() is True
        third.release()


def test_existing_public_writer_conflict_skips_before_detection(app, monkeypatch):
    patch_run_metadata(monkeypatch)

    def blocked(**kwargs):
        raise continuous.sync_metadata.SyncWriterConflict(
            reason=continuous.sync_metadata.SYNC_WRITER_ALREADY_RUNNING,
            job_name='postgame_refresh', source='scheduled',
        )

    monkeypatch.setattr(
        continuous.sync_metadata, 'acquire_sync_writer_guard', blocked,
    )
    with app.app_context():
        result = continuous.run_continuous_cycle(
            config=config(continuous.ActivationMode.SHADOW_FULL_CHAIN),
            represented_time=NOW,
            detector=lambda **kwargs: pytest.fail('detector must not overlap writer'),
            client=Client(), cycle_lock_factory=Lock,
        )
    assert result.status == continuous.RESULT_SKIPPED
    assert result.reason_code == continuous.sync_metadata.SYNC_WRITER_ALREADY_RUNNING
    assert result.games_checked == 0


def test_fifteen_game_unchanged_slate_does_zero_chain_work(app, monkeypatch):
    results = [
        change(classification='unchanged', changed=False, game_pk=GAME_PK + index)
        for index in range(15)
    ]
    result, calls = run(
        app, monkeypatch, config(continuous.ActivationMode.SHADOW_FULL_CHAIN),
        results=results,
    )
    assert result.games_checked == 15
    assert result.unchanged_games == 15
    assert result.canonical_actions == 0
    assert result.canonical_mutation_games == 0
    assert calls == []


def test_multi_cycle_change_then_replay_only_runs_chain_once(app, monkeypatch):
    cfg = config(continuous.ActivationMode.SHADOW_FULL_CHAIN)
    first, first_calls = run(app, monkeypatch, cfg, results=[change()])
    replay, replay_calls = run(
        app, monkeypatch, cfg,
        results=[change(classification='unchanged', changed=False)],
    )
    assert first.canonical_mutation_games == 1
    assert [item[0] for item in first_calls] == ['cu03', 'cu04', 'cu05', 'cu06']
    assert replay.canonical_actions == 0
    assert replay.canonical_mutation_games == 0
    assert replay_calls == []


def test_kill_switch_stops_next_cycle_without_touching_schedulers(app, monkeypatch):
    active, _calls = run(
        app, monkeypatch, config(continuous.ActivationMode.SHADOW_DETECT),
    )
    disabled = continuous.ContinuousExecutionConfig(
        mode=continuous.ActivationMode.SHADOW_DETECT,
        enabled=False,
    )
    with app.app_context():
        killed = continuous.run_continuous_cycle(
            config=disabled, represented_time=NOW,
            detector=lambda **kwargs: pytest.fail('disabled cycle must not fetch'),
        )
    assert active.status == continuous.RESULT_COMPLETE
    assert killed.status == continuous.RESULT_OFF
    assert killed.reason_code == 'kill_switch_disabled'


def test_proof_publication_honors_max_cohorts(app, monkeypatch):
    second = GAME_PK + 1
    cfg = config(
        continuous.ActivationMode.PROOF_PUBLICATION,
        expected_plan_fingerprints={GAME_PK: 'a', second: 'b'},
        max_publication_cohorts=1,
    )
    publications = []

    def publisher(read_models, **kwargs):
        publications.append(kwargs)
        return {'committed': True, 'cache_handoff_status': 'complete'}

    monkeypatch.setattr(continuous.cu07, 'get_current_publication', lambda: None)
    result, _calls = run(
        app, monkeypatch, cfg,
        results=[change(), change(game_pk=second)],
        proof_publisher=publisher,
    )
    assert len(publications) == 1
    assert result.publication_candidates == 1
    assert result.proof_publications == 1


def test_scheduler_files_do_not_activate_continuous_command():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    workflow_text = '\n'.join(
        path.read_text(encoding='utf-8')
        for path in (root / '.github' / 'workflows').glob('*.yml')
    )
    assert 'run_continuous_cycle.py' not in workflow_text
    assert not (root / 'render.yaml').exists()


def test_cycle_service_has_no_scheduler_or_what_changed_side_effects():
    from pathlib import Path

    source = Path(continuous.__file__).read_text(encoding='utf-8')
    forbidden = (
        'run_daily_sync(', 'run_postgame_refresh(', 'while True',
        'publish_share_artifact(', 'WhatChanged', 'team_changes',
        'invalidate_cache(',
    )
    assert [token for token in forbidden if token in source] == []


def test_strongest_real_shape_cycle_reaches_only_cu07_proof(app, monkeypatch):
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
        changed = detection.observe_game_change(
            REAL_GAME_PK,
            payload=observation(
                timestamp='20260827_230000', status='Final', code='F',
                inning=9, outs=3,
            ),
        )
        reviewed = game_driven_ingestion.run_game_driven_ingestion(
            GAME_DATE,
            mode=game_driven_ingestion.MODE_SHADOW,
            only_game_pks=[REAL_GAME_PK],
        )
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

        monkeypatch.setattr(
            continuous.sync_metadata, 'acquire_sync_writer_guard',
            lambda **kwargs: Guard(),
        )
        monkeypatch.setattr(
            continuous.sync_metadata, 'start_sync_run', lambda **kwargs: _sync_run(),
        )
        monkeypatch.setattr(
            continuous.sync_metadata, 'finish_sync_run', lambda *args, **kwargs: None,
        )
        cache = ProofCache()
        result = continuous.run_continuous_cycle(
            config=config(
                continuous.ActivationMode.PROOF_PUBLICATION,
                expected_plan_fingerprints={
                    REAL_GAME_PK: reviewed['complete_reconciliation_fingerprint'],
                },
            ),
            represented_time=datetime.combine(
                GAME_DATE, datetime.min.time(), tzinfo=timezone.utc,
            ),
            detector=detector_for([changed.to_dict()], [REAL_GAME_PK]),
            team_state_service=state_service,
            read_model_service=read_service,
            cache_adapter=cache,
            client=Client(), cycle_lock_factory=Lock,
        )

        assert result.status == continuous.RESULT_COMPLETE
        assert result.canonical_actions == 1
        assert result.canonical_mutation_games == 1
        assert len(result.affected_pitcher_ids) == 2
        assert result.affected_team_ids == tuple(sorted((AWAY_TEAM, HOME_TEAM)))
        assert result.cu04_pitchers_recomputed == 2
        assert result.cu05_arm_reads_recomputed == 2
        assert result.proof_publications == 1
        assert result.live_publications == 0
        assert result.cache_handoffs == 1
        assert result.production_authority_affected is False
