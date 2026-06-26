"""Team-level bullpen capacity and resource health intelligence.

This layer keeps two baseball questions separate:

* Bullpen Capacity: what does the manager have available tonight?
* Resource Health: how healthy is the broader bullpen resource pool?

It uses existing roster-status and availability reads only. It does not infer
injury severity, return timelines, medical context, recommendations, or future
availability.
"""

from __future__ import annotations

from typing import Any

from services.availability import STATUS_AVAILABLE, STATUS_UNAVAILABLE
from services.bullpen_eligibility_vocabulary import record_is_bullpen_eligible
from services.roster_authority import is_off_active_roster, is_roster_status_unknown
from services.roster_status import (
    STATUS_IL_10,
    STATUS_IL_15,
    STATUS_IL_60,
)


CAPABILITY = 'bullpen_resource_health_v1'
VERSION = '2026-06-19.v1_1'

STATE_HEALTHY = 'healthy'
STATE_REDUCED = 'reduced'
STATE_THIN = 'thin'
STATE_DEPLETED = 'depleted'
STATE_UNKNOWN = 'unknown'

RESOURCE_STATE_STRONG = 'strong'
RESOURCE_STATE_MODERATE = 'moderate'
RESOURCE_STATE_STRAINED = 'strained'
RESOURCE_STATE_DEPLETED = 'depleted'

INJURED_LIST_STATUSES = {
    STATUS_IL_10,
    STATUS_IL_15,
    STATUS_IL_60,
}

BULLPEN_CAPACITY_HEALTHY_MIN_ACTIVE = 8
BULLPEN_CAPACITY_REDUCED_MIN_ACTIVE = 7
BULLPEN_CAPACITY_THIN_MIN_ACTIVE = 5
BULLPEN_CAPACITY_HEALTHY_MIN_CLEAN_ACTIVE = 5
BULLPEN_CAPACITY_REDUCED_MIN_CLEAN_ACTIVE = 3
BULLPEN_CAPACITY_THIN_MIN_CLEAN_ACTIVE = 1

RESOURCE_HEALTH_STRONG_MIN_RATIO = 0.70
RESOURCE_HEALTH_MODERATE_MIN_RATIO = 0.60
RESOURCE_HEALTH_DEPLETED_BELOW_RATIO = 0.40

NO_RESOURCE_LIMITATION = (
    'Bullpen Resource Health is unknown because no bullpen resources were available to classify.'
)
INCOMPLETE_RESOURCE_LIMITATION = (
    'Bullpen Resource Health is unknown because roster or availability data is incomplete for one or more bullpen resources.'
)

DEFINITIONS = {
    'active_reliever_count': (
        'Active MLB bullpen resources not fully Unavailable in the current availability read.'
    ),
    'injured_reliever_count': (
        'Bullpen resources with an existing injured-list roster status. Severity, injury type, and return timeline are not inferred.'
    ),
    'unavailable_reliever_count': (
        'Bullpen resources unavailable for non-IL roster reasons or fully Unavailable in the current availability read.'
    ),
    'total_bullpen_resource_count': (
        'All bullpen-eligible resources passed to the health layer, including active, injured, unavailable, and unknown resources.'
    ),
    'resource_availability_ratio': (
        'Active relievers divided by total bullpen resources. Null means missing roster or availability data makes the ratio unsafe.'
    ),
    'capacity_state': (
        'Active bullpen capacity state: healthy, reduced, thin, depleted, or unknown.'
    ),
    'resource_health_state': (
        'Organizational bullpen resource pool state: strong, moderate, strained, depleted, or unknown.'
    ),
}

BULLPEN_CAPACITY_DEFINITIONS = {
    'healthy': 'Eight or more active bullpen resources are available tonight, with at least five clean active options.',
    'reduced': 'Seven or more active bullpen resources are available tonight, with at least three clean active options.',
    'thin': 'Five or more active bullpen resources are available tonight, with at least one clean active option.',
    'depleted': 'Four or fewer active bullpen resources are available tonight, or no clean active options remain.',
    'unknown': 'No resources were available to classify, or active roster/availability data is incomplete.',
}

RESOURCE_HEALTH_DEFINITIONS = {
    'strong': 'At least 70% of the known bullpen resource pool is active.',
    'moderate': 'At least 60% but less than 70% of the known bullpen resource pool is active.',
    'strained': 'At least 40% but less than 60% of the known bullpen resource pool is active.',
    'depleted': 'Less than 40% of the known bullpen resource pool is active, or no active bullpen resources remain.',
    'unknown': 'No resources were available to classify, or resource status data is incomplete.',
}


def _value(obj: Any, name: str, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _nested(mapping: dict[str, Any] | None, *keys, default=None):
    current = mapping or {}
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if current is not None else default


def _pitcher(record: dict[str, Any]) -> Any:
    return record.get('pitcher')


def _pitcher_id(record: dict[str, Any]) -> int | None:
    return (
        record.get('pitcher_id')
        or _value(_pitcher(record), 'id')
        or _value(record.get('pitcher'), 'pitcher_id')
    )


def _is_bullpen_record(record: dict[str, Any]) -> bool:
    return record_is_bullpen_eligible(record)


def _read_key(record: dict[str, Any]) -> str:
    return _nested(record.get('pitcher_labels'), 'read', 'key', default='') or ''


def _availability_status(record: dict[str, Any]) -> str:
    return str((record.get('availability') or {}).get('availability_status') or '')


def _roster_status(record: dict[str, Any]) -> dict[str, Any]:
    status = record.get('roster_status')
    return status if isinstance(status, dict) else {}


def _is_availability_unknown(record: dict[str, Any]) -> bool:
    return not _availability_status(record)


def _is_availability_unavailable(record: dict[str, Any]) -> bool:
    return (
        _read_key(record) == 'unavailable'
        or _availability_status(record) == STATUS_UNAVAILABLE
    )


def _team_identity(team):
    team = team or {}
    return {
        'team_id': team.get('team_id'),
        'team_name': team.get('team_name'),
        'team_abbreviation': team.get('team_abbreviation'),
    }


def _ratio(active_count: int, total_count: int, unknown_count: int):
    if total_count <= 0 or unknown_count > 0:
        return None
    return round(float(active_count) / float(total_count), 2)


def classify_bullpen_capacity_state(
    *,
    active_reliever_count: int,
    active_restricted_reliever_count: int = 0,
    total_bullpen_resource_count: int = 0,
    unknown_reliever_count: int = 0,
) -> str:
    """Classify active bullpen capacity from active MLB bullpen resources.

    Thresholds are intentionally baseball-shaped, not symmetric:
      - healthy: 8+ active bullpen resources and 5+ clean options.
      - reduced: 7+ active bullpen resources and 3+ clean options.
      - thin: 5+ active bullpen resources and 1+ clean option.
      - depleted: 4 or fewer active bullpen resources, or zero clean options.
      - unknown: no resources, or incomplete active roster/availability data.
    """
    total = int(total_bullpen_resource_count or 0)
    active = int(active_reliever_count or 0)
    restricted = int(active_restricted_reliever_count or 0)
    clean = max(active - restricted, 0)
    unknown = int(unknown_reliever_count or 0)

    if total <= 0 or unknown > 0:
        return STATE_UNKNOWN
    if (
        active >= BULLPEN_CAPACITY_HEALTHY_MIN_ACTIVE
        and clean >= BULLPEN_CAPACITY_HEALTHY_MIN_CLEAN_ACTIVE
    ):
        return STATE_HEALTHY
    if (
        active >= BULLPEN_CAPACITY_REDUCED_MIN_ACTIVE
        and clean >= BULLPEN_CAPACITY_REDUCED_MIN_CLEAN_ACTIVE
    ):
        return STATE_REDUCED
    if (
        active >= BULLPEN_CAPACITY_THIN_MIN_ACTIVE
        and clean >= BULLPEN_CAPACITY_THIN_MIN_CLEAN_ACTIVE
    ):
        return STATE_THIN
    return STATE_DEPLETED


def classify_resource_health_state(
    *,
    active_reliever_count: int,
    total_bullpen_resource_count: int,
    unknown_reliever_count: int = 0,
) -> str:
    """Classify organizational bullpen resource health from the total pool.

    Thresholds use the known active share of the broader bullpen resource pool:
      - strong: active share at or above 70%.
      - moderate: active share at or above 60% and below 70%.
      - strained: active share at or above 40% and below 60%.
      - depleted: active share below 40%, or zero active bullpen resources.
      - unknown: no resources, or incomplete status data.
    """
    total = int(total_bullpen_resource_count or 0)
    active = int(active_reliever_count or 0)
    unknown = int(unknown_reliever_count or 0)

    if total <= 0 or unknown > 0:
        return STATE_UNKNOWN
    if active <= 0:
        return RESOURCE_STATE_DEPLETED

    ratio = float(active) / float(total)
    if ratio < RESOURCE_HEALTH_DEPLETED_BELOW_RATIO:
        return RESOURCE_STATE_DEPLETED
    if ratio < RESOURCE_HEALTH_MODERATE_MIN_RATIO:
        return RESOURCE_STATE_STRAINED
    if ratio < RESOURCE_HEALTH_STRONG_MIN_RATIO:
        return RESOURCE_STATE_MODERATE
    return RESOURCE_STATE_STRONG


def classify_capacity_state(
    *,
    active_reliever_count: int,
    total_bullpen_resource_count: int,
    known_unavailable_count: int = 0,
    unknown_reliever_count: int = 0,
) -> str:
    """Backward-compatible alias for active bullpen capacity classification."""
    _ = known_unavailable_count
    return classify_bullpen_capacity_state(
        active_reliever_count=active_reliever_count,
        total_bullpen_resource_count=total_bullpen_resource_count,
        unknown_reliever_count=unknown_reliever_count,
    )


def _summary(
    capacity_state: str,
    resource_state: str,
    active: int,
    total: int,
    injured: int,
    unavailable: int,
    unknown: int,
) -> str:
    if capacity_state == STATE_UNKNOWN or resource_state == STATE_UNKNOWN:
        if total <= 0:
            return 'Bullpen resource health is unknown because no bullpen resources were available to classify.'
        return 'Bullpen resource health is unknown because part of the roster or availability picture is incomplete.'
    unavailable_total = injured + unavailable
    if unavailable_total <= 0:
        return f'Active bullpen capacity is {capacity_state}; {active} of {total} bullpen resources are active.'
    return (
        f'Active bullpen capacity is {capacity_state}; organizational resource health is {resource_state} '
        f'with {active} of {total} bullpen resources active and {unavailable_total} unavailable or on the injured list.'
    )


def build_bullpen_resource_health(
    records,
    *,
    team=None,
):
    """Build serializable bullpen resource health for one team."""
    active_count = 0
    injured_count = 0
    unavailable_count = 0
    roster_unavailable_count = 0
    workload_unavailable_count = 0
    active_restricted_count = 0
    active_unknown_count = 0
    unknown_count = 0
    total_count = 0

    for record in records or []:
        if not isinstance(record, dict) or not _is_bullpen_record(record):
            continue
        if _pitcher_id(record) is None:
            continue

        total_count += 1
        roster_status = _roster_status(record)

        if is_roster_status_unknown(roster_status):
            unknown_count += 1
            active_unknown_count += 1
            continue

        status = roster_status.get('status')
        if status in INJURED_LIST_STATUSES:
            injured_count += 1
            continue

        roster_unavailable = is_off_active_roster(roster_status)
        if roster_unavailable:
            unavailable_count += 1
            roster_unavailable_count += 1
            continue

        if _is_availability_unknown(record):
            unknown_count += 1
            active_unknown_count += 1
            continue

        availability_unavailable = _is_availability_unavailable(record)
        if availability_unavailable:
            unavailable_count += 1
            workload_unavailable_count += 1
            continue

        if _availability_status(record) != STATUS_AVAILABLE:
            active_restricted_count += 1
        active_count += 1

    capacity_state = classify_bullpen_capacity_state(
        active_reliever_count=active_count,
        active_restricted_reliever_count=active_restricted_count,
        total_bullpen_resource_count=total_count,
        unknown_reliever_count=active_unknown_count,
    )
    resource_health_state = classify_resource_health_state(
        active_reliever_count=active_count,
        total_bullpen_resource_count=total_count,
        unknown_reliever_count=unknown_count,
    )
    limitations = []
    if total_count <= 0:
        limitations.append(NO_RESOURCE_LIMITATION)
    if unknown_count > 0:
        limitations.append(INCOMPLETE_RESOURCE_LIMITATION)

    ratio = _ratio(active_count, total_count, unknown_count)
    identity = _team_identity(team)
    bullpen_capacity = {
        'state': capacity_state,
        'capacity_state': capacity_state,
        'active_reliever_count': active_count,
        'clean_active_reliever_count': max(active_count - active_restricted_count, 0),
        'active_restricted_reliever_count': active_restricted_count,
        'active_unknown_reliever_count': active_unknown_count,
        'thresholds': {
            'healthy_min_active_relievers': BULLPEN_CAPACITY_HEALTHY_MIN_ACTIVE,
            'healthy_min_clean_active_relievers': BULLPEN_CAPACITY_HEALTHY_MIN_CLEAN_ACTIVE,
            'reduced_min_active_relievers': BULLPEN_CAPACITY_REDUCED_MIN_ACTIVE,
            'reduced_min_clean_active_relievers': BULLPEN_CAPACITY_REDUCED_MIN_CLEAN_ACTIVE,
            'thin_min_active_relievers': BULLPEN_CAPACITY_THIN_MIN_ACTIVE,
            'thin_min_clean_active_relievers': BULLPEN_CAPACITY_THIN_MIN_CLEAN_ACTIVE,
            'depleted_max_active_relievers': BULLPEN_CAPACITY_THIN_MIN_ACTIVE - 1,
        },
        'definitions': dict(BULLPEN_CAPACITY_DEFINITIONS),
    }
    organizational_resource_health = {
        'state': resource_health_state,
        'resource_health_state': resource_health_state,
        'active_reliever_count': active_count,
        'injured_reliever_count': injured_count,
        'unavailable_reliever_count': unavailable_count,
        'total_bullpen_resource_count': total_count,
        'resource_availability_ratio': ratio,
        'thresholds': {
            'strong_min_ratio': RESOURCE_HEALTH_STRONG_MIN_RATIO,
            'moderate_min_ratio': RESOURCE_HEALTH_MODERATE_MIN_RATIO,
            'depleted_below_ratio': RESOURCE_HEALTH_DEPLETED_BELOW_RATIO,
        },
        'definitions': dict(RESOURCE_HEALTH_DEFINITIONS),
    }
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': 'backend',
        'team': identity.get('team_abbreviation'),
        **identity,
        'active_reliever_count': active_count,
        'injured_reliever_count': injured_count,
        'unavailable_reliever_count': unavailable_count,
        'roster_unavailable_reliever_count': roster_unavailable_count,
        'workload_unavailable_reliever_count': workload_unavailable_count,
        'unknown_reliever_count': unknown_count,
        'total_bullpen_resource_count': total_count,
        'resource_availability_ratio': ratio,
        'capacity_state': capacity_state,
        'resource_health_state': resource_health_state,
        'bullpen_capacity': bullpen_capacity,
        'organizational_resource_health': organizational_resource_health,
        'confidence': 'none' if total_count <= 0 else 'low' if unknown_count > 0 else 'high',
        'summary': _summary(
            capacity_state,
            resource_health_state,
            active_count,
            total_count,
            injured_count,
            unavailable_count,
            unknown_count,
        ),
        'thresholds': {
            'bullpen_capacity': bullpen_capacity['thresholds'],
            'organizational_resource_health': organizational_resource_health['thresholds'],
        },
        'definitions': dict(DEFINITIONS),
        'limitations': limitations,
    }


__all__ = [
    'BULLPEN_CAPACITY_HEALTHY_MIN_ACTIVE',
    'BULLPEN_CAPACITY_HEALTHY_MIN_CLEAN_ACTIVE',
    'BULLPEN_CAPACITY_REDUCED_MIN_ACTIVE',
    'BULLPEN_CAPACITY_REDUCED_MIN_CLEAN_ACTIVE',
    'BULLPEN_CAPACITY_THIN_MIN_ACTIVE',
    'BULLPEN_CAPACITY_THIN_MIN_CLEAN_ACTIVE',
    'CAPABILITY',
    'INCOMPLETE_RESOURCE_LIMITATION',
    'NO_RESOURCE_LIMITATION',
    'RESOURCE_HEALTH_DEPLETED_BELOW_RATIO',
    'RESOURCE_HEALTH_MODERATE_MIN_RATIO',
    'RESOURCE_HEALTH_STRONG_MIN_RATIO',
    'RESOURCE_STATE_DEPLETED',
    'RESOURCE_STATE_MODERATE',
    'RESOURCE_STATE_STRAINED',
    'RESOURCE_STATE_STRONG',
    'STATE_DEPLETED',
    'STATE_HEALTHY',
    'STATE_REDUCED',
    'STATE_THIN',
    'STATE_UNKNOWN',
    'VERSION',
    'build_bullpen_resource_health',
    'classify_bullpen_capacity_state',
    'classify_capacity_state',
    'classify_resource_health_state',
]
