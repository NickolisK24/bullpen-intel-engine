"""Bullpen Injury Context Layer 5.

This module measures neutral bullpen depth pressure from current roster status
data. It does not diagnose injuries, infer severity, predict return dates,
scrape news, alter availability, or change workload/fatigue scoring.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from services.availability_reference_date import product_current_date
from services.role_authority import (
    ROLE_AMBIGUOUS,
    ROLE_RELIEVER,
    ROLE_STARTER,
    ROLE_UNKNOWN,
    classify_role,
)
from services.roster_authority import (
    ROSTER_STATUS_CATEGORY_ACTIVE,
    ROSTER_STATUS_CATEGORY_INJURED_LIST,
    ROSTER_STATUS_CATEGORY_ORDER,
    ROSTER_STATUS_CATEGORY_UNKNOWN,
    roster_status_category_for_status,
)
from services.roster_status import (
    INACTIVE_STATUSES,
    STATUS_ACTIVE,
    STATUS_LABELS,
    STATUS_UNKNOWN,
    classify_roster_status,
)


CAPABILITY = 'injury_context_v1'
VERSION = '2026-06-21.layer5'

CONFIDENCE_HIGH = 'high'
CONFIDENCE_MEDIUM = 'medium'
CONFIDENCE_LOW = 'low'

DEPTH_PRESSURE_NONE = 'none'
DEPTH_PRESSURE_LIGHT = 'light'
DEPTH_PRESSURE_MODERATE = 'moderate'
DEPTH_PRESSURE_HEAVY = 'heavy'
DEPTH_PRESSURE_INSUFFICIENT_DATA = 'insufficient_data'

STATUS_TYPE_IL = 'IL'
STATUS_TYPE_NON_IL_INACTIVE = 'NON_IL_INACTIVE'

PITCHING_POSITIONS = {'P', 'SP', 'RP', 'CL'}
STARTER_POSITIONS = {'SP'}

# IL vs non-IL inactive is a split of Roster Authority's off-roster categories — the authority
# owns which statuses are injured vs otherwise off the roster, so this module no longer keeps
# its own status sets. Non-IL inactive = every off-roster category except the injured list
# (active and unknown are not off-roster). Deriving it from ROSTER_STATUS_CATEGORY_ORDER means
# a new off-roster category the authority adds is counted as non-IL depth here automatically.
_OFF_ROSTER_NON_IL_CATEGORIES = frozenset(ROSTER_STATUS_CATEGORY_ORDER) - {
    ROSTER_STATUS_CATEGORY_ACTIVE,
    ROSTER_STATUS_CATEGORY_INJURED_LIST,
    ROSTER_STATUS_CATEGORY_UNKNOWN,
}

ROSTER_STATUS_CONTEXT_LIMITATION = (
    'Injury context uses current roster/status data only; it does not diagnose injuries, infer severity, or predict returns.'
)
ACTIVE_AVAILABILITY_LIMITATION = (
    'Active bullpen count uses the same current availability population as BaseballOS bullpen planning.'
)
ROLE_UNCERTAINTY_LIMITATION = (
    'Some inactive pitchers have clear roster status but uncertain bullpen-vs-starter role.'
)
INCOMPLETE_ROSTER_STATUS_LIMITATION = (
    'Insufficient current roster/status data was available to produce bullpen-specific injury context.'
)
EXCLUSION_LIMITATION = (
    'Position players and safely identifiable starters are excluded from bullpen-specific inactive counts.'
)


def _value(obj: Any, name: str, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _date_value(value: Any):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _reference_date(reference_date=None):
    return _date_value(reference_date) or product_current_date()


def _pitcher_from_record(record):
    return _value(record, 'pitcher')


def _pitcher_id(pitcher):
    return _value(pitcher, 'id')


def _player_id(pitcher):
    return _value(pitcher, 'mlb_id') or _value(pitcher, 'player_id') or _pitcher_id(pitcher)


def _name(pitcher):
    return _value(pitcher, 'full_name') or _value(pitcher, 'name')


def _position(pitcher):
    return str(_value(pitcher, 'position', '') or '').strip().upper()


def _is_pitcher_position(pitcher):
    return _position(pitcher) in PITCHING_POSITIONS


def _is_starter_position(pitcher):
    return _position(pitcher) in STARTER_POSITIONS


def depth_pressure_band(inactive_count, *, context_available=True):
    if not context_available:
        return DEPTH_PRESSURE_INSUFFICIENT_DATA
    if inactive_count <= 0:
        return DEPTH_PRESSURE_NONE
    if inactive_count == 1:
        return DEPTH_PRESSURE_LIGHT
    if inactive_count <= 3:
        return DEPTH_PRESSURE_MODERATE
    return DEPTH_PRESSURE_HEAVY


def _inactive_share(active_count, inactive_count, *, context_available=True):
    if not context_available:
        return None
    total = active_count + inactive_count
    if total <= 0:
        return None
    return round(inactive_count / total * 100.0, 1)


def _status_type(status):
    category = roster_status_category_for_status(status)
    if category == ROSTER_STATUS_CATEGORY_INJURED_LIST:
        return STATUS_TYPE_IL
    if category in _OFF_ROSTER_NON_IL_CATEGORIES:
        return STATUS_TYPE_NON_IL_INACTIVE
    return None


def _status_label(roster_status):
    status = (roster_status or {}).get('status') or STATUS_UNKNOWN
    return (roster_status or {}).get('label') or STATUS_LABELS.get(status, STATUS_LABELS[STATUS_UNKNOWN])


def _is_active_record(record):
    availability = _value(record, 'availability') or {}
    if isinstance(availability, dict):
        roster_status = availability.get('roster_status') or {}
        if roster_status.get('is_active_mlb') is False:
            return False
    return _pitcher_from_record(record) is not None


def _active_pitcher_ids(active_records):
    return {
        _pitcher_id(_pitcher_from_record(record))
        for record in active_records or []
        if _is_active_record(record) and _pitcher_id(_pitcher_from_record(record)) is not None
    }


def _empty_context(reference_date=None):
    ref = _date_value(reference_date)
    band = DEPTH_PRESSURE_INSUFFICIENT_DATA
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': 'backend',
        'context_available': False,
        'reference_date': ref.isoformat() if ref else None,
        'active_bullpen_arms_count': 0,
        'inactive_bullpen_arms_count': 0,
        'il_bullpen_arms_count': 0,
        'non_il_inactive_bullpen_arms_count': 0,
        'inactive_bullpen_share': None,
        'depth_pressure_band': band,
        'injury_context_confidence': CONFIDENCE_LOW,
        'inactive_bullpen_arms': [],
        'injury_context_summary_inputs': {
            'active_count': 0,
            'inactive_count': 0,
            'il_count': 0,
            'non_il_inactive_count': 0,
            'inactive_share': None,
            'depth_pressure_band': band,
            'confidence': CONFIDENCE_LOW,
        },
        'excluded_position_player_count': 0,
        'excluded_starting_pitcher_count': 0,
        'role_uncertain_inactive_count': 0,
        'unknown_roster_status_count': 0,
        'limitations': [
            ROSTER_STATUS_CONTEXT_LIMITATION,
            ACTIVE_AVAILABILITY_LIMITATION,
            INCOMPLETE_ROSTER_STATUS_LIMITATION,
        ],
    }


def _inactive_arm(pitcher, roster_status):
    status = roster_status.get('status') or STATUS_UNKNOWN
    return {
        'player_id': _player_id(pitcher),
        'name': _name(pitcher),
        'status': _status_label(roster_status),
        'status_type': _status_type(status),
        'is_on_active_roster': False,
    }


def _sort_arms(arms):
    return sorted(
        arms,
        key=lambda arm: (
            str(arm.get('name') or '').lower(),
            arm.get('player_id') or 0,
        ),
    )


def _confidence(*, active_count, inactive_count, role_uncertain_count, unknown_status_count):
    if active_count == 0 and inactive_count == 0:
        return CONFIDENCE_LOW
    if role_uncertain_count or unknown_status_count:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_HIGH


def build_injury_context(
    pitchers,
    *,
    active_records=None,
    logs_by_pitcher=None,
    reference_date=None,
):
    """Build Bullpen Injury Context Layer 5 from roster/status data."""
    rows = list(pitchers or [])
    ref = _reference_date(reference_date)
    if not rows and not active_records:
        return _empty_context(reference_date=ref)

    logs_by_pitcher = logs_by_pitcher or {}
    active_ids = _active_pitcher_ids(active_records or [])
    active_count = len(active_ids)
    inactive_arms = []
    il_count = 0
    non_il_count = 0
    excluded_position_players = 0
    excluded_starters = 0
    role_uncertain_count = 0
    unknown_status_count = 0

    for pitcher in rows:
        roster_status = classify_roster_status(pitcher)
        status = roster_status.get('status') or STATUS_UNKNOWN
        if status == STATUS_UNKNOWN:
            unknown_status_count += 1
            continue
        if status == STATUS_ACTIVE:
            continue
        if status not in INACTIVE_STATUSES:
            continue
        if not _is_pitcher_position(pitcher):
            excluded_position_players += 1
            continue
        if _is_starter_position(pitcher):
            excluded_starters += 1
            continue

        role = classify_role(
            pitcher,
            logs_by_pitcher.get(_pitcher_id(pitcher), []),
            reference_date=ref,
        )
        role_name = role.get('role')
        if role_name == ROLE_STARTER:
            excluded_starters += 1
            continue
        if role_name == ROLE_UNKNOWN:
            role_uncertain_count += 1
        elif role_name not in {ROLE_RELIEVER, ROLE_AMBIGUOUS}:
            role_uncertain_count += 1

        status_type = _status_type(status)
        if status_type == STATUS_TYPE_IL:
            il_count += 1
        else:
            non_il_count += 1
        inactive_arms.append(_inactive_arm(pitcher, roster_status))

    inactive_count = len(inactive_arms)
    confidence = _confidence(
        active_count=active_count,
        inactive_count=inactive_count,
        role_uncertain_count=role_uncertain_count,
        unknown_status_count=unknown_status_count,
    )
    context_available = confidence != CONFIDENCE_LOW
    if not context_available:
        context = _empty_context(reference_date=ref)
        context.update({
            'excluded_position_player_count': excluded_position_players,
            'excluded_starting_pitcher_count': excluded_starters,
            'role_uncertain_inactive_count': role_uncertain_count,
            'unknown_roster_status_count': unknown_status_count,
        })
        return context

    share = _inactive_share(active_count, inactive_count, context_available=True)
    band = depth_pressure_band(inactive_count)
    limitations = [ROSTER_STATUS_CONTEXT_LIMITATION, ACTIVE_AVAILABILITY_LIMITATION]
    if role_uncertain_count:
        limitations.append(ROLE_UNCERTAINTY_LIMITATION)
    if unknown_status_count:
        limitations.append(INCOMPLETE_ROSTER_STATUS_LIMITATION)
    if excluded_position_players or excluded_starters:
        limitations.append(EXCLUSION_LIMITATION)

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': 'backend',
        'context_available': True,
        'reference_date': ref.isoformat(),
        'active_bullpen_arms_count': active_count,
        'inactive_bullpen_arms_count': inactive_count,
        'il_bullpen_arms_count': il_count,
        'non_il_inactive_bullpen_arms_count': non_il_count,
        'inactive_bullpen_share': share,
        'depth_pressure_band': band,
        'injury_context_confidence': confidence,
        'inactive_bullpen_arms': _sort_arms(inactive_arms),
        'injury_context_summary_inputs': {
            'active_count': active_count,
            'inactive_count': inactive_count,
            'il_count': il_count,
            'non_il_inactive_count': non_il_count,
            'inactive_share': share,
            'depth_pressure_band': band,
            'confidence': confidence,
        },
        'excluded_position_player_count': excluded_position_players,
        'excluded_starting_pitcher_count': excluded_starters,
        'role_uncertain_inactive_count': role_uncertain_count,
        'unknown_roster_status_count': unknown_status_count,
        'limitations': limitations,
    }


def empty_injury_context():
    """Return the normalized no-data Layer 5 context shape."""
    return _empty_context()


__all__ = [
    'CAPABILITY',
    'CONFIDENCE_HIGH',
    'CONFIDENCE_LOW',
    'CONFIDENCE_MEDIUM',
    'DEPTH_PRESSURE_HEAVY',
    'DEPTH_PRESSURE_INSUFFICIENT_DATA',
    'DEPTH_PRESSURE_LIGHT',
    'DEPTH_PRESSURE_MODERATE',
    'DEPTH_PRESSURE_NONE',
    'VERSION',
    'build_injury_context',
    'depth_pressure_band',
    'empty_injury_context',
]
