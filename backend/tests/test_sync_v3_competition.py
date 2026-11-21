from datetime import date
from types import SimpleNamespace

import pytest

from services.mlb_club_directory import MLB_TEAM_IDS
from sync_v3 import competition_calendar as competition
from sync_v3.discovery import competition_calendar_request


def game(pk, home, away, day, kind='R'):
    return {'gamePk': pk, 'officialDate': day, 'gameType': kind, 'season': '2024', 'gamesInSeries': 7,
            'status': {'abstractGameState': 'Final', 'detailedState': 'Final', 'statusCode': 'F'},
            'teams': {'home': {'team': {'id': home}, 'score': 4, 'isWinner': True},
                      'away': {'team': {'id': away}, 'score': 2, 'isWinner': False}}}


def season():
    teams = sorted(MLB_TEAM_IDS)
    day = '2024-09-29'
    regular = [game(i + 1, home, away, day) for i, (home, away) in enumerate(zip(teams[::2], teams[1::2]))]
    dates = [{'date': day, 'totalGames': 15, 'games': regular}]
    for n in range(4):
        day = f'2024-10-{22+n}'
        dates.append({'date': day, 'totalGames': 1, 'games': [game(100+n, 119, 147, day, 'W')]})
    return {'totalGames': 19, 'dates': dates}


def test_calendar_rejects_partial_and_conflicting_relistings():
    params = competition_calendar_request(2024).params()
    fixture = season()
    fixture['totalGames'] -= 1
    with pytest.raises(ValueError, match='coverage'):
        competition.calendar_games(params, fixture)
    fixture = season()
    extra = game(100, 119, 147, '2024-10-26', 'W')
    extra['gamesInSeries'] = 5
    fixture['dates'].append({'date': extra['officialDate'], 'totalGames': 1, 'games': [extra]})
    fixture['totalGames'] += 1
    with pytest.raises(ValueError, match='playoff format'):
        competition.calendar_games(params, fixture)


def test_world_series_requires_four_prior_compatible_official_wins(monkeypatch):
    from sync_v3 import evidence, workload

    fixture = season()
    monkeypatch.setattr(evidence, 'latest_qualified_source', lambda cur, ep, params: params.get('startDate', 99))
    by_day = {item['date']: item for item in fixture['dates']}
    monkeypatch.setattr(evidence, 'replay', lambda cur, source: SimpleNamespace(
        body=fixture if source == 99 else {'dates': [by_day[source]]}))
    winning_club = {100: 119, 101: 119, 102: 119, 103: 147}
    def final(cur, listing, day, source):
        pk = listing['gamePk']
        return ([{'team_id': winning_club[pk], 'win': True}], (source, source)), None
    monkeypatch.setattr(workload, '_game_workload', final)
    before = competition.competition_status(None, date(2024, 10, 25))
    assert len(before['decision_sources']) == 3 and before['clubs'][119]['status'] == 'active'
    assert before['reference_slate_source'] == '2024-10-25'
    after = competition.competition_status(None, date(2024, 10, 26))
    assert after['missing_decisions'] == [103]
    assert after['clubs'][119]['status'] == 'undetermined'
    winning_club[103] = 119
    result = competition.competition_status(None, date(2024, 10, 26))
    assert {item['basis'] for item in result['clubs'].values()} == {'world_series_decided'}
    assert len(result['clubs']) == 30 and len(result['decision_sources']) == 4
    assert result['retrospective']


def test_calendar_never_enqueues_season_of_daily_writers():
    from sync_v3.cycle import plan_children
    acquisition = SimpleNamespace(request=competition_calendar_request(2024))
    assert plan_children(None, 1, acquisition, 'historical', None, None) is None


def test_arm_requires_recent_game_identity_and_matching_work_including_prior_club():
    from sync_v3.readiness import _represented_arm

    reference = date(2024, 8, 8)
    split = {'game': {'gamePk': 9}, 'team': {'id': 133}, 'date': '2024-08-06',
             'stat': {'outs': 3, 'numberOfPitches': 14}}
    row = {'pitcher_mlb_id': 42, 'game_pk': 9, 'team_id': 133, 'game_date': '2024-08-06',
           'pitches_thrown': 14, 'outs_recorded': 3}
    arm, reason = _represented_arm(42, [split], [row], reference)
    assert reason is None and arm['games_compared'] == [9]
    assert arm['availability']['inputs']['days_rest'] == 2
    assert _represented_arm(42, [], [row], reference)[1] == 'game_log_and_final_population_conflict'
    assert _represented_arm(42, [split], [dict(row, pitches_thrown=None)], reference)[0] is None
    assert _represented_arm(42, [], [], reference)[1] == 'no_recent_verified_workload'


def test_complete_club_withholds_before_reading_a_roster(monkeypatch):
    from sync_v3 import readiness

    monkeypatch.setattr(readiness, 'competition_status', lambda cur, ref: {
        'calendar_source': 123, 'decision_sources': {}, 'missing_decisions': [], 'reference_slate_source': None,
        'clubs': {111: {'status': 'season_complete', 'basis': 'world_series_decided'}}})
    result = readiness.represented_readiness(None, 111, date(2024, 11, 29))
    assert result['reason'] == 'world_series_decided' and result['team_state'] is None and not result['arms']
    assert result['membership_date'] == '2024-11-29' and result['reference_date'] == '2024-11-30'
    assert result['current_serving_eligible'] is False


def test_missing_or_refused_latest_calendar_withholds_all_clubs(monkeypatch):
    from sync_v3 import evidence
    monkeypatch.setattr(evidence, 'latest_qualified_source', lambda cur, endpoint, params: None)
    result = competition.competition_status(None, date(2024, 11, 30))
    assert result['calendar_source'] is None and result['decision_sources'] == {}
    assert len(result['clubs']) == 30
    assert {club['status'] for club in result['clubs'].values()} == {'undetermined'}


def test_readiness_comparison_does_not_certify_a_withheld_or_misclassified_arm():
    from sync_v3.comparison import compare_readiness

    report = {'team_state': None, 'arms': {7: {'read': None}}}
    assert compare_readiness(report) == {'arm_statuses_compared': 0, 'team_states_compared': 0, 'withheld_arms': 1}
    report['arms'][7]['read'] = {'availability': {'data_state': 'fresh', 'availability_status': 'Available',
                                                'inputs': {'freshness_state': 'fresh', 'pitches_yesterday': 100}}}
    with pytest.raises(ValueError, match='arm status for 7'):
        compare_readiness(report)
