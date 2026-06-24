"""Shared board / published-snapshot freshness block.

The compact freshness/trust block the Today board and the team "What Changed"
surface present, derived from the published dashboard snapshot (preferred) or
durable sync metadata (fallback). This lives in a service so every caller — the
API routes AND the digest path — produces the SAME freshness. The digest
previously passed no freshness, which made the shared team_changes builder fail
closed to a stale state; sourcing this block keeps the digest aligned with Today.

Pure derivation over existing services (dashboard snapshot + durable sync
metadata). No request/Flask state, no ranking, selection, recommendation, or
prediction; it only reads and reshapes freshness metadata.
"""

from services import dashboard_snapshot as dashboard_snapshot_service
from services import sync_metadata
from services.availability import ACTIVE_WINDOW_DAYS
from services.availability_reference_date import (
    product_availability_reference_date_from_sync_status,
)


def sync_status_freshness_block(status_payload=None):
    """
    Compact freshness/trust block for the board, derived from the same durable
    sync metadata the dashboard trusts. Never raises — a DB hiccup degrades to a
    clearly-labelled "unavailable" state instead of failing the board.
    """
    try:
        status_payload = status_payload or sync_metadata.build_sync_status_payload()
        availability_reference_date = product_availability_reference_date_from_sync_status(
            status_payload
        )
        freshness = status_payload.get('freshness') or {}
        data = status_payload.get('data') or {}
        return {
            'data_through': data.get('latest_game_date'),
            'latest_workload_date': data.get('latest_workload_date'),
            'reference_date': freshness.get('reference_date'),
            'availability_reference_date': (
                availability_reference_date.isoformat()
                if availability_reference_date
                else None
            ),
            'last_successful_sync': status_payload.get('last_successful_sync'),
            'last_completed_game_refresh': status_payload.get('last_completed_game_refresh'),
            'last_morning_full_sync': status_payload.get('last_morning_full_sync'),
            'sync_status': status_payload.get('status'),
            'sync_authority': status_payload.get('sync_authority'),
            'freshness_state': freshness.get('freshness_state'),
            'is_current': freshness.get('is_current', False),
            'is_stale': freshness.get('is_stale', False),
            'data_age_days': freshness.get('data_age_days'),
            'active_window_days': freshness.get('active_window_days'),
            'active_cutoff_date': freshness.get('active_cutoff_date'),
            'reason_codes': list(freshness.get('reason_codes') or []),
            'label': freshness.get('label'),
            'limitations': list(freshness.get('limitations') or []),
            # Fail-closed degradation tier (fresh / stale / unavailable). When
            # fail_closed is True the data is past the hard threshold and must
            # not be presented as usable.
            'degradation': freshness.get('degradation'),
            'degradation_state': (freshness.get('degradation') or {}).get('state'),
            'fail_closed': bool((freshness.get('degradation') or {}).get('fail_closed')),
        }
    except Exception:
        # A metadata read failure itself fails closed — we cannot prove the data
        # is fresh, so we must not imply it is.
        return {
            'data_through': None,
            'latest_workload_date': None,
            'reference_date': None,
            'availability_reference_date': None,
            'last_successful_sync': None,
            'last_completed_game_refresh': None,
            'last_morning_full_sync': None,
            'sync_status': None,
            'sync_authority': 'sync_runs',
            'freshness_state': 'metadata_unavailable',
            'is_current': False,
            'is_stale': False,
            'data_age_days': None,
            'active_window_days': ACTIVE_WINDOW_DAYS,
            'active_cutoff_date': None,
            'reason_codes': ['durable_sync_metadata_unavailable'],
            'label': 'Freshness metadata unavailable.',
            'limitations': ['Could not read durable sync metadata.'],
            'degradation': {
                'state': 'unavailable',
                'fail_closed': True,
                'data_age_days': None,
                'stale_after_days': None,
                'unavailable_after_days': None,
            },
            'degradation_state': 'unavailable',
            'fail_closed': True,
        }


def published_snapshot_overlay(snapshot):
    try:
        status_payload = sync_metadata.build_sync_status_payload()
    except Exception:
        return {}
    latest_sync = status_payload.get('sync') or {}
    latest_id = latest_sync.get('id')
    snapshot_sync_id = snapshot.sync_run_id if snapshot is not None else None
    if latest_id == snapshot_sync_id:
        return {}
    if status_payload.get('status') not in (
        sync_metadata.STATUS_RUNNING,
        sync_metadata.STATUS_FAILED,
    ):
        return {}
    return {
        'served_consistency_state': 'previous_published_view',
        'current_sync_status': status_payload.get('status'),
        'current_sync_stage': latest_sync.get('stage'),
        'current_sync_run_id': latest_id,
    }


def published_snapshot_freshness_block():
    snapshot = dashboard_snapshot_service.get_latest_valid_dashboard_snapshot()
    if snapshot is None or not isinstance(snapshot.payload, dict):
        return None
    freshness = dict((snapshot.payload or {}).get('freshness') or {})
    if not freshness:
        return None
    overlay = published_snapshot_overlay(snapshot)
    if overlay:
        reason_codes = list(freshness.get('reason_codes') or [])
        limitations = list(freshness.get('limitations') or [])
        status = overlay.get('current_sync_status')
        if status == sync_metadata.STATUS_RUNNING:
            code = 'sync_in_progress_serving_previous_published_view'
            message = 'A sync is in progress; this is the last fully published view.'
        else:
            code = 'latest_sync_failed_serving_previous_published_view'
            message = 'The latest sync failed before publish; this is the last fully published view.'
        if code not in reason_codes:
            reason_codes.append(code)
        if message not in limitations:
            limitations.append(message)
        freshness.update(overlay)
        freshness['reason_codes'] = reason_codes
        freshness['limitations'] = limitations
    return freshness


def board_freshness_block(*, use_published=True):
    if use_published:
        published = published_snapshot_freshness_block()
        if published is not None:
            return published
    return sync_status_freshness_block()
