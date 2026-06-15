from datetime import date, timedelta

import pytest
from flask import Flask
from werkzeug.datastructures import MultiDict

from api.bullpen import bullpen_bp
from api.pitchers import pitchers_bp
from api.prospects import prospects_bp
from api.query_params import (
    parse_non_negative_int_param,
    parse_positive_int_param,
)
from api.recommendations import recommendations_bp
from api.team_operations import team_operations_bp
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.prospect import Prospect
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db
from utils.time import utc_now_naive


@pytest.fixture
def client():
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    app.register_blueprint(prospects_bp, url_prefix='/api/prospects')
    app.register_blueprint(pitchers_bp, url_prefix='/api/pitchers')
    app.register_blueprint(recommendations_bp, url_prefix='/api/recommendations')
    app.register_blueprint(team_operations_bp, url_prefix='/api/team-operations')
    with app.app_context():
        create_test_schema(app)
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            drop_test_schema(app)


def _seed_scored_pitcher(name='Craig Kimbrel', mlb_id=518886, raw_score=72.0):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=139,
        team_name='Tampa Bay Rays',
        team_abbreviation='TB',
        active=True,
    )
    db.session.add(pitcher)
    db.session.commit()
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=mlb_id * 10,
        game_date=date.today() - timedelta(days=1),
        pitches_thrown=12,
        innings_pitched=1.0,
        innings_pitched_outs=3,
    ))
    db.session.add(FatigueScore(
        pitcher_id=pitcher.id,
        calculated_at=utc_now_naive(),
        raw_score=raw_score,
        pitch_count_score=10.0,
        rest_days_score=10.0,
        appearances_score=10.0,
        innings_score=10.0,
        days_since_last_appearance=1,
        appearances_last_7=1,
        appearances_last_14=1,
        pitches_last_7_days=12,
        innings_last_7_days=1.0,
        risk_level='HIGH',
    ))
    db.session.commit()
    return pitcher


def _seed_prospect(name='Test Prospect', mlb_id=900001, grade=60):
    prospect = Prospect(
        mlb_id=mlb_id,
        full_name=name,
        team_id=139,
        team_name='Tampa Bay Rays',
        team_abbreviation='TB',
        position='P',
        current_level='AAA',
        overall_grade=grade,
        active=True,
    )
    db.session.add(prospect)
    db.session.commit()
    return prospect


def assert_invalid_param(response, parameter):
    assert response.status_code == 400
    body = response.get_json()
    assert body['status'] == 'error'
    assert body['reason_code'] == 'invalid_query_parameter'
    assert body['parameter'] == parameter
    assert body['message']


@pytest.mark.parametrize('value', ['-1', '0', 'abc'])
def test_bullpen_fatigue_rejects_invalid_limit_before_query(client, value):
    response = client.get(f'/api/bullpen/fatigue?limit={value}')

    assert_invalid_param(response, 'limit')


def test_bullpen_fatigue_clamps_over_max_limit_and_preserves_valid_results(client):
    with client.application.app_context():
        _seed_scored_pitcher(name='Pitcher One', mlb_id=100001, raw_score=80.0)
        _seed_scored_pitcher(name='Pitcher Two', mlb_id=100002, raw_score=70.0)

    clamped = client.get('/api/bullpen/fatigue?limit=999999&include_stale=true')
    limited = client.get('/api/bullpen/fatigue?limit=1&include_stale=true')

    assert clamped.status_code == 200
    assert len(clamped.get_json()) == 2
    assert limited.status_code == 200
    assert len(limited.get_json()) == 1


@pytest.mark.parametrize('value', ['-1', '0', 'abc'])
def test_prospects_rejects_invalid_limit_before_query(client, value):
    response = client.get(f'/api/prospects/?limit={value}')

    assert_invalid_param(response, 'limit')


def test_prospects_clamps_over_max_limit_and_preserves_valid_results(client):
    with client.application.app_context():
        _seed_prospect(name='Prospect One', mlb_id=200001, grade=65)
        _seed_prospect(name='Prospect Two', mlb_id=200002, grade=55)

    clamped = client.get('/api/prospects/?limit=999999')
    limited = client.get('/api/prospects/?limit=1')

    assert clamped.status_code == 200
    assert len(clamped.get_json()) == 2
    assert limited.status_code == 200
    assert len(limited.get_json()) == 1


@pytest.mark.parametrize(
    'path,parameter',
    [
        ('/api/bullpen/pitchers/1/logs?days=-1', 'days'),
        ('/api/bullpen/fatigue?team_id=-1', 'team_id'),
        ('/api/bullpen/fatigue?risk_level=SEVERE', 'risk_level'),
        ('/api/prospects/?min_grade=10', 'min_grade'),
        ('/api/prospects/?level=LOWA', 'level'),
        ('/api/prospects/?position=SP', 'position'),
        ('/api/pitchers/search?q=kim&limit=abc', 'limit'),
        ('/api/recommendations/v2/bullpen-state?limit=-1', 'limit'),
    ],
)
def test_numeric_and_enum_query_params_return_structured_400(client, path, parameter):
    response = client.get(path)

    assert_invalid_param(response, parameter)


def test_team_operations_uses_existing_refusal_envelope_for_invalid_team_id(client):
    response = client.get('/api/team-operations/bullpen-readiness?team_id=-1')

    assert response.status_code == 400
    body = response.get_json()
    assert body['contract_state'] == 'refused'
    assert body['refusal']['reason'] == 'invalid_request_parameter'
    assert 'team_id must be at least 1' in body['refusal']['message']


def test_query_param_helper_validates_pagination_style_values():
    offset, offset_error = parse_non_negative_int_param(
        MultiDict([('offset', '3')]),
        'offset',
    )
    page, page_error = parse_non_negative_int_param(
        MultiDict([('page', '0')]),
        'page',
    )
    bad_offset, bad_offset_error = parse_non_negative_int_param(
        MultiDict([('offset', '-1')]),
        'offset',
    )
    limit, limit_error = parse_positive_int_param(
        MultiDict([('limit', '999')]),
        'limit',
        maximum=25,
        clamp_max=True,
    )

    assert offset == 3
    assert offset_error is None
    assert page == 0
    assert page_error is None
    assert bad_offset is None
    assert bad_offset_error.parameter == 'offset'
    assert limit == 25
    assert limit_error is None


def test_omitted_params_use_existing_defaults(client):
    with client.application.app_context():
        _seed_prospect()

    response = client.get('/api/prospects/')

    assert response.status_code == 200
    assert len(response.get_json()) == 1
