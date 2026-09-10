from recommendation import (
    RecommendationCandidate,
    RecommendationCategory,
    RecommendationEngine,
    RecommendationRequest,
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


class TestRecommendationEngineIntegration:
    def test_recommend_without_candidate_still_refuses(self):
        result = RecommendationEngine().recommend()
        payload = result.to_dict()

        assert result.is_refusal is True
        assert result.has_recommendation is False
        assert payload['metadata']['candidate_pipeline_enabled'] is False
        assert payload['metadata']['ranking_applied'] is False
        assert payload['metadata']['selection_made'] is False

    def test_valid_available_candidate_returns_structured_candidate_response(self):
        result = RecommendationEngine().recommend(
            candidate=candidate(inputs={'fatigue_score': 20.0})
        )
        payload = result.to_dict()

        assert result.is_refusal is False
        assert result.has_recommendation is True
        assert is_valid_recommendation_result(result) is True
        assert payload['pitcher_id'] == 42
        assert 'BEST_AVAILABLE_ARM' in payload['metadata']['assigned_category_codes']
        assert payload['metadata']['candidate_pipeline_enabled'] is True
        assert payload['metadata']['response_mode'] == 'candidate_category_eligibility'

    def test_single_candidate_request_uses_candidate_pipeline(self):
        request = RecommendationRequest(
            category=RecommendationCategory.BEST_AVAILABLE_ARM,
            team_id=7,
            team_name='Example Club',
            candidates=(candidate(inputs={'fatigue_score': 20.0}),),
            metadata={'request_id': 'integration-test'},
        )

        result = RecommendationEngine().recommend(request)
        payload = result.to_dict()

        assert result.is_refusal is False
        assert payload['metadata']['context']['requested_category_code'] == (
            'BEST_AVAILABLE_ARM'
        )
        assert payload['metadata']['context']['team_id'] == 7
        assert payload['metadata']['request']['metadata']['request_id'] == (
            'integration-test'
        )

    def test_monitor_candidate_preserves_caution_behavior(self):
        result = RecommendationEngine().recommend(
            candidate=candidate(
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

    def test_limited_candidate_matches_gate_and_category_rules(self):
        result = RecommendationEngine().recommend(
            candidate=candidate(
                availability_status='Limited',
                inputs={'fatigue_score': 65.0},
            )
        )
        payload = result.to_dict()

        assert result.is_refusal is False
        assert payload['category_code'] == 'USE_WITH_CAUTION'
        assert payload['metadata']['positive_category_codes'] == []
        assert 'BEST_AVAILABLE_ARM' not in payload['metadata']['assigned_category_codes']

    def test_avoid_candidate_does_not_receive_positive_categories(self):
        result = RecommendationEngine().recommend(
            candidate=candidate(
                availability_status='Avoid',
                inputs={'pitches_yesterday': 38},
            )
        )
        payload = result.to_dict()

        assert result.is_refusal is False
        assert payload['category_code'] == 'AVOID_TONIGHT'
        assert payload['metadata']['positive_category_codes'] == []
        assert 'BEST_AVAILABLE_ARM' not in payload['metadata']['assigned_category_codes']

    def test_unavailable_candidate_refuses_with_no_positive_categories(self):
        result = RecommendationEngine().recommend(
            candidate=candidate(
                availability_status='Unavailable',
                inputs={'pitches_yesterday': 52},
            )
        )
        payload = result.to_dict()

        assert result.is_refusal is True
        assert result.has_recommendation is False
        assert payload['category_code'] is None
        assert payload['metadata']['positive_category_codes'] == []
        assert 'AVOID_TONIGHT' in payload['metadata']['assigned_category_codes']

    def test_low_confidence_candidate_refuses(self):
        result = RecommendationEngine().recommend(
            candidate=candidate(confidence='low', inputs={'fatigue_score': 10.0})
        )

        assert result.is_refusal is True
        assert result.refusal_reason.value == 'low_confidence'
        assert result.has_recommendation is False

    def test_stale_freshness_candidate_refuses(self):
        result = RecommendationEngine().recommend(
            candidate=candidate(data_state='stale', inputs={'fatigue_score': 10.0})
        )

        assert result.is_refusal is True
        assert result.refusal_reason.value == 'stale_data'
        assert result.has_recommendation is False

    def test_missing_required_candidate_fields_fail_closed(self):
        result = RecommendationEngine().recommend(
            candidate=candidate(
                pitcher_id=None,
                inputs={'fatigue_score': 10.0},
            )
        )

        assert result.is_refusal is True
        assert result.has_recommendation is False
        assert any(
            explanation.code == 'missing_pitcher_identity'
            for explanation in result.explanations
        )

    def test_invalid_candidate_fails_closed(self):
        result = RecommendationEngine().recommend(candidate='invalid')
        payload = result.to_dict()

        assert result.is_refusal is True
        assert result.has_recommendation is False
        assert payload['metadata']['refusal_boundary'] == 'invalid_candidate'

    def test_engine_response_includes_explanations_and_limitations(self):
        result = RecommendationEngine().recommend(
            candidate=candidate(inputs={'fatigue_score': 20.0})
        )
        payload = result.to_dict()

        assert payload['explanations']
        assert payload['limitations']

    def test_engine_response_includes_confidence_freshness_and_availability(self):
        result = RecommendationEngine().recommend(
            candidate=candidate(inputs={'fatigue_score': 20.0})
        )
        payload = result.to_dict()

        assert payload['confidence']['level'] == 'high'
        assert payload['freshness']['state'] == 'fresh'
        assert payload['metadata']['availability_state'] == 'Available'

    def test_engine_response_includes_assigned_and_blocked_categories(self):
        result = RecommendationEngine().recommend(
            candidate=candidate(inputs={'fatigue_score': 20.0})
        )
        payload = result.to_dict()

        assert payload['metadata']['assigned_categories']
        assert payload['metadata']['assigned_category_codes']
        assert payload['metadata']['blocked_categories']

    def test_engine_always_marks_no_ranking_or_selection(self):
        result = RecommendationEngine().recommend(
            candidate=candidate(inputs={'fatigue_score': 20.0})
        )
        payload = result.to_dict()

        assert payload['metadata']['ranking_applied'] is False
        assert payload['metadata']['selection_made'] is False
        assert payload['metadata']['selected_pitcher_id'] is None

    def test_engine_does_not_rank_score_compare_or_select_final_pitcher(self):
        request = RecommendationRequest(
            candidates=(
                candidate(pitcher_id=42, inputs={'fatigue_score': 20.0}),
                candidate(pitcher_id=43, inputs={'fatigue_score': 15.0}),
            )
        )

        result = RecommendationEngine().recommend(request)
        payload = result.to_dict()

        assert result.is_refusal is True
        assert result.has_recommendation is False
        assert payload['alternatives'] == []
        assert payload['metadata']['refusal_boundary'] == (
            'multi_candidate_ranking_not_implemented'
        )
        assert payload['metadata']['ranking_applied'] is False
        assert payload['metadata']['selection_made'] is False
        assert payload['metadata']['selected_pitcher_id'] is None
        assert 'rank' not in payload['metadata']
        assert 'score' not in payload['metadata']
        assert 'comparison' not in payload['metadata']
