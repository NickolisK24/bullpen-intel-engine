"""Internal bullpen trust hierarchy intelligence.

This layer answers a bounded, descriptive question: which bullpen resources
appear most structurally important to the current bullpen group?

It is deterministic and conservative. It does not select a pitcher, recommend
usage, predict availability, rank players for tactical decisions, or override
existing roster/availability governance.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from services.availability import STATUS_AVAILABLE, STATUS_UNAVAILABLE
from services.bullpen_eligibility_vocabulary import (
    record_is_bullpen_eligible,
    record_is_swing_bulk,
)
from services.roster_authority import is_off_active_roster, is_on_active_roster


CAPABILITY = 'bullpen_trust_hierarchy_v1'
VERSION = '2026-06-19'

BUCKET_ANCHOR = 'anchor'
BUCKET_LEVERAGE = 'leverage'
BUCKET_TRUSTED = 'trusted'
BUCKET_DEPTH = 'depth'
BUCKET_UNKNOWN = 'unknown'

BUCKET_ORDER = [
    BUCKET_ANCHOR,
    BUCKET_LEVERAGE,
    BUCKET_TRUSTED,
    BUCKET_DEPTH,
    BUCKET_UNKNOWN,
]

ROLE_TRUST_ARM = 'trust_arm'
ROLE_BRIDGE_ARM = 'bridge_arm'
ROLE_COVERAGE_ARM = 'coverage_arm'
ROLE_DEPTH_ARM = 'depth_arm'
ROLE_LIMITED_READ = 'limited_read'

READ_CLEAN = 'clean_option'
READ_WATCH = 'watch_arm'
READ_RESTRICTED = 'rest_restricted'
READ_UNAVAILABLE = 'unavailable'
READ_LIMITED = 'limited_read'

OBSERVED_LATE = 'late_high_leverage'
OBSERVED_SETUP = 'setup_bridge'
OBSERVED_MIDDLE = 'middle_relief'
OBSERVED_LONG = 'long_multi_inning'
OBSERVED_LOW = 'low_unclear'
OBSERVED_INSUFFICIENT = 'insufficient_data'

LATE_USAGE_KEYS = {OBSERVED_LATE}
LEVERAGE_USAGE_KEYS = {OBSERVED_LATE, OBSERVED_SETUP}
REGULAR_USAGE_KEYS = {OBSERVED_LATE, OBSERVED_SETUP, OBSERVED_MIDDLE}
DEPTH_USAGE_KEYS = {OBSERVED_LONG, OBSERVED_LOW}

LIMITED_DATA_STATES = {'stale', 'missing', 'incomplete', 'failed', 'historical', 'unknown'}
UNKNOWN_CONFIDENCE = {'none', 'unknown'}
WEAK_CONFIDENCE = {'none', 'unknown', 'low'}

SEASON_RELIEF_OUTS_TRUSTED_FLOOR = 30
RECENT_APPEARANCES_TRUSTED_FLOOR = 3
ANCHOR_MIN_RECENT_APPEARANCES = 10
ANCHOR_MIN_SAVE_FINISHES = 3

NO_HIERARCHY_LIMITATION = (
    'Trust Hierarchy is unknown because no active bullpen resources were available to classify.'
)
LIMITED_HIERARCHY_LIMITATION = (
    'Trust Hierarchy uses conservative buckets because one or more bullpen resources have limited role or availability data.'
)

BUCKET_DEFINITIONS = {
    BUCKET_ANCHOR: (
        'Active clean bullpen resource with repeated late-inning or high-leverage pillar signals.'
    ),
    BUCKET_LEVERAGE: (
        'Active bullpen resource with late/setup usage or Trust Arm signals, but short of the anchor threshold.'
    ),
    BUCKET_TRUSTED: (
        'Active bullpen resource with regular bridge/middle usage or enough relief workload to matter.'
    ),
    BUCKET_DEPTH: (
        'Active bullpen resource with coverage, depth, restricted, or limited trust signals.'
    ),
    BUCKET_UNKNOWN: (
        'Bullpen resource without enough active roster, availability, or role evidence for a stronger bucket.'
    ),
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


def _norm(value: Any) -> str:
    return str(value or '').strip().lower()


def _pitcher(record: dict[str, Any]) -> Any:
    return record.get('pitcher')


def _pitcher_id(record: dict[str, Any]) -> int | None:
    return (
        record.get('pitcher_id')
        or _value(_pitcher(record), 'id')
        or _value(record.get('pitcher'), 'pitcher_id')
    )


def _pitcher_name(record: dict[str, Any]) -> str | None:
    return record.get('name') or _value(_pitcher(record), 'full_name')


def _team_identity(team):
    team = team or {}
    return {
        'team_id': team.get('team_id'),
        'team_name': team.get('team_name'),
        'team_abbreviation': team.get('team_abbreviation'),
    }


def _is_bullpen_record(record: dict[str, Any]) -> bool:
    return record_is_bullpen_eligible(record)


def _roster_status(record: dict[str, Any]) -> dict[str, Any]:
    status = record.get('roster_status')
    return status if isinstance(status, dict) else {}


def _availability(record: dict[str, Any]) -> dict[str, Any]:
    availability = record.get('availability')
    return availability if isinstance(availability, dict) else {}


def _role(record: dict[str, Any]) -> dict[str, Any]:
    role = record.get('role')
    return role if isinstance(role, dict) else {}


def _role_label_key(record: dict[str, Any]) -> str:
    return _norm(_nested(record.get('pitcher_labels'), 'role', 'key', default=''))


def _read_key(record: dict[str, Any]) -> str:
    return _norm(_nested(record.get('pitcher_labels'), 'read', 'key', default=''))


def _observed_role_key(record: dict[str, Any]) -> str:
    role = _role(record)
    return _norm(role.get('role_key') or role.get('key') or role.get('role_type'))


def _role_confidence(record: dict[str, Any]) -> str:
    role = _role(record)
    return _norm(role.get('confidence') or role.get('role_confidence') or role.get('usage_confidence'))


def _availability_status(record: dict[str, Any]) -> str:
    return str(_availability(record).get('availability_status') or '')




def _is_availability_unavailable(record: dict[str, Any]) -> bool:
    return _read_key(record) == READ_UNAVAILABLE or _availability_status(record) == STATUS_UNAVAILABLE


def _is_clean_option(record: dict[str, Any]) -> bool:
    return _read_key(record) == READ_CLEAN and _availability_status(record) == STATUS_AVAILABLE


def _is_limited_read(record: dict[str, Any]) -> bool:
    availability = _availability(record)
    data_state = _norm(availability.get('data_state'))
    confidence = _norm(availability.get('confidence'))
    return (
        _read_key(record) == READ_LIMITED
        or _role_label_key(record) == ROLE_LIMITED_READ
        or data_state in LIMITED_DATA_STATES
        or confidence in UNKNOWN_CONFIDENCE
    )


def _role_sample_size(record: dict[str, Any]) -> int | None:
    role = _role(record)
    for key in (
        'sample_size',
        'usage_sample_size',
        'appearance_count',
        'appearances',
        'recent_appearances',
        'recent_outings',
        'relief_appearances',
    ):
        value = role.get(key)
        if isinstance(value, (int, float)):
            return int(value)
        if isinstance(value, str) and value.strip().isdigit():
            return int(value)
        if isinstance(value, (list, tuple)):
            return len(value)

    text = ' '.join(str(item or '') for item in (role.get('evidence') or []))
    match = re.search(r'\b(\d+)\s+(?:appearance|appearances|outing|outings)\b', text.lower())
    if match:
        return int(match.group(1))
    return None


def _role_evidence_text(record: dict[str, Any]) -> str:
    role = _role(record)
    evidence = role.get('evidence') or []
    if isinstance(evidence, str):
        return evidence.lower()
    return ' '.join(str(item or '') for item in evidence).lower()


def _role_evidence_count(record: dict[str, Any], pattern: str) -> int:
    match = re.search(pattern, _role_evidence_text(record))
    if not match:
        return 0
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return 0


def _save_finish_count(record: dict[str, Any]) -> int:
    return _role_evidence_count(
        record,
        r'\b(\d+)\s+save situation finish(?:\(es\)|es)? recorded\b',
    )


def _relief_outs(relief_outs_by_pitcher: dict[int, int] | None, pitcher_id: int) -> int:
    try:
        return int((relief_outs_by_pitcher or {}).get(int(pitcher_id), 0) or 0)
    except (TypeError, ValueError):
        return 0


def _availability_state(record: dict[str, Any]) -> str:
    if is_off_active_roster(_roster_status(record)) or _is_availability_unavailable(record):
        return 'unavailable'
    if _read_key(record) == READ_CLEAN:
        return 'clean'
    if _read_key(record) in {READ_WATCH, READ_RESTRICTED}:
        return _read_key(record)
    if _read_key(record) == READ_LIMITED:
        return 'limited_read'
    return _norm(_availability_status(record)) or 'unknown'


def _has_trusted_workload(record: dict[str, Any], season_relief_outs: int) -> bool:
    appearances = _role_sample_size(record)
    return (
        season_relief_outs >= SEASON_RELIEF_OUTS_TRUSTED_FLOOR
        or (appearances is not None and appearances >= RECENT_APPEARANCES_TRUSTED_FLOOR)
    )


def _has_anchor_evidence(record: dict[str, Any]) -> bool:
    appearances = _role_sample_size(record) or 0
    confidence = _role_confidence(record)
    return (
        appearances >= ANCHOR_MIN_RECENT_APPEARANCES
        and (
            confidence == 'high'
            or _save_finish_count(record) >= ANCHOR_MIN_SAVE_FINISHES
        )
    )


def _bucket_for(record: dict[str, Any], season_relief_outs: int) -> tuple[str, str]:
    role_key = _role_label_key(record)
    read_key = _read_key(record)
    observed_key = _observed_role_key(record)
    confidence = _role_confidence(record)
    clean = _is_clean_option(record)
    trusted_workload = _has_trusted_workload(record, season_relief_outs)

    if not is_on_active_roster(_roster_status(record)):
        return BUCKET_UNKNOWN, 'Not an active MLB bullpen resource.'
    if is_off_active_roster(_roster_status(record)) or _is_availability_unavailable(record):
        return BUCKET_UNKNOWN, 'Unavailable resources are not assigned active trust buckets.'
    if observed_key == OBSERVED_INSUFFICIENT:
        return BUCKET_UNKNOWN, 'Insufficient observed usage prevents a stronger bucket.'
    if _is_limited_read(record) and not trusted_workload:
        return BUCKET_UNKNOWN, 'Limited role or availability data prevents a stronger bucket.'
    if record_is_swing_bulk(record):
        return BUCKET_DEPTH, 'Swing/bulk role contributes to depth, not the trust or bridge lane.'

    strong_confidence = confidence not in WEAK_CONFIDENCE

    if (
        clean
        and role_key == ROLE_TRUST_ARM
        and observed_key in LATE_USAGE_KEYS
        and strong_confidence
        and _has_anchor_evidence(record)
    ):
        return BUCKET_ANCHOR, 'Clean Trust Arm with repeated late-inning or high-leverage pillar signals.'

    if (
        role_key == ROLE_TRUST_ARM
        or observed_key in LEVERAGE_USAGE_KEYS
    ) and (strong_confidence or trusted_workload):
        return BUCKET_LEVERAGE, 'Late/setup usage or Trust Arm signals are present.'

    if role_key in {ROLE_COVERAGE_ARM, ROLE_DEPTH_ARM} or observed_key in DEPTH_USAGE_KEYS or read_key in {READ_WATCH, READ_RESTRICTED}:
        return BUCKET_DEPTH, 'Coverage, depth, restricted, or low-usage signals are present.'

    if (
        role_key == ROLE_BRIDGE_ARM
        or observed_key in REGULAR_USAGE_KEYS
        or trusted_workload
    ):
        return BUCKET_TRUSTED, 'Regular usage or bridge workload signals are present.'

    return BUCKET_UNKNOWN, 'No strong enough role or usage signal is available.'


def classify_trust_bucket(record: dict[str, Any], *, relief_outs_by_pitcher=None) -> dict[str, Any] | None:
    """Classify one bullpen record into a conservative trust bucket."""
    if not isinstance(record, dict) or not _is_bullpen_record(record):
        return None
    pitcher_id = _pitcher_id(record)
    if pitcher_id is None:
        return None

    pitcher_id = int(pitcher_id)
    season_relief_outs = _relief_outs(relief_outs_by_pitcher, pitcher_id)
    bucket, reason = _bucket_for(record, season_relief_outs)
    active_resource = (
        is_on_active_roster(_roster_status(record))
        and not is_off_active_roster(_roster_status(record))
        and not _is_availability_unavailable(record)
    )
    clean = _is_clean_option(record)

    return {
        'pitcher_id': pitcher_id,
        'name': _pitcher_name(record),
        'bucket': bucket,
        'availability_state': _availability_state(record),
        'is_active_bullpen_resource': active_resource,
        'is_clean_option': clean,
        'role_key': _role_label_key(record) or None,
        'read_key': _read_key(record) or None,
        'observed_role_key': _observed_role_key(record) or None,
        'role_confidence': _role_confidence(record) or None,
        'season_relief_outs': season_relief_outs,
        'reason': reason,
    }


def _confidence(records: list[dict[str, Any]], trusted_group_size: int, unknown_count: int) -> str:
    active_count = sum(1 for record in records if record.get('is_active_bullpen_resource'))
    if active_count <= 0:
        return 'none'
    if active_count >= 5 and trusted_group_size >= 2 and unknown_count <= 1:
        return 'high'
    if active_count >= 3 and trusted_group_size >= 1:
        return 'medium'
    return 'low'


def _sort_key(record: dict[str, Any]):
    bucket = record.get('bucket')
    return (
        BUCKET_ORDER.index(bucket) if bucket in BUCKET_ORDER else len(BUCKET_ORDER),
        str(record.get('name') or ''),
        int(record.get('pitcher_id') or 0),
    )


def _top_bucket(records: list[dict[str, Any]]) -> str | None:
    for bucket in (BUCKET_ANCHOR, BUCKET_LEVERAGE, BUCKET_TRUSTED, BUCKET_DEPTH):
        if any(record.get('bucket') == bucket for record in records):
            return bucket
    return None


def build_bullpen_trust_hierarchy(
    records,
    *,
    team=None,
    relief_outs_by_pitcher=None,
    include_pitchers=True,
):
    """Build a serializable team bullpen trust hierarchy payload."""
    classified = [
        item
        for item in (
            classify_trust_bucket(record, relief_outs_by_pitcher=relief_outs_by_pitcher)
            for record in (records or [])
        )
        if item is not None
    ]
    classified = sorted(classified, key=_sort_key)
    counts = Counter(record['bucket'] for record in classified)
    trusted_group_size = (
        counts[BUCKET_ANCHOR]
        + counts[BUCKET_LEVERAGE]
        + counts[BUCKET_TRUSTED]
    )
    top_bucket = _top_bucket(classified)
    top_bucket_available_count = (
        sum(
            1
            for record in classified
            if record.get('bucket') == top_bucket
            and record.get('is_active_bullpen_resource')
        )
        if top_bucket else 0
    )
    confidence = _confidence(classified, trusted_group_size, counts[BUCKET_UNKNOWN])
    limitations = []
    if not any(record.get('is_active_bullpen_resource') for record in classified):
        limitations.append(NO_HIERARCHY_LIMITATION)
    if counts[BUCKET_UNKNOWN] > 0:
        limitations.append(LIMITED_HIERARCHY_LIMITATION)

    identity = _team_identity(team)
    payload = {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': 'backend',
        'team': identity.get('team_abbreviation'),
        **identity,
        'anchor_count': counts[BUCKET_ANCHOR],
        'leverage_count': counts[BUCKET_LEVERAGE],
        'trusted_count': counts[BUCKET_TRUSTED],
        'depth_count': counts[BUCKET_DEPTH],
        'unknown_count': counts[BUCKET_UNKNOWN],
        'trusted_group_size': trusted_group_size,
        'top_trust_bucket': top_bucket,
        'top_trust_bucket_available_count': top_bucket_available_count,
        'hierarchy_confidence': confidence,
        'bucket_counts': {bucket: counts[bucket] for bucket in BUCKET_ORDER},
        'bucket_definitions': dict(BUCKET_DEFINITIONS),
        'ranking_applied': False,
        'selection_made': False,
        'prediction_applied': False,
        'internal_ordering_basis': (
            'bucket order, then pitcher name, then pitcher id; not a tactical ranking.'
        ),
        'limitations': limitations,
    }
    if include_pitchers:
        payload['pitchers'] = classified
    return payload


__all__ = [
    'BUCKET_ANCHOR',
    'BUCKET_DEPTH',
    'BUCKET_LEVERAGE',
    'BUCKET_ORDER',
    'BUCKET_TRUSTED',
    'BUCKET_UNKNOWN',
    'CAPABILITY',
    'ANCHOR_MIN_RECENT_APPEARANCES',
    'ANCHOR_MIN_SAVE_FINISHES',
    'NO_HIERARCHY_LIMITATION',
    'LIMITED_HIERARCHY_LIMITATION',
    'VERSION',
    'build_bullpen_trust_hierarchy',
    'classify_trust_bucket',
]
