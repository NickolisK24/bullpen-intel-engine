"""Unit tests for the serving-snapshot freshness authority (readiness-freshness
repair). Pure/deterministic: no DB. Proves the fail-closed authority decision and
the sync-status anchoring that lets a current serving trusted snapshot supersede a
lagging live game-log freshness recompute — while a stale / untrusted / non-serving
snapshot never invents currency."""

from datetime import date, timedelta

from services.readiness_snapshot_freshness import (
    REASON_CURRENT_SERVING_SNAPSHOT,
    anchor_sync_status_to_serving_snapshot,
    serving_snapshot_freshness_authority,
)


REF = date(2026, 7, 24)


class _Snap:
    def __init__(self, data_through):
        self.data_through = data_through


def _trusted(_snapshot):
    return None


def _untrusted(_snapshot):
    return 'dashboard_snapshot_not_published'


# --- authority decision (fail closed) ----------------------------------------


def test_current_trusted_snapshot_yields_authority():
    authority = serving_snapshot_freshness_authority(
        _Snap(date(2026, 7, 23)), reference_date=REF, unavailable_reason=_trusted,
    )
    assert authority is not None
    assert authority['data_through'] == date(2026, 7, 23)
    assert authority['availability_reference_date'] == date(2026, 7, 24)
    assert authority['reason_code'] == REASON_CURRENT_SERVING_SNAPSHOT


def test_none_snapshot_fails_closed():
    assert serving_snapshot_freshness_authority(None, reference_date=REF) is None


def test_untrusted_snapshot_fails_closed():
    assert serving_snapshot_freshness_authority(
        _Snap(date(2026, 7, 23)), reference_date=REF, unavailable_reason=_untrusted,
    ) is None


def test_missing_data_through_fails_closed():
    assert serving_snapshot_freshness_authority(
        _Snap(None), reference_date=REF, unavailable_reason=_trusted,
    ) is None


def test_data_through_outside_window_fails_closed():
    # 15 days behind a 14-day window -> genuinely stale snapshot -> no authority.
    assert serving_snapshot_freshness_authority(
        _Snap(REF - timedelta(days=15)), reference_date=REF, unavailable_reason=_trusted,
    ) is None


def test_data_through_on_window_boundary_is_current():
    assert serving_snapshot_freshness_authority(
        _Snap(REF - timedelta(days=14)), reference_date=REF, unavailable_reason=_trusted,
    ) is not None


# --- sync-status anchoring -----------------------------------------------------


def _stale_sync_status():
    return {
        'status': 'partial',
        'data': {'latest_game_date': '2026-07-05', 'latest_workload_date': '2026-07-05'},
        'freshness': {
            'is_current': False,
            'is_stale': True,
            'freshness_state': 'stale',
            'reason_codes': ['workload_data_outside_active_window'],
            'label': 'Stale baseball data through 2026-07-05.',
            'stale_warning': 'Stale baseball data through 2026-07-05.',
        },
    }


def test_anchor_overrides_stale_freshness_to_current():
    authority = serving_snapshot_freshness_authority(
        _Snap(date(2026, 7, 23)), reference_date=REF, unavailable_reason=_trusted,
    )
    anchored = anchor_sync_status_to_serving_snapshot(_stale_sync_status(), authority)
    fr = anchored['freshness']
    assert fr['is_current'] is True
    assert fr['is_stale'] is False
    assert fr['freshness_state'] == 'current'
    assert fr['stale_warning'] is None
    assert 'workload_data_outside_active_window' not in fr['reason_codes']
    assert REASON_CURRENT_SERVING_SNAPSHOT in fr['reason_codes']
    assert anchored['data']['latest_workload_date'] == '2026-07-23'
    # Non-freshness fields are preserved (overall sync status stays honest).
    assert anchored['status'] == 'partial'


def test_anchor_none_authority_is_identity():
    original = _stale_sync_status()
    assert anchor_sync_status_to_serving_snapshot(original, None) is original
