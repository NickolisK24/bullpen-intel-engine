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

PROSE_PATH_WORKLOAD = 'workload_concentration'
PROSE_PATH_DEPENDENCY = 'named_dependency'
PROSE_PATH_RESULTS_MISMATCH = 'results_mismatch'
PROSE_PATH_ALTERNATIVES = 'alternatives_short'
PROSE_PATH_GAME_ROUTE = 'game_route'
PROSE_PATH_DEPTH_ROOM = 'depth_room'
PROSE_PATH_LATE_BRIDGE = 'late_bridge'
PROSE_PATH_CURRENT_MIX = 'current_mix'
PROSE_PATH_AVAILABLE_LAYER = 'available_layer'

PROSE_PATHS_BY_OBSERVATION = {
    OBSERVATION_WORKLOAD_CONCENTRATION: (
        PROSE_PATH_WORKLOAD,
        PROSE_PATH_DEPENDENCY,
        PROSE_PATH_ALTERNATIVES,
        PROSE_PATH_GAME_ROUTE,
    ),
    OBSERVATION_RESOURCE_CONSTRAINT: (
        PROSE_PATH_AVAILABLE_LAYER,
        PROSE_PATH_DEPENDENCY,
        PROSE_PATH_ALTERNATIVES,
        PROSE_PATH_GAME_ROUTE,
    ),
    OBSERVATION_FLEXIBILITY: (
        PROSE_PATH_DEPTH_ROOM,
        PROSE_PATH_DEPENDENCY,
        PROSE_PATH_GAME_ROUTE,
        PROSE_PATH_WORKLOAD,
    ),
    OBSERVATION_TRUST_SHAPE: (
        PROSE_PATH_LATE_BRIDGE,
        PROSE_PATH_DEPENDENCY,
        PROSE_PATH_ALTERNATIVES,
        PROSE_PATH_DEPTH_ROOM,
    ),
    OBSERVATION_RUN_PREVENTION_STRESS: (
        PROSE_PATH_RESULTS_MISMATCH,
        PROSE_PATH_DEPENDENCY,
        PROSE_PATH_WORKLOAD,
        PROSE_PATH_GAME_ROUTE,
        PROSE_PATH_ALTERNATIVES,
    ),
    OBSERVATION_IDENTITY: (
        PROSE_PATH_CURRENT_MIX,
        PROSE_PATH_DEPENDENCY,
        PROSE_PATH_ALTERNATIVES,
    ),
    OBSERVATION_CHANGE: (
        PROSE_PATH_CURRENT_MIX,
        PROSE_PATH_DEPENDENCY,
        PROSE_PATH_GAME_ROUTE,
    ),
}

THROAT_CLEARING_CLOSERS = (
    'there are still roster questions around the edges',
    'usage provides the strongest signal here',
    'the workload picture is clearer than the roster picture',
    'the read is strongest on recent usage',
)

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
    'story_prose_detemplating_v1',
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
    'active capacity',
    'trusted-group breadth',
    'clean options',
    'coverage safety',
    'resource health',
    'bullpen identity',
    'trust hierarchy',
    'resource pool',
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


def _join_names(names: list[str], limit: int = 2) -> str:
    cleaned: list[str] = []
    for name in names:
        text = _clean_text(name)
        if text and text not in cleaned:
            cleaned.append(text)
    names = cleaned[:limit]
    if not names:
        return ''
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f'{names[0]} and {names[1]}'
    return f"{', '.join(names[:-1])}, and {names[-1]}"


def _names_verb(names: list[str], singular: str, plural: str) -> str:
    return singular if len(names) == 1 else plural


def _stable_index(parts: list[Any], size: int) -> int:
    if size <= 0:
        return 0
    text = '|'.join(_clean_text(part) for part in parts if _clean_text(part))
    if not text:
        return 0
    return sum((idx + 1) * ord(char) for idx, char in enumerate(text)) % size


def observation_prose_paths(observation_type: str | None) -> tuple[str, ...]:
    """Return deterministic public prose pathways supported by an observation type."""

    return PROSE_PATHS_BY_OBSERVATION.get(observation_type, ())


def _selected_prose_path(facts: dict[str, Any], selected: dict[str, Any]) -> str | None:
    observation_type = selected.get('observation_type')
    paths = observation_prose_paths(observation_type)
    if not paths:
        return None
    forced = _clean_text(facts.get('prose_path') or facts.get('forced_prose_path'))
    if forced in paths:
        return forced
    team = facts.get('team') or {}
    index = _stable_index([
        observation_type,
        selected.get('observation_id'),
        selected.get('text'),
        team.get('team_id'),
        team.get('team_name'),
        facts.get('rule_key'),
        facts.get('lead_dimension'),
    ], len(paths))
    return paths[index]


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


def _headline(facts: dict[str, Any], selected: dict[str, Any], names: list[str], prose_path: str | None) -> str | None:
    observation_type = selected.get('observation_type')
    team = _team_name(facts)
    subject = _join_names(names)
    possessive = _possessive_team(facts)

    if observation_type == OBSERVATION_WORKLOAD_CONCENTRATION:
        if prose_path == PROSE_PATH_DEPENDENCY and subject:
            return _sentence(f'{subject} {_names_verb(names, "is", "are")} becoming {possessive} relief route')
        if prose_path == PROSE_PATH_ALTERNATIVES:
            return _sentence(f'{team} may need answers behind the first relief group')
        if prose_path == PROSE_PATH_GAME_ROUTE:
            return _sentence(f'Tonight could send {team} back through the same relief pocket')
        return _sentence(f'{possessive} bullpen work is bunched around the same arms')

    if observation_type == OBSERVATION_RESOURCE_CONSTRAINT:
        if prose_path == PROSE_PATH_DEPENDENCY and subject:
            return _sentence(f'{subject} matter more with fewer relief pivots available')
        if prose_path == PROSE_PATH_ALTERNATIVES:
            return _sentence(f'{team} has fewer alternatives if the game moves past the first group')
        if prose_path == PROSE_PATH_GAME_ROUTE:
            return _sentence(f'A bullpen-heavy game could press {team} past the first available group')
        return _sentence(f'{possessive} usable bullpen layer is thin')

    if observation_type == OBSERVATION_FLEXIBILITY:
        if prose_path == PROSE_PATH_DEPENDENCY and subject:
            return _sentence(f'{subject} give {team} more than one late path')
        if prose_path == PROSE_PATH_GAME_ROUTE:
            return _sentence(f'{team} can cover a close game through more than one route')
        if prose_path == PROSE_PATH_WORKLOAD:
            return _sentence(f'{team} is not boxed into one relief lane')
        return _sentence(f'{team} still has multiple ways to cover a close game')

    if observation_type == OBSERVATION_TRUST_SHAPE:
        stable = selected.get('consequence_category') == 'more_stable_bullpen_shape'
        if prose_path == PROSE_PATH_DEPENDENCY and subject:
            return _sentence(f'{subject} give {team} the shape of the late bridge')
        if prose_path == PROSE_PATH_ALTERNATIVES:
            return _sentence(
                f'{possessive} late bridge has more than one landing spot'
                if stable else f'{possessive} late bridge narrows behind the first group'
            )
        if prose_path == PROSE_PATH_DEPTH_ROOM:
            return _sentence(
                f'{team} has room to move through the late innings'
                if stable else f'{team} has less room behind the trusted late plan'
            )
        return _sentence(
            f'{possessive} late bridge has multiple landing spots'
            if stable else f'{possessive} late bridge is narrow tonight'
        )

    if observation_type == OBSERVATION_RUN_PREVENTION_STRESS:
        if prose_path == PROSE_PATH_DEPENDENCY and subject:
            return _sentence(f'{subject} {_names_verb(names, "is", "are")} carrying more than the ERA shows')
        if prose_path == PROSE_PATH_WORKLOAD:
            return _sentence(f'{team} has good run prevention and a tight workload pocket')
        if prose_path == PROSE_PATH_GAME_ROUTE:
            return _sentence(f'{possessive} next tight inning may find the same relief pocket')
        if prose_path == PROSE_PATH_ALTERNATIVES:
            return _sentence(f'{team} has strong results with less room behind the first group')
        return _sentence(f'{possessive} ERA is strong, but the workload is tighter')

    if observation_type == OBSERVATION_IDENTITY:
        if prose_path == PROSE_PATH_DEPENDENCY and subject:
            return _sentence(f'{possessive} relief shape starts with {subject}')
        if prose_path == PROSE_PATH_ALTERNATIVES and subject:
            return _sentence(f'{team} can still turn beyond {subject}, but the relief shape starts there')
        return _sentence(f'{possessive} current relief shape is easy to see')

    if observation_type == OBSERVATION_CHANGE:
        if prose_path == PROSE_PATH_DEPENDENCY and subject:
            return _sentence(f'{subject} {_names_verb(names, "is", "are")} holding together {possessive} changed bullpen mix')
        if prose_path == PROSE_PATH_GAME_ROUTE and subject:
            return _sentence(f'{possessive} next close route still runs through {subject}')
        return _sentence(f'{possessive} bullpen mix has shifted around familiar names')

    return None


def _voice_frame(facts: dict[str, Any], selected: dict[str, Any], names: list[str], prose_path: str | None) -> str | None:
    observation_type = selected.get('observation_type')
    team = _team_name(facts)
    count = len(names)
    count_text = _count_word(count)
    arm_text = _plural(count, 'arm')
    name_text = _plural(count, 'name')
    subject = _join_names(names)

    if observation_type == OBSERVATION_WORKLOAD_CONCENTRATION:
        if prose_path == PROSE_PATH_DEPENDENCY and subject:
            return _sentence(
                f'{subject} {_names_verb(names, "is", "are")} the dependency point in '
                f'{_possessive_team(facts)} recent relief workload'
            )
        if prose_path == PROSE_PATH_ALTERNATIVES and subject:
            return _sentence(
                f'{team} still {_team_has_verb(facts)} alternatives, but the workload leaves less room behind {subject}'
            )
        if prose_path == PROSE_PATH_GAME_ROUTE and subject:
            return _sentence(
                f'If tonight gets tight, {_possessive_team(facts)} bullpen route could run back through {subject}'
            )
        return _sentence(
            f'{team} {_team_is_verb(facts)} carrying a narrow recent workload, '
            f'with the relief pitches clustered around {count_text} {arm_text}'
        )

    if observation_type == OBSERVATION_RESOURCE_CONSTRAINT:
        if prose_path == PROSE_PATH_DEPENDENCY and subject:
            return _sentence(
                f'{subject} matter more because {team} does not have many relief pivots available'
            )
        if prose_path == PROSE_PATH_ALTERNATIVES and subject:
            return _sentence(
                f'{team} has fewer bullpen alternatives if the game moves past {subject}'
            )
        if prose_path == PROSE_PATH_GAME_ROUTE:
            return _sentence(
                f'A bullpen-heavy game could push {team} past the first available group quickly'
            )
        return _sentence(
            f'{_possessive_team(facts)} usable bullpen layer is thin enough that each available arm matters'
        )

    if observation_type == OBSERVATION_FLEXIBILITY:
        if prose_path == PROSE_PATH_DEPENDENCY and subject:
            return _sentence(
                f'{subject} give {team} multiple relief paths instead of a single late-game hinge'
            )
        if prose_path == PROSE_PATH_GAME_ROUTE:
            return _sentence(
                f'A close game can still take more than one route through {_possessive_team(facts)} bullpen'
            )
        if prose_path == PROSE_PATH_WORKLOAD:
            return _sentence(
                f'The work is spread enough for {team} to keep different relief hands in play'
            )
        return _sentence(
            f'{team} still {_team_has_verb(facts)} enough available depth to avoid one narrow relief route'
        )

    if observation_type == OBSERVATION_TRUST_SHAPE:
        if selected.get('consequence_category') == 'more_stable_bullpen_shape':
            if prose_path == PROSE_PATH_DEPENDENCY and subject:
                return _sentence(
                    f'{subject} give {team} more than one trusted late-inning choice'
                )
            if prose_path == PROSE_PATH_ALTERNATIVES:
                return _sentence(
                    f'{_possessive_team(facts)} late plan is not boxed into one trusted arm'
                )
            if prose_path == PROSE_PATH_DEPTH_ROOM:
                return _sentence(
                    f'{team} has room to move through the late innings without forcing one lane'
                )
            return _sentence(
                f'{team} still {_team_has_verb(facts)} more than one bridge into the late innings'
            )
        if prose_path == PROSE_PATH_DEPENDENCY and subject:
            return _sentence(
                f'{subject} {_names_verb(names, "is", "are")} the hinge of {_possessive_team(facts)} late-inning bridge'
            )
        if prose_path == PROSE_PATH_ALTERNATIVES:
            return _sentence(
                f'{team} has fewer trusted pivots if the game needs one more clean inning'
            )
        if prose_path == PROSE_PATH_DEPTH_ROOM:
            return _sentence(
                f'{team} has less room behind the trusted late plan than the roster sheet first suggests'
            )
        return _sentence(
            f'{_possessive_team(facts)} bridge into the late innings is narrower than the roster sheet first suggests'
        )

    if observation_type == OBSERVATION_RUN_PREVENTION_STRESS:
        if prose_path == PROSE_PATH_DEPENDENCY and subject:
            return _sentence(
                f'{subject} {_names_verb(names, "is", "are")} carrying more of '
                f'{_possessive_team(facts)} strong run-prevention line than the ERA first suggests'
            )
        if prose_path == PROSE_PATH_WORKLOAD:
            return _sentence(
                f'{team} has good run prevention and a workload still concentrated around the same relief pocket'
            )
        if prose_path == PROSE_PATH_GAME_ROUTE and subject:
            return _sentence(
                f'If tonight gets tight, {_possessive_team(facts)} strong ERA may still have to pass through {subject}'
            )
        if prose_path == PROSE_PATH_ALTERNATIVES and subject:
            return _sentence(
                f'{team} has strong results, but the workload leaves less room behind {subject}'
            )
        return _sentence(
            f'{_possessive_team(facts)} run prevention has held up, but the workload is tighter than the ERA alone shows'
        )

    if observation_type == OBSERVATION_IDENTITY:
        if prose_path == PROSE_PATH_DEPENDENCY and subject:
            return _sentence(
                f'{subject} sit at the front of {_possessive_team(facts)} current relief shape'
            )
        if prose_path == PROSE_PATH_ALTERNATIVES and subject:
            return _sentence(
                f'{team} can still turn beyond {subject}, but the current relief shape starts there'
            )
        return _sentence(
            f'{_possessive_team(facts)} current relief shape is visible through {count_text} named {name_text}'
        )

    if observation_type == OBSERVATION_CHANGE:
        if prose_path == PROSE_PATH_DEPENDENCY and subject:
            return _sentence(
                f'{subject} {_names_verb(names, "is", "are")} holding together {_possessive_team(facts)} changed bullpen mix'
            )
        if prose_path == PROSE_PATH_GAME_ROUTE and subject:
            return _sentence(
                f'The next close route for {team} still runs through {subject} even after the mix changed'
            )
        return _sentence(
            f'{_possessive_team(facts)} bullpen mix has changed, but the current story still comes back to {count_text} {name_text}'
        )

    return None


def _frame_support_groups(observation_type: str | None) -> tuple[tuple[str, ...], ...]:
    return {
        OBSERVATION_WORKLOAD_CONCENTRATION: (
            ('spreading', 'spread', 'leaning', 'collected', 'clustered', 'dependency', 'alternatives', 'route'),
            ('bullpen', 'workload', 'relief pitches', 'relief'),
        ),
        OBSERVATION_RESOURCE_CONSTRAINT: (
            ('thinner', 'thin', 'available', 'coverage', 'margin', 'pivots', 'alternatives', 'fewer'),
            ('bullpen', 'reliever', 'relief'),
        ),
        OBSERVATION_FLEXIBILITY: (
            ('path', 'paths', 'ways', 'room', 'route', 'spread'),
            ('close game', 'game', 'inning', 'relief'),
        ),
        OBSERVATION_TRUST_SHAPE: (
            ('bridge', 'late innings', 'comfortable', 'trusted', 'pivots', 'lane'),
            ('late', 'inning', 'finish', 'game'),
        ),
        OBSERVATION_RUN_PREVENTION_STRESS: (
            ('run prevention', 'results', 'era'),
            ('workload', 'usage', 'underneath', 'carrying', 'relief pocket', 'pass through'),
        ),
        OBSERVATION_IDENTITY: (
            ('shape', 'visible', 'named', 'front', 'starts'),
            ('bullpen', 'arms', 'names', 'relief'),
        ),
        OBSERVATION_CHANGE: (
            ('changed', 'moved', 'mix'),
            ('current', 'story', 'names', 'route', 'holding', 'bullpen'),
        ),
    }.get(observation_type, ())


def _frame_supported(frame: str, observation_type: str | None) -> bool:
    groups = _frame_support_groups(observation_type)
    lower = _normalize_text(frame)
    return bool(groups) and all(any(marker in lower for marker in group) for group in groups)


def _generic_frame_hits(frame: str) -> list[str]:
    lower = _normalize_text(frame)
    return [phrase for phrase in GENERIC_FRAME_DENYLIST if phrase in lower]


def _throat_clearing_hits(sentence: str) -> list[str]:
    lower = _normalize_text(sentence)
    return [phrase for phrase in THROAT_CLEARING_CLOSERS if phrase in lower]


def _public_language_safe(*sentences: str | None) -> bool:
    lower = _normalize_text(' '.join(_clean_text(sentence) for sentence in sentences if sentence))
    return not any(term in lower for term in INTERNAL_PUBLIC_UNSAFE_TERMS)


def _has_pitcher_name(text: str, names: list[str]) -> bool:
    lower = _normalize_text(text)
    return any(_normalize_text(name) in lower for name in names if _normalize_text(name))


def validate_observation_voice(voice: dict[str, Any]) -> dict[str, Any]:
    """Validate that a human frame is grounded in the selected observation."""

    headline = _clean_text(voice.get('headline'))
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
    closing_hits = _throat_clearing_hits(consequence)
    checks = {
        'human_frame_present': bool(frame),
        'human_frame_supported': _frame_supported(frame, voice.get('observation_type')),
        'generic_frame_absent': not generic_hits,
        'evidence_sentence_present': bool(evidence),
        'selected_observation_referenced': bool(selected_text and evidence == selected_text),
        'pitcher_name_present': _has_pitcher_name(evidence, names),
        'measurable_fact_present': bool(_MEASURABLE_FACT_RE.search(evidence)),
        'consequence_sentence_present': bool(consequence),
        'consequence_sentence_informational': bool(consequence) and not closing_hits,
        'public_language_safe': _public_language_safe(headline, frame, evidence, consequence),
    }
    fail_reasons = [key for key, passed in checks.items() if not passed]
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'passed': not fail_reasons,
        'checks': checks,
        'fail_reasons': fail_reasons,
        'generic_frame_hits': generic_hits,
        'closing_language_hits': closing_hits,
    }


def build_observation_voice(facts: dict[str, Any]) -> dict[str, Any]:
    """Build the public frame, evidence sentence, and consequence sentence."""

    selected = _selected_observation(facts)
    names = _pitcher_names(facts, selected)
    prose_path = _selected_prose_path(facts, selected)
    evidence_sentence = _sentence(selected.get('text') or facts.get('evidence_statement'))
    consequence_sentence = _sentence(
        selected.get('consequence_statement') or facts.get('consequence_statement')
    )
    headline = _headline(facts, selected, names, prose_path)
    observation_type = selected.get('observation_type')
    voice = {
        'capability': CAPABILITY,
        'version': VERSION,
        'applied': False,
        'observation_type': observation_type,
        'selected_observation_id': selected.get('observation_id'),
        'selected_observation_text': _clean_text(selected.get('text')),
        'prose_path': prose_path,
        'headline': headline,
        'headline_shape': f'{observation_type}:{prose_path}' if observation_type and prose_path else None,
        'body_shape': f'{observation_type}:{prose_path}' if observation_type and prose_path else None,
        'closing_shape': selected.get('consequence_category') or facts.get('consequence_category'),
        'human_frame': _voice_frame(facts, selected, names, prose_path),
        'evidence_sentence': evidence_sentence,
        'consequence_sentence': consequence_sentence,
        'pitcher_names': names,
        'support': {
            'source': 'selected_observation',
            'frame_requires_selected_observation': True,
            'evidence_requires_selected_observation_text': True,
            'prose_path_deterministic': True,
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
    'INTERNAL_PUBLIC_UNSAFE_TERMS',
    'PROSE_PATHS_BY_OBSERVATION',
    'THROAT_CLEARING_CLOSERS',
    'build_observation_voice',
    'observation_prose_paths',
    'validate_observation_voice',
]
