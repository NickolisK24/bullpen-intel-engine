"""Internal trusted snapshot audit payloads.

Read-only and admin-route only. Quotes stored dashboard snapshot trust state
for operator review, composes no baseball conclusions, and triggers no builds.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import desc

from models.dashboard_snapshot import DashboardSnapshot
from models.sync_run import SyncRun
from services import board_freshness
from services.dashboard_snapshot import (
    DASHBOARD_PAYLOAD_VERSION,
    DASHBOARD_SNAPSHOT_SLATE_COVERAGE_INCOMPLETE,
    DASHBOARD_SNAPSHOT_SLATE_COVERAGE_MISSING,
    SNAPSHOT_SOURCE_BUILDER_V2,
    SNAPSHOT_STATUS_FAILED,
    SNAPSHOT_STATUS_PENDING,
    SNAPSHOT_STATUS_READY,
    SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
    get_latest_dashboard_snapshot,
    get_latest_published_dashboard_snapshot_before,
    get_latest_valid_dashboard_snapshot,
    get_recent_dashboard_snapshots_before,
    payload_version_valid,
    snapshot_current_enough,
    snapshot_diagnostics,
    snapshot_unavailable_reason,
)


CAPABILITY = 'phase0h_internal_snapshot_audit'
ROUTE_STATUS = 'internal_admin_only'
DEFAULT_WINDOW_DAYS = 7
MAX_WINDOW_DAYS = 14

SNAPSHOT_CONSTANTS = (
    SNAPSHOT_SOURCE_BUILDER_V2,
    SNAPSHOT_STATUS_FAILED,
    SNAPSHOT_STATUS_PENDING,
    SNAPSHOT_STATUS_READY,
    DASHBOARD_SNAPSHOT_SLATE_COVERAGE_INCOMPLETE,
    DASHBOARD_SNAPSHOT_SLATE_COVERAGE_MISSING,
)


class SnapshotAuditRequestError(ValueError):
    pass


def build_internal_snapshot_audit_payload(
    *,
    product_date=None,
    window_days=None,
) -> dict:
    ref = _parse_product_date(product_date)
    normalized_window = _parse_window_days(window_days)
    latest_snapshot = _latest_snapshot_row(ref)
    anchor_date = ref or (latest_snapshot.data_through if latest_snapshot is not None else None)
    recent_snapshots = _recent_snapshot_rows(anchor_date, normalized_window)
    latest_valid = get_latest_valid_dashboard_snapshot()

    sections_present = {
        'served_freshness': True,
        'latest_snapshot': latest_snapshot is not None,
        'latest_valid_snapshot': latest_valid is not None,
        'recent_snapshots': bool(recent_snapshots),
        'diagnostics': True,
    }

    return {
        'capability': CAPABILITY,
        'route_status': ROUTE_STATUS,
        'internal_only_watermark': _watermark(),
        'request': {
            'date': ref.isoformat() if ref else None,
            'window_days': normalized_window,
        },
        'served_freshness': board_freshness.board_freshness_block(),
        'latest_snapshot': _snapshot_entry(latest_snapshot),
        'latest_valid_snapshot_id': latest_valid.id if latest_valid is not None else None,
        'recent_snapshots': [_snapshot_entry(row) for row in recent_snapshots],
        'diagnostics': snapshot_diagnostics(latest_snapshot),
        'sections_present': sections_present,
        'missing_sections': [
            key for key, present in sections_present.items() if not present
        ],
    }


def error_payload(reason: str, *, status: int) -> dict:
    return {
        'capability': CAPABILITY,
        'route_status': ROUTE_STATUS,
        'internal_only_watermark': _watermark(),
        'status': 'error',
        'error': reason,
        'http_status': status,
    }


def _parse_product_date(value) -> date | None:
    if value is None or str(value).strip() == '':
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise SnapshotAuditRequestError('date_invalid') from exc


def _parse_window_days(value) -> int:
    if value is None or str(value).strip() == '':
        return DEFAULT_WINDOW_DAYS
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise SnapshotAuditRequestError('window_invalid') from exc
    if parsed <= 0:
        raise SnapshotAuditRequestError('window_invalid')
    return min(parsed, MAX_WINDOW_DAYS)


def _latest_snapshot_row(ref: date | None) -> DashboardSnapshot | None:
    if ref is None:
        row = (
            DashboardSnapshot.query
            .filter(DashboardSnapshot.snapshot_type == SNAPSHOT_TYPE_BULLPEN_DASHBOARD)
            .order_by(
                desc(DashboardSnapshot.snapshot_generated_at),
                desc(DashboardSnapshot.id),
            )
            .first()
        )
        if row is not None:
            return row
        return get_latest_dashboard_snapshot()

    return (
        DashboardSnapshot.query
        .filter(DashboardSnapshot.snapshot_type == SNAPSHOT_TYPE_BULLPEN_DASHBOARD)
        .filter(DashboardSnapshot.data_through <= ref)
        .order_by(
            desc(DashboardSnapshot.data_through),
            desc(DashboardSnapshot.snapshot_generated_at),
            desc(DashboardSnapshot.id),
        )
        .first()
    )


def _recent_snapshot_rows(anchor_date: date | None, window_days: int) -> list[DashboardSnapshot]:
    if anchor_date is None:
        return []

    since = anchor_date - timedelta(days=window_days)
    helper_rows = get_recent_dashboard_snapshots_before(
        anchor_date + timedelta(days=1),
        lookback_days=window_days + 1,
    )
    rows = (
        DashboardSnapshot.query
        .filter(DashboardSnapshot.snapshot_type == SNAPSHOT_TYPE_BULLPEN_DASHBOARD)
        .filter(DashboardSnapshot.data_through <= anchor_date)
        .filter(DashboardSnapshot.data_through >= since)
        .order_by(
            desc(DashboardSnapshot.data_through),
            desc(DashboardSnapshot.snapshot_generated_at),
            desc(DashboardSnapshot.id),
        )
        .all()
    )
    by_id = {row.id: row for row in helper_rows}
    for row in rows:
        by_id[row.id] = row
    return sorted(
        by_id.values(),
        key=lambda row: (
            row.data_through or date.min,
            row.snapshot_generated_at or datetime.min,
            row.id or 0,
        ),
        reverse=True,
    )


def _snapshot_entry(row: DashboardSnapshot | None) -> dict | None:
    if row is None:
        return None
    sync_run = _sync_run(row.sync_run_id)
    payload = row.payload if isinstance(row.payload, dict) else {}
    return {
        'id': row.id,
        'snapshot_type': row.snapshot_type,
        'status': row.status,
        'is_published': bool(row.is_published),
        'published_at': _iso(row.published_at),
        'data_through': _iso(row.data_through),
        'availability_reference_date': _iso(row.availability_reference_date),
        'payload_version': row.payload_version,
        'source': row.source,
        'error_message': row.error_message,
        'snapshot_generated_at': _iso(row.snapshot_generated_at),
        'sync_run_id': row.sync_run_id,
        'sync_run': _sync_run_entry(sync_run),
        'trust': {
            'unavailable_reason': snapshot_unavailable_reason(row),
            'current_enough': snapshot_current_enough(row),
            'payload_version_valid': payload_version_valid(row),
        },
        'payload_freshness': payload.get('freshness') if payload else None,
        'embedded_what_changed': _embedded_what_changed(payload),
        'baseline_adjacency': _baseline_adjacency(row),
    }


def _sync_run(sync_run_id: int | None) -> SyncRun | None:
    if sync_run_id is None:
        return None
    return SyncRun.query.filter(SyncRun.id == sync_run_id).one_or_none()


def _sync_run_entry(row: SyncRun | None) -> dict | None:
    if row is None:
        return None
    return {
        'id': row.id,
        'job_name': row.job_name,
        'status': row.status,
        'stage': row.stage,
        'failed_stage': row.failed_stage,
        'published_dashboard_snapshot_id': row.published_dashboard_snapshot_id,
    }


def _embedded_what_changed(payload: dict) -> dict | None:
    value = payload.get('what_changed_since_yesterday')
    if not isinstance(value, dict):
        return None
    return {
        'state': value.get('state'),
        'reason_codes': value.get('reason_codes'),
        'limitations': value.get('limitations'),
    }


def _baseline_adjacency(row: DashboardSnapshot) -> dict:
    prior_data_through = (
        row.data_through - timedelta(days=1)
        if row.data_through is not None
        else None
    )
    prior_snapshot = get_latest_published_dashboard_snapshot_before(row.data_through)
    if (
        prior_snapshot is not None
        and prior_snapshot.data_through != prior_data_through
    ):
        prior_snapshot = None
    return {
        'prior_data_through': _iso(prior_data_through),
        'prior_published_snapshot_id': prior_snapshot.id if prior_snapshot else None,
        'adjacent_published_baseline_present': prior_snapshot is not None,
    }


def _watermark() -> dict:
    return {
        'internal_only': True,
        'admin_gated': True,
        'phase0b_public_evidence_gate': 'closed',
        'public_evidence_exposure': False,
        'quote_only_rendered_claims': True,
    }


def _iso(value):
    return value.isoformat() if value is not None else None
