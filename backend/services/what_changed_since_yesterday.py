"""What Changed Since Yesterday V1.

This layer compares existing bullpen intelligence snapshots and explains
meaningful team-level movement. It does not predict, recommend, rank, select
relievers, or create new source data.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from services.bullpen_coverage_safety import (
    LABEL_LIMITED,
    LABEL_LIMITED_READ,
    LABEL_STABLE,
    LABEL_STRONG,
    LABEL_THIN,
    build_bullpen_coverage_safety_read,
)


CAPABILITY = 'what_changed_since_yesterday_v1'
VERSION = '2026-06-19.v1'

STATUS_AVAILABLE = 'available'
STATUS_INSUFFICIENT_CONTEXT = 'insufficient_context'

STATE_CHANGES_DETECTED = 'changes_detected'
STATE_NO_MEANINGFUL_CHANGES = 'no_meaningful_changes'
STATE_INSUFFICIENT_CONTEXT = 'insufficient_context'

CHANGE_RESTED_OPTIONS = 'rested_options_changed'
CHANGE_USABLE_DEPTH = 'usable_bullpen_depth_changed'
CHANGE_RESOURCE_HEALTH = 'resource_health_changed'
CHANGE_COVERAGE_SAFETY = 'coverage_safety_changed'
CHANGE_TRUST_STRUCTURE = 'trusted_group_changed'
CHANGE_IDENTITY = 'identity_changed'

DIRECTION_INCREASED = 'increased'
DIRECTION_DECREASED = 'decreased'
DIRECTION_IMPROVED = 'improved'
DIRECTION_WORSENED = 'worsened'
DIRECTION_EXPANDED = 'expanded'
DIRECTION_NARROWED = 'narrowed'
DIRECTION_CHANGED = 'changed'

SIGNIFICANCE_MEANINGFUL = 'meaningful'
SIGNIFICANCE_STRUCTURAL = 'structural'

MEANINGFUL_CAPACITY_DELTA = 2
MEANINGFUL_TRUST_DELTA = 2

NO_CURRENT_LIMITATION = (
    'Current bullpen intelligence is unavailable; change detection cannot be computed.'
)
NO_PRIOR_LIMITATION = (
    'No prior bullpen intelligence snapshot is available for yesterday comparison.'
)
NO_PRIOR_TEAM_LIMITATION = (
    'Prior snapshot does not include comparable bullpen intelligence for this team.'
)
INVALID_PRIOR_LIMITATION = (
    'Prior snapshot is not earlier than the current snapshot.'
)

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
    LABEL_STRONG: 0,
    LABEL_STABLE: 1,
    LABEL_THIN: 2,
    LABEL_LIMITED: 3,
    LABEL_LIMITED_READ: 4,
}
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


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if value is None:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _date_value(payload: dict[str, Any] | None) -> date | None:
    freshness = payload.get('freshness') if isinstance(payload, dict) else {}
    freshness = freshness if isinstance(freshness, dict) else {}
    direct_reference = payload.get('reference_date') if isinstance(payload, dict) else None
    return _parse_date(
        freshness.get('data_through')
        or freshness.get('latest_workload_date')
        or freshness.get('availability_reference_date')
        or freshness.get('reference_date')
        or direct_reference
    )


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


def _team_id(item: dict[str, Any] | None) -> Any:
    return (item or {}).get('team_id') or (item or {}).get('teamId')


def _team_name(item: dict[str, Any] | None) -> str | None:
    item = item or {}
    return item.get('team_name') or item.get('teamName')


def _team_abbreviation(item: dict[str, Any] | None) -> str | None:
    item = item or {}
    return item.get('team_abbreviation') or item.get('teamAbbreviation') or item.get('team')


def _team_identity(item: dict[str, Any] | None) -> dict[str, Any]:
    return {
        'team_id': _team_id(item),
        'team_name': _team_name(item),
        'team_abbreviation': _team_abbreviation(item),
    }


def _team_key(item: dict[str, Any]) -> str | None:
    team_id = _team_id(item)
    if team_id is not None:
        return str(team_id)
    abbr = _team_abbreviation(item)
    return str(abbr).lower() if abbr else None


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


def _capacity_by_team(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    teams = {}
    for item in _capacity_items(payload):
        key = _team_key(item)
        if key is not None and key not in teams:
            teams[key] = item
    return teams


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
    capacity_item: dict[str, Any],
    *,
    payload: dict[str, Any] | None = None,
    team_key: str | None = None,
) -> str | None:
    explicit = (
        _nested(capacity_item, 'coverage_safety', 'label')
        or _nested(capacity_item, 'coverageSafety', 'label')
    )
    if explicit:
        return str(explicit)
    environment = _environment_by_team(payload).get(str(team_key)) if team_key is not None else None
    read = build_bullpen_coverage_safety_read(
        capacity_item,
        bullpen_environment=environment,
    )
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


def _resource_confidence(capacity_item: dict[str, Any]) -> str:
    return _confidence(_nested(capacity_item, 'resource_health', 'confidence'), fallback='medium')


def _trust_confidence(capacity_item: dict[str, Any]) -> str:
    return _confidence(
        _nested(capacity_item, 'trust_hierarchy', 'hierarchy_confidence'),
        fallback='medium',
    )


def _identity(capacity_item: dict[str, Any]) -> dict[str, Any]:
    value = capacity_item.get('bullpen_identity')
    return value if isinstance(value, dict) else {}


def _metrics(
    capacity_item: dict[str, Any],
    *,
    payload: dict[str, Any] | None = None,
    team_key: str | None = None,
) -> dict[str, Any]:
    resource_health = capacity_item.get('resource_health')
    resource_health = resource_health if isinstance(resource_health, dict) else {}
    bullpen_capacity = resource_health.get('bullpen_capacity')
    bullpen_capacity = bullpen_capacity if isinstance(bullpen_capacity, dict) else {}
    trust_hierarchy = capacity_item.get('trust_hierarchy')
    trust_hierarchy = trust_hierarchy if isinstance(trust_hierarchy, dict) else {}
    identity = _identity(capacity_item)

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
        'coverage_safety': _coverage_label(capacity_item, payload=payload, team_key=team_key),
        'identity_key': identity.get('identity_key'),
        'identity_label': identity.get('identity_label'),
        'identity_confidence': identity.get('confidence'),
    }


def _supporting_fact(fact_key: str, previous: Any, current: Any, description: str) -> dict[str, Any]:
    return {
        'fact_key': fact_key,
        'previous_value': previous,
        'current_value': current,
        'description': description,
    }


def _change(
    change_type: str,
    direction: str,
    summary: str,
    significance: str,
    confidence: str,
    supporting_facts: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        'change_type': change_type,
        'change_direction': direction,
        'change_summary': summary,
        'significance': significance,
        'confidence': confidence,
        'supporting_facts': supporting_facts,
    }


def _state_direction(previous: str, current: str, order: dict[str, int]) -> str | None:
    previous_index = order.get(previous)
    current_index = order.get(current)
    if previous_index is None or current_index is None or previous_index == current_index:
        return None
    return DIRECTION_IMPROVED if current_index < previous_index else DIRECTION_WORSENED


def _state_change(
    current_metrics: dict[str, Any],
    prior_metrics: dict[str, Any],
    *,
    field: str,
    change_type: str,
    label: str,
    order: dict[str, int],
    confidence: str,
) -> dict[str, Any] | None:
    previous = prior_metrics.get(field)
    current = current_metrics.get(field)
    if previous not in order or current not in order or previous == current:
        return None
    direction = _state_direction(previous, current, order)
    return _change(
        change_type,
        direction,
        f'{label} {direction} from {previous} to {current}.',
        SIGNIFICANCE_STRUCTURAL,
        confidence,
        [
            _supporting_fact(
                field,
                previous,
                current,
                f'{label} moved from {previous} to {current}.',
            )
        ],
    )


def _capacity_count_change(
    current_metrics: dict[str, Any],
    prior_metrics: dict[str, Any],
    *,
    field: str,
    change_type: str,
    label: str,
    confidence: str,
) -> dict[str, Any] | None:
    previous = prior_metrics.get(field)
    current = current_metrics.get(field)
    if previous is None or current is None or previous == current:
        return None
    delta = int(current) - int(previous)
    capacity_state_changed = (
        prior_metrics.get('capacity_state') in CAPACITY_ORDER
        and current_metrics.get('capacity_state') in CAPACITY_ORDER
        and prior_metrics.get('capacity_state') != current_metrics.get('capacity_state')
    )
    if abs(delta) < MEANINGFUL_CAPACITY_DELTA and not capacity_state_changed:
        return None
    direction = DIRECTION_INCREASED if delta > 0 else DIRECTION_DECREASED
    return _change(
        change_type,
        direction,
        f'{label} {direction} from {previous} to {current}.',
        SIGNIFICANCE_MEANINGFUL,
        confidence,
        [
            _supporting_fact(
                field,
                previous,
                current,
                f'{label} moved from {previous} to {current}.',
            )
        ],
    )


def _trust_change(
    current_metrics: dict[str, Any],
    prior_metrics: dict[str, Any],
    *,
    confidence: str,
) -> dict[str, Any] | None:
    previous = prior_metrics.get('trusted_group_size')
    current = current_metrics.get('trusted_group_size')
    if previous is None or current is None or previous == current:
        return None
    delta = int(current) - int(previous)
    if abs(delta) < MEANINGFUL_TRUST_DELTA:
        return None
    direction = DIRECTION_EXPANDED if delta > 0 else DIRECTION_NARROWED
    return _change(
        CHANGE_TRUST_STRUCTURE,
        direction,
        f'Trusted group {direction} from {previous} to {current}.',
        SIGNIFICANCE_STRUCTURAL,
        confidence,
        [
            _supporting_fact(
                'trusted_group_size',
                previous,
                current,
                f'Trusted-group size moved from {previous} to {current}.',
            )
        ],
    )


def _identity_change(
    current_metrics: dict[str, Any],
    prior_metrics: dict[str, Any],
    *,
    confidence: str,
) -> dict[str, Any] | None:
    previous = prior_metrics.get('identity_key')
    current = current_metrics.get('identity_key')
    if not previous or not current or previous == current:
        return None
    if previous == 'unknown_insufficient_context' or current == 'unknown_insufficient_context':
        return None
    previous_label = prior_metrics.get('identity_label') or previous
    current_label = current_metrics.get('identity_label') or current
    return _change(
        CHANGE_IDENTITY,
        DIRECTION_CHANGED,
        f'Bullpen identity changed from {previous_label} to {current_label}.',
        SIGNIFICANCE_STRUCTURAL,
        confidence,
        [
            _supporting_fact(
                'identity_key',
                previous,
                current,
                f'Identity key moved from {previous} to {current}.',
            )
        ],
    )


def _team_changes(
    current_item: dict[str, Any],
    prior_item: dict[str, Any],
    *,
    current_payload: dict[str, Any] | None = None,
    prior_payload: dict[str, Any] | None = None,
    team_key: str | None = None,
) -> list[dict[str, Any]]:
    current_metrics = _metrics(current_item, payload=current_payload, team_key=team_key)
    prior_metrics = _metrics(prior_item, payload=prior_payload, team_key=team_key)
    resource_confidence = _confidence(
        _resource_confidence(current_item),
        _resource_confidence(prior_item),
        fallback='medium',
    )
    trust_confidence = _confidence(
        _trust_confidence(current_item),
        _trust_confidence(prior_item),
        fallback='medium',
    )
    coverage_confidence = _confidence(resource_confidence, trust_confidence, fallback='medium')
    identity_confidence = _confidence(
        current_metrics.get('identity_confidence'),
        prior_metrics.get('identity_confidence'),
        fallback='low',
    )

    candidates = [
        _capacity_count_change(
            current_metrics,
            prior_metrics,
            field='rested_options',
            change_type=CHANGE_RESTED_OPTIONS,
            label='Rested options',
            confidence=resource_confidence,
        ),
        _capacity_count_change(
            current_metrics,
            prior_metrics,
            field='usable_depth',
            change_type=CHANGE_USABLE_DEPTH,
            label='Usable bullpen depth',
            confidence=resource_confidence,
        ),
        _state_change(
            current_metrics,
            prior_metrics,
            field='resource_health_state',
            change_type=CHANGE_RESOURCE_HEALTH,
            label='Resource health',
            order=RESOURCE_HEALTH_ORDER,
            confidence=resource_confidence,
        ),
        _state_change(
            current_metrics,
            prior_metrics,
            field='coverage_safety',
            change_type=CHANGE_COVERAGE_SAFETY,
            label='Coverage safety',
            order=COVERAGE_SAFETY_ORDER,
            confidence=coverage_confidence,
        ),
        _trust_change(current_metrics, prior_metrics, confidence=trust_confidence),
        _identity_change(current_metrics, prior_metrics, confidence=identity_confidence),
    ]
    return [item for item in candidates if item is not None]


def _base_team_payload(
    current_item: dict[str, Any],
    *,
    reference_date: date | None = None,
    prior_date: date | None = None,
) -> dict[str, Any]:
    return {
        **_team_identity(current_item),
        'status': STATUS_AVAILABLE,
        'state': STATE_NO_MEANINGFUL_CHANGES,
        'reference_date': _iso(reference_date),
        'prior_date': _iso(prior_date),
        'changes': [],
        'change_count': 0,
        'limitations': [],
    }


def _insufficient_team(
    current_item: dict[str, Any] | None,
    *,
    reference_date: date | None = None,
    prior_date: date | None = None,
    limitations: list[str] | None = None,
) -> dict[str, Any]:
    return {
        **_team_identity(current_item or {}),
        'status': STATUS_INSUFFICIENT_CONTEXT,
        'state': STATE_INSUFFICIENT_CONTEXT,
        'reference_date': _iso(reference_date),
        'prior_date': _iso(prior_date),
        'changes': [],
        'change_count': 0,
        'limitations': list(limitations or []),
    }


def build_team_what_changed_since_yesterday(
    current_snapshot: dict[str, Any] | None,
    prior_snapshot: dict[str, Any] | None,
    *,
    current_payload: dict[str, Any] | None = None,
    prior_payload: dict[str, Any] | None = None,
    reference_date: date | None = None,
    prior_date: date | None = None,
) -> dict[str, Any]:
    """Compare one team's current and prior bullpen intelligence snapshots."""
    current_item = _capacity_item(current_snapshot)
    prior_item = _capacity_item(prior_snapshot)
    if not current_item:
        return _insufficient_team(
            current_snapshot,
            reference_date=reference_date,
            prior_date=prior_date,
            limitations=[NO_CURRENT_LIMITATION],
        )
    if not prior_item:
        return _insufficient_team(
            current_item,
            reference_date=reference_date,
            prior_date=prior_date,
            limitations=[NO_PRIOR_TEAM_LIMITATION],
        )

    key = _team_key(current_item)
    payload = _base_team_payload(
        current_item,
        reference_date=reference_date,
        prior_date=prior_date,
    )
    current_metrics = _metrics(
        current_item,
        payload=current_payload,
        team_key=key,
    )
    prior_metrics = _metrics(
        prior_item,
        payload=prior_payload,
        team_key=key,
    )
    payload['rested_counts'] = {
        'yesterday_rested_count': prior_metrics.get('rested_options'),
        'today_rested_count': current_metrics.get('rested_options'),
    }
    changes = _team_changes(
        current_item,
        prior_item,
        current_payload=current_payload,
        prior_payload=prior_payload,
        team_key=key,
    )
    payload.update({
        'changes': changes,
        'change_count': len(changes),
        'state': STATE_CHANGES_DETECTED if changes else STATE_NO_MEANINGFUL_CHANGES,
    })
    return payload


def build_what_changed_since_yesterday_payload(
    current_payload: dict[str, Any] | None,
    prior_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build league/team change detection from current and prior dashboard snapshots."""
    current_date = _date_value(current_payload)
    prior_date = _date_value(prior_payload)
    current_teams = _capacity_by_team(current_payload)
    prior_teams = _capacity_by_team(prior_payload)

    if not current_teams:
        return {
            'capability': CAPABILITY,
            'version': VERSION,
            'source': 'backend',
            'status': STATUS_INSUFFICIENT_CONTEXT,
            'state': STATE_INSUFFICIENT_CONTEXT,
            'reference_date': _iso(current_date),
            'prior_date': _iso(prior_date),
            'ranking_applied': False,
            'selection_made': False,
            'prediction_applied': False,
            'changes': [],
            'teams': [],
            'by_team_id': {},
            'teams_evaluated': 0,
            'teams_compared': 0,
            'change_count': 0,
            'limitations': [NO_CURRENT_LIMITATION],
        }

    league_limitations = []
    history_missing = prior_payload is None or prior_date is None
    invalid_prior = prior_date is not None and current_date is not None and prior_date >= current_date
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
                reference_date=current_date,
                prior_date=prior_date,
                limitations=league_limitations,
            )
        else:
            team_payload = build_team_what_changed_since_yesterday(
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

    compared = sum(1 for team in teams if team.get('status') == STATUS_AVAILABLE)
    status = STATUS_AVAILABLE if compared > 0 and not league_limitations else STATUS_INSUFFICIENT_CONTEXT
    state = (
        STATE_INSUFFICIENT_CONTEXT
        if status == STATUS_INSUFFICIENT_CONTEXT
        else STATE_CHANGES_DETECTED if flat_changes else STATE_NO_MEANINGFUL_CHANGES
    )

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': 'backend',
        'status': status,
        'state': state,
        'reference_date': _iso(current_date),
        'prior_date': _iso(prior_date),
        'ranking_applied': False,
        'selection_made': False,
        'prediction_applied': False,
        'changes': flat_changes,
        'teams': teams,
        'by_team_id': {
            str(team['team_id']): team
            for team in teams
            if team.get('team_id') is not None
        },
        'teams_evaluated': len(teams),
        'teams_compared': compared,
        'change_count': len(flat_changes),
        'limitations': league_limitations,
    }


__all__ = [
    'CAPABILITY',
    'CHANGE_COVERAGE_SAFETY',
    'CHANGE_IDENTITY',
    'CHANGE_RESOURCE_HEALTH',
    'CHANGE_RESTED_OPTIONS',
    'CHANGE_TRUST_STRUCTURE',
    'CHANGE_USABLE_DEPTH',
    'STATE_CHANGES_DETECTED',
    'STATE_INSUFFICIENT_CONTEXT',
    'STATE_NO_MEANINGFUL_CHANGES',
    'VERSION',
    'build_team_what_changed_since_yesterday',
    'build_what_changed_since_yesterday_payload',
]
