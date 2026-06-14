"""
Tests for roster-status authority normalization.

Roster status must remain distinct from workload freshness and bullpen usage.
"""

from datetime import datetime
from types import SimpleNamespace

from services.roster_status import (
    ROSTER_STATUS_UNAVAILABLE_LIMITATION,
    STATUS_40_MAN_ONLY,
    STATUS_ACTIVE,
    STATUS_DFA,
    STATUS_IL_15,
    STATUS_IL_60,
    STATUS_MINORS,
    STATUS_NON_ROSTER,
    STATUS_OPTIONED,
    STATUS_UNKNOWN,
    allows_default_board,
    classify_roster_status,
    normalize_roster_status_value,
)


def test_normalizes_authoritative_active_and_inactive_statuses():
    assert normalize_roster_status_value('Active') == STATUS_ACTIVE
    assert normalize_roster_status_value('15-day IL') == STATUS_IL_15
    assert normalize_roster_status_value('D60') == STATUS_IL_60
    assert normalize_roster_status_value('Minors') == STATUS_MINORS
    assert normalize_roster_status_value('Optioned to minors') == STATUS_OPTIONED
    assert normalize_roster_status_value('DFA') == STATUS_DFA
    assert normalize_roster_status_value('Non-roster') == STATUS_NON_ROSTER
    assert normalize_roster_status_value('40-man only') == STATUS_40_MAN_ONLY
    assert normalize_roster_status_value('MIN') == STATUS_MINORS
    assert normalize_roster_status_value('Injured List') == STATUS_IL_15
    assert normalize_roster_status_value('Optioned to minor league') == STATUS_OPTIONED


def test_unknown_status_degrades_with_limitation_not_active_claim():
    result = classify_roster_status(SimpleNamespace(active=True))

    assert result['status'] == STATUS_UNKNOWN
    assert result['is_authoritative'] is False
    assert result['is_active_mlb'] is None
    assert ROSTER_STATUS_UNAVAILABLE_LIMITATION in result['limitations']


def test_stored_il_status_is_authoritative_inactive_context():
    result = classify_roster_status(
        SimpleNamespace(
            active=True,
            roster_status='IL_15',
            roster_status_source='fixture',
        )
    )

    assert result['status'] == STATUS_IL_15
    assert result['label'] == 'IL-15'
    assert result['is_authoritative'] is True
    assert result['is_active_mlb'] is False
    assert result['is_inactive_context'] is True


def test_stored_40_man_only_status_uses_baseball_facing_label():
    result = classify_roster_status(
        SimpleNamespace(
            active=True,
            roster_status='40_MAN_ONLY',
            roster_status_source='fixture',
        )
    )

    assert result['status'] == STATUS_40_MAN_ONLY
    assert result['label'] == '40-Man Only'
    assert result['is_authoritative'] is True
    assert result['is_active_mlb'] is False
    assert result['is_inactive_context'] is True


def test_current_active_assignment_keeps_player_active_over_stale_inactive_label():
    result = classify_roster_status(
        SimpleNamespace(
            active=True,
            roster_status=STATUS_MINORS,
            roster_status_source='mlb_stats_api:transactions:optioned',
            roster_status_updated_at=datetime(2026, 4, 13, 12, 0, 0),
            team_assignment_status='ASSIGNED',
            team_assignment_source='mlb_stats_api:team_assignment_sync:active',
            team_assignment_updated_at=datetime(2026, 6, 14, 12, 0, 0),
        )
    )

    assert result['status'] == STATUS_ACTIVE
    assert result['label'] == 'Active MLB'
    assert result['source'] == 'mlb_stats_api:team_assignment_sync:active'
    assert result['is_authoritative'] is True
    assert result['is_active_mlb'] is True


def test_current_minor_assignment_overrides_stale_activated_label():
    result = classify_roster_status(
        SimpleNamespace(
            active=True,
            roster_status=STATUS_ACTIVE,
            roster_status_source='mlb_stats_api:transactions:activated',
            roster_status_updated_at=datetime(2026, 4, 1, 12, 0, 0),
            team_assignment_status='ASSIGNED',
            team_assignment_source='mlb_stats_api:team_assignment_sync:fullRoster',
            team_assignment_updated_at=datetime(2026, 4, 13, 12, 0, 0),
        )
    )

    assert result['status'] == STATUS_MINORS
    assert result['label'] == 'Minors'
    assert result['source'] == 'mlb_stats_api:team_assignment_sync:fullRoster'
    assert result['updated_at'] == '2026-04-13T12:00:00'
    assert result['raw_status'] == 'fullRoster'
    assert result['is_authoritative'] is True
    assert result['is_active_mlb'] is False
    assert result['is_inactive_context'] is True


def test_current_roster_sync_il_status_is_preserved():
    result = classify_roster_status(
        SimpleNamespace(
            active=True,
            roster_status=STATUS_IL_15,
            roster_status_source='mlb_stats_api:roster_sync:40Man',
            roster_status_updated_at=datetime(2026, 6, 14, 12, 0, 0),
            team_assignment_status='ASSIGNED',
            team_assignment_source='mlb_stats_api:team_assignment_sync:40Man',
            team_assignment_updated_at=datetime(2026, 6, 14, 12, 0, 0),
        )
    )

    assert result['status'] == STATUS_IL_15
    assert result['label'] == 'IL-15'
    assert result['source'] == 'mlb_stats_api:roster_sync:40Man'
    assert result['is_active_mlb'] is False
    assert result['is_inactive_context'] is True


def test_unresolved_current_assignment_does_not_fall_back_to_stale_active_label():
    result = classify_roster_status(
        SimpleNamespace(
            active=True,
            roster_status=STATUS_ACTIVE,
            roster_status_source='mlb_stats_api:transactions:activated',
            roster_status_updated_at=datetime(2026, 4, 1, 12, 0, 0),
            team_assignment_status='UNKNOWN',
            team_assignment_source='mlb_stats_api:team_assignment_sync:unavailable',
            team_assignment_updated_at=datetime(2026, 6, 14, 12, 0, 0),
        )
    )

    assert result['status'] == STATUS_UNKNOWN
    assert result['is_authoritative'] is False
    assert result['is_active_mlb'] is None
    assert result['current_assignment_unresolved'] is True
    assert allows_default_board(result) is False
    assert ROSTER_STATUS_UNAVAILABLE_LIMITATION in result['limitations']
