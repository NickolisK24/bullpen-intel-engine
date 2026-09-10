"""Unit tests for the metric-agnostic baseline distribution infrastructure."""

from services.baseline_distribution import (
    CAPABILITY,
    build_baseline_payload,
    build_distribution,
    build_metric_distributions,
    field_extractor,
)


def test_build_distribution_reports_known_statistics():
    dist = build_distribution([10, 20, 30, 40, 50])
    assert dist['sample_count'] == 5
    assert dist['mean'] == 30.0
    assert dist['median'] == 30.0
    assert dist['p10'] == 14.0
    assert dist['p25'] == 20.0
    assert dist['p75'] == 40.0
    assert dist['p90'] == 46.0


def test_percentiles_interpolate_between_ranks():
    dist = build_distribution([0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    assert dist['median'] == 50.0
    assert dist['p25'] == 25.0
    assert dist['p75'] == 75.0
    assert dist['p10'] == 10.0
    assert dist['p90'] == 90.0
    # Order independence: shuffled input yields the same distribution.
    assert build_distribution([50, 0, 100, 30, 20, 90, 10, 70, 40, 80, 60]) == dist


def test_empty_sample_has_defined_null_shape():
    dist = build_distribution([])
    assert dist == {
        'sample_count': 0, 'mean': None, 'median': None,
        'p10': None, 'p25': None, 'p75': None, 'p90': None,
    }
    assert build_distribution(None)['sample_count'] == 0


def test_single_value_collapses_every_statistic_to_that_value():
    dist = build_distribution([42])
    assert dist['sample_count'] == 1
    for key in ('mean', 'median', 'p10', 'p25', 'p75', 'p90'):
        assert dist[key] == 42.0


def test_malformed_entries_are_dropped_not_fatal():
    dist = build_distribution(
        [10, None, 'x', True, False, float('nan'), float('inf'), {'a': 1}, [1], 20, 30]
    )
    # Only the three real, finite numbers survive (bools/NaN/inf/non-numerics dropped).
    assert dist['sample_count'] == 3
    assert dist['mean'] == 20.0
    assert dist['median'] == 20.0


def test_build_metric_distributions_registry_handles_missing_fields():
    items = [
        {'a': 1, 'b': 10},
        {'a': 2, 'b': 20},
        {'b': 30},  # missing 'a'
    ]
    extractors = {'a': field_extractor('a'), 'b': field_extractor('b')}
    dists = build_metric_distributions(items, extractors)
    # 'a' only has two defined values; 'b' has three.
    assert dists['a']['sample_count'] == 2
    assert dists['a']['mean'] == 1.5
    assert dists['b']['sample_count'] == 3
    assert dists['b']['mean'] == 20.0


def test_build_metric_distributions_with_no_items():
    dists = build_metric_distributions([], {'a': field_extractor('a')})
    assert dists['a']['sample_count'] == 0
    assert dists['a']['p90'] is None


def test_build_baseline_payload_wraps_families_with_capability():
    family = {'metric_family': 'workload_concentration', 'sample_count': 0, 'metrics': {}}
    payload = build_baseline_payload({'workload_concentration': family})
    assert payload['capability'] == CAPABILITY
    assert payload['families']['workload_concentration'] is family
    # Robust to empty / missing families.
    assert build_baseline_payload(None) == {'capability': CAPABILITY, 'families': {}}
