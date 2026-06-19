"""Public-safe bullpen intelligence context for team stories.

This adapter translates internal bullpen intelligence into one conservative
story sentence when the context materially helps explain the baseball read. It
does not rank pitchers, select pitchers, recommend usage, predict outcomes, or
surface internal state labels.
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


CAPABILITY = 'story_context_integration_v1'
VERSION = '2026-06-19'

RULE_STRESS_TRANSFER = 'stress_transfer'
RULE_PRESSURE_DISTRIBUTION = 'pressure_distribution'
RULE_SUSTAINABILITY_QUESTION = 'sustainability_question'
RULE_HIDDEN_CAPACITY_LOSS = 'hidden_capacity_loss'

LEAD_TRUST_LANE_ABSENCE = 'trust_lane_absence'
LEAD_TRUST_LANE_SHALLOW = 'trust_lane_shallow'
LEAD_TRUST_LANE_DEPTH = 'trust_lane_depth'
LEAD_DEEP_INTACT = 'deep_intact'
LEAD_AVAILABILITY_THIN = 'availability_thin'
LEAD_AVAILABILITY_DEEP = 'availability_deep'
LEAD_PARTICIPATION_BROAD = 'participation_broad'
LEAD_WORKLOAD_LIGHT = 'workload_light'
LEAD_ERA_ELITE = 'era_elite'
LEAD_ERA_ORDINARY = 'era_ordinary'

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

HIERARCHY_CONFIDENCE_ALLOWED = {'medium', 'high'}
ROLE_CHANGE_PUBLIC_STATUSES = {'available'}

INSUFFICIENT_INPUT_LIMITATION = (
    'Story context integration did not apply because bullpen intelligence inputs were incomplete.'
)
UNKNOWN_INPUT_LIMITATION = (
    'Story context integration did not apply because the bullpen intelligence read is unknown or limited.'
)

TRUST_LANE_LEADS = {
    LEAD_TRUST_LANE_ABSENCE,
    LEAD_TRUST_LANE_SHALLOW,
    LEAD_TRUST_LANE_DEPTH,
    LEAD_DEEP_INTACT,
}
FLEXIBILITY_LEADS = {
    LEAD_AVAILABILITY_DEEP,
    LEAD_PARTICIPATION_BROAD,
    LEAD_WORKLOAD_LIGHT,
    LEAD_DEEP_INTACT,
}
CAPACITY_PRESSURE_LEADS = {
    LEAD_AVAILABILITY_THIN,
    LEAD_TRUST_LANE_ABSENCE,
    LEAD_TRUST_LANE_SHALLOW,
}
RUN_PREVENTION_LEADS = {
    LEAD_ERA_ELITE,
    LEAD_ERA_ORDINARY,
}


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


def _coverage_label(capacity_intelligence, bullpen_environment) -> str | None:
    read = build_bullpen_coverage_safety_read(
        capacity_intelligence,
        bullpen_environment=bullpen_environment,
    )
    return read.get('label') if isinstance(read, dict) else None


def _evidence(inputs: dict[str, Any]) -> dict[str, Any] | None:
    capacity_intelligence = inputs.get('capacity_intelligence')
    if not isinstance(capacity_intelligence, dict) or not capacity_intelligence:
        return None

    resource_health = capacity_intelligence.get('resource_health')
    trust_hierarchy = capacity_intelligence.get('trust_hierarchy')
    if not isinstance(resource_health, dict) or not isinstance(trust_hierarchy, dict):
        return None

    bullpen_capacity = resource_health.get('bullpen_capacity') or {}
    organizational = resource_health.get('organizational_resource_health') or {}
    trust_loss = capacity_intelligence.get('trust_capacity_loss') or {}
    bullpen_environment = inputs.get('bullpen_environment') or {}
    coverage_label = _coverage_label(capacity_intelligence, bullpen_environment)

    capacity_state = _norm(
        bullpen_capacity.get('capacity_state')
        or resource_health.get('capacity_state')
        or CAPACITY_UNKNOWN
    )
    resource_state = _norm(
        organizational.get('resource_health_state')
        or resource_health.get('resource_health_state')
        or RESOURCE_UNKNOWN
    )
    hierarchy_confidence = _norm(trust_hierarchy.get('hierarchy_confidence'))

    return {
        'capacity_state': capacity_state,
        'resource_health_state': resource_state,
        'active_reliever_count': _int(
            bullpen_capacity.get('active_reliever_count')
            or resource_health.get('active_reliever_count')
        ),
        'clean_active_reliever_count': _int(
            bullpen_capacity.get('clean_active_reliever_count')
        ),
        'anchor_count': _int(trust_hierarchy.get('anchor_count')),
        'leverage_count': _int(trust_hierarchy.get('leverage_count')),
        'trusted_count': _int(trust_hierarchy.get('trusted_count')),
        'trusted_group_size': _int(trust_hierarchy.get('trusted_group_size')),
        'top_trust_bucket_available_count': _int(
            trust_hierarchy.get('top_trust_bucket_available_count')
        ),
        'trust_arms_unavailable': _int(trust_loss.get('trust_arms_unavailable')),
        'hierarchy_confidence': hierarchy_confidence,
        'coverage_label': coverage_label,
    }


def _limited_evidence(evidence: dict[str, Any]) -> bool:
    return (
        evidence['capacity_state'] in {'', CAPACITY_UNKNOWN}
        or evidence['resource_health_state'] in {'', RESOURCE_UNKNOWN}
        or evidence['hierarchy_confidence'] not in HIERARCHY_CONFIDENCE_ALLOWED
        or evidence['coverage_label'] in {None, LABEL_LIMITED_READ}
    )


def _lead_dimension(lead: dict[str, Any] | None) -> str:
    return _norm((lead or {}).get('dimension'))


def _result(text: str, *, reason: str, sources: list[str]) -> dict[str, Any]:
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'applied': True,
        'text': text,
        'reason': reason,
        'sources': sources,
        'ranking_applied': False,
        'selection_made': False,
        'prediction_applied': False,
        'limitations': [],
    }


def _not_applied(reason: str, limitations: list[str] | None = None) -> dict[str, Any]:
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'applied': False,
        'text': None,
        'reason': reason,
        'sources': [],
        'ranking_applied': False,
        'selection_made': False,
        'prediction_applied': False,
        'limitations': list(limitations or []),
    }


def _has_active_room(evidence: dict[str, Any]) -> bool:
    return (
        evidence['capacity_state'] in {CAPACITY_HEALTHY, CAPACITY_REDUCED}
        and evidence['active_reliever_count'] >= 7
    )


def _resource_pool_strained(evidence: dict[str, Any]) -> bool:
    return evidence['resource_health_state'] in {RESOURCE_STRAINED, RESOURCE_DEPLETED}


def _trust_lane_narrow(inputs: dict[str, Any], evidence: dict[str, Any]) -> bool:
    clean_trust_count = len(inputs.get('clean_trust_options') or [])
    clean_option_count = len(inputs.get('clean_options') or [])
    return (
        clean_option_count >= 3
        and (
            clean_trust_count <= 1
            or evidence['top_trust_bucket_available_count'] <= 1
            or evidence['trusted_group_size'] <= 3
            or evidence['trust_arms_unavailable'] >= 2
        )
    )


def _coverage_tight(evidence: dict[str, Any]) -> bool:
    return evidence['coverage_label'] in {LABEL_THIN, LABEL_LIMITED}


def _coverage_strong_or_stable(evidence: dict[str, Any]) -> bool:
    return evidence['coverage_label'] in {LABEL_STRONG, LABEL_STABLE}


def build_story_context_integration(
    rule_key: str,
    inputs: dict[str, Any] | None,
    *,
    lead: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return one public-safe context sentence for a rendered story, if useful."""

    inputs = inputs or {}
    evidence = _evidence(inputs)
    if evidence is None:
        return _not_applied('missing_inputs', [INSUFFICIENT_INPUT_LIMITATION])
    if _limited_evidence(evidence):
        return _not_applied('unknown_or_limited_inputs', [UNKNOWN_INPUT_LIMITATION])

    lead_dimension = _lead_dimension(lead)
    capacity_state = evidence['capacity_state']
    active_room = _has_active_room(evidence)
    resource_strained = _resource_pool_strained(evidence)
    trust_narrow = _trust_lane_narrow(inputs, evidence)
    coverage_tight = _coverage_tight(evidence)
    coverage_stable = _coverage_strong_or_stable(evidence)
    top_structure = evidence['anchor_count'] >= 1 or evidence['leverage_count'] >= 2
    flexible_story = (
        rule_key == RULE_PRESSURE_DISTRIBUTION
        or lead_dimension in FLEXIBILITY_LEADS
    )
    pressure_story = (
        rule_key in {RULE_STRESS_TRANSFER, RULE_HIDDEN_CAPACITY_LOSS}
        or lead_dimension in CAPACITY_PRESSURE_LEADS
    )
    results_mask_story = (
        rule_key in {RULE_SUSTAINABILITY_QUESTION, RULE_HIDDEN_CAPACITY_LOSS}
        or lead_dimension in RUN_PREVENTION_LEADS
    )

    if (lead_dimension in TRUST_LANE_LEADS or pressure_story) and trust_narrow:
        return _result(
            'Once you get past the first few names, the picture starts getting a little less comfortable.',
            reason='clean_trusted_lane_narrow',
            sources=['trusted_lane', 'active_capacity'],
        )

    if active_room and resource_strained:
        if top_structure:
            return _result(
                "The late innings still look pretty normal. It is everything behind that group being asked to handle more.",
                reason='top_structure_with_resource_strain',
                sources=['active_capacity', 'resource_pool', 'trusted_lane'],
            )
        return _result(
            'The late-inning group may still look intact, but the cushion behind it is not as thick.',
            reason='active_group_intact_resource_pool_strained',
            sources=['active_capacity', 'resource_pool'],
        )

    if capacity_state == CAPACITY_THIN and (pressure_story or coverage_tight):
        return _result(
            "On paper the bullpen still has names. The question is how many of those options you would really feel comfortable handing the game to.",
            reason='thin_active_capacity_margin',
            sources=['active_capacity', 'coverage_read'],
        )

    if capacity_state == CAPACITY_DEPLETED or coverage_tight:
        return _result(
            'Once the game gets past the obvious choices, there is not much room for error.',
            reason='dependable_group_narrow',
            sources=['active_capacity', 'coverage_read', 'trusted_lane'],
        )

    if flexible_story and coverage_stable and top_structure:
        return _result(
            'That looks like real flexibility, not just extra names on a roster sheet.',
            reason='flexibility_supported_by_trust_structure',
            sources=['active_capacity', 'trusted_lane', 'coverage_read'],
        )

    if results_mask_story and (resource_strained or trust_narrow):
        return _result(
            'The results can still look sturdy while the usable answers underneath them get thinner.',
            reason='results_mask_thinner_bullpen_context',
            sources=['resource_pool', 'trusted_lane'],
        )

    return _not_applied('context_not_material')


__all__ = [
    'CAPABILITY',
    'VERSION',
    'build_story_context_integration',
]
