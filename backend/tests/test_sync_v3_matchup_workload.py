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
