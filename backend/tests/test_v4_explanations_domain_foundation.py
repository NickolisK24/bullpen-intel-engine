import pytest

from explanations import (
    ADVICE_SCOPE,
    ALLOWED_EXPLANATION_SCOPES,
    ALLOWED_LIMITATION_TYPES,
    ALLOWED_REASON_CODES,
    ALLOWED_SUBJECT_TYPES,
    CAPABILITY,
    CONTRACT,
    CONTRACT_VERSION,
    DECISION_SCOPE,
    V4Confidence,
    V4EvidenceItem,
    V4Explanation,
    V4FreshnessReference,
    V4GovernancePayload,
    V4Limitation,
    V4Reason,
    V4TrustReference,
    governance_payload_errors,
    require_governance_payload_safe,
    validate_explanation_scope,
    validate_limitation_type,
    validate_reason_code,
    validate_subject_type,
    v4_governance_errors,
)


def representative_explanation():
    limitation = V4Limitation(
        limitation_type='insufficient_context',
        severity='informational',
        summary='Public data does not include warm-up activity or manager intent.',
        affected_scopes=('availability_state',),
    )
    evidence = V4EvidenceItem(
        evidence_id='recent_usage_3d',
        evidence_type='workload_metric',
        label='Recent usage',
        value=42,
        unit='pitches',
        source='mlb_stats_api_game_logs',
        freshness=V4FreshnessReference(
            status='current',
            data_through='2026-06-03',
            last_sync_at='2026-06-03T12:00:00Z',
        ),
        trust_status='trusted',
        impact='supports_monitor_state',
        limitation=limitation,
    )
    return V4Explanation(
        explanation_id='availability_state:pitcher:42:current',
        scope='availability_state',
        subject_type='pitcher',
        subject_id='42',
        state_explained='Monitor',
        summary='Availability is Monitor because recent workload evidence is elevated.',
        primary_reasons=(
            V4Reason.from_code('AVAILABILITY_MONITOR_THRESHOLD_MET'),
            V4Reason.from_code('WORKLOAD_RECENT_USAGE_ELEVATED'),
        ),
        supporting_evidence=(evidence,),
        limitations=(limitation,),
        freshness=V4FreshnessReference(
            status='current',
            data_through='2026-06-03',
            summary='Freshness is current for the explained state.',
        ),
        trust=V4TrustReference(
            status='trusted',
            source='certified_baseballos_surface',
            contract='availability_engine_v1',
            certification_status='certified',
            summary='Trust metadata is satisfied for this explanation.',
        ),
        confidence=V4Confidence(
            level='medium',
            summary='Confidence is limited to public workload evidence.',
        ),
        generated_at='2026-06-03T12:00:00Z',
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


class TestV4ExplanationsDomainFoundation:
    def test_supported_scope_subject_reason_and_limitation_vocabularies(self):
        assert ALLOWED_EXPLANATION_SCOPES == {
            'availability_state',
            'workload_state',
            'readiness_state',
            'risk_distribution',
            'freshness_state',
            'trust_state',
            'coverage_state',
        }
        assert ALLOWED_SUBJECT_TYPES == {
            'pitcher',
            'team',
            'bullpen',
            'distribution',
            'system',
        }
        assert {
            'WORKLOAD_RECENT_USAGE_ELEVATED',
            'FRESHNESS_STALE_SOURCE',
            'COVERAGE_PARTIAL',
            'TRUST_LIMITED',
            'AVAILABILITY_MONITOR_THRESHOLD_MET',
            'READINESS_DEGRADED_BY_LIMITATIONS',
        }.issubset(ALLOWED_REASON_CODES)
        assert {
            'missing_data',
            'stale_data',
            'partial_coverage',
            'uncertified_source',
            'limited_confidence',
            'insufficient_context',
        }.issubset(ALLOWED_LIMITATION_TYPES)

    def test_vocabulary_validators_reject_unsupported_values(self):
        assert validate_explanation_scope('availability_state') == 'availability_state'
        assert validate_subject_type('bullpen') == 'bullpen'
        assert validate_reason_code('TRUST_LIMITED') == 'TRUST_LIMITED'
        assert validate_limitation_type('stale_data') == 'stale_data'

        with pytest.raises(ValueError, match='scope uses unsupported vocabulary'):
            validate_explanation_scope('recommendation_state')
        with pytest.raises(ValueError, match='subject_type uses unsupported vocabulary'):
            validate_subject_type('manager_intent')
        with pytest.raises(ValueError, match='reason_code uses unsupported vocabulary'):
            validate_reason_code('BEST_ARM_AVAILABLE')
        with pytest.raises(ValueError, match='limitation_type uses unsupported vocabulary'):
            validate_limitation_type('private_clubhouse_context')

    def test_governance_payload_defaults_preserve_required_false_flags(self):
        governance = V4GovernancePayload()
        payload = governance.to_dict()

        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False
        assert payload['recommendation_made'] is False
        assert payload['prediction_made'] is False
        assert payload['decision_scope'] == 'explanation_only'
        assert payload['advice_scope'] == 'none'
        assert DECISION_SCOPE == 'explanation_only'
        assert ADVICE_SCOPE == 'none'
        assert governance_payload_errors(payload) == []

    @pytest.mark.parametrize(
        'field_name',
        (
            'ranking_applied',
            'selection_made',
            'recommendation_made',
            'prediction_made',
        ),
    )
    def test_governance_payload_rejects_unsafe_true_values(self, field_name):
        kwargs = {field_name: True}

        with pytest.raises(ValueError, match=f'{field_name} must be false'):
            V4GovernancePayload(**kwargs)

    def test_governance_payload_rejects_decision_or_advice_scope_changes(self):
        with pytest.raises(ValueError, match='decision_scope must be explanation_only'):
            V4GovernancePayload(decision_scope='decision_support')

        with pytest.raises(ValueError, match='advice_scope must be none'):
            V4GovernancePayload(advice_scope='pitcher_advice')

    def test_missing_governance_fields_are_fail_closed_validation_errors(self):
        errors = governance_payload_errors(
            {
                'ranking_applied': False,
                'selection_made': False,
            }
        )

        assert 'governance is missing required field recommendation_made.' in errors
        assert 'governance is missing required field prediction_made.' in errors
        assert 'governance is missing required field decision_scope.' in errors
        assert 'governance is missing required field advice_scope.' in errors

        with pytest.raises(ValueError, match='recommendation_made'):
            require_governance_payload_safe(
                {
                    'ranking_applied': False,
                    'selection_made': False,
                }
            )

    def test_evidence_item_creation_and_serialization_shape(self):
        limitation = V4Limitation(
            limitation_type='stale_data',
            severity='degrades_confidence',
            summary='Source freshness is stale.',
            affected_scopes=('freshness_state',),
        )
        evidence = V4EvidenceItem(
            evidence_id='source_freshness',
            evidence_type='freshness_metadata',
            label='Source freshness',
            value='stale',
            unit='status',
            source='sync_metadata',
            freshness=V4FreshnessReference(status='stale', data_through='2026-06-01'),
            trust_status='limited',
            impact='explains_freshness_limitation',
            limitation=limitation,
        )
        payload = evidence.to_dict()

        assert list(payload.keys()) == [
            'evidence_id',
            'evidence_type',
            'label',
            'value',
            'unit',
            'source',
            'freshness',
            'trust_status',
            'impact',
            'limitation',
        ]
        assert payload['evidence_id'] == 'source_freshness'
        assert payload['freshness']['status'] == 'stale'
        assert payload['trust_status'] == 'limited'
        assert payload['limitation']['limitation_type'] == 'stale_data'
        assert v4_governance_errors(payload) == []

    def test_explanation_object_creation_and_serialization_shape(self):
        explanation = representative_explanation()
        payload = explanation.to_dict()

        assert list(payload.keys()) == [
            'capability',
            'contract',
            'contract_version',
            'explanation_id',
            'scope',
            'subject_type',
            'subject_id',
            'state_explained',
            'summary',
            'primary_reasons',
            'supporting_evidence',
            'limitations',
            'freshness',
            'trust',
            'confidence',
            'governance',
            'generated_at',
        ]
        assert payload['capability'] == CAPABILITY
        assert payload['contract'] == CONTRACT
        assert payload['contract_version'] == CONTRACT_VERSION
        assert payload['scope'] == 'availability_state'
        assert payload['subject_type'] == 'pitcher'
        assert payload['primary_reasons'][0]['code'] == 'AVAILABILITY_MONITOR_THRESHOLD_MET'
        assert payload['supporting_evidence'][0]['evidence_id'] == 'recent_usage_3d'
        assert payload['limitations'][0]['limitation_type'] == 'insufficient_context'
        assert payload['governance']['ranking_applied'] is False
        assert payload['governance']['selection_made'] is False
        assert payload['governance']['recommendation_made'] is False
        assert payload['governance']['prediction_made'] is False
        assert payload['governance']['decision_scope'] == 'explanation_only'
        assert payload['governance']['advice_scope'] == 'none'
        assert v4_governance_errors(payload) == []

    def test_explanation_rejects_unsupported_scope_subject_reason_and_limitation(self):
        with pytest.raises(ValueError, match='scope uses unsupported vocabulary'):
            V4Explanation(
                explanation_id='invalid',
                scope='selection_state',
                subject_type='pitcher',
                subject_id='42',
                state_explained='Monitor',
                summary='Invalid explanation.',
            )

        with pytest.raises(ValueError, match='subject_type uses unsupported vocabulary'):
            V4Explanation(
                explanation_id='invalid',
                scope='availability_state',
                subject_type='matchup',
                subject_id='42',
                state_explained='Monitor',
                summary='Invalid explanation.',
            )

        with pytest.raises(ValueError, match='reason_code uses unsupported vocabulary'):
            V4Reason.from_code('RECOMMEND_THIS_ARM')

        with pytest.raises(ValueError, match='limitation_type uses unsupported vocabulary'):
            V4Limitation(
                limitation_type='best_arm_unavailable',
                summary='Invalid limitation.',
            )

    def test_serialization_is_deterministic_for_identical_inputs(self):
        first = representative_explanation().to_dict()
        second = representative_explanation().to_dict()

        assert first == second
        assert list(first.keys()) == list(second.keys())
        assert first['primary_reasons'] == second['primary_reasons']
        assert first['supporting_evidence'] == second['supporting_evidence']

    def test_prohibited_behavior_fields_remain_absent_or_false(self):
        payload = representative_explanation().to_dict()
        keys = payload_keys(payload)

        assert payload['governance']['ranking_applied'] is False
        assert payload['governance']['selection_made'] is False
        assert payload['governance']['recommendation_made'] is False
        assert payload['governance']['prediction_made'] is False
        assert 'rank' not in keys
        assert 'selected_pitcher' not in keys
        assert 'recommended_pitcher' not in keys
        assert 'preferred_pitcher' not in keys
        assert 'best_arm' not in keys
        assert 'matchup_advice' not in keys
        assert 'prediction' not in keys
        assert 'hidden_priority_ordering' not in keys

    def test_governance_scan_detects_forbidden_nested_fields(self):
        payload = representative_explanation().to_dict()
        payload['supporting_evidence'][0]['recommended_pitcher'] = 'Pitcher A'

        assert v4_governance_errors(payload) == [
            'payload.supporting_evidence[0].recommended_pitcher uses a forbidden V4 field name.'
        ]
