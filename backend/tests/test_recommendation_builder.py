from recommendation import (
    RecommendationCandidate,
    RecommendationEngine,
    build_recommendation_response,
    evaluate_candidate_gates,
    is_valid_recommendation_result,
)


def candidate(
    pitcher_id=42,
    pitcher_name='Example Pitcher',
    availability_status='Available',
    confidence='high',
    data_state='fresh',
    inputs=None,
    metadata=None,
):
    availability = {}
    if availability_status is not None:
        availability['availability_status'] = availability_status
    if confidence is not None:
        availability['confidence'] = confidence
    if data_state is not None:
        availability['data_state'] = data_state
    if inputs is not None:
        availability['inputs'] = inputs

    return RecommendationCandidate(
        pitcher_id=pitcher_id,
        pitcher_name=pitcher_name,
        availability=availability,
        metadata=metadata or {},
    )


class TestRecommendationResponseBuilder:
    def test_eligible_available_candidate_produces_structured_non_refusal_response(self):
        result = build_recommendation_response(
            candidate(inputs={'fatigue_score': 20.0})
        )
        payload = result.to_dict()

        assert result.is_refusal is False
        assert result.has_recommendation is True
        assert is_valid_recommendation_result(result) is True
        assert payload['pitcher_id'] == 42
        assert 'BEST_AVAILABLE_ARM' in payload['metadata']['assigned_category_codes']
        assert payload['metadata']['ranking_applied'] is False
        assert payload['metadata']['selection_made'] is False

    def test_monitor_candidate_preserves_caution_explanations_and_limitations(self):
        result = build_recommendation_response(
            candidate(
                availability_status='Monitor',
                inputs={'fatigue_score': 45.0},
            )
        )
        payload = result.to_dict()

        assert result.is_refusal is False
        assert 'USE_WITH_CAUTION' in payload['metadata']['assigned_category_codes']
        assert any(
            explanation['code'] == 'monitor_requires_review'
            for explanation in payload['explanations']
        )
        assert any(
            limitation['code'] == 'candidate_has_cautions'
            for limitation in payload['limitations']
        )

    def test_limited_candidate_matches_category_assignment_restrictions(self):
        result = build_recommendation_response(
            candidate(
                availability_status='Limited',
                inputs={'fatigue_score': 65.0},
            )
        )
        payload = result.to_dict()

        assert result.is_refusal is False
        assert payload['category_code'] == 'USE_WITH_CAUTION'
        assert 'USE_WITH_CAUTION' in payload['metadata']['assigned_category_codes']
        assert 'BEST_AVAILABLE_ARM' not in payload['metadata']['assigned_category_codes']
        assert payload['metadata']['positive_category_codes'] == []

    def test_avoid_candidate_produces_avoidance_response_with_no_positive_categories(self):
        result = build_recommendation_response(
            candidate(
                availability_status='Avoid',
                inputs={'pitches_yesterday': 38},
            )
        )
        payload = result.to_dict()

        assert result.is_refusal is False
        assert payload['category_code'] == 'AVOID_TONIGHT'
        assert payload['metadata']['positive_category_codes'] == []
        assert 'BEST_AVAILABLE_ARM' not in payload['metadata']['assigned_category_codes']

    def test_unavailable_candidate_never_emits_positive_recommendation(self):
        result = build_recommendation_response(
            candidate(
                availability_status='Unavailable',
                inputs={'pitches_yesterday': 52},
            )
        )
        payload = result.to_dict()

        assert result.is_refusal is True
        assert result.has_recommendation is False
        assert payload['category_code'] is None
        assert payload['metadata']['positive_category_codes'] == []

    def test_low_confidence_candidate_refuses(self):
        result = build_recommendation_response(
            candidate(confidence='low', inputs={'fatigue_score': 10.0})
        )

        assert result.is_refusal is True
        assert result.refusal_reason.value == 'low_confidence'
        assert result.has_recommendation is False

    def test_stale_freshness_candidate_refuses(self):
        result = build_recommendation_response(
            candidate(data_state='stale', inputs={'fatigue_score': 10.0})
        )

        assert result.is_refusal is True
        assert result.refusal_reason.value == 'stale_data'
        assert result.has_recommendation is False

    def test_missing_or_invalid_gate_result_refuses(self):
        result = build_recommendation_response(gate_result='invalid')
        payload = result.to_dict()

        assert result.is_refusal is True
        assert result.has_recommendation is False
        assert payload['refusal_reason'] == 'insufficient_data'
        assert payload['metadata']['selection_made'] is False

    def test_missing_or_invalid_category_result_refuses(self):
        player = candidate(inputs={'fatigue_score': 20.0})
        gate_result = evaluate_candidate_gates(player)

        result = build_recommendation_response(
            candidate=player,
            gate_result=gate_result,
            category_assignment='invalid',
        )

        assert result.is_refusal is True
        assert result.has_recommendation is False
        assert result.refusal_reason.value == 'insufficient_data'

    def test_response_includes_explanations(self):
        result = build_recommendation_response(
            candidate(inputs={'fatigue_score': 20.0})
        )

        assert result.explanations
        assert result.to_dict()['explanations']

    def test_response_includes_limitations(self):
        result = build_recommendation_response(
            candidate(inputs={'fatigue_score': 20.0})
        )

        assert result.limitations
        assert any(
            limitation.code == 'builder_not_final_recommender'
            for limitation in result.limitations
        )

    def test_response_includes_confidence_freshness_and_availability_state(self):
        result = build_recommendation_response(
            candidate(inputs={'fatigue_score': 20.0})
        )
        payload = result.to_dict()

        assert payload['confidence']['level'] == 'high'
        assert payload['freshness']['state'] == 'fresh'
        assert payload['metadata']['availability_state'] == 'Available'

    def test_response_includes_ranking_applied_false(self):
        result = build_recommendation_response(
            candidate(inputs={'fatigue_score': 20.0})
        )

        assert result.to_dict()['metadata']['ranking_applied'] is False

    def test_response_includes_selection_made_false(self):
        result = build_recommendation_response(
            candidate(inputs={'fatigue_score': 20.0})
        )

        assert result.to_dict()['metadata']['selection_made'] is False

    def test_builder_does_not_rank_or_compare_candidates(self):
        result = build_recommendation_response(
            candidate(inputs={'fatigue_score': 20.0})
        )
        payload = result.to_dict()

        assert payload['alternatives'] == []
        assert payload['metadata']['response_mode'] == 'candidate_category_eligibility'
        assert payload['metadata']['selected_pitcher_id'] is None
        assert 'comparison' not in payload['metadata']
        assert 'rank' not in payload['metadata']

    def test_existing_fail_closed_default_engine_behavior_remains_intact(self):
        result = RecommendationEngine().recommend()

        assert result.is_refusal is True
        assert result.has_recommendation is False
        assert result.refusal_reason.value == 'insufficient_data'
