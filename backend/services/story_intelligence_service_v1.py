"""Story Intelligence Service V1.

Backend coordinator for the deterministic story intelligence pipeline. It
connects bullpen context, structured observations, construction frames, and the
Story Writer V1 output without creating public UI, routes, forecasts, or new
metrics.
"""

from __future__ import annotations

from copy import deepcopy

from services.bullpen_context import build_team_bullpen_context
from services.story_construction_engine import (
    CONFIDENCE_LOW,
    construct_team_story_frames,
)
from services.story_observation_engine import (
    TYPE_CONCENTRATION_PRESSURE,
    TYPE_CORE_TRANSITION,
    TYPE_DEPTH_PRESSURE,
    TYPE_OPTIONALITY_STRENGTH,
    TYPE_ROTATION_PRESSURE,
    TYPE_STABLE_CORE,
    build_team_story_observation_payload,
)
from services.story_writer_v1 import write_story_frame


CAPABILITY = 'story_intelligence_service_v1'
VERSION = '2026-06-21.v1'
SOURCE = 'backend'

SERVICE_OBSERVATION_ORDER = (
    TYPE_ROTATION_PRESSURE,
    TYPE_CONCENTRATION_PRESSURE,
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
        'service_resolution': 'deterministic_severity_then_context_specific_observation',
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


def _candidate_selection_key(candidate):
    observation = _dict(_dict(candidate).get('selected_observation'))
    observation_type = observation.get('type')
    return (
        -SERVICE_SEVERITY_ORDER.get(observation.get('severity'), 0),
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
        writer_output = write_story_frame(frame)
        if _dict(writer_output.get('validation')).get('passed') is not True:
            continue
        candidates.append({
            'selected_observation': deepcopy(observation),
            'construction_frame': deepcopy(frame),
            'writer_output': writer_output,
        })
    if not candidates:
        return None
    return sorted(candidates, key=_candidate_selection_key)[0]


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
    context = (
        deepcopy(team_context)
        if isinstance(team_context, dict)
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
    payload.update({
        'state': STATE_STORY_AVAILABLE,
        'story_available': True,
        'selected_observation': candidate.get('selected_observation'),
        'construction_frame': construction_frame,
        'written_story': deepcopy(writer_output.get('written_observation')),
        'writer_output': writer_output,
        'supporting_context': _supporting_context(context, construction_frame),
        'limitations': _combined_limitations(
            payload['limitations'],
            construction_frame.get('limitations'),
            writer_output.get('limitations'),
        ),
    })
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
