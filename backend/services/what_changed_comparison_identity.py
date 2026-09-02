"""Exact publication identity for governed What Changed comparisons.

This module does not calculate deltas.  It binds the already-authored public
comparison to the two publications that produced it and validates that same
identity for immutable citation generation and reads.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from typing import Mapping

from models.dashboard_snapshot import DashboardSnapshot
from services.what_changed_since_yesterday import VERSION as METHOD_VERSION
from services.what_changed_since_yesterday_public import CAPABILITY as COMPARISON_AUTHORITY


CONTRACT_VERSION = 'what_changed_comparison_identity_v1'
SNAPSHOT_STATUS_READY = 'ready'


class ComparisonIdentityInvalid(ValueError):
    """The requested pair cannot be proven to be the rendered trusted pair."""


def _mapping(value) -> dict:
    return dict(value) if isinstance(value, Mapping) else {}


def _as_date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def comparison_identity_from_payload(payload) -> dict | None:
    block = _mapping(_mapping(payload).get('what_changed_since_yesterday'))
    comparison = _mapping(block.get('comparison'))
    identity = _mapping(comparison.get('identity'))
    return normalize_comparison_identity(identity) if identity else None


def normalize_comparison_identity(value) -> dict:
    identity = _mapping(value)
    normalized = {
        'contract': identity.get('contract'),
        'comparison_authority': identity.get('comparison_authority'),
        'method_version': identity.get('method_version'),
        'previous_snapshot_id': _as_int(identity.get('previous_snapshot_id')),
        'current_snapshot_id': _as_int(identity.get('current_snapshot_id')),
        'previous_sync_run_id': _as_int(identity.get('previous_sync_run_id')),
        'current_sync_run_id': _as_int(identity.get('current_sync_run_id')),
        'previous_payload_version': _as_int(identity.get('previous_payload_version')),
        'current_payload_version': _as_int(identity.get('current_payload_version')),
        'previous_data_through': (
            _as_date(identity.get('previous_data_through')).isoformat()
            if _as_date(identity.get('previous_data_through')) else None
        ),
        'current_data_through': (
            _as_date(identity.get('current_data_through')).isoformat()
            if _as_date(identity.get('current_data_through')) else None
        ),
        'previous_publication_state': identity.get('previous_publication_state'),
        'current_publication_state': identity.get('current_publication_state'),
    }
    required = (
        'previous_snapshot_id', 'current_snapshot_id',
        'previous_sync_run_id', 'current_sync_run_id',
        'previous_payload_version', 'current_payload_version',
        'previous_data_through', 'current_data_through',
    )
    if (
        normalized['contract'] != CONTRACT_VERSION
        or normalized['comparison_authority'] != COMPARISON_AUTHORITY
        or normalized['method_version'] != METHOD_VERSION
        or normalized['previous_publication_state'] != 'trusted_published'
        or normalized['current_publication_state'] != 'current_published'
        or any(normalized[key] is None for key in required)
        or normalized['previous_snapshot_id'] == normalized['current_snapshot_id']
        or normalized['previous_payload_version'] != normalized['current_payload_version']
        or normalized['previous_data_through'] >= normalized['current_data_through']
        or _as_date(normalized['previous_data_through'])
            != _as_date(normalized['current_data_through']) - timedelta(days=1)
    ):
        raise ComparisonIdentityInvalid('comparison_identity_invalid')
    return normalized


def build_comparison_identity(current_snapshot, previous_snapshot) -> dict:
    if current_snapshot is None or previous_snapshot is None:
        raise ComparisonIdentityInvalid('comparison_publication_missing')
    if (
        getattr(previous_snapshot, 'snapshot_type', None)
        != getattr(current_snapshot, 'snapshot_type', None)
    ):
        raise ComparisonIdentityInvalid('comparison_publication_incompatible')
    identity = {
        'contract': CONTRACT_VERSION,
        'comparison_authority': COMPARISON_AUTHORITY,
        'method_version': METHOD_VERSION,
        'previous_snapshot_id': getattr(previous_snapshot, 'id', None),
        'current_snapshot_id': getattr(current_snapshot, 'id', None),
        'previous_sync_run_id': getattr(previous_snapshot, 'sync_run_id', None),
        'current_sync_run_id': getattr(current_snapshot, 'sync_run_id', None),
        'previous_payload_version': getattr(previous_snapshot, 'payload_version', None),
        'current_payload_version': getattr(current_snapshot, 'payload_version', None),
        'previous_data_through': getattr(previous_snapshot, 'data_through', None),
        'current_data_through': getattr(current_snapshot, 'data_through', None),
        'previous_publication_state': 'trusted_published',
        'current_publication_state': 'current_published',
    }
    return normalize_comparison_identity(identity)


def bind_comparison_identity(payload, current_snapshot, previous_snapshot) -> dict:
    """Attach identity only when the frozen public comparison proves this pair."""
    stored = deepcopy(_mapping(payload))
    block = _mapping(stored.get('what_changed_since_yesterday'))
    comparison = _mapping(block.get('comparison'))
    if comparison.get('comparison_available') is not True:
        return stored
    if (
        previous_snapshot is None
        or comparison.get('previous_snapshot_id') != getattr(previous_snapshot, 'id', None)
        or getattr(previous_snapshot, 'status', None) != SNAPSHOT_STATUS_READY
        or getattr(previous_snapshot, 'published_at', None) is None
    ):
        comparison.pop('previous_snapshot_id', None)
        block['comparison'] = comparison
        stored['what_changed_since_yesterday'] = block
        return stored
    try:
        identity = build_comparison_identity(current_snapshot, previous_snapshot)
    except ComparisonIdentityInvalid:
        comparison.pop('previous_snapshot_id', None)
        block['comparison'] = comparison
        stored['what_changed_since_yesterday'] = block
        return stored
    if (
        comparison.get('previous_data_through') != identity['previous_data_through']
        or comparison.get('current_data_through') != identity['current_data_through']
    ):
        comparison.pop('previous_snapshot_id', None)
        block['comparison'] = comparison
        stored['what_changed_since_yesterday'] = block
        return stored
    comparison['identity'] = identity
    comparison.pop('previous_snapshot_id', None)
    block['comparison'] = comparison
    stored['what_changed_since_yesterday'] = block
    return stored


def validate_snapshot_pair(identity, previous_snapshot, current_snapshot) -> dict:
    normalized = normalize_comparison_identity(identity)
    expected = build_comparison_identity(current_snapshot, previous_snapshot)
    if normalized != expected:
        raise ComparisonIdentityInvalid('comparison_publication_mismatch')
    if (
        getattr(previous_snapshot, 'status', None) != SNAPSHOT_STATUS_READY
        or getattr(previous_snapshot, 'published_at', None) is None
        or getattr(current_snapshot, 'status', None) != SNAPSHOT_STATUS_READY
        or getattr(current_snapshot, 'published_at', None) is None
        or not getattr(current_snapshot, 'is_published', False)
        or getattr(previous_snapshot, 'snapshot_type', None)
            != getattr(current_snapshot, 'snapshot_type', None)
    ):
        raise ComparisonIdentityInvalid('comparison_publication_untrusted')
    embedded = comparison_identity_from_payload(current_snapshot.payload)
    if embedded != normalized:
        raise ComparisonIdentityInvalid('comparison_identity_not_rendered')
    return normalized


def resolve_snapshot_pair(identity, *, session) -> tuple[object, object, dict]:
    normalized = normalize_comparison_identity(identity)
    rows = (
        session.query(DashboardSnapshot)
        .filter(DashboardSnapshot.id.in_([
            normalized['previous_snapshot_id'], normalized['current_snapshot_id'],
        ]))
        .all()
    )
    by_id = {row.id: row for row in rows}
    previous = by_id.get(normalized['previous_snapshot_id'])
    current = by_id.get(normalized['current_snapshot_id'])
    if previous is None or current is None:
        raise ComparisonIdentityInvalid('comparison_publication_missing')
    validate_snapshot_pair(normalized, previous, current)
    return previous, current, normalized


__all__ = [
    'COMPARISON_AUTHORITY',
    'CONTRACT_VERSION',
    'METHOD_VERSION',
    'ComparisonIdentityInvalid',
    'bind_comparison_identity',
    'build_comparison_identity',
    'comparison_identity_from_payload',
    'normalize_comparison_identity',
    'resolve_snapshot_pair',
    'validate_snapshot_pair',
]
