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
from services.baseline_distribution import build_distribution
from services.baseline_engine import interpret_value
from services.game_shape import (
    SHAPE_BULLPEN_GAME,
    SHAPE_OPENER_BULK_GAME,
    game_shape_of,
)
from utils.games_started import RELIEF, START, games_started_state
from utils.innings import log_innings_outs, outs_to_decimal_innings


CAPABILITY = 'rotation_context_v1'
VERSION = '2026-06-20.layer1'

ROTATION_CONTEXT_7D = 7
ROTATION_CONTEXT_14D = 14
EARLY_BULLPEN_ENTRY_OUTS = 15
MIN_COMPLETE_TEAM_GAME_OUTS = 24

# Game shapes excluded from rotation-depth averages and early-bullpen-entry. An
# opener/bulk game is not a rotation start, so it must not drag starter depth or
# read as a failed start. Bullpen games have no starter and are already excluded
# from analysis; they are surfaced separately via the game-shape distribution.
ROTATION_DEPTH_EXCLUDED_SHAPES = frozenset({SHAPE_OPENER_BULK_GAME})

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
        # Additive game-shape metadata only; it does not affect any calculation.
        'game_shape': game_shape_of(game_logs),
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
    game_shape_counts = Counter()
    analyzed = []

    for game_pk, game_logs in grouped.items():
        item, reason = _analyze_game(game_logs)
        if item is None:
            exclusion_reasons[reason] += 1
            # Classify excluded games (e.g. bullpen games) too so the game-shape
            # distribution is complete. This is metadata only and changes no
            # existing calculation or which games are analyzed.
            game_shape_counts[game_shape_of(game_logs)] += 1
            continue
        item['mlb_game_pk'] = game_pk
        game_shape_counts[item['game_shape']] += 1
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

    # Opener/bulk games are not rotation starts: exclude them from starter-depth
    # averages and early-bullpen-entry so a short opener in front of a long bulk
    # arm is not read as a failed rotation start. Coverage burden is unchanged.
    rotation_games_7d = [
        game for game in games_7d
        if game.get('game_shape') not in ROTATION_DEPTH_EXCLUDED_SHAPES
    ]
    rotation_games_14d = [
        game for game in games_14d
        if game.get('game_shape') not in ROTATION_DEPTH_EXCLUDED_SHAPES
    ]

    avg_7d = _average_ip(rotation_games_7d)
    avg_14d = _average_ip(rotation_games_14d)
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
        'early_bullpen_entry_rate': _early_entry_rate(rotation_games_14d),
        'bullpen_coverage_ip_7d': _coverage_ip(games_7d),
        'games_in_window_14d': len(grouped),
        'games_analyzed_7d': len(games_7d),
        'games_analyzed_14d': len(games_14d),
        'rotation_starts_7d': len(rotation_games_7d),
        'rotation_starts_14d': len(rotation_games_14d),
        'opener_bulk_games_7d': sum(
            1 for game in games_7d if game.get('game_shape') == SHAPE_OPENER_BULK_GAME
        ),
        'opener_bulk_games_14d': sum(
            1 for game in games_14d if game.get('game_shape') == SHAPE_OPENER_BULK_GAME
        ),
        'bullpen_games_count': game_shape_counts.get(SHAPE_BULLPEN_GAME, 0),
        'games_excluded_14d': sum(exclusion_reasons.values()),
        'coverage_games_7d': sum(1 for game in games_7d if game.get('coverage_available')),
        'coverage_games_14d': sum(1 for game in games_14d if game.get('coverage_available')),
        'early_bullpen_entry_games_14d': sum(
            1 for game in rotation_games_14d if game['early_bullpen_entry']
        ),
        'excluded_game_reasons': dict(exclusion_reasons),
        'coverage_excluded_game_reasons': dict(coverage_exclusion_reasons),
        'game_shape_distribution': dict(game_shape_counts),
        'rows_without_game_pk': rows_without_game_pk,
        'limitations': limitations,
    }


ROTATION_LENGTH_BASELINE_METRIC = 'rotation_avg_ip_7d'
BULLPEN_COVERAGE_BASELINE_METRIC = 'bullpen_coverage_ip_7d'


def _team_id(log: Any):
    pitcher = _value(log, 'pitcher')
    return _value(pitcher, 'team_id') or _value(log, 'team_id')


def build_league_rotation_baseline(logs, *, reference_date=None):
    """Current 7-day-window league distribution of rotation_avg_ip_7d.

    Groups raw league game logs by team and reuses ``build_rotation_context`` so
    each team's rotation_avg_ip_7d is derived with the exact same starter-IP and
    start-classification logic as the per-team story value (one value per team).
    Teams without a usable 7-day rotation_avg_ip_7d are skipped, not counted low.
    This is a dedicated rotation distribution: independent of dashboard.baselines,
    the workload-concentration distribution, and the clean-options distribution.
    """
    by_team = defaultdict(list)
    for log in logs or []:
        team_id = _team_id(log)
        if team_id is None:
            continue
        by_team[team_id].append(log)

    values = []
    coverage_values = []
    for team_logs in by_team.values():
        context = build_rotation_context(team_logs, reference_date=reference_date)
        avg_7d = context.get('rotation_avg_ip_7d')
        if avg_7d is not None:
            values.append(avg_7d)
        coverage = context.get('bullpen_coverage_ip_7d')
        if coverage is not None:
            coverage_values.append(coverage)

    return {
        'rotation_avg_ip_7d_distribution': build_distribution(values),
        'bullpen_coverage_ip_7d_distribution': build_distribution(coverage_values),
        'league_team_count': len(values),
    }


def _league_rotation_distribution(league_baseline):
    if isinstance(league_baseline, dict):
        return league_baseline.get('rotation_avg_ip_7d_distribution')
    return None


def rotation_length_baseline_read(avg_7d, league_baseline):
    # Distribution-aware league read of the team's recent starter length. The
    # shared baseline engine owns the interpretation; this only feeds it the team
    # value and the current 7-day league distribution (longer starts are deeper).
    return interpret_value(
        ROTATION_LENGTH_BASELINE_METRIC,
        avg_7d,
        _league_rotation_distribution(league_baseline),
    )


def _league_coverage_distribution(league_baseline):
    if isinstance(league_baseline, dict):
        return league_baseline.get('bullpen_coverage_ip_7d_distribution')
    return None


def bullpen_coverage_baseline_read(coverage_ip, league_baseline):
    # Distribution-aware league read of the team's recent bullpen-coverage burden.
    # Separate from the rotation-length read; same dedicated 7-day league window.
    # Higher coverage is more bullpen burden; the language layer assigns direction.
    return interpret_value(
        BULLPEN_COVERAGE_BASELINE_METRIC,
        coverage_ip,
        _league_coverage_distribution(league_baseline),
    )


__all__ = [
    'CAPABILITY',
    'CURRENT_ASSIGNMENT_LIMITATION',
    'EARLY_BULLPEN_ENTRY_OUTS',
    'INCOMPLETE_GAME_DATA_LIMITATION',
    'MIN_COMPLETE_TEAM_GAME_OUTS',
    'OPENER_BULK_LIMITATION',
    'ROTATION_CONTEXT_7D',
    'ROTATION_CONTEXT_14D',
    'BULLPEN_COVERAGE_BASELINE_METRIC',
    'ROTATION_LENGTH_BASELINE_METRIC',
    'VERSION',
    'build_league_rotation_baseline',
    'build_rotation_context',
    'bullpen_coverage_baseline_read',
    'rotation_length_baseline_read',
]
