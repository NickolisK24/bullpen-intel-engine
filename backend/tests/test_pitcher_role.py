"""
Tests for Pitcher Usage Role Separation V1 (services/pitcher_role.py).

Pure classifier — no DB/Flask/network. Covers each role category, confidence
degradation, insufficient/stale/incomplete data, missing optional fields, and
transparency. Also guards that no forbidden advisory language appears.

GameLog stand-in carries only the fields the classifier reads.
"""

from datetime import date, timedelta

from services.pitcher_role import (
    BASE_LIMITATIONS,
    ROLE_INSUFFICIENT,
    ROLE_LATE,
    ROLE_LABELS,
    ROLE_LONG,
    ROLE_LOW,
    ROLE_MIDDLE,
    ROLE_SETUP,
    classify_usage_role,
)

REF = date(2026, 6, 5)


class LogStub:
    def __init__(self, days_ago, innings_pitched=1.0, save=False, hold=False,
                 save_situation=False, leverage_index=None):
        self.game_date = REF - timedelta(days=days_ago)
        self.innings_pitched = innings_pitched
        self.save = save
        self.hold = hold
        self.save_situation = save_situation
        self.leverage_index = leverage_index


def role_of(logs):
    return classify_usage_role(logs, reference_date=REF)


# ── Role categories ────────────────────────────────────────────────────────

class TestRoleCategories:
    def test_insufficient_data_when_no_logs(self):
        result = role_of([])
        assert result['role_key'] == ROLE_INSUFFICIENT
        assert result['confidence'] == 'none'

    def test_low_unclear_when_too_few_appearances(self):
        result = role_of([LogStub(2, innings_pitched=1.0)])
        assert result['role_key'] == ROLE_LOW
        assert result['confidence'] == 'low'

    def test_middle_relief_for_regular_short_outings(self):
        logs = [LogStub(d, innings_pitched=1.0) for d in (2, 5, 8, 11)]
        result = role_of(logs)
        assert result['role_key'] == ROLE_MIDDLE
        assert result['confidence'] == 'high'

    def test_long_multi_inning_for_repeated_multi_inning_workload(self):
        logs = [LogStub(2, 2.0), LogStub(6, 1.7), LogStub(10, 2.0)]
        result = role_of(logs)
        assert result['role_key'] == ROLE_LONG

    def test_late_high_leverage_requires_real_supporting_fields(self):
        # Saves present → late-inning pattern (not faked from fatigue).
        logs = [LogStub(2, 1.0, save=True), LogStub(5, 1.0, save=True), LogStub(8, 1.0)]
        result = role_of(logs)
        assert result['role_key'] == ROLE_LATE

    def test_late_high_leverage_from_high_leverage_index(self):
        logs = [LogStub(d, 1.0, leverage_index=2.0) for d in (2, 5, 8)]
        result = role_of(logs)
        assert result['role_key'] == ROLE_LATE
        assert result['confidence'] == 'high'  # leverage present, full sample

    def test_setup_bridge_from_holds(self):
        logs = [LogStub(2, 1.0, hold=True), LogStub(5, 1.0, hold=True), LogStub(8, 1.0)]
        result = role_of(logs)
        assert result['role_key'] == ROLE_SETUP

    def test_larger_sustained_pattern_wins_when_both_saves_and_holds_qualify(self):
        # Save and hold patterns are compared — prestige-first ordering is gone.
        more_saves = [
            LogStub(2, 1.0, save=True), LogStub(5, 1.0, save=True),
            LogStub(8, 1.0, save=True), LogStub(11, 1.0, save=True),
            LogStub(14, 1.0, hold=True), LogStub(17, 1.0, hold=True),
        ]
        assert role_of(more_saves)['role_key'] == ROLE_LATE

        more_holds = [
            LogStub(2, 1.0, hold=True), LogStub(5, 1.0, hold=True),
            LogStub(8, 1.0, hold=True), LogStub(11, 1.0, hold=True),
            LogStub(14, 1.0, save=True), LogStub(17, 1.0, save=True),
        ]
        assert role_of(more_holds)['role_key'] == ROLE_SETUP

    def test_one_isolated_save_or_hold_does_not_establish_a_role(self):
        one_save = [LogStub(2, 1.0, save=True)] + [LogStub(d, 1.0) for d in (5, 8, 11)]
        assert role_of(one_save)['role_key'] == ROLE_MIDDLE

        one_hold = [LogStub(2, 1.0, hold=True)] + [LogStub(d, 1.0) for d in (5, 8, 11)]
        assert role_of(one_hold)['role_key'] == ROLE_MIDDLE

    def test_save_situation_without_a_save_is_supporting_evidence_only(self):
        logs = (
            [LogStub(2, 1.0, save_situation=True), LogStub(5, 1.0, save_situation=True)]
            + [LogStub(d, 1.0) for d in (8, 11, 14)]
        )
        result = role_of(logs)
        assert result['role_key'] == ROLE_MIDDLE
        assert any('save-situation appearance' in e for e in result['evidence'])

    def test_save_hold_evidence_outranks_innings_length(self):
        # A pitcher with holds AND long outings reads as setup (defined role)
        # rather than long relief.
        logs = [LogStub(2, 2.0, hold=True), LogStub(5, 2.0, hold=True), LogStub(8, 2.0)]
        assert role_of(logs)['role_key'] == ROLE_SETUP


# ── Confidence degradation ─────────────────────────────────────────────────

class TestConfidence:
    def test_small_sample_caps_at_medium(self):
        logs = [LogStub(2, 1.0), LogStub(5, 1.0)]  # exactly 2 appearances
        assert role_of(logs)['confidence'] == 'medium'

    def test_stale_data_caps_at_low(self):
        # Most recent outing is well outside the 14-day window.
        logs = [LogStub(40, 1.0), LogStub(45, 1.0), LogStub(50, 1.0)]
        result = role_of(logs)
        assert result['confidence'] == 'low'
        assert any('freshness window' in lim for lim in result['limitations'])

    def test_incomplete_innings_caps_at_medium_and_notes_it(self):
        logs = [LogStub(2, 1.0), LogStub(5, None), LogStub(8, 1.0), LogStub(11, 1.0)]
        result = role_of(logs)
        assert result['confidence'] == 'medium'
        assert any('missing innings' in lim for lim in result['limitations'])

    def test_missing_leverage_caps_late_setup_at_medium(self):
        # Save flags only, no leverage index → capped at medium with a note.
        logs = [LogStub(2, 1.0, save=True), LogStub(5, 1.0, save=True), LogStub(8, 1.0, save=True)]
        result = role_of(logs)
        assert result['role_key'] == ROLE_LATE
        assert result['confidence'] == 'medium'
        assert any('Leverage-index data was not available' in lim for lim in result['limitations'])


# ── Transparency + governance ──────────────────────────────────────────────

class TestTransparency:
    def test_every_result_carries_label_reason_evidence_limitations(self):
        logs = [LogStub(d, 1.0) for d in (2, 5, 8)]
        result = role_of(logs)
        assert result['role'] == ROLE_LABELS[result['role_key']]
        assert isinstance(result['short_reason'], str) and result['short_reason']
        assert len(result['evidence']) >= 1
        for limitation in BASE_LIMITATIONS:
            assert limitation in result['limitations']

    def test_evidence_references_real_numbers(self):
        logs = [LogStub(2, 2.0), LogStub(6, 1.7), LogStub(10, 2.0)]
        evidence = role_of(logs)['evidence']
        assert any('3 appearances' in e for e in evidence)
        assert any('Average recent IP' in e for e in evidence)

    def test_missing_optional_fields_are_disclosed(self):
        logs = [LogStub(d, 1.0) for d in (2, 5, 8)]  # no save/hold/leverage
        result = role_of(logs)
        assert any('Save, hold, and leverage data were not available' in lim for lim in result['limitations'])

    def test_no_forbidden_advisory_language(self):
        forbidden = (
            'use this pitcher', 'best option', 'recommended', 'should pitch',
            'deploy', 'closer of the night', 'best arm', 'recommendation',
        )
        for logs in (
            [],
            [LogStub(2, 1.0)],
            [LogStub(d, 1.0) for d in (2, 5, 8)],
            [LogStub(2, 2.0), LogStub(6, 2.0), LogStub(10, 2.0)],
            [LogStub(2, 1.0, save=True), LogStub(5, 1.0, save=True), LogStub(8, 1.0)],
            [LogStub(2, 1.0, hold=True), LogStub(5, 1.0, hold=True), LogStub(8, 1.0)],
        ):
            result = role_of(logs)
            blob = ' '.join([
                result['role'], result['short_reason'],
                *result['evidence'], *result['limitations'],
            ]).lower()
            for term in forbidden:
                assert term not in blob, f'{term!r} leaked for {result["role_key"]}'


# ── Branch 3 calibration scenarios (synthetic evidence patterns only) ────────

class TestCalibrationScenarios:
    def test_s1_one_old_save_then_newer_middle_relief(self):
        logs = [LogStub(40, 1.0, save=True, save_situation=True)] + [
            LogStub(d, 1.0) for d in (2, 5, 8, 12, 16, 20, 25, 30)
        ]
        result = role_of(logs)
        assert result['role_key'] == ROLE_MIDDLE
        assert result['role_key'] != ROLE_LATE
        assert any('Older save evidence' in e for e in result['evidence'])
        assert any('did not meet the sustained late-inning threshold' in e for e in result['evidence'])

    def test_s2_one_old_hold_then_newer_long_relief(self):
        logs = [LogStub(35, 1.0, hold=True)] + [
            LogStub(d, 2.0) for d in (2, 5, 9, 13, 17, 20)
        ]
        result = role_of(logs)
        assert result['role_key'] == ROLE_LONG
        assert result['role_key'] != ROLE_SETUP

    def test_s3_fernando_style_setup_majority_beats_one_save(self):
        # 18 qualifying relief appearances, one save, six holds (one recent),
        # avg IP ~0.9, no leverage coverage.
        hold_days = (2, 24, 27, 30, 33, 36)
        logs = (
            [LogStub(d, 1.0, hold=True) for d in hold_days]
            + [LogStub(38, 1.0, save=True, save_situation=True)]
            + [LogStub(d, 1.0) for d in (4, 6, 9, 12, 15, 18, 21)]
            + [LogStub(d, 0.5) for d in (3, 7, 11, 14)]
        )
        result = role_of(logs)
        assert result['role_key'] == ROLE_SETUP
        assert result['role_key'] != ROLE_LATE
        assert result['confidence'] == 'medium'  # no leverage coverage
        assert any('Hold share: 33%' in e for e in result['evidence'])

    def test_s4_jake_style_isolated_hold_reads_middle_relief(self):
        logs = (
            [LogStub(10, 1.0, hold=True)]
            + [LogStub(12, 1.0, save_situation=True)]
            + [LogStub(d, 1.0) for d in (2, 4, 6, 8, 14, 16, 18, 20)]
            + [LogStub(d, 0.5) for d in (3, 5, 7, 9)]
        )
        result = role_of(logs)
        assert result['role_key'] == ROLE_MIDDLE
        assert result['role_key'] != ROLE_SETUP

    def test_s5_blackburn_style_long_relief_beats_isolated_save_and_hold(self):
        # 16 qualifying relief appearances, 1 save, 1 hold, 11 outings above
        # 1.0 IP, avg IP >= 1.5, no leverage coverage.
        logs = (
            [LogStub(2, 2.0, save=True, save_situation=True)]
            + [LogStub(6, 2.0, hold=True)]
            + [LogStub(d, 2.0) for d in (4, 9, 12, 15, 18, 22, 26, 30, 34)]
            + [LogStub(d, 1.0) for d in (3, 7, 11, 19, 27)]
        )
        result = role_of(logs)
        assert result['role_key'] == ROLE_LONG
        assert result['role_key'] not in (ROLE_LATE, ROLE_SETUP)

    def test_s6_sustained_closer_pattern_is_late(self):
        logs = (
            [LogStub(d, 1.0, save=True, save_situation=True) for d in (2, 6, 10, 14)]
            + [LogStub(18, 1.0, hold=True)]
            + [LogStub(d, 1.0) for d in (4, 8, 12, 16, 20, 24, 28)]
        )
        result = role_of(logs)
        assert result['role_key'] == ROLE_LATE

    def test_s7_sustained_setup_pattern_is_setup(self):
        logs = (
            [LogStub(d, 1.0, hold=True) for d in (2, 6, 10, 14)]
            + [LogStub(d, 1.0) for d in (4, 8, 12, 16, 20)]
        )
        result = role_of(logs)
        assert result['role_key'] == ROLE_SETUP

    def test_s8_emergency_save_on_setup_pattern_stays_setup(self):
        logs = (
            [LogStub(2, 1.0, save=True, save_situation=True)]
            + [LogStub(d, 1.0, hold=True) for d in (4, 8, 12, 16, 20)]
            + [LogStub(d, 1.0) for d in (6, 10, 14, 18, 22, 26)]
        )
        result = role_of(logs)
        assert result['role_key'] == ROLE_SETUP
        assert result['role_key'] != ROLE_LATE

    def test_s9_tied_save_and_hold_evidence_fails_closed(self):
        logs = (
            [LogStub(d, 1.0, save=True, save_situation=True) for d in (2, 24, 28)]
            + [LogStub(d, 1.0, hold=True) for d in (4, 26, 30)]
            + [LogStub(d, 1.0) for d in (6, 8, 10, 12, 14, 16)]
        )
        result = role_of(logs)
        assert result['role_key'] == ROLE_LOW
        assert result['confidence'] == 'low'
        assert any('equally sustained' in lim for lim in result['limitations'])
        assert 'equally sustained' in result['short_reason']

    def test_s10_strong_recent_high_leverage_is_late(self):
        logs = (
            [LogStub(d, 1.0, leverage_index=li) for d, li in ((2, 1.7), (6, 1.6), (10, 1.5))]
            + [LogStub(d, 1.0) for d in (4, 8, 12)]
        )
        result = role_of(logs)
        assert result['role_key'] == ROLE_LATE
        assert result['confidence'] == 'high'

    def test_s11_strong_recent_setup_leverage_is_setup(self):
        logs = (
            [LogStub(d, 1.0, leverage_index=li) for d, li in ((2, 1.2), (6, 1.1), (10, 1.3))]
            + [LogStub(d, 1.0) for d in (4, 8, 12)]
        )
        result = role_of(logs)
        assert result['role_key'] == ROLE_SETUP

    def test_s12_one_leverage_value_cannot_establish_a_late_role(self):
        logs = (
            [LogStub(2, 1.0, leverage_index=2.5)]
            + [LogStub(d, 1.0) for d in (5, 8, 11)]
        )
        result = role_of(logs)
        assert result['role_key'] == ROLE_MIDDLE

    def test_s13_leverage_and_categorical_disagreement_fails_closed(self):
        # Sustained save pattern says Late; recent leverage coverage says Setup.
        logs = (
            [LogStub(d, 1.0, save=True, save_situation=True, leverage_index=1.1)
             for d in (2, 6)]
            + [LogStub(d, 1.0, leverage_index=1.1) for d in (4, 8)]
            + [LogStub(d, 1.0) for d in (10, 12)]
        )
        result = role_of(logs)
        assert result['role_key'] == ROLE_LOW
        assert result['confidence'] == 'low'
        assert any('point to different' in lim for lim in result['limitations'])

    def test_s14_no_signal_short_relief_is_middle(self):
        logs = [LogStub(d, 1.0) for d in (2, 6, 10, 14)]
        assert role_of(logs)['role_key'] == ROLE_MIDDLE

    def test_s15_clean_coverage_pattern_is_long(self):
        logs = [LogStub(d, 2.0) for d in (2, 7, 12, 18, 24)]
        assert role_of(logs)['role_key'] == ROLE_LONG


# ── Temporal role movement across reference dates ────────────────────────────

class TestTemporalTransitions:
    def _classify(self, logs, ref):
        window = [log for log in logs if 0 <= (ref - log.game_date).days <= 45]
        return classify_usage_role(window, reference_date=ref)

    def test_promotion_requires_a_second_qualifying_hold(self):
        first_hold = date(2026, 6, 1)
        second_hold = date(2026, 6, 10)
        middles = [date(2026, 5, 28), date(2026, 6, 3), date(2026, 6, 6), date(2026, 6, 12)]

        def log(day, hold=False):
            stub = LogStub(0, 1.0, hold=hold)
            stub.game_date = day
            return stub

        logs = [log(first_hold, hold=True), log(second_hold, hold=True)] + [
            log(day) for day in middles
        ]

        ref_a = date(2026, 6, 5)  # only the first hold exists yet
        at_a = self._classify([l for l in logs if l.game_date <= ref_a], ref_a)
        assert at_a['role_key'] != ROLE_SETUP

        ref_b = date(2026, 6, 15)  # both holds in window, recently confirmed
        at_b = self._classify(logs, ref_b)
        assert at_b['role_key'] == ROLE_SETUP

    def test_demotion_happens_before_old_saves_leave_the_45_day_window(self):
        def log(day, save=False):
            stub = LogStub(0, 1.0, save=save, save_situation=save)
            stub.game_date = day
            return stub

        saves = [log(date(2026, 5, 1), save=True), log(date(2026, 5, 5), save=True)]
        early_middles = [log(date(2026, 5, 3)), log(date(2026, 5, 8)), log(date(2026, 5, 11))]
        newer_middles = [
            log(date(2026, 5, 20)), log(date(2026, 5, 24)),
            log(date(2026, 5, 28)), log(date(2026, 6, 1)), log(date(2026, 6, 3)),
        ]
        logs = saves + early_middles + newer_middles

        ref_a = date(2026, 5, 15)  # saves are recent → Late
        at_a = self._classify([l for l in logs if l.game_date <= ref_a], ref_a)
        assert at_a['role_key'] == ROLE_LATE

        ref_b = date(2026, 6, 5)  # saves still inside 45 days, outside 21 days
        at_b = self._classify(logs, ref_b)
        assert (ref_b - saves[0].game_date).days <= 45
        assert (ref_b - saves[0].game_date).days > 21
        assert at_b['role_key'] == ROLE_MIDDLE
        assert any('Older save evidence' in e for e in at_b['evidence'])

    def test_one_emergency_save_does_not_convert_a_setup_arm(self):
        def log(day, save=False, hold=False):
            stub = LogStub(0, 1.0, save=save, save_situation=save, hold=hold)
            stub.game_date = day
            return stub

        holds = [log(date(2026, 6, d), hold=True) for d in (1, 4, 8, 12, 15)]
        middles = [log(date(2026, 6, d)) for d in (2, 6, 10)]

        ref_a = date(2026, 6, 16)
        at_a = self._classify(holds + middles, ref_a)
        assert at_a['role_key'] == ROLE_SETUP

        emergency = [log(date(2026, 6, 17), save=True)]
        ref_b = date(2026, 6, 18)
        at_b = self._classify(holds + middles + emergency, ref_b)
        assert at_b['role_key'] == ROLE_SETUP

    def test_genuine_conversion_requires_sustained_save_evidence(self):
        def log(day, save=False, hold=False):
            stub = LogStub(0, 1.0, save=save, save_situation=save, hold=hold)
            stub.game_date = day
            return stub

        holds = [log(date(2026, 6, d), hold=True) for d in (1, 3, 5, 7, 9)]
        first_save = [log(date(2026, 6, 11), save=True)]
        more_saves = [log(date(2026, 6, d), save=True) for d in (13, 15, 17, 19, 21)]

        # The first isolated save does not trigger the conversion.
        ref_a = date(2026, 6, 12)
        at_a = self._classify(holds + first_save, ref_a)
        assert at_a['role_key'] == ROLE_SETUP

        # Sustained saves (6) exceeding the hold pattern (5) convert the role.
        ref_b = date(2026, 6, 22)
        at_b = self._classify(holds + first_save + more_saves, ref_b)
        assert at_b['role_key'] == ROLE_LATE
