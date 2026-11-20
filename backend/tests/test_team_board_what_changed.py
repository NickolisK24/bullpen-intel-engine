from copy import deepcopy
from datetime import date, datetime, timedelta
from types import SimpleNamespace

from services import public_team_relief_work as relief, role_movement
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
        'team': {'team_id': TEAM_ID},
        'recent_usage_rest_authority': {
            'method_version': relief.RECENT_USAGE_REST_METHOD_VERSION,
            'public_contract_version': relief.RECENT_USAGE_REST_PUBLIC_CONTRACT_VERSION,
            'carrier_contract_version': relief.RECENT_USAGE_REST_CONTRACT,
            'team_board_package_contract': 'trusted_team_board_publication_v1',
            'reference_date_policy': relief.RECENT_USAGE_REST_REFERENCE_DATE_POLICY,
            'data_through': snapshot.data_through.isoformat(),
            'reference_date': snapshot.availability_reference_date.isoformat(),
        },
        'default_pitcher_ids': list(pitcher_ids),
        'records': [{'pitcher_id': pitcher_id, 'name': f'Arm {pitcher_id}'} for pitcher_id in pitcher_ids],
        'frozen_team_state': make_receipt(
            snapshot, TEAM_ID, readiness, method_version=EXPECTED_METHOD_VERSION,
        ),
        'recent_usage_rest': {
            'contract': relief.RECENT_USAGE_REST_CONTRACT,
            'population_basis': relief.RECENT_USAGE_REST_POPULATION_BASIS,
            'appearance_policy': relief.RECENT_USAGE_REST_APPEARANCE_POLICY,
            'window_policy': relief.RECENT_USAGE_REST_REFERENCE_DATE_POLICY,
            'thresholds': {'high_pitch_outing_minimum_pitches': 25, 'multi_inning_minimum_outs': 4,
                           'three_in_four_minimum_distinct_days': 3, 'four_in_six_minimum_distinct_days': 4},
            'data_through': snapshot.data_through.isoformat(),
            'reference_date': snapshot.availability_reference_date.isoformat(),
            'status': 'complete',
            'active_pitchers': [{
                'pitcher_id': pitcher_id, 'pitcher_name': f'Arm {pitcher_id}',
                'back_to_back': _fact(False), 'three_in_four': _fact(False),
                'four_in_six': _fact(False), 'recent_multi_inning': _fact(False), 'high_pitch_outing': _fact(False),
            } for pitcher_id in pitcher_ids],
            'off_active_historical_contributors': [],
        },
        'frozen_roster_transactions': {'status': 'available', 'events': []},
        'frozen_rotation_impact': {'status': 'complete', 'starts': []},
    }


def _snapshot(snapshot_id, represented_date, state_code='operationally_stable', pitcher_ids=(7,)):
    snapshot = SimpleNamespace(
        id=snapshot_id, sync_run_id=snapshot_id + 1000,
        availability_reference_date=date.fromisoformat(represented_date) + timedelta(days=1),
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


def _movement(snapshot, late):
    from services import team_board_public_deployment_context as context

    team = snapshot.payload['trusted_team_boards']['by_team_id'][str(TEAM_ID)]
    start, end, prior_start, prior_end = role_movement.window_bounds(snapshot.data_through)
    window = dict(window_days=7, appearances=4, season_phase='regular_season',
                  known_leverage_appearances=4, high_leverage_appearances=0,
                  known_entry_appearances=4, eighth_or_later_appearances=0)
    recent = dict(window, start_date=str(start), through_date=str(end), eighth_or_later_appearances=late)
    prior = dict(window, start_date=str(prior_start), through_date=str(prior_end))
    profile = dict(pitcher_id=7, recent_window=recent, prior_window=prior,
                   **role_movement.classify_observed_role_movement(recent=recent, prior=prior))
    team['roles_deployment_authority'] = dict(method_version=context.METHOD_VERSION,
        public_contract_version=context.CONTRACT, team_board_package_contract='trusted_team_board_publication_v1',
        data_through=str(end))
    team['roles_deployment'] = dict(contract=context.CONTRACT, method_version=context.METHOD_VERSION,
        data_through=str(end), window_days=14, team_id=TEAM_ID, profiles=[], role_movement=dict(
            contract=role_movement.CONTRACT, method_version=role_movement.METHOD_VERSION, data_through=str(end),
            game_types=sorted(role_movement.GAME_TYPES), status='complete',
            population_basis=relief.DEPLOYMENT_PROFILE_POPULATION_BASIS, profiles=[profile]))
    return profile


def test_named_arm_history_retains_all_proven_events_before_board_limit():
    arms = tuple(range(7, 14))
    previous = _snapshot(1, '2026-09-21', pitcher_ids=arms)
    current = _snapshot(2, '2026-09-22', pitcher_ids=arms)
    _pair(previous, current)
    _movement(previous, 0)
    movement = _movement(current, 4)
    for snap in (previous, current):
        team = snap.payload['trusted_team_boards']['by_team_id'][str(TEAM_ID)]
        for arm in team['recent_usage_rest']['active_pitchers']:
            arm['back_to_back'] = _fact(snap is previous)
            arm['windows'] = {'yesterday': {
                'start_date': str(snap.data_through), 'through_date': str(snap.data_through), 'window_days': 1,
                'appearances': _fact(1), 'pitches': _fact(12), 'outs': _fact(3),
            }}
    attach_frozen_what_changed(current, previous)
    team = current.payload['trusted_team_boards']['by_team_id'][str(TEAM_ID)]
    board = team['frozen_what_changed']
    assert len(board['events']) == 5 and board['reason_code'] == 'event_limit_applied'
    history = team['frozen_arm_changes']
    assert history['comparison_identity'] == board['comparison_identity']
    events = history['events']
    assert sum(e['event_type'] == 'back_to_back_ended' for e in events) == 7
    assert sum(e['event_type'] == 'relief_work_recorded' for e in events) == 7
    deployed, = [e for e in events if e['domain'] == 'roles_deployment']
    assert (deployed['previous_value'], deployed['current_value']) == ('stable', 'later_or_higher_leverage')
    assert 'Arm 7' in deployed['summary'] and 'later-inning' in deployed['summary']
    movement['recent_window']['known_entry_appearances'] = 99
    assert not any(e['domain'] == 'roles_deployment' for e in build_frozen_what_changed(previous, current, TEAM_ID)['events'])
    assert history['domains']['roles_deployment']['status'] == 'complete'


def test_partial_prior_fact_or_incompatible_method_cannot_prove_a_transition():
    previous = _snapshot(1, '2026-09-21')
    current = _snapshot(2, '2026-09-22')
    _pair(previous, current)
    before = previous.payload['trusted_team_boards']['by_team_id'][str(TEAM_ID)]
    after = current.payload['trusted_team_boards']['by_team_id'][str(TEAM_ID)]
    before['recent_usage_rest']['active_pitchers'][0]['three_in_four'] = _fact(None)
    after['recent_usage_rest']['active_pitchers'][0]['three_in_four'] = _fact(True)
    _movement(previous, 0)
    _movement(current, 4)['method_version'] = 'unknown'
    result = build_frozen_what_changed(previous, current, TEAM_ID)
    assert result['events'] == []
    assert result['domains']['roles_deployment']['status'] == 'partial'
    before['recent_usage_rest_authority']['method_version'] = 'unknown'
    assert build_frozen_what_changed(previous, current, TEAM_ID)['domains']['workload_rest']['status'] == 'unavailable'


def test_same_movement_does_not_repeat_and_unavailable_signal_is_not_stability():
    prior = _snapshot(1, '2026-09-21')
    current = _snapshot(2, '2026-09-22')
    _pair(prior, current)
    _movement(prior, 4)
    profile = _movement(current, 4)
    read = build_frozen_what_changed(prior, current, TEAM_ID)
    assert read['domains']['roles_deployment']['status'] == 'complete' and not read['events']
    profile.update(status='unavailable', movement=None)
    read = build_frozen_what_changed(prior, current, TEAM_ID)
    assert read['domains']['roles_deployment']['status'] == 'partial' and not read['events']
    _movement(current, 0)
    event, = build_frozen_what_changed(prior, current, TEAM_ID)['events']
    assert event['current_value'] == 'stable' and event['previous_value'] == 'later_or_higher_leverage'


def _install_board_inputs(snapshot, read_key, pitch_count):
    from services import public_serving_authority as authority, team_board_delta_substrate as delta
    from services.pitcher_public_labels import ARM_READ_METHOD_VERSION, READ_PUBLIC_LABELS

    package = snapshot.payload['trusted_team_boards']
    team = package['by_team_id'][str(TEAM_ID)]
    ref = snapshot.availability_reference_date.isoformat()
    day = snapshot.data_through.isoformat()
    package['availability_reference_date'] = ref
    snapshot.payload['freshness'] = {'availability_reference_date': ref, 'data_through': day, 'is_current': True}
    team['arm_read_method'] = ARM_READ_METHOD_VERSION
    team['roster_authority'] = {'readiness': {'claims_available': True}}
    team['bullpen_membership_authority'] = {
        'method_version': authority.BULLPEN_MEMBERSHIP_METHOD_VERSION,
        'public_contract_version': authority.BULLPEN_MEMBERSHIP_PUBLIC_CONTRACT_VERSION,
        'carrier_contract_version': authority.BULLPEN_MEMBERSHIP_CARRIER_CONTRACT,
        'team_board_package_contract': package['contract'],
        'population_basis': delta._canonical_membership_population_basis(),
        'reference_date_policy': authority.BULLPEN_MEMBERSHIP_REFERENCE_DATE_POLICY,
        'membership_reference_date': ref,
    }
    team['records'][0].update({
        'pitcher_labels': {'read': READ_PUBLIC_LABELS[read_key]},
        'roster_status': {'is_authoritative': True, 'is_active_mlb': True},
        'availability': {'data_state': 'fresh'}, 'last_workload_appearance': {'game_date': day},
    })
    team['workload_windows_authority'] = {
        'method_version': relief.WORKLOAD_WINDOWS_METHOD_VERSION,
        'public_contract_version': relief.WORKLOAD_WINDOWS_PUBLIC_CONTRACT_VERSION,
        'team_board_package_contract': package['contract'], 'data_through': day,
        'population_basis': {'basis': relief.WORKLOAD_WINDOWS_POPULATION_BASIS,
                             'population_authority': relief.WORKLOAD_WINDOWS_POPULATION_AUTHORITY,
                             'membership_authority': relief.WORKLOAD_WINDOWS_MEMBERSHIP_AUTHORITY},
        'reference_date_policy': relief.WORKLOAD_WINDOWS_REFERENCE_DATE_POLICY,
    }
    team['workload_windows'] = {
        'contract': relief.WORKLOAD_WINDOWS_CARRIER_CONTRACT, 'data_through': day,
        'overview': {
            'contract': relief.WORKLOAD_OVERVIEW_CONTRACT, 'data_through': day,
            'window_policy': relief.WORKLOAD_WINDOWS_REFERENCE_DATE_POLICY,
            'population_basis': relief.WORKLOAD_WINDOWS_POPULATION_BASIS,
            'windows': {
                f'window_{n}': {
                    'start': (snapshot.data_through - timedelta(days=n-1)).isoformat(),
                    'through': day, 'pitches': _fact(pitch_count), 'appearances': _fact(1), 'outs': _fact(3),
                } for n in (3, 7, 14, 30)
            },
        },
    }
    return team


def test_board_changes_use_exact_windows_public_arm_reads_and_complete_population():
    previous, current = _snapshot(1, '2026-09-21'), _snapshot(2, '2026-09-22')
    _pair(previous, current)
    before = _install_board_inputs(previous, 'clean_option', 15)
    after = _install_board_inputs(current, 'watch_arm', 0)
    result = build_frozen_what_changed(previous, current, TEAM_ID)
    events = {event['event_type']: event for event in result['events']}
    assert events['arm_read_changed']['summary'] == 'Arm 7 moved from Clean Option to Watch Arm.'
    assert events['clean_option_count_changed']['current_value'] == 0
    assert events['workload_7_day_changed']['facts']['deltas']['pitches'] == -15
    assert 'pitches 15 to 0' in events['workload_14_day_changed']['summary']
    trend = result['domains']['team_burden']
    assert trend['status'] == 'complete'
    assert trend['deltas']['window_30'] == {'pitches': -15, 'appearances': 0, 'outs': 0}

    before['workload_windows']['overview']['windows']['window_7']['pitches'] = _fact(None, status='unknown')
    after['records'][0]['availability']['data_state'] = 'stale'
    result = build_frozen_what_changed(previous, current, TEAM_ID)
    assert result['domains']['team_burden']['status'] == 'partial'
    assert 'pitches' not in result['domains']['team_burden']['deltas']['window_7']
    assert [e['event_type'] for e in result['events']] == ['workload_14_day_changed']
    assert result['domains']['clean_options']['status'] == 'unavailable'

    after['workload_windows']['overview']['population_basis'] = 'different'
    result = build_frozen_what_changed(previous, current, TEAM_ID)
    assert result['domains']['team_burden']['status'] == 'unavailable'
    assert not result['events']

def test_served_overview_uses_the_same_frozen_comparison_as_what_changed():
    from services.public_serving_authority import build_published_team_board

    previous, current = _snapshot(1, '2026-09-21'), _snapshot(2, '2026-09-22')
    current.snapshot_generated_at = None
    _pair(previous, current)
    _install_board_inputs(previous, 'watch_arm', 0)
    _install_board_inputs(current, 'clean_option', 12)
    attach_frozen_what_changed(current, previous)
    board = build_published_team_board(TEAM_ID, snapshot_override=current, include_recent_usage_rest=True)
    assert board['workload_overview']['trend_status'] == 'complete'
    assert board['workload_overview']['trend_previous_date'] == '2026-09-21'
    assert board['workload_overview']['trend_deltas']['window_7']['pitches'] == 12
    assert len(board['frozen_what_changed']['events']) == 4

    team = current.payload['trusted_team_boards']['by_team_id'][str(TEAM_ID)]
    team['frozen_what_changed']['previous_snapshot_id'] += 1
    board = build_published_team_board(TEAM_ID, snapshot_override=current, include_recent_usage_rest=True)
    assert board['frozen_what_changed'] is None
    assert 'trend_deltas' not in board['workload_overview']


def test_historical_or_incompatible_arm_reads_leave_team_workload_comparable():
    previous, current = _snapshot(1, '2026-09-21'), _snapshot(2, '2026-09-22')
    _pair(previous, current)
    before = _install_board_inputs(previous, 'clean_option', 0)
    _install_board_inputs(current, 'watch_arm', 15)
    for field, invalid in [('arm_read_method', 'older'), ('roster_authority', {}),
                           ('default_pitcher_ids', [7, 8])]:
        saved = before[field]
        before[field] = invalid
        result = build_frozen_what_changed(previous, current, TEAM_ID)
        assert result['domains']['clean_options']['status'] == 'unavailable'
        assert result['domains']['arm_reads']['status'] == 'unavailable'
        assert result['domains']['team_burden']['status'] == 'complete'
        before[field] = saved
