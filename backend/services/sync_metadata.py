from datetime import timedelta
import logging

from flask import current_app, has_app_context
from sqlalchemy.exc import SQLAlchemyError

from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.sync_run import SyncRun
from services.availability import ACTIVE_WINDOW_DAYS
from services.availability_reference_date import (
    product_availability_reference_date_from_metadata,
    product_current_date,
)
from utils.db import db
from utils.time import utc_now_naive


STATUS_RUNNING = 'running'
STATUS_SUCCESS = 'success'
STATUS_PARTIAL = 'partial'
STATUS_FAILED = 'failed'
STATUS_NEVER = 'never'
STATUS_METADATA_UNAVAILABLE = 'metadata_unavailable'

# A run counts as a "successful" data write for freshness purposes when it
# either fully succeeded or completed with partial dead-lettered records — in
# both cases the domains it touched were refreshed.
SUCCESSFUL_STATUSES = (STATUS_SUCCESS, STATUS_PARTIAL)

SOURCE_MANUAL = 'manual'
SOURCE_SCHEDULED = 'scheduled'
SOURCE_GITHUB_ACTIONS = 'github_actions'

JOB_DAILY_SYNC = 'daily_sync'

logger = logging.getLogger(__name__)


def _now():
    return utc_now_naive()


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
    return value.isoformat() if value else None


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
                source=source,
                created_at=started_at or completed_at,
            )
            db.session.add(run)

        metadata = collect_data_metadata()
        run.completed_at = completed_at
        run.status = status
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
        db.session.commit()
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
        return {
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
        }

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

    return {
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
    }


def build_sync_status_payload(legacy_status=None, reference_date=None):
    # ``legacy_status`` is accepted only for older callers. It is intentionally
    # ignored so sync_status.json can never become the reporting authority.
    metadata = collect_data_metadata()
    try:
        latest_run = latest_sync_run()
        successful_run = latest_successful_sync_run()
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.warning('Could not read durable sync metadata: %s', exc)
        latest_run = None
        successful_run = None

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

    availability_reference_date = (
        product_availability_reference_date_from_metadata(metadata)
        if last_successful_sync
        else None
    )

    return {
        'status': status,
        'sync_authority': 'sync_runs',
        # Which durable source actually answered: 'sync_runs' or 'none'.
        'metadata_source': metadata_source,
        'last_sync': last_sync,
        'last_successful_sync': last_successful_sync,
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
        'freshness': determine_freshness_state(
            metadata,
            status=status,
            last_successful_sync=last_successful_sync,
            reference_date=reference_date,
        ),
        'sync': sync_block,
        'last_successful_sync_run': last_successful_sync_run,
    }
