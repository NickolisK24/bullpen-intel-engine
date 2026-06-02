import pytest

from recommendation import (
    BullpenState,
    CandidateGroup,
    RecommendationConfidence,
    RecommendationContext,
    RecommendationEngine,
    RecommendationFreshnessState,
    TeamBullpenContext,
    V2Explanation,
    V2FreshnessMetadata,
    V2Limitation,
    V2Refusal,
    v2_governance_errors,
)


FORBIDDEN_PAYLOAD_KEYS = {
    'rank',
    'ranking',
    'winner',
    'priority_score',
    'score',
    'score_ordering',
    'selected_pitcher',
    'selected_pitcher_id',
    'recommended_pitcher',
    'preferred_pitcher',
    'use_this_pitcher',
    'best_candidate',
    'pitcher_choice',
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


class TestRecommendationEngineV2DomainFoundation:
    def test_recommendation_context_defaults_preserve_governance_metadata(self):
        context = RecommendationContext()
        payload = context.to_dict()

        assert payload['scope'] == 'bullpen_state'
        assert payload['policy'] == 'recommendation_engine_v2_domain_foundation'
        assert payload['phase'] == 'phase_1_backend_domain_object_foundation'
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False
        assert payload['confidence'] == 'unknown'
        assert payload['confidence_code'] == 'UNKNOWN'
        assert payload['data_state'] == 'unknown'
        assert payload['freshness']['state'] == 'unknown'
        assert payload['limitations']
        assert payload['explanations'] == []
        assert payload['refusal_reasons'] == []
        assert v2_governance_errors(payload) == []

    def test_context_rejects_ranking_or_selection_activation(self):
        with pytest.raises(ValueError, match='ranking_applied=False'):
            RecommendationContext(ranking_applied=True)

        with pytest.raises(ValueError, match='selection_made=False'):
            RecommendationContext(selection_made=True)

    def test_context_represents_trust_freshness_refusal_and_explanations(self):
        context = RecommendationContext(
            scope='candidate_group',
            confidence=RecommendationConfidence.MEDIUM,
            data_state='stale',
            generated_at='2026-06-02T12:00:00Z',
            freshness=V2FreshnessMetadata(
                state=RecommendationFreshnessState.STALE,
                data_through='2026-06-01',
                last_successful_sync='2026-06-02T11:30:00Z',
                latest_sync_status='success',
                stale_warning='Current bullpen state is stale.',
            ),
            limitations=(
                V2Limitation(
                    limitation_id='no_manager_intent',
                    message='Manager intent is not available.',
                    applies_to='candidate_group',
                ),
            ),
            explanations=(
                V2Explanation(
                    code='grouped_by_shared_eligibility',
                    message='Candidates share the same documented eligibility criteria.',
                    applies_to='candidate_group',
                ),
            ),
            refusal_reasons=(
                V2Refusal(
                    refusal_id='stale_freshness',
                    reason='freshness_stale',
                    message='Current candidate grouping is downgraded because data is stale.',
                    applies_to='candidate_group',
                ),
            ),
        )

        payload = context.to_dict()

        assert payload['confidence'] == 'medium'
        assert payload['data_state'] == 'stale'
        assert payload['freshness']['data_through'] == '2026-06-01'
        assert payload['freshness']['stale_warning']
        assert payload['limitations'][0]['limitation_id'] == 'no_manager_intent'
        assert payload['explanations'][0]['code'] == 'grouped_by_shared_eligibility'
        assert payload['refusal_reasons'][0]['reason'] == 'freshness_stale'
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False
        assert v2_governance_errors(payload) == []

    def test_candidate_group_is_neutral_and_preserves_input_sequence(self):
        group = CandidateGroup(
            group_id='fresh_available_arms',
            label='Fresh Available Arms',
            criteria=('availability_status=Available', 'freshness=fresh'),
            candidates=(
                {'pitcher_id': 42, 'pitcher_name': 'Example Pitcher'},
                {'pitcher_id': 43, 'pitcher_name': 'Second Pitcher'},
            ),
        )

        payload = group.to_dict()

        assert payload['group_id'] == 'fresh_available_arms'
        assert payload['candidate_count'] == 2
        assert payload['candidates'][0]['pitcher_id'] == 42
        assert payload['candidates'][1]['pitcher_id'] == 43
        assert payload['neutral_sequence_basis'] == 'input_sequence_preserved'
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False
        assert FORBIDDEN_PAYLOAD_KEYS.isdisjoint(payload_keys(payload))
        assert v2_governance_errors(payload) == []

    def test_candidate_group_rejects_forbidden_ranking_or_selection_fields(self):
        with pytest.raises(ValueError, match='forbidden V2 field name'):
            CandidateGroup(
                group_id='invalid',
                label='Invalid',
                criteria=('demo',),
                candidates=({'pitcher_id': 42, 'rank': 1},),
            )

        with pytest.raises(ValueError, match='forbidden V2 field name'):
            CandidateGroup(
                group_id='invalid',
                label='Invalid',
                criteria=('demo',),
                metadata={'selected_pitcher': 42},
            )

    def test_bullpen_state_represents_inventory_readiness_workload_and_stress(self):
        state = BullpenState(
            team_id=7,
            team_name='Example Club',
            bullpen_status='monitor',
            inventory={'available': 3, 'limited': 1},
            readiness={'ready': 3, 'monitor': 2},
            workload={'recent_high_usage': 2},
            stress={'stress_level': 'elevated'},
            candidate_groups=(
                CandidateGroup(
                    group_id='use_with_caution',
                    label='Use With Caution',
                    criteria=('availability_status=Monitor',),
                    candidates=({'pitcher_id': 44, 'pitcher_name': 'Caution Arm'},),
                ),
            ),
        )

        payload = state.to_dict()

        assert payload['team_id'] == 7
        assert payload['bullpen_status'] == 'monitor'
        assert payload['inventory']['available'] == 3
        assert payload['readiness']['ready'] == 3
        assert payload['workload']['recent_high_usage'] == 2
        assert payload['stress']['stress_level'] == 'elevated'
        assert payload['candidate_groups'][0]['group_id'] == 'use_with_caution'
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False
        assert v2_governance_errors(payload) == []

    def test_team_bullpen_context_represents_team_level_distributions(self):
        team_context = TeamBullpenContext(
            team_id=7,
            team_name='Example Club',
            leverage_inventory={'high_leverage_available': 2},
            workload_distribution={'low': 3, 'moderate': 2, 'elevated': 1},
            readiness_distribution={'available': 3, 'monitor': 2, 'limited': 1},
            stress_indicators={'compressed_usage_window': True},
        )

        payload = team_context.to_dict()

        assert payload['leverage_inventory']['high_leverage_available'] == 2
        assert payload['workload_distribution']['elevated'] == 1
        assert payload['readiness_distribution']['available'] == 3
        assert payload['stress_indicators']['compressed_usage_window'] is True
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False
        assert FORBIDDEN_PAYLOAD_KEYS.isdisjoint(payload_keys(payload))
        assert v2_governance_errors(payload) == []

    def test_v1_recommendation_behavior_remains_unchanged(self):
        result = RecommendationEngine().recommend()
        payload = result.to_dict()

        assert result.is_refusal is True
        assert result.has_recommendation is False
        assert payload['outcome'] == 'refusal'
        assert payload['metadata']['ranking_applied'] is False
        assert payload['metadata']['selection_made'] is False
        assert payload['metadata']['policy'] == 'recommendation_engine_v1'
