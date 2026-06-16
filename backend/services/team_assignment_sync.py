"""
Synchronize authoritative MLB organization ownership into tracked pitchers.

Roster status answers whether a player is active, injured, optioned, or in
another roster category. This service answers which organization owns the
player record at all. It runs before roster-status sync so roster classification
uses the current team instead of the stale locally stored team.
"""

from collections import Counter, defaultdict

from models.pitcher import Pitcher
from services.mlb_api import MlbApiFetchError, mlb_client
from services.roster_status import STATUS_UNKNOWN
from services.roster_status_sync import (
    ROSTER_TYPES,
    ROSTER_TYPE_40_MAN,
    ROSTER_TYPE_ACTIVE,
    ROSTER_TYPE_FULL,
    ROSTER_TYPE_NON_ROSTER,
    roster_entry_player_id,
)
from utils.db import db
from utils.time import utc_now_naive


TEAM_ASSIGNMENT_ASSIGNED = 'ASSIGNED'
TEAM_ASSIGNMENT_NO_ORGANIZATION = 'NO_ORGANIZATION'
TEAM_ASSIGNMENT_UNKNOWN = 'UNKNOWN'

SOURCE_PREFIX = 'mlb_stats_api:team_assignment_sync'

MLB_TEAM_IDS = (
    108, 109, 110, 111, 112, 113, 114, 115, 116, 117,
    118, 119, 120, 121, 133, 134, 135, 136, 137, 138,
    139, 140, 141, 142, 143, 144, 145, 146, 147, 158,
)

ROSTER_PRECEDENCE = (
    ROSTER_TYPE_ACTIVE,
    ROSTER_TYPE_40_MAN,
    ROSTER_TYPE_FULL,
    ROSTER_TYPE_NON_ROSTER,
)

NO_ORGANIZATION_STATUS_VALUES = {
    'FA',
    'FREE AGENT',
    'FREE AGENCY',
    'RELEASED',
    'UNSIGNED',
    'NO ORGANIZATION',
    'NO ORG',
    'NOT CURRENTLY ASSIGNED',
    'RETIRED',
}


def _norm(value):
    if value is None:
        return ''
    text = str(value).strip().upper()
    text = text.replace('.', '')
    return ' '.join(text.replace('/', ' ').replace('_', ' ').replace('-', ' ').split())


def _status_value(status):
    if not isinstance(status, dict):
        return status
    return (
        status.get('code')
        or status.get('description')
        or status.get('name')
        or status.get('type')
    )


def _status_values_from_player_info(info):
    info = info or {}
    for candidate in (
        info.get('status'),
        info.get('rosterStatus'),
        info.get('roster_status'),
        info.get('statusCode'),
        info.get('statusDescription'),
    ):
        value = _status_value(candidate)
        if value not in (None, ''):
            yield value


def _is_no_organization_status(value):
    normalized = _norm(value)
    if normalized in NO_ORGANIZATION_STATUS_VALUES:
        return True
    return any(
        marker in normalized
        for marker in ('FREE AGENT', 'RELEASED', 'UNSIGNED', 'NO ORGANIZATION')
    )


def _existing_team_map():
    rows = (
        db.session.query(Pitcher.team_id, Pitcher.team_name, Pitcher.team_abbreviation)
        .filter(Pitcher.team_id.isnot(None))
        .distinct()
        .all()
    )
    return {
        row.team_id: {
            'id': row.team_id,
            'name': row.team_name,
            'abbreviation': row.team_abbreviation,
        }
        for row in rows
    }


def _fetch_team_map(client):
    errors = []
    team_map = _existing_team_map()
    try:
        teams = client.get_all_teams()
    except Exception as exc:
        teams = []
        errors.append({
            'source': f'{SOURCE_PREFIX}:teams',
            'error': str(exc),
        })

    for team in teams or []:
        team_id = team.get('id')
        if team_id is None:
            continue
        team_map[team_id] = {
            'id': team_id,
            'name': team.get('name'),
            'abbreviation': team.get('abbreviation'),
        }
    return team_map, errors


def _team_ids_to_sync(team_ids, team_map):
    if team_ids:
        return list(dict.fromkeys(team_ids))
    if team_map:
        return sorted(team_map)
    return list(MLB_TEAM_IDS)


def _team_identity(team_id, team_map, fallback=None):
    fallback = fallback or {}
    team = team_map.get(team_id) or {}
    return {
        'team_id': team_id,
        'team_name': team.get('name') or fallback.get('name'),
        'team_abbreviation': team.get('abbreviation') or fallback.get('abbreviation'),
    }


def _source_for(roster_type):
    return f'{SOURCE_PREFIX}:{roster_type}'


def _record_roster_evidence(index, team_id, roster_type, entry):
    player_id = roster_entry_player_id(entry)
    if player_id is None:
        return
    evidence = index[player_id]
    evidence['player_id'] = player_id
    evidence['appearances'].append({
        'team_id': team_id,
        'roster_type': roster_type,
        'entry': entry,
    })


def build_team_assignment_index(team_ids=None, client=None, roster_types=ROSTER_TYPES):
    """Fetch MLB team roster ownership evidence by MLB player id."""
    client = client or mlb_client
    team_map, errors = _fetch_team_map(client)
    resolved_team_ids = _team_ids_to_sync(team_ids, team_map)
    index = defaultdict(lambda: {
        'player_id': None,
        'appearances': [],
    })

    for team_id in resolved_team_ids:
        for roster_type in roster_types:
            try:
                roster = client.get_team_roster(team_id, roster_type=roster_type)
            except Exception as exc:
                errors.append({
                    'team_id': team_id,
                    'roster_type': roster_type,
                    'source': _source_for(roster_type),
                    'error': str(exc),
                })
                continue

            for entry in roster or []:
                _record_roster_evidence(index, team_id, roster_type, entry)

    return {
        'index': dict(index),
        'team_map': team_map,
        'team_ids': resolved_team_ids,
        'errors': errors,
    }


def _classification(status, source, **extra):
    payload = {
        'status': status,
        'source': source,
    }
    payload.update(extra)
    return payload


def _classification_from_roster_evidence(evidence, team_map):
    evidence = evidence or {}
    appearances = list(evidence.get('appearances') or [])
    if not appearances:
        return None

    for roster_type in ROSTER_PRECEDENCE:
        roster_hits = [
            appearance
            for appearance in appearances
            if appearance.get('roster_type') == roster_type
        ]
        team_ids = sorted({hit.get('team_id') for hit in roster_hits if hit.get('team_id') is not None})
        if len(team_ids) == 1:
            team_id = team_ids[0]
            return _classification(
                TEAM_ASSIGNMENT_ASSIGNED,
                _source_for(roster_type),
                **_team_identity(team_id, team_map),
            )
        if len(team_ids) > 1:
            return _classification(
                TEAM_ASSIGNMENT_UNKNOWN,
                f'{SOURCE_PREFIX}:ambiguous:{roster_type}',
                ambiguous_team_ids=team_ids,
            )

    return None


def _classification_from_player_info(pitcher, client, team_map):
    try:
        info = client.get_player_info(pitcher.mlb_id)
    except MlbApiFetchError as exc:
        return _classification(
            TEAM_ASSIGNMENT_UNKNOWN,
            f'{SOURCE_PREFIX}:people:fetch_failed',
            lookup_error=str(exc),
            fetch_failed=True,
        )

    if not info:
        return _classification(
            TEAM_ASSIGNMENT_UNKNOWN,
            f'{SOURCE_PREFIX}:people:unavailable',
        )

    current_team = info.get('currentTeam') or {}
    current_team_id = current_team.get('id')
    if current_team_id is not None:
        return _classification(
            TEAM_ASSIGNMENT_ASSIGNED,
            f'{SOURCE_PREFIX}:people:currentTeam',
            **_team_identity(current_team_id, team_map, fallback=current_team),
        )

    for raw_status in _status_values_from_player_info(info):
        if _is_no_organization_status(raw_status):
            return _classification(
                TEAM_ASSIGNMENT_NO_ORGANIZATION,
                f'{SOURCE_PREFIX}:people:status',
                raw_status=str(raw_status),
            )

    return _classification(
        TEAM_ASSIGNMENT_UNKNOWN,
        f'{SOURCE_PREFIX}:unavailable',
    )


def classify_team_assignment(pitcher, roster_index, team_map, client=None):
    """Resolve the current organization assignment for one tracked pitcher."""
    client = client or mlb_client
    roster_classification = _classification_from_roster_evidence(
        roster_index.get(pitcher.mlb_id),
        team_map,
    )
    if roster_classification is not None:
        return roster_classification
    return _classification_from_player_info(pitcher, client, team_map)


def _assignment_fields(pitcher):
    return {
        'team_id': pitcher.team_id,
        'team_name': pitcher.team_name,
        'team_abbreviation': pitcher.team_abbreviation,
        'active': pitcher.active,
        'team_assignment_status': pitcher.team_assignment_status,
        'team_assignment_source': pitcher.team_assignment_source,
    }


def _apply_assignment(pitcher, classification, timestamp):
    before = _assignment_fields(pitcher)
    status = classification['status']
    source = classification['source']

    if status == TEAM_ASSIGNMENT_ASSIGNED:
        pitcher.team_id = classification.get('team_id')
        pitcher.team_name = classification.get('team_name')
        pitcher.team_abbreviation = classification.get('team_abbreviation')
        pitcher.active = True
    else:
        pitcher.team_id = None
        pitcher.team_name = None
        pitcher.team_abbreviation = None
        pitcher.active = False
        pitcher.roster_status = STATUS_UNKNOWN
        pitcher.roster_status_source = source
        pitcher.roster_status_updated_at = timestamp

    pitcher.team_assignment_status = status
    pitcher.team_assignment_source = source
    pitcher.team_assignment_updated_at = timestamp
    return before != _assignment_fields(pitcher), before


def sync_team_assignments(team_ids=None, client=None, timestamp=None, commit=True):
    """
    Persist authoritative organization ownership for every tracked pitcher.

    Missing or ambiguous authority is fail-closed: the stale team assignment is
    cleared and the pitcher is marked inactive until ownership can be resolved.
    """
    client = client or mlb_client
    timestamp = timestamp or utc_now_naive()
    evidence = build_team_assignment_index(team_ids=team_ids, client=client)
    roster_index = evidence['index']
    team_map = evidence['team_map']
    errors = list(evidence['errors'])
    roster_error_team_ids = {
        item.get('team_id')
        for item in errors
        if item.get('team_id') is not None
    }

    pitchers = Pitcher.query.filter(Pitcher.mlb_id.isnot(None)).all()
    by_status = Counter()
    refreshed = 0
    changed = 0
    reassigned = 0
    cleared = 0
    lookup_errors = 0

    for pitcher in pitchers:
        classification = classify_team_assignment(
            pitcher,
            roster_index=roster_index,
            team_map=team_map,
            client=client,
        )
        if classification.get('lookup_error'):
            lookup_errors += 1
            errors.append({
                'pitcher_mlb_id': pitcher.mlb_id,
                'source': classification['source'],
                'error': classification['lookup_error'],
            })
        if classification.get('fetch_failed') or (
            classification['status'] == TEAM_ASSIGNMENT_UNKNOWN
            and pitcher.team_id in roster_error_team_ids
        ):
            continue

        by_status[classification['status']] += 1

        was_changed, before = _apply_assignment(pitcher, classification, timestamp)
        if was_changed:
            changed += 1
            if classification['status'] == TEAM_ASSIGNMENT_ASSIGNED and before.get('team_id') not in (None, classification.get('team_id')):
                reassigned += 1
            if classification['status'] != TEAM_ASSIGNMENT_ASSIGNED and before.get('team_id') is not None:
                cleared += 1
        refreshed += 1

    if commit:
        db.session.commit()

    return {
        'source': SOURCE_PREFIX,
        'teams_processed': len(evidence['team_ids']),
        'pitchers_refreshed': refreshed,
        'pitchers_changed': changed,
        'reassigned_count': reassigned,
        'cleared_team_count': cleared,
        'no_organization_count': by_status.get(TEAM_ASSIGNMENT_NO_ORGANIZATION, 0),
        'unknown_count': by_status.get(TEAM_ASSIGNMENT_UNKNOWN, 0),
        'errors': len(errors),
        'lookup_errors': lookup_errors,
        'error_details': errors,
        'by_status': dict(sorted(by_status.items())),
    }
