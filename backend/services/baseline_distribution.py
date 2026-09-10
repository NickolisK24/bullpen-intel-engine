"""League-wide baseline distribution infrastructure.

Metric-agnostic statistical infrastructure: given per-team (or per-entity) values
for a metric, it produces a league distribution summary — sample count, mean,
median, and the p10/p25/p75/p90 percentile values of that league sample.

It deliberately carries no interpretation, no per-team percentile rank, and no
comparison language. A later baseline engine decides how a single team's value
reads against these distributions; this module only describes the league.

Future metrics plug in by supplying their own value extractors to
``build_metric_distributions`` and registering a family via ``build_baseline_payload``.
Nothing here is specific to one metric.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Iterable, Mapping


CAPABILITY = 'baseline_distribution_v1'

# The percentile cut points every distribution reports, as fractions of 1.
DISTRIBUTION_PERCENTILES = {
    'p10': 0.10,
    'p25': 0.25,
    'p75': 0.75,
    'p90': 0.90,
}


def _is_real_number(value: Any) -> bool:
    # Bools are ints in Python; exclude them. Reject NaN/inf and non-numerics.
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _percentile(sorted_values, fraction: float):
    """Linear-interpolation percentile over an ascending list (numpy default)."""
    count = len(sorted_values)
    if count == 0:
        return None
    if count == 1:
        return float(sorted_values[0])
    rank = fraction * (count - 1)
    lower = int(math.floor(rank))
    upper = min(lower + 1, count - 1)
    weight = rank - lower
    return float(sorted_values[lower] + weight * (sorted_values[upper] - sorted_values[lower]))


def build_distribution(values: Iterable[Any]) -> dict:
    """Summarize a sample of numeric values into a league distribution.

    Non-numeric, boolean, and non-finite entries are dropped. An empty sample
    yields a defined shape with ``sample_count`` 0 and null statistics, so the
    output contract is stable regardless of input.
    """
    clean = sorted(float(value) for value in (values or []) if _is_real_number(value))
    count = len(clean)
    distribution = {
        'sample_count': count,
        'mean': (sum(clean) / count) if count else None,
        'median': _percentile(clean, 0.5),
    }
    for name, fraction in DISTRIBUTION_PERCENTILES.items():
        distribution[name] = _percentile(clean, fraction)
    return distribution


def build_metric_distributions(
    items: Iterable[Any],
    metric_extractors: Mapping[str, Callable[[Any], Any]],
) -> dict:
    """Build one distribution per metric from a shared set of per-entity items.

    ``metric_extractors`` maps a metric key to a callable that pulls that metric's
    value out of one item. This is the reuse point: a new metric family only needs
    to provide its own extractors and call this function. Items whose value cannot
    be extracted are skipped for that metric, not for the whole family.
    """
    materialized = list(items or [])
    distributions = {}
    for metric_key, extractor in (metric_extractors or {}).items():
        values = []
        for item in materialized:
            try:
                values.append(extractor(item))
            except (KeyError, TypeError, AttributeError, IndexError):
                continue
        distributions[metric_key] = build_distribution(values)
    return distributions


def field_extractor(field: str) -> Callable[[Any], Any]:
    """Extractor for a plain dict field, used to register dict-shaped metrics."""
    def _extract(item):
        return item.get(field) if isinstance(item, dict) else None
    return _extract


def build_baseline_payload(families: Mapping[str, Any]) -> dict:
    """Wrap one or more metric-family baseline blocks in the versioned container.

    Each value in ``families`` is a family block produced by a metric module
    (for example workload concentration). The container is the single backend
    surface consumers read; adding a future family is a one-line addition here.
    """
    return {
        'capability': CAPABILITY,
        'families': dict(families or {}),
    }


__all__ = [
    'CAPABILITY',
    'DISTRIBUTION_PERCENTILES',
    'build_distribution',
    'build_metric_distributions',
    'field_extractor',
    'build_baseline_payload',
]
