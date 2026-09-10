from recommendation import (
    INVENTORY_VISIBILITY_SECTIONS,
    RecommendationCandidate,
    RecommendationEngine,
    V2_INVENTORY_VISIBILITY_PHASE,
    assemble_v2_context,
    v2_governance_errors,
)


FORBIDDEN_OUTPUT_KEYS = {
    'rank',
    'winner',
    'priority',
    'priority_score',
    'score',
    'score_ordering',
    'selected_pitcher',
    'selected_pitcher_id',
    'recommended_pitcher',
    'preferred_pitcher',
    'preferred_option',
    'use_this_pitcher',
    'best_candidate',
    'best_pitcher',
    'pitcher_choice',
}


DEFAULT_INPUTS = {
    'fatigue_score': 20.0,
    'pitches_yesterday': 0,
    'latest_game_date': '2026-06-01',
}


def candidate(
    pitcher_id,
    pitcher_name,
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


class TestRecommendationEngineV2InventoryVisibility:
    def test_inventory_visibility_summarizes_bullpen_resources(self):
        payload = assemble_v2_context(
            (
                candidate(42, 'Available Arm', metadata={'high_leverage_evidence': True}),
                candidate(
                    43,
                    'Monitor Arm',
                    availability_status='Monitor',
                    confidence='medium',
                    inputs={'fatigue_score': 45.0, 'pitches_yesterday': 18},
                ),
                candidate(
                    44,
                    'Limited Arm',
                    availability_status='Limited',
                    inputs={'fatigue_score': 52.0, 'pitches_yesterday': 12},
                ),
                candidate(
                    45,
                    'Avoid Arm',
                    availability_status='Avoid',
                    inputs={'fatigue_score': 72.0, 'pitches_yesterday': 40},
                ),
                candidate(
                    46,
                    'Unavailable Arm',
                    availability_status='Unavailable',
                    inputs={},
                ),
            ),
            generated_at='2026-06-02T12:00:00Z',
        ).to_dict()

        inventory = payload['metadata']['inventory_visibility']
        bullpen_inventory = payload['bullpen_state']['inventory']['visibility_summary']
        availability = inventory['availability_inventory']
        freshness = inventory['freshness_inventory']
        readiness = inventory['readiness_inventory']
        workload = inventory['workload_inventory']

        assert inventory['phase'] == V2_INVENTORY_VISIBILITY_PHASE
        assert inventory['sections'] == list(INVENTORY_VISIBILITY_SECTIONS)
        assert inventory['total_inventory_count'] == 5
        assert bullpen_inventory == inventory
        assert availability['available_count'] == 1
        assert availability['monitor_count'] == 1
        assert availability['limited_count'] == 1
        assert availability['avoid_count'] == 1
        assert availability['unavailable_count'] == 1
        assert freshness['fresh_count'] == 5
        assert freshness['missing_data_count'] == 0
        assert readiness['available_or_monitor_count'] == 2
        assert readiness['limited_or_avoid_count'] == 2
        assert readiness['unavailable_or_unknown_count'] == 1
        assert workload['category_counts']['low'] == 1
        assert workload['category_counts']['moderate'] == 2
        assert workload['category_counts']['elevated'] == 1
        assert workload['category_counts']['unknown'] == 1
        assert workload['missing_workload_input_count'] == 1
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False
        assert v2_governance_errors(payload) == []

    def test_inventory_members_preserve_input_order_without_ranked_lists(self):
        payload = assemble_v2_context(
            (
                candidate(100, 'First Available'),
                candidate(101, 'Monitor Arm', availability_status='Monitor'),
                candidate(102, 'Second Available'),
            )
        ).to_dict()

        inventory = payload['metadata']['inventory_visibility']
        available_members = inventory['availability_inventory']['members_by_status']['Available']
        low_workload_members = inventory['workload_inventory']['members_by_workload']['low']

        assert [member['pitcher_id'] for member in available_members] == [100, 102]
        assert [member['pitcher_id'] for member in low_workload_members] == [
            100,
            101,
            102,
        ]
        for member in low_workload_members:
            assert member['inventory_membership']['basis'] == 'source_evidence_category_match'
            assert 'section' in member['inventory_membership']
            assert 'category' in member['inventory_membership']

        keys = payload_keys(payload)
        assert FORBIDDEN_OUTPUT_KEYS.isdisjoint(keys)
        assert 'ranked_candidates' not in keys
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False

    def test_inventory_preserves_trust_freshness_refusal_explanation_and_limitations(self):
        payload = assemble_v2_context(
            (
                candidate(
                    42,
                    'Stale Arm',
                    availability_status='Monitor',
                    confidence='low',
                    data_state='stale',
                    reasons=('Stale workload data must not be treated as current availability.',),
                    limitations=('Stale workload data limits current availability.',),
                ),
            ),
            generated_at='2026-06-02T12:00:00Z',
        ).to_dict()

        inventory = payload['metadata']['inventory_visibility']
        trust = inventory['trust_metadata']
        freshness = inventory['freshness_inventory']
        refusal = inventory['refusal_inventory']
        explanations = inventory['explanation_inventory']
        limitations = inventory['limitation_inventory']

        assert trust['confidence'] == 'low'
        assert trust['data_state'] == 'stale'
        assert trust['freshness']['state'] == 'stale'
        assert trust['failed_closed'] is True
        assert freshness['stale_count'] == 1
        assert refusal['refused_count'] == 1
        assert refusal['category_counts']['freshness_refusal'] == 1
        assert any(
            item['reason'] == 'data_state_stale'
            for item in refusal['context_refusal_reasons']
        )
        assert explanations['source_reason_messages'] == [
            'Stale workload data must not be treated as current availability.'
        ]
        assert limitations['source_limitations'] == [
            'Stale workload data limits current availability.'
        ]
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False

    def test_missing_evidence_fails_closed_with_zeroed_inventory(self):
        payload = assemble_v2_context(()).to_dict()
        inventory = payload['metadata']['inventory_visibility']
        trust = inventory['trust_metadata']

        assert payload['metadata']['failed_closed'] is True
        assert inventory['total_inventory_count'] == 0
        assert inventory['availability_inventory']['available_count'] == 0
        assert inventory['refusal_inventory']['context_refusal_reason_count'] >= 1
        assert inventory['freshness_inventory']['freshness']['missing_data_warning']
        assert trust['failed_closed'] is True
        assert trust['confidence'] == 'unknown'
        assert trust['data_state'] == 'missing'
        assert payload['candidate_groups'] == []
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False

    def test_unsafe_ranking_or_selection_source_fields_fail_closed(self):
        payload = assemble_v2_context(
            (
                {
                    'pitcher_id': 42,
                    'pitcher_name': 'Unsafe Arm',
                    'availability': {
                        'availability_status': 'Available',
                        'confidence': 'high',
                        'data_state': 'fresh',
                    },
                    'selected_pitcher_id': 42,
                },
            )
        ).to_dict()
        inventory = payload['metadata']['inventory_visibility']

        assert payload['metadata']['failed_closed'] is True
        assert payload['metadata']['unsafe_input_error_count'] == 1
        assert inventory['total_inventory_count'] == 0
        assert inventory['trust_metadata']['failed_closed'] is True
        assert payload['candidate_groups'] == []
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False

    def test_v1_recommendation_behavior_remains_unchanged(self):
        result = RecommendationEngine().recommend(candidate=(candidate(42, 'Available Arm')))
        payload = result.to_dict()

        assert result.is_refusal is False
        assert result.has_recommendation is True
        assert payload['metadata']['ranking_applied'] is False
        assert payload['metadata']['selection_made'] is False
        assert payload['metadata']['policy'] == 'recommendation_engine_v1'
