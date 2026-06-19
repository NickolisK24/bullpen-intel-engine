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
        ('preferred group', 'trusted group'),
        ('preferred lane', 'trusted lane'),
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

    if archetype == ARCHETYPE_WORKLOAD_CONCENTRATION and clustered:
        arms, share = clustered
        options: list[_SentenceBuilder] = [
            lambda f: f"The recent workload shows it: the top {arms} relievers have handled {share}% of the relief pitches in the window.",
            lambda f: f"The work has been bunched together, with {share}% of the recent relief pitches going through the top {arms} relievers.",
            lambda f: f"The pitch distribution says the same thing, with the top {arms} relievers taking {share}% of the recent work.",
        ]
        return _sentence(_choose(facts, f'{archetype}:metric:clustered', options))

    if archetype == ARCHETYPE_CAPACITY_CONSTRAINT and availability:
        available, total = availability
        options = [
            lambda f: f"The count matters here: {available} of {total} bullpen arms are available tonight.",
            lambda f: f"The usable layer is smaller than a full bullpen board, with {available} of {total} arms available.",
            lambda f: f"In baseball terms, this starts with depth, because the available group is {available} of {total} arms.",
        ]
        return _sentence(_choose(facts, f'{archetype}:metric:availability', options))

    if archetype == ARCHETYPE_FLEXIBLE_BULLPEN and broad:
        arms, pitches = broad
        options = [
            lambda f: f"The recent work has been spread across {arms} relievers, which gives the bullpen more than one path through the game.",
            lambda f: f"The work is not leaning on one small group, with {arms} relievers sharing the recent load.",
            lambda f: f"That flexibility comes from how the innings have been spread around, with {arms} relievers involved lately.",
        ]
        if pitches:
            options.append(
                lambda f: f"The recent work has been spread across {arms} relievers at about {pitches} pitches per participating arm."
            )
        return _sentence(_choose(facts, f'{archetype}:metric:broad', options))

    if archetype == ARCHETYPE_RUN_PREVENTION_MASK:
        supporting = _public_language(facts.get('supporting_context'))
        if supporting:
            options = [
                lambda f: "The results still matter, but recent usage tells a different story underneath them.",
                lambda f: "The scoreboard does not tell the whole story; recent usage can make good results feel a little thinner.",
                lambda f: "The results still look good on the surface, but recent usage keeps the bullpen picture from being that simple.",
            ]
            return _sentence(_choose(facts, f'{archetype}:metric:run-prevention', options))

    if clustered:
        arms, share = clustered
        return _sentence(f"The top {arms} relievers have handled {share}% of the recent relief work.")
    if broad:
        arms, pitches = broad
        if pitches:
            return _sentence(f"Recent relief work has been spread across {arms} relievers at about {pitches} pitches per participating arm.")
        return _sentence(f"Recent relief work has moved through {arms} relievers.")
    return None


def _opening_sentence(facts: dict[str, Any], archetype: str) -> str:
    article = _article_team(facts)
    possessive = _possessive_team(facts)

    pools: dict[str, list[_SentenceBuilder]] = {
        ARCHETYPE_WORKLOAD_CONCENTRATION: [
            lambda f: f"A small group is carrying most of the relief work for {article} right now.",
            lambda f: f"{possessive} bullpen story starts with concentration, not the full arm count.",
            lambda f: f"The workload story for {article} is about how often the same relievers are taking the ball.",
            lambda f: f"For {article}, the bullpen story is the same group getting pulled back into the game.",
        ],
        ARCHETYPE_THIN_TRUSTED_GROUP: [
            lambda f: f"Available innings may not be the main challenge for {article}; trusted innings are tighter.",
            lambda f: f"{possessive} bullpen has arms to consider, but the late-inning lane is narrower.",
            lambda f: f"For {article}, the count of usable arms does not fully answer the trust question.",
        ],
        ARCHETYPE_CAPACITY_CONSTRAINT: [
            lambda f: f"The bullpen picture for {article} starts with fewer comfortable options than usual.",
            lambda f: f"{possessive} relief situation is about depth before anything else.",
            lambda f: f"For {article}, the tight part of the bullpen board is how quickly the usable layer thins out.",
        ],
        ARCHETYPE_ROTATION_SPILLOVER: [
            lambda f: f"{possessive} bullpen has recently been asked to absorb more of the game.",
            lambda f: f"The relief story for {article} starts before the bullpen gate opens.",
            lambda f: f"For {article}, starter length is part of tonight's bullpen picture.",
        ],
        ARCHETYPE_STABILITY_EROSION: [
            lambda f: f"{possessive} bullpen picture is less settled than a simple arm count suggests.",
            lambda f: f"For {article}, the recent relief mix has been moving around.",
            lambda f: f"The bullpen story for {article} starts with a group that has not looked the same every night.",
        ],
        ARCHETYPE_STABILITY_RECOVERY: [
            lambda f: f"{possessive} bullpen picture starts with a group looking more settled over the recent games.",
            lambda f: f"For {article}, the relief picture has a little more footing than it did before.",
            lambda f: f"{possessive} bullpen story is about a usage shape that is starting to settle.",
        ],
        ARCHETYPE_MULTI_SOURCE_PRESSURE: [
            lambda f: f"{possessive} bullpen pressure is arriving from more than one direction.",
            lambda f: f"For {article}, more than one thing is shaping this bullpen right now.",
            lambda f: f"The current bullpen picture for {article} has multiple pressure points meeting at once.",
        ],
        ARCHETYPE_FLEXIBLE_BULLPEN: [
            lambda f: f"{possessive} bullpen enters tonight with room to maneuver.",
            lambda f: f"For {article}, the useful part of the picture is flexibility.",
            lambda f: f"{possessive} bullpen picture starts with more than one workable path.",
        ],
        ARCHETYPE_RUN_PREVENTION_MASK: [
            lambda f: f"{possessive} results still look sturdy, but the workload underneath still matters.",
            lambda f: f"For {article}, good run prevention is not the whole bullpen story.",
            lambda f: f"The scoreboard says one thing for {possessive} bullpen; recent usage adds another layer.",
        ],
    }
    return _sentence(_choose(facts, f'{archetype}:opening', pools[archetype])) or ''


def _middle_sentences(facts: dict[str, Any], archetype: str) -> list[str | None]:
    metric = _metric_sentence(facts, archetype)
    pools: dict[str, list[_SentenceBuilder]] = {
        ARCHETYPE_WORKLOAD_CONCENTRATION: [
            lambda f: "That makes the story less about the full bullpen count and more about how tightly the work has collected.",
            lambda f: "The same group keeps taking on most of the work.",
            lambda f: "The names on the board matter less than who keeps getting called on.",
        ],
        ARCHETYPE_THIN_TRUSTED_GROUP: [
            lambda f: "The split is between arms who are merely usable and arms who fit the innings a club usually protects.",
            lambda f: "That is why the raw arm count can overstate the amount of late-game comfort on the board.",
            lambda f: "The middle of the story is trust, not volume: the lane narrows when leverage starts to matter.",
        ],
        ARCHETYPE_CAPACITY_CONSTRAINT: [
            lambda f: "This is a depth problem in baseball terms: the next clean inning can matter as much as the late plan.",
            lambda f: "The squeeze is not just who is available, but how many comfortable pivots remain if the game asks for extra relief outs.",
            lambda f: "The bullpen can still have a plan, but there is less margin behind the first few choices.",
        ],
        ARCHETYPE_ROTATION_SPILLOVER: [
            lambda f: "Starter length is the background. When more outs keep landing on the pen, the same availability count carries a different weight.",
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
            lambda f: "No single issue explains the whole bullpen picture. Depth, workload, and recent bullpen shape all have to be held together.",
            lambda f: "The middle of the story is how those pressures stack, not which one wins the headline.",
            lambda f: "That mix matters because one clean answer would miss how the bullpen picture is tightening.",
        ],
        ARCHETYPE_FLEXIBLE_BULLPEN: [
            lambda f: "The useful part is how spread out the work has been. More arms in the recent path gives the bullpen multiple ways to cover the same game.",
            lambda f: "There is room to maneuver because the work has not collapsed onto one small group.",
            lambda f: "Flexibility shows up when the bullpen can move innings around without immediately returning to the same pocket.",
        ],
        ARCHETYPE_RUN_PREVENTION_MASK: [
            lambda f: "Good results can make the stress harder to see, so the better baseball question is how the innings have been handled underneath.",
            lambda f: "The results matter, but they do not erase how the innings have been distributed lately.",
            lambda f: "The scoreboard can hide the strain; underneath it, the same group may still be taking on a lot.",
        ],
    }
    return [
        metric,
        _sentence(_choose(facts, f'{archetype}:middle', pools[archetype])),
    ]


def _disclosure_sentence(facts: dict[str, Any]) -> str | None:
    if _disclosure_channel(facts) != _DISCLOSURE_CHANNEL_BODY:
        return None
    options: list[_SentenceBuilder] = [
        lambda f: "The cleanest takeaway is still how the innings have been handled, not a guess at the full roster picture.",
        lambda f: "The roster context is not complete enough to go beyond the usage pattern.",
        lambda f: "This stays focused on how the work has been distributed, because that is the clearest part of the bullpen picture.",
        lambda f: "The safer read is what has happened on the mound, not an assumption about every roster variable.",
    ]
    return _sentence(_choose(facts, 'disclosure:narrative', options))


def _watch_sentence(facts: dict[str, Any], archetype: str) -> str | None:
    tail = _tail_after_whether(facts.get('watch_question'))
    pools: dict[str, list[_SentenceBuilder]] = {
        ARCHETYPE_WORKLOAD_CONCENTRATION: [
            lambda f: "Can the workload spread to more of the group, or does it keep collecting around the same arms?",
            lambda f: "The next question is whether the innings start moving through a wider lane.",
            lambda f: "From here, watch whether the same relievers stay at the center of the work.",
        ],
        ARCHETYPE_THIN_TRUSTED_GROUP: [
            lambda f: "Can the trusted lane widen without turning back to the same relievers?",
            lambda f: "The next question is whether usable arms can also become trusted innings.",
            lambda f: "What matters next is whether the late-inning path gets wider or stays narrow.",
        ],
        ARCHETYPE_CAPACITY_CONSTRAINT: [
            lambda f: "Can another usable option emerge before the bullpen has to cover extra outs?",
            lambda f: "The next question is whether the available layer gains any room behind the first few choices.",
            lambda f: "From here, the question is whether the bullpen can find one more comfortable lane.",
        ],
        ARCHETYPE_ROTATION_SPILLOVER: [
            lambda f: "Will starters cover more innings and give the pen a cleaner night?",
            lambda f: "The next question is whether more outs stay with the rotation before the bullpen takes over.",
            lambda f: "From here, the question is whether the relief group gets a lighter handoff.",
        ],
        ARCHETYPE_STABILITY_EROSION: [
            lambda f: "Does the bullpen picture settle down, or does it keep changing from night to night?",
            lambda f: "The next question is whether the same group starts appearing more often.",
            lambda f: "What becomes interesting is whether the recent pattern steadies.",
        ],
        ARCHETYPE_STABILITY_RECOVERY: [
            lambda f: "Can that steadier shape hold after another game worth of bullpen choices?",
            lambda f: "The next question is whether the broader rhythm survives the next bullpen-heavy night.",
            lambda f: "From here, the question is whether the relief mix keeps looking settled.",
        ],
        ARCHETYPE_MULTI_SOURCE_PRESSURE: [
            lambda f: "Which part of the bullpen picture eases first: depth, starter length, or the usage mix?",
            lambda f: "The next question is whether one pressure point clears enough to simplify the board.",
            lambda f: "From here, the question is whether the bullpen story narrows back to one main issue.",
        ],
        ARCHETYPE_FLEXIBLE_BULLPEN: [
            lambda f: "Can this flexibility hold if the game asks for multiple relief lanes?",
            lambda f: "The next question is whether the work stays spread out.",
            lambda f: "From here, the bullpen picture is worth watching to see whether the wider shape holds.",
        ],
        ARCHETYPE_RUN_PREVENTION_MASK: [
            lambda f: "Does the workload start lining up with the results, or does stress stay underneath them?",
            lambda f: "The next question is whether the recent usage starts to look as sturdy as the results.",
            lambda f: "From here, the question is whether the good results get more support from the workload shape.",
        ],
    }
    if tail:
        pools[archetype].append(lambda f: f"One more useful check is whether {tail}.")
    return _sentence(_choose(facts, f'{archetype}:watch', pools[archetype]))


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
        lambda f: "Limited roster context.",
        lambda f: "Partial bullpen context.",
        lambda f: "Roster context not complete.",
        lambda f: "Source context is limited.",
    ]
    return _sentence(_choose(facts, 'disclosure:note', options))


def render_story_narrative(facts: dict[str, Any]) -> str:
    """Render a natural two-to-three paragraph baseball story."""

    archetype = select_story_archetype(facts)
    opening = _paragraph([_opening_sentence(facts, archetype)])
    middle = _paragraph(_middle_sentences(facts, archetype))
    closing = _paragraph([
        _disclosure_sentence(facts),
        _watch_sentence(facts, archetype),
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
