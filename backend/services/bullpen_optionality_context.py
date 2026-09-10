"""Bullpen Optionality Context Layer 3.

This module measures practical bullpen flexibility from existing BaseballOS
availability and workload evidence. It is descriptive only: no scores,
rankings, predictions, public UI, story output, ERA, leverage, or official role
inference are produced here.
"""

from __future__ import annotations

from datetime import date, datetime
from math import floor
from typing import Any

from services.availability import (
    STATUS_AVAILABLE,
    STATUS_AVOID,
    STATUS_LIMITED,
    STATUS_MONITOR,
    STATUS_UNAVAILABLE,
)
from services.availability_reference_date import product_current_date
from services.baseline_distribution import build_distribution
from services.baseline_engine import interpret_value
from services.workload_appearance import workload_appearance_logs


CAPABILITY = 'bullpen_optionality_context_v1'
VERSION = '2026-06-21.layer3'

OPTIONALITY_THIN = 'thin'
OPTIONALITY_NARROW = 'narrow'
OPTIONALITY_FLEXIBLE = 'flexible'
OPTIONALITY_DEEP = 'deep'
OPTIONALITY_INSUFFICIENT_DATA = 'insufficient_data'

RESTRICTED_STATUSES = {STATUS_LIMITED, STATUS_AVOID, STATUS_UNAVAILABLE}
LIMITED_DATA_STATES = {'stale', 'missing', 'incomplete', 'failed', 'historical', 'unknown'}

NO_OPTIONALITY_DATA_LIMITATION = (
    'No current bullpen availability records were available to measure optionality.'
)
INCOMPLETE_OPTIONALITY_DATA_LIMITATION = (
    'Some bullpen optionality inputs are limited-read or missing current availability status.'
)
WORKLOAD_CONTEXT_LIMITATION = (
    'Optionality uses current availability labels and valid workload appearances only; it does not infer roles or predict usage.'
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


def _reference_date(records, reference_date=None):
    ref = _date_value(reference_date)
    if ref is not None:
        return ref
    dates = [
        parsed
        for record in records or []
        for parsed in (
            _date_value(_value(record, 'evaluation_date')),
            _date_value(_value(record, 'latest_game_date')),
        )
        if parsed is not None
    ]
    return max(dates, default=product_current_date())


def _pitcher(record):
    return _value(record, 'pitcher')


def _pitcher_id(record):
    return _value(record, 'pitcher_id') or _value(_pitcher(record), 'id')


def _player_id(record):
    pitcher = _pitcher(record)
    return (
        _value(pitcher, 'mlb_id')
        or _value(record, 'player_id')
        or _value(record, 'mlb_id')
        or _pitcher_id(record)
    )


def _name(record):
    pitcher = _pitcher(record)
    return (
        _value(record, 'name')
        or _value(record, 'pitcher_name')
        or _value(pitcher, 'full_name')
    )


def _availability(record):
    availability = _value(record, 'availability') or {}
    return availability if isinstance(availability, dict) else {}


def _status(record):
    return _availability(record).get('availability_status')


def _inputs(record):
    inputs = _availability(record).get('inputs') or {}
    return inputs if isinstance(inputs, dict) else {}


def _reasons(record):
    reasons = _availability(record).get('reasons') or []
    return [str(reason) for reason in reasons if reason]


def _norm(value):
    return str(value or '').strip().lower()


def _int_value(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def optionality_band(practical_paths, *, context_available=True):
    if not context_available:
        return OPTIONALITY_INSUFFICIENT_DATA
    practical_paths = _int_value(practical_paths)
    if practical_paths <= 2:
        return OPTIONALITY_THIN
    if practical_paths == 3:
        return OPTIONALITY_NARROW
    if practical_paths <= 5:
        return OPTIONALITY_FLEXIBLE
    return OPTIONALITY_DEEP


def _workload_warning(record):
    availability = _availability(record)
    inputs = _inputs(record)
    if _norm(availability.get('data_state')) in LIMITED_DATA_STATES:
        return True
    if _norm(availability.get('confidence')) in {'low', 'none', 'unknown'}:
        return True
    if _reasons(record):
        return True
    return any([
        bool(inputs.get('back_to_back')),
        bool(inputs.get('three_in_four')),
        bool(inputs.get('four_in_five')),
        _int_value(inputs.get('pitches_yesterday')) >= 15,
        _int_value(inputs.get('pitches_last_3_days')) >= 30,
        _int_value(inputs.get('appearances_last_5_days')) >= 2,
        bool(inputs.get('workload_fetch_failed')),
    ])


def _recent_workload_label(record):
    inputs = _inputs(record)
    appearances = _int_value(inputs.get('appearances_last_5_days'))
    pitches = _int_value(inputs.get('pitches_last_5_days'))
    if appearances <= 0 and pitches <= 0:
        return 'none'
    if appearances <= 1 and pitches <= 20:
        return 'light'
    return 'moderate'


def _secondary_reason(record):
    reasons = _reasons(record)
    if reasons:
        return reasons[0]
    inputs = _inputs(record)
    if inputs.get('back_to_back'):
        return 'back-to-back usage concern'
    if inputs.get('workload_fetch_failed') or _norm(_availability(record).get('data_state')) in LIMITED_DATA_STATES:
        return 'limited workload data'
    return 'recent workload'


def _last_workload_label(logs, reference_date):
    valid = workload_appearance_logs(logs or [])
    latest = max(
        (_date_value(_value(log, 'game_date')) for log in valid),
        default=None,
    )
    if latest is None or reference_date is None:
        return None
    diff = (reference_date - latest).days
    if diff < 0:
        return None
    if diff == 0:
        return 'today'
    if diff == 1:
        return 'yesterday'
    return f'{diff} days ago'


def _option_base(record):
    return {
        'player_id': _player_id(record),
        'name': _name(record),
        'availability': _status(record),
    }


def _clean_option(record, logs, reference_date):
    option = _option_base(record)
    option.update({
        'last_workload': _last_workload_label(logs, reference_date),
        'recent_workload': _recent_workload_label(record),
    })
    return option


def _secondary_option(record):
    option = _option_base(record)
    option['reason'] = _secondary_reason(record)
    return option


def _sort_options(options):
    return sorted(
        options,
        key=lambda option: (
            str(option.get('name') or '').lower(),
            option.get('player_id') or 0,
        ),
    )


CLEAN_OPTIONS_BASELINE_METRIC = 'clean_trusted_options'


def _league_clean_options_distribution(league_baseline):
    if isinstance(league_baseline, dict):
        return league_baseline.get('clean_workload_options_distribution')
    return None


def _clean_options_baseline_read(clean_count, league_baseline):
    # Distribution-aware league read for the current clean-options count. The
    # shared baseline engine owns the interpretation; this only feeds it the team
    # value and the current-snapshot league distribution (higher is deeper).
    return interpret_value(
        CLEAN_OPTIONS_BASELINE_METRIC,
        clean_count,
        _league_clean_options_distribution(league_baseline),
    )


def _empty_context(reference_date=None, league_baseline=None):
    ref = _date_value(reference_date)
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': 'backend',
        'context_available': False,
        'reference_date': ref.isoformat() if ref else None,
        'available_arms_count': 0,
        'monitor_arms_count': 0,
        'restricted_arms_count': 0,
        'limited_arms_count': 0,
        'avoid_arms_count': 0,
        'unavailable_arms_count': 0,
        'unknown_status_count': 0,
        'clean_workload_options': [],
        'baseline_read': _clean_options_baseline_read(None, league_baseline),
        'secondary_options': [],
        'practical_close_game_paths_count': 0,
        'optionality_band': OPTIONALITY_INSUFFICIENT_DATA,
        'optionality_summary_inputs': {
            'available_count': 0,
            'clean_count': 0,
            'secondary_count': 0,
            'restricted_count': 0,
            'practical_paths': 0,
            'band': OPTIONALITY_INSUFFICIENT_DATA,
        },
        'limitations': [NO_OPTIONALITY_DATA_LIMITATION, WORKLOAD_CONTEXT_LIMITATION],
    }


def build_bullpen_optionality_context(
    records,
    *,
    logs_by_pitcher=None,
    reference_date=None,
    league_baseline=None,
):
    """Build Bullpen Optionality Context Layer 3 from availability records."""
    rows = list(records or [])
    if not rows:
        return _empty_context(reference_date=reference_date, league_baseline=league_baseline)

    ref = _reference_date(rows, reference_date=reference_date)
    logs_by_pitcher = logs_by_pitcher or {}
    counts = {
        STATUS_AVAILABLE: 0,
        STATUS_MONITOR: 0,
        STATUS_LIMITED: 0,
        STATUS_AVOID: 0,
        STATUS_UNAVAILABLE: 0,
    }
    unknown_status_count = 0
    clean_options = []
    secondary_options = []
    limited_read_count = 0

    for record in rows:
        status = _status(record)
        if status in counts:
            counts[status] += 1
        else:
            unknown_status_count += 1
            continue

        if _norm(_availability(record).get('data_state')) in LIMITED_DATA_STATES:
            limited_read_count += 1

        if status == STATUS_AVAILABLE:
            pitcher_id = _pitcher_id(record)
            logs = logs_by_pitcher.get(pitcher_id, [])
            if _workload_warning(record):
                secondary_options.append(_secondary_option(record))
            else:
                clean_options.append(_clean_option(record, logs, ref))
        elif status == STATUS_MONITOR:
            secondary_options.append(_secondary_option(record))

    restricted_count = (
        counts[STATUS_LIMITED]
        + counts[STATUS_AVOID]
        + counts[STATUS_UNAVAILABLE]
    )
    practical_paths = max(0, floor(len(clean_options) + (0.5 * len(secondary_options))))
    band = optionality_band(practical_paths)
    limitations = [WORKLOAD_CONTEXT_LIMITATION]
    if unknown_status_count or limited_read_count:
        limitations.append(INCOMPLETE_OPTIONALITY_DATA_LIMITATION)

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': 'backend',
        'context_available': True,
        'reference_date': ref.isoformat(),
        'available_arms_count': counts[STATUS_AVAILABLE],
        'monitor_arms_count': counts[STATUS_MONITOR],
        'restricted_arms_count': restricted_count,
        'limited_arms_count': counts[STATUS_LIMITED],
        'avoid_arms_count': counts[STATUS_AVOID],
        'unavailable_arms_count': counts[STATUS_UNAVAILABLE],
        'unknown_status_count': unknown_status_count,
        'clean_workload_options': _sort_options(clean_options),
        'baseline_read': _clean_options_baseline_read(len(clean_options), league_baseline),
        'secondary_options': _sort_options(secondary_options),
        'practical_close_game_paths_count': practical_paths,
        'optionality_band': band,
        'optionality_summary_inputs': {
            'available_count': counts[STATUS_AVAILABLE],
            'clean_count': len(clean_options),
            'secondary_count': len(secondary_options),
            'restricted_count': restricted_count,
            'practical_paths': practical_paths,
            'band': band,
        },
        'limitations': limitations,
    }


def build_league_clean_options_baseline(records_by_team, *, logs_by_pitcher=None, reference_date=None):
    """Current-snapshot league distribution of clean_workload_options_count.

    ``records_by_team`` maps team_id -> that team's current availability records.
    Every team with usable availability data contributes its clean-options count
    (including 0, which is a real thin value, not missing data), so the league
    distribution describes exactly the count the trust-lane story narrates. This
    is a current snapshot, not a rolling window, and is independent of the 7-day
    dashboard.baselines and the 10-day workload concentration distribution.
    """
    counts = []
    for team_records in (records_by_team or {}).values():
        context = build_bullpen_optionality_context(
            team_records,
            logs_by_pitcher=logs_by_pitcher,
            reference_date=reference_date,
        )
        if context.get('context_available') is not True:
            continue
        counts.append(context['optionality_summary_inputs']['clean_count'])
    return {
        'clean_workload_options_distribution': build_distribution(counts),
        'league_team_count': len(counts),
    }


def empty_bullpen_optionality_context():
    """Return the normalized no-data Layer 3 context shape."""
    return _empty_context()


__all__ = [
    'CAPABILITY',
    'INCOMPLETE_OPTIONALITY_DATA_LIMITATION',
    'NO_OPTIONALITY_DATA_LIMITATION',
    'OPTIONALITY_DEEP',
    'OPTIONALITY_FLEXIBLE',
    'OPTIONALITY_INSUFFICIENT_DATA',
    'OPTIONALITY_NARROW',
    'OPTIONALITY_THIN',
    'VERSION',
    'WORKLOAD_CONTEXT_LIMITATION',
    'build_bullpen_optionality_context',
    'empty_bullpen_optionality_context',
    'optionality_band',
]
