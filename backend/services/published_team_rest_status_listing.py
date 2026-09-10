"""Batch reader for frozen public Team Board Rest Status carriers.

This service projects each team's already-authored D-055 Rest Status from one
current trusted Dashboard snapshot. It never rebuilds Team Board, counts cards,
or recalculates calendar rest.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Mapping

from services import public_serving_authority
from services.team_board_delta_substrate import build_rest_status_capture


logger = logging.getLogger(__name__)

CAPABILITY = 'published_team_rest_status_listing_v1'
STATUS_OK = 'ok'
STATUS_SNAPSHOT_UNAVAILABLE = 'snapshot_unavailable'
REASON_SNAPSHOT_UNAVAILABLE = 'trusted_dashboard_snapshot_unavailable'
REASON_TEAM_MISSING = 'published_team_rest_status_missing'
REASON_AUTHORITY_INVALID = 'published_team_rest_status_authority_invalid'


def unavailable_rest_status(reason_code):
    return {
        'available': False,
        'active_arm_count': None,
        'rested_arm_count': None,
        'worked_yesterday_count': None,
        'back_to_back_count': None,
        'summary': None,
        'reason_code': reason_code,
    }


def _project_team(snapshot, team_id):
    try:
        capture = build_rest_status_capture(snapshot=snapshot, team_id=team_id)
    except Exception:  # noqa: BLE001 - one invalid team remains side-local
        logger.warning(
            'Published Rest Status carrier withheld team_id=%s',
            team_id,
            exc_info=True,
        )
        return unavailable_rest_status(REASON_AUTHORITY_INVALID)
    if not isinstance(capture, Mapping):
        return unavailable_rest_status(REASON_TEAM_MISSING)
    value = capture.get('value')
    if not isinstance(value, Mapping):
        return unavailable_rest_status(REASON_AUTHORITY_INVALID)
    return deepcopy(dict(value))


def build_published_team_rest_status_listing(*, snapshot_resolver=None):
    """Return exact frozen D-055 carriers from one trusted snapshot."""
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
            'rest_status': _project_team(snapshot, team_id),
        })
    rows.sort(key=lambda row: row['team_id'])
    return {
        'capability': CAPABILITY,
        'status': STATUS_OK,
        'reason_code': None,
        'teams': rows,
    }
