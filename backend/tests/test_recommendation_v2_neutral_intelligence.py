from recommendation import (
    NEUTRAL_INTELLIGENCE_DIMENSIONS,
    RecommendationCandidate,
    RecommendationEngine,
    V2_NEUTRAL_INTELLIGENCE_PHASE,
    assemble_v2_context,
    v2_governance_errors,
)


FORBIDDEN_OUTPUT_KEYS = {
    'rank',
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


class TestRecommendationEngineV2NeutralIntelligence:
    def test_neutral_intelligence_summarizes_bullpen_wide_categories(self):
        assembly = assemble_v2_context(
            (
                candidate(42, 'Available Arm'),
                candidate(
                    43,
                    'Monitor Arm',
                    availability_status='Monitor',
                    confidence='medium',
                    inputs={'fatigue_score': 45.0, 'pitches_yesterday': 18},
                ),
                candidate(
                    44,
                    'Unavailable Arm',
                    availability_status='Unavailable',
                    inputs={},
                ),
                candidate(
                    45,
                    'Stale Arm',
                    availability_status='Limited',
                    confidence='low',
                    data_state='stale',
                    inputs={'fatigue_score': 72.0, 'pitches_yesterday': 40},
                ),
            ),
            generated_at='2026-06-02T12:00:00Z',
        )

        payload = assembly.to_dict()
        neutral = payload['metadata']['neutral_intelligence']
        readiness = payload['bullpen_state']['readiness']
        workload = payload['team_context']['workload_distribution']

        assert neutral['phase'] == V2_NEUTRAL_INTELLIGENCE_PHASE
        assert neutral['dimensions'] == list(NEUTRAL_INTELLIGENCE_DIMENSIONS)
        assert neutral['eligibility_distribution']['evidence_complete'] == 1
        assert neutral['eligibility_distribution']['cautionary_evidence'] == 1
        assert neutral['eligibility_distribution']['refused_or_degraded_evidence'] == 2
        assert neutral['refusal_distribution']['no_refusal'] == 2
        assert neutral['refusal_distribution']['availability_refusal'] == 1
        assert neutral['refusal_distribution']['freshness_refusal'] == 1
        assert neutral['freshness_distribution']['fresh'] == 3
        assert neutral['freshness_distribution']['stale'] == 1
        assert neutral['readiness_distribution']['Available'] == 1
        assert neutral['readiness_distribution']['Monitor'] == 1
        assert neutral['workload_distribution']['low'] == 1
        assert neutral['workload_distribution']['moderate'] == 1
        assert neutral['workload_distribution']['elevated'] == 1
        assert neutral['workload_distribution']['unknown'] == 1
        assert neutral['grouping_dimension_counts']['eligibility'] > 0
        assert neutral['grouping_dimension_counts']['refusal'] > 0
        assert readiness['eligibility_category_counts'] == neutral['eligibility_distribution']
        assert readiness['refusal_category_counts'] == neutral['refusal_distribution']
        assert workload['workload_category_counts'] == neutral['workload_distribution']
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False
        assert v2_governance_errors(payload) == []

    def test_neutral_groups_preserve_input_order_without_ranked_lists(self):
        assembly = assemble_v2_context(
            (
                candidate(100, 'First Available'),
                candidate(101, 'Monitor Arm', availability_status='Monitor'),
                candidate(102, 'Second Available'),
            )
        )

        payload = assembly.to_dict()
        groups = {group['group_id']: group for group in payload['candidate_groups']}
        group_ids = [group['group_id'] for group in payload['candidate_groups']]

        assert group_ids[:2] == ['availability_available', 'availability_monitor']
        assert [item['pitcher_id'] for item in groups['availability_available']['candidates']] == [
            100,
            102,
        ]
        assert [item['pitcher_id'] for item in groups['eligibility_evidence_complete']['candidates']] == [
            100,
            102,
        ]
        assert [item['pitcher_id'] for item in groups['readiness_available']['candidates']] == [
            100,
            102,
        ]
        assert [item['pitcher_id'] for item in groups['workload_low']['candidates']] == [
            100,
            101,
            102,
        ]
        for group in payload['candidate_groups']:
            assert group['neutral_sequence_basis'] == 'input_sequence_preserved'
            assert group['metadata']['ordering_policy'] == (
                'input_order_preserved_not_preference'
            )
            assert group['metadata']['category_ordering_policy'] == (
                'documented_static_taxonomy_not_preference'
            )
            assert group['ranking_applied'] is False
            assert group['selection_made'] is False

        keys = payload_keys(payload)
        assert FORBIDDEN_OUTPUT_KEYS.isdisjoint(keys)
        assert 'ranked_candidates' not in keys
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False

    def test_trust_freshness_refusal_and_explanation_metadata_remain_attached(self):
        assembly = assemble_v2_context(
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
        )

        payload = assembly.to_dict()
        context = payload['recommendation_context']
        groups = {group['group_id']: group for group in payload['candidate_groups']}
        stale_candidate = groups['freshness_stale']['candidates'][0]

        assert context['confidence'] == 'low'
        assert context['freshness']['state'] == 'stale'
        assert context['freshness']['stale_warning'] == 'Some source evidence is stale.'
        assert any(
            refusal['reason'] == 'data_state_stale'
            for refusal in context['refusal_reasons']
        )
        assert stale_candidate['explanation_support']['source_reason_count'] == 1
        assert stale_candidate['explanation_support']['source_limitation_count'] == 1
        assert groups['refusal_freshness_refusal']['candidate_count'] == 1
        assert payload['metadata']['failed_closed'] is True
        assert payload['metadata']['neutral_intelligence']['failed_closed'] is True
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False

    def test_missing_evidence_fails_closed_with_neutral_metadata(self):
        payload = assemble_v2_context(()).to_dict()
        neutral = payload['metadata']['neutral_intelligence']
        context = payload['recommendation_context']

        assert payload['metadata']['failed_closed'] is True
        assert neutral['failed_closed'] is True
        assert neutral['candidate_group_count'] == 0
        assert neutral['eligibility_distribution']['evidence_complete'] == 0
        assert payload['candidate_groups'] == []
        assert context['freshness']['missing_data_warning']
        assert any(
            refusal['reason'] == 'missing_inputs'
            for refusal in context['refusal_reasons']
        )
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False

    def test_unsafe_selection_source_fields_fail_closed_without_groups(self):
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
        neutral = payload['metadata']['neutral_intelligence']

        assert payload['metadata']['failed_closed'] is True
        assert payload['candidate_groups'] == []
        assert neutral['failed_closed'] is True
        assert neutral['candidate_group_count'] == 0
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
