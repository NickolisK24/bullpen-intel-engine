"""Rotation Context Layer 1.

This module measures how much recent rotation workload has handed innings to
the bullpen. It is descriptive only: no scores, rankings, predictions, or story
generation are produced here.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from services.availability_reference_date import product_current_date
from utils.games_started import RELIEF, START, games_started_state
from utils.innings import log_innings_outs, outs_to_decimal_innings


CAPABILITY = 'rotation_context_v1'
VERSION = '2026-06-20.layer1'

ROTATION_CONTEXT_7D = 7
ROTATION_CONTEXT_14D = 14
EARLY_BULLPEN_ENTRY_OUTS = 15
MIN_COMPLETE_TEAM_GAME_OUTS = 24

CURRENT_ASSIGNMENT_LIMITATION = (
    'Rotation context uses currently assigned pitchers because game logs do not yet store team-at-appearance.'
)
OPENER_BULK_LIMITATION = (
    'Credited starters are used as recorded; opener/bulk-reliever roles are not separately inferred.'
)
INCOMPLETE_GAME_DATA_LIMITATION = (
    'Some games are excluded because starter/relief workload data is incomplete or ambiguous.'
)


def _value(obj: Any, name: str, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _date_value(value: Any):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _reference_date(logs, reference_date=None):
    ref = _date_value(reference_date)
    if ref is not None:
        return ref
    dates = [
        parsed
        for parsed in (_date_value(_value(log, 'game_date')) for log in logs or [])
        if parsed is not None
    ]
    return max(dates, default=product_current_date())


def _is_regular_season(log: Any):
    return _value(log, 'game_type') in (None, '', 'R')


def _game_pk(log: Any):
    return _value(log, 'mlb_game_pk')


def _log_outs(log: Any):
    if isinstance(log, dict):
        outs = log.get('innings_pitched_outs')
        if outs is not None:
            try:
                parsed = int(outs)
            except (TypeError, ValueError):
                return None
            return parsed if parsed >= 0 else None
    return log_innings_outs(log)


def _group_logs(logs, *, reference_date, window_days=ROTATION_CONTEXT_14D):
    window_start = reference_date - timedelta(days=window_days - 1)
    grouped = defaultdict(list)
    rows_without_game_pk = 0
    for log in logs or []:
        game_date = _date_value(_value(log, 'game_date'))
        if game_date is None or game_date < window_start or game_date > reference_date:
            continue
        if not _is_regular_season(log):
            continue
        game_pk = _game_pk(log)
        if game_pk is None:
            rows_without_game_pk += 1
            continue
        grouped[game_pk].append(log)
    return grouped, rows_without_game_pk


def _analyze_game(game_logs):
    start_logs = []
    relief_logs = []
    unknown_logs = []
    missing_start_innings_rows = 0
    missing_relief_innings_rows = 0
    game_date = None

    for log in game_logs or []:
        if game_date is None:
            game_date = _date_value(_value(log, 'game_date'))
        state = games_started_state(_value(log, 'games_started'))
        outs = _log_outs(log)
        if state == START:
            if outs is None:
                missing_start_innings_rows += 1
                continue
            start_logs.append((log, outs))
        elif state == RELIEF:
            if outs is None:
                missing_relief_innings_rows += 1
                continue
            relief_logs.append((log, outs))
        else:
            unknown_logs.append((log, outs))

    if missing_start_innings_rows:
        return None, 'missing_starter_innings'
    if len(start_logs) != 1:
        return None, 'multiple_starters' if len(start_logs) > 1 else 'no_starter'

    starter_outs = start_logs[0][1]
    bullpen_outs = sum(outs for _log, outs in relief_logs)
    known_outs = starter_outs + bullpen_outs
    coverage_reason = None
    if unknown_logs:
        coverage_reason = 'unknown_split'
    elif missing_relief_innings_rows:
        coverage_reason = 'missing_relief_innings'
    elif known_outs < MIN_COMPLETE_TEAM_GAME_OUTS:
        coverage_reason = 'incomplete_outs'

    return {
        'game_date': game_date,
        'starter_outs': starter_outs,
        'bullpen_outs': bullpen_outs,
        'known_outs': known_outs,
        'coverage_available': coverage_reason is None,
        'coverage_exclusion_reason': coverage_reason,
        'early_bullpen_entry': starter_outs < EARLY_BULLPEN_ENTRY_OUTS,
    }, None


def _average_ip(games):
    games = list(games or [])
    if not games:
        return None
    outs = sum(game['starter_outs'] for game in games)
    return round(outs_to_decimal_innings(outs) / len(games), 1)


def _coverage_ip(games):
    games = [game for game in (games or []) if game.get('coverage_available')]
    if not games:
        return None
    outs = sum(game['bullpen_outs'] for game in games)
    return round(outs_to_decimal_innings(outs) / len(games), 1)


def _early_entry_rate(games):
    games = list(games or [])
    if not games:
        return None
    early = sum(1 for game in games if game['early_bullpen_entry'])
    return round(early / len(games) * 100.0, 1)


def _trend(avg_7d, avg_14d):
    if avg_7d is None or avg_14d is None:
        return None
    return round(avg_7d - avg_14d, 1)


def build_rotation_context(logs, *, reference_date=None):
    """Build Rotation Context Layer 1 metrics from raw team game logs."""
    rows = list(logs or [])
    ref = _reference_date(rows, reference_date=reference_date)
    grouped, rows_without_game_pk = _group_logs(rows, reference_date=ref)
    exclusion_reasons = Counter()
    coverage_exclusion_reasons = Counter()
    analyzed = []

    for game_pk, game_logs in grouped.items():
        item, reason = _analyze_game(game_logs)
        if item is None:
            exclusion_reasons[reason] += 1
            continue
        item['mlb_game_pk'] = game_pk
        analyzed.append(item)
        if item.get('coverage_exclusion_reason'):
            coverage_exclusion_reasons[item['coverage_exclusion_reason']] += 1

    window_7_start = ref - timedelta(days=ROTATION_CONTEXT_7D - 1)
    window_14_start = ref - timedelta(days=ROTATION_CONTEXT_14D - 1)
    games_7d = [
        game for game in analyzed
        if game['game_date'] is not None and window_7_start <= game['game_date'] <= ref
    ]
    games_14d = [
        game for game in analyzed
        if game['game_date'] is not None and window_14_start <= game['game_date'] <= ref
    ]

    avg_7d = _average_ip(games_7d)
    avg_14d = _average_ip(games_14d)
    limitations = [CURRENT_ASSIGNMENT_LIMITATION, OPENER_BULK_LIMITATION]
    if exclusion_reasons or coverage_exclusion_reasons or rows_without_game_pk:
        limitations.append(INCOMPLETE_GAME_DATA_LIMITATION)

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': 'backend',
        'reference_date': ref.isoformat(),
        'window_start_7d': window_7_start.isoformat(),
        'window_start_14d': window_14_start.isoformat(),
        'rotation_avg_ip_7d': avg_7d,
        'rotation_avg_ip_14d': avg_14d,
        'rotation_ip_trend': _trend(avg_7d, avg_14d),
        'early_bullpen_entry_rate': _early_entry_rate(games_14d),
        'bullpen_coverage_ip_7d': _coverage_ip(games_7d),
        'games_in_window_14d': len(grouped),
        'games_analyzed_7d': len(games_7d),
        'games_analyzed_14d': len(games_14d),
        'games_excluded_14d': sum(exclusion_reasons.values()),
        'coverage_games_7d': sum(1 for game in games_7d if game.get('coverage_available')),
        'coverage_games_14d': sum(1 for game in games_14d if game.get('coverage_available')),
        'early_bullpen_entry_games_14d': sum(
            1 for game in games_14d if game['early_bullpen_entry']
        ),
        'excluded_game_reasons': dict(exclusion_reasons),
        'coverage_excluded_game_reasons': dict(coverage_exclusion_reasons),
        'rows_without_game_pk': rows_without_game_pk,
        'limitations': limitations,
    }


__all__ = [
    'CAPABILITY',
    'CURRENT_ASSIGNMENT_LIMITATION',
    'EARLY_BULLPEN_ENTRY_OUTS',
    'INCOMPLETE_GAME_DATA_LIMITATION',
    'MIN_COMPLETE_TEAM_GAME_OUTS',
    'OPENER_BULK_LIMITATION',
    'ROTATION_CONTEXT_7D',
    'ROTATION_CONTEXT_14D',
    'VERSION',
    'build_rotation_context',
]
