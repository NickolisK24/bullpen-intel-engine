"""Bullpen Identity V1.

This layer describes the structural personality of a bullpen from existing
backend-authored intelligence. It does not create new data, choose pitchers, or
turn daily workload state into a tactical instruction.
"""

from __future__ import annotations

from typing import Any

from services.bullpen_coverage_safety import (
    LABEL_LIMITED,
    LABEL_LIMITED_READ,
    LABEL_STABLE,
    LABEL_STRONG,
    LABEL_THIN,
    build_bullpen_coverage_safety_read,
)


CAPABILITY = 'bullpen_identity_v1'
VERSION = '2026-06-19.v1'

IDENTITY_TRUST_CONCENTRATED = 'trust_concentrated'
IDENTITY_DEPTH_DRIVEN = 'depth_driven'
IDENTITY_FLEXIBLE_DISTRIBUTION = 'flexible_distribution'
IDENTITY_LEVERAGE_HEAVY = 'leverage_heavy'
IDENTITY_FRAGILE_COVERAGE = 'fragile_coverage'
IDENTITY_RESOURCE_STRAINED = 'resource_strained'
IDENTITY_UNKNOWN = 'unknown_insufficient_context'

IDENTITY_LABELS = {
    IDENTITY_TRUST_CONCENTRATED: 'Trust-Concentrated Bullpen',
    IDENTITY_DEPTH_DRIVEN: 'Depth-Driven Bullpen',
    IDENTITY_FLEXIBLE_DISTRIBUTION: 'Flexible Distribution Bullpen',
    IDENTITY_LEVERAGE_HEAVY: 'Leverage-Heavy Bullpen',
    IDENTITY_FRAGILE_COVERAGE: 'Fragile Coverage Bullpen',
    IDENTITY_RESOURCE_STRAINED: 'Resource-Strained Bullpen',
    IDENTITY_UNKNOWN: 'Unknown / Insufficient Context',
}

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

HIERARCHY_CONFIDENCE_STRUCTURAL = {'medium', 'high'}
FAVORABLE_COVERAGE_LABELS = {LABEL_STRONG, LABEL_STABLE}
TIGHT_COVERAGE_LABELS = {LABEL_THIN, LABEL_LIMITED}

MISSING_INPUT_LIMITATION = (
    'Bullpen Identity is unknown because capacity, resource health, trust hierarchy, or coverage inputs are missing.'
)
UNKNOWN_INPUT_LIMITATION = (
    'Bullpen Identity is unknown because one or more structural inputs are unknown or limited.'
)
STRUCTURAL_SCOPE_CAVEAT = (
    'Identity describes bullpen structure from existing reads; daily availability can still change the board.'
)
TACTICAL_BOUNDARY_CAVEAT = 'This read is descriptive context only, not tactical advice.'


def _get(mapping: dict[str, Any] | None, *keys, default=None):
    current = mapping or {}
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if current is not None else default


def _norm(value: Any) -> str:
    return str(value or '').strip().lower()


def _int(value: Any, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _team_identity(capacity_intelligence: dict[str, Any]) -> dict[str, Any]:
    return {
        'team_id': capacity_intelligence.get('team_id'),
        'team_name': capacity_intelligence.get('team_name'),
        'team_abbreviation': capacity_intelligence.get('team_abbreviation'),
    }


def _coverage_read(
    capacity_intelligence: dict[str, Any],
    coverage_safety: dict[str, Any] | None,
) -> dict[str, Any]:
    if isinstance(coverage_safety, dict) and coverage_safety:
        return coverage_safety
    read = build_bullpen_coverage_safety_read(capacity_intelligence)
    return read if isinstance(read, dict) else {}


def _has_required_inputs(capacity_intelligence: dict[str, Any]) -> bool:
    return (
        isinstance(capacity_intelligence, dict)
        and isinstance(capacity_intelligence.get('resource_health'), dict)
        and isinstance(capacity_intelligence.get('trust_hierarchy'), dict)
    )


def _evidence(
    capacity_intelligence: dict[str, Any],
    coverage_safety: dict[str, Any] | None,
) -> dict[str, Any]:
    resource_health = _mapping(capacity_intelligence.get('resource_health'))
    bullpen_capacity = _mapping(resource_health.get('bullpen_capacity'))
    organizational = _mapping(resource_health.get('organizational_resource_health'))
    trust_hierarchy = _mapping(capacity_intelligence.get('trust_hierarchy'))
    trust_capacity_loss = _mapping(capacity_intelligence.get('trust_capacity_loss'))
    coverage_read = _coverage_read(capacity_intelligence, coverage_safety)

    capacity_state = _norm(
        bullpen_capacity.get('capacity_state')
        or bullpen_capacity.get('state')
        or resource_health.get('capacity_state')
        or CAPACITY_UNKNOWN
    )
    resource_state = _norm(
        organizational.get('resource_health_state')
        or organizational.get('state')
        or resource_health.get('resource_health_state')
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
    depth = _int(trust_hierarchy.get('depth_count'))
    trusted_group = _int(
        trust_hierarchy.get('trusted_group_size'),
        default=anchor + leverage + trusted,
    )

    return {
        'capacity_state': capacity_state,
        'resource_health_state': resource_state,
        'active_reliever_count': active,
        'clean_active_reliever_count': clean,
        'anchor_count': anchor,
        'leverage_count': leverage,
        'trusted_count': trusted,
        'depth_count': depth,
        'unknown_count': _int(trust_hierarchy.get('unknown_count')),
        'trusted_group_size': trusted_group,
        'leverage_group_size': anchor + leverage,
        'top_trust_bucket_available_count': _int(
            trust_hierarchy.get('top_trust_bucket_available_count')
        ),
        'trust_arms_unavailable': _int(trust_capacity_loss.get('trust_arms_unavailable')),
        'hierarchy_confidence': _norm(trust_hierarchy.get('hierarchy_confidence')),
        'coverage_label': coverage_read.get('label'),
        'coverage_limitations': _list(coverage_read.get('limitations')),
    }


def _insufficient_evidence(evidence: dict[str, Any]) -> bool:
    structural_total = (
        evidence['trusted_group_size']
        + evidence['depth_count']
        + evidence['unknown_count']
    )
    return (
        evidence['active_reliever_count'] <= 0
        or evidence['capacity_state'] in {'', CAPACITY_UNKNOWN}
        or evidence['resource_health_state'] in {'', RESOURCE_UNKNOWN}
        or not evidence['coverage_label']
        or evidence['coverage_label'] == LABEL_LIMITED_READ
        or structural_total <= 0
    )


def _trust_concentrated(evidence: dict[str, Any]) -> bool:
    return (
        evidence['hierarchy_confidence'] in HIERARCHY_CONFIDENCE_STRUCTURAL
        and evidence['trusted_group_size'] in {2, 3}
        and evidence['leverage_group_size'] >= 1
        and evidence['top_trust_bucket_available_count'] <= 1
        and evidence['depth_count'] <= 2
    )


def _depth_driven(evidence: dict[str, Any]) -> bool:
    return (
        evidence['hierarchy_confidence'] in HIERARCHY_CONFIDENCE_STRUCTURAL
        and evidence['capacity_state'] in {CAPACITY_HEALTHY, CAPACITY_REDUCED}
        and evidence['coverage_label'] in FAVORABLE_COVERAGE_LABELS
        and evidence['depth_count'] >= 3
        and evidence['active_reliever_count'] >= 7
    )


def _flexible_distribution(evidence: dict[str, Any]) -> bool:
    return (
        evidence['hierarchy_confidence'] in HIERARCHY_CONFIDENCE_STRUCTURAL
        and evidence['capacity_state'] in {CAPACITY_HEALTHY, CAPACITY_REDUCED}
        and evidence['coverage_label'] in FAVORABLE_COVERAGE_LABELS
        and evidence['active_reliever_count'] >= 7
        and evidence['clean_active_reliever_count'] >= 4
        and evidence['trusted_group_size'] >= 4
    )


def _leverage_heavy(evidence: dict[str, Any]) -> bool:
    return (
        evidence['hierarchy_confidence'] in HIERARCHY_CONFIDENCE_STRUCTURAL
        and evidence['leverage_count'] >= 3
        and evidence['depth_count'] <= 1
        and evidence['trusted_group_size'] >= 3
    )


def _resource_strained(evidence: dict[str, Any]) -> bool:
    if evidence['resource_health_state'] == RESOURCE_DEPLETED:
        return True
    return (
        evidence['resource_health_state'] == RESOURCE_STRAINED
        and (
            evidence['capacity_state'] in {CAPACITY_REDUCED, CAPACITY_THIN, CAPACITY_DEPLETED}
            or evidence['coverage_label'] in TIGHT_COVERAGE_LABELS
            or evidence['clean_active_reliever_count'] <= 3
        )
    )


def _identity_key(evidence: dict[str, Any]) -> str:
    if _insufficient_evidence(evidence):
        return IDENTITY_UNKNOWN
    if _resource_strained(evidence):
        return IDENTITY_RESOURCE_STRAINED
    if (
        evidence['capacity_state'] in {CAPACITY_THIN, CAPACITY_DEPLETED}
        or evidence['clean_active_reliever_count'] <= 2
        or evidence['trusted_group_size'] <= 1
        or evidence['top_trust_bucket_available_count'] <= 0
        or evidence['trust_arms_unavailable'] >= 2
    ):
        return IDENTITY_FRAGILE_COVERAGE
    if _trust_concentrated(evidence):
        return IDENTITY_TRUST_CONCENTRATED
    if evidence['coverage_label'] in TIGHT_COVERAGE_LABELS:
        return IDENTITY_FRAGILE_COVERAGE
    if _depth_driven(evidence):
        return IDENTITY_DEPTH_DRIVEN
    if _leverage_heavy(evidence):
        return IDENTITY_LEVERAGE_HEAVY
    if _flexible_distribution(evidence):
        return IDENTITY_FLEXIBLE_DISTRIBUTION
    if evidence['coverage_label'] in FAVORABLE_COVERAGE_LABELS:
        return IDENTITY_FLEXIBLE_DISTRIBUTION
    return IDENTITY_UNKNOWN


def _summary(identity_key: str, evidence: dict[str, Any]) -> str:
    label = IDENTITY_LABELS[identity_key]
    if identity_key == IDENTITY_TRUST_CONCENTRATED:
        return (
            f'{label}: the current structure runs through a narrow trusted lane before it reaches the rest of the group.'
        )
    if identity_key == IDENTITY_DEPTH_DRIVEN:
        return (
            f'{label}: this bullpen has meaningful depth behind the trusted group, giving the structure more ways to absorb innings.'
        )
    if identity_key == IDENTITY_FLEXIBLE_DISTRIBUTION:
        return (
            f'{label}: active capacity, clean options, and trusted-group breadth point to a bullpen with several usable lanes.'
        )
    if identity_key == IDENTITY_LEVERAGE_HEAVY:
        return (
            f'{label}: the structure is built around multiple leverage arms more than broad depth.'
        )
    if identity_key == IDENTITY_FRAGILE_COVERAGE:
        return (
            f'{label}: coverage can narrow quickly once the primary trusted group or clean options are stressed.'
        )
    if identity_key == IDENTITY_RESOURCE_STRAINED:
        return (
            f'{label}: the active group may still have usable pieces, but the broader resource pool is thinner than normal.'
        )
    return 'Existing bullpen intelligence is too incomplete to assign a stable structural identity.'


def _trait(key: str, text: str) -> dict[str, str]:
    return {'key': key, 'text': text}


def _supporting_traits(identity_key: str, evidence: dict[str, Any]) -> list[dict[str, str]]:
    traits = [
        _trait(
            'capacity_shape',
            (
                f"Active capacity is {evidence['capacity_state']} with "
                f"{evidence['active_reliever_count']} active relievers and "
                f"{evidence['clean_active_reliever_count']} clean active options."
            ),
        ),
        _trait(
            'resource_health',
            f"Resource health is {evidence['resource_health_state']}.",
        ),
        _trait(
            'trust_structure',
            (
                f"Trust structure has {evidence['anchor_count']} anchors, "
                f"{evidence['leverage_count']} leverage arms, "
                f"{evidence['trusted_group_size']} trusted-group arms, and "
                f"{evidence['depth_count']} depth arms."
            ),
        ),
    ]
    if evidence.get('coverage_label'):
        traits.append(_trait('coverage_safety', f"Coverage Safety reads {evidence['coverage_label']}."))

    identity_trait = {
        IDENTITY_TRUST_CONCENTRATED: 'The primary trusted lane is narrow relative to the full bullpen.',
        IDENTITY_DEPTH_DRIVEN: 'Depth volume is a material part of the bullpen structure.',
        IDENTITY_FLEXIBLE_DISTRIBUTION: 'Usable capacity is spread across several structural lanes.',
        IDENTITY_LEVERAGE_HEAVY: 'Leverage arms carry much of the bullpen shape.',
        IDENTITY_FRAGILE_COVERAGE: 'Coverage and clean capacity leave little margin behind the primary group.',
        IDENTITY_RESOURCE_STRAINED: 'The broader resource pool is strained even if the active layer has usable arms.',
        IDENTITY_UNKNOWN: 'Required structural context is incomplete.',
    }[identity_key]
    traits.append(_trait('identity_reason', identity_trait))
    return traits


def _collect_caveats(
    capacity_intelligence: dict[str, Any],
    coverage_limitations: list[Any],
    extra: list[str] | None = None,
) -> list[str]:
    caveats: list[str] = []

    for path in (
        ('resource_health', 'limitations'),
        ('trust_hierarchy', 'limitations'),
        ('capacity_loss', 'limitations'),
        ('trust_capacity_loss', 'limitations'),
    ):
        for item in _list(_get(capacity_intelligence, *path, default=[])):
            text = str(item or '').strip()
            if text and text not in caveats:
                caveats.append(text)

    for item in coverage_limitations:
        text = str(item or '').strip()
        if text and text not in caveats:
            caveats.append(text)

    for item in extra or []:
        if item and item not in caveats:
            caveats.append(item)

    for item in (STRUCTURAL_SCOPE_CAVEAT, TACTICAL_BOUNDARY_CAVEAT):
        if item not in caveats:
            caveats.append(item)

    return caveats


def _confidence(identity_key: str, evidence: dict[str, Any], caveats: list[str], *, missing_inputs: bool) -> str:
    if missing_inputs:
        return 'none'
    if identity_key == IDENTITY_UNKNOWN:
        return 'low'
    hierarchy_confidence = evidence['hierarchy_confidence']
    if (
        hierarchy_confidence == 'high'
        and evidence['coverage_label'] in FAVORABLE_COVERAGE_LABELS
        and len(caveats) <= 2
    ):
        return 'high'
    if hierarchy_confidence in HIERARCHY_CONFIDENCE_STRUCTURAL:
        return 'medium'
    return 'low'


def _unknown_payload(
    capacity_intelligence: dict[str, Any] | None,
    *,
    caveats: list[str],
    confidence: str,
) -> dict[str, Any]:
    identity = _team_identity(capacity_intelligence or {})
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': 'backend',
        'team': identity.get('team_abbreviation'),
        **identity,
        'identity_key': IDENTITY_UNKNOWN,
        'identity_label': IDENTITY_LABELS[IDENTITY_UNKNOWN],
        'identity_summary': _summary(IDENTITY_UNKNOWN, {}),
        'supporting_traits': [_trait('input_quality', 'Required structural context is incomplete.')],
        'caveats': caveats,
        'confidence': confidence,
        'ranking_applied': False,
        'selection_made': False,
        'prediction_applied': False,
    }


def build_bullpen_identity(
    capacity_intelligence: dict[str, Any] | None,
    *,
    coverage_safety: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a public-safe structural identity payload for one bullpen."""

    capacity_intelligence = _mapping(capacity_intelligence)
    if not _has_required_inputs(capacity_intelligence):
        caveats = _collect_caveats(
            capacity_intelligence,
            [],
            extra=[MISSING_INPUT_LIMITATION],
        )
        return _unknown_payload(capacity_intelligence, caveats=caveats, confidence='none')

    evidence = _evidence(capacity_intelligence, coverage_safety)
    extra_caveats = []
    if _insufficient_evidence(evidence):
        extra_caveats.append(UNKNOWN_INPUT_LIMITATION)
    identity_key = _identity_key(evidence)
    caveats = _collect_caveats(
        capacity_intelligence,
        evidence['coverage_limitations'],
        extra=extra_caveats,
    )
    confidence = _confidence(
        identity_key,
        evidence,
        caveats,
        missing_inputs=False,
    )
    identity = _team_identity(capacity_intelligence)

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': 'backend',
        'team': identity.get('team_abbreviation'),
        **identity,
        'identity_key': identity_key,
        'identity_label': IDENTITY_LABELS[identity_key],
        'identity_summary': _summary(identity_key, evidence),
        'supporting_traits': _supporting_traits(identity_key, evidence),
        'caveats': caveats,
        'confidence': confidence,
        'ranking_applied': False,
        'selection_made': False,
        'prediction_applied': False,
    }


__all__ = [
    'CAPABILITY',
    'IDENTITY_DEPTH_DRIVEN',
    'IDENTITY_FLEXIBLE_DISTRIBUTION',
    'IDENTITY_FRAGILE_COVERAGE',
    'IDENTITY_LABELS',
    'IDENTITY_LEVERAGE_HEAVY',
    'IDENTITY_RESOURCE_STRAINED',
    'IDENTITY_TRUST_CONCENTRATED',
    'IDENTITY_UNKNOWN',
    'MISSING_INPUT_LIMITATION',
    'UNKNOWN_INPUT_LIMITATION',
    'VERSION',
    'build_bullpen_identity',
]
