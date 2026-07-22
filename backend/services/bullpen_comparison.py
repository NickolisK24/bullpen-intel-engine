"""
Team Bullpen Comparison V1 — descriptive side-by-side over two board payloads.

This module aggregates two existing Tonight's Bullpen Board payloads (V1 groups +
V2 team context) into a plain-language, self-explaining comparison. It answers
"which bullpen appears more available tonight?" descriptively.

It performs NO ranking of teams, NO bullpen grading, NO scoring, NO matchup or
win-probability logic, and NO recommendation. Every observation is a transparent
count comparison: public prose explains the baseball consequence while raw
numbers stay in structured fields. There is no "better", "stronger", or "best".
"""

from services.editorial_voice_contract_v1 import (
    build_comparison_explanation,
    contains_editorial_banned_language,
    count_to_baseball_language,
)

# Dimensions compared, in a fixed reading order. Each pulls a count straight from
# the V2 context metrics — no new availability math happens here.
COMPARISON_DIMENSIONS = [
    {
        'key': 'available',
        'metric': 'available',
        'descriptor': 'classified Available',
        'reason_label': 'Available',
    },
    {
        'key': 'restricted',
        'metric': 'restricted',
        'descriptor': 'marked Avoid or Unavailable',
        'reason_label': 'Avoid or Unavailable',
    },
    {
        'key': 'monitor',
        'metric': 'monitor',
        'descriptor': 'in the Monitor group',
        'reason_label': 'Monitor',
    },
]

CAPABILITY = 'team_bullpen_comparison'


def _count_phrase(count, singular, plural=None):
    return count_to_baseball_language(count, singular, plural)


def _team_subject(label):
    return f'The {label}'


def _has_count(label, count, singular, plural=None):
    return f'{_team_subject(label)} have {_count_phrase(count, singular, plural)}'


def _safe_public_copy(text, fallback):
    """Fail closed if future local copy trips the shared banned-language scan."""
    return fallback if contains_editorial_banned_language(text) else text


def _comparison_sentence(*, subject, reason, stable_parts, consequence=None, consequence_key=None):
    explanation = build_comparison_explanation(
        subject=subject,
        reason=reason,
        consequence=consequence,
        consequence_key=consequence_key,
        stable_parts=stable_parts,
    )
    fallback = build_comparison_explanation(
        subject='The bullpen comparison stays descriptive',
        reason='the side-by-side needs a clean baseball consequence before it separates',
        consequence='That keeps the side-by-side note focused on the game shape',
        stable_parts=('compare_bullpens', 'fallback'),
    )['sentence']
    return _safe_public_copy(explanation['sentence'], fallback)


def _reason_line(label, count, singular, plural=None, suffix=''):
    sentence = f'{_has_count(label, count, singular, plural)}{suffix}.'
    return _safe_public_copy(sentence, 'This side has a neutral bullpen note.')


def _dimension_reason_lines(dimension_key, label_a, label_b, value_a, value_b):
    if dimension_key == 'available':
        return [
            _reason_line(label_a, value_a, 'available arm', 'available arms', ' ready'),
            _reason_line(label_b, value_b, 'available arm', 'available arms', ' ready'),
        ]
    if dimension_key == 'restricted':
        return [
            _reason_line(
                label_a,
                value_a,
                'restricted arm',
                'restricted arms',
                ' needing rest or unavailable',
            ),
            _reason_line(
                label_b,
                value_b,
                'restricted arm',
                'restricted arms',
                ' needing rest or unavailable',
            ),
        ]
    return [
        _reason_line(label_a, value_a, 'watch-list arm', 'watch-list arms', ' carrying recent workload'),
        _reason_line(label_b, value_b, 'watch-list arm', 'watch-list arms', ' carrying recent workload'),
    ]


def _tie_statement(dimension_key, value):
    # Availability counts describe workload state only, so the comparison stays
    # on the availability groups themselves — it never treats an available count
    # as late-inning or leverage-role coverage the evidence does not establish.
    if dimension_key == 'available':
        return _comparison_sentence(
            subject='Both bullpens currently have the same number of relievers in the Available group',
            reason=f'each side has {_count_phrase(value, "available arm", "available arms")} ready',
            consequence='That keeps the available-arm count even between the two clubs',
            stable_parts=('compare_bullpens', dimension_key, 'tie', value),
        )
    if dimension_key == 'restricted':
        return _comparison_sentence(
            subject='Both bullpens currently have the same number of relievers marked Avoid or Unavailable',
            reason=(
                f'each side has {_count_phrase(value, "restricted arm", "restricted arms")} '
                'needing rest or unavailable'
            ),
            consequence='That keeps the count of arms needing rest even between the two clubs',
            stable_parts=('compare_bullpens', dimension_key, 'tie', value),
        )
    return _comparison_sentence(
        subject='Both bullpens currently have the same number of relievers in the Monitor group',
        reason=f'each side has {_count_phrase(value, "watch-list arm", "watch-list arms")} carrying recent workload',
        consequence='That keeps the On Watch count even between the two clubs',
        stable_parts=('compare_bullpens', dimension_key, 'tie', value),
    )


def _leader_statement(dimension_key, leader_label, other_label, leader_value, other_value):
    # Each statement names the availability group it counts and shows both sides'
    # counts as its reason. No shared "late-inning"/"leverage route" consequence
    # is attached: those keys assert role coverage the availability data cannot
    # authorize, and this surface carries no role evidence to support them.
    if dimension_key == 'available':
        return _comparison_sentence(
            subject=f'{_team_subject(leader_label)} currently have more relievers in the Available group',
            reason=(
                f'{_has_count(leader_label, leader_value, "available arm", "available arms")} '
                f'while {_has_count(other_label, other_value, "available arm", "available arms")}'
            ),
            stable_parts=('compare_bullpens', dimension_key, leader_label, other_label, leader_value, other_value),
        )
    if dimension_key == 'restricted':
        return _comparison_sentence(
            subject=f'{_team_subject(leader_label)} currently have more relievers marked Avoid or Unavailable',
            reason=(
                f'{_has_count(leader_label, leader_value, "restricted arm", "restricted arms")} '
                'needing rest or unavailable while '
                f'{_has_count(other_label, other_value, "restricted arm", "restricted arms")}'
            ),
            stable_parts=('compare_bullpens', dimension_key, leader_label, other_label, leader_value, other_value),
        )
    return _comparison_sentence(
        subject=f'{_team_subject(leader_label)} currently have more relievers in the Monitor group',
        reason=(
            f'{_has_count(leader_label, leader_value, "watch-list arm", "watch-list arms")} '
            'carrying recent workload while '
            f'{_has_count(other_label, other_value, "watch-list arm", "watch-list arms")} '
            'carrying recent workload'
        ),
        stable_parts=('compare_bullpens', dimension_key, leader_label, other_label, leader_value, other_value),
    )


def _team_label(board, fallback):
    team = (board or {}).get('team') or {}
    return team.get('team_name') or team.get('team_abbreviation') or fallback


def _metrics(board):
    context = (board or {}).get('context') or {}
    metrics = context.get('metrics') or {}
    # Default every metric to 0 so an empty/missing board compares cleanly.
    return {
        'total_relievers': int(metrics.get('total_relievers') or 0),
        'available': int(metrics.get('available') or 0),
        'monitor': int(metrics.get('monitor') or 0),
        'limited': int(metrics.get('limited') or 0),
        'avoid': int(metrics.get('avoid') or 0),
        'unavailable': int(metrics.get('unavailable') or 0),
        'restricted': int(metrics.get('restricted') or 0),
        'pct_available': int(metrics.get('pct_available') or 0),
        'pct_unavailable': int(metrics.get('pct_unavailable') or 0),
        'pct_restricted': int(metrics.get('pct_restricted') or 0),
    }


def _build_observation(dimension, label_a, label_b, value_a, value_b):
    """
    One transparent comparison for a single availability group.

    leader is 'A', 'B', or 'tie' based purely on which count is larger. The
    reasons keep both sides visible without putting raw count prose in public
    copy. Exact values remain available in team_a_value and team_b_value.
    """
    reason_label = dimension['reason_label']
    dimension_key = dimension['key']

    if value_a == value_b:
        leader = 'tie'
        statement = _tie_statement(dimension_key, value_a)
    elif value_a > value_b:
        leader = 'A'
        statement = _leader_statement(dimension_key, label_a, label_b, value_a, value_b)
    else:
        leader = 'B'
        statement = _leader_statement(dimension_key, label_b, label_a, value_b, value_a)

    return {
        'dimension': dimension_key,
        'reason_label': reason_label,
        'statement': statement,
        'leader': leader,
        'team_a_value': value_a,
        'team_b_value': value_b,
        'reasons': _dimension_reason_lines(dimension_key, label_a, label_b, value_a, value_b),
    }


def _confidence_of(board):
    context = (board or {}).get('context') or {}
    return context.get('confidence') or 'high'


def _combine_confidence(conf_a, conf_b):
    """Honest overall confidence: the weaker of the two teams wins."""
    confs = {conf_a, conf_b}
    if confs == {'none'}:
        return 'none'
    if 'none' in confs or 'low' in confs:
        return 'low'
    return 'high'


def _freshness_summary(board):
    freshness = (board or {}).get('freshness') or {}
    return {
        'is_current': freshness.get('is_current', True),
        'label': freshness.get('label'),
        'data_through': freshness.get('data_through'),
        'last_successful_sync': freshness.get('last_successful_sync'),
        'sync_status': freshness.get('sync_status'),
    }


def _no_data_summary(label_a, label_b):
    return {
        'state': 'no_data',
        'statement': _comparison_sentence(
            subject='Neither bullpen has a current relief group to compare',
            reason='both relief groups are empty in the freshness window',
            consequence_key='no_clear_signal',
            stable_parts=('compare_bullpens', 'summary', 'no_data', label_a, label_b),
        ),
        'reasons': [
            _reason_line(label_a, 0, 'current bullpen arm', 'current bullpen arms', ' in the freshness window'),
            _reason_line(label_b, 0, 'current bullpen arm', 'current bullpen arms', ' in the freshness window'),
        ],
    }


def _similar_summary(observations):
    return {
        'state': 'similar',
        'statement': _comparison_sentence(
            subject='The side-by-side bullpen read is even',
            reason='available arms, on-watch arms, and arms needing rest all match',
            consequence='That leaves neither club with a clearer bullpen margin from this comparison alone',
            stable_parts=('compare_bullpens', 'summary', 'similar'),
        ),
        'reasons': [observation['statement'] for observation in observations],
    }


def _difference_summary(label_a, label_b, metrics_a, metrics_b, observations):
    if metrics_a['available'] != metrics_b['available']:
        leader_label, other_label = (
            (label_a, label_b) if metrics_a['available'] > metrics_b['available'] else (label_b, label_a)
        )
        leader_value = max(metrics_a['available'], metrics_b['available'])
        other_value = min(metrics_a['available'], metrics_b['available'])
        statement = _comparison_sentence(
            subject=f'{_team_subject(leader_label)} currently have more relievers in the Available group',
            reason=(
                f'{_has_count(leader_label, leader_value, "available arm", "available arms")} '
                f'while {_has_count(other_label, other_value, "available arm", "available arms")}'
            ),
            stable_parts=('compare_bullpens', 'summary', 'available', leader_label, other_label, leader_value, other_value),
        )
    elif metrics_a['restricted'] != metrics_b['restricted']:
        thinner_label, cleaner_label = (
            (label_a, label_b) if metrics_a['restricted'] > metrics_b['restricted'] else (label_b, label_a)
        )
        thinner_value = max(metrics_a['restricted'], metrics_b['restricted'])
        cleaner_value = min(metrics_a['restricted'], metrics_b['restricted'])
        statement = _comparison_sentence(
            subject=f'{_team_subject(cleaner_label)} currently have fewer relievers marked Avoid or Unavailable',
            reason=(
                f'{_has_count(thinner_label, thinner_value, "restricted arm", "restricted arms")} '
                'needing rest or unavailable while '
                f'{_has_count(cleaner_label, cleaner_value, "restricted arm", "restricted arms")}'
            ),
            stable_parts=('compare_bullpens', 'summary', 'restricted', thinner_label, cleaner_label, thinner_value, cleaner_value),
        )
    else:
        higher_label, lower_label = (
            (label_a, label_b) if metrics_a['monitor'] > metrics_b['monitor'] else (label_b, label_a)
        )
        higher_value = max(metrics_a['monitor'], metrics_b['monitor'])
        lower_value = min(metrics_a['monitor'], metrics_b['monitor'])
        statement = _comparison_sentence(
            subject=f'{_team_subject(lower_label)} currently have fewer relievers in the Monitor group',
            reason=(
                f'{_has_count(higher_label, higher_value, "watch-list arm", "watch-list arms")} '
                'carrying recent workload while '
                f'{_has_count(lower_label, lower_value, "watch-list arm", "watch-list arms")} '
                'carrying recent workload'
            ),
            stable_parts=('compare_bullpens', 'summary', 'monitor', higher_label, lower_label, higher_value, lower_value),
        )
    return {
        'state': 'differ',
        'statement': statement,
        'reasons': [observation['statement'] for observation in observations],
    }


def build_team_comparison(board_a, board_b, generated_at=None):
    """
    Build the comparison block from two board payloads.

    Args:
        board_a, board_b: full board payloads (build_board_payload output).
        generated_at: ISO timestamp override (tests pass a fixed value).

    Returns:
        Dict safe to embed in an API response. No scores/rankings/grades.
    """
    label_a = _team_label(board_a, 'Team A')
    label_b = _team_label(board_b, 'Team B')
    metrics_a = _metrics(board_a)
    metrics_b = _metrics(board_b)

    observations = [
        _build_observation(
            dimension,
            label_a,
            label_b,
            metrics_a[dimension['metric']],
            metrics_b[dimension['metric']],
        )
        for dimension in COMPARISON_DIMENSIONS
    ]

    all_tied = all(observation['leader'] == 'tie' for observation in observations)
    both_empty = metrics_a['total_relievers'] == 0 and metrics_b['total_relievers'] == 0

    if both_empty:
        summary = _no_data_summary(label_a, label_b)
    elif all_tied:
        summary = _similar_summary(observations)
    else:
        summary = _difference_summary(label_a, label_b, metrics_a, metrics_b, observations)

    conf_a = _confidence_of(board_a)
    conf_b = _confidence_of(board_b)
    confidence = _combine_confidence(conf_a, conf_b)

    limitations = []
    for label, board in ((label_a, board_a), (label_b, board_b)):
        context = (board or {}).get('context') or {}
        for limitation in context.get('limitations') or []:
            limitations.append(f'{label}: {limitation}')

    payload = {
        'capability': CAPABILITY,
        'generated_at': generated_at,
        'ranking_applied': False,
        'selection_made': False,
        'teams': {
            'team_a': {'label': label_a, 'team': (board_a or {}).get('team')},
            'team_b': {'label': label_b, 'team': (board_b or {}).get('team')},
        },
        'snapshot': {
            'team_a': metrics_a,
            'team_b': metrics_b,
        },
        'observations': observations,
        'summary': summary,
        'confidence': confidence,
        'team_confidence': {'team_a': conf_a, 'team_b': conf_b},
        'freshness': {
            'team_a': _freshness_summary(board_a),
            'team_b': _freshness_summary(board_b),
        },
        'limitations': limitations,
    }
    return payload
