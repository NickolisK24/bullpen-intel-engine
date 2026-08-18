from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest
from flask import Flask

import api.team_board_v2 as team_board_v2_api
from services.team_board_v2 import (
    ACTIVE_BULLPEN_POPULATION_BASIS,
    CAPABILITY,
    CONTRACT_VERSION,
    RECENT_USAGE_POPULATION_BASIS,
    RECENT_RELIEF_WORK_POPULATION_BASIS,
    ROTATION_IMPACT_POPULATION_BASIS,
    build_team_board_v2_payload,
    unavailable_section,
)


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


def test_contract_pins_version_and_preserves_canonical_owner_outputs():
    board = _board()
    relief = _relief_work()
    context = _game_context()
    originals = deepcopy((board, relief, context))

    payload = build_team_board_v2_payload(
        board,
        recent_relief_work=relief,
        game_context=context,
    )

    assert payload['capability'] == CAPABILITY
    assert payload['contract_version'] == CONTRACT_VERSION
    assert payload['team_state'] == TEAM_STATE
    assert payload['summary'] == TEAM_STATE['summary']
    assert payload['rotation_impact']['read'] == ROTATION
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
    calls = {'board': 0, 'rotation': 0, 'relief': 0, 'game': 0}

    def rotation(team, reference_date):
        calls['rotation'] += 1
        assert team == TEAM
        assert reference_date == date(2026, 8, 16)
        return deepcopy(ROTATION)

    def board(team_id, **kwargs):
        calls['board'] += 1
        assert team_id == 1
        payload = _board(rotation={})
        payload['rotation_support_pressure'] = kwargs['rotation_builder'](
            deepcopy(TEAM), date(2026, 8, 16)
        )
        return payload

    def relief(team_id):
        calls['relief'] += 1
        assert team_id == 1
        return _relief_work()

    def game(team_id, reference_date=None):
        calls['game'] += 1
        assert team_id == 1
        assert reference_date == date(2026, 8, 16)
        return _game_context()

    monkeypatch.setattr(team_board_v2_api, '_build_team_board', board)
    monkeypatch.setattr(team_board_v2_api, '_rotation_support_for_team', rotation)
    monkeypatch.setattr(team_board_v2_api, 'build_public_team_relief_work_payload', relief)
    monkeypatch.setattr(team_board_v2_api, 'build_team_game_context', game)

    response = client.get('/api/bullpen/teams/1/board-v2')
    assert response.status_code == 200
    payload = response.get_json()
    assert calls == {'board': 1, 'rotation': 1, 'relief': 1, 'game': 1}
    assert payload['contract_version'] == CONTRACT_VERSION
    assert payload['summary'] == TEAM_STATE['summary']


def test_route_scopes_optional_failure_without_destroying_core(client, monkeypatch):
    monkeypatch.setattr(
        team_board_v2_api,
        '_build_team_board',
        lambda _team_id, **_kwargs: _board(),
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

    response = client.get('/api/bullpen/teams/1/board-v2')
    assert response.status_code == 200
    payload = response.get_json()
    assert payload['team_state'] == TEAM_STATE
    assert payload['active_bullpen']['arms'][0]['pitcher_id'] == 7
    assert payload['recent_relief_work']['read'] is None
    assert payload['section_status']['recent_relief_work'] == unavailable_section(
        'recent_relief_work_unavailable'
    )


def test_route_scopes_rotation_failure_without_rebuilding_board(client, monkeypatch):
    calls = {'board': 0, 'rotation': 0}

    def rotation(_team, _reference_date):
        calls['rotation'] += 1
        raise RuntimeError('fixture rotation failure')

    def board(_team_id, **kwargs):
        calls['board'] += 1
        payload = _board(rotation={})
        payload['rotation_support_pressure'] = kwargs['rotation_builder'](
            deepcopy(TEAM), date(2026, 8, 16)
        )
        return payload

    monkeypatch.setattr(team_board_v2_api, '_build_team_board', board)
    monkeypatch.setattr(team_board_v2_api, '_rotation_support_for_team', rotation)
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

    response = client.get('/api/bullpen/teams/1/board-v2')
    assert response.status_code == 200
    payload = response.get_json()
    assert calls == {'board': 1, 'rotation': 1}
    assert payload['active_bullpen']['arms'][0]['pitcher_id'] == 7
    assert payload['rotation_impact']['read'] == {}
    assert payload['section_status']['rotation_impact'] == unavailable_section(
        'rotation_impact_unavailable'
    )


def test_endpoint_is_get_only_and_composition_has_no_write_path():
    root = Path(__file__).resolve().parents[2]
    api_source = (root / 'backend/api/team_board_v2.py').read_text(encoding='utf-8')
    service_source = (root / 'backend/services/team_board_v2.py').read_text(encoding='utf-8')
    app_source = (root / 'backend/app.py').read_text(encoding='utf-8')

    assert "@team_board_v2_bp.route('/teams/<int:team_id>/board-v2', methods=['GET'])" in api_source
    assert 'from api.team_board_v2 import team_board_v2_bp' in app_source
    assert "app.register_blueprint(team_board_v2_bp, url_prefix='/api/bullpen')" in app_source
    for forbidden in ('db.session', '.commit(', '.add(', '.delete(', 'requests.', 'mlb_client'):
        assert forbidden not in api_source
        assert forbidden not in service_source
