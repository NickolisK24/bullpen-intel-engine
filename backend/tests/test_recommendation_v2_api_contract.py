from datetime import date, datetime, timedelta

import pytest
from flask import Flask
from tests.db_config import configure_test_database

import models.prospect  # noqa: F401
from api.recommendations import recommendations_bp
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.sync_run import SyncRun
from recommendation import v2_governance_errors, v2_trust_metadata_errors
from recommendation.v2_assembly import V2ContextAssembly
from services.availability import ACTIVE_WINDOW_DAYS
from utils.db import db


ROUTE = '/api/recommendations/v2/bullpen-state'
V1_ROUTE = '/api/recommendations/candidate'

FORBIDDEN_OUTPUT_KEYS = {
    'rank',
    'ranking',
    'winner',
    'priority',
    'priority_score',
    'score',
    'score_ordering',
    'selected_pitcher',
    'selected_pitcher_id',
    'selected_candidate',
    'selected_candidate_id',
    'recommended_pitcher',
    'recommended_option',
    'preferred_pitcher',
    'preferred_option',
    'use_this_pitcher',
    'best_candidate',
    'best_pitcher',
    'top_candidate',
    'pitcher_choice',
    'prediction',
    'predicted_performance',
    'performance_prediction',
    'injury_prediction',
    'save_prediction',
    'game_prediction',
    'game_outcome_prediction',
}


@pytest.fixture
def client():
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(recommendations_bp, url_prefix='/api/recommendations')
    with app.app_context():
        db.create_all()
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            db.drop_all()


def add_scored_pitcher(
    name,
    *,
    seed=1,
    team_id=7,
    team_name='Example Club',
    team_abbreviation='EX',
    days_since_last_game=3,
    raw_score=20.0,
    log_pitches=8,
    calculated_at=None,
):
    pitcher = Pitcher(
        mlb_id=900000 + seed,
        full_name=name,
        team_id=team_id,
        team_name=team_name,
        team_abbreviation=team_abbreviation,
        active=True,
    )
    db.session.add(pitcher)
    db.session.flush()

    game_date = date.today() - timedelta(days=days_since_last_game)
    db.session.add(
        GameLog(
            pitcher_id=pitcher.id,
            mlb_game_pk=910000 + seed,
            game_date=game_date,
            pitches_thrown=log_pitches,
            innings_pitched=1.0,
            innings_pitched_outs=3,
        )
    )
    db.session.add(
        FatigueScore(
            pitcher_id=pitcher.id,
            calculated_at=calculated_at or datetime(2026, 6, 2, 12, 0, seed),
            raw_score=raw_score,
            pitch_count_score=0.0,
            rest_days_score=0.0,
            appearances_score=0.0,
            innings_score=0.0,
            leverage_score=0.0,
            days_since_last_appearance=days_since_last_game,
            appearances_last_7=1,
            appearances_last_14=1,
            pitches_last_7_days=log_pitches,
            innings_last_7_days=1.0,
            avg_leverage_last_7=1.6 if seed == 1 else None,
            risk_level='LOW',
        )
    )
    db.session.commit()
    return pitcher


def add_successful_sync_run(
    *,
    started_at=datetime(2026, 6, 3, 7, 30, 0),
    completed_at=datetime(2026, 6, 3, 7, 44, 27),
):
    db.session.add(
        SyncRun(
            started_at=started_at,
            completed_at=completed_at,
            status='success',
            source='scheduled',
            latest_game_date=date.today(),
            latest_workload_date=date.today(),
            latest_fatigue_calculated_at=completed_at,
            records_processed=12,
            new_logs_added=6,
            pitchers_updated=2,
            errors=0,
            created_at=started_at,
        )
    )
    db.session.commit()


def v1_candidate_payload():
    return {
        'candidate': {
            'pitcher_id': 42,
            'pitcher_name': 'Example Pitcher',
            'team_id': 7,
            'team_name': 'Example Club',
            'availability': {
                'availability_status': 'Available',
                'confidence': 'high',
                'data_state': 'fresh',
                'inputs': {'fatigue_score': 20.0},
                'reasons': ['Trusted availability signal is present.'],
                'limitations': ['Candidate-level output is not a final selection.'],
            },
            'metadata': {
                'data_through': '2026-06-01',
                'last_successful_sync': '2026-06-02T10:00:00Z',
                'latest_sync_status': 'success',
            },
        }
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


def assert_v2_governance(payload):
    assert payload['ranking_applied'] is False
    assert payload['selection_made'] is False
    assert payload['trust_metadata']['ranking_applied'] is False
    assert payload['trust_metadata']['selection_made'] is False
    assert v2_governance_errors(payload) == []
    assert v2_trust_metadata_errors(payload) == []


class TestRecommendationEngineV2ApiContract:
    def test_successful_v2_api_response_matches_contract_shape(self, client):
        with client.application.app_context():
            add_scored_pitcher('Alpha Arm', seed=1, log_pitches=8)
            add_scored_pitcher('Bravo Arm', seed=2, log_pitches=18)

        response = client.get(f'{ROUTE}?team_id=7')
        payload = response.get_json()
        bullpen_state = payload['bullpen_state']

        assert response.status_code == 200
        assert payload['scope'] == 'bullpen_state'
        assert payload['confidence'] in {'high', 'medium', 'low', 'unknown'}
        assert payload['data_state'] == 'fresh'
        assert payload['freshness']['freshness_state'] == 'fresh'
        assert payload['limitations']
        assert payload['explanations']
        assert payload['refusal_reasons'] == []
        assert payload['fail_closed']['state'] == 'passed'
        assert bullpen_state['status'] in {'stable', 'monitor', 'stress_visible'}
        assert bullpen_state['inventory_summary']
        assert bullpen_state['candidate_groups']
        assert bullpen_state['team_context']['availability_distribution']
        assert bullpen_state['trust']['ranking_applied'] is False
        assert bullpen_state['trust']['selection_made'] is False
        assert_v2_governance(payload)

    def test_candidate_groups_preserve_neutral_ordering(self, client):
        with client.application.app_context():
            add_scored_pitcher('Alpha Arm', seed=1, log_pitches=8)
            add_scored_pitcher('Bravo Arm', seed=2, log_pitches=8)

        payload = client.get(f'{ROUTE}?team_id=7').get_json()
        groups = {
            group['group_id']: group
            for group in payload['bullpen_state']['candidate_groups']
        }
        available_group = groups['availability_available']

        assert available_group['ordering'].endswith('_non_ranking')
        assert [item['display_name'] for item in available_group['candidates']] == [
            'Alpha Arm',
            'Bravo Arm',
        ]
        assert_v2_governance(payload)

    def test_response_contains_no_forbidden_ranking_selection_or_prediction_fields(self, client):
        with client.application.app_context():
            add_scored_pitcher('Alpha Arm', seed=1)

        payload = client.get(f'{ROUTE}?team_id=7').get_json()
        keys = collect_keys(payload)

        assert FORBIDDEN_OUTPUT_KEYS.isdisjoint(keys)
        assert 'ranked_candidates' not in keys
        assert_v2_governance(payload)

    def test_v2_route_avoids_full_internal_context_serialization(self, client, monkeypatch):
        with client.application.app_context():
            add_scored_pitcher('Alpha Arm', seed=1)

        def fail_full_internal_serialization(self):
            raise AssertionError('public V2 route should use lean API serialization')

        monkeypatch.setattr(
            V2ContextAssembly,
            'to_dict',
            fail_full_internal_serialization,
        )

        response = client.get(f'{ROUTE}?team_id=7')
        payload = response.get_json()

        assert response.status_code == 200
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False
        assert payload['bullpen_state']['candidate_groups']
        assert_v2_governance(payload)

    def test_missing_evidence_returns_fail_closed_api_response(self, client):
        response = client.get(f'{ROUTE}?team_id=999')
        payload = response.get_json()

        assert response.status_code == 200
        assert payload['bullpen_state'] is None
        assert payload['fail_closed']['state'] == 'failed_closed'
        assert payload['fail_closed']['critical_failure'] is True
        assert 'missing_inputs' in payload['fail_closed']['reason_codes']
        assert payload['freshness']['missing_data_warning']
        assert payload['limitations']
        assert payload['explanations']
        assert payload['refusal_reasons']
        assert_v2_governance(payload)

    def test_stale_evidence_returns_explicit_refusal_metadata(self, client):
        with client.application.app_context():
            add_successful_sync_run()
            add_scored_pitcher(
                'Stale Arm',
                seed=1,
                days_since_last_game=ACTIVE_WINDOW_DAYS + 5,
            )
            add_scored_pitcher('Fresh Arm', seed=2, days_since_last_game=1)

        payload = client.get(f'{ROUTE}?team_id=7').get_json()

        assert payload['data_state'] == 'stale'
        assert payload['freshness']['freshness_state'] == 'stale'
        assert payload['freshness']['source_freshness_status'] == 'stale'
        assert payload['freshness']['aggregate_v2_freshness_status'] == 'stale'
        assert payload['freshness']['overall_sync_status'] == 'success'
        assert payload['freshness']['overall_sync_current'] is True
        assert payload['freshness']['sync_timestamp'] == '2026-06-03T07:44:27'
        assert payload['fail_closed']['failed_closed'] is True
        assert payload['fail_closed']['state'] == 'degraded'
        assert payload['fail_closed']['critical_failure'] is False
        assert payload['fail_closed']['safe_partial_output_allowed'] is True
        assert payload['fail_closed']['partial_context_safe'] is True
        assert payload['fail_closed']['trust_failed'] is False
        assert payload['fail_closed']['freshness_failed'] is True
        assert payload['fail_closed']['primary_reason_code'] == 'data_state_stale'
        assert 'Source freshness is stale.' in payload['fail_closed']['reason_summary']
        assert 'data_state_stale' in payload['fail_closed']['reason_codes']
        assert payload['status_metadata']['overall_sync_status'] == 'success'
        assert payload['status_metadata']['sync_timestamp'] == '2026-06-03T07:44:27'
        assert payload['status_metadata']['source_freshness_status'] == 'stale'
        assert payload['status_metadata']['aggregate_v2_freshness_status'] == 'stale'
        assert payload['status_metadata']['fail_closed_reason_code'] == 'data_state_stale'
        assert payload['status_metadata']['trust_status'] == 'passed'
        assert payload['status_metadata']['freshness_status'] == 'failed'
        assert payload['status_metadata']['partial_context_safe'] is True
        assert any(
            refusal['reason'] == 'data_state_stale'
            for refusal in payload['refusal_reasons']
        )
        assert payload['bullpen_state'] is not None
        assert_v2_governance(payload)

    def test_unsafe_request_fields_return_fail_closed_api_response(self, client):
        with client.application.app_context():
            add_scored_pitcher('Alpha Arm', seed=1)

        payload = client.get(f'{ROUTE}?team_id=7&rank=1').get_json()

        assert payload['bullpen_state'] is None
        assert payload['fail_closed']['state'] == 'failed_closed'
        assert payload['fail_closed']['critical_failure'] is True
        assert 'governance_unsafe_source_evidence' in (
            payload['fail_closed']['reason_codes']
        )
        assert any(
            refusal['reason'] == 'unsupported_fields'
            for refusal in payload['refusal_reasons']
        )
        assert_v2_governance(payload)

    def test_v1_candidate_api_behavior_remains_unchanged(self, client):
        response = client.post(V1_ROUTE, json=v1_candidate_payload())
        payload = response.get_json()

        assert response.status_code == 200
        assert payload['data']['outcome_code'] == 'RECOMMENDATION'
        assert payload['data']['candidate']['pitcher_id'] == 42
        assert payload['meta']['policy'] == 'recommendation_engine_v1'
        assert payload['meta']['ranking_applied'] is False
        assert payload['meta']['selection_made'] is False
