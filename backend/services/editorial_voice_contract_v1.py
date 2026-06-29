"""Shared public editorial voice helpers for surface migrations.

E2C-1 introduced the infrastructure. Later phases opt in surface by surface
while preserving public contracts under tests.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from string import Formatter
from typing import Any

from services.story_voice_library_v1 import (
    BANNED_PUBLIC_LANGUAGE as STORY_BANNED_PUBLIC_LANGUAGE,
    DENIED_PUBLIC_PHRASES as STORY_DENIED_PUBLIC_PHRASES,
    stable_voice_index,
)


CAPABILITY = 'editorial_voice_contract_v1'
VERSION = '2026-06-29.v1'

STATUS_PASS = 'pass'
STATUS_WARN = 'warn'

COUNT_WORDS = {
    0: 'not one',
    1: 'the lone',
    2: 'both',
    3: 'three',
    4: 'four',
    5: 'five',
    6: 'six',
}

BASEBALL_CONSEQUENCE_LINES = {
    'late_inning_margin': (
        'That gives the bullpen more ways to cover the late innings',
        'That gives the staff more margin before the game reaches the final outs',
        'That leaves the late innings with more than one clean path',
    ),
    'narrow_late_path': (
        'That leaves less margin before the game reaches the trusted arms',
        'That narrows the path through the highest-pressure innings',
        'That makes each clean arm matter more when the game tightens',
    ),
    'bridge_pressure': (
        'That puts more of the game on the bridge to the late arms',
        'That makes the handoff to the trusted arms the part worth watching',
        'That shifts the pressure to the innings before the back of the bullpen',
    ),
    'route_turnover': (
        "That matters because yesterday's comfortable route may not be today's cleanest path",
        'That kind of turnover matters because the late-inning order has changed beneath the same roster',
        'That changes how the bullpen has to build the path to the biggest outs',
    ),
    'workload_spread': (
        'That lets the bullpen spread the work across more arms',
        'That gives the staff more ways to keep the same arms from carrying every inning',
        'That creates room for the workload to move beyond the usual pocket',
    ),
    'workload_concentration': (
        'That keeps the work gathered on a smaller group',
        'That leaves the meaningful innings concentrated around the same arms',
        'That keeps the workload from spreading across the full bullpen',
    ),
    'availability_narrowed': (
        'That narrows the usable group before the game gets late',
        'That leaves fewer clean ways through a close game',
        'That shortens the bullpen before the late innings arrive',
    ),
    'no_clear_signal': (
        'That keeps the read descriptive until the evidence separates',
        'That keeps the note quiet until the baseball consequence is clear',
        'That leaves the surface without a strong enough public story yet',
    ),
}

EXPANDED_EDITORIAL_DENY_TERMS = (
    '0 trusted',
    'retained 0 arm',
    '3-spot change',
    'clean option is limited',
    'clean options are limited',
    'availability distribution',
    'practical path',
    'usable reliever',
    'route count',
    'active route',
    'relief lane',
    'baseline fact',
    'constraint fact',
    'observation type',
    'context indicates',
    'the frame shows',
    'the frame marks',
    'deterministic',
    'raw score',
    'manager should',
    'should use',
    'best option',
    'recommendation engine',
)

EDITORIAL_BANNED_LANGUAGE = tuple(dict.fromkeys((
    *(term.lower() for term in STORY_BANNED_PUBLIC_LANGUAGE),
    *(term.lower() for term in STORY_DENIED_PUBLIC_PHRASES),
    *EXPANDED_EDITORIAL_DENY_TERMS,
)))

RAW_COUNT_PATTERN = re.compile(r'(?<![\w-])\d+(?:\.\d+)?(?![\w-])')
NO_PLURALIZE_TOKENS = {'odds', 'news'}


@dataclass(frozen=True)
class EditorialViolation:
    """One deterministic public-language violation."""

    term: str
    match: str
    category: str
    start: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return ''


def _clean(value: Any) -> str:
    return ' '.join(str(value or '').strip().split())


def _sentence(value: Any) -> str:
    text = _clean(value)
    if not text:
        return ''
    return text if text[-1] in '.!?' else f'{text}.'


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _pluralize(noun: str) -> str:
    noun = _clean(noun)
    if not noun:
        return ''
    if noun.endswith('y') and len(noun) > 1:
        return f'{noun[:-1]}ies'
    if noun.endswith(('s', 'x', 'z', 'ch', 'sh')):
        return f'{noun}es'
    return f'{noun}s'


def count_to_baseball_language(
    count: Any,
    singular: str,
    plural: str | None = None,
    *,
    include_noun: bool = True,
) -> str:
    """Translate a count into public baseball language without raw numerals.

    This is for prose. Exact numerals still belong in evidence tables, chips, and
    structured fields. For larger counts, the helper intentionally buckets the
    phrase rather than putting raw numbers into a public sentence.
    """

    value = _as_int(count)
    singular = _clean(singular)
    plural = _clean(plural) or _pluralize(singular)
    if value is None or not singular:
        return ''

    if value <= 0:
        phrase, noun = COUNT_WORDS[0], singular
    elif value == 1:
        phrase, noun = COUNT_WORDS[1], singular
    elif value == 2:
        phrase, noun = COUNT_WORDS[2], plural
    elif value <= 6:
        phrase, noun = COUNT_WORDS[value], plural
    elif value <= 9:
        phrase, noun = 'a deeper group of', plural
    else:
        phrase, noun = 'a large group of', plural

    return _clean(f'{phrase} {noun}') if include_noun else phrase


def _format_fields(template: str) -> set[str]:
    fields: set[str] = set()
    for _, field_name, _, _ in Formatter().parse(template):
        if field_name:
            fields.add(field_name)
    return fields


def render_baseball_consequence(
    consequence_key: str,
    *,
    stable_parts: tuple[Any, ...] = (),
    **slots: Any,
) -> str:
    """Render an approved baseball consequence line deterministically."""

    key = _clean(consequence_key)
    forms = BASEBALL_CONSEQUENCE_LINES.get(key) or ()
    if not forms:
        return ''
    usable = [
        form for form in forms
        if all(_clean(slots.get(field)) for field in _format_fields(form))
    ]
    forms = tuple(usable or forms)
    index = stable_voice_index((CAPABILITY, VERSION, 'consequence', key, *stable_parts), len(forms))
    rendered = forms[index].format_map(_SafeFormatDict({name: _clean(value) for name, value in slots.items()}))
    return _sentence(rendered)


def build_comparison_sentence(
    *,
    subject: Any,
    reason: Any,
    consequence: Any = None,
    consequence_key: str | None = None,
    stable_parts: tuple[Any, ...] = (),
    **slots: Any,
) -> str:
    """Compose a comparison explanation as subject, reason, consequence."""

    subject_text = _clean(subject)
    reason_text = _clean(reason)
    consequence_text = _clean(consequence) or render_baseball_consequence(
        consequence_key or '',
        stable_parts=stable_parts,
        **slots,
    )

    lead = ''
    if subject_text and reason_text:
        lead = _sentence(f'{subject_text} because {reason_text}')
    else:
        lead = _sentence(subject_text or reason_text)
    return ' '.join(part for part in (lead, _sentence(consequence_text)) if part)


def build_comparison_explanation(
    *,
    subject: Any,
    reason: Any,
    consequence: Any = None,
    consequence_key: str | None = None,
    stable_parts: tuple[Any, ...] = (),
    **slots: Any,
) -> dict[str, str]:
    """Return structured comparison copy for future API surfaces."""

    consequence_text = _clean(consequence) or render_baseball_consequence(
        consequence_key or '',
        stable_parts=stable_parts,
        **slots,
    )
    return {
        'subject': _clean(subject),
        'reason': _clean(reason),
        'baseball_consequence': _sentence(consequence_text),
        'sentence': build_comparison_sentence(
            subject=subject,
            reason=reason,
            consequence=consequence_text,
            stable_parts=stable_parts,
            **slots,
        ),
    }


def _plural_token_pattern(token: str) -> str:
    escaped = re.escape(token)
    lower = token.lower()
    if lower in NO_PLURALIZE_TOKENS or not re.search(r'[a-z]$', lower):
        return escaped
    if lower.endswith('ies') and len(lower) > 3:
        return f'{re.escape(token[:-3])}(?:y|ies)'
    if lower.endswith('s') and len(lower) > 3:
        return f'{re.escape(token[:-1])}s?'
    if lower.endswith('y') and len(lower) > 1:
        return f'{re.escape(token[:-1])}(?:y|ies)'
    return f'{escaped}s?'


def _term_pattern(term: str) -> re.Pattern:
    tokens = _clean(term).split()
    parts = [_plural_token_pattern(token) for token in tokens]
    body = r'\s+'.join(parts)
    return re.compile(rf'(?<![A-Za-z0-9]){body}(?![A-Za-z0-9])', re.IGNORECASE)


def _violation_category(term: str) -> str:
    if term in STORY_BANNED_PUBLIC_LANGUAGE:
        return 'prediction_betting_or_certainty'
    if term in STORY_DENIED_PUBLIC_PHRASES:
        return 'story_voice_denied_phrase'
    return 'editorial_contract_denied_phrase'


def find_editorial_violations(text: Any, *, terms: tuple[str, ...] = EDITORIAL_BANNED_LANGUAGE) -> list[dict[str, Any]]:
    """Find banned public-language terms, including singular/plural variants."""

    value = _clean(text)
    if not value:
        return []
    violations: list[EditorialViolation] = []
    seen: set[tuple[str, int, str]] = set()
    for term in terms:
        pattern = _term_pattern(term)
        for match in pattern.finditer(value):
            key = (term, match.start(), match.group(0).lower())
            if key in seen:
                continue
            seen.add(key)
            violations.append(EditorialViolation(
                term=term,
                match=match.group(0),
                category=_violation_category(term),
                start=match.start(),
            ))
    violations.sort(key=lambda item: (item.start, item.term))
    return [item.to_dict() for item in violations]


def contains_editorial_banned_language(text: Any) -> bool:
    return bool(find_editorial_violations(text))


def raw_count_matches(text: Any) -> list[str]:
    return [match.group(0) for match in RAW_COUNT_PATTERN.finditer(_clean(text))]


def editorial_conformance_report(text: Any, *, allow_raw_counts: bool = True) -> dict[str, Any]:
    """Return a deterministic report future surfaces can use before publishing."""

    clean_text = _clean(text)
    violations = find_editorial_violations(clean_text)
    raw_counts = [] if allow_raw_counts else raw_count_matches(clean_text)
    status = STATUS_PASS if not violations and not raw_counts else STATUS_WARN
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'status': status,
        'violations': violations,
        'raw_counts': raw_counts,
        'allow_raw_counts': bool(allow_raw_counts),
    }


def is_editorially_conformant(text: Any, *, allow_raw_counts: bool = True) -> bool:
    return editorial_conformance_report(text, allow_raw_counts=allow_raw_counts)['status'] == STATUS_PASS


def editorial_voice_contract_report() -> dict[str, Any]:
    """Compact metadata for tests and diagnostic scripts."""

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'count_language': {
            'small_count_max': max(COUNT_WORDS),
            'raw_counts_in_prose': False,
        },
        'consequence_keys': sorted(BASEBALL_CONSEQUENCE_LINES),
        'banned_language_count': len(EDITORIAL_BANNED_LANGUAGE),
        'plural_aware_matching': True,
        'public_surfaces_migrated': ['compare_bullpens'],
    }


__all__ = [
    'BASEBALL_CONSEQUENCE_LINES',
    'CAPABILITY',
    'COUNT_WORDS',
    'EDITORIAL_BANNED_LANGUAGE',
    'EXPANDED_EDITORIAL_DENY_TERMS',
    'STATUS_PASS',
    'STATUS_WARN',
    'VERSION',
    'build_comparison_explanation',
    'build_comparison_sentence',
    'contains_editorial_banned_language',
    'count_to_baseball_language',
    'editorial_conformance_report',
    'editorial_voice_contract_report',
    'find_editorial_violations',
    'is_editorially_conformant',
    'raw_count_matches',
    'render_baseball_consequence',
]
