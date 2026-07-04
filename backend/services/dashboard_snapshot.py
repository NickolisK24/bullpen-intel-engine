import json
import logging
from datetime import timedelta
from time import perf_counter
from collections.abc import Mapping

from sqlalchemy.exc import SQLAlchemyError

from models.dashboard_snapshot import DashboardSnapshot
from models.sync_run import SyncRun
from services import slate_coverage
from services import sync_metadata
from services.availability_reference_date import (
    parse_reference_date,
    product_current_date,
)
from utils.db import db
from utils.time import utc_now_naive


logger = logging.getLogger(__name__)

SNAPSHOT_TYPE_BULLPEN_DASHBOARD = 'bullpen_dashboard'
SNAPSHOT_STATUS_PENDING = 'pending'
SNAPSHOT_STATUS_READY = 'ready'
SNAPSHOT_STATUS_FAILED = 'failed'
DASHBOARD_PAYLOAD_VERSION = 1
SNAPSHOT_SOURCE_BUILDER_V2 = 'snapshot_builder_v2'
DASHBOARD_SNAPSHOT_SLATE_COVERAGE_MISSING = 'dashboard_snapshot_slate_coverage_missing'
DASHBOARD_SNAPSHOT_SLATE_COVERAGE_INCOMPLETE = 'dashboard_snapshot_slate_coverage_incomplete'
_PUBLISH_WITHHELD_REASONS = {
    DASHBOARD_SNAPSHOT_SLATE_COVERAGE_MISSING,
    DASHBOARD_SNAPSHOT_SLATE_COVERAGE_INCOMPLETE,
}


def _elapsed_ms(started):
    return round((perf_counter() - started) * 1000, 2)


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


def _payload_slate_coverage(payload):
    freshness = _payload_freshness(payload)
    coverage = freshness.get('slate_coverage')
    return coverage if isinstance(coverage, Mapping) else {}


def _payload_slate_coverage_unavailable_reason(payload):
    coverage = _payload_slate_coverage(payload)
    if not coverage:
        return DASHBOARD_SNAPSHOT_SLATE_COVERAGE_MISSING
    data_through = _data_through_from_payload(payload)
    coverage_date = parse_reference_date(coverage.get('slate_date'))
    if data_through is not None and coverage_date != data_through:
        return DASHBOARD_SNAPSHOT_SLATE_COVERAGE_INCOMPLETE
    if coverage.get('validations_passed') is not True:
        return DASHBOARD_SNAPSHOT_SLATE_COVERAGE_INCOMPLETE
    if coverage.get('complete_enough_to_publish') is not True:
        return DASHBOARD_SNAPSHOT_SLATE_COVERAGE_INCOMPLETE
    return None


def _coverage_matches_payload_data_through(payload, coverage):
    if not isinstance(coverage, Mapping):
        return False
    data_through = _data_through_from_payload(payload)
    if data_through is None:
        return True
    return parse_reference_date(coverage.get('slate_date')) == data_through


def _compute_payload_slate_coverage(payload):
    data_through = _data_through_from_payload(payload)
    if data_through is None:
        return slate_coverage.unknown_slate_coverage(None)

    freshness = _payload_freshness(payload)
    try:
        return slate_coverage.compute_slate_coverage(
            data_through,
            sync_status=freshness.get('sync_status'),
        )
    except Exception as exc:  # noqa: BLE001 - snapshot coverage must fail closed
        logger.warning(
            'Could not compute dashboard snapshot slate coverage for %s: %s',
            data_through,
            exc,
        )
        return slate_coverage.unknown_slate_coverage(data_through)


def _payload_with_slate_coverage(payload):
    if not isinstance(payload, Mapping):
        return payload

    result = dict(payload)
    freshness = dict(_payload_freshness(result))
    coverage = freshness.get('slate_coverage')
    if not _coverage_matches_payload_data_through(result, coverage):
        coverage = _compute_payload_slate_coverage(result)

    result['freshness'] = slate_coverage.append_slate_coverage_to_freshness(
        freshness,
        coverage,
    )
    return result


def _latest_successful_sync_run_id():
    try:
        run = sync_metadata.latest_successful_sync_run()
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.warning(
            'Could not resolve latest successful sync run for dashboard snapshot publish: %s',
            exc,
        )
        return None
    return run.id if run is not None else None


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
        if snapshot.error_message in _PUBLISH_WITHHELD_REASONS:
            return snapshot.error_message
        return 'dashboard_snapshot_not_ready'
    if not getattr(snapshot, 'is_published', False):
        return 'dashboard_snapshot_not_published'
    if not payload_version_valid(snapshot):
        return 'dashboard_snapshot_version_mismatch'
    if not isinstance(snapshot.payload, Mapping):
        return 'dashboard_snapshot_payload_invalid'
    coverage_reason = _payload_slate_coverage_unavailable_reason(snapshot.payload)
    if coverage_reason is not None:
        return coverage_reason

    payload_freshness = _payload_freshness(snapshot.payload)
    data_age_days = (
        (product_current_date() - snapshot.data_through).days
        if snapshot.data_through is not None
        else None
    )
    degradation = sync_metadata.build_degradation_block(data_age_days)
    if degradation.get('fail_closed'):
        return 'dashboard_snapshot_freshness_fail_closed'

    if snapshot.data_through != _data_through_from_payload(snapshot.payload):
        return 'dashboard_snapshot_data_through_mismatch'
    if snapshot.availability_reference_date != _availability_reference_date_from_payload(snapshot.payload):
        return 'dashboard_snapshot_availability_reference_mismatch'

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
    publish=True,
    commit=True,
):
    serialize_started = perf_counter()
    logger.info(
        'Dashboard snapshot JSON serialization starting source=%s publish=%s sync_run_id=%s.',
        source,
        publish,
        sync_run_id,
    )
    stored_payload = _json_payload(_payload_with_slate_coverage(payload))
    logger.info(
        'Dashboard snapshot JSON serialization completed in %.2f ms source=%s.',
        _elapsed_ms(serialize_started),
        source,
    )

    write_started = perf_counter()
    logger.info(
        'Dashboard snapshot DB write starting source=%s publish=%s sync_run_id=%s payload_keys=%s.',
        source,
        publish,
        sync_run_id,
        len(stored_payload) if isinstance(stored_payload, Mapping) else None,
    )
    snapshot = DashboardSnapshot(
        snapshot_type=snapshot_type,
        sync_run_id=sync_run_id,
        status=SNAPSHOT_STATUS_PENDING,
        is_published=False,
        payload=stored_payload,
        payload_version=DASHBOARD_PAYLOAD_VERSION,
        data_through=_data_through_from_payload(stored_payload),
        availability_reference_date=_availability_reference_date_from_payload(stored_payload),
        snapshot_generated_at=utc_now_naive(),
        source=source or 'sync',
    )
    db.session.add(snapshot)
    db.session.flush()
    if publish:
        publish_dashboard_snapshot(snapshot, commit=commit)
    elif commit:
        db.session.commit()
    logger.info(
        'Dashboard snapshot DB write completed snapshot_id=%s status=%s published=%s in %.2f ms.',
        snapshot.id,
        snapshot.status,
        bool(snapshot.is_published),
        _elapsed_ms(write_started),
    )
    return snapshot


def publish_dashboard_snapshot(snapshot, *, commit=True):
    if snapshot is None:
        return None
    if snapshot.id is None:
        db.session.flush()
    if snapshot.sync_run_id is None:
        raise ValueError('Published dashboard snapshots require sync_run_id provenance.')
    coverage_reason = _payload_slate_coverage_unavailable_reason(snapshot.payload)
    if coverage_reason is not None:
        snapshot.status = SNAPSHOT_STATUS_PENDING
        snapshot.is_published = False
        snapshot.error_message = coverage_reason
        db.session.add(snapshot)
        if commit:
            db.session.commit()
        else:
            db.session.flush()
        return snapshot

    now = utc_now_naive()
    prior_published_ids = [
        row.id
        for row in (
            DashboardSnapshot.query
            .with_entities(DashboardSnapshot.id)
            .filter(
                DashboardSnapshot.snapshot_type == snapshot.snapshot_type,
                DashboardSnapshot.is_published == True,
                DashboardSnapshot.id != snapshot.id,
            )
            .all()
        )
    ]
    (
        DashboardSnapshot.query
        .filter(
            DashboardSnapshot.snapshot_type == snapshot.snapshot_type,
            DashboardSnapshot.is_published == True,
            DashboardSnapshot.id != snapshot.id,
        )
        .update({DashboardSnapshot.is_published: False}, synchronize_session=False)
    )
    snapshot.status = SNAPSHOT_STATUS_READY
    snapshot.is_published = True
    snapshot.published_at = now
    db.session.add(snapshot)
    if prior_published_ids:
        (
            SyncRun.query
            .filter(SyncRun.published_dashboard_snapshot_id.in_(prior_published_ids))
            .update(
                {SyncRun.published_dashboard_snapshot_id: snapshot.id},
                synchronize_session=False,
            )
        )
    (
        SyncRun.query
        .filter(SyncRun.id == snapshot.sync_run_id)
        .update(
            {
                SyncRun.stage: sync_metadata.STAGE_PUBLISHED,
                SyncRun.published_dashboard_snapshot_id: snapshot.id,
            },
            synchronize_session=False,
        )
    )
    if commit:
        db.session.commit()
    else:
        db.session.flush()
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
        is_published=False,
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


def build_dashboard_snapshot(
    payload_builder,
    *,
    sync_run_id=None,
    source='sync',
    publish=True,
    commit=True,
    raise_errors=False,
):
    try:
        payload_started = perf_counter()
        logger.info(
            'Dashboard snapshot payload assembly starting source=%s publish=%s sync_run_id=%s.',
            source,
            publish,
            sync_run_id,
        )
        payload = payload_builder()
        logger.info(
            'Dashboard snapshot payload assembly completed in %.2f ms source=%s payload_keys=%s.',
            _elapsed_ms(payload_started),
            source,
            len(payload) if isinstance(payload, Mapping) else None,
        )
        return store_dashboard_snapshot(
            payload,
            sync_run_id=sync_run_id,
            source=source,
            publish=publish,
            commit=commit,
        )
    except Exception as exc:
        db.session.rollback()
        if raise_errors:
            raise
        logger.warning('Dashboard snapshot build failed: %s', exc)
        return mark_dashboard_snapshot_failed(
            exc,
            sync_run_id=sync_run_id,
            source=source,
        )


def build_bullpen_dashboard_snapshot(
    *,
    sync_run_id=None,
    source='sync',
    publish=True,
    commit=True,
    raise_errors=False,
):
    from api.bullpen import build_bullpen_dashboard_payload

    resolved_sync_run_id = sync_run_id
    if publish and resolved_sync_run_id is None:
        resolved_sync_run_id = _latest_successful_sync_run_id()

    def payload_builder():
        try:
            payload = build_bullpen_dashboard_payload(use_published_freshness=False)
        except TypeError as exc:
            if 'use_published_freshness' not in str(exc):
                raise
            payload = build_bullpen_dashboard_payload()
        if publish and resolved_sync_run_id is None:
            raise RuntimeError(
                'Dashboard snapshot publish requires sync_run_id provenance.'
            )
        return payload

    return build_dashboard_snapshot(
        payload_builder,
        sync_run_id=resolved_sync_run_id,
        source=source,
        publish=publish,
        commit=commit,
        raise_errors=raise_errors,
    )


def _snapshot_build_result(snapshot, *, duration_ms, source):
    reason = snapshot_unavailable_reason(snapshot)
    payload = snapshot.payload if snapshot is not None else None
    coverage = _payload_slate_coverage(payload)
    if snapshot is None:
        status = 'failed'
    elif snapshot.status == SNAPSHOT_STATUS_FAILED:
        status = 'failed'
    elif snapshot.status == SNAPSHOT_STATUS_PENDING and not snapshot.is_published:
        status = 'pending'
        reason = (
            snapshot.error_message
            if snapshot.error_message in _PUBLISH_WITHHELD_REASONS
            else 'dashboard_snapshot_pending_not_published'
        )
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
        'is_published': (
            bool(snapshot.is_published)
            if snapshot is not None
            else False
        ),
        'error_message': snapshot.error_message if snapshot is not None else None,
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
        'payload_has_slate_coverage': bool(coverage),
        'slate_coverage': dict(coverage) if coverage else None,
        'source': source,
        'duration_ms': duration_ms,
    }


def snapshot_diagnostics(snapshot):
    coverage = _payload_slate_coverage(snapshot.payload if snapshot is not None else None)
    return {
        'reason': snapshot_unavailable_reason(snapshot),
        'snapshot_id': snapshot.id if snapshot is not None else None,
        'snapshot_status': snapshot.status if snapshot is not None else None,
        'is_published': (
            bool(snapshot.is_published)
            if snapshot is not None
            else False
        ),
        'error_message': snapshot.error_message if snapshot is not None else None,
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
        'payload_has_slate_coverage': bool(coverage),
        'slate_coverage': dict(coverage) if coverage else None,
    }


def build_bullpen_dashboard_snapshot_v2(
    *,
    source=SNAPSHOT_SOURCE_BUILDER_V2,
    publish=False,
    sync_run_id=None,
):
    started = perf_counter()
    logger.info(
        'Dashboard snapshot builder v2 starting source=%s publish=%s sync_run_id=%s.',
        source,
        publish,
        sync_run_id,
    )
    snapshot = build_bullpen_dashboard_snapshot(
        source=source,
        publish=publish,
        sync_run_id=sync_run_id,
    )
    duration_ms = _elapsed_ms(started)
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
                is_published=True,
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


def get_latest_published_dashboard_snapshot_before(
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
                is_published=True,
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
        logger.warning('Could not read published prior dashboard snapshot: %s', exc)
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
