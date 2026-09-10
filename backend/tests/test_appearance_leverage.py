"""Tests for the additive per-appearance leverage classifier (Phase 3)."""

from services.appearance_leverage import (
    BASIS_INDEX,
    BASIS_NONE,
    BASIS_SAVE_HOLD,
    ROLE_HIGH,
    ROLE_LOW,
    ROLE_MEDIUM,
    ROLE_UNKNOWN,
    classify_appearance_leverage,
    summarize_reliever_leverage,
)


def _log(**kwargs):
    base = {
        'game_date': '2026-06-20',
        'pitches_thrown': 15,
        'innings_pitched': 1.0,
        'innings_pitched_outs': 3,
        'leverage_index': None,
        'save_situation': False,
        'hold': False,
        'blown_save': False,
    }
    base.update(kwargs)
    return base


def test_high_leverage_from_index():
    result = classify_appearance_leverage(_log(leverage_index=2.1))
    assert result['role'] == ROLE_HIGH
    assert result['is_high_leverage'] is True
    assert result['basis'] == BASIS_INDEX


def test_low_leverage_from_index():
    result = classify_appearance_leverage(_log(leverage_index=0.4))
    assert result['role'] == ROLE_LOW
    assert result['is_low_leverage'] is True


def test_medium_leverage_from_index():
    result = classify_appearance_leverage(_log(leverage_index=1.1))
    assert result['role'] == ROLE_MEDIUM


def test_save_situation_fallback_when_index_missing():
    result = classify_appearance_leverage(_log(leverage_index=None, save_situation=True))
    assert result['role'] == ROLE_HIGH
    assert result['basis'] == BASIS_SAVE_HOLD


def test_hold_fallback():
    result = classify_appearance_leverage(_log(leverage_index=None, hold=True))
    assert result['role'] == ROLE_HIGH
    assert result['basis'] == BASIS_SAVE_HOLD


def test_unknown_when_no_signal():
    result = classify_appearance_leverage(_log(leverage_index=None))
    assert result['role'] == ROLE_UNKNOWN
    assert result['basis'] == BASIS_NONE


def test_index_takes_precedence_over_flags():
    # An explicit low index should win even if a (stale) save flag is set.
    result = classify_appearance_leverage(_log(leverage_index=0.3, save_situation=True))
    assert result['role'] == ROLE_LOW


def test_summary_counts_and_shares():
    logs = [
        _log(game_date='2026-06-10', leverage_index=2.0),
        _log(game_date='2026-06-12', leverage_index=0.5),
        _log(game_date='2026-06-14', leverage_index=1.2),
        _log(game_date='2026-06-16', leverage_index=None),  # unknown
    ]
    summary = summarize_reliever_leverage(logs)
    assert summary['appearances'] == 4
    assert summary['high_leverage_count'] == 1
    assert summary['low_leverage_count'] == 1
    assert summary['medium_leverage_count'] == 1
    assert summary['unknown_leverage_count'] == 1
    assert summary['classified_appearances'] == 3
    assert summary['high_leverage_share'] == round(1 / 3, 2)


def test_summary_reentry_uses_latest_appearance():
    # Reintroduced arm whose most recent outing was the low-leverage door.
    logs = [
        _log(game_date='2026-06-10', leverage_index=2.2),  # earlier: the close
        _log(game_date='2026-06-18', leverage_index=0.4),  # latest: mop-up
    ]
    summary = summarize_reliever_leverage(logs)
    assert summary['most_recent_role'] == ROLE_LOW
    assert summary['reentered_low_leverage'] is True
    assert summary['reentered_high_leverage'] is False


def test_summary_ignores_zero_pitch_artifacts():
    logs = [
        _log(game_date='2026-06-10', leverage_index=2.0),
        _log(game_date='2026-06-11', pitches_thrown=0, innings_pitched=0.0,
             innings_pitched_outs=0, leverage_index=1.9),  # boxscore artifact
    ]
    summary = summarize_reliever_leverage(logs)
    assert summary['appearances'] == 1


def test_summary_empty():
    summary = summarize_reliever_leverage([])
    assert summary['appearances'] == 0
    assert summary['most_recent_role'] == ROLE_UNKNOWN
    assert summary['high_leverage_share'] is None
