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


def pitcher_requests(day, players, *, postseason_rounds=(), round_totals=False):
    from services.club_competition_status import POSTSEASON_GAME_TYPES
    rounds = sorted(set(postseason_rounds))
    if not set(rounds).issubset(POSTSEASON_GAME_TYPES):
        raise ValueError('Unknown postseason round for pitcher game logs')
    players = set(players)
    if any(type(player) is not int or player <= 0 for player in players):
        raise ValueError('Pitcher discovery requires positive MLB player identities')
    requests = []
    for player in sorted(players):
        endpoint = f'/people/{player}/stats'
        scope = {'group': 'pitching', 'sportIds': 1, 'gameType': 'R', 'season': day.year}
        requests.append(_request(endpoint, 21600, stats='gameLog', limit=1000, **scope))
        requests.append(_request(endpoint, 21600, stats='byDateRange', startDate=f'{day.year}-01-01',
                                 endDate=day.isoformat(), **scope))
        for stage in rounds:
            stage_scope = dict(scope, gameType=stage)
            requests.append(_request(endpoint, 21600, stats='gameLog', limit=1000, **stage_scope))
            if round_totals:
                requests.append(_request(endpoint, 21600, stats='byDateRange', startDate=f'{day.year}-01-01',
                                         endDate=day.isoformat(), **stage_scope))
    return tuple(requests)


def roster_requests(day, teams):
    teams = set(teams)
    if not teams.issubset(MLB_TEAM_IDS):
        raise ValueError('Roster discovery requires official MLB club identities')
    return tuple(_request(f'/teams/{team}/roster', 21600, date=day.isoformat(), rosterType=kind)
                 for team in sorted(teams) for kind in ('active', '40Man', 'fullRoster', 'nonRosterInvitees'))


def affiliate_directory_request(day, club):
    if club not in MLB_TEAM_IDS:
        raise ValueError('An MLB parent club is required')
    return _request('/teams/affiliates', 86400, teamIds=club, season=day.year)


def depth_directory(request, body):
    scope = request.params()
    club = scope['teamIds']
    rows = body.get('teams')
    if club not in MLB_TEAM_IDS or not isinstance(rows, list):
        raise ValueError('Missing official affiliate directory')
    result = {}
    for row in rows:
        team = row.get('id')
        sport = (row.get('sport') or {}).get('id')
        if (type(team) is not int or team <= 0 or team in result or type(sport) is not int
                or row.get('season') != scope['season']
                or (team == club and sport != 1)
                or (team != club and (team in MLB_TEAM_IDS or row.get('parentOrgId') != club or sport == 1))):
            raise ValueError('Affiliate directory identity or season conflict')
        result[team] = {'team': team, 'name': row.get('name'), 'sport': sport}
    if club not in result:
        raise ValueError('Directory does not identify its MLB parent')
    return result


def active_profile_request(day, team):
    return _request(f'/teams/{team}/roster', 21600, date=day.isoformat(), rosterType='active', hydrate='person')


def depth_roster_requests(day, directory):
    # Affiliated minor-league levels, plus the parent club for person attributes.
    return tuple(active_profile_request(day, team)
                 for team, row in sorted(directory.items()) if row['sport'] in (1, 11, 12, 13, 14, 15, 16))


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


def competition_calendar_request(year):
    fields = ('totalGames,dates,date,games,gamePk,gameType,season,officialDate,status,abstractGameState,'
              'detailedState,statusCode,teams,home,away,team,id,score,isWinner,gamesInSeries')
    return _request('/schedule', 21600, sportId=1, season=year, gameTypes='R,F,D,L,W', fields=fields)
