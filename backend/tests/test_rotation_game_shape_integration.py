"""Tests for Game Shape integration into rotation context (Phase C3G).

Opener/bulk games are excluded from rotation-depth averages and early-bullpen-
entry so they are not read as failed starts; bullpen games are surfaced
separately; normal and short starts keep their current behavior.
"""

from datetime import date, timedelta

from services.rotation_context import build_rotation_context
from utils.innings import outs_to_decimal_innings

REF = date(2026, 6, 20)


def _row(game_pk, days_ago, outs, games_started):
    return {
        'mlb_game_pk': game_pk,
        'game_date': REF - timedelta(days=days_ago),
        'game_type': 'R',
        'games_started': games_started,
        'innings_pitched_outs': outs,
        'innings_pitched': outs_to_decimal_innings(outs) if outs is not None else None,
    }


def _start_game(game_pk, days_ago, starter_outs, relief_outs):
    return [_row(game_pk, days_ago, starter_outs, 1), _row(game_pk, days_ago, relief_outs, 0)]


def _bullpen_game(game_pk, days_ago, *relief_outs):
    return [_row(game_pk, days_ago, outs, 0) for outs in relief_outs]


def _ctx(logs):
    return build_rotation_context(logs, reference_date=REF)


def test_opener_and_failed_short_start_treated_differently():
    # A 1-IP opener in front of a 6-IP bulk arm must not behave like a genuine
    # 1-IP short start.
    result = _ctx([
        *_start_game(1, 1, 3, 18),   # opener/bulk game
        *_start_game(2, 2, 3, 3),    # genuine short start (no bulk follower)
        *_start_game(3, 3, 18, 9),   # normal start
    ])

    distribution = result['game_shape_distribution']
    assert distribution['opener_bulk_game'] == 1
    assert distribution['short_start'] == 1
    assert distribution['normal_start'] == 1

    # Average is over the short start (1.0 IP) and the normal start (6.0 IP); the
    # opener is excluded. (3 + 18) outs over 2 starts -> 3.5 IP.
    assert result['rotation_starts_7d'] == 2
    assert result['opener_bulk_games_7d'] == 1
    assert result['rotation_avg_ip_7d'] == 3.5

    # Early-bullpen-entry counts the genuine short start, not the opener.
    assert result['early_bullpen_entry_games_14d'] == 1
    assert result['early_bullpen_entry_rate'] == 50.0


def test_bullpen_game_tracked_separately_not_as_short_start():
    result = _ctx([
        *_start_game(1, 1, 18, 9),       # normal start
        *_bullpen_game(2, 2, 9, 9, 9),   # bullpen game, no starter
    ])

    assert result['game_shape_distribution'].get('bullpen_game') == 1
    assert result['bullpen_games_count'] == 1
    # The bullpen game is excluded from analysis (no starter), never counted as a
    # short start or early entry.
    assert result['games_excluded_14d'] == 1
    assert result['excluded_game_reasons'].get('no_starter') == 1
    assert result['rotation_starts_14d'] == 1
    assert result['rotation_avg_ip_14d'] == 6.0
    assert result['early_bullpen_entry_games_14d'] == 0


def test_normal_and_short_starts_keep_current_behavior():
    result = _ctx([
        *_start_game(1, 1, 18, 9),    # normal
        *_start_game(2, 2, 12, 12),   # short (4.0 IP)
        *_start_game(3, 3, 18, 9),    # normal
    ])

    # Nothing is excluded by shape: rotation starts equal analyzed games.
    assert result['rotation_starts_7d'] == result['games_analyzed_7d'] == 3
    assert result['opener_bulk_games_7d'] == 0
    # (18 + 12 + 18) outs over 3 starts -> 5.3 IP.
    assert result['rotation_avg_ip_7d'] == 5.3
    assert result['early_bullpen_entry_games_14d'] == 1  # the short start


def test_mixed_sample_handles_each_shape():
    result = _ctx([
        *_start_game(1, 1, 18, 9),       # normal
        *_start_game(2, 2, 12, 9),       # short
        *_start_game(3, 3, 3, 18),       # opener/bulk
        *_bullpen_game(4, 4, 9, 9, 9),   # bullpen game
    ])

    distribution = result['game_shape_distribution']
    assert distribution['normal_start'] == 1
    assert distribution['short_start'] == 1
    assert distribution['opener_bulk_game'] == 1
    assert distribution['bullpen_game'] == 1

    assert result['opener_bulk_games_14d'] == 1
    assert result['bullpen_games_count'] == 1
    # Opener excluded from depth, bullpen game excluded from analysis: depth is
    # the normal + short start only.
    assert result['rotation_starts_14d'] == 2
    # Opener stays visible as an analyzed game; bullpen game is excluded.
    assert result['games_analyzed_14d'] == 3
    assert result['games_excluded_14d'] == 1
