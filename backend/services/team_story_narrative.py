"""Narrative renderer for normalized team story facts."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Callable


CAPABILITY = 'team_story_narrative_renderer_v2'
VERSION = '2026-06-18.v2'

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
)

_SentenceBuilder = Callable[[dict[str, Any]], str]


def _clean_text(value: Any) -> str:
    return ' '.join(str(value or '').strip().split())


def _sentence(value: Any) -> str | None:
    text = _public_language(value)
    if not text:
        return None
    if text[-1] not in '.!?':
        text = f'{text}.'
    return text


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
    ]
    return ' '.join(_public_language(value).lower() for value in values if value)


def _opening_family(facts: dict[str, Any]) -> str:
    text = _all_fact_text(facts)
    if facts.get('environment_context'):
        return 'environment'
    if 'season run-prevention' in text or 'run prevention' in text:
        return 'run_prevention'
    if facts.get('capacity_context') or 'thin usable layer' in text or ('only ' in text and ' available' in text):
        return 'capacity'
    if facts.get('rotation_context'):
        return 'rotation'
    if facts.get('stability_context'):
        return 'stability'
    if 'spread across' in text or 'broad' in text or 'deeper usable layer' in text:
        return 'broad'
    if 'trusted late-inning' in text:
        return 'trust'
    if 'clustered' in text or 'concentrated' in text or 'smaller set' in text or 'narrow' in text:
        return 'narrow'
    return 'default'


def _opening_sentence(facts: dict[str, Any]) -> str | None:
    family = _opening_family(facts)
    article = _article_team(facts)
    possessive = _possessive_team(facts)
    team = _team_name(facts)

    pools: dict[str, list[_SentenceBuilder]] = {
        'narrow': [
            lambda f: f"{possessive} bullpen enters tonight with recent relief work tilted toward a smaller group.",
            lambda f: f"For {article}, the bullpen story starts with pressure moving toward a tighter relief lane.",
            lambda f: f"The current {team} bullpen picture starts with a narrower workload shape.",
            lambda f: f"One of the more interesting bullpen reads tonight is how {article} is carrying recent relief work through fewer arms.",
        ],
        'broad': [
            lambda f: f"{possessive} bullpen enters tonight with more of the recent work spread across the group.",
            lambda f: f"For {article}, the bullpen story is a broader path through the relief mix.",
            lambda f: f"The current {team} bullpen picture starts with a little more room to maneuver.",
            lambda f: f"One of the cleaner bullpen reads tonight is {article} keeping the work from collapsing onto one small lane.",
        ],
        'capacity': [
            lambda f: f"{possessive} bullpen enters tonight with the usable layer carrying the main tension.",
            lambda f: f"For {article}, the bullpen story is less about the headline shape and more about how much usable depth is left.",
            lambda f: f"The current {team} bullpen picture starts with how thin the available layer looks behind the results.",
            lambda f: f"One of the more important bullpen reads tonight is how much room {article} has behind the first few lanes.",
        ],
        'rotation': [
            lambda f: f"{possessive} bullpen enters tonight with recent starter support adding to the relief read.",
            lambda f: f"For {article}, the bullpen story is tied to how much of the game the pen has had to cover.",
            lambda f: f"The current {team} bullpen picture starts with the innings that have been landing on the relief group.",
            lambda f: f"One of the more interesting bullpen reads tonight is how starter length has shaped {possessive} relief workload.",
        ],
        'stability': [
            lambda f: f"{possessive} bullpen enters tonight with the relief mix looking less settled than a simple count suggests.",
            lambda f: f"For {article}, the bullpen story includes how often the recent mix has shifted.",
            lambda f: f"The current {team} bullpen picture starts with a group that has not been the same every night.",
            lambda f: f"One of the more interesting bullpen reads tonight is how {article} has been moving innings through a changing group.",
        ],
        'environment': [
            lambda f: f"{possessive} bullpen enters tonight with more than one pressure point shaping the read.",
            lambda f: f"For {article}, the bullpen story is not coming from just one part of the picture.",
            lambda f: f"The current {team} bullpen picture starts with several sources tightening at once.",
            lambda f: f"One of the more interesting bullpen reads tonight is how multiple pressures are meeting in {possessive} relief group.",
        ],
        'run_prevention': [
            lambda f: f"{possessive} bullpen enters tonight with strong results sitting next to a workload question.",
            lambda f: f"For {article}, the bullpen story is the split between the run-prevention line and the recent relief ask.",
            lambda f: f"The current {team} bullpen picture starts with results that look sturdier than the workload underneath.",
            lambda f: f"One of the more interesting bullpen reads tonight is how {article} is pairing run prevention with recent usage.",
        ],
        'trust': [
            lambda f: f"{possessive} bullpen enters tonight with the late-inning lane carrying extra importance.",
            lambda f: f"For {article}, the bullpen story starts with how much of the read runs through the trusted late-inning group.",
            lambda f: f"The current {team} bullpen picture starts with the trusted lane and how much sits behind it.",
            lambda f: f"One of the more interesting bullpen reads tonight is whether {article} has enough support behind the trusted lane.",
        ],
        'default': [
            lambda f: f"{possessive} bullpen has a live read tonight.",
            lambda f: f"For {article}, the bullpen story starts with the recent usage shape.",
            lambda f: f"The current {team} bullpen picture starts with how the relief work has been distributed.",
        ],
    }
    return _sentence(_choose(facts, f'opening:{family}', pools[family]))


def _supporting_context_sentence(facts: dict[str, Any]) -> str | None:
    text = _public_language(facts.get('supporting_context'))
    if not text:
        return None
    lower = text.lower()
    clustered = re.search(
        r'top\s+(\d+)\s+relievers?.*?handled\s+(\d+)%.*?while\s+(\d+)\s+of\s+(\d+)\s+bullpen arms are available',
        lower,
    )
    if clustered:
        top_arms, top_share, available, total = clustered.groups()
        options: list[_SentenceBuilder] = [
            lambda f: (
                f"The recent innings have not been spread evenly: the top {top_arms} "
                f"relievers have handled {top_share}% of the relief pitches, with {available} "
                f"of {total} arms available."
            ),
            lambda f: (
                f"That read is rooted in distribution, with {top_share}% of recent relief "
                f"work going to the top {top_arms} relievers and {available} of {total} "
                "arms available."
            ),
            lambda f: (
                f"The underlying shape is tight: {available} of {total} arms are available, "
                f"and the top {top_arms} relievers have taken {top_share}% of the recent relief work."
            ),
        ]
        return _sentence(_choose(facts, 'supporting:clustered', options))

    broad = re.search(
        r'spread across\s+(\d+)\s+relievers?.*?averaging\s+([\d.]+)\s+pitches',
        lower,
    )
    if broad:
        participants, per_arm = broad.groups()
        options = [
            lambda f: (
                f"The base of the read is distribution: {participants} relievers have shared "
                f"the work at about {per_arm} pitches per participating arm."
            ),
            lambda f: (
                f"That comes from a wider workload map, with {participants} relievers involved "
                f"and no single arm carrying the whole recent picture."
            ),
            lambda f: (
                f"The recent work has been more spread out, with {participants} relievers "
                f"averaging {per_arm} pitches apiece in the window."
            ),
        ]
        return _sentence(_choose(facts, 'supporting:broad', options))

    if 'season run prevention' in lower or 'run prevention' in lower:
        options = [
            lambda f: "That read is grounded in the split between the results line and the recent workload ask.",
            lambda f: "The results line is part of the story, but the recent usage still has to be read on its own.",
            lambda f: "The run-prevention line gives the bullpen some cover, while the workload trail explains why the read is not finished there.",
        ]
        return _sentence(_choose(facts, 'supporting:run_prevention', options))

    return _sentence(text)


def _pressure_sentence(facts: dict[str, Any]) -> str | None:
    text = _public_language(facts.get('pressure_source'))
    if not text:
        return None
    lower = text.lower()
    if 'heavier usage flag' in lower or 'heavier workload flag' in lower:
        options = [
            lambda f: "The heavier part of the read is recent work landing on arms that already carry a larger usage marker.",
            lambda f: "A lot of the strain sits in the same place: the recent workload has found arms that were already carrying more.",
            lambda f: "The workload trail matters here because some of the same arms are already on the heavier side of the usage read.",
        ]
        return _sentence(_choose(facts, 'pressure:fatigue', options))
    if 'trusted late-inning layer' in lower:
        options = [
            lambda f: "The late-inning layer is doing more of the explaining, especially where the trusted group and the usable group do not fully overlap.",
            lambda f: "Part of the squeeze is late-inning trust: the cleanest lane is not as wide as the full bullpen count.",
            lambda f: "The read tightens around the trusted lane, where usable arms and high-leverage comfort are not the same thing.",
        ]
        return _sentence(_choose(facts, 'pressure:trust', options))
    if 'concentrated' in lower or 'smaller set' in lower or 'smaller usable group' in lower:
        options = [
            lambda f: "The recent work has been gathering around fewer relievers, which makes the board feel tighter than the raw arm count.",
            lambda f: "The shape is coming from concentration: the same part of the bullpen has been asked to absorb a larger share.",
            lambda f: "The narrow lane is the point, with recent innings finding a smaller group more often.",
        ]
        return _sentence(_choose(facts, 'pressure:concentration', options))
    if 'spread across more' in lower or 'workload distribution' in lower:
        options = [
            lambda f: "The shape is coming from distribution rather than one narrow lane.",
            lambda f: "What backs the read is the way recent work has moved through more of the group.",
            lambda f: "The workload map is doing the work here, with more relievers involved in the recent path.",
        ]
        return _sentence(_choose(facts, 'pressure:distribution', options))
    if 'thinner usable layer' in lower or 'usable depth' in lower:
        options = [
            lambda f: "The pinch point is usable depth behind the late-inning plan.",
            lambda f: "The available layer is the part that makes the read tighter.",
            lambda f: "The bullpen count is less important than how many of those arms look usable right now.",
        ]
        return _sentence(_choose(facts, 'pressure:capacity', options))
    if 'deeper usable layer' in lower:
        options = [
            lambda f: "The useful part of the read is the depth behind the late-inning plan.",
            lambda f: "There is more room in the usable layer than the average stressed bullpen read.",
            lambda f: "The board has more than one path because the usable layer is not as thin.",
        ]
        return _sentence(_choose(facts, 'pressure:depth', options))
    if 'run-prevention' in lower or 'run prevention' in lower:
        options = [
            lambda f: "The results line belongs in the read, but it does not erase the workload picture.",
            lambda f: "Run prevention is part of the story, while recent usage explains why the bullpen still needs a closer look.",
            lambda f: "The season line gives the bullpen one kind of cushion; the recent workload gives it another kind of question.",
        ]
        return _sentence(_choose(facts, 'pressure:run_prevention', options))
    return _sentence(text)


def _workload_sentence(facts: dict[str, Any]) -> str | None:
    text = _public_language(facts.get('workload_pattern'))
    if not text:
        return None
    lower = text.lower()
    narrow = re.search(r'top\s+(\d+)\s+relievers?.*?taken\s+(\d+)%', lower)
    if narrow:
        top_arms, top_share = narrow.groups()
        options: list[_SentenceBuilder] = [
            lambda f: f"That concentration shows up in the workload ledger, with the top {top_arms} relievers taking {top_share}% of the recent relief work.",
            lambda f: f"The usage trail is narrow enough to matter: {top_share}% of the recent work has gone through the top {top_arms} relievers.",
            lambda f: f"That is a smaller-lane workload shape, with the top {top_arms} relievers absorbing {top_share}% of the recent relief work.",
        ]
        return _sentence(_choose(facts, 'workload:narrow', options))

    broad = re.search(r'(\d+)\s+relievers have shared.*?([\d.]+)\s+pitches', lower)
    if broad:
        participants, per_arm = broad.groups()
        options = [
            lambda f: f"The recent workload has more balance to it, with {participants} relievers sharing the work at {per_arm} pitches per participating arm.",
            lambda f: f"The usage trail is broader: {participants} relievers have been involved, and the per-arm load sits around {per_arm} pitches.",
            lambda f: f"That gives the read a wider base, with {participants} relievers carrying the recent work instead of one small pocket.",
        ]
        return _sentence(_choose(facts, 'workload:broad', options))

    if 'too thin' in lower:
        options = [
            lambda f: "The recent sample is thin enough that the read should stay modest.",
            lambda f: "There is not enough recent workload to make a bigger claim from usage alone.",
            lambda f: "The usage trail is light, so the story has to stay narrower.",
        ]
        return _sentence(_choose(facts, 'workload:thin_sample', options))
    return _sentence(text)


def _capacity_sentence(facts: dict[str, Any]) -> str | None:
    text = _public_language(facts.get('capacity_context'))
    if not text:
        return None
    lower = text.lower()
    if any(marker in lower for marker in ('fewer usable arms', 'short on usable arms', 'available group', 'less usable depth', 'thin')):
        options = [
            lambda f: "The usable layer is part of the squeeze, with fewer clean paths available if the game asks for repeat relief innings.",
            lambda f: "Capacity is showing up in baseball terms: there are fewer comfortable places to turn if the bullpen has to cover more outs.",
            lambda f: "The depth read is narrower than the roster count, which keeps the bullpen room tighter.",
        ]
        return _sentence(_choose(facts, 'capacity:constrained', options))
    return _sentence(text)


def _rotation_sentence(facts: dict[str, Any]) -> str | None:
    text = _public_language(facts.get('rotation_context'))
    if not text:
        return None
    options = [
        lambda f: "Starter length is part of the background here, because extra outs have recently been finding the relief group.",
        lambda f: "The rotation side matters only as workload pressure: more of the game has been landing on the bullpen.",
        lambda f: "Recent starter support has kept the bullpen more involved than a clean availability count would show.",
    ]
    return _sentence(_choose(facts, 'rotation', options))


def _stability_sentence(facts: dict[str, Any]) -> str | None:
    text = _public_language(facts.get('stability_context'))
    if not text:
        return None
    options = [
        lambda f: "The mix has also been moving around, so the usage trail matters more than a static roster count.",
        lambda f: "There is a stability piece too: recent innings have not always moved through the same exact group.",
        lambda f: "The bullpen has not looked identical night to night, which keeps the read tied to actual usage.",
    ]
    return _sentence(_choose(facts, 'stability', options))


def _environment_sentence(facts: dict[str, Any]) -> str | None:
    text = _public_language(facts.get('environment_context'))
    if not text:
        return None
    options = [
        lambda f: "This does not read like one isolated issue; several pressure points are tightening the bullpen picture at once.",
        lambda f: "The story is layered, with more than one part of the recent bullpen picture adding weight.",
        lambda f: "The read is not coming from a single lane, which is why the workload trail has to be paired with the rest of the bullpen picture.",
    ]
    return _sentence(_choose(facts, 'environment', options))


def _domain_sentences(facts: dict[str, Any]) -> list[str]:
    if facts.get('environment_context'):
        candidates = [
            _environment_sentence(facts),
            _capacity_sentence(facts),
            _rotation_sentence(facts),
            _stability_sentence(facts),
            _workload_sentence(facts),
        ]
    else:
        candidates = [
            _pressure_sentence(facts),
            _capacity_sentence(facts),
            _rotation_sentence(facts),
            _stability_sentence(facts),
            _workload_sentence(facts),
        ]

    sentences: list[str] = []
    seen = set()
    for sentence in candidates:
        if not sentence:
            continue
        key = sentence.lower()
        if key in seen:
            continue
        seen.add(key)
        sentences.append(sentence)
        if len(sentences) >= 2:
            break
    return sentences


def _disclosure_sentence(facts: dict[str, Any]) -> str | None:
    if not facts.get('disclosure'):
        return None
    options: list[_SentenceBuilder] = [
        lambda f: "Because the full bullpen picture is not completely settled, this read stays grounded in usage rather than roster assumptions.",
        lambda f: "The safer read is usage-based: the clearer part is how the innings have been distributed, not every roster variable behind them.",
        lambda f: "That keeps the story focused on workload patterns rather than assuming the entire bullpen picture is known.",
        lambda f: "When part of the bullpen picture is less settled, the cleaner read is the usage trail rather than a full roster assumption.",
    ]
    return _sentence(_choose(facts, 'disclosure:narrative', options))


def _watch_sentence(facts: dict[str, Any]) -> str | None:
    tail = _tail_after_whether(facts.get('watch_question'))
    if not tail:
        return _sentence(facts.get('watch_question'))
    options: list[_SentenceBuilder] = [
        lambda f: f"The next question is whether {tail}.",
        lambda f: f"What becomes interesting from here is whether {tail}.",
        lambda f: f"The next few games should show whether {tail}.",
        lambda f: f"The bullpen picture will be worth watching to see whether {tail}.",
        lambda f: f"From here, the question is whether {tail}.",
    ]
    return _sentence(_choose(facts, 'watch', options))


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

    if not facts.get('disclosure'):
        return None
    options: list[_SentenceBuilder] = [
        lambda f: "Usage-based read; the full bullpen picture is not completely settled.",
        lambda f: "Roster assumptions are limited, so this stays anchored to usage.",
        lambda f: "The clearest evidence here is workload distribution, not every roster variable.",
        lambda f: "Some bullpen variables are less clear, so the public read stays usage-first.",
    ]
    return _sentence(_choose(facts, 'disclosure:note', options))


def render_story_narrative(facts: dict[str, Any]) -> str:
    """Render a natural two-to-three paragraph baseball story."""

    opening = _paragraph([
        _opening_sentence(facts),
        _supporting_context_sentence(facts),
    ])
    supporting = _paragraph(_domain_sentences(facts))
    closing = _paragraph([
        _disclosure_sentence(facts),
        _watch_sentence(facts),
    ])

    paragraphs = [item for item in (opening, supporting, closing) if item]
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
    'FORBIDDEN_PUBLIC_LABELS',
    'INTERNAL_TAXONOMY_TERMS',
    'narrative_contains_forbidden_language',
    'render_story_disclosure_note',
    'render_story_narrative',
]
