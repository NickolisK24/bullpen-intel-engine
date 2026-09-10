"""Batch reader for frozen public Team Board Rotation Impact carriers.

This service projects two already-authored seven-day facts from the current
trusted Team Board package. It never queries starters or game logs, rebuilds a
Team Board, recalculates rotation burden, or forecasts future usage.
"""

from __future__ import annotations

import logging
from typing import Mapping

from services import public_serving_authority
from services.rotation_support_pressure import DELTA_CARRIER_CONTRACT
from services.team_board_delta_substrate import build_rotation_impact_capture


logger = logging.getLogger(__name__)


CAPABILITY = 'published_team_rotation_listing_v1'
CARRIER_CONTRACT = 'tonight_rotation_transfer_context_v1'
STATUS_OK = 'ok'
STATUS_SNAPSHOT_UNAVAILABLE = 'snapshot_unavailable'
STATUS_AVAILABLE = 'available'
STATUS_PARTIAL = 'partial'
STATUS_WITHHELD = 'withheld'
REASON_SNAPSHOT_UNAVAILABLE = 'trusted_dashboard_snapshot_unavailable'
REASON_TEAM_MISSING = 'published_team_rotation_missing'
REASON_AUTHORITY_INVALID = 'published_team_rotation_authority_invalid'
REASON_PARTIAL = 'published_team_rotation_partial'


def withheld_rotation_context(reason_code, *, reference_date=None):
    return {
        'contract': CARRIER_CONTRACT,
        'source_contract': DELTA_CARRIER_CONTRACT,
        'status': STATUS_WITHHELD,
        'reason_code': reason_code,
        'reference_date': reference_date,
        'window_days': None,
        'short_start_count': None,
        'bullpen_innings_required': None,
    }


def _project_team(snapshot, team_id):
    try:
        capture = build_rotation_impact_capture(
            snapshot=snapshot,
            team_id=team_id,
        )
    except Exception:  # noqa: BLE001 - one invalid team remains side-local
        logger.warning(
            'Published Rotation Impact carrier withheld team_id=%s',
            team_id,
            exc_info=True,
        )
        return withheld_rotation_context(REASON_AUTHORITY_INVALID)
    if not isinstance(capture, Mapping):
        return withheld_rotation_context(REASON_TEAM_MISSING)

    value = capture.get('value')
    if not isinstance(value, Mapping):
        return withheld_rotation_context(REASON_AUTHORITY_INVALID)

    limitations = list(value.get('limitations') or [])
    reason_codes = list(value.get('limitation_reasons') or [])
    partial = value.get('status') == 'limited_read' or bool(limitations)
    games_analyzed = value.get('games_analyzed')
    has_completed_rotation_facts = (
        type(games_analyzed) is int and games_analyzed > 0
    )

    short_starts = value.get('short_start_count')
    if type(short_starts) is not int or short_starts < 0:
        short_starts = None
    bullpen_innings = value.get('bullpen_innings_required')
    if (
        isinstance(bullpen_innings, bool)
        or not isinstance(bullpen_innings, (int, float))
        or bullpen_innings < 0
    ):
        bullpen_innings = None

    # The canonical owner uses zero-valued metrics together with a limited read
    # when no rotation starts were established. Keep those missing facts absent;
    # genuine zero remains visible once at least one governed start was analyzed.
    if not has_completed_rotation_facts:
        short_starts = None
        bullpen_innings = None

    return {
        'contract': CARRIER_CONTRACT,
        'source_contract': capture.get('carrier_contract_version'),
        'status': STATUS_PARTIAL if partial else STATUS_AVAILABLE,
        'reason_code': (reason_codes or [REASON_PARTIAL if partial else None])[0],
        'reference_date': capture.get('reference_date'),
        'window_days': value.get('window_days'),
        'short_start_count': short_starts,
        'bullpen_innings_required': bullpen_innings,
    }


def build_published_team_rotation_listing(*, snapshot_resolver=None):
    """Return narrow Rotation Impact carriers from one trusted snapshot."""
    if snapshot_resolver is None:
        from services.league_team_state_listing import (
            resolve_current_trusted_dashboard_snapshot,
        )
        snapshot_resolver = resolve_current_trusted_dashboard_snapshot

    snapshot, unavailable_reason = snapshot_resolver()
    if snapshot is None:
        return {
            'capability': CAPABILITY,
            'status': STATUS_SNAPSHOT_UNAVAILABLE,
            'reason_code': unavailable_reason or REASON_SNAPSHOT_UNAVAILABLE,
            'teams': [],
        }

    payload = getattr(snapshot, 'payload', None)
    package = (
        payload.get(public_serving_authority.TEAM_BOARD_PACKAGE_KEY)
        if isinstance(payload, Mapping)
        else None
    )
    by_team_id = package.get('by_team_id') if isinstance(package, Mapping) else None
    if not isinstance(by_team_id, Mapping):
        return {
            'capability': CAPABILITY,
            'status': STATUS_SNAPSHOT_UNAVAILABLE,
            'reason_code': REASON_AUTHORITY_INVALID,
            'teams': [],
        }

    rows = []
    for raw_team_id in by_team_id:
        try:
            team_id = int(raw_team_id)
        except (TypeError, ValueError):
            continue
        rows.append({
            'team_id': team_id,
            'rotation_context': _project_team(snapshot, team_id),
        })
    rows.sort(key=lambda row: row['team_id'])
    return {
        'capability': CAPABILITY,
        'status': STATUS_OK,
        'reason_code': None,
        'teams': rows,
    }
