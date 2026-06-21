"""Story Observation Engine V1.

Internal structured intelligence only. This module identifies bullpen
observation types from existing context layers, but it does not render story
copy, create public UI, alter scoring, infer roles, or predict future usage.
"""

from __future__ import annotations

from typing import Any

from models.pitcher import Pitcher
from services.bullpen_context import build_team_bullpen_context
from utils.db import db


CAPABILITY = 'story_observation_engine_v1'
VERSION = '2026-06-21.v1'
SOURCE = 'backend'

TYPE_ROTATION_PRESSURE = 'rotation_pressure'
TYPE_CONCENTRATION_PRESSURE = 'concentration_pressure'
TYPE_OPTIONALITY_STRENGTH = 'optionality_strength'
TYPE_STABLE_CORE = 'stable_core'
TYPE_CORE_TRANSITION = 'core_transition'
TYPE_DEPTH_PRESSURE = 'depth_pressure'

SEVERITY_LOW = 'low'
SEVERITY_MEDIUM = 'medium'
SEVERITY_HIGH = 'high'

ROTATION_TREND_PRESSURE_THRESHOLD = -0.5
ROTATION_TREND_HIGH_PRESSURE_THRESHOLD = -1.0
EARLY_BULLPEN_ENTRY_PRESSURE_THRESHOLD = 40.0
EARLY_BULLPEN_ENTRY_HIGH_PRESSURE_THRESHOLD = 60.0

CONCENTRATION_PRESSURE_BANDS = {'concentrated', 'narrow'}
OPTIONALITY_STRENGTH_BANDS = {'flexible', 'deep'}
STABLE_CORE_BANDS = {'stable'}
CORE_TRANSITION_BANDS = {'transitioning', 'rebuilding'}
DEPTH_PRESSURE_BANDS = {'moderate', 'heavy'}

SEVERITY_ORDER = {
    SEVERITY_HIGH: 3,
    SEVERITY_MEDIUM: 2,
    SEVERITY_LOW: 1,
}

TYPE_PRIORITY = {
    TYPE_ROTATION_PRESSURE: 60,
    TYPE_CONCENTRATION_PRESSURE: 50,
    TYPE_DEPTH_PRESSURE: 45,
    TYPE_CORE_TRANSITION: 40,
    TYPE_OPTIONALITY_STRENGTH: 30,
    TYPE_STABLE_CORE: 20,
}


def _number(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _list(value):
    return value if isinstance(value, list) else []


def _dict(value):
    return value if isinstance(value, dict) else {}


def _team_identity(team_context: dict[str, Any]) -> dict[str, Any]:
    team = _dict(team_context.get('team'))
    team_id = team_context.get('team_id') or team.get('team_id')
    team_name = (
        team.get('team_name')
        or team_context.get('team_name')
        or team_context.get('team')
    )
    team_abbreviation = (
        team.get('team_abbreviation')
        or team_context.get('team_abbreviation')
    )
    return {
        'team_id': team_id,
        'team_name': team_name,
        'team_abbreviation': team_abbreviation,
    }


def _context_limitations(team_context: dict[str, Any], layer: dict[str, Any]) -> list[str]:
    return [
        *[item for item in _list(layer.get('limitations')) if item],
        *[item for item in _list(team_context.get('limitations')) if item],
    ]


def _observation(
    team_context: dict[str, Any],
    observation_type: str,
    severity: str,
    *,
    source_layers: list[str],
    headline_inputs: dict[str, Any],
    baseline_inputs: dict[str, Any] | None = None,
    cause_inputs: dict[str, Any] | None = None,
    constraint_inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    identity = _team_identity(team_context)
    return {
        'team_id': identity['team_id'],
        'team': identity['team_name'],
        'team_abbreviation': identity['team_abbreviation'],
        'type': observation_type,
        'severity': severity,
        'source_layers': source_layers,
        'headline_inputs': headline_inputs or {},
        'baseline_inputs': baseline_inputs or {},
        'cause_inputs': cause_inputs or {},
        'constraint_inputs': constraint_inputs or {},
    }


def _rotation_pressure(team_context: dict[str, Any]) -> dict[str, Any] | None:
    rotation = _dict(team_context.get('rotation_context'))
    if rotation.get('context_available') is False:
        return None

    trend = _number(rotation.get('rotation_ip_trend'))
    early_entry_rate = _number(rotation.get('early_bullpen_entry_rate'))
    trend_trigger = (
        trend is not None
        and trend <= ROTATION_TREND_PRESSURE_THRESHOLD
    )
    early_trigger = (
        early_entry_rate is not None
        and early_entry_rate >= EARLY_BULLPEN_ENTRY_PRESSURE_THRESHOLD
    )
    if not trend_trigger and not early_trigger:
        return None

    severity = SEVERITY_MEDIUM
    if (
        trend is not None
        and trend <= ROTATION_TREND_HIGH_PRESSURE_THRESHOLD
    ) or (
        early_entry_rate is not None
        and early_entry_rate >= EARLY_BULLPEN_ENTRY_HIGH_PRESSURE_THRESHOLD
    ):
        severity = SEVERITY_HIGH

    return _observation(
        team_context,
        TYPE_ROTATION_PRESSURE,
        severity,
        source_layers=['rotation_context'],
        headline_inputs={
            'rotation_avg_ip_7d': rotation.get('rotation_avg_ip_7d'),
            'rotation_avg_ip_14d': rotation.get('rotation_avg_ip_14d'),
            'rotation_ip_trend': rotation.get('rotation_ip_trend'),
            'early_bullpen_entry_rate': rotation.get('early_bullpen_entry_rate'),
        },
        baseline_inputs={
            'rotation_avg_ip_14d': rotation.get('rotation_avg_ip_14d'),
            'rotation_games_analyzed_14d': rotation.get('rotation_games_analyzed_14d'),
            'rotation_trend_pressure_threshold': ROTATION_TREND_PRESSURE_THRESHOLD,
            'early_bullpen_entry_pressure_threshold': EARLY_BULLPEN_ENTRY_PRESSURE_THRESHOLD,
        },
        cause_inputs={
            'bullpen_coverage_ip_7d': rotation.get('bullpen_coverage_ip_7d'),
            'early_bullpen_entry_games_14d': (
                rotation.get('rotation_early_bullpen_entry_games_14d')
                or rotation.get('early_bullpen_entry_games_14d')
            ),
            'rotation_games_analyzed_7d': rotation.get('rotation_games_analyzed_7d'),
        },
        constraint_inputs={
            'limitations': _context_limitations(team_context, rotation),
        },
    )


def _concentration_pressure(team_context: dict[str, Any]) -> dict[str, Any] | None:
    concentration = _dict(team_context.get('bullpen_concentration_context'))
    band = concentration.get('concentration_band')
    if band not in CONCENTRATION_PRESSURE_BANDS:
        return None

    rotation = _dict(team_context.get('rotation_context'))
    stability = _dict(team_context.get('role_stability_context'))
    severity = SEVERITY_HIGH if band == 'narrow' else SEVERITY_MEDIUM
    return _observation(
        team_context,
        TYPE_CONCENTRATION_PRESSURE,
        severity,
        source_layers=['bullpen_concentration_context', 'rotation_context', 'role_stability_context'],
        headline_inputs={
            'top_three_workload_share_10d': concentration.get('top_three_workload_share_10d'),
            'concentration_band': band,
            'bullpen_workload_total_10d': concentration.get('bullpen_workload_total_10d'),
        },
        baseline_inputs={
            'league_top_three_workload_share_10d': (
                concentration.get('league_top_three_workload_share_10d')
            ),
            'top_three_share_delta_vs_league': concentration.get('top_three_share_delta_vs_league'),
            'league_team_count_10d': concentration.get('league_team_count_10d'),
        },
        cause_inputs={
            'rotation_avg_ip_7d': rotation.get('rotation_avg_ip_7d'),
            'rotation_avg_ip_14d': rotation.get('rotation_avg_ip_14d'),
            'rotation_ip_trend': rotation.get('rotation_ip_trend'),
            'early_bullpen_entry_rate': rotation.get('early_bullpen_entry_rate'),
        },
        constraint_inputs={
            'top_three_relievers_10d': _list(concentration.get('top_three_relievers_10d')),
            'current_operational_core': _list(stability.get('current_operational_core')),
            'limitations': _context_limitations(team_context, concentration),
        },
    )


def _optionality_strength(team_context: dict[str, Any]) -> dict[str, Any] | None:
    optionality = _dict(team_context.get('bullpen_optionality_context'))
    band = optionality.get('optionality_band')
    if band not in OPTIONALITY_STRENGTH_BANDS:
        return None

    severity = SEVERITY_HIGH if band == 'deep' else SEVERITY_MEDIUM
    return _observation(
        team_context,
        TYPE_OPTIONALITY_STRENGTH,
        severity,
        source_layers=['bullpen_optionality_context'],
        headline_inputs={
            'optionality_band': band,
            'practical_close_game_paths_count': optionality.get('practical_close_game_paths_count'),
        },
        baseline_inputs={
            'available_arms_count': optionality.get('available_arms_count'),
            'monitor_arms_count': optionality.get('monitor_arms_count'),
            'restricted_arms_count': optionality.get('restricted_arms_count'),
        },
        cause_inputs={
            'clean_workload_option_count': len(_list(optionality.get('clean_workload_options'))),
            'secondary_option_count': len(_list(optionality.get('secondary_options'))),
            'clean_workload_options': _list(optionality.get('clean_workload_options')),
            'secondary_options': _list(optionality.get('secondary_options')),
        },
        constraint_inputs={
            'limited_arms_count': optionality.get('limited_arms_count'),
            'avoid_arms_count': optionality.get('avoid_arms_count'),
            'unavailable_arms_count': optionality.get('unavailable_arms_count'),
            'limitations': _context_limitations(team_context, optionality),
        },
    )


def _stable_core(team_context: dict[str, Any]) -> dict[str, Any] | None:
    stability = _dict(team_context.get('role_stability_context'))
    band = stability.get('stability_band')
    if band not in STABLE_CORE_BANDS:
        return None

    return _observation(
        team_context,
        TYPE_STABLE_CORE,
        SEVERITY_MEDIUM,
        source_layers=['role_stability_context'],
        headline_inputs={
            'stability_band': band,
            'core_stability_pct': stability.get('core_stability_pct'),
            'core_retention_count': stability.get('core_retention_count'),
        },
        baseline_inputs={
            'previous_operational_core': _list(stability.get('previous_operational_core')),
            'previous_core_size': stability.get('previous_core_size'),
        },
        cause_inputs={
            'current_operational_core': _list(stability.get('current_operational_core')),
            'core_change_count': stability.get('core_change_count'),
        },
        constraint_inputs={
            'current_core_size': stability.get('current_core_size'),
            'limitations': _context_limitations(team_context, stability),
        },
    )


def _core_transition(team_context: dict[str, Any]) -> dict[str, Any] | None:
    stability = _dict(team_context.get('role_stability_context'))
    band = stability.get('stability_band')
    if band not in CORE_TRANSITION_BANDS:
        return None

    severity = SEVERITY_HIGH if band == 'rebuilding' else SEVERITY_MEDIUM
    return _observation(
        team_context,
        TYPE_CORE_TRANSITION,
        severity,
        source_layers=['role_stability_context'],
        headline_inputs={
            'stability_band': band,
            'core_change_count': stability.get('core_change_count'),
            'core_stability_pct': stability.get('core_stability_pct'),
        },
        baseline_inputs={
            'previous_operational_core': _list(stability.get('previous_operational_core')),
            'previous_core_size': stability.get('previous_core_size'),
        },
        cause_inputs={
            'current_operational_core': _list(stability.get('current_operational_core')),
            'new_core_members': _list(stability.get('new_core_members')),
            'departed_core_members': _list(stability.get('departed_core_members')),
        },
        constraint_inputs={
            'current_core_size': stability.get('current_core_size'),
            'core_retention_count': stability.get('core_retention_count'),
            'limitations': _context_limitations(team_context, stability),
        },
    )


def _depth_pressure(team_context: dict[str, Any]) -> dict[str, Any] | None:
    injury = _dict(team_context.get('injury_context'))
    band = injury.get('depth_pressure_band')
    if band not in DEPTH_PRESSURE_BANDS:
        return None

    severity = SEVERITY_HIGH if band == 'heavy' else SEVERITY_MEDIUM
    return _observation(
        team_context,
        TYPE_DEPTH_PRESSURE,
        severity,
        source_layers=['injury_context'],
        headline_inputs={
            'depth_pressure_band': band,
            'inactive_bullpen_arms_count': injury.get('inactive_bullpen_arms_count'),
            'inactive_bullpen_share': injury.get('inactive_bullpen_share'),
        },
        baseline_inputs={
            'active_bullpen_arms_count': injury.get('active_bullpen_arms_count'),
            'injury_context_confidence': injury.get('injury_context_confidence'),
        },
        cause_inputs={
            'il_bullpen_arms_count': injury.get('il_bullpen_arms_count'),
            'non_il_inactive_bullpen_arms_count': injury.get('non_il_inactive_bullpen_arms_count'),
            'inactive_bullpen_arms': _list(injury.get('inactive_bullpen_arms')),
        },
        constraint_inputs={
            'role_uncertain_inactive_count': injury.get('role_uncertain_inactive_count'),
            'unknown_roster_status_count': injury.get('unknown_roster_status_count'),
            'limitations': _context_limitations(team_context, injury),
        },
    )


OBSERVATION_BUILDERS = (
    _rotation_pressure,
    _concentration_pressure,
    _optionality_strength,
    _stable_core,
    _core_transition,
    _depth_pressure,
)


def build_team_observations(team_context: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Build structured observations for one team context payload."""
    if not isinstance(team_context, dict):
        return []
    observations = [
        observation
        for builder in OBSERVATION_BUILDERS
        for observation in [builder(team_context)]
        if observation is not None
    ]
    return sorted(observations, key=_selection_key)


def _selection_key(observation: dict[str, Any]):
    return (
        -SEVERITY_ORDER.get(observation.get('severity'), 0),
        -TYPE_PRIORITY.get(observation.get('type'), 0),
        str(observation.get('team') or '').lower(),
        str(observation.get('type') or ''),
    )


def select_strongest_observation(observations: list[dict[str, Any]] | None):
    """Return the strongest internal observation for one team, if any."""
    rows = [row for row in observations or [] if isinstance(row, dict)]
    if not rows:
        return None
    return sorted(rows, key=_selection_key)[0]


def build_team_story_observation_payload(
    team_context: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build the internal V1 observation payload for one team."""
    team_context = team_context if isinstance(team_context, dict) else {}
    identity = _team_identity(team_context)
    observations = build_team_observations(team_context)
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': SOURCE,
        'team_id': identity['team_id'],
        'team_name': identity['team_name'],
        'team_abbreviation': identity['team_abbreviation'],
        'reference_date': team_context.get('reference_date'),
        'data_through_date': team_context.get('data_through_date'),
        'observation_count': len(observations),
        'observations': observations,
        'strongest_observation': select_strongest_observation(observations),
        'limitations': _list(team_context.get('limitations')),
    }


def select_top_observations(
    team_payloads: list[dict[str, Any]] | None,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return the strongest internal observations across supplied teams."""
    observations = [
        observation
        for payload in team_payloads or []
        for observation in _list(_dict(payload).get('observations'))
        if isinstance(observation, dict)
    ]
    selected = sorted(observations, key=_selection_key)
    if limit is None:
        return selected
    return selected[:max(0, int(limit))]


def story_observation_team_ids(limit: int | None = None) -> list[int]:
    """Return team ids available for internal story observation evaluation."""
    query = (
        db.session.query(Pitcher.team_id)
        .filter(Pitcher.team_id.isnot(None))
        .distinct()
        .order_by(Pitcher.team_id)
    )
    if limit is not None:
        query = query.limit(max(0, int(limit)))
    return [row[0] for row in query.all() if row[0] is not None]


def build_story_observation_engine_v1(
    *,
    team_contexts: list[dict[str, Any]] | None = None,
    team_ids: list[int] | None = None,
    reference_date=None,
    limit: int | None = None,
) -> dict[str, Any]:
    """Build internal structured observation intelligence for MLB teams."""
    if team_contexts is None:
        ids = team_ids if team_ids is not None else story_observation_team_ids()
        contexts = [
            build_team_bullpen_context(team_id, reference_date=reference_date)
            for team_id in ids
        ]
    else:
        contexts = list(team_contexts)

    teams = [
        build_team_story_observation_payload(context)
        for context in contexts
    ]
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': SOURCE,
        'reference_date': (
            reference_date.isoformat()
            if hasattr(reference_date, 'isoformat')
            else reference_date
        ),
        'team_count': len(teams),
        'teams': teams,
        'top_observations': select_top_observations(teams, limit=limit),
        'limitations': [
            'Story Observation Engine V1 returns structured inputs only.',
            'Story Observation Engine V1 does not generate prose, predictions, public UI, or scoring changes.',
        ],
    }


__all__ = [
    'CAPABILITY',
    'TYPE_CONCENTRATION_PRESSURE',
    'TYPE_CORE_TRANSITION',
    'TYPE_DEPTH_PRESSURE',
    'TYPE_OPTIONALITY_STRENGTH',
    'TYPE_ROTATION_PRESSURE',
    'TYPE_STABLE_CORE',
    'VERSION',
    'build_story_observation_engine_v1',
    'build_team_observations',
    'build_team_story_observation_payload',
    'select_strongest_observation',
    'select_top_observations',
    'story_observation_team_ids',
]
