from copy import deepcopy

import pytest

from explanations import (
    build_readiness_explanation,
    serialize_readiness_explanation,
    stable_json_dumps,
    v4_governance_errors,
)
from team_operations import assemble_bullpen_readiness


def valid_trust_metadata(**overrides):
    payload = {
        'confidence': 'high',
        'confidence_reasons': ['fresh_data', 'complete_metadata'],
        'data_state': 'fresh',
        'source_evidence_state': 'represented',
        'governance_state': 'compliant',
        'generated_at': '2026-06-03T12:00:00Z',
        'limitations': [],
        'explanations': [],
        'refusal_reasons': [],
        'trust_validation_errors': [],
        'ranking_applied': False,
        'selection_made': False,
    }
    payload.update(overrides)
    return payload


def valid_freshness_metadata(**overrides):
    payload = {
        'freshness_state': 'current',
        'data_through': '2026-06-03',
        'latest_workload_date': '2026-06-03',
        'last_successful_sync': '2026-06-03T11:30:00Z',
        'latest_sync_status': 'success',
        'latest_fatigue_calculated_at': '2026-06-03T11:45:00Z',
        'generated_at': '2026-06-03T12:00:00Z',
        'stale_warning': None,
        'missing_data_warning': None,
        'limitations': [],
    }
    payload.update(overrides)
    return payload


def team_payload():
    return {
        'team_id': 111,
        'team_name': 'Example Club',
        'team_abbreviation': 'EX',
    }


def stable_pitcher_records():
    return (
        {
            'availability_status': 'available',
            'workload_category': 'low',
            'throwing_hand': 'left',
        },
        {
            'availability_status': 'available',
            'workload_category': 'low',
            'throwing_hand': 'right',
        },
    )


def constrained_pitcher_records():
    return (
        {
            'availability_status': 'available',
            'workload_category': 'low',
            'throwing_hand': 'left',
        },
        {
            'availability_status': 'monitor',
            'workload_category': 'moderate',
            'throwing_hand': 'right',
        },
        {
            'availability_status': 'limited',
            'workload_category': 'low',
            'throwing_hand': 'right',
        },
    )


def stressed_pitcher_records():
    return (
        {
            'availability_status': 'available',
            'workload_category': 'low',
            'throwing_hand': 'left',
        },
        {
            'availability_status': 'unavailable',
            'workload_category': 'elevated',
            'throwing_hand': 'right',
        },
    )


def coverage_limited_pitcher_records():
    return (
        {
            'availability_status': 'available',
            'workload_category': 'low',
            'throwing_hand': 'left',
            'has_current_workload': True,
            'has_availability': True,
        },
        {
            'availability_status': 'unknown',
            'workload_category': 'unknown',
            'throwing_hand': 'unknown',
            'has_current_workload': False,
            'has_availability': False,
        },
    )


def readiness_payload(**overrides):
    args = {
        'team': team_payload(),
        'pitcher_records': stable_pitcher_records(),
        'trust_metadata': valid_trust_metadata(),
        'freshness': valid_freshness_metadata(),
    }
    args.update(overrides)
    return assemble_bullpen_readiness(**args)


def explanation_payload(payload, **kwargs):
    return serialize_readiness_explanation(
        payload,
        generated_at='2026-06-03T12:05:00Z',
        **kwargs,
    )


def reason_codes(payload):
    return {reason['code'] for reason in payload['primary_reasons']}


def evidence_by_type(payload):
    return {
        evidence['evidence_type']: evidence
        for evidence in payload['supporting_evidence']
    }


def limitation_types(payload):
    return {limitation['limitation_type'] for limitation in payload['limitations']}


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


def assert_governance_safe(payload):
    governance = payload['governance']

    assert governance['ranking_applied'] is False
    assert governance['selection_made'] is False
    assert governance['recommendation_made'] is False
    assert governance['prediction_made'] is False
    assert governance['decision_scope'] == 'explanation_only'
    assert governance['advice_scope'] == 'none'
    assert v4_governance_errors(payload) == []


class TestV4TeamOperationsReadinessExplanationIntegration:
    def test_operationally_stable_readiness_explanation_preserves_payload(self):
        readiness = readiness_payload()
        original = deepcopy(readiness)

        payload = explanation_payload(readiness)

        assert readiness == original
        assert readiness['readiness']['status_code'] == 'operationally_stable'
        assert payload['scope'] == 'readiness_state'
        assert payload['subject_type'] == 'bullpen'
        assert payload['subject_id'] == 'team:111:bullpen'
        assert payload['state_explained'] == 'operationally_stable'
        assert reason_codes(payload) == set()
        evidence = evidence_by_type(payload)
        assert evidence['readiness_status_code']['value'] == 'operationally_stable'
        assert evidence['workload_pressure_state']['value'] == 'low'
        assert evidence['availability_distribution_total']['value'] == 2
        assert_governance_safe(payload)

    def test_operationally_constrained_readiness_explanation_is_neutral(self):
        readiness = readiness_payload(pitcher_records=constrained_pitcher_records())

        payload = explanation_payload(readiness)

        assert readiness['readiness']['status_code'] == 'operationally_constrained'
        assert payload['state_explained'] == 'operationally_constrained'
        assert reason_codes(payload) == {'READINESS_DEGRADED_BY_LIMITATIONS'}
        assert evidence_by_type(payload)['availability_distribution_monitor']['value'] == 1
        assert_governance_safe(payload)

    def test_operationally_stressed_workload_scope_maps_pressure_evidence(self):
        readiness = readiness_payload(pitcher_records=stressed_pitcher_records())

        payload = explanation_payload(readiness, scope='workload_state')

        assert readiness['readiness']['status_code'] == 'operationally_stressed'
        assert payload['scope'] == 'workload_state'
        assert payload['state_explained'] == 'elevated'
        assert 'WORKLOAD_RECENT_USAGE_ELEVATED' in reason_codes(payload)
        evidence = evidence_by_type(payload)
        assert evidence['workload_pressure_state']['value'] == 'elevated'
        assert evidence['workload_pressure_elevated_count']['value'] == 1
        assert_governance_safe(payload)

    def test_data_limited_freshness_scope_maps_stale_limitation(self):
        readiness = readiness_payload(
            freshness=valid_freshness_metadata(
                freshness_state='stale',
                stale_warning='Current workload evidence is stale.',
            )
        )

        payload = explanation_payload(readiness, scope='freshness_state')

        assert readiness['readiness']['status_code'] == 'data_limited'
        assert payload['scope'] == 'freshness_state'
        assert payload['state_explained'] == 'stale'
        assert 'FRESHNESS_STALE_SOURCE' in reason_codes(payload)
        assert payload['freshness']['status'] == 'stale'
        assert 'stale_data' in limitation_types(payload)
        assert_governance_safe(payload)

    def test_coverage_scope_maps_partial_coverage_evidence_and_limitations(self):
        readiness = readiness_payload(pitcher_records=coverage_limited_pitcher_records())

        payload = explanation_payload(readiness, scope='coverage_state')

        assert readiness['readiness']['status_code'] == 'data_limited'
        assert payload['scope'] == 'coverage_state'
        assert payload['state_explained'] == 'workload:partial;handedness:partial'
        assert 'COVERAGE_PARTIAL' in reason_codes(payload)
        evidence = evidence_by_type(payload)
        assert evidence['coverage_inventory_state']['value'] == 'partial'
        assert evidence['coverage_inventory_missing_workload_data_count']['value'] == 1
        assert evidence['handedness_coverage_unknown_count']['value'] == 1
        assert 'partial_coverage' in limitation_types(payload)
        assert_governance_safe(payload)

    def test_trust_scope_maps_limited_confidence_without_advice(self):
        readiness = readiness_payload(
            trust_metadata=valid_trust_metadata(
                confidence='low',
                data_state='fresh',
                confidence_reasons=['limited_source_evidence'],
            )
        )

        payload = explanation_payload(readiness, scope='trust_state')

        assert readiness['readiness']['status_code'] == 'data_limited'
        assert payload['scope'] == 'trust_state'
        assert payload['state_explained'] == 'limited'
        assert 'TRUST_LIMITED' in reason_codes(payload)
        assert payload['trust']['status'] == 'limited'
        assert payload['confidence']['level'] == 'low'
        assert 'limited_confidence' in limitation_types(payload)
        assert_governance_safe(payload)

    def test_refused_readiness_explanation_maps_fail_closed_limitations(self):
        readiness = readiness_payload(trust_metadata=None)

        payload = explanation_payload(readiness)

        assert readiness['contract_state'] == 'refused'
        assert readiness['readiness']['status_code'] == 'refused'
        assert payload['state_explained'] == 'refused'
        assert payload['trust']['status'] == 'failed'
        assert 'READINESS_DEGRADED_BY_LIMITATIONS' in reason_codes(payload)
        assert 'TRUST_LIMITED' in reason_codes(payload)
        assert 'missing_data' in limitation_types(payload)
        assert_governance_safe(payload)

    def test_missing_or_unavailable_evidence_becomes_limitation_not_fabrication(self):
        readiness = readiness_payload(pitcher_records=coverage_limited_pitcher_records())
        payload = explanation_payload(readiness)
        evidence = evidence_by_type(payload)

        assert 'coverage_inventory_missing_workload_data_count' in evidence
        assert evidence['coverage_inventory_missing_workload_data_count']['value'] == 1
        assert 'partial_coverage' in limitation_types(payload)
        assert 'readiness_risk_distribution' not in evidence
        assert_governance_safe(payload)

    def test_repeated_generation_is_deterministic(self):
        readiness = readiness_payload(pitcher_records=stressed_pitcher_records())

        first = explanation_payload(readiness, scope='readiness_state')
        second = explanation_payload(readiness, scope='readiness_state')

        assert first == second
        assert first['explanation_id'] == second['explanation_id']
        assert stable_json_dumps(first) == stable_json_dumps(second)
        assert_governance_safe(first)

    def test_invalid_inputs_fail_closed_before_explanation_creation(self):
        readiness = readiness_payload()

        with pytest.raises(ValueError, match='readiness explanation scope'):
            build_readiness_explanation(readiness, scope='risk_distribution')

        unsafe = deepcopy(readiness)
        unsafe['ranking_applied'] = True
        with pytest.raises(ValueError, match='ranking_applied must be false'):
            build_readiness_explanation(unsafe)

        invalid_status = deepcopy(readiness)
        invalid_status['readiness']['status_code'] = 'choose_pitcher'
        with pytest.raises(ValueError, match='readiness status uses unsupported'):
            build_readiness_explanation(invalid_status)

    def test_payload_contains_no_prohibited_behavior_fields_or_language(self):
        readiness = readiness_payload(pitcher_records=stressed_pitcher_records())

        payload = explanation_payload(readiness)
        serialized = stable_json_dumps(payload).lower()
        keys = payload_keys(payload)

        assert 'rank' not in keys
        assert 'selected_pitcher' not in keys
        assert 'recommended_pitcher' not in keys
        assert 'preferred_pitcher' not in keys
        assert 'best_arm' not in keys
        assert 'matchup_advice' not in keys
        assert 'prediction' not in keys
        assert 'hidden_priority_ordering' not in keys
        assert 'use this pitcher' not in serialized
        assert 'avoid this pitcher' not in serialized
        assert 'best option' not in serialized
        assert 'preferred arm' not in serialized
        assert 'recommended arm' not in serialized
        assert 'choose this bullpen option' not in serialized
        assert_governance_safe(payload)
