from datetime import date, datetime, timedelta

import pytest
from flask import Flask

import models.prospect  # noqa: F401
from api.explanations import explanations_bp
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.sync_run import SyncRun
from utils.db import db


AVAILABILITY_ROUTE = '/api/explanations/availability'
TEAM_READINESS_ROUTE = '/api/explanations/team-readiness'

FORBIDDEN_KEYS = {
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
    'recommended_pitcher_id',
    'recommended_option',
    'preferred_pitcher',
    'preferred_option',
    'best_arm',
    'best_candidate',
    'best_pitcher',
    'top_candidate',
    'pitcher_choice',
    'matchup',
    'matchup_advice',
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
    'use this pitcher',
    'best option',
    'preferred arm',
    'recommended arm',
    'matchup advice',
    'choose this bullpen option',
)


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(explanations_bp, url_prefix='/api/explanations')
    with app.app_context():
        db.create_all()
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            db.drop_all()


def add_scored_pitcher(
    name='Alpha Arm',
    *,
    seed=1,
    team_id=7,
    team_name='Example Club',
    team_abbreviation='EX',
    throwing_hand='R',
    days_since_last_game=2,
    raw_score=20.0,
    log_pitches=8,
    calculated_at=datetime(2026, 6, 3, 12, 0, 0),
):
    pitcher = Pitcher(
        mlb_id=990000 + seed,
        full_name=name,
        team_id=team_id,
        team_name=team_name,
        team_abbreviation=team_abbreviation,
        throws=throwing_hand,
        active=True,
    )
    db.session.add(pitcher)
    db.session.flush()

    game_date = date.today() - timedelta(days=days_since_last_game)
    db.session.add(
        GameLog(
            pitcher_id=pitcher.id,
            mlb_game_pk=991000 + seed,
            game_date=game_date,
            pitches_thrown=log_pitches,
            innings_pitched=1.0,
        )
    )
    db.session.add(
        FatigueScore(
            pitcher_id=pitcher.id,
            calculated_at=calculated_at,
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
            avg_leverage_last_7=None,
            risk_level='LOW',
        )
    )
    db.session.commit()
    return pitcher.id


def add_pitcher_without_fatigue(name='Missing Arm', *, seed=100):
    pitcher = Pitcher(
        mlb_id=991000 + seed,
        full_name=name,
        team_id=9,
        team_name='Missing Club',
        team_abbreviation='MS',
        throws='L',
        active=True,
    )
    db.session.add(pitcher)
    db.session.commit()
    return pitcher.id


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


def seed_team_readiness_data():
    add_scored_pitcher('Alpha Arm', seed=1, throwing_hand='L')
    add_scored_pitcher('Bravo Arm', seed=2, throwing_hand='R')
    add_successful_sync_run()


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
    strings = []
    if isinstance(value, dict):
        for key, item in value.items():
            strings.append(str(key))
            strings.extend(collect_strings(item))
    elif isinstance(value, list):
        for item in value:
            strings.extend(collect_strings(item))
    elif isinstance(value, str):
        strings.append(value)
    return strings


def assert_envelope_governance(payload):
    governance = payload['governance']

    assert governance['ranking_applied'] is False
    assert governance['selection_made'] is False
    assert governance['recommendation_made'] is False
    assert governance['prediction_made'] is False
    assert governance['decision_scope'] == 'explanation_only'
    assert governance['advice_scope'] == 'none'

    if payload.get('explanation'):
        assert payload['explanation']['governance'] == governance


def assert_no_prohibited_behavior(payload):
    keys = collect_keys(payload)
    strings = ' '.join(collect_strings(payload)).lower()

    assert not (FORBIDDEN_KEYS & keys)
    for text in FORBIDDEN_TEXT:
        assert text not in strings


class TestV4ExplanationApiRoutes:
    def test_availability_route_returns_governed_explanation(self, client):
        with client.application.app_context():
            pitcher_id = add_scored_pitcher()

        response = client.get(f'{AVAILABILITY_ROUTE}/{pitcher_id}')
        payload = response.get_json()

        assert response.status_code == 200
        assert payload['status'] == 'ok'
        assert payload['explanation_type'] == 'availability_explanation'
        assert payload['certification_status'] == 'certified_with_non_blocking_observations'
        assert payload['route_status'] == 'internal_uncertified_route'
        assert payload['explanation']['scope'] == 'availability_state'
        assert payload['explanation']['subject_type'] == 'pitcher'
        assert payload['explanation']['subject_id'] == str(pitcher_id)
        assert_envelope_governance(payload)
        assert_no_prohibited_behavior(payload)

    def test_availability_unknown_pitcher_fails_closed(self, client):
        response = client.get(f'{AVAILABILITY_ROUTE}/999999')
        payload = response.get_json()

        assert response.status_code == 404
        assert payload['status'] == 'unavailable'
        assert payload['explanation_type'] == 'availability_explanation'
        assert payload['explanation'] is None
        assert payload['refusal']['reason_code'] == 'unknown_subject'
        assert_envelope_governance(payload)
        assert_no_prohibited_behavior(payload)

    def test_availability_missing_data_fails_closed(self, client):
        with client.application.app_context():
            pitcher_id = add_pitcher_without_fatigue()

        response = client.get(f'{AVAILABILITY_ROUTE}/{pitcher_id}')
        payload = response.get_json()

        assert response.status_code == 503
        assert payload['status'] == 'unavailable'
        assert payload['explanation'] is None
        assert payload['refusal']['reason_code'] == 'missing_source_data'
        assert_envelope_governance(payload)
        assert_no_prohibited_behavior(payload)

    def test_availability_route_refuses_prohibited_query_intent(self, client):
        with client.application.app_context():
            pitcher_id = add_scored_pitcher()

        response = client.get(f'{AVAILABILITY_ROUTE}/{pitcher_id}?rank=true')
        payload = response.get_json()

        assert response.status_code == 400
        assert payload['status'] == 'unavailable'
        assert payload['refusal']['reason_code'] == 'forbidden_request_parameter'
        assert_envelope_governance(payload)
        assert_no_prohibited_behavior(payload)

    def test_team_readiness_route_returns_governed_explanation(self, client):
        with client.application.app_context():
            seed_team_readiness_data()

        response = client.get(f'{TEAM_READINESS_ROUTE}?team_id=7')
        payload = response.get_json()

        assert response.status_code == 200
        assert payload['status'] == 'ok'
        assert payload['explanation_type'] == 'team_readiness_explanation'
        assert payload['route_status'] == 'internal_uncertified_route'
        assert payload['explanation']['scope'] == 'readiness_state'
        assert payload['explanation']['subject_type'] == 'bullpen'
        assert_envelope_governance(payload)
        assert_no_prohibited_behavior(payload)

    def test_team_readiness_certified_scope_route_returns_governed_explanation(self, client):
        with client.application.app_context():
            seed_team_readiness_data()

        response = client.get(f'{TEAM_READINESS_ROUTE}/workload_state?team_id=7')
        payload = response.get_json()

        assert response.status_code == 200
        assert payload['status'] == 'ok'
        assert payload['explanation_type'] == 'team_readiness_explanation'
        assert payload['explanation']['scope'] == 'workload_state'
        assert_envelope_governance(payload)
        assert_no_prohibited_behavior(payload)

    def test_team_readiness_unsupported_scope_fails_closed(self, client):
        with client.application.app_context():
            seed_team_readiness_data()

        response = client.get(f'{TEAM_READINESS_ROUTE}/risk_distribution?team_id=7')
        payload = response.get_json()

        assert response.status_code == 422
        assert payload['status'] == 'unavailable'
        assert payload['explanation_type'] == 'team_readiness_explanation'
        assert payload['explanation'] is None
        assert payload['refusal']['reason_code'] == 'unsupported_scope'
        assert_envelope_governance(payload)
        assert_no_prohibited_behavior(payload)

    def test_team_readiness_route_fails_closed_on_missing_records(self, client):
        response = client.get(f'{TEAM_READINESS_ROUTE}?team_id=404')
        payload = response.get_json()

        assert response.status_code == 503
        assert payload['status'] == 'unavailable'
        assert payload['explanation'] is None
        assert payload['refusal']['reason_code'] == 'missing_source_data'
        assert_envelope_governance(payload)
        assert_no_prohibited_behavior(payload)

    def test_team_readiness_route_refuses_prohibited_query_intent(self, client):
        with client.application.app_context():
            seed_team_readiness_data()

        response = client.get(f'{TEAM_READINESS_ROUTE}?team_id=7&matchup=true')
        payload = response.get_json()

        assert response.status_code == 400
        assert payload['status'] == 'unavailable'
        assert payload['refusal']['reason_code'] == 'forbidden_request_parameter'
        assert_envelope_governance(payload)
        assert_no_prohibited_behavior(payload)

    def test_uncertified_explanation_type_fails_closed(self, client):
        response = client.get('/api/explanations/recommendation')
        payload = response.get_json()

        assert response.status_code == 403
        assert payload['status'] == 'unavailable'
        assert payload['explanation_type'] == 'recommendation'
        assert payload['certification_status'] == 'uncertified'
        assert payload['refusal']['reason_code'] == 'uncertified_explanation_type'
        assert_envelope_governance(payload)
        assert_no_prohibited_behavior(payload)

    def test_repeated_route_calls_are_deterministic(self, client):
        with client.application.app_context():
            pitcher_id = add_scored_pitcher()

        first = client.get(f'{AVAILABILITY_ROUTE}/{pitcher_id}').get_json()
        second = client.get(f'{AVAILABILITY_ROUTE}/{pitcher_id}').get_json()

        assert first == second
        assert first['explanation']['explanation_id'] == second['explanation']['explanation_id']
        assert_envelope_governance(first)
        assert_no_prohibited_behavior(first)
