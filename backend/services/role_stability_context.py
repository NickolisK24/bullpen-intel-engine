"""Bullpen Role Stability Context Layer 4.

This module compares recent bullpen workload cores across two historical
windows. It is descriptive only: no official roles, leverage assumptions,
quality ratings, rankings, predictions, public UI, or story output are
produced here.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from services.availability_reference_date import product_current_date
from services.bullpen_concentration_context import (
    BULLPEN_CONCENTRATION_WINDOW_DAYS,
    TOP_RELIEVER_COUNT,
)
from services.workload_appearance import (
    is_pitch_count_workload_log,
    is_workload_appearance_log,
    workload_pitch_count,
)
from utils.games_started import RELIEF, START, UNKNOWN, games_started_state


CAPABILITY = 'role_stability_context_v1'
VERSION = '2026-06-21.layer4'

ROLE_STABILITY_STABLE = 'stable'
ROLE_STABILITY_MOSTLY_STABLE = 'mostly_stable'
ROLE_STABILITY_TRANSITIONING = 'transitioning'
ROLE_STABILITY_REBUILDING = 'rebuilding'
ROLE_STABILITY_INSUFFICIENT_DATA = 'insufficient_data'

CURRENT_ASSIGNMENT_LIMITATION = (
    'Role stability uses pitchers currently assigned to the team because game logs do not yet store team-at-appearance.'
)
WORKLOAD_CONTEXT_LIMITATION = (
    'Role stability uses recorded positive pitch-count workload only; it does not infer official roles, leverage, quality, or future usage.'
)
COMPARISON_WORKLOAD_LIMITATION = (
    'Role stability requires valid bullpen workload in both comparison windows.'
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


def _windows(reference_date):
    days = BULLPEN_CONCENTRATION_WINDOW_DAYS
    return {
        'current': {
            'start_date': reference_date - timedelta(days=days - 1),
            'end_date': reference_date,
        },
        'previous': {
            'start_date': reference_date - timedelta(days=(days * 2) - 1),
            'end_date': reference_date - timedelta(days=days),
        },
    }


def _iso(value):
    return value.isoformat() if value else None


def _empty_context(reference_date=None, windows=None):
    ref = _date_value(reference_date)
    current = (windows or {}).get('current') or {}
    previous = (windows or {}).get('previous') or {}
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': 'backend',
        'context_available': False,
        'reference_date': _iso(ref),
        'current_window_start_10d': _iso(current.get('start_date')),
        'current_window_end_10d': _iso(current.get('end_date')),
        'previous_window_start_10d': _iso(previous.get('start_date')),
        'previous_window_end_10d': _iso(previous.get('end_date')),
        'current_operational_core': [],
        'previous_operational_core': [],
        'core_retention_count': 0,
        'core_stability_pct': None,
        'core_change_count': 0,
        'stability_band': ROLE_STABILITY_INSUFFICIENT_DATA,
        'new_core_members': [],
        'departed_core_members': [],
        'role_stability_summary_inputs': {
            'current_core': [],
            'previous_core': [],
            'retention_count': 0,
            'stability_pct': None,
            'change_count': 0,
            'band': ROLE_STABILITY_INSUFFICIENT_DATA,
        },
        'current_core_size': 0,
        'previous_core_size': 0,
        'current_workload_total_10d': 0,
        'previous_workload_total_10d': 0,
        'excluded_starting_workload_rows_20d': 0,
        'unknown_role_rows_excluded_20d': 0,
        'zero_pitch_artifact_rows_excluded_20d': 0,
        'non_pitch_workload_rows_excluded_20d': 0,
        'rows_without_pitcher_id_20d': 0,
        'excluded_row_reasons': {},
        'limitations': [
            CURRENT_ASSIGNMENT_LIMITATION,
            WORKLOAD_CONTEXT_LIMITATION,
            COMPARISON_WORKLOAD_LIMITATION,
        ],
    }


def stability_band(stability_pct):
    if stability_pct is None:
        return ROLE_STABILITY_INSUFFICIENT_DATA
    if stability_pct >= 100:
        return ROLE_STABILITY_STABLE
    if stability_pct >= 67:
        return ROLE_STABILITY_MOSTLY_STABLE
    if stability_pct >= 33:
        return ROLE_STABILITY_TRANSITIONING
    return ROLE_STABILITY_REBUILDING


def _window_name(game_date, windows):
    for name, bounds in windows.items():
        if bounds['start_date'] <= game_date <= bounds['end_date']:
            return name
    return None


def _is_zero_pitch_artifact(log: Any):
    return not is_workload_appearance_log(log)


def _display_name(row):
    name = row.get('name')
    if name:
        return name
    player_id = row.get('player_id')
    return str(player_id) if player_id is not None else None


def _core_for_window(rows):
    relievers = [
        row for row in rows.values()
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
    return relievers[:TOP_RELIEVER_COUNT], sum(row['pitches'] for row in relievers)


def _member_names(rows):
    return [
        name for name in (_display_name(row) for row in rows)
        if name is not None
    ]


def _names_for_keys(rows, keys):
    return [
        _display_name(row)
        for row in rows
        if row['key'] in keys and _display_name(row) is not None
    ]


def _core_change_count(current_core_size, retention_count, comparison_available):
    if not comparison_available:
        return 0
    return max(0, current_core_size - retention_count)


def build_role_stability_context(logs, *, reference_date=None):
    """Build Bullpen Role Stability Context Layer 4 from raw team game logs."""
    rows = list(logs or [])
    ref = _reference_date(rows, reference_date=reference_date)
    windows = _windows(ref)
    if not rows:
        return _empty_context(reference_date=ref, windows=windows)

    reliever_rows = {
        'current': defaultdict(lambda: {
            'key': None,
            'player_id': None,
            'name': None,
            'pitches': 0,
            'appearances': 0,
        }),
        'previous': defaultdict(lambda: {
            'key': None,
            'player_id': None,
            'name': None,
            'pitches': 0,
            'appearances': 0,
        }),
    }
    exclusions = Counter()

    for log in rows:
        game_date = _date_value(_value(log, 'game_date'))
        if game_date is None or not _is_regular_season(log):
            continue
        window = _window_name(game_date, windows)
        if window is None:
            continue

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

        row = reliever_rows[window][pitcher_key]
        row['key'] = pitcher_key
        row['player_id'] = row['player_id'] or _player_id(log)
        row['name'] = row['name'] or _player_name(log)
        row['pitches'] += workload_pitch_count(log) or 0
        row['appearances'] += 1

    current_core, current_total = _core_for_window(reliever_rows['current'])
    previous_core, previous_total = _core_for_window(reliever_rows['previous'])
    current_names = _member_names(current_core)
    previous_names = _member_names(previous_core)
    current_keys = {row['key'] for row in current_core}
    previous_keys = {row['key'] for row in previous_core}
    comparison_available = bool(current_core and previous_core)
    retained_keys = current_keys & previous_keys if comparison_available else set()
    retention_count = len(retained_keys)
    stability_pct = (
        int(round(retention_count / len(current_core) * 100))
        if comparison_available and current_core
        else None
    )
    band = stability_band(stability_pct)
    change_count = _core_change_count(len(current_core), retention_count, comparison_available)
    new_core_members = _names_for_keys(current_core, current_keys - previous_keys) if comparison_available else []
    departed_core_members = (
        _names_for_keys(previous_core, previous_keys - current_keys)
        if comparison_available
        else []
    )

    limitations = [CURRENT_ASSIGNMENT_LIMITATION, WORKLOAD_CONTEXT_LIMITATION]
    if not comparison_available:
        limitations.append(COMPARISON_WORKLOAD_LIMITATION)
    if exclusions:
        limitations.append(INCOMPLETE_WORKLOAD_LIMITATION)

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': 'backend',
        'context_available': comparison_available,
        'reference_date': ref.isoformat(),
        'current_window_start_10d': windows['current']['start_date'].isoformat(),
        'current_window_end_10d': windows['current']['end_date'].isoformat(),
        'previous_window_start_10d': windows['previous']['start_date'].isoformat(),
        'previous_window_end_10d': windows['previous']['end_date'].isoformat(),
        'current_operational_core': current_names,
        'previous_operational_core': previous_names,
        'core_retention_count': retention_count,
        'core_stability_pct': stability_pct,
        'core_change_count': change_count,
        'stability_band': band,
        'new_core_members': new_core_members,
        'departed_core_members': departed_core_members,
        'role_stability_summary_inputs': {
            'current_core': current_names,
            'previous_core': previous_names,
            'retention_count': retention_count,
            'stability_pct': stability_pct,
            'change_count': change_count,
            'band': band,
        },
        'current_core_size': len(current_core),
        'previous_core_size': len(previous_core),
        'current_workload_total_10d': current_total,
        'previous_workload_total_10d': previous_total,
        'excluded_starting_workload_rows_20d': exclusions['starter_workload'],
        'unknown_role_rows_excluded_20d': exclusions['unknown_role'],
        'zero_pitch_artifact_rows_excluded_20d': exclusions['zero_pitch_artifact'],
        'non_pitch_workload_rows_excluded_20d': exclusions['non_pitch_workload'],
        'rows_without_pitcher_id_20d': exclusions['missing_pitcher_id'],
        'excluded_row_reasons': dict(exclusions),
        'limitations': limitations,
    }


def empty_role_stability_context():
    """Return the normalized no-data Layer 4 context shape."""
    return _empty_context()


__all__ = [
    'CAPABILITY',
    'COMPARISON_WORKLOAD_LIMITATION',
    'CURRENT_ASSIGNMENT_LIMITATION',
    'INCOMPLETE_WORKLOAD_LIMITATION',
    'ROLE_STABILITY_INSUFFICIENT_DATA',
    'ROLE_STABILITY_MOSTLY_STABLE',
    'ROLE_STABILITY_REBUILDING',
    'ROLE_STABILITY_STABLE',
    'ROLE_STABILITY_TRANSITIONING',
    'VERSION',
    'WORKLOAD_CONTEXT_LIMITATION',
    'build_role_stability_context',
    'empty_role_stability_context',
    'stability_band',
]
