from datetime import date, datetime, timezone

import pytest

from sync_v3.discovery import calendar_requests, game_requests, roster_requests


DAY = date(2026, 9, 10)
NOW = datetime(2026, 9, 10, 17, tzinfo=timezone.utc)


def test_quiet_day_still_checks_rosters_and_transactions():
    assert game_requests(DAY, {'totalGames': 0, 'dates': []}, now=NOW) == ()
    assert {r.endpoint for r in calendar_requests(DAY)} == {'/transactions', '/schedule'}
    assert {r.params()['rosterType'] for r in roster_requests(DAY, [111])} == {
        'active', '40Man', 'fullRoster', 'nonRosterInvitees'}
    with pytest.raises(ValueError):
        roster_requests(DAY, [9999])


def test_partial_schedule_is_not_an_off_day():
    with pytest.raises(ValueError):
        game_requests(DAY, {'totalGames': 1, 'dates': []}, now=NOW)


def test_doubleheader_and_final_correction_are_separate():
    games = [{'gamePk': 11, 'status': {'statusCode': 'F'}},
             {'gamePk': 12, 'status': {'statusCode': 'I'}}]
    response = {'totalGames': 2, 'dates': [
        {'date': DAY.isoformat(), 'totalGames': 2, 'games': games}]}
    assert [r.poll_seconds for r in game_requests(DAY, response, now=NOW, reconciled={11})] == [90]
    polled = game_requests(DAY, response, now=NOW, reconciled={11}, corrected={11})
    assert len(polled) == 4
    games[1]['gamePk'] = 11
    with pytest.raises(ValueError):
        game_requests(DAY, response, now=NOW)
