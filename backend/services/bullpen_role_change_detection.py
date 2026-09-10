"""Deterministic bullpen role structure change detection.

This layer compares current and prior dashboard intelligence snapshots. It
describes team-level structural movement only; it does not select pitchers,
recommend usage, predict performance, or generate public story prose.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from services.bullpen_coverage_safety import build_bullpen_coverage_safety_read


CAPABILITY = 'bullpen_role_change_detection_v1'
VERSION = '2026-06-19'

STATUS_AVAILABLE = 'available'
STATUS_INSUFFICIENT_HISTORY = 'insufficient_history'
STATUS_UNAVAILABLE = 'unavailable'

DIRECTION_IMPROVED = 'improved'
DIRECTION_DECLINED = 'declined'
DIRECTION_EXPANDED = 'expanded'
DIRECTION_CONTRACTED = 'contracted'

SEVERITY_MINOR = 'minor'
SEVERITY_MEANINGFUL = 'meaningful'
SEVERITY_MAJOR = 'major'

CAPACITY_ORDER = {
    'healthy': 0,
    'reduced': 1,
    'thin': 2,
    'depleted': 3,
}
RESOURCE_HEALTH_ORDER = {
    'strong': 0,
    'moderate': 1,
    'strained': 2,
    'depleted': 3,
}
COVERAGE_SAFETY_ORDER = {
    'Strong Coverage Safety': 0,
    'Stable Coverage Safety': 1,
    'Thin Coverage Safety': 2,
    'Limited Coverage Safety': 3,
    'Limited Read': 4,
}

NO_CURRENT_LIMITATION = (
    'Current bullpen intelligence is unavailable; role changes cannot be computed.'
)
NO_PRIOR_LIMITATION = (
    'No prior bullpen dashboard snapshot is available for role change comparison.'
)
NO_PRIOR_TEAM_LIMITATION = (
    'Prior bullpen dashboard snapshot does not include comparable team bullpen intelligence.'
)
INVALID_PRIOR_LIMITATION = (
    'Prior bullpen dashboard snapshot is not earlier than the current snapshot.'
)


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


def _date_value(payload: dict[str, Any] | None) -> date | None:
    freshness = payload.get('freshness') if isinstance(payload, dict) else {}
    freshness = freshness if isinstance(freshness, dict) else {}
    return _parse_date(
        freshness.get('data_through')
        or freshness.get('latest_workload_date')
        or freshness.get('availability_reference_date')
        or freshness.get('reference_date')
    )


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _int(value: Any, default: int | None = 0) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _nested(mapping: dict[str, Any] | None, *keys, default=None):
    current = mapping or {}
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if current is not None else default


def _team_id(item: dict[str, Any] | None) -> Any:
    return (item or {}).get('team_id') or (item or {}).get('teamId')


def _team_name(item: dict[str, Any] | None) -> str | None:
    item = item or {}
    return item.get('team_name') or item.get('teamName')


def _team_abbreviation(item: dict[str, Any] | None) -> str | None:
    item = item or {}
    return item.get('team_abbreviation') or item.get('teamAbbreviation') or item.get('team')


def _team_identity(item: dict[str, Any] | None) -> dict[str, Any]:
    team_id = _team_id(item)
    return {
        'team_id': team_id,
        'team_name': _team_name(item),
        'team_abbreviation': _team_abbreviation(item),
    }


def _team_key(item: dict[str, Any]) -> str | None:
    team_id = _team_id(item)
    if team_id is not None:
        return str(team_id)
    abbr = _team_abbreviation(item)
    return str(abbr).lower() if abbr else None


def _capacity_items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    capacity = payload.get('capacity_intelligence') if isinstance(payload, dict) else {}
    capacity = capacity if isinstance(capacity, dict) else {}
    teams = capacity.get('teams')
    if isinstance(teams, list):
        return [item for item in teams if isinstance(item, dict)]
    by_team = capacity.get('by_team_id')
    if isinstance(by_team, dict):
        return [item for item in by_team.values() if isinstance(item, dict)]
    return []


def _capacity_by_team(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    teams = {}
    for item in _capacity_items(payload):
        key = _team_key(item)
        if key is not None and key not in teams:
            teams[key] = item
    return teams


def has_role_change_detection_inputs(payload: dict[str, Any] | None) -> bool:
    """Return whether a dashboard payload can be used as a comparison source."""
    return _date_value(payload) is not None and bool(_capacity_by_team(payload))


def _environment_by_team(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    environment = payload.get('bullpen_environment') if isinstance(payload, dict) else {}
    environment = environment if isinstance(environment, dict) else {}
    by_team = environment.get('by_team_id')
    if isinstance(by_team, dict):
        return {
            str(key): value
            for key, value in by_team.items()
            if isinstance(value, dict)
        }
    teams = environment.get('teams')
    if isinstance(teams, list):
        return {
            str(_team_id(item)): item
            for item in teams
            if isinstance(item, dict) and _team_id(item) is not None
        }
    return {}


def _coverage_label(
    team_item: dict[str, Any] | None,
    environment: dict[str, Any] | None,
) -> str | None:
    explicit = (
        _nested(team_item, 'coverage_safety', 'label')
        or _nested(team_item, 'coverageSafety', 'label')
    )
    if explicit:
        return str(explicit)
    read = build_bullpen_coverage_safety_read(
        team_item,
        bullpen_environment=environment,
    )
    return read.get('label') if isinstance(read, dict) else None


def _clean_trusted_options(item: dict[str, Any]) -> int | None:
    for direct in (
        item.get('clean_trusted_options_count'),
        item.get('clean_trust_count'),
        item.get('cleanTrustedOptionsCount'),
        _nested(item, 'team_shape', 'supportingCounts', 'cleanTrustArms'),
        _nested(item, 'team_shape', 'cleanOptions', 'supportingCounts', 'cleanTrustArms'),
    ):
        parsed = _int(direct, default=None)
        if parsed is not None:
            return parsed
    return None


def _team_metrics(
    payload: dict[str, Any] | None,
    team_key: str,
    item: dict[str, Any],
) -> dict[str, Any]:
    resource_health = item.get('resource_health') if isinstance(item, dict) else {}
    resource_health = resource_health if isinstance(resource_health, dict) else {}
    bullpen_capacity = resource_health.get('bullpen_capacity')
    bullpen_capacity = bullpen_capacity if isinstance(bullpen_capacity, dict) else {}
    trust_hierarchy = item.get('trust_hierarchy')
    trust_hierarchy = trust_hierarchy if isinstance(trust_hierarchy, dict) else {}
    trust_capacity_loss = item.get('trust_capacity_loss')
    trust_capacity_loss = trust_capacity_loss if isinstance(trust_capacity_loss, dict) else {}
    environment = _environment_by_team(payload).get(str(team_key)) if isinstance(payload, dict) else {}

    anchor = _int(trust_hierarchy.get('anchor_count'))
    leverage = _int(trust_hierarchy.get('leverage_count'))
    trusted = _int(trust_hierarchy.get('trusted_count'))
    trusted_group = _int(
        trust_hierarchy.get('trusted_group_size'),
        default=(anchor or 0) + (leverage or 0) + (trusted or 0),
    )

    return {
        'capacity_state': (
            bullpen_capacity.get('capacity_state')
            or resource_health.get('capacity_state')
        ),
        'resource_health_state': (
            resource_health.get('resource_health_state')
            or _nested(resource_health, 'organizational_resource_health', 'resource_health_state')
        ),
        'coverage_safety': _coverage_label(item, environment),
        'anchor_count': anchor,
        'leverage_count': leverage,
        'trusted_group_size': trusted_group,
        'clean_trusted_options_count': _clean_trusted_options(item),
        'trust_arms_unavailable': _int(trust_capacity_loss.get('trust_arms_unavailable')),
    }


def _state_direction(previous: str, current: str, order: dict[str, int]) -> str | None:
    previous_index = order.get(previous)
    current_index = order.get(current)
    if previous_index is None or current_index is None or previous_index == current_index:
        return None
    return DIRECTION_IMPROVED if current_index < previous_index else DIRECTION_DECLINED


def _state_severity(previous: str, current: str, order: dict[str, int]) -> str:
    delta = abs(order[current] - order[previous])
    if delta >= 2:
        return SEVERITY_MAJOR
    return SEVERITY_MEANINGFUL


def _count_direction(previous: int, current: int, *, inverse=False) -> str | None:
    if previous == current:
        return None
    if inverse:
        return DIRECTION_IMPROVED if current < previous else DIRECTION_DECLINED
    return DIRECTION_EXPANDED if current > previous else DIRECTION_CONTRACTED


def _count_severity(delta: int, *, one_is_meaningful=False) -> str:
    magnitude = abs(delta)
    if magnitude >= 3:
        return SEVERITY_MAJOR
    if magnitude >= 2 or one_is_meaningful:
        return SEVERITY_MEANINGFUL
    return SEVERITY_MINOR


def _change(
    change_type: str,
    direction: str,
    severity: str,
    summary: str,
    previous: Any,
    current: Any,
) -> dict[str, Any]:
    return {
        'type': change_type,
        'direction': direction,
        'severity': severity,
        'summary': summary,
        'evidence': {
            'previous': {'value': previous},
            'current': {'value': current},
        },
    }


def _state_change(
    metrics_prior: dict[str, Any],
    metrics_current: dict[str, Any],
    *,
    field: str,
    change_type: str,
    label: str,
    order: dict[str, int],
) -> dict[str, Any] | None:
    previous = metrics_prior.get(field)
    current = metrics_current.get(field)
    if previous not in order or current not in order or previous == current:
        return None
    direction = _state_direction(previous, current, order)
    return _change(
        change_type,
        direction,
        _state_severity(previous, current, order),
        f'{label} moved from {previous} to {current}.',
        previous,
        current,
    )


def _count_change(
    metrics_prior: dict[str, Any],
    metrics_current: dict[str, Any],
    *,
    field: str,
    change_type: str,
    label: str,
    inverse=False,
    one_is_meaningful=False,
) -> dict[str, Any] | None:
    previous = metrics_prior.get(field)
    current = metrics_current.get(field)
    if previous is None or current is None or previous == current:
        return None
    direction = _count_direction(previous, current, inverse=inverse)
    if change_type == 'anchor_count_change' and previous <= 0 < current:
        summary = f'Anchor emerged from {previous} to {current}.'
    elif change_type == 'anchor_count_change' and current <= 0 < previous:
        summary = f'Anchor lost from {previous} to {current}.'
    elif change_type == 'trusted_unavailability_change' and current > previous:
        summary = f'Trusted unavailability worsened from {previous} to {current}.'
    elif change_type == 'trusted_unavailability_change':
        summary = f'Trusted unavailability improved from {previous} to {current}.'
    else:
        summary = f'{label} {direction} from {previous} to {current}.'
    return _change(
        change_type,
        direction,
        _count_severity(current - previous, one_is_meaningful=one_is_meaningful),
        summary,
        previous,
        current,
    )


def _team_changes(metrics_current: dict[str, Any], metrics_prior: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [
        _state_change(
            metrics_prior,
            metrics_current,
            field='capacity_state',
            change_type='capacity_state_change',
            label='Capacity state',
            order=CAPACITY_ORDER,
        ),
        _state_change(
            metrics_prior,
            metrics_current,
            field='resource_health_state',
            change_type='resource_health_change',
            label='Resource health',
            order=RESOURCE_HEALTH_ORDER,
        ),
        _state_change(
            metrics_prior,
            metrics_current,
            field='coverage_safety',
            change_type='coverage_safety_change',
            label='Coverage safety',
            order=COVERAGE_SAFETY_ORDER,
        ),
        _count_change(
            metrics_prior,
            metrics_current,
            field='anchor_count',
            change_type='anchor_count_change',
            label='Anchor count',
            one_is_meaningful=True,
        ),
        _count_change(
            metrics_prior,
            metrics_current,
            field='leverage_count',
            change_type='leverage_count_change',
            label='Leverage group',
        ),
        _count_change(
            metrics_prior,
            metrics_current,
            field='trusted_group_size',
            change_type='trusted_group_change',
            label='Trusted group',
        ),
        _count_change(
            metrics_prior,
            metrics_current,
            field='clean_trusted_options_count',
            change_type='clean_trusted_options_change',
            label='Clean trusted options',
        ),
        _count_change(
            metrics_prior,
            metrics_current,
            field='trust_arms_unavailable',
            change_type='trusted_unavailability_change',
            label='Trusted unavailability',
            inverse=True,
            one_is_meaningful=True,
        ),
    ]
    return [item for item in candidates if item is not None]


def _insufficient_team(
    current_item: dict[str, Any],
    current_date: date | None,
    prior_date: date | None,
    limitations: list[str],
) -> dict[str, Any]:
    return {
        **_team_identity(current_item),
        'status': STATUS_INSUFFICIENT_HISTORY,
        'reference_date': _iso(current_date),
        'prior_date': _iso(prior_date),
        'changes': [],
        'change_count': 0,
        'limitations': list(limitations),
    }


def build_team_role_change_detection(
    current_item: dict[str, Any],
    prior_item: dict[str, Any] | None,
    *,
    current_payload: dict[str, Any] | None = None,
    prior_payload: dict[str, Any] | None = None,
    reference_date: date | None = None,
    prior_date: date | None = None,
) -> dict[str, Any]:
    """Compare one team bullpen intelligence item with its prior snapshot item."""
    if prior_item is None:
        return _insufficient_team(
            current_item,
            reference_date,
            prior_date,
            [NO_PRIOR_TEAM_LIMITATION],
        )

    key = _team_key(current_item)
    prior_key = _team_key(prior_item)
    current_metrics = _team_metrics(current_payload, key or '', current_item)
    prior_metrics = _team_metrics(prior_payload, prior_key or key or '', prior_item)
    changes = _team_changes(current_metrics, prior_metrics)
    return {
        **_team_identity(current_item),
        'status': STATUS_AVAILABLE,
        'reference_date': _iso(reference_date),
        'prior_date': _iso(prior_date),
        'changes': changes,
        'change_count': len(changes),
        'limitations': [],
    }


def build_role_change_detection_payload(
    current_payload: dict[str, Any] | None,
    prior_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build league/team role structure change detection from dashboard payloads."""
    current_date = _date_value(current_payload)
    prior_date = _date_value(prior_payload)
    current_teams = _capacity_by_team(current_payload)
    prior_teams = _capacity_by_team(prior_payload)

    if not current_teams or current_date is None:
        return {
            'capability': CAPABILITY,
            'version': VERSION,
            'source': 'backend',
            'status': STATUS_UNAVAILABLE,
            'reference_date': _iso(current_date),
            'prior_date': _iso(prior_date),
            'ranking_applied': False,
            'selection_made': False,
            'changes': [],
            'teams': [],
            'by_team_id': {},
            'teams_evaluated': 0,
            'teams_compared': 0,
            'change_count': 0,
            'limitations': [NO_CURRENT_LIMITATION],
        }

    history_missing = prior_payload is None or prior_date is None
    invalid_prior = prior_date is not None and prior_date >= current_date
    league_limitations = []
    if history_missing:
        league_limitations.append(NO_PRIOR_LIMITATION)
    elif invalid_prior:
        league_limitations.append(INVALID_PRIOR_LIMITATION)

    teams = []
    flat_changes = []
    for key, current_item in sorted(
        current_teams.items(),
        key=lambda pair: (
            str(_team_abbreviation(pair[1]) or ''),
            str(pair[0]),
        ),
    ):
        if history_missing or invalid_prior:
            team_payload = _insufficient_team(
                current_item,
                current_date,
                prior_date,
                league_limitations,
            )
        else:
            team_payload = build_team_role_change_detection(
                current_item,
                prior_teams.get(key),
                current_payload=current_payload,
                prior_payload=prior_payload,
                reference_date=current_date,
                prior_date=prior_date,
            )
        teams.append(team_payload)
        for change in team_payload['changes']:
            flat_changes.append({
                'team_id': team_payload.get('team_id'),
                'team_name': team_payload.get('team_name'),
                'team_abbreviation': team_payload.get('team_abbreviation'),
                **change,
            })

    available_team_count = sum(1 for team in teams if team.get('status') == STATUS_AVAILABLE)
    if league_limitations:
        status = STATUS_INSUFFICIENT_HISTORY
    elif available_team_count <= 0:
        status = STATUS_INSUFFICIENT_HISTORY
        league_limitations = [NO_PRIOR_TEAM_LIMITATION]
    else:
        status = STATUS_AVAILABLE
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': 'backend',
        'status': status,
        'reference_date': _iso(current_date),
        'prior_date': _iso(prior_date),
        'ranking_applied': False,
        'selection_made': False,
        'changes': flat_changes,
        'teams': teams,
        'by_team_id': {
            str(team['team_id']): team
            for team in teams
            if team.get('team_id') is not None
        },
        'teams_evaluated': len(teams),
        'teams_compared': available_team_count,
        'change_count': len(flat_changes),
        'limitations': league_limitations,
    }


__all__ = [
    'CAPABILITY',
    'STATUS_AVAILABLE',
    'STATUS_INSUFFICIENT_HISTORY',
    'STATUS_UNAVAILABLE',
    'VERSION',
    'build_role_change_detection_payload',
    'build_team_role_change_detection',
    'has_role_change_detection_inputs',
]
