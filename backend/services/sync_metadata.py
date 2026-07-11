from datetime import timedelta
import threading
import logging

from flask import current_app, has_app_context
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.sync_run import SyncRun
from services import slate_coverage, source_readiness
from services.availability import ACTIVE_WINDOW_DAYS
from services.availability_reference_date import (
    product_availability_reference_date_from_metadata,
    product_current_date,
)
from utils.db import db
from utils.time import to_utc_iso, utc_now_naive


STATUS_RUNNING = 'running'
STATUS_SUCCESS = 'success'
STATUS_PARTIAL = 'partial'
STATUS_FAILED = 'failed'
STATUS_NEVER = 'never'
STATUS_METADATA_UNAVAILABLE = 'metadata_unavailable'

STAGE_STARTED = 'started'
STAGE_TEAM_ASSIGNMENTS = 'team_assignments'
STAGE_ROSTER_STATUS = 'roster_status'
STAGE_TRANSACTIONS = 'transactions'
STAGE_SCHEDULE_FINALITY_PREFLIGHT = 'schedule_finality_preflight'
STAGE_LOG_INGESTION = 'log_ingestion'
STAGE_FATIGUE_RECALCULATION = 'fatigue_recalculation'
STAGE_WORKLOAD_EVIDENCE = 'workload_evidence'
STAGE_COMPOSED_READS = 'composed_reads'
STAGE_BACKTEST_REFRESH = 'backtest_refresh'
STAGE_DASHBOARD_SNAPSHOT = 'dashboard_snapshot'
STAGE_PUBLISHED = 'published'
STAGE_FAILED = 'failed'

# A run counts as a "successful" data write for freshness purposes when it
# either fully succeeded or completed with partial dead-lettered records — in
# both cases the domains it touched were refreshed.
SUCCESSFUL_STATUSES = (STATUS_SUCCESS, STATUS_PARTIAL)

SOURCE_MANUAL = 'manual'
SOURCE_SCHEDULED = 'scheduled'
SOURCE_GITHUB_ACTIONS = 'github_actions'

JOB_DAILY_SYNC = 'daily_sync'
JOB_POSTGAME_REFRESH = 'postgame_refresh'
JOB_FATIGUE_RECALCULATION = 'fatigue_recalculation'
JOB_DASHBOARD_SNAPSHOT_BUILD = 'dashboard_snapshot_build'
JOB_INTERNAL_ENRICHMENT = 'internal_enrichment'

SYNC_WRITER_LOCK_KEY = 820260801
INTERNAL_ENRICHMENT_LOCK_KEY = 820260802
LOCK_SCOPE_PUBLIC = 'public'
LOCK_SCOPE_INTERNAL = 'internal'
INTERNAL_SYNC_JOB_NAMES = (JOB_INTERNAL_ENRICHMENT,)
SYNC_WRITER_ALREADY_RUNNING = 'sync_writer_already_running'
SYNC_WRITER_LOCK_UNAVAILABLE = 'sync_writer_lock_unavailable'
SYNC_WRITER_STALE_RECLAIMED = 'sync_writer_stale_reclaimed'
SYNC_WRITER_ABANDONED_RECLAIMED = 'sync_writer_abandoned_reclaimed'
SYNC_WRITER_STALE_AFTER_MINUTES = 120

logger = logging.getLogger(__name__)
_process_writer_locks = {
    LOCK_SCOPE_PUBLIC: threading.Lock(),
    LOCK_SCOPE_INTERNAL: threading.Lock(),
}


def _now():
    return utc_now_naive()


def _sync_writer_stale_after_minutes():
    if has_app_context():
        return int(
            current_app.config.get(
                'SYNC_WRITER_STALE_AFTER_MINUTES',
                SYNC_WRITER_STALE_AFTER_MINUTES,
            )
        )
    return SYNC_WRITER_STALE_AFTER_MINUTES


def _sync_writer_stale_cutoff(now=None):
    return (now or _now()) - timedelta(minutes=_sync_writer_stale_after_minutes())


def _sync_run_summary(run):
    if run is None:
        return None
    return {
        'id': run.id,
        'job_name': run.job_name,
        'status': run.status,
        'stage': run.stage,
        'source': run.source,
        'started_at': _iso(run.started_at),
        'completed_at': _iso(run.completed_at),
    }


def _normalize_lock_scope(lock_scope=None, *, job_name=None):
    if lock_scope in (LOCK_SCOPE_PUBLIC, LOCK_SCOPE_INTERNAL):
        return lock_scope
    if job_name in INTERNAL_SYNC_JOB_NAMES:
        return LOCK_SCOPE_INTERNAL
    return LOCK_SCOPE_PUBLIC


def _lock_key_for_scope(lock_scope):
    return (
        INTERNAL_ENRICHMENT_LOCK_KEY
        if lock_scope == LOCK_SCOPE_INTERNAL
        else SYNC_WRITER_LOCK_KEY
    )


def _process_writer_lock_for_scope(lock_scope):
    return _process_writer_locks[_normalize_lock_scope(lock_scope)]


def _running_sync_query(lock_scope=None):
    query = SyncRun.query.filter(SyncRun.status == STATUS_RUNNING)
    if lock_scope == LOCK_SCOPE_PUBLIC:
        return query.filter(
            db.or_(
                ~SyncRun.job_name.in_(INTERNAL_SYNC_JOB_NAMES),
                SyncRun.job_name.is_(None),
            )
        )
    if lock_scope == LOCK_SCOPE_INTERNAL:
        return query.filter(SyncRun.job_name.in_(INTERNAL_SYNC_JOB_NAMES))
    return query


def latest_running_sync_run(lock_scope=None):
    return (
        _running_sync_query(lock_scope)
        .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
        .first()
    )


def stale_running_sync_runs(now=None, *, lock_scope=None):
    cutoff = _sync_writer_stale_cutoff(now)
    return (
        _running_sync_query(lock_scope)
        .filter(SyncRun.started_at <= cutoff)
        .order_by(SyncRun.started_at.asc(), SyncRun.id.asc())
        .all()
    )


def running_sync_runs(lock_scope=None):
    return (
        _running_sync_query(lock_scope)
        .order_by(SyncRun.started_at.asc(), SyncRun.id.asc())
        .all()
    )


def _mark_running_sync_runs_reclaimed(runs, *, completed_at, message, commit):
    if not runs:
        return []
    for run in runs:
        prior_stage = run.stage
        run.status = STATUS_FAILED
        run.stage = STAGE_FAILED
        run.failed_stage = prior_stage
        run.completed_at = completed_at
        run.errors = max(run.errors or 0, 1)
        if run.error_message:
            run.error_message = f'{run.error_message}; {message}'
        else:
            run.error_message = message
        db.session.add(run)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return runs


def recover_stale_running_sync_runs(now=None, *, commit=True, lock_scope=None):
    """
    Mark abandoned running rows failed after the writer lock is held.

    Advisory locks release when a crashed process disconnects. A durable
    ``running`` row can remain, though, so the next valid writer reclaims only
    rows older than the configured timeout.
    """
    now = now or _now()
    stale_runs = stale_running_sync_runs(now, lock_scope=lock_scope)
    if not stale_runs:
        return []
    message = (
        f'Stale running sync reclaimed after '
        f'{_sync_writer_stale_after_minutes()} minutes.'
    )
    return _mark_running_sync_runs_reclaimed(
        stale_runs,
        completed_at=now,
        message=message,
        commit=commit,
    )


def recover_abandoned_running_sync_runs(now=None, *, commit=True, lock_scope=None):
    """
    Mark all durable running rows failed while the Postgres writer lock is held.

    A successfully acquired Postgres advisory lock proves no other writer still
    holds the exclusive sync lock. Any durable running row observed at that point
    was left behind by an interrupted process and should not block retries.
    """
    now = now or _now()
    abandoned_runs = running_sync_runs(lock_scope)
    if not abandoned_runs:
        return []
    message = (
        'Abandoned running sync reclaimed because Postgres advisory lock was free.'
    )
    reclaimed = _mark_running_sync_runs_reclaimed(
        abandoned_runs,
        completed_at=now,
        message=message,
        commit=commit,
    )
    logger.warning(
        'Reclaimed %s abandoned running sync row(s) after acquiring the '
        'Postgres advisory lock.',
        len(reclaimed),
    )
    return reclaimed


class SyncWriterConflict(RuntimeError):
    def __init__(
        self,
        *,
        reason=SYNC_WRITER_ALREADY_RUNNING,
        job_name=None,
        source=None,
        active_run=None,
        message=None,
    ):
        self.reason = reason
        self.job_name = job_name
        self.source = source
        self.active_run = active_run
        self.message = message or (
            'Another sync writer is already running.'
            if reason == SYNC_WRITER_ALREADY_RUNNING
            else 'Sync writer lock state is unavailable.'
        )
        super().__init__(self.message)

    def to_dict(self):
        return {
            'status': 'blocked',
            'reason': self.reason,
            'message': self.message,
            'job_name': self.job_name,
            'source': self.source,
            'active_writer': _sync_run_summary(self.active_run),
        }


class SyncWriterGuard:
    def __init__(
        self,
        *,
        connection=None,
        process_lock_acquired=False,
        lock_scope=LOCK_SCOPE_PUBLIC,
    ):
        self.connection = connection
        self.process_lock_acquired = process_lock_acquired
        self.lock_scope = _normalize_lock_scope(lock_scope)
        self.lock_key = _lock_key_for_scope(self.lock_scope)
        self.released = False

    def release(self):
        if self.released:
            return
        self.released = True
        try:
            if self.connection is not None:
                self.connection.execute(
                    text('SELECT pg_advisory_unlock(:lock_key)'),
                    {'lock_key': self.lock_key},
                )
        finally:
            if self.connection is not None:
                self.connection.close()
            if self.process_lock_acquired:
                _process_writer_lock_for_scope(self.lock_scope).release()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.release()
        return False


def _acquire_postgres_writer_lock(job_name=None, source=None, lock_scope=None):
    lock_scope = _normalize_lock_scope(lock_scope, job_name=job_name)
    connection = db.engine.connect()
    try:
        locked = connection.execute(
            text('SELECT pg_try_advisory_lock(:lock_key)'),
            {'lock_key': _lock_key_for_scope(lock_scope)},
        ).scalar()
    except SQLAlchemyError as exc:
        connection.close()
        db.session.rollback()
        logger.warning('Could not acquire sync writer advisory lock: %s', exc)
        raise SyncWriterConflict(
            reason=SYNC_WRITER_LOCK_UNAVAILABLE,
            job_name=job_name,
            source=source,
        ) from exc
    if locked is not True:
        connection.close()
        raise SyncWriterConflict(
            reason=SYNC_WRITER_ALREADY_RUNNING,
            job_name=job_name,
            source=source,
            active_run=latest_running_sync_run(lock_scope),
        )
    return SyncWriterGuard(connection=connection, lock_scope=lock_scope)


def _acquire_process_writer_lock(job_name=None, source=None, lock_scope=None):
    lock_scope = _normalize_lock_scope(lock_scope, job_name=job_name)
    process_lock = _process_writer_lock_for_scope(lock_scope)
    if not process_lock.acquire(blocking=False):
        raise SyncWriterConflict(
            reason=SYNC_WRITER_ALREADY_RUNNING,
            job_name=job_name,
            source=source,
            active_run=latest_running_sync_run(lock_scope),
        )
    return SyncWriterGuard(process_lock_acquired=True, lock_scope=lock_scope)


def _uses_postgres_advisory_writer_lock():
    return getattr(db.engine.dialect, 'name', '') == 'postgresql'


def acquire_sync_writer_guard(
    *,
    job_name=JOB_DAILY_SYNC,
    source=SOURCE_MANUAL,
    lock_scope=None,
):
    lock_scope = _normalize_lock_scope(lock_scope, job_name=job_name)
    uses_postgres_lock = _uses_postgres_advisory_writer_lock()
    guard = (
        _acquire_postgres_writer_lock(
            job_name=job_name,
            source=source,
            lock_scope=lock_scope,
        )
        if uses_postgres_lock
        else _acquire_process_writer_lock(
            job_name=job_name,
            source=source,
            lock_scope=lock_scope,
        )
    )
    try:
        if uses_postgres_lock:
            recover_abandoned_running_sync_runs(lock_scope=lock_scope)
        else:
            recover_stale_running_sync_runs(lock_scope=lock_scope)
        active_run = latest_running_sync_run(lock_scope)
        if active_run is not None:
            raise SyncWriterConflict(
                reason=SYNC_WRITER_ALREADY_RUNNING,
                job_name=job_name,
                source=source,
                active_run=active_run,
            )
    except Exception:
        guard.release()
        raise
    return guard


def sync_writer_conflict_payload(conflict):
    if isinstance(conflict, SyncWriterConflict):
        return conflict.to_dict()
    return {
        'status': 'blocked',
        'reason': SYNC_WRITER_LOCK_UNAVAILABLE,
        'message': str(conflict),
        'job_name': None,
        'source': None,
        'active_writer': None,
    }


# ── Freshness degradation (fail-closed) ──────────────────────────────────────

DEGRADATION_FRESH = 'fresh'
DEGRADATION_STALE = 'stale'
DEGRADATION_UNAVAILABLE = 'unavailable'
DEGRADATION_MISSING = 'missing'


def freshness_thresholds():
    """
    Resolve the stale / unavailable day thresholds from app config when an app
    context is active, else fall back to the established 14-day active window
    for stale and a hard 30-day boundary for unavailable.
    """
    # Fallbacks mirror config.Config defaults so behavior is identical whether
    # or not an app config is loaded (e.g. bare test apps).
    stale_default = ACTIVE_WINDOW_DAYS  # 14
    unavailable_default = 30
    if has_app_context():
        stale = current_app.config.get('FRESHNESS_STALE_AFTER_DAYS', stale_default)
        unavailable = current_app.config.get(
            'FRESHNESS_UNAVAILABLE_AFTER_DAYS', unavailable_default
        )
    else:
        stale = stale_default
        unavailable = unavailable_default
    # An unavailable threshold below the stale threshold would be incoherent;
    # clamp so unavailable is always at least the stale boundary.
    return int(stale), int(max(unavailable, stale))


def classify_freshness_degradation(data_age_days, stale_after_days, unavailable_after_days):
    """
    Pure classification of data age into fresh / stale / unavailable.

    Boundaries are inclusive at the degrading edge so there is no silent gap:
      - age <  stale_after            → fresh
      - stale_after <= age < unavail  → stale
      - age >= unavailable_after      → unavailable (fail closed)
      - age is None (no data)         → missing (fail closed)

    Unavailable and missing both fail closed: the domain must not be presented
    as usable.
    """
    if data_age_days is None:
        return DEGRADATION_MISSING
    if data_age_days >= unavailable_after_days:
        return DEGRADATION_UNAVAILABLE
    if data_age_days >= stale_after_days:
        return DEGRADATION_STALE
    return DEGRADATION_FRESH


def build_degradation_block(data_age_days):
    """Additive freshness-degradation descriptor for trust surfaces."""
    stale_after, unavailable_after = freshness_thresholds()
    state = classify_freshness_degradation(data_age_days, stale_after, unavailable_after)
    fail_closed = state in (DEGRADATION_UNAVAILABLE, DEGRADATION_MISSING)
    return {
        'state': state,
        'fail_closed': fail_closed,
        'data_age_days': data_age_days,
        'stale_after_days': stale_after,
        'unavailable_after_days': unavailable_after,
    }


def _iso(value):
    # Emit timezone-explicit UTC (…Z) for datetimes so the frontend renders the
    # correct local/ET time; dates stay date-only. See utils.time.to_utc_iso.
    return to_utc_iso(value)


def collect_data_metadata():
    latest_game_date = db.session.query(db.func.max(GameLog.game_date)).scalar()
    latest_fatigue = db.session.query(db.func.max(FatigueScore.calculated_at)).scalar()
    game_logs = db.session.query(db.func.count(GameLog.id)).scalar() or 0
    return {
        'game_logs': int(game_logs),
        'latest_game_date': latest_game_date,
        # V1 workload coverage is based on MLB game logs, so this matches the
        # latest game-log date while leaving a distinct API field for future
        # workload sources.
        'latest_workload_date': latest_game_date,
        'latest_fatigue_calculated_at': latest_fatigue,
    }


def canonical_fatigue_reference_date(reference_date=None):
    """
    Single production authority for the fatigue recalculation reference date:
    the latest completed MLB workload date + 1 day ("tonight's availability").

    Every production-facing recalculation path — the scheduled APScheduler sync,
    the GitHub Actions / manual sync endpoint, and the recalculate endpoint —
    anchors here, so identical game logs always produce identical fatigue scores
    regardless of which path last ran. This is the same anchor the read /
    availability path derives from durable sync metadata
    (product_availability_reference_date_from_metadata), so stored scores and
    displayed availability share one calendar date instead of diverging between a
    per-pitcher last-game-date and the host's runtime "today".

    Returns None when there is no workload data to anchor against.
    """
    if reference_date is not None:
        return reference_date
    return product_availability_reference_date_from_metadata(collect_data_metadata())


def start_sync_run(source=SOURCE_MANUAL, started_at=None, job_name=JOB_DAILY_SYNC):
    started_at = started_at or _now()
    # Start from a clean transaction. If an earlier statement in this request
    # left the session in an aborted/poisoned state (a classic Postgres
    # "current transaction is aborted" trap), the insert below would otherwise
    # fail silently and we would never write a durable row.
    try:
        db.session.rollback()
    except SQLAlchemyError:
        pass
    try:
        run = SyncRun(
            job_name=job_name,
            started_at=started_at,
            status=STATUS_RUNNING,
            stage=STAGE_STARTED,
            source=source,
            created_at=started_at,
        )
        db.session.add(run)
        db.session.commit()
        return run.id
    except SQLAlchemyError as exc:
        db.session.rollback()
        # Loud: a failed durable write must not hide behind the legacy file.
        logger.error('Could not persist sync start metadata: %s', exc)
        return None


def set_sync_stage(sync_run_id, stage, *, commit=True):
    if not sync_run_id:
        return None
    try:
        run = db.session.get(SyncRun, sync_run_id)
        if run is None:
            return None
        run.stage = stage
        if commit:
            db.session.commit()
        else:
            db.session.flush()
        return run
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.warning('Could not persist sync stage %s: %s', stage, exc)
        return None


def finish_sync_run(
    sync_run_id,
    status,
    completed_at=None,
    records_processed=0,
    records_failed=0,
    new_logs_added=0,
    pitchers_updated=0,
    errors=0,
    api_calls_made=0,
    retries_used=0,
    error_message=None,
    source=SOURCE_MANUAL,
    started_at=None,
    job_name=JOB_DAILY_SYNC,
    stage=None,
    failed_stage=None,
    published_dashboard_snapshot_id=None,
    commit=True,
    rollback_before=True,
):
    """
    Record the outcome of a sync as a durable sync_runs row.

    Self-healing: if ``sync_run_id`` is missing or the row cannot be found
    (e.g. ``start_sync_run`` failed to persist), a brand-new row is created with
    the final status. This guarantees that every completed or failed sync leaves
    at least one durable row, so the freshness chain never has to fall back to the
    legacy status file simply because the start write hiccuped.
    """
    completed_at = completed_at or _now()
    if rollback_before:
        try:
            db.session.rollback()
        except SQLAlchemyError:
            pass
    try:
        run = db.session.get(SyncRun, sync_run_id) if sync_run_id else None
        if run is None:
            # Self-heal: start never persisted (or the id was lost). Create the
            # durable row now so the sync is never recorded only in the file.
            run = SyncRun(
                job_name=job_name,
                started_at=started_at or completed_at,
                status=status,
                stage=stage or (
                    STAGE_FAILED if status == STATUS_FAILED else STAGE_PUBLISHED
                ),
                source=source,
                created_at=started_at or completed_at,
            )
            db.session.add(run)

        metadata = collect_data_metadata()
        run.completed_at = completed_at
        run.status = status
        run.stage = stage or (
            STAGE_FAILED if status == STATUS_FAILED else STAGE_PUBLISHED
        )
        run.failed_stage = failed_stage
        if published_dashboard_snapshot_id is not None:
            run.published_dashboard_snapshot_id = published_dashboard_snapshot_id
        run.latest_game_date = metadata['latest_game_date']
        run.latest_workload_date = metadata['latest_workload_date']
        run.latest_fatigue_calculated_at = metadata['latest_fatigue_calculated_at']
        run.records_processed = records_processed or 0
        run.records_failed = records_failed or 0
        run.new_logs_added = new_logs_added or 0
        run.pitchers_updated = pitchers_updated or 0
        run.errors = errors or 0
        run.api_calls_made = api_calls_made or 0
        run.retries_used = retries_used or 0
        run.error_message = error_message
        if commit:
            db.session.commit()
        else:
            db.session.flush()
        return run
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.error('Could not persist sync completion metadata: %s', exc)
        return None


def latest_sync_run():
    return SyncRun.query.order_by(SyncRun.started_at.desc(), SyncRun.id.desc()).first()


def latest_successful_sync_run():
    # A partial run still refreshed the domains it touched (it dead-lettered
    # only the records that failed), so it counts as a successful data write
    # for freshness purposes.
    return (
        SyncRun.query
        .filter(SyncRun.status.in_(SUCCESSFUL_STATUSES))
        .order_by(SyncRun.completed_at.desc(), SyncRun.started_at.desc(), SyncRun.id.desc())
        .first()
    )


def latest_successful_run_for_job(job_name):
    return (
        SyncRun.query
        .filter(SyncRun.job_name == job_name)
        .filter(SyncRun.status.in_(SUCCESSFUL_STATUSES))
        .order_by(SyncRun.completed_at.desc(), SyncRun.started_at.desc(), SyncRun.id.desc())
        .first()
    )


def last_run_per_job():
    """Latest sync_runs row for each distinct job_name, most-recent first."""
    job_names = [
        row[0]
        for row in db.session.query(SyncRun.job_name).distinct().all()
    ]
    runs = []
    for job_name in job_names:
        run = (
            SyncRun.query
            .filter_by(job_name=job_name)
            .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
            .first()
        )
        if run is not None:
            runs.append(run)
    runs.sort(key=lambda r: (r.started_at or r.created_at), reverse=True)
    return runs


def domain_freshness(metadata=None, reference_date=None):
    """
    Per-domain fresh / stale / unavailable classification.

    Each tracked data domain (workload game logs, fatigue scores) is aged
    against the product reference date and run through the same configurable
    degradation thresholds, so the operator can see exactly which domain is
    degrading rather than a single blended freshness signal.
    """
    metadata = metadata or collect_data_metadata()
    ref = reference_date or product_current_date()

    def _age_days(value):
        if value is None:
            return None
        as_date = value.date() if hasattr(value, 'date') else value
        return (ref - as_date).days

    return {
        'workload': {
            'latest_date': _iso(metadata['latest_workload_date']),
            **build_degradation_block(_age_days(metadata['latest_workload_date'])),
        },
        'fatigue': {
            'latest_date': _iso(metadata['latest_fatigue_calculated_at']),
            **build_degradation_block(_age_days(metadata['latest_fatigue_calculated_at'])),
        },
    }


def pipeline_health_payload(reference_date=None):
    """
    Operator-facing pipeline observability: last run per job, each run's status,
    per-domain freshness classification, and the unresolved dead-letter count.

    Read-only and deterministic — everything here is traceable to sync_runs and
    sync_failures rows.
    """
    # Imported here to avoid any import-time coupling between the two services.
    from services import dead_letter

    metadata = collect_data_metadata()
    runs = last_run_per_job()
    overall = build_sync_status_payload(reference_date=reference_date)
    diagnostic_slate_coverage = overall.get('slate_coverage')
    diagnostic_slate_date = (
        diagnostic_slate_coverage.get('slate_date')
        if isinstance(diagnostic_slate_coverage, dict)
        else None
    )
    if diagnostic_slate_date is not None:
        try:
            diagnostic_slate_coverage = slate_coverage.compute_slate_coverage(
                diagnostic_slate_date,
                sync_status=overall.get('status'),
                include_diagnostics=True,
            )
        except Exception as exc:  # noqa: BLE001 - diagnostics must not hide health
            db.session.rollback()
            logger.warning('Could not compute slate coverage diagnostics: %s', exc)

    health_reference_date = reference_date or product_current_date()
    try:
        readiness = source_readiness.source_readiness_payload(
            metadata=metadata,
            sync_status=overall.get('status'),
            slate_coverage_payload=diagnostic_slate_coverage,
            reference_date=health_reference_date,
        )
    except Exception as exc:  # noqa: BLE001 - health diagnostics fail closed
        db.session.rollback()
        logger.warning('Could not compute source readiness diagnostics: %s', exc)
        readiness = source_readiness.unknown_source_readiness_payload()

    return {
        'capability': 'pipeline_health',
        'jobs': [
            {
                'job_name': run.job_name,
                'status': run.status,
                'last_run': run.to_dict(),
            }
            for run in runs
        ],
        'domains': domain_freshness(metadata, reference_date=reference_date),
        'source_readiness': readiness,
        'freshness': overall.get('freshness'),
        'slate_coverage': diagnostic_slate_coverage,
        'sync_status': overall.get('status'),
        'active_writer': overall.get('active_writer'),
        'last_successful_sync': overall.get('last_successful_sync'),
        'dead_letters': {
            'unresolved_count': dead_letter.unresolved_count(),
            'recent': [f.to_dict() for f in dead_letter.unresolved_failures(limit=20)],
        },
    }


def _run_message(run):
    if run is None:
        return ''
    if run.status == STATUS_FAILED:
        return run.error_message or 'Last sync failed.'
    return run.error_message or ''


def determine_freshness_state(
    metadata,
    *,
    status,
    last_successful_sync,
    reference_date=None,
    slate_coverage_payload=None,
):
    """
    Determine workload freshness from durable sync metadata and DB coverage.

    The sync timestamp comes only from sync_runs. Workload coverage comes from
    persisted game/fatigue tables. This function does not infer a successful
    sync from local files or from data presence.
    """
    ref = reference_date or product_current_date()
    availability_reference_date = (
        product_availability_reference_date_from_metadata(metadata)
        if last_successful_sync
        else None
    )
    latest_game_date = metadata['latest_game_date']
    latest_workload_date = metadata['latest_workload_date'] or latest_game_date
    latest_fatigue = metadata['latest_fatigue_calculated_at']
    limitations = []
    reason_codes = []
    cutoff = ref - timedelta(days=ACTIVE_WINDOW_DAYS)
    data_age_days = (
        (ref - latest_workload_date).days
        if latest_workload_date is not None
        else None
    )

    if not metadata['game_logs'] or latest_game_date is None:
        return slate_coverage.append_slate_coverage_to_freshness({
            'is_current': False,
            'is_stale': False,
            'freshness_state': 'missing',
            'data_age_days': None,
            'active_window_days': ACTIVE_WINDOW_DAYS,
            'active_cutoff_date': cutoff.isoformat(),
            'reference_date': ref.isoformat(),
            'availability_reference_date': (
                availability_reference_date.isoformat()
                if availability_reference_date
                else None
            ),
            'reason_codes': ['workload_data_missing'],
            'label': 'No baseball workload data loaded.',
            'limitations': ['No game logs are available.'],
            'degradation': build_degradation_block(None),
        }, slate_coverage_payload)

    is_current = latest_workload_date >= cutoff
    freshness_state = 'current' if is_current else 'stale'
    label = (
        f"Current baseball data through {latest_workload_date.isoformat()}."
        if is_current
        else f"Stale baseball data through {latest_workload_date.isoformat()}."
    )

    if status == STATUS_METADATA_UNAVAILABLE:
        reason_codes.append('durable_sync_metadata_unavailable')
        limitations.append('Sync metadata unavailable; data coverage is based on game logs.')
    if last_successful_sync is None:
        reason_codes.append('successful_sync_missing')
        limitations.append('No durable successful sync timestamp is available.')
    if latest_fatigue is None:
        reason_codes.append('fatigue_timestamp_missing')
        limitations.append('No fatigue calculation timestamp is available.')
    if not is_current:
        reason_codes.append('workload_data_outside_active_window')
        limitations.append(f'Latest game date is outside the {ACTIVE_WINDOW_DAYS}-day freshness window.')
    if status == STATUS_FAILED:
        reason_codes.append('latest_sync_failed')
        limitations.append('The latest sync attempt failed; data may reflect an earlier successful sync.')
    if status == STATUS_RUNNING:
        reason_codes.append('latest_sync_running')
        limitations.append('A sync is currently running; data may reflect the previous completed sync.')

    degradation = build_degradation_block(data_age_days)
    # Fail-closed: past the hard unavailable threshold the domain must not be
    # presented as usable. Surface it explicitly so no caller can render data
    # older than the threshold as fresh.
    if degradation['fail_closed']:
        if 'workload_data_unavailable' not in reason_codes:
            reason_codes.append('workload_data_unavailable')
        unavailable_after = degradation['unavailable_after_days']
        limitations.append(
            f'Latest workload data is older than the {unavailable_after}-day '
            'availability threshold; availability is failing closed.'
        )
        label = (
            f"Unavailable: baseball data through {latest_workload_date.isoformat()} "
            f"is older than the {unavailable_after}-day threshold."
        )

    return slate_coverage.append_slate_coverage_to_freshness({
        'is_current': is_current,
        'is_stale': freshness_state == 'stale',
        'freshness_state': freshness_state,
        'data_age_days': data_age_days,
        'active_window_days': ACTIVE_WINDOW_DAYS,
        'active_cutoff_date': cutoff.isoformat(),
        'reference_date': ref.isoformat(),
        'availability_reference_date': (
            availability_reference_date.isoformat()
            if availability_reference_date
            else None
        ),
        'reason_codes': reason_codes,
        'label': label,
        'limitations': limitations,
        'degradation': degradation,
    }, slate_coverage_payload)


def build_sync_status_payload(legacy_status=None, reference_date=None):
    # ``legacy_status`` is accepted only for older callers. It is intentionally
    # ignored so sync_status.json can never become the reporting authority.
    metadata = collect_data_metadata()
    try:
        latest_run = latest_sync_run()
        successful_run = latest_successful_sync_run()
        active_writer = latest_running_sync_run()
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.warning('Could not read durable sync metadata: %s', exc)
        latest_run = None
        successful_run = None
        active_writer = None

    if latest_run:
        status = latest_run.status
        last_sync = _iso(latest_run.started_at)
        finished_at = _iso(latest_run.completed_at)
        pitchers_updated = latest_run.pitchers_updated or 0
        new_logs_added = latest_run.new_logs_added or 0
        errors = latest_run.errors or 0
        message = _run_message(latest_run)
        sync_block = latest_run.to_dict()
        metadata_source = 'sync_runs'
    else:
        status = STATUS_METADATA_UNAVAILABLE if metadata['game_logs'] else STATUS_NEVER
        last_sync = None
        finished_at = None
        pitchers_updated = 0
        new_logs_added = 0
        errors = 0
        message = (
            'Sync metadata unavailable.'
            if status == STATUS_METADATA_UNAVAILABLE
            else 'No sync has run yet.'
        )
        sync_block = None
        metadata_source = 'none'

    if successful_run:
        last_successful_sync = _iso(successful_run.completed_at or successful_run.started_at)
        last_successful_sync_run = successful_run.to_dict()
    elif status in SUCCESSFUL_STATUSES and finished_at:
        last_successful_sync = finished_at
        last_successful_sync_run = sync_block
    elif status in SUCCESSFUL_STATUSES:
        last_successful_sync = last_sync
        last_successful_sync_run = sync_block
    else:
        last_successful_sync = None
        last_successful_sync_run = None

    try:
        postgame_run = latest_successful_run_for_job(JOB_POSTGAME_REFRESH)
        daily_run = latest_successful_run_for_job(JOB_DAILY_SYNC)
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.warning('Could not read job-specific sync metadata: %s', exc)
        postgame_run = None
        daily_run = None

    availability_reference_date = (
        product_availability_reference_date_from_metadata(metadata)
        if last_successful_sync
        else None
    )
    coverage_slate_date = (
        metadata['latest_workload_date']
        or metadata['latest_game_date']
        or reference_date
        or product_current_date()
    )
    try:
        slate_coverage_payload = slate_coverage.compute_slate_coverage(
            coverage_slate_date,
            sync_status=status,
        )
    except Exception as exc:  # noqa: BLE001 - trust metadata must fail closed
        db.session.rollback()
        logger.warning('Could not compute slate coverage: %s', exc)
        slate_coverage_payload = slate_coverage.unknown_slate_coverage(
            coverage_slate_date
        )

    return {
        'status': status,
        'sync_authority': 'sync_runs',
        # Which durable source actually answered: 'sync_runs' or 'none'.
        'metadata_source': metadata_source,
        'last_sync': last_sync,
        # Clearly named alias of last_sync: the latest check attempt, including
        # no-op postgame runs (so a healthy quiet check is visible as "checked").
        'last_checked': last_sync,
        'last_successful_sync': last_successful_sync,
        'last_completed_game_refresh': (
            _iso(postgame_run.completed_at or postgame_run.started_at)
            if postgame_run is not None
            else None
        ),
        'last_completed_game_refresh_run': (
            postgame_run.to_dict() if postgame_run is not None else None
        ),
        'last_morning_full_sync': (
            _iso(daily_run.completed_at or daily_run.started_at)
            if daily_run is not None
            else None
        ),
        'last_morning_full_sync_run': (
            daily_run.to_dict() if daily_run is not None else None
        ),
        'pitchers_updated': pitchers_updated,
        'new_logs_added': new_logs_added,
        'errors': errors,
        'message': message,
        'finished_at': finished_at,
        'data': {
            'game_logs': metadata['game_logs'],
            'latest_game_date': _iso(metadata['latest_game_date']),
            'latest_workload_date': _iso(metadata['latest_workload_date']),
            'latest_fatigue_calculated_at': _iso(metadata['latest_fatigue_calculated_at']),
        },
        'availability_reference_date': _iso(availability_reference_date),
        'slate_coverage': slate_coverage_payload,
        'freshness': determine_freshness_state(
            metadata,
            status=status,
            last_successful_sync=last_successful_sync,
            reference_date=reference_date,
            slate_coverage_payload=slate_coverage_payload,
        ),
        'sync': sync_block,
        'active_writer': _sync_run_summary(active_writer),
        'last_successful_sync_run': last_successful_sync_run,
    }
