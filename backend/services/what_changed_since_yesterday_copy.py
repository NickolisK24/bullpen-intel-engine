"""Public-safe copy helper for What Changed Since Yesterday V1 review."""

from __future__ import annotations

import re
from typing import Any

from services.bullpen_identity import IDENTITY_LABELS
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


def _count_phrase(value: int | None) -> str:
    words = {
        1: 'one',
        2: 'two',
        3: 'three',
        4: 'four',
        5: 'five',
    }
    if value in words:
        return words[value]
    return str(value) if value is not None else 'more'


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
            f'The {team} bullpen has more room than yesterday.',
            f'The {team} bullpen has a few more paths available.',
        ],
        (CHANGE_RESTED_OPTIONS, 'decreased'): [
            f'The {team} bullpen has a thinner margin today.',
            f'The {team} bullpen has fewer clean paths than yesterday.',
        ],
        (CHANGE_USABLE_DEPTH, 'increased'): [
            f'The {team} bullpen has more ways to cover tonight.',
            f'The {team} bullpen has more usable depth today.',
        ],
        (CHANGE_USABLE_DEPTH, 'decreased'): [
            f'The {team} bullpen has fewer paths available today.',
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
            f'More of the {team} bullpen sits in the trusted layer.',
        ],
        (CHANGE_TRUST_STRUCTURE, 'narrowed'): [
            f'The trusted group narrowed for the {team} bullpen.',
            f'The {team} trusted layer is smaller than yesterday.',
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
            f'The {team} bullpen has a different shape today.',
            f'The broader {team} bullpen picture looks different today.',
        ],
    }.get((change_type, direction), [
        f'The {team} bullpen looks different from yesterday.',
    ])
    return options[_variant_index(team_change, change, len(options))]


def _summary(team_change: dict[str, Any], change: dict[str, Any]) -> str:
    team = _team_name(team_change)
    change_type = change.get('change_type')
    direction = change.get('change_direction')
    previous, current = _values(change)
    delta = _count_delta(change)
    delta_phrase = _count_phrase(delta)

    if change_type == CHANGE_RESTED_OPTIONS:
        if direction == 'increased':
            options = [
                (
                    f'For the {team} bullpen, rested options moved from {previous} to '
                    f'{current}, giving the group {delta_phrase} more usable paths than '
                    'yesterday.'
                ),
                (
                    f'The rested count moved from {previous} to {current}, opening '
                    f'{delta_phrase} more ways to cover the game.'
                ),
                (
                    f"Yesterday's {previous} rested options became {current}, so there is "
                    'more room around the edges.'
                ),
                (
                    f'The bullpen went from {previous} rested options to {current}, adding '
                    f'{delta_phrase} cleaner paths than yesterday.'
                ),
                (
                    f'There are {current} rested options after {previous} yesterday, giving '
                    'the bullpen more margin.'
                ),
            ]
            return options[_variant_index(team_change, change, len(options))]
        options = [
            (
                f'For the {team} bullpen, rested options moved from {previous} to '
                f'{current}, leaving {delta_phrase} fewer clean paths than yesterday.'
            ),
            (
                f'The rested count slipped from {previous} to {current}, so the bullpen '
                'has less room around the edges.'
            ),
            (
                f"Yesterday's {previous} rested options became {current}, tightening the "
                'available paths for this bullpen.'
            ),
            (
                f'The bullpen went from {previous} rested options to {current}, removing '
                f'{delta_phrase} cleaner paths from yesterday.'
            ),
            (
                f'There are {current} rested options after {previous} yesterday, leaving '
                'less margin around the edges.'
            ),
        ]
        return options[_variant_index(team_change, change, len(options))]

    if change_type == CHANGE_USABLE_DEPTH:
        if direction == 'increased':
            return (
                f'Usable bullpen depth moved from {previous} to {current}, creating '
                f'{delta_phrase} more paths through the game.'
            )
        return (
            f'Usable bullpen depth moved from {previous} to {current}, leaving fewer '
            'ways to cover a full game.'
        )

    if change_type == CHANGE_COVERAGE_SAFETY:
        previous_label = _coverage_label(previous)
        current_label = _coverage_label(current)
        if direction == 'improved':
            return (
                f'Coverage moved from {previous_label} to {current_label}, giving the '
                'bullpen more room if the game stretches.'
            )
        return (
            f'Coverage slipped from {previous_label} to {current_label}, leaving less '
            'room if the game stretches.'
        )

    if change_type == CHANGE_TRUST_STRUCTURE:
        if direction == 'expanded':
            return (
                f'The trusted group moved from {previous} to {current}, so more of the '
                'bullpen can support the late innings than yesterday.'
            )
        return (
            f'The trusted group moved from {previous} to {current}, making the late-inning '
            'support layer smaller than yesterday.'
        )

    if change_type == CHANGE_RESOURCE_HEALTH:
        if direction == 'improved':
            return (
                f'Resource health moved from {previous} to {current}, giving the bullpen '
                'more flexibility than yesterday.'
            )
        return (
            f'Resource health moved from {previous} to {current}, leaving less flexibility '
            'around the edges.'
        )

    if change_type == CHANGE_IDENTITY:
        return (
            'The broader bullpen shape moved enough to read differently from the prior '
            'snapshot.'
        )

    return str(change.get('change_summary') or '').strip()


def _secondary_phrase(change: dict[str, Any]) -> str:
    change_type = change.get('change_type')
    direction = change.get('change_direction')
    phrases = {
        (CHANGE_RESTED_OPTIONS, 'increased'): 'rested depth also improved',
        (CHANGE_RESTED_OPTIONS, 'decreased'): 'rested depth also tightened',
        (CHANGE_USABLE_DEPTH, 'increased'): 'usable depth also widened',
        (CHANGE_USABLE_DEPTH, 'decreased'): 'usable depth also narrowed',
        (CHANGE_COVERAGE_SAFETY, 'improved'): 'coverage also stabilized',
        (CHANGE_COVERAGE_SAFETY, 'worsened'): 'coverage also tightened',
        (CHANGE_TRUST_STRUCTURE, 'expanded'): 'the trusted group also widened',
        (CHANGE_TRUST_STRUCTURE, 'narrowed'): 'the trusted group also narrowed',
        (CHANGE_RESOURCE_HEALTH, 'improved'): 'resource health also improved',
        (CHANGE_RESOURCE_HEALTH, 'worsened'): 'resource health also tightened',
        (CHANGE_IDENTITY, 'changed'): 'the broader bullpen shape also changed',
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
        f'There are {len(secondary)} other meaningful shifts here, including '
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
