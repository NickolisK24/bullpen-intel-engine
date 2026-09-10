"""Tests for the baseline interpretation engine (workload concentration MVP)."""

from services.baseline_distribution import build_distribution
from services.baseline_engine import (
    CAPABILITY,
    interpret_value,
    interpret_workload_concentration,
)
from services.workload_concentration import build_workload_concentration_baselines


def _dist(sample_count=30, mean=0.48, median=0.50, p10=0.38, p25=0.42, p75=0.58, p90=0.66):
    return {
        'sample_count': sample_count, 'mean': mean, 'median': median,
        'p10': p10, 'p25': p25, 'p75': p75, 'p90': p90,
    }


# ── Interpretation bands (higher-is-more-notable) ─────────────────────────────

def test_value_at_or_above_p90_is_among_highest():
    read = interpret_value('top_share', 0.70, _dist())
    assert read['available'] is True
    assert read['comparison'] == 'among_highest'
    assert read['band'] == 'at_or_above_p90'
    assert read['direction'] == 'higher'
    assert read['nearest_threshold'] == 'p90'
    assert read['metric'] == 'top_share'
    assert read['value'] == 0.70
    assert read['sample_count'] == 30
    assert read['mean'] == 0.48


def test_value_between_p75_and_p90_is_well_above_average():
    read = interpret_value('top_share', 0.60, _dist())
    assert read['comparison'] == 'well_above_average'
    assert read['band'] == 'p75_to_p90'
    assert read['nearest_threshold'] == 'p75'
    assert read['direction'] == 'higher'


def test_value_above_mean_below_p75_is_above_average():
    read = interpret_value('top_share', 0.53, _dist())
    assert read['comparison'] == 'above_average'
    assert read['band'] == 'mean_to_p75'
    assert read['direction'] == 'higher'


def test_value_around_mean_is_about_typical():
    read = interpret_value('top_share', 0.48, _dist())
    assert read['comparison'] == 'about_typical'
    assert read['band'] == 'around_mean'
    assert read['direction'] == 'typical'
    # A small deviation on either side of the mean stays typical (tolerance band).
    assert interpret_value('top_share', 0.49, _dist())['comparison'] == 'about_typical'
    assert interpret_value('top_share', 0.47, _dist())['comparison'] == 'about_typical'


def test_value_below_mean_is_below_average():
    read = interpret_value('top_share', 0.40, _dist())
    assert read['comparison'] == 'below_average'
    assert read['band'] == 'below_mean'
    assert read['direction'] == 'lower'


# ── Guards / unavailable states ───────────────────────────────────────────────

def test_insufficient_sample_suppresses_interpretation():
    read = interpret_value('top_share', 0.70, _dist(sample_count=5))
    assert read['available'] is False
    assert read['comparison'] == 'insufficient_sample'
    assert read['band'] is None
    assert read['value'] == 0.70
    # An explicit higher minimum also suppresses an otherwise adequate sample.
    stricter = interpret_value('top_share', 0.7, _dist(sample_count=12), min_sample_count=20)
    assert stricter['comparison'] == 'insufficient_sample'


def test_empty_distribution_is_insufficient_sample():
    read = interpret_value('top_share', 0.70, build_distribution([]))
    assert read['available'] is False
    assert read['comparison'] == 'insufficient_sample'


def test_malformed_distribution_is_flagged():
    broken = {
        'sample_count': 30, 'mean': None, 'median': None,
        'p10': None, 'p25': None, 'p75': None, 'p90': None,
    }
    assert interpret_value('top_share', 0.70, broken)['comparison'] == 'malformed_distribution'
    # Non-numeric statistic despite an adequate sample.
    bad_stat = {'sample_count': 30, 'mean': 'x', 'p75': 0.5, 'p90': 0.6}
    assert interpret_value('top_share', 0.70, bad_stat)['comparison'] == 'malformed_distribution'
    # Not a dict at all.
    assert interpret_value('top_share', 0.70, None)['comparison'] == 'malformed_distribution'


def test_missing_or_nonnumeric_value_is_unavailable():
    read = interpret_value('top_share', None, _dist())
    assert read['available'] is False
    assert read['comparison'] == 'unavailable'
    assert read['value'] is None
    assert interpret_value('top_share', 'x', _dist())['comparison'] == 'unavailable'
    assert interpret_value('top_share', True, _dist())['comparison'] == 'unavailable'


def test_output_is_structured_with_no_ranking_or_prediction_fields():
    read = interpret_value('top_share', 0.70, _dist())
    assert read['capability'] == CAPABILITY
    # Structured fields only — no prose, ranking, recommendation, or prediction.
    for forbidden in ('rank', 'ranking', 'recommendation', 'prediction', 'prose', 'text', 'narrative'):
        assert forbidden not in read


# ── Workload concentration wrapper (both supported metrics) ───────────────────

def _family(sample_count=12):
    return {
        'metric_family': 'workload_concentration',
        'window_days': 7,
        'sample_count': sample_count,
        'metrics': {
            'top_share': _dist(sample_count=sample_count),
            'top_one_share': _dist(
                sample_count=sample_count, mean=0.25, median=0.24,
                p10=0.18, p25=0.21, p75=0.30, p90=0.34,
            ),
        },
    }


def test_workload_concentration_supports_both_metrics():
    family = _family()
    top_share = interpret_workload_concentration('top_share', 0.70, family)
    assert top_share['available'] is True
    assert top_share['comparison'] == 'among_highest'
    assert top_share['metric'] == 'top_share'

    top_one = interpret_workload_concentration('top_one_share', 0.32, family)
    assert top_one['available'] is True
    assert top_one['comparison'] == 'well_above_average'
    assert top_one['metric'] == 'top_one_share'


def test_workload_concentration_rejects_unsupported_metric():
    read = interpret_workload_concentration('coverage_depth', 0.5, _family())
    assert read['available'] is False
    assert read['comparison'] == 'unavailable'
    assert read['reason'] == 'unsupported metric'


def test_workload_concentration_insufficient_family_sample():
    read = interpret_workload_concentration('top_share', 0.70, _family(sample_count=4))
    assert read['comparison'] == 'insufficient_sample'


def test_engine_consumes_a_real_c1b_baseline_block():
    # End-to-end: C1B builds the league distribution, C1C interprets against it.
    values = [0.40, 0.42, 0.44, 0.46, 0.48, 0.50, 0.52, 0.54, 0.58, 0.62, 0.66, 0.72]
    per_team = [
        {'team_id': idx, 'top_share': value, 'top_one_share': value / 2}
        for idx, value in enumerate(values)
    ]
    family = build_workload_concentration_baselines(per_team)
    assert family['metrics']['top_share']['sample_count'] == 12

    high = interpret_workload_concentration('top_share', 0.72, family)
    assert high['available'] is True
    assert high['comparison'] in ('among_highest', 'well_above_average')
    assert high['direction'] == 'higher'

    low = interpret_workload_concentration('top_share', 0.40, family)
    assert low['available'] is True
    assert low['direction'] in ('lower', 'typical')
