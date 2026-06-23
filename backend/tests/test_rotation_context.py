from datetime import date, timedelta

from services.rotation_context import (
    CAPABILITY,
    INCOMPLETE_GAME_DATA_LIMITATION,
    OPENER_BULK_LIMITATION,
    build_league_rotation_baseline,
    build_rotation_context,
    rotation_length_baseline_read,
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


def team_log(team_id, game_pk, days_ago, outs, games_started):
    row = log(game_pk, days_ago, outs, games_started)
    row['team_id'] = team_id
    return row


def team_game(team_id, game_pk, days_ago, starter_outs, relief_outs=None):
    rows = [team_log(team_id, game_pk, days_ago, starter_outs, 1)]
    if relief_outs is not None:
        rows.append(team_log(team_id, game_pk, days_ago, relief_outs, 0))
    return rows


# Current 7-day-window league distribution of rotation_avg_ip_7d: a typical
# rotation runs ~5.2 innings, so 4.0 is short and 6.2 is among the longer.
_LEAGUE_ROTATION = {
    'rotation_avg_ip_7d_distribution': {
        'sample_count': 28, 'mean': 5.2, 'median': 5.3,
        'p10': 4.2, 'p25': 4.8, 'p75': 5.7, 'p90': 6.1,
    },
    'league_team_count': 28,
}


def test_league_rotation_baseline_builds_distribution_from_team_values():
    logs = [
        *team_game(1, 101, 1, 18), *team_game(1, 102, 2, 18),  # 6.0 IP
        *team_game(2, 201, 1, 12), *team_game(2, 202, 2, 12),  # 4.0 IP
        *team_game(3, 301, 1, 15), *team_game(3, 302, 2, 15),  # 5.0 IP
    ]

    baseline = build_league_rotation_baseline(logs, reference_date=REF)

    assert baseline['league_team_count'] == 3
    distribution = baseline['rotation_avg_ip_7d_distribution']
    assert distribution['sample_count'] == 3
    assert round(distribution['mean'], 1) == 5.0
    assert distribution['median'] == 5.0


def test_league_rotation_baseline_skips_teams_without_a_seven_day_value():
    logs = [
        *team_game(1, 101, 1, 18), *team_game(1, 102, 2, 18),  # 6.0 IP (in 7d)
        *team_game(2, 201, 10, 18),  # only a game 10 days ago -> no 7d value
    ]

    baseline = build_league_rotation_baseline(logs, reference_date=REF)

    assert baseline['league_team_count'] == 1
    assert baseline['rotation_avg_ip_7d_distribution']['sample_count'] == 1


def test_rotation_length_baseline_read_marks_short_rotation_below_norm():
    read = rotation_length_baseline_read(4.0, _LEAGUE_ROTATION)

    assert read['available'] is True
    assert read['metric'] == 'rotation_avg_ip_7d'
    assert read['comparison'] == 'below_average'
    assert read['value'] == 4.0


def test_rotation_length_baseline_read_marks_long_rotation_above_norm():
    read = rotation_length_baseline_read(5.5, _LEAGUE_ROTATION)

    assert read['available'] is True
    assert read['comparison'] == 'above_average'


def test_rotation_length_baseline_read_guards_on_thin_league_sample():
    thin = {
        'rotation_avg_ip_7d_distribution': {
            'sample_count': 3, 'mean': 5.0, 'median': 5.0,
            'p10': 4.5, 'p25': 4.8, 'p75': 5.2, 'p90': 5.5,
        },
        'league_team_count': 3,
    }

    read = rotation_length_baseline_read(4.0, thin)

    assert read['available'] is False
    assert read['comparison'] == 'insufficient_sample'


def test_rotation_length_baseline_read_without_distribution_degrades_gracefully():
    assert rotation_length_baseline_read(4.0, {'league_team_count': 5})['available'] is False
    assert rotation_length_baseline_read(None, None)['available'] is False
