"""Purpose-built public projections from one trusted Dashboard publication.

The comprehensive Dashboard snapshot remains the canonical compute-once source,
but public surfaces should not serialize that multi-megabyte carrier merely to
read a few frozen fields.  These projections copy only the fields each surface
uses.  They do not calculate baseball semantics or consult mutable baseball
tables.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Mapping

from services import board_freshness
from services import dashboard_snapshot as dashboard_snapshot_service
from services import public_serving_authority
from services.league_team_state_listing import (
    build_league_team_state_listing,
    build_snapshot_unavailable_listing,
    resolve_current_trusted_dashboard_snapshot,
)
from services.public_landscape import build_public_landscape, unavailable_landscape


VERSION = '1.0.0'
HOME_CAPABILITY = 'public_home_projection_v1'
LEAGUE_CAPABILITY = 'public_league_projection_v1'
STORIES_CAPABILITY = 'public_stories_projection_v1'
TRUST_CAPABILITY = 'public_trust_projection_v1'
STATUS_AVAILABLE = 'ok'
STATUS_UNAVAILABLE = 'snapshot_unavailable'
HOME_PAYLOAD_KEYS = ('freshness', 'landscape', 'what_changed_since_yesterday')
LEAGUE_PAYLOAD_KEYS = (
    'freshness', 'landscape', 'roles', 'injury_il_context', 'roster_readiness',
)
STORIES_PAYLOAD_KEYS = ('freshness', 'stories', 'today_flagship')
TRUST_PAYLOAD_KEYS = ('freshness',)


def _iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def _snapshot_identity(snapshot):
    if snapshot is None:
        return {
            'snapshot_id': None,
            'snapshot_type': dashboard_snapshot_service.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
            'sync_run_id': None,
            'represented_date': None,
            'availability_reference_date': None,
            'snapshot_generated_at': None,
            'published_at': None,
            'payload_version': dashboard_snapshot_service.DASHBOARD_PAYLOAD_VERSION,
        }
    return {
        'snapshot_id': snapshot.id,
        'snapshot_type': snapshot.snapshot_type,
        'sync_run_id': snapshot.sync_run_id,
        'represented_date': _iso(snapshot.data_through),
        'availability_reference_date': _iso(snapshot.availability_reference_date),
        'snapshot_generated_at': _iso(snapshot.snapshot_generated_at),
        'published_at': _iso(snapshot.published_at),
        'payload_version': snapshot.payload_version,
    }


def _unavailable_freshness(reason):
    return {
        'data_through': None,
        'freshness_state': STATUS_UNAVAILABLE,
        'is_current': False,
        'fail_closed': True,
        'reason_codes': [reason],
    }


def _base(capability, snapshot, *, reason=None, freshness_builder=None):
    available = snapshot is not None and reason is None
    if available:
        builder = freshness_builder or board_freshness.published_snapshot_freshness_block
        freshness = builder(snapshot=snapshot)
        freshness = deepcopy(freshness) if isinstance(freshness, Mapping) else {}
    else:
        freshness = _unavailable_freshness(reason or 'dashboard_snapshot_missing')
    result = {
        'capability': capability,
        'version': VERSION,
        'status': STATUS_AVAILABLE if available else STATUS_UNAVAILABLE,
        'ranking_applied': False,
        'selection_made': False,
        'prediction_applied': False,
        'publication_authority': (
            public_serving_authority.publication_authority(snapshot)
            if available else None
        ),
        'snapshot': _snapshot_identity(snapshot if available else None),
        'freshness': freshness,
    }
    if not available:
        result['reason'] = reason or 'dashboard_snapshot_missing'
    return result


def _validated_snapshot(snapshot, unavailable_reason=None):
    if snapshot is None and unavailable_reason:
        return None, unavailable_reason
    reason = dashboard_snapshot_service.snapshot_unavailable_reason(snapshot)
    return (snapshot, None) if reason is None else (None, reason)


def select_trusted_publication(payload_keys):
    """Resolve one trusted publication while reading only named frozen domains."""
    snapshot = dashboard_snapshot_service.get_latest_valid_dashboard_snapshot_projection(
        payload_keys
    )
    if snapshot is not None:
        return snapshot, None
    # This is a failure-only diagnostic read. The healthy path never loads the
    # comprehensive payload merely to establish why no projection can be served.
    return resolve_current_trusted_dashboard_snapshot()


def build_home_projection(
    snapshot,
    *,
    unavailable_reason=None,
    landscape_builder=build_public_landscape,
    freshness_builder=None,
):
    snapshot, reason = _validated_snapshot(snapshot, unavailable_reason)
    result = _base(
        HOME_CAPABILITY,
        snapshot,
        reason=reason,
        freshness_builder=freshness_builder,
    )
    if snapshot is None:
        result.update({
            'landscape': unavailable_landscape(reason),
            'what_changed_since_yesterday': None,
        })
        return result

    payload = snapshot.payload
    result.update({
        'landscape': landscape_builder(snapshot),
        'what_changed_since_yesterday': deepcopy(
            payload.get('what_changed_since_yesterday')
        ),
    })
    return result


def _compact_landscape_context(landscape):
    if not isinstance(landscape, Mapping):
        return None
    return {
        key: deepcopy(landscape.get(key))
        for key in (
            'capability',
            'status',
            'reason',
            'storylines',
            'freshness',
            'publication_authority',
            'snapshot',
        )
        if key in landscape
    }


def build_league_projection(
    snapshot,
    *,
    unavailable_reason=None,
    team_state_listing_builder=build_league_team_state_listing,
    landscape_builder=build_public_landscape,
    freshness_builder=None,
):
    snapshot, reason = _validated_snapshot(snapshot, unavailable_reason)
    result = _base(
        LEAGUE_CAPABILITY,
        snapshot,
        reason=reason,
        freshness_builder=freshness_builder,
    )
    if snapshot is None:
        result.update({
            'team_states': build_snapshot_unavailable_listing(
                reason,
                directory_loader=lambda: {},
            ),
            'landscape': _compact_landscape_context(unavailable_landscape(reason)),
            'roles': None,
            'injury_il_context': None,
            'roster_readiness': None,
        })
        return result

    listing = team_state_listing_builder(
        snapshot_resolver=lambda: (snapshot, None),
    )
    landscape = landscape_builder(
        snapshot,
        team_state_listing_builder=lambda **_kwargs: listing,
    )
    payload = snapshot.payload
    result.update({
        'team_states': deepcopy(listing),
        'landscape': _compact_landscape_context(landscape),
        'roles': deepcopy(payload.get('roles')),
        'injury_il_context': deepcopy(payload.get('injury_il_context')),
        'roster_readiness': deepcopy(payload.get('roster_readiness')),
    })
    return result


def build_stories_projection(
    snapshot, *, unavailable_reason=None, freshness_builder=None,
):
    snapshot, reason = _validated_snapshot(snapshot, unavailable_reason)
    result = _base(
        STORIES_CAPABILITY,
        snapshot,
        reason=reason,
        freshness_builder=freshness_builder,
    )
    if snapshot is None:
        result.update({'stories': None, 'today_flagship': None})
        return result

    payload = snapshot.payload
    result.update({
        'stories': deepcopy(payload.get('stories')),
        'today_flagship': deepcopy(payload.get('today_flagship')),
    })
    return result


def build_trust_projection(
    snapshot, *, unavailable_reason=None, freshness_builder=None,
):
    snapshot, reason = _validated_snapshot(snapshot, unavailable_reason)
    return _base(
        TRUST_CAPABILITY,
        snapshot,
        reason=reason,
        freshness_builder=freshness_builder,
    )


__all__ = [
    'HOME_CAPABILITY',
    'HOME_PAYLOAD_KEYS',
    'LEAGUE_CAPABILITY',
    'LEAGUE_PAYLOAD_KEYS',
    'STORIES_CAPABILITY',
    'STORIES_PAYLOAD_KEYS',
    'TRUST_CAPABILITY',
    'TRUST_PAYLOAD_KEYS',
    'build_home_projection',
    'build_league_projection',
    'build_stories_projection',
    'build_trust_projection',
    'select_trusted_publication',
]
