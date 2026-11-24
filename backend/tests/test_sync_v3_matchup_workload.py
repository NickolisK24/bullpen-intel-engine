from datetime import date

import pytest

from services.public_team_relief_work import WORKLOAD_WINDOWS_POPULATION_BASIS, WORKLOAD_WINDOWS_REFERENCE_DATE_POLICY
from sync_v3 import readiness
from sync_v3.product_reads import _board_date_rest, _matchup_workload


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


THROUGH = date(2017, 8, 28)
REFERENCE = date(2017, 8, 29)


def arm(days, back_to_back=False):
    return dict(read=dict(availability=dict(data_state='fresh', inputs=dict(
        days_rest=days, back_to_back=back_to_back))))


def test_departure_is_excluded_from_board_rest_without_rewriting_team_state(monkeypatch):
    report = dict(team=111, reference_date=str(REFERENCE), arms={1: arm(1, True), 2: arm(4)})
    rosters = {THROUGH: {1, 2}, REFERENCE: {2}}
    monkeypatch.setattr(readiness, 'board_rest_pitchers', lambda cur, club, day: rosters[day])
    rest = readiness.availability_day_rest(None, report, THROUGH)
    assert (rest['active_arm_count'], rest['rested_arm_count'], rest['back_to_back_count']) == (1, 1, 0)
    assert set(report['arms']) == {1, 2}


def test_new_arm_requires_qualified_evidence_at_the_original_workload_cutoff(monkeypatch):
    report = dict(team=111, reference_date=str(REFERENCE), arms={1: arm(4)})
    monkeypatch.setattr(readiness, 'board_rest_pitchers',
                        lambda cur, club, day: {1, 2} if day == REFERENCE else {1})
    monkeypatch.setattr(readiness, 'competition_status', lambda cur, day: {})

    def recalculate(cur, team, through, reference, league, *, roster_day):
        assert (team, through, reference, roster_day) == (111, THROUGH, REFERENCE, REFERENCE)
        return dict(reason='missing_round_game_log', arms={1: arm(4)})

    monkeypatch.setattr(readiness, '_club_readiness', recalculate)
    rest = readiness.availability_day_rest(None, report, THROUGH)
    assert rest['reason_code'] == 'roster_context_unavailable' and rest['active_arm_count'] is None


@pytest.mark.parametrize('facts,reason', [
    ({'arms': {1: arm(1)}}, 'roster_context_unavailable'),
    ({'board_date_rest': {'available': True}}, 'frozen_rest_status_invalid'),
])
def test_unqualified_frozen_generations_cannot_publish_rest_counts(facts, reason):
    rest = _board_date_rest(facts)
    assert rest['reason_code'] == reason and rest['worked_yesterday_count'] is None


def test_hydrated_active_roster_cannot_contradict_the_plain_response(monkeypatch):
    from types import SimpleNamespace
    from sync_v3 import depth

    day = REFERENCE
    body = dict(teamId=111, rosterType='active', roster=[
        dict(person=dict(id=7), position=dict(code='1'), status=dict(code='A'), parentTeamId=111),
    ])
    monkeypatch.setattr(depth, 'roster_on', lambda cur, team, kind, day: ({}, 1))
    monkeypatch.setattr(depth, 'replay', lambda cur, source: SimpleNamespace(body=body))
    monkeypatch.setattr(depth, 'latest_source_status', lambda cur, endpoint, params: (2, 'received', None))
    monkeypatch.setattr(depth, '_view', lambda *args: dict(pitchers={8: dict(status_codes=['A'])}))
    assert depth.board_rest_pitchers(None, 111, day) is None
