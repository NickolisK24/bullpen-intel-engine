from dataclasses import dataclass
from datetime import date, timedelta

import pytest

from services.availability import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
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


class TestAvailabilityClassification:
    def test_available_when_workload_is_light(self, make_log):
        ref = date(2026, 6, 1)
        result = classify(
            ScoreStub(raw_score=20.0),
            [make_log(ref - timedelta(days=3), pitches_thrown=8)],
            reference_date=ref,
        )

        assert result['availability_status'] == STATUS_AVAILABLE
        assert result['confidence'] == CONFIDENCE_HIGH
        assert result['reasons'] == []

    def test_monitor_for_light_yesterday_workload(self, make_log):
        ref = date(2026, 6, 1)
        result = classify(
            ScoreStub(raw_score=20.0),
            [make_log(ref - timedelta(days=1), pitches_thrown=16)],
            reference_date=ref,
        )

        assert result['availability_status'] == STATUS_MONITOR
        assert result['confidence'] == CONFIDENCE_HIGH
        assert '16 pitches yesterday' in result['reasons']

    def test_limited_for_moderate_yesterday_workload(self, make_log):
        ref = date(2026, 6, 1)
        result = classify(
            ScoreStub(raw_score=30.0),
            [make_log(ref - timedelta(days=1), pitches_thrown=28)],
            reference_date=ref,
        )

        assert result['availability_status'] == STATUS_LIMITED
        assert '28 pitches yesterday' in result['reasons']

    def test_avoid_for_heavy_yesterday_workload(self, make_log):
        ref = date(2026, 6, 1)
        result = classify(
            ScoreStub(raw_score=30.0),
            [make_log(ref - timedelta(days=1), pitches_thrown=42)],
            reference_date=ref,
        )

        assert result['availability_status'] == STATUS_AVOID
        assert '42 pitches yesterday' in result['reasons']

    def test_unavailable_for_extreme_yesterday_workload(self, make_log):
        ref = date(2026, 6, 1)
        result = classify(
            ScoreStub(raw_score=30.0),
            [make_log(ref - timedelta(days=1), pitches_thrown=52)],
            reference_date=ref,
        )

        assert result['availability_status'] == STATUS_UNAVAILABLE
        assert '52 pitches yesterday' in result['reasons']

    def test_multi_day_usage_generates_reasons(self, make_log):
        ref = date(2026, 6, 1)
        logs = [
            make_log(ref, pitches_thrown=18),
            make_log(ref - timedelta(days=1), pitches_thrown=18),
            make_log(ref - timedelta(days=2), pitches_thrown=18),
        ]

        result = classify(ScoreStub(raw_score=35.0), logs, reference_date=ref)

        assert result['availability_status'] == STATUS_AVOID
        assert '54 pitches in 3 days' in result['reasons']
        assert '3 appearances in 4 days' in result['reasons']
        assert result['inputs']['three_in_four'] is True

    @pytest.mark.parametrize(
        ('three_day_pitches', 'expected_status'),
        [
            (79, STATUS_AVOID),
            (80, STATUS_AVOID),
            (89, STATUS_AVOID),
            (90, STATUS_UNAVAILABLE),
            (91, STATUS_UNAVAILABLE),
        ],
    )
    def test_three_day_unavailable_boundary_uses_adopted_90_pitch_threshold(
        self,
        make_log,
        three_day_pitches,
        expected_status,
    ):
        ref = date(2026, 6, 1)
        result = classify(
            ScoreStub(raw_score=20.0),
            [make_log(ref - timedelta(days=2), pitches_thrown=three_day_pitches)],
            reference_date=ref,
        )

        assert result['availability_status'] == expected_status
        assert f'{three_day_pitches} pitches in 3 days' in result['reasons']

    def test_missing_data_is_low_confidence_monitor(self):
        result = classify_availability(
            score=None,
            game_logs=[],
            reference_date=date(2026, 6, 1),
            latest_game_date=None,
        )

        assert result['availability_status'] == STATUS_MONITOR
        assert result['confidence'] == CONFIDENCE_LOW
        assert result['data_state'] == 'missing'
        assert result['reasons'] == ['Missing workload history or fatigue score']

    def test_stale_data_is_low_confidence_and_not_current(self, make_log):
        ref = date(2026, 6, 1)
        result = classify_availability(
            score=ScoreStub(raw_score=20.0),
            game_logs=[],
            reference_date=ref,
            latest_game_date=ref - timedelta(days=30),
        )

        assert result['availability_status'] == STATUS_MONITOR
        assert result['confidence'] == CONFIDENCE_LOW
        assert result['data_state'] == 'stale'
        assert 'Latest workload data is outside the 14-day freshness window' in result['reasons']
        assert any('Stale workload data' in note for note in result['limitations'])

    def test_incomplete_inputs_reduce_confidence(self, make_log):
        ref = date(2026, 6, 1)
        result = classify(
            ScoreStub(raw_score=20.0),
            [make_log(ref - timedelta(days=1), pitches_thrown=None)],
            reference_date=ref,
        )

        assert result['availability_status'] == STATUS_MONITOR
        assert result['confidence'] == CONFIDENCE_LOW
        assert result['data_state'] == 'incomplete'
        assert 'Incomplete workload inputs' in result['reasons']
