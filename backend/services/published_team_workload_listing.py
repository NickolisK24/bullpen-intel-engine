"""Batch reader for frozen public Team Board workload-window carriers.

This service reads one current trusted Dashboard snapshot and projects each
team's already-authored seven-day workload window. It never queries game logs,
rebuilds Team Board, recalculates workload, or selects pitchers.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Mapping

from services import public_serving_authority
from services.public_team_relief_work import (
    WORKLOAD_WINDOWS_CARRIER_CONTRACT,
    WORKLOAD_WINDOWS_COMPLETE,
    WORKLOAD_WINDOWS_WITHHELD,
    WORKLOAD_WINDOWS_METHOD_VERSION,
    WORKLOAD_WINDOWS_POPULATION_AUTHORITY,
    WORKLOAD_WINDOWS_POPULATION_BASIS,
    WORKLOAD_WINDOWS_MEMBERSHIP_AUTHORITY,
    WORKLOAD_WINDOWS_PUBLIC_CONTRACT_VERSION,
    WORKLOAD_WINDOWS_REFERENCE_DATE_POLICY,
)


CAPABILITY = 'published_team_workload_listing_v1'
WINDOW_DAYS = 7
STATUS_OK = 'ok'
STATUS_SNAPSHOT_UNAVAILABLE = 'snapshot_unavailable'
STATUS_WITHHELD = 'withheld'
REASON_SNAPSHOT_UNAVAILABLE = 'trusted_dashboard_snapshot_unavailable'
REASON_TEAM_MISSING = 'published_team_workload_missing'
REASON_AUTHORITY_INVALID = 'published_team_workload_authority_invalid'


def _iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def withheld_recent_volume(reason_code, *, data_through=None):
    return {
        'contract': WORKLOAD_WINDOWS_CARRIER_CONTRACT,
        'status': STATUS_WITHHELD,
        'reason_code': reason_code,
        'data_through': _iso(data_through),
        'window_days': WINDOW_DAYS,
        'window': None,
    }


def _authority_valid(authority, *, data_through):
    if not isinstance(authority, Mapping):
        return False
    population = authority.get('population_basis')
    return (
        authority.get('method_version') == WORKLOAD_WINDOWS_METHOD_VERSION
        and authority.get('public_contract_version')
        == WORKLOAD_WINDOWS_PUBLIC_CONTRACT_VERSION
        and authority.get('team_board_package_contract')
        == public_serving_authority.TEAM_BOARD_PACKAGE_CONTRACT
        and isinstance(population, Mapping)
        and population.get('basis') == WORKLOAD_WINDOWS_POPULATION_BASIS
        and population.get('population_authority')
        == WORKLOAD_WINDOWS_POPULATION_AUTHORITY
        and population.get('membership_authority')
        == WORKLOAD_WINDOWS_MEMBERSHIP_AUTHORITY
        and authority.get('reference_date_policy')
        == WORKLOAD_WINDOWS_REFERENCE_DATE_POLICY
        and authority.get('data_through') == data_through
    )


def _project_team(team_id, team_package, *, data_through):
    if not isinstance(team_package, Mapping):
        return withheld_recent_volume(REASON_TEAM_MISSING, data_through=data_through)

    identity = team_package.get('team')
    if isinstance(identity, Mapping) and identity.get('team_id') not in (None, team_id):
        return withheld_recent_volume(REASON_AUTHORITY_INVALID, data_through=data_through)

    carrier = team_package.get('workload_windows')
    authority = team_package.get('workload_windows_authority')
    if (
        not isinstance(carrier, Mapping)
        or carrier.get('contract') != WORKLOAD_WINDOWS_CARRIER_CONTRACT
        or carrier.get('status') not in (
            WORKLOAD_WINDOWS_COMPLETE,
            WORKLOAD_WINDOWS_WITHHELD,
        )
        or carrier.get('data_through') != data_through
        or not _authority_valid(authority, data_through=data_through)
    ):
        return withheld_recent_volume(REASON_AUTHORITY_INVALID, data_through=data_through)

    if carrier.get('status') == WORKLOAD_WINDOWS_WITHHELD:
        return withheld_recent_volume(
            carrier.get('reason_code') or REASON_AUTHORITY_INVALID,
            data_through=data_through,
        )

    windows = carrier.get('windows')
    window = windows.get('window_7') if isinstance(windows, Mapping) else None
    if not isinstance(window, Mapping) or window.get('through') != data_through:
        return withheld_recent_volume(REASON_AUTHORITY_INVALID, data_through=data_through)

    return {
        'contract': carrier['contract'],
        'status': carrier['status'],
        'reason_code': carrier.get('reason_code'),
        'data_through': carrier['data_through'],
        'window_days': WINDOW_DAYS,
        'window': deepcopy(dict(window)),
    }


def build_published_team_workload_listing(*, snapshot_resolver=None):
    """Return frozen seven-day workload carriers from one trusted snapshot."""
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
            'data_through': None,
            'teams': [],
        }

    data_through = _iso(getattr(snapshot, 'data_through', None))
    payload = getattr(snapshot, 'payload', None)
    package = (
        payload.get(public_serving_authority.TEAM_BOARD_PACKAGE_KEY)
        if isinstance(payload, Mapping)
        else None
    )
    if (
        not data_through
        or not isinstance(package, Mapping)
        or package.get('contract')
        != public_serving_authority.TEAM_BOARD_PACKAGE_CONTRACT
        or package.get('data_through') != data_through
        or not isinstance(package.get('by_team_id'), Mapping)
    ):
        return {
            'capability': CAPABILITY,
            'status': STATUS_SNAPSHOT_UNAVAILABLE,
            'reason_code': REASON_AUTHORITY_INVALID,
            'data_through': data_through,
            'teams': [],
        }

    rows = []
    for raw_team_id, team_package in package['by_team_id'].items():
        try:
            team_id = int(raw_team_id)
        except (TypeError, ValueError):
            continue
        rows.append({
            'team_id': team_id,
            'recent_bullpen_volume': _project_team(
                team_id,
                team_package,
                data_through=data_through,
            ),
        })
    rows.sort(key=lambda row: row['team_id'])
    return {
        'capability': CAPABILITY,
        'status': STATUS_OK,
        'reason_code': None,
        'data_through': data_through,
        'teams': rows,
    }
