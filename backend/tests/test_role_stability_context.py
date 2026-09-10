from datetime import date, timedelta
from types import SimpleNamespace

from services.role_stability_context import (
    CAPABILITY,
    build_role_stability_context,
)


REF = date(2026, 6, 20)


NAMES = {
    1: 'Alpha Arm',
    2: 'Bravo Arm',
    3: 'Charlie Arm',
    4: 'Delta Arm',
    5: 'Echo Arm',
    6: 'Foxtrot Arm',
    7: 'Golf Arm',
    8: 'Hotel Arm',
    9: 'India Arm',
}


def pitcher(player_id, team_id=1):
    return SimpleNamespace(
        id=player_id + 100000,
        mlb_id=player_id,
        full_name=NAMES.get(player_id, f'Pitcher {player_id}'),
        team_id=team_id,
    )


def log(
    player_id,
    days_ago,
    pitches,
    *,
    team_id=1,
    games_started=0,
    outs=3,
    game_pk=None,
):
    return SimpleNamespace(
        pitcher_id=player_id + 100000,
        pitcher=pitcher(player_id, team_id=team_id),
        mlb_game_pk=game_pk or (team_id * 100000 + player_id + days_ago),
        game_date=REF - timedelta(days=days_ago),
        game_type='R',
        games_started=games_started,
        innings_pitched_outs=outs,
        innings_pitched=outs / 3.0,
        pitches_thrown=pitches,
    )


def context(logs):
    return build_role_stability_context(logs, reference_date=REF)


def test_fully_stable_core_reads_stable():
    result = context([
        log(1, 1, 50),
        log(2, 2, 40),
        log(3, 3, 30),
        log(4, 4, 20),
        log(1, 11, 45),
        log(2, 12, 35),
        log(3, 13, 25),
        log(5, 14, 10),
    ])

    assert result['capability'] == CAPABILITY
    assert result['context_available'] is True
    assert result['current_operational_core'] == ['Alpha Arm', 'Bravo Arm', 'Charlie Arm']
    assert result['previous_operational_core'] == ['Alpha Arm', 'Bravo Arm', 'Charlie Arm']
    assert result['core_retention_count'] == 3
    assert result['core_stability_pct'] == 100
    assert result['core_change_count'] == 0
    assert result['stability_band'] == 'stable'
    assert result['new_core_members'] == []
    assert result['departed_core_members'] == []
    assert result['role_stability_summary_inputs'] == {
        'current_core': ['Alpha Arm', 'Bravo Arm', 'Charlie Arm'],
        'previous_core': ['Alpha Arm', 'Bravo Arm', 'Charlie Arm'],
        'retention_count': 3,
        'stability_pct': 100,
        'change_count': 0,
        'band': 'stable',
    }


def test_one_member_change_reads_mostly_stable():
    result = context([
        log(1, 1, 50),
        log(2, 2, 40),
        log(4, 3, 30),
        log(5, 4, 10),
        log(1, 11, 45),
        log(2, 12, 35),
        log(3, 13, 25),
        log(6, 14, 10),
    ])

    assert result['current_operational_core'] == ['Alpha Arm', 'Bravo Arm', 'Delta Arm']
    assert result['previous_operational_core'] == ['Alpha Arm', 'Bravo Arm', 'Charlie Arm']
    assert result['core_retention_count'] == 2
    assert result['core_stability_pct'] == 67
    assert result['core_change_count'] == 1
    assert result['stability_band'] == 'mostly_stable'
    assert result['new_core_members'] == ['Delta Arm']
    assert result['departed_core_members'] == ['Charlie Arm']


def test_two_member_change_reads_transitioning():
    result = context([
        log(1, 1, 50),
        log(4, 2, 40),
        log(5, 3, 30),
        log(7, 4, 10),
        log(1, 11, 45),
        log(2, 12, 35),
        log(3, 13, 25),
        log(6, 14, 10),
    ])

    assert result['current_operational_core'] == ['Alpha Arm', 'Delta Arm', 'Echo Arm']
    assert result['previous_operational_core'] == ['Alpha Arm', 'Bravo Arm', 'Charlie Arm']
    assert result['core_retention_count'] == 1
    assert result['core_stability_pct'] == 33
    assert result['core_change_count'] == 2
    assert result['stability_band'] == 'transitioning'
    assert result['new_core_members'] == ['Delta Arm', 'Echo Arm']
    assert result['departed_core_members'] == ['Bravo Arm', 'Charlie Arm']


def test_complete_turnover_reads_rebuilding():
    result = context([
        log(4, 1, 50),
        log(5, 2, 40),
        log(6, 3, 30),
        log(7, 4, 10),
        log(1, 11, 45),
        log(2, 12, 35),
        log(3, 13, 25),
        log(8, 14, 10),
    ])

    assert result['current_operational_core'] == ['Delta Arm', 'Echo Arm', 'Foxtrot Arm']
    assert result['previous_operational_core'] == ['Alpha Arm', 'Bravo Arm', 'Charlie Arm']
    assert result['core_retention_count'] == 0
    assert result['core_stability_pct'] == 0
    assert result['core_change_count'] == 3
    assert result['stability_band'] == 'rebuilding'
    assert result['new_core_members'] == ['Delta Arm', 'Echo Arm', 'Foxtrot Arm']
    assert result['departed_core_members'] == ['Alpha Arm', 'Bravo Arm', 'Charlie Arm']


def test_zero_pitch_artifacts_and_starters_are_excluded():
    result = context([
        log(1, 1, 20),
        log(2, 1, 90, games_started=1, outs=18),
        log(3, 2, 0, outs=0),
        log(1, 11, 18),
    ])

    assert result['current_operational_core'] == ['Alpha Arm']
    assert result['previous_operational_core'] == ['Alpha Arm']
    assert result['current_workload_total_10d'] == 20
    assert result['previous_workload_total_10d'] == 18
    assert result['excluded_starting_workload_rows_20d'] == 1
    assert result['zero_pitch_artifact_rows_excluded_20d'] == 1
    assert result['excluded_row_reasons'] == {
        'starter_workload': 1,
        'zero_pitch_artifact': 1,
    }
    assert result['stability_band'] == 'stable'


def test_off_days_do_not_break_window_comparison():
    result = context([
        log(1, 3, 22),
        log(2, 4, 18),
        log(3, 5, 15),
        log(1, 13, 20),
        log(2, 14, 17),
        log(3, 15, 14),
    ])

    assert result['current_window_end_10d'] == '2026-06-20'
    assert result['current_operational_core'] == ['Alpha Arm', 'Bravo Arm', 'Charlie Arm']
    assert result['previous_operational_core'] == ['Alpha Arm', 'Bravo Arm', 'Charlie Arm']
    assert result['core_stability_pct'] == 100
    assert result['stability_band'] == 'stable'


def test_doubleheader_workload_aggregates_without_duplicate_core_members():
    result = context([
        log(1, 1, 12, game_pk=101),
        log(1, 1, 13, game_pk=102),
        log(2, 1, 20, game_pk=101),
        log(3, 2, 15, game_pk=103),
        log(1, 11, 10, game_pk=201),
        log(1, 11, 12, game_pk=202),
        log(2, 12, 20, game_pk=203),
        log(3, 13, 15, game_pk=204),
    ])

    assert result['current_operational_core'] == ['Alpha Arm', 'Bravo Arm', 'Charlie Arm']
    assert result['previous_operational_core'] == ['Alpha Arm', 'Bravo Arm', 'Charlie Arm']
    assert result['current_workload_total_10d'] == 60
    assert result['previous_workload_total_10d'] == 57
    assert result['core_retention_count'] == 3
    assert result['stability_band'] == 'stable'


def test_small_bullpen_sample_handles_fewer_than_three_core_members():
    result = context([
        log(1, 1, 20),
        log(4, 2, 15),
        log(1, 11, 18),
        log(2, 12, 16),
    ])

    assert result['current_operational_core'] == ['Alpha Arm', 'Delta Arm']
    assert result['previous_operational_core'] == ['Alpha Arm', 'Bravo Arm']
    assert result['current_core_size'] == 2
    assert result['previous_core_size'] == 2
    assert result['core_retention_count'] == 1
    assert result['core_stability_pct'] == 50
    assert result['core_change_count'] == 1
    assert result['stability_band'] == 'transitioning'
    assert result['new_core_members'] == ['Delta Arm']
    assert result['departed_core_members'] == ['Bravo Arm']
