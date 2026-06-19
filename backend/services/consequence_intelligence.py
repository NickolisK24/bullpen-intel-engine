"""Consequence Intelligence V1.

This layer translates existing bullpen intelligence and meaningful day-over-day
changes into descriptive baseball consequences. It does not predict outcomes,
recommend usage, rank teams or relievers, expose scores, or select pitchers.
"""

from __future__ import annotations

from typing import Any

from services.bullpen_coverage_safety import build_bullpen_coverage_safety_read
from services.bullpen_identity import (
    IDENTITY_DEPTH_DRIVEN,
    IDENTITY_FLEXIBLE_DISTRIBUTION,
    IDENTITY_FRAGILE_COVERAGE,
    IDENTITY_LEVERAGE_HEAVY,
    IDENTITY_RESOURCE_STRAINED,
    IDENTITY_TRUST_CONCENTRATED,
    IDENTITY_UNKNOWN,
)
from services.what_changed_since_yesterday import (
    CHANGE_COVERAGE_SAFETY,
    CHANGE_IDENTITY,
    CHANGE_RESOURCE_HEALTH,
    CHANGE_RESTED_OPTIONS,
    CHANGE_TRUST_STRUCTURE,
    CHANGE_USABLE_DEPTH,
    STATE_NO_MEANINGFUL_CHANGES,
    STATUS_INSUFFICIENT_CONTEXT as CHANGE_STATUS_INSUFFICIENT_CONTEXT,
    build_team_what_changed_since_yesterday,
    build_what_changed_since_yesterday_payload,
)


CAPABILITY = 'consequence_intelligence_v1'
VERSION = '2026-06-19.v1'

STATUS_AVAILABLE = 'available'
STATUS_INSUFFICIENT_CONTEXT = 'insufficient_context'

STATE_CONSEQUENCES_DETECTED = 'consequences_detected'
STATE_NO_CONSEQUENCES = 'no_consequences'
STATE_INSUFFICIENT_CONTEXT = 'insufficient_context'

CONSEQUENCE_MORE_FLEXIBILITY = 'more_flexibility'
CONSEQUENCE_LESS_FLEXIBILITY = 'less_flexibility'
CONSEQUENCE_MORE_COVERAGE_MARGIN = 'more_coverage_margin'
CONSEQUENCE_LESS_COVERAGE_MARGIN = 'less_coverage_margin'
CONSEQUENCE_WIDER_TRUST_SUPPORT = 'wider_trust_support'
CONSEQUENCE_NARROWER_TRUST_SUPPORT = 'narrower_trust_support'
CONSEQUENCE_EASIER_WORKLOAD_DISTRIBUTION = 'easier_workload_distribution'
CONSEQUENCE_HEAVIER_WORKLOAD_CONCENTRATION = 'heavier_workload_concentration'
CONSEQUENCE_MORE_STABLE_BULLPEN_SHAPE = 'more_stable_bullpen_shape'
CONSEQUENCE_LESS_STABLE_BULLPEN_SHAPE = 'less_stable_bullpen_shape'

SIGNIFICANCE_MEANINGFUL = 'meaningful'
SIGNIFICANCE_STRUCTURAL = 'structural'

NO_CURRENT_LIMITATION = (
    'Current bullpen intelligence is unavailable; consequence intelligence cannot be computed.'
)
NO_CHANGE_CONTEXT_LIMITATION = (
    'Consequence Intelligence requires a What Changed payload or comparable prior snapshot.'
)
CHANGE_CONTEXT_LIMITATION = (
    'What Changed context is insufficient, so consequences cannot be described safely.'
)

CONFIDENCE_ORDER = {
    'none': 0,
    'unknown': 0,
    'low': 1,
    'medium': 2,
    'high': 3,
}
CONFIDENCE_BY_VALUE = {
    0: 'none',
    1: 'low',
    2: 'medium',
    3: 'high',
}

MORE_STABLE_IDENTITIES = {
    IDENTITY_DEPTH_DRIVEN,
    IDENTITY_FLEXIBLE_DISTRIBUTION,
    IDENTITY_LEVERAGE_HEAVY,
}
LESS_STABLE_IDENTITIES = {
    IDENTITY_FRAGILE_COVERAGE,
    IDENTITY_RESOURCE_STRAINED,
    IDENTITY_TRUST_CONCENTRATED,
}


def _nested(mapping: dict[str, Any] | None, *keys, default=None):
    current = mapping or {}
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if current is not None else default


def _int(value: Any, default: int | None = 0) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _norm(value: Any) -> str:
    return str(value or '').strip().lower()


def _capacity_item(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        return {}
    capacity = snapshot.get('capacity_intelligence')
    if isinstance(capacity, dict):
        return capacity
    if isinstance(snapshot.get('resource_health'), dict) or isinstance(snapshot.get('trust_hierarchy'), dict):
        return snapshot
    return {}


def _capacity_items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    capacity = payload.get('capacity_intelligence') if isinstance(payload, dict) else {}
    capacity = capacity if isinstance(capacity, dict) else {}
    teams = capacity.get('teams')
    if isinstance(teams, list):
        return [item for item in teams if isinstance(item, dict)]
    by_team = capacity.get('by_team_id')
    if isinstance(by_team, dict):
        return [item for item in by_team.values() if isinstance(item, dict)]
    single = _capacity_item(payload)
    return [single] if single else []


def _team_id(item: dict[str, Any] | None) -> Any:
    return (item or {}).get('team_id') or (item or {}).get('teamId')


def _team_name(item: dict[str, Any] | None) -> str | None:
    item = item or {}
    return item.get('team_name') or item.get('teamName')


def _team_abbreviation(item: dict[str, Any] | None) -> str | None:
    item = item or {}
    return item.get('team_abbreviation') or item.get('teamAbbreviation') or item.get('team')


def _team_identity(item: dict[str, Any]) -> dict[str, Any]:
    return {
        'team_id': _team_id(item),
        'team_name': _team_name(item),
        'team_abbreviation': _team_abbreviation(item),
    }


def _team_key(item: dict[str, Any] | None) -> str | None:
    item = item or {}
    team_id = _team_id(item)
    if team_id is not None:
        return str(team_id)
    abbr = _team_abbreviation(item)
    return str(abbr).lower() if abbr else None


def _capacity_by_team(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    teams = {}
    for item in _capacity_items(payload):
        key = _team_key(item)
        if key is not None and key not in teams:
            teams[key] = item
    return teams


def _change_by_team(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        return {}
    by_team = payload.get('by_team_id')
    if isinstance(by_team, dict):
        return {
            str(key): value
            for key, value in by_team.items()
            if isinstance(value, dict)
        }
    teams = payload.get('teams')
    if isinstance(teams, list):
        return {
            str(_team_key(item)): item
            for item in teams
            if isinstance(item, dict) and _team_key(item) is not None
        }
    return {}


def _coverage_label(capacity_item: dict[str, Any]) -> str | None:
    explicit = (
        _nested(capacity_item, 'coverage_safety', 'label')
        or _nested(capacity_item, 'coverageSafety', 'label')
    )
    if explicit:
        return str(explicit)
    read = build_bullpen_coverage_safety_read(capacity_item)
    return read.get('label') if isinstance(read, dict) else None


def _confidence(*values: Any, fallback: str = 'medium') -> str:
    parsed = []
    for value in values:
        normalized = _norm(value)
        if normalized in CONFIDENCE_ORDER:
            parsed.append(CONFIDENCE_ORDER[normalized])
    if not parsed:
        return fallback
    return CONFIDENCE_BY_VALUE[min(parsed)]


def _metrics(capacity_item: dict[str, Any]) -> dict[str, Any]:
    resource_health = capacity_item.get('resource_health')
    resource_health = resource_health if isinstance(resource_health, dict) else {}
    bullpen_capacity = resource_health.get('bullpen_capacity')
    bullpen_capacity = bullpen_capacity if isinstance(bullpen_capacity, dict) else {}
    trust_hierarchy = capacity_item.get('trust_hierarchy')
    trust_hierarchy = trust_hierarchy if isinstance(trust_hierarchy, dict) else {}
    identity = capacity_item.get('bullpen_identity')
    identity = identity if isinstance(identity, dict) else {}

    anchor = _int(trust_hierarchy.get('anchor_count'), 0) or 0
    leverage = _int(trust_hierarchy.get('leverage_count'), 0) or 0
    trusted = _int(trust_hierarchy.get('trusted_count'), 0) or 0
    trusted_group = _int(
        trust_hierarchy.get('trusted_group_size'),
        default=anchor + leverage + trusted,
    )

    return {
        'capacity_state': (
            bullpen_capacity.get('capacity_state')
            or bullpen_capacity.get('state')
            or resource_health.get('capacity_state')
        ),
        'resource_health_state': (
            resource_health.get('resource_health_state')
            or _nested(resource_health, 'organizational_resource_health', 'resource_health_state')
        ),
        'rested_options': _int(
            bullpen_capacity.get('clean_active_reliever_count'),
            default=None,
        ),
        'usable_depth': _int(
            bullpen_capacity.get('active_reliever_count')
            or resource_health.get('active_reliever_count'),
            default=None,
        ),
        'trusted_group_size': trusted_group,
        'coverage_safety': _coverage_label(capacity_item),
        'identity_key': identity.get('identity_key'),
        'identity_confidence': identity.get('confidence'),
        'resource_confidence': resource_health.get('confidence'),
        'trust_confidence': trust_hierarchy.get('hierarchy_confidence'),
    }


def _supporting_fact(
    fact_key: str,
    previous: Any,
    current: Any,
    description: str,
) -> dict[str, Any]:
    return {
        'fact_key': fact_key,
        'previous_value': previous,
        'current_value': current,
        'description': description,
    }


def _change_facts(change: dict[str, Any], fallback_description: str) -> list[dict[str, Any]]:
    facts = change.get('supporting_facts')
    if isinstance(facts, list) and facts:
        return [
            fact
            for fact in facts
            if isinstance(fact, dict)
        ]
    return [
        _supporting_fact(
            str(change.get('change_type') or 'change'),
            None,
            change.get('change_direction'),
            fallback_description,
        )
    ]


def _context_fact(metrics: dict[str, Any], fact_key: str, description: str) -> dict[str, Any]:
    return {
        'fact_key': fact_key,
        'current_value': metrics.get(fact_key),
        'description': description,
    }


def _consequence(
    consequence_type: str,
    summary: str,
    context: str,
    *,
    significance: str,
    confidence: str,
    supporting_facts: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        'consequence_type': consequence_type,
        'consequence_summary': summary,
        'consequence_context': context,
        'significance': significance,
        'confidence': confidence,
        'supporting_facts': supporting_facts,
    }


def _capacity_flexibility(change: dict[str, Any]) -> list[dict[str, Any]]:
    direction = change.get('change_direction')
    confidence = str(change.get('confidence') or 'medium')
    if direction == 'increased':
        return [
            _consequence(
                CONSEQUENCE_MORE_FLEXIBILITY,
                'The bullpen has more flexibility than yesterday.',
                'More rested options add clean paths before the game reaches the tightest lanes.',
                significance=SIGNIFICANCE_MEANINGFUL,
                confidence=confidence,
                supporting_facts=_change_facts(change, 'Rested options increased.'),
            )
        ]
    if direction == 'decreased':
        return [
            _consequence(
                CONSEQUENCE_LESS_FLEXIBILITY,
                'The bullpen has less flexibility than yesterday.',
                'Fewer rested options leave fewer clean paths before the game reaches the tightest lanes.',
                significance=SIGNIFICANCE_MEANINGFUL,
                confidence=confidence,
                supporting_facts=_change_facts(change, 'Rested options decreased.'),
            )
        ]
    return []


def _depth_workload(change: dict[str, Any]) -> list[dict[str, Any]]:
    direction = change.get('change_direction')
    confidence = str(change.get('confidence') or 'medium')
    if direction == 'increased':
        return [
            _consequence(
                CONSEQUENCE_EASIER_WORKLOAD_DISTRIBUTION,
                'The bullpen has more ways to distribute ordinary workload.',
                'Additional usable depth spreads coverage across more of the group.',
                significance=SIGNIFICANCE_MEANINGFUL,
                confidence=confidence,
                supporting_facts=_change_facts(change, 'Usable bullpen depth increased.'),
            )
        ]
    if direction == 'decreased':
        return [
            _consequence(
                CONSEQUENCE_HEAVIER_WORKLOAD_CONCENTRATION,
                'The workload picture is more concentrated than yesterday.',
                'Less usable depth puts more of the coverage burden on a smaller part of the group.',
                significance=SIGNIFICANCE_MEANINGFUL,
                confidence=confidence,
                supporting_facts=_change_facts(change, 'Usable bullpen depth decreased.'),
            )
        ]
    return []


def _resource_flexibility(change: dict[str, Any]) -> list[dict[str, Any]]:
    direction = change.get('change_direction')
    confidence = str(change.get('confidence') or 'medium')
    if direction == 'improved':
        return [
            _consequence(
                CONSEQUENCE_MORE_FLEXIBILITY,
                'The bullpen has a little more resource flexibility than yesterday.',
                'A healthier resource picture creates more room around the active group.',
                significance=SIGNIFICANCE_STRUCTURAL,
                confidence=confidence,
                supporting_facts=_change_facts(change, 'Resource health improved.'),
            )
        ]
    if direction == 'worsened':
        return [
            _consequence(
                CONSEQUENCE_LESS_FLEXIBILITY,
                'The bullpen has less resource flexibility than yesterday.',
                'A tighter resource picture leaves less margin around the active group.',
                significance=SIGNIFICANCE_STRUCTURAL,
                confidence=confidence,
                supporting_facts=_change_facts(change, 'Resource health worsened.'),
            )
        ]
    return []


def _coverage_margin(change: dict[str, Any]) -> list[dict[str, Any]]:
    direction = change.get('change_direction')
    confidence = str(change.get('confidence') or 'medium')
    if direction == 'improved':
        return [
            _consequence(
                CONSEQUENCE_MORE_COVERAGE_MARGIN,
                'Coverage has more margin than yesterday.',
                'The bullpen has more room if the game asks for several relief innings.',
                significance=SIGNIFICANCE_STRUCTURAL,
                confidence=confidence,
                supporting_facts=_change_facts(change, 'Coverage safety improved.'),
            )
        ]
    if direction == 'worsened':
        return [
            _consequence(
                CONSEQUENCE_LESS_COVERAGE_MARGIN,
                'Coverage has less margin than yesterday.',
                'The bullpen has less room if the game asks for several relief innings.',
                significance=SIGNIFICANCE_STRUCTURAL,
                confidence=confidence,
                supporting_facts=_change_facts(change, 'Coverage safety worsened.'),
            )
        ]
    return []


def _trust_support(
    change: dict[str, Any],
    metrics: dict[str, Any],
) -> list[dict[str, Any]]:
    direction = change.get('change_direction')
    confidence = _confidence(
        change.get('confidence'),
        metrics.get('trust_confidence'),
        fallback='medium',
    )
    if direction == 'expanded':
        return [
            _consequence(
                CONSEQUENCE_WIDER_TRUST_SUPPORT,
                'The trusted group is wider than yesterday.',
                'More of the bullpen can support the bridge from middle innings to the late innings.',
                significance=SIGNIFICANCE_STRUCTURAL,
                confidence=confidence,
                supporting_facts=_change_facts(change, 'Trusted group expanded.'),
            )
        ]
    if direction != 'narrowed':
        return []

    consequences = [
        _consequence(
            CONSEQUENCE_NARROWER_TRUST_SUPPORT,
            'The trusted group is narrower than yesterday.',
            'Late-inning support has less breadth around the most trusted part of the group.',
            significance=SIGNIFICANCE_STRUCTURAL,
            confidence=confidence,
            supporting_facts=_change_facts(change, 'Trusted group narrowed.'),
        )
    ]
    trusted_group_size = metrics.get('trusted_group_size')
    if isinstance(trusted_group_size, int) and trusted_group_size <= 3:
        consequences.append(
            _consequence(
                CONSEQUENCE_HEAVIER_WORKLOAD_CONCENTRATION,
                'Workload coverage is more concentrated around the remaining trusted group.',
                'With fewer trusted options, the structure has less room to spread the middle and late innings.',
                significance=SIGNIFICANCE_STRUCTURAL,
                confidence=confidence,
                supporting_facts=[
                    *_change_facts(change, 'Trusted group narrowed.'),
                    _context_fact(
                        metrics,
                        'trusted_group_size',
                        'Current trusted-group size leaves a narrower support layer.',
                    ),
                ],
            )
        )
    return consequences


def _identity_stability(
    change: dict[str, Any],
    metrics: dict[str, Any],
) -> list[dict[str, Any]]:
    if change.get('change_direction') != 'changed':
        return []
    current_identity = metrics.get('identity_key')
    if not current_identity or current_identity == IDENTITY_UNKNOWN:
        return []

    confidence = _confidence(
        change.get('confidence'),
        metrics.get('identity_confidence'),
        fallback='low',
    )
    if current_identity in MORE_STABLE_IDENTITIES:
        return [
            _consequence(
                CONSEQUENCE_MORE_STABLE_BULLPEN_SHAPE,
                'The bullpen shape is more settled than yesterday.',
                'The current structure gives the daily read a clearer baseball shape than the prior snapshot.',
                significance=SIGNIFICANCE_STRUCTURAL,
                confidence=confidence,
                supporting_facts=[
                    *_change_facts(change, 'Bullpen identity changed.'),
                    _context_fact(
                        metrics,
                        'identity_key',
                        'Current identity points to a more defined bullpen shape.',
                    ),
                ],
            )
        ]
    if current_identity in LESS_STABLE_IDENTITIES:
        return [
            _consequence(
                CONSEQUENCE_LESS_STABLE_BULLPEN_SHAPE,
                'The bullpen shape is less settled than yesterday.',
                'The current structure is more dependent on constrained parts of the group.',
                significance=SIGNIFICANCE_STRUCTURAL,
                confidence=confidence,
                supporting_facts=[
                    *_change_facts(change, 'Bullpen identity changed.'),
                    _context_fact(
                        metrics,
                        'identity_key',
                        'Current identity points to a more constrained bullpen shape.',
                    ),
                ],
            )
        ]
    return []


def _consequences_from_change(
    change: dict[str, Any],
    metrics: dict[str, Any],
) -> list[dict[str, Any]]:
    change_type = change.get('change_type')
    if change_type == CHANGE_RESTED_OPTIONS:
        return _capacity_flexibility(change)
    if change_type == CHANGE_USABLE_DEPTH:
        return _depth_workload(change)
    if change_type == CHANGE_RESOURCE_HEALTH:
        return _resource_flexibility(change)
    if change_type == CHANGE_COVERAGE_SAFETY:
        return _coverage_margin(change)
    if change_type == CHANGE_TRUST_STRUCTURE:
        return _trust_support(change, metrics)
    if change_type == CHANGE_IDENTITY:
        return _identity_stability(change, metrics)
    return []


def _insufficient_team(
    current_item: dict[str, Any] | None,
    *,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    identity = _team_identity(current_item or {})
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': 'backend',
        **identity,
        'status': STATUS_INSUFFICIENT_CONTEXT,
        'state': STATE_INSUFFICIENT_CONTEXT,
        'consequences': [],
        'consequence_count': 0,
        'ranking_applied': False,
        'selection_made': False,
        'prediction_applied': False,
        'limitations': list(limitations or []),
    }


def build_team_consequence_intelligence(
    current_snapshot: dict[str, Any] | None,
    prior_snapshot: dict[str, Any] | None = None,
    *,
    what_changed: dict[str, Any] | None = None,
    current_payload: dict[str, Any] | None = None,
    prior_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build consequence intelligence for one team.

    If a What Changed payload is not supplied, a prior snapshot can be supplied
    and the existing change-detection layer will be used as the source of
    meaningful changes.
    """

    current_item = _capacity_item(current_snapshot)
    if not current_item:
        return _insufficient_team(current_snapshot, limitations=[NO_CURRENT_LIMITATION])

    if what_changed is None and prior_snapshot is not None:
        what_changed = build_team_what_changed_since_yesterday(
            current_item,
            prior_snapshot,
            current_payload=current_payload,
            prior_payload=prior_payload,
        )
    if not isinstance(what_changed, dict):
        return _insufficient_team(current_item, limitations=[NO_CHANGE_CONTEXT_LIMITATION])

    if what_changed.get('status') == CHANGE_STATUS_INSUFFICIENT_CONTEXT:
        return _insufficient_team(
            current_item,
            limitations=list(what_changed.get('limitations') or [CHANGE_CONTEXT_LIMITATION]),
        )

    metrics = _metrics(current_item)
    consequences = []
    for change in what_changed.get('changes') or []:
        if isinstance(change, dict):
            consequences.extend(_consequences_from_change(change, metrics))

    identity = _team_identity(current_item)
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': 'backend',
        **identity,
        'status': STATUS_AVAILABLE,
        'state': (
            STATE_CONSEQUENCES_DETECTED
            if consequences
            else STATE_NO_CONSEQUENCES
        ),
        'what_changed_state': what_changed.get('state') or STATE_NO_MEANINGFUL_CHANGES,
        'change_count': int(what_changed.get('change_count') or 0),
        'consequences': consequences,
        'consequence_count': len(consequences),
        'ranking_applied': False,
        'selection_made': False,
        'prediction_applied': False,
        'limitations': [],
    }


def build_consequence_intelligence_payload(
    current_payload: dict[str, Any] | None,
    prior_payload: dict[str, Any] | None = None,
    *,
    what_changed_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build league/team Consequence Intelligence V1 from existing reads."""

    current_teams = _capacity_by_team(current_payload)
    if not current_teams:
        return {
            'capability': CAPABILITY,
            'version': VERSION,
            'source': 'backend',
            'status': STATUS_INSUFFICIENT_CONTEXT,
            'state': STATE_INSUFFICIENT_CONTEXT,
            'ranking_applied': False,
            'selection_made': False,
            'prediction_applied': False,
            'ordering_basis': 'team_abbreviation_then_team_id',
            'consequences': [],
            'teams': [],
            'by_team_id': {},
            'teams_evaluated': 0,
            'teams_with_consequences': 0,
            'consequence_count': 0,
            'limitations': [NO_CURRENT_LIMITATION],
        }

    if what_changed_payload is None and prior_payload is not None:
        what_changed_payload = build_what_changed_since_yesterday_payload(
            current_payload,
            prior_payload,
        )

    change_teams = _change_by_team(what_changed_payload)
    no_change_context = not isinstance(what_changed_payload, dict)
    teams = []
    flat_consequences = []
    for key, current_item in sorted(
        current_teams.items(),
        key=lambda pair: (
            str(_team_abbreviation(pair[1]) or ''),
            str(pair[0]),
        ),
    ):
        team_payload = build_team_consequence_intelligence(
            current_item,
            what_changed=None if no_change_context else change_teams.get(key),
            current_payload=current_payload,
            prior_payload=prior_payload,
        )
        teams.append(team_payload)
        for consequence in team_payload.get('consequences') or []:
            flat_consequences.append({
                'team_id': team_payload.get('team_id'),
                'team_name': team_payload.get('team_name'),
                'team_abbreviation': team_payload.get('team_abbreviation'),
                **consequence,
            })

    available_count = sum(1 for team in teams if team.get('status') == STATUS_AVAILABLE)
    status = STATUS_AVAILABLE if available_count > 0 else STATUS_INSUFFICIENT_CONTEXT
    state = (
        STATE_INSUFFICIENT_CONTEXT
        if status == STATUS_INSUFFICIENT_CONTEXT
        else STATE_CONSEQUENCES_DETECTED if flat_consequences else STATE_NO_CONSEQUENCES
    )

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': 'backend',
        'status': status,
        'state': state,
        'ranking_applied': False,
        'selection_made': False,
        'prediction_applied': False,
        'ordering_basis': 'team_abbreviation_then_team_id',
        'consequences': flat_consequences,
        'teams': teams,
        'by_team_id': {
            str(team['team_id']): team
            for team in teams
            if team.get('team_id') is not None
        },
        'teams_evaluated': len(teams),
        'teams_with_consequences': sum(
            1
            for team in teams
            if team.get('consequence_count', 0) > 0
        ),
        'consequence_count': len(flat_consequences),
        'limitations': [NO_CHANGE_CONTEXT_LIMITATION] if no_change_context else [],
    }


__all__ = [
    'CAPABILITY',
    'CONSEQUENCE_EASIER_WORKLOAD_DISTRIBUTION',
    'CONSEQUENCE_HEAVIER_WORKLOAD_CONCENTRATION',
    'CONSEQUENCE_LESS_COVERAGE_MARGIN',
    'CONSEQUENCE_LESS_FLEXIBILITY',
    'CONSEQUENCE_LESS_STABLE_BULLPEN_SHAPE',
    'CONSEQUENCE_MORE_COVERAGE_MARGIN',
    'CONSEQUENCE_MORE_FLEXIBILITY',
    'CONSEQUENCE_MORE_STABLE_BULLPEN_SHAPE',
    'CONSEQUENCE_NARROWER_TRUST_SUPPORT',
    'CONSEQUENCE_WIDER_TRUST_SUPPORT',
    'STATE_CONSEQUENCES_DETECTED',
    'STATE_INSUFFICIENT_CONTEXT',
    'STATE_NO_CONSEQUENCES',
    'VERSION',
    'build_consequence_intelligence_payload',
    'build_team_consequence_intelligence',
]
