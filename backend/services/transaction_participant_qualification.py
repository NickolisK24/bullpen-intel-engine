"""Governed bullpen relevance for transaction participants.

Qualification is authored during transaction ingestion from explicit MLB
position evidence. Public readers consume only the persisted result; they do
not contact MLB or infer role from missing Pitcher rows.
"""

from __future__ import annotations

from dataclasses import dataclass


ROLE_PITCHER = 'pitcher'
ROLE_NON_PITCHER = 'non_pitcher'
ROLE_UNRESOLVED = 'unresolved'

AUTHORITY_CANONICAL_PITCHER = 'canonical_pitcher_identity_v1'
AUTHORITY_MLB_PEOPLE = 'mlb_people_primary_position_v1'
AUTHORITY_MLB_TRANSACTION = 'mlb_transaction_primary_position_v1'
AUTHORITY_UNRESOLVED = 'unresolved'

PITCHER_POSITION_CODES = frozenset({'1'})
PITCHER_POSITION_ABBREVIATIONS = frozenset({'P'})
TWO_WAY_POSITION_CODES = frozenset({'Y'})
TWO_WAY_POSITION_ABBREVIATIONS = frozenset({'TWP'})


@dataclass(frozen=True)
class TransactionParticipantQualificationBatch:
    qualifications: dict
    people_by_mlb_id: dict


def _text(value):
    value = str(value).strip() if value is not None else ''
    return value or None


def position_fields(position):
    position = position or {}
    return {
        'participant_position_code': _text(position.get('code')),
        'participant_position_abbreviation': _text(position.get('abbreviation')),
        'participant_position_type': _text(position.get('type')),
    }


def classify_position(*, code=None, abbreviation=None, position_type=None):
    """Classify only explicit position evidence.

    Two-way evidence remains pitcher-relevant. Missing evidence remains
    unresolved; absence of a canonical Pitcher is never non-pitcher proof.
    """
    code = (_text(code) or '').upper()
    abbreviation = (_text(abbreviation) or '').upper()
    position_type = (_text(position_type) or '').lower()
    if (
        code in TWO_WAY_POSITION_CODES
        or abbreviation in TWO_WAY_POSITION_ABBREVIATIONS
        or 'two-way' in position_type
    ):
        return ROLE_PITCHER
    if (
        code in PITCHER_POSITION_CODES
        or abbreviation in PITCHER_POSITION_ABBREVIATIONS
        or position_type == 'pitcher'
    ):
        return ROLE_PITCHER
    if code or abbreviation or position_type:
        return ROLE_NON_PITCHER
    return ROLE_UNRESOLVED


def qualification_from_position(position, *, authority):
    fields = position_fields(position)
    role = classify_position(
        code=fields['participant_position_code'],
        abbreviation=fields['participant_position_abbreviation'],
        position_type=fields['participant_position_type'],
    )
    return {
        'participant_role': role,
        'participant_role_authority': authority if role != ROLE_UNRESOLVED else AUTHORITY_UNRESOLVED,
        **fields,
    }


def pitcher_qualification():
    return {
        'participant_role': ROLE_PITCHER,
        'participant_role_authority': AUTHORITY_CANONICAL_PITCHER,
        'participant_position_code': None,
        'participant_position_abbreviation': None,
        'participant_position_type': None,
    }


def unresolved_qualification():
    return {
        'participant_role': ROLE_UNRESOLVED,
        'participant_role_authority': AUTHORITY_UNRESOLVED,
        'participant_position_code': None,
        'participant_position_abbreviation': None,
        'participant_position_type': None,
    }


def source_position(transaction):
    transaction = transaction or {}
    return {
        'code': transaction.get('participant_position_code'),
        'abbreviation': transaction.get('participant_position_abbreviation'),
        'type': transaction.get('participant_position_type'),
    }


def qualify_transactions_with_people(transactions, *, pitchers_by_mlb_id, client):
    """Return qualifications and reusable MLB person authority in one batch.

    Missing canonical identities whose structured transaction evidence already
    looks pitcher-relevant still enter the people lookup.  Canonical acquisition
    requires MLB person authority and must never rely on the transaction shape
    alone.
    """
    qualifications = {}
    lookup_ids = set()
    for transaction in transactions:
        if not isinstance(transaction, dict):
            continue
        try:
            mlb_id = int(transaction.get('player_mlb_id'))
        except (TypeError, ValueError):
            continue
        if mlb_id in pitchers_by_mlb_id:
            qualifications[mlb_id] = pitcher_qualification()
            continue
        source = qualification_from_position(
            source_position(transaction),
            authority=AUTHORITY_MLB_TRANSACTION,
        )
        if source['participant_role'] != ROLE_UNRESOLVED:
            qualifications[mlb_id] = source
            if source['participant_role'] == ROLE_PITCHER:
                lookup_ids.add(mlb_id)
        else:
            lookup_ids.add(mlb_id)

    people = {}
    if lookup_ids:
        try:
            people = client.get_people_info(sorted(lookup_ids)) or {}
        except Exception:  # fail closed; source availability must not imply role
            people = {}
    for mlb_id in lookup_ids:
        person = people.get(mlb_id) or people.get(str(mlb_id)) or {}
        person_qualification = qualification_from_position(
            person.get('primaryPosition') or {},
            authority=AUTHORITY_MLB_PEOPLE,
        )
        if (
            person_qualification['participant_role'] != ROLE_UNRESOLVED
            or mlb_id not in qualifications
        ):
            qualifications[mlb_id] = person_qualification
    people_by_mlb_id = {}
    for raw_id, person in people.items():
        try:
            mlb_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if person:
            people_by_mlb_id[mlb_id] = person
    return TransactionParticipantQualificationBatch(
        qualifications=qualifications,
        people_by_mlb_id=people_by_mlb_id,
    )


def qualify_transactions(transactions, *, pitchers_by_mlb_id, client):
    """Backward-compatible qualification-only wrapper."""
    return qualify_transactions_with_people(
        transactions,
        pitchers_by_mlb_id=pitchers_by_mlb_id,
        client=client,
    ).qualifications


def is_proven_non_pitcher(row):
    """Revalidate stored non-pitcher evidence instead of trusting a stamp."""
    if getattr(row, 'participant_role', None) != ROLE_NON_PITCHER:
        return False
    if getattr(row, 'participant_role_authority', None) not in {
        AUTHORITY_MLB_PEOPLE,
        AUTHORITY_MLB_TRANSACTION,
    }:
        return False
    return classify_position(
        code=getattr(row, 'participant_position_code', None),
        abbreviation=getattr(row, 'participant_position_abbreviation', None),
        position_type=getattr(row, 'participant_position_type', None),
    ) == ROLE_NON_PITCHER
