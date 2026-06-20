"""Grounded voice framing for selected story observations."""

from __future__ import annotations

import re
from typing import Any

from services.story_observation_discovery import (
    OBSERVATION_CHANGE,
    OBSERVATION_FLEXIBILITY,
    OBSERVATION_IDENTITY,
    OBSERVATION_RESOURCE_CONSTRAINT,
    OBSERVATION_RUN_PREVENTION_STRESS,
    OBSERVATION_TRUST_SHAPE,
    OBSERVATION_WORKLOAD_CONCENTRATION,
)


CAPABILITY = 'observation_voice_layer_v1'
VERSION = '2026-06-19'

GENERIC_FRAME_DENYLIST = (
    'the bullpen picture remains stable',
    'bullpen picture remains stable',
    'the back end gives the night structure',
    'gives the night structure',
    'the shape is less about one arm and more about the paths still open',
    'what happened on the mound is the cleanest part of the picture',
    'cleanest part of the picture',
    'shape of the bullpen remains stable',
    'shape of the picture',
    'steadies the picture',
    'tells the story',
    'remains part of the equation',
    'still sits in a workable spot',
)

INTERNAL_PUBLIC_UNSAFE_TERMS = (
    'observation_voice_layer_v1',
    'observation_discovery_engine_v1',
    'selected_observation',
    'story_observation',
    'story_voice',
    'ranking_applied',
    'selection_made',
    'workload_concentration',
    'resource_constraint',
    'run_prevention_stress',
    'trust_shape',
    'capability',
)

_MEASURABLE_FACT_RE = re.compile(
    r'(\b\d+(?:\.\d+)?%?\b|\b\d+\s+of\s+\d+\b|\btop\s+\d+\b|\b\d+(?:\.\d+)?\s+season ERA\b)',
    re.IGNORECASE,
)

_COUNT_WORDS = {
    0: 'no',
    1: 'one',
    2: 'two',
    3: 'three',
    4: 'four',
    5: 'five',
    6: 'six',
    7: 'seven',
    8: 'eight',
    9: 'nine',
    10: 'ten',
}


def _clean_text(value: Any) -> str:
    return ' '.join(str(value or '').strip().split())


def _normalize_text(value: Any) -> str:
    return _clean_text(value).lower()


def _sentence(value: Any) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    if text[-1] not in '.!?':
        text = f'{text}.'
    return text


def _team_name(facts: dict[str, Any]) -> str:
    team = facts.get('team') or {}
    return _clean_text(team.get('team_name')) or 'This bullpen'


def _possessive_team(facts: dict[str, Any]) -> str:
    name = _team_name(facts)
    return f"{name}'" if name.endswith('s') else f"{name}'s"


def _team_is_verb(facts: dict[str, Any]) -> str:
    return 'are' if _team_name(facts).endswith(('s', 'x')) else 'is'


def _team_has_verb(facts: dict[str, Any]) -> str:
    return 'have' if _team_name(facts).endswith(('s', 'x')) else 'has'


def _team_pronoun(facts: dict[str, Any]) -> str:
    return 'they' if _team_name(facts).endswith(('s', 'x')) else 'it'


def _team_pronoun_is_verb(facts: dict[str, Any]) -> str:
    return 'are' if _team_pronoun(facts) == 'they' else 'is'


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return singular if count == 1 else (plural or f'{singular}s')


def _count_word(count: int) -> str:
    return _COUNT_WORDS.get(count, str(count))


def _pitcher_names(facts: dict[str, Any], selected: dict[str, Any]) -> list[str]:
    ordered: list[str] = []
    for source in (
        selected.get('pitcher_names'),
        facts.get('named_pitchers'),
    ):
        for name in source or []:
            text = _clean_text(name)
            if text and text not in ordered:
                ordered.append(text)
    return ordered


def _selected_observation(facts: dict[str, Any]) -> dict[str, Any]:
    selected = facts.get('selected_observation') or {}
    return selected if isinstance(selected, dict) else {}


def _voice_frame(facts: dict[str, Any], selected: dict[str, Any], names: list[str]) -> str | None:
    observation_type = selected.get('observation_type')
    team = _team_name(facts)
    count = len(names)
    count_text = _count_word(count)
    arm_text = _plural(count, 'arm')
    name_text = _plural(count, 'name')

    if observation_type == OBSERVATION_WORKLOAD_CONCENTRATION:
        return _sentence(
            f'{team} {_team_is_verb(facts)} not really spreading bullpen work right now; '
            f'{_team_pronoun(facts)} {_team_pronoun_is_verb(facts)} leaning on {count_text} {arm_text}'
        )

    if observation_type == OBSERVATION_RESOURCE_CONSTRAINT:
        return _sentence(
            f'{team} {_team_is_verb(facts)} not just managing usage; '
            f'{_team_pronoun(facts)} {_team_pronoun_is_verb(facts)} managing a thinner bullpen pool'
        )

    if observation_type == OBSERVATION_FLEXIBILITY:
        return _sentence(
            f'{team} still {_team_has_verb(facts)} more than one path through a close game'
        )

    if observation_type == OBSERVATION_TRUST_SHAPE:
        if selected.get('consequence_category') == 'more_stable_bullpen_shape':
            return _sentence(
                f'{team} still {_team_has_verb(facts)} more than one bridge into the late innings'
            )
        return _sentence(
            f'{_possessive_team(facts)} bridge into the late innings is narrower than the roster sheet first suggests'
        )

    if observation_type == OBSERVATION_RUN_PREVENTION_STRESS:
        return _sentence(
            f'{_possessive_team(facts)} run prevention is strong, but the workload underneath still matters'
        )

    if observation_type == OBSERVATION_IDENTITY:
        return _sentence(
            f'{_possessive_team(facts)} bullpen shape is visible through {count_text} named {name_text}'
        )

    if observation_type == OBSERVATION_CHANGE:
        return _sentence(
            f'{_possessive_team(facts)} bullpen mix has changed, but the current story still comes back to {count_text} {name_text}'
        )

    return None


def _frame_support_groups(observation_type: str | None) -> tuple[tuple[str, ...], ...]:
    return {
        OBSERVATION_WORKLOAD_CONCENTRATION: (
            ('spreading', 'spread', 'leaning', 'collected', 'clustered'),
            ('bullpen work', 'workload', 'relief pitches'),
        ),
        OBSERVATION_RESOURCE_CONSTRAINT: (
            ('thinner', 'available', 'coverage', 'pool', 'margin'),
            ('bullpen', 'reliever', 'relief'),
        ),
        OBSERVATION_FLEXIBILITY: (
            ('path', 'paths', 'ways', 'room'),
            ('close game', 'game', 'inning'),
        ),
        OBSERVATION_TRUST_SHAPE: (
            ('bridge', 'late innings', 'comfortable', 'trusted'),
            ('late', 'inning', 'finish', 'game'),
        ),
        OBSERVATION_RUN_PREVENTION_STRESS: (
            ('run prevention', 'results', 'era'),
            ('workload', 'usage', 'underneath'),
        ),
        OBSERVATION_IDENTITY: (
            ('shape', 'visible', 'named'),
            ('bullpen', 'arms', 'names'),
        ),
        OBSERVATION_CHANGE: (
            ('changed', 'moved', 'mix'),
            ('current', 'story', 'names'),
        ),
    }.get(observation_type, ())


def _frame_supported(frame: str, observation_type: str | None) -> bool:
    groups = _frame_support_groups(observation_type)
    lower = _normalize_text(frame)
    return bool(groups) and all(any(marker in lower for marker in group) for group in groups)


def _generic_frame_hits(frame: str) -> list[str]:
    lower = _normalize_text(frame)
    return [phrase for phrase in GENERIC_FRAME_DENYLIST if phrase in lower]


def _public_language_safe(*sentences: str | None) -> bool:
    lower = _normalize_text(' '.join(_clean_text(sentence) for sentence in sentences if sentence))
    return not any(term in lower for term in INTERNAL_PUBLIC_UNSAFE_TERMS)


def _has_pitcher_name(text: str, names: list[str]) -> bool:
    lower = _normalize_text(text)
    return any(_normalize_text(name) in lower for name in names if _normalize_text(name))


def validate_observation_voice(voice: dict[str, Any]) -> dict[str, Any]:
    """Validate that a human frame is grounded in the selected observation."""

    selected_text = _clean_text(voice.get('selected_observation_text'))
    frame = _clean_text(voice.get('human_frame'))
    evidence = _clean_text(voice.get('evidence_sentence'))
    consequence = _clean_text(voice.get('consequence_sentence'))
    names = [
        _clean_text(name)
        for name in voice.get('pitcher_names') or []
        if _clean_text(name)
    ]
    generic_hits = _generic_frame_hits(frame)
    checks = {
        'human_frame_present': bool(frame),
        'human_frame_supported': _frame_supported(frame, voice.get('observation_type')),
        'generic_frame_absent': not generic_hits,
        'evidence_sentence_present': bool(evidence),
        'selected_observation_referenced': bool(selected_text and evidence == selected_text),
        'pitcher_name_present': _has_pitcher_name(evidence, names),
        'measurable_fact_present': bool(_MEASURABLE_FACT_RE.search(evidence)),
        'consequence_sentence_present': bool(consequence),
        'public_language_safe': _public_language_safe(frame, evidence, consequence),
    }
    fail_reasons = [key for key, passed in checks.items() if not passed]
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'passed': not fail_reasons,
        'checks': checks,
        'fail_reasons': fail_reasons,
        'generic_frame_hits': generic_hits,
    }


def build_observation_voice(facts: dict[str, Any]) -> dict[str, Any]:
    """Build the public frame, evidence sentence, and consequence sentence."""

    selected = _selected_observation(facts)
    names = _pitcher_names(facts, selected)
    evidence_sentence = _sentence(selected.get('text') or facts.get('evidence_statement'))
    consequence_sentence = _sentence(
        selected.get('consequence_statement') or facts.get('consequence_statement')
    )
    voice = {
        'capability': CAPABILITY,
        'version': VERSION,
        'applied': False,
        'observation_type': selected.get('observation_type'),
        'selected_observation_id': selected.get('observation_id'),
        'selected_observation_text': _clean_text(selected.get('text')),
        'human_frame': _voice_frame(facts, selected, names),
        'evidence_sentence': evidence_sentence,
        'consequence_sentence': consequence_sentence,
        'pitcher_names': names,
        'support': {
            'source': 'selected_observation',
            'frame_requires_selected_observation': True,
            'evidence_requires_selected_observation_text': True,
        },
    }
    validation = validate_observation_voice(voice)
    voice['validation'] = validation
    voice['applied'] = validation['passed']
    return voice


__all__ = [
    'CAPABILITY',
    'VERSION',
    'GENERIC_FRAME_DENYLIST',
    'build_observation_voice',
    'validate_observation_voice',
]
