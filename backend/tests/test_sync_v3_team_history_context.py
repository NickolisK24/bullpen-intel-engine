from datetime import date, timedelta

from sync_v3.team_history_reads import calendar_events, confirmed_extra_innings


def test_off_day_needs_two_final_dates_and_a_verified_empty_calendar():
    day = date(2024, 7, 23)
    dates = {str(day - timedelta(days=n)): dict(games=[], reason=None) for n in range(7)}
    schedule = dict(gaps={}, dates={d: dict(games=[]) for d in dates})
    for offset in (0, 2):
        d = str(day - timedelta(days=offset))
        game = dict(game_pk=100 + offset, shape_reason=None, relief_outs=9,
                    rotation=dict(starter_outs=18, bullpen_outs_required=9, short_start=False))
        dates[d]['games'].append(game)
        schedule['dates'][d]['games'].append(dict(game_pk=game['game_pk'], status='final', official_date=d))
    rotation = dict(dates=dates)
    events, reason = calendar_events(day, rotation, schedule)
    assert reason is None and events[-1] == dict(date='2024-07-22', kind='off_day', game_pks=[100, 102])
    assert events[0]['week'] == dict(final_games=2, verified_games=2, bullpen_outs=18)
    dates['2024-07-18']['reason'] = 'missing_complete_schedule'
    schedule['gaps']['2024-07-22'] = 'previous_listing_requires_absence_proof'
    events, reason = calendar_events(day, rotation, schedule)
    assert reason == 'adjacent_calendar_unverified' and [e['kind'] for e in events] == ['game']
    assert events[0]['week'] == dict(final_games=None, verified_games=2, bullpen_outs=None)


def test_extra_innings_requires_final_evidence_against_scheduled_length():
    day = date(2024, 7, 26)
    game = dict(officialDate=str(day), scheduledInnings=7, gameType='R',
                teams={side: dict(team=dict(id=i)) for i, side in enumerate(('home', 'away'), 1)})
    lines = [dict(team_id=1, outs_recorded=24), dict(team_id=2, outs_recorded=21)]
    assert confirmed_extra_innings(game, lines, day) is True
    assert confirmed_extra_innings(dict(game, linescore=dict(currentInning=7)), lines, day) is None
    assert confirmed_extra_innings(dict(game, scheduledInnings=9), lines, day) is None
    nine = dict(game, scheduledInnings=9, linescore=dict(currentInning=9))
    assert confirmed_extra_innings(nine, lines, day) is None
    walkoff = [dict(team_id=1, outs_recorded=27), dict(team_id=2, outs_recorded=24)]
    assert confirmed_extra_innings(nine, walkoff, day) is False
    assert confirmed_extra_innings(dict(nine, linescore=dict(currentInning=10)), walkoff, day) is None
    assert confirmed_extra_innings(game, [lines[0], dict(team_id=2, outs_recorded=17)], day) is None
    impossible_tenth = [dict(team_id=1, outs_recorded=28), dict(team_id=2, outs_recorded=25)]
    assert confirmed_extra_innings(dict(game, scheduledInnings=9), impossible_tenth, day) is None
    assert confirmed_extra_innings(dict(game, resumeDate='2024-07-28'), lines, day) is None
    assert confirmed_extra_innings(game, lines[:1], day) is None
