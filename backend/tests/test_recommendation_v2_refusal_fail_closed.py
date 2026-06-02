from recommendation import (
    RecommendationCandidate,
    RecommendationEngine,
    V2_REFUSAL_FAIL_CLOSED_PHASE,
    assemble_v2_context,
    v2_governance_errors,
    v2_trust_metadata_errors,
)


FORBIDDEN_OUTPUT_KEYS = {
    'rank',
    'ranking',
    'winner',
    'priority',
    'priority_score',
    'score',
    'score_ordering',
    'selected_pitcher',
    'selected_pitcher_id',
    'selected_candidate',
    'selected_candidate_id',
    'recommended_pitcher',
    'recommended_option',
    'preferred_pitcher',
    'preferred_option',
    'use_this_pitcher',
    'best_candidate',
    'best_pitcher',
    'top_candidate',
    'pitcher_choice',
    'prediction',
    'predicted_performance',
    'performance_prediction',
    'injury_prediction',
    'save_prediction',
    'game_prediction',
    'game_outcome_prediction',
}

DEFAULT_INPUTS = {
    'fatigue_score': 20.0,
    'pitches_yesterday': 0,
    'latest_game_date': '2026-06-01',
}


def candidate(
    pitcher_id=42,
    pitcher_name='Available Arm',
    availability_status='Available',
    confidence='high',
    data_state='fresh',
    inputs=None,
    reasons=None,
    limitations=None,
    metadata=None,
):
    source_inputs = dict(DEFAULT_INPUTS if inputs is None else inputs)
    return RecommendationCandidate(
        pitcher_id=pitcher_id,
        pitcher_name=pitcher_name,
        team_id=7,
        team_name='Example Club',
        availability={
            'availability_status': availability_status,
            'confidence': confidence,
            'data_state': data_state,
            'reasons': list(reasons or ()),
            'limitations': list(limitations or ()),
            'inputs': source_inputs,
            'data_through': '2026-06-01',
            'last_successful_sync': '2026-06-02T10:00:00Z',
            'latest_sync_status': 'success',
        },
        metadata=metadata or {},
    )


def raw_candidate(availability=None, metadata=None, **extra):
    return {
        'pitcher_id': 42,
        'pitcher_name': 'Raw Arm',
        'team_id': 7,
        'team_name': 'Example Club',
        'availability': {
            **dict(availability or {}),
            'inputs': dict(DEFAULT_INPUTS),
            'data_through': '2026-06-01',
            'last_successful_sync': '2026-06-02T10:00:00Z',
            'latest_sync_status': 'success',
        },
        'metadata': dict(metadata or {}),
        **extra,
    }


def payload_keys(payload):
    keys = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            keys.add(key)
            keys.update(payload_keys(value))
    elif isinstance(payload, list):
        for value in payload:
            keys.update(payload_keys(value))
    return keys


def refusal_summary(payload):
    return payload['metadata']['refusal_fail_closed']


def assert_phase_7_summary(payload, expected_state):
    summary = refusal_summary(payload)
    assert summary['phase'] == V2_REFUSAL_FAIL_CLOSED_PHASE
    assert summary['state'] == expected_state
    assert summary['ranking_applied'] is False
    assert summary['selection_made'] is False
    assert summary['trust_metadata']['ranking_applied'] is False
    assert summary['trust_metadata']['selection_made'] is False
    assert v2_trust_metadata_errors(summary) == []

    assert payload['metadata']['neutral_intelligence']['refusal_fail_closed'] == summary
    assert payload['metadata']['inventory_visibility']['refusal_fail_closed'] == summary
    assert (
        payload['metadata']['team_bullpen_context_summary']['refusal_fail_closed']
        == summary
    )


class TestRecommendationEngineV2RefusalFailClosedIntegration:
    def test_missing_evidence_fails_closed_with_explicit_metadata(self):
        payload = assemble_v2_context(()).to_dict()
        summary = refusal_summary(payload)

        assert_phase_7_summary(payload, expected_state='failed_closed')
        assert payload['metadata']['failed_closed'] is True
        assert summary['critical_failure'] is True
        assert summary['safe_partial_output_allowed'] is False
        assert 'missing_inputs' in summary['reason_codes']
        assert payload['candidate_groups'] == []
        assert payload['recommendation_context']['source_evidence_state'] == 'missing'
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False
        assert v2_governance_errors(payload) == []

    def test_incomplete_evidence_produces_degraded_safe_summary(self):
        payload = assemble_v2_context(
            (
                candidate(
                    data_state='incomplete',
                    reasons=('Incomplete source evidence was supplied.',),
                    limitations=('Incomplete source evidence limits confidence.',),
                ),
            )
        ).to_dict()
        summary = refusal_summary(payload)

        assert_phase_7_summary(payload, expected_state='degraded')
        assert payload['metadata']['failed_closed'] is True
        assert summary['critical_failure'] is False
        assert summary['safe_partial_output_allowed'] is True
        assert 'data_state_incomplete' in summary['reason_codes']
        assert payload['metadata']['assembled_candidate_count'] == 1
        assert payload['candidate_groups']
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False

    def test_stale_evidence_produces_refusal_and_degraded_metadata(self):
        payload = assemble_v2_context(
            (
                candidate(
                    availability_status='Monitor',
                    confidence='low',
                    data_state='stale',
                    reasons=('Stale workload data must be reviewed.',),
                    limitations=('Stale workload data limits current context.',),
                ),
            )
        ).to_dict()
        context = payload['recommendation_context']
        summary = refusal_summary(payload)

        assert_phase_7_summary(payload, expected_state='degraded')
        assert context['freshness']['state'] == 'stale'
        assert any(
            refusal['reason'] == 'data_state_stale'
            for refusal in context['refusal_reasons']
        )
        assert 'data_state_stale' in summary['reason_codes']
        assert summary['safe_partial_output_allowed'] is True
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False

    def test_unsupported_trust_metadata_fails_closed_and_suppresses_groups(self):
        payload = assemble_v2_context(
            (
                raw_candidate(
                    availability={
                        'availability_status': 'Available',
                        'confidence': 'high',
                        'data_state': 'fresh',
                        'reasons': [],
                        'limitations': [],
                    },
                    metadata={'trust_metadata': 'unsupported'},
                ),
            )
        ).to_dict()
        context = payload['recommendation_context']
        summary = refusal_summary(payload)

        assert_phase_7_summary(payload, expected_state='failed_closed')
        assert context['source_evidence_state'] == 'unsupported'
        assert 'unsupported_trust_fields' in summary['reason_codes']
        assert payload['metadata']['assembled_candidate_count'] == 0
        assert payload['candidate_groups'] == []
        assert payload['bullpen_state']['inventory']['total_pitchers'] == 0
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False

    def test_malformed_evidence_fails_closed_and_suppresses_groups(self):
        payload = assemble_v2_context((object(),)).to_dict()
        context = payload['recommendation_context']
        summary = refusal_summary(payload)

        assert_phase_7_summary(payload, expected_state='failed_closed')
        assert context['source_evidence_state'] == 'malformed'
        assert 'malformed_evidence' in summary['reason_codes']
        assert payload['metadata']['assembled_candidate_count'] == 0
        assert payload['candidate_groups'] == []
        assert payload['metadata']['inventory_visibility']['total_inventory_count'] == 0
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False

    def test_missing_required_metadata_fails_closed_with_reason_codes(self):
        payload = assemble_v2_context(
            (
                raw_candidate(
                    availability={
                        'availability_status': 'Available',
                    },
                ),
            )
        ).to_dict()
        summary = refusal_summary(payload)
        reason_codes = set(summary['reason_codes'])

        assert_phase_7_summary(payload, expected_state='failed_closed')
        assert 'missing_confidence_metadata' in reason_codes
        assert 'missing_freshness_metadata' in reason_codes
        assert 'missing_data_state_metadata' in reason_codes
        assert 'missing_limitations_metadata' in reason_codes
        assert 'missing_explanations_metadata' in reason_codes
        assert summary['safe_partial_output_allowed'] is False
        assert payload['recommendation_context']['source_evidence_state'] == (
            'trust_metadata_incomplete'
        )
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False

    def test_unsafe_ranking_selection_and_prediction_fields_fail_closed(self):
        payload = assemble_v2_context(
            (
                raw_candidate(
                    availability={
                        'availability_status': 'Available',
                        'confidence': 'high',
                        'data_state': 'fresh',
                    },
                    top_candidate=True,
                ),
                raw_candidate(
                    availability={
                        'availability_status': 'Available',
                        'confidence': 'high',
                        'data_state': 'fresh',
                    },
                    selected_candidate_id=43,
                ),
                raw_candidate(
                    availability={
                        'availability_status': 'Available',
                        'confidence': 'high',
                        'data_state': 'fresh',
                    },
                    performance_prediction='unsafe',
                ),
            )
        ).to_dict()
        summary = refusal_summary(payload)

        assert_phase_7_summary(payload, expected_state='failed_closed')
        assert summary['critical_failure'] is True
        assert summary['unsafe_source_error_count'] == 3
        assert 'governance_unsafe_source_evidence' in summary['reason_codes']
        assert payload['metadata']['unsafe_input_error_count'] == 3
        assert payload['candidate_groups'] == []
        assert payload['bullpen_state']['bullpen_status'] == 'refused'
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False
        assert v2_governance_errors(payload) == []

    def test_serialization_is_deterministic_and_contains_no_forbidden_outputs(self):
        source_candidates = (
            candidate(42, 'Available Arm'),
            candidate(
                43,
                'Stale Arm',
                availability_status='Monitor',
                confidence='low',
                data_state='stale',
            ),
        )

        first_payload = assemble_v2_context(source_candidates).to_dict()
        second_payload = assemble_v2_context(source_candidates).to_dict()

        assert first_payload == second_payload
        keys = payload_keys(first_payload)
        assert FORBIDDEN_OUTPUT_KEYS.isdisjoint(keys)
        assert 'ranked_candidates' not in keys
        assert first_payload['ranking_applied'] is False
        assert first_payload['selection_made'] is False
        assert v2_governance_errors(first_payload) == []

    def test_v1_recommendation_behavior_remains_unchanged(self):
        result = RecommendationEngine().recommend(candidate=candidate())
        payload = result.to_dict()

        assert result.is_refusal is False
        assert result.has_recommendation is True
        assert payload['metadata']['ranking_applied'] is False
        assert payload['metadata']['selection_made'] is False
        assert payload['metadata']['policy'] == 'recommendation_engine_v1'
