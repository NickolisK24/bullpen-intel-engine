"""Plan bounded MLB requests from a complete one-day official schedule."""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from services.game_finality import classify_status
from services.mlb_club_directory import MLB_TEAM_IDS


@dataclass(frozen=True)
class Request:
    endpoint: str
    parameters: tuple
    poll_seconds: int

    def params(self):
        return dict(self.parameters)


def _request(endpoint, seconds, **params):
    return Request(endpoint, tuple(sorted(params.items())), seconds)


def calendar_requests(day):
    represented = day.isoformat()
    return (
        _request('/schedule', 21600, sportId=1, startDate=represented, endDate=represented),
        _request('/transactions', 21600, sportId=1, startDate=represented, endDate=represented),
    )


def roster_requests(day, teams):
    teams = set(teams)
    if not teams.issubset(MLB_TEAM_IDS):
        raise ValueError('Roster discovery requires official MLB club identities')
    return tuple(_request(f'/teams/{team}/roster', 21600, date=day.isoformat(), rosterType=kind)
                 for team in sorted(teams) for kind in ('active', '40Man', 'fullRoster', 'nonRosterInvitees'))


def game_requests(day: date, schedule, *, now: datetime, reconciled=(), corrected=()):
    """Reconcile finals once per evidence revision; live/scheduled games stay adaptive."""
    dates = schedule.get('dates')
    total = schedule.get('totalGames')
    if now.utcoffset() is None:
        raise ValueError('Discovery requires an aware observation time')
    if not isinstance(dates, list) or type(total) is not int or total < 0 or len(dates) > 1:
        raise ValueError('Missing or incoherent official schedule counts')
    games = []
    if dates:
        entry = dates[0]
        games = entry.get('games')
        if (entry.get('date') != day.isoformat() or not isinstance(games, list)
                or type(entry.get('totalGames')) is not int or entry['totalGames'] != len(games)):
            raise ValueError('Incomplete or misdated game list')
    if len(games) != total:
        raise ValueError('Partial official schedule')
    requests = []
    seen = set()
    for game in games:
        pk = game.get('gamePk')
        if type(pk) is not int or pk <= 0 or pk in seen:
            raise ValueError('Invalid or duplicate game identity')
        seen.add(pk)
        status = classify_status(game.get('status'), game_pk=pk)
        if status.final_status:
            if pk not in reconciled or pk in corrected:
                for item in ('boxscore', 'linescore', 'playByPlay'):
                    requests.append(_request(f'/game/{pk}/{item}', 900))
        elif status.reason == 'live_or_in_progress_status':
            requests.append(_request(f'/api/v1.1/game/{pk}/feed/live', 90))
        elif status.reason == 'scheduled_status':
            start = datetime.fromisoformat(game['gameDate'].replace('Z', '+00:00'))
            if start.utcoffset() is None:
                raise ValueError('Scheduled first pitch must include timezone')
            until = start - now
            interval = 300 if until <= timedelta(hours=1) else 1800
            requests.append(_request(f'/api/v1.1/game/{pk}/feed/live', interval))
    return tuple(requests)
