"""Trusted-publication projection for the public Bullpen Landscape.

``build_landscape`` remains the publication-building computation.  This module
owns the public serving boundary: it projects only the Landscape and governed
Team States attached to one already-selected trusted Dashboard publication.
It never reads mutable availability rows or recalculates Team State.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Mapping

from services import dashboard_snapshot as dashboard_snapshot_service
from services import public_serving_authority
from services.league_team_state_listing import build_league_team_state_listing
from services.mlb_club_directory import EXPECTED_CLUB_COUNT, MLB_TEAM_IDS
from services.team_state_public_vocabulary import (
    PUBLIC_TEAM_STATE_CONTRACT,
    PUBLIC_TEAM_STATE_LABEL_SET,
)


CAPABILITY = 'tonights_bullpen_landscape'
STATUS_AVAILABLE = 'ok'
STATUS_UNAVAILABLE = 'snapshot_unavailable'
LANDSCAPE_MISSING = 'trusted_publication_landscape_missing'
LANDSCAPE_INCOMPLETE = 'trusted_publication_landscape_incomplete'
LANDSCAPE_AUTHORITY_INVALID = 'trusted_publication_landscape_authority_invalid'
LANDSCAPE_TEAM_STATE_INCOMPLETE = 'trusted_publication_team_states_incomplete'
LANDSCAPE_LANES = (
    'constrained_bullpens',
    'available_bullpens',
    'monitoring_concentration',
)


def _iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def _snapshot_identity(snapshot, *, available):
    if not available or snapshot is None:
        return {
            'served_from': 'snapshot_unavailable',
            'snapshot_type': dashboard_snapshot_service.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
            'snapshot_id': None,
            'sync_run_id': None,
            'data_through': None,
            'availability_reference_date': None,
            'snapshot_generated_at': None,
            'published_at': None,
            'payload_version': dashboard_snapshot_service.DASHBOARD_PAYLOAD_VERSION,
        }
    return {
        'served_from': 'trusted_dashboard_snapshot',
        'snapshot_type': snapshot.snapshot_type,
        'snapshot_id': snapshot.id,
        'sync_run_id': snapshot.sync_run_id,
        'data_through': _iso(snapshot.data_through),
        'availability_reference_date': _iso(snapshot.availability_reference_date),
        'snapshot_generated_at': _iso(snapshot.snapshot_generated_at),
        'published_at': _iso(snapshot.published_at),
        'payload_version': snapshot.payload_version,
    }


def unavailable_landscape(reason):
    """Return an explicit dependent-scope refusal with no league substitutes."""
    return {
        'capability': CAPABILITY,
        'status': STATUS_UNAVAILABLE,
        'reason': reason or 'dashboard_snapshot_missing',
        'ranking_applied': False,
        'selection_made': False,
        'prediction_applied': False,
        'reference_date': None,
        'teams_evaluated': None,
        'expected_team_count': EXPECTED_CLUB_COUNT,
        'team_count': None,
        'represented_team_count': None,
        'games': None,
        'constrained_bullpens': None,
        'available_bullpens': None,
        'monitoring_concentration': None,
        'teams': None,
        'freshness': {
            'data_through': None,
            'freshness_state': STATUS_UNAVAILABLE,
            'reason_codes': [reason or 'dashboard_snapshot_missing'],
        },
        'notes': [],
        'publication_authority': None,
        'snapshot': _snapshot_identity(None, available=False),
    }


def _governed_team_state(team_state, data_through):
    if not isinstance(team_state, Mapping):
        return False
    return (
        team_state.get('contract') == PUBLIC_TEAM_STATE_CONTRACT
        and team_state.get('available') is True
        and team_state.get('public_label') in PUBLIC_TEAM_STATE_LABEL_SET
        and team_state.get('data_through') == data_through
    )


def _complete_team_state_projection(listing, snapshot):
    if not isinstance(listing, Mapping) or listing.get('status') != STATUS_AVAILABLE:
        return None
    teams = listing.get('teams')
    if not isinstance(teams, list) or len(teams) != EXPECTED_CLUB_COUNT:
        return None
    if listing.get('team_count') != EXPECTED_CLUB_COUNT:
        return None
    if listing.get('represented_team_count') != EXPECTED_CLUB_COUNT:
        return None

    data_through = _iso(snapshot.data_through)
    by_team_id = {}
    for row in teams:
        if not isinstance(row, Mapping):
            return None
        team_id = row.get('team_id')
        if team_id not in MLB_TEAM_IDS or team_id in by_team_id:
            return None
        if not _governed_team_state(row.get('team_state'), data_through):
            return None
        by_team_id[team_id] = dict(row)
    if set(by_team_id) != set(MLB_TEAM_IDS):
        return None
    return by_team_id


def _project_lanes(landscape, team_states):
    projected = {}
    for lane in LANDSCAPE_LANES:
        entries = landscape.get(lane)
        if not isinstance(entries, list):
            return None
        seen = set()
        lane_entries = []
        for entry in entries:
            if not isinstance(entry, Mapping):
                return None
            team_id = entry.get('team_id')
            if team_id in seen or team_id not in team_states:
                return None
            seen.add(team_id)
            item = dict(entry)
            item['team_state'] = deepcopy(team_states[team_id]['team_state'])
            lane_entries.append(item)
        projected[lane] = lane_entries
    return projected


def build_public_landscape(
    snapshot,
    *,
    team_state_listing_builder=build_league_team_state_listing,
):
    """Project public Landscape from one exact trusted publication or withhold."""
    authority_reason = dashboard_snapshot_service.snapshot_unavailable_reason(snapshot)
    if authority_reason is not None:
        return unavailable_landscape(authority_reason)

    payload = snapshot.payload if isinstance(snapshot.payload, Mapping) else None
    landscape = payload.get('landscape') if payload is not None else None
    if not isinstance(landscape, Mapping):
        return unavailable_landscape(LANDSCAPE_MISSING)
    if landscape.get('capability') != CAPABILITY:
        return unavailable_landscape(LANDSCAPE_AUTHORITY_INVALID)
    if landscape.get('teams_evaluated') != EXPECTED_CLUB_COUNT:
        return unavailable_landscape(LANDSCAPE_INCOMPLETE)
    if landscape.get('reference_date') != _iso(snapshot.availability_reference_date):
        return unavailable_landscape(LANDSCAPE_AUTHORITY_INVALID)

    listing = team_state_listing_builder(
        snapshot_resolver=lambda: (snapshot, None),
        directory_loader=lambda: {},
    )
    team_states = _complete_team_state_projection(listing, snapshot)
    if team_states is None:
        return unavailable_landscape(LANDSCAPE_TEAM_STATE_INCOMPLETE)

    lanes = _project_lanes(landscape, team_states)
    if lanes is None:
        return unavailable_landscape(LANDSCAPE_INCOMPLETE)

    result = deepcopy(dict(landscape))
    result.update(lanes)
    result.update({
        'status': STATUS_AVAILABLE,
        'expected_team_count': EXPECTED_CLUB_COUNT,
        'team_count': EXPECTED_CLUB_COUNT,
        'represented_team_count': EXPECTED_CLUB_COUNT,
        'teams': [deepcopy(team_states[team_id]) for team_id in sorted(team_states)],
        'freshness': deepcopy(listing.get('freshness') or {}),
        'publication_authority': public_serving_authority.publication_authority(snapshot),
        'snapshot': _snapshot_identity(snapshot, available=True),
    })
    return result
