"""Canonical, team-neutral Pitcher acquisition from MLB person authority.

Transaction endpoints and transaction copy are historical/event evidence, not
current-team or roster authority.  This writer therefore creates only the
minimal canonical identity already governed by D-009, and only when MLB person
``primaryPosition`` explicitly proves pitcher or two-way status.
"""

from __future__ import annotations

from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from models.pitcher import Pitcher
from services import pitcher_identity_reconciliation as pitcher_identity
from services.transaction_participant_qualification import (
    TWO_WAY_POSITION_ABBREVIATIONS,
    TWO_WAY_POSITION_CODES,
    ROLE_PITCHER,
    ROLE_UNRESOLVED,
    classify_position,
)
from utils.db import db


SOURCE = 'mlb_stats_api:transaction_participant_identity'
ROSTER_DESCRIPTION = 'MLB person identity; roster status unverified'

assert len(SOURCE) <= Pitcher.roster_status_source.type.length
assert len(ROSTER_DESCRIPTION) <= Pitcher.roster_status_raw_description.type.length


def _positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _position(person):
    return (person or {}).get('primaryPosition') or {}


def _canonical_position(person):
    position = _position(person)
    evidence = (
        classify_position(code=position.get('code')),
        classify_position(abbreviation=position.get('abbreviation')),
        classify_position(position_type=position.get('type')),
    )
    resolved = {value for value in evidence if value != ROLE_UNRESOLVED}
    if resolved != {ROLE_PITCHER}:
        return None
    code = str(position.get('code') or '').strip().upper()
    abbreviation = str(position.get('abbreviation') or '').strip().upper()
    position_type = str(position.get('type') or '').strip().lower()
    return (
        'TWP'
        if (
            code in TWO_WAY_POSITION_CODES
            or abbreviation in TWO_WAY_POSITION_ABBREVIATIONS
            or 'two-way' in position_type
        )
        else 'P'
    )


def _creation_values(mlb_id, person):
    if _positive_int((person or {}).get('id')) != mlb_id:
        return None
    canonical_position = _canonical_position(person)
    if canonical_position is None:
        return None
    name = str((person or {}).get('fullName') or '').strip()
    if not name:
        return None
    return pitcher_identity.minimal_identity_values(
        player_mlb_id=mlb_id,
        line_name=name[:100],
        line_position=canonical_position,
        source_authority=SOURCE,
        roster_description=ROSTER_DESCRIPTION,
    )


def acquire_canonical_transaction_pitchers(
    *, people_by_mlb_id, pitchers_by_mlb_id
):
    """Bulk-acquire missing canonical identities and return the refreshed map.

    One conflict-safe insert handles repeated transactions, repeated syncs, and
    a canonical row committed after the caller's initial prefetch.  One bounded
    refresh SELECT returns the winning canonical rows; no per-person query or
    commit occurs here.
    """
    existing = dict(pitchers_by_mlb_id or {})
    values = []
    candidate_ids = set()
    for raw_id, person in (people_by_mlb_id or {}).items():
        mlb_id = _positive_int(raw_id)
        if mlb_id is None or mlb_id in existing:
            continue
        creation = _creation_values(mlb_id, person)
        if creation is None:
            continue
        values.append(creation)
        candidate_ids.add(mlb_id)

    inserted = 0
    if values:
        dialect = db.session.get_bind().dialect.name
        if dialect == 'postgresql':
            statement = postgresql_insert(Pitcher).values(values)
            statement = statement.on_conflict_do_nothing(index_elements=['mlb_id'])
        elif dialect == 'sqlite':
            statement = sqlite_insert(Pitcher).values(values)
            statement = statement.on_conflict_do_nothing(index_elements=['mlb_id'])
        else:  # pragma: no cover - supported application/test dialects are above
            raise RuntimeError(
                f'Canonical transaction pitcher acquisition does not support {dialect}.'
            )
        result = db.session.execute(statement)
        inserted = max(int(result.rowcount or 0), 0)
        db.session.flush()
        acquired = Pitcher.query.filter(Pitcher.mlb_id.in_(candidate_ids)).all()
        existing.update({pitcher.mlb_id: pitcher for pitcher in acquired})

    return {
        'pitchers_by_mlb_id': existing,
        'candidate_ids': tuple(sorted(candidate_ids)),
        'created_count': inserted,
    }


__all__ = [
    'ROSTER_DESCRIPTION',
    'SOURCE',
    'acquire_canonical_transaction_pitchers',
]
