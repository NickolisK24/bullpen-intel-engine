from datetime import date, timedelta
import os
from pathlib import Path
import subprocess
import sys

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


def test_stale_running_sync_run_is_reclaimed_before_new_writer_starts(client):
    with client.application.app_context():
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


def test_active_running_sync_run_is_not_stolen(client):
    with client.application.app_context():
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
