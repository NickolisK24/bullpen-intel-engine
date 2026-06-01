from services.availability_threshold_audit import (
    reason_frequencies,
    select_near_threshold_examples,
    summarize_records,
)


def _record(name, status, data_state, reasons, inputs, confidence='high'):
    return {
        'pitcher_id': hash(name) % 10000,
        'pitcher_name': name,
        'team': 'TST',
        'availability': {
            'availability_status': status,
            'confidence': confidence,
            'data_state': data_state,
            'reasons': reasons,
            'limitations': [],
            'inputs': inputs,
        },
    }


def test_audit_summary_keeps_stale_monitor_separate_from_fresh_monitor():
    records = [
        _record(
            'Fresh Monitor',
            'Monitor',
            'fresh',
            ['15 pitches yesterday', '1 day rest'],
            {
                'fatigue_score': 42,
                'pitches_yesterday': 15,
                'pitches_last_3_days': 28,
                'pitches_last_5_days': 30,
                'appearances_last_3_days': 1,
                'appearances_last_5_days': 2,
            },
        ),
        _record(
            'Stale Monitor',
            'Monitor',
            'stale',
            ['Latest game log is older than 14 days'],
            {
                'fatigue_score': 72,
                'pitches_yesterday': 0,
                'pitches_last_3_days': 0,
                'pitches_last_5_days': 0,
                'appearances_last_3_days': 0,
                'appearances_last_5_days': 0,
            },
            confidence='low',
        ),
        _record(
            'Avoid Workload',
            'Avoid',
            'fresh',
            ['42 pitches yesterday', '4 appearances in last 5 days'],
            {
                'fatigue_score': 79,
                'pitches_yesterday': 42,
                'pitches_last_3_days': 61,
                'pitches_last_5_days': 76,
                'appearances_last_3_days': 2,
                'appearances_last_5_days': 4,
            },
            confidence='medium',
        ),
    ]

    summary = summarize_records(records)

    assert summary['total_pitchers'] == 3
    assert summary['status_distribution'] == {'Monitor': 2, 'Avoid': 1}
    assert summary['data_state_distribution'] == {'fresh': 2, 'stale': 1}
    assert summary['status_by_data_state']['fresh'] == {'Monitor': 1, 'Avoid': 1}
    assert summary['status_by_data_state']['stale'] == {'Monitor': 1}
    assert summary['data_quality_counts'] == {'stale': 1, 'missing': 0, 'incomplete': 0}
    assert summary['workload_input_summary']['fatigue_score']['median'] == 72


def test_reason_frequencies_count_repeated_rule_reasons():
    records = [
        {
            'reasons': ['1 day rest', '15 pitches yesterday'],
        },
        {
            'reasons': ['1 day rest', 'Fatigue score 55'],
        },
        {
            'reasons': ['Fatigue score 55'],
        },
    ]

    counts = reason_frequencies(records)

    assert counts['1 day rest'] == 2
    assert counts['Fatigue score 55'] == 2
    assert counts['15 pitches yesterday'] == 1


def test_near_threshold_examples_find_closest_boundary_inputs():
    records = [
        _record(
            'Near Limited',
            'Monitor',
            'fresh',
            ['24 pitches yesterday'],
            {
                'fatigue_score': 59.5,
                'pitches_yesterday': 24,
                'pitches_last_3_days': 44,
                'pitches_last_5_days': 58,
                'appearances_last_3_days': 1,
                'appearances_last_5_days': 2,
            },
        ),
        _record(
            'Far Away',
            'Available',
            'fresh',
            [],
            {
                'fatigue_score': 12,
                'pitches_yesterday': 0,
                'pitches_last_3_days': 0,
                'pitches_last_5_days': 0,
                'appearances_last_3_days': 0,
                'appearances_last_5_days': 0,
            },
        ),
    ]

    examples = select_near_threshold_examples(records, limit=3)

    assert examples[0]['pitcher_name'] == 'Near Limited'
    assert examples[0]['distance'] <= 1
    assert examples[0]['input'] in {
        'fatigue_score',
        'pitches_yesterday',
        'pitches_last_3_days',
        'appearances_last_5_days',
    }
