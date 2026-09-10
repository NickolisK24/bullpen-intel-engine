"""Reader-safe recent transaction chronology for one Team Board.

This projection reads the existing typed ``PlayerTransaction`` owner and its
bounded source sync window. It does not ingest, normalize, classify, persist,
or infer roster impact.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import or_

from models.pitcher import Pitcher
from models.player_transaction import PlayerTransaction
from services.availability_reference_date import product_current_date
from services.transaction_ingestion import (
    CATEGORY_BEREAVEMENT,
    CATEGORY_CONTRACT_SELECTION,
    CATEGORY_DFA,
    CATEGORY_IL_ACTIVATION,
    CATEGORY_IL_PLACEMENT,
    CATEGORY_OPTION,
    CATEGORY_OUTRIGHT,
    CATEGORY_PATERNITY,
    CATEGORY_RECALL,
    CATEGORY_RELEASE,
    CATEGORY_RESTRICTED,
    CATEGORY_ROSTER_ACTIVATION,
    CATEGORY_ROSTER_DEACTIVATION,
    CATEGORY_SUSPENSION,
    CATEGORY_TRADE,
    CATEGORY_WAIVER_CLAIM,
    TRANSACTION_STALE_AFTER_DAYS,
    WINDOW_STATUS_PARTIAL,
    WINDOW_STATUS_SUCCESS,
    latest_transaction_sync_window,
)
from services.transaction_participant_qualification import is_proven_non_pitcher
from services.transaction_rehab_assignment import (
    is_certified_non_material_rehab_assignment,
)


CAPABILITY = 'public_recent_transactions_v1'
VERSION = '2026-08-20.rotation-roster'
POPULATION_BASIS = (
    'explanatory_eligible_pitcher_transactions_touching_selected_team_'
    'in_latest_source_sync_window'
)

STATUS_AVAILABLE = 'available'
STATUS_PARTIAL = 'partial'
STATUS_UNAVAILABLE = 'unavailable'

TRANSACTION_PUBLIC_LABELS = {
    CATEGORY_RECALL: 'Recalled',
    CATEGORY_OPTION: 'Optioned',
    CATEGORY_IL_PLACEMENT: 'Placed on injured list',
    CATEGORY_IL_ACTIVATION: 'Activated from injured list',
    CATEGORY_ROSTER_ACTIVATION: 'Activated',
    CATEGORY_ROSTER_DEACTIVATION: 'Deactivated',
    CATEGORY_TRADE: 'Traded',
    CATEGORY_DFA: 'Designated for assignment',
    CATEGORY_OUTRIGHT: 'Outrighted',
    CATEGORY_RELEASE: 'Released',
    CATEGORY_CONTRACT_SELECTION: 'Contract selected',
    CATEGORY_WAIVER_CLAIM: 'Claimed off waivers',
    CATEGORY_SUSPENSION: 'Suspended',
    CATEGORY_BEREAVEMENT: 'Placed on bereavement list',
    CATEGORY_PATERNITY: 'Placed on paternity list',
    CATEGORY_RESTRICTED: 'Placed on restricted list',
}

TRANSACTION_PUBLIC_DESCRIPTIONS = {
    CATEGORY_RECALL: '{name} was recalled.',
    CATEGORY_OPTION: '{name} was optioned.',
    CATEGORY_IL_PLACEMENT: '{name} was placed on the injured list.',
    CATEGORY_IL_ACTIVATION: '{name} was activated from the injured list.',
    CATEGORY_ROSTER_ACTIVATION: '{name} was activated.',
    CATEGORY_ROSTER_DEACTIVATION: '{name} was deactivated.',
    CATEGORY_TRADE: '{name} was traded.',
    CATEGORY_DFA: '{name} was designated for assignment.',
    CATEGORY_OUTRIGHT: '{name} was outrighted.',
    CATEGORY_RELEASE: '{name} was released.',
    CATEGORY_CONTRACT_SELECTION: "{name}'s contract was selected.",
    CATEGORY_WAIVER_CLAIM: '{name} was claimed off waivers.',
    CATEGORY_SUSPENSION: '{name} was suspended.',
    CATEGORY_BEREAVEMENT: '{name} was placed on the bereavement list.',
    CATEGORY_PATERNITY: '{name} was placed on the paternity list.',
    CATEGORY_RESTRICTED: '{name} was placed on the restricted list.',
}

SOURCE_UNAVAILABLE_LIMITATION = 'Recent official transaction records are unavailable.'
SOURCE_STALE_LIMITATION = 'Recent official transaction records have not been verified recently.'
SOURCE_WINDOW_NOT_COVERED_LIMITATION = (
    'Recent official transaction records do not cover the represented Team Board date.'
)
SOURCE_PARTIAL_LIMITATION = 'Some records from the latest transaction source window are unavailable.'
WITHHELD_EVENT_LIMITATION = (
    'Some recent transaction records are withheld because player identity, event type, '
    'or team attribution could not be verified.'
)


def _iso(value):
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _coerce_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _unavailable(*, limitation, represented_date=None):
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'population_basis': POPULATION_BASIS,
        'status': STATUS_UNAVAILABLE,
        'events': [],
        'window_start_date': None,
        'window_end_date': None,
        'represented_date': _iso(represented_date),
        'limitations': [limitation],
    }


def project_qualified_public_transaction(row, pitcher):
    """Project one already-ingested transaction through the public qualifier.

    This is the shared semantic boundary for Team Board chronology and History.
    Callers may format or group the returned identity facts, but they must not
    recreate category qualification, public wording, or participant exclusions.
    """
    if is_proven_non_pitcher(row):
        return None
    if is_certified_non_material_rehab_assignment(row):
        return None

    label = TRANSACTION_PUBLIC_LABELS.get(row.normalized_category)
    description_template = TRANSACTION_PUBLIC_DESCRIPTIONS.get(
        row.normalized_category
    )
    player_name = str(getattr(pitcher, 'full_name', '') or '').strip()
    if (
        row.explanatory_linkage_eligible is not True
        or pitcher is None
        or not player_name
        or not label
        or not description_template
    ):
        return None

    return {
        'transaction_key': row.transaction_key,
        'transaction_id': row.transaction_id,
        'transaction_date': _iso(row.transaction_date),
        'normalized_category': row.normalized_category,
        'label': label,
        'description': description_template.format(name=player_name),
        'pitcher': {
            'pitcher_id': row.pitcher_id,
            'player_mlb_id': row.player_mlb_id,
            'name': player_name,
        },
        'from_team_id': row.from_team_id,
        'to_team_id': row.to_team_id,
    }


def build_public_recent_transactions(team_id, *, reference_date=None):
    """Return the latest governed transaction window for ``team_id``.

    The latest sync window is the existing bounded depth owner. Events must
    already be typed, identity-resolved, roster-aligned, and explicitly marked
    explanatory-eligible by ingestion. Rows touching the selected team as
    either source or destination are included; current pitcher assignment is
    never used for event-team attribution.
    """
    window = latest_transaction_sync_window()
    if window is None:
        return _unavailable(limitation=SOURCE_UNAVAILABLE_LIMITATION)

    start_date = _coerce_date(window.source_query_start_date)
    end_date = _coerce_date(window.source_query_end_date)
    ref = _coerce_date(reference_date) or product_current_date()
    if (
        window.status not in (WINDOW_STATUS_SUCCESS, WINDOW_STATUS_PARTIAL)
        or start_date is None
        or end_date is None
    ):
        return _unavailable(
            limitation=SOURCE_UNAVAILABLE_LIMITATION,
            represented_date=end_date,
        )
    if ref is not None and (ref - end_date).days > TRANSACTION_STALE_AFTER_DAYS:
        return _unavailable(
            limitation=SOURCE_STALE_LIMITATION,
            represented_date=end_date,
        )
    represented_date = min(end_date, ref) if ref is not None else end_date
    if represented_date < start_date:
        return _unavailable(
            limitation=SOURCE_WINDOW_NOT_COVERED_LIMITATION,
            represented_date=represented_date,
        )

    rows = (
        PlayerTransaction.query
        .filter(PlayerTransaction.transaction_date >= start_date)
        .filter(PlayerTransaction.transaction_date <= represented_date)
        .filter(or_(
            PlayerTransaction.from_team_id == team_id,
            PlayerTransaction.to_team_id == team_id,
        ))
        .order_by(
            PlayerTransaction.transaction_date.desc(),
            PlayerTransaction.transaction_key.asc(),
            PlayerTransaction.id.asc(),
        )
        .all()
    )
    pitcher_ids = {
        row.pitcher_id
        for row in rows
        if row.pitcher_id is not None
    }
    pitchers = {
        pitcher.id: pitcher
        for pitcher in (
            Pitcher.query.filter(Pitcher.id.in_(pitcher_ids)).all()
            if pitcher_ids else []
        )
    }

    events = []
    withheld_count = 0
    for row in rows:
        pitcher = pitchers.get(row.pitcher_id)
        projected = project_qualified_public_transaction(row, pitcher)
        if projected is None:
            if is_proven_non_pitcher(row) or is_certified_non_material_rehab_assignment(row):
                continue
            withheld_count += 1
            continue
        events.append({
            'event_id': row.transaction_id or row.transaction_key,
            'player_id': row.pitcher_id,
            'player_mlb_id': row.player_mlb_id,
            'player_name': projected['pitcher']['name'],
            'date': projected['transaction_date'],
            'type': projected['normalized_category'],
            'label': projected['label'],
            'description': projected['description'],
        })

    limitations = []
    if window.status == WINDOW_STATUS_PARTIAL:
        limitations.append(SOURCE_PARTIAL_LIMITATION)
    if withheld_count:
        limitations.append(WITHHELD_EVENT_LIMITATION)

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'population_basis': POPULATION_BASIS,
        'status': STATUS_PARTIAL if limitations else STATUS_AVAILABLE,
        'events': events,
        'window_start_date': _iso(start_date),
        'window_end_date': _iso(represented_date),
        'represented_date': _iso(represented_date),
        'limitations': limitations,
    }


__all__ = [
    'CAPABILITY',
    'POPULATION_BASIS',
    'TRANSACTION_PUBLIC_LABELS',
    'TRANSACTION_PUBLIC_DESCRIPTIONS',
    'VERSION',
    'build_public_recent_transactions',
    'project_qualified_public_transaction',
]
