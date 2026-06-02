from recommendation import (
    BASE_RECOMMENDATION_LIMITATIONS,
    RecommendationCandidate,
    RecommendationCategory,
    RecommendationConfidence,
    RecommendationConfidenceContext,
    RecommendationEngine,
    RecommendationExplanation,
    RecommendationFreshnessContext,
    RecommendationFreshnessState,
    RecommendationLimitation,
    RecommendationRequest,
    RecommendationResult,
    RefusalReason,
    is_valid_recommendation_result,
    recommendation_result_errors,
)


def enum_names(enum_type):
    return {member.name for member in enum_type}


class TestRecommendationFoundation:
    def test_engine_initializes_with_foundation_metadata(self):
        engine = RecommendationEngine()

        assert engine.policy_name == 'recommendation_engine_v1'
        assert engine.implementation_phase == 'candidate_engine_integration'
        assert engine.policy_document == 'docs/RECOMMENDATION_ENGINE_V1_POLICY.md'

    def test_default_engine_behavior_refuses(self):
        result = RecommendationEngine().recommend()

        assert result.is_refusal is True
        assert result.has_recommendation is False
        assert result.category is None
        assert result.pitcher_id is None
        assert result.pitcher_name is None
        assert result.refusal_reason == RefusalReason.INSUFFICIENT_DATA
        assert is_valid_recommendation_result(result) is True

    def test_refusal_response_shape_is_valid(self):
        payload = RecommendationEngine().recommend().to_dict()

        assert payload['outcome'] == 'refusal'
        assert payload['outcome_code'] == 'REFUSAL'
        assert payload['category'] is None
        assert payload['pitcher_id'] is None
        assert payload['pitcher_name'] is None
        assert payload['confidence']['level'] == 'unknown'
        assert payload['freshness']['state'] == 'unknown'
        assert payload['refusal_reason'] == 'insufficient_data'
        assert payload['refusal_reason_code'] == 'INSUFFICIENT_DATA'
        assert payload['refusal']['message']
        assert payload['explanations']
        assert payload['limitations']
        assert payload['metadata']['decision_logic_enabled'] is False

    def test_required_enums_are_available(self):
        assert enum_names(RecommendationCategory) == {
            'BEST_AVAILABLE_ARM',
            'FRESHEST_HIGH_LEVERAGE_ARM',
            'LOWEST_CURRENT_WORKLOAD_RISK',
            'USE_WITH_CAUTION',
            'AVOID_TONIGHT',
            'BULLPEN_STRESS_ALERT',
        }
        assert enum_names(RecommendationConfidence) == {
            'HIGH',
            'MEDIUM',
            'LOW',
            'UNKNOWN',
        }
        assert {
            'INSUFFICIENT_DATA',
            'STALE_DATA',
            'LOW_CONFIDENCE',
            'NO_ELIGIBLE_PITCHERS',
            'DATA_UNAVAILABLE',
        }.issubset(enum_names(RefusalReason))

    def test_contracts_serialize_to_stable_shapes(self):
        candidate = RecommendationCandidate(
            pitcher_id=42,
            pitcher_name='Example Pitcher',
            team_id=7,
            team_name='Example Club',
            availability={'availability_status': 'Available'},
        )
        request = RecommendationRequest(
            category=RecommendationCategory.BEST_AVAILABLE_ARM,
            team_id=7,
            team_name='Example Club',
            candidates=(candidate,),
        )
        confidence = RecommendationConfidenceContext(
            level=RecommendationConfidence.HIGH,
            reasons=('fresh availability output',),
        )
        freshness = RecommendationFreshnessContext(
            state=RecommendationFreshnessState.FRESH,
            data_through='2026-06-01',
            last_successful_sync='2026-06-02T10:00:00Z',
        )
        explanation = RecommendationExplanation(
            code='workload_context_available',
            message='Workload context is available.',
        )
        limitation = RecommendationLimitation(
            code='public_workload_data_only',
            message='Based on public workload data tracked by BaseballOS.',
        )

        assert request.to_dict()['category_code'] == 'BEST_AVAILABLE_ARM'
        assert request.to_dict()['candidates'][0]['pitcher_id'] == 42
        assert confidence.to_dict()['level_code'] == 'HIGH'
        assert freshness.to_dict()['state_code'] == 'FRESH'
        assert explanation.to_dict()['code'] == 'workload_context_available'
        assert limitation.to_dict()['code'] == 'public_workload_data_only'

    def test_result_schema_can_represent_future_success_without_engine_logic(self):
        result = RecommendationResult.recommendation(
            category=RecommendationCategory.BEST_AVAILABLE_ARM,
            pitcher_id=42,
            pitcher_name='Example Pitcher',
            confidence=RecommendationConfidenceContext(
                level=RecommendationConfidence.HIGH
            ),
            freshness=RecommendationFreshnessContext(
                state=RecommendationFreshnessState.FRESH,
                data_through='2026-06-01',
            ),
            explanations=(
                RecommendationExplanation(
                    code='future_policy_reason',
                    message='Future policy reason placeholder.',
                ),
            ),
            limitations=BASE_RECOMMENDATION_LIMITATIONS,
        )

        assert result.is_refusal is False
        assert result.has_recommendation is True
        assert is_valid_recommendation_result(result) is True
        assert result.to_dict()['category_code'] == 'BEST_AVAILABLE_ARM'

    def test_multi_candidate_engine_request_fails_closed_without_ranking(self):
        request = RecommendationRequest(
            category=RecommendationCategory.BEST_AVAILABLE_ARM,
            candidates=(
                RecommendationCandidate(
                    pitcher_id=99,
                    pitcher_name='Candidate Pitcher',
                    availability={
                        'availability_status': 'Available',
                        'confidence': 'high',
                        'data_state': 'fresh',
                    },
                ),
                RecommendationCandidate(
                    pitcher_id=100,
                    pitcher_name='Second Candidate',
                    availability={
                        'availability_status': 'Available',
                        'confidence': 'high',
                        'data_state': 'fresh',
                    },
                ),
            ),
        )

        result = RecommendationEngine().recommend(request)
        payload = result.to_dict()

        assert result.is_refusal is True
        assert result.has_recommendation is False
        assert payload['category'] is None
        assert payload['pitcher_id'] is None
        assert payload['pitcher_name'] is None
        assert payload['metadata']['ranking_applied'] is False
        assert payload['metadata']['selection_made'] is False
        assert payload['metadata']['refusal_boundary'] == (
            'multi_candidate_ranking_not_implemented'
        )
        assert payload['metadata']['request']['candidates'][0]['pitcher_id'] == 99

    def test_bare_result_defaults_to_refusal(self):
        result = RecommendationResult()

        assert result.is_refusal is True
        assert result.has_recommendation is False
        assert result.refusal_reason == RefusalReason.INSUFFICIENT_DATA
        assert is_valid_recommendation_result(result) is True

    def test_validator_rejects_malformed_recommendation_result(self):
        result = RecommendationResult(
            category=RecommendationCategory.BEST_AVAILABLE_ARM,
            pitcher_id=42,
        )

        assert is_valid_recommendation_result(result) is False
        assert 'Refusal result must not include a category.' in (
            recommendation_result_errors(result)
        )
