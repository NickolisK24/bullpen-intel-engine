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
PURPOSE_FORWARD = 'forward'

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
            'The roster lists more relievers than the bullpen really trusts late',
            'The bullpen has bodies listed, but fewer arms to call on late',
            '{team} has more relievers on paper than in the late-inning plan',
            '{names} become the pressure point when the bullpen runs short',
            'A long game gets back to {names} in a hurry',
            'The roster count hides how fast a tight game gets back to {names}',
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
            '{team} has plenty of rested arms for the late innings tonight',
            'The bullpen is rested and ready for a close one',
            '{names} headline a rested, ready late-inning group',
            '{team} can mix and match late without overworking anyone',
            'Plenty of fresh arms for the seventh, eighth, and ninth',
            'The bullpen is rested enough to cover the late innings more than one way',
            "{possessive} late-inning depth runs well past the top arm",
            'The manager has real choices late tonight',
            'A full, rested bullpen heading into tonight',
            'The late innings can run through more than one rested arm',
            '{names} lead a deep group of rested options',
            'The bullpen has fresh arms to spare late',
        ),
    },
    BEAT_TRUST_LANE: {
        PURPOSE_OPENING: (
            'The board is full; the late-inning circle of trust is small',
            'Plenty of arms available, few {team} trusts with a lead',
            'The late innings still come down to {names}',
            '{team} has arms to spare, few it trusts in the ninth',
            'A full bullpen, a narrow group of trusted late arms',
            'When the lead is thin, the calls still go to {names}',
            'The dependable late innings keep running through {names}',
            'More arms than trusted late-game answers',
            'The bullpen looks deep until the late innings, when it narrows to {names}',
        ),
    },
    BEAT_BRIDGE: {
        PURPOSE_OPENING: (
            'The late innings are covered; the bridge to them is the soft spot',
            'The back of the bullpen is settled; the bridge to it is not',
            'Getting to {names} is the hard part',
            '{team} can finish games; the trouble is getting to the ninth',
            'Solid at the back, shaky getting there',
            'The trusted arms are set; the path to them is not',
            'The starters keep leaving a long walk to {names}',
            "{possessive} bullpen is strong in the ninth, thin in the seventh",
            'The save is covered; the setup to it is the worry',
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


# Forward-clause ("what it creates") shapes per beat. Each beat carries several
# governed openings so the closing beat no longer always reads "If X, then Y".
# Positive beats (availability depth) describe what the depth lets the manager
# do, not a worry. Descriptive only — no prediction, recommendation, ranking,
# betting, internal-engine, eligibility, or game-shape terms.
FORWARD_CLAUSE_LINES = {
    BEAT_COVERAGE_PRESSURE: (
        'If the short starts continue, the bullpen has fewer ways to spread the middle innings',
        'In a tight game, more of the middle innings keep landing on the bullpen',
        'The immediate effect is a bullpen asked to cover innings the rotation usually would',
    ),
    BEAT_SUSTAINABILITY_QUESTION: (
        'If this workload pattern holds, the late innings stay narrow around {names}',
        'For now, the meaningful innings keep coming back to {names}',
        'In a close game, the bullpen still leans on {names}',
    ),
    BEAT_ROUTE_CHANGE: (
        'If the next game tightens, the late innings point back through {names}',
        'In a close game, the important outs now run through {names}',
        'The immediate effect is a late-inning order reshaped around {names}',
    ),
    BEAT_DEPTH_CONSTRAINT: (
        'If the roster stays this thin, the manager has fewer ways to cover the late innings than the roster count suggests',
        'In a long game, the bullpen runs short of fresh options before the roster count would suggest',
        'That leaves the manager fewer trusted late-inning options than the roster shows',
    ),
    BEAT_AVAILABILITY_DEPTH: (
        'In a close game, the manager can lean on more than one rested arm',
        'For now, the late innings can be spread across {names} rather than forced onto one arm',
        'The immediate effect is real late-inning flexibility for the manager',
    ),
    BEAT_TRUST_LANE: (
        'If the game tightens, the late-game plan leans back on {names}, thinner than the available arm count suggests',
        'In a tight game, the dependable late innings still run through {names}',
        'The immediate effect is a short, trusted late-game group around {names}',
    ),
    BEAT_BRIDGE: (
        'If the starters keep exiting early, the path to {names} runs through a fragile middle',
        'In a close game, reaching {names} means getting through an unsettled middle',
        'For now, the bullpen has to cross a shaky middle to reach {names}',
    ),
}

for _beat, _forms in FORWARD_CLAUSE_LINES.items():
    VOICE_LIBRARY.setdefault(_beat, {})[PURPOSE_FORWARD] = _forms


# Approved openings a forward clause may use. The closing beat is recognized by
# these (not only "If …"), so varied governed shapes are preserved downstream.
FORWARD_CLAUSE_OPENERS = (
    'if ',
    'in a tight game',
    'in a close game',
    'in a long game',
    'for now',
    'the immediate effect',
    'that leaves',
)


class _SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return ''


def _clean_text(value: Any) -> str:
    return ' '.join(str(value or '').strip().split())


def _normalize(value: Any) -> str:
    return _clean_text(value).lower()


def looks_like_forward_clause(text: Any) -> bool:
    """Recognize a governed forward-looking 'what it creates' clause.

    Forward beats vary their opening (not only "If …"), so recognition is by the
    approved opener set plus a mid-sentence conditional. Keeps downstream layers
    from rewriting a perfectly good varied clause back into the old cadence.
    """
    lower = _normalize(text)
    if not lower:
        return False
    return any(lower.startswith(opener) for opener in FORWARD_CLAUSE_OPENERS) or ' if ' in lower


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
    'FORWARD_CLAUSE_LINES',
    'FORWARD_CLAUSE_OPENERS',
    'PURPOSE_ELIGIBILITY_CONTEXT',
    'PURPOSE_FORWARD',
    'PURPOSE_OPENING',
    'VERSION',
    'approved_sentence_forms',
    'contains_banned_public_language',
    'contains_denied_public_phrase',
    'looks_like_forward_clause',
    'render_voice_line',
    'select_voice_template',
    'stable_voice_index',
    'voice_library_report',
]
