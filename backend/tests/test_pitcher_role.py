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

    def test_late_outranks_setup_when_both_present(self):
        logs = [LogStub(2, 1.0, save=True, hold=True), LogStub(5, 1.0), LogStub(8, 1.0)]
        assert role_of(logs)['role_key'] == ROLE_LATE

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
