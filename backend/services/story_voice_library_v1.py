"""Deterministic surface-voice variants for the four public story beats.

The library owns approved sentence constructions only. It does not interpret
evidence, select stories, score teams, calculate context, or call external text
generation.
"""

from __future__ import annotations

import hashlib
from string import Formatter
from typing import Any


CAPABILITY = 'story_voice_library_v1'
VERSION = '2026-06-21.v1'

BEAT_ROUTE_CHANGE = 'route_change'
BEAT_COVERAGE_PRESSURE = 'coverage_pressure'
BEAT_DEPTH_CONSTRAINT = 'depth_constraint'
BEAT_SUSTAINABILITY_QUESTION = 'sustainability_question'
BEAT_AVAILABILITY_DEPTH = 'availability_depth'
BEAT_TRUST_LANE = 'trust_lane'
BEAT_BRIDGE = 'bridge'

PURPOSE_OPENING = 'opening'
PURPOSE_ELIGIBILITY_CONTEXT = 'eligibility_context'

DENIED_PUBLIC_PHRASES = (
    'sit at the front of',
    'define the first bullpen group',
    'active route',
    'practical path',
    'route count',
    'the first is',
    'the second is',
    'named names',
    'usable relievers',
    'still have multiple ways to cover a close game',
    'not boxed into one relief lane',
    'less room behind the trusted late plan',
    'relief read',
)

BANNED_PUBLIC_LANGUAGE = (
    'bet',
    'betting',
    'odds',
    'probability',
    'projection',
    'projected',
    'predict',
    'prediction',
    'lock',
    'guaranteed',
    'expected to win',
    'will win',
)

VOICE_LIBRARY = {
    BEAT_ROUTE_CHANGE: {
        PURPOSE_OPENING: (
            '{names} remain the first names the game reaches for',
            'The late innings still begin with {names}',
            'The bullpen continues to bend toward {names}',
            '{names} remain the center of the leverage route',
            'The next close game still points toward {names}',
            '{names} remain the hinge of the bullpen plan',
            "{possessive} leverage plan still starts with {names}",
            'When the game tightens, {names} still shape the first call',
            '{names} remain the clearest late-game answers',
            "{possessive} close-game route still runs through {names}",
            '{names} still organize the late innings',
            "{possessive} bullpen has changed around the same leverage center",
            'The roster movement has not moved the late-game center away from {names}',
        ),
    },
    BEAT_COVERAGE_PRESSURE: {
        PURPOSE_OPENING: (
            "{possessive} results remain strong, but the workload is getting heavier",
            "{possessive} bullpen is carrying more of the game than the surface numbers suggest",
            'The run prevention remains steady while the innings burden grows',
            'The ERA tells one story; the workload tells another',
            "The starter handoff is asking more of {possessive} relief group",
            'The bullpen is getting pulled into the game earlier than usual',
            'The recent starts have pushed more innings onto the bullpen',
            'The results still hold for {team}, but the inning burden is less comfortable',
            'The bullpen line looks stable while the coverage job gets harder',
            'The surface result holds; the workload underneath is tighter',
            'The pitching staff is asking the bullpen to cover more middle innings',
            'The game keeps arriving at the bullpen sooner than the baseline',
        ),
    },
    BEAT_DEPTH_CONSTRAINT: {
        PURPOSE_OPENING: (
            'The roster lists more relievers than the bullpen is practically using',
            'The bullpen has bodies listed, but fewer obvious places to turn',
            '{team} has more relievers on paper than the game plan is using',
            '{names} become the pressure point in a thinner late bridge',
            'The late-game map narrows around {names}',
            'The roster count hides how quickly the game gets back to {names}',
        ),
    },
    BEAT_SUSTAINABILITY_QUESTION: {
        PURPOSE_OPENING: (
            'The recent innings keep finding the same arms',
            'The workload continues to land in the same pocket',
            'The route is narrowing around a small group',
            'The same relievers continue carrying the meaningful work',
            'The bullpen keeps asking the same names to absorb the pressure',
            'The workload shape is starting to bunch around {names}',
            'The meaningful innings are collecting around {names}',
            'The burden is still gathering around the same relief pocket',
            "{possessive} recent work keeps circling back to {names}",
            'The late-inning plan is still leaning on {names}',
            'The workload is not spreading far beyond {names}',
            '{names} remain the place the recent pressure keeps landing',
        ),
    },
    BEAT_AVAILABILITY_DEPTH: {
        PURPOSE_OPENING: (
            'The bullpen has more rested options than most clubs today',
            'The late innings give {team} room to spread the work',
            "{possessive} late-inning plan can lean on more than one rested group",
            '{team} carries clean late-inning depth into tonight',
            "{possessive} bullpen has several rested arms to choose from",
            'The bullpen has room to share the late innings tonight',
            'The trusted late group still has rested help around it',
            'The recent innings have spread across more than the top arms',
            "{possessive} late-inning depth runs past the top group",
            'The bullpen can turn to more than one rested arm tonight',
            '{names} anchor a deep, rested late-inning group tonight',
            '{team} can mix and match late without overworking one arm',
            'The bullpen is rested enough to script the late innings more than one way',
        ),
    },
    BEAT_TRUST_LANE: {
        PURPOSE_OPENING: (
            'The bullpen has arms available, but the dependable late-game lane stays a short list',
            'The active board looks full, yet the dependable late-inning work still runs through {names}',
            '{team} has bodies available, but the trusted late-game options stay few',
            "{possessive} available board is wider than its trusted late-inning lane",
            'The bullpen can fill a board, but the clean late-game choices narrow to {names}',
            'The relief group has bodies available while the trusted late-inning lane stays narrow',
            'The dependable late innings still lean on {names} more than the available count suggests',
            "{possessive} trusted late-inning lane is thinner than the available arm count",
            'The available arms outnumber the trusted late-game choices',
            'The bullpen looks stocked, but the dependable late-inning lane holds at a few names',
        ),
    },
    BEAT_BRIDGE: {
        PURPOSE_OPENING: (
            "The bullpen's late-game options remain intact, but the route into those innings is thinner than it appears",
            'The trusted late arms are set, yet the path to reach them runs through a fragile middle',
            "{possessive} late-game core is settled, but the handoff into it is unstable",
            'The late innings are covered; the bridge to them is the soft spot',
            '{team} can finish games, but the road from the starter to the late arms is shaky',
            "{possessive} bullpen is solid at the back, thinner in the bridge",
            'The trusted late group is intact while the middle-relief path stays volatile',
            'The late-game plan holds, but the handoff arms are less certain',
            'The back of the bullpen is settled; the bridge to it is not',
            'The starters are leaving the bullpen a long, unsteady bridge to the late arms',
        ),
    },
}


# Eligibility-aware context lines (Phase C3E). Each qualifies an existing
# forward-constraint beat when Swing/Bulk arms materially shape coverage or
# depth. They are governed surface voice: descriptive only, with no public
# roles, rankings, recommendations, or predictions.
ELIGIBILITY_CONTEXT_LINES = {
    BEAT_COVERAGE_PRESSURE: (
        'Some of that coverage comes from swing and bulk options rather than dedicated relief roles',
    ),
    BEAT_DEPTH_CONSTRAINT: (
        'Part of that depth is tied to swing and bulk usage rather than traditional bullpen roles',
    ),
    BEAT_TRUST_LANE: (
        'The clean late-inning lane is thinner than the raw arm count, with some arms working as swing or bulk options',
    ),
    BEAT_BRIDGE: (
        'Some of the bullpen count is swing or bulk usage, leaving the bridge thinner than the raw total suggests',
    ),
    BEAT_AVAILABILITY_DEPTH: (
        'Some of that depth comes from swing and bulk options rather than dedicated late-inning roles',
    ),
}

for _beat, _forms in ELIGIBILITY_CONTEXT_LINES.items():
    VOICE_LIBRARY.setdefault(_beat, {})[PURPOSE_ELIGIBILITY_CONTEXT] = _forms


class _SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return ''


def _clean_text(value: Any) -> str:
    return ' '.join(str(value or '').strip().split())


def _normalize(value: Any) -> str:
    return _clean_text(value).lower()


def _stable_text(parts: list[Any] | tuple[Any, ...]) -> str:
    return '|'.join(_clean_text(part) for part in parts if _clean_text(part))


def stable_voice_index(parts: list[Any] | tuple[Any, ...], size: int) -> int:
    """Return a reproducible index for stable story identifiers."""

    if size <= 0:
        return 0
    text = _stable_text(parts)
    if not text:
        return 0
    digest = hashlib.sha256(text.encode('utf-8')).hexdigest()
    return int(digest[:12], 16) % size


def approved_sentence_forms(beat: str, purpose: str = PURPOSE_OPENING) -> tuple[str, ...]:
    """Expose approved constructions for tests and audit tooling."""

    return tuple((VOICE_LIBRARY.get(beat) or {}).get(purpose) or ())


def _template_fields(template: str) -> set[str]:
    fields: set[str] = set()
    for _, field_name, _, _ in Formatter().parse(template):
        if field_name:
            fields.add(field_name)
    return fields


def select_voice_template(
    beat: str,
    *,
    purpose: str = PURPOSE_OPENING,
    stable_parts: list[Any] | tuple[Any, ...] = (),
    slots: dict[str, Any] | None = None,
) -> tuple[int, str]:
    """Select one approved template deterministically for the provided inputs."""

    forms = approved_sentence_forms(beat, purpose)
    if not forms:
        return 0, ''
    slots = slots or {}
    usable = [
        template for template in forms
        if all(_clean_text(slots.get(field)) for field in _template_fields(template))
    ]
    forms = tuple(usable or forms)
    index = stable_voice_index((CAPABILITY, VERSION, beat, purpose, *stable_parts), len(forms))
    return index, forms[index]


def render_voice_line(
    beat: str,
    *,
    purpose: str = PURPOSE_OPENING,
    stable_parts: list[Any] | tuple[Any, ...] = (),
    **slots: Any,
) -> str | None:
    """Render one approved voice line with deterministic template selection."""

    _, template = select_voice_template(
        beat,
        purpose=purpose,
        stable_parts=stable_parts,
        slots=slots,
    )
    if not template:
        return None
    rendered = template.format_map(_SafeFormatDict({key: _clean_text(value) for key, value in slots.items()}))
    return _clean_text(rendered)


def contains_denied_public_phrase(text: Any) -> bool:
    lower = _normalize(text)
    return any(phrase in lower for phrase in DENIED_PUBLIC_PHRASES)


def contains_banned_public_language(text: Any) -> bool:
    lower = _normalize(text)
    return any(term in lower for term in BANNED_PUBLIC_LANGUAGE)


def voice_library_report() -> dict[str, Any]:
    """Return compact deterministic metadata for audit tests."""

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'deterministic': True,
        'beats': {
            beat: {
                purpose: {
                    'count': len(forms),
                    'contains_denied_public_phrase': any(
                        contains_denied_public_phrase(form)
                        for form in forms
                    ),
                    'contains_banned_public_language': any(
                        contains_banned_public_language(form)
                        for form in forms
                    ),
                }
                for purpose, forms in purposes.items()
            }
            for beat, purposes in VOICE_LIBRARY.items()
        },
    }


__all__ = [
    'BANNED_PUBLIC_LANGUAGE',
    'BEAT_AVAILABILITY_DEPTH',
    'BEAT_BRIDGE',
    'BEAT_COVERAGE_PRESSURE',
    'BEAT_DEPTH_CONSTRAINT',
    'BEAT_ROUTE_CHANGE',
    'BEAT_SUSTAINABILITY_QUESTION',
    'BEAT_TRUST_LANE',
    'CAPABILITY',
    'DENIED_PUBLIC_PHRASES',
    'ELIGIBILITY_CONTEXT_LINES',
    'PURPOSE_ELIGIBILITY_CONTEXT',
    'PURPOSE_OPENING',
    'VERSION',
    'approved_sentence_forms',
    'contains_banned_public_language',
    'contains_denied_public_phrase',
    'render_voice_line',
    'select_voice_template',
    'stable_voice_index',
    'voice_library_report',
]
