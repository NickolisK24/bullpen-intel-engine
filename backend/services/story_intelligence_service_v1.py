"""Story Intelligence Service V1.

Backend coordinator for the deterministic story intelligence pipeline. It
connects bullpen context, structured observations, construction frames, and the
Story Writer V1 output without creating public UI, routes, forecasts, or new
metrics.
"""

from __future__ import annotations

from copy import deepcopy

from services.bullpen_context import build_team_bullpen_context
from services.story_eligibility_context import apply_swing_bulk_story_context
from services.story_construction_engine import (
    CONFIDENCE_LOW,
    construct_team_story_frames,
)
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
)
from services.story_four_beat_interpreter_v1 import (
    BEAT_AVAILABILITY_DEPTH,
    BEAT_BRIDGE,
    BEAT_COVERAGE_PRESSURE,
    BEAT_DEPTH_CONSTRAINT,
    BEAT_ROUTE_CHANGE,
    BEAT_SUSTAINABILITY_QUESTION,
    BEAT_TRUST_LANE,
    interpret_story_candidate,
)
from services.story_reasoning_engine_v1 import build_editorial_intent
from services.story_writer_v1 import validate_written_observation, write_story_frame


CAPABILITY = 'story_intelligence_service_v1'
VERSION = '2026-06-21.v1'
SOURCE = 'backend'

SERVICE_OBSERVATION_ORDER = (
    TYPE_ROTATION_PRESSURE,
    TYPE_CONCENTRATION_PRESSURE,
    TYPE_BRIDGE_INSTABILITY,
    TYPE_TRUST_LANE_PRESSURE,
    TYPE_CORE_TRANSITION,
    TYPE_OPTIONALITY_STRENGTH,
    TYPE_STABLE_CORE,
    TYPE_DEPTH_PRESSURE,
)

SERVICE_SEVERITY_ORDER = {
    'high': 3,
    'medium': 2,
    'low': 1,
}

SERVICE_OBSERVATION_PRIORITY = {
    observation_type: index
    for index, observation_type in enumerate(SERVICE_OBSERVATION_ORDER)
}

# Positive depth/rest sits last so that on equal strength a pressure or change
# story is preferred. Bridge-instability and trust-lane sit below the acute
# pressure beats but above positive depth (bridge above trust-lane), so on equal
# strength an acute pressure story still wins while a strong bridge read outranks
# a trust-lane read, which outranks a generic positive-depth read. A stronger
# story of any kind still wins outright on strength.
PUBLIC_BEAT_TIEBREAK_PRIORITY = {
    BEAT_COVERAGE_PRESSURE: 0,
    BEAT_SUSTAINABILITY_QUESTION: 1,
    BEAT_ROUTE_CHANGE: 2,
    BEAT_DEPTH_CONSTRAINT: 3,
    BEAT_BRIDGE: 4,
    BEAT_TRUST_LANE: 5,
    BEAT_AVAILABILITY_DEPTH: 6,
}

SUPPORTING_CONTEXT_KEYS = (
    'rotation_context',
    'bullpen_concentration_context',
    'bullpen_optionality_context',
    'role_stability_context',
    'injury_context',
)

STATE_STORY_AVAILABLE = 'story_available'
STATE_NEUTRAL = 'neutral'

NEUTRAL_NO_OBSERVATIONS = 'no_story_observations'
NEUTRAL_NO_VALID_FRAME = 'no_valid_story_frame'


def _dict(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def _identity(team_context, team_id=None):
    context = _dict(team_context)
    team = _dict(context.get('team'))
    return {
        'team_id': context.get('team_id') or team.get('team_id') or team_id,
        'team_name': team.get('team_name') or context.get('team_name'),
        'team_abbreviation': team.get('team_abbreviation') or context.get('team_abbreviation'),
    }


def _supporting_context(team_context, frame=None):
    source_context = _dict(_dict(frame).get('source_context'))
    if source_context:
        return deepcopy({
            key: _dict(source_context.get(key))
            for key in SUPPORTING_CONTEXT_KEYS
        })
    context = _dict(team_context)
    return deepcopy({
        key: _dict(context.get(key))
        for key in SUPPORTING_CONTEXT_KEYS
    })


def _freshness(team_context, as_of_date=None):
    context = _dict(team_context)
    data_through = context.get('data_through_date')
    return {
        'as_of_date': _iso(as_of_date) or context.get('reference_date'),
        'reference_date': context.get('reference_date'),
        'data_through_date': data_through,
        'data_through': data_through,
        'limitations': list(_list(context.get('limitations'))),
    }


def _trust_metadata():
    return {
        'service_resolution': 'deterministic_public_beat_strength_then_context_specific_observation',
        'service_observation_order': list(SERVICE_OBSERVATION_ORDER),
        'external_generation_used': False,
        'new_metrics_created': False,
        'context_formula_changes': False,
        'availability_changes': False,
        'fatigue_changes': False,
        'public_ui_added': False,
    }


def _combined_limitations(*groups):
    limitations = []
    for group in groups:
        for item in _list(group):
            if item and item not in limitations:
                limitations.append(item)
    return limitations


def _frame_by_type(story_frames):
    return {
        frame.get('observation_type'): frame
        for frame in _list(story_frames)
        if isinstance(frame, dict)
    }


def _valid_frame(frame):
    frame = _dict(frame)
    return bool(frame) and frame.get('construction_confidence') != CONFIDENCE_LOW


def _number(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coalesce(*values):
    for value in values:
        if value is not None:
            return value
    return None


def _present(value):
    if value is None or value == '':
        return False
    if isinstance(value, (list, dict)) and not value:
        return False
    return True


def _name_from_row(row):
    if isinstance(row, str):
        return ' '.join(row.strip().split())
    return ' '.join(str(_dict(row).get('name') or '').strip().split())


def _names_from(value):
    names = []
    for row in _list(value):
        name = _name_from_row(row)
        if name and name not in names:
            names.append(name)
    return names


def _story_frame(frame):
    return _dict(_dict(frame).get('story_frame'))


def _facts(frame, key):
    return _dict(_story_frame(frame).get(key))


def _strength_step(value, thresholds):
    number = _number(value)
    if number is None:
        return 0
    for threshold, strength in thresholds:
        if number >= threshold:
            return strength
    return 0


def _negative_strength_step(value, thresholds):
    number = _number(value)
    if number is None:
        return 0
    for threshold, strength in thresholds:
        if number <= threshold:
            return strength
    return 0


def _selection_strength_for_coverage(frame):
    observed = _facts(frame, 'observation_facts')
    cause = _facts(frame, 'cause_facts')
    interpretation = _facts(frame, 'interpretation_facts')
    trend = observed.get('rotation_ip_trend') or cause.get('rotation_ip_trend')
    early_rate = observed.get('early_bullpen_entry_rate') or cause.get('early_bullpen_entry_rate')
    coverage = (
        cause.get('bullpen_coverage_ip_7d')
        or interpretation.get('bullpen_coverage_ip_7d')
    )
    return (
        _negative_strength_step(trend, ((-1.0, 2), (-0.5, 1)))
        + _strength_step(early_rate, ((70.0, 4), (60.0, 3), (50.0, 2), (40.0, 1)))
        + _strength_step(coverage, ((5.0, 3), (4.5, 2), (4.0, 1)))
    )


def _coverage_selection_reasons(frame):
    observed = _facts(frame, 'observation_facts')
    cause = _facts(frame, 'cause_facts')
    interpretation = _facts(frame, 'interpretation_facts')
    trend = _number(_coalesce(
        observed.get('rotation_ip_trend'),
        cause.get('rotation_ip_trend'),
    ))
    early_rate = _number(_coalesce(
        observed.get('early_bullpen_entry_rate'),
        cause.get('early_bullpen_entry_rate'),
    ))
    coverage = _number(
        _coalesce(
            cause.get('bullpen_coverage_ip_7d'),
            interpretation.get('bullpen_coverage_ip_7d'),
        )
    )
    reasons = []
    if trend is not None and trend <= -0.5:
        reasons.append('short_start_trend')
    if early_rate is not None and early_rate >= 40.0:
        reasons.append('early_bullpen_entry_pressure')
    if coverage is not None and coverage >= 4.0:
        reasons.append('bullpen_coverage_load')
    return reasons


def _sustainability_evidence(frame, public_story=None):
    observed = _facts(frame, 'observation_facts')
    headline = _facts(frame, 'headline_facts')
    baseline = _facts(frame, 'baseline_facts')
    cause = _facts(frame, 'cause_facts')
    interpretation = _facts(frame, 'interpretation_facts')
    constraint = _facts(frame, 'constraint_facts')
    evidence_package = _dict(_dict(public_story).get('evidence_package'))

    share = _coalesce(
        observed.get('top_three_workload_share_10d'),
        headline.get('top_three_workload_share_10d'),
        interpretation.get('top_three_workload_share_10d'),
    )
    band = _coalesce(
        observed.get('concentration_band'),
        interpretation.get('concentration_band'),
        headline.get('concentration_band'),
    )
    paths = _coalesce(
        interpretation.get('practical_close_game_paths_count'),
        observed.get('practical_close_game_paths_count'),
        headline.get('practical_close_game_paths_count'),
    )
    clean_count = _coalesce(
        constraint.get('clean_workload_options_count'),
        observed.get('clean_workload_options_count'),
        cause.get('clean_workload_option_count'),
    )
    optionality = _coalesce(
        interpretation.get('optionality_band'),
        observed.get('optionality_band'),
        headline.get('optionality_band'),
    )
    core_arms = _names_from(constraint.get('current_operational_core'))
    top_arms = (
        _names_from(headline.get('top_three_relievers'))
        or _names_from(constraint.get('top_three_relievers_10d'))
    )
    route_arms = core_arms or top_arms

    share_number = _number(share)
    paths_number = _number(paths)
    clean_number = _number(clean_count)
    concentration_elevated = (
        band == 'narrow'
        or (share_number is not None and share_number >= 75.0)
    )
    optionality_limited = (
        (paths_number is not None and paths_number <= 3)
        or (clean_number is not None and clean_number <= 1)
    )
    named_arms_available = bool(route_arms)
    forward_route_can_name_arms = bool(route_arms)
    has_baseline = (
        evidence_package.get('has_baseline')
        if 'has_baseline' in evidence_package
        else _present(baseline.get('league_top_three_workload_share_10d'))
    )
    has_cause = (
        evidence_package.get('has_cause')
        if 'has_cause' in evidence_package
        else (
            _present(cause.get('rotation_ip_trend'))
            or _present(paths)
            or _present(clean_count)
        )
    )
    has_forward_constraint = (
        evidence_package.get('has_forward_constraint')
        if 'has_forward_constraint' in evidence_package
        else forward_route_can_name_arms
    )

    suppression_reasons = []
    if not concentration_elevated:
        suppression_reasons.append('insufficient_concentration')
    if not optionality_limited:
        suppression_reasons.append('insufficient_optionality_constraint')
    if not named_arms_available:
        suppression_reasons.append('missing_named_arms')
    if not forward_route_can_name_arms:
        suppression_reasons.append('missing_forward_route_names')
    if not has_baseline:
        suppression_reasons.append('missing_baseline')
    if not has_cause:
        suppression_reasons.append('missing_cause')

    evidence_present = (
        concentration_elevated
        and optionality_limited
        and named_arms_available
        and forward_route_can_name_arms
    )
    return {
        'sustainability_evidence_present': evidence_present,
        'top_three_workload_share_10d': share,
        'concentration_band': band,
        'clean_workload_options_count': clean_count,
        'practical_close_game_paths_count': paths,
        'repeated_route_core_arms': route_arms,
        'top_three_relievers': top_arms,
        'optionality_band': optionality,
        'rotation_pressure': {
            'rotation_avg_ip_7d': _coalesce(
                cause.get('rotation_avg_ip_7d'),
                observed.get('rotation_avg_ip_7d'),
            ),
            'rotation_avg_ip_14d': _coalesce(
                cause.get('rotation_avg_ip_14d'),
                observed.get('rotation_avg_ip_14d'),
            ),
            'rotation_ip_trend': _coalesce(
                cause.get('rotation_ip_trend'),
                observed.get('rotation_ip_trend'),
            ),
            'early_bullpen_entry_rate': _coalesce(
                cause.get('early_bullpen_entry_rate'),
                observed.get('early_bullpen_entry_rate'),
            ),
            'bullpen_coverage_ip_7d': _coalesce(
                cause.get('bullpen_coverage_ip_7d'),
                interpretation.get('bullpen_coverage_ip_7d'),
            ),
        },
        'has_named_arms': named_arms_available,
        'has_baseline': bool(has_baseline),
        'has_cause': bool(has_cause),
        'has_forward_constraint': bool(has_forward_constraint),
        'concentration_meaningfully_elevated': concentration_elevated,
        'optionality_constraint_limited': optionality_limited,
        'forward_route_can_name_arms': forward_route_can_name_arms,
        'suppression_reasons': suppression_reasons,
    }


def _selection_strength_for_sustainability(frame):
    observed = _facts(frame, 'observation_facts')
    interpretation = _facts(frame, 'interpretation_facts')
    constraint = _facts(frame, 'constraint_facts')
    if observed.get('type') != TYPE_CONCENTRATION_PRESSURE:
        return 0
    share = (
        observed.get('top_three_workload_share_10d')
        or interpretation.get('top_three_workload_share_10d')
    )
    band = (
        observed.get('concentration_band')
        or interpretation.get('concentration_band')
    )
    paths = (
        interpretation.get('practical_close_game_paths_count')
        or observed.get('practical_close_game_paths_count')
    )
    clean_count = (
        constraint.get('clean_workload_options_count')
        or observed.get('clean_workload_options_count')
    )
    current_core = _list(constraint.get('current_operational_core'))

    strength = _strength_step(share, ((90.0, 4), (85.0, 3), (75.0, 2), (70.0, 1)))
    if band == 'narrow':
        strength += 2
    elif band == 'concentrated':
        strength += 1
    if _number(paths) is not None and _number(paths) <= 3:
        strength += 1
    if _number(clean_count) is not None and _number(clean_count) <= 1:
        strength += 2
    if current_core:
        strength += 1
    return strength


def _sustainability_selection_reasons(frame, public_story=None):
    evidence = _sustainability_evidence(frame, public_story=public_story)
    reasons = []
    if evidence.get('concentration_meaningfully_elevated'):
        reasons.append('elevated_top_three_workload_share')
    if evidence.get('optionality_constraint_limited'):
        if _number(evidence.get('practical_close_game_paths_count')) is not None:
            reasons.append('limited_practical_paths')
        if _number(evidence.get('clean_workload_options_count')) is not None:
            reasons.append('limited_clean_options')
    if evidence.get('has_named_arms'):
        reasons.append('named_route_arms_available')
    rotation = _dict(evidence.get('rotation_pressure'))
    trend = _number(rotation.get('rotation_ip_trend'))
    early_rate = _number(rotation.get('early_bullpen_entry_rate'))
    if (trend is not None and trend < 0) or (early_rate is not None and early_rate >= 40.0):
        reasons.append('rotation_pressure_context')
    return reasons


def _selection_strength_for_depth(frame):
    observed = _facts(frame, 'observation_facts')
    interpretation = _facts(frame, 'interpretation_facts')
    band = observed.get('depth_pressure_band')
    inactive = observed.get('inactive_bullpen_arms_count')
    paths = interpretation.get('practical_close_game_paths_count')
    optionality = interpretation.get('optionality_band')

    strength = 0
    if band == 'heavy':
        strength += 3
    elif band == 'moderate':
        strength += 1
    strength += _strength_step(inactive, ((12.0, 2), (7.0, 1)))
    paths_number = _number(paths)
    if paths_number is not None and paths_number <= 2:
        strength += 2
    elif paths_number is not None and paths_number <= 3:
        strength += 1
    if optionality == 'thin':
        strength += 2
    elif optionality == 'narrow':
        strength += 1
    return strength


def _depth_selection_reasons(frame):
    observed = _facts(frame, 'observation_facts')
    interpretation = _facts(frame, 'interpretation_facts')
    reasons = []
    if observed.get('depth_pressure_band') in {'moderate', 'heavy'}:
        reasons.append('inactive_depth_pressure')
    inactive = _number(observed.get('inactive_bullpen_arms_count'))
    if inactive is not None and inactive >= 7.0:
        reasons.append('large_inactive_group')
    paths = _number(interpretation.get('practical_close_game_paths_count'))
    if paths is not None and paths <= 3:
        reasons.append('practical_paths_narrowed')
    if interpretation.get('optionality_band') in {'thin', 'narrow'}:
        reasons.append('optionality_constraint')
    return reasons


def _selection_strength_for_route(frame):
    observed = _facts(frame, 'observation_facts')
    interpretation = _facts(frame, 'interpretation_facts')
    band = observed.get('stability_band') or interpretation.get('stability_band')
    changes = observed.get('core_change_count')
    retention = interpretation.get('core_retention_count')

    strength = 0
    if band == 'rebuilding':
        strength += 4
    elif band == 'transitioning':
        strength += 2
    strength += _strength_step(changes, ((3.0, 2), (2.0, 1)))
    if _number(retention) is not None and _number(retention) <= 0:
        strength += 1
    return strength


def _route_selection_reasons(frame):
    observed = _facts(frame, 'observation_facts')
    interpretation = _facts(frame, 'interpretation_facts')
    reasons = []
    band = observed.get('stability_band') or interpretation.get('stability_band')
    if band in {'transitioning', 'rebuilding'}:
        reasons.append('operational_core_changed')
    changes = _number(observed.get('core_change_count'))
    if changes is not None and changes >= 2:
        reasons.append('multiple_core_changes')
    retention = _number(interpretation.get('core_retention_count'))
    if retention is not None and retention <= 0:
        reasons.append('no_core_retention')
    return reasons


def _selection_strength_for_availability_depth(frame):
    observed = _facts(frame, 'observation_facts')
    interpretation = _facts(frame, 'interpretation_facts')
    headline = _facts(frame, 'headline_facts')
    observation_type = observed.get('type')

    strength = 0
    if observation_type == TYPE_OPTIONALITY_STRENGTH:
        band = _coalesce(
            observed.get('optionality_band'),
            interpretation.get('optionality_band'),
            headline.get('optionality_band'),
        )
        paths = _coalesce(
            observed.get('practical_close_game_paths_count'),
            headline.get('practical_close_game_paths_count'),
        )
        if band == 'deep':
            strength += 3
        elif band == 'flexible':
            strength += 1
        strength += _strength_step(paths, ((5.0, 1),))
        strength += _strength_step(observed.get('clean_workload_options_count'), ((3.0, 1),))
        strength += _strength_step(observed.get('available_arms_count'), ((7.0, 1),))
    elif observation_type == TYPE_STABLE_CORE:
        band = _coalesce(
            observed.get('stability_band'),
            interpretation.get('stability_band'),
        )
        if band == 'stable':
            strength += 2
        strength += _strength_step(observed.get('core_retention_count'), ((4.0, 1),))
        changes = _number(observed.get('core_change_count'))
        if changes is not None and changes <= 0:
            strength += 1
    return strength


def _availability_depth_selection_reasons(frame):
    observed = _facts(frame, 'observation_facts')
    interpretation = _facts(frame, 'interpretation_facts')
    observation_type = observed.get('type')
    reasons = []
    if observation_type == TYPE_OPTIONALITY_STRENGTH:
        band = _coalesce(observed.get('optionality_band'), interpretation.get('optionality_band'))
        if band in {'deep', 'flexible'}:
            reasons.append('rested_optionality_band')
        paths = _number(observed.get('practical_close_game_paths_count'))
        if paths is not None and paths >= 5:
            reasons.append('multiple_close_game_paths')
        clean = _number(observed.get('clean_workload_options_count'))
        if clean is not None and clean >= 3:
            reasons.append('clean_workload_options')
        available = _number(observed.get('available_arms_count'))
        if available is not None and available >= 7:
            reasons.append('deep_available_board')
    elif observation_type == TYPE_STABLE_CORE:
        band = _coalesce(observed.get('stability_band'), interpretation.get('stability_band'))
        if band == 'stable':
            reasons.append('stable_operational_core')
        retention = _number(observed.get('core_retention_count'))
        if retention is not None and retention >= 4:
            reasons.append('high_core_retention')
        changes = _number(observed.get('core_change_count'))
        if changes is not None and changes <= 0:
            reasons.append('no_core_changes')
    return reasons


def _selection_strength_for_trust_lane(frame):
    observed = _facts(frame, 'observation_facts')
    interpretation = _facts(frame, 'interpretation_facts')
    cause = _facts(frame, 'cause_facts')
    clean = _number(observed.get('clean_workload_options_count'))
    secondary = _number(observed.get('secondary_options_count'))
    share = _coalesce(
        cause.get('top_three_workload_share_10d'),
        interpretation.get('top_three_workload_share_10d'),
    )
    concentration = _coalesce(
        interpretation.get('concentration_band'),
        observed.get('concentration_band'),
    )

    strength = 0
    # A thinner trusted/clean lane is a stronger trust-lane read.
    if clean is not None:
        if clean <= 0:
            strength += 4
        elif clean <= 1:
            strength += 3
        elif clean <= 2:
            strength += 2
    # More available arms working behind workload flags widens the gap between the
    # apparent board and the trusted lane.
    strength += _strength_step(secondary, ((5.0, 2), (3.0, 1)))
    # A high top-three workload share corroborates that the few trusted arms are
    # carrying the leverage route.
    strength += _strength_step(share, ((85.0, 2), (75.0, 1)))
    if concentration == 'narrow':
        strength += 1
    return strength


def _trust_lane_selection_reasons(frame):
    observed = _facts(frame, 'observation_facts')
    interpretation = _facts(frame, 'interpretation_facts')
    cause = _facts(frame, 'cause_facts')
    reasons = []
    clean = _number(observed.get('clean_workload_options_count'))
    if clean is not None and clean <= 2:
        reasons.append('thin_trusted_lane')
    secondary = _number(observed.get('secondary_options_count'))
    if secondary is not None and secondary >= 3:
        reasons.append('available_arms_working_through_flags')
    available = _number(observed.get('available_arms_count'))
    if available is not None and available >= 4:
        reasons.append('acceptable_available_board')
    share = _number(_coalesce(
        cause.get('top_three_workload_share_10d'),
        interpretation.get('top_three_workload_share_10d'),
    ))
    if share is not None and share >= 75.0:
        reasons.append('trusted_arms_carrying_route')
    return reasons


def _selection_strength_for_bridge(frame):
    observed = _facts(frame, 'observation_facts')
    interpretation = _facts(frame, 'interpretation_facts')
    cause = _facts(frame, 'cause_facts')
    early_rate = _coalesce(observed.get('early_bullpen_entry_rate'), cause.get('early_bullpen_entry_rate'))
    coverage_ip = _coalesce(observed.get('bullpen_coverage_ip_7d'), cause.get('bullpen_coverage_ip_7d'))
    volatile = _number(_coalesce(
        observed.get('volatile_middle_count'),
        interpretation.get('volatile_middle_count'),
    ))
    clean = _number(observed.get('clean_workload_options_count'))

    strength = 0
    # A longer/earlier handoff demand is a stronger bridge read.
    strength += _strength_step(early_rate, ((50.0, 2), (35.0, 1)))
    strength += _strength_step(coverage_ip, ((4.5, 2), (3.8, 1)))
    # More volatile middle arms carrying the bridge widens the instability.
    strength += _strength_step(volatile, ((4.0, 2), (2.0, 1)))
    # Fewer clean bridge arms is a thinner, more fragile handoff.
    if clean is not None:
        if clean <= 0:
            strength += 2
        elif clean <= 1:
            strength += 1
    return strength


def _bridge_selection_reasons(frame):
    observed = _facts(frame, 'observation_facts')
    interpretation = _facts(frame, 'interpretation_facts')
    cause = _facts(frame, 'cause_facts')
    reasons = []
    if (observed.get('stability_band') or interpretation.get('stability_band')) == 'stable':
        reasons.append('settled_late_core')
    early_rate = _number(_coalesce(observed.get('early_bullpen_entry_rate'), cause.get('early_bullpen_entry_rate')))
    coverage_ip = _number(_coalesce(observed.get('bullpen_coverage_ip_7d'), cause.get('bullpen_coverage_ip_7d')))
    if (early_rate is not None and early_rate >= 35.0) or (coverage_ip is not None and coverage_ip >= 3.8):
        reasons.append('starter_handoff_demand')
    volatile = _number(_coalesce(observed.get('volatile_middle_count'), interpretation.get('volatile_middle_count')))
    if volatile is not None and volatile >= 2:
        reasons.append('volatile_middle_options')
    clean = _number(observed.get('clean_workload_options_count'))
    if clean is not None and clean <= 2:
        reasons.append('thin_clean_bridge')
    return reasons


def _candidate_selection_profile(candidate):
    public_story = _dict(candidate.get('public_story'))
    frame = _dict(candidate.get('construction_frame'))
    story_type = public_story.get('story_type')
    sustainability_evidence = None
    if story_type == BEAT_COVERAGE_PRESSURE:
        strength = _selection_strength_for_coverage(frame)
        reasons = _coverage_selection_reasons(frame)
    elif story_type == BEAT_SUSTAINABILITY_QUESTION:
        strength = _selection_strength_for_sustainability(frame)
        sustainability_evidence = _sustainability_evidence(
            frame,
            public_story=public_story,
        )
        reasons = _sustainability_selection_reasons(frame, public_story=public_story)
    elif story_type == BEAT_DEPTH_CONSTRAINT:
        strength = _selection_strength_for_depth(frame)
        reasons = _depth_selection_reasons(frame)
    elif story_type == BEAT_ROUTE_CHANGE:
        strength = _selection_strength_for_route(frame)
        reasons = _route_selection_reasons(frame)
    elif story_type == BEAT_AVAILABILITY_DEPTH:
        strength = _selection_strength_for_availability_depth(frame)
        reasons = _availability_depth_selection_reasons(frame)
    elif story_type == BEAT_TRUST_LANE:
        strength = _selection_strength_for_trust_lane(frame)
        reasons = _trust_lane_selection_reasons(frame)
    elif story_type == BEAT_BRIDGE:
        strength = _selection_strength_for_bridge(frame)
        reasons = _bridge_selection_reasons(frame)
    else:
        strength = 0
        reasons = []
    profile = {
        'story_type': story_type,
        'selection_strength': strength,
        'evidence_completeness': int(public_story.get('evidence_completeness') or 0),
        'selection_reasons': reasons,
    }
    if sustainability_evidence is not None:
        profile['sustainability_evidence'] = sustainability_evidence
    return profile


def _candidate_is_publicly_selectable(candidate):
    public_story = _dict(candidate.get('public_story'))
    selected = _dict(candidate.get('selected_observation'))
    profile = _dict(candidate.get('selection_profile'))
    story_type = public_story.get('story_type')
    strength = int(profile.get('selection_strength') or 0)
    # Never publish a zero-strength optionality read reframed as a worry beat.
    if (
        story_type == BEAT_SUSTAINABILITY_QUESTION
        and selected.get('type') == TYPE_OPTIONALITY_STRENGTH
        and strength <= 0
    ):
        return False
    # Positive depth/rest must clear an evidence bar; no fabricated good news.
    if story_type == BEAT_AVAILABILITY_DEPTH and strength <= 0:
        return False
    # Trust-lane must clear an evidence bar too; no fabricated thin-lane story.
    if story_type == BEAT_TRUST_LANE and strength <= 0:
        return False
    # Bridge-instability must clear an evidence bar too; no fabricated bridge story.
    if story_type == BEAT_BRIDGE and strength <= 0:
        return False
    return True


def _candidate_selection_key(candidate):
    observation = _dict(_dict(candidate).get('selected_observation'))
    observation_type = observation.get('type')
    public_story = _dict(candidate.get('public_story'))
    profile = _dict(candidate.get('selection_profile')) or _candidate_selection_profile(candidate)
    return (
        -int(profile.get('selection_strength') or 0),
        -SERVICE_SEVERITY_ORDER.get(observation.get('severity'), 0),
        PUBLIC_BEAT_TIEBREAK_PRIORITY.get(
            public_story.get('story_type'),
            len(PUBLIC_BEAT_TIEBREAK_PRIORITY),
        ),
        -int(profile.get('evidence_completeness') or public_story.get('evidence_completeness') or 0),
        SERVICE_OBSERVATION_PRIORITY.get(observation_type, len(SERVICE_OBSERVATION_ORDER)),
        str(observation_type or ''),
    )


def select_service_story_candidate(observations, story_frames):
    """Return the strongest valid service story candidate deterministically."""
    rows = [
        observation
        for observation in _list(observations)
        if isinstance(observation, dict)
    ]
    frames = _frame_by_type(story_frames)
    candidates = []
    for observation in rows:
        observation_type = observation.get('type')
        frame = frames.get(observation_type)
        if not _valid_frame(frame):
            continue
        # Reasoning layer between Story Construction and the Story Writer: build
        # the editorial intent from the construction frame, then let the writer
        # consume it. The intent is carried on the writer output (internal only).
        editorial_intent = build_editorial_intent(
            observation_type=observation_type,
            frame=frame,
            selected_observation=observation,
        )
        writer_output = write_story_frame(frame, editorial_intent=editorial_intent)
        if _dict(writer_output.get('validation')).get('passed') is not True:
            continue
        candidate = {
            'selected_observation': deepcopy(observation),
            'construction_frame': deepcopy(frame),
            'writer_output': writer_output,
        }
        public_story = interpret_story_candidate(candidate)
        if public_story.get('suppressed') is True:
            continue
        writer_output = deepcopy(writer_output)
        writer_output['written_observation'] = deepcopy(public_story.get('written_story') or {})
        writer_output['validation'] = validate_written_observation(writer_output)
        if _dict(writer_output.get('validation')).get('passed') is not True:
            continue
        selection_profile = _candidate_selection_profile({
            'selected_observation': observation,
            'construction_frame': frame,
            'writer_output': writer_output,
            'public_story': public_story,
        })
        candidate = {
            'selected_observation': deepcopy(observation),
            'construction_frame': deepcopy(frame),
            'writer_output': writer_output,
            'public_story': public_story,
            'selection_profile': selection_profile,
        }
        if not _candidate_is_publicly_selectable(candidate):
            continue
        candidates.append(candidate)
    if not candidates:
        return None
    selected = sorted(candidates, key=_candidate_selection_key)[0]
    selected['candidate_profiles'] = [
        {
            'selected': candidate is selected,
            'selection_rank': rank + 1,
            'observation_type': _dict(candidate.get('selected_observation')).get('type'),
            'severity': _dict(candidate.get('selected_observation')).get('severity'),
            'evidence_package': deepcopy(
                _dict(_dict(candidate.get('public_story')).get('evidence_package'))
            ),
            **_dict(candidate.get('selection_profile')),
        }
        for rank, candidate in enumerate(sorted(candidates, key=_candidate_selection_key))
    ]
    return selected


def _base_payload(team_id, as_of_date, team_context, observation_payload, construction_payload):
    identity = _identity(team_context, team_id=team_id)
    observations = _list(_dict(observation_payload).get('observations'))
    story_frames = _list(_dict(construction_payload).get('story_frames'))
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': SOURCE,
        'team_id': identity['team_id'],
        'team_name': identity['team_name'],
        'team_abbreviation': identity['team_abbreviation'],
        'as_of_date': _iso(as_of_date) or _dict(team_context).get('reference_date'),
        'state': STATE_NEUTRAL,
        'story_available': False,
        'neutral_reason': None,
        'selected_observation': None,
        'construction_frame': None,
        'written_story': None,
        'writer_output': None,
        'story_type': None,
        'story_type_label': None,
        'public_story_beat': None,
        'selection_metadata': None,
        'supporting_context': _supporting_context(team_context),
        'freshness': _freshness(team_context, as_of_date=as_of_date),
        'trust_metadata': _trust_metadata(),
        'observation_count': len(observations),
        'construction_frame_count': len(story_frames),
        'limitations': _combined_limitations(
            _dict(team_context).get('limitations'),
            _dict(observation_payload).get('limitations'),
            _dict(construction_payload).get('limitations'),
        ),
    }


def build_team_story(team_id, as_of_date=None, *, team_context=None):
    """
    Build one deterministic BaseballOS story contract for a team and date.

    The service coordinates the existing pipeline and returns a neutral payload
    when no valid observation can be written from the supplied facts.
    """
    context_supplied = isinstance(team_context, dict)
    context = (
        deepcopy(team_context)
        if context_supplied
        else build_team_bullpen_context(team_id, reference_date=as_of_date)
    )
    observation_payload = build_team_story_observation_payload(context)
    construction_payload = construct_team_story_frames(
        context,
        observation_payload=observation_payload,
    )
    payload = _base_payload(
        team_id,
        as_of_date,
        context,
        observation_payload,
        construction_payload,
    )

    observations = _list(observation_payload.get('observations'))
    if not observations:
        payload['neutral_reason'] = NEUTRAL_NO_OBSERVATIONS
        payload['limitations'] = _combined_limitations(
            payload['limitations'],
            [NEUTRAL_NO_OBSERVATIONS],
        )
        return payload

    candidate = select_service_story_candidate(
        observations,
        construction_payload.get('story_frames'),
    )
    if candidate is None:
        payload['neutral_reason'] = NEUTRAL_NO_VALID_FRAME
        payload['limitations'] = _combined_limitations(
            payload['limitations'],
            [NEUTRAL_NO_VALID_FRAME],
        )
        return payload

    writer_output = _dict(candidate.get('writer_output'))
    construction_frame = _dict(candidate.get('construction_frame'))
    public_story = _dict(candidate.get('public_story'))
    payload.update({
        'state': STATE_STORY_AVAILABLE,
        'story_available': True,
        'selected_observation': candidate.get('selected_observation'),
        'construction_frame': construction_frame,
        'written_story': deepcopy(writer_output.get('written_observation')),
        'writer_output': writer_output,
        'story_type': public_story.get('story_type'),
        'story_type_label': public_story.get('story_type_label'),
        'public_story_beat': {
            key: deepcopy(value)
            for key, value in public_story.items()
            if key not in {'written_story'}
        },
        'selection_metadata': {
            'selected_profile': deepcopy(candidate.get('selection_profile')),
            'candidate_profiles': deepcopy(candidate.get('candidate_profiles') or []),
        },
        'supporting_context': _supporting_context(context, construction_frame),
        'limitations': _combined_limitations(
            payload['limitations'],
            construction_frame.get('limitations'),
            writer_output.get('limitations'),
        ),
    })
    # Eligibility-aware context is added only on the live path (no externally
    # supplied team_context), so mocked story tests stay byte-stable. It appends
    # a governed sentence to an existing forward-constraint beat when Swing/Bulk
    # arms materially shape coverage/depth; it never changes payload shape.
    if not context_supplied:
        payload = apply_swing_bulk_story_context(payload, reference_date=as_of_date)
    return payload


def build_story_intelligence_service_v1(*, team_ids=None, as_of_date=None, team_contexts=None):
    """Build service-level story contracts for supplied teams."""
    if team_contexts is not None:
        teams = [
            build_team_story(
                _identity(team_context).get('team_id'),
                as_of_date=as_of_date,
                team_context=team_context,
            )
            for team_context in _list(team_contexts)
        ]
    else:
        teams = [
            build_team_story(team_id, as_of_date=as_of_date)
            for team_id in _list(team_ids)
        ]
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': SOURCE,
        'as_of_date': _iso(as_of_date),
        'team_count': len(teams),
        'teams': teams,
        'limitations': [
            'service_coordinates_existing_deterministic_engines',
            'neutral_state_when_no_valid_story_exists',
            'no_external_generation',
            'no_new_metrics',
            'no_engine_state_changes',
        ],
    }


__all__ = [
    'CAPABILITY',
    'NEUTRAL_NO_OBSERVATIONS',
    'NEUTRAL_NO_VALID_FRAME',
    'SERVICE_OBSERVATION_ORDER',
    'SERVICE_SEVERITY_ORDER',
    'STATE_NEUTRAL',
    'STATE_STORY_AVAILABLE',
    'VERSION',
    'build_story_intelligence_service_v1',
    'build_team_story',
    'select_service_story_candidate',
]
