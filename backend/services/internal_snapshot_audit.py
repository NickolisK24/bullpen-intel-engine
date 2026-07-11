"""Internal trusted snapshot audit payloads.

Read-only and admin-route only. Quotes stored dashboard snapshot trust state
for operator review, composes no baseball conclusions, and triggers no builds.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from time import monotonic

from sqlalchemy import desc, text

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
    payload_version_valid,
    snapshot_current_enough,
    snapshot_unavailable_reason,
)
from utils.db import db


CAPABILITY = 'phase0h_internal_snapshot_audit'
ROUTE_STATUS = 'internal_admin_only'
ROUTE_STATUS_DEGRADED = 'degraded'
DEFAULT_WINDOW_DAYS = 7
MAX_WINDOW_DAYS = 14
RECENT_ROW_QUERY_LIMIT = 64
MAX_RECENT_ROW_QUERY_LIMIT = 512
MAX_REASON_CODES = 20
MAX_LIMITATIONS = 5
MAX_ADJACENT_DETAILS = 20

# Safe in-request limits for the full bounded-summary path. Production runs
# behind Gunicorn --timeout 60; a summary that cannot finish inside these
# bounds must fail fast as a catchable exception (never a worker SIGKILL) so
# the route can degrade to the cheap DB-row fallback instead of a 502.
SUMMARY_STATEMENT_TIMEOUT_MS = 5000
SUMMARY_TIME_BUDGET_SECONDS = 20.0
FALLBACK_STATEMENT_TIMEOUT_MS = 3000

FALLBACK_RESPONSE_MODE = 'fallback_db_row_metadata'
DIAGNOSTIC_SUMMARY_UNAVAILABLE = 'audit_summary_unavailable'
DIAGNOSTIC_FALLBACK_ROW_SUMMARY_ONLY = 'fallback_db_row_summary_only'
SUMMARY_TIME_BUDGET_EXCEEDED = 'summary_time_budget_exceeded'

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


class SnapshotAuditSummaryUnavailable(RuntimeError):
    """The bounded summary could not finish within safe request limits.

    Carries only a stage name and a short reason code — never a raw
    exception message — so nothing secret can leak into responses or logs.
    """

    def __init__(self, *, stage: str, code: str):
        super().__init__(code)
        self.stage = stage
        self.code = code


def _noop_checkpoint(stage_name: str) -> None:
    return None


class _TrustSnapshotAdapter:
    def __init__(self, row: dict, payload: dict):
        self.id = row.get('id')
        self.snapshot_type = row.get('snapshot_type')
        self.status = row.get('status')
        self.is_published = row.get('is_published')
        self.payload = payload
        self.payload_version = row.get('payload_version')
        self.data_through = row.get('data_through')
        self.availability_reference_date = row.get('availability_reference_date')
        self.snapshot_generated_at = row.get('snapshot_generated_at')
        self.source = row.get('source')
        self.error_message = row.get('error_message')
        self.sync_run_id = row.get('sync_run_id')


def build_internal_snapshot_audit_payload(
    *,
    product_date=None,
    window_days=None,
    recent_row_query_limit=None,
    checkpoint=None,
    statement_timeout_ms=None,
    time_budget_seconds=None,
) -> dict:
    mark = checkpoint if checkpoint is not None else _noop_checkpoint
    started = monotonic()
    budget = (
        SUMMARY_TIME_BUDGET_SECONDS
        if time_budget_seconds is None
        else time_budget_seconds
    )

    def stage(name: str) -> None:
        mark(name)
        if budget and monotonic() - started > budget:
            raise SnapshotAuditSummaryUnavailable(
                stage=name,
                code=SUMMARY_TIME_BUDGET_EXCEEDED,
            )

    stage('summary_build_started')
    ref = _parse_product_date(product_date)
    normalized_window = _parse_window_days(window_days)
    normalized_recent_row_limit = _parse_recent_row_query_limit(
        recent_row_query_limit,
    )
    stage('request_parsed')
    _set_local_statement_timeout(
        SUMMARY_STATEMENT_TIMEOUT_MS
        if statement_timeout_ms is None
        else statement_timeout_ms
    )
    stage('db_session_acquired')
    stage('latest_snapshot_query_started')
    latest_snapshot = _latest_snapshot_row(ref)
    stage('latest_snapshot_query_finished')
    anchor_date = ref or (
        latest_snapshot.get('data_through')
        if latest_snapshot is not None
        else None
    )
    stage('recent_snapshot_query_started')
    recent_rows = _recent_snapshot_rows(
        anchor_date,
        normalized_window,
        normalized_recent_row_limit,
    )
    stage('recent_snapshot_query_finished')
    latest_valid = _latest_valid_snapshot(recent_rows)
    stage('sync_run_query_started')
    sync_runs = _sync_runs_by_id(_dedupe_rows(recent_rows, latest_snapshot))
    stage('sync_run_query_finished')
    published_by_date = _latest_published_rows_by_date(recent_rows)

    stage('adjacency_summary_started')
    recent_snapshot_rows = _latest_rows_by_date(recent_rows)
    recent_snapshots = [
        _snapshot_entry(row, published_by_date, sync_runs)
        for row in recent_snapshot_rows
    ]
    latest_snapshot_entry = _snapshot_entry(
        latest_snapshot,
        published_by_date,
        sync_runs,
    )
    latest_valid_entry = _snapshot_entry(
        latest_valid,
        published_by_date,
        sync_runs,
    )
    adjacency_summary = _snapshot_adjacency_summary(
        recent_rows,
        published_by_date,
        sync_runs,
        recent_row_query_limit=normalized_recent_row_limit,
    )
    stage('adjacency_summary_finished')

    stage('response_construction_started')
    sections_present = {
        'served_freshness': True,
        'latest_snapshot': latest_snapshot is not None,
        'latest_valid_snapshot': latest_valid is not None,
        'recent_snapshots': bool(recent_snapshots),
        'snapshot_adjacency_summary': True,
        'diagnostics': True,
    }

    result = {
        'capability': CAPABILITY,
        'route_status': ROUTE_STATUS,
        'internal_only_watermark': _watermark(),
        'request': {
            'date': ref.isoformat() if ref else None,
            'window_days': normalized_window,
        },
        'served_freshness': _served_freshness_summary(latest_valid_entry),
        'latest_snapshot': latest_snapshot_entry,
        'latest_valid_snapshot_id': (
            latest_valid.get('id')
            if latest_valid is not None
            else None
        ),
        'recent_snapshots': recent_snapshots,
        'snapshot_adjacency_summary': adjacency_summary,
        'diagnostics': _diagnostics_summary(
            latest_snapshot_entry,
            recent_row_count=len(recent_rows),
            recent_query_limit=normalized_recent_row_limit,
        ),
        'sections_present': sections_present,
        'missing_sections': [
            key for key, present in sections_present.items() if not present
        ],
    }
    stage('response_construction_finished')
    return result


def build_internal_snapshot_audit_fallback_payload(
    *,
    product_date=None,
    window_days=None,
    failure_stage=None,
    failure_code=None,
    checkpoint=None,
) -> dict:
    """Bounded degraded payload quoting only cheap snapshot row columns.

    Used when the full bounded summary cannot be produced inside safe request
    limits. Reads plain DashboardSnapshot columns only — never the payload
    JSON — so it cannot evaluate trust, comparability, or reason codes and
    never pretends to: those fields are explicitly null/unavailable and the
    payload is marked as unable to support Decision 4/5 ratification.
    """
    mark = checkpoint if checkpoint is not None else _noop_checkpoint
    ref, normalized_window, request_param_errors = _fallback_request_params(
        product_date,
        window_days,
    )

    _rollback_quietly()
    try:
        _set_local_statement_timeout(FALLBACK_STATEMENT_TIMEOUT_MS)
    except Exception:
        _rollback_quietly()

    mark('fallback_latest_row_query_started')
    latest_row, latest_row_error = _fallback_guarded(
        lambda: _fallback_latest_row(ref),
    )
    mark('fallback_latest_row_query_finished')
    anchor_date = ref or (
        latest_row.get('data_through')
        if latest_row is not None
        else None
    )
    mark('fallback_recent_rows_query_started')
    recent_rows, recent_rows_error = _fallback_guarded(
        lambda: _fallback_recent_rows(anchor_date, normalized_window),
    )
    mark('fallback_recent_rows_query_finished')

    diagnostics = [
        _drop_empty({
            'code': DIAGNOSTIC_SUMMARY_UNAVAILABLE,
            'failure_stage': failure_stage,
            'failure_code': failure_code,
        }),
        {
            'code': DIAGNOSTIC_FALLBACK_ROW_SUMMARY_ONLY,
            'detail': (
                'Trust and comparability evidence live in stored payload '
                'JSON; this degraded response quotes only cheap snapshot '
                'row columns and cannot evaluate trusted pairs.'
            ),
        },
    ]
    for param_error in request_param_errors:
        diagnostics.extend([{'code': f'fallback_request_param_ignored:{param_error}'}])
    if latest_row_error is not None:
        diagnostics.extend([{
            'code': 'fallback_latest_snapshot_row_unavailable',
            'error_type': latest_row_error,
        }])
    if recent_rows_error is not None:
        diagnostics.extend([{
            'code': 'fallback_recent_snapshot_rows_unavailable',
            'error_type': recent_rows_error,
        }])

    recent_entries = [
        _fallback_row_entry(row)
        for row in (recent_rows or [])
    ]

    mark('fallback_response_construction_started')
    result = {
        'capability': CAPABILITY,
        'route_status': ROUTE_STATUS_DEGRADED,
        'route_access': ROUTE_STATUS,
        'internal_only_watermark': _watermark(),
        'response_mode': FALLBACK_RESPONSE_MODE,
        'request': {
            'date': ref.isoformat() if ref else None,
            'window_days': normalized_window,
        },
        'ratification_ready': False,
        'decision_4_5_supported': False,
        'ratification_blocked_reason': (
            'fallback_row_metadata_cannot_prove_trusted_pairs'
        ),
        'latest_snapshot': _fallback_row_entry(latest_row),
        'recent_snapshots': recent_entries,
        'recent_snapshot_count': len(recent_entries),
        'recent_row_query_limit': RECENT_ROW_QUERY_LIMIT,
        'snapshot_adjacency_summary': {
            'available': False,
            'reason': 'trust_summary_unavailable_in_fallback',
            'trusted_pair_count': None,
            'comparable_adjacent_pair_count': None,
            'non_comparable_count': None,
            'non_comparable_reason_codes': None,
            'non_adjacent_comparison_count': None,
        },
        'diagnostics': diagnostics,
    }
    mark('fallback_response_construction_finished')
    return result


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


def _parse_recent_row_query_limit(value) -> int:
    if value is None or str(value).strip() == '':
        return RECENT_ROW_QUERY_LIMIT
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise SnapshotAuditRequestError('recent_row_query_limit_invalid') from exc
    if parsed <= 0:
        raise SnapshotAuditRequestError('recent_row_query_limit_invalid')
    return min(parsed, MAX_RECENT_ROW_QUERY_LIMIT)


def _latest_snapshot_row(ref: date | None) -> dict | None:
    query = _snapshot_projection_query()
    if ref is not None:
        query = query.filter(DashboardSnapshot.data_through <= ref)
        query = query.order_by(
            desc(DashboardSnapshot.data_through),
            desc(DashboardSnapshot.snapshot_generated_at),
            desc(DashboardSnapshot.id),
        )
    else:
        query = query.order_by(
            desc(DashboardSnapshot.snapshot_generated_at),
            desc(DashboardSnapshot.id),
        )
    return _projection_dict(query.first())


def _recent_snapshot_rows(
    anchor_date: date | None,
    window_days: int,
    recent_row_query_limit: int,
) -> list[dict]:
    if anchor_date is None:
        return []

    since = anchor_date - timedelta(days=window_days)
    rows = (
        _snapshot_projection_query()
        .filter(DashboardSnapshot.data_through <= anchor_date)
        .filter(DashboardSnapshot.data_through >= since)
        .order_by(
            desc(DashboardSnapshot.data_through),
            desc(DashboardSnapshot.snapshot_generated_at),
            desc(DashboardSnapshot.id),
        )
        .limit(recent_row_query_limit)
        .all()
    )
    return [
        _projection_dict(row)
        for row in rows
        if row is not None
    ]


def _snapshot_projection_query():
    return (
        DashboardSnapshot.query
        .with_entities(*_snapshot_projection_entities())
        .filter(DashboardSnapshot.snapshot_type == SNAPSHOT_TYPE_BULLPEN_DASHBOARD)
    )


def _snapshot_projection_entities():
    payload = DashboardSnapshot.payload
    freshness = payload['freshness']
    coverage = freshness['slate_coverage']
    changed = payload['what_changed_since_yesterday']
    comparison = changed['comparison']
    return (
        DashboardSnapshot.id.label('id'),
        DashboardSnapshot.snapshot_type.label('snapshot_type'),
        DashboardSnapshot.sync_run_id.label('sync_run_id'),
        DashboardSnapshot.status.label('status'),
        DashboardSnapshot.is_published.label('is_published'),
        DashboardSnapshot.published_at.label('published_at'),
        DashboardSnapshot.payload_version.label('payload_version'),
        DashboardSnapshot.data_through.label('data_through'),
        DashboardSnapshot.availability_reference_date.label('availability_reference_date'),
        DashboardSnapshot.snapshot_generated_at.label('snapshot_generated_at'),
        DashboardSnapshot.source.label('source'),
        DashboardSnapshot.error_message.label('error_message'),
        freshness['data_through'].as_string().label('freshness_data_through'),
        freshness['availability_reference_date'].as_string().label(
            'freshness_availability_reference_date',
        ),
        freshness['reference_date'].as_string().label('freshness_reference_date'),
        freshness['sync_status'].as_string().label('freshness_sync_status'),
        freshness['validations_passed'].as_boolean().label(
            'freshness_validations_passed',
        ),
        freshness['complete_enough_to_publish'].as_boolean().label(
            'freshness_complete_enough_to_publish',
        ),
        freshness['reason_codes'].label('freshness_reason_codes'),
        freshness['limitations'].label('freshness_limitations'),
        coverage['slate_date'].as_string().label('coverage_slate_date'),
        coverage['validations_passed'].as_boolean().label(
            'coverage_validations_passed',
        ),
        coverage['complete_enough_to_publish'].as_boolean().label(
            'coverage_complete_enough_to_publish',
        ),
        coverage['coverage_known'].as_boolean().label('coverage_known'),
        coverage['reason_codes'].label('coverage_reason_codes'),
        changed['state'].as_string().label('changed_state'),
        changed['reason_codes'].label('changed_reason_codes'),
        changed['limitations'].label('changed_limitations'),
        changed['comparison_available'].as_boolean().label(
            'changed_comparison_available',
        ),
        changed['baseline_date'].as_string().label('changed_baseline_date'),
        changed['current_date'].as_string().label('changed_current_date'),
        changed['data_through'].as_string().label('changed_data_through'),
        changed['prior_data_through'].as_string().label(
            'changed_prior_data_through',
        ),
        changed['item_count'].as_integer().label('changed_item_count'),
        changed['items_count'].as_integer().label('changed_items_count'),
        changed['change_count'].as_integer().label('changed_change_count'),
        changed['max_items'].as_integer().label('changed_max_items'),
        changed['omitted_count'].as_integer().label('changed_omitted_count'),
        comparison['state'].as_string().label('comparison_state'),
        comparison['reason_codes'].label('comparison_reason_codes'),
        comparison['limitations'].label('comparison_limitations'),
        comparison['comparison_available'].as_boolean().label(
            'comparison_available',
        ),
        comparison['baseline_date'].as_string().label('comparison_baseline_date'),
        comparison['current_date'].as_string().label('comparison_current_date'),
        comparison['data_through'].as_string().label('comparison_data_through'),
        comparison['prior_data_through'].as_string().label(
            'comparison_prior_data_through',
        ),
    )


def _projection_dict(row) -> dict | None:
    if row is None:
        return None
    if hasattr(row, '_asdict'):
        return dict(row._asdict())
    return dict(row)


def _snapshot_entry(
    row: dict | None,
    published_by_date: dict,
    sync_runs: dict,
) -> dict | None:
    if row is None:
        return None
    embedded_what_changed = _embedded_what_changed(row)
    adjacent_baseline = _adjacent_published_baseline(row, published_by_date)
    baseline_adjacency = _baseline_adjacency(row, adjacent_baseline)
    trust = _trust_summary(row)
    return {
        'id': row.get('id'),
        'snapshot_type': row.get('snapshot_type'),
        'status': row.get('status'),
        'is_published': bool(row.get('is_published')),
        'published_at': _iso(row.get('published_at')),
        'data_through': _iso(row.get('data_through')),
        'availability_reference_date': _iso(row.get('availability_reference_date')),
        'payload_version': row.get('payload_version'),
        'source': row.get('source'),
        'error_message': row.get('error_message'),
        'snapshot_generated_at': _iso(row.get('snapshot_generated_at')),
        'sync_run_id': row.get('sync_run_id'),
        'sync_run': _sync_run_entry(sync_runs.get(row.get('sync_run_id'))),
        'trust': trust,
        'payload_freshness': _payload_freshness_summary(row),
        'embedded_what_changed': embedded_what_changed,
        'baseline_adjacency': baseline_adjacency,
        'comparison_contract_check': _comparison_contract_check(
            row,
            embedded_what_changed,
            baseline_adjacency,
            adjacent_baseline,
        ),
        'response_mode': 'bounded_summary',
    }


def _sync_runs_by_id(rows: list[dict]) -> dict:
    ids = sorted({
        row.get('sync_run_id')
        for row in rows
        if row is not None and row.get('sync_run_id') is not None
    })
    if not ids:
        return {}
    return {
        row.id: row
        for row in SyncRun.query.filter(SyncRun.id.in_(ids)).all()
    }


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


def _payload_freshness_summary(row: dict) -> dict:
    coverage = _slate_coverage_summary(row)
    return _drop_empty({
        'data_through': row.get('freshness_data_through'),
        'availability_reference_date': row.get(
            'freshness_availability_reference_date',
        ),
        'reference_date': row.get('freshness_reference_date'),
        'sync_status': row.get('freshness_sync_status'),
        'validations_passed': row.get('freshness_validations_passed'),
        'complete_enough_to_publish': row.get(
            'freshness_complete_enough_to_publish',
        ),
        'reason_codes': _limited_list(row.get('freshness_reason_codes')),
        'limitations': _limited_list(
            row.get('freshness_limitations'),
            max_items=MAX_LIMITATIONS,
        ),
        'slate_coverage': coverage if coverage else None,
    })


def _slate_coverage_summary(row: dict) -> dict:
    return _drop_empty({
        'slate_date': row.get('coverage_slate_date'),
        'validations_passed': row.get('coverage_validations_passed'),
        'complete_enough_to_publish': row.get(
            'coverage_complete_enough_to_publish',
        ),
        'coverage_known': row.get('coverage_known'),
        'reason_codes': _limited_list(row.get('coverage_reason_codes')),
    })


def _embedded_what_changed(row: dict) -> dict | None:
    comparison = _drop_empty({
        'state': row.get('comparison_state'),
        'reason_codes': _limited_list(row.get('comparison_reason_codes')),
        'limitations': _limited_list(
            row.get('comparison_limitations'),
            max_items=MAX_LIMITATIONS,
        ),
        'comparison_available': row.get('comparison_available'),
        'baseline_date': row.get('comparison_baseline_date'),
        'current_date': row.get('comparison_current_date'),
        'data_through': row.get('comparison_data_through'),
        'prior_data_through': row.get('comparison_prior_data_through'),
    })
    extracted = _drop_empty({
        'state': row.get('changed_state'),
        'reason_codes': _limited_list(row.get('changed_reason_codes')),
        'limitations': _limited_list(
            row.get('changed_limitations'),
            max_items=MAX_LIMITATIONS,
        ),
        'comparison_available': row.get('changed_comparison_available'),
        'baseline_date': row.get('changed_baseline_date'),
        'current_date': row.get('changed_current_date'),
        'data_through': row.get('changed_data_through'),
        'prior_data_through': row.get('changed_prior_data_through'),
        'item_count': row.get('changed_item_count'),
        'items_count': row.get('changed_items_count'),
        'change_count': row.get('changed_change_count'),
        'max_items': row.get('changed_max_items'),
        'omitted_count': row.get('changed_omitted_count'),
        'comparison': comparison if comparison else None,
    })
    return extracted if extracted else None


def _adjacent_published_baseline(row: dict, published_by_date: dict) -> dict | None:
    data_through = row.get('data_through')
    if data_through is None:
        return None
    return published_by_date.get(data_through - timedelta(days=1))


def _baseline_adjacency(
    row: dict,
    prior_snapshot: dict | None = None,
) -> dict:
    prior_data_through = (
        row.get('data_through') - timedelta(days=1)
        if row.get('data_through') is not None
        else None
    )
    return {
        'prior_data_through': _iso(prior_data_through),
        'prior_published_snapshot_id': (
            prior_snapshot.get('id') if prior_snapshot else None
        ),
        'adjacent_published_baseline_present': prior_snapshot is not None,
    }


def _comparison_contract_check(
    row: dict,
    embedded_what_changed: dict | None,
    baseline_adjacency: dict,
    adjacent_baseline: dict | None,
) -> dict:
    prior_required_data_through = (
        row.get('data_through') - timedelta(days=1)
        if row.get('data_through') is not None
        else None
    )
    adjacent_trusted_baseline_present = (
        adjacent_baseline is not None
        and _snapshot_unavailable_reason(adjacent_baseline) is None
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
    stored_metadata_present = _stored_comparison_metadata_present(
        embedded_what_changed,
    )
    expected_current_date = _iso(row.get('data_through'))
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
    if stored_comparison_available is not True:
        notes.append('stored_comparison_not_available')

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
        'notes': _dedupe_text(notes),
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


def _snapshot_adjacency_summary(
    rows: list[dict],
    published_by_date: dict,
    sync_runs: dict,
    *,
    recent_row_query_limit: int,
) -> dict:
    published_rows = [row for row in rows if bool(row.get('is_published'))]
    trusted_published_rows = [
        row for row in published_rows
        if _snapshot_unavailable_reason(row) is None
    ]
    data_through_dates = sorted(published_by_date)
    adjacent_pairs = []
    missing_prior_dates = []
    trusted_pair_count = 0
    comparable_adjacent_pair_count = 0
    non_comparable_count = 0
    non_comparable_reason_codes = []
    non_adjacent_comparisons = []

    for current_data_through in data_through_dates:
        prior_data_through = current_data_through - timedelta(days=1)
        current_snapshot = published_by_date.get(current_data_through)
        prior_snapshot = published_by_date.get(prior_data_through)
        if prior_snapshot is None:
            missing_prior_dates.append(current_data_through.isoformat())
            continue

        adjacent_pair = {
            'current_data_through': current_data_through.isoformat(),
            'prior_data_through': prior_data_through.isoformat(),
            'current_snapshot_id': current_snapshot.get('id'),
            'prior_snapshot_id': prior_snapshot.get('id'),
        }
        adjacent_pairs.append(adjacent_pair)
        if (
            _snapshot_unavailable_reason(current_snapshot) is None
            and _snapshot_unavailable_reason(prior_snapshot) is None
        ):
            trusted_pair_count += 1

        current_entry = _snapshot_entry(current_snapshot, published_by_date, sync_runs)
        contract_check = current_entry.get('comparison_contract_check') or {}
        if (
            contract_check.get('stored_comparison_available') is True
            and contract_check.get('stored_comparison_matches_adjacent_contract') is True
            and contract_check.get('adjacent_trusted_baseline_present') is True
        ):
            comparable_adjacent_pair_count += 1
        else:
            non_comparable_count += 1
            non_comparable_reason_codes.extend(
                _non_comparable_reasons(current_entry)
            )
        if contract_check.get('stored_comparison_matches_adjacent_contract') is False:
            non_adjacent_comparisons.append({
                'snapshot_id': current_snapshot.get('id'),
                'data_through': current_data_through.isoformat(),
                'stored_baseline_date': contract_check.get(
                    'stored_comparison_baseline_date',
                ),
                'expected_baseline_date': contract_check.get(
                    'prior_required_data_through',
                ),
            })

    return {
        'published_snapshot_count': len(published_rows),
        'trusted_published_snapshot_count': len(trusted_published_rows),
        'data_through_dates': [
            data_through.isoformat()
            for data_through in data_through_dates
        ],
        'adjacent_published_pairs': adjacent_pairs[:MAX_ADJACENT_DETAILS],
        'adjacent_published_pair_count': len(adjacent_pairs),
        'missing_prior_dates': missing_prior_dates[:MAX_ADJACENT_DETAILS],
        'trusted_pair_count': trusted_pair_count,
        'comparable_adjacent_pair_count': comparable_adjacent_pair_count,
        'non_comparable_count': non_comparable_count,
        'non_comparable_reason_codes': _dedupe_text(
            non_comparable_reason_codes,
            limit=MAX_REASON_CODES,
        ),
        'non_adjacent_comparison_count': len(non_adjacent_comparisons),
        'non_adjacent_comparisons': (
            non_adjacent_comparisons[:MAX_ADJACENT_DETAILS]
        ),
        'response_mode': 'bounded_summary',
        'recent_row_query_limit': recent_row_query_limit,
        'recent_rows_truncated': len(rows) >= recent_row_query_limit,
    }


def _non_comparable_reasons(entry: dict) -> list[str]:
    reasons = []
    trust = entry.get('trust') or {}
    if trust.get('unavailable_reason'):
        reasons.append(trust.get('unavailable_reason'))
    changed = entry.get('embedded_what_changed') or {}
    reasons.extend(_limited_list(changed.get('reason_codes')))
    comparison = changed.get('comparison') or {}
    reasons.extend(_limited_list(comparison.get('reason_codes')))
    check = entry.get('comparison_contract_check') or {}
    reasons.extend(_limited_list(check.get('notes')))
    return reasons


def _latest_rows_by_date(rows: list[dict]) -> list[dict]:
    by_date = {}
    for row in rows:
        data_through = row.get('data_through')
        if data_through is None:
            continue
        current = by_date.get(data_through)
        if current is None or _row_order_key(row) > _row_order_key(current):
            by_date[data_through] = row
    return sorted(
        by_date.values(),
        key=_row_order_key,
        reverse=True,
    )


def _latest_published_rows_by_date(rows: list[dict]) -> dict:
    by_date = {}
    for row in rows:
        data_through = row.get('data_through')
        if data_through is None or not bool(row.get('is_published')):
            continue
        current = by_date.get(data_through)
        if current is None or _row_order_key(row) > _row_order_key(current):
            by_date[data_through] = row
    return by_date


def _latest_valid_snapshot(rows: list[dict]) -> dict | None:
    for row in sorted(rows, key=_row_order_key, reverse=True):
        if _snapshot_unavailable_reason(row) is None:
            return row
    return None


def _row_order_key(row: dict):
    return (
        row.get('data_through') or date.min,
        row.get('snapshot_generated_at') or datetime.min,
        row.get('id') or 0,
    )


def _trust_summary(row: dict) -> dict:
    payload = _compact_payload(row)
    adapter = _TrustSnapshotAdapter(row, payload)
    return {
        'unavailable_reason': snapshot_unavailable_reason(adapter),
        'current_enough': snapshot_current_enough(adapter),
        'payload_version_valid': payload_version_valid(adapter),
    }


def _snapshot_unavailable_reason(row: dict) -> str | None:
    payload = _compact_payload(row)
    return snapshot_unavailable_reason(_TrustSnapshotAdapter(row, payload))


def _compact_payload(row: dict) -> dict:
    freshness = _payload_freshness_summary(row)
    if not freshness:
        return {}
    return {'freshness': freshness}


def _served_freshness_summary(latest_valid_entry: dict | None) -> dict:
    if latest_valid_entry is not None:
        freshness = dict(latest_valid_entry.get('payload_freshness') or {})
        freshness.update({
            'snapshot_id': latest_valid_entry.get('id'),
            'snapshot_status': latest_valid_entry.get('status'),
            'snapshot_generated_at': latest_valid_entry.get('snapshot_generated_at'),
            'source': latest_valid_entry.get('source'),
            'response_mode': 'bounded_summary',
        })
        return _json_safe(freshness)
    return _json_safe(board_freshness.sync_status_freshness_block())


def _diagnostics_summary(
    latest_snapshot: dict | None,
    *,
    recent_row_count: int,
    recent_query_limit: int,
) -> dict:
    if latest_snapshot is None:
        return {
            'reason': 'dashboard_snapshot_missing',
            'snapshot_id': None,
            'payload_has_slate_coverage': False,
            'response_mode': 'bounded_summary',
            'recent_row_count': recent_row_count,
            'recent_row_query_limit': recent_query_limit,
            'recent_rows_truncated': recent_row_count >= recent_query_limit,
        }
    freshness = latest_snapshot.get('payload_freshness') or {}
    coverage = freshness.get('slate_coverage') or {}
    trust = latest_snapshot.get('trust') or {}
    return {
        'reason': trust.get('unavailable_reason'),
        'snapshot_id': latest_snapshot.get('id'),
        'snapshot_status': latest_snapshot.get('status'),
        'is_published': latest_snapshot.get('is_published'),
        'error_message': latest_snapshot.get('error_message'),
        'payload_version': latest_snapshot.get('payload_version'),
        'data_through': latest_snapshot.get('data_through'),
        'availability_reference_date': latest_snapshot.get(
            'availability_reference_date',
        ),
        'snapshot_generated_at': latest_snapshot.get('snapshot_generated_at'),
        'payload_has_slate_coverage': bool(coverage),
        'slate_coverage': coverage or None,
        'response_mode': 'bounded_summary',
        'recent_row_count': recent_row_count,
        'recent_row_query_limit': recent_query_limit,
        'recent_rows_truncated': recent_row_count >= recent_query_limit,
    }


def _dedupe_rows(*groups) -> list[dict]:
    by_id = {}
    for group in groups:
        if group is None:
            continue
        if isinstance(group, dict):
            rows = [group]
        else:
            rows = group
        for row in rows:
            if row is not None and row.get('id') is not None:
                by_id[row.get('id')] = row
    return list(by_id.values())


def _drop_empty(value: dict) -> dict:
    return {
        key: nested
        for key, nested in value.items()
        if nested is not None and nested != [] and nested != {}
    }


def _limited_list(value, *, max_items: int = MAX_REASON_CODES) -> list:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        values = list(value)
    else:
        values = [value]
    return [
        _json_safe(item)
        for item in values[:max_items]
    ]


def _dedupe_text(values, *, limit: int | None = None) -> list[str]:
    result = []
    seen = set()
    for value in values:
        if value is None:
            continue
        text = str(value)
        if text in seen:
            continue
        seen.update([text])
        result.append(text)
        if limit is not None and len(result) >= limit:
            break
    return result


def _set_local_statement_timeout(timeout_ms) -> bool:
    """Scope a Postgres statement timeout to the current transaction.

    Bounds each audit query well under the Gunicorn worker timeout so an
    expensive query raises a catchable DB error instead of the worker being
    SIGKILLed into an empty-body 502. No-op on non-Postgres (tests/SQLite).
    """
    if not timeout_ms:
        return False
    bind = db.session.get_bind()
    if bind is None or bind.dialect.name != 'postgresql':
        return False
    db.session.execute(text(f'SET LOCAL statement_timeout = {int(timeout_ms)}'))
    return True


def _rollback_quietly() -> None:
    # Read-only route: rollback only clears an aborted transaction (for
    # example after a statement timeout) so fallback reads can proceed.
    try:
        db.session.rollback()
    except Exception:
        return None


def _fallback_guarded(query_fn):
    """Run one fallback query; on any failure return (None, error_type).

    Only the exception class name is captured — never the message, which for
    DB errors can embed connection details.
    """
    try:
        return query_fn(), None
    except Exception as exc:
        _rollback_quietly()
        return None, type(exc).__name__


def _fallback_request_params(product_date, window_days):
    errors = []
    try:
        ref = _parse_product_date(product_date)
    except SnapshotAuditRequestError:
        ref = None
        errors.extend(['date_invalid'])
    try:
        normalized_window = _parse_window_days(window_days)
    except SnapshotAuditRequestError:
        normalized_window = DEFAULT_WINDOW_DAYS
        errors.extend(['window_invalid'])
    return ref, normalized_window, errors


def _fallback_row_query():
    return (
        DashboardSnapshot.query
        .with_entities(
            DashboardSnapshot.id.label('id'),
            DashboardSnapshot.snapshot_type.label('snapshot_type'),
            DashboardSnapshot.sync_run_id.label('sync_run_id'),
            DashboardSnapshot.status.label('status'),
            DashboardSnapshot.is_published.label('is_published'),
            DashboardSnapshot.published_at.label('published_at'),
            DashboardSnapshot.payload_version.label('payload_version'),
            DashboardSnapshot.data_through.label('data_through'),
            DashboardSnapshot.availability_reference_date.label(
                'availability_reference_date',
            ),
            DashboardSnapshot.snapshot_generated_at.label(
                'snapshot_generated_at',
            ),
            DashboardSnapshot.source.label('source'),
            DashboardSnapshot.error_message.label('error_message'),
        )
        .filter(DashboardSnapshot.snapshot_type == SNAPSHOT_TYPE_BULLPEN_DASHBOARD)
    )


def _fallback_latest_row(ref: date | None) -> dict | None:
    query = _fallback_row_query()
    if ref is not None:
        query = query.filter(DashboardSnapshot.data_through <= ref)
        query = query.order_by(
            desc(DashboardSnapshot.data_through),
            desc(DashboardSnapshot.snapshot_generated_at),
            desc(DashboardSnapshot.id),
        )
    else:
        query = query.order_by(
            desc(DashboardSnapshot.snapshot_generated_at),
            desc(DashboardSnapshot.id),
        )
    return _projection_dict(query.first())


def _fallback_recent_rows(anchor_date: date | None, window_days: int) -> list[dict]:
    if anchor_date is None:
        return []
    since = anchor_date - timedelta(days=window_days)
    rows = (
        _fallback_row_query()
        .filter(DashboardSnapshot.data_through <= anchor_date)
        .filter(DashboardSnapshot.data_through >= since)
        .order_by(
            desc(DashboardSnapshot.data_through),
            desc(DashboardSnapshot.snapshot_generated_at),
            desc(DashboardSnapshot.id),
        )
        .limit(RECENT_ROW_QUERY_LIMIT)
        .all()
    )
    return [
        _projection_dict(row)
        for row in rows
        if row is not None
    ]


def _fallback_row_entry(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {
        'id': row.get('id'),
        'snapshot_type': row.get('snapshot_type'),
        'status': row.get('status'),
        'is_published': bool(row.get('is_published')),
        'published_at': _iso(row.get('published_at')),
        'payload_version': row.get('payload_version'),
        'data_through': _iso(row.get('data_through')),
        'availability_reference_date': _iso(
            row.get('availability_reference_date'),
        ),
        'snapshot_generated_at': _iso(row.get('snapshot_generated_at')),
        'source': row.get('source'),
        'error_message': row.get('error_message'),
        'sync_run_id': row.get('sync_run_id'),
        'trust_evaluated': False,
        'response_mode': 'db_row_metadata_only',
    }


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
