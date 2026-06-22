"""Bullpen Concentration Context Layer 2.

This module measures whether recent bullpen pitch workload is spread across
the group or concentrated into a small number of relievers. It is descriptive
only: no scores, rankings, predictions, roles, leverage labels, or story output
are produced here.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from services.availability_reference_date import product_current_date
from services.baseline_distribution import build_distribution
from services.baseline_engine import interpret_value
from services.workload_appearance import (
    is_pitch_count_workload_log,
    is_workload_appearance_log,
    workload_pitch_count,
)
from utils.games_started import RELIEF, START, UNKNOWN, games_started_state


CAPABILITY = 'bullpen_concentration_context_v1'
VERSION = '2026-06-21.layer2'

BULLPEN_CONCENTRATION_WINDOW_DAYS = 10
TOP_RELIEVER_COUNT = 3

CONCENTRATION_BALANCED = 'balanced'
CONCENTRATION_NORMAL = 'normal'
CONCENTRATION_CONCENTRATED = 'concentrated'
CONCENTRATION_NARROW = 'narrow'
CONCENTRATION_INSUFFICIENT_DATA = 'insufficient_data'

CURRENT_ASSIGNMENT_LIMITATION = (
    'Bullpen concentration uses currently assigned pitchers because game logs do not yet store team-at-appearance.'
)
PITCH_COUNT_WORKLOAD_LIMITATION = (
    'Bullpen concentration uses recorded positive pitch-count workload only; it does not estimate missing pitch totals.'
)
INCOMPLETE_WORKLOAD_LIMITATION = (
    'Some rows are excluded because role or pitch-count workload data is incomplete.'
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


def _pitcher_key(log: Any):
    pitcher_id = _value(log, 'pitcher_id')
    if pitcher_id is not None:
        return pitcher_id
    return _value(log, 'player_id')


def _pitcher_obj(log: Any):
    return _value(log, 'pitcher')


def _player_id(log: Any):
    pitcher = _pitcher_obj(log)
    return (
        _value(pitcher, 'mlb_id')
        or _value(log, 'player_id')
        or _value(log, 'mlb_id')
        or _pitcher_key(log)
    )


def _player_name(log: Any):
    pitcher = _pitcher_obj(log)
    return (
        _value(pitcher, 'full_name')
        or _value(log, 'pitcher_name')
        or _value(log, 'name')
    )


def _team_id(log: Any):
    pitcher = _pitcher_obj(log)
    return _value(pitcher, 'team_id') or _value(log, 'team_id')


def _window_logs(logs, *, reference_date, window_days=BULLPEN_CONCENTRATION_WINDOW_DAYS):
    window_start = reference_date - timedelta(days=window_days - 1)
    rows = []
    for log in logs or []:
        game_date = _date_value(_value(log, 'game_date'))
        if game_date is None or game_date < window_start or game_date > reference_date:
            continue
        if not _is_regular_season(log):
            continue
        rows.append(log)
    return rows, window_start


def _is_zero_pitch_artifact(log: Any):
    return not is_workload_appearance_log(log)


def _empty_context(ref, window_start, league_baseline=None):
    league_baseline = league_baseline or {}
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': 'backend',
        'reference_date': ref.isoformat() if ref else None,
        'window_days': BULLPEN_CONCENTRATION_WINDOW_DAYS,
        'window_start_10d': window_start.isoformat() if window_start else None,
        'window_end_10d': ref.isoformat() if ref else None,
        'top_three_workload_share_10d': None,
        'league_top_three_workload_share_10d': league_baseline.get(
            'league_top_three_workload_share_10d'
        ),
        'top_three_share_delta_vs_league': None,
        'baseline_read': _baseline_read(None, league_baseline),
        'bullpen_workload_total_10d': 0,
        'concentration_band': CONCENTRATION_INSUFFICIENT_DATA,
        'top_three_relievers_10d': [],
        'qualifying_reliever_count_10d': 0,
        'bullpen_workload_appearances_10d': 0,
        'league_team_count_10d': league_baseline.get('league_team_count_10d', 0),
        'excluded_starting_workload_rows_10d': 0,
        'unknown_role_rows_excluded_10d': 0,
        'zero_pitch_artifact_rows_excluded_10d': 0,
        'non_pitch_workload_rows_excluded_10d': 0,
        'rows_without_pitcher_id_10d': 0,
        'excluded_row_reasons': {},
        'limitations': [CURRENT_ASSIGNMENT_LIMITATION, PITCH_COUNT_WORKLOAD_LIMITATION],
    }


def concentration_band(top_three_share):
    if top_three_share is None:
        return CONCENTRATION_INSUFFICIENT_DATA
    if top_three_share < 55.0:
        return CONCENTRATION_BALANCED
    if top_three_share <= 65.0:
        return CONCENTRATION_NORMAL
    if top_three_share <= 80.0:
        return CONCENTRATION_CONCENTRATED
    return CONCENTRATION_NARROW


def _share(part, total):
    if total <= 0:
        return None
    return round(part / total * 100.0, 1)


def _delta(value, baseline):
    if value is None or baseline is None:
        return None
    return round(value - baseline, 1)


def _league_baseline_value(league_baseline):
    if league_baseline is None:
        return None
    if isinstance(league_baseline, dict):
        return league_baseline.get('league_top_three_workload_share_10d')
    return league_baseline


def _league_baseline_distribution(league_baseline):
    if isinstance(league_baseline, dict):
        return league_baseline.get('top_three_workload_share_distribution_10d')
    return None


def _baseline_read(top_three_share, league_baseline):
    # Distribution-aware league read for the top-three workload share. The shared
    # baseline engine owns the interpretation; this only feeds it the team value
    # and the 10-day league distribution, in the same percentage units.
    return interpret_value(
        'top_share',
        top_three_share,
        _league_baseline_distribution(league_baseline),
    )


def build_bullpen_concentration_context(
    logs,
    *,
    reference_date=None,
    league_baseline=None,
):
    """Build Bullpen Concentration Context Layer 2 from raw team game logs."""
    rows = list(logs or [])
    ref = _reference_date(rows, reference_date=reference_date)
    window_rows, window_start = _window_logs(rows, reference_date=ref)

    if not window_rows:
        return _empty_context(ref, window_start, league_baseline=league_baseline)

    reliever_rows = defaultdict(lambda: {
        'player_id': None,
        'name': None,
        'pitches': 0,
        'appearances': 0,
    })
    exclusions = Counter()

    for log in window_rows:
        state = games_started_state(_value(log, 'games_started'))
        if state == START:
            exclusions['starter_workload'] += 1
            continue
        if state == UNKNOWN:
            exclusions['unknown_role'] += 1
            continue
        if state != RELIEF:
            exclusions['unknown_role'] += 1
            continue
        if not is_pitch_count_workload_log(log):
            if _is_zero_pitch_artifact(log):
                exclusions['zero_pitch_artifact'] += 1
            else:
                exclusions['non_pitch_workload'] += 1
            continue

        pitcher_key = _pitcher_key(log)
        if pitcher_key is None:
            exclusions['missing_pitcher_id'] += 1
            continue

        pitches = workload_pitch_count(log)
        row = reliever_rows[pitcher_key]
        row['player_id'] = row['player_id'] or _player_id(log)
        row['name'] = row['name'] or _player_name(log)
        row['pitches'] += pitches or 0
        row['appearances'] += 1

    relievers = [
        row for row in reliever_rows.values()
        if row['pitches'] > 0
    ]
    relievers.sort(
        key=lambda row: (
            -row['pitches'],
            -row['appearances'],
            str(row.get('name') or '').lower(),
            row.get('player_id') or 0,
        )
    )

    total_workload = sum(row['pitches'] for row in relievers)
    if total_workload <= 0:
        context = _empty_context(ref, window_start, league_baseline=league_baseline)
        context.update({
            'excluded_starting_workload_rows_10d': exclusions['starter_workload'],
            'unknown_role_rows_excluded_10d': exclusions['unknown_role'],
            'zero_pitch_artifact_rows_excluded_10d': exclusions['zero_pitch_artifact'],
            'non_pitch_workload_rows_excluded_10d': exclusions['non_pitch_workload'],
            'rows_without_pitcher_id_10d': exclusions['missing_pitcher_id'],
            'excluded_row_reasons': dict(exclusions),
        })
        if exclusions:
            context['limitations'].append(INCOMPLETE_WORKLOAD_LIMITATION)
        return context

    top_three = relievers[:TOP_RELIEVER_COUNT]
    top_three_total = sum(row['pitches'] for row in top_three)
    top_three_share = _share(top_three_total, total_workload)
    league_value = _league_baseline_value(league_baseline)
    league_team_count = (
        (league_baseline or {}).get('league_team_count_10d', 0)
        if isinstance(league_baseline, dict)
        else 0
    )
    limitations = [CURRENT_ASSIGNMENT_LIMITATION, PITCH_COUNT_WORKLOAD_LIMITATION]
    if exclusions:
        limitations.append(INCOMPLETE_WORKLOAD_LIMITATION)

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': 'backend',
        'reference_date': ref.isoformat(),
        'window_days': BULLPEN_CONCENTRATION_WINDOW_DAYS,
        'window_start_10d': window_start.isoformat(),
        'window_end_10d': ref.isoformat(),
        'top_three_workload_share_10d': top_three_share,
        'league_top_three_workload_share_10d': league_value,
        'top_three_share_delta_vs_league': _delta(top_three_share, league_value),
        'baseline_read': _baseline_read(top_three_share, league_baseline),
        'bullpen_workload_total_10d': total_workload,
        'concentration_band': concentration_band(top_three_share),
        'top_three_relievers_10d': [
            {
                'player_id': row['player_id'],
                'name': row['name'],
                'workload_share': _share(row['pitches'], total_workload),
                'pitches': row['pitches'],
                'appearances': row['appearances'],
            }
            for row in top_three
        ],
        'qualifying_reliever_count_10d': len(relievers),
        'bullpen_workload_appearances_10d': sum(row['appearances'] for row in relievers),
        'league_team_count_10d': league_team_count,
        'excluded_starting_workload_rows_10d': exclusions['starter_workload'],
        'unknown_role_rows_excluded_10d': exclusions['unknown_role'],
        'zero_pitch_artifact_rows_excluded_10d': exclusions['zero_pitch_artifact'],
        'non_pitch_workload_rows_excluded_10d': exclusions['non_pitch_workload'],
        'rows_without_pitcher_id_10d': exclusions['missing_pitcher_id'],
        'excluded_row_reasons': dict(exclusions),
        'limitations': limitations,
    }


def build_league_bullpen_concentration_baseline(logs, *, reference_date=None):
    """Compute league average top-three bullpen workload share for the window."""
    rows = list(logs or [])
    ref = _reference_date(rows, reference_date=reference_date)
    window_rows, _window_start = _window_logs(rows, reference_date=ref)
    by_team = defaultdict(list)
    for log in window_rows:
        team_id = _team_id(log)
        if team_id is None:
            continue
        by_team[team_id].append(log)

    shares = []
    for team_logs in by_team.values():
        context = build_bullpen_concentration_context(team_logs, reference_date=ref)
        share = context.get('top_three_workload_share_10d')
        if share is not None and context.get('bullpen_workload_total_10d', 0) > 0:
            shares.append(share)

    league_share = round(sum(shares) / len(shares), 1) if shares else None
    return {
        'league_top_three_workload_share_10d': league_share,
        'league_team_count_10d': len(shares),
        'top_three_workload_share_distribution_10d': build_distribution(shares),
    }


def empty_bullpen_concentration_context():
    """Return the normalized no-data Layer 2 context shape."""
    return _empty_context(None, None)


__all__ = [
    'BULLPEN_CONCENTRATION_WINDOW_DAYS',
    'CAPABILITY',
    'CONCENTRATION_BALANCED',
    'CONCENTRATION_CONCENTRATED',
    'CONCENTRATION_INSUFFICIENT_DATA',
    'CONCENTRATION_NARROW',
    'CONCENTRATION_NORMAL',
    'CURRENT_ASSIGNMENT_LIMITATION',
    'INCOMPLETE_WORKLOAD_LIMITATION',
    'PITCH_COUNT_WORKLOAD_LIMITATION',
    'TOP_RELIEVER_COUNT',
    'VERSION',
    'build_bullpen_concentration_context',
    'build_league_bullpen_concentration_baseline',
    'concentration_band',
    'empty_bullpen_concentration_context',
]
