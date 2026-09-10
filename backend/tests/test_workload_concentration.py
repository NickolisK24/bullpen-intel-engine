"""Tests for league-wide workload concentration aggregation + baseline outputs."""

from datetime import date, timedelta
from types import SimpleNamespace

from services.workload_concentration import (
    RECENT_WORKLOAD_WINDOW_DAYS,
    build_workload_concentration_baselines,
    league_relief_workload_by_team,
    recent_relief_pitch_totals,
    summarize_workload_concentration,
)

REF = date(2026, 6, 22)


def _log(days_ago, pitches, games_started=0):
    # Object-shaped log: is_relief() reads .games_started via getattr.
    return SimpleNamespace(
        game_date=REF - timedelta(days=days_ago),
        pitches_thrown=pitches,
        games_started=games_started,
    )


def test_league_relief_workload_by_team_computes_per_team_shares():
    logs = {
        1: [_log(1, 30)], 2: [_log(1, 10)], 3: [_log(1, 10)],   # Team 100: total 50
        4: [_log(2, 20)], 5: [_log(2, 20)], 6: [_log(2, 10)],   # Team 200: total 50
    }
    result = league_relief_workload_by_team({100: [1, 2, 3], 200: [4, 5, 6]}, logs, REF)
    by_team = {row['team_id']: row for row in result}

    assert by_team[100]['total_pitches'] == 50
    assert by_team[100]['participant_count'] == 3
    assert by_team[100]['top_share'] == 1.0            # only three arms -> top-3 is everything
    assert round(by_team[100]['top_one_share'], 4) == 0.6   # 30 / 50
    assert round(by_team[200]['top_one_share'], 4) == 0.4   # 20 / 50


def test_league_excludes_teams_without_relief_workload():
    logs = {1: [_log(1, 30)], 2: []}
    result = league_relief_workload_by_team({100: [1], 200: [2]}, logs, REF)
    assert {row['team_id'] for row in result} == {100}


def test_league_excludes_starts_from_relief_workload():
    # A start (games_started=1) is not relief, so the team has no relief workload.
    logs = {1: [_log(1, 30, games_started=1)]}
    assert league_relief_workload_by_team({100: [1]}, logs, REF) == []


def test_league_ignores_none_team_id():
    logs = {1: [_log(1, 30)]}
    result = league_relief_workload_by_team({None: [1], 100: [1]}, logs, REF)
    assert {row['team_id'] for row in result} == {100}


def test_recent_relief_totals_preserve_unknown_pitch_counts():
    logs = {
        1: [_log(1, None)],
        2: [_log(1, 0)],
        3: [_log(1, 18)],
    }

    result = recent_relief_pitch_totals(logs, REF)

    assert result[1] is None
    assert result[2] == 0
    assert result[3] == 18


def test_workload_concentration_marks_unknown_pitch_counts_unavailable():
    result = summarize_workload_concentration({
        1: None,
        2: 0,
        3: 18,
    })

    assert result['unknown_pitch_count'] is True
    assert result['pitch_by_pitcher'][1] is None
    assert result['pitch_by_pitcher'][2] == 0
    assert result['total_pitches'] is None
    assert result['top_share'] is None
    assert result['per_arm_pitches'] is None


def test_league_excludes_teams_with_unknown_relief_pitch_counts():
    logs = {
        1: [_log(1, None)],
        2: [_log(1, 20)],
    }

    result = league_relief_workload_by_team({100: [1], 200: [2]}, logs, REF)

    assert {row['team_id'] for row in result} == {200}


def test_build_workload_concentration_baselines_distributions():
    per_team = [
        {'team_id': 1, 'top_share': 0.4, 'top_one_share': 0.2},
        {'team_id': 2, 'top_share': 0.6, 'top_one_share': 0.3},
        {'team_id': 3, 'top_share': 0.8, 'top_one_share': 0.5},
    ]
    block = build_workload_concentration_baselines(per_team)

    assert block['metric_family'] == 'workload_concentration'
    assert block['window_days'] == RECENT_WORKLOAD_WINDOW_DAYS
    assert block['sample_count'] == 3

    top_share = block['metrics']['top_share']
    assert top_share['sample_count'] == 3
    assert round(top_share['mean'], 6) == 0.6
    assert top_share['median'] == 0.6
    for percentile in ('p10', 'p25', 'p75', 'p90'):
        assert percentile in top_share

    top_one = block['metrics']['top_one_share']
    assert top_one['sample_count'] == 3
    assert round(top_one['mean'], 6) == round((0.2 + 0.3 + 0.5) / 3, 6)


def test_build_workload_concentration_baselines_empty_sample():
    block = build_workload_concentration_baselines([])
    assert block['sample_count'] == 0
    for metric_key in ('top_share', 'top_one_share'):
        dist = block['metrics'][metric_key]
        assert dist['sample_count'] == 0
        assert dist['mean'] is None
        assert dist['p90'] is None
