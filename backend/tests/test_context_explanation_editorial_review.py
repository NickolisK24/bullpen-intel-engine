from services.context_explanation_editorial_review import (
    build_context_explanation_editorial_review,
    write_context_explanation_editorial_review,
)


def test_context_explanation_editorial_review_artifact_integrity(tmp_path):
    examples = [
        {
            'surface_name': 'Pitcher public role/read labels',
            'team': 'New York Mets (NYM, 121)',
            'pitcher': 'Example Pitcher',
            'status': 'Available',
            'role_or_classification': {
                'role': 'Trust Arm',
                'read': 'Clean Option',
            },
            'source_path': 'services.pitcher_public_labels.build_pitcher_labels',
            'fallback_status': 'rendered',
            'rendered_public_copy': [
                'Trust Arm',
                'Clean Option',
            ],
            'structured_fields_used': {
                'availability_status': 'Available',
                'labels': {
                    'role': {'label': 'Trust Arm'},
                    'read': {'label': 'Clean Option'},
                },
            },
            'evidence_sections': {},
        },
        {
            'surface_name': 'Team Operations readiness V4 explanation',
            'team': 'Los Angeles Angels (LAA, 108)',
            'pitcher': None,
            'status': 'data_limited',
            'role_or_classification': {
                'scope': 'readiness_state',
                'readiness_status_code': 'data_limited',
            },
            'source_path': 'explanations.readiness.serialize_readiness_explanation',
            'fallback_status': 'data_limited',
            'rendered_public_copy': [
                'The public data is not strong enough to give this team a full bullpen readiness note.',
                'Readiness is based on public workload data, not private team information.',
                'Readiness is not injury or medical information.',
                'Readiness is not a performance forecast.',
                'Manager intent and bullpen warm-up state are not available.',
            ],
            'structured_fields_used': {
                'readiness': {'status_code': 'data_limited'},
            },
            'evidence_sections': {
                'primary_reasons': [
                    {
                        'code': 'READINESS_DEGRADED_BY_LIMITATIONS',
                        'summary': 'The public data is not strong enough to give this team a full bullpen readiness note.',
                    },
                ],
            },
        },
        {
            'surface_name': 'Team bullpen shape explanations',
            'team': 'Los Angeles Angels (LAA, 108)',
            'pitcher': None,
            'status': 'team_shape',
            'role_or_classification': {'read_labels': ['Limited Read']},
            'source_path': 'services.team_bullpen_shape.build_team_bullpen_shape',
            'fallback_status': 'limited_read_shape',
            'rendered_public_copy': [
                'Only 0 of 0 bullpen arms have clear workload or availability labels.',
            ],
            'structured_fields_used': {},
            'evidence_sections': {},
        },
    ]

    report = build_context_explanation_editorial_review(
        seed_examples=examples,
        seed_missing_categories={'pitcher_availability_statuses': ['Avoid']},
        generated_at='2026-06-29T00:00:00',
        artifact_path='artifacts/context_explanation_editorial_review_E2D2.md',
    )
    output = write_context_explanation_editorial_review(
        report,
        tmp_path / 'context_explanation_editorial_review_E2D2.md',
    )
    text = output.read_text(encoding='utf-8')

    assert report['artifact'] == 'artifacts/context_explanation_editorial_review_E2D2.md'
    assert report['example_count'] == 3
    assert report['retired_phrase_scan']['status'] == 'warn'
    assert report['retired_phrase_scan']['violation_count'] >= 1
    assert report['raw_count_formula_scan']['status'] == 'warn'
    assert any(
        item['match'] == '0 of 0'
        for item in report['raw_count_formula_scan']['violations']
    )
    assert report['disclaimer_preservation_check']['status'] == 'pass'
    assert 'Clean Option' in text
    assert 'The public data is not strong enough to give this team a full bullpen readiness note.' in text
    assert 'Raw-Count / Formula Scan' in text
    assert 'Circular-Meta Scan' in text
    assert 'Disclaimer Preservation Check' in text
    assert 'pitcher_availability_statuses' in text
    assert 'Avoid' in text
    assert 'Context Explanation Examples' in text
    assert 'Structured fields used' in text
