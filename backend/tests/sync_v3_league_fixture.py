"""Synthetic, scheduled 30-club rehearsal using the existing played-game boxscore shape."""

from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path

from services.availability import ACTIVE_WINDOW_DAYS
from services.mlb_club_directory import MLB_TEAM_IDS
from sync_v3.discovery import calendar_requests, competition_calendar_request, pitcher_requests, roster_requests


def _response(request, body):
    return dict(endpoint=request.endpoint, params=request.params(), body=body)


def _slate(day, games):
    dates = [dict(date=str(day), totalGames=len(games), games=games)] if games else []
    return dict(totalGames=len(games), dates=dates)


def _fixture(day, games, teams=(), responses=(), **options):
    schedule, transactions = calendar_requests(day)
    return dict(baseball_date=str(day), observed_at=f'{day + timedelta(days=1)}T12:00:00Z',
                team_ids=list(teams), responses=[_response(schedule, _slate(day, games)),
                                                 _response(transactions, dict(transactions=[])), *responses], **options)


def _club(day, team, game, template, include_starter):
    staff = deepcopy(template)
    staff['team']['id'] = team
    staff.update(players={}, pitchers=[])
    for index, original in enumerate(template['pitchers']):
        player = 100 * team + index
        line = deepcopy(template['players'][f'ID{original}'])
        if team == 111:
            line['stats']['pitching']['inningsPitched'] = '4.0' if index == 0 else '5.0'
        line['person'] = dict(id=player, fullName=f'Rehearsal Arm {player}')
        staff['players'][f'ID{player}'] = line
        staff['pitchers'].append(player)
    reliever = staff['pitchers'][-1]
    arm = staff['players'][f'ID{reliever}']
    responses = []
    for request in roster_requests(day, [team]):
        kind = request.params()['rosterType']
        members = [] if kind == 'nonRosterInvitees' else [
            dict(person=arm['person'], position=arm['position'], status=dict(code='A'), parentTeamId=team)]
        if include_starter and members:
            starter = staff['players'][f"ID{staff['pitchers'][0]}"]
            members.append(dict(person=starter['person'], position=starter['position'], status=dict(code='A'), parentTeamId=team))
        responses.append(_response(request, dict(teamId=team, rosterType=kind, roster=members)))
    from utils.innings import parse_mlb_innings_to_outs
    arm['stats']['pitching'].update(saves=int(team in (110,111)), holds=0, saveOpportunities=int(team in (110,111)), gamesFinished=1)
    members = staff['pitchers'] if include_starter else [reliever]
    for player in members:
        line = staff['players'][f'ID{player}']['stats']['pitching']
        if player != reliever:
            line.update(saves=0, holds=0, saveOpportunities=0, gamesFinished=0)
        stats = dict(line, outs=parse_mlb_innings_to_outs(line['inningsPitched']), gamesPitched=1)
        split = dict(player=dict(id=player), team=dict(id=team), sport=dict(id=1), stat=stats, season=str(day.year),
                     gameType='R', date=str(day), game=dict(gamePk=game))
        for request in pitcher_requests(day, [player]):
            kind = request.params()['stats']
            responses.append(_response(request, dict(stats=[
                dict(type=dict(displayName=kind), group=dict(displayName='pitching'), splits=[split])])))
    return staff, members, responses


def league_fixtures(*, idle_next_day=False, boston_starter=False):
    played = json.loads((Path(__file__).parent / 'fixtures/sync_v3/played.json').read_text())
    day = date.fromisoformat(played['baseball_date'])
    bodies = {item['endpoint']: item['body'] for item in played['responses']}
    example = bodies['/schedule']['dates'][0]['games'][0]
    staff = bodies['/game/12345/boxscore']['teams']['home']
    teams = sorted(MLB_TEAM_IDS)
    games, responses, players = [], [], []
    pairings = list(zip(teams[::2], teams[1::2]))
    # Boston and Baltimore meet tomorrow after facing different opponents.
    played_pairs = [(home, pairings[(index + 1) % len(pairings)][1]) for index, (home, _) in enumerate(pairings)]
    for index, (home, away) in enumerate(played_pairs):
        pk = 10000 + index
        game = dict(deepcopy(example), gamePk=pk, season=str(day.year))
        sides = {}
        for side, team in [('home', home), ('away', away)]:
            game['teams'][side]['team']['id'] = team
            sides[side], pitchers, club = _club(day, team, pk, staff, boston_starter and team == 111)
            responses.extend(club)
            players.extend(pitchers)
        games.append(game)
        for suffix, body in [('boxscore', dict(teams=sides)), ('playByPlay', dict(allPlays=[])), ('linescore', dict(innings=[]))]:
            responses.append(dict(endpoint=f'/game/{pk}/{suffix}', params={}, body=body))
    responses.append(dict(endpoint='/teams/affiliates', params=dict(teamIds=111, season=day.year),
                          body=dict(teams=[dict(id=111, season=day.year, sport=dict(id=1))])))
    profile = deepcopy(next(r for r in responses if r['endpoint']=='/teams/111/roster'
                            and r['params']['rosterType']=='active'))
    profile['params']['hydrate'] = 'person'
    profile['body']['roster'][0]['person']['pitchHand'] = {'code':'L'}
    responses.append(profile)
    following = day + timedelta(days=1)
    scheduled = following + timedelta(days=int(idle_next_day))
    upcoming = deepcopy(games)
    for game, (home, away) in zip(upcoming, pairings):
        game['teams']['home']['team']['id'] = home
        game['teams']['away']['team']['id'] = away
        game.update(gamePk=game['gamePk'] + 100, officialDate=str(scheduled), gameDate=f'{scheduled}T22:00:00Z',
                    status=dict(statusCode='S', abstractGameState='Preview', detailedState='Scheduled'))
    season = dict(totalGames=30, dates=_slate(day, games)['dates'] + _slate(scheduled, upcoming)['dates'])
    responses.append(_response(competition_calendar_request(day.year), season))
    quiet = [_fixture(day - timedelta(days=n), []) for n in reversed(range(1, ACTIVE_WINDOW_DAYS))]
    feeds = [dict(endpoint=f"/../v1.1/game/{game['gamePk']}/feed/live", params={},
                  body=dict(gamePk=game['gamePk'], liveData={})) for game in upcoming]
    next_slate = dict(_fixture(following, [] if idle_next_day else upcoming, responses=[] if idle_next_day else feeds), observed_at=f'{following}T16:00:00Z')
    return day, [*quiet, _fixture(day, games, teams, responses, competition=True, pitcher_ids=players, depth_teams=[111]), next_slate]
