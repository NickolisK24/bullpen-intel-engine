"""Bounded cross-entity identity search for public discovery.

This service composes existing team, pitcher, and product-day schedule owners.
It identifies canonical destinations; it does not load destination intelligence,
rank baseball subjects, or create a new entity authority.
"""

from dataclasses import dataclass
from typing import Callable
import unicodedata

from models.slate_game import SlateGame
from services.availability_reference_date import product_current_date
from services.pitcher_search import (
    MIN_SEARCH_QUERY_LENGTH,
    search_pitchers_by_name,
)
from services.team_directory import valid_team_directory


CAPABILITY = 'unified_entity_search_v1'
CONTRACT = 'unified_entity_search_carrier_v1'
DEFAULT_GROUP_LIMIT = 5
MAX_GROUP_LIMIT = 10

STATUS_AVAILABLE = 'available'
STATUS_PARTIAL = 'partial'
STATUS_UNAVAILABLE = 'unavailable'
STATUS_QUIET = 'quiet'

TEAM_OWNER_UNAVAILABLE = 'team_search_owner_unavailable'
PITCHER_OWNER_UNAVAILABLE = 'pitcher_search_owner_unavailable'
MATCHUP_OWNER_UNAVAILABLE = 'matchup_search_owner_unavailable'


def normalize_search_text(value):
    normalized = unicodedata.normalize('NFKD', str(value or ''))
    ascii_folded = ''.join(
        char for char in normalized
        if not unicodedata.combining(char)
    )
    return ' '.join(ascii_folded.casefold().strip().split())


def _coerce_limit(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_GROUP_LIMIT
    return max(1, min(parsed, MAX_GROUP_LIMIT))


def _identity_rank(query, *values):
    normalized = [normalize_search_text(value) for value in values]
    normalized = [value for value in normalized if value]
    if any(value == query for value in normalized):
        return 0
    if any(value.startswith(query) for value in normalized):
        return 1
    if any(query in value for value in normalized):
        return 2
    tokens = query.split()
    combined = ' '.join(normalized)
    if tokens and all(token in combined for token in tokens):
        return 3
    return None


def _available_group(entity_type, results):
    return {
        'entity_type': entity_type,
        'status': STATUS_AVAILABLE,
        'reason_code': None,
        'results': list(results),
    }


def _unavailable_group(entity_type, reason_code):
    return {
        'entity_type': entity_type,
        'status': STATUS_UNAVAILABLE,
        'reason_code': reason_code,
        'results': [],
    }


def _team_results(query, directory, limit):
    matches = []
    for team_id, team in (directory or {}).items():
        name = team.get('team_name')
        abbreviation = team.get('team_abbreviation')
        rank = _identity_rank(query, name, abbreviation)
        if rank is None:
            continue
        matches.append((
            rank,
            normalize_search_text(name),
            int(team_id),
            {
                'entity_type': 'team',
                'id': int(team_id),
                'primary_label': name,
                'secondary_label': abbreviation,
                'metadata': {
                    'team_id': int(team_id),
                    'team_name': name,
                    'team_abbreviation': abbreviation,
                },
            },
        ))
    matches.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[3] for item in matches[:limit]]


def _pitcher_results(query, limit, reference_date):
    payload = search_pitchers_by_name(
        query,
        limit=limit,
        reference_date=reference_date,
    )
    results = []
    for pitcher in payload.get('results') or []:
        player_id = pitcher.get('player_id')
        name = pitcher.get('player_name')
        if player_id is None or not name:
            continue
        results.append({
            'entity_type': 'pitcher',
            'id': player_id,
            'primary_label': name,
            'secondary_label': pitcher.get('team_name'),
            'metadata': {
                'player_id': player_id,
                'player_name': name,
                'team_id': pitcher.get('team_id'),
                'team_name': pitcher.get('team_name'),
                'position': pitcher.get('position'),
                'roster_status': pitcher.get('roster_status'),
            },
        })
    return results


def _matchup_results(query, directory, reference_date, limit):
    rows = (
        SlateGame.query
        .filter(SlateGame.game_date_et == reference_date)
        .order_by(SlateGame.game_time_utc.asc(), SlateGame.game_pk.asc())
        .all()
    )
    matches = []
    for game in rows:
        away = (directory or {}).get(game.away_team_id) or {}
        home = (directory or {}).get(game.home_team_id) or {}
        away_name = away.get('team_name')
        home_name = home.get('team_name')
        if not away_name or not home_name:
            continue
        rank = 0 if query == str(game.game_pk) else _identity_rank(
            query,
            away_name,
            away.get('team_abbreviation'),
            home_name,
            home.get('team_abbreviation'),
            f'{away_name} at {home_name}',
            f'{away_name} vs {home_name}',
        )
        if rank is None:
            continue
        source = game.to_dict()
        matches.append((
            rank,
            game.game_time_utc,
            game.game_pk,
            {
                'entity_type': 'matchup',
                'id': game.game_pk,
                'primary_label': f'{away_name} at {home_name}',
                'secondary_label': reference_date.isoformat(),
                'metadata': {
                    'game_pk': game.game_pk,
                    'reference_date': reference_date.isoformat(),
                    'game_time_utc': source.get('game_time_utc'),
                    'status': source.get('status'),
                    'away': away,
                    'home': home,
                    'doubleheader_flag': source.get('doubleheader_flag'),
                    'game_number': source.get('game_number'),
                },
            },
        ))
    matches.sort(key=lambda item: (item[0], item[1], item[2]))
    return [item[3] for item in matches[:limit]]


@dataclass(frozen=True)
class SearchOwners:
    teams: Callable = valid_team_directory
    pitchers: Callable = _pitcher_results
    matchups: Callable = _matchup_results


def search_discovery(raw_query, *, limit=DEFAULT_GROUP_LIMIT, reference_date=None, owners=None):
    query = str(raw_query or '').strip()
    normalized_query = normalize_search_text(query)
    safe_limit = _coerce_limit(limit)
    represented_date = reference_date or product_current_date()

    if len(normalized_query) < MIN_SEARCH_QUERY_LENGTH:
        return {
            'capability': CAPABILITY,
            'contract': CONTRACT,
            'status': STATUS_QUIET,
            'query': query,
            'min_query_length': MIN_SEARCH_QUERY_LENGTH,
            'represented_date': represented_date.isoformat(),
            'result_count': 0,
            'groups': [
                _available_group('team', []),
                _available_group('pitcher', []),
                _available_group('matchup', []),
            ],
        }

    owner_set = owners or SearchOwners()
    directory = None
    try:
        directory = owner_set.teams()
        team_group = _available_group(
            'team', _team_results(normalized_query, directory, safe_limit),
        )
    except Exception:  # noqa: BLE001 - optional discovery group
        team_group = _unavailable_group('team', TEAM_OWNER_UNAVAILABLE)

    try:
        pitcher_group = _available_group(
            'pitcher', owner_set.pitchers(query, safe_limit, represented_date),
        )
    except Exception:  # noqa: BLE001 - optional discovery group
        pitcher_group = _unavailable_group('pitcher', PITCHER_OWNER_UNAVAILABLE)

    if directory is None:
        matchup_group = _unavailable_group('matchup', MATCHUP_OWNER_UNAVAILABLE)
    else:
        try:
            matchup_group = _available_group(
                'matchup',
                owner_set.matchups(
                    normalized_query, directory, represented_date, safe_limit,
                ),
            )
        except Exception:  # noqa: BLE001 - optional discovery group
            matchup_group = _unavailable_group('matchup', MATCHUP_OWNER_UNAVAILABLE)

    groups = [team_group, pitcher_group, matchup_group]
    unavailable_count = sum(
        group['status'] == STATUS_UNAVAILABLE for group in groups
    )
    status = (
        STATUS_UNAVAILABLE if unavailable_count == len(groups)
        else STATUS_PARTIAL if unavailable_count
        else STATUS_AVAILABLE
    )
    return {
        'capability': CAPABILITY,
        'contract': CONTRACT,
        'status': status,
        'query': query,
        'min_query_length': MIN_SEARCH_QUERY_LENGTH,
        'represented_date': represented_date.isoformat(),
        'result_count': sum(len(group['results']) for group in groups),
        'groups': groups,
    }


__all__ = [
    'CAPABILITY',
    'CONTRACT',
    'DEFAULT_GROUP_LIMIT',
    'MAX_GROUP_LIMIT',
    'SearchOwners',
    'normalize_search_text',
    'search_discovery',
]
