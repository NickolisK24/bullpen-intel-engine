from copy import deepcopy
from dataclasses import dataclass
from datetime import date, timedelta

import pytest

from explanations import (
    build_availability_explanation,
    serialize_availability_explanation,
    stable_json_dumps,
    v4_governance_errors,
)
from services.availability import (
    STATUS_AVAILABLE,
    STATUS_AVOID,
    STATUS_LIMITED,
    STATUS_MONITOR,
    STATUS_UNAVAILABLE,
    classify_availability,
)


@dataclass
class ScoreStub:
    raw_score: float
    risk_level: str = 'LOW'


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


def classify(score, logs, latest_game_date=None, reference_date=None):
    ref = reference_date or date(2026, 6, 1)
    if latest_game_date is None and logs:
        latest_game_date = max(log.game_date for log in logs)
    return classify_availability(
        score=score,
        game_logs=logs,
        reference_date=ref,
        latest_game_date=latest_game_date,
    )


def explanation_payload(availability, subject_id='42'):
    return serialize_availability_explanation(
        availability,
        subject_id=subject_id,
        generated_at='2026-06-03T12:00:00Z',
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


def assert_governance_safe(payload):
    governance = payload['governance']

    assert governance['ranking_applied'] is False
    assert governance['selection_made'] is False
    assert governance['recommendation_made'] is False
    assert governance['prediction_made'] is False
    assert governance['decision_scope'] == 'explanation_only'
    assert governance['advice_scope'] == 'none'
    assert v4_governance_errors(payload) == []


def assert_no_availability_meta_copy(payload):
    serialized = stable_json_dumps(payload).lower()
    for phrase in (
        'governed availability evidence',
        'explanation confidence mirrors',
        'visibility reflects existing availability confidence',
        'explained state',
    ):
        assert phrase not in serialized


class TestV4AvailabilityExplanationIntegration:
    def test_available_state_explanation_preserves_status_and_governance(self, make_log):
        ref = date(2026, 6, 1)
        availability = classify(
            ScoreStub(raw_score=20.0),
            [make_log(ref - timedelta(days=3), pitches_thrown=8)],
            reference_date=ref,
        )
        original = deepcopy(availability)

        payload = explanation_payload(availability)

        assert availability == original
        assert availability['availability_status'] == STATUS_AVAILABLE
        assert payload['scope'] == 'availability_state'
        assert payload['subject_type'] == 'pitcher'
        assert payload['subject_id'] == '42'
        assert payload['state_explained'] == STATUS_AVAILABLE
        assert payload['primary_reasons'] == []
        assert evidence_by_type(payload)['availability_status']['value'] == STATUS_AVAILABLE
        assert evidence_by_type(payload)['availability_fatigue_score']['value'] == 20.0
        assert_governance_safe(payload)

    def test_monitor_state_explanation_maps_monitor_and_workload_reasons(self, make_log):
        ref = date(2026, 6, 1)
        availability = classify(
            ScoreStub(raw_score=20.0),
            [make_log(ref - timedelta(days=1), pitches_thrown=16)],
            reference_date=ref,
        )

        payload = explanation_payload(availability)

        assert availability['availability_status'] == STATUS_MONITOR
        assert payload['state_explained'] == STATUS_MONITOR
        assert reason_codes(payload) == {
            'AVAILABILITY_MONITOR_THRESHOLD_MET',
            'WORKLOAD_RECENT_USAGE_ELEVATED',
        }
        evidence = evidence_by_type(payload)
        assert evidence['availability_pitches_yesterday']['value'] == 16
        assert evidence['availability_data_state']['value'] == 'fresh'
        assert_governance_safe(payload)

    def test_limited_state_explanation_maps_workload_evidence(self, make_log):
        ref = date(2026, 6, 1)
        availability = classify(
            ScoreStub(raw_score=30.0),
            [make_log(ref - timedelta(days=1), pitches_thrown=28)],
            reference_date=ref,
        )

        payload = explanation_payload(availability)

        assert availability['availability_status'] == STATUS_LIMITED
        assert payload['state_explained'] == STATUS_LIMITED
        assert reason_codes(payload) == {'WORKLOAD_RECENT_USAGE_ELEVATED'}
        assert evidence_by_type(payload)['availability_pitches_yesterday']['value'] == 28
        assert_governance_safe(payload)

    def test_avoid_state_explanation_maps_workload_evidence(self, make_log):
        ref = date(2026, 6, 1)
        availability = classify(
            ScoreStub(raw_score=30.0),
            [make_log(ref - timedelta(days=1), pitches_thrown=42)],
            reference_date=ref,
        )

        payload = explanation_payload(availability)

        assert availability['availability_status'] == STATUS_AVOID
        assert payload['state_explained'] == STATUS_AVOID
        assert reason_codes(payload) == {'WORKLOAD_RECENT_USAGE_ELEVATED'}
        assert evidence_by_type(payload)['availability_pitches_yesterday']['value'] == 42
        assert_governance_safe(payload)

    def test_unavailable_state_explanation_maps_extreme_workload_evidence(self, make_log):
        ref = date(2026, 6, 1)
        availability = classify(
            ScoreStub(raw_score=30.0),
            [make_log(ref - timedelta(days=1), pitches_thrown=52)],
            reference_date=ref,
        )

        payload = explanation_payload(availability)

        assert availability['availability_status'] == STATUS_UNAVAILABLE
        assert payload['state_explained'] == STATUS_UNAVAILABLE
        assert reason_codes(payload) == {'WORKLOAD_RECENT_USAGE_ELEVATED'}
        assert evidence_by_type(payload)['availability_pitches_yesterday']['value'] == 52
        assert_governance_safe(payload)

    def test_freshness_evidence_and_stale_limitation_are_mapped(self):
        ref = date(2026, 6, 1)
        availability = classify_availability(
            score=ScoreStub(raw_score=20.0),
            game_logs=[],
            reference_date=ref,
            latest_game_date=ref - timedelta(days=30),
        )

        payload = explanation_payload(availability)

        assert availability['availability_status'] == STATUS_MONITOR
        assert payload['freshness']['status'] == 'stale'
        assert 'FRESHNESS_STALE_SOURCE' in reason_codes(payload)
        assert evidence_by_type(payload)['availability_data_state']['value'] == 'stale'
        assert 'stale_data' in limitation_types(payload)
        assert 'limited_confidence' in limitation_types(payload)
        assert 'BaseballOS is treating him as a monitor arm' in payload['summary']
        assert_no_availability_meta_copy(payload)
        assert_governance_safe(payload)

    def test_missing_evidence_becomes_limitation_without_fabricated_workload(self):
        availability = classify_availability(
            score=None,
            game_logs=[],
            reference_date=date(2026, 6, 1),
            latest_game_date=None,
        )

        payload = explanation_payload(availability)
        evidence = evidence_by_type(payload)

        assert availability['data_state'] == 'missing'
        assert payload['freshness']['status'] == 'missing'
        assert 'TRUST_LIMITED' in reason_codes(payload)
        assert 'missing_data' in limitation_types(payload)
        assert 'limited_confidence' in limitation_types(payload)
        assert 'availability_fatigue_score' not in evidence
        assert 'availability_pitches_yesterday' not in evidence
        assert 'recent workload data is missing' in payload['summary']
        assert_no_availability_meta_copy(payload)
        assert_governance_safe(payload)

    def test_incomplete_evidence_becomes_partial_coverage_limitation(self, make_log):
        ref = date(2026, 6, 1)
        availability = classify(
            ScoreStub(raw_score=20.0),
            [make_log(ref - timedelta(days=1), pitches_thrown=None)],
            reference_date=ref,
        )

        payload = explanation_payload(availability)

        assert availability['data_state'] == 'incomplete'
        assert payload['freshness']['status'] == 'incomplete'
        assert 'COVERAGE_PARTIAL' in reason_codes(payload)
        assert 'partial_coverage' in limitation_types(payload)
        assert 'limited_confidence' in limitation_types(payload)
        assert 'workload detail is incomplete' in payload['summary']
        assert_no_availability_meta_copy(payload)
        assert_governance_safe(payload)

    def test_repeated_generation_is_deterministic(self, make_log):
        ref = date(2026, 6, 1)
        availability = classify(
            ScoreStub(raw_score=78.2),
            [
                make_log(ref, pitches_thrown=10),
                make_log(ref - timedelta(days=1), pitches_thrown=40),
                make_log(ref - timedelta(days=2), pitches_thrown=10),
                make_log(ref - timedelta(days=4), pitches_thrown=15),
            ],
            reference_date=ref,
        )

        first = explanation_payload(availability)
        second = explanation_payload(availability)

        assert first == second
        assert first['explanation_id'] == second['explanation_id']
        assert stable_json_dumps(first) == stable_json_dumps(second)
        assert_governance_safe(first)

    def test_invalid_availability_input_fails_closed(self):
        with pytest.raises(ValueError, match='availability_status uses unsupported'):
            build_availability_explanation(
                {'availability_status': 'Recommended'},
                subject_id='42',
            )

        with pytest.raises(ValueError, match='subject_id is required'):
            build_availability_explanation(
                {'availability_status': STATUS_AVAILABLE, 'confidence': 'high'},
                subject_id=None,
            )

    def test_payload_contains_no_prohibited_behavior_fields_or_language(self, make_log):
        ref = date(2026, 6, 1)
        availability = classify(
            ScoreStub(raw_score=30.0),
            [make_log(ref - timedelta(days=1), pitches_thrown=42)],
            reference_date=ref,
        )

        payload = explanation_payload(availability)
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
        assert_governance_safe(payload)
