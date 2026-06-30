"""Coverage Safety V2 for team bullpen reads.

This layer describes how much coverage room the bullpen has if a game requires
multiple relief innings. It combines already-authored capacity, resource health,
and trust hierarchy reads. It does not select pitchers, forecast performance, or
simulate game paths.
"""

from __future__ import annotations

from typing import Any


CAPABILITY = 'bullpen_coverage_safety_v2'
VERSION = '2026-06-19'

LABEL_STRONG = 'Strong Coverage Safety'
LABEL_STABLE = 'Stable Coverage Safety'
LABEL_THIN = 'Thin Coverage Safety'
LABEL_LIMITED = 'Limited Coverage Safety'
LABEL_LIMITED_READ = 'Limited Read'

CAPACITY_HEALTHY = 'healthy'
CAPACITY_REDUCED = 'reduced'
CAPACITY_THIN = 'thin'
CAPACITY_DEPLETED = 'depleted'
CAPACITY_UNKNOWN = 'unknown'

RESOURCE_STRONG = 'strong'
RESOURCE_MODERATE = 'moderate'
RESOURCE_STRAINED = 'strained'
RESOURCE_DEPLETED = 'depleted'
RESOURCE_UNKNOWN = 'unknown'

ENVIRONMENT_PRESSURE = 'pressure_with_context'
ENVIRONMENT_MULTI_SOURCE = 'multi_source_pressure'

STRONG_MIN_CLEAN_ACTIVE = 5
STABLE_MIN_CLEAN_ACTIVE = 3
STRONG_MIN_TRUSTED_GROUP = 5
STABLE_MIN_TRUSTED_GROUP = 4
THIN_MIN_TRUSTED_GROUP = 2
STABLE_MIN_LEVERAGE_GROUP = 2
THIN_TRUST_UNAVAILABLE_MIN = 2
THIN_TRUST_UNAVAILABLE_PCT = 40

MISSING_INPUT_LIMITATION = (
    'There is not enough stored bullpen context to read multi-inning coverage yet.'
)
UNKNOWN_INPUT_LIMITATION = (
    'There is not enough stored bullpen context to read multi-inning coverage yet.'
)

COUNT_WORDS = {
    0: 'no',
    1: 'one',
    2: 'two',
    3: 'three',
    4: 'four',
    5: 'five',
    6: 'six',
    7: 'seven',
    8: 'eight',
    9: 'nine',
    10: 'ten',
    11: 'eleven',
    12: 'twelve',
}


def _get(mapping: dict[str, Any] | None, *keys, default=None):
    current = mapping or {}
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if current is not None else default


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _number(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _count_word(value):
    count = _int(value)
    return COUNT_WORDS.get(count, 'more than twelve')


def _reliever_phrase(count, noun='reliever'):
    count = _int(count)
    plural = f'{noun}s'
    return f'{_count_word(count)} {noun if count == 1 else plural}'


def _has_v2_inputs(capacity_intelligence: dict[str, Any] | None) -> bool:
    if not isinstance(capacity_intelligence, dict) or not capacity_intelligence:
        return False
    return (
        isinstance(capacity_intelligence.get('resource_health'), dict)
        and isinstance(capacity_intelligence.get('trust_hierarchy'), dict)
    )


def _evidence(capacity_intelligence, bullpen_environment):
    resource_health = capacity_intelligence.get('resource_health') or {}
    bullpen_capacity = resource_health.get('bullpen_capacity') or {}
    trust_hierarchy = capacity_intelligence.get('trust_hierarchy') or {}
    trust_capacity_loss = capacity_intelligence.get('trust_capacity_loss') or {}

    capacity_state = (
        bullpen_capacity.get('capacity_state')
        or bullpen_capacity.get('state')
        or resource_health.get('capacity_state')
        or CAPACITY_UNKNOWN
    )
    resource_state = (
        resource_health.get('resource_health_state')
        or _get(resource_health, 'organizational_resource_health', 'resource_health_state')
        or RESOURCE_UNKNOWN
    )
    active = _int(
        bullpen_capacity.get('active_reliever_count')
        or resource_health.get('active_reliever_count')
    )
    clean = _int(
        bullpen_capacity.get('clean_active_reliever_count'),
        default=max(active - _int(bullpen_capacity.get('active_restricted_reliever_count')), 0),
    )
    anchor = _int(trust_hierarchy.get('anchor_count'))
    leverage = _int(trust_hierarchy.get('leverage_count'))
    trusted = _int(trust_hierarchy.get('trusted_count'))
    trusted_group = _int(
        trust_hierarchy.get('trusted_group_size'),
        default=anchor + leverage + trusted,
    )
    top_available = _int(trust_hierarchy.get('top_trust_bucket_available_count'))
    trust_unavailable = _int(trust_capacity_loss.get('trust_arms_unavailable'))
    trust_unavailable_pct = _number(trust_capacity_loss.get('trust_capacity_unavailable_pct'))
    hierarchy_confidence = str(trust_hierarchy.get('hierarchy_confidence') or '').strip().lower()
    environment_status = str((bullpen_environment or {}).get('status') or '').strip().lower()
    environment_sources = list((bullpen_environment or {}).get('primary_pressure_sources') or [])

    return {
        'capacity_state': str(capacity_state or CAPACITY_UNKNOWN),
        'resource_health_state': str(resource_state or RESOURCE_UNKNOWN),
        'active_reliever_count': active,
        'clean_active_reliever_count': clean,
        'anchor_count': anchor,
        'leverage_count': leverage,
        'trusted_count': trusted,
        'trusted_group_size': trusted_group,
        'top_trust_bucket_available_count': top_available,
        'trust_arms_unavailable': trust_unavailable,
        'trust_capacity_unavailable_pct': round(trust_unavailable_pct),
        'hierarchy_confidence': hierarchy_confidence,
        'environment_status': environment_status,
        'environment_pressure_sources': environment_sources,
        'leverage_group_size': anchor + leverage,
    }


def _limited_read(evidence):
    return (
        LABEL_LIMITED_READ,
        [
            (
                'BaseballOS cannot yet say how much room this bullpen has if the starter exits early. '
                'This is a data-limited note, not a statement about injury status or manager intent.'
            )
        ],
        [UNKNOWN_INPUT_LIMITATION],
    )


def _base_label(evidence):
    capacity_state = evidence['capacity_state']
    resource_state = evidence['resource_health_state']
    hierarchy_confidence = evidence['hierarchy_confidence']
    active = evidence['active_reliever_count']
    clean = evidence['clean_active_reliever_count']
    trusted_group = evidence['trusted_group_size']
    top_available = evidence['top_trust_bucket_available_count']
    trust_unavailable = evidence['trust_arms_unavailable']
    trust_unavailable_pct = evidence['trust_capacity_unavailable_pct']
    anchor = evidence['anchor_count']
    leverage_group = evidence['leverage_group_size']

    if (
        capacity_state in {'', CAPACITY_UNKNOWN}
        or resource_state in {'', RESOURCE_UNKNOWN}
        or hierarchy_confidence in {'', 'none', 'unknown'}
    ):
        return _limited_read(evidence)

    reasons = [
        (
            f'The bullpen has {_reliever_phrase(active)} active in the stored board, '
            f'with {_reliever_phrase(clean)} rested enough to cover innings.'
        ),
        (
            f'The wider relief picture is {resource_state}, with {_reliever_phrase(anchor, "late anchor")} '
            f'and {_reliever_phrase(evidence["leverage_count"], "leverage arm")} near the back of the game.'
        ),
    ]

    if capacity_state == CAPACITY_DEPLETED or resource_state == RESOURCE_DEPLETED:
        return LABEL_LIMITED, [
            'Coverage is limited because the stored bullpen pool is depleted.'
        ], []
    if active <= 4 or clean <= 0:
        return LABEL_LIMITED, [
            'Coverage is limited because too few rested relievers remain.'
        ], []
    if trusted_group <= 1 or top_available <= 0:
        return LABEL_LIMITED, [
            'Coverage is limited because the late-inning support layer is too thin.'
        ], []

    trust_loss_material = (
        trust_unavailable >= THIN_TRUST_UNAVAILABLE_MIN
        or trust_unavailable_pct >= THIN_TRUST_UNAVAILABLE_PCT
    )
    if capacity_state == CAPACITY_THIN or clean <= 2 or trust_loss_material:
        reasons.append('Coverage reads thin because the rested group or late-inning availability is already tight.')
        return LABEL_THIN, reasons, []

    strong_shape = (
        capacity_state == CAPACITY_HEALTHY
        and resource_state in {RESOURCE_STRONG, RESOURCE_MODERATE}
        and clean >= STRONG_MIN_CLEAN_ACTIVE
        and anchor >= 1
        and trusted_group >= STRONG_MIN_TRUSTED_GROUP
        and top_available >= 1
        and trust_unavailable == 0
        and hierarchy_confidence in {'medium', 'high'}
    )
    if strong_shape:
        reasons.append('Coverage reads strong because rested relief, late-inning depth, and top-end availability all align.')
        return LABEL_STRONG, reasons, []

    if resource_state == RESOURCE_STRAINED:
        if (
            capacity_state == CAPACITY_HEALTHY
            and clean >= STRONG_MIN_CLEAN_ACTIVE
            and trusted_group >= STRONG_MIN_TRUSTED_GROUP
            and leverage_group >= STABLE_MIN_LEVERAGE_GROUP
        ):
            reasons.append('The wider relief pool is strained, so coverage holds at stable rather than strong.')
            return LABEL_STABLE, reasons, []
        reasons.append('Coverage reads thin because the wider relief pool is strained.')
        return LABEL_THIN, reasons, []

    stable_shape = (
        capacity_state in {CAPACITY_HEALTHY, CAPACITY_REDUCED}
        and resource_state in {RESOURCE_STRONG, RESOURCE_MODERATE}
        and clean >= STABLE_MIN_CLEAN_ACTIVE
        and trusted_group >= STABLE_MIN_TRUSTED_GROUP
        and leverage_group >= STABLE_MIN_LEVERAGE_GROUP
        and top_available >= 1
        and hierarchy_confidence in {'medium', 'high'}
    )
    if stable_shape:
        reasons.append('Coverage reads stable because there are enough rested relievers with a broad late-inning group.')
        return LABEL_STABLE, reasons, []

    if trusted_group >= THIN_MIN_TRUSTED_GROUP and active >= 5 and clean >= 1:
        reasons.append('Coverage reads thin because the bullpen has some coverage, but not enough for a stable read.')
        return LABEL_THIN, reasons, []

    return LABEL_LIMITED, [
        'Coverage is limited because the stored data does not support a broader coverage note.'
    ], []


def _apply_environment_context(label, reasons, evidence):
    environment_status = evidence['environment_status']
    if environment_status in {ENVIRONMENT_PRESSURE, ENVIRONMENT_MULTI_SOURCE} and label == LABEL_STRONG:
        return LABEL_STABLE, [
            *reasons,
            'Current bullpen environment pressure keeps the coverage read at stable rather than strong.',
        ]
    return label, reasons


def _explanation(evidence, label):
    if label == LABEL_LIMITED_READ:
        return (
            'There is not enough recent workload data to read this bullpen yet. '
            'This is a data-limited note, not a statement about injury status or manager intent.'
        )
    if label == LABEL_LIMITED:
        return 'The late innings leave less margin if the starter exits early.'
    if label == LABEL_THIN:
        return 'The bullpen has some coverage, but less room if the starter exits early.'
    if label == LABEL_STABLE:
        return 'The bullpen has enough stored coverage to handle more than one relief inning.'
    return 'The bullpen has enough stored coverage to protect a multi-inning bridge.'


def build_bullpen_coverage_safety_read(
    capacity_intelligence=None,
    *,
    bullpen_environment=None,
):
    """Build the public Coverage Safety read when V2 inputs are available.

    Returns None when the caller has not provided the V2 source payloads so
    older count-based coverage logic can remain the fallback.
    """
    if not _has_v2_inputs(capacity_intelligence):
        return None

    evidence = _evidence(capacity_intelligence, bullpen_environment)
    label, reasons, limitations = _base_label(evidence)
    if label != LABEL_LIMITED_READ:
        label, reasons = _apply_environment_context(label, reasons, evidence)

    supporting_counts = {
        'coverageSafetyVersion': '2.0',
        'capacityState': evidence['capacity_state'],
        'resourceHealthState': evidence['resource_health_state'],
        'activeRelieverCount': evidence['active_reliever_count'],
        'cleanActiveRelieverCount': evidence['clean_active_reliever_count'],
        'anchorCount': evidence['anchor_count'],
        'leverageCount': evidence['leverage_count'],
        'trustedCount': evidence['trusted_count'],
        'trustedGroupSize': evidence['trusted_group_size'],
        'topTrustBucketAvailableCount': evidence['top_trust_bucket_available_count'],
        'trustArmsUnavailable': evidence['trust_arms_unavailable'],
        'trustCapacityUnavailablePct': evidence['trust_capacity_unavailable_pct'],
        'hierarchyConfidence': evidence['hierarchy_confidence'],
        'environmentStatus': evidence['environment_status'] or None,
        'environmentPressureSources': evidence['environment_pressure_sources'],
        'thresholds': {
            'strongMinCleanActiveRelievers': STRONG_MIN_CLEAN_ACTIVE,
            'strongMinTrustedGroupSize': STRONG_MIN_TRUSTED_GROUP,
            'stableMinCleanActiveRelievers': STABLE_MIN_CLEAN_ACTIVE,
            'stableMinTrustedGroupSize': STABLE_MIN_TRUSTED_GROUP,
            'thinTrustUnavailableMin': THIN_TRUST_UNAVAILABLE_MIN,
            'thinTrustUnavailablePct': THIN_TRUST_UNAVAILABLE_PCT,
        },
    }

    return {
        'key': 'coverageSafety',
        'label': label,
        'explanation': _explanation(evidence, label),
        'supportingCounts': supporting_counts,
        'reasons': reasons,
        'source': 'backend',
        'limitations': limitations,
        'capability': CAPABILITY,
        'version': VERSION,
    }


__all__ = [
    'CAPABILITY',
    'LABEL_LIMITED',
    'LABEL_LIMITED_READ',
    'LABEL_STABLE',
    'LABEL_STRONG',
    'LABEL_THIN',
    'VERSION',
    'build_bullpen_coverage_safety_read',
]
