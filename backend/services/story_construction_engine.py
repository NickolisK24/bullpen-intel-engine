"""Story Construction Engine V1.

Internal structured frame builder only. This module consumes Story Observation
Engine V1 outputs and existing bullpen context payloads, then returns facts for
future story writers. It does not generate prose, expose public UI, predict
usage, infer roles, call external language systems, or alter scoring.
"""

from __future__ import annotations

from typing import Any

from services.bullpen_context import build_team_bullpen_context
from services.story_observation_engine import (
    TYPE_BRIDGE_INSTABILITY,
    TYPE_CONCENTRATION_PRESSURE,
    TYPE_CORE_TRANSITION,
    TYPE_DEPTH_PRESSURE,
    TYPE_OPTIONALITY_STRENGTH,
    TYPE_ROTATION_PRESSURE,
    TYPE_STABLE_CORE,
    TYPE_TRUST_LANE_PRESSURE,
    build_team_story_observation_payload,
    select_strongest_observation,
)


CAPABILITY = 'story_construction_engine_v1'
VERSION = '2026-06-21.v1'
SOURCE = 'backend'

CONFIDENCE_HIGH = 'high'
CONFIDENCE_MEDIUM = 'medium'
CONFIDENCE_LOW = 'low'

CONTEXT_LAYER_KEYS = (
    'rotation_context',
    'bullpen_concentration_context',
    'bullpen_optionality_context',
    'role_stability_context',
    'injury_context',
)


def _dict(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _present(value):
    if value is None:
        return False
    if value == '':
        return False
    if isinstance(value, (list, dict)) and not value:
        return False
    return True


def _names(rows):
    names = []
    for row in _list(rows):
        if isinstance(row, str):
            if row:
                names.append(row)
            continue
        name = _dict(row).get('name')
        if name:
            names.append(name)
    return names


def _count(rows):
    return len(_list(rows))


def _team_identity(team_context, observation):
    context = _dict(team_context)
    team = _dict(context.get('team'))
    obs = _dict(observation)
    return {
        'team_id': context.get('team_id') or obs.get('team_id') or team.get('team_id'),
        'team_name': team.get('team_name') or context.get('team_name') or obs.get('team'),
        'team_abbreviation': (
            team.get('team_abbreviation')
            or context.get('team_abbreviation')
            or obs.get('team_abbreviation')
        ),
    }


def _source_context(team_context):
    context = _dict(team_context)
    return {
        key: _dict(context.get(key))
        for key in CONTEXT_LAYER_KEYS
    }


def _context_dates_present(team_context):
    context = _dict(team_context)
    return _present(context.get('reference_date')) and _present(context.get('data_through_date'))


def _append_missing(limitations, code):
    if code and code not in limitations:
        limitations.append(code)


def _confidence(required_values, supporting_values, team_context, limitations):
    missing_required = [code for code, value in required_values if not _present(value)]
    for code in missing_required:
        _append_missing(limitations, code)
    if missing_required:
        return CONFIDENCE_LOW

    missing_support = [code for code, value in supporting_values if not _present(value)]
    for code in missing_support:
        _append_missing(limitations, code)
    if not _context_dates_present(team_context):
        _append_missing(limitations, 'missing_context_date')
    if missing_support or 'missing_context_date' in limitations:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_HIGH


def _base_frame():
    return {
        'headline_facts': {},
        'observation_facts': {},
        'baseline_facts': {},
        'cause_facts': {},
        'interpretation_facts': {},
        'constraint_facts': {},
    }


def _rotation_pressure_frame(team_context, observation):
    identity = _team_identity(team_context, observation)
    rotation = _dict(_dict(team_context).get('rotation_context'))
    concentration = _dict(_dict(team_context).get('bullpen_concentration_context'))
    optionality = _dict(_dict(team_context).get('bullpen_optionality_context'))
    frame = _base_frame()
    frame['headline_facts'] = {
        'team_name': identity['team_name'],
        'rotation_avg_ip_7d': rotation.get('rotation_avg_ip_7d'),
        'rotation_avg_ip_14d': rotation.get('rotation_avg_ip_14d'),
        'rotation_ip_trend': rotation.get('rotation_ip_trend'),
    }
    frame['observation_facts'] = {
        'type': TYPE_ROTATION_PRESSURE,
        'rotation_avg_ip_7d': rotation.get('rotation_avg_ip_7d'),
        'rotation_avg_ip_14d': rotation.get('rotation_avg_ip_14d'),
        'rotation_ip_trend': rotation.get('rotation_ip_trend'),
        'early_bullpen_entry_rate': rotation.get('early_bullpen_entry_rate'),
    }
    frame['baseline_facts'] = {
        'rotation_avg_ip_14d': rotation.get('rotation_avg_ip_14d'),
        'rotation_games_analyzed_14d': rotation.get('rotation_games_analyzed_14d'),
    }
    frame['cause_facts'] = {
        'bullpen_coverage_ip_7d': rotation.get('bullpen_coverage_ip_7d'),
        'early_bullpen_entry_rate': rotation.get('early_bullpen_entry_rate'),
        'early_bullpen_entry_games_14d': (
            rotation.get('rotation_early_bullpen_entry_games_14d')
            or rotation.get('early_bullpen_entry_games_14d')
        ),
    }
    frame['interpretation_facts'] = {
        'bullpen_coverage_ip_7d': rotation.get('bullpen_coverage_ip_7d'),
        'concentration_band': concentration.get('concentration_band'),
        'optionality_band': optionality.get('optionality_band'),
    }
    frame['constraint_facts'] = {
        'rotation_games_analyzed_7d': rotation.get('rotation_games_analyzed_7d'),
        'rotation_games_analyzed_14d': rotation.get('rotation_games_analyzed_14d'),
        'bullpen_coverage_ip_7d': rotation.get('bullpen_coverage_ip_7d'),
    }
    required = [
        ('missing_rotation_avg_ip_7d', frame['observation_facts']['rotation_avg_ip_7d']),
        ('missing_rotation_avg_ip_14d', frame['observation_facts']['rotation_avg_ip_14d']),
        ('missing_rotation_ip_trend', frame['observation_facts']['rotation_ip_trend']),
    ]
    supporting = [
        ('missing_early_bullpen_entry_rate', frame['observation_facts']['early_bullpen_entry_rate']),
        ('missing_bullpen_coverage_ip_7d', frame['cause_facts']['bullpen_coverage_ip_7d']),
    ]
    return frame, required, supporting


def _concentration_pressure_frame(team_context, observation):
    identity = _team_identity(team_context, observation)
    concentration = _dict(_dict(team_context).get('bullpen_concentration_context'))
    rotation = _dict(_dict(team_context).get('rotation_context'))
    optionality = _dict(_dict(team_context).get('bullpen_optionality_context'))
    stability = _dict(_dict(team_context).get('role_stability_context'))
    top_three = _list(concentration.get('top_three_relievers_10d'))
    frame = _base_frame()
    frame['headline_facts'] = {
        'team_name': identity['team_name'],
        'top_three_relievers': _names(top_three),
        'top_three_workload_share_10d': concentration.get('top_three_workload_share_10d'),
    }
    frame['observation_facts'] = {
        'type': TYPE_CONCENTRATION_PRESSURE,
        'concentration_band': concentration.get('concentration_band'),
        'top_three_workload_share_10d': concentration.get('top_three_workload_share_10d'),
        'bullpen_workload_total_10d': concentration.get('bullpen_workload_total_10d'),
    }
    frame['baseline_facts'] = {
        'league_top_three_workload_share_10d': concentration.get('league_top_three_workload_share_10d'),
        'top_three_share_delta_vs_league': concentration.get('top_three_share_delta_vs_league'),
        'league_team_count_10d': concentration.get('league_team_count_10d'),
        'baseline_read': concentration.get('baseline_read'),
    }
    frame['cause_facts'] = {
        'rotation_avg_ip_7d': rotation.get('rotation_avg_ip_7d'),
        'rotation_avg_ip_14d': rotation.get('rotation_avg_ip_14d'),
        'rotation_ip_trend': rotation.get('rotation_ip_trend'),
        'early_bullpen_entry_rate': rotation.get('early_bullpen_entry_rate'),
    }
    frame['interpretation_facts'] = {
        'available_arms_count': optionality.get('available_arms_count'),
        'practical_close_game_paths_count': optionality.get('practical_close_game_paths_count'),
        'optionality_band': optionality.get('optionality_band'),
        'concentration_band': concentration.get('concentration_band'),
    }
    frame['constraint_facts'] = {
        'current_operational_core': _list(stability.get('current_operational_core')),
        'stability_band': stability.get('stability_band'),
        'clean_workload_options_count': _count(optionality.get('clean_workload_options')),
        'secondary_options_count': _count(optionality.get('secondary_options')),
    }
    required = [
        ('missing_top_three_relievers', frame['headline_facts']['top_three_relievers']),
        ('missing_top_three_workload_share_10d', frame['observation_facts']['top_three_workload_share_10d']),
        ('missing_concentration_band', frame['observation_facts']['concentration_band']),
    ]
    supporting = [
        ('missing_league_baseline', frame['baseline_facts']['league_top_three_workload_share_10d']),
        ('missing_top_three_share_delta_vs_league', frame['baseline_facts']['top_three_share_delta_vs_league']),
        ('missing_rotation_context', frame['cause_facts']['rotation_avg_ip_7d']),
        ('missing_operational_core', frame['constraint_facts']['current_operational_core']),
    ]
    return frame, required, supporting


def _optionality_strength_frame(team_context, observation):
    identity = _team_identity(team_context, observation)
    optionality = _dict(_dict(team_context).get('bullpen_optionality_context'))
    concentration = _dict(_dict(team_context).get('bullpen_concentration_context'))
    clean = _list(optionality.get('clean_workload_options'))
    secondary = _list(optionality.get('secondary_options'))
    frame = _base_frame()
    frame['headline_facts'] = {
        'team_name': identity['team_name'],
        'practical_close_game_paths_count': optionality.get('practical_close_game_paths_count'),
        'optionality_band': optionality.get('optionality_band'),
    }
    frame['observation_facts'] = {
        'type': TYPE_OPTIONALITY_STRENGTH,
        'optionality_band': optionality.get('optionality_band'),
        'available_arms_count': optionality.get('available_arms_count'),
        'clean_workload_options_count': len(clean),
        'secondary_options_count': len(secondary),
        'practical_close_game_paths_count': optionality.get('practical_close_game_paths_count'),
    }
    frame['baseline_facts'] = {
        'available_arms_count': optionality.get('available_arms_count'),
        'monitor_arms_count': optionality.get('monitor_arms_count'),
        'restricted_arms_count': optionality.get('restricted_arms_count'),
        'baseline_read': optionality.get('baseline_read'),
    }
    frame['cause_facts'] = {
        'clean_workload_options': clean,
        'secondary_options': secondary,
    }
    frame['interpretation_facts'] = {
        'optionality_band': optionality.get('optionality_band'),
        'concentration_band': concentration.get('concentration_band'),
        'top_three_workload_share_10d': concentration.get('top_three_workload_share_10d'),
    }
    frame['constraint_facts'] = {
        'limited_arms_count': optionality.get('limited_arms_count'),
        'avoid_arms_count': optionality.get('avoid_arms_count'),
        'unavailable_arms_count': optionality.get('unavailable_arms_count'),
    }
    required = [
        ('missing_optionality_band', frame['observation_facts']['optionality_band']),
        ('missing_practical_close_game_paths_count', frame['observation_facts']['practical_close_game_paths_count']),
    ]
    supporting = [
        ('missing_available_arms_count', frame['observation_facts']['available_arms_count']),
        ('missing_clean_workload_options', frame['cause_facts']['clean_workload_options']),
    ]
    return frame, required, supporting


def _stable_core_frame(team_context, observation):
    identity = _team_identity(team_context, observation)
    stability = _dict(_dict(team_context).get('role_stability_context'))
    concentration = _dict(_dict(team_context).get('bullpen_concentration_context'))
    frame = _base_frame()
    frame['headline_facts'] = {
        'team_name': identity['team_name'],
        'current_operational_core': _list(stability.get('current_operational_core')),
        'core_stability_pct': stability.get('core_stability_pct'),
    }
    frame['observation_facts'] = {
        'type': TYPE_STABLE_CORE,
        'stability_band': stability.get('stability_band'),
        'core_retention_count': stability.get('core_retention_count'),
        'core_stability_pct': stability.get('core_stability_pct'),
        'core_change_count': stability.get('core_change_count'),
    }
    frame['baseline_facts'] = {
        'previous_operational_core': _list(stability.get('previous_operational_core')),
        'previous_core_size': stability.get('previous_core_size'),
    }
    frame['cause_facts'] = {
        'current_operational_core': _list(stability.get('current_operational_core')),
        'previous_operational_core': _list(stability.get('previous_operational_core')),
        'core_retention_count': stability.get('core_retention_count'),
    }
    frame['interpretation_facts'] = {
        'stability_band': stability.get('stability_band'),
        'concentration_band': concentration.get('concentration_band'),
        'top_three_workload_share_10d': concentration.get('top_three_workload_share_10d'),
    }
    frame['constraint_facts'] = {
        'current_operational_core': _list(stability.get('current_operational_core')),
        'current_core_size': stability.get('current_core_size'),
        'stability_band': stability.get('stability_band'),
    }
    required = [
        ('missing_current_operational_core', frame['headline_facts']['current_operational_core']),
        ('missing_previous_operational_core', frame['baseline_facts']['previous_operational_core']),
        ('missing_core_stability_pct', frame['observation_facts']['core_stability_pct']),
    ]
    supporting = [
        ('missing_core_retention_count', frame['observation_facts']['core_retention_count']),
        ('missing_concentration_context', frame['interpretation_facts']['concentration_band']),
    ]
    return frame, required, supporting


def _core_transition_frame(team_context, observation):
    identity = _team_identity(team_context, observation)
    stability = _dict(_dict(team_context).get('role_stability_context'))
    frame = _base_frame()
    frame['headline_facts'] = {
        'team_name': identity['team_name'],
        'current_operational_core': _list(stability.get('current_operational_core')),
        'new_core_members': _list(stability.get('new_core_members')),
        'core_change_count': stability.get('core_change_count'),
    }
    frame['observation_facts'] = {
        'type': TYPE_CORE_TRANSITION,
        'stability_band': stability.get('stability_band'),
        'core_change_count': stability.get('core_change_count'),
        'core_stability_pct': stability.get('core_stability_pct'),
    }
    frame['baseline_facts'] = {
        'previous_operational_core': _list(stability.get('previous_operational_core')),
        'previous_core_size': stability.get('previous_core_size'),
    }
    frame['cause_facts'] = {
        'current_operational_core': _list(stability.get('current_operational_core')),
        'new_core_members': _list(stability.get('new_core_members')),
        'departed_core_members': _list(stability.get('departed_core_members')),
    }
    frame['interpretation_facts'] = {
        'stability_band': stability.get('stability_band'),
        'core_stability_pct': stability.get('core_stability_pct'),
        'core_retention_count': stability.get('core_retention_count'),
    }
    frame['constraint_facts'] = {
        'current_core_size': stability.get('current_core_size'),
        'previous_core_size': stability.get('previous_core_size'),
        'core_retention_count': stability.get('core_retention_count'),
    }
    required = [
        ('missing_current_operational_core', frame['cause_facts']['current_operational_core']),
        ('missing_previous_operational_core', frame['baseline_facts']['previous_operational_core']),
        ('missing_core_change_count', frame['observation_facts']['core_change_count']),
    ]
    supporting = [
        ('missing_new_core_members', frame['cause_facts']['new_core_members']),
        ('missing_departed_core_members', frame['cause_facts']['departed_core_members']),
        ('missing_core_stability_pct', frame['observation_facts']['core_stability_pct']),
    ]
    return frame, required, supporting


def _depth_pressure_frame(team_context, observation):
    identity = _team_identity(team_context, observation)
    injury = _dict(_dict(team_context).get('injury_context'))
    optionality = _dict(_dict(team_context).get('bullpen_optionality_context'))
    concentration = _dict(_dict(team_context).get('bullpen_concentration_context'))
    frame = _base_frame()
    frame['headline_facts'] = {
        'team_name': identity['team_name'],
        'inactive_bullpen_arms_count': injury.get('inactive_bullpen_arms_count'),
        'depth_pressure_band': injury.get('depth_pressure_band'),
    }
    frame['observation_facts'] = {
        'type': TYPE_DEPTH_PRESSURE,
        'inactive_bullpen_arms_count': injury.get('inactive_bullpen_arms_count'),
        'inactive_bullpen_share': injury.get('inactive_bullpen_share'),
        'depth_pressure_band': injury.get('depth_pressure_band'),
    }
    frame['baseline_facts'] = {
        'active_bullpen_arms_count': injury.get('active_bullpen_arms_count'),
        'injury_context_confidence': injury.get('injury_context_confidence'),
    }
    frame['cause_facts'] = {
        'inactive_bullpen_arms_count': injury.get('inactive_bullpen_arms_count'),
        'il_bullpen_arms_count': injury.get('il_bullpen_arms_count'),
        'non_il_inactive_bullpen_arms_count': injury.get('non_il_inactive_bullpen_arms_count'),
        'depth_pressure_band': injury.get('depth_pressure_band'),
        'inactive_bullpen_arms': _list(injury.get('inactive_bullpen_arms')),
    }
    frame['interpretation_facts'] = {
        'available_arms_count': optionality.get('available_arms_count'),
        'practical_close_game_paths_count': optionality.get('practical_close_game_paths_count'),
        'optionality_band': optionality.get('optionality_band'),
        'concentration_band': concentration.get('concentration_band'),
    }
    frame['constraint_facts'] = {
        'active_bullpen_arms_count': injury.get('active_bullpen_arms_count'),
        'role_uncertain_inactive_count': injury.get('role_uncertain_inactive_count'),
        'unknown_roster_status_count': injury.get('unknown_roster_status_count'),
        'injury_context_confidence': injury.get('injury_context_confidence'),
    }
    required = [
        ('missing_inactive_bullpen_arms_count', frame['observation_facts']['inactive_bullpen_arms_count']),
        ('missing_depth_pressure_band', frame['observation_facts']['depth_pressure_band']),
    ]
    supporting = [
        ('missing_active_bullpen_arms_count', frame['baseline_facts']['active_bullpen_arms_count']),
        ('missing_il_bullpen_arms_count', frame['cause_facts']['il_bullpen_arms_count']),
        ('missing_optionality_context', frame['interpretation_facts']['optionality_band']),
    ]
    return frame, required, supporting


def _trust_lane_pressure_frame(team_context, observation):
    identity = _team_identity(team_context, observation)
    optionality = _dict(_dict(team_context).get('bullpen_optionality_context'))
    concentration = _dict(_dict(team_context).get('bullpen_concentration_context'))
    stability = _dict(_dict(team_context).get('role_stability_context'))
    clean = _list(optionality.get('clean_workload_options'))
    secondary = _list(optionality.get('secondary_options'))
    top_three = _list(concentration.get('top_three_relievers_10d'))
    frame = _base_frame()
    frame['headline_facts'] = {
        'team_name': identity['team_name'],
        'available_arms_count': optionality.get('available_arms_count'),
        'clean_workload_options_count': len(clean),
    }
    frame['observation_facts'] = {
        'type': TYPE_TRUST_LANE_PRESSURE,
        'available_arms_count': optionality.get('available_arms_count'),
        'clean_workload_options_count': len(clean),
        'secondary_options_count': len(secondary),
        'optionality_band': optionality.get('optionality_band'),
        'practical_close_game_paths_count': optionality.get('practical_close_game_paths_count'),
        'concentration_band': concentration.get('concentration_band'),
    }
    frame['baseline_facts'] = {
        'available_arms_count': optionality.get('available_arms_count'),
        'monitor_arms_count': optionality.get('monitor_arms_count'),
        'restricted_arms_count': optionality.get('restricted_arms_count'),
        'baseline_read': optionality.get('baseline_read'),
    }
    frame['cause_facts'] = {
        'clean_workload_options': clean,
        'secondary_options': secondary,
        'top_three_relievers': _names(top_three),
        'top_three_workload_share_10d': concentration.get('top_three_workload_share_10d'),
    }
    frame['interpretation_facts'] = {
        'optionality_band': optionality.get('optionality_band'),
        'concentration_band': concentration.get('concentration_band'),
        'top_three_workload_share_10d': concentration.get('top_three_workload_share_10d'),
        'practical_close_game_paths_count': optionality.get('practical_close_game_paths_count'),
    }
    frame['constraint_facts'] = {
        'clean_workload_options': clean,
        'clean_workload_options_count': len(clean),
        'secondary_options_count': len(secondary),
        'current_operational_core': _list(stability.get('current_operational_core')),
    }
    required = [
        ('missing_available_arms_count', frame['observation_facts']['available_arms_count']),
        ('missing_clean_workload_options_count', frame['observation_facts']['clean_workload_options_count']),
        ('missing_secondary_options_count', frame['observation_facts']['secondary_options_count']),
    ]
    supporting = [
        ('missing_optionality_band', frame['observation_facts']['optionality_band']),
        (
            'missing_named_trust_lane_arms',
            frame['cause_facts']['clean_workload_options'] or frame['cause_facts']['top_three_relievers'],
        ),
    ]
    return frame, required, supporting


def _bridge_instability_frame(team_context, observation):
    identity = _team_identity(team_context, observation)
    rotation = _dict(_dict(team_context).get('rotation_context'))
    stability = _dict(_dict(team_context).get('role_stability_context'))
    optionality = _dict(_dict(team_context).get('bullpen_optionality_context'))
    concentration = _dict(_dict(team_context).get('bullpen_concentration_context'))
    monitor = optionality.get('monitor_arms_count') or 0
    limited = optionality.get('limited_arms_count') or 0
    volatile_middle = monitor + limited
    clean = _list(optionality.get('clean_workload_options'))
    core = _list(stability.get('current_operational_core'))
    top_three = _list(concentration.get('top_three_relievers_10d'))
    frame = _base_frame()
    frame['headline_facts'] = {
        'team_name': identity['team_name'],
        'current_operational_core': core,
        'volatile_middle_count': volatile_middle,
    }
    frame['observation_facts'] = {
        'type': TYPE_BRIDGE_INSTABILITY,
        'stability_band': stability.get('stability_band'),
        'early_bullpen_entry_rate': rotation.get('early_bullpen_entry_rate'),
        'bullpen_coverage_ip_7d': rotation.get('bullpen_coverage_ip_7d'),
        'volatile_middle_count': volatile_middle,
        'clean_workload_options_count': len(clean),
    }
    frame['baseline_facts'] = {
        'current_operational_core': core,
        'core_stability_pct': stability.get('core_stability_pct'),
        'available_arms_count': optionality.get('available_arms_count'),
    }
    frame['cause_facts'] = {
        'early_bullpen_entry_rate': rotation.get('early_bullpen_entry_rate'),
        'bullpen_coverage_ip_7d': rotation.get('bullpen_coverage_ip_7d'),
        'monitor_arms_count': optionality.get('monitor_arms_count'),
        'limited_arms_count': optionality.get('limited_arms_count'),
    }
    frame['interpretation_facts'] = {
        'stability_band': stability.get('stability_band'),
        'volatile_middle_count': volatile_middle,
        'clean_workload_options_count': len(clean),
        'early_bullpen_entry_rate': rotation.get('early_bullpen_entry_rate'),
    }
    frame['constraint_facts'] = {
        'current_operational_core': core,
        'top_three_relievers': _names(top_three),
        'volatile_middle_count': volatile_middle,
        'clean_workload_options_count': len(clean),
    }
    required = [
        ('missing_stability_band', frame['observation_facts']['stability_band']),
        (
            'missing_handoff_demand',
            frame['observation_facts']['early_bullpen_entry_rate']
            or frame['observation_facts']['bullpen_coverage_ip_7d'],
        ),
        ('missing_volatile_middle_count', frame['observation_facts']['volatile_middle_count']),
    ]
    supporting = [
        ('missing_operational_core', frame['headline_facts']['current_operational_core']),
        ('missing_early_bullpen_entry_rate', frame['cause_facts']['early_bullpen_entry_rate']),
    ]
    return frame, required, supporting


FRAME_BUILDERS = {
    TYPE_ROTATION_PRESSURE: _rotation_pressure_frame,
    TYPE_CONCENTRATION_PRESSURE: _concentration_pressure_frame,
    TYPE_OPTIONALITY_STRENGTH: _optionality_strength_frame,
    TYPE_TRUST_LANE_PRESSURE: _trust_lane_pressure_frame,
    TYPE_BRIDGE_INSTABILITY: _bridge_instability_frame,
    TYPE_STABLE_CORE: _stable_core_frame,
    TYPE_CORE_TRANSITION: _core_transition_frame,
    TYPE_DEPTH_PRESSURE: _depth_pressure_frame,
}


def construct_story_frame(observation, team_context):
    """Construct one structured story frame from one observation."""
    observation = _dict(observation)
    team_context = _dict(team_context)
    identity = _team_identity(team_context, observation)
    observation_type = observation.get('type')
    builder = FRAME_BUILDERS.get(observation_type)
    limitations = []
    if builder is None:
        _append_missing(limitations, 'unsupported_observation_type')
        frame = _base_frame()
        confidence = CONFIDENCE_LOW
    else:
        frame, required, supporting = builder(team_context, observation)
        confidence = _confidence(required, supporting, team_context, limitations)

    injury = _dict(team_context.get('injury_context'))
    if (
        observation_type == TYPE_DEPTH_PRESSURE
        and injury.get('injury_context_confidence') == CONFIDENCE_LOW
    ):
        _append_missing(limitations, 'low_injury_context_confidence')
        if confidence == CONFIDENCE_HIGH:
            confidence = CONFIDENCE_MEDIUM

    return {
        'team_id': identity['team_id'],
        'team_name': identity['team_name'],
        'team_abbreviation': identity['team_abbreviation'],
        'observation_type': observation_type,
        'severity': observation.get('severity'),
        'story_frame': frame,
        'source_context': _source_context(team_context),
        'construction_confidence': confidence,
        'limitations': limitations,
    }


def construct_team_story_frames(team_context, observation_payload=None):
    """Construct all structured story frames for one team context."""
    team_context = _dict(team_context)
    observation_payload = (
        _dict(observation_payload)
        if isinstance(observation_payload, dict)
        else build_team_story_observation_payload(team_context)
    )
    observations = _list(observation_payload.get('observations'))
    frames = [
        construct_story_frame(observation, team_context)
        for observation in observations
    ]
    strongest = select_strongest_observation(observations)
    strongest_type = strongest.get('type') if isinstance(strongest, dict) else None
    strongest_frame = next(
        (frame for frame in frames if frame.get('observation_type') == strongest_type),
        None,
    )
    identity = _team_identity(team_context, observation_payload)
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': SOURCE,
        'team_id': identity['team_id'],
        'team_name': identity['team_name'],
        'team_abbreviation': identity['team_abbreviation'],
        'reference_date': team_context.get('reference_date'),
        'data_through_date': team_context.get('data_through_date'),
        'frame_count': len(frames),
        'story_frames': frames,
        'strongest_story_frame': strongest_frame,
        'limitations': _list(team_context.get('limitations')),
    }


def build_story_construction_engine_v1(
    *,
    team_contexts=None,
    team_ids=None,
    reference_date=None,
):
    """Build internal structured story frames for supplied teams."""
    if team_contexts is None:
        team_contexts = [
            build_team_bullpen_context(team_id, reference_date=reference_date)
            for team_id in (team_ids or [])
        ]
    teams = [
        construct_team_story_frames(team_context)
        for team_context in _list(team_contexts)
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
        'limitations': [
            'structured_story_frames_only',
            'no_prose_generation',
            'no_predictions_or_scoring_changes',
        ],
    }


__all__ = [
    'CAPABILITY',
    'CONFIDENCE_HIGH',
    'CONFIDENCE_LOW',
    'CONFIDENCE_MEDIUM',
    'VERSION',
    'build_story_construction_engine_v1',
    'construct_story_frame',
    'construct_team_story_frames',
]
