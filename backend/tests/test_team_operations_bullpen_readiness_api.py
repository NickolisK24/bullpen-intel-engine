from datetime import date, datetime, timedelta

import pytest
from flask import Flask
from tests.db_config import configure_test_database

import models.prospect  # noqa: F401
from api.team_operations import team_operations_bp
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.sync_run import SyncRun
from team_operations import team_operations_governance_errors
from utils.db import db


ROUTE = '/api/team-operations/bullpen-readiness'

FORBIDDEN_RANKING_KEYS = {
    'rank',
    'ranking',
    'winner',
    'priority',
    'priority_score',
    'score',
    'score_ordering',
}

FORBIDDEN_SELECTION_KEYS = {
    'selected_pitcher',
    'selected_pitcher_id',
    'selected_candidate',
    'selected_candidate_id',
    'pitcher_choice',
    'use_this_pitcher',
}

FORBIDDEN_DECISION_LABEL_KEYS = {
    'recommended_pitcher',
    'recommended_pitcher_id',
    'recommended_option',
    'preferred_pitcher',
    'preferred_option',
    'best_candidate',
    'best_pitcher',
    'top_candidate',
}

FORBIDDEN_LABEL_TEXT = ('best', 'preferred', 'recommended')
ALLOWED_GOVERNANCE_KEYS = {'ranking_applied', 'selection_made'}


@pytest.fixture
def client():
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(team_operations_bp, url_prefix='/api/team-operations')
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
    throwing_hand='R',
    days_since_last_game=3,
    raw_score=20.0,
    log_pitches=8,
    calculated_at=None,
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
            innings_pitched_outs=3,
        )
    )
    db.session.add(
        FatigueScore(
            pitcher_id=pitcher.id,
            calculated_at=calculated_at or datetime(2026, 6, 3, 12, 0, seed),
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


def seed_route_data():
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
    assert payload['trust_metadata']['ranking_applied'] is False
    assert payload['trust_metadata']['selection_made'] is False
    assert all(value is False for value in governance_flag_values(payload))
    assert team_operations_governance_errors(payload) == []


class TestTeamOperationsBullpenReadinessApi:
    def test_route_exists_and_returns_governed_payload(self, client):
        with client.application.app_context():
            seed_route_data()

        response = client.get(f'{ROUTE}?team_id=7')
        payload = response.get_json()

        assert response.status_code == 200
        assert payload['capability'] == 'team_operations_bullpen_readiness'
        assert payload['contract'] == 'team_operations_bullpen_readiness_api_contract'
        assert payload['contract_state'] == 'available'
        assert payload['team']['team_id'] == 7
        assert payload['availability_distribution']['total'] == 2
        assert payload['readiness']['status_code'] in {
            'operationally_stable',
            'operationally_constrained',
            'operationally_stressed',
            'data_limited',
        }
        assert_governed_payload(payload)

    def test_route_is_marked_internal_non_production_and_uncertified(self, client):
        with client.application.app_context():
            seed_route_data()

        payload = client.get(f'{ROUTE}?team_id=7').get_json()
        route_metadata = payload['route_metadata']

        assert route_metadata['route'] == ROUTE
        assert route_metadata['exposure'] == 'internal'
        assert route_metadata['production_status'] == 'non_production'
        assert route_metadata['certification_status'] == 'uncertified'
        assert route_metadata['public_certified'] is False
        assert route_metadata['frontend_exposure'] is False
        assert_governed_payload(payload)

    def test_governance_flags_are_always_false_for_refusal(self, client):
        response = client.get(f'{ROUTE}?team_id=7&rank=true')
        payload = response.get_json()

        assert response.status_code == 400
        assert payload['contract_state'] == 'refused'
        assert payload['refusal']['refused'] is True
        assert payload['refusal']['reason'] == 'forbidden_request_parameter'
        assert payload['fail_closed']['failed_closed'] is True
        assert_governed_payload(payload)

    def test_prohibited_query_parameters_are_refused(self, client):
        with client.application.app_context():
            seed_route_data()

        response = client.get(f'{ROUTE}?matchup=true')
        payload = response.get_json()

        assert response.status_code == 400
        assert payload['contract_state'] == 'refused'
        assert payload['readiness']['status_code'] == 'refused'
        assert payload['refusal']['reason'] == 'forbidden_request_parameter'
        assert payload['fail_closed']['critical_failure'] is True
        assert_governed_payload(payload)

    def test_unsupported_query_parameters_are_refused(self, client):
        with client.application.app_context():
            seed_route_data()

        response = client.get(f'{ROUTE}?mode=debug')
        payload = response.get_json()

        assert response.status_code == 400
        assert payload['contract_state'] == 'refused'
        assert payload['refusal']['reason'] == 'unsupported_request_parameter'
        assert_governed_payload(payload)

    def test_missing_required_freshness_inputs_fail_closed(self, client, monkeypatch):
        with client.application.app_context():
            seed_route_data()

        import api.team_operations as route_module

        monkeypatch.setattr(
            route_module,
            '_team_operations_freshness_metadata',
            lambda *args, **kwargs: None,
        )

        response = client.get(f'{ROUTE}?team_id=7')
        payload = response.get_json()

        assert response.status_code == 503
        assert payload['contract_state'] == 'refused'
        assert payload['refusal']['reason'] == 'freshness_metadata_missing'
        assert payload['fail_closed']['failed_closed'] is True
        assert_governed_payload(payload)

    def test_missing_required_trust_inputs_fail_closed(self, client, monkeypatch):
        with client.application.app_context():
            seed_route_data()

        import api.team_operations as route_module

        monkeypatch.setattr(
            route_module,
            '_team_operations_trust_metadata',
            lambda *args, **kwargs: None,
        )

        response = client.get(f'{ROUTE}?team_id=7')
        payload = response.get_json()

        assert response.status_code == 503
        assert payload['contract_state'] == 'refused'
        assert payload['refusal']['reason'] == 'trust_metadata_missing'
        assert payload['fail_closed']['failed_closed'] is True
        assert_governed_payload(payload)

    def test_response_contains_no_ranking_fields(self, client):
        with client.application.app_context():
            seed_route_data()

        payload = client.get(f'{ROUTE}?team_id=7').get_json()
        keys = collect_keys(payload).difference(ALLOWED_GOVERNANCE_KEYS)

        assert FORBIDDEN_RANKING_KEYS.isdisjoint(keys)
        assert_governed_payload(payload)

    def test_response_contains_no_selection_fields(self, client):
        with client.application.app_context():
            seed_route_data()

        payload = client.get(f'{ROUTE}?team_id=7').get_json()
        keys = collect_keys(payload).difference(ALLOWED_GOVERNANCE_KEYS)

        assert FORBIDDEN_SELECTION_KEYS.isdisjoint(keys)
        assert_governed_payload(payload)

    def test_response_contains_no_decision_labels(self, client):
        with client.application.app_context():
            seed_route_data()

        payload = client.get(f'{ROUTE}?team_id=7').get_json()
        keys = collect_keys(payload).difference(ALLOWED_GOVERNANCE_KEYS)
        text = ' '.join(collect_strings(payload)).lower()

        assert FORBIDDEN_DECISION_LABEL_KEYS.isdisjoint(keys)
        assert all(label not in text for label in FORBIDDEN_LABEL_TEXT)
        assert_governed_payload(payload)
