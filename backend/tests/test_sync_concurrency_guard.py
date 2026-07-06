from datetime import date, timedelta
import logging
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.prospect  # noqa: F401
import services.sync as sync_service
from api.bullpen import bullpen_bp
from models.sync_run import SyncRun
from services import sync_metadata
from utils.db import db
from utils.time import utc_now_naive


REPO_BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    with app.app_context():
        create_test_schema(app)
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            drop_test_schema(app)


@pytest.fixture
def app_context_client(client):
    with client.application.app_context():
        yield client


def _run_count():
    return db.session.query(db.func.count(SyncRun.id)).scalar() or 0


def _latest_run():
    return SyncRun.query.order_by(SyncRun.id.desc()).first()


def test_manual_sync_is_refused_when_writer_lock_is_held(app_context_client):
    guard = sync_metadata.acquire_sync_writer_guard(
        job_name=sync_metadata.JOB_DAILY_SYNC,
        source='scheduled',
    )
    try:
        response = app_context_client.post('/api/bullpen/sync', json={'days_back': 7})
    finally:
        guard.release()

    body = response.get_json()
    assert response.status_code == 409
    assert body['status'] == 'blocked'
    assert body['reason'] == sync_metadata.SYNC_WRITER_ALREADY_RUNNING
    assert _run_count() == 0


def test_app_sync_runtime_registers_composed_read_evidence_object_mapper():
    code = (
        "from app import create_app; "
        "from models.sync_run import SyncRun; "
        "from services import sync_metadata; "
        "from utils.db import db; "
        "app = create_app('test'); "
        "ctx = app.app_context(); "
        "ctx.push(); "
        "db.create_all(); "
        "SyncRun.query.count(); "
        "guard = sync_metadata.acquire_sync_writer_guard(); "
        "guard.release(); "
        "db.session.remove(); "
        "db.drop_all(); "
        "ctx.pop(); "
        "print('mapper-ok')"
    )
    env = {
        **os.environ,
        'APP_ENV': 'test',
        'AUTO_SYNC': 'false',
        'DATABASE_URL': 'sqlite:///:memory:',
        'TEST_DATABASE_URL': 'sqlite:///:memory:',
    }
    result = subprocess.run(
        [sys.executable, '-c', code],
        cwd=str(REPO_BACKEND_DIR),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert 'mapper-ok' in result.stdout


def test_fatigue_recalculation_is_refused_when_writer_lock_is_held(app_context_client):
    guard = sync_metadata.acquire_sync_writer_guard(
        job_name=sync_metadata.JOB_DAILY_SYNC,
        source='scheduled',
    )
    try:
        response = app_context_client.post('/api/bullpen/fatigue/recalculate')
    finally:
        guard.release()

    body = response.get_json()
    assert response.status_code == 409
    assert body['status'] == 'blocked'
    assert body['reason'] == sync_metadata.SYNC_WRITER_ALREADY_RUNNING
    assert _run_count() == 0


def test_postgame_refresh_is_blocked_by_existing_writer_lock(client):
    with client.application.app_context():
        guard = sync_metadata.acquire_sync_writer_guard(
            job_name=sync_metadata.JOB_DAILY_SYNC,
            source='scheduled',
        )
    try:
        status = sync_service.run_postgame_refresh(
            client.application,
            schedule_date=date(2026, 7, 3),
            source='test',
        )
    finally:
        guard.release()

    assert status['status'] == 'blocked'
    assert status['reason'] == sync_metadata.SYNC_WRITER_ALREADY_RUNNING
    with client.application.app_context():
        assert _run_count() == 0


def test_stage_failure_reports_in_progress_stage_not_uncompleted_future_stage(
    client,
    monkeypatch,
):
    monkeypatch.setattr(sync_service, 'sync_team_assignments', lambda: {
        'pitchers_refreshed': 1,
        'pitchers_changed': 0,
        'reassigned_count': 0,
        'no_organization_count': 0,
        'unknown_count': 0,
        'errors': 0,
        'by_status': {'ASSIGNED': 1},
    })
    monkeypatch.setattr(
        sync_service,
        'sync_roster_statuses',
        lambda: (_ for _ in ()).throw(RuntimeError('roster crashed')),
    )

    response = client.post('/api/bullpen/sync', json={'days_back': 7})

    assert response.status_code == 500
    with client.application.app_context():
        run = _latest_run()
        assert run.status == sync_metadata.STATUS_FAILED
        assert run.stage == sync_metadata.STAGE_FAILED
        assert run.failed_stage == sync_metadata.STAGE_ROSTER_STATUS


def test_daily_sync_logs_post_fatigue_phase_instrumentation(
    client,
    monkeypatch,
    caplog,
):
    monkeypatch.setattr(sync_service, 'sync_team_assignments', lambda: {
        'pitchers_refreshed': 1,
        'pitchers_changed': 0,
        'reassigned_count': 0,
        'no_organization_count': 0,
        'unknown_count': 0,
        'errors': 0,
        'by_status': {'ASSIGNED': 1},
        'error_details': [],
    })
    monkeypatch.setattr(sync_service, 'sync_roster_statuses', lambda **_kwargs: {
        'pitchers_refreshed': 1,
        'pitchers_changed': 0,
        'unknown_count': 0,
        'records_failed': 0,
        'errors': 0,
        'error_details': [],
    })
    monkeypatch.setattr(sync_service, 'sync_transactions', lambda **_kwargs: {
        'records_fetched': 0,
        'records_stored': 0,
        'unknown_type_count': 0,
        'records_failed': 0,
        'errors': 0,
        'error_details': [],
    })
    monkeypatch.setattr(sync_service, 'sync_recent_logs', lambda **_kwargs: {
        'new_logs_added': 1,
        'pitchers_touched': 1,
        'errors': 0,
        'records_failed': 0,
        'logs_corrected': 0,
        'correction_attempts_failed': 0,
    })
    monkeypatch.setattr(sync_service, 'recalculate_all_fatigue', lambda: 2)
    monkeypatch.setattr(
        sync_service,
        '_safe_build_workload_recovery_evidence_stage',
        lambda *args, **kwargs: {'status': 'built'},
    )
    monkeypatch.setattr(
        sync_service,
        '_safe_build_composed_reads_stage',
        lambda *args, **kwargs: {'status': 'built'},
    )
    monkeypatch.setattr(
        sync_service,
        '_safe_run_legacy_read_reconciliation_audit_stage',
        lambda *args, **kwargs: {'status': 'completed'},
    )
    monkeypatch.setattr(
        sync_service,
        'complete_sync_run_with_snapshot',
        lambda *args, **kwargs: (SimpleNamespace(id=1), SimpleNamespace(id=88)),
    )

    import services.availability_backtest as availability_backtest

    monkeypatch.setattr(
        availability_backtest,
        'refresh_availability_backtest',
        lambda: {'status': 'skipped', 'computed_at': None},
    )

    with caplog.at_level(logging.INFO, logger='baseballos.daily_sync'):
        status = sync_service.run_daily_sync(client.application, days_back=7)

    messages = [record.getMessage() for record in caplog.records]
    assert status['status'] == sync_metadata.STATUS_SUCCESS
    assert status['pitchers_updated'] == 2
    assert status['dashboard_snapshot_id'] == 88

    expected_phases = [
        'sync_completion_snapshot_publish',
        sync_metadata.STAGE_WORKLOAD_EVIDENCE,
        sync_metadata.STAGE_COMPOSED_READS,
        sync_service.STAGE_LEGACY_READ_RECONCILIATION_AUDIT,
        sync_metadata.STAGE_BACKTEST_REFRESH,
        'writer_guard_release',
        'local_status_write',
        'logger_cleanup',
    ]
    for phase in expected_phases:
        assert any(
            f'Daily sync post-fatigue phase completed: phase={phase}' in message
            and 'elapsed_seconds=' in message
            for message in messages
        ), phase
    phase_completed_messages = {
        phase: next(
            index
            for index, message in enumerate(messages)
            if f'Daily sync post-fatigue phase completed: phase={phase}' in message
        )
        for phase in expected_phases
    }
    assert (
        phase_completed_messages['sync_completion_snapshot_publish']
        < phase_completed_messages[sync_metadata.STAGE_WORKLOAD_EVIDENCE]
        < phase_completed_messages[sync_metadata.STAGE_COMPOSED_READS]
        < phase_completed_messages[
            sync_service.STAGE_LEGACY_READ_RECONCILIATION_AUDIT
        ]
        < phase_completed_messages[sync_metadata.STAGE_BACKTEST_REFRESH]
    )
    assert any(
        'Daily sync post-fatigue phase duration summary:' in message
        and sync_metadata.STAGE_COMPOSED_READS in message
        and sync_service.STAGE_LEGACY_READ_RECONCILIATION_AUDIT in message
        and 'sync_completion_snapshot_publish' in message
        for message in messages
    ), messages


def test_daily_sync_public_snapshot_survives_post_publish_internal_failure(
    client,
    monkeypatch,
    caplog,
):
    events = []
    monkeypatch.setattr(sync_service, 'sync_team_assignments', lambda: {
        'pitchers_refreshed': 1,
        'pitchers_changed': 0,
        'reassigned_count': 0,
        'no_organization_count': 0,
        'unknown_count': 0,
        'errors': 0,
        'by_status': {'ASSIGNED': 1},
        'error_details': [],
    })
    monkeypatch.setattr(sync_service, 'sync_roster_statuses', lambda **_kwargs: {
        'pitchers_refreshed': 1,
        'pitchers_changed': 0,
        'unknown_count': 0,
        'records_failed': 0,
        'errors': 0,
        'error_details': [],
    })
    monkeypatch.setattr(sync_service, 'sync_transactions', lambda **_kwargs: {
        'records_fetched': 0,
        'records_stored': 0,
        'unknown_type_count': 0,
        'records_failed': 0,
        'errors': 0,
        'error_details': [],
    })
    monkeypatch.setattr(sync_service, 'sync_recent_logs', lambda **_kwargs: {
        'new_logs_added': 1,
        'pitchers_touched': 1,
        'errors': 0,
        'records_failed': 0,
        'logs_corrected': 0,
        'correction_attempts_failed': 0,
    })
    monkeypatch.setattr(sync_service, 'recalculate_all_fatigue', lambda: 2)

    def fake_complete(*args, **kwargs):
        events.append('public_snapshot')
        return SimpleNamespace(id=1), SimpleNamespace(id=88)

    def fail_workload(*args, **kwargs):
        events.append('workload_evidence')
        raise RuntimeError('internal evidence failed')

    monkeypatch.setattr(sync_service, 'complete_sync_run_with_snapshot', fake_complete)
    monkeypatch.setattr(
        sync_service,
        '_safe_build_workload_recovery_evidence_stage',
        fail_workload,
    )
    monkeypatch.setattr(
        sync_service,
        '_safe_build_composed_reads_stage',
        lambda *args, **kwargs: {'status': 'built'},
    )
    monkeypatch.setattr(
        sync_service,
        '_safe_run_legacy_read_reconciliation_audit_stage',
        lambda *args, **kwargs: {'status': 'completed'},
    )

    import services.availability_backtest as availability_backtest

    monkeypatch.setattr(
        availability_backtest,
        'refresh_availability_backtest',
        lambda: {'status': 'skipped', 'computed_at': None},
    )

    with caplog.at_level(logging.INFO, logger='baseballos.daily_sync'):
        status = sync_service.run_daily_sync(client.application, days_back=7)

    assert events[:2] == ['public_snapshot', 'workload_evidence']
    assert status['status'] == sync_metadata.STATUS_SUCCESS
    assert status['dashboard_snapshot_id'] == 88
    assert any(
        'Daily sync post-publish internal phase failed after public snapshot publish'
        in record.getMessage()
        for record in caplog.records
    )


def test_daily_sync_public_only_skips_internal_enrichment(
    client,
    monkeypatch,
):
    monkeypatch.setattr(sync_service, 'sync_team_assignments', lambda: {
        'pitchers_refreshed': 1,
        'pitchers_changed': 0,
        'reassigned_count': 0,
        'no_organization_count': 0,
        'unknown_count': 0,
        'errors': 0,
        'by_status': {'ASSIGNED': 1},
        'error_details': [],
    })
    monkeypatch.setattr(sync_service, 'sync_roster_statuses', lambda **_kwargs: {
        'pitchers_refreshed': 1,
        'pitchers_changed': 0,
        'unknown_count': 0,
        'records_failed': 0,
        'errors': 0,
        'error_details': [],
    })
    monkeypatch.setattr(sync_service, 'sync_transactions', lambda **_kwargs: {
        'records_fetched': 0,
        'records_stored': 0,
        'unknown_type_count': 0,
        'records_failed': 0,
        'errors': 0,
        'error_details': [],
    })
    monkeypatch.setattr(sync_service, 'sync_recent_logs', lambda **_kwargs: {
        'new_logs_added': 1,
        'pitchers_touched': 1,
        'errors': 0,
        'records_failed': 0,
        'logs_corrected': 0,
        'correction_attempts_failed': 0,
    })
    monkeypatch.setattr(sync_service, 'recalculate_all_fatigue', lambda: 2)
    monkeypatch.setattr(
        sync_service,
        'complete_sync_run_with_snapshot',
        lambda *args, **kwargs: (SimpleNamespace(id=1), SimpleNamespace(id=88)),
    )
    monkeypatch.setattr(
        sync_service,
        '_safe_build_workload_recovery_evidence_stage',
        lambda *args, **kwargs: pytest.fail('workload evidence should not run'),
    )
    monkeypatch.setattr(
        sync_service,
        '_safe_build_composed_reads_stage',
        lambda *args, **kwargs: pytest.fail('composed reads should not run'),
    )
    monkeypatch.setattr(
        sync_service,
        '_safe_run_legacy_read_reconciliation_audit_stage',
        lambda *args, **kwargs: pytest.fail('reconciliation audit should not run'),
    )

    import services.availability_backtest as availability_backtest

    monkeypatch.setattr(
        availability_backtest,
        'refresh_availability_backtest',
        lambda: pytest.fail('backtest should not run'),
    )

    status = sync_service.run_daily_sync(
        client.application,
        days_back=7,
        include_internal_enrichment=False,
    )

    assert status['status'] == sync_metadata.STATUS_SUCCESS
    assert status['dashboard_snapshot_id'] == 88
    assert status['internal_enrichment'] == 'skipped_public_only'


def test_internal_enrichment_runs_internal_phases_without_public_snapshot(
    client,
    monkeypatch,
):
    events = []
    monkeypatch.setattr(
        sync_service,
        'complete_sync_run_with_snapshot',
        lambda *args, **kwargs: pytest.fail('public snapshot should not publish'),
    )
    monkeypatch.setattr(
        sync_service,
        '_safe_build_workload_recovery_evidence_stage',
        lambda *args, **kwargs: (
            events.append(sync_metadata.STAGE_WORKLOAD_EVIDENCE)
            or {'status': 'built'}
        ),
    )
    monkeypatch.setattr(
        sync_service,
        '_safe_build_composed_reads_stage',
        lambda *args, **kwargs: (
            events.append(sync_metadata.STAGE_COMPOSED_READS)
            or {'status': 'built'}
        ),
    )
    monkeypatch.setattr(
        sync_service,
        '_safe_run_legacy_read_reconciliation_audit_stage',
        lambda *args, **kwargs: (
            events.append(sync_service.STAGE_LEGACY_READ_RECONCILIATION_AUDIT)
            or {'status': 'completed'}
        ),
    )

    import services.availability_backtest as availability_backtest

    monkeypatch.setattr(
        availability_backtest,
        'refresh_availability_backtest',
        lambda: (
            events.append(sync_metadata.STAGE_BACKTEST_REFRESH)
            or {'status': 'computed', 'computed_at': None}
        ),
    )

    status = sync_service.run_internal_enrichment(
        client.application,
        product_dates=[date(2026, 7, 5)],
        source='test',
        include_backtest=True,
    )

    assert status['status'] == sync_metadata.STATUS_SUCCESS
    assert events == [
        sync_metadata.STAGE_WORKLOAD_EVIDENCE,
        sync_metadata.STAGE_COMPOSED_READS,
        sync_service.STAGE_LEGACY_READ_RECONCILIATION_AUDIT,
        sync_metadata.STAGE_BACKTEST_REFRESH,
    ]
    with client.application.app_context():
        run = SyncRun.query.order_by(SyncRun.id.desc()).first()
        assert run.job_name == sync_metadata.JOB_INTERNAL_ENRICHMENT
        assert run.status == sync_metadata.STATUS_SUCCESS
        assert run.published_dashboard_snapshot_id is None


def test_internal_enrichment_failure_is_isolated_from_public_sync(
    client,
    monkeypatch,
):
    events = []
    monkeypatch.setattr(sync_service, 'sync_team_assignments', lambda: {
        'pitchers_refreshed': 1,
        'pitchers_changed': 0,
        'reassigned_count': 0,
        'no_organization_count': 0,
        'unknown_count': 0,
        'errors': 0,
        'by_status': {'ASSIGNED': 1},
        'error_details': [],
    })
    monkeypatch.setattr(sync_service, 'sync_roster_statuses', lambda **_kwargs: {
        'pitchers_refreshed': 1,
        'pitchers_changed': 0,
        'unknown_count': 0,
        'records_failed': 0,
        'errors': 0,
        'error_details': [],
    })
    monkeypatch.setattr(sync_service, 'sync_transactions', lambda **_kwargs: {
        'records_fetched': 0,
        'records_stored': 0,
        'unknown_type_count': 0,
        'records_failed': 0,
        'errors': 0,
        'error_details': [],
    })
    monkeypatch.setattr(sync_service, 'sync_recent_logs', lambda **_kwargs: {
        'new_logs_added': 1,
        'pitchers_touched': 1,
        'errors': 0,
        'records_failed': 0,
        'logs_corrected': 0,
        'correction_attempts_failed': 0,
    })
    monkeypatch.setattr(sync_service, 'recalculate_all_fatigue', lambda: 2)
    monkeypatch.setattr(
        sync_service,
        'complete_sync_run_with_snapshot',
        lambda *args, **kwargs: (
            events.append('public_snapshot')
            or (SimpleNamespace(id=1), SimpleNamespace(id=88))
        ),
    )
    monkeypatch.setattr(
        sync_service,
        '_safe_build_workload_recovery_evidence_stage',
        lambda *args, **kwargs: {'status': 'failed', 'error': 'internal failed'},
    )
    monkeypatch.setattr(
        sync_service,
        '_safe_build_composed_reads_stage',
        lambda *args, **kwargs: {'status': 'built'},
    )
    monkeypatch.setattr(
        sync_service,
        '_safe_run_legacy_read_reconciliation_audit_stage',
        lambda *args, **kwargs: {'status': 'completed'},
    )

    public_status = sync_service.run_daily_sync(
        client.application,
        days_back=7,
        include_internal_enrichment=False,
    )
    internal_status = sync_service.run_internal_enrichment(
        client.application,
        product_dates=[date(2026, 7, 5)],
        source='test',
        include_backtest=False,
    )

    assert public_status['status'] == sync_metadata.STATUS_SUCCESS
    assert public_status['dashboard_snapshot_id'] == 88
    assert events == ['public_snapshot']
    assert internal_status['status'] == sync_metadata.STATUS_FAILED
    assert internal_status['failed_phases'] == [
        sync_metadata.STAGE_WORKLOAD_EVIDENCE
    ]


def test_internal_enrichment_lock_does_not_block_public_sync_lock(client):
    with client.application.app_context():
        internal_guard = sync_metadata.acquire_sync_writer_guard(
            job_name=sync_metadata.JOB_INTERNAL_ENRICHMENT,
            source='internal',
        )
        try:
            public_guard = sync_metadata.acquire_sync_writer_guard(
                job_name=sync_metadata.JOB_DAILY_SYNC,
                source='scheduled',
            )
            public_guard.release()
        finally:
            internal_guard.release()


def test_internal_running_row_does_not_block_public_sync_guard(client):
    with client.application.app_context():
        run = SyncRun(
            job_name=sync_metadata.JOB_INTERNAL_ENRICHMENT,
            started_at=utc_now_naive(),
            status=sync_metadata.STATUS_RUNNING,
            stage=sync_metadata.STAGE_WORKLOAD_EVIDENCE,
            source='internal',
            created_at=utc_now_naive(),
        )
        db.session.add(run)
        db.session.commit()

        guard = sync_metadata.acquire_sync_writer_guard(
            job_name=sync_metadata.JOB_DAILY_SYNC,
            source='scheduled',
        )
        guard.release()

        db.session.refresh(run)
        assert run.status == sync_metadata.STATUS_RUNNING


def test_stale_running_sync_run_is_reclaimed_before_new_writer_starts(client, monkeypatch):
    with client.application.app_context():
        monkeypatch.setattr(
            sync_metadata,
            '_uses_postgres_advisory_writer_lock',
            lambda: False,
        )
        stale_run = SyncRun(
            started_at=utc_now_naive() - timedelta(minutes=180),
            status=sync_metadata.STATUS_RUNNING,
            stage=sync_metadata.STAGE_LOG_INGESTION,
            source='manual',
            created_at=utc_now_naive() - timedelta(minutes=180),
        )
        db.session.add(stale_run)
        db.session.commit()

        guard = sync_metadata.acquire_sync_writer_guard(
            job_name=sync_metadata.JOB_DAILY_SYNC,
            source='manual',
        )
        guard.release()

        run = db.session.get(SyncRun, stale_run.id)
        assert run.status == sync_metadata.STATUS_FAILED
        assert run.stage == sync_metadata.STAGE_FAILED
        assert run.failed_stage == sync_metadata.STAGE_LOG_INGESTION
        assert 'Stale running sync reclaimed' in run.error_message


def test_postgres_busy_advisory_lock_preserves_active_running_row(
    client,
    monkeypatch,
):
    with client.application.app_context():
        active_run = SyncRun(
            started_at=utc_now_naive() - timedelta(minutes=10),
            status=sync_metadata.STATUS_RUNNING,
            stage=sync_metadata.STAGE_LOG_INGESTION,
            source='github_actions',
            created_at=utc_now_naive() - timedelta(minutes=10),
        )
        db.session.add(active_run)
        db.session.commit()
        active_run_id = active_run.id

        monkeypatch.setattr(
            sync_metadata,
            '_uses_postgres_advisory_writer_lock',
            lambda: True,
        )

        def busy_lock(*, job_name=None, source=None, lock_scope=None):
            raise sync_metadata.SyncWriterConflict(
                reason=sync_metadata.SYNC_WRITER_ALREADY_RUNNING,
                job_name=job_name,
                source=source,
                active_run=sync_metadata.latest_running_sync_run(),
            )

        monkeypatch.setattr(
            sync_metadata,
            '_acquire_postgres_writer_lock',
            busy_lock,
        )

        with pytest.raises(sync_metadata.SyncWriterConflict) as exc:
            sync_metadata.acquire_sync_writer_guard(
                job_name=sync_metadata.JOB_DAILY_SYNC,
                source='github_actions',
            )

        run = db.session.get(SyncRun, active_run_id)
        assert exc.value.reason == sync_metadata.SYNC_WRITER_ALREADY_RUNNING
        assert exc.value.active_run.id == active_run_id
        assert run.status == sync_metadata.STATUS_RUNNING
        assert run.completed_at is None
        assert run.stage == sync_metadata.STAGE_LOG_INGESTION


def test_postgres_free_advisory_lock_reclaims_abandoned_running_row_immediately(
    client,
    monkeypatch,
):
    with client.application.app_context():
        abandoned_run = SyncRun(
            started_at=utc_now_naive() - timedelta(minutes=10),
            status=sync_metadata.STATUS_RUNNING,
            stage=sync_metadata.STAGE_COMPOSED_READS,
            source='github_actions',
            created_at=utc_now_naive() - timedelta(minutes=10),
        )
        db.session.add(abandoned_run)
        db.session.commit()
        abandoned_run_id = abandoned_run.id

        guard = sync_metadata.SyncWriterGuard()
        monkeypatch.setattr(
            sync_metadata,
            '_uses_postgres_advisory_writer_lock',
            lambda: True,
        )
        monkeypatch.setattr(
            sync_metadata,
            '_acquire_postgres_writer_lock',
            lambda **_kwargs: guard,
        )

        acquired = sync_metadata.acquire_sync_writer_guard(
            job_name=sync_metadata.JOB_DAILY_SYNC,
            source='github_actions',
        )
        acquired.release()

        run = db.session.get(SyncRun, abandoned_run_id)
        assert acquired is guard
        assert run.status == sync_metadata.STATUS_FAILED
        assert run.stage == sync_metadata.STAGE_FAILED
        assert run.failed_stage == sync_metadata.STAGE_COMPOSED_READS
        assert run.completed_at is not None
        assert run.errors == 1
        assert 'Postgres advisory lock was free' in run.error_message
        assert sync_metadata.latest_running_sync_run() is None


def test_active_running_sync_run_is_not_stolen(client, monkeypatch):
    with client.application.app_context():
        monkeypatch.setattr(
            sync_metadata,
            '_uses_postgres_advisory_writer_lock',
            lambda: False,
        )
        active_run = SyncRun(
            started_at=utc_now_naive() - timedelta(minutes=10),
            status=sync_metadata.STATUS_RUNNING,
            stage=sync_metadata.STAGE_LOG_INGESTION,
            source='manual',
            created_at=utc_now_naive() - timedelta(minutes=10),
        )
        db.session.add(active_run)
        db.session.commit()

        with pytest.raises(sync_metadata.SyncWriterConflict) as exc:
            sync_metadata.acquire_sync_writer_guard(
                job_name=sync_metadata.JOB_DAILY_SYNC,
                source='scheduled',
            )

        run = db.session.get(SyncRun, active_run.id)
        assert exc.value.reason == sync_metadata.SYNC_WRITER_ALREADY_RUNNING
        assert run.status == sync_metadata.STATUS_RUNNING
        assert run.stage == sync_metadata.STAGE_LOG_INGESTION


def test_sync_status_exposes_active_writer(client):
    with client.application.app_context():
        run = SyncRun(
            started_at=utc_now_naive(),
            status=sync_metadata.STATUS_RUNNING,
            stage=sync_metadata.STAGE_LOG_INGESTION,
            source='manual',
            created_at=utc_now_naive(),
        )
        db.session.add(run)
        db.session.commit()
        run_id = run.id

    response = client.get('/api/bullpen/sync/status')
    body = response.get_json()

    assert response.status_code == 200
    assert body['status'] == sync_metadata.STATUS_RUNNING
    assert body['active_writer']['id'] == run_id
    assert body['freshness']['degradation']['fail_closed'] is True
