"""
Role Authority V1 — classification, confidence, and eligibility mapping.

Pure-Python: builds Pitcher/GameLog stubs and calls classify_role directly. No
database, app context, or network. These replay the audit findings at the unit
level (starters excluded, long relievers included, swingmen/openers ambiguous,
no-evidence withheld as Unknown).
"""

from datetime import date, timedelta
from types import SimpleNamespace

from models.game_log import GameLog
from services.role_authority import (
    CONF_HIGH,
    CONF_LOW,
    CONF_MEDIUM,
    CONF_NONE,
    ROLE_AMBIGUOUS,
    ROLE_RELIEVER,
    ROLE_STARTER,
    ROLE_UNKNOWN,
    classify_role,
    role_authority_enabled,
)
from utils.innings import outs_to_decimal_innings, parse_mlb_innings_to_outs

REF = date(2026, 6, 9)


def log(days_ago, games_started=None, innings_pitched=1.0,
        save=False, hold=False, save_situation=False):
    innings_outs = parse_mlb_innings_to_outs(innings_pitched)
    return SimpleNamespace(
        game_date=REF - timedelta(days=days_ago),
        games_started=games_started,
        innings_pitched=outs_to_decimal_innings(innings_outs),
        innings_pitched_outs=innings_outs,
        save=save, hold=hold, save_situation=save_situation,
    )


def _pitcher():
    return SimpleNamespace(id=1, full_name='Test Pitcher', active=True)


# ── Starter ─────────────────────────────────────────────────────────────────

def test_clear_starter_is_excluded_high_confidence():
    logs = [log(d, games_started=1, innings_pitched=6.0) for d in (1, 6, 11, 16, 21, 26)]
    result = classify_role(_pitcher(), logs, reference_date=REF)
    assert result['role'] == ROLE_STARTER
    assert result['eligible'] is False
    assert result['confidence'] == CONF_HIGH


def test_starter_with_small_sample_is_excluded_medium():
    # Rookie-call-up starter: 3 starts, all GS=1 → still excluded, medium conf.
    logs = [log(d, games_started=1, innings_pitched=5.0) for d in (2, 7, 12)]
    result = classify_role(_pitcher(), logs, reference_date=REF)
    assert result['role'] == ROLE_STARTER
    assert result['eligible'] is False
    assert result['confidence'] == CONF_MEDIUM


def test_single_start_is_low_confidence():
    result = classify_role(_pitcher(), [log(2, games_started=1, innings_pitched=6.0)], reference_date=REF)
    assert result['role'] == ROLE_STARTER
    assert result['confidence'] == CONF_LOW


# ── Reliever ────────────────────────────────────────────────────────────────

def test_pure_reliever_is_included_high_confidence():
    logs = [log(d, games_started=0, innings_pitched=1.0) for d in (1, 3, 5, 7, 9, 11)]
    result = classify_role(_pitcher(), logs, reference_date=REF)
    assert result['role'] == ROLE_RELIEVER
    assert result['eligible'] is True
    assert result['confidence'] == CONF_HIGH


def test_long_multi_inning_reliever_is_included_not_excluded():
    # The key reversed false-negative: 3+ IP relief outings, but GS=0 → Reliever.
    logs = [log(d, games_started=0, innings_pitched=3.1) for d in (2, 6, 10, 14, 18)]
    result = classify_role(_pitcher(), logs, reference_date=REF)
    assert result['role'] == ROLE_RELIEVER
    assert result['eligible'] is True


def test_relief_context_without_start_data_is_reliever_low():
    logs = [log(1, games_started=None, innings_pitched=1.0, save=True),
            log(3, games_started=None, innings_pitched=1.0, hold=True)]
    result = classify_role(_pitcher(), logs, reference_date=REF)
    assert result['role'] == ROLE_RELIEVER
    assert result['eligible'] is True
    assert result['confidence'] == CONF_LOW


# ── Ambiguous ───────────────────────────────────────────────────────────────

def test_swingman_is_ambiguous_with_caveat_and_included():
    logs = [log(2, games_started=1, innings_pitched=5.0),
            log(6, games_started=1, innings_pitched=5.0),
            log(9, games_started=1, innings_pitched=5.0),
            log(12, games_started=0, innings_pitched=1.0),
            log(14, games_started=0, innings_pitched=1.0),
            log(16, games_started=0, innings_pitched=1.0)]
    result = classify_role(_pitcher(), logs, reference_date=REF)
    assert result['role'] == ROLE_AMBIGUOUS
    assert result['eligible'] is True
    assert result['limitations']  # caveat present


def test_opener_short_starts_are_ambiguous_not_starter():
    # All credited starts but ~1 IP each → opener tie-breaker → Ambiguous.
    logs = [log(d, games_started=1, innings_pitched=1.0) for d in (2, 7, 12, 17)]
    result = classify_role(_pitcher(), logs, reference_date=REF)
    assert result['role'] == ROLE_AMBIGUOUS
    assert result['eligible'] is True


# ── Unknown ─────────────────────────────────────────────────────────────────

def test_no_logs_is_unknown_and_withheld():
    result = classify_role(_pitcher(), [], reference_date=REF)
    assert result['role'] == ROLE_UNKNOWN
    assert result['eligible'] is False
    assert result['confidence'] == CONF_NONE


def test_relief_position_without_logs_is_included_with_low_confidence():
    pitcher = SimpleNamespace(id=1, full_name='Roster Reliever', active=True, position='RP')
    result = classify_role(pitcher, [], reference_date=REF)
    assert result['role'] == ROLE_RELIEVER
    assert result['eligible'] is True
    assert result['confidence'] == CONF_LOW
    assert result['limitations']


def test_no_start_data_no_relief_context_is_unknown_not_reliever():
    # Thin-evidence pitchers must NOT silently become relievers.
    logs = [log(2, games_started=None, innings_pitched=1.0),
            log(5, games_started=None, innings_pitched=1.0)]
    result = classify_role(_pitcher(), logs, reference_date=REF)
    assert result['role'] == ROLE_UNKNOWN
    assert result['eligible'] is False


# ── Determinism + contract ──────────────────────────────────────────────────

def test_classification_is_deterministic():
    logs = [log(d, games_started=0, innings_pitched=1.0) for d in (1, 3, 5)]
    first = classify_role(_pitcher(), logs, reference_date=REF)
    second = classify_role(_pitcher(), logs, reference_date=REF)
    assert first == second


def test_eligibility_shape_is_drop_in_compatible():
    result = classify_role(_pitcher(), [log(1, games_started=0)], reference_date=REF)
    for key in ('eligible', 'status', 'confidence', 'reason', 'evidence', 'limitations', 'role'):
        assert key in result


def test_role_authority_flag_supports_explicit_enable_and_disable(monkeypatch):
    monkeypatch.setenv('ROLE_AUTHORITY_ENABLED', 'false')
    assert role_authority_enabled() is False
    monkeypatch.setenv('ROLE_AUTHORITY_ENABLED', 'true')
    assert role_authority_enabled() is True


def test_game_log_model_declares_games_started_column():
    assert 'games_started' in GameLog.__table__.columns
    assert GameLog.__table__.columns['games_started'].nullable is True
    assert 'innings_pitched_outs' in GameLog.__table__.columns
    assert GameLog.__table__.columns['innings_pitched_outs'].nullable is False
