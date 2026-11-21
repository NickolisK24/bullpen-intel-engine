from datetime import date

import pytest

from services.public_team_relief_work import WORKLOAD_WINDOWS_POPULATION_BASIS, WORKLOAD_WINDOWS_REFERENCE_DATE_POLICY
from sync_v3.product_reads import _matchup_workload


@pytest.fixture
def snapshot():
    zero = dict(status='complete', value=0)
    week = dict(start='2024-08-01', through='2024-08-07', appearances=zero, pitches=zero, outs=zero)
    overview = dict(data_through=week['through'], windows=dict(window_7=week),
                    window_policy=WORKLOAD_WINDOWS_REFERENCE_DATE_POLICY, population_basis=WORKLOAD_WINDOWS_POPULATION_BASIS,
                    concentration_7_day=dict(status='complete', pitcher_count=0))
    return dict(windows=dict(workload=overview, compared_windows=['window_7']))


def test_observed_idle_week_preserves_zero_and_unknown_pitches_remain_unknown(snapshot):
    day = date(2024, 8, 7)
    assert _matchup_workload(snapshot, day) == dict(window_days=7, relief_appearances=0, pitches=0,
                                                    contributing_relievers=0, innings='0.0')
    overview = snapshot['windows']['workload']
    overview['windows']['window_7'].update(appearances=dict(status='complete', value=1),
                                          pitches=dict(status='unavailable', value=None), outs=dict(status='complete', value=2))
    overview['concentration_7_day'] = dict(status='unavailable', pitcher_count=None)
    assert _matchup_workload(snapshot, day) == dict(window_days=7, relief_appearances=1, pitches=None,
                                                    contributing_relievers=None, innings='0.2')


def test_matchup_workload_requires_compared_window_and_official_club_scope(snapshot):
    day = date(2024, 8, 7)
    assert _matchup_workload(snapshot, date(2024, 8, 8)) is None
    snapshot['windows']['compared_windows'] = []
    assert _matchup_workload(snapshot, day) is None
    snapshot['windows']['compared_windows'] = ['window_7']
    snapshot['windows']['workload']['population_basis'] = 'current_active_only'
    assert _matchup_workload(snapshot, day) is None


def test_game_date_controls_both_sides_of_the_rest_comparison():
    from sync_v3.product_reads import _matchup_rest

    counts = dict(rested_arm_count=0, worked_yesterday_count=1, back_to_back_count=0)
    side = dict(rest=counts, rest_reference_date='2024-08-08')
    for away, home in ((side, dict(side, rest_reference_date='2024-08-07')),
                       (dict(side, rest_reference_date='2024-08-07'), side)):
        result = _matchup_rest(away, home, '2024-08-08')
        assert result['reason_code'] == 'rest_reference_date_mismatch'
        assert result['team_a'] is None and result['team_b'] is None
    assert _matchup_rest(side, dict(side, rest=None), '2024-08-08')['status'] == 'withheld'


def test_competitive_matchup_projects_the_board_counts_and_withholds_an_unobserved_week(snapshot):
    from sync_v3.product_reads import _seven_day_side

    overview = snapshot['windows']['workload']
    week = overview['windows']['window_7']
    for field, value in [('appearances', 18), ('outs', 47), ('pitches', 245)]:
        week[field] = dict(status='complete', value=value)
    overview['concentration_7_day'] = dict(status='unavailable', pitcher_count=None)
    assert _seven_day_side(overview, 8) == dict(window_days=7, relief_appearances=18, pitches=245,
                                             contributing_relievers=8, innings='15.2')
    for field in ('appearances', 'pitches', 'outs'):
        week[field] = dict(status='unavailable', value=None, reason_codes=['missing_game'])
    assert _seven_day_side(overview, None) is None


def test_competitive_save_work_uses_qualified_club_relief_and_exact_fourteen_day_window():
    from sync_v3.product_reads import _competitive_saves

    week = dict(through='2026-10-18', start='2026-10-05', appearances=dict(status='complete', value=4))
    view = dict(data_through=week['through'], windows=dict(window_14=week))
    lines = [dict(mlb_id=1, game_date='2026-10-04', save=1), dict(mlb_id=1, game_date='2026-10-05', save=1),
             dict(mlb_id=2, game_date='2026-10-12', save=1), dict(mlb_id=2, game_date='2026-10-18', save=None),
             dict(mlb_id=3, game_date='2026-10-18', save=0)]
    for pk, line in enumerate(lines, start=1):
        line['game_pk'] = pk
    assert _competitive_saves(view, lines) == {1: 1, 3: 0}
    assert _competitive_saves(view, [*lines[:-1], lines[-2]]) == {}
    assert _competitive_saves(view, lines[2:]) == {}
    week['appearances']['status'] = 'partial'
    assert _competitive_saves(view, lines) == {}
