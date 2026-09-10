"""Fail-closed execution-source authorization for production sync requests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os


SOURCE_GITHUB_SCHEDULE = 'github_schedule'
SOURCE_EXTERNAL_SCHEDULE = 'external_schedule'
SOURCE_INCIDENT_RECOVERY = 'incident_recovery'

MODE_DAILY = 'daily'
MODE_POSTGAME = 'postgame'
MODE_MORNING = 'morning'

ALLOWED_SOURCES = frozenset({
    SOURCE_GITHUB_SCHEDULE,
    SOURCE_EXTERNAL_SCHEDULE,
    SOURCE_INCIDENT_RECOVERY,
})
ALLOWED_MODES = frozenset({MODE_DAILY, MODE_POSTGAME, MODE_MORNING})

RECOVERY_CONFIRMATION = 'RECOVER'
PRODUCTION_REPOSITORY = 'NickolisK24/bullpen-intel-engine'
PRODUCTION_REF = 'refs/heads/main'
EXTERNAL_AUTHORITY = 'render_cron_v1'
PRODUCTION_SCHEDULES = {
    SOURCE_GITHUB_SCHEDULE: {
        MODE_DAILY: ((10,), 17),
        MODE_POSTGAME: ((2, 4, 6), 11),
        MODE_MORNING: ((14,), 23),
    },
    SOURCE_EXTERNAL_SCHEDULE: {
        MODE_DAILY: ((10,), 5),
        MODE_POSTGAME: ((2, 4, 6), 5),
        MODE_MORNING: ((14,), 5),
    },
}


class SyncExecutionAuthorizationError(RuntimeError):
    """Raised before application initialization for unauthorized production work."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def _truthy(value):
    return str(value or '').strip().lower() in {'1', 'true', 'yes', 'on'}


def parse_utc_datetime(value):
    text = str(value or '').strip()
    if not text:
        raise SyncExecutionAuthorizationError('scheduled_for_required')
    try:
        parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError as exc:
        raise SyncExecutionAuthorizationError('scheduled_for_invalid') from exc
    if parsed.tzinfo is None:
        raise SyncExecutionAuthorizationError('scheduled_for_timezone_required')
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class SyncExecutionContext:
    mode: str
    source: str
    scheduled_for: datetime
    recovery_reason: str | None = None
    operator: str | None = None

    @property
    def intended_window(self):
        scheduled = self.scheduled_for.astimezone(timezone.utc)
        if self.mode == MODE_POSTGAME:
            return f'postgame:{scheduled:%Y-%m-%dT%H:00Z}'
        return f'{self.mode}:{scheduled:%Y-%m-%d}'


def validate_execution_context(
    *, mode, source, scheduled_for, recovery_reason=None,
    recovery_confirmation=None, operator=None, environ=None,
):
    env = environ if environ is not None else os.environ
    mode = str(mode or '').strip().lower()
    source = str(source or '').strip().lower()
    if mode not in ALLOWED_MODES:
        raise SyncExecutionAuthorizationError('execution_mode_invalid')
    if source not in ALLOWED_SOURCES:
        raise SyncExecutionAuthorizationError('execution_source_invalid')

    scheduled = parse_utc_datetime(scheduled_for)
    reason = str(recovery_reason or '').strip() or None
    actor = str(operator or '').strip() or None

    if str(env.get('APP_ENV') or '').strip().lower() == 'production':
        if source == SOURCE_GITHUB_SCHEDULE:
            if not _truthy(env.get('GITHUB_ACTIONS')):
                raise SyncExecutionAuthorizationError('github_actions_required')
            if str(env.get('GITHUB_EVENT_NAME') or '').strip() != 'schedule':
                raise SyncExecutionAuthorizationError('github_schedule_event_required')
            if str(env.get('GITHUB_RUN_ATTEMPT') or '1').strip() != '1':
                raise SyncExecutionAuthorizationError('github_first_attempt_required')
            if str(env.get('GITHUB_REF') or '').strip() != PRODUCTION_REF:
                raise SyncExecutionAuthorizationError('production_main_ref_required')
            if str(env.get('GITHUB_REPOSITORY') or '').strip() != PRODUCTION_REPOSITORY:
                raise SyncExecutionAuthorizationError('production_repository_required')
        elif source == SOURCE_EXTERNAL_SCHEDULE:
            if not _truthy(env.get('RENDER')):
                raise SyncExecutionAuthorizationError('render_runtime_required')
            if str(env.get('BASEBALLOS_SCHEDULER_AUTHORITY') or '').strip() != EXTERNAL_AUTHORITY:
                raise SyncExecutionAuthorizationError('external_scheduler_authority_required')
            if str(env.get('BASEBALLOS_PRODUCTION_BRANCH') or '').strip() != 'main':
                raise SyncExecutionAuthorizationError('production_main_branch_required')
        else:
            if not _truthy(env.get('GITHUB_ACTIONS')):
                raise SyncExecutionAuthorizationError('github_actions_required')
            if str(env.get('GITHUB_EVENT_NAME') or '').strip() != 'workflow_dispatch':
                raise SyncExecutionAuthorizationError('recovery_dispatch_required')
            if str(env.get('GITHUB_REF') or '').strip() != PRODUCTION_REF:
                raise SyncExecutionAuthorizationError('production_main_ref_required')
            if str(env.get('GITHUB_REPOSITORY') or '').strip() != PRODUCTION_REPOSITORY:
                raise SyncExecutionAuthorizationError('production_repository_required')
            if not reason:
                raise SyncExecutionAuthorizationError('recovery_reason_required')
            if str(recovery_confirmation or '').strip() != RECOVERY_CONFIRMATION:
                raise SyncExecutionAuthorizationError('recovery_confirmation_required')
            if not actor:
                raise SyncExecutionAuthorizationError('recovery_operator_required')

        if source in PRODUCTION_SCHEDULES:
            expected_hours, expected_minute = PRODUCTION_SCHEDULES[source][mode]
            if scheduled.hour not in expected_hours or scheduled.minute != expected_minute:
                raise SyncExecutionAuthorizationError('scheduled_for_window_invalid')

    if source != SOURCE_INCIDENT_RECOVERY and reason:
        raise SyncExecutionAuthorizationError('recovery_reason_not_allowed')

    return SyncExecutionContext(
        mode=mode,
        source=source,
        scheduled_for=scheduled,
        recovery_reason=reason,
        operator=actor,
    )
