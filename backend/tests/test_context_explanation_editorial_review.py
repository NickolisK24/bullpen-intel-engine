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
                'Interpretation weighs clean Trust Arms above clean Depth Arms.',
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
    assert report['weighting_scoring_scan']['status'] == 'warn'
    assert any(
        item['term'] == 'interpretation weighs'
        for item in report['weighting_scoring_scan']['violations']
    )
    assert any(
        item['match'] == '0 of 0'
        for item in report['raw_count_formula_scan']['violations']
    )
    assert report['disclaimer_preservation_check']['status'] == 'pass'
    assert 'Clean Option' in text
    assert 'The public data is not strong enough to give this team a full bullpen readiness note.' in text
    assert 'Raw-Count / Formula Scan' in text
    assert 'Weighting / Scoring Narration Scan' in text
    assert 'Circular-Meta Scan' in text
    assert 'Disclaimer Preservation Check' in text
    assert 'pitcher_availability_statuses' in text
    assert 'Avoid' in text
    assert 'Context Explanation Examples' in text
    assert 'Structured fields used' in text


def test_context_explanation_editorial_review_fixture_backed_healthy_corpus(tmp_path):
    report = build_context_explanation_editorial_review(
        include_fixture_examples=True,
        generated_at='2026-06-29T00:00:00',
        artifact_path='artifacts/context_explanation_editorial_review_E2D4.md',
        review_label='E2D-4 Healthy-State Team Context Voice Migration',
    )
    output = write_context_explanation_editorial_review(
        report,
        tmp_path / 'context_explanation_editorial_review_E2D3.md',
    )
    text = output.read_text(encoding='utf-8')

    coverage = report['coverage_summary']

    assert report['artifact'] == 'artifacts/context_explanation_editorial_review_E2D4.md'
    assert coverage['fixture_backed_examples'] > 0
    assert coverage['stored_data_examples'] == 0
    assert set(coverage['pitcher_availability_statuses_found']) == {
        'Available',
        'Monitor',
        'Limited',
        'Avoid',
        'Unavailable',
    }
    assert set(coverage['pitcher_context_statuses_found']) == {
        'Available',
        'Monitor',
        'Limited',
        'Avoid',
        'Unavailable',
    }
    assert {
        'Available',
        'Monitor',
        'Limited',
        'Avoid',
        'Unavailable',
    }.issubset(set(coverage['board_card_groups_found']))
    assert {
        'Trust Arm',
        'Bridge Arm',
        'Coverage Arm',
        'Depth Arm',
        'Limited Read',
    }.issubset(set(coverage['role_labels_found']))
    assert {
        'Rested',
        'Watch Arm',
        'Rest-Restricted',
        'Unavailable',
        'Limited Read',
    }.issubset(set(coverage['read_labels_found']))
    assert {
        'operationally_stable',
        'operationally_constrained',
        'operationally_stressed',
        'refused',
    }.issubset(set(coverage['team_readiness_states_found']))
    assert any(
        label != 'Limited Read'
        for label in coverage['team_shape_read_labels_found']
    )
    assert 'Clean Option' not in text
    assert 'Clean Options' not in text
    assert 'Interpretation weighs' not in text
    assert '(84 of 100)' not in text
    assert report['weighting_scoring_scan']['status'] == 'pass'
    assert report['circular_meta_scan']['status'] == 'pass'
    assert 'deterministic fixture example' in text
    assert 'examples_by_source' in text
    assert 'Raw-Count / Formula Scan' in text
    assert 'Weighting / Scoring Narration Scan' in text
    assert 'Circular-Meta Scan' in text
