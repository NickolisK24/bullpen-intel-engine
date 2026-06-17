"""
Synchronize MLB roster status into tracked pitcher rows.

The source of authority is the existing MLB Stats API team roster endpoint.
BaseballOS compares active roster membership with 40-man, full-roster, and
non-roster invitee roster views so roster status stays separate from workload
freshness and local tracking state.
"""

from collections import Counter, defaultdict

from models.pitcher import Pitcher
from services.mlb_api import mlb_client
from services.roster_status import (
    STATUS_40_MAN_ONLY,
    STATUS_ACTIVE,
    STATUS_MINORS,
    STATUS_NON_ROSTER,
    STATUS_UNKNOWN,
    normalize_roster_status_value,
)
from utils.db import db
from utils.time import utc_now_naive


ROSTER_TYPE_ACTIVE = 'active'
ROSTER_TYPE_40_MAN = '40Man'
ROSTER_TYPE_FULL = 'fullRoster'
ROSTER_TYPE_NON_ROSTER = 'nonRosterInvitees'

ROSTER_TYPES = (
    ROSTER_TYPE_ACTIVE,
    ROSTER_TYPE_40_MAN,
    ROSTER_TYPE_FULL,
    ROSTER_TYPE_NON_ROSTER,
)

SOURCE_PREFIX = 'mlb_stats_api:roster_sync'


def _status_from_dict(status):
    if not isinstance(status, dict):
        return status
    return (
        status.get('code')
        or status.get('description')
        or status.get('name')
        or status.get('type')
    )


def _status_details_from_value(status):
    if isinstance(status, dict):
        raw = _status_from_dict(status)
        return {
            'raw_status': raw,
            'raw_status_code': status.get('code'),
            'raw_status_description': (
                status.get('description')
                or status.get('name')
                or status.get('type')
            ),
        }
    if status not in (None, ''):
        return {
            'raw_status': status,
            'raw_status_code': None,
            'raw_status_description': str(status),
        }
    return {
        'raw_status': None,
        'raw_status_code': None,
        'raw_status_description': None,
    }


def _status_details_from_fields(code=None, description=None):
    raw = code or description
    if raw in (None, ''):
        return {
            'raw_status': None,
            'raw_status_code': None,
            'raw_status_description': None,
        }
    return {
        'raw_status': raw,
        'raw_status_code': str(code) if code not in (None, '') else None,
        'raw_status_description': str(description) if description not in (None, '') else None,
    }


def roster_entry_player_id(entry):
    person = entry.get('person') or {}
    return person.get('id') or entry.get('personId') or entry.get('playerId')


def roster_entry_position(entry):
    position = entry.get('position') or {}
    person = entry.get('person') or {}
    primary = person.get('primaryPosition') or {}
    return (
        position.get('abbreviation')
        or position.get('code')
        or primary.get('abbreviation')
        or primary.get('code')
    )


def roster_entry_raw_status(entry):
    """Extract the first roster-status hint from a Stats API roster entry."""
    return roster_entry_status_details(entry)['raw_status']


def roster_entry_status_details(entry):
    """Extract raw roster-status code and description from a Stats API entry."""
    person = entry.get('person') or {}
    candidates = (
        entry.get('status'),
        entry.get('rosterStatus'),
        entry.get('roster_status'),
        _status_details_from_fields(entry.get('statusCode'), entry.get('statusDescription')),
        person.get('status'),
        person.get('rosterStatus'),
        person.get('roster_status'),
        _status_details_from_fields(person.get('statusCode'), person.get('statusDescription')),
    )
    for candidate in candidates:
        details = candidate if isinstance(candidate, dict) and 'raw_status' in candidate else _status_details_from_value(candidate)
        if details['raw_status'] not in (None, ''):
            return details
    return {
        'raw_status': None,
        'raw_status_code': None,
        'raw_status_description': None,
    }


def _record_evidence(index, roster_type, entry):
    player_id = roster_entry_player_id(entry)
    if player_id is None:
        return

    evidence = index[player_id]
    evidence['player_id'] = player_id
    evidence['roster_types'].add(roster_type)
    evidence['entries'][roster_type] = entry

    raw_status = roster_entry_status_details(entry)
    if raw_status['raw_status'] not in (None, ''):
        evidence['raw_statuses'].append((roster_type, raw_status))


def _source_for(roster_type):
    return f'{SOURCE_PREFIX}:{roster_type}'


def _raw_status_payload(raw_status):
    if isinstance(raw_status, dict):
        return {
            'raw_status': raw_status.get('raw_status'),
            'raw_status_code': raw_status.get('raw_status_code'),
            'raw_status_description': raw_status.get('raw_status_description'),
        }
    return {
        'raw_status': raw_status,
        'raw_status_code': None,
        'raw_status_description': None,
    }


def _classification(status, raw_status, source):
    payload = _raw_status_payload(raw_status)
    return {
        'status': status,
        'raw_status': str(payload['raw_status']) if payload['raw_status'] not in (None, '') else None,
        'raw_status_code': (
            str(payload['raw_status_code'])
            if payload['raw_status_code'] not in (None, '') else None
        ),
        'raw_status_description': (
            str(payload['raw_status_description'])
            if payload['raw_status_description'] not in (None, '') else None
        ),
        'source': source,
    }


def classify_roster_evidence(evidence):
    """
    Classify one player from merged roster endpoint evidence.

    Precedence:
      1. Active roster membership is authoritative ACTIVE.
      2. Explicit MLB status codes/text classify IL, minors, optioned, DFA, etc.
      3. Non-roster invitee endpoint membership is NON_ROSTER.
      4. Full-roster-only membership is MINORS.
      5. 40-man-only membership is 40_MAN_ONLY.
      6. Missing evidence is UNKNOWN.
    """
    evidence = evidence or {}
    roster_types = set(evidence.get('roster_types') or ())
    raw_statuses = list(evidence.get('raw_statuses') or [])

    if ROSTER_TYPE_ACTIVE in roster_types:
        raw = next((raw for source, raw in raw_statuses if source == ROSTER_TYPE_ACTIVE), 'active roster')
        return _classification(STATUS_ACTIVE, raw, _source_for(ROSTER_TYPE_ACTIVE))

    for roster_type, raw in raw_statuses:
        payload = _raw_status_payload(raw)
        status = normalize_roster_status_value(payload['raw_status_code'])
        if status == STATUS_UNKNOWN:
            status = normalize_roster_status_value(payload['raw_status_description'])
        if status == STATUS_UNKNOWN:
            status = normalize_roster_status_value(payload['raw_status'])
        if status == STATUS_ACTIVE and roster_type != ROSTER_TYPE_ACTIVE:
            continue
        if status != STATUS_UNKNOWN:
            return _classification(status, raw, _source_for(roster_type))

    if ROSTER_TYPE_NON_ROSTER in roster_types:
        return _classification(STATUS_NON_ROSTER, ROSTER_TYPE_NON_ROSTER, _source_for(ROSTER_TYPE_NON_ROSTER))

    if ROSTER_TYPE_FULL in roster_types and ROSTER_TYPE_40_MAN not in roster_types:
        return _classification(STATUS_MINORS, ROSTER_TYPE_FULL, _source_for(ROSTER_TYPE_FULL))

    if ROSTER_TYPE_40_MAN in roster_types:
        return _classification(STATUS_40_MAN_ONLY, ROSTER_TYPE_40_MAN, _source_for(ROSTER_TYPE_40_MAN))

    return _classification(STATUS_UNKNOWN, None, f'{SOURCE_PREFIX}:unavailable')


def build_team_roster_status_index(team_id, client=None, roster_types=ROSTER_TYPES):
    """Fetch roster evidence for one MLB team and return it by MLB player id."""
    client = client or mlb_client
    index = defaultdict(lambda: {
        'player_id': None,
        'roster_types': set(),
        'raw_statuses': [],
        'entries': {},
    })
    errors = []

    for roster_type in roster_types:
        try:
            roster = client.get_team_roster(team_id, roster_type=roster_type)
        except Exception as exc:
            errors.append({
                'team_id': team_id,
                'roster_type': roster_type,
                'error': str(exc),
            })
            continue

        for entry in roster or []:
            _record_evidence(index, roster_type, entry)

    return dict(index), errors


def _team_ids_to_sync(team_ids=None):
    if team_ids:
        return list(dict.fromkeys(team_ids))
    rows = (
        db.session.query(Pitcher.team_id)
        .filter(Pitcher.team_id.isnot(None))
        .filter(Pitcher.active == True)
        .distinct()
        .all()
    )
    return [row[0] for row in rows]


def sync_roster_statuses(team_ids=None, client=None, timestamp=None, commit=True):
    """
    Persist roster status for tracked pitchers.

    Returns a summary suitable for sync status payloads and tests. Unknowns are
    explicit persisted values when no roster endpoint can classify the row.
    """
    client = client or mlb_client
    timestamp = timestamp or utc_now_naive()
    team_ids = _team_ids_to_sync(team_ids)
    by_status = Counter()
    errors = []
    changed = 0
    refreshed = 0
    missing = 0

    for team_id in team_ids:
        index, team_errors = build_team_roster_status_index(team_id, client=client)
        errors.extend(team_errors)
        if team_errors:
            continue
        pitchers = (
            Pitcher.query
            .filter(Pitcher.team_id == team_id)
            .filter(Pitcher.active == True)
            .all()
        )

        for pitcher in pitchers:
            evidence = index.get(pitcher.mlb_id)
            if evidence is None:
                missing += 1
            classification = classify_roster_evidence(evidence)
            status = classification['status']
            source = classification['source']
            raw_code = classification.get('raw_status_code')
            raw_description = classification.get('raw_status_description')
            by_status[status] += 1

            if (
                pitcher.roster_status != status
                or pitcher.roster_status_source != source
                or pitcher.roster_status_raw_code != raw_code
                or pitcher.roster_status_raw_description != raw_description
            ):
                changed += 1

            pitcher.roster_status = status
            pitcher.roster_status_source = source
            pitcher.roster_status_raw_code = raw_code
            pitcher.roster_status_raw_description = raw_description
            pitcher.roster_status_updated_at = timestamp
            refreshed += 1

    if commit:
        db.session.commit()

    unknown = by_status.get(STATUS_UNKNOWN, 0)
    return {
        'source': SOURCE_PREFIX,
        'teams_processed': len(team_ids),
        'pitchers_refreshed': refreshed,
        'pitchers_changed': changed,
        'missing_from_roster_sources': missing,
        'unknown_count': unknown,
        'errors': len(errors),
        'error_details': errors,
        'by_status': dict(sorted(by_status.items())),
    }
