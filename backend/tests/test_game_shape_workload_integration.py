"""Tests for Game Shape integration into workload concentration (Phase C3I).

A planned bulk-follower outing in an opener/bulk game is separated from ordinary
bullpen concentration, while ordinary long relief and bullpen-game work are
unaffected and per-pitcher fatigue/availability still count the full workload.
"""

from datetime import date, timedelta
from types import SimpleNamespace

from services.bullpen_concentration_context import build_bullpen_concentration_context
from services.game_shape import (
    SHAPE_BULLPEN_GAME,
    SHAPE_NORMAL_START,
    SHAPE_OPENER_BULK_GAME,
    bulk_follower_appearance_keys,
    game_shape_of,
)

REF = date(2026, 6, 20)


def _log(player_id, days_ago, pitches, *, games_started=0, outs=3, game_pk=None, team_id=1):
    pid = player_id + 100000
    return SimpleNamespace(
        pitcher_id=pid,
        pitcher=SimpleNamespace(
            id=pid, mlb_id=player_id, full_name=f'P{player_id}',
            team_id=team_id, team_name=f'Team {team_id}', team_abbreviation=f'T{team_id}',
        ),
        mlb_game_pk=game_pk if game_pk is not None else (team_id * 100000 + player_id + days_ago),
        game_date=REF - timedelta(days=days_ago),
        game_type='R',
        games_started=games_started,
        innings_pitched_outs=outs,
        innings_pitched=outs / 3.0,
        pitches_thrown=pitches,
    )


# ── Detection helper (game-shape-aware, not length-only) ─────────────────────

def test_bulk_follower_detected_only_in_opener_game():
    opener_game = [
        _log(1, 1, 30, games_started=1, outs=3, game_pk=1001),
        _log(2, 1, 80, games_started=0, outs=18, game_pk=1001),
    ]
    assert game_shape_of(opener_game) == SHAPE_OPENER_BULK_GAME
    assert bulk_follower_appearance_keys(opener_game) == {(100002, 1001)}


def test_long_reliever_in_normal_game_is_not_a_bulk_follower():
    normal_game = [
        _log(3, 1, 90, games_started=1, outs=18, game_pk=2001),
        _log(7, 1, 55, games_started=0, outs=12, game_pk=2001),  # 4 IP long relief
    ]
    assert game_shape_of(normal_game) == SHAPE_NORMAL_START
    assert bulk_follower_appearance_keys(normal_game) == set()


def test_long_reliever_in_bullpen_game_is_not_a_bulk_follower():
    bullpen_game = [
        _log(8, 1, 70, games_started=0, outs=18, game_pk=3001),
        _log(9, 1, 30, games_started=0, outs=9, game_pk=3001),
    ]
    assert game_shape_of(bullpen_game) == SHAPE_BULLPEN_GAME
    assert bulk_follower_appearance_keys(bullpen_game) == set()


# ── Concentration context ─────────────────────────────────────────────────────

def _discount_scenario():
    return [
        _log(1, 1, 30, games_started=1, outs=3, game_pk=1001),   # opener (start, excluded)
        _log(2, 1, 80, games_started=0, outs=18, game_pk=1001),  # bulk follower -> separated
        _log(4, 2, 14, games_started=0, outs=3, game_pk=1002),
        _log(5, 3, 12, games_started=0, outs=3, game_pk=1003),
        _log(6, 4, 10, games_started=0, outs=3, game_pk=1004),
    ]


def test_concentration_separates_bulk_follower_with_transparency():
    result = build_bullpen_concentration_context(_discount_scenario(), reference_date=REF)

    assert result['bulk_follower_appearances_10d'] == 1
    assert result['bulk_follower_pitches_discounted_10d'] == 80
    assert result['excluded_row_reasons'].get('bulk_follower') == 1
    # The bulk follower (player_id 2) is not part of bullpen concentration.
    assert 2 not in [row['player_id'] for row in result['top_three_relievers_10d']]
    # Concentration reflects only genuine relief workload (14 + 12 + 10).
    assert result['bullpen_workload_total_10d'] == 36


def test_ordinary_long_reliever_counts_in_full():
    logs = [
        _log(3, 1, 90, games_started=1, outs=18, game_pk=2001),  # normal starter
        _log(7, 1, 55, games_started=0, outs=12, game_pk=2001),  # 4 IP long relief, normal game
        _log(4, 2, 12, games_started=0, outs=3, game_pk=2002),
    ]
    result = build_bullpen_concentration_context(logs, reference_date=REF)
    assert result['bulk_follower_appearances_10d'] == 0
    assert result['bulk_follower_pitches_discounted_10d'] == 0
    assert 7 in [row['player_id'] for row in result['top_three_relievers_10d']]
    assert result['bullpen_workload_total_10d'] == 67  # 55 + 12


def test_bullpen_game_relievers_count_in_full():
    logs = [
        _log(8, 1, 70, games_started=0, outs=18, game_pk=3001),  # long relief in a bullpen game
        _log(9, 1, 30, games_started=0, outs=9, game_pk=3001),
        _log(4, 2, 12, games_started=0, outs=3, game_pk=3002),
    ]
    result = build_bullpen_concentration_context(logs, reference_date=REF)
    assert result['bulk_follower_appearances_10d'] == 0
    assert 8 in [row['player_id'] for row in result['top_three_relievers_10d']]
    assert result['bullpen_workload_total_10d'] == 112  # 70 + 30 + 12


def test_concentration_outputs_remain_deterministic():
    first = build_bullpen_concentration_context(_discount_scenario(), reference_date=REF)
    second = build_bullpen_concentration_context(_discount_scenario(), reference_date=REF)
    assert first == second


# ── workload_concentration shared engine ─────────────────────────────────────

def test_recent_relief_totals_discount_bulk_follower_when_opener_visible():
    from services.workload_concentration import recent_relief_pitch_totals

    logs_by_pitcher = {
        100001: [_log(1, 1, 30, games_started=1, outs=3, game_pk=1001)],   # opener visible
        100002: [_log(2, 1, 80, games_started=0, outs=18, game_pk=1001)],  # bulk follower
        100004: [_log(4, 2, 14, games_started=0, outs=3, game_pk=1002)],   # genuine relief
    }
    totals = recent_relief_pitch_totals(logs_by_pitcher, REF)
    assert 100002 not in totals          # bulk follower separated
    assert totals.get(100004) == 14       # genuine relief fully counted


# ── Fatigue and availability inputs are untouched ────────────────────────────

def test_fatigue_counts_bulk_follower_workload_in_full():
    from services.fatigue import calculate_fatigue

    pitcher = SimpleNamespace(id=100002)
    logs = [_log(2, 1, 80, games_started=0, outs=18, game_pk=1001)]
    score = calculate_fatigue(pitcher, logs, reference_date=REF)
    assert score.pitches_last_7_days == 80


def test_per_pitcher_workload_primitive_counts_bulk_outing():
    from services.workload_appearance import is_workload_appearance_log, workload_pitch_count

    bulk = _log(2, 1, 80, games_started=0, outs=18, game_pk=1001)
    assert is_workload_appearance_log(bulk) is True
    assert workload_pitch_count(bulk) == 80
