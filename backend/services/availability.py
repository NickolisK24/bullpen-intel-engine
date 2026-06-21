"""
Deterministic bullpen availability classification.

This layer translates existing BaseballOS workload inputs into explainable
decision-support statuses. It intentionally uses only fatigue scores, MLB game
logs, and data freshness signals already available to the backend.
"""

from dataclasses import dataclass
from datetime import timedelta

from services.availability_reference_date import product_current_date
from services.availability_explanations import (
    BASE_LIMITATIONS,
    INCOMPLETE_WORKLOAD_LIMITATION,
    INCOMPLETE_WORKLOAD_REASON,
    MISSING_WORKLOAD_LIMITATION,
    MISSING_WORKLOAD_REASON,
    STALE_WORKLOAD_LIMITATION,
    WORKLOAD_FALLBACK_REASON,
    appearance_frequency_reason,
    back_to_back_reason,
    fatigue_score_reason,
    pitch_count_reason,
    rest_reason,
    stale_workload_reason,
)
from services.workload_appearance import workload_appearance_logs


ACTIVE_WINDOW_DAYS = 14

STATUS_AVAILABLE = 'Available'
STATUS_MONITOR = 'Monitor'
STATUS_LIMITED = 'Limited'
STATUS_AVOID = 'Avoid'
STATUS_UNAVAILABLE = 'Unavailable'

CONFIDENCE_HIGH = 'high'
CONFIDENCE_MEDIUM = 'medium'
CONFIDENCE_LOW = 'low'


@dataclass(frozen=True)
class AvailabilityThresholds:
    """Centralized V1 knobs so rule tuning does not scatter magic numbers."""
    monitor_fatigue_score: float = 40.0
    limited_fatigue_score: float = 60.0
    avoid_fatigue_score: float = 75.0
    unavailable_fatigue_score: float = 85.0

    monitor_pitches_yesterday: int = 15
    limited_pitches_yesterday: int = 25
    avoid_pitches_yesterday: int = 35
    unavailable_pitches_yesterday: int = 50

    monitor_pitches_last_3_days: int = 30
    limited_pitches_last_3_days: int = 45
    avoid_pitches_last_3_days: int = 60
    unavailable_pitches_last_3_days: int = 90

    limited_pitches_last_5_days: int = 60
    avoid_pitches_last_5_days: int = 75

    monitor_appearances_last_5_days: int = 2
    limited_appearances_last_5_days: int = 3
    avoid_appearances_last_5_days: int = 4

    limited_appearances_last_3_days: int = 2
    avoid_appearances_last_3_days: int = 3

    limited_back_to_back_pitches_last_3_days: int = 35
    unavailable_multi_day_pitch_threshold: int = 75


THRESHOLDS = AvailabilityThresholds()


def _value(obj, name, default=None):
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _iso_or_none(value):
    return value.isoformat() if value else None


def _sum_pitches(logs):
    return sum((getattr(log, 'pitches_thrown', 0) or 0) for log in logs)


def _logs_between(logs, start, end):
    return [
        log for log in logs
        if getattr(log, 'game_date', None) is not None
        and start <= log.game_date <= end
    ]


def _has_back_to_back(appearance_dates):
    sorted_dates = sorted(appearance_dates, reverse=True)
    return any((day - timedelta(days=1)) in appearance_dates for day in sorted_dates)


def _derive_inputs(score, game_logs, reference_date, latest_game_date, freshness_state):
    logs = workload_appearance_logs(game_logs)
    yesterday = reference_date - timedelta(days=1)
    start_3 = reference_date - timedelta(days=2)
    start_5 = reference_date - timedelta(days=4)
    start_4 = reference_date - timedelta(days=3)

    logs_yesterday = _logs_between(logs, yesterday, yesterday)
    logs_3 = _logs_between(logs, start_3, reference_date)
    logs_4 = _logs_between(logs, start_4, reference_date)
    logs_5 = _logs_between(logs, start_5, reference_date)
    appearance_dates = {
        log.game_date for log in logs_5
        if getattr(log, 'game_date', None) is not None
    }

    days_rest = None
    if latest_game_date is not None:
        days_rest = (reference_date - latest_game_date).days

    return {
        'fatigue_score': round(float(_value(score, 'raw_score')), 1) if _value(score, 'raw_score') is not None else None,
        'fatigue_risk_level': _value(score, 'risk_level'),
        'pitches_yesterday': _sum_pitches(logs_yesterday),
        'pitches_last_3_days': _sum_pitches(logs_3),
        'pitches_last_5_days': _sum_pitches(logs_5),
        'appearances_last_3_days': len(logs_3),
        'appearances_last_5_days': len(logs_5),
        'days_rest': days_rest,
        'back_to_back': _has_back_to_back(appearance_dates),
        'three_in_four': len(logs_4) >= 3,
        'four_in_five': len(logs_5) >= 4,
        'freshness_state': freshness_state,
        'latest_game_date': _iso_or_none(latest_game_date),
        'reference_date': reference_date.isoformat(),
    }


def _data_state(reference_date, latest_game_date, score, game_logs, active_window_days):
    logs = list(game_logs or [])
    incomplete = any(
        getattr(log, 'game_date', None) is None or getattr(log, 'pitches_thrown', None) is None
        for log in logs
    )
    if incomplete:
        return 'incomplete'
    if score is None or _value(score, 'raw_score') is None:
        return 'missing'
    if latest_game_date is None:
        return 'missing'
    if latest_game_date < reference_date - timedelta(days=active_window_days):
        return 'stale'
    return 'fresh'


def _add_reason(reasons, text):
    if text not in reasons:
        reasons.append(text)


def _evaluate_workload(inputs, thresholds):
    reasons = []
    status = STATUS_AVAILABLE

    fatigue = inputs['fatigue_score']
    pitches_yesterday = inputs['pitches_yesterday']
    pitches_3 = inputs['pitches_last_3_days']
    pitches_5 = inputs['pitches_last_5_days']
    apps_3 = inputs['appearances_last_3_days']
    apps_5 = inputs['appearances_last_5_days']
    days_rest = inputs['days_rest']

    if (
        pitches_yesterday >= thresholds.unavailable_pitches_yesterday
        or pitches_3 >= thresholds.unavailable_pitches_last_3_days
        or (apps_5 >= 4 and pitches_5 >= thresholds.unavailable_multi_day_pitch_threshold)
        or (fatigue is not None and fatigue >= thresholds.unavailable_fatigue_score and pitches_yesterday >= thresholds.avoid_pitches_yesterday)
    ):
        status = STATUS_UNAVAILABLE
    elif (
        pitches_yesterday >= thresholds.avoid_pitches_yesterday
        or pitches_3 >= thresholds.avoid_pitches_last_3_days
        or apps_3 >= thresholds.avoid_appearances_last_3_days
        or apps_5 >= thresholds.avoid_appearances_last_5_days
        or (inputs['back_to_back'] and pitches_3 >= thresholds.limited_back_to_back_pitches_last_3_days)
        or (fatigue is not None and fatigue >= thresholds.avoid_fatigue_score)
    ):
        status = STATUS_AVOID
    elif (
        pitches_yesterday >= thresholds.limited_pitches_yesterday
        or pitches_3 >= thresholds.limited_pitches_last_3_days
        or pitches_5 >= thresholds.limited_pitches_last_5_days
        or apps_3 >= thresholds.limited_appearances_last_3_days
        or apps_5 >= thresholds.limited_appearances_last_5_days
        or inputs['back_to_back']
        or (fatigue is not None and fatigue >= thresholds.limited_fatigue_score)
        or (days_rest is not None and days_rest <= 1 and fatigue is not None and fatigue >= 50)
    ):
        status = STATUS_LIMITED
    elif (
        pitches_yesterday >= thresholds.monitor_pitches_yesterday
        or pitches_3 >= thresholds.monitor_pitches_last_3_days
        or apps_5 >= thresholds.monitor_appearances_last_5_days
        or (days_rest is not None and days_rest <= 1)
        or (fatigue is not None and fatigue >= thresholds.monitor_fatigue_score)
    ):
        status = STATUS_MONITOR

    if pitches_yesterday >= thresholds.monitor_pitches_yesterday:
        _add_reason(reasons, pitch_count_reason(pitches_yesterday, 'yesterday'))
    if pitches_3 >= thresholds.monitor_pitches_last_3_days:
        _add_reason(reasons, pitch_count_reason(pitches_3, '3 days'))
    if pitches_5 >= thresholds.limited_pitches_last_5_days:
        _add_reason(reasons, pitch_count_reason(pitches_5, '5 days'))
    if apps_3 >= thresholds.limited_appearances_last_3_days:
        _add_reason(reasons, appearance_frequency_reason(apps_3, '3 days'))
    if apps_5 >= thresholds.monitor_appearances_last_5_days:
        _add_reason(reasons, appearance_frequency_reason(apps_5, '5 days'))
    if inputs['back_to_back']:
        _add_reason(reasons, back_to_back_reason())
    if inputs['three_in_four']:
        _add_reason(reasons, '3 appearances in 4 days')
    if inputs['four_in_five']:
        _add_reason(reasons, '4 appearances in 5 days')
    if days_rest is not None and days_rest <= 1:
        _add_reason(reasons, rest_reason(days_rest))
    if fatigue is not None and fatigue >= thresholds.monitor_fatigue_score:
        _add_reason(reasons, fatigue_score_reason(fatigue))

    if status != STATUS_AVAILABLE and not reasons:
        _add_reason(reasons, WORKLOAD_FALLBACK_REASON)

    return status, reasons


def classify_availability(
    score,
    game_logs=None,
    reference_date=None,
    latest_game_date=None,
    active_window_days=ACTIVE_WINDOW_DAYS,
    thresholds=THRESHOLDS,
):
    """
    Classify pitcher availability from existing workload data.

    Args:
        score: FatigueScore-like object or dict. May be None.
        game_logs: Recent GameLog-like objects for the reference-date window.
        reference_date: Date of the availability snapshot. Defaults to the
            product calendar date.
        latest_game_date: Most recent known appearance date. If omitted, derived
            from game_logs when possible.
        active_window_days: Freshness window for current availability.
        thresholds: AvailabilityThresholds instance for deterministic rule tuning.

    Returns:
        Dict safe to embed in API responses.
    """
    ref = reference_date or product_current_date()
    raw_logs = list(game_logs or [])
    logs = workload_appearance_logs(raw_logs)
    if latest_game_date is None and logs:
        latest_game_date = max(
            (log.game_date for log in logs if getattr(log, 'game_date', None) is not None),
            default=None,
        )

    data_state = _data_state(ref, latest_game_date, score, raw_logs, active_window_days)
    inputs = _derive_inputs(score, logs, ref, latest_game_date, data_state)
    limitations = list(BASE_LIMITATIONS)

    if data_state == 'missing':
        return {
            'availability_status': STATUS_MONITOR,
            'confidence': CONFIDENCE_LOW,
            'data_state': data_state,
            'reasons': [MISSING_WORKLOAD_REASON],
            'limitations': limitations + [MISSING_WORKLOAD_LIMITATION],
            'inputs': inputs,
        }

    if data_state == 'incomplete':
        status, reasons = _evaluate_workload(inputs, thresholds)
        if status == STATUS_AVAILABLE:
            status = STATUS_MONITOR
        _add_reason(reasons, INCOMPLETE_WORKLOAD_REASON)
        return {
            'availability_status': status,
            'confidence': CONFIDENCE_LOW,
            'data_state': data_state,
            'reasons': reasons,
            'limitations': limitations + [INCOMPLETE_WORKLOAD_LIMITATION],
            'inputs': inputs,
        }

    if data_state == 'stale':
        return {
            'availability_status': STATUS_MONITOR,
            'confidence': CONFIDENCE_LOW,
            'data_state': data_state,
            'reasons': [stale_workload_reason(active_window_days)],
            'limitations': limitations + [STALE_WORKLOAD_LIMITATION],
            'inputs': inputs,
        }

    status, reasons = _evaluate_workload(inputs, thresholds)
    confidence = CONFIDENCE_HIGH
    if status in (STATUS_LIMITED, STATUS_AVOID) and inputs['fatigue_score'] is None:
        confidence = CONFIDENCE_MEDIUM

    return {
        'availability_status': status,
        'confidence': confidence,
        'data_state': data_state,
        'reasons': reasons,
        'limitations': limitations,
        'inputs': inputs,
    }
