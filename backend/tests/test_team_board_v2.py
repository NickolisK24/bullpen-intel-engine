from copy import deepcopy
from pathlib import Path

import pytest
from flask import Flask

import api.team_board_v2 as team_board_v2_api
from services.team_board_v2 import (
    ACTIVE_BULLPEN_POPULATION_BASIS,
    CAPABILITY,
    CONTRACT_VERSION,
    RECENT_USAGE_POPULATION_BASIS,
    RECENTLY_USED_ARMS_CONTRACT,
    RECENTLY_USED_ARMS_WINDOW_DAYS,
    RECENTLY_USED_ARMS_WINDOW_POLICY,
    RECENT_RELIEF_WORK_POPULATION_BASIS,
    ROLES_DEPLOYMENT_POPULATION_BASIS,
    ROTATION_IMPACT_POPULATION_BASIS,
    WORKLOAD_OVERVIEW_POPULATION_BASIS,
    build_team_board_v2_payload,
    unavailable_section,
)
from services.public_recent_transactions import POPULATION_BASIS as RECENT_TRANSACTIONS_POPULATION_BASIS


TEAM = {
    'team_id': 1,
    'team_name': 'Example Club',
    'team_abbreviation': 'EX',
}


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(team_board_v2_api.team_board_v2_bp, url_prefix='/api/bullpen')
    return app.test_client()
TEAM_STATE = {
    'contract': 'public_team_state_v1',
    'available': True,
    'public_state': 'fresh',
    'public_label': 'Fresh',
    'summary': 'Canonical Team State summary.',
    'outcome': 'available',
    'unavailable_message': None,
    'reason_code': None,
    'data_through': '2026-08-16',
}
ROTATION = {
    'capability': 'rotation_support_pressure_v1',
    'version': '2026-06-18.phase2',
    'status': 'neutral',
    'reference_date': '2026-08-16',
    'starter_avg_innings': 5.33,
    'bullpen_innings_required': 8.0,
    'short_start_rate': 0.25,
    'summary': 'The rotation averaged 5.3 innings per start over the last 7 days, requiring 8.0 bullpen innings.',
    'limitations': [],
}
ARM = {
    'pitcher_id': 7,
    'name': 'Example Arm',
    'availability_status': 'Monitor',
    'availability_public_label': 'On Watch',
    'confidence': 'high',
    'short_reason': 'Recent workload needs a check',
    'last_appearance': {'date': '2026-08-15', 'pitches': 18},
    'last_workload_appearance': {'date': '2026-08-15', 'pitches': 18},
    'workload_facts': {
        'days_since_last_appearance': 1,
        'appearances_last_7': 2,
        'pitches_last_7_days': None,
        'back_to_back': False,
    },
    'data_state': 'fresh',
    'reasons': ['Worked yesterday'],
    'limitations': [],
    'pitcher_labels': {
        'role': {'key': 'bridge_arm', 'label': 'Setup Arm'},
        'read': {'key': 'monitor', 'label': 'On Watch'},
    },
    'public_role_read': {
        'key': 'bridge_arm',
        'label': 'Setup Arm',
        'headline': 'Setup / Bridge Pattern',
        'reason': 'Observed usage supports this role read.',
        'evidence': [],
    },
    'roster_status': {'status': 'active'},
    'visibility': {'is_visible_by_default': True},
}


def _board(*, rotation=None):
    return {
        'capability': 'tonights_bullpen_board',
        'team': deepcopy(TEAM),
        'generated_at': '2026-08-17T12:00:00+00:00',
        'freshness': {'data_through': '2026-08-16'},
        'team_state': deepcopy(TEAM_STATE),
        'groups': [
            {'status': 'Available', 'count': 0, 'pitchers': []},
            {'status': 'Monitor', 'count': 1, 'pitchers': [deepcopy(ARM)]},
            {'status': 'Avoid', 'count': 0, 'pitchers': []},
            {'status': 'Unavailable', 'count': 0, 'pitchers': []},
        ],
        'total_pitchers': 1,
        'rest_status': {
            'available': True,
            'active_arm_count': 1,
            'rested_arm_count': 0,
            'worked_yesterday_count': 1,
            'back_to_back_count': 0,
            'summary': '0 of 1 active bullpen arm have at least one full day of rest.',
            'reason_code': None,
        },
        'rotation_support_pressure': deepcopy(rotation or ROTATION),
        'team_shape': {
            'workloadConcentration': {
                'key': 'workloadConcentration',
                'label': 'Some Workload Concentration',
                'summary': 'Two arms have carried 62% of the recent relief work across five bullpen arms.',
                'supportingCounts': {
                    'windowDays': 7,
                    'topSharePct': 62,
                    'topArmCount': 2,
                },
            },
        },
        'roster_authority': {
            'capability': 'roster_authority_v1',
            'readiness': {'current_roster_claims_available': True},
            'limitations': [],
        },
        'limitations': ['Manager intent is not known.'],
    }


def _relief_work():
    return {
        'capability': 'public_team_relief_work',
        'team': deepcopy(TEAM),
        'data_through': '2026-08-16',
        'scope_sentence': 'Covers appearances made for EX per official MLB game records.',
        'relief_by_date': [{
            'game_date': '2026-08-15',
            'available': True,
            'appearances': [{
                'pitcher_id': 7,
                'pitcher_full_name': 'Example Arm',
                'mlb_game_pk': 123,
                'game_date': '2026-08-15',
                'innings_pitched_outs': 3,
                'innings_pitched': 1.0,
                'pitches_thrown': None,
                'opponent': 'Opponent Club',
                'opponent_abbreviation': 'OPP',
            }],
        }],
        'windows': {
            'window_7': {
                'through': '2026-08-16',
                'relief_appearances': 4,
                'pitchers_in_relief': 3,
                'pitches_total': None,
                'appearances_with_pitches': 3,
                'start_relief_unknown': 0,
                'pitches_sentence': 'Pitch count unavailable for 1 of 4 relief appearances; 52 pitches across the other 3.',
            },
            'window_14': {
                'through': '2026-08-16',
                'relief_appearances': 8,
                'pitchers_in_relief': 5,
                'pitches_total': 121,
                'appearances_with_pitches': 8,
                'start_relief_unknown': 0,
                'pitches_sentence': '121 pitches across those 8 relief appearances.',
            },
        },
    }


def _game_context():
    return {
        'capability': 'team_game_context',
        'team': deepcopy(TEAM),
        'available': True,
        'state': 'stored_game_log',
        'reference_date': '2026-08-16',
        'game_date': '2026-08-15',
        'opponent': 'Opponent Club',
        'missing_fields': ['home_away', 'scheduled_time'],
    }


def _recent_transactions(*, status='available', events=None, limitations=None):
    return {
        'capability': 'public_recent_transactions_v1',
        'version': '2026-08-20.rotation-roster',
        'population_basis': RECENT_TRANSACTIONS_POPULATION_BASIS,
        'status': status,
        'events': events if events is not None else [{
            'event_id': 'tx-1',
            'player_id': 7,
            'player_mlb_id': 700007,
            'player_name': 'Example Arm',
            'date': '2026-08-16',
            'type': 'recall',
            'label': 'Recalled',
            'description': 'Example Arm was recalled.',
        }],
        'window_start_date': '2026-08-10',
        'window_end_date': '2026-08-17',
        'represented_date': '2026-08-17',
        'limitations': limitations or [],
    }


def test_contract_pins_version_and_preserves_canonical_owner_outputs():
    board = _board()
    relief = _relief_work()
    context = _game_context()
    originals = deepcopy((board, relief, context))

    payload = build_team_board_v2_payload(
        board,
        recent_relief_work=relief,
        recent_transactions=_recent_transactions(),
        game_context=context,
    )

    assert payload['capability'] == CAPABILITY
    assert payload['contract_version'] == CONTRACT_VERSION
    assert payload['team_state'] == TEAM_STATE
    assert payload['summary'] == TEAM_STATE['summary']
    assert payload['rotation_impact']['read'] == ROTATION
    assert payload['recent_transactions'] == _recent_transactions()
    assert payload['section_status']['recent_transactions']['status'] == 'available'
    assert payload['recent_relief_work']['read'] == relief
    assert payload['section_status']['recent_relief_work']['status'] == 'available'
    assert payload['game_context'] == context
    assert (board, relief, context) == originals


def test_active_bullpen_matches_legacy_population_and_preserves_unknowns():
    board = _board()
    payload = build_team_board_v2_payload(board, recent_relief_work=_relief_work())
    arms = payload['active_bullpen']['arms']

    legacy_ids = [
        card['pitcher_id']
        for group in board['groups']
        for card in group['pitchers']
    ]
    assert [arm['pitcher_id'] for arm in arms] == legacy_ids
    assert payload['active_bullpen']['population_basis'] == ACTIVE_BULLPEN_POPULATION_BASIS
    assert arms[0]['workload']['pitches_last_7_days'] is None
    assert arms[0]['workload']['back_to_back'] is False
    assert arms[0]['availability']['label'] == 'On Watch'
    assert arms[0]['public_role_read'] == ARM['public_role_read']
    assert set(arms[0]) == {
        'pitcher_id', 'name', 'public_role_read', 'public_labels', 'availability',
        'last_appearance', 'workload', 'roster_status', 'visibility',
    }
    assert 'fatigue_score' not in repr(arms)
    assert '3_in_4' not in repr(arms)
    assert '4_in_6' not in repr(arms)


def test_roles_deployment_reuses_public_role_reads_in_governed_order():
    board = _board()
    roles = [
        ('coverage_arm', 'Coverage Arm'),
        ('limited_read', 'Role Unclear'),
        ('trust_arm', 'Trusted Arm'),
        ('bridge_arm', 'Setup Arm'),
        ('depth_arm', 'Middle Relief Arm'),
    ]
    cards = []
    for index, (key, label) in enumerate(roles, start=1):
        card = deepcopy(ARM)
        card['pitcher_id'] = index
        card['name'] = f'Arm {index}'
        card['public_role_read'] = {'key': key, 'label': label}
        card['pitcher_labels']['role'] = {'key': key, 'label': label}
        cards.append(card)
    board['groups'][1]['pitchers'] = cards
    board['groups'][1]['count'] = len(cards)
    board['total_pitchers'] = len(cards)

    payload = build_team_board_v2_payload(board)
    composition = payload['roles_deployment']

    assert composition['population_basis'] == ROLES_DEPLOYMENT_POPULATION_BASIS
    assert composition['arm_count'] == len(cards)
    assert composition['role_arm_count'] == len(cards)
    assert composition['missing_role_count'] == 0
    assert [role['role_key'] for role in composition['roles']] == [
        'trust_arm', 'bridge_arm', 'depth_arm', 'coverage_arm', 'limited_read',
    ]
    assert [role['label'] for role in composition['roles']] == [
        'Trusted Arm', 'Setup Arm', 'Middle Relief Arm', 'Coverage Arm', 'Role Unclear',
    ]
    assert [role['arm_count'] for role in composition['roles']] == [1, 1, 1, 1, 1]
    assert payload['section_status']['roles_deployment']['status'] == 'partial'
    assert composition['deployment_profile'] is None


def test_roles_deployment_matches_visible_active_population_and_preserves_missing_role():
    board = _board()
    missing = deepcopy(ARM)
    missing['pitcher_id'] = 8
    missing['name'] = 'Unknown Role Arm'
    missing['public_role_read'] = None
    missing['pitcher_labels']['role'] = {'key': 'trust_arm', 'label': 'Trusted Arm'}
    hidden = deepcopy(ARM)
    hidden['pitcher_id'] = 9
    hidden['visibility'] = {'is_visible_by_default': False}
    board['groups'][1]['pitchers'] = [missing, hidden]
    board['groups'][1]['count'] = 2
    board['total_pitchers'] = 1

    payload = build_team_board_v2_payload(board)
    composition = payload['roles_deployment']

    assert [arm['pitcher_id'] for arm in payload['active_bullpen']['arms']] == [8]
    assert composition['arm_count'] == 1
    assert composition['role_arm_count'] == 0
    assert composition['missing_role_count'] == 1
    assert composition['roles'] == []
    assert payload['section_status']['roles_deployment']['status'] == 'partial'
    assert payload['section_status']['roles_deployment']['reason_code'] == 'role_composition_limited'
    assert payload['active_bullpen']['arms'][0]['public_labels']['role']['label'] == 'Trusted Arm'


def test_roles_deployment_copies_canonical_observed_profile_without_inference():
    board = _board()
    card = board['groups'][1]['pitchers'][0]
    card.update({
        'saves': 12,
        'holds': 8,
        'inning_entered': 9,
        'multi_inning_appearances': 4,
        'leverage_index': 2.4,
        'role_movement': 'promoted',
    })

    deployment = {
        'contract': 'team_board_deployment_profile_carrier_v1',
        'status': 'complete',
        'data_through': '2026-08-20',
        'window_days': 14,
        'summary': 'One arm recorded a save or hold and one arm worked multiple innings.',
        'profiles': [{
            'pitcher_id': 1,
            'pitcher_name': 'Observed Arm',
            'saves': 0,
            'holds': 2,
            'multi_inning_appearances': 1,
            'appearances_analyzed': 3,
            'appearances_with_outs': 3,
            'summary': 'Observed Arm recorded 0 saves, 2 holds, and worked multiple innings in 1 of 3 relief appearances with recorded outs during the 14-day window.',
        }],
        'limitations': [],
    }
    composition = build_team_board_v2_payload(
        board,
        recent_relief_work={'deployment_profile': deployment},
    )['roles_deployment']

    assert composition['roles'] == [{
        'role_key': 'bridge_arm',
        'label': 'Setup Arm',
        'arm_count': 1,
    }]
    assert composition['deployment_profile'] == deployment
    for forbidden in (
        'inning_entered', 'leverage', 'movement', 'trend', 'manager', 'prediction',
        'closer', 'fireman',
    ):
        assert forbidden not in repr(composition).lower()


def test_recent_usage_projects_existing_chronology_and_preserves_nulls():
    relief = _relief_work()
    relief['relief_by_date'].append({
        'game_date': '2026-08-14',
        'available': True,
        'appearances': [{
            'pitcher_id': 9,
            'pitcher_full_name': 'Second Arm',
            'mlb_game_pk': 122,
            'game_date': '2026-08-14',
            'innings_pitched_outs': 2,
            'pitches_thrown': 0,
            'opponent': None,
            'opponent_abbreviation': None,
        }],
    })

    payload = build_team_board_v2_payload(_board(), recent_relief_work=relief)
    recent = payload['recent_usage']

    assert recent == {
        'population_basis': RECENT_USAGE_POPULATION_BASIS,
        'appearances': [
            {
                'pitcher_id': 7,
                'pitcher_name': 'Example Arm',
                'game_date': '2026-08-15',
                'opponent': 'Opponent Club',
                'opponent_abbreviation': 'OPP',
                'pitches_thrown': None,
                'outs_recorded': 3,
                'game_id': 123,
            },
            {
                'pitcher_id': 9,
                'pitcher_name': 'Second Arm',
                'game_date': '2026-08-14',
                'opponent': None,
                'opponent_abbreviation': None,
                'pitches_thrown': 0,
                'outs_recorded': 2,
                'game_id': 122,
            },
        ],
        'represented_date': '2026-08-16',
        'limitations': [],
    }
    assert payload['section_status']['recent_usage']['status'] == 'available'
    assert [row['pitcher_id'] for row in recent['appearances']] == [7, 9]
    for forbidden in ('3_in_4', '4_in_5', '4_in_6', 'fatigue', 'rest_quality'):
        assert forbidden not in repr(recent)


def test_recent_usage_scopes_source_limitations_without_partial_rows():
    relief = _relief_work()
    relief['relief_by_date'].insert(0, {
        'game_date': '2026-08-16',
        'unavailable': True,
        'sentence': 'August 16 — relief work is unavailable.',
        'appearances': [],
    })

    payload = build_team_board_v2_payload(_board(), recent_relief_work=relief)

    assert [row['pitcher_id'] for row in payload['recent_usage']['appearances']] == [7]
    assert payload['section_status']['recent_usage'] == {
        'status': 'partial',
        'reason_code': 'recent_usage_reconciliation_limited',
        'limitations': ['August 16 — relief work is unavailable.'],
        'represented_date': '2026-08-16',
    }
    assert payload['recently_used_arms']['value'] is None
    assert payload['recently_used_arms']['reason_code'] == (
        'recent_relief_work_incomplete'
    )
    assert payload['rest_status'] == _board()['rest_status']


def test_recent_relief_work_status_recognizes_reconciled_withheld_groups():
    relief = _relief_work()
    relief['relief_by_date'].insert(0, {
        'game_date': '2026-08-16',
        'unavailable': True,
        'sentence': 'August 16 — relief work is unavailable.',
        'appearances': [],
    })

    payload = build_team_board_v2_payload(_board(), recent_relief_work=relief)

    assert payload['recent_relief_work']['read'] == relief
    assert payload['section_status']['recent_relief_work'] == {
        'status': 'partial',
        'reason_code': 'relief_work_reconciliation_limited',
        'limitations': [],
        'represented_date': '2026-08-16',
    }


def test_recent_usage_distinguishes_missing_anchor_from_empty_population():
    unavailable = _relief_work()
    unavailable['data_through'] = None
    unavailable['relief_by_date'] = []
    empty = _relief_work()
    empty['relief_by_date'] = []

    unavailable_payload = build_team_board_v2_payload(
        _board(), recent_relief_work=unavailable
    )
    empty_payload = build_team_board_v2_payload(_board(), recent_relief_work=empty)

    assert unavailable_payload['section_status']['recent_usage'] == unavailable_section(
        'recent_usage_unavailable'
    )
    assert empty_payload['section_status']['recent_usage']['status'] == 'available'
    assert empty_payload['recent_usage']['appearances'] == []


def test_recently_used_arms_counts_distinct_current_arms_in_inclusive_three_day_window():
    board = _board()
    cards = []
    for pitcher_id in (7, 8, 9):
        card = deepcopy(ARM)
        card['pitcher_id'] = pitcher_id
        card['name'] = f'Active Arm {pitcher_id}'
        cards.append(card)
    off_active = deepcopy(ARM)
    off_active['pitcher_id'] = 10
    off_active['name'] = 'Off Active Arm'
    off_active['roster_status'] = {'status': '15-day injured list'}
    off_active['visibility'] = {'is_visible_by_default': False}
    board['groups'][1]['pitchers'] = [*cards, off_active]
    board['groups'][1]['count'] = 4
    board['total_pitchers'] = 3

    relief = _relief_work()
    relief['relief_by_date'] = [
        {
            'game_date': '2026-08-16',
            'available': True,
            'appearances': [
                {'pitcher_id': 7},
                {'pitcher_id': 7},
                {'pitcher_id': 10},
            ],
        },
        {
            'game_date': '2026-08-14',
            'available': True,
            'appearances': [{'pitcher_id': 8}],
        },
        {
            'game_date': '2026-08-13',
            'available': True,
            'appearances': [{'pitcher_id': 9}],
        },
    ]

    payload = build_team_board_v2_payload(board, recent_relief_work=relief)
    read = payload['recently_used_arms']

    assert read == {
        'contract': RECENTLY_USED_ARMS_CONTRACT,
        'status': 'available',
        'reason_code': None,
        'value': 2,
        'window_days': RECENTLY_USED_ARMS_WINDOW_DAYS,
        'window_label': 'Last 3 days',
        'window_start': '2026-08-14',
        'through': '2026-08-16',
        'window_policy': RECENTLY_USED_ARMS_WINDOW_POLICY,
        'population_basis': ACTIVE_BULLPEN_POPULATION_BASIS,
        'appearance_population_basis': RECENT_USAGE_POPULATION_BASIS,
        'summary': (
            '2 current active bullpen arms appeared in relief during the last 3 days.'
        ),
    }
    assert payload['section_status']['recently_used_arms']['status'] == 'available'


def test_recently_used_arms_empty_authoritative_window_is_zero():
    relief = _relief_work()
    relief['relief_by_date'] = []

    payload = build_team_board_v2_payload(_board(), recent_relief_work=relief)

    assert payload['recently_used_arms']['value'] == 0
    assert payload['recently_used_arms']['status'] == 'available'
    assert payload['recently_used_arms']['summary'].startswith(
        '0 current active bullpen arms'
    )


@pytest.mark.parametrize(
    ('mutate', 'reason_code'),
    [
        (
            lambda relief: relief['relief_by_date'].insert(0, {
                'game_date': '2026-08-17',
                'available': True,
                'appearances': [{'pitcher_id': 7}],
            }),
            'recent_relief_work_invalid',
        ),
        (
            lambda relief: relief.update({'unattributed_appearance_count': 1}),
            'recent_relief_work_attribution_incomplete',
        ),
        (
            lambda relief: relief.update({'data_through': '2026-08-15'}),
            'recent_relief_work_reference_mismatch',
        ),
    ],
)
def test_recently_used_arms_fails_closed_without_suppressing_other_reads(
    mutate,
    reason_code,
):
    relief = _relief_work()
    mutate(relief)

    payload = build_team_board_v2_payload(_board(), recent_relief_work=relief)

    assert payload['recently_used_arms']['value'] is None
    assert payload['recently_used_arms']['status'] == 'unavailable'
    assert payload['recently_used_arms']['reason_code'] == reason_code
    assert payload['rest_status']['available'] is True
    assert payload['active_bullpen']['arms'][0]['pitcher_id'] == 7


def test_workload_overview_projects_only_governed_windows_and_concentration():
    board = _board()
    relief = _relief_work()
    relief['windows']['window_30'] = {
        'through': '2026-08-16',
        'relief_appearances': 20,
        'pitchers_in_relief': 9,
        'pitches_total': 350,
    }

    payload = build_team_board_v2_payload(board, recent_relief_work=relief)
    workload = payload['workload_overview']

    assert workload['population_basis'] == WORKLOAD_OVERVIEW_POPULATION_BASIS
    assert workload['windows'] == [
        {
            'window_days': 7,
            'through': '2026-08-16',
            'relief_appearances': 4,
            'pitchers_in_relief': 3,
            'pitches_total': None,
        },
        {
            'window_days': 14,
            'through': '2026-08-16',
            'relief_appearances': 8,
            'pitchers_in_relief': 5,
            'pitches_total': 121,
        },
    ]
    assert workload['concentration'] == {
        'population_basis': 'current_bullpen_eligible_pitchers_recent_relief_pitch_workload',
        'label': 'Some Workload Concentration',
        'summary': 'Two arms have carried 62% of the recent relief work across five bullpen arms.',
    }
    assert payload['section_status']['workload_overview']['status'] == 'partial'
    assert workload['limitations'] == [
        'Pitch count unavailable for 1 of 4 relief appearances; 52 pitches across the other 3.'
    ]
    rendered = repr(workload)
    for forbidden in ('window_30', 'trend', 'workload_score', 'fatigue_score', '3_in_4', '4_in_6'):
        assert forbidden not in rendered


def test_workload_overview_preserves_legitimate_zero_and_missing_metrics():
    relief = _relief_work()
    relief['windows']['window_7'].update({
        'relief_appearances': 0,
        'pitchers_in_relief': 0,
        'pitches_total': 0,
        'appearances_with_pitches': 0,
    })
    relief['windows']['window_14']['pitches_total'] = None
    relief['windows']['window_14']['appearances_with_pitches'] = 7
    relief['windows']['window_14']['pitches_sentence'] = (
        'Pitch count unavailable for 1 of 8 relief appearances; 109 pitches across the other 7.'
    )

    workload = build_team_board_v2_payload(
        _board(), recent_relief_work=relief
    )['workload_overview']

    assert workload['windows'][0]['relief_appearances'] == 0
    assert workload['windows'][0]['pitches_total'] == 0
    assert workload['windows'][1]['pitches_total'] is None


def test_workload_overview_scopes_missing_parts_without_destroying_other_sections():
    board = _board()
    board['team_shape']['workloadConcentration'] = {
        'label': 'Limited Read',
        'summary': 'Recent relief pitch-count workload is incomplete.',
    }
    relief = _relief_work()
    relief['windows'].pop('window_14')

    payload = build_team_board_v2_payload(board, recent_relief_work=relief)

    assert payload['section_status']['workload_overview']['status'] == 'partial'
    assert payload['workload_overview']['windows'][0]['window_days'] == 7
    assert payload['workload_overview']['concentration']['label'] == 'Limited Read'
    assert payload['active_bullpen']['arms'][0]['pitcher_id'] == 7
    assert payload['recent_usage']['appearances'][0]['pitcher_id'] == 7
    assert payload['rest_status']['available'] is True


def test_population_bases_do_not_claim_identical_cohorts():
    payload = build_team_board_v2_payload(_board(), recent_relief_work=_relief_work())

    assert payload['active_bullpen']['population_basis'] == ACTIVE_BULLPEN_POPULATION_BASIS
    assert payload['recent_relief_work']['population_basis'] == RECENT_RELIEF_WORK_POPULATION_BASIS
    assert payload['rotation_impact']['population_basis'] == ROTATION_IMPACT_POPULATION_BASIS
    assert len({
        payload['active_bullpen']['population_basis'],
        payload['recent_relief_work']['population_basis'],
        payload['rotation_impact']['population_basis'],
    }) == 3


def test_optional_failure_keeps_independent_sections_available():
    payload = build_team_board_v2_payload(
        _board(rotation={}),
        recent_relief_work=None,
        game_context=_game_context(),
        section_errors={
            'rotation_impact': unavailable_section('rotation_impact_unavailable'),
            'recent_relief_work': unavailable_section('recent_relief_work_unavailable'),
        },
    )

    assert payload['team_state'] == TEAM_STATE
    assert payload['active_bullpen']['arms'][0]['pitcher_id'] == 7
    assert payload['section_status']['active_bullpen']['status'] == 'available'
    assert payload['section_status']['rotation_impact']['status'] == 'unavailable'
    assert payload['section_status']['recent_relief_work']['status'] == 'unavailable'
    assert payload['section_status']['recent_usage'] == unavailable_section(
        'recent_usage_unavailable'
    )
    assert payload['section_status']['game_context']['status'] == 'available'


def test_recent_transactions_status_is_scoped_and_preserves_available_events():
    partial = _recent_transactions(
        status='partial',
        limitations=['Some verified transaction records are unavailable.'],
    )
    payload = build_team_board_v2_payload(
        _board(),
        recent_transactions=partial,
    )

    assert payload['recent_transactions']['events'][0]['event_id'] == 'tx-1'
    assert payload['section_status']['recent_transactions'] == {
        'status': 'partial',
        'reason_code': 'recent_transactions_limited',
        'limitations': ['Some verified transaction records are unavailable.'],
        'represented_date': '2026-08-17',
    }

    unavailable = build_team_board_v2_payload(
        _board(),
        recent_transactions=_recent_transactions(
            status='unavailable',
            events=[],
            limitations=['Recent official transaction records are unavailable.'],
        ),
    )
    assert unavailable['team_state'] == TEAM_STATE
    assert unavailable['active_bullpen']['arms'][0]['pitcher_id'] == 7
    assert unavailable['section_status']['recent_transactions'] == unavailable_section(
        'recent_transactions_unavailable',
        limitations=['Recent official transaction records are unavailable.'],
    )


def test_unavailable_team_state_remains_null_and_uses_governed_message():
    board = _board()
    board['team_state'] = {
        'contract': 'public_team_state_v1',
        'available': False,
        'public_state': None,
        'public_label': None,
        'summary': None,
        'outcome': 'data_limited',
        'unavailable_message': 'A current Team State read is not available.',
        'reason_code': 'data_limited',
        'data_through': '2026-08-16',
    }

    payload = build_team_board_v2_payload(board)

    assert payload['team_state'] == board['team_state']
    assert payload['summary'] is None
    assert payload['section_status']['team_state'] == {
        'status': 'unavailable',
        'reason_code': 'data_limited',
        'limitations': ['A current Team State read is not available.'],
        'represented_date': '2026-08-16',
    }


def test_route_composes_each_owner_once_without_frontend_derivation(client, monkeypatch):
    calls = {'board': 0, 'relief': 0, 'game': 0, 'transactions': 0}

    def board(team_id):
        calls['board'] += 1
        assert team_id == 1
        return _board()

    def relief(team_id):
        calls['relief'] += 1
        assert team_id == 1
        return _relief_work()

    def game(team_id, reference_date=None):
        calls['game'] += 1
        assert team_id == 1
        assert reference_date.isoformat() == '2026-08-16'
        return _game_context()

    def transactions(team_id, reference_date=None):
        calls['transactions'] += 1
        assert team_id == 1
        assert reference_date.isoformat() == '2026-08-16'
        return _recent_transactions()

    monkeypatch.setattr(team_board_v2_api, 'build_published_team_board', board)
    monkeypatch.setattr(team_board_v2_api, 'build_public_team_relief_work_payload', relief)
    monkeypatch.setattr(team_board_v2_api, 'build_team_game_context', game)
    monkeypatch.setattr(team_board_v2_api, 'build_public_recent_transactions', transactions)

    response = client.get('/api/bullpen/teams/1/board-v2')
    assert response.status_code == 200
    payload = response.get_json()
    assert calls == {'board': 1, 'relief': 1, 'game': 1, 'transactions': 1}
    assert payload['contract_version'] == CONTRACT_VERSION
    assert payload['summary'] == TEAM_STATE['summary']
    assert payload['recently_used_arms']['value'] == 1
    assert payload['recently_used_arms']['window_label'] == 'Last 3 days'


def test_route_scopes_optional_failure_without_destroying_core(client, monkeypatch):
    monkeypatch.setattr(
        team_board_v2_api,
        'build_published_team_board',
        lambda _team_id: _board(),
    )
    monkeypatch.setattr(
        team_board_v2_api,
        'build_public_team_relief_work_payload',
        lambda _team_id: (_ for _ in ()).throw(RuntimeError('fixture failure')),
    )
    monkeypatch.setattr(
        team_board_v2_api,
        'build_team_game_context',
        lambda _team_id, reference_date=None: _game_context(),
    )
    monkeypatch.setattr(
        team_board_v2_api,
        'build_public_recent_transactions',
        lambda _team_id, reference_date=None: _recent_transactions(),
    )

    response = client.get('/api/bullpen/teams/1/board-v2')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['team_state'] == TEAM_STATE
    assert payload['active_bullpen']['arms'][0]['pitcher_id'] == 7
    assert payload['recent_relief_work']['read'] is None
    assert payload['section_status']['recent_relief_work'] == unavailable_section(
        'recent_relief_work_unavailable'
    )


def test_route_uses_rotation_already_frozen_in_published_board(client, monkeypatch):
    calls = {'board': 0}

    def board(_team_id):
        calls['board'] += 1
        return _board()

    monkeypatch.setattr(team_board_v2_api, 'build_published_team_board', board)
    monkeypatch.setattr(
        team_board_v2_api,
        'build_public_team_relief_work_payload',
        lambda _team_id: _relief_work(),
    )
    monkeypatch.setattr(
        team_board_v2_api,
        'build_team_game_context',
        lambda _team_id, reference_date=None: _game_context(),
    )
    monkeypatch.setattr(
        team_board_v2_api,
        'build_public_recent_transactions',
        lambda _team_id, reference_date=None: _recent_transactions(),
    )

    response = client.get('/api/bullpen/teams/1/board-v2')
    assert response.status_code == 200
    payload = response.get_json()
    assert calls == {'board': 1}
    assert payload['active_bullpen']['arms'][0]['pitcher_id'] == 7
    assert payload['rotation_impact']['read'] == ROTATION


def test_route_scopes_transaction_failure_without_destroying_other_sections(client, monkeypatch):
    monkeypatch.setattr(
        team_board_v2_api,
        'build_published_team_board',
        lambda _team_id: _board(),
    )
    monkeypatch.setattr(
        team_board_v2_api,
        'build_public_team_relief_work_payload',
        lambda _team_id: _relief_work(),
    )
    monkeypatch.setattr(
        team_board_v2_api,
        'build_team_game_context',
        lambda _team_id, reference_date=None: _game_context(),
    )
    monkeypatch.setattr(
        team_board_v2_api,
        'build_public_recent_transactions',
        lambda _team_id, reference_date=None: (_ for _ in ()).throw(RuntimeError('fixture failure')),
    )

    response = client.get('/api/bullpen/teams/1/board-v2')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['active_bullpen']['arms'][0]['pitcher_id'] == 7
    assert payload['rotation_impact']['read'] == ROTATION
    assert payload['section_status']['recent_transactions'] == unavailable_section(
        'recent_transactions_unavailable'
    )


def test_endpoint_is_get_only_and_composition_has_no_write_path():
    root = Path(__file__).resolve().parents[2]
    api_source = (root / 'backend/api/team_board_v2.py').read_text(encoding='utf-8')
    service_source = (root / 'backend/services/team_board_v2.py').read_text(encoding='utf-8')
    transactions_source = (root / 'backend/services/public_recent_transactions.py').read_text(encoding='utf-8')
    app_source = (root / 'backend/app.py').read_text(encoding='utf-8')

    assert "@team_board_v2_bp.route('/teams/<int:team_id>/board-v2', methods=['GET'])" in api_source
    assert 'build_published_team_board(team_id)' in api_source
    assert '_build_team_board' not in api_source
    assert '_rotation_support_for_team' not in api_source
    assert 'from api.team_board_v2 import team_board_v2_bp' in app_source
    assert "app.register_blueprint(team_board_v2_bp, url_prefix='/api/bullpen')" in app_source
    for forbidden in ('db.session', '.commit(', '.add(', '.delete(', 'requests.', 'mlb_client'):
        assert forbidden not in api_source
        assert forbidden not in service_source
        assert forbidden not in transactions_source
