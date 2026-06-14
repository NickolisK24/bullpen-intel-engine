import json
import logging
from datetime import timedelta
from time import perf_counter
from collections.abc import Mapping

from sqlalchemy.exc import SQLAlchemyError

from models.dashboard_snapshot import DashboardSnapshot
from services import sync_metadata
from services.availability_reference_date import (
    parse_reference_date,
    product_availability_reference_date_from_sync_status,
)
from utils.db import db
from utils.time import utc_now_naive


logger = logging.getLogger(__name__)

SNAPSHOT_TYPE_BULLPEN_DASHBOARD = 'bullpen_dashboard'
SNAPSHOT_STATUS_READY = 'ready'
SNAPSHOT_STATUS_FAILED = 'failed'
DASHBOARD_PAYLOAD_VERSION = 1
SNAPSHOT_SOURCE_BUILDER_V2 = 'snapshot_builder_v2'


def _json_payload(payload):
    return json.loads(json.dumps(payload))


def _payload_freshness(payload):
    if not isinstance(payload, Mapping):
        return {}
    freshness = payload.get('freshness')
    return freshness if isinstance(freshness, Mapping) else {}


def _data_through_from_payload(payload):
    freshness = _payload_freshness(payload)
    return parse_reference_date(
        freshness.get('data_through')
        or freshness.get('latest_workload_date')
    )


def _availability_reference_date_from_payload(payload):
    freshness = _payload_freshness(payload)
    return parse_reference_date(freshness.get('availability_reference_date'))


def _current_data_through(sync_status):
    data = (sync_status or {}).get('data') or {}
    return parse_reference_date(
        data.get('latest_workload_date')
        or data.get('latest_game_date')
    )


def _current_freshness(sync_status):
    freshness = (sync_status or {}).get('freshness') or {}
    return freshness if isinstance(freshness, Mapping) else {}


def payload_version_valid(snapshot):
    return (
        snapshot is not None
        and snapshot.payload_version == DASHBOARD_PAYLOAD_VERSION
        and snapshot.snapshot_type == SNAPSHOT_TYPE_BULLPEN_DASHBOARD
    )


def snapshot_unavailable_reason(snapshot, sync_status=None):
    if snapshot is None:
        return 'dashboard_snapshot_missing'
    if snapshot.status != SNAPSHOT_STATUS_READY:
        return 'dashboard_snapshot_not_ready'
    if not payload_version_valid(snapshot):
        return 'dashboard_snapshot_version_mismatch'
    if not isinstance(snapshot.payload, Mapping):
        return 'dashboard_snapshot_payload_invalid'

    try:
        sync_status = sync_status or sync_metadata.build_sync_status_payload()
    except Exception as exc:
        db.session.rollback()
        logger.warning('Could not validate dashboard snapshot freshness: %s', exc)
        return 'dashboard_snapshot_freshness_validation_unavailable'

    current_freshness = _current_freshness(sync_status)
    degradation = current_freshness.get('degradation') or {}
    if degradation.get('fail_closed'):
        return 'dashboard_snapshot_freshness_fail_closed'

    if snapshot.data_through != _current_data_through(sync_status):
        return 'dashboard_snapshot_data_through_mismatch'

    availability_reference_date = product_availability_reference_date_from_sync_status(
        sync_status
    )
    if snapshot.availability_reference_date != availability_reference_date:
        return 'dashboard_snapshot_availability_reference_mismatch'

    payload_freshness = _payload_freshness(snapshot.payload)
    if payload_freshness.get('reference_date') != current_freshness.get('reference_date'):
        return 'dashboard_snapshot_reference_date_mismatch'
    if payload_freshness.get('sync_status') != sync_status.get('status'):
        return 'dashboard_snapshot_sync_status_mismatch'
    if payload_freshness.get('last_successful_sync') != sync_status.get('last_successful_sync'):
        return 'dashboard_snapshot_last_successful_sync_mismatch'

    return None


def snapshot_current_enough(snapshot, sync_status=None):
    if snapshot_unavailable_reason(snapshot, sync_status=sync_status) is not None:
        return False
    return True


def store_dashboard_snapshot(
    payload,
    *,
    sync_run_id=None,
    source='sync',
    snapshot_type=SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
):
    stored_payload = _json_payload(payload)
    snapshot = DashboardSnapshot(
        snapshot_type=snapshot_type,
        sync_run_id=sync_run_id,
        status=SNAPSHOT_STATUS_READY,
        payload=stored_payload,
        payload_version=DASHBOARD_PAYLOAD_VERSION,
        data_through=_data_through_from_payload(stored_payload),
        availability_reference_date=_availability_reference_date_from_payload(stored_payload),
        snapshot_generated_at=utc_now_naive(),
        source=source or 'sync',
    )
    db.session.add(snapshot)
    db.session.commit()
    return snapshot


def mark_dashboard_snapshot_failed(
    error,
    *,
    sync_run_id=None,
    source='sync',
    snapshot_type=SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
):
    message = str(error or 'Dashboard snapshot build failed.')
    snapshot = DashboardSnapshot(
        snapshot_type=snapshot_type,
        sync_run_id=sync_run_id,
        status=SNAPSHOT_STATUS_FAILED,
        payload=None,
        payload_version=DASHBOARD_PAYLOAD_VERSION,
        snapshot_generated_at=utc_now_naive(),
        source=source or 'sync',
        error_message=message[:4000],
    )
    try:
        db.session.add(snapshot)
        db.session.commit()
        return snapshot
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.warning('Could not record failed dashboard snapshot: %s', exc)
        return None


def build_dashboard_snapshot(payload_builder, *, sync_run_id=None, source='sync'):
    try:
        payload = payload_builder()
        return store_dashboard_snapshot(
            payload,
            sync_run_id=sync_run_id,
            source=source,
        )
    except Exception as exc:
        db.session.rollback()
        logger.warning('Dashboard snapshot build failed: %s', exc)
        return mark_dashboard_snapshot_failed(
            exc,
            sync_run_id=sync_run_id,
            source=source,
        )


def build_bullpen_dashboard_snapshot(*, sync_run_id=None, source='sync'):
    from api.bullpen import build_bullpen_dashboard_payload

    return build_dashboard_snapshot(
        build_bullpen_dashboard_payload,
        sync_run_id=sync_run_id,
        source=source,
    )


def _snapshot_build_result(snapshot, *, duration_ms, source):
    reason = snapshot_unavailable_reason(snapshot)
    if snapshot is None:
        status = 'failed'
    elif snapshot.status == SNAPSHOT_STATUS_FAILED:
        status = 'failed'
    elif reason is None:
        status = 'ready'
    else:
        status = 'stored_invalid'

    return {
        'status': status,
        'reason': reason,
        'snapshot_served_by_dashboard': reason is None,
        'snapshot_id': snapshot.id if snapshot is not None else None,
        'snapshot_status': snapshot.status if snapshot is not None else None,
        'snapshot_type': (
            snapshot.snapshot_type
            if snapshot is not None
            else SNAPSHOT_TYPE_BULLPEN_DASHBOARD
        ),
        'sync_run_id': snapshot.sync_run_id if snapshot is not None else None,
        'payload_version': (
            snapshot.payload_version
            if snapshot is not None
            else DASHBOARD_PAYLOAD_VERSION
        ),
        'data_through': (
            snapshot.data_through.isoformat()
            if snapshot is not None and snapshot.data_through
            else None
        ),
        'availability_reference_date': (
            snapshot.availability_reference_date.isoformat()
            if snapshot is not None and snapshot.availability_reference_date
            else None
        ),
        'snapshot_generated_at': (
            snapshot.snapshot_generated_at.isoformat()
            if snapshot is not None and snapshot.snapshot_generated_at
            else None
        ),
        'source': source,
        'duration_ms': duration_ms,
    }


def build_bullpen_dashboard_snapshot_v2(*, source=SNAPSHOT_SOURCE_BUILDER_V2):
    started = perf_counter()
    logger.info('Dashboard snapshot builder v2 starting.')
    snapshot = build_bullpen_dashboard_snapshot(source=source)
    duration_ms = round((perf_counter() - started) * 1000, 2)
    result = _snapshot_build_result(
        snapshot,
        duration_ms=duration_ms,
        source=source,
    )
    if result['status'] == 'ready':
        logger.info(
            'Dashboard snapshot builder v2 stored ready snapshot id=%s in %.2f ms.',
            result['snapshot_id'],
            duration_ms,
        )
    else:
        logger.warning(
            'Dashboard snapshot builder v2 finished with status=%s reason=%s in %.2f ms.',
            result['status'],
            result['reason'],
            duration_ms,
        )
    return result


def get_latest_dashboard_snapshot(snapshot_type=SNAPSHOT_TYPE_BULLPEN_DASHBOARD):
    try:
        return (
            DashboardSnapshot.query
            .filter_by(
                snapshot_type=snapshot_type,
                status=SNAPSHOT_STATUS_READY,
                payload_version=DASHBOARD_PAYLOAD_VERSION,
            )
            .order_by(
                DashboardSnapshot.snapshot_generated_at.desc(),
                DashboardSnapshot.id.desc(),
            )
            .first()
        )
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.warning('Could not read dashboard snapshot: %s', exc)
        return None


def get_latest_dashboard_snapshot_record(snapshot_type=SNAPSHOT_TYPE_BULLPEN_DASHBOARD):
    try:
        return (
            DashboardSnapshot.query
            .filter_by(snapshot_type=snapshot_type)
            .order_by(
                DashboardSnapshot.snapshot_generated_at.desc(),
                DashboardSnapshot.id.desc(),
            )
            .first()
        )
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.warning('Could not read dashboard snapshot record: %s', exc)
        return None


def get_latest_dashboard_snapshot_before(
    data_through,
    snapshot_type=SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
):
    if data_through is None:
        return None

    try:
        return (
            DashboardSnapshot.query
            .filter_by(
                snapshot_type=snapshot_type,
                status=SNAPSHOT_STATUS_READY,
                payload_version=DASHBOARD_PAYLOAD_VERSION,
            )
            .filter(DashboardSnapshot.data_through < data_through)
            .order_by(
                DashboardSnapshot.data_through.desc(),
                DashboardSnapshot.snapshot_generated_at.desc(),
                DashboardSnapshot.id.desc(),
            )
            .first()
        )
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.warning('Could not read prior dashboard snapshot: %s', exc)
        return None


def get_recent_dashboard_snapshots_before(
    data_through,
    *,
    lookback_days=7,
    snapshot_type=SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
):
    if data_through is None:
        return []

    since = data_through - timedelta(days=lookback_days)
    try:
        return (
            DashboardSnapshot.query
            .filter_by(
                snapshot_type=snapshot_type,
                status=SNAPSHOT_STATUS_READY,
                payload_version=DASHBOARD_PAYLOAD_VERSION,
            )
            .filter(DashboardSnapshot.data_through < data_through)
            .filter(DashboardSnapshot.data_through >= since)
            .order_by(
                DashboardSnapshot.data_through.desc(),
                DashboardSnapshot.snapshot_generated_at.desc(),
                DashboardSnapshot.id.desc(),
            )
            .all()
        )
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.warning('Could not read recent dashboard snapshots: %s', exc)
        return []


def latest_dashboard_snapshot_unavailable_reason(
    snapshot_type=SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
):
    snapshot = get_latest_dashboard_snapshot(snapshot_type=snapshot_type)
    if snapshot is not None:
        return snapshot_unavailable_reason(snapshot)

    latest_record = get_latest_dashboard_snapshot_record(snapshot_type=snapshot_type)
    return snapshot_unavailable_reason(latest_record)


def get_latest_valid_dashboard_snapshot(snapshot_type=SNAPSHOT_TYPE_BULLPEN_DASHBOARD):
    snapshot = get_latest_dashboard_snapshot(snapshot_type=snapshot_type)
    if snapshot_current_enough(snapshot):
        return snapshot
    return None
