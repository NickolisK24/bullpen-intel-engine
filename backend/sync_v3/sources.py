"""Acquire parsed MLB responses before normalization, preserving request scope."""

from dataclasses import dataclass
from datetime import date
import re

from services.mlb_api import MLBApiClient
from sync_v3.discovery import Request, game_requests


@dataclass(frozen=True)
class Acquisition:
    request: Request
    retrieved_at: object
    body: dict
    status: str


def inspect_response(request, body, acquired_at):
    endpoint, params = request.endpoint, request.params()
    if not isinstance(body, dict) or acquired_at.utcoffset() is None:
        raise ValueError('Expected a JSON object and a timezone-aware acquisition time')
    if endpoint == '/schedule':
        day = date.fromisoformat(params['startDate'])
        if params.get('endDate') != day.isoformat() or params.get('sportId') != 1:
            raise ValueError('Unsupported schedule scope')
        game_requests(day, body, now=acquired_at)
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


def acquire(request, fetch, clock):
    endpoint = request.endpoint
    if endpoint.startswith('/api/v1.1/'):
        endpoint = endpoint.replace('/api/v1.1/', '/../v1.1/', 1)
    body = fetch(endpoint, params=request.params())
    return inspect_response(request, body, clock())
