"""Snapshot-bound Team State receipts for trusted Team Board publications.

The mandatory pre-trust Team State proof authors these receipts.  Serving and
the exact-pair TB-09 comparison only read them; neither recalculates readiness.
"""

from copy import deepcopy
from datetime import date
from typing import Mapping

from services.team_state_public_vocabulary import (
    TEAM_STATE_READINESS_UNAVAILABLE,
    public_team_state,
    team_state_unavailable,
)


CONTRACT = 'team_board_snapshot_team_state_v1'
COMPARISON_CONTRACT = 'team_board_team_state_comparison_v1'
ACCOUNTING_CONTRACT = 'trusted_team_board_team_accounting_v1'
ACCOUNTING_PUBLISHABLE = 'publishable'
ACCOUNTING_UNAVAILABLE = 'unavailable'
ACCOUNTING_UNAVAILABLE_REASON = 'team_board_source_records_unavailable'


def build_team_accounting(publishable_team_ids, canonical_team_ids):
    """Account for every canonical club without fabricating a Team Board."""
    publishable = {int(team_id) for team_id in publishable_team_ids}
    canonical = tuple(sorted(int(value) for value in canonical_team_ids))
    return {
        'contract': ACCOUNTING_CONTRACT,
        'accounted_team_count': len(canonical),
        'teams': [
            {
                'team_id': int(team_id),
                'team_board_status': (
                    ACCOUNTING_PUBLISHABLE
                    if int(team_id) in publishable
                    else ACCOUNTING_UNAVAILABLE
                ),
                'reason_code': (
                    None
                    if int(team_id) in publishable
                    else ACCOUNTING_UNAVAILABLE_REASON
                ),
            }
            for team_id in canonical
        ],
    }


def require_complete_team_accounting(package, expected_team_ids):
    """Validate exact canonical accounting separately from board availability."""
    expected = tuple(sorted(int(team_id) for team_id in expected_team_ids))
    accounting = package.get('team_accounting') if isinstance(package, Mapping) else None
    teams = accounting.get('teams') if isinstance(accounting, Mapping) else None
    if (
        not isinstance(accounting, Mapping)
        or accounting.get('contract') != ACCOUNTING_CONTRACT
        or accounting.get('accounted_team_count') != len(expected)
        or not isinstance(teams, list)
    ):
        raise ValueError('snapshot_team_state_package_accounting_invalid')

    accounted_ids = [
        item.get('team_id') if isinstance(item, Mapping) else None
        for item in teams
    ]
    if (
        any(type(team_id) is not int for team_id in accounted_ids)
        or
        len(accounted_ids) != len(expected)
        or len(set(accounted_ids)) != len(expected)
        or tuple(sorted(accounted_ids)) != expected
    ):
        raise ValueError('snapshot_team_state_package_requires_30_accounted_teams')

    by_team = package.get('by_team_id')
    if not isinstance(by_team, Mapping):
        raise ValueError('snapshot_team_state_package_accounting_invalid')
    try:
        published_ids = {int(team_id) for team_id in by_team}
    except (TypeError, ValueError):
        raise ValueError('snapshot_team_state_package_accounting_invalid') from None
    if not published_ids.issubset(set(expected)):
        raise ValueError('snapshot_team_state_package_noncanonical_team')

    status_by_team = {
        item['team_id']: item for item in teams if isinstance(item, Mapping)
    }
    for team_id in expected:
        item = status_by_team[team_id]
        status = item.get('team_board_status')
        if team_id in published_ids:
            if status != ACCOUNTING_PUBLISHABLE or item.get('reason_code') is not None:
                raise ValueError('snapshot_team_state_package_accounting_mismatch')
        elif (
            status != ACCOUNTING_UNAVAILABLE
            or item.get('reason_code') != ACCOUNTING_UNAVAILABLE_REASON
        ):
            raise ValueError('snapshot_team_state_package_accounting_mismatch')
    return accounting


def _date(value):
    return value.isoformat() if isinstance(value, date) else value


def make_receipt(snapshot, team_id, readiness, *, method_version):
    """Freeze the existing public vocabulary projection, not a new classifier."""
    value = public_team_state(readiness)
    if value.get('available') is not True:
        raise ValueError('snapshot_team_state_public_value_unavailable')
    if _date(value.get('data_through')) != _date(snapshot.data_through):
        raise ValueError('snapshot_team_state_date_mismatch')
    value['data_through'] = _date(snapshot.data_through)
    return {
        'contract': CONTRACT,
        'team_id': int(team_id),
        'dashboard_snapshot_id': snapshot.id,
        'represented_date': _date(snapshot.data_through),
        'method_version': method_version,
        'value': deepcopy(value),
    }


def receipt_value(snapshot, team_id):
    """Return (present, value); a present but invalid receipt never falls back."""
    payload = snapshot.payload if isinstance(snapshot.payload, Mapping) else {}
    package = payload.get('trusted_team_boards')
    if not isinstance(package, Mapping):
        return False, None
    by_team = package.get('by_team_id') or {}
    receipts = package.get('frozen_team_state_by_team_id')
    has_package_receipts = isinstance(receipts, Mapping)
    has_receipts = has_package_receipts or any(
        isinstance(item, Mapping) and 'frozen_team_state' in item
        for item in by_team.values()
    )
    if not has_receipts:
        # Earlier trusted packages intentionally have no receipt. They retain
        # their old published-artifact serving path, not a synthesized receipt.
        return False, None
    from services.public_serving_authority import TEAM_BOARD_PACKAGE_CONTRACT
    if (
        package.get('contract') != TEAM_BOARD_PACKAGE_CONTRACT
        or package.get('data_through') != _date(snapshot.data_through)
    ):
        return True, team_state_unavailable(
            TEAM_STATE_READINESS_UNAVAILABLE,
            data_through=_date(snapshot.data_through),
            reason_code='snapshot_team_state_package_identity_mismatch',
        )
    team = by_team.get(str(int(team_id)))
    receipt = (
        receipts.get(str(int(team_id)))
        if has_package_receipts
        else team.get('frozen_team_state') if isinstance(team, Mapping) else None
    )
    if not isinstance(receipt, Mapping):
        return True, team_state_unavailable(
            TEAM_STATE_READINESS_UNAVAILABLE,
            data_through=_date(snapshot.data_through),
            reason_code='snapshot_team_state_receipt_missing',
        )
    from services.team_state_vnext_production_proof import EXPECTED_METHOD_VERSION
    expected_date = _date(snapshot.data_through)
    if not isinstance(receipt, Mapping) or any((
        receipt.get('contract') != CONTRACT,
        receipt.get('team_id') != int(team_id),
        receipt.get('dashboard_snapshot_id') != snapshot.id,
        receipt.get('represented_date') != expected_date,
        receipt.get('method_version') != EXPECTED_METHOD_VERSION,
        not isinstance(receipt.get('value'), Mapping),
        receipt.get('value', {}).get('data_through') != expected_date,
    )):
        return True, team_state_unavailable(
            TEAM_STATE_READINESS_UNAVAILABLE,
            data_through=expected_date,
            reason_code='snapshot_team_state_receipt_invalid',
        )
    return True, deepcopy(dict(receipt['value']))


def compare_exact_team_state(previous_snapshot, current_snapshot, team_id, identity):
    """Compare only the exact, already-bound trusted Dashboard pair."""
    from services.what_changed_comparison_identity import validate_snapshot_pair

    validate_snapshot_pair(identity, previous_snapshot, current_snapshot)
    previous_present, previous = receipt_value(previous_snapshot, team_id)
    current_present, current = receipt_value(current_snapshot, team_id)
    base = {
        'contract': COMPARISON_CONTRACT,
        'team_id': int(team_id),
        'current_snapshot_id': current_snapshot.id,
        'previous_snapshot_id': previous_snapshot.id,
        'current_represented_date': _date(current_snapshot.data_through),
        'previous_represented_date': _date(previous_snapshot.data_through),
        'event': None,
    }
    if not previous_present or not current_present:
        return {**base, 'status': 'unavailable', 'reason_code': 'snapshot_team_state_receipt_missing'}
    if previous.get('available') is not True or current.get('available') is not True:
        return {**base, 'status': 'unavailable', 'reason_code': 'team_state_not_comparable'}
    from_state = previous.get('public_state')
    to_state = current.get('public_state')
    if from_state not in {'fresh', 'stretched', 'vulnerable'} or to_state not in {'fresh', 'stretched', 'vulnerable'}:
        return {**base, 'status': 'unavailable', 'reason_code': 'team_state_not_comparable'}
    if from_state == to_state:
        return {**base, 'status': 'unchanged', 'reason_code': None}
    return {
        **base,
        'status': 'changed',
        'reason_code': None,
        'event': {
            'event_type': 'team_state_change',
            'previous_state': from_state,
            'previous_label': previous['public_label'],
            'current_state': to_state,
            'current_label': current['public_label'],
        },
    }
