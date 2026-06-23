"""Baseline interpretation engine.

Turns a single metric value into a structured, deterministic read against a
league distribution produced by ``baseline_distribution`` (sample_count, mean,
median, p10/p25/p75/p90). It emits structured fields only — never prose, never a
recommendation, prediction, or per-team ranking. A later story/UI phase decides
how to word these reads; this module just classifies.

Scope (C1C): applied to workload concentration (``top_share`` / ``top_one_share``)
via ``interpret_workload_concentration``. ``interpret_value`` itself is metric
agnostic so future metrics can reuse it.
"""

from __future__ import annotations

import math
from typing import Any


CAPABILITY = 'baseline_engine_v1'

# Minimum league sample before a value is interpreted at all (MVP guard).
MIN_SAMPLE_COUNT = 10

# Half-width of the "about typical" band around the mean, as a fraction of the
# interquartile range. Keeps small deviations from over-labeling above/below.
MEAN_TOLERANCE_IQR_RATIO = 0.15

# Unavailable states (available = False).
COMPARISON_UNAVAILABLE = 'unavailable'
COMPARISON_INSUFFICIENT_SAMPLE = 'insufficient_sample'
COMPARISON_MALFORMED = 'malformed_distribution'

# Interpretation bands for higher-is-more-notable metrics (available = True).
BELOW_AVERAGE = 'below_average'
ABOUT_TYPICAL = 'about_typical'
ABOVE_AVERAGE = 'above_average'
WELL_ABOVE_AVERAGE = 'well_above_average'
AMONG_HIGHEST = 'among_highest'

# Metrics this phase is allowed to interpret.
WORKLOAD_CONCENTRATION_METRICS = ('top_share', 'top_one_share')


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _mean_tolerance(p25, p75, mean) -> float:
    """Symmetric tolerance around the mean defining the 'about typical' band."""
    if _is_number(p25) and _is_number(p75) and p75 > p25:
        return MEAN_TOLERANCE_IQR_RATIO * (float(p75) - float(p25))
    # Degenerate/absent IQR: fall back to a small fraction of the mean magnitude.
    return abs(float(mean)) * 0.02 if _is_number(mean) else 0.0


def _classify(value, mean, p75, p90, tolerance):
    """Return (band, comparison, direction, severity, nearest_threshold).

    Evaluated from the highest cut point down so the outcome is unambiguous.
    """
    if value >= p90:
        return ('at_or_above_p90', AMONG_HIGHEST, 'higher', 'high', 'p90')
    if value >= p75:
        return ('p75_to_p90', WELL_ABOVE_AVERAGE, 'higher', 'elevated', 'p75')
    if value > mean + tolerance:
        return ('mean_to_p75', ABOVE_AVERAGE, 'higher', 'notable', 'mean')
    if value >= mean - tolerance:
        return ('around_mean', ABOUT_TYPICAL, 'typical', 'typical', 'mean')
    return ('below_mean', BELOW_AVERAGE, 'lower', 'low', 'mean')


def _state(comparison, metric, value, sample_count, mean, median, reason):
    """An unavailable read (insufficient / malformed / no value)."""
    return {
        'capability': CAPABILITY,
        'available': False,
        'metric': metric,
        'value': float(value) if _is_number(value) else None,
        'comparison': comparison,
        'band': None,
        'direction': None,
        'severity': None,
        'sample_count': int(sample_count) if _is_number(sample_count) else None,
        'mean': float(mean) if _is_number(mean) else None,
        'median': float(median) if _is_number(median) else None,
        'nearest_threshold': None,
        'reason': reason,
    }


def interpret_value(metric, value, distribution, *, sample_count=None, min_sample_count=MIN_SAMPLE_COUNT):
    """Interpret ``value`` for ``metric`` against a league ``distribution``.

    ``distribution`` is a ``baseline_distribution.build_distribution`` shape.
    ``sample_count`` defaults to the distribution's own sample_count. Returns a
    structured read; unavailable states carry available=False and a ``reason``.
    """
    dist = distribution if isinstance(distribution, dict) else {}
    resolved_sample = sample_count if sample_count is not None else dist.get('sample_count')
    mean = dist.get('mean')
    median = dist.get('median')
    p25 = dist.get('p25')
    p75 = dist.get('p75')
    p90 = dist.get('p90')

    # Nothing to interpret.
    if not _is_number(value):
        return _state(COMPARISON_UNAVAILABLE, metric, None, resolved_sample, mean, median, 'no value to interpret')

    # Too little league data (an empty distribution lands here: sample_count 0).
    if _is_number(resolved_sample) and resolved_sample < min_sample_count:
        return _state(
            COMPARISON_INSUFFICIENT_SAMPLE, metric, value, resolved_sample, mean, median,
            f'sample_count below minimum of {min_sample_count}',
        )

    # Distribution is unusable: missing sample_count or non-finite cut points.
    if not _is_number(resolved_sample) or not all(_is_number(point) for point in (mean, p75, p90)):
        return _state(
            COMPARISON_MALFORMED, metric, value, resolved_sample, mean, median,
            'distribution missing a finite sample_count, mean, p75, or p90',
        )

    value = float(value)
    mean = float(mean)
    tolerance = _mean_tolerance(p25, p75, mean)
    band, comparison, direction, severity, nearest = _classify(value, mean, float(p75), float(p90), tolerance)
    return {
        'capability': CAPABILITY,
        'available': True,
        'metric': metric,
        'value': value,
        'comparison': comparison,
        'band': band,
        'direction': direction,
        'severity': severity,
        'sample_count': int(resolved_sample),
        'mean': mean,
        'median': float(median) if _is_number(median) else None,
        'nearest_threshold': nearest,
    }


def interpret_workload_concentration(metric, value, family, *, min_sample_count=MIN_SAMPLE_COUNT):
    """Interpret a team's workload-concentration value against the league family.

    ``family`` is the ``workload_concentration`` block from ``dashboard.baselines``
    (carrying a per-metric distribution under ``metrics``). Only ``top_share`` and
    ``top_one_share`` are supported in this phase.
    """
    if metric not in WORKLOAD_CONCENTRATION_METRICS:
        return _state(COMPARISON_UNAVAILABLE, metric, value, None, None, None, 'unsupported metric')
    metrics = (family or {}).get('metrics') if isinstance(family, dict) else None
    distribution = (metrics or {}).get(metric) if isinstance(metrics, dict) else None
    return interpret_value(metric, value, distribution, min_sample_count=min_sample_count)


__all__ = [
    'CAPABILITY',
    'MIN_SAMPLE_COUNT',
    'MEAN_TOLERANCE_IQR_RATIO',
    'COMPARISON_UNAVAILABLE',
    'COMPARISON_INSUFFICIENT_SAMPLE',
    'COMPARISON_MALFORMED',
    'BELOW_AVERAGE',
    'ABOUT_TYPICAL',
    'ABOVE_AVERAGE',
    'WELL_ABOVE_AVERAGE',
    'AMONG_HIGHEST',
    'WORKLOAD_CONCENTRATION_METRICS',
    'interpret_value',
    'interpret_workload_concentration',
]
