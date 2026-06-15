"""
Tests for bullpen roster eligibility filtering.

This protects the boundary between broad pitcher availability data and
bullpen-specific surfaces. Clear starters must not enter default bullpen counts,
while relief usage stays included without team-specific names.
"""

from datetime import date, timedelta
from types import SimpleNamespace

from services.bullpen_eligibility import (
    STATUS_BULLPEN_RELEVANT,
    STATUS_CLEAR_STARTER,
    STATUS_INACTIVE_BULLPEN_RELEVANT,
    STATUS_UNCERTAIN,
    evaluate_bullpen_eligibility,
)
from utils.innings import outs_to_decimal_innings, parse_mlb_innings_to_outs

REF = date(2026, 6, 6)


class LogStub:
    def __init__(self, days_ago, innings_pitched, game_type='R', save=False, hold=False, save_situation=False):
        innings_outs = parse_mlb_innings_to_outs(innings_pitched)
        self.game_date = REF - timedelta(days=days_ago)
        self.innings_pitched = outs_to_decimal_innings(innings_outs)
        self.innings_pitched_outs = innings_outs
        self.game_type = game_type
        self.save = save
        self.hold = hold
        self.save_situation = save_situation


def pitcher(position='P', active=True):
    return SimpleNamespace(position=position, active=active)


def test_clear_starter_pattern_is_excluded():
    result = evaluate_bullpen_eligibility(
        pitcher(),
        [LogStub(1, 6.0), LogStub(6, 5.1), LogStub(11, 6.0)],
        reference_date=REF,
    )

    assert result['eligible'] is False
    assert result['status'] == STATUS_CLEAR_STARTER
    assert 'starter-length pattern' in result['reason']


def test_recent_relief_usage_is_included_without_explicit_role_data():
    result = evaluate_bullpen_eligibility(
        pitcher(),
        [LogStub(1, 1.0), LogStub(3, 0.2), LogStub(5, 1.0)],
        reference_date=REF,
    )

    assert result['eligible'] is True
    assert result['status'] == STATUS_BULLPEN_RELEVANT
    assert result['confidence'] == 'high'


def test_recent_relief_streak_overrides_older_starter_history():
    result = evaluate_bullpen_eligibility(
        pitcher(),
        [
            LogStub(1, 1.0),
            LogStub(3, 1.0),
            LogStub(5, 1.1),
            LogStub(15, 6.0),
            LogStub(20, 5.0),
        ],
        reference_date=REF,
    )

    assert result['eligible'] is True
    assert result['status'] == STATUS_BULLPEN_RELEVANT


def test_recent_short_outings_do_not_override_deep_starter_history():
    result = evaluate_bullpen_eligibility(
        pitcher(),
        [
            LogStub(1, 1.0, game_type=None),
            LogStub(3, 1.0, game_type=None),
            LogStub(5, 0.2, game_type=None),
            LogStub(10, 6.0, game_type=None),
            LogStub(15, 7.0, game_type=None),
            LogStub(20, 6.1, game_type=None),
        ],
        reference_date=REF,
    )

    assert result['eligible'] is False
    assert result['status'] in {STATUS_CLEAR_STARTER, STATUS_UNCERTAIN}


def test_save_situation_alone_does_not_override_starter_history():
    result = evaluate_bullpen_eligibility(
        pitcher(),
        [
            LogStub(1, 1.0, game_type=None, save_situation=True),
            LogStub(6, 6.0, game_type=None),
            LogStub(12, 7.0, game_type=None),
            LogStub(18, 6.1, game_type=None),
        ],
        reference_date=REF,
    )

    assert result['eligible'] is False
    assert result['status'] in {STATUS_CLEAR_STARTER, STATUS_UNCERTAIN}


def test_uncertain_non_bullpen_usage_is_withheld():
    result = evaluate_bullpen_eligibility(
        pitcher(),
        [LogStub(1, 2.2), LogStub(5, 2.1), LogStub(9, 2.2)],
        reference_date=REF,
    )

    assert result['eligible'] is False
    assert result['status'] == STATUS_UNCERTAIN
    assert any('withheld' in limitation for limitation in result['limitations'])


def test_inactive_relief_context_is_labelled_when_included():
    result = evaluate_bullpen_eligibility(
        pitcher(),
        [LogStub(30, 1.0), LogStub(32, 1.0), LogStub(35, 0.2)],
        reference_date=REF,
    )

    assert result['eligible'] is True
    assert result['status'] == STATUS_INACTIVE_BULLPEN_RELEVANT
    assert result['confidence'] == 'low'
    assert any('unavailable or stale workload pitchers are included' in limitation for limitation in result['limitations'])
