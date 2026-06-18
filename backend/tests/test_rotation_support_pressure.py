from datetime import date, timedelta

from services.rotation_support_pressure import (
    CURRENT_ASSIGNMENT_LIMITATION,
    INCOMPLETE_GAME_DATA_LIMITATION,
    LIMITED_SAMPLE_LIMITATION,
    MATERIAL_EXCLUSION_LIMITATION,
    OPENER_BULK_LIMITATION,
    STATUS_HEAVY,
    STATUS_LIMITED,
    STATUS_MODERATE,
    STATUS_SUPPORTIVE,
    UNKNOWN_SPLIT_LIMITATION,
    build_team_rotation_support_pressure,
)
from utils.innings import outs_to_decimal_innings


REF = date(2026, 6, 18)


def log(game_pk, days_ago, outs, games_started):
    return {
        'pitcher_id': game_pk * 10 + (games_started or 0),
        'mlb_game_pk': game_pk,
        'game_date': REF - timedelta(days=days_ago),
        'game_type': 'R',
        'games_started': games_started,
        'innings_pitched_outs': outs,
        'innings_pitched': outs_to_decimal_innings(outs),
    }


def game(game_pk, days_ago, starter_outs, relief_outs):
    rows = [log(game_pk, days_ago, starter_outs, 1)]
    if relief_outs:
        rows.append(log(game_pk, days_ago, relief_outs, 0))
    return rows


def pressure(logs):
    return build_team_rotation_support_pressure(
        logs,
        team={'team_id': 1, 'team_name': 'Test Team', 'team_abbreviation': 'TST'},
        reference_date=REF,
    )


def test_strong_starter_support_reads_supportive_with_low_bullpen_burden():
    result = pressure([
        *game(1, 1, 18, 9),
        *game(2, 2, 18, 9),
        *game(3, 3, 18, 9),
        *game(4, 4, 18, 9),
    ])

    assert result['status'] == STATUS_SUPPORTIVE
    assert result['games_analyzed'] == 4
    assert result['starter_outs'] == 72
    assert result['starter_innings'] == 24.0
    assert result['starter_avg_innings'] == 6.0
    assert result['bullpen_outs_required'] == 36
    assert result['bullpen_innings_required'] == 12.0
    assert result['short_start_count'] == 0
    assert result['short_start_rate'] == 0.0
    assert result['limitations'] == []
    assert CURRENT_ASSIGNMENT_LIMITATION in result['source_limitations']
    assert OPENER_BULK_LIMITATION in result['source_limitations']


def test_short_starts_create_heavy_rotation_pressure():
    result = pressure([
        *game(1, 1, 12, 15),
        *game(2, 2, 12, 15),
        *game(3, 3, 12, 15),
        *game(4, 4, 12, 15),
    ])

    assert result['status'] == STATUS_HEAVY
    assert result['starter_avg_innings'] == 4.0
    assert result['bullpen_innings_required'] == 20.0
    assert result['short_start_count'] == 4
    assert result['short_start_rate'] == 1.0


def test_elevated_short_start_rate_creates_moderate_pressure():
    result = pressure([
        *game(1, 1, 14, 13),
        *game(2, 2, 18, 9),
        *game(3, 3, 18, 9),
    ])

    assert result['status'] == STATUS_MODERATE
    assert result['starter_avg_innings'] == 5.56
    assert result['short_start_count'] == 1
    assert result['short_start_rate'] == 0.33


def test_limited_read_when_complete_game_sample_is_too_small():
    result = pressure([
        *game(1, 1, 18, 9),
        *game(2, 2, 18, 9),
    ])

    assert result['status'] == STATUS_LIMITED
    assert result['games_analyzed'] == 2
    assert LIMITED_SAMPLE_LIMITATION in result['limitations']


def test_same_date_multiple_games_are_grouped_by_game_pk():
    result = pressure([
        *game(101, 1, 18, 9),
        *game(102, 1, 18, 9),
        *game(103, 2, 18, 9),
    ])

    assert result['status'] == STATUS_SUPPORTIVE
    assert result['games_in_window'] == 3
    assert result['games_analyzed'] == 3
    assert result['games_excluded'] == 0
    assert result['starter_outs'] == 54
    assert result['bullpen_outs_required'] == 27


def test_missing_starter_game_is_excluded_with_clear_semantics():
    result = pressure([
        *game(1, 1, 18, 9),
        *game(2, 2, 18, 9),
        *game(3, 3, 18, 9),
        log(4, 4, 27, 0),
    ])

    assert result['games_in_window'] == 4
    assert result['games_analyzed'] == 3
    assert result['games_excluded'] == 1
    assert result['excluded_game_reasons'] == {'no_starter': 1}
    assert INCOMPLETE_GAME_DATA_LIMITATION in result['limitations']
    assert result['definitions']['games_analyzed'] == (
        'Games with usable starter/bullpen split data. Excluded games are not counted here.'
    )


def test_opener_bulk_style_games_keep_source_caveat_visible():
    result = pressure([
        *game(1, 1, 3, 24),
        *game(2, 2, 3, 24),
        *game(3, 3, 3, 24),
    ])

    assert result['status'] == STATUS_HEAVY
    assert result['games_analyzed'] == 3
    assert result['starter_avg_innings'] == 1.0
    assert result['bullpen_innings_required'] == 24.0
    assert OPENER_BULK_LIMITATION in result['source_limitations']


def test_ambiguous_or_incomplete_split_excludes_games_with_limitations():
    result = pressure([
        *game(1, 1, 18, 9),
        log(2, 2, 18, 1),
        log(2, 2, 9, None),
        log(3, 3, 9, 1),
        log(3, 3, 9, 1),
        log(3, 3, 9, 0),
        log(4, 4, 12, 1),
    ])

    assert result['status'] == STATUS_LIMITED
    assert result['games_in_window'] == 4
    assert result['games_analyzed'] == 1
    assert result['games_excluded'] == 3
    assert result['excluded_game_reasons'] == {
        'unknown_split': 1,
        'multiple_starters': 1,
        'incomplete_outs': 1,
    }
    assert INCOMPLETE_GAME_DATA_LIMITATION in result['limitations']
    assert UNKNOWN_SPLIT_LIMITATION in result['limitations']
    assert MATERIAL_EXCLUSION_LIMITATION in result['limitations']


def test_percentage_and_innings_rounding_remain_stable():
    result = pressure([
        *game(1, 1, 13, 14),
        *game(2, 2, 13, 14),
        *game(3, 3, 13, 14),
        *game(4, 4, 13, 14),
        *game(5, 5, 13, 14),
        *game(6, 6, 13, 14),
    ])

    assert result['status'] == STATUS_HEAVY
    assert result['starter_outs'] == 78
    assert result['starter_innings'] == 26.0
    assert result['starter_avg_innings'] == 4.33
    assert result['bullpen_outs_required'] == 84
    assert result['bullpen_innings_required'] == 28.0
    assert result['short_start_rate'] == 1.0
    assert result['summary'] == (
        'The rotation averaged 4.3 innings per start over the last 7 days, '
        'requiring 28.0 bullpen innings.'
    )
