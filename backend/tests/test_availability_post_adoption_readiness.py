from pathlib import Path

from services.availability_post_adoption_readiness import (
    CURRENT_THRESHOLD_DOCS,
    availability_field_gaps,
    final_classification,
    find_current_threshold_doc_issues,
    status_reachability_examples,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


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


def _write_threshold_corpus(root, unavailable_column):
    """Write the real corpus paths under ``root`` with the given threshold."""
    for relative in CURRENT_THRESHOLD_DOCS:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            '| Rule | Monitor | Limited | Avoid | Unavailable |\n'
            '| --- | --- | --- | --- | --- |\n'
            f'| Pitches in 3 days | >= 30 | >= 45 | >= 60 | >= {unavailable_column} |\n',
            encoding='utf-8',
        )


def test_current_threshold_doc_scan_flags_unadopted_80_table(tmp_path):
    _write_threshold_corpus(tmp_path, 80)

    assert find_current_threshold_doc_issues(tmp_path) == [
        {
            'file': relative,
            'issue': 'Current threshold table still lists Unavailable 3-day pitches as >= 80.',
        }
        for relative in CURRENT_THRESHOLD_DOCS
    ]


def test_current_threshold_doc_scan_accepts_adopted_90_table(tmp_path):
    _write_threshold_corpus(tmp_path, 90)

    assert find_current_threshold_doc_issues(tmp_path) == []


def test_current_threshold_doc_scan_is_not_vacuous_when_the_corpus_moves(tmp_path):
    """A scan that reads no documents must not report a clean result.

    This is the defect the explicit corpus replaced. The check was a
    non-recursive ``docs/*.md`` glob; the August 13 retirement pass moved both
    threshold documents to ``docs/methodology/``; and the gate kept reporting
    PASS afterwards because it had nothing left to read. An empty corpus is now
    a finding per expected file.
    """
    (tmp_path / 'docs').mkdir()

    issues = find_current_threshold_doc_issues(tmp_path)

    assert [issue['file'] for issue in issues] == list(CURRENT_THRESHOLD_DOCS)
    assert all('missing' in issue['issue'] for issue in issues)


def test_current_threshold_doc_scan_reads_the_real_repository_corpus(tmp_path):
    """The named corpus exists where the service says it does.

    Without this, the corpus could move again and only the synthetic fixtures
    above would keep passing — which is precisely how the original scan went
    quiet.
    """
    for relative in CURRENT_THRESHOLD_DOCS:
        assert (REPO_ROOT / relative).is_file(), relative

    assert find_current_threshold_doc_issues(REPO_ROOT) == []


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
