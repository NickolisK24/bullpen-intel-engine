import inspect

import pytest
from flask import Flask

from api.observations import observations_bp
from observations import observation_governance_errors


ROUTE = '/api/observations'
PREVIEW_ROUTE = '/api/observations/preview'

ALLOWED_GOVERNANCE_KEYS = {'ranking_applied', 'selection_made'}
FORBIDDEN_OUTPUT_KEYS = {
    'rank',
    'ranking',
    'winner',
    'priority',
    'priority_score',
    'score_ordering',
    'selected_pitcher',
    'selected_pitcher_id',
    'selected_candidate',
    'selected_candidate_id',
    'recommended_pitcher',
    'recommended_pitcher_id',
    'recommended_option',
    'preferred_pitcher',
    'preferred_option',
    'use_this_pitcher',
    'best_arm',
    'best_candidate',
    'best_pitcher',
    'top_candidate',
    'top_option',
    'pitcher_choice',
    'matchup',
    'matchup_advice',
    'matchup_advantage',
    'prediction',
    'predicted_performance',
    'performance_prediction',
    'performance_forecast',
    'predicted_injury',
    'injury_prediction',
    'predicted_saves',
    'save_prediction',
    'game_prediction',
    'game_outcome_prediction',
    'outcome_prediction',
    'projected_outcome',
    'projected_performance',
    'hidden_priority_ordering',
}
FORBIDDEN_TEXT = (
    'use pitcher',
    'best option',
    'manager should',
    'matchup advantage',
    'should close',
)


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(observations_bp, url_prefix='/api/observations')
    return app.test_client()


def supplied_state(**overrides):
    state = {
        'observation_id': 'inventory:preview:2026-06-04',
        'evidence': [
            {
                'evidence_id': 'inventory:preview-evidence:2026-06-04',
                'source': 'test_supplied_state',
                'source_type': 'trusted_platform_state',
                'label': 'Available inventory count',
                'value': 5,
                'freshness_status': 'current',
                'data_through': '2026-06-04',
                'generated_at': '2026-06-04T18:00:00Z',
                'metadata': {'field': 'available_count'},
            }
        ],
        'limitations': [
            {
                'limitation_type': 'public_workload_data_only',
                'summary': 'Observation is limited to supplied public workload state.',
                'source': 'governance_boundary',
            }
        ],
        'confidence': {
            'status': 'medium',
            'reason': 'Supplied state is sufficient for preview validation.',
        },
        'freshness': {
            'status': 'current',
            'data_through': '2026-06-04',
            'generated_at': '2026-06-04T18:00:00Z',
        },
        'trust_status': 'supported',
        'generated_at': '2026-06-04T18:00:00Z',
    }
    state.update(overrides)
    return state


def collect_keys(value):
    keys = set()
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(key)
            keys.update(collect_keys(item))
    elif isinstance(value, list):
        for item in value:
            keys.update(collect_keys(item))
    return keys


def collect_strings(value):
    values = []
    if isinstance(value, dict):
        for key, item in value.items():
            values.append(str(key))
            values.extend(collect_strings(item))
    elif isinstance(value, list):
        for item in value:
            values.extend(collect_strings(item))
    elif isinstance(value, str):
        values.append(value)
    return values


def governance_flag_values(payload):
    values = []
    if isinstance(payload, dict):
        if 'ranking_applied' in payload:
            values.append(payload['ranking_applied'])
        if 'selection_made' in payload:
            values.append(payload['selection_made'])
        for value in payload.values():
            values.extend(governance_flag_values(value))
    elif isinstance(payload, list):
        for value in payload:
            values.extend(governance_flag_values(value))
    return values


def assert_governed_payload(payload):
    assert payload['ranking_applied'] is False
    assert payload['selection_made'] is False
    assert all(value is False for value in governance_flag_values(payload))
    assert observation_governance_errors(payload) == []


def assert_no_prohibited_output(payload):
    keys = collect_keys(payload).difference(ALLOWED_GOVERNANCE_KEYS)
    text = ' '.join(collect_strings(payload)).lower()

    assert FORBIDDEN_OUTPUT_KEYS.isdisjoint(keys)
    for phrase in FORBIDDEN_TEXT:
        assert phrase not in text


class TestObservationApi:
    def test_application_factory_registers_observation_routes(self):
        from app import create_app

        app = create_app('development')
        routes = {str(rule) for rule in app.url_map.iter_rules()}

        assert ROUTE in routes
        assert f'{ROUTE}/' in routes
        assert PREVIEW_ROUTE in routes

    def test_api_returns_governed_observation_collection(self, client):
        response = client.get(ROUTE)
        payload = response.get_json()

        assert response.status_code == 200
        assert payload['status'] == 'ok'
        assert payload['collection_id'] == 'bullpen-observations:deterministic-sample'
        assert payload['observation_count'] == 5
        assert payload['trust_status'] == 'supported'
        assert payload['freshness']['status'] == 'current'
        assert payload['confidence']['status'] == 'medium'
        assert payload['limitations']
        assert payload['route_metadata']['route'] == ROUTE
        assert payload['route_metadata']['read_only'] is True
        assert payload['route_metadata']['frontend_exposure'] is False
        assert payload['route_metadata']['database_required'] is False
        assert payload['route_metadata']['live_runtime_integration'] is False
        assert_governed_payload(payload)
        assert_no_prohibited_output(payload)

    def test_each_observation_preserves_governance_flags_and_contract_fields(self, client):
        payload = client.get(ROUTE).get_json()
        observed_types = [
            observation['observation_type']
            for observation in payload['observations']
        ]

        assert observed_types == [
            'inventory',
            'readiness',
            'workload_pressure',
            'freshness',
            'trust',
        ]
        for observation in payload['observations']:
            assert observation['ranking_applied'] is False
            assert observation['selection_made'] is False
            assert observation['observation_id']
            assert observation['family'] == observation['observation_type']
            assert observation['severity']
            assert observation['title']
            assert observation['summary']
            assert observation['evidence']
            assert observation['limitations']
            assert observation['confidence']
            assert observation['freshness']
            assert observation['trust_status']
            assert observation['explanation_reference']
        assert_governed_payload(payload)

    def test_response_serializes_evidence_limitations_trust_freshness_and_confidence(self, client):
        payload = client.get(ROUTE).get_json()
        observation = payload['observations'][0]

        assert observation['evidence'][0]['source_type'] == 'trusted_platform_state'
        assert observation['limitations'][0]['limitation_type']
        assert observation['trust_status'] == 'supported'
        assert observation['freshness']['data_through'] == '2026-06-04'
        assert observation['confidence']['status'] == 'medium'
        assert payload['trust_status'] == 'supported'
        assert payload['freshness']['data_through'] == '2026-06-04'
        assert payload['confidence']['status'] == 'medium'
        assert_governed_payload(payload)

    def test_preview_route_returns_supplied_state_observation_collection(self, client):
        response = client.post(
            PREVIEW_ROUTE,
            json={'states': {'inventory': supplied_state()}},
        )
        payload = response.get_json()

        assert response.status_code == 200
        assert payload['status'] == 'ok'
        assert payload['route_metadata']['source_mode'] == 'supplied_preview_state'
        assert payload['observation_count'] == 1
        assert payload['observations'][0]['observation_type'] == 'inventory'
        assert_governed_payload(payload)
        assert_no_prohibited_output(payload)

    def test_prohibited_language_cannot_be_returned(self, client):
        response = client.post(
            PREVIEW_ROUTE,
            json={
                'states': {
                    'inventory': supplied_state(title='Use Pitcher X.')
                }
            },
        )
        payload = response.get_json()

        assert response.status_code == 400
        assert payload['status'] == 'fail_closed'
        assert payload['observation_count'] == 0
        assert payload['observations'] == []
        assert payload['trust_status'] == 'fail_closed'
        assert payload['suppression_reasons'] == ['invalid_supplied_state']
        assert 'Use Pitcher X.' not in ' '.join(collect_strings(payload))
        assert_governed_payload(payload)
        assert_no_prohibited_output(payload)

    def test_invalid_or_incomplete_supplied_state_fails_closed(self, client):
        incomplete_state = supplied_state()
        incomplete_state.pop('evidence')

        response = client.post(
            PREVIEW_ROUTE,
            json={'states': {'inventory': incomplete_state}},
        )
        payload = response.get_json()

        assert response.status_code == 400
        assert payload['status'] == 'fail_closed'
        assert payload['observation_count'] == 0
        assert payload['limitations']
        assert payload['freshness']['status'] == 'unavailable'
        assert payload['confidence']['status'] == 'low'
        assert_governed_payload(payload)
        assert_no_prohibited_output(payload)

    def test_prohibited_query_parameters_fail_closed(self, client):
        response = client.get(f'{ROUTE}?rank=true')
        payload = response.get_json()

        assert response.status_code == 400
        assert payload['status'] == 'fail_closed'
        assert payload['observation_count'] == 0
        assert payload['suppression_reasons'] == ['forbidden_request_parameter']
        assert_governed_payload(payload)
        assert_no_prohibited_output(payload)

    def test_route_does_not_require_database_access(self, client):
        response = client.get(ROUTE)

        assert response.status_code == 200
        assert response.get_json()['route_metadata']['database_required'] is False

    def test_route_does_not_call_external_services(self):
        import api.observations as route_module
        import observations.api_assembly as assembly_module

        source = inspect.getsource(route_module) + inspect.getsource(assembly_module)

        assert 'requests.' not in source
        assert 'httpx' not in source
        assert 'urllib' not in source
        assert 'sqlalchemy' not in source
        assert 'db.session' not in source
        assert 'latest_fatigue_rows' not in source
