"""Publication identity contract for answer-first Team Board delivery.

The core and deferred resources use this exact immutable identity.  Deferred
reads may be reconstructed only for the named trusted publication and are
withheld when any identity field disagrees.
"""

from __future__ import annotations

from datetime import date
from typing import Mapping

from models.dashboard_snapshot import DashboardSnapshot
from services import dashboard_snapshot as dashboard_snapshot_service
from services.public_serving_authority import (
    PUBLICATION_AUTHORITY_CONTRACT,
    TEAM_BOARD_PACKAGE_CONTRACT,
    publication_authority,
)
from services.team_board_v2 import CONTRACT_VERSION as TEAM_BOARD_CONTRACT_VERSION


IDENTITY_CONTRACT = 'team_board_publication_identity_v1'


class TeamBoardIdentityMismatch(ValueError):
    """The requested deferred resource cannot be tied to the rendered core."""


def _mapping(value):
    return dict(value) if isinstance(value, Mapping) else {}


def _as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_date(value):
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(str(value)).isoformat()
    except (TypeError, ValueError):
        return None


def build_team_board_identity(snapshot, board) -> dict:
    authority = publication_authority(snapshot) or {}
    team = _mapping(_mapping(board).get('team'))
    team_state = _mapping(_mapping(board).get('team_state'))
    methods = _mapping(_mapping(board).get('publication_method_versions'))
    return {
        'contract': IDENTITY_CONTRACT,
        'team_id': _as_int(team.get('team_id')),
        'team_abbreviation': team.get('team_abbreviation'),
        'snapshot_id': _as_int(authority.get('snapshot_id')),
        'sync_run_id': _as_int(authority.get('sync_run_id')),
        'represented_date': _as_date(
            team_state.get('data_through') or authority.get('data_through')
        ),
        'availability_reference_date': _as_date(
            authority.get('availability_reference_date')
        ),
        'published_at': authority.get('published_at'),
        'snapshot_generated_at': authority.get('snapshot_generated_at'),
        'dashboard_payload_version': _as_int(
            getattr(snapshot, 'payload_version', None)
        ),
        'publication_authority_contract': PUBLICATION_AUTHORITY_CONTRACT,
        'team_board_package_contract': TEAM_BOARD_PACKAGE_CONTRACT,
        'team_board_contract_version': TEAM_BOARD_CONTRACT_VERSION,
        'team_state_contract': team_state.get('contract'),
        'bullpen_membership_method_version': methods.get('bullpen_membership'),
        'rest_status_method_version': methods.get('rest_status'),
        'workload_windows_method_version': methods.get('workload_windows'),
        'deployment_profile_method_version': methods.get('deployment_profile'),
        'rotation_impact_method_version': methods.get('rotation_impact'),
    }


def normalize_team_board_identity(value) -> dict:
    identity = _mapping(value)
    normalized = {
        'contract': identity.get('contract'),
        'team_id': _as_int(identity.get('team_id')),
        'team_abbreviation': identity.get('team_abbreviation'),
        'snapshot_id': _as_int(identity.get('snapshot_id')),
        'sync_run_id': _as_int(identity.get('sync_run_id')),
        'represented_date': _as_date(identity.get('represented_date')),
        'availability_reference_date': _as_date(
            identity.get('availability_reference_date')
        ),
        'published_at': identity.get('published_at'),
        'snapshot_generated_at': identity.get('snapshot_generated_at'),
        'dashboard_payload_version': _as_int(
            identity.get('dashboard_payload_version')
        ),
        'publication_authority_contract': identity.get(
            'publication_authority_contract'
        ),
        'team_board_package_contract': identity.get(
            'team_board_package_contract'
        ),
        'team_board_contract_version': identity.get(
            'team_board_contract_version'
        ),
        'team_state_contract': identity.get('team_state_contract'),
        'bullpen_membership_method_version': identity.get(
            'bullpen_membership_method_version'
        ),
        'rest_status_method_version': identity.get('rest_status_method_version'),
        'workload_windows_method_version': identity.get(
            'workload_windows_method_version'
        ),
        'deployment_profile_method_version': identity.get(
            'deployment_profile_method_version'
        ),
        'rotation_impact_method_version': identity.get(
            'rotation_impact_method_version'
        ),
    }
    required = (
        'team_id', 'team_abbreviation', 'snapshot_id', 'sync_run_id',
        'represented_date', 'availability_reference_date', 'published_at',
        'snapshot_generated_at', 'dashboard_payload_version',
        'team_state_contract',
        'bullpen_membership_method_version', 'rest_status_method_version',
        'workload_windows_method_version', 'deployment_profile_method_version',
        'rotation_impact_method_version',
    )
    if (
        normalized['contract'] != IDENTITY_CONTRACT
        or normalized['publication_authority_contract']
        != PUBLICATION_AUTHORITY_CONTRACT
        or normalized['team_board_package_contract']
        != TEAM_BOARD_PACKAGE_CONTRACT
        or normalized['team_board_contract_version']
        != TEAM_BOARD_CONTRACT_VERSION
        or any(normalized[field] in (None, '') for field in required)
    ):
        raise TeamBoardIdentityMismatch('team_board_identity_invalid')
    return normalized


def resolve_team_board_snapshot(identity, *, team_id, session):
    normalized = normalize_team_board_identity(identity)
    if normalized['team_id'] != int(team_id):
        raise TeamBoardIdentityMismatch('team_board_team_mismatch')
    snapshot = (
        session.query(DashboardSnapshot)
        .filter(DashboardSnapshot.id == normalized['snapshot_id'])
        .one_or_none()
    )
    if snapshot is None:
        raise TeamBoardIdentityMismatch('team_board_publication_missing')
    if (
        snapshot.status != dashboard_snapshot_service.SNAPSHOT_STATUS_READY
        or snapshot.published_at is None
        or not dashboard_snapshot_service.payload_version_valid(snapshot)
        or not isinstance(snapshot.payload, Mapping)
    ):
        raise TeamBoardIdentityMismatch('team_board_publication_untrusted')
    return snapshot, normalized


def require_matching_team_board_identity(identity, snapshot, board) -> dict:
    normalized = normalize_team_board_identity(identity)
    expected = build_team_board_identity(snapshot, board)
    if normalized != expected:
        raise TeamBoardIdentityMismatch('team_board_identity_mismatch')
    return normalized


__all__ = [
    'IDENTITY_CONTRACT',
    'TeamBoardIdentityMismatch',
    'build_team_board_identity',
    'normalize_team_board_identity',
    'require_matching_team_board_identity',
    'resolve_team_board_snapshot',
]
