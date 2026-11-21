"""Acquire parsed MLB responses before normalization, preserving request scope."""

from dataclasses import dataclass
from datetime import date, datetime
import re

from services.mlb_api import MLBApiClient
from sync_v3.discovery import Request, depth_directory, game_requests


@dataclass(frozen=True)
class RetainedResponse:
    body: dict
    retrieved_at: datetime


@dataclass(frozen=True)
class Acquisition:
    request: Request
    retrieved_at: datetime
    body: dict
    status: str


def inspect_response(request, body, acquired_at):
    endpoint, params = request.endpoint, request.params()
    if not isinstance(body, dict) or acquired_at.utcoffset() is None:
        raise ValueError('Expected a JSON object and a timezone-aware acquisition time')
    if endpoint == '/schedule' and 'season' in params:
        from sync_v3.competition_calendar import calendar_games
        calendar_games(params, body)
    elif endpoint == '/schedule':
        day = date.fromisoformat(params['startDate'])
        if params.get('endDate') != day.isoformat() or params.get('sportId') != 1:
            raise ValueError('Unsupported schedule scope')
        game_requests(day, body, now=acquired_at)
    elif re.fullmatch(r'/people/[1-9][0-9]*/stats', endpoint):
        from services.club_competition_status import POSTSEASON_GAME_TYPES
        groups = body.get('stats')
        stage = params.get('gameType')
        postseason = stage in POSTSEASON_GAME_TYPES and params.get('stats') == 'gameLog'
        if (not isinstance(groups, list) or params.get('stats') not in ('byDateRange', 'gameLog')
                or (stage != 'R' and not postseason) or params.get('group') != 'pitching' or params.get('sportIds') != 1
                or any(not isinstance(g, dict) or (g.get('type') or {}).get('displayName') != params['stats']
                       or (g.get('group') or {}).get('displayName') != 'pitching'
                       or not isinstance(g.get('splits'), list) for g in groups)):
            raise ValueError('Unexpected official pitcher stats scope')
        if postseason:
            player = int(endpoint.split('/')[2])
            if (type(params.get('season')) is not int or len(groups) > 1 or any(
                    not isinstance(split, dict) or split.get('gameType') != stage or (split.get('player') or {}).get('id') != player
                    or str(split.get('season')) != str(params.get('season'))
                    or (split.get('sport') or {}).get('id') != 1
                    for group in groups for split in group['splits'])):
                raise ValueError('Postseason game log differs from the requested player, round or season')
    elif endpoint == '/teams/affiliates':
        depth_directory(request, body)
    elif endpoint == '/transactions':
        if not isinstance(body.get('transactions'), list):
            raise ValueError('Missing transaction collection')
    elif re.fullmatch(r'/teams/\d+/roster', endpoint):
        # Exercise the existing official response/roster scope validator without refetching.
        class CapturedClient:
            def _get(self, endpoint, params):
                return body
        MLBApiClient.get_team_roster(CapturedClient(), int(endpoint.split('/')[2]),
                                     roster_type=params['rosterType'], date=params['date'])
    elif re.fullmatch(r'/game/\d+/boxscore', endpoint):
        if not all(isinstance(body.get('teams', {}).get(side), dict) for side in ('home','away')):
            raise ValueError('Missing boxscore sides')
    elif re.fullmatch(r'/game/\d+/linescore', endpoint):
        if not isinstance(body.get('innings'), list):
            raise ValueError('Missing innings')
    elif re.fullmatch(r'/game/\d+/playByPlay', endpoint):
        if not isinstance(body.get('allPlays'), list):
            raise ValueError('Missing play collection')
    elif re.fullmatch(r'/api/v1\.1/game/\d+/feed/live', endpoint):
        if body.get('gamePk') != int(endpoint.split('/')[4]) or not isinstance(body.get('liveData'), dict):
            raise ValueError('Live feed scope mismatch')
    else:
        raise ValueError('Unsupported acquisition endpoint')
    # A structurally valid response still needs domain-specific authority checks.
    return Acquisition(request, acquired_at, body, 'received')



def transport_endpoint(request):
    if not re.fullmatch(r'/(schedule|transactions|teams/affiliates|people/[1-9][0-9]*/stats|teams/[0-9]+/roster|game/[0-9]+/(boxscore|linescore|playByPlay)|api/v1\.1/game/[0-9]+/feed/live)', request.endpoint):
        raise ValueError('Unsupported acquisition endpoint')
    return request.endpoint.replace('/api/v1.1/', '/../v1.1/', 1)
