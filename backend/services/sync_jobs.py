"""Durable checkpoint helpers for internal sync enrichment jobs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import logging
import time

from models.sync_job import SyncJob
from utils.db import db
from utils.time import utc_now_naive


STATUS_PENDING = 'pending'
STATUS_RUNNING = 'running'
STATUS_SUCCEEDED = 'succeeded'
STATUS_FAILED = 'failed'
STATUS_SKIPPED = 'skipped'

LANE_INTERNAL = 'internal'
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_STALE_AFTER_MINUTES = 60

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


def scope_key_for_product_date(product_date):
    return f'product_date:{product_date.isoformat()}'


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
                scope_key=spec.scope_key,
                product_date=spec.product_date,
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
