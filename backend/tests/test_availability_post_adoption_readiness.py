from services.availability_post_adoption_readiness import (
    availability_field_gaps,
    final_classification,
    find_current_threshold_doc_issues,
    status_reachability_examples,
)


def test_status_reachability_examples_cover_all_five_statuses():
    examples = status_reachability_examples()

    assert [row['expected_status'] for row in examples] == [
        'Available',
        'Monitor',
        'Limited',
        'Avoid',
        'Unavailable',
    ]
    assert all(row['passed'] for row in examples)
    assert examples[3]['inputs']['pitches_last_3_days'] == 80
    assert examples[3]['actual_status'] == 'Avoid'
    assert examples[4]['inputs']['pitches_last_3_days'] == 90
    assert examples[4]['actual_status'] == 'Unavailable'


def test_availability_field_gaps_detect_required_api_contract_fields():
    availability = {
        'availability_status': 'Monitor',
        'data_state': 'fresh',
        'reasons': [],
        'limitations': [],
        'inputs': {},
    }

    assert availability_field_gaps(availability) == ['confidence']


def test_current_threshold_doc_scan_flags_unadopted_80_table(tmp_path):
    docs_dir = tmp_path / 'docs'
    docs_dir.mkdir()
    doc = docs_dir / 'availability.md'
    doc.write_text(
        '| Rule | Monitor | Limited | Avoid | Unavailable |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| Pitches in 3 days | >= 30 | >= 45 | >= 60 | >= 80 |\n',
        encoding='utf-8',
    )

    issues = find_current_threshold_doc_issues(tmp_path)

    assert issues == [
        {
            'file': 'docs/availability.md',
            'issue': 'Current threshold table still lists Unavailable 3-day pitches as >= 80.',
        }
    ]


def test_current_threshold_doc_scan_accepts_adopted_90_table(tmp_path):
    docs_dir = tmp_path / 'docs'
    docs_dir.mkdir()
    doc = docs_dir / 'availability.md'
    doc.write_text(
        '| Rule | Monitor | Limited | Avoid | Unavailable |\n'
        '| --- | --- | --- | --- | --- |\n'
        '| Pitches in 3 days | >= 30 | >= 45 | >= 60 | >= 90 |\n',
        encoding='utf-8',
    )

    assert find_current_threshold_doc_issues(tmp_path) == []


def test_final_classification_is_minor_findings_when_consistency_passes():
    evidence = {
        'documentation': {'status': 'PASS'},
        'api': {'status': 'PASS'},
        'dashboard': {'status': 'PASS'},
        'explanation': {'status': 'PASS'},
        'snapshot': {'status': 'PASS'},
        'reachability': {'status': 'PASS'},
        'governance': {
            'reports': {
                'threshold_audit': True,
                'baseline_report': True,
                'adoption_report': True,
                'boundary_report': True,
                'experiment_report': True,
            },
            'current_threshold': 90,
            'threshold_audit_distribution_matches_adoption': True,
            'baseline_refs_90': True,
            'adoption_records_change': True,
            'boundary_keeps_historical_review': True,
        },
        'recommendation': {'status': 'READY_WITH_ACTION_ITEMS'},
    }

    assert final_classification(evidence) == 'READY_WITH_MINOR_FINDINGS'
