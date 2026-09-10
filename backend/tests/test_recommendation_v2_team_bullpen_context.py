from recommendation import (
    RecommendationCandidate,
    RecommendationEngine,
    TEAM_BULLPEN_CONTEXT_SECTIONS,
    V2_TEAM_BULLPEN_CONTEXT_PHASE,
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


class TestRecommendationEngineV2TeamBullpenContext:
    def test_team_context_summarizes_team_bullpen_patterns(self):
        payload = assemble_v2_context(
            (
                candidate(
                    42,
                    'Available Arm',
                    metadata={'high_leverage_evidence': True},
                ),
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

        summary = payload['metadata']['team_bullpen_context_summary']
        team_context_summary = payload['team_context']['team_summary']

        assert summary == team_context_summary
        assert summary['phase'] == V2_TEAM_BULLPEN_CONTEXT_PHASE
        assert summary['sections'] == list(TEAM_BULLPEN_CONTEXT_SECTIONS)
        assert summary['team_bullpen_status'] == 'stress_visible'
        assert summary['total_pitcher_count'] == 5
        assert summary['availability_distribution']['Available'] == 1
        assert summary['availability_distribution']['Monitor'] == 1
        assert summary['availability_distribution']['Limited'] == 1
        assert summary['availability_distribution']['Avoid'] == 1
        assert summary['availability_distribution']['Unavailable'] == 1
        assert summary['eligibility_distribution']['evidence_complete'] == 1
        assert summary['eligibility_distribution']['cautionary_evidence'] == 3
        assert summary['eligibility_distribution']['refused_or_degraded_evidence'] == 1
        assert summary['refusal_distribution']['no_refusal'] == 4
        assert summary['refusal_distribution']['availability_refusal'] == 1
        assert summary['freshness_distribution']['fresh'] == 5
        assert summary['data_state_distribution']['fresh'] == 5
        assert summary['readiness_context']['available_or_monitor_count'] == 2
        assert summary['readiness_context']['limited_or_avoid_count'] == 2
        assert summary['readiness_context']['unavailable_or_unknown_count'] == 1
        assert summary['workload_distribution']['low'] == 1
        assert summary['workload_distribution']['moderate'] == 2
        assert summary['workload_distribution']['elevated'] == 1
        assert summary['workload_distribution']['unknown'] == 1
        assert summary['workload_context']['missing_workload_input_count'] == 1
        assert summary['leverage_context']['available_high_leverage_evidence_count'] == 1
        assert summary['ranking_applied'] is False
        assert summary['selection_made'] is False
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False
        assert v2_governance_errors(payload) == []

    def test_team_context_preserves_input_order_without_ranked_lists(self):
        payload = assemble_v2_context(
            (
                candidate(100, 'First Available'),
                candidate(101, 'Monitor Arm', availability_status='Monitor'),
                candidate(102, 'Second Available'),
            )
        ).to_dict()

        summary = payload['metadata']['team_bullpen_context_summary']
        member_reference = summary['member_reference']

        assert [member['pitcher_id'] for member in member_reference] == [
            100,
            101,
            102,
        ]
        for member in member_reference:
            assert member['context_membership']['basis'] == 'source_input_sequence'
            assert (
                member['context_membership']['sequence_policy']
                == 'input_order_preserved_not_preference'
            )

        keys = payload_keys(payload)
        assert FORBIDDEN_OUTPUT_KEYS.isdisjoint(keys)
        assert 'ranked_candidates' not in keys
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False

    def test_team_context_preserves_trust_freshness_refusal_explanations_and_limits(self):
        payload = assemble_v2_context(
            (
                candidate(
                    42,
                    'Stale Arm',
                    availability_status='Monitor',
                    confidence='low',
                    data_state='stale',
                    reasons=(
                        'Stale workload data must not be treated as current availability.',
                    ),
                    limitations=('Stale workload data limits current availability.',),
                ),
            ),
            generated_at='2026-06-02T12:00:00Z',
        ).to_dict()

        summary = payload['metadata']['team_bullpen_context_summary']
        trust = summary['trust_summary']
        refusal = summary['refusal_context']
        explanations = summary['explanation_summary']
        limitations = summary['limitation_summary']

        assert summary['team_bullpen_status'] == 'degraded_evidence'
        assert trust['confidence'] == 'low'
        assert trust['data_state'] == 'stale'
        assert trust['freshness']['state'] == 'stale'
        assert trust['failed_closed'] is True
        assert summary['freshness_distribution']['stale'] == 1
        assert summary['refusal_distribution']['freshness_refusal'] == 1
        assert refusal['context_refusal_reason_count'] >= 1
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

    def test_missing_evidence_fails_closed_with_empty_team_context(self):
        payload = assemble_v2_context(()).to_dict()
        summary = payload['metadata']['team_bullpen_context_summary']

        assert payload['metadata']['failed_closed'] is True
        assert summary['failed_closed'] is True
        assert summary['team_bullpen_status'] == 'missing_evidence'
        assert summary['total_pitcher_count'] == 0
        assert summary['member_reference'] == []
        assert summary['trust_summary']['failed_closed'] is True
        assert summary['trust_summary']['confidence'] == 'unknown'
        assert summary['trust_summary']['data_state'] == 'missing'
        assert summary['refusal_context']['context_refusal_reason_count'] >= 1
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
        summary = payload['metadata']['team_bullpen_context_summary']

        assert payload['metadata']['failed_closed'] is True
        assert payload['metadata']['unsafe_input_error_count'] == 1
        assert summary['failed_closed'] is True
        assert summary['total_pitcher_count'] == 0
        assert summary['team_bullpen_status'] == 'missing_evidence'
        assert summary == payload['team_context']['team_summary']
        assert payload['candidate_groups'] == []
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False

    def test_unsafe_ranking_source_fields_fail_closed(self):
        payload = assemble_v2_context(
            (
                {
                    'pitcher_id': 43,
                    'pitcher_name': 'Ranked Arm',
                    'availability': {
                        'availability_status': 'Available',
                        'confidence': 'high',
                        'data_state': 'fresh',
                    },
                    'top_candidate': True,
                },
            )
        ).to_dict()
        summary = payload['metadata']['team_bullpen_context_summary']

        assert payload['metadata']['failed_closed'] is True
        assert payload['metadata']['unsafe_input_error_count'] == 1
        assert summary['failed_closed'] is True
        assert summary['total_pitcher_count'] == 0
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
