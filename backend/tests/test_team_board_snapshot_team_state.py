from datetime import date, datetime
from types import SimpleNamespace

import pytest

from services.team_board_snapshot_team_state import (
    build_team_accounting,
    compare_exact_team_state,
    make_receipt,
    receipt_value,
    require_complete_team_accounting,
)
from services.mlb_club_directory import MLB_TEAM_IDS
from services.what_changed_comparison_identity import (
    ComparisonIdentityInvalid, build_comparison_identity,
)


def _snapshot(snapshot_id, represented_date, status_code, *, with_receipt=True):
    snapshot = SimpleNamespace(
        id=snapshot_id, sync_run_id=snapshot_id + 100,
        data_through=date.fromisoformat(represented_date),
        snapshot_type='bullpen_dashboard', payload_version=1,
        status='ready', published_at=datetime(2026, 9, 22),
        is_published=True, payload={},
    )
    if with_receipt:
        readiness = {
            'readiness': {'status_code': status_code},
            'freshness': {'data_through': represented_date},
        }
        snapshot.payload['trusted_team_boards'] = {
            'contract': 'trusted_team_board_publication_v1',
            'data_through': represented_date,
            'by_team_id': {'110': {
                'frozen_team_state': make_receipt(
                    snapshot, 110, readiness, method_version='v3_phase_5',
                ),
            }},
        }
    return snapshot


def _pair(previous, current):
    identity = build_comparison_identity(current, previous)
    current.payload['what_changed_since_yesterday'] = {
        'comparison': {'identity': identity},
    }
    return identity


def test_receipt_is_exact_snapshot_team_date_and_method():
    snapshot = _snapshot(12, '2026-09-22', 'operationally_stable')
    present, value = receipt_value(snapshot, 110)
    assert present is True
    assert value['public_label'] == 'Fresh'
    value['public_label'] = 'Altered'
    assert receipt_value(snapshot, 110)[1]['public_label'] == 'Fresh'

    for field, wrong in (
        ('dashboard_snapshot_id', 999), ('team_id', 111),
        ('represented_date', '2026-09-21'), ('method_version', 'unknown'),
    ):
        invalid = _snapshot(12, '2026-09-22', 'operationally_stable')
        invalid.payload['trusted_team_boards']['by_team_id']['110']['frozen_team_state'][field] = wrong
        assert receipt_value(invalid, 110)[1]['available'] is False
    assert receipt_value(snapshot, 111)[1]['available'] is False


def test_package_level_receipt_serves_team_state_without_fabricating_a_board():
    snapshot = _snapshot(12, '2026-09-22', 'operationally_stable')
    package = snapshot.payload['trusted_team_boards']
    receipt = package['by_team_id'].pop('110')['frozen_team_state']
    package['frozen_team_state_by_team_id'] = {'110': receipt}

    present, value = receipt_value(snapshot, 110)

    assert present is True
    assert value['public_label'] == 'Fresh'
    assert package['by_team_id'] == {}
    package['frozen_team_state_by_team_id'].pop('110')
    package['frozen_team_state_by_team_id']['111'] = receipt
    assert receipt_value(snapshot, 110)[1]['available'] is False


@pytest.mark.parametrize('published_ids', (
    tuple(MLB_TEAM_IDS) + (484, 531, 534, 5434),
    tuple(MLB_TEAM_IDS[:-1]) + (484,),
))
def test_noncanonical_board_cannot_enter_or_substitute_for_canonical_team(
    published_ids,
):
    package = {
        'team_accounting': build_team_accounting(MLB_TEAM_IDS, MLB_TEAM_IDS),
        'by_team_id': {str(team_id): {} for team_id in published_ids},
    }

    with pytest.raises(ValueError, match='package_noncanonical_team'):
        require_complete_team_accounting(package, MLB_TEAM_IDS)


def test_duplicate_accounting_cannot_substitute_for_missing_canonical_team():
    accounting = build_team_accounting(MLB_TEAM_IDS, MLB_TEAM_IDS)
    accounting['teams'][-1] = dict(accounting['teams'][0])
    package = {
        'team_accounting': accounting,
        'by_team_id': {str(team_id): {} for team_id in MLB_TEAM_IDS[:-1]},
    }

    with pytest.raises(ValueError, match='requires_30_accounted_teams'):
        require_complete_team_accounting(package, MLB_TEAM_IDS)


def test_exact_pair_change_and_unchanged():
    previous = _snapshot(11, '2026-09-21', 'operationally_constrained')
    current = _snapshot(12, '2026-09-22', 'operationally_stable')
    identity = _pair(previous, current)
    result = compare_exact_team_state(previous, current, 110, identity)
    assert result['status'] == 'changed'
    assert result['event']['previous_label'] == 'Stretched'
    assert result['event']['current_label'] == 'Fresh'
    current.payload['trusted_team_boards']['by_team_id']['110']['frozen_team_state'] = (
        make_receipt(current, 110, {
            'readiness': {'status_code': 'operationally_constrained'},
            'freshness': {'data_through': '2026-09-22'},
        }, method_version='v3_phase_5')
    )
    assert compare_exact_team_state(previous, current, 110, identity)['status'] == 'unchanged'


def test_wrong_predecessor_rejected_and_missing_receipt_unavailable():
    previous = _snapshot(11, '2026-09-21', 'operationally_constrained')
    current = _snapshot(12, '2026-09-22', 'operationally_stable')
    identity = _pair(previous, current)
    wrong = _snapshot(10, '2026-09-21', 'operationally_constrained')
    with pytest.raises(ComparisonIdentityInvalid):
        compare_exact_team_state(wrong, current, 110, identity)
    previous.payload.pop('trusted_team_boards')
    result = compare_exact_team_state(previous, current, 110, identity)
    assert result['status'] == 'unavailable'
    assert result['event'] is None
