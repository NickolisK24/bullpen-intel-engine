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

WHAT_CHANGED_KEYS = (
    'state',
    'reason_codes',
    'limitations',
    'comparison_available',
    'baseline_date',
    'current_date',
    'data_through',
    'prior_data_through',
    'item_count',
    'items_count',
    'change_count',
    'max_items',
    'omitted_count',
)

WHAT_CHANGED_COMPARISON_KEYS = (
    'state',
    'reason_codes',
    'limitations',
    'comparison_available',
    'baseline_date',
    'current_date',
    'data_through',
    'prior_data_through',
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
        'snapshot_adjacency_summary': True,
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
        'served_freshness': _json_safe(board_freshness.board_freshness_block()),
        'latest_snapshot': _snapshot_entry(latest_snapshot),
        'latest_valid_snapshot_id': latest_valid.id if latest_valid is not None else None,
        'recent_snapshots': [_snapshot_entry(row) for row in recent_snapshots],
        'snapshot_adjacency_summary': _snapshot_adjacency_summary(recent_snapshots),
        'diagnostics': _json_safe(snapshot_diagnostics(latest_snapshot)),
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
    embedded_what_changed = _embedded_what_changed(payload)
    adjacent_baseline = _adjacent_published_baseline(row)
    baseline_adjacency = _baseline_adjacency(row, adjacent_baseline)
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
        'payload_freshness': _json_safe(payload.get('freshness')) if payload else None,
        'embedded_what_changed': embedded_what_changed,
        'baseline_adjacency': baseline_adjacency,
        'comparison_contract_check': _comparison_contract_check(
            row,
            embedded_what_changed,
            baseline_adjacency,
            adjacent_baseline,
        ),
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
    extracted = _controlled_extract(value, WHAT_CHANGED_KEYS)
    comparison = value.get('comparison')
    if isinstance(comparison, dict):
        extracted['comparison'] = _controlled_extract(
            comparison,
            WHAT_CHANGED_COMPARISON_KEYS,
        )
    return extracted


def _controlled_extract(value: dict, keys: tuple[str, ...]) -> dict:
    extracted = {}
    for key in keys:
        if key in value:
            extracted[key] = _json_safe(value.get(key))
    return extracted


def _adjacent_published_baseline(row: DashboardSnapshot) -> DashboardSnapshot | None:
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
        return None
    return prior_snapshot


def _baseline_adjacency(
    row: DashboardSnapshot,
    prior_snapshot: DashboardSnapshot | None = None,
) -> dict:
    prior_data_through = (
        row.data_through - timedelta(days=1)
        if row.data_through is not None
        else None
    )
    if prior_snapshot is None:
        prior_snapshot = _adjacent_published_baseline(row)
    return {
        'prior_data_through': _iso(prior_data_through),
        'prior_published_snapshot_id': prior_snapshot.id if prior_snapshot else None,
        'adjacent_published_baseline_present': prior_snapshot is not None,
    }


def _comparison_contract_check(
    row: DashboardSnapshot,
    embedded_what_changed: dict | None,
    baseline_adjacency: dict,
    adjacent_baseline: DashboardSnapshot | None,
) -> dict:
    prior_required_data_through = (
        row.data_through - timedelta(days=1)
        if row.data_through is not None
        else None
    )
    adjacent_trusted_baseline_present = (
        adjacent_baseline is not None
        and snapshot_unavailable_reason(adjacent_baseline) is None
    )
    stored_comparison_available = _stored_comparison_available(embedded_what_changed)
    stored_current_date = _stored_comparison_date(
        embedded_what_changed,
        'current_date',
        fallback_key='data_through',
    )
    stored_baseline_date = _stored_comparison_date(
        embedded_what_changed,
        'baseline_date',
        fallback_key='prior_data_through',
    )
    stored_metadata_present = _stored_comparison_metadata_present(embedded_what_changed)
    expected_current_date = _iso(row.data_through)
    expected_baseline_date = _iso(prior_required_data_through)
    if not stored_metadata_present:
        stored_matches_contract = None
    else:
        stored_matches_contract = (
            stored_current_date == expected_current_date
            and stored_baseline_date == expected_baseline_date
        )

    notes = []
    if not stored_metadata_present:
        notes.append('stored_comparison_metadata_absent')
    elif stored_matches_contract is False:
        notes.append('stored_comparison_non_adjacent')
    if not baseline_adjacency.get('adjacent_published_baseline_present'):
        notes.append('adjacent_baseline_missing')
    elif not adjacent_trusted_baseline_present:
        notes.append('adjacent_baseline_untrusted')

    return {
        'prior_required_data_through': _iso(prior_required_data_through),
        'adjacent_published_baseline_present': bool(
            baseline_adjacency.get('adjacent_published_baseline_present')
        ),
        'adjacent_trusted_baseline_present': adjacent_trusted_baseline_present,
        'stored_comparison_available': stored_comparison_available,
        'stored_comparison_current_date': stored_current_date,
        'stored_comparison_baseline_date': stored_baseline_date,
        'stored_comparison_matches_adjacent_contract': stored_matches_contract,
        'notes': notes,
    }


def _stored_comparison_metadata_present(embedded_what_changed: dict | None) -> bool:
    if not isinstance(embedded_what_changed, dict):
        return False
    metadata_keys = (
        'comparison_available',
        'baseline_date',
        'current_date',
        'data_through',
        'prior_data_through',
    )
    comparison = embedded_what_changed.get('comparison')
    for key in metadata_keys:
        if key in embedded_what_changed:
            return True
        if isinstance(comparison, dict) and key in comparison:
            return True
    return False


def _stored_comparison_available(embedded_what_changed: dict | None) -> bool | None:
    value = _stored_comparison_value(embedded_what_changed, 'comparison_available')
    return value if isinstance(value, bool) else None


def _stored_comparison_date(
    embedded_what_changed: dict | None,
    key: str,
    *,
    fallback_key: str,
) -> str | None:
    value = _stored_comparison_value(embedded_what_changed, key)
    if value is None:
        value = _stored_comparison_value(embedded_what_changed, fallback_key)
    return _date_text(value)


def _stored_comparison_value(embedded_what_changed: dict | None, key: str):
    if not isinstance(embedded_what_changed, dict):
        return None
    comparison = embedded_what_changed.get('comparison')
    if isinstance(comparison, dict) and key in comparison:
        return comparison.get(key)
    if key in embedded_what_changed:
        return embedded_what_changed.get(key)
    return None


def _date_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _snapshot_adjacency_summary(rows: list[DashboardSnapshot]) -> dict:
    published_rows = [row for row in rows if bool(row.is_published)]
    trusted_published_rows = [
        row for row in published_rows
        if snapshot_unavailable_reason(row) is None
    ]
    published_by_date = _latest_published_rows_by_date(published_rows)
    data_through_dates = sorted(published_by_date)
    adjacent_pairs = []
    missing_prior_dates = []
    trusted_pair_count = 0
    for current_data_through in data_through_dates:
        prior_data_through = current_data_through - timedelta(days=1)
        current_snapshot = published_by_date.get(current_data_through)
        prior_snapshot = published_by_date.get(prior_data_through)
        if prior_snapshot is None:
            missing_prior_dates.append(current_data_through.isoformat())
            continue
        adjacent_pairs.append({
            'current_data_through': current_data_through.isoformat(),
            'prior_data_through': prior_data_through.isoformat(),
            'current_snapshot_id': current_snapshot.id,
            'prior_snapshot_id': prior_snapshot.id,
        })
        if (
            snapshot_unavailable_reason(current_snapshot) is None
            and snapshot_unavailable_reason(prior_snapshot) is None
        ):
            trusted_pair_count += 1

    return {
        'published_snapshot_count': len(published_rows),
        'trusted_published_snapshot_count': len(trusted_published_rows),
        'data_through_dates': [
            data_through.isoformat()
            for data_through in data_through_dates
        ],
        'adjacent_published_pairs': adjacent_pairs,
        'adjacent_published_pair_count': len(adjacent_pairs),
        'missing_prior_dates': missing_prior_dates,
        'trusted_pair_count': trusted_pair_count,
    }


def _latest_published_rows_by_date(rows: list[DashboardSnapshot]) -> dict:
    by_date = {}
    for row in rows:
        if row.data_through is None:
            continue
        current = by_date.get(row.data_through)
        if current is None or _row_order_key(row) > _row_order_key(current):
            by_date[row.data_through] = row
    return by_date


def _row_order_key(row: DashboardSnapshot):
    return (
        row.snapshot_generated_at or datetime.min,
        row.id or 0,
    )


def _watermark() -> dict:
    return {
        'internal_only': True,
        'admin_gated': True,
        'phase0b_public_evidence_gate': 'closed',
        'public_evidence_exposure': False,
        'quote_only_rendered_claims': True,
    }


def _json_safe(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            str(key): _json_safe(nested)
            for key, nested in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(nested) for nested in value]
    return f'non_json_value:{type(value).__name__}'


def _iso(value):
    return value.isoformat() if value is not None else None
