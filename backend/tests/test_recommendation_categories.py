from recommendation import (
    RecommendationCandidate,
    RecommendationCategory,
    RecommendationEngine,
    RecommendationRequest,
    assign_recommendation_categories,
    evaluate_candidate_gates,
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


def assignment_for(candidate_value, context=None):
    gate_result = evaluate_candidate_gates(candidate_value)
    return assign_recommendation_categories(
        gate_result,
        candidate=candidate_value,
        context=context,
    )


def assigned_codes(assignment):
    return {category.name for category in assignment.assigned_categories}


def blocked_reasons(assignment, category):
    for blocked in assignment.blocked_categories:
        if blocked.category == category:
            return set(blocked.reasons)
    return set()


class TestRecommendationCategoryAssignment:
    def test_eligible_available_candidate_can_assign_positive_category_eligibility(self):
        assignment = assignment_for(
            candidate(inputs={'fatigue_score': 20.0, 'latest_game_date': '2026-06-01'})
        )

        assert 'BEST_AVAILABLE_ARM' in assigned_codes(assignment)
        assert assignment.selection_made is False
        assert assignment.ranking_applied is False
        assert assignment.selected_pitcher_id is None

    def test_monitor_candidate_receives_use_with_caution(self):
        assignment = assignment_for(
            candidate(
                availability_status='Monitor',
                inputs={'fatigue_score': 42.0},
            )
        )

        assert 'USE_WITH_CAUTION' in assigned_codes(assignment)
        assert any(
            explanation.code == 'use_with_caution_eligible'
            for explanation in assignment.assignment_explanations
        )

    def test_limited_behavior_matches_gate_policy_restrictions(self):
        assignment = assignment_for(
            candidate(
                availability_status='Limited',
                inputs={'fatigue_score': 65.0},
            )
        )

        assert 'USE_WITH_CAUTION' in assigned_codes(assignment)
        assert 'BEST_AVAILABLE_ARM' not in assigned_codes(assignment)
        assert 'not_positive_pool_eligible' in blocked_reasons(
            assignment,
            RecommendationCategory.BEST_AVAILABLE_ARM,
        )

    def test_avoid_maps_to_avoidance_behavior_not_positive_categories(self):
        assignment = assignment_for(
            candidate(
                availability_status='Avoid',
                inputs={'pitches_yesterday': 38},
            )
        )

        assert 'AVOID_TONIGHT' in assigned_codes(assignment)
        assert 'BEST_AVAILABLE_ARM' not in assigned_codes(assignment)
        assert 'not_positive_pool_eligible' in blocked_reasons(
            assignment,
            RecommendationCategory.BEST_AVAILABLE_ARM,
        )

    def test_unavailable_never_receives_positive_categories(self):
        assignment = assignment_for(
            candidate(
                availability_status='Unavailable',
                inputs={'pitches_yesterday': 52},
            )
        )

        assert 'BEST_AVAILABLE_ARM' not in assigned_codes(assignment)
        assert 'LOWEST_CURRENT_WORKLOAD_RISK' not in assigned_codes(assignment)
        assert 'FRESHEST_HIGH_LEVERAGE_ARM' not in assigned_codes(assignment)
        assert 'AVOID_TONIGHT' in assigned_codes(assignment)

    def test_low_confidence_receives_no_positive_categories(self):
        assignment = assignment_for(
            candidate(
                confidence='low',
                inputs={'fatigue_score': 10.0},
            )
        )

        assert 'BEST_AVAILABLE_ARM' not in assigned_codes(assignment)
        assert 'LOWEST_CURRENT_WORKLOAD_RISK' not in assigned_codes(assignment)
        assert 'candidate_not_eligible' in blocked_reasons(
            assignment,
            RecommendationCategory.BEST_AVAILABLE_ARM,
        )

    def test_stale_freshness_receives_no_positive_categories(self):
        assignment = assignment_for(
            candidate(
                data_state='stale',
                inputs={'fatigue_score': 10.0},
            )
        )

        assert 'BEST_AVAILABLE_ARM' not in assigned_codes(assignment)
        assert 'positive_category_requires_fresh_data' in blocked_reasons(
            assignment,
            RecommendationCategory.BEST_AVAILABLE_ARM,
        )

    def test_missing_gate_result_fails_closed(self):
        assignment = assign_recommendation_categories(None)

        assert assignment.assigned_categories == ()
        assert len(assignment.blocked_categories) == len(RecommendationCategory)
        assert assignment.confidence_state.value == 'unknown'
        assert assignment.freshness_state.value == 'unknown'
        assert assignment.selection_made is False

    def test_category_assignment_includes_explanations(self):
        assignment = assignment_for(candidate(inputs={'fatigue_score': 20.0}))

        assert assignment.assignment_explanations
        assert assignment.to_dict()['assignment_explanations']

    def test_category_assignment_includes_limitations(self):
        assignment = assignment_for(candidate(inputs={'fatigue_score': 20.0}))

        assert assignment.limitations
        assert any(
            limitation.code == 'category_assignment_only'
            for limitation in assignment.limitations
        )

    def test_best_available_arm_assignment_is_not_final_selection(self):
        assignment = assignment_for(candidate(inputs={'fatigue_score': 20.0}))
        payload = assignment.to_dict()

        assert 'BEST_AVAILABLE_ARM' in payload['assigned_category_codes']
        assert payload['selection_made'] is False
        assert payload['ranking_applied'] is False
        assert payload['selected_pitcher_id'] is None

    def test_lowest_current_workload_risk_requires_workload_or_fatigue_evidence(self):
        without_evidence = assignment_for(candidate())
        with_evidence = assignment_for(candidate(inputs={'fatigue_score': 20.0}))

        assert 'LOWEST_CURRENT_WORKLOAD_RISK' not in assigned_codes(without_evidence)
        assert 'missing_workload_evidence' in blocked_reasons(
            without_evidence,
            RecommendationCategory.LOWEST_CURRENT_WORKLOAD_RISK,
        )
        assert 'LOWEST_CURRENT_WORKLOAD_RISK' in assigned_codes(with_evidence)

    def test_freshest_high_leverage_requires_existing_leverage_evidence(self):
        without_leverage = assignment_for(
            candidate(inputs={'pitches_yesterday': 0})
        )
        with_leverage = assignment_for(
            candidate(
                inputs={'pitches_yesterday': 0},
                metadata={'high_leverage_evidence': True},
            )
        )

        assert 'FRESHEST_HIGH_LEVERAGE_ARM' not in assigned_codes(without_leverage)
        assert 'missing_leverage_evidence' in blocked_reasons(
            without_leverage,
            RecommendationCategory.FRESHEST_HIGH_LEVERAGE_ARM,
        )
        assert 'FRESHEST_HIGH_LEVERAGE_ARM' in assigned_codes(with_leverage)

    def test_bullpen_stress_alert_not_assigned_without_bullpen_level_evidence(self):
        assignment = assignment_for(candidate(inputs={'fatigue_score': 20.0}))

        assert 'BULLPEN_STRESS_ALERT' not in assigned_codes(assignment)
        assert 'requires_bullpen_context' in blocked_reasons(
            assignment,
            RecommendationCategory.BULLPEN_STRESS_ALERT,
        )

    def test_bullpen_stress_alert_requires_team_scope_even_with_evidence(self):
        assignment = assignment_for(
            candidate(inputs={'fatigue_score': 20.0}),
            context={'bullpen_stress_evidence': True},
        )

        assert 'BULLPEN_STRESS_ALERT' not in assigned_codes(assignment)

    def test_no_ranking_or_final_recommendation_selection_is_implemented(self):
        player = candidate(inputs={'fatigue_score': 20.0})
        gate_result = evaluate_candidate_gates(player)
        assignment = assign_recommendation_categories(gate_result, candidate=player)
        engine_result = RecommendationEngine().recommend(
            RecommendationRequest(candidates=(player,))
        )

        assert assignment.ranking_applied is False
        assert assignment.selection_made is False
        assert assignment.selected_pitcher_id is None
        assert engine_result.is_refusal is True
        assert engine_result.has_recommendation is False
