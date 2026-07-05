"""
Synchronize MLB roster status into tracked pitcher rows.

The source of authority is the existing MLB Stats API team roster endpoint.
BaseballOS compares active roster membership with 40-man, full-roster, and
non-roster invitee roster views so roster status stays separate from workload
freshness and local tracking state.
"""

from collections import Counter, defaultdict
import logging

from models.pitcher import Pitcher
from models.roster_status_snapshot import RosterStatusSnapshot
from services import dead_letter, source_provenance
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


logger = logging.getLogger(__name__)

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
ROSTER_STATUS_FETCH_ENTITY_TYPE = 'roster_status_fetch'
ROSTER_STATUS_IDENTITY_ENTITY_TYPE = 'roster_status_snapshot_identity'
ROSTER_STATUS_CONFLICT_ENTITY_TYPE = 'roster_status_snapshot_conflict'

_SNAPSHOT_FACT_FIELDS = (
    'roster_status',
    'active_roster',
    'forty_man_roster',
    'position_code',
    'position_name',
    'position_type',
    'two_way_eligible',
    'roster_status_raw',
    'roster_status_raw_code',
    'roster_status_raw_description',
    'source',
)

_CACHE_FIELDS = (
    ('roster_status', 'roster_status'),
    ('roster_status_source', 'source'),
    ('roster_status_raw_code', 'roster_status_raw_code'),
    ('roster_status_raw_description', 'roster_status_raw_description'),
)


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


def _record_evidence(index, team_id, roster_type, entry):
    player_id = roster_entry_player_id(entry)
    if player_id is None:
        return {
            'reason': 'missing_player_identity',
            'team_id': team_id,
            'roster_type': roster_type,
            'entity_type': ROSTER_STATUS_IDENTITY_ENTITY_TYPE,
            'error': 'Roster entry missing player identity',
            'entry': entry,
        }

    evidence = index[player_id]
    evidence['player_id'] = player_id
    evidence['roster_types'].add(roster_type)
    evidence['entries'][roster_type] = entry

    raw_status = roster_entry_status_details(entry)
    if raw_status['raw_status'] not in (None, ''):
        evidence['raw_statuses'].append((roster_type, raw_status))
    return None


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
                'reason': 'fetch_failed',
                'team_id': team_id,
                'roster_type': roster_type,
                'entity_type': ROSTER_STATUS_FETCH_ENTITY_TYPE,
                'error': str(exc),
            })
            continue

        for entry in roster or []:
            error = _record_evidence(index, team_id, roster_type, entry)
            if error:
                errors.append(error)

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


def _preferred_entry(evidence):
    entries = (evidence or {}).get('entries') or {}
    for roster_type in ROSTER_TYPES:
        entry = entries.get(roster_type)
        if entry:
            return entry
    return None


def _position_details(entry):
    if not entry:
        return {
            'position_code': None,
            'position_name': None,
            'position_type': None,
        }
    position = entry.get('position') or {}
    person = entry.get('person') or {}
    primary = person.get('primaryPosition') or {}
    return {
        'position_code': (
            position.get('code')
            or position.get('abbreviation')
            or primary.get('code')
            or primary.get('abbreviation')
        ),
        'position_name': position.get('name') or primary.get('name'),
        'position_type': position.get('type') or primary.get('type'),
    }


def _bool_or_none(value):
    if isinstance(value, bool):
        return value
    if value in (None, ''):
        return None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {'true', 't', 'yes', 'y', '1'}:
            return True
        if lowered in {'false', 'f', 'no', 'n', '0'}:
            return False
    if isinstance(value, int):
        if value == 1:
            return True
        if value == 0:
            return False
    return None


def _two_way_eligible(entry):
    if not entry:
        return None
    person = entry.get('person') or {}
    for source in (entry, person):
        for key in (
            'twoWayEligible',
            'twoWayPlayer',
            'isTwoWayEligible',
            'isTwoWayPlayer',
        ):
            value = _bool_or_none(source.get(key))
            if value is not None:
                return value
    return None


def _snapshot_values(
    *,
    pitcher,
    team_id,
    snapshot_date,
    classification,
    evidence,
    timestamp,
    sync_run_id,
):
    roster_types = set((evidence or {}).get('roster_types') or ())
    entry = _preferred_entry(evidence)
    positions = _position_details(entry)
    return {
        'pitcher_id': pitcher.id,
        'mlb_id': pitcher.mlb_id,
        'team_id': team_id,
        'snapshot_date': snapshot_date,
        'roster_status': classification['status'],
        'active_roster': (
            ROSTER_TYPE_ACTIVE in roster_types
            if evidence is not None else None
        ),
        'forty_man_roster': (
            ROSTER_TYPE_40_MAN in roster_types
            if evidence is not None else None
        ),
        'position_code': positions['position_code'],
        'position_name': positions['position_name'],
        'position_type': positions['position_type'],
        'two_way_eligible': _two_way_eligible(entry),
        'roster_status_raw': classification.get('raw_status'),
        'roster_status_raw_code': classification.get('raw_status_code'),
        'roster_status_raw_description': classification.get('raw_status_description'),
        'source': classification['source'],
        'sync_run_id': sync_run_id,
        'first_seen_at': timestamp,
        'created_at': timestamp,
        'updated_at': timestamp,
    }


def _record_roster_failure(detail, *, sync_run_id=None):
    payload = dict(detail)
    entity_type = payload.pop('entity_type', None) or ROSTER_STATUS_FETCH_ENTITY_TYPE
    entity_ref = (
        payload.get('pitcher_mlb_id')
        or payload.get('player_id')
        or payload.get('team_id')
        or payload.get('roster_type')
    )
    failure = dead_letter.record_failure(
        entity_type,
        payload.get('error') or payload.get('reason') or 'Roster status sync failed',
        entity_ref=entity_ref,
        payload=payload,
        sync_run_id=sync_run_id,
        job_name='daily_sync',
    )
    return failure is not None


def _upsert_roster_status_snapshot(values, *, sync_run_id=None, timestamp=None):
    timestamp = timestamp or utc_now_naive()
    existing = (
        RosterStatusSnapshot.query
        .filter_by(
            pitcher_id=values['pitcher_id'],
            snapshot_date=values['snapshot_date'],
        )
        .first()
    )

    if existing and existing.team_id != values['team_id']:
        failure = dead_letter.record_failure(
            ROSTER_STATUS_CONFLICT_ENTITY_TYPE,
            'Roster snapshot team conflict for same pitcher/date',
            entity_ref=values['mlb_id'],
            payload={
                'pitcher_id': values['pitcher_id'],
                'mlb_id': values['mlb_id'],
                'snapshot_date': values['snapshot_date'].isoformat(),
                'existing_team_id': existing.team_id,
                'incoming_team_id': values['team_id'],
            },
            sync_run_id=sync_run_id,
            job_name='daily_sync',
        )
        return None, 'conflict', failure is not None

    if existing is None:
        snapshot = RosterStatusSnapshot(**values)
        source_provenance.apply_initial_source_provenance(
            snapshot,
            source=values['source'],
            sync_run_id=sync_run_id,
            first_seen_at=timestamp,
        )
        db.session.add(snapshot)
        db.session.flush()
        return snapshot, 'created', False

    changed = False
    for field in _SNAPSHOT_FACT_FIELDS:
        if getattr(existing, field) != values[field]:
            setattr(existing, field, values[field])
            changed = True
    existing.sync_run_id = sync_run_id
    existing.updated_at = timestamp
    if changed:
        source_provenance.record_source_correction(
            existing,
            correction_source=values['source'],
            sync_run_id=sync_run_id,
            corrected_at=timestamp,
        )
        _notify_roster_depth_evidence_snapshot_correction(
            existing,
            sync_run_id=sync_run_id,
        )
        db.session.add(existing)
        db.session.flush()
        return existing, 'corrected', False

    db.session.add(existing)
    db.session.flush()
    return existing, 'unchanged', False


def _notify_roster_depth_evidence_snapshot_correction(snapshot_row, *, sync_run_id=None):
    try:
        from services.roster_depth_evidence import (
            mark_roster_status_snapshot_correction_for_roster_depth,
        )
        return mark_roster_status_snapshot_correction_for_roster_depth(
            snapshot_row,
            sync_run_id=sync_run_id,
        )
    except Exception as exc:  # noqa: BLE001 - correction marking must not block sync
        logger.warning(
            'Could not mark roster depth evidence for snapshot correction id=%s: %s',
            getattr(snapshot_row, 'id', None),
            exc,
        )
        return {'marked_count': 0, 'evidence_ids': []}


def latest_roster_status_snapshot_for_pitcher(pitcher_id):
    return (
        RosterStatusSnapshot.query
        .filter_by(pitcher_id=pitcher_id)
        .order_by(
            RosterStatusSnapshot.snapshot_date.desc(),
            RosterStatusSnapshot.updated_at.desc(),
            RosterStatusSnapshot.id.desc(),
        )
        .first()
    )


def _cache_timestamp(snapshot):
    return (
        snapshot.last_corrected_at
        or snapshot.updated_at
        or snapshot.first_seen_at
        or utc_now_naive()
    )


def _apply_snapshot_to_pitcher_cache(pitcher, snapshot):
    before = (
        pitcher.roster_status,
        pitcher.roster_status_source,
        pitcher.roster_status_raw_code,
        pitcher.roster_status_raw_description,
        pitcher.roster_status_updated_at,
    )
    pitcher.roster_status = snapshot.roster_status
    pitcher.roster_status_source = snapshot.source
    pitcher.roster_status_raw_code = snapshot.roster_status_raw_code
    pitcher.roster_status_raw_description = snapshot.roster_status_raw_description
    pitcher.roster_status_updated_at = _cache_timestamp(snapshot)
    after = (
        pitcher.roster_status,
        pitcher.roster_status_source,
        pitcher.roster_status_raw_code,
        pitcher.roster_status_raw_description,
        pitcher.roster_status_updated_at,
    )
    return before != after


def roster_status_cache_divergences(team_ids=None):
    query = Pitcher.query.filter(Pitcher.active == True)
    if team_ids:
        query = query.filter(Pitcher.team_id.in_(tuple(team_ids)))

    divergences = []
    for pitcher in query.all():
        snapshot = latest_roster_status_snapshot_for_pitcher(pitcher.id)
        if snapshot is None:
            continue
        mismatched = [
            cache_field
            for cache_field, snapshot_field in _CACHE_FIELDS
            if getattr(pitcher, cache_field) != getattr(snapshot, snapshot_field)
        ]
        if mismatched:
            divergences.append({
                'pitcher_id': pitcher.id,
                'mlb_id': pitcher.mlb_id,
                'team_id': pitcher.team_id,
                'snapshot_id': snapshot.id,
                'snapshot_date': snapshot.snapshot_date.isoformat(),
                'mismatched_fields': mismatched,
            })
    return divergences


def roster_status_cache_divergence_count(team_ids=None):
    return len(roster_status_cache_divergences(team_ids=team_ids))


def sync_roster_statuses(
    team_ids=None,
    client=None,
    timestamp=None,
    commit=True,
    sync_run_id=None,
    snapshot_date=None,
):
    """
    Persist roster status for tracked pitchers.

    Returns a summary suitable for sync status payloads and tests. Unknowns are
    explicit persisted values when no roster endpoint can classify the row.
    """
    client = client or mlb_client
    timestamp = timestamp or utc_now_naive()
    snapshot_date = snapshot_date or timestamp.date()
    team_ids = _team_ids_to_sync(team_ids)
    by_status = Counter()
    errors = []
    changed = 0
    refreshed = 0
    missing = 0
    snapshot_rows_created = 0
    snapshot_rows_corrected = 0
    snapshot_rows_unchanged = 0
    snapshot_conflicts = 0
    records_failed = 0

    for team_id in team_ids:
        index, team_errors = build_team_roster_status_index(team_id, client=client)
        errors.extend(team_errors)
        fetch_errors = [
            error for error in team_errors
            if error.get('reason') == 'fetch_failed'
        ]
        identity_errors = [
            error for error in team_errors
            if error.get('reason') != 'fetch_failed'
        ]
        for detail in identity_errors:
            if _record_roster_failure(detail, sync_run_id=sync_run_id):
                records_failed += 1
        if fetch_errors:
            for detail in fetch_errors:
                if _record_roster_failure(detail, sync_run_id=sync_run_id):
                    records_failed += 1
            continue
        dead_letter.resolve_entity_failures(
            ROSTER_STATUS_FETCH_ENTITY_TYPE,
            team_id,
            job_name='daily_sync',
        )
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
            by_status[status] += 1

            values = _snapshot_values(
                pitcher=pitcher,
                team_id=team_id,
                snapshot_date=snapshot_date,
                classification=classification,
                evidence=evidence,
                timestamp=timestamp,
                sync_run_id=sync_run_id,
            )
            snapshot, action, failure_recorded = _upsert_roster_status_snapshot(
                values,
                sync_run_id=sync_run_id,
                timestamp=timestamp,
            )
            if failure_recorded:
                records_failed += 1
            if snapshot is None:
                snapshot_conflicts += 1
                continue
            if action == 'created':
                snapshot_rows_created += 1
            elif action == 'corrected':
                snapshot_rows_corrected += 1
            else:
                snapshot_rows_unchanged += 1

            latest_snapshot = latest_roster_status_snapshot_for_pitcher(pitcher.id)
            if latest_snapshot and _apply_snapshot_to_pitcher_cache(pitcher, latest_snapshot):
                changed += 1
            refreshed += 1

    if commit:
        db.session.commit()

    unknown = by_status.get(STATUS_UNKNOWN, 0)
    return {
        'source': SOURCE_PREFIX,
        'teams_processed': len(team_ids),
        'pitchers_refreshed': refreshed,
        'pitchers_changed': changed,
        'snapshots_created': snapshot_rows_created,
        'snapshots_corrected': snapshot_rows_corrected,
        'snapshots_unchanged': snapshot_rows_unchanged,
        'snapshot_conflicts': snapshot_conflicts,
        'records_failed': records_failed,
        'missing_from_roster_sources': missing,
        'unknown_count': unknown,
        'errors': len(errors),
        'error_details': errors,
        'by_status': dict(sorted(by_status.items())),
    }
