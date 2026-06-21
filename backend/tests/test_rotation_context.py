from datetime import date, timedelta

from services.rotation_context import (
    CAPABILITY,
    INCOMPLETE_GAME_DATA_LIMITATION,
    OPENER_BULK_LIMITATION,
    build_rotation_context,
)
from utils.innings import outs_to_decimal_innings


REF = date(2026, 6, 20)


def log(game_pk, days_ago, outs, games_started):
    return {
        'mlb_game_pk': game_pk,
        'game_date': REF - timedelta(days=days_ago),
        'game_type': 'R',
        'games_started': games_started,
        'innings_pitched_outs': outs,
        'innings_pitched': outs_to_decimal_innings(outs),
    }


def game(game_pk, days_ago, starter_outs, relief_outs):
    rows = [log(game_pk, days_ago, starter_outs, 1)]
    if relief_outs is not None:
        rows.append(log(game_pk, days_ago, relief_outs, 0))
    return rows


def context(logs):
    return build_rotation_context(logs, reference_date=REF)


def test_normal_starter_usage_builds_rotation_context_layer():
    result = context([
        *game(1, 1, 18, 9),
        *game(2, 2, 18, 9),
        *game(3, 3, 18, 9),
        *game(4, 4, 18, 9),
        *game(5, 8, 15, 12),
        *game(6, 10, 15, 12),
    ])

    assert result['capability'] == CAPABILITY
    assert result['rotation_avg_ip_7d'] == 6.0
    assert result['rotation_avg_ip_14d'] == 5.7
    assert result['rotation_ip_trend'] == 0.3
    assert result['early_bullpen_entry_rate'] == 0.0
    assert result['bullpen_coverage_ip_7d'] == 3.0
    assert result['games_analyzed_7d'] == 4
    assert result['games_analyzed_14d'] == 6


def test_multiple_opener_games_are_measured_without_role_inference():
    result = context([
        *game(1, 1, 3, 24),
        *game(2, 2, 3, 24),
        *game(3, 3, 3, 24),
        *game(4, 8, 18, 9),
        *game(5, 9, 18, 9),
    ])

    assert result['rotation_avg_ip_7d'] == 1.0
    assert result['rotation_avg_ip_14d'] == 3.0
    assert result['rotation_ip_trend'] == -2.0
    assert result['early_bullpen_entry_rate'] == 60.0
    assert result['bullpen_coverage_ip_7d'] == 8.0
    assert OPENER_BULK_LIMITATION in result['limitations']


def test_short_starts_lower_rotation_trend_and_increase_early_entry_rate():
    result = context([
        *game(1, 1, 12, 15),
        *game(2, 2, 12, 15),
        *game(3, 3, 12, 15),
        *game(4, 8, 18, 9),
        *game(5, 10, 18, 9),
    ])

    assert result['rotation_avg_ip_7d'] == 4.0
    assert result['rotation_avg_ip_14d'] == 4.8
    assert result['rotation_ip_trend'] == -0.8
    assert result['early_bullpen_entry_rate'] == 60.0
    assert result['bullpen_coverage_ip_7d'] == 5.0
    assert result['early_bullpen_entry_games_14d'] == 3


def test_doubleheaders_are_counted_by_game_pk_not_date():
    result = context([
        *game(101, 1, 18, 9),
        *game(102, 1, 15, 12),
        *game(103, 2, 18, 9),
    ])

    assert result['games_in_window_14d'] == 3
    assert result['games_analyzed_7d'] == 3
    assert result['rotation_avg_ip_7d'] == 5.7
    assert result['rotation_avg_ip_14d'] == 5.7
    assert result['bullpen_coverage_ip_7d'] == 3.3
    assert result['early_bullpen_entry_rate'] == 0.0


def test_games_without_clear_starter_are_excluded_from_context():
    result = context([
        *game(1, 1, 18, 9),
        log(2, 2, 27, 0),
        log(3, 3, 12, 1),
        log(3, 3, 15, 1),
        {
            'mlb_game_pk': 4,
            'game_date': REF - timedelta(days=4),
            'game_type': 'R',
            'games_started': 1,
            'innings_pitched_outs': None,
            'innings_pitched': None,
        },
    ])

    assert result['games_in_window_14d'] == 4
    assert result['games_analyzed_14d'] == 1
    assert result['games_excluded_14d'] == 3
    assert result['excluded_game_reasons'] == {
        'no_starter': 1,
        'multiple_starters': 1,
        'missing_starter_innings': 1,
    }
    assert result['rotation_avg_ip_7d'] == 6.0
    assert result['early_bullpen_entry_rate'] == 0.0
    assert result['bullpen_coverage_ip_7d'] == 3.0
    assert INCOMPLETE_GAME_DATA_LIMITATION in result['limitations']
