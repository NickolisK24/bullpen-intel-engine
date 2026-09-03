from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import pytest
from flask import Flask

from services import continuous_execution as continuous
from services import game_change_detection as detection
from services import game_driven_ingestion
from services import incremental_arm_read_team_state as cu05
from services import incremental_publication as cu07
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
from tests.test_game_change_detection import _equal_timestamp_final_incident
from tests.test_incremental_arm_read_team_state import _fake_provider
from tests.test_incremental_publication import ProofCache, _sync_run
from tests.test_incremental_read_model_rebuild import (
    _builders as cu06_builders,
    _snapshot as cu06_snapshot,
)
from models.dashboard_snapshot import DashboardSnapshot
from models.game_ingestion_work_item import GameIngestionWorkItem
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.game_observation_state import GameObservationState
from models.play_by_play_foundation import GamePitchEvent
from models.slate_game import SlateGame
from models.sync_job import SyncJob
from models.sync_run import SyncRun
from services import continuous_game_work
from services import sync_jobs
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
        db.session.add_all([
            SyncRun(
                id=sync_run_id,
                job_name='continuous_cycle_test',
                status='success',
                stage='complete',
                source='continuous_test',
            )
            for sync_run_id in range(90, 121)
        ])
        db.session.commit()
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


class RetryAwareClient(Client):
    def __init__(self, attempts_per_request):
        self._attempts_per_request = attempts_per_request

    def max_attempts_per_request(self):
        return self._attempts_per_request


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


def seed_accepted_observation(game_pk=GAME_PK, *, fingerprint=None):
    fingerprint = fingerprint or f'identity-{game_pk}'
    row = GameObservationState(
        mlb_game_pk=game_pk,
        observation_fingerprint=fingerprint,
        observation={
            'game_pk': game_pk,
            'identity': {
                'official_date': '2026-08-29',
                'home_team_id': 21,
                'away_team_id': 22,
            },
            'linescore': {
                'home': {'runs': 5},
                'away': {'runs': 3},
            },
            'finality': {
                'state': 'final_and_usable',
                'final_status': True,
            },
        },
        source_authority=detection.SOURCE_AUTHORITY,
        source_endpoint=detection.SOURCE_ENDPOINT.format(game_pk=game_pk),
        source_observed_at=datetime(2026, 8, 29, 22, 0),
        finality_state='final_and_usable',
        previous_observation_fingerprint=f'previous-{game_pk}',
        last_classification='corrected',
        last_change_summary={'finality.state': {
            'previous': 'final_pending_data',
            'current': 'final_and_usable',
        }},
        accepted_at=datetime(2026, 8, 29, 22, 0),
    )
    db.session.add(row)
    db.session.commit()
    return row


def durable_jobs():
    return (
        SyncJob.query
        .filter_by(job_name=continuous_game_work.JOB_NAME)
        .order_by(SyncJob.id.asc())
        .all()
    )


def seed_completed_ingestion_work_item(
    game_pk=GAME_PK,
    *,
    represented_date=date(2026, 8, 29),
    last_attempted_at=datetime(2026, 8, 28, 12, 0),
):
    item = GameIngestionWorkItem(
        mlb_game_pk=game_pk,
        represented_date=represented_date,
        game_date=represented_date,
        home_team_id=21,
        away_team_id=22,
        candidate_reason=GameIngestionWorkItem.REASON_CORRECTED_FINAL,
        criticality=GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL,
        finality_state='final',
        source_authority='scheduled_games',
        status=GameIngestionWorkItem.STATUS_COMPLETED,
        attempt_count=1,
        first_attempted_at=last_attempted_at,
        last_attempted_at=last_attempted_at,
        completed_at=last_attempted_at,
        source_revision='prior-appearance-set',
        rows_expected=2,
        rows_reconciled=2,
        relief_rows_reconciled=2,
        correction_count=0,
    )
    db.session.add(item)
    db.session.commit()
    return item


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


def patch_run_metadata(monkeypatch, *, sync_run_id=91):
    monkeypatch.setattr(
        continuous.sync_metadata, 'acquire_sync_writer_guard', lambda **kwargs: Guard(),
    )
    monkeypatch.setattr(
        continuous.sync_metadata, 'start_sync_run', lambda **kwargs: sync_run_id,
    )
    monkeypatch.setattr(
        continuous.sync_metadata, 'finish_sync_run', lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(continuous, '_game_data_through', lambda game_pk: date(2026, 8, 29))


def chain_services(calls):
    def orchestrator(value, **kwargs):
        calls.append(('cu03', value['game_pk'], kwargs))
        completion_callback = kwargs.get('canonical_completion_callback')
        if completion_callback is not None:
            completion_callback({
                'game_pk': value['game_pk'],
                'represented_date': '2026-08-29',
                'inserted': 1,
                'updated': 0,
                'pitcher_identity_mutations': 0,
                'impact': {
                    'affected_pitcher_mlb_ids': [101, 102],
                    'affected_pitcher_ids': [11, 12],
                    'affected_team_ids': [21, 22],
                },
                'optional_source_domains': {
                    'final_play_by_play': {
                        'processing_status': 'complete',
                        'pitch_rows': {
                            'inserted': 0, 'updated': 0, 'superseded': 0,
                        },
                    },
                },
            })
            db.session.commit()
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


def run(
    app, monkeypatch, cfg, *, results=None, metadata_sync_run_id=91, **kwargs,
):
    patch_run_metadata(monkeypatch, sync_run_id=metadata_sync_run_id)
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
            client=kwargs.pop('client', Client()), cycle_lock_factory=Lock, **kwargs,
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


def test_full_live_derives_current_plan_when_no_manual_fingerprint(
    app, monkeypatch,
):
    cfg = config(
        continuous.ActivationMode.FULL_LIVE,
        production_publication_enabled=True,
        full_live_acknowledged=True,
        expected_plan_fingerprints={},
    )
    monkeypatch.setattr(
        continuous.cu03,
        'derive_current_plan_fingerprint',
        lambda value, **_kwargs: f"automatic-{value['game_pk']}",
    )
    publications = []

    def publisher(read_models, **kwargs):
        publications.append(kwargs)
        return {'committed': True, 'cache_handoff_status': 'complete'}

    result, calls = run(
        app, monkeypatch, cfg,
        production_publisher=publisher,
        production_current_id_provider=lambda: 44,
    )

    assert calls[0][0] == 'cu03'
    assert calls[0][2]['expected_plan_fingerprint'] == f'automatic-{GAME_PK}'
    assert len(publications) == 1
    assert result.live_publications == 1


def test_full_live_publishes_one_complete_cycle_after_multiple_games(
    app, monkeypatch,
):
    second = GAME_PK + 1
    cfg = config(
        continuous.ActivationMode.FULL_LIVE,
        production_publication_enabled=True,
        full_live_acknowledged=True,
        expected_plan_fingerprints={GAME_PK: 'a', second: 'b'},
    )
    publications = []

    def publisher(read_models, **kwargs):
        publications.append((read_models, kwargs))
        return {'committed': True, 'cache_handoff_status': 'complete'}

    result, _calls = run(
        app, monkeypatch, cfg,
        results=[change(), change(game_pk=second)],
        production_publisher=publisher,
        production_current_id_provider=lambda: 44,
    )

    assert len(publications) == 1
    assert result.canonical_mutation_games == 2
    assert result.publication_candidates == 1
    assert result.live_publications == 1
    assert result.downstream_results[0]['publication'] == {
        'status': 'included',
        'reason_code': 'included_in_cycle_publication',
        'published_with_game_pk': second,
    }
    assert result.downstream_results[1]['publication']['committed'] is True


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


def test_live_dashboard_commit_with_tonight_retry_is_visible_as_partial(
    app, monkeypatch,
):
    cfg = config(
        continuous.ActivationMode.LIMITED_LIVE,
        production_publication_enabled=True,
        allowlist_game_pks=(GAME_PK,),
    )

    result, _calls = run(
        app, monkeypatch, cfg,
        production_publisher=lambda *_args, **_kwargs: {
            'committed': True,
            'cache_handoff_status': 'retry_required',
        },
        production_current_id_provider=lambda: 44,
    )

    assert result.live_publications == 1
    assert result.status == continuous.RESULT_PARTIAL
    assert result.failures[-1] == {
        'scope': 'tonight_refresh',
        'game_pk': GAME_PK,
        'error': 'tonight_refresh_retry_required',
    }


def test_live_dashboard_receipt_retries_cache_without_losing_obligation(
    app, monkeypatch,
):
    with app.app_context():
        seed_accepted_observation()

    cfg = config(
        continuous.ActivationMode.LIMITED_LIVE,
        production_publication_enabled=True,
        allowlist_game_pks=(GAME_PK,),
    )
    publication_sync_runs = []

    def first_publisher(*_args, **kwargs):
        publication_sync_runs.append(kwargs['sync_run_id'])
        return {
            'committed': True,
            'reason_code': 'production_snapshot_published',
            'cache_handoff_status': 'retry_required',
        }

    first, _first_calls = run(
        app, monkeypatch, cfg, results=[change()],
        metadata_sync_run_id=91,
        production_publisher=first_publisher,
        production_current_id_provider=lambda: 44,
    )

    with app.app_context():
        job = durable_jobs()[0]
        assert job.status == sync_jobs.STATUS_FAILED
        assert job.attempts == 1
        assert job.details_json['stage'] == (
            continuous_game_work.STAGE_PUBLICATION_CACHE_PENDING
        )
        assert job.details_json['publication_attempt_sync_run_id'] == 91
    assert first.live_publications == 1
    assert first.work_obligations_pending == 1

    def receipt_publisher(*_args, **kwargs):
        publication_sync_runs.append(kwargs['sync_run_id'])
        return {
            'committed': False,
            'reason_code': 'production_snapshot_already_committed',
            'cache_handoff_status': 'complete',
        }

    retried, retry_calls = run(
        app, monkeypatch, cfg,
        results=[change(classification='unchanged', changed=False)],
        metadata_sync_run_id=92,
        production_publisher=receipt_publisher,
        production_current_id_provider=lambda: 52,
    )

    with app.app_context():
        job = durable_jobs()[0]
        assert job.status == sync_jobs.STATUS_SUCCEEDED
        assert job.attempts == 2
        assert job.details_json['total_attempts'] == 2
    assert publication_sync_runs == [91, 91]
    assert retry_calls == []
    assert retried.work_obligations_completed == 1
    assert retried.work_obligations_pending == 0


def test_cache_retry_without_durable_receipt_identity_fails_closed(
    app, monkeypatch,
):
    with app.app_context():
        seed_accepted_observation()
        job = continuous_game_work.ensure_obligation(change())
        details = dict(job.details_json or {})
        details.update({
            'stage': continuous_game_work.STAGE_PUBLICATION_CACHE_PENDING,
            'canonical_impact': {
                'game_pk': GAME_PK,
                'canonical_mutation_performed': True,
                'affected_pitcher_ids': [11, 12],
                'affected_team_ids': [21, 22],
            },
        })
        job.details_json = details
        db.session.commit()

    result, retry_calls = run(
        app,
        monkeypatch,
        config(
            continuous.ActivationMode.LIMITED_LIVE,
            production_publication_enabled=True,
            allowlist_game_pks=(GAME_PK,),
        ),
        results=[change(classification='unchanged', changed=False)],
        production_publisher=lambda *_args, **_kwargs: pytest.fail(
            'cache retry without its receipt must never publish'
        ),
        production_current_id_provider=lambda: 52,
    )

    with app.app_context():
        job = durable_jobs()[0]
        assert job.status == sync_jobs.STATUS_FAILED
        assert job.details_json['work_status'] == (
            continuous_game_work.WORK_RETRYABLE_FAILURE
        )
        assert job.details_json['last_failure'] == (
            'publication_receipt_identity_missing'
        )
    assert retry_calls == []
    assert result.failures[-1]['error'] == 'publication_receipt_identity_missing'
    assert result.live_publications == 0


def test_failed_cohort_does_not_consume_healthy_publication_attempts(
    app, monkeypatch,
):
    failing_game_pk = GAME_PK + 1
    with app.app_context():
        seed_accepted_observation()
        seed_accepted_observation(failing_game_pk)

    cfg = config(
        continuous.ActivationMode.LIMITED_LIVE,
        production_publication_enabled=True,
        allowlist_game_pks=(GAME_PK, failing_game_pk),
        expected_plan_fingerprints={
            GAME_PK: 'healthy-reviewed',
            failing_game_pk: 'failing-reviewed',
        },
        max_canonical_actions=2,
    )
    failure_enabled = {'value': True}

    def workload(impact, **_kwargs):
        if failure_enabled['value'] and impact['game_pk'] == failing_game_pk:
            raise RuntimeError('controlled cohort failure')
        return {
            'game_pk': impact['game_pk'],
            'status': 'complete',
            'parity_status': 'match',
            'recomputation_performed': True,
            'data_through': '2026-08-29',
            'availability_reference_date': '2026-08-30',
            'pitchers_recomputed': [11, 12],
            'teams_recomputed': [21, 22],
        }

    publications = []

    def publisher(*_args, **kwargs):
        publications.append(kwargs)
        return {'committed': True, 'cache_handoff_status': 'complete'}

    first_results = [change(), change(game_pk=failing_game_pk)]
    unchanged = [
        change(classification='unchanged', changed=False),
        change(
            classification='unchanged', changed=False,
            game_pk=failing_game_pk,
        ),
    ]
    run(
        app, monkeypatch, cfg, results=first_results, metadata_sync_run_id=91,
        workload_service=workload,
        production_publisher=publisher,
        production_current_id_provider=lambda: 44,
    )
    run(
        app, monkeypatch, cfg, results=unchanged, metadata_sync_run_id=92,
        workload_service=workload,
        production_publisher=publisher,
        production_current_id_provider=lambda: 44,
    )
    blocked, _ = run(
        app, monkeypatch, cfg, results=unchanged, metadata_sync_run_id=93,
        workload_service=workload,
        production_publisher=publisher,
        production_current_id_provider=lambda: 44,
    )

    with app.app_context():
        by_game = {
            job.details_json['game_pk']: job
            for job in durable_jobs()
        }
        assert by_game[GAME_PK].status == sync_jobs.STATUS_PENDING
        assert by_game[GAME_PK].attempts == 0
        assert by_game[GAME_PK].details_json['stage'] == (
            continuous_game_work.STAGE_PUBLICATION_PENDING
        )
        assert by_game[failing_game_pk].status == sync_jobs.STATUS_FAILED
        assert by_game[failing_game_pk].attempts == 3
    assert publications == []
    assert blocked.work_obligations_pending == 2

    failure_enabled['value'] = False
    completed, _ = run(
        app, monkeypatch, cfg, results=unchanged, metadata_sync_run_id=94,
        workload_service=workload,
        production_publisher=publisher,
        production_current_id_provider=lambda: 44,
    )

    with app.app_context():
        assert all(
            job.status == sync_jobs.STATUS_SUCCEEDED
            for job in durable_jobs()
        )
    assert len(publications) == 1
    assert completed.work_obligations_pending == 0


def test_mixed_publication_batch_cannot_reuse_one_old_receipt(
    app, monkeypatch,
):
    new_game_pk = GAME_PK + 1
    with app.app_context():
        seed_accepted_observation()
        old_job = continuous_game_work.ensure_obligation(change())
        old_job = continuous_game_work.claim(old_job, sync_run_id=90)
        old_job = continuous_game_work.checkpoint(
            old_job,
            continuous_game_work.STAGE_PUBLICATION_PENDING,
            canonical_impact={
                'game_pk': GAME_PK,
                'orchestration_status': 'reconciled',
                'cu01_invocations': 1,
                'canonical_mutation_performed': True,
                'affected_pitcher_ids': [11, 12],
                'affected_team_ids': [21, 22],
            },
            publication_attempt_sync_run_id=91,
        )
        continuous_game_work.fail(
            old_job,
            'tonight_refresh_retry_required',
            stage=continuous_game_work.STAGE_PUBLICATION_PENDING,
        )
        seed_accepted_observation(new_game_pk)

    publication_sync_runs = []

    def publisher(*_args, **kwargs):
        publication_sync_runs.append(kwargs['sync_run_id'])
        return {
            'committed': True,
            'reason_code': 'production_snapshot_published',
            'cache_handoff_status': 'complete',
        }

    result, calls = run(
        app, monkeypatch,
        config(
            continuous.ActivationMode.LIMITED_LIVE,
            production_publication_enabled=True,
            allowlist_game_pks=(GAME_PK, new_game_pk),
            expected_plan_fingerprints={
                GAME_PK: 'old-reviewed',
                new_game_pk: 'new-reviewed',
            },
            max_canonical_actions=2,
        ),
        results=[
            change(classification='unchanged', changed=False),
            change(game_pk=new_game_pk),
        ],
        metadata_sync_run_id=92,
        production_publisher=publisher,
        production_current_id_provider=lambda: 52,
    )

    assert publication_sync_runs == [92]
    assert [item[1] for item in calls if item[0] == 'cu03'] == [new_game_pk]
    assert result.live_publications == 1
    assert result.work_obligations_completed == 2
    assert result.work_obligations_pending == 0
    with app.app_context():
        by_game = {
            job.details_json['game_pk']: job
            for job in durable_jobs()
        }
        assert by_game[GAME_PK].status == sync_jobs.STATUS_SUCCEEDED
        assert by_game[GAME_PK].attempts == 2
        assert by_game[GAME_PK].details_json[
            'publication_attempt_sync_run_id'
        ] == 92
        assert by_game[new_game_pk].status == sync_jobs.STATUS_SUCCEEDED
        assert by_game[new_game_pk].attempts == 1
        assert by_game[new_game_pk].details_json[
            'publication_attempt_sync_run_id'
        ] == 92


def test_cache_receipt_retry_stays_separate_from_new_publication_batch(
    app, monkeypatch,
):
    new_game_pk = GAME_PK + 1
    with app.app_context():
        seed_accepted_observation()
        old_job = continuous_game_work.ensure_obligation(change())
        old_job = continuous_game_work.claim(old_job, sync_run_id=90)
        old_job = continuous_game_work.checkpoint(
            old_job,
            continuous_game_work.STAGE_PUBLICATION_CACHE_PENDING,
            canonical_impact={
                'game_pk': GAME_PK,
                'orchestration_status': 'reconciled',
                'cu01_invocations': 1,
                'canonical_mutation_performed': True,
                'affected_pitcher_ids': [11, 12],
                'affected_team_ids': [21, 22],
            },
            publication_attempt_sync_run_id=91,
        )
        continuous_game_work.fail(
            old_job,
            'tonight_refresh_retry_required',
            stage=continuous_game_work.STAGE_PUBLICATION_CACHE_PENDING,
        )
        seed_accepted_observation(new_game_pk)

    publication_calls = []

    def publisher(*_args, **kwargs):
        publication_calls.append((
            kwargs['sync_run_id'],
            kwargs.get('require_published_receipt', False),
        ))
        if kwargs.get('require_published_receipt'):
            return {
                'committed': False,
                'reason_code': 'production_snapshot_already_committed',
                'cache_handoff_status': 'complete',
            }
        return {
            'committed': True,
            'reason_code': 'production_snapshot_published',
            'cache_handoff_status': 'complete',
        }

    result, calls = run(
        app,
        monkeypatch,
        config(
            continuous.ActivationMode.LIMITED_LIVE,
            production_publication_enabled=True,
            allowlist_game_pks=(GAME_PK, new_game_pk),
            expected_plan_fingerprints={new_game_pk: 'new-reviewed'},
            max_canonical_actions=2,
        ),
        results=[
            change(classification='unchanged', changed=False),
            change(game_pk=new_game_pk),
        ],
        metadata_sync_run_id=92,
        production_publisher=publisher,
        production_current_id_provider=lambda: 52,
    )

    assert publication_calls == [(91, True), (92, False)]
    assert [item[1] for item in calls if item[0] == 'cu03'] == [new_game_pk]
    assert result.work_obligations_completed == 2
    assert result.work_obligations_pending == 0
    with app.app_context():
        assert all(
            job.status == sync_jobs.STATUS_SUCCEEDED
            for job in durable_jobs()
        )


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


@pytest.mark.parametrize(
    ('budget', 'expected_max_games'),
    ((8, 1), (7, 0)),
)
def test_source_budget_candidate_admission_reserves_retry_attempts(
    app, monkeypatch, budget, expected_max_games,
):
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
        continuous.run_continuous_cycle(
            config=config(
                continuous.ActivationMode.SHADOW_DETECT,
                source_request_budget=budget,
                max_games=15,
            ),
            represented_time=NOW,
            detector=detector,
            client=RetryAwareClient(4),
            cycle_lock_factory=Lock,
        )

    assert captured['max_games'] == expected_max_games


def test_source_budget_reserves_a_complete_durable_canonical_action(
    app, monkeypatch,
):
    captured = {}

    def detector(**kwargs):
        captured.update(kwargs)
        return {
            'candidate_game_pks': [], 'games_checked': 0, 'unchanged_games': 0,
            'changed_games': 0, 'source_failures': 0, 'requests_expected': 1,
            'results': [],
        }

    with app.app_context():
        seed_accepted_observation()
        continuous_game_work.ensure_obligation(change())

    calls = []
    services = chain_services(calls)
    patch_run_metadata(monkeypatch)
    with app.app_context():
        result = continuous.run_continuous_cycle(
            config=config(
                continuous.ActivationMode.SHADOW_FULL_CHAIN,
                source_request_budget=5,
                max_games=15,
            ),
            represented_time=NOW,
            detector=detector,
            orchestrator=services[0],
            workload_service=services[1],
            team_state_service=services[2],
            read_model_service=services[3],
            client=Client(),
            cycle_lock_factory=Lock,
        )

    assert captured['max_games'] == 1
    assert [item[0] for item in calls] == ['cu03', 'cu04', 'cu05', 'cu06']
    assert result.work_obligations_pending == 0


def test_source_budget_deferral_keeps_existing_obligation_pending(
    app, monkeypatch,
):
    with app.app_context():
        seed_accepted_observation()
        continuous_game_work.ensure_obligation(change())

    patch_run_metadata(monkeypatch)
    with app.app_context():
        result = continuous.run_continuous_cycle(
            config=config(
                continuous.ActivationMode.SHADOW_FULL_CHAIN,
                source_request_budget=4,
            ),
            represented_time=NOW,
            detector=detector_for([
                change(classification='unchanged', changed=False),
            ]),
            client=Client(), cycle_lock_factory=Lock,
        )

        job = durable_jobs()[0]
        assert job.status == sync_jobs.STATUS_PENDING
        assert job.attempts == 0
    assert result.work_obligations_pending == 1
    assert result.canonical_actions == 0


def test_retry_aware_source_reservation_defers_before_claim(
    app, monkeypatch,
):
    with app.app_context():
        seed_accepted_observation()
        continuous_game_work.ensure_obligation(change())

    patch_run_metadata(monkeypatch)
    with app.app_context():
        result = continuous.run_continuous_cycle(
            config=config(
                continuous.ActivationMode.SHADOW_FULL_CHAIN,
                source_request_budget=11,
            ),
            represented_time=NOW,
            detector=detector_for([]),
            client=RetryAwareClient(4),
            cycle_lock_factory=Lock,
        )
        job = durable_jobs()[0]
        assert job.status == sync_jobs.STATUS_PENDING
        assert job.attempts == 0
        assert job.details_json['last_deferral'] == 'source_budget_deferred'

    assert result.canonical_actions == 0
    assert result.work_obligations_pending == 1


def test_durable_action_can_use_budget_without_redundant_detection(
    app, monkeypatch,
):
    with app.app_context():
        seed_accepted_observation()
        continuous_game_work.ensure_obligation(change())

    patch_run_metadata(monkeypatch)
    calls = []
    services = chain_services(calls)
    with app.app_context():
        result = continuous.run_continuous_cycle(
            config=config(
                continuous.ActivationMode.SHADOW_FULL_CHAIN,
                source_request_budget=12,
            ),
            represented_time=NOW,
            detector=lambda **_kwargs: pytest.fail(
                'reserved canonical work must not spend its budget on detection'
            ),
            orchestrator=services[0],
            workload_service=services[1],
            team_state_service=services[2],
            read_model_service=services[3],
            client=RetryAwareClient(4),
            cycle_lock_factory=Lock,
        )

    assert [item[0] for item in calls] == ['cu03', 'cu04', 'cu05', 'cu06']
    assert result.canonical_actions == 1
    assert result.work_obligations_pending == 0


def test_source_outage_does_not_block_already_committed_downstream_work(
    app, monkeypatch,
):
    with app.app_context():
        seed_accepted_observation()
        job = continuous_game_work.ensure_obligation(change())
        job = continuous_game_work.claim(job, sync_run_id=90)
        job = continuous_game_work.checkpoint(
            job,
            continuous_game_work.STAGE_DOWNSTREAM_PENDING,
            canonical_impact={
                'game_pk': GAME_PK,
                'orchestration_status': 'reconciled',
                'canonical_action_attempted': True,
                'cu01_invocations': 1,
                'canonical_mutation_performed': True,
                'affected_pitcher_ids': [11, 12],
                'affected_team_ids': [21, 22],
            },
        )
        continuous_game_work.fail(
            job,
            'source_failed_after_canonical_commit',
            stage=continuous_game_work.STAGE_CANONICAL_PENDING,
        )

    source_failures = [
        change(
            classification='source_failure', changed=False,
            game_pk=GAME_PK + index,
        )
        for index in range(2)
    ]
    result, calls = run(
        app,
        monkeypatch,
        config(
            continuous.ActivationMode.SHADOW_FULL_CHAIN,
            expected_plan_fingerprints={},
            core_failure_breaker=2,
        ),
        results=source_failures,
    )

    assert result.circuit_breaker_open is True
    assert [item[0] for item in calls] == ['cu04', 'cu05', 'cu06']
    with app.app_context():
        job = durable_jobs()[0]
        assert job.status == sync_jobs.STATUS_SUCCEEDED
        assert job.attempts == 2
    assert result.work_obligations_pending == 0


def test_missing_plan_authorization_does_not_consume_durable_work(
    app, monkeypatch,
):
    with app.app_context():
        seed_accepted_observation()
        continuous_game_work.ensure_obligation(change())

    result, calls = run(
        app,
        monkeypatch,
        config(
            continuous.ActivationMode.SHADOW_FULL_CHAIN,
            expected_plan_fingerprints={},
        ),
        results=[change(classification='unchanged', changed=False)],
    )

    with app.app_context():
        job = durable_jobs()[0]
        assert job.status == sync_jobs.STATUS_PENDING
        assert job.attempts == 0
    assert result.failures == ({
        'scope': 'plan_authorization',
        'game_pk': GAME_PK,
        'error': 'reviewed_plan_fingerprint_unavailable',
    },)
    assert result.work_obligations_pending == 1
    assert calls == []


def test_deferred_head_job_does_not_starve_later_authorized_work(
    app, monkeypatch,
):
    later_game_pk = GAME_PK + 1
    with app.app_context():
        seed_accepted_observation()
        continuous_game_work.ensure_obligation(change())
        seed_accepted_observation(later_game_pk)
        continuous_game_work.ensure_obligation(change(game_pk=later_game_pk))

    cfg = config(
        continuous.ActivationMode.SHADOW_FULL_CHAIN,
        max_canonical_actions=1,
        expected_plan_fingerprints={later_game_pk: 'later-reviewed'},
    )
    unchanged = [
        change(classification='unchanged', changed=False),
        change(
            classification='unchanged', changed=False, game_pk=later_game_pk,
        ),
    ]
    first, first_calls = run(
        app, monkeypatch, cfg, results=unchanged, metadata_sync_run_id=91,
    )
    second, second_calls = run(
        app, monkeypatch, cfg, results=unchanged, metadata_sync_run_id=92,
    )

    assert first_calls == []
    assert [item[1] for item in second_calls if item[0] == 'cu03'] == [
        later_game_pk,
    ]
    with app.app_context():
        by_game = {
            job.details_json['game_pk']: job
            for job in durable_jobs()
        }
        assert by_game[GAME_PK].status == sync_jobs.STATUS_PENDING
        assert by_game[GAME_PK].attempts == 0
        assert by_game[GAME_PK].details_json['last_deferral'] == (
            'reviewed_plan_fingerprint_unavailable'
        )
        assert by_game[later_game_pk].status == sync_jobs.STATUS_SUCCEEDED
    assert first.work_obligations_pending == 2
    assert second.work_obligations_pending == 1


def test_allowlist_deferral_keeps_work_for_later_authorized_cycle(
    app, monkeypatch,
):
    with app.app_context():
        seed_accepted_observation()
        continuous_game_work.ensure_obligation(change())

    blocked, blocked_calls = run(
        app, monkeypatch,
        config(
            continuous.ActivationMode.LIMITED_LIVE,
            production_publication_enabled=True,
            allowlist_game_pks=(GAME_PK + 1,),
        ),
        results=[change(classification='unchanged', changed=False)],
        production_publisher=lambda *_args, **_kwargs: pytest.fail(
            'publication must not run for unauthorized work'
        ),
        production_current_id_provider=lambda: 44,
    )

    with app.app_context():
        job = durable_jobs()[0]
        assert job.status == sync_jobs.STATUS_PENDING
        assert job.attempts == 0
    assert blocked.skipped_by_allowlist == 1
    assert blocked_calls == []

    allowed, allowed_calls = run(
        app, monkeypatch,
        config(
            continuous.ActivationMode.LIMITED_LIVE,
            production_publication_enabled=True,
            allowlist_game_pks=(GAME_PK,),
        ),
        results=[change(classification='unchanged', changed=False)],
        production_publisher=lambda *_args, **_kwargs: {
            'committed': True,
            'cache_handoff_status': 'complete',
        },
        production_current_id_provider=lambda: 44,
    )

    with app.app_context():
        job = durable_jobs()[0]
        assert job.status == sync_jobs.STATUS_SUCCEEDED
        assert job.attempts == 1
    assert [item[0] for item in allowed_calls] == ['cu03', 'cu04', 'cu05', 'cu06']
    assert allowed.live_publications == 1
    assert allowed.work_obligations_pending == 0


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


@pytest.mark.parametrize('failure_shape', ('exception', 'canonical_failed'))
def test_canonical_failure_retries_on_unchanged_observation(
    app, monkeypatch, failure_shape,
):
    with app.app_context():
        seed_accepted_observation()

    def failing_orchestrator(value, **_kwargs):
        if failure_shape == 'exception':
            raise RuntimeError('controlled canonical failure')
        return {
            'game_pk': value['game_pk'],
            'orchestration_status': 'canonical_failed',
            'source_failure_state': 'appearance_reconciliation_failed',
            'cu01_invocations': 1,
            'canonical_mutation_performed': False,
            'affected_pitcher_ids': [],
            'affected_team_ids': [],
        }

    failed, _failed_calls = run(
        app, monkeypatch,
        config(continuous.ActivationMode.SHADOW_FULL_CHAIN),
        results=[change()], orchestrator=failing_orchestrator,
    )

    with app.app_context():
        job = durable_jobs()[0]
        assert job.status == sync_jobs.STATUS_FAILED
        assert job.attempts == 1
        assert job.details_json['work_status'] == (
            continuous_game_work.WORK_RETRYABLE_FAILURE
        )
        assert job.details_json['stage'] == (
            continuous_game_work.STAGE_CANONICAL_PENDING
        )
    assert failed.work_obligations_failed == 1
    assert failed.work_obligations_pending == 1

    retried, retry_calls = run(
        app, monkeypatch,
        config(continuous.ActivationMode.SHADOW_FULL_CHAIN),
        results=[change(classification='unchanged', changed=False)],
    )

    with app.app_context():
        job = durable_jobs()[0]
        assert job.status == sync_jobs.STATUS_SUCCEEDED
        assert job.attempts == 1
        assert job.details_json['total_attempts'] == 2
    assert [item[0] for item in retry_calls] == ['cu03', 'cu04', 'cu05', 'cu06']
    assert retried.work_obligations_completed == 1
    assert retried.work_obligations_pending == 0


def test_postcommit_orchestrator_failure_preserves_atomic_canonical_checkpoint(
    app, monkeypatch,
):
    with app.app_context():
        seed_accepted_observation()

    def commit_then_crash(value, **kwargs):
        kwargs['canonical_completion_callback']({
            'game_pk': value['game_pk'],
            'represented_date': '2026-08-29',
            'inserted': 1,
            'updated': 0,
            'pitcher_identity_mutations': 0,
            'impact': {
                'affected_pitcher_mlb_ids': [101],
                'affected_pitcher_ids': [11],
                'affected_team_ids': [21],
            },
            'optional_source_domains': {
                'final_play_by_play': {
                    'processing_status': 'complete',
                    'pitch_rows': {
                        'inserted': 0, 'updated': 0, 'superseded': 0,
                    },
                },
            },
        })
        db.session.commit()
        raise RuntimeError('controlled postcommit transport failure')

    failed, _ = run(
        app,
        monkeypatch,
        config(continuous.ActivationMode.SHADOW_FULL_CHAIN),
        results=[change()],
        orchestrator=commit_then_crash,
    )

    with app.app_context():
        job = durable_jobs()[0]
        assert job.status == sync_jobs.STATUS_FAILED
        assert job.details_json['stage'] == (
            continuous_game_work.STAGE_DOWNSTREAM_PENDING
        )
        assert job.details_json['canonical_impact'][
            'canonical_mutation_performed'
        ] is True
    assert failed.work_obligations_pending == 1

    retried, retry_calls = run(
        app,
        monkeypatch,
        config(continuous.ActivationMode.SHADOW_FULL_CHAIN),
        results=[change(classification='unchanged', changed=False)],
    )

    assert [item[0] for item in retry_calls] == ['cu04', 'cu05', 'cu06']
    with app.app_context():
        job = durable_jobs()[0]
        assert job.status == sync_jobs.STATUS_SUCCEEDED
        assert job.attempts == 2
    assert retried.work_obligations_pending == 0


@pytest.mark.parametrize(
    ('failed_stage', 'expected_first_calls'),
    (
        ('cu04', ('cu03',)),
        ('cu05', ('cu03', 'cu04')),
        ('cu06', ('cu03', 'cu04', 'cu05')),
        ('publication', ('cu03', 'cu04', 'cu05', 'cu06')),
    ),
)
def test_downstream_and_publication_failures_resume_durable_work(
    app, monkeypatch, failed_stage, expected_first_calls,
):
    with app.app_context():
        seed_accepted_observation()

    first_calls = []
    services = chain_services(first_calls)

    def explode(*_args, **_kwargs):
        raise RuntimeError(f'controlled {failed_stage} failure')

    kwargs = {
        'orchestrator': services[0],
        'workload_service': explode if failed_stage == 'cu04' else services[1],
        'team_state_service': explode if failed_stage == 'cu05' else services[2],
        'read_model_service': explode if failed_stage == 'cu06' else services[3],
    }
    mode = continuous.ActivationMode.SHADOW_FULL_CHAIN
    if failed_stage == 'publication':
        mode = continuous.ActivationMode.PROOF_PUBLICATION
        kwargs['proof_publisher'] = explode

    failed, _ = run(
        app, monkeypatch, config(mode), results=[change()], **kwargs,
    )

    with app.app_context():
        job = durable_jobs()[0]
        assert job.status == sync_jobs.STATUS_FAILED
        assert job.attempts == 1
        assert job.details_json['stage'] == (
            continuous_game_work.STAGE_PUBLICATION_PENDING
            if failed_stage == 'publication'
            else continuous_game_work.STAGE_DOWNSTREAM_PENDING
        )
        assert job.details_json['canonical_impact']['canonical_mutation_performed'] is True
    assert tuple(item[0] for item in first_calls) == expected_first_calls
    assert failed.work_obligations_failed == 1
    assert failed.work_obligations_pending == 1

    success_publications = []
    retried, retry_calls = run(
        app, monkeypatch, config(mode),
        results=[change(classification='unchanged', changed=False)],
        proof_publisher=lambda *_args, **_kwargs: (
            success_publications.append(True)
            or {
                'committed': True,
                'cache_handoff_status': 'complete',
            }
        ),
    )

    with app.app_context():
        job = durable_jobs()[0]
        assert job.status == sync_jobs.STATUS_SUCCEEDED
        assert job.attempts == 2
    assert [item[0] for item in retry_calls] == ['cu04', 'cu05', 'cu06']
    assert success_publications == ([True] if failed_stage == 'publication' else [])
    assert retried.work_obligations_completed == 1
    assert retried.work_obligations_pending == 0


def test_abandoned_running_work_is_reclaimed_after_session_restart(
    app, monkeypatch,
):
    with app.app_context():
        seed_accepted_observation()
        job = continuous_game_work.ensure_obligation(change())
        claimed = continuous_game_work.claim(job, sync_run_id=90)
        job_id = claimed.id
        assert claimed.status == sync_jobs.STATUS_RUNNING
        assert claimed.attempts == 1
        abandoned_at = continuous_game_work.utc_now_naive() - timedelta(minutes=4)
        claimed.started_at = abandoned_at
        claimed.last_heartbeat_at = abandoned_at
        claimed.updated_at = abandoned_at
        db.session.commit()
        db.session.remove()

    result, calls = run(
        app, monkeypatch,
        config(continuous.ActivationMode.SHADOW_FULL_CHAIN),
        results=[change(classification='unchanged', changed=False)],
    )

    with app.app_context():
        job = db.session.get(SyncJob, job_id)
        assert job.status == sync_jobs.STATUS_SUCCEEDED
        assert job.attempts == 1
        assert job.details_json['total_attempts'] == 2
        assert job.details_json['last_reclaim']['reason'] == (
            'stale running checkpoint'
        )
    assert [item[0] for item in calls] == ['cu03', 'cu04', 'cu05', 'cu06']
    assert result.work_obligations_pending == 0


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


def test_equal_timestamp_upgrade_creates_one_durable_job_and_shadow_preserves_it(
    app, monkeypatch,
):
    with app.app_context():
        pending, usable = _equal_timestamp_final_incident()
        detection.observe_game_change(
            usable['gamePk'], payload=pending, create_work_obligation=True,
        )
        upgraded = detection.observe_game_change(
            usable['gamePk'], payload=usable, create_work_obligation=True,
        )
        replayed = detection.observe_game_change(
            usable['gamePk'], payload=deepcopy(usable),
        )

        jobs = durable_jobs()
        assert upgraded.classification == 'corrected'
        assert replayed.classification == 'unchanged'
        assert len(jobs) == 1
        assert jobs[0].status == sync_jobs.STATUS_PENDING
        assert jobs[0].attempts == 0
        assert jobs[0].details_json['observation_fingerprint'] == (
            upgraded.current_observation_identity
        )

    shadow, shadow_calls = run(
        app, monkeypatch, config(continuous.ActivationMode.SHADOW_DETECT),
        results=[upgraded.to_dict()],
    )

    with app.app_context():
        jobs = durable_jobs()
        assert len(jobs) == 1
        assert jobs[0].status == sync_jobs.STATUS_PENDING
        assert jobs[0].attempts == 0
    assert shadow.work_obligations_pending == 1
    assert shadow_calls == []


def test_daily_correction_recheck_is_durable_bounded_and_idempotent(app):
    with app.app_context():
        seed_accepted_observation()
        seed_completed_ingestion_work_item()

        first = continuous_game_work.ensure_due_correction_rechecks(
            reference_date=NOW.date(),
            correction_days=2,
            limit=1,
            sync_run_id=91,
        )
        replay = continuous_game_work.ensure_due_correction_rechecks(
            reference_date=NOW.date(),
            correction_days=2,
            limit=1,
            sync_run_id=92,
        )

        jobs = durable_jobs()
        assert len(first) == 1
        assert replay == []
        assert len(jobs) == 1
        assert jobs[0].status == sync_jobs.STATUS_PENDING
        assert jobs[0].details_json['work_kind'] == (
            continuous_game_work.WORK_KIND_CORRECTION_RECHECK
        )
        assert jobs[0].details_json['correction_recheck_date'] == (
            NOW.date().isoformat()
        )


def test_stronger_final_evidence_supersedes_only_the_unfinished_obligation(app):
    pending, usable = _equal_timestamp_final_incident()
    live = _feed(timestamp='20260903_035300')

    with app.app_context():
        detection.observe_game_change(
            live['gamePk'], payload=live, create_work_obligation=True,
        )
        finalized = detection.observe_game_change(
            pending['gamePk'], payload=pending, create_work_obligation=True,
        )
        upgraded = detection.observe_game_change(
            usable['gamePk'], payload=usable, create_work_obligation=True,
        )
        replayed = detection.observe_game_change(
            usable['gamePk'], payload=deepcopy(usable),
        )

        jobs = durable_jobs()
        assert finalized.classification == detection.FINALIZED
        assert upgraded.classification == detection.CORRECTED
        assert replayed.classification == detection.UNCHANGED
        assert len(jobs) == 2
        assert jobs[0].status == sync_jobs.STATUS_SKIPPED
        assert jobs[0].details_json['work_status'] == (
            continuous_game_work.WORK_SUPERSEDED
        )
        assert jobs[0].details_json[
            'superseded_by_observation_fingerprint'
        ] == upgraded.current_observation_identity
        assert jobs[1].status == sync_jobs.STATUS_PENDING
        assert jobs[1].details_json['observation_fingerprint'] == (
            upgraded.current_observation_identity
        )


def test_successor_preserves_predecessor_canonical_impact_until_propagated(
    app, monkeypatch,
):
    successor_fingerprint = f'successor-{GAME_PK}'
    with app.app_context():
        row = seed_accepted_observation()
        predecessor = continuous_game_work.ensure_obligation(change())
        predecessor = continuous_game_work.claim(predecessor, sync_run_id=90)
        predecessor = continuous_game_work.checkpoint(
            predecessor,
            continuous_game_work.STAGE_DOWNSTREAM_PENDING,
            canonical_impact={
                'game_pk': GAME_PK,
                'orchestration_status': 'reconciled',
                'canonical_action_attempted': True,
                'cu01_invocations': 1,
                'canonical_mutation_performed': True,
                'affected_pitcher_ids': [11, 12],
                'affected_team_ids': [21, 22],
            },
        )
        predecessor = continuous_game_work.fail(
            predecessor,
            'controlled_failure_after_canonical_commit',
            stage=continuous_game_work.STAGE_CANONICAL_PENDING,
        )
        row.observation_fingerprint = successor_fingerprint
        row.previous_observation_fingerprint = f'identity-{GAME_PK}'
        row.last_classification = detection.CORRECTED
        db.session.commit()
        successor_change = dict(change())
        successor_change['current_observation_identity'] = successor_fingerprint
        successor = continuous_game_work.ensure_obligation(successor_change)

        assert predecessor.status == sync_jobs.STATUS_FAILED
        assert predecessor.details_json['stage'] == (
            continuous_game_work.STAGE_DOWNSTREAM_PENDING
        )
        assert successor.status == sync_jobs.STATUS_PENDING

    result, calls = run(
        app,
        monkeypatch,
        config(
            continuous.ActivationMode.SHADOW_FULL_CHAIN,
            max_canonical_actions=2,
        ),
        results=[change(classification='unchanged', changed=False)],
    )

    assert [item[0] for item in calls] == ['cu04', 'cu05', 'cu06']
    with app.app_context():
        jobs = durable_jobs()
        assert jobs[0].status == sync_jobs.STATUS_SUCCEEDED
        assert jobs[0].attempts == 2
        assert jobs[1].status == sync_jobs.STATUS_PENDING
        assert jobs[1].attempts == 0
    assert result.work_obligations_pending == 1

    successor_result, successor_calls = run(
        app,
        monkeypatch,
        config(
            continuous.ActivationMode.SHADOW_FULL_CHAIN,
            max_canonical_actions=2,
            expected_plan_fingerprints={
                GAME_PK: 'successor-reviewed',
            },
        ),
        results=[change(classification='unchanged', changed=False)],
    )

    assert [item[0] for item in successor_calls] == [
        'cu03', 'cu04', 'cu05', 'cu06',
    ]
    with app.app_context():
        jobs = durable_jobs()
        assert [job.status for job in jobs] == [
            sync_jobs.STATUS_SUCCEEDED,
            sync_jobs.STATUS_SUCCEEDED,
        ]
    assert successor_result.work_obligations_pending == 0


def test_reconciliation_obligation_stops_after_bounded_terminal_failure(app):
    with app.app_context():
        seed_accepted_observation()
        job = continuous_game_work.ensure_obligation(change())
        for attempt in range(1, continuous_game_work.MAX_ATTEMPTS + 1):
            job = continuous_game_work.claim(job, sync_run_id=90 + attempt)
            job = continuous_game_work.fail(
                job,
                'controlled_failure',
                stage=continuous_game_work.STAGE_CANONICAL_PENDING,
            )

        assert job.status == sync_jobs.STATUS_FAILED
        assert job.attempts == continuous_game_work.MAX_ATTEMPTS
        assert job.details_json['work_status'] == (
            continuous_game_work.WORK_TERMINAL_FAILURE
        )
        assert continuous_game_work.claimable_obligations(limit=1) == []
        assert continuous_game_work.unresolved_count() == 0


def test_retry_budget_resets_when_canonical_work_advances_to_downstream(
    app, monkeypatch,
):
    with app.app_context():
        seed_accepted_observation()

    cfg = config(continuous.ActivationMode.SHADOW_FULL_CHAIN)

    def canonical_failure(*_args, **_kwargs):
        raise RuntimeError('controlled canonical failure')

    for cycle in range(continuous_game_work.MAX_ATTEMPTS - 1):
        failed, _ = run(
            app,
            monkeypatch,
            cfg,
            results=[
                change()
                if cycle == 0
                else change(classification='unchanged', changed=False)
            ],
            metadata_sync_run_id=100 + cycle,
            orchestrator=canonical_failure,
        )
        assert failed.work_obligations_pending == 1

    services = chain_services([])

    def downstream_failure(*_args, **_kwargs):
        raise RuntimeError('controlled downstream failure')

    failed_downstream, _ = run(
        app,
        monkeypatch,
        cfg,
        results=[change(classification='unchanged', changed=False)],
        metadata_sync_run_id=110,
        orchestrator=services[0],
        workload_service=downstream_failure,
    )

    with app.app_context():
        job = durable_jobs()[0]
        assert job.status == sync_jobs.STATUS_FAILED
        assert job.attempts == 1
        assert job.details_json['stage'] == (
            continuous_game_work.STAGE_DOWNSTREAM_PENDING
        )
        assert job.details_json['work_status'] == (
            continuous_game_work.WORK_RETRYABLE_FAILURE
        )
        assert job.details_json['attempts_by_stage'][
            continuous_game_work.STAGE_CANONICAL_PENDING
        ] == continuous_game_work.MAX_ATTEMPTS
        assert job.details_json['total_attempts'] == (
            continuous_game_work.MAX_ATTEMPTS
        )
    assert failed_downstream.work_obligations_pending == 1

    recovered, calls = run(
        app,
        monkeypatch,
        cfg,
        results=[change(classification='unchanged', changed=False)],
        metadata_sync_run_id=111,
    )

    assert [item[0] for item in calls] == ['cu04', 'cu05', 'cu06']
    with app.app_context():
        job = durable_jobs()[0]
        assert job.status == sync_jobs.STATUS_SUCCEEDED
        assert job.attempts == 2
        assert job.details_json['total_attempts'] == (
            continuous_game_work.MAX_ATTEMPTS + 1
        )
    assert recovered.work_obligations_pending == 0


def test_terminal_predecessor_does_not_block_an_authoritative_successor(app):
    successor_fingerprint = f'terminal-successor-{GAME_PK}'
    with app.app_context():
        row = seed_accepted_observation()
        predecessor = continuous_game_work.ensure_obligation(change())
        for attempt in range(1, continuous_game_work.MAX_ATTEMPTS + 1):
            predecessor = continuous_game_work.claim(
                predecessor, sync_run_id=90 + attempt,
            )
            predecessor = continuous_game_work.fail(
                predecessor,
                'controlled_failure',
                stage=continuous_game_work.STAGE_CANONICAL_PENDING,
            )

        row.observation_fingerprint = successor_fingerprint
        row.previous_observation_fingerprint = f'identity-{GAME_PK}'
        row.last_classification = detection.CORRECTED
        db.session.commit()
        successor_change = dict(change())
        successor_change['current_observation_identity'] = successor_fingerprint
        successor = continuous_game_work.ensure_obligation(successor_change)

        assert continuous_game_work.claimable_obligations(limit=1) == [successor]


def test_unchanged_feed_processes_pending_obligation_after_shadow(app, monkeypatch):
    with app.app_context():
        seed_accepted_observation()
        continuous_game_work.ensure_obligation(change())

    result, calls = run(
        app, monkeypatch, config(continuous.ActivationMode.SHADOW_FULL_CHAIN),
        results=[change(classification='unchanged', changed=False)],
    )

    with app.app_context():
        jobs = durable_jobs()
        assert len(jobs) == 1
        assert jobs[0].status == sync_jobs.STATUS_SUCCEEDED
        assert jobs[0].attempts == 1
        assert jobs[0].details_json['outcome'] == 'bounded_downstream_complete'
    assert [item[0] for item in calls] == ['cu03', 'cu04', 'cu05', 'cu06']
    assert result.work_obligations_completed == 1
    assert result.work_obligations_pending == 0


def test_action_cap_processes_oldest_pending_work_before_new_candidates(
    app, monkeypatch,
):
    game_pks = [GAME_PK + index for index in range(5)]
    accepted = [change(game_pk=game_pk) for game_pk in game_pks]
    with app.app_context():
        for game_pk in game_pks:
            seed_accepted_observation(game_pk)

    first, first_calls = run(
        app, monkeypatch,
        config(
            continuous.ActivationMode.SHADOW_FULL_CHAIN,
            max_canonical_actions=4,
            expected_plan_fingerprints={
                game_pk: f'reviewed-{game_pk}' for game_pk in game_pks
            },
        ),
        results=accepted,
    )

    with app.app_context():
        jobs = durable_jobs()
        assert [job.status for job in jobs] == [
            sync_jobs.STATUS_SUCCEEDED,
            sync_jobs.STATUS_SUCCEEDED,
            sync_jobs.STATUS_SUCCEEDED,
            sync_jobs.STATUS_SUCCEEDED,
            sync_jobs.STATUS_PENDING,
        ]
        assert jobs[-1].attempts == 0
    assert [item[1] for item in first_calls if item[0] == 'cu03'] == game_pks[:4]
    assert first.work_obligations_pending == 1

    newer_game = GAME_PK + 100
    with app.app_context():
        seed_accepted_observation(newer_game)
    second, second_calls = run(
        app, monkeypatch,
        config(
            continuous.ActivationMode.SHADOW_FULL_CHAIN,
            max_canonical_actions=1,
            expected_plan_fingerprints={
                game_pks[-1]: 'oldest-pending-reviewed',
                newer_game: 'new-candidate-reviewed',
            },
        ),
        results=[
            *(change(
                classification='unchanged', changed=False, game_pk=game_pk,
            ) for game_pk in game_pks),
            change(game_pk=newer_game),
        ],
    )

    assert [item[1] for item in second_calls if item[0] == 'cu03'] == [game_pks[-1]]
    with app.app_context():
        by_game = {
            job.details_json['game_pk']: job
            for job in durable_jobs()
        }
        assert by_game[game_pks[-1]].status == sync_jobs.STATUS_SUCCEEDED
        assert by_game[newer_game].status == sync_jobs.STATUS_PENDING
    assert second.work_obligations_pending == 1


def test_new_pending_games_do_not_starve_older_retryable_work(app, monkeypatch):
    with app.app_context():
        seed_accepted_observation()
        old_job = continuous_game_work.ensure_obligation(change())
        old_job = continuous_game_work.claim(old_job, sync_run_id=90)
        old_job = continuous_game_work.fail(
            old_job,
            'controlled_retryable_failure',
            stage=continuous_game_work.STAGE_CANONICAL_PENDING,
        )
        old_job.created_at = (
            continuous_game_work.utc_now_naive() - timedelta(hours=1)
        )
        db.session.commit()

        new_game_pks = [GAME_PK + index for index in range(1, 4)]
        for game_pk in new_game_pks:
            seed_accepted_observation(game_pk)

    result, calls = run(
        app, monkeypatch,
        config(
            continuous.ActivationMode.SHADOW_FULL_CHAIN,
            max_canonical_actions=1,
        ),
        results=[
            change(classification='unchanged', changed=False),
            *(change(game_pk=game_pk) for game_pk in new_game_pks),
        ],
    )

    assert [item[1] for item in calls if item[0] == 'cu03'] == [GAME_PK]
    with app.app_context():
        by_game = {
            job.details_json['game_pk']: job
            for job in durable_jobs()
        }
        assert by_game[GAME_PK].status == sync_jobs.STATUS_SUCCEEDED
        assert all(
            by_game[game_pk].status == sync_jobs.STATUS_PENDING
            for game_pk in new_game_pks
        )
    assert result.work_obligations_pending == len(new_game_pks)


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


def test_successful_live_obligation_is_idempotent_on_identical_replay(
    app, monkeypatch,
):
    with app.app_context():
        seed_accepted_observation()

    cfg = config(
        continuous.ActivationMode.LIMITED_LIVE,
        production_publication_enabled=True,
        allowlist_game_pks=(GAME_PK,),
    )
    publications = []

    def publisher(*_args, **kwargs):
        publications.append(kwargs)
        return {'committed': True, 'cache_handoff_status': 'complete'}

    first, first_calls = run(
        app, monkeypatch, cfg, results=[change()],
        production_publisher=publisher,
        production_current_id_provider=lambda: 44,
    )
    replay, replay_calls = run(
        app, monkeypatch, cfg,
        results=[change(classification='unchanged', changed=False)],
        production_publisher=publisher,
        production_current_id_provider=lambda: 44,
    )

    with app.app_context():
        jobs = durable_jobs()
        assert len(jobs) == 1
        assert jobs[0].status == sync_jobs.STATUS_SUCCEEDED
        assert jobs[0].attempts == 1
    assert [item[0] for item in first_calls] == ['cu03', 'cu04', 'cu05', 'cu06']
    assert first.live_publications == 1
    assert len(publications) == 1
    assert replay_calls == []
    assert replay.canonical_actions == 0
    assert replay.live_publications == 0
    assert replay.work_obligations_pending == 0


def test_observation_cleanup_with_canonical_noop_does_not_publish(
    app, monkeypatch,
):
    with app.app_context():
        seed_accepted_observation()
        continuous_game_work.ensure_obligation(change())

    def canonical_noop(value, **_kwargs):
        completion_callback = _kwargs.get('canonical_completion_callback')
        if completion_callback is not None:
            completion_callback({
                'game_pk': value['game_pk'],
                'represented_date': '2026-08-29',
                'inserted': 0,
                'updated': 0,
                'pitcher_identity_mutations': 0,
                'impact': {
                    'affected_pitcher_mlb_ids': [],
                    'affected_pitcher_ids': [],
                    'affected_team_ids': [],
                },
                'optional_source_domains': {
                    'final_play_by_play': {
                        'processing_status': 'complete',
                        'pitch_rows': {
                            'inserted': 0, 'updated': 0, 'superseded': 0,
                        },
                    },
                },
            })
            db.session.commit()
        return {
            'game_pk': value['game_pk'],
            'orchestration_status': 'reconciled',
            'canonical_action_attempted': True,
            'cu01_invocations': 1,
            'canonical_mutation_performed': False,
            'affected_pitcher_ids': [],
            'affected_team_ids': [],
        }

    result, calls = run(
        app,
        monkeypatch,
        config(
            continuous.ActivationMode.LIMITED_LIVE,
            production_publication_enabled=True,
            allowlist_game_pks=(GAME_PK,),
        ),
        results=[change(classification='unchanged', changed=False)],
        orchestrator=canonical_noop,
        production_publisher=lambda *_args, **_kwargs: pytest.fail(
            'canonical no-op must not publish'
        ),
        production_current_id_provider=lambda: 44,
    )

    with app.app_context():
        job = durable_jobs()[0]
        assert job.status == sync_jobs.STATUS_SUCCEEDED
        assert job.details_json['outcome'] == 'canonical_no_op'
    assert calls == []
    assert result.canonical_actions == 1
    assert result.canonical_mutation_games == 0
    assert result.live_publications == 0
    assert result.production_authority_affected is False


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
        metrics = Metrics()

        def __init__(self, live_feed):
            self.live_feed = live_feed
            self.boxscore = _boxscore()

        def get_schedule(self, **_kwargs):
            return [{
                'gamePk': REAL_GAME_PK,
                'officialDate': GAME_DATE.isoformat(),
                'gameDate': f'{GAME_DATE.isoformat()}T19:00:00Z',
                'status': {
                    'abstractGameState': 'Final',
                    'codedGameState': 'F',
                    'detailedState': 'Final',
                    'statusCode': 'F',
                },
            }]

        def get_game_live_feed(self, game_pk):
            assert game_pk == REAL_GAME_PK
            return deepcopy(self.live_feed)

        def get_game_boxscore(self, game_pk):
            assert game_pk == REAL_GAME_PK
            return deepcopy(self.boxscore)

        def get_game_play_by_play(self, game_pk):
            assert game_pk == REAL_GAME_PK
            return _play_by_play()

    def observation(*, timestamp, usable=False):
        payload = deepcopy(_feed(
            timestamp=timestamp, status='Final', code='F', inning=9, outs=3,
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
        if usable:
            payload['liveData']['boxscore'] = deepcopy(_boxscore())
        return payload

    with app.app_context():
        _seed_pitchers()
        schedule_final_game(REAL_GAME_PK, game_date=GAME_DATE)
        pending_feed = observation(timestamp='20260827_230000')
        usable_feed = observation(timestamp='20260827_230000', usable=True)
        source_client = SourceClient(usable_feed)
        monkeypatch.setattr(sync_service, 'mlb_client', source_client)
        pending = detection.observe_game_change(
            REAL_GAME_PK, payload=pending_feed,
        )
        assert pending.finality_state == 'final_pending_data'
        assert durable_jobs() == []
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
            team_state_service=state_service,
            read_model_service=read_service,
            cache_adapter=cache,
            client=source_client, cycle_lock_factory=Lock,
        )

        assert result.status == continuous.RESULT_COMPLETE
        assert result.detection_results[0]['classification'] == 'corrected'
        assert result.detection_results[0]['reason'] == (
            detection.EQUAL_REVISION_FINAL_VERIFIED
        )
        assert result.detection_results[0]['finality_state'] == 'final_and_usable'
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
        assert result.work_obligations_completed == 1
        assert result.work_obligations_pending == 0

        jobs = durable_jobs()
        assert len(jobs) == 1
        assert jobs[0].status == sync_jobs.STATUS_SUCCEEDED
        assert jobs[0].attempts == 1
        assert GameLog.query.filter_by(mlb_game_pk=REAL_GAME_PK).count() == 4
        assert GamePitchEvent.query.filter_by(mlb_game_pk=REAL_GAME_PK).count() == 4
        work_items = GameIngestionWorkItem.query.filter_by(
            mlb_game_pk=REAL_GAME_PK,
        ).all()
        assert len(work_items) == 1
        assert work_items[0].status == GameIngestionWorkItem.STATUS_COMPLETED
        proof_rows = DashboardSnapshot.query.filter_by(
            snapshot_type=cu07.PROOF_SNAPSHOT_TYPE,
        ).all()
        assert len(proof_rows) == 1
        assert len(cache.calls) == 1

        replay = continuous.run_continuous_cycle(
            config=config(
                continuous.ActivationMode.PROOF_PUBLICATION,
                expected_plan_fingerprints={
                    REAL_GAME_PK: reviewed['complete_reconciliation_fingerprint'],
                },
            ),
            represented_time=datetime.combine(
                GAME_DATE, datetime.min.time(), tzinfo=timezone.utc,
            ),
            team_state_service=state_service,
            read_model_service=read_service,
            cache_adapter=cache,
            client=source_client, cycle_lock_factory=Lock,
        )

        assert replay.detection_results[0]['classification'] == 'unchanged'
        assert replay.canonical_actions == 0
        assert replay.canonical_mutation_games == 0
        assert replay.proof_publications == 0
        assert replay.work_obligations_pending == 0
        assert len(durable_jobs()) == 1
        assert GameLog.query.filter_by(mlb_game_pk=REAL_GAME_PK).count() == 4
        assert GamePitchEvent.query.filter_by(mlb_game_pk=REAL_GAME_PK).count() == 4
        assert GameIngestionWorkItem.query.filter_by(
            mlb_game_pk=REAL_GAME_PK,
        ).count() == 1
        assert DashboardSnapshot.query.filter_by(
            snapshot_type=cu07.PROOF_SNAPSHOT_TYPE,
        ).count() == 1
        assert len(cache.calls) == 1

        initial_work_item = GameIngestionWorkItem.query.filter_by(
            mlb_game_pk=REAL_GAME_PK,
        ).one()
        initial_source_revision = initial_work_item.source_revision
        initial_work_item.last_attempted_at = datetime.combine(
            GAME_DATE, datetime.min.time(),
        )
        corrected_boxscore = deepcopy(source_client.boxscore)
        corrected_boxscore['teams']['home']['players'][
            'ID1002'
        ]['stats']['pitching']['numberOfPitches'] = 50
        source_client.boxscore = corrected_boxscore
        source_client.live_feed['liveData']['boxscore'] = deepcopy(
            corrected_boxscore
        )
        db.session.commit()

        corrected_plan = game_driven_ingestion.run_game_driven_ingestion(
            GAME_DATE,
            mode=game_driven_ingestion.MODE_SHADOW,
            only_game_pks=[REAL_GAME_PK],
            source_client=source_client,
        )
        correction_reference = GAME_DATE + timedelta(days=1)
        correction = continuous.run_continuous_cycle(
            config=config(
                continuous.ActivationMode.PROOF_PUBLICATION,
                correction_days=2,
                expected_plan_fingerprints={
                    REAL_GAME_PK: corrected_plan[
                        'complete_reconciliation_fingerprint'
                    ],
                },
            ),
            represented_time=datetime.combine(
                correction_reference,
                datetime.min.time(),
                tzinfo=timezone.utc,
            ),
            team_state_service=state_service,
            read_model_service=read_service,
            cache_adapter=cache,
            client=source_client,
            cycle_lock_factory=Lock,
        )

        assert correction.detection_results[0]['classification'] == (
            detection.AMBIGUOUS_OBSERVATION
        )
        assert correction.canonical_actions == 1
        assert correction.canonical_mutation_games == 1
        assert correction.work_obligations_completed == 1
        correction_jobs = durable_jobs()
        assert len(correction_jobs) == 2
        assert correction_jobs[-1].details_json['work_kind'] == (
            continuous_game_work.WORK_KIND_CORRECTION_RECHECK
        )
        assert correction_jobs[-1].status == sync_jobs.STATUS_SUCCEEDED
        corrected_work_item = GameIngestionWorkItem.query.filter_by(
            mlb_game_pk=REAL_GAME_PK,
        ).one()
        assert corrected_work_item.source_revision != initial_source_revision
        assert corrected_work_item.correction_count == 1
        assert GameLog.query.filter_by(
            mlb_game_pk=REAL_GAME_PK,
            pitcher_id=Pitcher.query.filter_by(mlb_id=1002).one().id,
        ).one().pitches_thrown == 50
        correction_proof_count = DashboardSnapshot.query.filter_by(
            snapshot_type=cu07.PROOF_SNAPSHOT_TYPE,
        ).count()
        assert correction_proof_count == 2
        assert len(cache.calls) == 2

        correction_replay = continuous.run_continuous_cycle(
            config=config(
                continuous.ActivationMode.PROOF_PUBLICATION,
                correction_days=2,
                expected_plan_fingerprints={
                    REAL_GAME_PK: corrected_plan[
                        'complete_reconciliation_fingerprint'
                    ],
                },
            ),
            represented_time=datetime.combine(
                correction_reference,
                datetime.min.time(),
                tzinfo=timezone.utc,
            ),
            team_state_service=state_service,
            read_model_service=read_service,
            cache_adapter=cache,
            client=source_client,
            cycle_lock_factory=Lock,
        )

        assert correction_replay.canonical_actions == 0
        assert correction_replay.proof_publications == 0
        assert len(durable_jobs()) == 2
        assert GameLog.query.filter_by(mlb_game_pk=REAL_GAME_PK).count() == 4
        assert GameIngestionWorkItem.query.filter_by(
            mlb_game_pk=REAL_GAME_PK,
        ).count() == 1
        assert DashboardSnapshot.query.filter_by(
            snapshot_type=cu07.PROOF_SNAPSHOT_TYPE,
        ).count() == correction_proof_count
        assert len(cache.calls) == 2
