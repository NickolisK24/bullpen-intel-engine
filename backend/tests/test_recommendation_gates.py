from recommendation import (
    RecommendationCandidate,
    RecommendationCandidatePool,
    RecommendationConfidence,
    RecommendationEngine,
    RecommendationFreshnessState,
    RecommendationRequest,
    evaluate_candidate_gates,
    evaluate_candidate_pool,
)


def candidate(
    pitcher_id=42,
    pitcher_name='Example Pitcher',
    availability_status='Available',
    confidence='high',
    data_state='fresh',
):
    availability = {}
    if availability_status is not None:
        availability['availability_status'] = availability_status
    if confidence is not None:
        availability['confidence'] = confidence
    if data_state is not None:
        availability['data_state'] = data_state

    return RecommendationCandidate(
        pitcher_id=pitcher_id,
        pitcher_name=pitcher_name,
        availability=availability,
    )


class TestRecommendationEligibilityGates:
    def test_fully_eligible_candidate_passes(self):
        result = evaluate_candidate_gates(candidate())

        assert result.eligible is True
        assert result.excluded is False
        assert result.exclusion_reasons == ()
        assert result.caution_reasons == ()
        assert result.availability_state == 'Available'
        assert result.confidence_state == RecommendationConfidence.HIGH
        assert result.freshness_state == RecommendationFreshnessState.FRESH
        assert result.positive_pool_eligible is True

    def test_missing_pitcher_identity_fails_closed(self):
        result = evaluate_candidate_gates(candidate(pitcher_id=None))

        assert result.eligible is False
        assert result.excluded is True
        assert 'missing_pitcher_identity' in result.exclusion_reasons
        assert result.positive_pool_eligible is False

    def test_missing_availability_fails_closed(self):
        result = evaluate_candidate_gates(
            RecommendationCandidate(pitcher_id=42, pitcher_name='Example Pitcher')
        )

        assert result.eligible is False
        assert result.excluded is True
        assert 'missing_availability' in result.exclusion_reasons
        assert 'missing_availability_status' not in result.exclusion_reasons

    def test_unavailable_fails_closed(self):
        result = evaluate_candidate_gates(candidate(availability_status='Unavailable'))

        assert result.eligible is False
        assert result.excluded is True
        assert 'availability_unavailable' in result.exclusion_reasons
        assert result.positive_pool_eligible is False

    def test_avoid_is_excluded_from_positive_recommendation_pool(self):
        result = evaluate_candidate_gates(
            candidate(availability_status='Avoid'),
            candidate_pool=RecommendationCandidatePool.POSITIVE,
        )

        assert result.eligible is False
        assert result.excluded is True
        assert 'avoid_not_positive_candidate' in result.exclusion_reasons
        assert result.positive_pool_eligible is False

    def test_avoid_can_only_enter_non_positive_context_with_caution(self):
        result = evaluate_candidate_gates(candidate(availability_status='Avoid'))

        assert result.eligible is True
        assert result.excluded is False
        assert 'avoid_only_for_avoidance_context' in result.caution_reasons
        assert result.positive_pool_eligible is False

    def test_low_confidence_fails_closed(self):
        result = evaluate_candidate_gates(candidate(confidence='low'))

        assert result.eligible is False
        assert result.excluded is True
        assert 'low_confidence' in result.exclusion_reasons

    def test_unknown_confidence_fails_closed(self):
        result = evaluate_candidate_gates(candidate(confidence=None))

        assert result.eligible is False
        assert result.excluded is True
        assert result.confidence_state == RecommendationConfidence.UNKNOWN
        assert 'unknown_confidence' in result.exclusion_reasons

    def test_missing_freshness_fails_closed(self):
        result = evaluate_candidate_gates(candidate(data_state=None))

        assert result.eligible is False
        assert result.excluded is True
        assert result.freshness_state == RecommendationFreshnessState.UNKNOWN
        assert 'missing_freshness' in result.exclusion_reasons

    def test_stale_freshness_fails_closed(self):
        result = evaluate_candidate_gates(candidate(data_state='stale'))

        assert result.eligible is False
        assert result.excluded is True
        assert result.freshness_state == RecommendationFreshnessState.STALE
        assert 'stale_freshness' in result.exclusion_reasons

    def test_monitor_passes_with_caution(self):
        result = evaluate_candidate_gates(candidate(availability_status='Monitor'))

        assert result.eligible is True
        assert result.excluded is False
        assert 'monitor_requires_review' in result.caution_reasons
        assert result.positive_pool_eligible is True
        assert any(
            explanation.code == 'monitor_requires_review'
            for explanation in result.explanations
        )

    def test_limited_behavior_matches_approved_policy(self):
        general_result = evaluate_candidate_gates(
            candidate(availability_status='Limited')
        )
        positive_result = evaluate_candidate_gates(
            candidate(availability_status='Limited'),
            candidate_pool=RecommendationCandidatePool.POSITIVE,
        )

        assert general_result.eligible is True
        assert general_result.excluded is False
        assert 'limited_use_only' in general_result.caution_reasons
        assert general_result.positive_pool_eligible is False
        assert positive_result.eligible is False
        assert positive_result.excluded is True
        assert 'limited_not_positive_candidate' in positive_result.exclusion_reasons

    def test_medium_confidence_passes_with_limitation(self):
        result = evaluate_candidate_gates(candidate(confidence='medium'))

        assert result.eligible is True
        assert result.excluded is False
        assert 'medium_confidence_requires_limitation' in result.caution_reasons
        assert result.confidence_state == RecommendationConfidence.MEDIUM
        assert result.positive_pool_eligible is False

    def test_gate_results_include_explanations_and_limitations(self):
        result = evaluate_candidate_gates(candidate(availability_status='Monitor'))
        payload = result.to_dict()

        assert payload['explanations']
        assert payload['limitations']
        assert payload['confidence_state'] == 'high'
        assert payload['freshness_state'] == 'fresh'
        assert payload['availability_state'] == 'Monitor'

    def test_gate_layer_does_not_emit_final_recommendation(self):
        evaluated_candidate = candidate()
        gate_result = evaluate_candidate_gates(evaluated_candidate)
        gate_payload = gate_result.to_dict()
        engine_result = RecommendationEngine().recommend(
            RecommendationRequest(candidates=(evaluated_candidate,))
        )

        assert 'category' not in gate_payload
        assert 'outcome' not in gate_payload
        assert gate_result.positive_pool_eligible is True
        assert engine_result.is_refusal is True
        assert engine_result.has_recommendation is False

    def test_candidate_pool_helper_evaluates_each_candidate(self):
        results = evaluate_candidate_pool(
            [
                candidate(pitcher_id=1),
                candidate(pitcher_id=2, confidence='low'),
            ]
        )

        assert len(results) == 2
        assert results[0].eligible is True
        assert results[1].eligible is False
