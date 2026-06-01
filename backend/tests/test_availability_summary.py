from services.availability_summary import summarize_availability_records


def _record(status, confidence, data_state):
    return {
        'availability': {
            'availability_status': status,
            'confidence': confidence,
            'data_state': data_state,
            'reasons': [],
            'limitations': [],
            'inputs': {},
        },
    }


def test_availability_summary_counts_all_statuses_confidence_and_data_states():
    records = [
        _record('Available', 'high', 'fresh'),
        _record('Monitor', 'low', 'stale'),
        _record('Limited', 'medium', 'fresh'),
        _record('Avoid', 'medium', 'incomplete'),
        _record('Unavailable', 'high', 'missing'),
    ]

    summary = summarize_availability_records(records)

    assert summary['mode'] == 'current_availability'
    assert summary['is_current_availability'] is True
    assert summary['total_pitchers'] == 5
    assert summary['statuses'] == {
        'Available': 1,
        'Monitor': 1,
        'Limited': 1,
        'Avoid': 1,
        'Unavailable': 1,
    }
    assert summary['confidence'] == {
        'high': 2,
        'medium': 2,
        'low': 1,
    }
    assert summary['data_state'] == {
        'fresh': 2,
        'stale': 1,
        'missing': 1,
        'incomplete': 1,
    }


def test_availability_summary_includes_zero_counts_for_expected_buckets():
    summary = summarize_availability_records([
        _record('Monitor', 'low', 'stale'),
    ])

    assert summary['statuses']['Available'] == 0
    assert summary['statuses']['Monitor'] == 1
    assert summary['statuses']['Limited'] == 0
    assert summary['confidence']['high'] == 0
    assert summary['confidence']['medium'] == 0
    assert summary['confidence']['low'] == 1
    assert summary['data_state']['fresh'] == 0
    assert summary['data_state']['stale'] == 1
    assert summary['data_state']['missing'] == 0
    assert summary['data_state']['incomplete'] == 0


def test_availability_summary_adds_stale_dominant_trust_note():
    summary = summarize_availability_records([
        _record('Monitor', 'low', 'stale'),
        _record('Monitor', 'low', 'stale'),
        _record('Monitor', 'low', 'missing'),
        _record('Available', 'high', 'fresh'),
    ])

    assert 'Most pitchers are classified from stale or missing workload data.' in summary['notes']
    assert 'Stale workload data must not be treated as current availability' in summary['notes']
    assert 'Missing workload history reduces availability confidence.' in summary['notes']


def test_availability_summary_reports_empty_classification_set():
    summary = summarize_availability_records([])

    assert summary['total_pitchers'] == 0
    assert summary['notes'] == ['No availability classifications are available yet.']
