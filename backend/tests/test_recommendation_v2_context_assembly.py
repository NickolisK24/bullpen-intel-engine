from recommendation import (
    RecommendationCandidate,
    RecommendationEngine,
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
            'inputs': inputs or {
                'fatigue_score': 20.0,
                'pitches_yesterday': 0,
                'latest_game_date': '2026-06-01',
            },
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


class TestRecommendationEngineV2ContextAssembly:
    def test_assembles_bullpen_state_from_existing_availability_evidence(self):
        assembly = assemble_v2_context(
            (
                candidate(42, 'Available Arm'),
                candidate(
                    43,
                    'Monitor Arm',
                    availability_status='Monitor',
                    confidence='medium',
                    inputs={'fatigue_score': 45.0, 'pitches_yesterday': 18},
                    reasons=('Monitor workload evidence.',),
                    limitations=('Monitor requires review.',),
                ),
                candidate(
                    44,
                    'Avoid Arm',
                    availability_status='Avoid',
                    confidence='medium',
                    inputs={'fatigue_score': 72.0, 'pitches_yesterday': 40},
                ),
            ),
            team_id=7,
            team_name='Example Club',
            generated_at='2026-06-02T12:00:00Z',
        )

        payload = assembly.to_dict()
        bullpen_state = payload['bullpen_state']
        team_context = payload['team_context']

        assert payload['metadata']['assembly_phase'] == 'phase_2_backend_context_assembly'
        assert bullpen_state['team_id'] == 7
        assert bullpen_state['bullpen_status'] == 'stress_visible'
        assert bullpen_state['inventory']['total_pitchers'] == 3
        assert bullpen_state['inventory']['availability_status_counts']['Available'] == 1
        assert bullpen_state['inventory']['availability_status_counts']['Monitor'] == 1
        assert bullpen_state['inventory']['availability_status_counts']['Avoid'] == 1
        assert bullpen_state['readiness']['confidence_counts']['medium'] == 2
        assert bullpen_state['readiness']['data_state_counts']['fresh'] == 3
        assert bullpen_state['workload']['fatigue_value_available_count'] == 3
        assert bullpen_state['workload']['recent_pitch_count_available_count'] == 3
        assert bullpen_state['stress']['avoid_or_unavailable_count'] == 1
        assert bullpen_state['stress']['elevated_workload_count'] == 1
        assert team_context['workload_distribution']['fatigue_band_counts']['elevated'] == 1
        assert team_context['readiness_distribution']['availability_status_counts']['Avoid'] == 1
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False
        assert v2_governance_errors(payload) == []

    def test_candidate_groups_are_neutral_and_preserve_input_order_within_groups(self):
        assembly = assemble_v2_context(
            (
                candidate(42, 'First Available'),
                candidate(43, 'Monitor Arm', availability_status='Monitor'),
                candidate(44, 'Second Available'),
            )
        )

        payload = assembly.to_dict()
        groups = {
            group['group_id']: group
            for group in payload['candidate_groups']
        }
        available_group = groups['availability_available']

        assert available_group['neutral_sequence_basis'] == 'input_sequence_preserved'
        assert available_group['metadata']['ordering_policy'] == (
            'input_order_preserved_not_preference'
        )
        assert [item['pitcher_id'] for item in available_group['candidates']] == [42, 44]
        assert available_group['ranking_applied'] is False
        assert available_group['selection_made'] is False
        assert FORBIDDEN_OUTPUT_KEYS.isdisjoint(payload_keys(payload))
        assert 'ranked_candidates' not in payload_keys(payload)

    def test_trust_freshness_limitation_explanation_and_refusal_metadata_propagates(self):
        assembly = assemble_v2_context(
            (
                candidate(
                    42,
                    'Stale Arm',
                    availability_status='Monitor',
                    confidence='low',
                    data_state='stale',
                    inputs={'fatigue_score': 10.0, 'pitches_yesterday': 0},
                    reasons=('Stale workload data must not be treated as current availability.',),
                    limitations=('Stale workload data limits current availability.',),
                ),
            ),
            generated_at='2026-06-02T12:00:00Z',
        )

        payload = assembly.to_dict()
        context = payload['recommendation_context']

        assert context['confidence'] == 'low'
        assert context['data_state'] == 'stale'
        assert context['freshness']['state'] == 'stale'
        assert context['freshness']['stale_warning'] == 'Some source evidence is stale.'
        assert any(
            limitation['limitation_id'].startswith('source_')
            for limitation in context['limitations']
        )
        assert any(
            explanation['code'].startswith('source_')
            for explanation in context['explanations']
        )
        assert any(
            refusal['reason'] == 'data_state_stale'
            for refusal in context['refusal_reasons']
        )
        assert payload['metadata']['failed_closed'] is True
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False

    def test_missing_evidence_fails_closed_without_fabricated_context(self):
        assembly = assemble_v2_context(())
        payload = assembly.to_dict()
        context = payload['recommendation_context']

        assert payload['metadata']['failed_closed'] is True
        assert payload['metadata']['input_candidate_count'] == 0
        assert payload['bullpen_state']['bullpen_status'] == 'unknown'
        assert payload['bullpen_state']['inventory']['total_pitchers'] == 0
        assert context['confidence'] == 'unknown'
        assert context['data_state'] == 'missing'
        assert context['freshness']['missing_data_warning']
        assert any(
            refusal['reason'] == 'missing_inputs'
            for refusal in context['refusal_reasons']
        )
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False

    def test_unsafe_ranking_or_selection_source_fields_fail_closed(self):
        assembly = assemble_v2_context(
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
        )

        payload = assembly.to_dict()
        context = payload['recommendation_context']

        assert payload['metadata']['failed_closed'] is True
        assert payload['metadata']['unsafe_input_error_count'] == 1
        assert payload['candidate_groups'] == []
        assert payload['bullpen_state']['bullpen_status'] == 'refused'
        assert any(
            refusal['reason'] == 'unsupported_fields'
            for refusal in context['refusal_reasons']
        )
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False

    def test_team_context_represents_missing_leverage_evidence_as_limitation(self):
        assembly = assemble_v2_context((candidate(42, 'Available Arm'),))
        payload = assembly.to_dict()
        leverage_inventory = payload['team_context']['leverage_inventory']

        assert leverage_inventory['source_evidence_available'] is False
        assert leverage_inventory['available_high_leverage_evidence_count'] == 0
        assert leverage_inventory['leverage_evidence_limitations'] == [
            'No leverage evidence was supplied to V2 context assembly.'
        ]

    def test_v1_recommendation_behavior_remains_unchanged(self):
        result = RecommendationEngine().recommend(candidate=(
            candidate(42, 'Available Arm')
        ))
        payload = result.to_dict()

        assert result.is_refusal is False
        assert result.has_recommendation is True
        assert payload['metadata']['ranking_applied'] is False
        assert payload['metadata']['selection_made'] is False
        assert payload['metadata']['policy'] == 'recommendation_engine_v1'
