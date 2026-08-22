"""Persisted authority for non-material pitcher rehab assignments.

Raw ``ASG`` means only "Assigned" and remains an unknown public transaction
category.  This module certifies the narrower rehab subtype only from typed,
transaction-time evidence authored during ingestion.  Public readers revalidate
the persisted evidence without querying rosters or contacting MLB.
"""

from __future__ import annotations

from services.transaction_participant_qualification import ROLE_NON_PITCHER, ROLE_PITCHER


RAW_CODE_ASG = 'ASG'
MLB_SPORT_ID = 1

SUBTYPE_REHAB_ASSIGNMENT = 'rehab_assignment'
MATERIALITY_NON_MATERIAL = 'non_material'
MATERIALITY_UNRESOLVED = 'unresolved'

STATUS_CERTIFIED = 'certified'
STATUS_NOT_CERTIFIED = 'not_certified'
STATUS_UNRESOLVED = 'unresolved'

AUTHORITY = 'asg_pitcher_rehab_assignment_v1'
AUTHORITY_UNRESOLVED = 'unresolved'

REASON_CERTIFIED = 'certified_rehab_assignment'
REASON_NOT_ASG = 'not_asg'
REASON_NON_PITCHER = 'participant_proven_non_pitcher'
REASON_PITCHER_MISSING = 'canonical_pitcher_missing'
REASON_SOURCE_TEAM_MISSING = 'source_team_missing'
REASON_SOURCE_METADATA_MISSING = 'source_team_metadata_missing'
REASON_SOURCE_METADATA_INCOMPATIBLE = 'source_team_metadata_incompatible'
REASON_SOURCE_NOT_MLB = 'source_team_not_mlb'
REASON_DESTINATION_MISSING = 'destination_team_missing'
REASON_DESTINATION_METADATA_MISSING = 'destination_team_metadata_missing'
REASON_DESTINATION_METADATA_INCOMPATIBLE = 'destination_team_metadata_incompatible'
REASON_DESTINATION_IS_MLB = 'destination_team_is_mlb'
REASON_PARENT_MISMATCH = 'destination_parent_org_mismatch'
REASON_SNAPSHOT_MISSING = 'exact_roster_snapshot_missing'
REASON_SNAPSHOT_DATE_MISMATCH = 'roster_snapshot_date_mismatch'
REASON_SNAPSHOT_TEAM_MISMATCH = 'roster_snapshot_team_mismatch'
REASON_ACTIVE_ROSTER = 'roster_snapshot_active'
REASON_NOT_IL = 'roster_snapshot_not_pitcher_il'

CERTIFIED_IL_STATUSES = frozenset({'IL_15', 'IL_60'})


def _text(value):
    value = str(value).strip() if value is not None else ''
    return value or None


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _base(status, reason_code):
    return {
        'transaction_subtype': None,
        'transaction_materiality': MATERIALITY_UNRESOLVED,
        'subtype_status': status,
        'subtype_authority': AUTHORITY if status != STATUS_UNRESOLVED else AUTHORITY_UNRESOLVED,
        'subtype_reason_code': reason_code,
        'subtype_evidence': None,
    }


def _unresolved(reason_code):
    return _base(STATUS_UNRESOLVED, reason_code)


def _not_certified(reason_code):
    return _base(STATUS_NOT_CERTIFIED, reason_code)


def classify_rehab_assignment(
    *,
    transaction_type_code,
    pitcher,
    participant_role,
    from_team_id,
    to_team_id,
    transaction_date,
    source_team_metadata,
    destination_team_metadata,
    roster_snapshot,
):
    """Return the persisted rehab subtype authority for one source row."""
    if (_text(transaction_type_code) or '').upper() != RAW_CODE_ASG:
        return _not_certified(REASON_NOT_ASG)
    if pitcher is None:
        if participant_role == ROLE_NON_PITCHER:
            return _not_certified(REASON_NON_PITCHER)
        return _unresolved(REASON_PITCHER_MISSING)
    if participant_role != ROLE_PITCHER:
        return _unresolved(REASON_PITCHER_MISSING)

    from_team_id = _int(from_team_id)
    to_team_id = _int(to_team_id)
    if from_team_id is None:
        return _unresolved(REASON_SOURCE_TEAM_MISSING)
    if not source_team_metadata:
        return _unresolved(REASON_SOURCE_METADATA_MISSING)
    if (
        _int(source_team_metadata.get('team_id')) != from_team_id
        or _int(source_team_metadata.get('season')) != transaction_date.year
        or _int(source_team_metadata.get('sport_id')) is None
    ):
        return _unresolved(REASON_SOURCE_METADATA_INCOMPATIBLE)
    if _int(source_team_metadata.get('sport_id')) != MLB_SPORT_ID:
        return _not_certified(REASON_SOURCE_NOT_MLB)
    if to_team_id is None:
        return _unresolved(REASON_DESTINATION_MISSING)
    if not destination_team_metadata:
        return _unresolved(REASON_DESTINATION_METADATA_MISSING)
    destination_sport_id = _int(destination_team_metadata.get('sport_id'))
    destination_parent_org_id = _int(destination_team_metadata.get('parent_org_id'))
    if (
        _int(destination_team_metadata.get('team_id')) != to_team_id
        or _int(destination_team_metadata.get('season')) != transaction_date.year
        or destination_sport_id is None
    ):
        return _unresolved(REASON_DESTINATION_METADATA_INCOMPATIBLE)
    if destination_sport_id == MLB_SPORT_ID:
        return _not_certified(REASON_DESTINATION_IS_MLB)
    if destination_parent_org_id is None:
        return _unresolved(REASON_DESTINATION_METADATA_INCOMPATIBLE)
    if destination_parent_org_id != from_team_id:
        return _not_certified(REASON_PARENT_MISMATCH)

    if roster_snapshot is None:
        return _unresolved(REASON_SNAPSHOT_MISSING)
    if roster_snapshot.snapshot_date != transaction_date:
        return _unresolved(REASON_SNAPSHOT_DATE_MISMATCH)
    if _int(roster_snapshot.team_id) != from_team_id:
        return _unresolved(REASON_SNAPSHOT_TEAM_MISMATCH)
    if roster_snapshot.active_roster is not False:
        return _not_certified(REASON_ACTIVE_ROSTER)
    if roster_snapshot.roster_status not in CERTIFIED_IL_STATUSES:
        return _not_certified(REASON_NOT_IL)

    evidence = {
        'authority': AUTHORITY,
        'transaction_type_code': RAW_CODE_ASG,
        'pitcher_id': pitcher.id,
        'player_mlb_id': pitcher.mlb_id,
        'participant_role': ROLE_PITCHER,
        'from_team_id': from_team_id,
        'to_team_id': to_team_id,
        'destination_team_id': _int(destination_team_metadata.get('team_id')),
        'destination_sport_id': destination_sport_id,
        'destination_parent_org_id': destination_parent_org_id,
        'metadata_season': _int(destination_team_metadata.get('season')),
        'roster_snapshot_id': roster_snapshot.id,
        'roster_snapshot_date': roster_snapshot.snapshot_date.isoformat(),
        'roster_team_id': roster_snapshot.team_id,
        'roster_status': roster_snapshot.roster_status,
        'active_roster': roster_snapshot.active_roster,
    }
    return {
        'transaction_subtype': SUBTYPE_REHAB_ASSIGNMENT,
        'transaction_materiality': MATERIALITY_NON_MATERIAL,
        'subtype_status': STATUS_CERTIFIED,
        'subtype_authority': AUTHORITY,
        'subtype_reason_code': REASON_CERTIFIED,
        'subtype_evidence': evidence,
    }


def is_certified_non_material_rehab_assignment(row):
    """Revalidate stored certification without queries or source acquisition."""
    evidence = getattr(row, 'subtype_evidence', None)
    transaction_date = getattr(row, 'transaction_date', None)
    if not isinstance(evidence, dict) or transaction_date is None:
        return False
    if (
        getattr(row, 'transaction_subtype', None) != SUBTYPE_REHAB_ASSIGNMENT
        or getattr(row, 'transaction_materiality', None) != MATERIALITY_NON_MATERIAL
        or getattr(row, 'subtype_status', None) != STATUS_CERTIFIED
        or getattr(row, 'subtype_authority', None) != AUTHORITY
        or getattr(row, 'subtype_reason_code', None) != REASON_CERTIFIED
        or (_text(getattr(row, 'transaction_type_code', None)) or '').upper() != RAW_CODE_ASG
        or getattr(row, 'pitcher_id', None) is None
        or getattr(row, 'participant_role', None) != ROLE_PITCHER
    ):
        return False
    return (
        evidence.get('authority') == AUTHORITY
        and evidence.get('transaction_type_code') == RAW_CODE_ASG
        and _int(evidence.get('pitcher_id')) == _int(getattr(row, 'pitcher_id', None))
        and _int(evidence.get('player_mlb_id')) == _int(getattr(row, 'player_mlb_id', None))
        and evidence.get('participant_role') == ROLE_PITCHER
        and _int(evidence.get('from_team_id')) == _int(getattr(row, 'from_team_id', None))
        and _int(evidence.get('to_team_id')) == _int(getattr(row, 'to_team_id', None))
        and _int(evidence.get('destination_team_id')) == _int(getattr(row, 'to_team_id', None))
        and _int(evidence.get('destination_sport_id')) is not None
        and _int(evidence.get('destination_sport_id')) != MLB_SPORT_ID
        and _int(evidence.get('destination_parent_org_id')) == _int(getattr(row, 'from_team_id', None))
        and _int(evidence.get('metadata_season')) == transaction_date.year
        and evidence.get('roster_snapshot_date') == transaction_date.isoformat()
        and _int(evidence.get('roster_team_id')) == _int(getattr(row, 'from_team_id', None))
        and evidence.get('roster_status') in CERTIFIED_IL_STATUSES
        and evidence.get('active_roster') is False
        and _int(evidence.get('roster_snapshot_id')) is not None
    )


__all__ = [
    'AUTHORITY',
    'MATERIALITY_NON_MATERIAL',
    'STATUS_CERTIFIED',
    'SUBTYPE_REHAB_ASSIGNMENT',
    'classify_rehab_assignment',
    'is_certified_non_material_rehab_assignment',
]
