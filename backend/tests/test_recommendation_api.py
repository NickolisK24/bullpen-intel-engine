import pytest

from app import create_app


ROUTE = '/api/recommendations/candidate'
POSITIVE_CATEGORY_CODES = {
    'BEST_AVAILABLE_ARM',
    'FRESHEST_HIGH_LEVERAGE_ARM',
    'LOWEST_CURRENT_WORKLOAD_RISK',
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv('AUTO_SYNC', raising=False)
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
    app = create_app('development')
    return app.test_client()


def candidate_payload(
    pitcher_id=42,
    pitcher_name='Example Pitcher',
    availability_status='Available',
    confidence='high',
    data_state='fresh',
    inputs=None,
):
    return {
        'pitcher_id': pitcher_id,
        'pitcher_name': pitcher_name,
        'team_id': 7,
        'team_name': 'Example Club',
        'availability': {
            'availability_status': availability_status,
            'confidence': confidence,
            'data_state': data_state,
            'inputs': inputs if inputs is not None else {'fatigue_score': 20.0},
            'reasons': ['Trusted availability signal is present.'],
            'limitations': ['Candidate-level output is not a final selection.'],
        },
        'metadata': {
            'data_through': '2026-06-01',
            'last_successful_sync': '2026-06-02T10:00:00Z',
            'latest_sync_status': 'success',
        },
    }


def post_candidate(client, payload=None):
    if payload is None:
        payload = {'candidate': candidate_payload()}
    return client.post(ROUTE, json=payload)


def assigned_codes(payload):
    return {
        category['category_code']
        for category in payload['data']['assigned_categories']
    }


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


class TestRecommendationCandidateApi:
    def test_route_exists(self, client):
        response = post_candidate(client)

        assert response.status_code == 200

    def test_valid_available_candidate_returns_200(self, client):
        response = post_candidate(client)
        payload = response.get_json()

        assert response.status_code == 200
        assert payload['data']['outcome_code'] == 'RECOMMENDATION'
        assert payload['data']['candidate']['pitcher_id'] == 42

    def test_response_includes_recommendation_fields(self, client):
        payload = post_candidate(client).get_json()

        assert payload['data']['category_code'] == 'BEST_AVAILABLE_ARM'
        assert payload['data']['refusal'] is None
        assert payload['data']['alternatives'] == []

    def test_response_includes_explanations(self, client):
        payload = post_candidate(client).get_json()

        assert payload['data']['explanations']

    def test_response_includes_limitations(self, client):
        payload = post_candidate(client).get_json()

        assert payload['data']['limitations']

    def test_response_includes_confidence_freshness_and_availability(self, client):
        payload = post_candidate(client).get_json()

        assert payload['data']['confidence']['level'] == 'high'
        assert payload['data']['freshness']['state'] == 'fresh'
        assert payload['data']['freshness']['data_through'] == '2026-06-01'
        assert payload['data']['availability']['availability_status'] == 'Available'

    def test_response_includes_assigned_and_blocked_categories(self, client):
        payload = post_candidate(client).get_json()

        assert 'BEST_AVAILABLE_ARM' in assigned_codes(payload)
        assert payload['data']['blocked_categories']

    def test_response_includes_no_ranking_marker(self, client):
        payload = post_candidate(client).get_json()

        assert payload['meta']['ranking_applied'] is False

    def test_response_includes_no_selection_marker(self, client):
        payload = post_candidate(client).get_json()

        assert payload['meta']['selection_made'] is False
        assert payload['meta']['selected_pitcher_id'] is None

    def test_missing_body_fails_closed(self, client):
        response = client.post(ROUTE)
        payload = response.get_json()

        assert response.status_code == 400
        assert payload['data']['outcome_code'] == 'REFUSAL'
        assert payload['meta']['ranking_applied'] is False
        assert payload['meta']['selection_made'] is False

    def test_invalid_json_fails_closed(self, client):
        response = client.post(
            ROUTE,
            data='{',
            content_type='application/json',
        )
        payload = response.get_json()

        assert response.status_code == 400
        assert payload['data']['outcome_code'] == 'REFUSAL'
        assert payload['meta']['ranking_applied'] is False

    def test_missing_candidate_fails_closed(self, client):
        response = post_candidate(client, payload={})
        payload = response.get_json()

        assert response.status_code == 200
        assert payload['data']['outcome_code'] == 'REFUSAL'
        assert payload['data']['refusal']['reason_code'] == 'INSUFFICIENT_DATA'

    def test_invalid_candidate_fails_closed(self, client):
        response = post_candidate(client, payload={'candidate': 'invalid'})
        payload = response.get_json()

        assert response.status_code == 200
        assert payload['data']['outcome_code'] == 'REFUSAL'
        assert payload['meta']['refusal_boundary'] == 'invalid_candidate'

    def test_low_confidence_candidate_refuses(self, client):
        response = post_candidate(
            client,
            payload={'candidate': candidate_payload(confidence='low')},
        )
        payload = response.get_json()

        assert response.status_code == 200
        assert payload['data']['outcome_code'] == 'REFUSAL'
        assert payload['data']['refusal']['reason_code'] == 'LOW_CONFIDENCE'
        assert assigned_codes(payload).isdisjoint(POSITIVE_CATEGORY_CODES)

    def test_stale_freshness_candidate_refuses(self, client):
        response = post_candidate(
            client,
            payload={'candidate': candidate_payload(data_state='stale')},
        )
        payload = response.get_json()

        assert response.status_code == 200
        assert payload['data']['outcome_code'] == 'REFUSAL'
        assert payload['data']['refusal']['reason_code'] == 'STALE_DATA'
        assert payload['data']['freshness']['state'] == 'stale'
        assert assigned_codes(payload).isdisjoint(POSITIVE_CATEGORY_CODES)

    def test_unavailable_candidate_refuses_with_avoidance_context(self, client):
        response = post_candidate(
            client,
            payload={
                'candidate': candidate_payload(
                    availability_status='Unavailable',
                    inputs={'pitches_yesterday': 52},
                )
            },
        )
        payload = response.get_json()

        assert response.status_code == 200
        assert payload['data']['outcome_code'] == 'REFUSAL'
        assert 'AVOID_TONIGHT' in assigned_codes(payload)
        assert assigned_codes(payload).isdisjoint(POSITIVE_CATEGORY_CODES)

    def test_multi_candidate_payload_fails_closed(self, client):
        response = post_candidate(
            client,
            payload={
                'candidates': [
                    candidate_payload(pitcher_id=42),
                    candidate_payload(pitcher_id=43),
                ]
            },
        )
        payload = response.get_json()

        assert response.status_code == 200
        assert payload['data']['outcome_code'] == 'REFUSAL'
        assert payload['meta']['refusal_boundary'] == (
            'multi_candidate_ranking_not_implemented'
        )
        assert payload['meta']['ranking_applied'] is False
        assert payload['meta']['selection_made'] is False

    def test_no_ranking_scoring_or_final_selection_fields_are_introduced(self, client):
        payload = post_candidate(client).get_json()
        keys = collect_keys(payload)

        assert 'rank' not in keys
        assert 'score' not in keys
        assert 'comparison' not in keys
        assert 'selected_pitcher' not in keys
        assert 'selected_pitcher_name' not in keys
        assert 'final_selection' not in keys
        assert payload['meta']['selected_pitcher_id'] is None
