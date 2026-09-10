from recommendation import (
    RecommendationCandidate,
    RecommendationEngine,
    V2_REQUIRED_TRUST_METADATA_FIELDS,
    V2_TRUST_METADATA_INTEGRATION_PHASE,
    assemble_v2_context,
    v2_governance_errors,
    v2_trust_metadata_errors,
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
    pitcher_id=42,
    pitcher_name='Available Arm',
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


def raw_candidate(**availability):
    return {
        'pitcher_id': 42,
        'pitcher_name': 'Raw Arm',
        'team_id': 7,
        'team_name': 'Example Club',
        'availability': {
            **availability,
            'inputs': dict(DEFAULT_INPUTS),
            'data_through': '2026-06-01',
            'last_successful_sync': '2026-06-02T10:00:00Z',
            'latest_sync_status': 'success',
        },
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


def trust_source(layer):
    return layer.get('trust_metadata') or layer.get('trust_summary') or layer


def assert_valid_trust_metadata(layer):
    trust = trust_source(layer)
    assert V2_REQUIRED_TRUST_METADATA_FIELDS.issubset(trust.keys())
    assert trust['ranking_applied'] is False
    assert trust['selection_made'] is False
    assert isinstance(trust['freshness'], dict)
    assert isinstance(trust['limitations'], list)
    assert isinstance(trust['explanations'], list)
    assert isinstance(trust['refusal_reasons'], list)
    assert trust['source_evidence_state']
    assert trust['governance_state']
    assert v2_trust_metadata_errors(layer) == []


class TestRecommendationEngineV2TrustMetadataIntegration:
    def test_valid_trust_metadata_propagates_across_internal_layers(self):
        payload = assemble_v2_context(
            (
                candidate(
                    reasons=('Current availability evidence is complete.',),
                    limitations=('Public workload data only.',),
                ),
            ),
            generated_at='2026-06-02T12:00:00Z',
        ).to_dict()

        layers = [
            payload,
            payload['recommendation_context'],
            payload['bullpen_state'],
            payload['team_context'],
            payload['candidate_groups'][0],
            payload['metadata']['neutral_intelligence'],
            payload['metadata']['inventory_visibility'],
            payload['metadata']['team_bullpen_context_summary'],
        ]

        for layer in layers:
            assert_valid_trust_metadata(layer)

        assert (
            payload['metadata']['trust_metadata']['phase']
            == V2_TRUST_METADATA_INTEGRATION_PHASE
        )
        assert payload['trust_metadata']['confidence'] == 'high'
        assert payload['trust_metadata']['data_state'] == 'fresh'
        assert payload['trust_metadata']['source_evidence_state'] == 'represented'
        assert payload['trust_metadata']['governance_state'] == 'compliant'
        assert payload['metadata']['failed_closed'] is False
        assert v2_governance_errors(payload) == []

    def test_missing_confidence_metadata_fails_closed(self):
        payload = assemble_v2_context(
            (
                raw_candidate(
                    availability_status='Available',
                    data_state='fresh',
                    reasons=[],
                    limitations=[],
                ),
            )
        ).to_dict()
        context = payload['recommendation_context']

        assert payload['metadata']['failed_closed'] is True
        assert context['source_evidence_state'] == 'trust_metadata_incomplete'
        assert context['governance_state'] == 'failed_closed'
        assert any(
            refusal['reason'] == 'missing_confidence_metadata'
            for refusal in context['refusal_reasons']
        )
        assert any('candidate[0].confidence' in item for item in context['trust_validation_errors'])
        assert_valid_trust_metadata(payload)
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False

    def test_missing_freshness_and_data_state_metadata_fail_closed(self):
        payload = assemble_v2_context(
            (
                raw_candidate(
                    availability_status='Available',
                    confidence='high',
                    reasons=[],
                    limitations=[],
                ),
            )
        ).to_dict()
        context = payload['recommendation_context']
        reasons = {refusal['reason'] for refusal in context['refusal_reasons']}

        assert payload['metadata']['failed_closed'] is True
        assert 'missing_freshness_metadata' in reasons
        assert 'missing_data_state_metadata' in reasons
        assert context['freshness']['missing_data_warning']
        assert context['source_evidence_state'] == 'trust_metadata_incomplete'
        assert_valid_trust_metadata(payload)

    def test_missing_limitation_and_explanation_metadata_fail_closed(self):
        payload = assemble_v2_context(
            (
                raw_candidate(
                    availability_status='Available',
                    confidence='high',
                    data_state='fresh',
                ),
            )
        ).to_dict()
        context = payload['recommendation_context']
        reasons = {refusal['reason'] for refusal in context['refusal_reasons']}

        assert payload['metadata']['failed_closed'] is True
        assert 'missing_limitations_metadata' in reasons
        assert 'missing_explanations_metadata' in reasons
        assert any(
            limitation['limitation_id'] == 'missing_limitations_metadata'
            for limitation in context['limitations']
        )
        assert any(
            explanation['code'] == 'trust_metadata_validation_failed'
            for explanation in context['explanations']
        )
        assert_valid_trust_metadata(payload)

    def test_missing_refusal_state_metadata_fails_closed(self):
        payload = assemble_v2_context(
            (
                raw_candidate(
                    confidence='high',
                    data_state='fresh',
                    reasons=[],
                    limitations=[],
                ),
            )
        ).to_dict()
        context = payload['recommendation_context']

        assert payload['metadata']['failed_closed'] is True
        assert any(
            refusal['reason'] == 'missing_refusal_metadata'
            for refusal in context['refusal_reasons']
        )
        assert context['source_evidence_state'] == 'trust_metadata_incomplete'
        assert_valid_trust_metadata(payload)

    def test_unsafe_ranking_and_selection_source_fields_fail_closed(self):
        ranked_payload = assemble_v2_context(
            (
                {
                    'pitcher_id': 42,
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
        selected_payload = assemble_v2_context(
            (
                {
                    'pitcher_id': 43,
                    'pitcher_name': 'Selected Arm',
                    'availability': {
                        'availability_status': 'Available',
                        'confidence': 'high',
                        'data_state': 'fresh',
                    },
                    'selected_candidate_id': 43,
                },
            )
        ).to_dict()

        for payload in (ranked_payload, selected_payload):
            assert payload['metadata']['failed_closed'] is True
            assert payload['metadata']['unsafe_input_error_count'] == 1
            assert payload['candidate_groups'] == []
            assert any(
                refusal['reason'] == 'unsupported_fields'
                for refusal in payload['recommendation_context']['refusal_reasons']
            )
            assert_valid_trust_metadata(payload)
            assert payload['ranking_applied'] is False
            assert payload['selection_made'] is False

    def test_serialization_is_deterministic_and_contains_no_forbidden_outputs(self):
        source_candidates = (
            candidate(42, 'Available Arm'),
            candidate(43, 'Monitor Arm', availability_status='Monitor', confidence='medium'),
        )

        first_payload = assemble_v2_context(source_candidates).to_dict()
        second_payload = assemble_v2_context(source_candidates).to_dict()

        assert first_payload == second_payload
        keys = payload_keys(first_payload)
        assert FORBIDDEN_OUTPUT_KEYS.isdisjoint(keys)
        assert 'ranked_candidates' not in keys
        assert_valid_trust_metadata(first_payload)

    def test_v1_recommendation_behavior_remains_unchanged(self):
        result = RecommendationEngine().recommend(candidate=candidate())
        payload = result.to_dict()

        assert result.is_refusal is False
        assert result.has_recommendation is True
        assert payload['metadata']['ranking_applied'] is False
        assert payload['metadata']['selection_made'] is False
        assert payload['metadata']['policy'] == 'recommendation_engine_v1'
