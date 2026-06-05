from datetime import date, timedelta
import logging

from sqlalchemy.exc import SQLAlchemyError

from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.sync_run import SyncRun
from services.availability import ACTIVE_WINDOW_DAYS
from utils.db import db
from utils.time import utc_now_naive


STATUS_RUNNING = 'running'
STATUS_SUCCESS = 'success'
STATUS_FAILED = 'failed'
STATUS_NEVER = 'never'
STATUS_METADATA_UNAVAILABLE = 'metadata_unavailable'

SOURCE_MANUAL = 'manual'
SOURCE_SCHEDULED = 'scheduled'
SOURCE_GITHUB_ACTIONS = 'github_actions'

logger = logging.getLogger(__name__)


def _now():
    return utc_now_naive()


def _iso(value):
    return value.isoformat() if value else None


def _normalize_legacy_status(status):
    if status == 'ok':
        return STATUS_SUCCESS
    if status == 'error':
        return STATUS_FAILED
    if status in ('no_games', STATUS_SUCCESS, STATUS_FAILED, STATUS_RUNNING):
        return status
    return status or STATUS_NEVER


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


def start_sync_run(source=SOURCE_MANUAL, started_at=None):
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
    new_logs_added=0,
    pitchers_updated=0,
    errors=0,
    error_message=None,
    source=SOURCE_MANUAL,
    started_at=None,
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
        run.new_logs_added = new_logs_added or 0
        run.pitchers_updated = pitchers_updated or 0
        run.errors = errors or 0
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
    return (
        SyncRun.query
        .filter_by(status=STATUS_SUCCESS)
        .order_by(SyncRun.completed_at.desc(), SyncRun.started_at.desc(), SyncRun.id.desc())
        .first()
    )


def _run_message(run):
    if run is None:
        return ''
    if run.status == STATUS_FAILED:
        return run.error_message or 'Last sync failed.'
    return run.error_message or ''


def _freshness_payload(metadata, status, last_successful_sync, reference_date=None):
    ref = reference_date or date.today()
    latest_game_date = metadata['latest_game_date']
    latest_fatigue = metadata['latest_fatigue_calculated_at']
    limitations = []

    if not metadata['game_logs'] or latest_game_date is None:
        return {
            'is_current': False,
            'label': 'No baseball workload data loaded.',
            'limitations': ['No game logs are available.'],
        }

    cutoff = ref - timedelta(days=ACTIVE_WINDOW_DAYS)
    is_current = latest_game_date >= cutoff
    label = (
        f"Current baseball data through {latest_game_date.isoformat()}."
        if is_current
        else f"Historical baseball data through {latest_game_date.isoformat()}."
    )

    if status == STATUS_METADATA_UNAVAILABLE:
        limitations.append('Sync metadata unavailable; data coverage is based on game logs.')
    if last_successful_sync is None:
        limitations.append('No durable successful sync timestamp is available.')
    if latest_fatigue is None:
        limitations.append('No fatigue calculation timestamp is available.')
    if not is_current:
        limitations.append(f'Latest game date is outside the {ACTIVE_WINDOW_DAYS}-day freshness window.')
    if status == STATUS_FAILED:
        limitations.append('The latest sync attempt failed; data may reflect an earlier successful sync.')

    return {
        'is_current': is_current,
        'label': label,
        'limitations': limitations,
    }


def build_sync_status_payload(legacy_status=None, reference_date=None):
    legacy_status = legacy_status or {}
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
    elif legacy_status.get('last_sync'):
        status = _normalize_legacy_status(legacy_status.get('status'))
        last_sync = legacy_status.get('last_sync')
        finished_at = legacy_status.get('finished_at')
        pitchers_updated = legacy_status.get('pitchers_updated', 0) or 0
        new_logs_added = legacy_status.get('new_logs_added', 0) or 0
        errors = legacy_status.get('errors', 0) or 0
        message = legacy_status.get('message', '') or ''
        sync_block = {
            'id': None,
            'source': 'legacy_status_file',
            'started_at': last_sync,
            'completed_at': finished_at,
            'status': status,
        }
        metadata_source = 'legacy_status_file'
    else:
        status = STATUS_METADATA_UNAVAILABLE if metadata['game_logs'] else STATUS_NEVER
        last_sync = None
        finished_at = None
        pitchers_updated = legacy_status.get('pitchers_updated', 0) or 0
        new_logs_added = legacy_status.get('new_logs_added', 0) or 0
        errors = legacy_status.get('errors', 0) or 0
        message = (
            'Sync metadata unavailable.'
            if status == STATUS_METADATA_UNAVAILABLE
            else legacy_status.get('message', 'No sync has run yet.')
        )
        sync_block = None
        metadata_source = 'none'

    if successful_run:
        last_successful_sync = _iso(successful_run.completed_at or successful_run.started_at)
        last_successful_sync_run = successful_run.to_dict()
    elif status == STATUS_SUCCESS and finished_at:
        last_successful_sync = finished_at
        last_successful_sync_run = sync_block
    elif status == STATUS_SUCCESS:
        last_successful_sync = last_sync
        last_successful_sync_run = sync_block
    else:
        last_successful_sync = None
        last_successful_sync_run = None

    return {
        'status': status,
        # Which store actually answered: durable 'sync_runs', the cache
        # 'legacy_status_file', or 'none'. Durable always wins when present.
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
        'freshness': _freshness_payload(
            metadata,
            status=status,
            last_successful_sync=last_successful_sync,
            reference_date=reference_date,
        ),
        'sync': sync_block,
        'last_successful_sync_run': last_successful_sync_run,
    }
