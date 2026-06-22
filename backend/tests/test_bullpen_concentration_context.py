from datetime import date, timedelta
from types import SimpleNamespace

from services.bullpen_concentration_context import (
    CAPABILITY,
    build_bullpen_concentration_context,
    build_league_bullpen_concentration_baseline,
)


REF = date(2026, 6, 20)


def pitcher(player_id, name, team_id):
    return SimpleNamespace(
        id=player_id + 100000,
        mlb_id=player_id,
        full_name=name,
        team_id=team_id,
    )


def log(player_id, days_ago, pitches, *, team_id=1, games_started=0, outs=3, game_pk=None):
    return SimpleNamespace(
        pitcher_id=player_id + 100000,
        pitcher=pitcher(player_id, f'Pitcher {player_id}', team_id),
        mlb_game_pk=game_pk or (team_id * 100000 + player_id),
        game_date=REF - timedelta(days=days_ago),
        game_type='R',
        games_started=games_started,
        innings_pitched_outs=outs,
        innings_pitched=outs / 3.0,
        pitches_thrown=pitches,
    )


def context(logs, league_baseline=None):
    return build_bullpen_concentration_context(
        logs,
        reference_date=REF,
        league_baseline=league_baseline,
    )


def test_normal_bullpen_distribution_reads_normal_band():
    result = context([
        log(1, 1, 40),
        log(2, 1, 40),
        log(3, 2, 40),
        log(4, 2, 30),
        log(5, 3, 30),
        log(6, 4, 20),
    ])

    assert result['capability'] == CAPABILITY
    assert result['bullpen_workload_total_10d'] == 200
    assert result['top_three_workload_share_10d'] == 60.0
    assert result['concentration_band'] == 'normal'
    assert [row['player_id'] for row in result['top_three_relievers_10d']] == [1, 2, 3]


def test_highly_concentrated_bullpen_reads_narrow_band():
    result = context([
        log(1, 1, 80),
        log(2, 1, 70),
        log(3, 2, 50),
        log(4, 3, 20),
        log(5, 4, 10),
    ])

    assert result['bullpen_workload_total_10d'] == 230
    assert result['top_three_workload_share_10d'] == 87.0
    assert result['concentration_band'] == 'narrow'
    assert result['top_three_relievers_10d'][0] == {
        'player_id': 1,
        'name': 'Pitcher 1',
        'workload_share': 34.8,
        'pitches': 80,
        'appearances': 1,
    }


def test_balanced_bullpen_distribution_reads_balanced_band():
    result = context([
        log(1, 1, 40),
        log(2, 1, 30),
        log(3, 2, 20),
        log(4, 2, 20),
        log(5, 3, 20),
        log(6, 4, 20),
        log(7, 5, 20),
    ])

    assert result['bullpen_workload_total_10d'] == 170
    assert result['top_three_workload_share_10d'] == 52.9
    assert result['concentration_band'] == 'balanced'


def test_concentrated_bullpen_distribution_reads_concentrated_band():
    result = context([
        log(1, 1, 60),
        log(2, 1, 50),
        log(3, 2, 40),
        log(4, 3, 40),
        log(5, 4, 30),
    ])

    assert result['bullpen_workload_total_10d'] == 220
    assert result['top_three_workload_share_10d'] == 68.2
    assert result['concentration_band'] == 'concentrated'


def test_team_with_fewer_than_three_qualifying_relievers_is_safe():
    result = context([
        log(1, 1, 20),
        log(2, 2, 10),
    ])

    assert result['qualifying_reliever_count_10d'] == 2
    assert len(result['top_three_relievers_10d']) == 2
    assert result['top_three_workload_share_10d'] == 100.0
    assert result['concentration_band'] == 'narrow'


def test_zero_pitch_artifacts_and_starter_workload_are_excluded():
    result = context([
        log(1, 1, 20),
        log(2, 1, 90, games_started=1, outs=18),
        log(3, 2, 0, outs=0),
        log(4, 2, 10),
    ])

    assert result['bullpen_workload_total_10d'] == 30
    assert result['bullpen_workload_appearances_10d'] == 2
    assert result['excluded_starting_workload_rows_10d'] == 1
    assert result['zero_pitch_artifact_rows_excluded_10d'] == 1
    assert result['excluded_row_reasons'] == {
        'starter_workload': 1,
        'zero_pitch_artifact': 1,
    }


def test_league_baseline_and_delta_are_calculated_from_team_shares():
    team_one = [
        log(1, 1, 40, team_id=1),
        log(2, 1, 40, team_id=1),
        log(3, 2, 40, team_id=1),
        log(4, 2, 30, team_id=1),
        log(5, 3, 30, team_id=1),
        log(6, 4, 20, team_id=1),
    ]
    team_two = [
        log(11, 1, 80, team_id=2),
        log(12, 1, 60, team_id=2),
        log(13, 2, 40, team_id=2),
        log(14, 3, 20, team_id=2),
    ]
    baseline = build_league_bullpen_concentration_baseline(
        [*team_one, *team_two],
        reference_date=REF,
    )

    assert baseline['league_top_three_workload_share_10d'] == 75.0
    assert baseline['league_team_count_10d'] == 2
    distribution = baseline['top_three_workload_share_distribution_10d']
    assert distribution['sample_count'] == 2
    assert round(distribution['mean'], 1) == 75.0

    result = context(team_two, league_baseline=baseline)
    assert result['top_three_workload_share_10d'] == 90.0
    assert result['league_top_three_workload_share_10d'] == 75.0
    assert result['top_three_share_delta_vs_league'] == 15.0


_LEAGUE_DISTRIBUTION = {
    'league_top_three_workload_share_10d': 48.0,
    'league_team_count_10d': 28,
    'top_three_workload_share_distribution_10d': {
        'sample_count': 28, 'mean': 48.0, 'median': 50.0,
        'p10': 38.0, 'p25': 42.0, 'p75': 58.0, 'p90': 66.0,
    },
}


def test_baseline_read_interprets_team_value_against_league_distribution():
    # Three arms carry nearly all the work -> top-three share at/above p90.
    result = context(
        [log(1, 1, 80), log(2, 1, 10), log(3, 1, 10), log(4, 2, 5)],
        league_baseline=_LEAGUE_DISTRIBUTION,
    )
    read = result['baseline_read']
    assert read['available'] is True
    assert read['metric'] == 'top_share'
    assert read['comparison'] == 'among_highest'
    assert read['direction'] == 'higher'


def test_baseline_read_guards_on_thin_league_sample():
    thin = {
        'league_top_three_workload_share_10d': 90.0,
        'league_team_count_10d': 1,
        'top_three_workload_share_distribution_10d': {
            'sample_count': 1, 'mean': 90.0, 'median': 90.0,
            'p10': 90.0, 'p25': 90.0, 'p75': 90.0, 'p90': 90.0,
        },
    }
    result = context([log(1, 1, 80), log(2, 1, 10), log(3, 1, 10)], league_baseline=thin)
    assert result['baseline_read']['available'] is False
    assert result['baseline_read']['comparison'] == 'insufficient_sample'


def test_baseline_read_without_distribution_degrades_gracefully():
    # A legacy-shaped league baseline (no distribution) must not crash the context.
    result = context(
        [log(1, 1, 80), log(2, 1, 10), log(3, 1, 10)],
        league_baseline={'league_top_three_workload_share_10d': 50.0},
    )
    assert result['baseline_read']['available'] is False


def test_doubleheader_workload_aggregation_counts_distinct_appearances():
    result = context([
        log(1, 1, 12, game_pk=101),
        log(1, 1, 13, game_pk=102),
        log(2, 1, 10, game_pk=101),
        log(3, 2, 5, game_pk=103),
        log(4, 3, 5, game_pk=104),
    ])

    assert result['bullpen_workload_total_10d'] == 45
    assert result['bullpen_workload_appearances_10d'] == 5
    assert result['top_three_relievers_10d'][0]['player_id'] == 1
    assert result['top_three_relievers_10d'][0]['pitches'] == 25
    assert result['top_three_relievers_10d'][0]['appearances'] == 2
    assert result['top_three_workload_share_10d'] == 88.9
