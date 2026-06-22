"""Public four-beat interpretation for Story Intelligence V1.

This layer translates internal observation evidence into the public editorial
beat names. It does not build context, calculate availability, alter fatigue,
or change trust labels.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from services.story_observation_engine import (
    TYPE_BRIDGE_INSTABILITY,
    TYPE_CONCENTRATION_PRESSURE,
    TYPE_CORE_TRANSITION,
    TYPE_DEPTH_PRESSURE,
    TYPE_OPTIONALITY_STRENGTH,
    TYPE_ROTATION_PRESSURE,
    TYPE_STABLE_CORE,
    TYPE_TRUST_LANE_PRESSURE,
)
from services.story_voice_library_v1 import render_voice_line


CAPABILITY = 'story_four_beat_interpreter_v1'
VERSION = '2026-06-21.v1'

BEAT_ROUTE_CHANGE = 'route_change'
BEAT_COVERAGE_PRESSURE = 'coverage_pressure'
BEAT_DEPTH_CONSTRAINT = 'depth_constraint'
BEAT_SUSTAINABILITY_QUESTION = 'sustainability_question'
BEAT_AVAILABILITY_DEPTH = 'availability_depth'
BEAT_TRUST_LANE = 'trust_lane'
BEAT_BRIDGE = 'bridge'

PUBLIC_BEATS = {
    BEAT_ROUTE_CHANGE: {
        'key': BEAT_ROUTE_CHANGE,
        'label': 'Route Change',
        'question_answered': 'Who is handling the important outs now?',
    },
    BEAT_COVERAGE_PRESSURE: {
        'key': BEAT_COVERAGE_PRESSURE,
        'label': 'Coverage Pressure',
        'question_answered': 'Why is the bullpen carrying extra innings?',
    },
    BEAT_DEPTH_CONSTRAINT: {
        'key': BEAT_DEPTH_CONSTRAINT,
        'label': 'Depth Constraint',
        'question_answered': 'Why does the bullpen have fewer late-inning choices than the roster suggests?',
    },
    BEAT_SUSTAINABILITY_QUESTION: {
        'key': BEAT_SUSTAINABILITY_QUESTION,
        'label': 'Sustainability Question',
        'question_answered': 'Can the current usage pattern keep functioning if the same conditions continue?',
    },
    BEAT_AVAILABILITY_DEPTH: {
        'key': BEAT_AVAILABILITY_DEPTH,
        'label': 'Availability Depth',
        'question_answered': 'How many rested, usable late-inning options does the bullpen have to work with?',
    },
    BEAT_TRUST_LANE: {
        'key': BEAT_TRUST_LANE,
        'label': 'Trust Lane',
        'question_answered': 'How many rested, trusted arms does the late-game plan actually lean on?',
    },
    BEAT_BRIDGE: {
        'key': BEAT_BRIDGE,
        'label': 'Bridge Instability',
        'question_answered': 'How fragile is the path from the starter to the trusted late-game arms?',
    },
}

# Positive depth/rest reads keep a positive beat. A genuine constraint is a
# separate observation (depth_pressure / rotation_pressure) that competes on its
# own evidence in selection, so positive optionality is not folded into a worry
# frame, and a settled core is not forced into a route-change story.
BASE_OBSERVATION_BEAT_MAP = {
    TYPE_CORE_TRANSITION: BEAT_ROUTE_CHANGE,
    TYPE_STABLE_CORE: BEAT_AVAILABILITY_DEPTH,
    TYPE_ROTATION_PRESSURE: BEAT_COVERAGE_PRESSURE,
    TYPE_DEPTH_PRESSURE: BEAT_DEPTH_CONSTRAINT,
    TYPE_CONCENTRATION_PRESSURE: BEAT_SUSTAINABILITY_QUESTION,
    TYPE_OPTIONALITY_STRENGTH: BEAT_AVAILABILITY_DEPTH,
    TYPE_TRUST_LANE_PRESSURE: BEAT_TRUST_LANE,
    TYPE_BRIDGE_INSTABILITY: BEAT_BRIDGE,
}

PUBLIC_BANNED_TERMS = (
    'bet',
    'betting',
    'odds',
    'probability',
    'projection',
    'projected',
    'predict',
    'prediction',
    'guaranteed',
    'lock',
    'will win',
    'expected to win',
)


def _dict(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _clean_text(value):
    return ' '.join(str(value or '').strip().split())


def _present(value):
    if value is None or value == '':
        return False
    if isinstance(value, (list, dict)) and not value:
        return False
    return True


def _number(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _story_frame(frame):
    return _dict(_dict(frame).get('story_frame'))


def _facts(frame, key):
    return _dict(_story_frame(frame).get(key))


def _name_from_row(row):
    if isinstance(row, str):
        return _clean_text(row)
    return _clean_text(_dict(row).get('name'))


def _names_from(value):
    names = []
    for row in _list(value):
        name = _name_from_row(row)
        if name and name not in names:
            names.append(name)
    return names


def _join_names(names, *, limit=3):
    names = [name for name in _list(names) if _clean_text(name)]
    if not names:
        return None
    shown = names[:limit]
    if len(shown) == 1:
        return shown[0]
    if len(shown) == 2:
        return f'{shown[0]} and {shown[1]}'
    return f"{', '.join(shown[:-1])}, and {shown[-1]}"


def _sentence(text):
    text = _clean_text(text)
    if not text:
        return None
    if text[-1] not in '.!?':
        text = f'{text}.'
    return text


def _all_story_text(written_story):
    return ' '.join(
        _clean_text(value)
        for value in _dict(written_story).values()
        if value
    )


def contains_public_banned_language(text):
    lower = _clean_text(text).lower()
    return any(term in lower for term in PUBLIC_BANNED_TERMS)


def _has_forward_clause(text):
    lower = _clean_text(text).lower()
    return (
        lower.startswith('if ')
        or ' if ' in lower
        or 'current route points back to' in lower
        or 'fewer ways to' in lower
        or 'late-inning choices' in lower
    )


def _candidate_names(frame):
    sections = _story_frame(frame)
    names = []
    for section_key in (
        'headline_facts',
        'cause_facts',
        'constraint_facts',
        'interpretation_facts',
    ):
        facts = _dict(sections.get(section_key))
        for key in (
            'top_three_relievers',
            'current_operational_core',
            'new_core_members',
            'clean_workload_options',
            'secondary_options',
            'inactive_bullpen_arms',
        ):
            for name in _names_from(facts.get(key)):
                if name not in names:
                    names.append(name)
    return names


def public_beat_for_observation(observation_type, *, frame=None):
    """Map one internal observation type to a public beat key."""

    if observation_type == TYPE_CONCENTRATION_PRESSURE:
        cause = _facts(frame, 'cause_facts')
        rotation_trend = _number(cause.get('rotation_ip_trend'))
        early_rate = _number(cause.get('early_bullpen_entry_rate'))
        if (
            (rotation_trend is not None and rotation_trend <= -0.5)
            or (early_rate is not None and early_rate >= 40.0)
        ):
            return BEAT_COVERAGE_PRESSURE
        return BEAT_SUSTAINABILITY_QUESTION

    return BASE_OBSERVATION_BEAT_MAP.get(observation_type)


def observation_public_beat_map():
    """Return the deterministic baseline map used by tests and reports."""

    return {
        TYPE_CORE_TRANSITION: BEAT_ROUTE_CHANGE,
        TYPE_STABLE_CORE: BEAT_AVAILABILITY_DEPTH,
        TYPE_ROTATION_PRESSURE: BEAT_COVERAGE_PRESSURE,
        TYPE_CONCENTRATION_PRESSURE: BEAT_SUSTAINABILITY_QUESTION,
        TYPE_DEPTH_PRESSURE: BEAT_DEPTH_CONSTRAINT,
        TYPE_OPTIONALITY_STRENGTH: BEAT_AVAILABILITY_DEPTH,
        TYPE_TRUST_LANE_PRESSURE: BEAT_TRUST_LANE,
        TYPE_BRIDGE_INSTABILITY: BEAT_BRIDGE,
    }


def _default_forward_clause(beat, frame, names):
    name_text = _join_names(names)
    if beat == BEAT_ROUTE_CHANGE:
        if name_text:
            return f'If the next game tightens, the route points back through {name_text}.'
        return 'If the next game tightens, the route points back through the current core.'
    if beat == BEAT_COVERAGE_PRESSURE:
        return 'If the short starts continue, the bullpen has fewer ways to spread the middle innings.'
    if beat == BEAT_DEPTH_CONSTRAINT:
        return 'If the roster stays this thin, the manager has fewer ways to cover the late innings than the roster count suggests.'
    if beat == BEAT_SUSTAINABILITY_QUESTION:
        if name_text:
            return f'If this workload pattern holds, the route remains narrow around {name_text}.'
        return 'If this workload pattern holds, the bullpen has fewer ways to spread the late innings.'
    if beat == BEAT_AVAILABILITY_DEPTH:
        if name_text:
            return f'If the game stays close, the manager can spread the late innings beyond {name_text} alone.'
        return 'If the game stays close, the bullpen has room to spread the late innings across several rested arms.'
    if beat == BEAT_TRUST_LANE:
        if name_text:
            return f'If the game tightens, the trusted late-game lane runs back through {name_text}, thinner than the available arm count suggests.'
        return 'If the game tightens, the trusted late-game lane stays thinner than the available arm count suggests.'
    if beat == BEAT_BRIDGE:
        if name_text:
            return f'If the starters keep exiting early, the path to {name_text} runs through a fragile middle, thinner than the settled late group suggests.'
        return 'If the starters keep exiting early, the path to the late group runs through a fragile middle, thinner than the settled late arms suggest.'
    return None


def _route_change_headline(frame, written_story):
    current = (
        _names_from(_facts(frame, 'headline_facts').get('current_operational_core'))
        or _names_from(_facts(frame, 'cause_facts').get('current_operational_core'))
        or _candidate_names(frame)
    )
    previous = _names_from(_facts(frame, 'baseline_facts').get('previous_operational_core'))
    retention = (
        _number(_facts(frame, 'interpretation_facts').get('core_retention_count'))
        if _present(_facts(frame, 'interpretation_facts').get('core_retention_count'))
        else _number(_facts(frame, 'constraint_facts').get('core_retention_count'))
    )
    if current and previous:
        names = _join_names(current)
        if retention is not None and retention <= 0:
            return f'The route has changed, now running through {names}.'
        library_headline = render_voice_line(
            BEAT_ROUTE_CHANGE,
            stable_parts=(
                _dict(frame).get('team_id'),
                _dict(frame).get('team_abbreviation'),
                names,
                _join_names(previous),
                retention,
            ),
            team=_dict(frame).get('team_name') or 'This bullpen',
            possessive=(
                f"{_dict(frame).get('team_name')}'"
                if _clean_text(_dict(frame).get('team_name')).lower().endswith('s')
                else f"{_dict(frame).get('team_name')}'s"
            ) if _clean_text(_dict(frame).get('team_name')) else 'This bullpen',
            names=names,
        )
        return library_headline or f'The roster changed while the route still runs through {names}.'
    return _dict(written_story).get('headline')


def _public_written_story(beat, frame, written_story):
    written = deepcopy(_dict(written_story))
    if beat == BEAT_ROUTE_CHANGE:
        headline = _route_change_headline(frame, written)
        if headline:
            written['headline'] = _sentence(headline)

    names = _candidate_names(frame)
    constraint = _sentence(written.get('constraint_paragraph'))
    if not _has_forward_clause(constraint):
        constraint = _default_forward_clause(beat, frame, names)
    written['constraint_paragraph'] = _sentence(constraint)
    return written


def _evidence_package(frame, written_story):
    written = _dict(written_story)
    names = _candidate_names(frame)
    baseline = written.get('baseline_paragraph')
    cause = written.get('cause_paragraph')
    consequence = written.get('observation_paragraph') or written.get('constraint_paragraph')
    constraint = written.get('constraint_paragraph')
    return {
        'has_named_arms': bool(names),
        'has_cause': bool(_clean_text(cause)),
        'has_baseline': bool(_clean_text(baseline)),
        'has_present_consequence': bool(_clean_text(consequence)),
        'has_forward_constraint': bool(_has_forward_clause(constraint)),
    }


def _evidence_completeness_value(package):
    return sum(1 for value in _dict(package).values() if value is True)


def interpret_story_candidate(candidate):
    """Return public beat metadata and public written copy for a candidate."""

    candidate = _dict(candidate)
    selected = _dict(candidate.get('selected_observation'))
    frame = _dict(candidate.get('construction_frame'))
    writer_output = _dict(candidate.get('writer_output'))
    written = _dict(writer_output.get('written_observation'))
    internal_type = selected.get('type') or frame.get('observation_type')
    beat = public_beat_for_observation(internal_type, frame=frame)
    if beat not in PUBLIC_BEATS:
        return {
            'capability': CAPABILITY,
            'version': VERSION,
            'story_type': None,
            'suppressed': True,
            'suppression_reason': 'unsupported_internal_observation_type',
            'internal_observation_type': internal_type,
        }

    public_written = _public_written_story(beat, frame, written)
    evidence_package = _evidence_package(frame, public_written)
    text = _all_story_text(public_written)
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'story_type': beat,
        'story_type_label': PUBLIC_BEATS[beat]['label'],
        'question_answered': PUBLIC_BEATS[beat]['question_answered'],
        'internal_observation_type': internal_type,
        'source_layers': list(_list(selected.get('source_layers'))),
        'written_story': public_written,
        'evidence_package': evidence_package,
        'evidence_completeness': _evidence_completeness_value(evidence_package),
        'contains_banned_language': contains_public_banned_language(text),
        'suppressed': contains_public_banned_language(text),
        'suppression_reason': (
            'banned_public_language'
            if contains_public_banned_language(text)
            else None
        ),
    }


__all__ = [
    'BEAT_AVAILABILITY_DEPTH',
    'BEAT_BRIDGE',
    'BEAT_COVERAGE_PRESSURE',
    'BEAT_DEPTH_CONSTRAINT',
    'BEAT_ROUTE_CHANGE',
    'BEAT_SUSTAINABILITY_QUESTION',
    'BEAT_TRUST_LANE',
    'CAPABILITY',
    'PUBLIC_BEATS',
    'VERSION',
    'contains_public_banned_language',
    'interpret_story_candidate',
    'observation_public_beat_map',
    'public_beat_for_observation',
]
