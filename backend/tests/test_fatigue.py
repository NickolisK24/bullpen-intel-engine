"""
Unit + lightweight integration tests for the fatigue scoring engine
(backend/services/fatigue.py).

The engine is the core of the bullpen product, so these tests pin down its
behavior. The implementation in services/fatigue.py is the source of truth —
expected values below were derived from that implementation, not redefined
independently. No database, Flask context, or network is required.
"""

from datetime import date

import pytest

from services.fatigue import (
    score_pitch_count,
    score_rest_days,
    score_appearances,
    score_innings,
    get_risk_level,
    calculate_fatigue,
)


# ─── Pitch Count Load (35%) ────────────────────────────────────────────────────

class TestScorePitchCount:
    @pytest.mark.parametrize("pitches, expected", [
        (0,   0.0),    # no pitches → fresh
        (25,  12.5),   # light-usage ramp (p/50 * 25)
        (50,  25.0),   # moderate threshold — continuous with the light band
        (70,  37.5),   # moderate buildup (ramps 25→50 across 50..90)
        (90,  50.0),   # high threshold
        (105, 75.0),   # high-fatigue zone (ramps 50→100 across 90..120)
        (120, 100.0),  # critical threshold
        (150, 100.0),  # above critical → clamped at 100
    ])
    def test_representative_values(self, pitches, expected):
        assert score_pitch_count(pitches) == pytest.approx(expected)

    def test_moderate_threshold_is_continuous(self):
        """
        The light-usage band reaches ~24.5 at 49 pitches and the moderate band
        starts at 25.0 at 50 pitches — continuous, with no downward jump.
        """
        assert score_pitch_count(49) == pytest.approx(24.5)
        assert score_pitch_count(50) == pytest.approx(25.0)
        assert score_pitch_count(50) >= score_pitch_count(49)

    def test_regression_no_downward_jump_at_50(self):
        """
        Regression guard for the Phase 4 discontinuity (49 -> 24.5, 50 -> 0.0):
        one extra pitch must never *lower* the fatigue score.
        """
        assert score_pitch_count(50) > score_pitch_count(49)
        assert score_pitch_count(50) != pytest.approx(0.0)

    def test_monotonic_non_decreasing(self):
        """Score must never decrease as pitch count rises (covers every boundary)."""
        scores = [score_pitch_count(p) for p in range(0, 151)]
        assert all(b >= a for a, b in zip(scores, scores[1:]))

    def test_never_exceeds_bounds(self):
        for p in (0, 10, 55, 95, 119, 200):
            assert 0.0 <= score_pitch_count(p) <= 100.0


# ─── Rest Days (30%) ────────────────────────────────────────────────────────────

class TestScoreRestDays:
    @pytest.mark.parametrize("days, expected", [
        (None, 0.0),   # unknown / no prior appearance
        (0,    100.0), # pitched today → maximum fatigue signal
        (1,    80.0),
        (2,    55.0),
        (3,    30.0),
        (4,    10.0),
        (5,    0.0),   # 5+ days fully rested
        (6,    0.0),
    ])
    def test_representative_values(self, days, expected):
        assert score_rest_days(days) == pytest.approx(expected)

    def test_more_rest_never_increases_fatigue(self):
        scores = [score_rest_days(d) for d in (0, 1, 2, 3, 4, 5)]
        assert scores == sorted(scores, reverse=True)


# ─── Appearance Frequency (20%) ──────────────────────────────────────────────────

class TestScoreAppearances:
    @pytest.mark.parametrize("apps7, apps14, expected", [
        (0, 0,  0.0),    # no appearances
        (1, 1,  12.75),  # light load (below moderate band)
        (3, 10, 48.0),   # moderate band
        (5, 8,  88.0),   # high band
        (6, 8,  100.0),  # critical → clamped at 100
    ])
    def test_representative_values(self, apps7, apps14, expected):
        assert score_appearances(apps7, apps14) == pytest.approx(expected)

    def test_fourteen_day_window_contributes(self):
        """
        With the same 7-day count, more appearances in the 14-day window must
        raise the score — verifies the 70/15 weighted blend is wired in.
        """
        fewer = score_appearances(3, 3)
        more = score_appearances(3, 10)
        assert more > fewer
        assert fewer == pytest.approx(16.5)
        assert more == pytest.approx(48.0)


# ─── Innings Load (15%) ───────────────────────────────────────────────────────

class TestScoreInnings:
    @pytest.mark.parametrize("innings, expected", [
        (0.0, 0.0),    # no innings
        (2.0, 25.0),   # low workload (ramps 0→50 across 0..4)
        (4.0, 50.0),   # 4 IP threshold
        (5.0, 75.0),   # inside 4..6 band
        (6.0, 100.0),  # 6 IP threshold
        (7.0, 100.0),  # above 6 → clamped at 100
    ])
    def test_representative_values(self, innings, expected):
        assert score_innings(innings) == pytest.approx(expected)


# ─── Risk Level Thresholds ──────────────────────────────────────────────────────

class TestGetRiskLevel:
    @pytest.mark.parametrize("score, expected", [
        (0,      "LOW"),
        (24,     "LOW"),
        (24.999, "LOW"),
        (25,     "MODERATE"),  # lower edge of MODERATE
        (49,     "MODERATE"),
        (50,     "HIGH"),      # lower edge of HIGH
        (80,     "HIGH"),
        (80.999, "HIGH"),
        (81,     "CRITICAL"),  # lower edge of CRITICAL
        (100,    "CRITICAL"),
        (101,    "CRITICAL"),  # beyond range still CRITICAL
    ])
    def test_threshold_boundaries(self, score, expected):
        assert get_risk_level(score) == expected


# ─── calculate_fatigue (integration, deterministic) ─────────────────────────────

class TestCalculateFatigue:
    def test_returns_expected_shape_and_values(self, pitcher, make_log, reference_date):
        # Logs ordered most-recent-first, as calculate_fatigue expects.
        logs = [
            make_log("2024-09-10", pitches_thrown=20, innings_pitched=1.0),
            make_log("2024-09-08", pitches_thrown=15, innings_pitched=1.0),
            make_log("2024-09-01", pitches_thrown=18, innings_pitched=2.0),  # outside 7d window
        ]

        score = calculate_fatigue(pitcher, logs, reference_date=reference_date)

        # Identity + supporting windows
        assert score.pitcher_id == 42
        assert score.days_since_last_appearance == 0          # last log == reference_date
        assert score.pitches_last_7_days == 35                # 20 + 15 (09-01 excluded)
        assert score.innings_last_7_days == pytest.approx(2.0)
        assert score.appearances_last_7 == 2
        assert score.appearances_last_14 == 3

        # Composite score is deterministic for fixed inputs:
        # pc(35)=17.5*.35 + rest(0)=100*.30 + app(2,3)=27.75*.20 + inn(2.0)=25*.15
        assert score.raw_score == pytest.approx(45.425)
        assert score.risk_level == "MODERATE"

        # Leverage Index was removed from the model — never contributes.
        assert score.leverage_score == 0.0

    def test_empty_logs_score_zero_and_low_risk(self, pitcher):
        score = calculate_fatigue(pitcher, [], reference_date=date(2024, 9, 10))
        assert score.raw_score == 0.0
        assert score.risk_level == "LOW"
        assert score.days_since_last_appearance is None
        assert score.pitches_last_7_days == 0
        assert score.appearances_last_7 == 0
        assert score.appearances_last_14 == 0

    def test_innings_load_sums_outs_not_display_decimals(self, pitcher, make_log):
        ref = date(2024, 9, 10)
        logs = [
            make_log("2024-09-10", innings_pitched=2 / 3, innings_pitched_outs=2),
            make_log("2024-09-09", innings_pitched=2 / 3, innings_pitched_outs=2),
            make_log("2024-09-08", innings_pitched=2 / 3, innings_pitched_outs=2),
        ]

        score = calculate_fatigue(pitcher, logs, reference_date=ref)

        assert score.innings_last_7_days == 2.0
        assert score.innings_score == pytest.approx(25.0)

    def test_raw_score_clamped_to_100(self, pitcher, make_log):
        # Heavy back-to-back usage drives every component toward its max.
        ref = date(2024, 9, 10)
        logs = [
            make_log("2024-09-10", pitches_thrown=130, innings_pitched=7.0),
            make_log("2024-09-09", pitches_thrown=60,  innings_pitched=3.0),
            make_log("2024-09-08", pitches_thrown=60,  innings_pitched=3.0),
            make_log("2024-09-07", pitches_thrown=60,  innings_pitched=3.0),
            make_log("2024-09-06", pitches_thrown=60,  innings_pitched=3.0),
        ]
        score = calculate_fatigue(pitcher, logs, reference_date=ref)
        assert 0.0 <= score.raw_score <= 100.0
        assert score.risk_level in ("HIGH", "CRITICAL")
