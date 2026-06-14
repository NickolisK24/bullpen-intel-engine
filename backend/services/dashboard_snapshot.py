import json
import logging
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


def snapshot_current_enough(snapshot, sync_status=None):
    if snapshot is None or snapshot.status != SNAPSHOT_STATUS_READY:
        return False
    if not payload_version_valid(snapshot):
        return False
    if not isinstance(snapshot.payload, Mapping):
        return False

    try:
        sync_status = sync_status or sync_metadata.build_sync_status_payload()
    except Exception as exc:
        db.session.rollback()
        logger.warning('Could not validate dashboard snapshot freshness: %s', exc)
        return False

    current_freshness = _current_freshness(sync_status)
    degradation = current_freshness.get('degradation') or {}
    if degradation.get('fail_closed'):
        return False

    if snapshot.data_through != _current_data_through(sync_status):
        return False

    availability_reference_date = product_availability_reference_date_from_sync_status(
        sync_status
    )
    if snapshot.availability_reference_date != availability_reference_date:
        return False

    payload_freshness = _payload_freshness(snapshot.payload)
    if payload_freshness.get('reference_date') != current_freshness.get('reference_date'):
        return False
    if payload_freshness.get('sync_status') != sync_status.get('status'):
        return False
    if payload_freshness.get('last_successful_sync') != sync_status.get('last_successful_sync'):
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


def get_latest_valid_dashboard_snapshot(snapshot_type=SNAPSHOT_TYPE_BULLPEN_DASHBOARD):
    snapshot = get_latest_dashboard_snapshot(snapshot_type=snapshot_type)
    if snapshot_current_enough(snapshot):
        return snapshot
    return None
