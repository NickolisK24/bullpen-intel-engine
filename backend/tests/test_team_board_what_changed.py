from copy import deepcopy
from datetime import date, datetime
from types import SimpleNamespace

from services.team_board_snapshot_team_state import make_receipt
from services.team_board_what_changed import (
    QUIET_COPY, attach_frozen_what_changed, build_frozen_what_changed,
)
from services.public_serving_authority import _frozen_what_changed_for_view
from services.team_state_vnext_production_proof import EXPECTED_METHOD_VERSION
from services.what_changed_comparison_identity import build_comparison_identity


TEAM_ID = 110


def _fact(value, *, status='complete', most_recent_date=None):
    return {'value': value, 'status': status, 'reason_codes': [], 'most_recent_date': most_recent_date}


def _team(snapshot, state_code, pitcher_ids=(7,)):
    readiness = {
        'readiness': {'status_code': state_code},
        'freshness': {'data_through': snapshot.data_through.isoformat()},
    }
    return {
        'default_pitcher_ids': list(pitcher_ids),
        'records': [{'pitcher_id': pitcher_id, 'name': f'Arm {pitcher_id}'} for pitcher_id in pitcher_ids],
        'frozen_team_state': make_receipt(
            snapshot, TEAM_ID, readiness, method_version=EXPECTED_METHOD_VERSION,
        ),
        'recent_usage_rest': {
            'status': 'complete',
            'active_pitchers': [{
                'pitcher_id': pitcher_id, 'pitcher_name': f'Arm {pitcher_id}',
                'back_to_back': _fact(False), 'three_in_four': _fact(False),
                'four_in_six': _fact(False), 'high_pitch_outing': _fact(False),
            } for pitcher_id in pitcher_ids],
            'off_active_historical_contributors': [],
        },
        'frozen_roster_transactions': {'status': 'available', 'events': []},
        'frozen_rotation_impact': {'status': 'complete', 'starts': []},
    }


def _snapshot(snapshot_id, represented_date, state_code='operationally_stable', pitcher_ids=(7,)):
    snapshot = SimpleNamespace(
        id=snapshot_id, sync_run_id=snapshot_id + 1000,
        data_through=date.fromisoformat(represented_date), payload_version=1,
        snapshot_type='bullpen_dashboard', status='ready', is_published=True,
        published_at=datetime(2026, 9, 22, 12), payload={},
    )
    snapshot.payload = {
        'trusted_team_boards': {
            'contract': 'trusted_team_board_publication_v1',
            'data_through': represented_date,
            'by_team_id': {str(TEAM_ID): _team(snapshot, state_code, pitcher_ids)},
        },
    }
    return snapshot


def _pair(previous, current):
    identity = build_comparison_identity(current, previous)
    current.payload['what_changed_since_yesterday'] = {'comparison': {'identity': identity}}
    return identity


def test_changed_team_state_uses_receipts_and_quiet_is_distinct():
    previous = _snapshot(1, '2026-09-21', 'operationally_stable')
    current = _snapshot(2, '2026-09-22', 'operationally_constrained')
    _pair(previous, current)
    result = build_frozen_what_changed(previous, current, TEAM_ID)
    assert result['events'][0]['event_type'] == 'team_state_changed'
    assert result['events'][0]['previous_value'] == 'Fresh'
    assert result['events'][0]['current_value'] == 'Stretched'
    assert result['comparison_identity']['previous_snapshot_id'] == previous.id

    current = _snapshot(2, '2026-09-22', 'operationally_stable')
    _pair(previous, current)
    quiet = build_frozen_what_changed(previous, current, TEAM_ID)
    assert quiet['state'] == 'quiet'
    assert quiet['quiet_message'] == QUIET_COPY
    assert quiet['events'] == []
    assert quiet['domains']['team_state']['outcome'] == 'unchanged'


def test_missing_predecessor_and_missing_old_receipt_are_not_quiet():
    current = _snapshot(2, '2026-09-22')
    missing = build_frozen_what_changed(None, current, TEAM_ID)
    assert missing['state'] == 'unavailable'
    assert missing['reason_code'] == 'no_prior_trusted_comparison'

    previous = _snapshot(1, '2026-09-21')
    _pair(previous, current)
    previous.payload['trusted_team_boards']['by_team_id'][str(TEAM_ID)].pop('frozen_team_state')
    result = build_frozen_what_changed(previous, current, TEAM_ID)
    assert result['domains']['team_state']['status'] == 'unavailable'
    assert result['state'] == 'quiet'
    assert result['comparison_status'] == 'partial'


def test_roster_transaction_usage_and_rotation_events_are_selective_and_ordered():
    previous = _snapshot(1, '2026-09-21', pitcher_ids=(7, 8))
    current = _snapshot(2, '2026-09-22', 'operationally_constrained', pitcher_ids=(7, 9))
    _pair(previous, current)
    before = previous.payload['trusted_team_boards']['by_team_id'][str(TEAM_ID)]
    after = current.payload['trusted_team_boards']['by_team_id'][str(TEAM_ID)]
    after['recent_usage_rest']['active_pitchers'][0]['back_to_back'] = _fact(
        True, most_recent_date='2026-09-22',
    )
    prior_event = {'event_id': 'old'}
    before['frozen_roster_transactions']['events'] = [prior_event]
    after['frozen_roster_transactions']['events'] = [prior_event, {
        'event_id': 'new', 'evidence_status': 'complete', 'player_id': 9,
        'player_name': 'Arm 9', 'date': '2026-09-22', 'label': 'Recalled',
        'direction': 'addition',
    }]
    after['frozen_rotation_impact']['starts'] = [{
        'mlb_game_pk': 123, 'status': 'complete', 'short_start': True,
        'short_start_evidence': {'status': 'complete'}, 'starter_pitcher_id': 42,
        'starter_name': 'Starter', 'starter_innings': '3.2',
        'bullpen_innings': '5.1', 'game_date': '2026-09-22',
    }]
    result = build_frozen_what_changed(previous, current, TEAM_ID)
    assert [event['domain'] for event in result['events']] == [
        'team_state', 'roster', 'roster', 'workload_rest', 'rotation',
    ]
    assert result['reason_code'] is None
    joined = next(event for event in result['events'] if event['event_type'] == 'active_bullpen_joined')
    assert joined['facts']['verified_transaction']['transaction_id'] == 'new'
    assert 'Recalled' in joined['summary']
    assert 'old' not in repr(result['events'])
    assert result['domains']['roles_deployment']['status'] == 'not_comparable'
    assert result['domains']['performance']['status'] == 'not_comparable'


def test_partial_domain_does_not_erase_valid_event_and_raw_numeric_changes_are_ignored():
    previous = _snapshot(1, '2026-09-21')
    current = _snapshot(2, '2026-09-22', 'operationally_constrained')
    _pair(previous, current)
    after = current.payload['trusted_team_boards']['by_team_id'][str(TEAM_ID)]
    after['recent_usage_rest']['active_pitchers'][0]['back_to_back'] = _fact(None, status='partial')
    after['recent_usage_rest']['active_pitchers'][0]['pitches_last_7_days'] = 999
    result = build_frozen_what_changed(previous, current, TEAM_ID)
    assert [event['event_type'] for event in result['events']] == ['team_state_changed']
    assert result['comparison_status'] == 'partial'
    assert result['domains']['workload_rest']['status'] == 'partial'


def test_attachment_freezes_by_value_for_every_team_package():
    previous = _snapshot(1, '2026-09-21')
    current = _snapshot(2, '2026-09-22')
    _pair(previous, current)
    original = deepcopy(previous.payload)
    attach_frozen_what_changed(current, previous)
    carrier = current.payload['trusted_team_boards']['by_team_id'][str(TEAM_ID)]['frozen_what_changed']
    assert carrier['current_snapshot_id'] == current.id
    assert carrier['previous_snapshot_id'] == previous.id
    assert previous.payload == original

    team = current.payload['trusted_team_boards']['by_team_id'][str(TEAM_ID)]
    served = _frozen_what_changed_for_view(current, team, TEAM_ID)
    assert served == carrier
    team['frozen_what_changed']['events'] = [{
        **carrier['events'][0], 'current_snapshot_id': 999,
    }] if carrier['events'] else [{
        'event_type': 'invalid', 'domain': 'team_state', 'summary': 'Invalid',
        'evidence_status': 'complete', 'current_snapshot_id': 999,
        'previous_snapshot_id': previous.id,
        'method_version': 'team_board_what_changed_event_v1',
    }]
    assert _frozen_what_changed_for_view(current, team, TEAM_ID) is None
