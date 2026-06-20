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
    'current relief shape is easy to see',
    'relief shape starts there',
    'changed bullpen mix',
    'bullpen mix has been shifting',
    'the bullpen is under pressure',
    'limited flexibility',
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
    while len(text) > 1 and text[-1] in '.?!' and text[-2] in '.?!':
        text = text[:-1]
    if text[-1] not in '.!?':
        text = f'{text}.'
    return text


def _sentence_text(value: Any) -> str:
    sentence = _sentence(value)
    return sentence or ''


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _count(value: Any) -> int:
    return int(_number(value, 0))


def _pct(value: Any) -> int:
    return round(_number(value, 0) * 100)


def _decimal(value: Any) -> str:
    number = _number(value, 0)
    if number == int(number):
        return str(int(number))
    return f'{number:.1f}'


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


def _variant(
    facts: dict[str, Any],
    selected: dict[str, Any],
    prose_path: str | None,
    options: tuple[str, ...],
) -> str:
    index = _stable_index([
        _team_name(facts),
        (facts.get('team') or {}).get('team_id'),
        selected.get('observation_type'),
        selected.get('observation_id'),
        prose_path,
    ], len(options))
    return options[index]


def _team_inputs(facts: dict[str, Any]) -> dict[str, Any]:
    inputs = facts.get('story_inputs')
    return inputs if isinstance(inputs, dict) else {}


def _available_phrase(available: int, total: int) -> str:
    return f'{available} of {total} relievers {"is" if available == 1 else "are"} available'


def _available_count_phrase(available: int, total: int) -> str:
    return f'{available} of {total} relievers available'


def _identity_public_summary(facts: dict[str, Any]) -> str:
    inputs = _team_inputs(facts)
    capacity = inputs.get('capacity_intelligence') or {}
    identity = capacity.get('bullpen_identity') if isinstance(capacity, dict) else None
    summary = identity.get('identity_summary') if isinstance(identity, dict) else ''
    summary = _clean_text(summary)
    if ':' in summary:
        summary = summary.split(':', 1)[1].strip()
    return _clean_text(summary).rstrip('.?!')


def _identity_stable_shape(summary: str, clean_option_count: int) -> bool:
    lower = _normalize_text(summary)
    if clean_option_count >= 5:
        return True
    return any(
        phrase in lower
        for phrase in (
            'enough trusted relievers',
            'avoid forcing every important inning',
            'more than one',
            'multiple',
            'not forced',
        )
    )


def select_observation_prose_path(facts: dict[str, Any], selected: dict[str, Any]) -> str | None:
    """Expose the deterministic prose path so evidence and consequence can vary with it."""

    return _selected_prose_path(facts, selected)


def polish_selected_observation(
    facts: dict[str, Any],
    selected: dict[str, Any],
    prose_path: str | None,
) -> dict[str, Any]:
    """Apply deterministic editorial sentence variety to the selected observation."""

    if not isinstance(selected, dict) or not selected:
        return selected

    inputs = _team_inputs(facts)
    workload = inputs.get('workload') or {}
    availability = inputs.get('availability') or {}
    season_era = inputs.get('season_era') or {}
    stability = inputs.get('bullpen_stability') or {}
    team = _team_name(facts)
    possessive = _possessive_team(facts)
    names = _pitcher_names(facts, selected)
    subject = _join_names(names, limit=3)
    short_subject = _join_names(names, limit=2) or 'the same group'
    observation_type = selected.get('observation_type')
    polished = {**selected}

    available = _count(availability.get('available'))
    total = _count(availability.get('total'))
    participants = _count(workload.get('participant_count'))
    top_share = _pct(workload.get('top_share'))
    per_arm = _decimal(workload.get('per_arm_pitches'))
    clean_option_count = len(inputs.get('clean_options') or [])
    clean_trust_count = len(inputs.get('clean_trust_options') or [])
    changed = _count(stability.get('new_or_reintroduced_arm_count'))
    era = season_era.get('era')
    era_text = f'{era:.2f}' if isinstance(era, (int, float)) else ''

    evidence = selected.get('text')
    category = selected.get('consequence_category')
    consequence = selected.get('consequence_statement')

    if subject and observation_type == OBSERVATION_WORKLOAD_CONCENTRATION and top_share:
        variants = {
            PROSE_PATH_DEPENDENCY: (
                f'{subject} are the center of {possessive} recent relief workload, taking {top_share}% of the pitches.',
                'heavier_workload_concentration',
                _variant(facts, selected, prose_path, (
                    f'The next tight inning still points back toward {short_subject} before the rest of the bullpen.',
                    f'That makes {short_subject} the first pressure point if the game tightens again.',
                    'The workload shape gives the first group less distance from another leverage pocket.',
                )),
            ),
            PROSE_PATH_ALTERNATIVES: (
                f'{team} still {_team_has_verb(facts)} names behind the front group, but {subject} have taken {top_share}% of recent relief pitches.',
                'heavier_workload_concentration',
                _variant(facts, selected, prose_path, (
                    f'That leaves less room to change the game path once it has already run through {short_subject}.',
                    'The alternatives matter, but the recent workload has already narrowed the first turn.',
                    'The burden is still concentrated enough to make the next pivot important.',
                )),
            ),
            PROSE_PATH_GAME_ROUTE: (
                f'{possessive} close-game route has recently run through {subject}, who have handled {top_share}% of relief pitches.',
                'heavier_workload_concentration',
                _variant(facts, selected, prose_path, (
                    'A close game can still bend back toward the same pocket of relievers.',
                    'The path is playable, but it has been running through a tighter group.',
                    f'The next close inning starts with how much more {short_subject} can absorb.',
                )),
            ),
            PROSE_PATH_WORKLOAD: (
                f'Recent relief work is bunched around {subject}, with {top_share}% of {possessive} pitches landing there.',
                'heavier_workload_concentration',
                _variant(facts, selected, prose_path, (
                    'The bullpen has support pieces, but the workload burden is not evenly shared.',
                    'The shape is less about total arms and more about where the recent innings have landed.',
                    'The staff has options, but the first strain still sits with the same workload pocket.',
                )),
            ),
        }
        evidence, category, consequence = variants.get(prose_path, variants[PROSE_PATH_WORKLOAD])

    elif subject and observation_type == OBSERVATION_RESOURCE_CONSTRAINT and total:
        availability_text = _available_phrase(available, total)
        availability_count_text = _available_count_phrase(available, total)
        variants = {
            PROSE_PATH_DEPENDENCY: (
                f'{subject} matter more in {possessive} current bullpen picture because only {availability_text} tonight.',
                'less_coverage_margin',
                f'The margin gets thin once the game moves past {short_subject}.',
            ),
            PROSE_PATH_ALTERNATIVES: (
                f'{team} {_team_has_verb(facts)} {availability_count_text} tonight, leaving {subject} as the clearest named layer.',
                'less_coverage_margin',
                'One extra close inning can force the staff beyond the available layer quickly.',
            ),
            PROSE_PATH_GAME_ROUTE: (
                f'Only {availability_text} for {team} tonight, with {subject} sitting in the current relief route.',
                'less_coverage_margin',
                'A bullpen-heavy game would test how far that first route can stretch.',
            ),
            PROSE_PATH_AVAILABLE_LAYER: (
                f'{subject} sit in {possessive} current bullpen picture while only {availability_text} tonight.',
                'less_coverage_margin',
                'The usable layer is thin enough that one more leverage pocket matters.',
            ),
        }
        evidence, category, consequence = variants.get(prose_path, variants[PROSE_PATH_AVAILABLE_LAYER])

    elif subject and observation_type == OBSERVATION_FLEXIBILITY and participants and total:
        availability_text = _available_phrase(available, total)
        availability_count_text = _available_count_phrase(available, total)
        variants = {
            PROSE_PATH_DEPENDENCY: (
                f'{subject} lead a {team} group that has spread recent work across {participants} relievers with {availability_count_text}.',
                'more_stable_bullpen_shape',
                _variant(facts, selected, prose_path, (
                    'That gives the late innings more than one route instead of a single hinge.',
                    'The bullpen can move through the game without making one reliever the whole answer.',
                    'The available spread gives the manager more than one way to reach the finish.',
                )),
            ),
            PROSE_PATH_GAME_ROUTE: (
                f'{team} {_team_has_verb(facts)} used {participants} relievers recently and still {_team_has_verb(facts)} {availability_count_text}, with {subject} in the mix.',
                'more_stable_bullpen_shape',
                _variant(facts, selected, prose_path, (
                    'A close game can move through more than one relief lane.',
                    'The staff can choose a second route before the game narrows.',
                    'That keeps a tight game from depending on a single relief lane.',
                )),
            ),
            PROSE_PATH_WORKLOAD: (
                f'Recent {team} bullpen work has reached {participants} relievers while {subject} remain part of an available group of {available}.',
                'more_stable_bullpen_shape',
                _variant(facts, selected, prose_path, (
                    'The workload is broad enough to keep different hands in play.',
                    'That spread keeps the bullpen from turning into a one-lane plan.',
                    'The recent distribution gives the staff more ways to absorb another close inning.',
                )),
            ),
            PROSE_PATH_DEPTH_ROOM: (
                f'{team} {_team_has_verb(facts)} spread recent bullpen work across {participants} relievers and still {_team_has_verb(facts)} {availability_count_text}, led by {subject}.',
                'more_stable_bullpen_shape',
                'That leaves the staff with room to cover a tight inning without forcing one lane.',
            ),
        }
        evidence, category, consequence = variants.get(prose_path, variants[PROSE_PATH_DEPTH_ROOM])

    elif subject and observation_type == OBSERVATION_TRUST_SHAPE and clean_option_count:
        stable = selected.get('consequence_category') == 'more_stable_bullpen_shape'
        if stable:
            variants = {
                PROSE_PATH_LATE_BRIDGE: (
                    f'{subject} give {team} {clean_trust_count} trusted late-inning choices among {clean_option_count} usable relievers.',
                    'more_stable_bullpen_shape',
                    'That keeps the late bridge from depending on one reliever.',
                ),
                PROSE_PATH_DEPENDENCY: (
                    f'{subject} give {team} {clean_trust_count} trusted late-inning choices among {clean_option_count} usable relievers.',
                    'more_stable_bullpen_shape',
                    'That keeps the late bridge from depending on one reliever.',
                ),
                PROSE_PATH_ALTERNATIVES: (
                    f'{team} {_team_has_verb(facts)} {clean_option_count} usable relievers, with {subject} among the trusted late-inning choices.',
                    'more_stable_bullpen_shape',
                    'The staff has more than one landing spot before the game reaches the finish.',
                ),
                PROSE_PATH_DEPTH_ROOM: (
                    f'{subject} sit inside a {clean_option_count}-reliever usable layer for {team}.',
                    'more_stable_bullpen_shape',
                    'That gives the bullpen room to move through the late innings.',
                ),
            }
            evidence, category, consequence = variants.get(prose_path, variants[PROSE_PATH_LATE_BRIDGE])
        else:
            evidence = (
                f'{subject} are carrying the named part of {possessive} relief read while only '
                f'{clean_trust_count} trusted late-inning {_plural(clean_trust_count, "option")} '
                f'{"is" if clean_trust_count == 1 else "are"} available.'
            )
            consequence = (
                f'That leaves fewer comfortable pivots if the game needs one more clean inning before {short_subject}.'
            )
            category = 'reduced_flexibility'

    elif subject and observation_type == OBSERVATION_RUN_PREVENTION_STRESS and era_text:
        variants = {
            PROSE_PATH_DEPENDENCY: (
                f'{possessive} {era_text} bullpen ERA still leans heavily on {subject}, with recent usage at {per_arm} pitches per participating reliever.',
                'heavier_workload_concentration',
                f'The next tight inning still points back toward {short_subject} rather than a wider group.',
            ),
            PROSE_PATH_WORKLOAD: (
                f'{team} {_team_has_verb(facts)} a {era_text} bullpen ERA, but {subject} remain tied to a {per_arm}-pitch recent workload per participating reliever.',
                'heavier_workload_concentration',
                _variant(facts, selected, prose_path, (
                    'The bullpen remains effective, but fewer relievers are sharing the burden.',
                    'The ERA says stable; the workload says the same arms are still doing more of the carrying.',
                    'The run prevention is real, but the workload underneath is not as broad.',
                )),
            ),
            PROSE_PATH_GAME_ROUTE: (
                f'A {era_text} season ERA gives {team} results, but the recent route still runs through {subject} at {per_arm} pitches per participating reliever.',
                'heavier_workload_concentration',
                _variant(facts, selected, prose_path, (
                    'A close game can still ask the same pocket of arms to carry the leverage.',
                    'The results are strong, but the next leverage pocket may still return to the same arms.',
                    'The ERA gives the staff cover, while the workload keeps the pressure on the front group.',
                )),
            ),
            PROSE_PATH_ALTERNATIVES: (
                f'{possessive} run prevention is strong at a {era_text} ERA, but recent usage still averages {per_arm} pitches per participating reliever around {subject}.',
                'heavier_workload_concentration',
                'The first read is good run prevention; the second is how much of it is concentrated in the same arms.',
            ),
            PROSE_PATH_RESULTS_MISMATCH: (
                f'{subject} have kept {possessive} run prevention strong with a {era_text} ERA, but the recent workload is still {per_arm} pitches per participating reliever.',
                'heavier_workload_concentration',
                _variant(facts, selected, prose_path, (
                    'The results look stable, but the workload underneath is narrower than the ERA alone shows.',
                    'The ERA is carrying a steadier public read than the recent workload shape deserves.',
                    'The scoreboard result is clean; the bullpen structure underneath is tighter.',
                )),
            ),
        }
        evidence, category, consequence = variants.get(prose_path, variants[PROSE_PATH_RESULTS_MISMATCH])

    elif subject and observation_type == OBSERVATION_IDENTITY:
        summary = _identity_public_summary(facts)
        stable = _identity_stable_shape(summary, clean_option_count)
        category = 'more_stable_bullpen_shape' if stable else 'reduced_flexibility'
        if stable:
            variants = {
                PROSE_PATH_DEPENDENCY: (
                    f'{subject} give {team} a defined first group with {clean_option_count} usable relievers behind them.',
                    category,
                    f'That gives {team} a front group while still leaving the manager more than one path through the late innings.',
                ),
                PROSE_PATH_ALTERNATIVES: (
                    f'{team} can still turn beyond {subject}, with {clean_option_count} usable relievers available behind the first group.',
                    category,
                    'The late-game path is defined, but it does not end with one lane.',
                ),
                PROSE_PATH_CURRENT_MIX: (
                    f'{subject} sit at the front of {possessive} bullpen, with {clean_option_count} usable relievers behind them because {summary.lower()}.',
                    category,
                    'The bullpen has a defined first group without forcing every close inning through the same lane.',
                ),
            }
        else:
            variants = {
                PROSE_PATH_DEPENDENCY: (
                    f'{subject} give {team} a defined first group, but only {clean_option_count} usable relievers sit behind them.',
                    category,
                    f'The manager has less room once the game moves beyond {short_subject}.',
                ),
                PROSE_PATH_ALTERNATIVES: (
                    f'{team} can turn beyond {subject}, but only {clean_option_count} usable relievers sit behind the first group.',
                    category,
                    'That leaves less room if the game moves away from the first late-game lane.',
                ),
                PROSE_PATH_CURRENT_MIX: (
                    f'{subject} sit at the front of {possessive} bullpen, with {clean_option_count} usable relievers behind them.',
                    category,
                    f'That reduces flexibility if the game moves away from {short_subject}.',
                ),
            }
        evidence, category, consequence = variants.get(prose_path, variants[PROSE_PATH_CURRENT_MIX])

    elif subject and observation_type == OBSERVATION_CHANGE and changed:
        arm_word = _plural(changed, 'reliever')
        variants = {
            PROSE_PATH_DEPENDENCY: (
                f'{team} {_team_has_verb(facts)} {changed} recently reintroduced {arm_word} back into the bullpen, but {subject} still anchor the current late-game route.',
                'more_stable_bullpen_shape',
                _variant(facts, selected, prose_path, (
                    'The mix has changed, but the leverage path still starts with the same names.',
                    'The new piece changes the group, not the first late-game turn.',
                    'The bullpen route is still anchored by the familiar names despite the added arm.',
                )),
            ),
            PROSE_PATH_GAME_ROUTE: (
                f'{team} {_team_has_verb(facts)} {changed} recently reintroduced {arm_word}, while the next close route still runs through {subject}.',
                'more_stable_bullpen_shape',
                _variant(facts, selected, prose_path, (
                    'The return gives the bullpen another piece without changing who anchors the current read.',
                    'The bullpen has a fresh option, but the close-game route still starts in the same place.',
                    'The added arm broadens the mix before it changes the leverage center.',
                )),
            ),
            PROSE_PATH_CURRENT_MIX: (
                f'{team} {_team_has_verb(facts)} {changed} recently reintroduced {arm_word}, but {subject} still anchor the current late-game route.',
                'more_stable_bullpen_shape',
                _variant(facts, selected, prose_path, (
                    'The current mix is different, but the late-game center still comes back to the familiar group.',
                    'The roster movement matters less than who still sits at the center of the leverage route.',
                    'The change adds depth without moving the leverage center away from the same anchors.',
                )),
            ),
        }
        evidence, category, consequence = variants.get(prose_path, variants[PROSE_PATH_CURRENT_MIX])

    polished['text'] = _sentence_text(evidence)
    polished['consequence_category'] = category
    polished['consequence_statement'] = _sentence_text(consequence)
    polish_meta = dict(polished.get('editorial_polish') or {})
    polish_meta.update({
        'capability': 'story_editorial_polish_p0',
        'deterministic': True,
        'prose_path': prose_path,
        'evidence_structure_varied': polished['text'] != selected.get('text'),
        'consequence_structure_varied': polished['consequence_statement'] != selected.get('consequence_statement'),
    })
    polished['editorial_polish'] = polish_meta
    return polished


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
            return _sentence(f'{team} {_team_has_verb(facts)} fewer alternatives if the game moves past the first group')
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
        return _sentence(f'{team} still {_team_has_verb(facts)} multiple ways to cover a close game')

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
                f'{team} {_team_has_verb(facts)} room to move through the late innings'
                if stable else f'{team} {_team_has_verb(facts)} less room behind the trusted late plan'
            )
        return _sentence(
            f'{possessive} late bridge has multiple landing spots'
            if stable else f'{possessive} late bridge is narrow tonight'
        )

    if observation_type == OBSERVATION_RUN_PREVENTION_STRESS:
        if prose_path == PROSE_PATH_DEPENDENCY and subject:
            return _sentence(f'{subject} {_names_verb(names, "is", "are")} carrying more than the ERA shows')
        if prose_path == PROSE_PATH_WORKLOAD:
            return _sentence(f'{team} {_team_has_verb(facts)} good run prevention and a tight workload pocket')
        if prose_path == PROSE_PATH_GAME_ROUTE:
            return _sentence(f'{possessive} next tight inning may find the same relief pocket')
        if prose_path == PROSE_PATH_ALTERNATIVES:
            return _sentence(f'{team} {_team_has_verb(facts)} strong results with less room behind the first group')
        return _sentence(f'{possessive} ERA is strong, but the workload is tighter')

    if observation_type == OBSERVATION_IDENTITY:
        if prose_path == PROSE_PATH_DEPENDENCY and subject:
            return _sentence(f'{subject} define {possessive} first bullpen group')
        if prose_path == PROSE_PATH_ALTERNATIVES and subject:
            return _sentence(f'{team} has options beyond {subject}, but the bullpen path starts with that first group')
        return _sentence(f'{possessive} bullpen is organized around a clear first group')

    if observation_type == OBSERVATION_CHANGE:
        if prose_path == PROSE_PATH_DEPENDENCY and subject:
            return _sentence(f'{subject} still anchor {possessive} bullpen leverage route after the mix changed')
        if prose_path == PROSE_PATH_GAME_ROUTE and subject:
            return _sentence(f'{possessive} next close route still runs through {subject}')
        return _sentence(f'{possessive} bullpen mix changed without moving the leverage center')

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
                f'{team} {_team_has_verb(facts)} fewer bullpen alternatives if the game moves past {subject}'
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
                    f'{team} {_team_has_verb(facts)} room to move through the late innings without forcing one lane'
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
                f'{team} {_team_has_verb(facts)} fewer trusted pivots if the game needs one more clean inning'
            )
        if prose_path == PROSE_PATH_DEPTH_ROOM:
            return _sentence(
                f'{team} {_team_has_verb(facts)} less room behind the trusted late plan than the roster sheet first suggests'
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
                f'{team} {_team_has_verb(facts)} good run prevention and a workload still concentrated around the same relief pocket'
            )
        if prose_path == PROSE_PATH_GAME_ROUTE and subject:
            return _sentence(
                f'If tonight gets tight, {_possessive_team(facts)} strong ERA may still have to pass through {subject}'
            )
        if prose_path == PROSE_PATH_ALTERNATIVES and subject:
            return _sentence(
                f'{team} {_team_has_verb(facts)} strong results, but the workload leaves less room behind {subject}'
            )
        return _sentence(
            f'{_possessive_team(facts)} run prevention has held up, but the workload is tighter than the ERA alone shows'
        )

    if observation_type == OBSERVATION_IDENTITY:
        if prose_path == PROSE_PATH_DEPENDENCY and subject:
            return _sentence(
                f'{subject} sit at the front of {_possessive_team(facts)} bullpen plan'
            )
        if prose_path == PROSE_PATH_ALTERNATIVES and subject:
            return _sentence(
                f'{team} can still turn beyond {subject}, but the bullpen path starts with that first group'
            )
        return _sentence(
            f'{_possessive_team(facts)} bullpen is organized around {count_text} named {name_text}'
        )

    if observation_type == OBSERVATION_CHANGE:
        if prose_path == PROSE_PATH_DEPENDENCY and subject:
            return _sentence(
                f'{subject} still anchor {_possessive_team(facts)} bullpen leverage route after the mix changed'
            )
        if prose_path == PROSE_PATH_GAME_ROUTE and subject:
            return _sentence(
                f'The next close route for {team} still runs through {subject} even after the mix changed'
            )
        return _sentence(
            f'{_possessive_team(facts)} bullpen mix has changed, but the current late-game route still comes back to {count_text} {name_text}'
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
    'polish_selected_observation',
    'select_observation_prose_path',
    'validate_observation_voice',
]
