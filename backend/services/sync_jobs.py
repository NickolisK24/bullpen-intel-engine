"""Durable checkpoint helpers for internal sync enrichment jobs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
import hashlib
import logging
import time
from uuid import uuid4

from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError

from models.sync_job import SyncJob, SyncJobAttempt
from utils.db import db
from utils.time import utc_now_naive


STATUS_PENDING = 'pending'
STATUS_RUNNING = 'running'
STATUS_SUCCEEDED = 'succeeded'
STATUS_FAILED = 'failed'
STATUS_SKIPPED = 'skipped'
STATUS_RETRY_WAIT = 'retry_wait'
STATUS_DEAD = 'dead'

LANE_INTERNAL = 'internal'
LANE_SYNC_PIPELINE = 'sync_pipeline'
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_STALE_AFTER_MINUTES = 60
DEFAULT_PRIORITY = 100
MIN_PRIORITY = 0
MAX_PRIORITY = 1000
DEFAULT_LEASE_SECONDS = 300
DEFAULT_MAX_LEASE_SECONDS = 3600
DEFAULT_RETRY_BASE_SECONDS = 30
DEFAULT_RETRY_MAX_SECONDS = 3600
MAX_RETRY_AFTER_SECONDS = 21600


class JobType(str, Enum):
    FETCH_SCHEDULE = 'fetch_schedule'
    FETCH_GAME = 'fetch_game'
    RECONCILE_FINAL_GAME = 'reconcile_final_game'
    FETCH_ROSTER = 'fetch_roster'
    FETCH_TRANSACTIONS = 'fetch_transactions'
    FETCH_STATCAST = 'fetch_statcast'
    REBUILD_PITCHER = 'rebuild_pitcher'
    REBUILD_TEAM = 'rebuild_team'
    BUILD_READ_MODELS = 'build_read_models'
    PUBLISH = 'publish'
    RECONCILE_DATE = 'reconcile_date'
    TARGETED_REPAIR = 'targeted_repair'
    WORKLOAD_EVIDENCE = 'workload_evidence'
    COMPOSED_READS = 'composed_reads'
    LEGACY_READ_RECONCILIATION_AUDIT = 'legacy_read_reconciliation_audit'
    BACKTEST_REFRESH = 'backtest_refresh'
    CONTINUOUS_FINAL_GAME_RECONCILIATION = 'continuous_final_game_reconciliation'
    CONTINUOUS_GAME_REPLAY = 'continuous_game_replay'


class JobStatus(str, Enum):
    PENDING = STATUS_PENDING
    RUNNING = STATUS_RUNNING
    RETRY_WAIT = STATUS_RETRY_WAIT
    SUCCEEDED = STATUS_SUCCEEDED
    DEAD = STATUS_DEAD


class JobScopeType(str, Enum):
    LEAGUE = 'league'
    BASEBALL_DATE = 'baseball_date'
    GAME = 'game'
    TEAM = 'team'
    PITCHER = 'pitcher'
    SOURCE_DOMAIN = 'source_domain'


CANONICAL_ACTIVE_STATUSES = frozenset({
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_RETRY_WAIT,
})
CANONICAL_TERMINAL_STATUSES = frozenset({STATUS_SUCCEEDED, STATUS_DEAD})
COMPATIBILITY_STATUSES = frozenset({STATUS_FAILED, STATUS_SKIPPED})
ALLOWED_CANONICAL_TRANSITIONS = {
    STATUS_PENDING: frozenset({STATUS_RUNNING}),
    STATUS_RETRY_WAIT: frozenset({STATUS_RUNNING}),
    STATUS_RUNNING: frozenset({
        STATUS_RUNNING,
        STATUS_PENDING,
        STATUS_RETRY_WAIT,
        STATUS_SUCCEEDED,
        STATUS_DEAD,
    }),
    STATUS_SUCCEEDED: frozenset(),
    STATUS_DEAD: frozenset(),
}


class SyncJobError(RuntimeError):
    pass


class InvalidJobError(SyncJobError):
    pass


class JobNotFoundError(SyncJobError):
    pass


class JobStateError(SyncJobError):
    pass


class LeaseOwnershipError(SyncJobError):
    pass


class LeaseExpiredError(LeaseOwnershipError):
    pass

INTERNAL_STAGE_JOBS = (
    {
        'job_name': 'workload_evidence',
        'job_family': 'phase0d_evidence',
    },
    {
        'job_name': 'composed_reads',
        'job_family': 'phase0e_reads',
    },
    {
        'job_name': 'legacy_read_reconciliation_audit',
        'job_family': 'phase0e_reconciliation',
    },
)
BACKTEST_JOB = {
    'job_name': 'backtest_refresh',
    'job_family': 'availability_backtest',
}

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SyncJobSpec:
    job_name: str
    job_family: str
    scope_key: str
    product_date: date
    lane: str = LANE_INTERNAL
    max_attempts: int = DEFAULT_MAX_ATTEMPTS


def _now():
    return utc_now_naive()


def _enum_value(value, enum_type, field_name):
    if isinstance(value, enum_type):
        return value.value
    try:
        return enum_type(str(value)).value
    except (TypeError, ValueError):
        allowed = ', '.join(item.value for item in enum_type)
        raise InvalidJobError(
            f'Invalid {field_name}: {value!r}. Expected one of: {allowed}.'
        ) from None


def _bounded_int(value, *, field_name, minimum, maximum):
    if isinstance(value, bool):
        raise InvalidJobError(f'{field_name} must be an integer.')
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise InvalidJobError(f'{field_name} must be an integer.') from None
    if parsed < minimum or parsed > maximum:
        raise InvalidJobError(
            f'{field_name} must be between {minimum} and {maximum}.'
        )
    return parsed


def _required_text(value, *, field_name, max_length):
    text = str(value or '').strip()
    if not text or len(text) > max_length:
        raise InvalidJobError(
            f'{field_name} must contain 1 to {max_length} characters.'
        )
    return text


def _utc_naive_datetime(value, *, field_name):
    if not isinstance(value, datetime):
        raise InvalidJobError(f'{field_name} must be a datetime.')
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _operation_time(value, *, field_name='now'):
    if value is None:
        return _now()
    return _utc_naive_datetime(value, field_name=field_name)


def _transition(job, status):
    allowed = ALLOWED_CANONICAL_TRANSITIONS.get(job.status, frozenset())
    if status not in allowed:
        raise JobStateError(
            f'Cannot transition sync job {job.id} from {job.status!r} '
            f'to {status!r}.'
        )
    job.status = status


def _active_dedupe_query(dedupe_key):
    return SyncJob.query.filter(
        SyncJob.dedupe_key == dedupe_key,
        SyncJob.status.in_(CANONICAL_ACTIVE_STATUSES),
    )


def enqueue_job(
    *,
    job_type,
    scope_type,
    scope_key,
    product_date,
    dedupe_key,
    payload=None,
    payload_schema_version=1,
    priority=DEFAULT_PRIORITY,
    max_attempts=DEFAULT_MAX_ATTEMPTS,
    available_at=None,
    sync_run_id=None,
    parent_job_id=None,
    job_family='sync_pipeline',
    lane=LANE_SYNC_PIPELINE,
    commit=True,
):
    """Transactionally enqueue or return identical active work.

    The partial unique index on ``dedupe_key`` is the concurrency authority.
    Terminal rows release that identity, so the same logical key may represent
    a later generation while a source-version-specific key can coexist.
    """
    job_name = _enum_value(job_type, JobType, 'job_type')
    normalized_scope_type = _enum_value(
        scope_type, JobScopeType, 'scope_type'
    )
    normalized_scope_key = _required_text(
        scope_key, field_name='scope_key', max_length=160
    )
    normalized_dedupe_key = _required_text(
        dedupe_key, field_name='dedupe_key', max_length=255
    )
    normalized_priority = _bounded_int(
        priority,
        field_name='priority',
        minimum=MIN_PRIORITY,
        maximum=MAX_PRIORITY,
    )
    normalized_max_attempts = _bounded_int(
        max_attempts,
        field_name='max_attempts',
        minimum=1,
        maximum=100,
    )
    normalized_schema_version = _bounded_int(
        payload_schema_version,
        field_name='payload_schema_version',
        minimum=1,
        maximum=1000,
    )
    if not isinstance(product_date, date) or isinstance(product_date, datetime):
        raise InvalidJobError('product_date must be a date.')
    if payload is not None and not isinstance(payload, dict):
        raise InvalidJobError('payload must be a JSON object when supplied.')
    if parent_job_id is not None and db.session.get(SyncJob, parent_job_id) is None:
        raise InvalidJobError(f'Parent sync job {parent_job_id} does not exist.')

    existing = _active_dedupe_query(normalized_dedupe_key).one_or_none()
    if existing is not None:
        return existing

    now = _now()
    eligible_at = (
        _utc_naive_datetime(available_at, field_name='available_at')
        if available_at is not None else now
    )
    job = SyncJob(
        job_name=job_name,
        job_family=_required_text(
            job_family, field_name='job_family', max_length=50
        ),
        lane=_required_text(lane, field_name='lane', max_length=50),
        scope_type=normalized_scope_type,
        scope_key=normalized_scope_key,
        product_date=product_date,
        payload_schema_version=normalized_schema_version,
        dedupe_key=normalized_dedupe_key,
        priority=normalized_priority,
        status=STATUS_PENDING,
        attempts=0,
        max_attempts=normalized_max_attempts,
        first_available_at=eligible_at,
        available_at=eligible_at,
        sync_run_id=sync_run_id,
        parent_job_id=parent_job_id,
        details_json=_json_safe(payload or {}),
        created_at=now,
        updated_at=now,
    )
    try:
        with db.session.begin_nested():
            db.session.add(job)
            db.session.flush()
    except IntegrityError:
        existing = _active_dedupe_query(normalized_dedupe_key).one_or_none()
        if existing is None:
            raise
        job = existing
    if commit:
        db.session.commit()
    return job


def _eligible_claim_query(now, job_types=None):
    available = func.coalesce(SyncJob.available_at, SyncJob.created_at)
    query = SyncJob.query.filter(
        SyncJob.lane == LANE_SYNC_PIPELINE,
        available <= now,
        or_(
            SyncJob.status.in_((STATUS_PENDING, STATUS_RETRY_WAIT)),
            and_(
                SyncJob.status == STATUS_RUNNING,
                SyncJob.lease_until.is_not(None),
                SyncJob.lease_until <= now,
            ),
        ),
    )
    if job_types:
        if isinstance(job_types, (str, JobType)):
            job_types = (job_types,)
        values = [_enum_value(item, JobType, 'job_type') for item in job_types]
        query = query.filter(SyncJob.job_name.in_(values))
    return query.order_by(
        SyncJob.priority.asc(),
        available.asc(),
        SyncJob.created_at.asc(),
        SyncJob.id.asc(),
    )


def _attempt_for_token(job_id, claim_token):
    if not claim_token:
        return None
    return SyncJobAttempt.query.filter_by(
        sync_job_id=job_id,
        claim_token=claim_token,
    ).one_or_none()


def _finish_attempt(
    job,
    *,
    claim_token,
    now,
    outcome,
    retryable=None,
    error_message=None,
    error_type=None,
):
    attempt = _attempt_for_token(job.id, claim_token)
    if attempt is None or attempt.finished_at is not None:
        return attempt
    attempt.finished_at = now
    attempt.outcome = outcome
    attempt.retryable = retryable
    attempt.error_message = error_message
    attempt.error_type = error_type
    return attempt


def _clear_lease(job):
    job.worker_id = None
    job.claim_token = None
    job.lease_until = None


def _mark_exhausted(job, *, now, reason):
    previous_token = job.claim_token
    _finish_attempt(
        job,
        claim_token=previous_token,
        now=now,
        outcome='dead',
        retryable=False,
        error_message=reason,
        error_type='AttemptsExhausted',
    )
    job.status = STATUS_DEAD
    job.dead_at = now
    job.completed_at = now
    job.error_message = reason
    job.error_type = 'AttemptsExhausted'
    job.updated_at = now
    _clear_lease(job)


def claim_next_job(
    worker_id,
    *,
    job_types=None,
    lease_seconds=DEFAULT_LEASE_SECONDS,
    max_lease_seconds=DEFAULT_MAX_LEASE_SECONDS,
    now=None,
    commit=True,
):
    """Claim one eligible job using row locking and PostgreSQL SKIP LOCKED."""
    owner = _required_text(worker_id, field_name='worker_id', max_length=120)
    lease_seconds = _bounded_int(
        lease_seconds, field_name='lease_seconds', minimum=1, maximum=86400
    )
    max_lease_seconds = _bounded_int(
        max_lease_seconds,
        field_name='max_lease_seconds',
        minimum=lease_seconds,
        maximum=86400,
    )
    claimed_at = _operation_time(now)

    while True:
        job = (
            _eligible_claim_query(claimed_at, job_types)
            .with_for_update(skip_locked=True)
            .first()
        )
        if job is None:
            if commit:
                db.session.commit()
            return None

        if (job.attempts or 0) >= (job.max_attempts or 0):
            _mark_exhausted(
                job,
                now=claimed_at,
                reason='Automatic attempts exhausted before claim.',
            )
            db.session.flush()
            continue

        previous_token = job.claim_token
        if job.status == STATUS_RUNNING:
            _finish_attempt(
                job,
                claim_token=previous_token,
                now=claimed_at,
                outcome='lease_expired',
                retryable=True,
                error_message='Worker lease expired before completion.',
                error_type='LeaseExpired',
            )

        _transition(job, STATUS_RUNNING)
        job.attempts = (job.attempts or 0) + 1
        job.started_at = job.started_at or claimed_at
        job.claimed_at = claimed_at
        job.last_heartbeat_at = claimed_at
        job.worker_id = owner
        job.claim_token = str(uuid4())
        job.lease_until = claimed_at + timedelta(
            seconds=min(lease_seconds, max_lease_seconds)
        )
        job.completed_at = None
        job.dead_at = None
        job.duration_ms = None
        job.error_message = None
        job.error_type = None
        job.updated_at = claimed_at
        db.session.add(SyncJobAttempt(
            sync_job_id=job.id,
            attempt_number=job.attempts,
            worker_id=owner,
            claim_token=job.claim_token,
            claimed_at=claimed_at,
            lease_until=job.lease_until,
        ))
        if commit:
            db.session.commit()
        else:
            db.session.flush()
        return job


def _owned_job(job_id, *, worker_id, claim_token, now):
    job = (
        SyncJob.query
        .filter(SyncJob.id == job_id)
        .with_for_update()
        .one_or_none()
    )
    if job is None:
        raise JobNotFoundError(f'Sync job {job_id} does not exist.')
    if job.status != STATUS_RUNNING:
        raise JobStateError(
            f'Sync job {job_id} is {job.status!r}, not running.'
        )
    if job.worker_id != worker_id or job.claim_token != claim_token:
        raise LeaseOwnershipError(
            f'Worker does not own the current lease for sync job {job_id}.'
        )
    if job.lease_until is None or job.lease_until <= now:
        raise LeaseExpiredError(f'Lease for sync job {job_id} has expired.')
    return job


def heartbeat_job(
    job_id,
    *,
    worker_id,
    claim_token,
    extension_seconds=DEFAULT_LEASE_SECONDS,
    max_lease_seconds=DEFAULT_MAX_LEASE_SECONDS,
    now=None,
    commit=True,
):
    heartbeat_at = _operation_time(now)
    extension_seconds = _bounded_int(
        extension_seconds,
        field_name='extension_seconds',
        minimum=1,
        maximum=86400,
    )
    max_lease_seconds = _bounded_int(
        max_lease_seconds,
        field_name='max_lease_seconds',
        minimum=extension_seconds,
        maximum=86400,
    )
    job = _owned_job(
        job_id,
        worker_id=worker_id,
        claim_token=claim_token,
        now=heartbeat_at,
    )
    hard_limit = job.claimed_at + timedelta(seconds=max_lease_seconds)
    proposed = min(
        hard_limit,
        heartbeat_at + timedelta(seconds=extension_seconds),
    )
    job.lease_until = max(job.lease_until, proposed)
    job.last_heartbeat_at = heartbeat_at
    job.updated_at = heartbeat_at
    attempt = _attempt_for_token(job.id, claim_token)
    if attempt is not None:
        attempt.lease_until = job.lease_until
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return job


def _error_fields(error):
    if isinstance(error, BaseException):
        return str(error), type(error).__name__
    return str(error), None


def succeed_job(
    job_id,
    *,
    worker_id,
    claim_token,
    result=None,
    now=None,
    commit=True,
):
    completed_at = _operation_time(now)
    job = _owned_job(
        job_id,
        worker_id=worker_id,
        claim_token=claim_token,
        now=completed_at,
    )
    _transition(job, STATUS_SUCCEEDED)
    _finish_attempt(
        job,
        claim_token=claim_token,
        now=completed_at,
        outcome=STATUS_SUCCEEDED,
        retryable=False,
    )
    job.completed_at = completed_at
    job.last_heartbeat_at = completed_at
    job.duration_ms = _duration_ms(job.started_at)
    job.error_message = None
    job.error_type = None
    job.result_json = _json_safe(result or {})
    job.updated_at = completed_at
    _clear_lease(job)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return job


def retry_delay_seconds(
    *,
    job_id,
    attempt_count,
    base_seconds=DEFAULT_RETRY_BASE_SECONDS,
    max_seconds=DEFAULT_RETRY_MAX_SECONDS,
):
    """Return bounded exponential backoff with deterministic ±20% jitter."""
    attempt = max(1, int(attempt_count or 1))
    base = max(1, int(base_seconds or 1))
    maximum = max(base, int(max_seconds or base))
    raw = min(maximum, base * (2 ** (attempt - 1)))
    digest = hashlib.sha256(f'{job_id}:{attempt}'.encode('utf-8')).digest()
    fraction = int.from_bytes(digest[:2], 'big') / 65535
    jittered = raw * (0.8 + (0.4 * fraction))
    return max(1, min(maximum, int(round(jittered))))


def retry_job(
    job_id,
    error,
    *,
    worker_id,
    claim_token,
    retryable=True,
    retry_after_seconds=None,
    now=None,
    commit=True,
):
    failed_at = _operation_time(now)
    job = _owned_job(
        job_id,
        worker_id=worker_id,
        claim_token=claim_token,
        now=failed_at,
    )
    error_message, error_type = _error_fields(error)
    exhausted = (job.attempts or 0) >= (job.max_attempts or 0)
    if not retryable or exhausted:
        _transition(job, STATUS_DEAD)
        _finish_attempt(
            job,
            claim_token=claim_token,
            now=failed_at,
            outcome=STATUS_DEAD,
            retryable=False,
            error_message=error_message,
            error_type=error_type,
        )
        job.dead_at = failed_at
        job.completed_at = failed_at
    else:
        _transition(job, STATUS_RETRY_WAIT)
        if retry_after_seconds is None:
            delay = retry_delay_seconds(
                job_id=job.id,
                attempt_count=job.attempts,
            )
        else:
            delay = _bounded_int(
                retry_after_seconds,
                field_name='retry_after_seconds',
                minimum=0,
                maximum=MAX_RETRY_AFTER_SECONDS,
            )
        job.available_at = failed_at + timedelta(seconds=delay)
        job.completed_at = None
        _finish_attempt(
            job,
            claim_token=claim_token,
            now=failed_at,
            outcome=STATUS_RETRY_WAIT,
            retryable=True,
            error_message=error_message,
            error_type=error_type,
        )
    job.error_message = error_message
    job.error_type = error_type
    job.last_heartbeat_at = failed_at
    job.duration_ms = _duration_ms(job.started_at)
    job.updated_at = failed_at
    _clear_lease(job)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return job


def dead_job(
    job_id,
    error,
    *,
    worker_id,
    claim_token,
    now=None,
    commit=True,
):
    """Settle currently owned work as immediately non-retryable."""
    return retry_job(
        job_id,
        error,
        worker_id=worker_id,
        claim_token=claim_token,
        retryable=False,
        now=now,
        commit=commit,
    )


def release_job(
    job_id,
    *,
    worker_id,
    claim_token,
    available_at=None,
    now=None,
    commit=True,
):
    released_at = _operation_time(now)
    job = _owned_job(
        job_id,
        worker_id=worker_id,
        claim_token=claim_token,
        now=released_at,
    )
    _transition(job, STATUS_PENDING)
    _finish_attempt(
        job,
        claim_token=claim_token,
        now=released_at,
        outcome='released',
        retryable=True,
    )
    job.available_at = (
        _utc_naive_datetime(available_at, field_name='available_at')
        if available_at is not None else released_at
    )
    job.updated_at = released_at
    _clear_lease(job)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return job


def run_next_job(
    worker_id,
    handlers,
    *,
    job_types=None,
    lease_seconds=DEFAULT_LEASE_SECONDS,
    error_retryable=None,
):
    """Claim and execute exactly one job; no scheduler or busy loop is included."""
    job = claim_next_job(
        worker_id,
        job_types=job_types,
        lease_seconds=lease_seconds,
    )
    if job is None:
        return None
    claim_token = job.claim_token
    handler = handlers.get(job.job_name) if isinstance(handlers, dict) else None
    if handler is None:
        error = InvalidJobError(f'No handler registered for {job.job_name!r}.')
        retry_job(
            job.id,
            error,
            worker_id=worker_id,
            claim_token=claim_token,
            retryable=False,
        )
        raise error
    try:
        result = handler(job)
    except BaseException as error:
        db.session.rollback()
        try:
            retry_job(
                job.id,
                error,
                worker_id=worker_id,
                claim_token=claim_token,
                retryable=(
                    bool(error_retryable(error))
                    if error_retryable is not None else True
                ),
            )
        except BaseException:
            logger.exception('Failed to persist sync job retry state.')
        raise
    return succeed_job(
        job.id,
        worker_id=worker_id,
        claim_token=claim_token,
        result=result,
    )


def job_state_summary(sync_run_id):
    rows = (
        db.session.query(SyncJob.status, SyncJob.attempts, SyncJob.max_attempts)
        .filter(SyncJob.sync_run_id == sync_run_id)
        .all()
    )
    counts = {}
    for status, _attempts, _max_attempts in rows:
        counts[status] = counts.get(status, 0) + 1
    legacy_retryable = sum(
        1 for status, attempts, max_attempts in rows
        if status == STATUS_FAILED and (attempts or 0) < (max_attempts or 0)
    )
    legacy_exhausted = counts.get(STATUS_FAILED, 0) - legacy_retryable
    return {
        'sync_run_id': sync_run_id,
        'total': len(rows),
        'counts': counts,
        'active': (
            sum(counts.get(status, 0) for status in CANONICAL_ACTIVE_STATUSES)
            + legacy_retryable
        ),
        'terminal': (
            sum(counts.get(status, 0) for status in CANONICAL_TERMINAL_STATUSES)
            + counts.get(STATUS_SKIPPED, 0)
            + legacy_exhausted
        ),
    }


def scope_key_for_product_date(product_date):
    return f'product_date:{product_date.isoformat()}'


def legacy_dedupe_key(job_name, scope_key, product_date):
    """Give established checkpoint writers active database uniqueness."""
    raw = f'legacy:{job_name}:{scope_key}:{product_date.isoformat()}'
    if len(raw) <= 255:
        return raw
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    return f'{raw[:181]}:sha256:{digest}'


def internal_enrichment_job_specs(product_dates, *, include_backtest=True):
    dates = sorted({_date for _date in product_dates or [] if _date is not None})
    specs = []
    for product_date in dates:
        scope_key = scope_key_for_product_date(product_date)
        for stage in INTERNAL_STAGE_JOBS:
            specs.append(
                SyncJobSpec(
                    job_name=stage['job_name'],
                    job_family=stage['job_family'],
                    scope_key=scope_key,
                    product_date=product_date,
                )
            )
        if include_backtest:
            specs.append(
                SyncJobSpec(
                    job_name=BACKTEST_JOB['job_name'],
                    job_family=BACKTEST_JOB['job_family'],
                    scope_key=scope_key,
                    product_date=product_date,
                )
            )
    return specs


def ensure_jobs(specs, *, sync_run_id=None, commit=True, run_logger=None):
    log = run_logger or logger
    planned = []
    created = 0
    for spec in specs:
        job = (
            SyncJob.query
            .filter_by(
                job_name=spec.job_name,
                scope_key=spec.scope_key,
                product_date=spec.product_date,
            )
            .first()
        )
        if job is None:
            job = SyncJob(
                job_name=spec.job_name,
                job_family=spec.job_family,
                lane=spec.lane,
                scope_type=JobScopeType.BASEBALL_DATE.value,
                scope_key=spec.scope_key,
                product_date=spec.product_date,
                payload_schema_version=1,
                dedupe_key=legacy_dedupe_key(
                    spec.job_name,
                    spec.scope_key,
                    spec.product_date,
                ),
                status=STATUS_PENDING,
                attempts=0,
                max_attempts=spec.max_attempts,
                sync_run_id=sync_run_id,
                created_at=_now(),
                updated_at=_now(),
            )
            db.session.add(job)
            created += 1
        else:
            job.job_family = spec.job_family
            job.lane = spec.lane
            job.max_attempts = spec.max_attempts
            if sync_run_id is not None and job.status in (STATUS_PENDING, STATUS_SKIPPED):
                job.sync_run_id = sync_run_id
            job.updated_at = _now()
        planned.append(job)
    if commit:
        db.session.commit()
    log.info(
        'Sync jobs planned: total=%s created=%s existing=%s.',
        len(planned),
        created,
        len(planned) - created,
    )
    return planned


def plan_internal_enrichment_jobs(
    product_dates,
    *,
    include_backtest=True,
    sync_run_id=None,
    commit=True,
    run_logger=None,
):
    specs = internal_enrichment_job_specs(
        product_dates,
        include_backtest=include_backtest,
    )
    return ensure_jobs(
        specs,
        sync_run_id=sync_run_id,
        commit=commit,
        run_logger=run_logger,
    )


def jobs_by_name(jobs):
    grouped = {}
    for job in jobs:
        grouped.setdefault(job.job_name, []).append(job)
    for name in grouped:
        grouped[name].sort(key=lambda item: (item.product_date, item.id or 0))
    return grouped


def _stale_cutoff(stale_after_minutes=None, now=None):
    return (now or _now()) - timedelta(
        minutes=stale_after_minutes or DEFAULT_STALE_AFTER_MINUTES
    )


def _running_started_at(job):
    return job.last_heartbeat_at or job.started_at or job.updated_at or job.created_at


def _is_stale_running(job, *, stale_after_minutes=None, now=None):
    if job.status != STATUS_RUNNING:
        return False
    started_at = _running_started_at(job)
    if started_at is None:
        return True
    return started_at <= _stale_cutoff(stale_after_minutes, now)


def reclaim_running_jobs(
    jobs,
    *,
    reason,
    stale_after_minutes=None,
    reclaim_abandoned=False,
    commit=True,
    run_logger=None,
):
    log = run_logger or logger
    reclaimed = []
    now = _now()
    for job in jobs:
        if job.status != STATUS_RUNNING:
            continue
        if not reclaim_abandoned and not _is_stale_running(
            job,
            stale_after_minutes=stale_after_minutes,
            now=now,
        ):
            continue
        details = dict(job.details_json or {})
        details['last_reclaim'] = {
            'reason': reason,
            'reclaimed_at': now.isoformat(),
            'previous_started_at': (
                job.started_at.isoformat() if job.started_at else None
            ),
            'previous_sync_run_id': job.sync_run_id,
        }
        job.status = STATUS_PENDING
        job.completed_at = None
        job.error_message = f'Running sync job reclaimed: {reason}'
        job.error_type = 'SyncJobReclaimed'
        job.details_json = details
        job.updated_at = now
        reclaimed.append(job)
        log.info(
            'Sync job reclaimed: job_name=%s product_date=%s scope_key=%s reason=%s.',
            job.job_name,
            job.product_date,
            job.scope_key,
            reason,
        )
    if reclaimed and commit:
        db.session.commit()
    return reclaimed


def claim_job(
    job,
    *,
    sync_run_id=None,
    stale_after_minutes=None,
    reclaim_abandoned=False,
    commit=True,
    run_logger=None,
):
    log = run_logger or logger
    job = db.session.get(SyncJob, job.id) if job.id is not None else job
    if job.status == STATUS_SUCCEEDED:
        log.info(
            'Sync job skipped because already succeeded: job_name=%s '
            'product_date=%s scope_key=%s.',
            job.job_name,
            job.product_date,
            job.scope_key,
        )
        return None
    if job.status == STATUS_RUNNING:
        reclaimed = reclaim_running_jobs(
            [job],
            reason=(
                'internal enrichment lock acquired'
                if reclaim_abandoned
                else 'stale running checkpoint'
            ),
            stale_after_minutes=stale_after_minutes,
            reclaim_abandoned=reclaim_abandoned,
            commit=False,
            run_logger=log,
        )
        if not reclaimed:
            log.info(
                'Sync job still running and not claimable: job_name=%s '
                'product_date=%s scope_key=%s.',
                job.job_name,
                job.product_date,
                job.scope_key,
            )
            return None
    if job.status == STATUS_FAILED and (job.attempts or 0) >= (job.max_attempts or 0):
        log.warning(
            'Sync job not retried because max attempts exhausted: job_name=%s '
            'product_date=%s scope_key=%s attempts=%s max_attempts=%s.',
            job.job_name,
            job.product_date,
            job.scope_key,
            job.attempts,
            job.max_attempts,
        )
        return None

    now = _now()
    job.status = STATUS_RUNNING
    job.attempts = (job.attempts or 0) + 1
    job.started_at = now
    job.completed_at = None
    job.last_heartbeat_at = now
    job.duration_ms = None
    job.error_message = None
    job.error_type = None
    job.sync_run_id = sync_run_id
    job.updated_at = now
    if commit:
        db.session.commit()
    log.info(
        'Sync job starting: job_name=%s product_date=%s scope_key=%s '
        'attempt=%s.',
        job.job_name,
        job.product_date,
        job.scope_key,
        job.attempts,
    )
    return job


def _duration_ms(started_at):
    if started_at is None:
        return None
    return max(0, int(round((_now() - started_at).total_seconds() * 1000)))


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _result_failed(result):
    return isinstance(result, dict) and result.get('status') == STATUS_FAILED


def _result_skipped(result):
    return isinstance(result, dict) and result.get('status') == STATUS_SKIPPED


def complete_job(job, *, result=None, commit=True, run_logger=None):
    log = run_logger or logger
    now = _now()
    job.status = STATUS_SUCCEEDED
    job.completed_at = now
    job.last_heartbeat_at = now
    job.duration_ms = _duration_ms(job.started_at)
    job.error_message = None
    job.error_type = None
    job.details_json = _json_safe(result or {})
    job.updated_at = now
    if commit:
        db.session.commit()
    log.info(
        'Sync job completed: job_name=%s product_date=%s scope_key=%s '
        'elapsed_ms=%s.',
        job.job_name,
        job.product_date,
        job.scope_key,
        job.duration_ms,
    )
    return job


def skip_job(job, *, result=None, commit=True, run_logger=None):
    log = run_logger or logger
    now = _now()
    job.status = STATUS_SKIPPED
    job.completed_at = now
    job.last_heartbeat_at = now
    job.duration_ms = _duration_ms(job.started_at)
    job.details_json = _json_safe(result or {})
    job.updated_at = now
    if commit:
        db.session.commit()
    log.info(
        'Sync job skipped: job_name=%s product_date=%s scope_key=%s '
        'elapsed_ms=%s.',
        job.job_name,
        job.product_date,
        job.scope_key,
        job.duration_ms,
    )
    return job


def fail_job(job, exc_or_message, *, result=None, commit=True, run_logger=None):
    log = run_logger or logger
    now = _now()
    if isinstance(exc_or_message, BaseException):
        error_message = str(exc_or_message)
        error_type = type(exc_or_message).__name__
    else:
        error_message = str(exc_or_message)
        error_type = None
    job.status = STATUS_FAILED
    job.completed_at = now
    job.last_heartbeat_at = now
    job.duration_ms = _duration_ms(job.started_at)
    job.error_message = error_message
    job.error_type = error_type
    job.details_json = _json_safe(result or {})
    job.updated_at = now
    if commit:
        db.session.commit()
    log.warning(
        'Sync job failed: job_name=%s product_date=%s scope_key=%s '
        'elapsed_ms=%s error_type=%s error=%s.',
        job.job_name,
        job.product_date,
        job.scope_key,
        job.duration_ms,
        job.error_type,
        job.error_message,
    )
    return job


def run_checkpointed_job(
    job,
    operation,
    *,
    sync_run_id=None,
    stale_after_minutes=None,
    reclaim_abandoned=False,
    run_logger=None,
):
    claimed = claim_job(
        job,
        sync_run_id=sync_run_id,
        stale_after_minutes=stale_after_minutes,
        reclaim_abandoned=reclaim_abandoned,
        run_logger=run_logger,
    )
    if claimed is None:
        current = db.session.get(SyncJob, job.id)
        if current is not None and current.status == STATUS_SUCCEEDED:
            return {
                'status': STATUS_SKIPPED,
                'reason': 'already_succeeded',
                'checkpoint': current.to_dict(),
            }
        return {
            'status': STATUS_FAILED,
            'reason': 'not_claimable',
            'checkpoint': current.to_dict() if current is not None else None,
        }

    started = time.perf_counter()
    try:
        result = operation()
    except BaseException as exc:
        db.session.rollback()
        fail_job(claimed, exc, run_logger=run_logger)
        raise

    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    if isinstance(result, dict):
        result = dict(result)
        result.setdefault('checkpoint_elapsed_ms', elapsed_ms)
    else:
        result = {'status': 'completed', 'value': _json_safe(result), 'checkpoint_elapsed_ms': elapsed_ms}

    if _result_failed(result):
        fail_job(claimed, result.get('error') or result.get('reason') or 'job failed', result=result, run_logger=run_logger)
    elif _result_skipped(result):
        skip_job(claimed, result=result, run_logger=run_logger)
    else:
        complete_job(claimed, result=result, run_logger=run_logger)
    result['checkpoint'] = claimed.to_dict()
    return result


def summary_for_product_dates(product_dates):
    dates = sorted({_date for _date in product_dates or [] if _date is not None})
    if not dates:
        return {
            'total': 0,
            'succeeded': 0,
            'pending': 0,
            'running': 0,
            'failed': 0,
            'skipped': 0,
            'latest_failed_jobs': [],
        }
    rows = (
        SyncJob.query
        .filter(SyncJob.product_date.in_(dates))
        .order_by(SyncJob.updated_at.desc(), SyncJob.id.desc())
        .all()
    )
    counts = {
        'total': len(rows),
        'succeeded': 0,
        'pending': 0,
        'running': 0,
        'failed': 0,
        'skipped': 0,
        'latest_failed_jobs': [],
    }
    for row in rows:
        if row.status in counts:
            counts[row.status] += 1
    counts['latest_failed_jobs'] = [
        row.to_dict()
        for row in rows
        if row.status == STATUS_FAILED
    ][:5]
    return counts
