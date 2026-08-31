from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from app import create_app
from models.sync_schedule_attempt import SyncScheduleAttempt
from services import sync_due, sync_metadata
from services.sync_execution_context import (
    SOURCE_EXTERNAL_SCHEDULE,
    SOURCE_GITHUB_SCHEDULE,
    SOURCE_INCIDENT_RECOVERY,
    SyncExecutionAuthorizationError,
    validate_execution_context,
)
from services.github_schedule_slot import resolve_github_schedule_slot
from scripts.refresh_slate_schedule import PRODUCTION_MORNING_TRIGGER_REFUSAL
from scripts.run_postgame_refresh import (
    PRODUCTION_POSTGAME_TRIGGER_REFUSAL,
    production_postgame_trigger_refusal_reason,
)
from tests.db_config import create_test_schema, drop_test_schema
from utils.db import db


BASE_GITHUB_ENV = {
    'APP_ENV': 'production',
    'GITHUB_ACTIONS': 'true',
    'GITHUB_EVENT_NAME': 'schedule',
    'GITHUB_RUN_ATTEMPT': '1',
    'GITHUB_REF': 'refs/heads/main',
    'GITHUB_REPOSITORY': 'NickolisK24/bullpen-intel-engine',
}
BASE_RENDER_ENV = {
    'APP_ENV': 'production',
    'RENDER': 'true',
    'BASEBALLOS_SCHEDULER_AUTHORITY': 'render_cron_v1',
    'BASEBALLOS_PRODUCTION_BRANCH': 'main',
}


@pytest.fixture
def scheduling_app(tmp_path, monkeypatch):
    database_url = f'sqlite:///{(tmp_path / "sync-scheduling.db").as_posix()}'
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('TEST_DATABASE_URL', database_url)
    monkeypatch.setenv('DATABASE_URL', database_url)
    monkeypatch.setenv('AUTO_SYNC', 'false')
    app = create_app('test')
    with app.app_context():
        create_test_schema(app)
        try:
            yield app
        finally:
            db.session.remove()
            drop_test_schema(app)


def _context(source, mode='daily', scheduled_for='2026-08-27T10:05:00Z'):
    return validate_execution_context(
        mode=mode,
        source=source,
        scheduled_for=scheduled_for,
        environ={'APP_ENV': 'test'},
    )


def _successful_lane(*args, **kwargs):
    return ({'status': 'success', 'sync_run_id': None}, {'verified': True}, True)


def test_github_scheduled_daily_is_authorized():
    context = validate_execution_context(
        mode='daily', source=SOURCE_GITHUB_SCHEDULE,
        scheduled_for='2026-08-27T10:17:00Z', environ=BASE_GITHUB_ENV,
    )
    assert context.intended_window == 'daily:2026-08-27'


@pytest.mark.parametrize(
    ('launched_at', 'expected'),
    [
        ('2026-08-31T02:11:00Z', '2026-08-31T02:11:00+00:00'),
        ('2026-08-31T04:11:00Z', '2026-08-31T04:11:00+00:00'),
        ('2026-08-31T06:11:00Z', '2026-08-31T06:11:00+00:00'),
        ('2026-08-31T06:44:00Z', '2026-08-31T06:11:00+00:00'),
        ('2026-08-31T08:36:00Z', '2026-08-31T06:11:00+00:00'),
    ],
)
def test_delayed_github_postgame_delivery_resolves_authorized_slot(launched_at, expected):
    slot = resolve_github_schedule_slot(
        mode='postgame',
        event_schedule='11 2,4,6 * * *',
        launched_at=launched_at,
    )
    assert slot.isoformat() == expected
    context = validate_execution_context(
        mode='postgame',
        source=SOURCE_GITHUB_SCHEDULE,
        scheduled_for=slot.isoformat(),
        environ=BASE_GITHUB_ENV,
    )
    assert context.scheduled_for == slot


def test_slot_resolution_does_not_widen_execution_authority():
    with pytest.raises(ValueError, match='event_schedule_mismatch'):
        resolve_github_schedule_slot(
            mode='postgame',
            event_schedule='11 8 * * *',
            launched_at='2026-08-31T08:36:00Z',
        )
    with pytest.raises(SyncExecutionAuthorizationError, match='scheduled_for_window_invalid'):
        validate_execution_context(
            mode='postgame',
            source=SOURCE_GITHUB_SCHEDULE,
            scheduled_for='2026-08-31T08:11:00Z',
            environ=BASE_GITHUB_ENV,
        )


def test_external_scheduled_daily_is_authorized():
    context = validate_execution_context(
        mode='daily', source=SOURCE_EXTERNAL_SCHEDULE,
        scheduled_for='2026-08-27T10:05:00Z', environ=BASE_RENDER_ENV,
    )
    assert context.source == SOURCE_EXTERNAL_SCHEDULE


def test_governed_recovery_daily_is_authorized_and_identified():
    env = {
        **BASE_GITHUB_ENV,
        'GITHUB_EVENT_NAME': 'workflow_dispatch',
    }
    context = validate_execution_context(
        mode='daily', source=SOURCE_INCIDENT_RECOVERY,
        scheduled_for='2026-08-27T10:05:00Z',
        recovery_reason='GitHub and Render Daily window missed',
        recovery_confirmation='RECOVER', operator='nikko', environ=env,
    )
    assert context.source == SOURCE_INCIDENT_RECOVERY
    assert context.recovery_reason
    assert env['GITHUB_EVENT_NAME'] == 'workflow_dispatch'


@pytest.mark.parametrize(
    ('overrides', 'reason'),
    [
        ({'GITHUB_EVENT_NAME': 'workflow_dispatch'}, 'github_schedule_event_required'),
        ({'GITHUB_RUN_ATTEMPT': '2'}, 'github_first_attempt_required'),
        ({'GITHUB_REF': 'refs/heads/feature'}, 'production_main_ref_required'),
    ],
)
def test_arbitrary_manual_production_daily_is_rejected(overrides, reason):
    with pytest.raises(SyncExecutionAuthorizationError, match=reason):
        validate_execution_context(
            mode='daily', source=SOURCE_GITHUB_SCHEDULE,
            scheduled_for='2026-08-27T10:17:00Z',
            environ={**BASE_GITHUB_ENV, **overrides},
        )


def test_invalid_source_is_rejected():
    with pytest.raises(SyncExecutionAuthorizationError, match='execution_source_invalid'):
        validate_execution_context(
            mode='daily', source='manual', scheduled_for='2026-08-27T10:05:00Z',
            environ={'APP_ENV': 'production'},
        )


def test_legacy_production_postgame_runner_rejects_arbitrary_manual_execution():
    assert production_postgame_trigger_refusal_reason(
        source='manual', schedule_date=None,
        environ={'APP_ENV': 'production'},
    ) == PRODUCTION_POSTGAME_TRIGGER_REFUSAL


def test_governed_explicit_backfill_remains_authorized():
    assert production_postgame_trigger_refusal_reason(
        source='github_actions_backfill',
        schedule_date=datetime(2026, 8, 20).date(),
        environ={
            'APP_ENV': 'production',
            'GITHUB_ACTIONS': 'true',
            'GITHUB_EVENT_NAME': 'workflow_dispatch',
            'GITHUB_REF': 'refs/heads/main',
            'GITHUB_REPOSITORY': 'NickolisK24/bullpen-intel-engine',
        },
    ) is None


def test_legacy_production_morning_runner_is_coordinator_only():
    assert PRODUCTION_MORNING_TRIGGER_REFUSAL == (
        'production_morning_runner_requires_due_sync_coordinator'
    )


@pytest.mark.parametrize(
    ('reason', 'confirmation', 'expected'),
    [('', 'RECOVER', 'recovery_reason_required'), ('incident', '', 'recovery_confirmation_required')],
)
def test_incomplete_recovery_is_rejected(reason, confirmation, expected):
    with pytest.raises(SyncExecutionAuthorizationError, match=expected):
        validate_execution_context(
            mode='daily', source=SOURCE_INCIDENT_RECOVERY,
            scheduled_for='2026-08-27T10:05:00Z', recovery_reason=reason,
            recovery_confirmation=confirmation, operator='nikko',
            environ={**BASE_GITHUB_ENV, 'GITHUB_EVENT_NAME': 'workflow_dispatch'},
        )


def test_render_primary_executes_and_github_fallback_noops(
    scheduling_app, monkeypatch,
):
    monkeypatch.setattr(sync_due, '_run_daily', _successful_lane)
    primary = sync_due.run_due_sync(
        scheduling_app, _context(SOURCE_EXTERNAL_SCHEDULE), public_only=True,
    )
    fallback = sync_due.run_due_sync(
        scheduling_app,
        _context(SOURCE_GITHUB_SCHEDULE, scheduled_for='2026-08-27T10:17:00Z'),
        public_only=True,
    )

    assert primary['status'] == 'executed'
    assert fallback['status'] == 'already_satisfied'
    with scheduling_app.app_context():
        rows = SyncScheduleAttempt.query.order_by(SyncScheduleAttempt.id).all()
        assert [row.source for row in rows] == [
            SOURCE_EXTERNAL_SCHEDULE, SOURCE_GITHUB_SCHEDULE,
        ]
        assert rows[1].outcome == 'already_satisfied'


def test_github_fallback_executes_when_primary_did_not(scheduling_app, monkeypatch):
    monkeypatch.setattr(sync_due, '_run_daily', _successful_lane)
    result = sync_due.run_due_sync(
        scheduling_app,
        _context(SOURCE_GITHUB_SCHEDULE, scheduled_for='2026-08-27T10:17:00Z'),
    )
    assert result['status'] == 'executed'


def test_duplicate_postgame_window_noops(scheduling_app, monkeypatch):
    monkeypatch.setattr(sync_due, '_run_postgame', _successful_lane)
    context = _context(
        SOURCE_EXTERNAL_SCHEDULE, mode='postgame',
        scheduled_for='2026-08-27T02:05:00Z',
    )
    assert sync_due.run_due_sync(scheduling_app, context)['status'] == 'executed'
    fallback = _context(
        SOURCE_GITHUB_SCHEDULE, mode='postgame',
        scheduled_for='2026-08-27T02:11:00Z',
    )
    assert sync_due.run_due_sync(scheduling_app, fallback)['status'] == 'already_satisfied'


def test_cross_source_lock_conflict_prevents_authoritative_work(
    scheduling_app, monkeypatch,
):
    called = False

    def lane(*args, **kwargs):
        nonlocal called
        called = True
        return _successful_lane()

    monkeypatch.setattr(sync_due, '_run_daily', lane)
    with scheduling_app.app_context():
        guard = sync_metadata.acquire_sync_writer_guard(
            job_name=sync_metadata.JOB_DAILY_SYNC,
            source=SOURCE_EXTERNAL_SCHEDULE,
        )
    try:
        result = sync_due.run_due_sync(
            scheduling_app, _context(SOURCE_GITHUB_SCHEDULE),
        )
    finally:
        guard.release()
    assert result['status'] == 'blocked'
    assert called is False


def test_coordinator_releases_lock_after_exception(scheduling_app, monkeypatch):
    def failed_lane(*args, **kwargs):
        raise RuntimeError('lane failed')

    monkeypatch.setattr(sync_due, '_run_daily', failed_lane)
    with pytest.raises(RuntimeError, match='lane failed'):
        sync_due.run_due_sync(scheduling_app, _context(SOURCE_EXTERNAL_SCHEDULE))

    with scheduling_app.app_context():
        guard = sync_metadata.acquire_sync_writer_guard(
            job_name=sync_metadata.JOB_DAILY_SYNC,
            source=SOURCE_GITHUB_SCHEDULE,
        )
        guard.release()


def test_workflow_pins_fallback_recovery_and_due_coordinator_contract():
    path = Path(__file__).resolve().parents[2] / '.github/workflows/baseballos-sync.yml'
    text = path.read_text(encoding='utf-8')
    workflow = yaml.safe_load(text)

    assert [row['cron'] for row in workflow[True]['schedule']] == [
        '17 10 * * *', '23 14 * * *', '11 2,4,6 * * *',
    ]
    assert workflow['concurrency'] == {
        'group': 'baseballos-sync', 'cancel-in-progress': False,
    }
    options = workflow[True]['workflow_dispatch']['inputs']['mode']['options']
    assert options == ['recovery_daily', 'recovery_postgame', 'backfill', 'intraday']
    assert '--execution-source "$EXECUTION_SOURCE"' in text
    assert 'run_due_sync.py --mode daily' in text
    assert 'run_due_sync.py --mode postgame' in text
    assert 'run_due_sync.py --mode morning' in text
    assert '--confirm-recovery "$CONFIRM_RECOVERY"' in text
    assert 'run_postgame_refresh.py --date "$BACKFILL_DATE"' in text
    assert 'run_intraday_reconcile.py' in text
