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

PURPOSE_OPENING = 'opening'

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
            'The bullpen appears deeper than the current game plan',
            'The available names outnumber the trusted paths',
            'The depth chart looks larger than the route being used',
            "{possessive} roster has more names than comfortable late-inning answers",
            'The bullpen has bodies listed, but fewer obvious places to turn',
            'The roster count is larger than the late-game map',
            '{team} has more relievers on paper than the game plan is using',
            'The bullpen looks deeper in the file than it does in a tight game',
            'The active roster does not give {team} the same number of trusted turns',
            "{possessive} depth is thinner than the roster count first suggests",
            'The practical bullpen picture is smaller than the list of names',
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
}


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
    'BEAT_COVERAGE_PRESSURE',
    'BEAT_DEPTH_CONSTRAINT',
    'BEAT_ROUTE_CHANGE',
    'BEAT_SUSTAINABILITY_QUESTION',
    'CAPABILITY',
    'DENIED_PUBLIC_PHRASES',
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
