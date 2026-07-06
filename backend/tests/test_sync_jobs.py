from datetime import date, timedelta

import pytest
from flask import Flask
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import services.sync as sync_service
from models.sync_job import SyncJob
from services import sync_jobs, sync_metadata
from utils.db import db
from utils.time import utc_now_naive


PRODUCT_DATE = date(2026, 7, 5)


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    app = Flask('test_sync_jobs')
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        create_test_schema(app)
        try:
            yield app
        finally:
            db.session.remove()
            drop_test_schema(app)


def _jobs_by_name():
    return {
        job.job_name: job
        for job in SyncJob.query.order_by(SyncJob.job_name.asc()).all()
    }


def test_sync_jobs_table_has_unique_constraint_and_indexes(app):
    with app.app_context():
        inspector = inspect(db.engine)
        assert 'sync_jobs' in inspector.get_table_names()

        indexes = {index['name'] for index in inspector.get_indexes('sync_jobs')}
        assert {
            'ix_sync_jobs_status',
            'ix_sync_jobs_product_date',
            'ix_sync_jobs_job_family',
            'ix_sync_jobs_lane',
            'ix_sync_jobs_job_name',
            'ix_sync_jobs_updated_at',
        }.issubset(indexes)

        job = SyncJob(
            job_name='workload_evidence',
            job_family='phase0d_evidence',
            lane=sync_jobs.LANE_INTERNAL,
            scope_key=sync_jobs.scope_key_for_product_date(PRODUCT_DATE),
            product_date=PRODUCT_DATE,
            status=sync_jobs.STATUS_PENDING,
            created_at=utc_now_naive(),
            updated_at=utc_now_naive(),
        )
        duplicate = SyncJob(
            job_name=job.job_name,
            job_family=job.job_family,
            lane=job.lane,
            scope_key=job.scope_key,
            product_date=job.product_date,
            status=sync_jobs.STATUS_PENDING,
            created_at=utc_now_naive(),
            updated_at=utc_now_naive(),
        )
        db.session.add(job)
        db.session.commit()
        db.session.add(duplicate)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_sync_job_planning_and_lifecycle_are_idempotent(app):
    with app.app_context():
        first = sync_jobs.plan_internal_enrichment_jobs(
            [PRODUCT_DATE],
            include_backtest=True,
        )
        second = sync_jobs.plan_internal_enrichment_jobs(
            [PRODUCT_DATE],
            include_backtest=True,
        )

        assert len(first) == 4
        assert len(second) == 4
        assert SyncJob.query.count() == 4

        job = _jobs_by_name()[sync_metadata.STAGE_WORKLOAD_EVIDENCE]
        claimed = sync_jobs.claim_job(job, sync_run_id=10)
        assert claimed.status == sync_jobs.STATUS_RUNNING
        assert claimed.attempts == 1

        sync_jobs.complete_job(claimed, result={'status': 'built'})
        assert claimed.status == sync_jobs.STATUS_SUCCEEDED
        assert claimed.completed_at is not None
        assert claimed.duration_ms is not None
        assert sync_jobs.claim_job(claimed) is None
        assert claimed.status == sync_jobs.STATUS_SUCCEEDED


def test_failed_retryable_and_stale_running_jobs_can_be_reclaimed(app):
    with app.app_context():
        jobs = sync_jobs.plan_internal_enrichment_jobs(
            [PRODUCT_DATE],
            include_backtest=False,
        )
        grouped = sync_jobs.jobs_by_name(jobs)

        retryable = grouped[sync_metadata.STAGE_COMPOSED_READS][0]
        claimed = sync_jobs.claim_job(retryable)
        sync_jobs.fail_job(claimed, RuntimeError('first failure'))
        assert claimed.status == sync_jobs.STATUS_FAILED
        assert claimed.error_type == 'RuntimeError'

        retried = sync_jobs.claim_job(claimed)
        assert retried.status == sync_jobs.STATUS_RUNNING
        assert retried.attempts == 2

        active = grouped[sync_service.STAGE_LEGACY_READ_RECONCILIATION_AUDIT][0]
        active.status = sync_jobs.STATUS_RUNNING
        active.started_at = utc_now_naive()
        active.last_heartbeat_at = utc_now_naive()
        active.attempts = 1
        db.session.commit()
        assert sync_jobs.claim_job(active) is None
        assert active.status == sync_jobs.STATUS_RUNNING

        active.last_heartbeat_at = utc_now_naive() - timedelta(minutes=90)
        db.session.commit()
        reclaimed = sync_jobs.claim_job(active, stale_after_minutes=60)
        assert reclaimed.status == sync_jobs.STATUS_RUNNING
        assert reclaimed.attempts == 2
        assert reclaimed.details_json['last_reclaim']['reason'] == 'stale running checkpoint'


def test_internal_enrichment_runs_once_then_skips_completed_checkpoints(app, monkeypatch):
    events = []
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
        app,
        product_dates=[PRODUCT_DATE],
        source='test',
        include_backtest=True,
    )
    second = sync_service.run_internal_enrichment(
        app,
        product_dates=[PRODUCT_DATE],
        source='test',
        include_backtest=True,
    )

    assert status['status'] == sync_metadata.STATUS_SUCCESS
    assert second['status'] == sync_metadata.STATUS_SUCCESS
    assert events == [
        sync_metadata.STAGE_WORKLOAD_EVIDENCE,
        sync_metadata.STAGE_COMPOSED_READS,
        sync_service.STAGE_LEGACY_READ_RECONCILIATION_AUDIT,
        sync_metadata.STAGE_BACKTEST_REFRESH,
    ]
    assert second['checkpoint_summary']['succeeded'] == 4
    assert second['phase_results'][sync_metadata.STAGE_WORKLOAD_EVIDENCE]['status'] == sync_jobs.STATUS_SKIPPED


def test_internal_enrichment_resumes_failed_checkpoint_without_rerunning_prior_jobs(app, monkeypatch):
    events = []
    composed_calls = {'count': 0}

    monkeypatch.setattr(
        sync_service,
        '_safe_build_workload_recovery_evidence_stage',
        lambda *args, **kwargs: (
            events.append(sync_metadata.STAGE_WORKLOAD_EVIDENCE)
            or {'status': 'built'}
        ),
    )

    def _composed(*args, **kwargs):
        composed_calls['count'] += 1
        events.append(sync_metadata.STAGE_COMPOSED_READS)
        if composed_calls['count'] == 1:
            return {'status': 'failed', 'error': 'composed failed'}
        return {'status': 'built'}

    monkeypatch.setattr(sync_service, '_safe_build_composed_reads_stage', _composed)
    monkeypatch.setattr(
        sync_service,
        '_safe_run_legacy_read_reconciliation_audit_stage',
        lambda *args, **kwargs: (
            events.append(sync_service.STAGE_LEGACY_READ_RECONCILIATION_AUDIT)
            or {'status': 'completed'}
        ),
    )

    first = sync_service.run_internal_enrichment(
        app,
        product_dates=[PRODUCT_DATE],
        source='test',
        include_backtest=False,
    )
    assert first['status'] == sync_metadata.STATUS_FAILED
    assert first['failed_phases'] == [sync_metadata.STAGE_COMPOSED_READS]

    with app.app_context():
        jobs = _jobs_by_name()
        assert jobs[sync_metadata.STAGE_WORKLOAD_EVIDENCE].status == sync_jobs.STATUS_SUCCEEDED
        assert jobs[sync_metadata.STAGE_COMPOSED_READS].status == sync_jobs.STATUS_FAILED
        assert jobs[sync_service.STAGE_LEGACY_READ_RECONCILIATION_AUDIT].status == sync_jobs.STATUS_SUCCEEDED

    second = sync_service.run_internal_enrichment(
        app,
        product_dates=[PRODUCT_DATE],
        source='test',
        include_backtest=False,
    )

    assert second['status'] == sync_metadata.STATUS_SUCCESS
    assert events == [
        sync_metadata.STAGE_WORKLOAD_EVIDENCE,
        sync_metadata.STAGE_COMPOSED_READS,
        sync_service.STAGE_LEGACY_READ_RECONCILIATION_AUDIT,
        sync_metadata.STAGE_COMPOSED_READS,
    ]
    with app.app_context():
        assert all(job.status == sync_jobs.STATUS_SUCCEEDED for job in SyncJob.query.all())
