"""Narrative renderer for normalized team story facts."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable


CAPABILITY = 'team_story_narrative_renderer_v3'
VERSION = '2026-06-18.v3'

ARCHETYPE_WORKLOAD_CONCENTRATION = 'workload_concentration'
ARCHETYPE_THIN_TRUSTED_GROUP = 'thin_trusted_group'
ARCHETYPE_CAPACITY_CONSTRAINT = 'capacity_constraint'
ARCHETYPE_ROTATION_SPILLOVER = 'rotation_spillover'
ARCHETYPE_STABILITY_EROSION = 'stability_erosion'
ARCHETYPE_STABILITY_RECOVERY = 'stability_recovery'
ARCHETYPE_MULTI_SOURCE_PRESSURE = 'multi_source_pressure'
ARCHETYPE_FLEXIBLE_BULLPEN = 'flexible_bullpen'
ARCHETYPE_RUN_PREVENTION_MASK = 'run_prevention_mask'

SITUATION_FIRST_MOVE_OK_THEN_THIN = 'first_move_ok_then_thin'
SITUATION_LATE_INNINGS_STABLE_MIDDLE_TESTED = 'late_innings_stable_middle_getting_tested'
SITUATION_FULL_BOARD_CLOSE_GAME_QUESTIONS = 'full_board_but_close_game_questions'
SITUATION_RESULTS_GOOD_PATH_NARROWING = 'results_good_path_narrowing'
SITUATION_SAME_FEW_CARRYING_TIGHT_SPOTS = 'same_few_names_carrying_tight_spots'
SITUATION_ENOUGH_BODIES_NOT_ENOUGH_COMFORT = 'enough_bodies_not_enough_comfort'
SITUATION_FLEXIBILITY_WORK_SPREAD_OUT = 'flexibility_real_because_work_spread_out'
SITUATION_DEPTH_STRAIN_HIDDEN_BY_TOP_END = 'depth_strain_hidden_by_top_end_structure'
SITUATION_WORKLOAD_SPREAD_TRUST_UNEVEN = 'workload_spread_but_trust_not_equal'
SITUATION_ROTATION_HANDOFF_STRETCHING_PEN = 'rotation_handoff_stretching_pen'
SITUATION_ROOM_FOR_ERROR_NARROWING = 'room_for_error_narrowing'
SITUATION_ROOM_FOR_ERROR_RETURNING = 'room_for_error_returning'
SITUATION_PRESSURES_STACKING_IN_GAME_PATH = 'pressures_stacking_in_game_path'

FORBIDDEN_PUBLIC_LABELS = (
    'Signal',
    'Evidence',
    'Context',
    'Mechanism',
    'Implication',
    'Observation',
    'Why It Matters',
    "What I'm Watching",
    'What BaseballOS Is Watching',
)

INTERNAL_TAXONOMY_TERMS = (
    'stress_transfer',
    'pressure_distribution',
    'sustainability_question',
    'hidden_capacity_loss',
    'fatigue_load',
    'trust_lane_absence',
    'trust_lane_shallow',
    'workload_high',
    'workload_light',
    'availability_thin',
    'availability_deep',
    'deep_intact',
    'concentration_shape',
    'participation_narrow',
    'participation_broad',
    'era_elite',
    'era_ordinary',
    'trust_lane_depth',
    'HIGH or CRITICAL',
    'fatigue score',
    'confidence score',
    'pressure source',
    'capacity state',
    'resource health',
    'coverage safety',
    'trust hierarchy',
    'trust-concentrated bullpen',
    'depth-driven bullpen',
    'flexible distribution bullpen',
    'leverage-heavy bullpen',
    'fragile coverage bullpen',
    'resource-strained bullpen',
    'unknown / insufficient context',
    'trust_concentrated',
    'depth_driven',
    'flexible_distribution',
    'leverage_heavy',
    'fragile_coverage',
    'resource_strained',
    'unknown_insufficient_context',
    'role_change_detection',
    'ranking_applied',
    'selection_made',
    'prediction_applied',
    'workload pattern is',
    ARCHETYPE_WORKLOAD_CONCENTRATION,
    ARCHETYPE_THIN_TRUSTED_GROUP,
    ARCHETYPE_CAPACITY_CONSTRAINT,
    ARCHETYPE_ROTATION_SPILLOVER,
    ARCHETYPE_STABILITY_EROSION,
    ARCHETYPE_STABILITY_RECOVERY,
    ARCHETYPE_MULTI_SOURCE_PRESSURE,
    ARCHETYPE_FLEXIBLE_BULLPEN,
    ARCHETYPE_RUN_PREVENTION_MASK,
)

_SentenceBuilder = Callable[[dict[str, Any]], str]
_DISCLOSURE_CHANNEL_BODY = 'body'
_DISCLOSURE_CHANNEL_FOOTER = 'footer'
_ENDING_WATCH_QUESTION = 'watch_question'
_ENDING_CLOSING_OBSERVATION = 'closing_observation'
_ENDING_IMPLICATION = 'implication'
_ENDING_WATCH_STATEMENT = 'watch_statement'
_ENDING_BASEBALL_TAKEAWAY = 'baseball_takeaway'


def _clean_text(value: Any) -> str:
    return ' '.join(str(value or '').strip().split())


def _public_language(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ''

    replacements = (
        ('HIGH or CRITICAL fatigue', 'a heavier workload flag'),
        ('HIGH or CRITICAL', 'heavier'),
        ('Trust Arms', 'trusted late-inning arms'),
        ('Trust Arm', 'trusted late-inning arm'),
        ('Clean Options', 'usable arms'),
        ('Clean Option', 'usable arm'),
        ('Available', 'available'),
        ('preferred group', 'go-to group'),
        ('preferred lane', 'late-inning answer'),
    )
    for source, replacement in replacements:
        text = text.replace(source, replacement)

    text = re.sub(r',?\s*\d+(?:st|nd|rd|th)\s+among current pens', '', text)
    text = text.replace('among current pens', 'among current bullpens')
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _sentence(value: Any) -> str | None:
    text = _public_language(value)
    if not text:
        return None
    if text[-1] not in '.!?':
        text = f'{text}.'
    return text


def _stable_seed(facts: dict[str, Any], namespace: str) -> str:
    team = facts.get('team') or {}
    payload = {
        'namespace': namespace,
        'team_id': team.get('team_id'),
        'team_name': team.get('team_name'),
        'team_abbreviation': team.get('team_abbreviation'),
        'primary_observation': facts.get('primary_observation'),
        'supporting_context': facts.get('supporting_context'),
        'pressure_source': facts.get('pressure_source'),
        'workload_pattern': facts.get('workload_pattern'),
        'capacity_context': facts.get('capacity_context'),
        'rotation_context': facts.get('rotation_context'),
        'stability_context': facts.get('stability_context'),
        'environment_context': facts.get('environment_context'),
        'watch_question': facts.get('watch_question'),
    }
    if facts.get('bullpen_context'):
        payload['bullpen_context'] = facts.get('bullpen_context')
    return json.dumps(payload, sort_keys=True, default=str)


def _stable_index(facts: dict[str, Any], namespace: str, length: int) -> int:
    if length <= 0:
        return 0
    digest = hashlib.sha256(_stable_seed(facts, namespace).encode('utf-8')).hexdigest()
    return int(digest[:12], 16) % length


def _choose(facts: dict[str, Any], namespace: str, options: list[_SentenceBuilder]) -> str:
    return options[_stable_index(facts, namespace, len(options))](facts)


def _disclosure_channel(facts: dict[str, Any]) -> str | None:
    if not facts.get('disclosure'):
        return None
    options = (
        _DISCLOSURE_CHANNEL_BODY,
        _DISCLOSURE_CHANNEL_BODY,
        _DISCLOSURE_CHANNEL_FOOTER,
        _DISCLOSURE_CHANNEL_FOOTER,
    )
    return options[_stable_index(facts, 'disclosure:channel', len(options))]


def _ending_family(facts: dict[str, Any], archetype: str) -> str:
    pools = {
        ARCHETYPE_WORKLOAD_CONCENTRATION: (
            _ENDING_WATCH_QUESTION,
            _ENDING_IMPLICATION,
            _ENDING_IMPLICATION,
        ),
        ARCHETYPE_THIN_TRUSTED_GROUP: (
            _ENDING_WATCH_QUESTION,
            _ENDING_IMPLICATION,
            _ENDING_IMPLICATION,
        ),
        ARCHETYPE_CAPACITY_CONSTRAINT: (
            _ENDING_CLOSING_OBSERVATION,
            _ENDING_IMPLICATION,
            _ENDING_CLOSING_OBSERVATION,
        ),
        ARCHETYPE_ROTATION_SPILLOVER: (
            _ENDING_WATCH_QUESTION,
            _ENDING_WATCH_STATEMENT,
            _ENDING_WATCH_STATEMENT,
        ),
        ARCHETYPE_STABILITY_EROSION: (
            _ENDING_CLOSING_OBSERVATION,
            _ENDING_WATCH_QUESTION,
            _ENDING_CLOSING_OBSERVATION,
        ),
        ARCHETYPE_STABILITY_RECOVERY: (
            _ENDING_CLOSING_OBSERVATION,
            _ENDING_BASEBALL_TAKEAWAY,
            _ENDING_BASEBALL_TAKEAWAY,
        ),
        ARCHETYPE_MULTI_SOURCE_PRESSURE: (
            _ENDING_CLOSING_OBSERVATION,
            _ENDING_IMPLICATION,
            _ENDING_IMPLICATION,
        ),
        ARCHETYPE_FLEXIBLE_BULLPEN: (
            _ENDING_BASEBALL_TAKEAWAY,
            _ENDING_CLOSING_OBSERVATION,
            _ENDING_BASEBALL_TAKEAWAY,
        ),
        ARCHETYPE_RUN_PREVENTION_MASK: (
            _ENDING_WATCH_QUESTION,
            _ENDING_IMPLICATION,
            _ENDING_IMPLICATION,
        ),
    }
    options = pools[archetype]
    return options[_stable_index(facts, f'{archetype}:ending-family', len(options))]


def _team_name(facts: dict[str, Any]) -> str:
    team = facts.get('team') or {}
    return _clean_text(team.get('team_name')) or 'this club'


def _article_team(facts: dict[str, Any]) -> str:
    team = _team_name(facts)
    if team == 'this club':
        return team
    return f'the {team}'


def _possessive_team(facts: dict[str, Any]) -> str:
    team = _team_name(facts)
    if team == 'this club':
        return "this club's"
    return f"{team}'" if team.endswith('s') else f"{team}'s"


def _sentence_start(text: str) -> str:
    if not text:
        return text
    return f'{text[0].upper()}{text[1:]}'


def _all_fact_text(facts: dict[str, Any]) -> str:
    values = [
        facts.get('primary_observation'),
        facts.get('supporting_context'),
        facts.get('pressure_source'),
        facts.get('workload_pattern'),
        facts.get('capacity_context'),
        facts.get('rotation_context'),
        facts.get('stability_context'),
        facts.get('environment_context'),
        facts.get('bullpen_context'),
        facts.get('watch_question'),
    ]
    return ' '.join(_public_language(value).lower() for value in values if value)


def _source_count(facts: dict[str, Any]) -> int:
    return sum(
        1
        for key in (
            'capacity_context',
            'rotation_context',
            'stability_context',
            'environment_context',
        )
        if facts.get(key)
    )


def _tail_after_whether(text: Any) -> str | None:
    sentence = _public_language(text)
    match = re.search(
        r'\bwhether\s+(.+?)(?:[.!?])?$',
        sentence,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    tail = match.group(1).strip()
    return tail[0].lower() + tail[1:] if tail else None


def _clustered_workload_parts(facts: dict[str, Any]) -> tuple[str, str] | None:
    text = _all_fact_text(facts)
    match = re.search(r'top\s+(\d+)\s+relievers?.*?(?:handled|taken|taking)\s+(\d+)%', text)
    if not match:
        return None
    return match.group(1), match.group(2)


def _broad_workload_parts(facts: dict[str, Any]) -> tuple[str, str | None] | None:
    text = _all_fact_text(facts)
    match = re.search(r'spread across\s+(\d+)\s+relievers?.*?averaging\s+([\d.]+)\s+pitches', text)
    if match:
        return match.group(1), match.group(2)
    shared = re.search(r'(\d+)\s+relievers have shared.*?(?:at|around)\s+([\d.]+)\s+pitches', text)
    if shared:
        return shared.group(1), shared.group(2)
    involved = re.search(r'(\d+)\s+relievers? (?:have been involved|carrying|shared)', text)
    if involved:
        return involved.group(1), None
    return None


def _availability_parts(facts: dict[str, Any]) -> tuple[str, str] | None:
    text = _all_fact_text(facts)
    match = re.search(r'(\d+)\s+of\s+(\d+)\s+(?:bullpen\s+)?arms are available', text)
    if match:
        return match.group(1), match.group(2)
    match = re.search(r'only\s+(\d+)\s+of\s+(\d+)\s+(?:bullpen\s+)?arms are available', text)
    if match:
        return match.group(1), match.group(2)
    return None


def _context_reason(facts: dict[str, Any]) -> str:
    integration = facts.get('bullpen_context_integration') or {}
    if not isinstance(integration, dict):
        return ''
    return _clean_text(integration.get('reason')).lower()


def _int_text(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _story_angle(facts: dict[str, Any], archetype: str) -> str:
    reason = _context_reason(facts)
    text = _all_fact_text(facts)
    availability = _availability_parts(facts)
    clustered = _clustered_workload_parts(facts)
    broad = _broad_workload_parts(facts)
    available = _int_text(availability[0]) if availability else None
    total = _int_text(availability[1]) if availability else None
    top_share = _int_text(clustered[1]) if clustered else None
    broad_arms = _int_text(broad[0]) if broad else None

    if archetype == ARCHETYPE_WORKLOAD_CONCENTRATION:
        if reason == 'clean_trusted_lane_narrow':
            return 'comfort_drop'
        if available is not None and available <= 3:
            return 'short_board_repeat_group'
        if top_share is not None and top_share >= 70:
            return 'same_few_carrying'
        return 'repeat_group'

    if archetype == ARCHETYPE_THIN_TRUSTED_GROUP:
        if reason == 'clean_trusted_lane_narrow':
            return 'comfort_drop'
        if available is not None and total is not None and available >= 5:
            return 'bodies_not_comfort'
        if 'late-inning' in text:
            return 'late_middle_split'
        return 'top_heavy_depth'

    if archetype == ARCHETYPE_CAPACITY_CONSTRAINT:
        if reason == 'dependable_group_narrow':
            return 'obvious_choices_then_gap'
        if reason == 'thin_active_capacity_margin':
            return 'full_board_comfort_question'
        if available is not None and available <= 3:
            return 'short_comfort_board'
        return 'usable_layer_thins'

    if archetype == ARCHETYPE_ROTATION_SPILLOVER:
        if top_share is not None and top_share >= 60:
            return 'starter_handoff_same_arms'
        if broad_arms is not None and broad_arms >= 6:
            return 'starter_handoff_broad_group'
        return 'starter_handoff'

    if archetype == ARCHETYPE_STABILITY_EROSION:
        if 'moving in and out' in text or 'shifting' in text:
            return 'moving_mix'
        return 'less_settled'

    if archetype == ARCHETYPE_STABILITY_RECOVERY:
        if broad_arms is not None and broad_arms >= 6:
            return 'rhythm_with_width'
        return 'rhythm_return'

    if archetype == ARCHETYPE_MULTI_SOURCE_PRESSURE:
        if reason == 'thin_active_capacity_margin':
            return 'full_board_comfort_question'
        if reason == 'top_structure_with_resource_strain':
            return 'late_structure_cover'
        if reason == 'clean_trusted_lane_narrow':
            return 'comfort_drop'
        if top_share is not None and top_share >= 65:
            return 'stacked_on_same_arms'
        return 'stacked_pressures'

    if archetype == ARCHETYPE_FLEXIBLE_BULLPEN:
        if reason == 'top_structure_with_resource_strain':
            return 'late_structure_cover'
        if broad_arms is not None and broad_arms >= 8:
            return 'wide_routes'
        if reason == 'flexibility_supported_by_trust_structure':
            return 'real_flexibility'
        return 'usable_width'

    if archetype == ARCHETYPE_RUN_PREVENTION_MASK:
        if reason == 'results_mask_thinner_bullpen_context':
            return 'results_paths_thin'
        if top_share is not None and top_share >= 60:
            return 'good_results_same_arms'
        return 'results_not_whole_story'

    return 'standard'


def _story_situation(facts: dict[str, Any], archetype: str) -> str:
    angle = _story_angle(facts, archetype)
    reason = _context_reason(facts)
    availability = _availability_parts(facts)
    available = _int_text(availability[0]) if availability else None

    if archetype == ARCHETYPE_WORKLOAD_CONCENTRATION:
        if angle == 'comfort_drop' or (available is not None and available <= 3):
            return SITUATION_ENOUGH_BODIES_NOT_ENOUGH_COMFORT
        return SITUATION_SAME_FEW_CARRYING_TIGHT_SPOTS

    if archetype == ARCHETYPE_THIN_TRUSTED_GROUP:
        if angle == 'late_middle_split':
            return SITUATION_LATE_INNINGS_STABLE_MIDDLE_TESTED
        if angle == 'bodies_not_comfort':
            return SITUATION_WORKLOAD_SPREAD_TRUST_UNEVEN
        return SITUATION_ENOUGH_BODIES_NOT_ENOUGH_COMFORT

    if archetype == ARCHETYPE_CAPACITY_CONSTRAINT:
        if angle in {'obvious_choices_then_gap', 'short_comfort_board'}:
            return SITUATION_FIRST_MOVE_OK_THEN_THIN
        if angle == 'full_board_comfort_question':
            return SITUATION_FULL_BOARD_CLOSE_GAME_QUESTIONS
        return SITUATION_ENOUGH_BODIES_NOT_ENOUGH_COMFORT

    if archetype == ARCHETYPE_ROTATION_SPILLOVER:
        return SITUATION_ROTATION_HANDOFF_STRETCHING_PEN

    if archetype == ARCHETYPE_STABILITY_EROSION:
        return SITUATION_ROOM_FOR_ERROR_NARROWING

    if archetype == ARCHETYPE_STABILITY_RECOVERY:
        return SITUATION_ROOM_FOR_ERROR_RETURNING

    if archetype == ARCHETYPE_MULTI_SOURCE_PRESSURE:
        if angle == 'full_board_comfort_question':
            return SITUATION_FULL_BOARD_CLOSE_GAME_QUESTIONS
        if angle == 'late_structure_cover':
            return SITUATION_DEPTH_STRAIN_HIDDEN_BY_TOP_END
        if angle == 'comfort_drop':
            return SITUATION_ENOUGH_BODIES_NOT_ENOUGH_COMFORT
        if angle == 'stacked_on_same_arms':
            return SITUATION_SAME_FEW_CARRYING_TIGHT_SPOTS
        return SITUATION_PRESSURES_STACKING_IN_GAME_PATH

    if archetype == ARCHETYPE_FLEXIBLE_BULLPEN:
        if angle == 'late_structure_cover' or reason == 'top_structure_with_resource_strain':
            return SITUATION_LATE_INNINGS_STABLE_MIDDLE_TESTED
        return SITUATION_FLEXIBILITY_WORK_SPREAD_OUT

    if archetype == ARCHETYPE_RUN_PREVENTION_MASK:
        return SITUATION_RESULTS_GOOD_PATH_NARROWING

    return 'standard'


def select_story_archetype(facts: dict[str, Any]) -> str:
    """Select the internal narrative family from already-normalized story facts."""

    text = _all_fact_text(facts)
    stability = _public_language(facts.get('stability_context')).lower()
    pressure = _public_language(facts.get('pressure_source')).lower()

    if facts.get('environment_context') or _source_count(facts) >= 2:
        return ARCHETYPE_MULTI_SOURCE_PRESSURE

    run_prevention_signal = (
        'run-prevention' in text
        or 'run prevention' in text
        or 'results line' in text
        or re.search(r'\bera\b', text) is not None
    )

    if run_prevention_signal and any(marker in text for marker in (
        'workload',
        'usage',
        'thin',
        'only ',
        'smaller set',
        'concentrated',
    )):
        return ARCHETYPE_RUN_PREVENTION_MASK

    if stability and any(marker in stability for marker in (
        'more settled',
        'settled',
        'steadier',
        'finding footing',
        'same group',
        'stable',
        'recovery',
    )):
        return ARCHETYPE_STABILITY_RECOVERY

    if stability:
        return ARCHETYPE_STABILITY_EROSION

    if facts.get('rotation_context'):
        return ARCHETYPE_ROTATION_SPILLOVER

    if 'trusted late-inning' in pressure and any(marker in pressure for marker in (
        'do not fully line up',
        'not fully line up',
        'thin',
        'shortage',
        'scarce',
        'absence',
        'shallow',
    )):
        return ARCHETYPE_THIN_TRUSTED_GROUP

    if facts.get('capacity_context') or any(marker in text for marker in (
        'thin usable layer',
        'thinner usable layer',
        'fewer usable arms',
        'short on usable arms',
        'available group is smaller',
        'only ',
    )):
        return ARCHETYPE_CAPACITY_CONSTRAINT

    if any(marker in text for marker in (
        'deeper usable layer',
        'spread across',
        'broad',
        'room to maneuver',
        'more ways',
        'usable shape still holds',
    )):
        return ARCHETYPE_FLEXIBLE_BULLPEN

    if any(marker in text for marker in (
        'clustered',
        'concentrated',
        'smaller set',
        'smaller group',
        'narrow',
        'top ',
    )):
        return ARCHETYPE_WORKLOAD_CONCENTRATION

    return ARCHETYPE_WORKLOAD_CONCENTRATION


def _metric_sentence(facts: dict[str, Any], archetype: str) -> str | None:
    clustered = _clustered_workload_parts(facts)
    broad = _broad_workload_parts(facts)
    availability = _availability_parts(facts)
    angle = _story_angle(facts, archetype)

    if archetype == ARCHETYPE_WORKLOAD_CONCENTRATION and clustered:
        top_share = _int_text(clustered[1])
        if top_share is not None and top_share >= 70:
            options: list[_SentenceBuilder] = [
                lambda f: "The same few names keep showing up in the heaviest spots.",
                lambda f: "The late work keeps circling back to the same small group.",
                lambda f: "The biggest relief pockets have been finding the same arms.",
            ]
        else:
            options = [
                lambda f: "The recent work has been bunched into a smaller group.",
                lambda f: "The bullpen has not been spreading the work around as much lately.",
                lambda f: "The workload has been moving through familiar hands.",
            ]
        return _sentence(_choose(facts, f'{archetype}:metric:clustered:{angle}', options))

    if archetype == ARCHETYPE_CAPACITY_CONSTRAINT and availability:
        available = _int_text(availability[0])
        if available is not None and available <= 3:
            options = [
                lambda f: "The choices get thin quickly once the game starts stretching.",
                lambda f: "There are not many comfortable pivots left if the night gets long.",
                lambda f: "A clean first answer does not settle the rest of the game.",
            ]
        else:
            options = [
                lambda f: "The board has names, but the comfortable part is not very deep.",
                lambda f: "This starts with a shorter list of usable choices than a normal night.",
                lambda f: "The margin is thinner than the names on the board make it look.",
            ]
        return _sentence(_choose(facts, f'{archetype}:metric:availability:{angle}', options))

    if archetype == ARCHETYPE_FLEXIBLE_BULLPEN and broad:
        options: list[_SentenceBuilder] = [
            lambda f: "They have had to use a lot of different arms lately, and that gives the staff more than one way to manage a game.",
            lambda f: "The workload has been moving through a lot of different hands.",
            lambda f: "Recent games have not been stuck on one small pocket of the bullpen.",
        ]
        return _sentence(_choose(facts, f'{archetype}:metric:broad:{angle}', options))

    if archetype == ARCHETYPE_RUN_PREVENTION_MASK:
        supporting = _public_language(facts.get('supporting_context'))
        if supporting:
            options = [
                lambda f: "The results still matter, but recent usage tells a different story underneath them.",
                lambda f: "The scoreboard does not tell the whole story; recent usage can make good results feel a little thinner.",
                lambda f: "The results still look good on the surface, but recent usage keeps the read from being that simple.",
            ]
            return _sentence(_choose(facts, f'{archetype}:metric:run-prevention', options))

    if clustered:
        return _sentence("The same few names keep showing up in the heaviest spots.")
    if broad:
        options = [
            lambda f: "Recent relief work has moved through a lot of different hands.",
            lambda f: "The staff has had to involve a wider slice of the bullpen lately.",
            lambda f: "The recent workload has not stayed with one small group.",
            lambda f: "More of the bullpen has had to be part of the recent innings.",
        ]
        return _sentence(_choose(facts, f'{archetype}:metric:broad-fallback:{angle}', options))
    return None


def _opening_sentence(facts: dict[str, Any], archetype: str) -> str:
    article = _article_team(facts)
    possessive = _possessive_team(facts)
    angle = _story_angle(facts, archetype)
    situation = _story_situation(facts, archetype)

    pools: dict[str, list[_SentenceBuilder]] = {
        ARCHETYPE_WORKLOAD_CONCENTRATION: [
            lambda f: f"A small group is carrying most of the relief work for {article} right now.",
            lambda f: f"{possessive} relief work is less about the full list and more about who keeps getting the ball.",
            lambda f: f"The workload story for {article} is about how often the same relievers are taking the ball.",
            lambda f: f"For {article}, the same relief group keeps getting pulled back into the game.",
        ],
        ARCHETYPE_THIN_TRUSTED_GROUP: [
            lambda f: f"Available innings may not be the main challenge for {article}; comfortable late innings are tighter.",
            lambda f: f"{possessive} bullpen has arms to consider, but the late-inning comfort is tighter.",
            lambda f: f"For {article}, a fuller-looking board does not fully answer the comfort question.",
        ],
        ARCHETYPE_CAPACITY_CONSTRAINT: [
            lambda f: f"{possessive} bullpen is running with fewer comfortable choices than usual.",
            lambda f: f"{possessive} relief depth is the part that shows up first tonight.",
            lambda f: f"For {article}, the tight part of the bullpen board is how quickly the usable layer thins out.",
        ],
        ARCHETYPE_ROTATION_SPILLOVER: [
            lambda f: f"{possessive} bullpen has recently been asked to absorb more of the game.",
            lambda f: f"For {article}, the relief read starts before the bullpen gate opens.",
            lambda f: f"For {article}, starter length changes what the bullpen has to solve tonight.",
        ],
        ARCHETYPE_STABILITY_EROSION: [
            lambda f: f"{possessive} bullpen is less settled than the roster sheet suggests.",
            lambda f: f"For {article}, the recent relief mix has been moving around.",
            lambda f: f"{possessive} relief group has not looked the same every night.",
        ],
        ARCHETYPE_STABILITY_RECOVERY: [
            lambda f: f"{possessive} bullpen has looked more settled over the recent games.",
            lambda f: f"For {article}, the relief picture has a little more footing than it did before.",
            lambda f: f"{possessive} usage shape is starting to settle.",
        ],
        ARCHETYPE_MULTI_SOURCE_PRESSURE: [
            lambda f: f"{possessive} bullpen is being squeezed from a few directions at once.",
            lambda f: f"For {article}, the pressure is not coming from one clean spot.",
            lambda f: f"{possessive} bullpen is trying to hold together depth, workload, and recent shape at the same time.",
        ],
        ARCHETYPE_FLEXIBLE_BULLPEN: [
            lambda f: f"{possessive} bullpen enters tonight with room to maneuver.",
            lambda f: f"For {article}, the useful part is having multiple ways to cover the game.",
            lambda f: f"{possessive} bullpen has more than one workable answer.",
        ],
        ARCHETYPE_RUN_PREVENTION_MASK: [
            lambda f: f"{possessive} results still look sturdy, but the workload underneath still matters.",
            lambda f: f"For {article}, good run prevention is not the whole read.",
            lambda f: f"The scoreboard says one thing for {possessive} bullpen; recent usage adds another layer.",
        ],
    }
    angle_pools: dict[str, dict[str, list[_SentenceBuilder]]] = {
        ARCHETYPE_WORKLOAD_CONCENTRATION: {
            'comfort_drop': [
                lambda f: f"There is a clear drop from {possessive} first bullpen choices to the rest of the night.",
                lambda f: f"For {article}, familiar relief options can start the night, but the comfort drops quickly after that.",
            ],
            'short_board_repeat_group': [
                lambda f: f"For {article}, a small relief group is covering a board that is already short.",
                lambda f: f"The same {possessive} relievers keep coming up because there are not many clean pivots behind them.",
            ],
            'same_few_carrying': [
                lambda f: f"{possessive} bullpen keeps finding outs through the same few names.",
                lambda f: f"The recent {possessive} relief work keeps circling back to the same arms.",
            ],
        },
        ARCHETYPE_THIN_TRUSTED_GROUP: {
            'comfort_drop': [
                lambda f: f"{possessive} bullpen has a noticeable line between the first few options and everyone else.",
                lambda f: f"For {article}, comfort drops fast once the obvious late-game choices are gone.",
            ],
            'bodies_not_comfort': [
                lambda f: f"For {article}, there are arms on the board, but not all of them answer the same questions.",
                lambda f: f"{possessive} bullpen looks fuller before the game starts choosing the biggest innings.",
            ],
            'late_middle_split': [
                lambda f: f"{possessive} late innings and middle innings do not look like the same conversation right now.",
                lambda f: f"For {article}, the game looks different before and after the leverage starts to climb.",
            ],
        },
        ARCHETYPE_CAPACITY_CONSTRAINT: {
            'obvious_choices_then_gap': [
                lambda f: f"Once {article} get past the obvious bullpen choices, the night gets tighter.",
                lambda f: f"{possessive} first move may be clear; the harder part is what comes after it.",
            ],
            'full_board_comfort_question': [
                lambda f: f"{possessive} bullpen looks fuller until the game starts asking who you really want with it close.",
                lambda f: f"On paper {article} have names, but the comfort level is not spread evenly across the board.",
            ],
            'short_comfort_board': [
                lambda f: f"For {article}, the list of comfortable relief choices is shorter than usual.",
                lambda f: f"The usable part of {possessive} bullpen thins out early tonight.",
            ],
        },
        ARCHETYPE_ROTATION_SPILLOVER: {
            'starter_handoff_same_arms': [
                lambda f: f"{possessive} bullpen keeps inheriting more game, and the same arms keep meeting it.",
                lambda f: f"For {article}, shorter starts are pushing the relief plan back toward familiar names.",
            ],
            'starter_handoff_broad_group': [
                lambda f: f"For {article}, the relief work has been spread around, but the starter handoff still matters.",
                lambda f: f"{possessive} bullpen has had multiple ways through games because it has needed them.",
            ],
            'starter_handoff': [
                lambda f: f"The first bullpen question for {article} is how much game the starter leaves behind.",
                lambda f: f"{possessive} relief story starts with the handoff from the rotation.",
            ],
        },
        ARCHETYPE_STABILITY_EROSION: {
            'moving_mix': [
                lambda f: f"{possessive} bullpen has been changing shape from night to night.",
                lambda f: f"For {article}, the recent relief map has not stayed in one place.",
            ],
            'less_settled': [
                lambda f: f"{possessive} bullpen is harder to read because the recent shape has not settled.",
                lambda f: f"The question around {article} is not just who is available, but how the group fits together.",
            ],
        },
        ARCHETYPE_STABILITY_RECOVERY: {
            'rhythm_with_width': [
                lambda f: f"{possessive} bullpen is starting to look like a group with more than one bridge through a game.",
                lambda f: f"For {article}, the recent relief shape has widened into something more usable.",
            ],
            'rhythm_return': [
                lambda f: f"{possessive} bullpen has started to look a little more like itself.",
                lambda f: f"For {article}, the relief group is finding a steadier rhythm.",
            ],
        },
        ARCHETYPE_MULTI_SOURCE_PRESSURE: {
            'full_board_comfort_question': [
                lambda f: f"{possessive} bullpen looks full until the game starts asking which arms belong in the biggest spots.",
                lambda f: f"For {article}, the board has names; the harder question is how many feel comfortable when the score is close.",
            ],
            'late_structure_cover': [
                lambda f: f"{possessive} late innings still have shape, but the rest of the bullpen is doing more work around them.",
                lambda f: f"For {article}, the back of the game still makes sense while the innings before it are getting tighter.",
            ],
            'comfort_drop': [
                lambda f: f"{possessive} pressure comes from how quickly the comfortable choices run out.",
                lambda f: f"For {article}, this is less about having no arms and more about how fast the comfort falls off.",
            ],
            'stacked_on_same_arms': [
                lambda f: f"{possessive} bullpen has more than one issue, and too much of it keeps landing on the same names.",
                lambda f: f"For {article}, the pressure is layered because the workload has not been spreading cleanly.",
            ],
        },
        ARCHETYPE_FLEXIBLE_BULLPEN: {
            'late_structure_cover': [
                lambda f: f"{possessive} late innings still have structure, which is helping cover the work building in front of them.",
                lambda f: f"For {article}, the back-end shape is what makes the broader bullpen read workable.",
            ],
            'wide_routes': [
                lambda f: f"{possessive} bullpen has had several ways through games lately.",
                lambda f: f"For {article}, flexibility is showing up in how many different hands have actually been part of the answer.",
            ],
            'real_flexibility': [
                lambda f: f"{possessive} flexibility looks real, not just like a long list of available names.",
                lambda f: f"For {article}, the bullpen has more than one practical way through the night.",
            ],
        },
        ARCHETYPE_RUN_PREVENTION_MASK: {
            'results_paths_thin': [
                lambda f: f"{possessive} results still look good, but the bullpen work underneath is getting tighter.",
                lambda f: f"For {article}, the run prevention has held up while the relief handoffs underneath have gotten less simple.",
            ],
            'good_results_same_arms': [
                lambda f: f"{possessive} bullpen keeps getting outs, but too many of them are coming from the same pocket.",
                lambda f: f"For {article}, the results are cleaner than the workload shape underneath them.",
            ],
        },
    }
    situation_pools: dict[str, list[_SentenceBuilder]] = {
        SITUATION_FIRST_MOVE_OK_THEN_THIN: [
            lambda f: f"{_sentence_start(article)} can probably get through the first bullpen decision; the night gets harder if it asks for another answer right away.",
            lambda f: f"{_sentence_start(possessive)} first bullpen move can still be clean, but the game becomes trickier if it needs a second or third answer.",
            lambda f: f"For {article}, the first relief move is not the whole issue; the harder part is what happens if the night keeps stretching.",
        ],
        SITUATION_LATE_INNINGS_STABLE_MIDDLE_TESTED: [
            lambda f: f"{_sentence_start(possessive)} late innings still have shape, which gives the staff somewhere to land while the middle of the game does more work.",
            lambda f: f"For {article}, the finish still looks familiar; the bigger test is how much has to happen before that point.",
            lambda f: f"{_sentence_start(possessive)} late innings still have anchors, even while the bridge into them asks for more.",
        ],
        SITUATION_FULL_BOARD_CLOSE_GAME_QUESTIONS: [
            lambda f: f"{_sentence_start(article)} can find arms for the game; the harder question is which ones fit once the score gets tight.",
            lambda f: f"{_sentence_start(possessive)} bullpen looks full enough until the game starts asking for close-game answers.",
            lambda f: f"For {article}, the issue is not finding names. It is deciding how many of them belong in the innings that can swing the night.",
        ],
        SITUATION_RESULTS_GOOD_PATH_NARROWING: [
            lambda f: f"{_sentence_start(possessive)} results are still holding, but the outs are taking more care to piece together.",
            lambda f: f"For {article}, the scoreboard still reads clean while the bullpen handoffs get a little more delicate.",
            lambda f: f"{_sentence_start(possessive)} run prevention is still doing its job, but the bullpen has had to work harder underneath.",
        ],
        SITUATION_SAME_FEW_CARRYING_TIGHT_SPOTS: [
            lambda f: f"When {article} get into the tighter parts of the game, the same relief names keep coming back into the picture.",
            lambda f: f"{_sentence_start(possessive)} bullpen keeps finding its way back to the same few arms when the game starts to matter most.",
            lambda f: f"For {article}, the biggest relief pockets keep landing on a familiar part of the bullpen.",
        ],
        SITUATION_ENOUGH_BODIES_NOT_ENOUGH_COMFORT: [
            lambda f: f"{_sentence_start(article)} have bullpen bodies for the night, but the comfort starts dropping after the first few names.",
            lambda f: f"For {article}, the list is longer than the list of choices you would feel good about in a tight spot.",
            lambda f: f"{_sentence_start(possessive)} bullpen is not empty; it just gets uncomfortable quickly once the game moves past the first few names.",
        ],
        SITUATION_FLEXIBILITY_WORK_SPREAD_OUT: [
            lambda f: f"{_sentence_start(possessive)} bullpen has more than one way through the game because the work has been moving around.",
            lambda f: f"For {article}, the recent usage gives the staff a few different answers instead of forcing everything through one lane.",
            lambda f: f"{_sentence_start(possessive)} flexibility shows up in the way the staff can move the game around without going straight back to the same answer.",
        ],
        SITUATION_DEPTH_STRAIN_HIDDEN_BY_TOP_END: [
            lambda f: f"{_sentence_start(possessive)} late innings can still look normal while the group behind them takes on more of the night.",
            lambda f: f"For {article}, the top of the bullpen still gives the game a shape; the tighter part is everything needed before that.",
            lambda f: f"{_sentence_start(possessive)} late innings can still look familiar, but the lead-in to them is carrying more weight.",
        ],
        SITUATION_WORKLOAD_SPREAD_TRUST_UNEVEN: [
            lambda f: f"{_sentence_start(possessive)} work has moved through enough arms, but not every option carries the same close-game comfort.",
            lambda f: f"For {article}, the innings have moved around; the comfort has not spread quite as evenly.",
            lambda f: f"{_sentence_start(article)} have had different arms involved, but the game still narrows when the leverage climbs.",
        ],
        SITUATION_ROTATION_HANDOFF_STRETCHING_PEN: [
            lambda f: f"{_sentence_start(possessive)} bullpen story starts with how much game the starter leaves behind.",
            lambda f: f"For {article}, a shorter handoff can turn an ordinary relief night into a longer puzzle.",
            lambda f: f"{_sentence_start(possessive)} relievers are not just covering the end of games; lately they have had to solve more of the middle, too.",
        ],
        SITUATION_ROOM_FOR_ERROR_NARROWING: [
            lambda f: f"{_sentence_start(possessive)} bullpen has less room for a clean fallback when the game moves off script.",
            lambda f: f"For {article}, the recent relief shape has been moving enough that the night is harder to map out cleanly.",
            lambda f: f"{_sentence_start(possessive)} group is losing some of the easy structure that makes a bullpen night feel simple.",
        ],
        SITUATION_ROOM_FOR_ERROR_RETURNING: [
            lambda f: f"{_sentence_start(possessive)} bullpen is getting back to a shape the staff can plan around.",
            lambda f: f"For {article}, the relief group is starting to give the game a cleaner shape again.",
            lambda f: f"{_sentence_start(possessive)} recent usage has started to look less like patchwork and more like a usable bridge.",
        ],
        SITUATION_PRESSURES_STACKING_IN_GAME_PATH: [
            lambda f: f"{_sentence_start(possessive)} bullpen has a few small problems that start to matter more when the game asks for multiple answers.",
            lambda f: f"For {article}, the issue is how the pressures line up once the starter hands the game over.",
            lambda f: f"{_sentence_start(possessive)} bullpen is not dealing with one clean problem; the night gets tighter when those pieces stack.",
        ],
    }
    options = (
        situation_pools.get(situation)
        or angle_pools.get(archetype, {}).get(angle)
        or pools[archetype]
    )
    return _sentence(_choose(facts, f'{archetype}:opening:{situation}:{angle}', options)) or ''


def _contextual_middle_observation(
    facts: dict[str, Any],
    archetype: str,
    angle: str,
    fallback: str | None,
) -> str | None:
    if not fallback:
        return None
    article = _article_team(facts)
    possessive = _possessive_team(facts)
    reason = _context_reason(facts)
    keyed_options: dict[tuple[str, str], list[_SentenceBuilder]] = {
        ('clean_trusted_lane_narrow', 'comfort_drop'): [
            lambda f: "Once the first few choices are gone, the game starts asking uncomfortable questions.",
            lambda f: "The difference between the first layer and the rest of the group is doing a lot of work here.",
            lambda f: "That is where the night changes: the first few names are one conversation, and everything after them is another.",
        ],
        ('clean_trusted_lane_narrow', 'short_comfort_board'): [
            lambda f: "The first few choices can carry a plan; after that, the night gets less comfortable.",
            lambda f: "The top of the list is still usable. The thinner part is what happens after the first turn.",
            lambda f: "This is where a short board gets uncomfortable: the game can move past the best choices quickly.",
        ],
        ('clean_trusted_lane_narrow', 'usable_layer_thins'): [
            lambda f: "The first few choices can carry a plan; after that, the night gets less comfortable.",
            lambda f: "The top of the list is still usable. The thinner part is what happens after the first turn.",
            lambda f: "This is where a short board gets uncomfortable: the game can move past the best choices quickly.",
        ],
        ('top_structure_with_resource_strain', 'late_structure_cover'): [
            lambda f: "The back of the game still makes sense; the innings before it are carrying more of the strain.",
            lambda f: "The late innings can still look familiar, but the middle innings have to do more of the lifting.",
            lambda f: "The late innings still give the staff a spine, which helps cover for everything being asked before then.",
        ],
        ('top_structure_with_resource_strain', 'wide_routes'): [
            lambda f: "That width matters because the finish still has structure even while the group behind it is working harder.",
            lambda f: "The late innings still look familiar, which makes the broader workload easier to absorb.",
            lambda f: "The late innings have not lost their shape, and that is what keeps the wider usage from feeling loose.",
        ],
        ('top_structure_with_resource_strain', 'stacked_pressures'): [
            lambda f: "The late innings still have shape, but the stress is showing up in how much has to happen before then.",
            lambda f: "The finish may still be recognizable; the tighter part is the bridge into it.",
            lambda f: "The top of the night still looks orderly, while the rest of the game asks for more patchwork.",
        ],
        ('thin_active_capacity_margin', 'full_board_comfort_question'): [
            lambda f: "The board has names, but the comfort is not spread evenly across it.",
            lambda f: "This is where a full-looking bullpen can still feel short once the game gets tight.",
            lambda f: f"The question is not whether {article} can find arms; it is how many of them fit a close game.",
        ],
        ('dependable_group_narrow', 'obvious_choices_then_gap'): [
            lambda f: "The first turn may be straightforward, but the next one is where the night gets uncomfortable.",
            lambda f: "There are still obvious choices; the thin part is what sits behind them.",
            lambda f: "Once the game moves past the cleanest choices, there is not much cushion left.",
        ],
        ('active_group_intact_resource_pool_strained', 'usable_layer_thins'): [
            lambda f: "The main group can still look intact while the cushion behind it gets lighter.",
            lambda f: "That is the kind of bullpen read that looks better at first glance than it feels by the sixth or seventh inning.",
            lambda f: "The front of the board is not the issue; the depth behind it is where the night can get tighter.",
        ],
        ('flexibility_supported_by_trust_structure', 'real_flexibility'): [
            lambda f: f"That looks like real flexibility for {article}, not just a long list of available names.",
            lambda f: f"{possessive} flexibility is useful because it has a baseball shape, not just extra bodies.",
            lambda f: "The width is meaningful because it gives the staff more than one practical way to cover the game.",
        ],
        ('results_mask_thinner_bullpen_context', 'results_paths_thin'): [
            lambda f: "The results can look sturdy while the bullpen underneath loses some cushion.",
            lambda f: "That is how good results can hide a bullpen that has fewer comfortable turns.",
            lambda f: "The outs are still there, but the innings underneath are less comfortable than the line suggests.",
        ],
        ('results_mask_thinner_bullpen_context', 'good_results_same_arms'): [
            lambda f: "The run prevention has held, but the workload underneath is leaning on familiar names.",
            lambda f: "The results look cleaner than the way the bullpen has had to get there.",
            lambda f: "That is the tension: the outs are coming, but more of them are coming from the same place.",
        ],
    }
    options = (
        keyed_options.get((reason, angle))
        or keyed_options.get((reason, archetype))
    )
    if not options:
        return fallback
    return _choose(facts, f'{archetype}:middle-context:{reason}:{angle}', options)


def _situation_middle_observation(
    facts: dict[str, Any],
    archetype: str,
    situation: str,
) -> str | None:
    options_by_situation: dict[str, list[_SentenceBuilder]] = {
        SITUATION_FIRST_MOVE_OK_THEN_THIN: [
            lambda f: "The first move can still make sense; the trouble is how quickly the staff has to start looking for the next one.",
            lambda f: "This is the kind of night where the second relief decision can be more revealing than the first.",
            lambda f: "A clean handoff is still possible, but the plan gets thinner if the game needs multiple turns from the pen.",
        ],
        SITUATION_LATE_INNINGS_STABLE_MIDDLE_TESTED: [
            lambda f: "That matters because the late innings can still look familiar, even if the middle of the game is doing more work.",
            lambda f: "The staff still has somewhere to point the late innings; the bridge into that part is carrying more of the night.",
            lambda f: "The late innings are not the uncomfortable part. The bridge into them is working harder than the finish.",
        ],
        SITUATION_FULL_BOARD_CLOSE_GAME_QUESTIONS: [
            lambda f: "It is less a question of finding names and more a question of finding the right inning for them.",
            lambda f: "The board can look complete before the game starts sorting the comfortable choices from the merely available ones.",
            lambda f: "A longer list helps, but it does not mean every arm fits the same pocket of the game.",
        ],
        SITUATION_RESULTS_GOOD_PATH_NARROWING: [
            lambda f: f"For {_article_team(f)}, the outs are still coming, but they are not arriving as easily as the results make it look.",
            lambda f: "That is the tension: the line still looks fine, while the bullpen has less cushion underneath it.",
            lambda f: "Good results still count. They just do not make the way there feel as easy as the line suggests.",
            lambda f: "The line still matters, but it is not the whole bullpen read.",
        ],
        SITUATION_SAME_FEW_CARRYING_TIGHT_SPOTS: [
            lambda f: "When the game gets tight, it keeps finding the same pocket of the bullpen.",
            lambda f: "That can work for a night, but the same few names keep making the next clean inning behind them matter more.",
            lambda f: "The bullpen still has answers; they just keep coming from the same few names.",
        ],
        SITUATION_ENOUGH_BODIES_NOT_ENOUGH_COMFORT: [
            lambda f: "The staff can cover innings, but leverage narrows the usable part of the board quickly.",
            lambda f: "The staff can find a pitcher, but the game gets harder once it moves past the first few choices.",
            lambda f: "That is where a normal-looking list can turn into a tougher in-game problem after the first few choices.",
        ],
        SITUATION_FLEXIBILITY_WORK_SPREAD_OUT: [
            lambda f: "Because the work has moved around, the staff is not forced back to one answer every time the game changes.",
            lambda f: "The value is practical: a messy inning does not immediately collapse the whole night onto one small group.",
            lambda f: "That kind of width gives the staff a way to adjust without treating every inning like the same inning.",
        ],
        SITUATION_DEPTH_STRAIN_HIDDEN_BY_TOP_END: [
            lambda f: "The back end can still make the night feel normal; the work before that is where the stress shows.",
            lambda f: "A normal-looking back end can make the rest of the stress easier to miss.",
            lambda f: "That structure helps, but it also puts more importance on getting the game there cleanly.",
        ],
        SITUATION_WORKLOAD_SPREAD_TRUST_UNEVEN: [
            lambda f: "The work has moved around, but not every arm carries the same late-game comfort.",
            lambda f: "That is a different kind of width: useful, but still uneven once the game gets tight.",
            lambda f: "Several arms can be part of the night without making every inning feel equally settled.",
        ],
        SITUATION_ROTATION_HANDOFF_STRETCHING_PEN: [
            lambda f: "The handoff matters because a shorter start can turn a normal bullpen night into a coverage problem.",
            lambda f: "The bullpen can look different depending on whether it is asked for the sixth inning or just the finish.",
            lambda f: "A few extra outs in the middle of the game can change which relief choices are still comfortable late.",
        ],
        SITUATION_ROOM_FOR_ERROR_NARROWING: [
            lambda f: "A moving group leaves less room for a clean fallback if the first plan changes.",
            lambda f: "The more the relief map moves, the harder it is for the staff to know where the safe exits are.",
            lambda f: "That kind of churn makes a normal bullpen night feel a little more improvised.",
        ],
        SITUATION_ROOM_FOR_ERROR_RETURNING: [
            lambda f: "A steadier group gives the staff a cleaner fallback if the game moves off script.",
            lambda f: "The useful part is not just who is available; it is that the innings are starting to line up again.",
            lambda f: "When the bridge looks familiar, the game does not have to be solved from scratch every night.",
        ],
        SITUATION_PRESSURES_STACKING_IN_GAME_PATH: [
            lambda f: "None of the issues has to carry the whole headline; together, they make the game harder to manage.",
            lambda f: "One clean answer would miss the point. The game gets complicated when those smaller pressures arrive together.",
            lambda f: "The squeeze is cumulative: depth, workload, and the handoff all start touching the same part of the night.",
        ],
    }
    options = options_by_situation.get(situation)
    if not options:
        return None
    return _choose(facts, f'{archetype}:middle-situation:{situation}', options)


def _identity_texture_sentence(facts: dict[str, Any]) -> str | None:
    integration = facts.get('story_identity_integration') or {}
    if not isinstance(integration, dict) or not integration.get('applied'):
        return None
    return _sentence(integration.get('text'))


def _middle_sentences(facts: dict[str, Any], archetype: str) -> list[str | None]:
    metric = _metric_sentence(facts, archetype)
    bullpen_context = facts.get('bullpen_context')
    angle = _story_angle(facts, archetype)
    situation = _story_situation(facts, archetype)
    pools: dict[str, list[_SentenceBuilder]] = {
        ARCHETYPE_WORKLOAD_CONCENTRATION: [
            lambda f: "That makes the story less about the roster sheet and more about how tightly the work has collected.",
            lambda f: "The same group keeps taking on most of the work.",
            lambda f: "The names on the board matter less than who keeps getting called on.",
        ],
        ARCHETYPE_THIN_TRUSTED_GROUP: [
            lambda f: "The split is between arms who are merely usable and arms who fit the innings a club usually protects.",
            lambda f: "That is why the roster sheet can overstate the amount of late-game comfort on the board.",
            lambda f: "The middle of the story is comfort, not volume: the choices tighten when leverage starts to matter.",
        ],
        ARCHETYPE_CAPACITY_CONSTRAINT: [
            lambda f: "This is a depth problem in baseball terms: the next clean inning can matter as much as the late plan.",
            lambda f: "The squeeze is not just who is available, but how many comfortable pivots remain if the game asks for extra relief outs.",
            lambda f: "The bullpen can still have a plan, but there is less margin behind the first few choices.",
        ],
        ARCHETYPE_ROTATION_SPILLOVER: [
            lambda f: "Starter length is the background. When more outs keep landing on the pen, the same list of arms carries a different weight.",
            lambda f: "The innings tell the story here: the bullpen has had to pick up more of the game lately.",
            lambda f: "The burden is cumulative, because relief depth changes when starters leave more work behind.",
        ],
        ARCHETYPE_STABILITY_EROSION: [
            lambda f: "Continuity is the issue. When the mix changes, recent usage is a cleaner guide than assuming yesterday's bullpen shape still applies.",
            lambda f: "A moving relief group makes recent usage more important, because the board is not static night to night.",
            lambda f: "The innings have been moving through a changing group, which keeps the story tied to actual usage.",
        ],
        ARCHETYPE_STABILITY_RECOVERY: [
            lambda f: "The important part is balance. A steadier run of games gives the group more ways through the middle innings.",
            lambda f: "This is less about one arm carrying the whole night and more about the bullpen finding a usable rhythm.",
            lambda f: "A steadier mix gives the story a different shape: the bullpen has more ways to get from the starter to the late plan.",
        ],
        ARCHETYPE_MULTI_SOURCE_PRESSURE: [
            lambda f: "No single issue explains this bullpen. Depth, workload, and recent shape all have to be held together.",
            lambda f: "The middle of the story is how those pressures stack, not which one wins the headline.",
            lambda f: "That mix matters because one clean answer would miss how the night is tightening.",
        ],
        ARCHETYPE_FLEXIBLE_BULLPEN: [
            lambda f: "The useful part is how spread out the work has been. More arms in the recent mix gives the bullpen multiple ways to cover the same game.",
            lambda f: "There is room to maneuver because the work has not collapsed onto one small group.",
            lambda f: "Flexibility shows up when the bullpen can move innings around without immediately returning to the same pocket.",
        ],
        ARCHETYPE_RUN_PREVENTION_MASK: [
            lambda f: "Good results can make the stress harder to see, so the better baseball question is how the innings have been handled underneath.",
            lambda f: "The results matter, but they do not erase how the innings have been distributed lately.",
            lambda f: "The scoreboard can hide the strain; underneath it, the same group may still be taking on a lot.",
        ],
    }
    middle_observation = _sentence(
        _situation_middle_observation(facts, archetype, situation)
        or _contextual_middle_observation(facts, archetype, angle, bullpen_context)
        or _choose(facts, f'{archetype}:middle', pools[archetype])
    )
    return [
        metric,
        middle_observation,
        _identity_texture_sentence(facts),
    ]


def _disclosure_sentence(facts: dict[str, Any]) -> str | None:
    if _disclosure_channel(facts) != _DISCLOSURE_CHANNEL_BODY:
        return None
    options: list[_SentenceBuilder] = [
        lambda f: "The bullpen workload tells the clearest part of the story here.",
        lambda f: f"For {_article_team(f)}, the recent innings tell the clearest part.",
        lambda f: "The recent innings are the cleanest part of the read.",
        lambda f: "What happened on the mound gives the firmest part of the read.",
        lambda f: "Recent innings give the clearest clue here.",
        lambda f: "The innings tell the story better than the roster edges.",
    ]
    return _sentence(_choose(facts, 'disclosure:narrative', options))


def _ending_sentence(facts: dict[str, Any], archetype: str) -> str | None:
    tail = _tail_after_whether(facts.get('watch_question'))
    family = _ending_family(facts, archetype)
    situation = _story_situation(facts, archetype)
    pools: dict[str, dict[str, list[_SentenceBuilder]]] = {
        ARCHETYPE_WORKLOAD_CONCENTRATION: {
            _ENDING_WATCH_QUESTION: [
                lambda f: "Can the workload begin spreading across a wider group?",
                lambda f: "Can more of the bullpen take on the work, or does it stay with the same arms?",
            ],
            _ENDING_IMPLICATION: [
                lambda f: "That shape leaves little margin if the workload stays concentrated.",
                lambda f: "That kind of concentration makes every clean inning behind the main group matter.",
            ],
        },
        ARCHETYPE_THIN_TRUSTED_GROUP: {
            _ENDING_WATCH_QUESTION: [
                lambda f: "Can the biggest innings widen beyond the first few choices?",
                lambda f: "Can more usable arms become comfortable choices before the game gets tight?",
            ],
            _ENDING_IMPLICATION: [
                lambda f: "That leaves a narrower bridge to the late innings than the roster sheet suggests.",
                lambda f: "The gap between available arms and comfortable innings is where the pressure sits.",
            ],
        },
        ARCHETYPE_CAPACITY_CONSTRAINT: {
            _ENDING_CLOSING_OBSERVATION: [
                lambda f: "That leaves fewer comfortable pivots if the game asks for extra relief outs.",
                lambda f: "The bullpen still has a plan, but the back side of that plan is thinner.",
            ],
            _ENDING_IMPLICATION: [
                lambda f: "That shape leaves little margin once the game starts asking for extra outs.",
                lambda f: "The pressure is not only the first move; it is what is left behind it.",
            ],
        },
        ARCHETYPE_ROTATION_SPILLOVER: {
            _ENDING_WATCH_QUESTION: [
                lambda f: "Can the rotation hand off a cleaner game before the bullpen has to cover the middle innings?",
                lambda f: "Can more outs stay with the starter before the relievers take over?",
            ],
            _ENDING_WATCH_STATEMENT: [
                lambda f: "The next turn through the rotation can put a clearer shape on the handoff.",
                lambda f: "The next few games are the reference point for how much work reaches the pen.",
            ],
        },
        ARCHETYPE_STABILITY_EROSION: {
            _ENDING_CLOSING_OBSERVATION: [
                lambda f: "That leaves the group less settled than the availability list alone would show.",
                lambda f: "The important part is the moving target, not just who is listed as available.",
            ],
            _ENDING_WATCH_QUESTION: [
                lambda f: "Does the relief mix start settling, or does it keep moving night to night?",
                lambda f: "Can the bullpen find a steadier shape over the next few games?",
            ],
        },
        ARCHETYPE_STABILITY_RECOVERY: {
            _ENDING_CLOSING_OBSERVATION: [
                lambda f: "That gives the bullpen a more usable shape than it had when the work was tighter.",
                lambda f: "The group looks closer to a normal bridge from the starter to the late plan.",
            ],
            _ENDING_BASEBALL_TAKEAWAY: [
                lambda f: "The main takeaway is balance: the innings are no longer squeezing one small pocket as hard.",
                lambda f: "That is the useful part of the recovery, a bullpen with more than one way through the middle innings.",
            ],
        },
        ARCHETYPE_MULTI_SOURCE_PRESSURE: {
            _ENDING_CLOSING_OBSERVATION: [
                lambda f: "That leaves a night shaped by more than one problem at the same time.",
                lambda f: "The story is not one clean pressure point; it is how those pressures stack.",
            ],
            _ENDING_IMPLICATION: [
                lambda f: "That mix leaves less margin for any one part of the plan to absorb the whole night.",
                lambda f: "When several pressures meet at once, the bullpen can look tighter even before the late innings.",
            ],
        },
        ARCHETYPE_FLEXIBLE_BULLPEN: {
            _ENDING_BASEBALL_TAKEAWAY: [
                lambda f: "That gives the staff more than one way to get through a game.",
                lambda f: "That is real flexibility: the work has not collapsed onto one small group.",
            ],
            _ENDING_CLOSING_OBSERVATION: [
                lambda f: "This is a bullpen with room to move innings around.",
                lambda f: "The shape is wider than a bullpen leaning on the same few arms every night.",
            ],
        },
        ARCHETYPE_RUN_PREVENTION_MASK: {
            _ENDING_WATCH_QUESTION: [
                lambda f: "Does the workload start lining up with the results, or does stress stay underneath them?",
                lambda f: "Can the usage underneath start looking as steady as the results?",
            ],
            _ENDING_IMPLICATION: [
                lambda f: "That shape keeps the strong results from being the whole story.",
                lambda f: "Good run prevention helps, but it does not erase how much work the same group has been absorbing.",
            ],
        },
    }
    situation_pools: dict[str, list[_SentenceBuilder]] = {
        SITUATION_FIRST_MOVE_OK_THEN_THIN: [
            lambda f: "The pressure is not only the first move; it is how carefully they have to manage the next one.",
            lambda f: "That leaves the staff managing the second and third answers more carefully than the first.",
        ],
        SITUATION_LATE_INNINGS_STABLE_MIDDLE_TESTED: [
            lambda f: "That gives the staff more than one way to get through a game.",
            lambda f: "That is useful flexibility: the late plan still has somewhere to land.",
        ],
        SITUATION_FULL_BOARD_CLOSE_GAME_QUESTIONS: [
            lambda f: "That makes close-game fit more important than the size of the board.",
            lambda f: "The game can look covered before it starts asking which arms fit the biggest innings.",
        ],
        SITUATION_RESULTS_GOOD_PATH_NARROWING: [
            lambda f: "That shape keeps the strong results from being the whole story.",
            lambda f: "Good run prevention helps, but it does not erase how tight the margin has become.",
            lambda f: "The results help, but they do not make the bullpen beneath them feel deeper.",
            lambda f: "The line is doing its job; the bullpen underneath still deserves a closer look.",
        ],
        SITUATION_SAME_FEW_CARRYING_TIGHT_SPOTS: [
            lambda f: "That kind of concentration makes every clean inning behind the main group matter.",
            lambda f: "That leaves little margin if the same few names keep carrying the tight spots.",
        ],
        SITUATION_ENOUGH_BODIES_NOT_ENOUGH_COMFORT: [
            lambda f: "The gap between available arms and comfortable innings is where the pressure sits.",
            lambda f: "That leaves less margin once the game moves past the first comfortable choices.",
            lambda f: "That gap between bodies and comfort can matter quickly if the night gets messy.",
            lambda f: "That leaves little margin once the first few choices are gone.",
            lambda f: "Can the comfortable part of the bullpen widen before the game gets tight?",
            lambda f: "Can more of the bullpen become usable before the first few choices are gone?",
        ],
        SITUATION_FLEXIBILITY_WORK_SPREAD_OUT: [
            lambda f: "That gives the staff more than one way to get through a game.",
            lambda f: "That is the useful part of the flexibility, a game that does not have to keep returning to one answer.",
        ],
        SITUATION_DEPTH_STRAIN_HIDDEN_BY_TOP_END: [
            lambda f: "That mix leaves less margin for the bridge into the late innings.",
            lambda f: "When several pressures meet at once, the bullpen can look tighter even before the late innings.",
        ],
        SITUATION_WORKLOAD_SPREAD_TRUST_UNEVEN: [
            lambda f: "The gap between available arms and comfortable innings is where the pressure sits.",
            lambda f: "That gap between available arms and comfortable innings can matter more than the size of the board.",
            lambda f: "Can more usable arms become comfortable choices before the game gets tight?",
        ],
        SITUATION_ROTATION_HANDOFF_STRETCHING_PEN: [
            lambda f: "The next few games are the reference point for how much work reaches the pen.",
            lambda f: "The next turn through the rotation can put a clearer shape on the handoff.",
        ],
        SITUATION_ROOM_FOR_ERROR_NARROWING: [
            lambda f: "That leaves the group less settled than the availability list alone would show.",
            lambda f: "The important part is the moving target, not just who is listed as available.",
        ],
        SITUATION_ROOM_FOR_ERROR_RETURNING: [
            lambda f: "That gives the bullpen a more usable shape than it had when the work was tighter.",
            lambda f: "That is the useful part of the recovery, a bullpen with more than one way through the middle innings.",
        ],
        SITUATION_PRESSURES_STACKING_IN_GAME_PATH: [
            lambda f: "That mix leaves less margin for any one part of the plan to absorb the whole night.",
            lambda f: "When several pressures meet at once, the bullpen can look tighter even before the late innings.",
        ],
    }
    if situation == SITUATION_LATE_INNINGS_STABLE_MIDDLE_TESTED and archetype == ARCHETYPE_THIN_TRUSTED_GROUP:
        options = [
            lambda f: "Can the comfortable part of the bridge widen before the game gets tight?",
            lambda f: "The gap between the late plan and the innings before it is where the pressure sits.",
        ]
    elif situation == SITUATION_ENOUGH_BODIES_NOT_ENOUGH_COMFORT and archetype in {
        ARCHETYPE_CAPACITY_CONSTRAINT,
        ARCHETYPE_MULTI_SOURCE_PRESSURE,
    }:
        options = [
            lambda f: "The gap between available arms and comfortable innings is where the pressure sits.",
            lambda f: "That leaves less margin once the game moves past the first comfortable choices.",
            lambda f: "That gap between bodies and comfort can matter quickly if the night gets messy.",
            lambda f: "That leaves little margin once the first few choices are gone.",
        ]
    else:
        options = list(situation_pools.get(situation, pools[archetype][family]))
    if tail and family == _ENDING_WATCH_STATEMENT:
        options.append(lambda f: f"The next few games are the cleanest place to see whether {tail}.")
    return _sentence(_choose(facts, f'{archetype}:ending:{situation}:{family}', options))


def _paragraph(sentences: list[str | None]) -> str | None:
    cleaned: list[str] = []
    seen = set()
    for sentence in sentences:
        sentence = _sentence(sentence)
        if not sentence:
            continue
        key = sentence.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(sentence)
    if not cleaned:
        return None
    return ' '.join(cleaned)


def render_story_disclosure_note(facts: dict[str, Any]) -> str | None:
    """Render a short public disclosure note without changing canonical facts."""

    if _disclosure_channel(facts) != _DISCLOSURE_CHANNEL_FOOTER:
        return None
    options: list[_SentenceBuilder] = [
        lambda f: "Usage provides the strongest signal here.",
        lambda f: "The workload picture is clearer than the roster picture.",
        lambda f: "There are still roster questions around the edges.",
        lambda f: "The read is strongest on recent usage.",
    ]
    return _sentence(_choose(facts, 'disclosure:note', options))


def render_story_narrative(facts: dict[str, Any]) -> str:
    """Render a natural two-to-three paragraph baseball story."""

    archetype = select_story_archetype(facts)
    observation = _clean_text(facts.get('evidence_statement'))
    opening = _paragraph([
        observation if observation else _opening_sentence(facts, archetype),
    ])
    middle = _paragraph(_middle_sentences(facts, archetype))
    closing = _paragraph([
        _disclosure_sentence(facts),
        facts.get('consequence_statement'),
        _ending_sentence(facts, archetype),
    ])

    paragraphs = [item for item in (opening, middle, closing) if item]
    if not paragraphs:
        return ''
    return '\n\n'.join(paragraphs)


def narrative_contains_forbidden_language(narrative: str) -> bool:
    text = narrative or ''
    lower = text.lower()
    labels = {label.lower() for label in FORBIDDEN_PUBLIC_LABELS}
    terms = {term.lower() for term in INTERNAL_TAXONOMY_TERMS}
    return any(label in text for label in FORBIDDEN_PUBLIC_LABELS) or any(term in lower for term in labels | terms)


__all__ = [
    'CAPABILITY',
    'VERSION',
    'ARCHETYPE_WORKLOAD_CONCENTRATION',
    'ARCHETYPE_THIN_TRUSTED_GROUP',
    'ARCHETYPE_CAPACITY_CONSTRAINT',
    'ARCHETYPE_ROTATION_SPILLOVER',
    'ARCHETYPE_STABILITY_EROSION',
    'ARCHETYPE_STABILITY_RECOVERY',
    'ARCHETYPE_MULTI_SOURCE_PRESSURE',
    'ARCHETYPE_FLEXIBLE_BULLPEN',
    'ARCHETYPE_RUN_PREVENTION_MASK',
    'FORBIDDEN_PUBLIC_LABELS',
    'INTERNAL_TAXONOMY_TERMS',
    'narrative_contains_forbidden_language',
    'render_story_disclosure_note',
    'render_story_narrative',
    'select_story_archetype',
]
