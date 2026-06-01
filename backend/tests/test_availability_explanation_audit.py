from services.availability_explanation_audit import (
    audit_explanations,
    render_markdown_report,
)


def _record(name, reasons, limitations=None):
    return {
        'pitcher_id': hash(name) % 10000,
        'pitcher_name': name,
        'team': 'TST',
        'availability': {
            'availability_status': 'Monitor',
            'confidence': 'low',
            'data_state': 'fresh',
            'reasons': reasons,
            'limitations': limitations or [],
            'inputs': {},
        },
    }


def test_explanation_audit_groups_reason_and_limitation_frequencies():
    audit = audit_explanations([
        _record(
            'Pitch Volume',
            ['42 pitches yesterday', 'Only 1 day of rest'],
            ['No injury data available'],
        ),
        _record(
            'Repeated Pitch Volume',
            ['42 pitches yesterday', 'Back-to-back appearances'],
            ['No injury data available', 'Stale workload data must not be treated as current availability'],
        ),
    ])

    assert audit['total_pitchers'] == 2
    assert audit['total_reasons'] == 4
    assert audit['unique_reasons'] == 3
    assert audit['reason_category_distribution'] == {
        'pitch_count': 2,
        'appearance_frequency': 1,
        'rest': 1,
    }
    assert audit['limitation_category_distribution'] == {
        'data_state': 1,
        'limitation': 2,
    }
    assert audit['reason_frequencies'][0] == {
        'category': 'pitch_count',
        'text': '42 pitches yesterday',
        'count': 2,
    }


def test_explanation_audit_catalog_documents_possible_reason_families():
    audit = audit_explanations([])
    catalog = audit['reason_catalog']

    templates = {row['template'] for row in catalog}

    assert '{n} pitches yesterday' in templates
    assert '{n} pitches in 3 days' in templates
    assert '{n} appearances in 5 days' in templates
    assert 'Latest workload data is outside the {days}-day freshness window' in templates


def test_markdown_report_includes_grouped_reason_tables():
    audit = audit_explanations([
        _record('Pitch Volume', ['42 pitches yesterday']),
    ])

    report = render_markdown_report(audit, reference_date='2026-06-01')

    assert '# Availability Explanation Quality Audit' in report
    assert '## Current Availability Explanations' in report
    assert '| pitch_count | 42 pitches yesterday | 1 |' in report
    assert '### Possible Reason Catalog' in report
