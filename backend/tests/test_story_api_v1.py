from copy import deepcopy
from datetime import date

import pytest
from flask import Flask

import api.bullpen as bullpen_api
from api.bullpen import bullpen_bp
from services.story_four_beat_interpreter_v1 import BEAT_SUSTAINABILITY_QUESTION
from services.story_observation_engine import TYPE_CONCENTRATION_PRESSURE


ROUTE = '/api/bullpen/teams/118/story'

EXPECTED_KEYS = {
    'capability',
    'contract',
    'contract_state',
    'team_id',
    'team_name',
    'team_abbreviation',
    'as_of_date',
    'state',
    'story_available',
    'neutral_reason',
    'story_type',
    'headline',
    'observation',
    'baseline',
    'cause',
    'constraint',
    'freshness',
    'trust_metadata',
    'supporting_context',
    'selected_observation',
    'construction_frame',
    'limitations',
}


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    return app.test_client()


def service_payload(**overrides):
    payload = {
        'capability': 'story_intelligence_service_v1',
        'team_id': 118,
        'team_name': 'Kansas City Royals',
        'team_abbreviation': 'KC',
        'as_of_date': '2026-06-20',
        'state': 'story_available',
        'story_available': True,
        'neutral_reason': None,
        'selected_observation': {
            'type': TYPE_CONCENTRATION_PRESSURE,
            'severity': 'high',
            'headline_inputs': {'top_three_workload_share_10d': 94.0},
        },
        'construction_frame': {
            'observation_type': TYPE_CONCENTRATION_PRESSURE,
            'construction_confidence': 'high',
            'story_frame': {
                'headline_facts': {'top_three_workload_share_10d': 94.0},
                'observation_facts': {},
                'baseline_facts': {},
                'cause_facts': {},
                'interpretation_facts': {},
                'constraint_facts': {},
            },
        },
        'written_story': {
            'headline': "Kansas City Royals' bullpen is running through First Arm, Second Arm, and Third Arm",
            'observation_paragraph': 'The top group has handled 94% of the bullpen workload.',
            'baseline_paragraph': 'The league comparison is 58% for top-three bullpen workload.',
            'cause_paragraph': 'The optionality layer shows 3 practical close-game paths.',
            'constraint_paragraph': 'If the game shape repeats, the structural constraint remains the same core: First Arm, Second Arm, and Third Arm.',
        },
        'freshness': {
            'as_of_date': '2026-06-20',
            'data_through': '2026-06-20',
            'data_through_date': '2026-06-20',
            'limitations': [],
        },
        'trust_metadata': {
            'service_resolution': 'deterministic_first_valid_observation',
            'external_generation_used': False,
            'new_metrics_created': False,
            'context_formula_changes': False,
            'availability_changes': False,
            'fatigue_changes': False,
            'public_ui_added': False,
        },
        'supporting_context': {
            'rotation_context': {},
            'bullpen_concentration_context': {},
            'bullpen_optionality_context': {},
            'role_stability_context': {},
            'injury_context': {},
        },
        'limitations': [],
    }
    payload.update(overrides)
    return payload


def neutral_payload():
    payload = service_payload()
    payload.update({
        'state': 'neutral',
        'story_available': False,
        'neutral_reason': 'no_story_observations',
        'selected_observation': None,
        'construction_frame': None,
        'written_story': None,
        'limitations': ['no_story_observations'],
    })
    return payload


def test_story_route_returns_valid_story_contract(client, monkeypatch):
    calls = []

    def fake_build(team_id, as_of_date=None):
        calls.append((team_id, as_of_date))
        return service_payload()

    monkeypatch.setattr(bullpen_api, 'build_story_intelligence_team_story', fake_build)

    response = client.get(f'{ROUTE}?as_of_date=2026-06-20')
    body = response.get_json()

    assert response.status_code == 200
    assert calls == [(118, date(2026, 6, 20))]
    assert set(body) == EXPECTED_KEYS
    assert body['capability'] == 'story_intelligence_api_v1'
    assert body['contract_state'] == 'available'
    assert body['story_available'] is True
    assert body['story_type'] == BEAT_SUSTAINABILITY_QUESTION
    assert body['story_type'] != TYPE_CONCENTRATION_PRESSURE
    assert body['headline'].startswith('Kansas City Royals')
    assert body['observation'] == 'The top group has handled 94% of the bullpen workload.'
    assert body['freshness']['data_through'] == '2026-06-20'
    assert body['trust_metadata']['external_generation_used'] is False
    assert body['supporting_context']['rotation_context'] == {}


def test_story_route_returns_neutral_state_without_error(client, monkeypatch):
    monkeypatch.setattr(
        bullpen_api,
        'build_story_intelligence_team_story',
        lambda team_id, as_of_date=None: neutral_payload(),
    )

    response = client.get(ROUTE)
    body = response.get_json()

    assert response.status_code == 200
    assert set(body) == EXPECTED_KEYS
    assert body['contract_state'] == 'neutral'
    assert body['story_available'] is False
    assert body['neutral_reason'] == 'no_story_observations'
    assert body['story_type'] is None
    assert body['headline'] is None
    assert body['observation'] is None
    assert body['baseline'] is None
    assert body['cause'] is None
    assert body['constraint'] is None
    assert body['limitations'] == ['no_story_observations']


def test_story_route_rejects_malformed_as_of_date_before_service_call(client, monkeypatch):
    def fail_if_called(team_id, as_of_date=None):
        raise AssertionError('service should not be called')

    monkeypatch.setattr(bullpen_api, 'build_story_intelligence_team_story', fail_if_called)

    response = client.get(f'{ROUTE}?as_of_date=not-a-date')
    body = response.get_json()

    assert response.status_code == 400
    assert body['status'] == 'error'
    assert body['reason_code'] == 'invalid_query_parameter'
    assert body['parameter'] == 'as_of_date'


def test_story_route_rejects_invalid_team_id_before_service_call(client, monkeypatch):
    def fail_if_called(team_id, as_of_date=None):
        raise AssertionError('service should not be called')

    monkeypatch.setattr(bullpen_api, 'build_story_intelligence_team_story', fail_if_called)

    response = client.get('/api/bullpen/teams/0/story')
    body = response.get_json()

    assert response.status_code == 400
    assert body['status'] == 'error'
    assert body['reason_code'] == 'invalid_query_parameter'
    assert body['parameter'] == 'team_id'


def test_story_route_schema_is_stable_for_missing_optional_story_sections(client, monkeypatch):
    payload = service_payload()
    payload['written_story'] = deepcopy(payload['written_story'])
    payload['written_story']['baseline_paragraph'] = None
    payload['written_story']['cause_paragraph'] = None
    monkeypatch.setattr(
        bullpen_api,
        'build_story_intelligence_team_story',
        lambda team_id, as_of_date=None: payload,
    )

    response = client.get(ROUTE)
    body = response.get_json()

    assert response.status_code == 200
    assert set(body) == EXPECTED_KEYS
    assert body['baseline'] is None
    assert body['cause'] is None
    assert body['constraint'] is not None
    assert body['story_type'] == BEAT_SUSTAINABILITY_QUESTION
    assert body['selected_observation']['type'] == TYPE_CONCENTRATION_PRESSURE
    assert body['construction_frame']['observation_type'] == TYPE_CONCENTRATION_PRESSURE
