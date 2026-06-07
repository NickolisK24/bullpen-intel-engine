"""
Tests for roster-status authority normalization.

Roster status must remain distinct from workload freshness and bullpen usage.
"""

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
