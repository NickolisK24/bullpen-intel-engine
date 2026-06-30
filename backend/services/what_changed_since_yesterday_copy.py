"""Public-safe copy helper for What Changed Since Yesterday V1 review."""

from __future__ import annotations

import re
from typing import Any

from services.bullpen_identity import IDENTITY_LABELS
from services.editorial_voice_contract_v1 import (
    build_comparison_sentence,
    contains_editorial_banned_language,
    count_to_baseball_language,
)
from services.what_changed_since_yesterday import (
    CHANGE_COVERAGE_SAFETY,
    CHANGE_IDENTITY,
    CHANGE_RESOURCE_HEALTH,
    CHANGE_RESTED_OPTIONS,
    CHANGE_TRUST_STRUCTURE,
    CHANGE_USABLE_DEPTH,
    MEANINGFUL_CAPACITY_DELTA,
    MEANINGFUL_TRUST_DELTA,
)


COPY_STATUS_GENERATED = 'generated'
COPY_STATUS_SKIPPED_NO_MEANINGFUL_CHANGE = 'skipped_no_meaningful_change'
COPY_STATUS_SKIPPED_TINY_CHANGE = 'skipped_tiny_change'

COPY_FLAG_REPEATED_HEADLINE = 'repeated_headline'
COPY_FLAG_REPEATED_SUMMARY = 'repeated_summary'
COPY_FLAG_TOO_MECHANICAL = 'too_mechanical'
COPY_FLAG_TOO_LONG = 'too_long'
COPY_FLAG_PREDICTION_LANGUAGE = 'prediction_language'
COPY_FLAG_RECOMMENDATION_LANGUAGE = 'recommendation_language'
COPY_FLAG_RANKING_LANGUAGE = 'ranking_language'
COPY_FLAG_RAW_SCORE_LEAK = 'raw_score_leak'
COPY_FLAG_IDENTITY_LABEL_LEAK = 'identity_label_leak'
COPY_FLAG_TINY_CHANGE_PROMOTED = 'tiny_change_promoted'

HEADLINE_MAX_WORDS = 13
SUMMARY_MAX_WORDS = 28
CONTEXT_MAX_WORDS = 22

RECOMMENDATION_PATTERNS = (
    'recommend',
    'recommendation',
    'should use',
    'should pitch',
    'must use',
    'manager should',
)
PREDICTION_PATTERNS = (
    'predict',
    'prediction',
    'projected',
    'expected',
    'likely',
)
RANKING_PATTERNS = (
    'ranking',
    'ranked',
    'best reliever',
    'best bullpen',
    'worst bullpen',
    'top-ranked',
)
RAW_SCORE_PATTERNS = (
    'raw_score',
    'raw score',
    'score:',
    'score =',
)
MECHANICAL_PATTERN = re.compile(
    r'\b(increased|decreased|improved|worsened|expanded|narrowed|changed) from\b',
    re.IGNORECASE,
)
VOICE_SURFACE = 'what_changed'


def _norm(value: Any) -> str:
    return str(value or '').strip().lower()


def _team_name(team_change: dict[str, Any]) -> str:
    return str(
        team_change.get('team_name')
        or team_change.get('team_abbreviation')
        or 'This bullpen'
    ).strip()


def _variant_index(team_change: dict[str, Any], change: dict[str, Any], size: int) -> int:
    if size <= 1:
        return 0
    seed = '|'.join([
        str(team_change.get('team_abbreviation') or ''),
        str(team_change.get('team_name') or ''),
        str(change.get('change_type') or ''),
        str(change.get('change_direction') or ''),
    ])
    return sum(ord(char) for char in seed) % size


def _facts(change: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(change, dict):
        return []
    facts = change.get('supporting_facts')
    return list(facts) if isinstance(facts, list) else []


def _first_fact(change: dict[str, Any] | None) -> dict[str, Any]:
    facts = _facts(change)
    return facts[0] if facts else {}


def _values(change: dict[str, Any] | None) -> tuple[Any, Any]:
    fact = _first_fact(change)
    return fact.get('previous_value'), fact.get('current_value')


def _count_delta(change: dict[str, Any] | None) -> int | None:
    previous, current = _values(change)
    if not isinstance(previous, int) or not isinstance(current, int):
        return None
    return abs(current - previous)


def _is_tiny_count_change(change: dict[str, Any] | None) -> bool:
    if not isinstance(change, dict):
        return False
    delta = _count_delta(change)
    if delta is None:
        return False
    change_type = change.get('change_type')
    if (
        change_type in {CHANGE_RESTED_OPTIONS, CHANGE_USABLE_DEPTH}
        and delta < MEANINGFUL_CAPACITY_DELTA
    ):
        return True
    return change_type == CHANGE_TRUST_STRUCTURE and delta < MEANINGFUL_TRUST_DELTA


def _safe_public_copy(text: str, fallback: str) -> str:
    """Fail closed if future What Changed copy trips the shared banned scan."""
    return fallback if contains_editorial_banned_language(text) else text


def _public_sentence(
    *,
    subject: str,
    reason: str,
    stable_parts: tuple[Any, ...],
    consequence: str | None = None,
    consequence_key: str | None = None,
) -> str:
    sentence = build_comparison_sentence(
        subject=subject,
        reason=reason,
        consequence=consequence,
        consequence_key=consequence_key,
        stable_parts=(VOICE_SURFACE, *stable_parts),
    )
    fallback = build_comparison_sentence(
        subject='The bullpen movement stays descriptive',
        reason='the public read needs a baseball consequence',
        consequence='That keeps the note tied to the game shape',
        stable_parts=(VOICE_SURFACE, 'fallback'),
    )
    return _safe_public_copy(sentence, fallback)


def _count_phrase(value: int | None, singular: str, plural: str | None = None) -> str:
    phrase = count_to_baseball_language(value, singular, plural)
    return phrase or f'more {plural or singular}'


def _other_shift_phrase(count: int) -> str:
    if count == 2:
        return 'two other meaningful shifts'
    return _count_phrase(count, 'other meaningful shift', 'other meaningful shifts')


def _coverage_label(value: Any) -> str:
    label = str(value or '').replace(' Coverage Safety', '').strip()
    return label.lower() if label else 'unknown'


def _headline(team_change: dict[str, Any], change: dict[str, Any]) -> str:
    team = _team_name(team_change)
    change_type = change.get('change_type')
    direction = change.get('change_direction')

    options = {
        (CHANGE_RESTED_OPTIONS, 'increased'): [
            f'The {team} bullpen has more breathing room today.',
            f'The {team} bullpen has a wider late-inning cushion today.',
            f'The {team} bullpen has more rested arms for a close game.',
        ],
        (CHANGE_RESTED_OPTIONS, 'decreased'): [
            f'The {team} bullpen has a thinner margin today.',
            f'The {team} bullpen has a shorter late-inning cushion today.',
        ],
        (CHANGE_USABLE_DEPTH, 'increased'): [
            f'The {team} bullpen has more ways to cover tonight.',
            f'The {team} bullpen has more full-game coverage today.',
        ],
        (CHANGE_USABLE_DEPTH, 'decreased'): [
            f'The {team} bullpen has a shorter full-game route today.',
            f'The {team} bullpen margin is thinner than yesterday.',
        ],
        (CHANGE_COVERAGE_SAFETY, 'improved'): [
            f'The {team} coverage picture stabilized.',
            f'Coverage looks sturdier for the {team} bullpen today.',
        ],
        (CHANGE_COVERAGE_SAFETY, 'worsened'): [
            f'The {team} margin got thinner.',
            f'Coverage is tighter for the {team} bullpen today.',
        ],
        (CHANGE_TRUST_STRUCTURE, 'expanded'): [
            f'The trusted group widened for the {team} bullpen.',
            f'The {team} bullpen has a wider late-inning support layer.',
        ],
        (CHANGE_TRUST_STRUCTURE, 'narrowed'): [
            f'The trusted group narrowed for the {team} bullpen.',
            f'The {team} late-inning support layer is smaller today.',
        ],
        (CHANGE_RESOURCE_HEALTH, 'improved'): [
            f'The {team} bullpen has a healthier resource picture today.',
            f'The {team} bullpen is operating with more room today.',
        ],
        (CHANGE_RESOURCE_HEALTH, 'worsened'): [
            f'The {team} bullpen resource picture tightened.',
            f'The {team} bullpen has less margin today.',
        ],
        (CHANGE_IDENTITY, 'changed'): [
            f'The {team} bullpen route reads differently today.',
            f'The {team} bullpen has a new close-game shape today.',
        ],
    }.get((change_type, direction), [
        f'The {team} bullpen route reads differently today.',
    ])
    return options[_variant_index(team_change, change, len(options))]


def _summary(team_change: dict[str, Any], change: dict[str, Any]) -> str:
    team = _team_name(team_change)
    change_type = change.get('change_type')
    direction = change.get('change_direction')
    previous, current = _values(change)
    delta = _count_delta(change)
    clean_delta = _count_phrase(delta, 'rested arm', 'rested arms')
    coverage_delta = _count_phrase(delta, 'coverage route', 'coverage routes')
    support_delta = _count_phrase(delta, 'support arm', 'support arms')

    if change_type == CHANGE_RESTED_OPTIONS:
        if direction == 'increased':
            options = [
                _public_sentence(
                    subject=f'The {team} bullpen has more breathing room',
                    reason=f'{clean_delta} came back into the late-inning mix',
                    consequence='That gives the staff more ways through a close game',
                    stable_parts=(team, change_type, direction, 'a', delta),
                ),
                _public_sentence(
                    subject='The late-inning cushion is wider',
                    reason=f'the rested side has {clean_delta} back',
                    consequence='That leaves more room for the biggest outs',
                    stable_parts=(team, change_type, direction, 'b', delta),
                ),
                _public_sentence(
                    subject=f'The {team} bullpen has more close-game room',
                    reason=f'the rested side gained {clean_delta}',
                    consequence='That helps bridge the middle innings',
                    stable_parts=(team, change_type, direction, 'c', delta),
                ),
                _public_sentence(
                    subject='The bullpen has a wider close-game lane',
                    reason=f'{clean_delta} returned to the late-inning mix',
                    consequence='That adds margin before the biggest outs',
                    stable_parts=(team, change_type, direction, 'd', delta),
                ),
                _public_sentence(
                    subject=f'The {team} bullpen has more middle-inning cover',
                    reason=f'the bullpen gained {clean_delta}',
                    consequence='That widens the route to the late arms',
                    stable_parts=(team, change_type, direction, 'e', delta),
                ),
                _public_sentence(
                    subject='The path to the late innings has more room',
                    reason=f'the bullpen gained {clean_delta}',
                    consequence='That gives the staff more choices in a tight game',
                    stable_parts=(team, change_type, direction, 'f', delta),
                ),
            ]
            return options[_variant_index(team_change, change, len(options))]
        options = [
            _public_sentence(
                subject=f'The {team} bullpen has a thinner late-inning cushion',
                reason=f'the bullpen lost {clean_delta}',
                consequence='That puts more weight on the bridge before the trusted arms',
                stable_parts=(team, change_type, direction, 'a', delta),
            ),
            _public_sentence(
                subject='The close-game route is tighter',
                reason=f'the rested side lost {clean_delta}',
                consequence='That leaves less margin before the late innings',
                stable_parts=(team, change_type, direction, 'b', delta),
            ),
            _public_sentence(
                subject='The bullpen has less breathing room around the edges',
                reason=f'the bullpen no longer has {clean_delta}',
                consequence='That makes the middle innings matter more',
                stable_parts=(team, change_type, direction, 'c', delta),
            ),
        ]
        return options[_variant_index(team_change, change, len(options))]

    if change_type == CHANGE_USABLE_DEPTH:
        if direction == 'increased':
            return _public_sentence(
                subject='The bullpen has more full-game coverage',
                reason=f'{coverage_delta} opened',
                consequence='That helps if the starter exits early',
                stable_parts=(team, change_type, direction, delta),
            )
        return _public_sentence(
            subject='The full-game route is shorter than yesterday',
            reason=f'{coverage_delta} dropped out of the coverage picture',
            consequence='That makes the bridge to the late arms more important',
            stable_parts=(team, change_type, direction, delta),
        )

    if change_type == CHANGE_COVERAGE_SAFETY:
        previous_label = _coverage_label(previous)
        current_label = _coverage_label(current)
        if direction == 'improved':
            return _public_sentence(
                subject='The coverage picture is sturdier than yesterday',
                reason=f'the read shifted out of {previous_label} territory toward {current_label}',
                consequence='That gives the bullpen more room if the game stretches',
                stable_parts=(team, change_type, direction, previous_label, current_label),
            )
        return _public_sentence(
            subject='The coverage picture is tighter than yesterday',
            reason=f'the read shifted from {previous_label} toward {current_label}',
            consequence='That leaves less margin if the game stretches',
            stable_parts=(team, change_type, direction, previous_label, current_label),
        )

    if change_type == CHANGE_TRUST_STRUCTURE:
        if direction == 'expanded':
            return _public_sentence(
                subject='The late-inning support layer is wider',
                reason=f'the trusted side added {support_delta}',
                consequence='That gives the staff more ways to reach the biggest outs',
                stable_parts=(team, change_type, direction, delta),
            )
        return _public_sentence(
            subject='The late-inning support layer is narrower',
            reason=f'the trusted side lost {support_delta}',
            consequence='That puts more pressure on the bridge before the biggest outs',
            stable_parts=(team, change_type, direction, delta),
        )

    if change_type == CHANGE_RESOURCE_HEALTH:
        if direction == 'improved':
            return _public_sentence(
                subject='The bullpen has more breathing room than yesterday',
                reason='the resource picture is less tight',
                consequence='That gives the staff more ways to cover tonight',
                stable_parts=(team, change_type, direction, previous, current),
            )
        return _public_sentence(
            subject='The bullpen margin tightened from yesterday',
            reason='the resource picture is more constrained',
            consequence='That leaves less room around the middle innings',
            stable_parts=(team, change_type, direction, previous, current),
        )

    if change_type == CHANGE_IDENTITY:
        return _public_sentence(
            subject='The close-game route changed',
            reason='the broader shape no longer matches yesterday',
            consequence='That changes the path to the final outs',
            stable_parts=(team, change_type, direction),
        )

    return _safe_public_copy(
        str(change.get('change_summary') or '').strip(),
        'The bullpen route changed enough to affect the close-game shape.',
    )


def _secondary_phrase(change: dict[str, Any]) -> str:
    change_type = change.get('change_type')
    direction = change.get('change_direction')
    phrases = {
        (CHANGE_RESTED_OPTIONS, 'increased'): 'the late-inning cushion also widened',
        (CHANGE_RESTED_OPTIONS, 'decreased'): 'the late-inning cushion also tightened',
        (CHANGE_USABLE_DEPTH, 'increased'): 'full-game coverage also widened',
        (CHANGE_USABLE_DEPTH, 'decreased'): 'full-game coverage also narrowed',
        (CHANGE_COVERAGE_SAFETY, 'improved'): 'coverage also stabilized',
        (CHANGE_COVERAGE_SAFETY, 'worsened'): 'coverage also tightened',
        (CHANGE_TRUST_STRUCTURE, 'expanded'): 'late-inning support also widened',
        (CHANGE_TRUST_STRUCTURE, 'narrowed'): 'late-inning support also narrowed',
        (CHANGE_RESOURCE_HEALTH, 'improved'): 'the bullpen margin also improved',
        (CHANGE_RESOURCE_HEALTH, 'worsened'): 'the bullpen margin also tightened',
        (CHANGE_IDENTITY, 'changed'): 'the broader close-game route also changed',
    }
    return phrases.get((change_type, direction), 'another bullpen detail also changed')


def _context(
    changes: list[dict[str, Any]],
    top_change: dict[str, Any],
) -> str | None:
    secondary = [
        change
        for change in changes
        if change is not top_change and not _is_tiny_count_change(change)
    ]
    if not secondary:
        return None
    phrase = _secondary_phrase(secondary[0])
    if len(secondary) == 1:
        return f'There is another meaningful shift here: {phrase}.'
    return (
        f'There are {_other_shift_phrase(len(secondary))} here, including '
        f'{phrase}.'
    )


def _word_count(value: str | None) -> int:
    return len(re.findall(r'\b\S+\b', value or ''))


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(pattern in lower for pattern in patterns)


def _identity_label_leaked(text: str) -> bool:
    labels = {str(label).lower() for label in IDENTITY_LABELS.values()}
    labels.update(str(key).lower() for key in IDENTITY_LABELS)
    lower = text.lower()
    return any(label and label in lower for label in labels)


def _copy_flags(
    *,
    headline: str | None,
    summary: str | None,
    context: str | None,
    tiny_change_promoted: bool,
) -> list[str]:
    flags = []
    text = ' '.join(part for part in (headline, summary, context) if part)

    if tiny_change_promoted:
        flags.append(COPY_FLAG_TINY_CHANGE_PROMOTED)
    if any(MECHANICAL_PATTERN.search(part or '') for part in (headline, summary, context)):
        flags.append(COPY_FLAG_TOO_MECHANICAL)
    if (
        _word_count(headline) > HEADLINE_MAX_WORDS
        or _word_count(summary) > SUMMARY_MAX_WORDS
        or _word_count(context) > CONTEXT_MAX_WORDS
    ):
        flags.append(COPY_FLAG_TOO_LONG)
    if _contains_any(text, PREDICTION_PATTERNS):
        flags.append(COPY_FLAG_PREDICTION_LANGUAGE)
    if _contains_any(text, RECOMMENDATION_PATTERNS):
        flags.append(COPY_FLAG_RECOMMENDATION_LANGUAGE)
    if _contains_any(text, RANKING_PATTERNS):
        flags.append(COPY_FLAG_RANKING_LANGUAGE)
    if _contains_any(text, RAW_SCORE_PATTERNS):
        flags.append(COPY_FLAG_RAW_SCORE_LEAK)
    if _identity_label_leaked(text):
        flags.append(COPY_FLAG_IDENTITY_LABEL_LEAK)
    if contains_editorial_banned_language(text):
        flags.append(COPY_FLAG_TOO_MECHANICAL)

    return flags


def build_what_changed_public_copy(
    team_change: dict[str, Any],
    *,
    top_change: dict[str, Any] | None,
    changes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Convert structured change output into concise public-safe copy."""

    if not top_change:
        return {
            'public_copy_generated': False,
            'public_copy_status': COPY_STATUS_SKIPPED_NO_MEANINGFUL_CHANGE,
            'public_headline': None,
            'public_summary': None,
            'public_context': None,
            'copy_review_flags': [],
        }

    tiny_change_promoted = _is_tiny_count_change(top_change)
    if tiny_change_promoted:
        return {
            'public_copy_generated': False,
            'public_copy_status': COPY_STATUS_SKIPPED_TINY_CHANGE,
            'public_headline': None,
            'public_summary': None,
            'public_context': None,
            'copy_review_flags': [COPY_FLAG_TINY_CHANGE_PROMOTED],
        }

    headline = _headline(team_change, top_change)
    summary = _summary(team_change, top_change)
    context = _context(changes, top_change)

    return {
        'public_copy_generated': True,
        'public_copy_status': COPY_STATUS_GENERATED,
        'public_headline': headline,
        'public_summary': summary,
        'public_context': context,
        'copy_review_flags': _copy_flags(
            headline=headline,
            summary=summary,
            context=context,
            tiny_change_promoted=False,
        ),
    }


__all__ = [
    'COPY_FLAG_IDENTITY_LABEL_LEAK',
    'COPY_FLAG_PREDICTION_LANGUAGE',
    'COPY_FLAG_RANKING_LANGUAGE',
    'COPY_FLAG_RAW_SCORE_LEAK',
    'COPY_FLAG_RECOMMENDATION_LANGUAGE',
    'COPY_FLAG_REPEATED_HEADLINE',
    'COPY_FLAG_REPEATED_SUMMARY',
    'COPY_FLAG_TINY_CHANGE_PROMOTED',
    'COPY_FLAG_TOO_LONG',
    'COPY_FLAG_TOO_MECHANICAL',
    'COPY_STATUS_GENERATED',
    'COPY_STATUS_SKIPPED_NO_MEANINGFUL_CHANGE',
    'COPY_STATUS_SKIPPED_TINY_CHANGE',
    'build_what_changed_public_copy',
]
