import pytest

from explanations import (
    V4EvidenceItem,
    V4Explanation,
    build_evidence_item,
    build_explanation,
    build_limitation,
    build_numeric_evidence,
    build_percentage_evidence,
    build_reason,
    build_reasons,
    serialize_explanation,
    stable_json_dumps,
    v4_governance_errors,
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


def freshness_payload():
    return {
        'status': 'current',
        'data_through': '2026-06-03',
        'last_sync_at': '2026-06-03T12:00:00Z',
        'source_updated_at': '2026-06-03T11:45:00Z',
        'summary': 'Source freshness is current for controlled builder input.',
    }


def trust_payload():
    return {
        'status': 'trusted',
        'source': 'controlled_phase_5_fixture',
        'contract': 'baseballos.v4.explanation.domain',
        'certification_status': 'internal_only',
        'summary': 'Trust metadata is present for controlled builder input.',
    }


class TestV4ExplanationsDeterministicBuilder:
    def test_minimal_valid_explanation_builder_attaches_governance_defaults(self):
        explanation = build_explanation(
            scope='availability_state',
            subject_type='pitcher',
            subject_id='42',
            state_explained='Monitor',
            summary='Availability state is explained from controlled input.',
        )
        payload = explanation.to_dict()

        assert isinstance(explanation, V4Explanation)
        assert payload['explanation_id'].startswith(
            'explanation:availability_state:pitcher:42:'
        )
        assert payload['scope'] == 'availability_state'
        assert payload['subject_type'] == 'pitcher'
        assert payload['primary_reasons'] == []
        assert payload['supporting_evidence'] == []
        assert payload['limitations'] == []
        assert payload['governance']['ranking_applied'] is False
        assert payload['governance']['selection_made'] is False
        assert payload['governance']['recommendation_made'] is False
        assert payload['governance']['prediction_made'] is False
        assert payload['governance']['decision_scope'] == 'explanation_only'
        assert payload['governance']['advice_scope'] == 'none'
        assert v4_governance_errors(payload) == []

    def test_fully_populated_builder_output_contains_expected_sections(self):
        stale_limitation = build_limitation(
            limitation_type='stale_data',
            severity='degrades_confidence',
            summary='The source evidence is stale in this controlled input.',
            affected_scopes=('freshness_state', 'availability_state'),
        )
        context_limitation = build_limitation(
            limitation_type='insufficient_context',
            summary='Private manager intent is not available.',
            affected_scopes=('availability_state',),
        )
        evidence_items = (
            build_numeric_evidence(
                evidence_type='workload_metric',
                label='Recent pitch count',
                value=42,
                unit='pitches',
                source='controlled_fixture',
                freshness=freshness_payload(),
                trust_status='trusted',
                impact='explains_monitor_state',
                limitation=stale_limitation,
            ),
            build_percentage_evidence(
                label='Coverage confidence',
                value=75,
                source='controlled_fixture',
                freshness=freshness_payload(),
                trust_status='trusted',
                impact='explains_limited_confidence',
            ),
        )

        explanation = build_explanation(
            scope='availability_state',
            subject_type='pitcher',
            subject_id='42',
            state_explained='Monitor',
            summary='Availability is Monitor because controlled evidence is elevated.',
            reason_codes=(
                'AVAILABILITY_MONITOR_THRESHOLD_MET',
                'WORKLOAD_RECENT_USAGE_ELEVATED',
                'FRESHNESS_STALE_SOURCE',
            ),
            supporting_evidence=evidence_items,
            limitations=(stale_limitation, context_limitation),
            freshness=freshness_payload(),
            trust=trust_payload(),
            confidence={
                'level': 'medium',
                'summary': 'Confidence is limited to controlled public evidence.',
            },
            generated_at='2026-06-03T12:00:00Z',
        )
        payload = serialize_explanation(explanation)

        assert len(payload['primary_reasons']) == 3
        assert len(payload['supporting_evidence']) == 2
        assert len(payload['limitations']) == 2
        assert payload['supporting_evidence'][0]['unit'] == 'pitches'
        assert payload['supporting_evidence'][1]['unit'] == 'percent'
        assert payload['freshness']['status'] == 'current'
        assert payload['trust']['status'] == 'trusted'
        assert payload['confidence']['level'] == 'medium'
        assert payload['governance']['ranking_applied'] is False
        assert payload['governance']['selection_made'] is False
        assert payload['governance']['recommendation_made'] is False
        assert payload['governance']['prediction_made'] is False
        assert v4_governance_errors(payload) == []

    def test_multiple_evidence_items_and_limitations_from_mappings(self):
        explanation = build_explanation(
            scope='coverage_state',
            subject_type='bullpen',
            subject_id='team-111',
            state_explained='Partial Coverage',
            summary='Coverage is partial in controlled input.',
            reason_codes=('COVERAGE_PARTIAL',),
            supporting_evidence=(
                {
                    'evidence_type': 'coverage_count',
                    'label': 'Known handedness records',
                    'value': 8,
                    'unit': 'count',
                    'source': 'controlled_fixture',
                    'freshness': freshness_payload(),
                    'trust_status': 'trusted',
                    'impact': 'explains_partial_coverage',
                },
                {
                    'evidence_type': 'coverage_count',
                    'label': 'Unknown handedness records',
                    'value': 2,
                    'unit': 'count',
                    'source': 'controlled_fixture',
                    'freshness': freshness_payload(),
                    'trust_status': 'limited',
                    'impact': 'explains_partial_coverage',
                },
            ),
            limitations=(
                {
                    'limitation_type': 'partial_coverage',
                    'summary': 'Some records are missing handedness evidence.',
                    'affected_scopes': ('coverage_state',),
                },
                {
                    'limitation_type': 'limited_confidence',
                    'summary': 'Confidence is limited by controlled fixture coverage.',
                    'affected_scopes': ('coverage_state',),
                },
            ),
        )
        payload = explanation.to_dict()

        assert len(payload['supporting_evidence']) == 2
        assert len(payload['limitations']) == 2
        assert payload['supporting_evidence'][0]['evidence_id'].startswith(
            'evidence:coverage_count:'
        )
        assert payload['supporting_evidence'][1]['trust_status'] == 'limited'
        assert payload['limitations'][0]['limitation_type'] == 'partial_coverage'

    def test_reason_helper_rejects_invalid_reason_code(self):
        assert build_reason('TRUST_LIMITED').code == 'TRUST_LIMITED'
        assert build_reasons(('TRUST_LIMITED',))[0].code == 'TRUST_LIMITED'

        with pytest.raises(ValueError, match='reason_code uses unsupported vocabulary'):
            build_reason('RECOMMEND_THIS_ARM')

    def test_builder_rejects_invalid_scope_subject_and_limitation(self):
        with pytest.raises(ValueError, match='scope uses unsupported vocabulary'):
            build_explanation(
                scope='selection_state',
                subject_type='pitcher',
                subject_id='42',
                state_explained='Monitor',
                summary='Invalid scope.',
            )

        with pytest.raises(ValueError, match='subject_type uses unsupported vocabulary'):
            build_explanation(
                scope='availability_state',
                subject_type='matchup',
                subject_id='42',
                state_explained='Monitor',
                summary='Invalid subject.',
            )

        with pytest.raises(ValueError, match='limitation_type uses unsupported vocabulary'):
            build_limitation(
                limitation_type='best_arm_hidden',
                summary='Invalid limitation.',
            )

    def test_numeric_and_percentage_evidence_validate_values(self):
        numeric = build_numeric_evidence(
            evidence_type='workload_metric',
            label='Recent pitch count',
            value=42,
            unit='pitches',
        )
        percentage = build_percentage_evidence(
            label='Coverage confidence',
            value=75.5,
        )

        assert isinstance(numeric, V4EvidenceItem)
        assert numeric.value == 42
        assert percentage.unit == 'percent'
        assert percentage.value == 75.5

        with pytest.raises(ValueError, match='numeric evidence value'):
            build_numeric_evidence(
                evidence_type='workload_metric',
                label='Recent pitch count',
                value='42',
                unit='pitches',
            )

        with pytest.raises(ValueError, match='between 0 and 100'):
            build_percentage_evidence(label='Coverage confidence', value=120)

    def test_repeated_builder_calls_produce_equivalent_output_and_ids(self):
        kwargs = {
            'scope': 'readiness_state',
            'subject_type': 'team',
            'subject_id': '111',
            'state_explained': 'Data Limited',
            'summary': 'Readiness is data limited by controlled evidence.',
            'reason_codes': ('READINESS_DEGRADED_BY_LIMITATIONS', 'TRUST_LIMITED'),
            'supporting_evidence': (
                build_evidence_item(
                    evidence_type='trust_metadata',
                    label='Trust status',
                    value='limited',
                    source='controlled_fixture',
                    freshness=freshness_payload(),
                    trust_status='limited',
                    impact='explains_data_limited_state',
                ),
            ),
            'limitations': (
                build_limitation(
                    limitation_type='limited_confidence',
                    summary='Confidence is limited by trust metadata.',
                    affected_scopes=('readiness_state',),
                ),
            ),
            'freshness': freshness_payload(),
            'trust': trust_payload(),
            'confidence': {'level': 'low', 'summary': 'Trust is limited.'},
            'generated_at': '2026-06-03T12:00:00Z',
        }

        first = build_explanation(**kwargs).to_dict()
        second = build_explanation(**kwargs).to_dict()

        assert first == second
        assert first['explanation_id'] == second['explanation_id']
        assert first['supporting_evidence'][0]['evidence_id'] == (
            second['supporting_evidence'][0]['evidence_id']
        )
        assert stable_json_dumps(first) == stable_json_dumps(second)

    def test_explicit_ids_are_preserved_when_supplied(self):
        evidence = build_evidence_item(
            evidence_id='evidence:explicit',
            evidence_type='freshness_metadata',
            label='Freshness state',
            value='current',
        )
        explanation = build_explanation(
            explanation_id='explanation:explicit',
            scope='freshness_state',
            subject_type='system',
            subject_id='sync',
            state_explained='Current',
            summary='Freshness is current in controlled input.',
            supporting_evidence=(evidence,),
        )
        payload = explanation.to_dict()

        assert payload['explanation_id'] == 'explanation:explicit'
        assert payload['supporting_evidence'][0]['evidence_id'] == 'evidence:explicit'

    def test_invalid_input_cannot_produce_explanation_object(self):
        with pytest.raises(ValueError, match='freshness must be'):
            build_explanation(
                scope='freshness_state',
                subject_type='system',
                subject_id='sync',
                state_explained='Current',
                summary='Invalid freshness input.',
                freshness='current',
            )

        with pytest.raises(ValueError, match='confidence must be'):
            build_explanation(
                scope='trust_state',
                subject_type='system',
                subject_id='trust',
                state_explained='Trusted',
                summary='Invalid confidence input.',
                confidence='high',
            )

    def test_serialization_helper_requires_explanation_object(self):
        explanation = build_explanation(
            scope='trust_state',
            subject_type='system',
            subject_id='trust',
            state_explained='Trusted',
            summary='Trust is explained from controlled input.',
        )

        assert serialize_explanation(explanation) == explanation.to_dict()

        with pytest.raises(ValueError, match='explanation must be a V4Explanation'):
            serialize_explanation({'not': 'an explanation'})

    def test_builder_output_contains_no_prohibited_behavior_fields(self):
        payload = build_explanation(
            scope='workload_state',
            subject_type='bullpen',
            subject_id='team-111',
            state_explained='Elevated',
            summary='Workload is elevated by controlled evidence.',
            reason_codes=('WORKLOAD_RECENT_USAGE_ELEVATED',),
            supporting_evidence=(
                build_numeric_evidence(
                    evidence_type='workload_metric',
                    label='Recent pitches',
                    value=88,
                    unit='pitches',
                    impact='explains_elevated_workload',
                ),
            ),
        ).to_dict()
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
        assert v4_governance_errors(payload) == []
