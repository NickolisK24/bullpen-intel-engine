"""
Roster-status authority for bullpen planning surfaces.

Usage freshness answers whether workload data is current. Bullpen eligibility
answers whether a pitcher is bullpen-relevant. This module answers whether a
pitcher is currently an active MLB roster option when authoritative status data
is available.
"""

from datetime import date, datetime

from services.availability import STATUS_UNAVAILABLE


STATUS_ACTIVE = 'ACTIVE'
STATUS_IL_10 = 'IL_10'
STATUS_IL_15 = 'IL_15'
STATUS_IL_60 = 'IL_60'
STATUS_MINORS = 'MINORS'
STATUS_OPTIONED = 'OPTIONED'
STATUS_DFA = 'DFA'
STATUS_NON_ROSTER = 'NON_ROSTER'
STATUS_40_MAN_ONLY = '40_MAN_ONLY'
STATUS_UNKNOWN = 'UNKNOWN'

ROSTER_STATUS_UNAVAILABLE_LIMITATION = (
    'Roster status unavailable; bullpen eligibility is based on stored usage and position data.'
)
TEAM_ASSIGNMENT_UNRESOLVED_LIMITATION = (
    'Current team assignment is unresolved; historical roster labels are not treated as active.'
)
ROSTER_ASSIGNMENT_TIER_UNRESOLVED_LIMITATION = (
    'Current roster assignment tier is unresolved; historical roster labels are not treated as active.'
)

INACTIVE_STATUSES = {
    STATUS_IL_10,
    STATUS_IL_15,
    STATUS_IL_60,
    STATUS_MINORS,
    STATUS_OPTIONED,
    STATUS_DFA,
    STATUS_NON_ROSTER,
    STATUS_40_MAN_ONLY,
}

STATUS_LABELS = {
    STATUS_ACTIVE: 'Active MLB',
    STATUS_IL_10: 'IL-10',
    STATUS_IL_15: 'IL-15',
    STATUS_IL_60: 'IL-60',
    STATUS_MINORS: 'Minors',
    STATUS_OPTIONED: 'Optioned',
    STATUS_DFA: 'DFA',
    STATUS_NON_ROSTER: 'Non-roster',
    STATUS_40_MAN_ONLY: '40-Man Only',
    STATUS_UNKNOWN: 'Roster Unknown',
}

_STATUS_ATTRS = (
    'roster_status',
    'roster_status_code',
    'current_roster_status',
    'current_status',
    'player_status',
    'status',
)

_TEAM_ASSIGNMENT_ASSIGNED = 'ASSIGNED'
_TEAM_ASSIGNMENT_NO_ORGANIZATION = 'NO_ORGANIZATION'
_TEAM_ASSIGNMENT_UNKNOWN = 'UNKNOWN'
_TEAM_ASSIGNMENT_SOURCE_PREFIX = 'mlb_stats_api:team_assignment_sync:'
_ROSTER_SYNC_SOURCE_PREFIX = 'mlb_stats_api:roster_sync:'

_ASSIGNMENT_SOURCE_STATUSES = {
    'active': STATUS_ACTIVE,
    'fullRoster': STATUS_MINORS,
    'nonRosterInvitees': STATUS_NON_ROSTER,
    '40Man': STATUS_40_MAN_ONLY,
}

_ACTIVE_VALUES = {
    'A',
    'ACTIVE',
    'ACTIVE MLB',
    'ACTIVE_MLB',
    'MLB ACTIVE',
    'ON ACTIVE ROSTER',
    'ACTIVE ROSTER',
}

_IL_10_VALUES = {
    'IL10',
    'IL_10',
    'IL-10',
    '10 DAY IL',
    '10-DAY IL',
    '10-DAY INJURED LIST',
    'D10',
}

_IL_15_VALUES = {
    'IL',
    'IL15',
    'IL_15',
    'IL-15',
    'INJURED LIST',
    '15 DAY IL',
    '15-DAY IL',
    '15-DAY INJURED LIST',
    'D15',
}

_IL_60_VALUES = {
    'IL60',
    'IL_60',
    'IL-60',
    '60 DAY IL',
    '60-DAY IL',
    '60-DAY INJURED LIST',
    'D60',
}

_MINORS_VALUES = {
    'MIN',
    'MINORS',
    'MINOR',
    'MINOR LEAGUES',
    'MINOR LEAGUE',
    'MINOR_LEAGUE',
    'MINOR LEAGUE ASSIGNMENT',
    'ASSIGNED TO MINORS',
    'OUTRIGHTED TO MINORS',
    'REHAB ASSIGNMENT',
    'MILB',
}

_OPTIONED_VALUES = {
    'O',
    'OPTIONED',
    'OPTION',
    'OPT',
    'OPTIONED TO MINORS',
    'OPTIONED TO MINOR LEAGUE',
}

_DFA_VALUES = {
    'DFA',
    'DESIGNATED FOR ASSIGNMENT',
    'DESIGNATED_FOR_ASSIGNMENT',
}

_NON_ROSTER_VALUES = {
    'NON ROSTER',
    'NON-ROSTER',
    'NON_ROSTER',
    'NON ROSTER INVITEE',
    'NON-ROSTER INVITEE',
    'NRI',
    'NR',
}

_FORTY_MAN_ONLY_VALUES = {
    '40 MAN ONLY',
    '40-MAN ONLY',
    '40_MAN_ONLY',
    'FORTY MAN ONLY',
}


def _norm(value):
    if value is None:
        return ''
    text = str(value).strip().upper()
    text = text.replace('.', '')
    return ' '.join(text.replace('/', ' ').replace('_', ' ').split())


def _compact(value):
    return _norm(value).replace(' ', '').replace('-', '')


def _status_from_raw(raw):
    normalized = _norm(raw)
    compact = _compact(raw)
    if not normalized:
        return STATUS_UNKNOWN
    if normalized in _ACTIVE_VALUES or compact in {'ACTIVE', 'ACTIVEMLB', 'ACTIVEROSTER'}:
        return STATUS_ACTIVE
    if normalized in _IL_10_VALUES or compact in {'IL10', '10DAYIL', '10DAYINJUREDLIST', 'D10'}:
        return STATUS_IL_10
    if normalized in _IL_15_VALUES or compact in {'IL', 'IL15', 'INJUREDLIST', '15DAYIL', '15DAYINJUREDLIST', 'D15'}:
        return STATUS_IL_15
    if normalized in _IL_60_VALUES or compact in {'IL60', '60DAYIL', '60DAYINJUREDLIST', 'D60'}:
        return STATUS_IL_60
    if normalized in _MINORS_VALUES or compact in {
        'MIN',
        'MINORS',
        'MINORLEAGUES',
        'MINORLEAGUE',
        'MINORLEAGUEASSIGNMENT',
        'ASSIGNEDTOMINORS',
        'OUTRIGHTEDTOMINORS',
        'REHABASSIGNMENT',
        'MILB',
    }:
        return STATUS_MINORS
    if normalized in _OPTIONED_VALUES or 'OPTIONED' in normalized or 'OPTION' in normalized:
        return STATUS_OPTIONED
    if normalized in _DFA_VALUES or 'DESIGNATED FOR ASSIGNMENT' in normalized:
        return STATUS_DFA
    if normalized in _NON_ROSTER_VALUES:
        return STATUS_NON_ROSTER
    if normalized in _FORTY_MAN_ONLY_VALUES:
        return STATUS_40_MAN_ONLY
    return STATUS_UNKNOWN


def normalize_roster_status_value(raw):
    """Normalize an external roster-status value into BaseballOS vocabulary."""
    return _status_from_raw(raw)


def _raw_status_from_pitcher(pitcher):
    if pitcher is None:
        return None
    for attr in _STATUS_ATTRS:
        raw = getattr(pitcher, attr, None)
        if raw not in (None, ''):
            return raw
    return None


def _iso_or_none(value):
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _source_for(pitcher, raw):
    if pitcher is None:
        return 'unavailable'
    source = getattr(pitcher, 'roster_status_source', None)
    if source:
        return str(source)
    if raw not in (None, ''):
        return 'stored_roster_status'
    if getattr(pitcher, 'active', True) is False:
        return 'local_active_flag'
    return 'unavailable'


def _team_assignment_status(pitcher):
    return _norm(getattr(pitcher, 'team_assignment_status', None))


def _team_assignment_source(pitcher):
    source = getattr(pitcher, 'team_assignment_source', None)
    return str(source) if source else None


def _assignment_source_type(source):
    if not source or not source.startswith(_TEAM_ASSIGNMENT_SOURCE_PREFIX):
        return None
    return source.removeprefix(_TEAM_ASSIGNMENT_SOURCE_PREFIX).split(':', 1)[0]


def _is_current_roster_sync_source(source):
    return bool(source and str(source).startswith(_ROSTER_SYNC_SOURCE_PREFIX))


def _is_current_roster_sync_candidate(candidate):
    return bool(candidate and _is_current_roster_sync_source(candidate.get('source')))


def _updated_at_from(pitcher, attr):
    if pitcher is None:
        return None
    return getattr(pitcher, attr, None)


def _candidate(status, *, raw_status, source, updated_at, evidence=None,
               limitations=None, authoritative=True, current_assignment_unresolved=False):
    return {
        'status': status,
        'raw_status': raw_status,
        'source': source,
        'updated_at': updated_at,
        'evidence': list(evidence or []),
        'limitations': list(limitations or []),
        'authoritative': authoritative,
        'current_assignment_unresolved': current_assignment_unresolved,
    }


def _current_assignment_candidate(pitcher):
    assignment_status = _team_assignment_status(pitcher)
    assignment_source = _team_assignment_source(pitcher)
    assignment_type = _assignment_source_type(assignment_source)
    updated_at = _updated_at_from(pitcher, 'team_assignment_updated_at')

    if assignment_status == _TEAM_ASSIGNMENT_ASSIGNED:
        status = _ASSIGNMENT_SOURCE_STATUSES.get(assignment_type)
        if status:
            label = STATUS_LABELS.get(status, STATUS_LABELS[STATUS_UNKNOWN])
            return _candidate(
                status,
                raw_status=assignment_type,
                source=assignment_source,
                updated_at=updated_at,
                evidence=[f'Current roster assignment: {label}.'],
            )
        if assignment_source and assignment_source.startswith(_TEAM_ASSIGNMENT_SOURCE_PREFIX):
            return _candidate(
                STATUS_UNKNOWN,
                raw_status=assignment_type or assignment_status,
                source=assignment_source,
                updated_at=updated_at,
                evidence=['Current roster assignment tier is unresolved.'],
                limitations=[
                    ROSTER_STATUS_UNAVAILABLE_LIMITATION,
                    ROSTER_ASSIGNMENT_TIER_UNRESOLVED_LIMITATION,
                ],
                authoritative=False,
                current_assignment_unresolved=True,
            )
        return None

    if assignment_status in {_TEAM_ASSIGNMENT_NO_ORGANIZATION, _TEAM_ASSIGNMENT_UNKNOWN}:
        return _candidate(
            STATUS_UNKNOWN,
            raw_status=assignment_status,
            source=assignment_source or 'team_assignment_unavailable',
            updated_at=updated_at,
            evidence=['Current team assignment is unresolved.'],
            limitations=[
                ROSTER_STATUS_UNAVAILABLE_LIMITATION,
                TEAM_ASSIGNMENT_UNRESOLVED_LIMITATION,
            ],
            authoritative=False,
            current_assignment_unresolved=True,
        )

    return None


def _stored_roster_candidate(pitcher):
    raw = _raw_status_from_pitcher(pitcher)
    status = _status_from_raw(raw)
    source = _source_for(pitcher, raw)
    if raw in (None, '') or status == STATUS_UNKNOWN:
        return None

    return _candidate(
        status,
        raw_status=str(raw),
        source=source,
        updated_at=_updated_at_from(pitcher, 'roster_status_updated_at'),
        evidence=[f'Stored roster status: {STATUS_LABELS[status]}.'],
    )


def _select_status_candidate(pitcher):
    """
    Deterministic current-state precedence for roster status.

    Current assignment evidence is consulted before historical transaction
    labels, so a stale activation label cannot override a newer minor-league
    assignment. Stored roster-sync ACTIVE still wins when the current active
    roster endpoint says the player is on the MLB active roster.
    """
    assignment = _current_assignment_candidate(pitcher)
    stored = _stored_roster_candidate(pitcher)

    if stored and stored['status'] == STATUS_ACTIVE and _is_current_roster_sync_candidate(stored):
        return stored
    if assignment and assignment['status'] == STATUS_ACTIVE:
        return assignment
    if assignment and assignment['status'] == STATUS_MINORS:
        return assignment
    if stored and _is_current_roster_sync_candidate(stored) and stored['status'] in {STATUS_IL_10, STATUS_IL_15, STATUS_IL_60}:
        return stored
    if stored and _is_current_roster_sync_candidate(stored) and stored['status'] in INACTIVE_STATUSES:
        return stored
    if assignment and assignment['status'] in INACTIVE_STATUSES:
        return assignment
    if assignment and assignment['current_assignment_unresolved']:
        return assignment
    if stored and stored['status'] in {STATUS_IL_10, STATUS_IL_15, STATUS_IL_60}:
        return stored
    if stored and stored['status'] in INACTIVE_STATUSES:
        return stored
    if stored:
        return stored
    return _candidate(
        STATUS_UNKNOWN,
        raw_status=None,
        source=_source_for(pitcher, None),
        updated_at=_updated_at_from(pitcher, 'roster_status_updated_at'),
        limitations=[ROSTER_STATUS_UNAVAILABLE_LIMITATION],
        authoritative=False,
    )


def classify_roster_status(pitcher):
    """
    Return a serializable roster-status classification for a pitcher.

    Unknown status is deliberately not upgraded from usage data or the legacy
    ``active`` flag. That keeps roster status separate from freshness and role
    inference until authoritative data is stored.
    """
    selected = _select_status_candidate(pitcher)
    status = selected['status']
    authoritative = bool(selected['authoritative']) and status != STATUS_UNKNOWN
    active_mlb = True if status == STATUS_ACTIVE else False if status in INACTIVE_STATUSES else None
    limitations = list(selected['limitations'])
    evidence = list(selected['evidence'])

    if not authoritative and ROSTER_STATUS_UNAVAILABLE_LIMITATION not in limitations:
        limitations.append(ROSTER_STATUS_UNAVAILABLE_LIMITATION)
    if not authoritative:
        if pitcher is not None and getattr(pitcher, 'active', True) is False:
            evidence.append('Legacy local active flag is false; no authoritative roster status is stored.')

    return {
        'status': status,
        'label': STATUS_LABELS.get(status, STATUS_LABELS[STATUS_UNKNOWN]),
        'raw_status': selected['raw_status'],
        'source': selected['source'],
        'updated_at': _iso_or_none(selected['updated_at']),
        'is_authoritative': authoritative,
        'is_active_mlb': active_mlb,
        'is_inactive_context': status in INACTIVE_STATUSES,
        'current_assignment_unresolved': bool(selected['current_assignment_unresolved']),
        'confidence': 'high' if authoritative else 'low',
        'evidence': evidence,
        'limitations': limitations,
    }


def allows_default_board(status_payload):
    """
    True when a pitcher can appear on the default board after bullpen filtering.

    Active-only board inclusion requires a resolved active MLB roster state.
    Unknown roster state and historical workload/transaction evidence do not
    imply active roster eligibility.
    """
    return (status_payload or {}).get('is_active_mlb') is True


def allows_inactive_context(status_payload):
    status = (status_payload or {}).get('status') or STATUS_UNKNOWN
    return status in INACTIVE_STATUSES


def apply_roster_status_to_availability(availability, roster_status):
    """Prevent inactive roster statuses from rendering as workload Available."""
    merged = dict(availability or {})
    reasons = list(merged.get('reasons') or [])
    limitations = list(merged.get('limitations') or [])
    roster_status = roster_status or classify_roster_status(None)
    label = roster_status.get('label') or STATUS_LABELS[STATUS_UNKNOWN]

    for limitation in roster_status.get('limitations') or []:
        if limitation not in limitations:
            limitations.append(limitation)

    if roster_status.get('is_inactive_context'):
        reason = f'Roster status: {label}.'
        if reason not in reasons:
            reasons.insert(0, reason)
        limitation = 'Unavailable due to roster status; not available for bullpen planning.'
        if limitation not in limitations:
            limitations.append(limitation)
        merged['availability_status'] = STATUS_UNAVAILABLE
        merged['confidence'] = roster_status.get('confidence') or 'high'

    merged['reasons'] = reasons
    merged['limitations'] = limitations
    merged['roster_status'] = roster_status
    return merged


def roster_status_summary(statuses, included_records=None):
    """Summarize roster authority for top-level board trust messaging."""
    statuses = list(statuses or [])
    included_records = list(included_records or [])
    included_statuses = [
        record.get('roster_status') or {}
        for record in included_records
    ]

    known = [status for status in statuses if status.get('is_authoritative')]
    unknown = [status for status in statuses if not status.get('is_authoritative')]
    included_inactive = [status for status in included_statuses if status.get('is_inactive_context')]
    included_unknown = [status for status in included_statuses if not status.get('is_authoritative')]
    included_active = [status for status in included_statuses if status.get('is_active_mlb') is True]
    excluded_inactive = [
        status for status in statuses
        if status.get('is_inactive_context') and status not in included_statuses
    ]

    if not statuses:
        authority = 'none'
    elif not known:
        authority = 'unavailable'
    elif unknown:
        authority = 'partial'
    else:
        authority = 'available'

    limitations = []
    if unknown:
        limitations.append(ROSTER_STATUS_UNAVAILABLE_LIMITATION)
    if included_inactive:
        limitations.append('Unavailable pitchers are shown for roster awareness and are not counted as active bullpen options.')

    return {
        'authority': authority,
        'total_candidates': len(statuses),
        'known_count': len(known),
        'unknown_count': len(unknown),
        'included_unknown_count': len(included_unknown),
        'active_mlb_count': len(included_active),
        'inactive_context_count': len(included_inactive),
        'excluded_inactive_count': len(excluded_inactive),
        'limitations': limitations,
    }
