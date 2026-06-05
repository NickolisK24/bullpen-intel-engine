"""
Team Bullpen Comparison V1 — descriptive side-by-side over two board payloads.

This module aggregates two existing Tonight's Bullpen Board payloads (V1 groups +
V2 team context) into a plain-language, self-explaining comparison. It answers
"which bullpen appears more available tonight?" descriptively.

It performs NO ranking of teams, NO bullpen grading, NO scoring, NO matchup or
win-probability logic, and NO recommendation. Every observation is a transparent
count comparison: it names which side currently has more of a given availability
group and shows both numbers. There is no "better", "stronger", or "best".
"""

# Dimensions compared, in a fixed reading order. Each pulls a count straight from
# the V2 context metrics — no new availability math happens here.
COMPARISON_DIMENSIONS = [
    {
        'key': 'available',
        'metric': 'available',
        'descriptor': 'classified Available Tonight',
        'reason_label': 'Available Tonight',
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
    reasons always show both raw numbers so nothing is hidden.
    """
    descriptor = dimension['descriptor']
    reason_label = dimension['reason_label']

    if value_a == value_b:
        leader = 'tie'
        statement = (
            f'Both bullpens currently have the same number of relievers '
            f'{descriptor} ({value_a}).'
        )
    elif value_a > value_b:
        leader = 'A'
        statement = f'{label_a} currently has more relievers {descriptor}.'
    else:
        leader = 'B'
        statement = f'{label_b} currently has more relievers {descriptor}.'

    return {
        'dimension': dimension['key'],
        'reason_label': reason_label,
        'statement': statement,
        'leader': leader,
        'team_a_value': value_a,
        'team_b_value': value_b,
        'reasons': [
            f'{label_a} {reason_label}: {value_a}.',
            f'{label_b} {reason_label}: {value_b}.',
        ],
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
        summary = {
            'state': 'no_data',
            'statement': 'Neither bullpen has relievers in the current freshness window.',
            'reasons': [
                f'{label_a} total relievers: 0.',
                f'{label_b} total relievers: 0.',
            ],
        }
    elif all_tied:
        summary = {
            'state': 'similar',
            'statement': 'Both bullpens currently show similar availability distributions.',
            'reasons': [observation['statement'] for observation in observations],
        }
    else:
        summary = {
            'state': 'differ',
            'statement': 'These bullpens currently show different availability profiles.',
            'reasons': [observation['statement'] for observation in observations],
        }

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
