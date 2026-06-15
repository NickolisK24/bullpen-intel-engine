import json
from datetime import date, timedelta

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.fatigue_score  # noqa: F401
from api.bullpen import bullpen_bp
from models.game_log import GameLog
from models.pitcher import Pitcher
from utils.db import db


REFERENCE_DATE = date(2026, 6, 12)


@pytest.fixture
def client():
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    with app.app_context():
        create_test_schema(app)
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            drop_test_schema(app)


def _seed_pitcher(name, team_id, mlb_id):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=team_id,
        team_name=f'Team {team_id}',
        team_abbreviation=f'T{team_id}',
        active=True,
    )
    db.session.add(pitcher)
    db.session.commit()
    return pitcher


def _seed_log(pitcher, days_ago, game_pk, pitches=12, games_started=0):
    innings = 1.0 if games_started == 0 else 5.0
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
        game_date=REFERENCE_DATE - timedelta(days=days_ago),
        pitches_thrown=pitches,
        innings_pitched=innings,
        innings_pitched_outs=round(innings * 3),
        games_started=games_started,
        game_type='R',
    ))


def _seed_team(team_id=101, mlb_base=1000):
    primary = _seed_pitcher(f'Team {team_id} Arm One', team_id, mlb_base + 1)
    secondary = _seed_pitcher(f'Team {team_id} Arm Two', team_id, mlb_base + 2)
    depth = _seed_pitcher(f'Team {team_id} Arm Three', team_id, mlb_base + 3)
    starter = _seed_pitcher(f'Team {team_id} Starter', team_id, mlb_base + 4)

    _seed_log(primary, 0, mlb_base + 10, pitches=15)
    _seed_log(primary, 2, mlb_base + 12, pitches=14)
    _seed_log(primary, 4, mlb_base + 14, pitches=13)
    _seed_log(secondary, 0, mlb_base + 10, pitches=12)
    _seed_log(secondary, 3, mlb_base + 13, pitches=11)
    _seed_log(depth, 6, mlb_base + 16, pitches=10)
    _seed_log(starter, 1, mlb_base + 11, pitches=82, games_started=1)
    db.session.commit()
    return {
        'primary': primary,
        'secondary': secondary,
        'depth': depth,
        'starter': starter,
    }


def _assert_contract(result):
    for field in ('window_start', 'window_end', 'data_through_date', 'evidence', 'limitations'):
        assert field in result
    assert isinstance(result['evidence'], dict)
    assert isinstance(result['limitations'], list)


def test_narrative_memory_diagnostic_default_sample_is_capped(client):
    with client.application.app_context():
        for index, team_id in enumerate(range(201, 207)):
            _seed_team(team_id=team_id, mlb_base=2000 + index * 100)

    response = client.get('/api/bullpen/narrative-memory/diagnostic')
    payload = response.get_json()

    assert response.status_code == 200
    assert payload['status'] == 'ok'
    assert payload['mode'] == 'league_sample'
    assert payload['window_days'] == 10
    assert payload['sample_cap'] == 5
    assert len(payload['sampled_team_ids']) == 5
    assert len(payload['results']) == 10
    assert payload['data_through_date'] == '2026-06-12'
    assert all(result['team']['team_id'] in payload['sampled_team_ids'] for result in payload['results'])
    for result in payload['results']:
        _assert_contract(result)


def test_narrative_memory_diagnostic_team_mode_returns_team_evidence(client):
    with client.application.app_context():
        _seed_team(team_id=101, mlb_base=1000)

    response = client.get('/api/bullpen/narrative-memory/diagnostic?team_id=101&window_days=10')
    payload = response.get_json()

    assert response.status_code == 200
    assert payload['status'] == 'ok'
    assert payload['mode'] == 'team'
    assert payload['team_id'] == 101
    assert [result['result_type'] for result in payload['results']] == [
        'team_workload_concentration',
        'team_workload_easing',
    ]
    concentration = payload['results'][0]
    _assert_contract(concentration)
    assert concentration['evidence']['bullpen_appearances'] == 6
    assert concentration['evidence']['excluded_starter_appearances'] == 1
    assert concentration['team']['team_abbreviation'] == 'T101'


def test_narrative_memory_diagnostic_pitcher_mode_returns_usage_trend(client):
    with client.application.app_context():
        seeded = _seed_team(team_id=102, mlb_base=1100)
        pitcher_id = seeded['primary'].id

    response = client.get(
        f'/api/bullpen/narrative-memory/diagnostic?pitcher_id={pitcher_id}&window_days=10'
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload['status'] == 'ok'
    assert payload['mode'] == 'pitcher'
    assert payload['pitcher_id'] == pitcher_id
    assert payload['team_id'] == 102
    assert len(payload['results']) == 1
    result = payload['results'][0]
    _assert_contract(result)
    assert result['result_type'] == 'pitcher_usage_trend'
    assert result['pitcher']['pitcher_id'] == pitcher_id
    assert result['evidence']['appearance_frequency'][0]['game_window'] == 6
    assert result['evidence']['window_appearances'] == 3


def test_narrative_memory_diagnostic_invalid_params_are_json_errors(client):
    bad_window = client.get('/api/bullpen/narrative-memory/diagnostic?window_days=11')
    bad_team = client.get('/api/bullpen/narrative-memory/diagnostic?team_id=abc')
    missing_team = client.get('/api/bullpen/narrative-memory/diagnostic?team_id=9999')

    assert bad_window.status_code == 400
    assert bad_window.get_json()['status'] == 'error'
    assert bad_window.get_json()['reason_code'] == 'invalid_request'
    assert bad_team.status_code == 400
    assert bad_team.get_json()['message'] == 'team_id must be an integer.'
    assert missing_team.status_code == 404
    assert missing_team.get_json()['reason_code'] == 'team_not_found'


def test_narrative_memory_diagnostic_rejects_team_pitcher_mismatch(client):
    with client.application.app_context():
        seeded = _seed_team(team_id=103, mlb_base=1200)
        _seed_team(team_id=104, mlb_base=1300)
        pitcher_id = seeded['primary'].id

    response = client.get(
        f'/api/bullpen/narrative-memory/diagnostic?team_id=104&pitcher_id={pitcher_id}'
    )
    payload = response.get_json()

    assert response.status_code == 422
    assert payload['status'] == 'error'
    assert payload['reason_code'] == 'pitcher_team_mismatch'


def test_narrative_memory_diagnostic_avoids_unsupported_claims(client):
    with client.application.app_context():
        _seed_team(team_id=105, mlb_base=1400)

    payload = client.get(
        '/api/bullpen/narrative-memory/diagnostic?team_id=105'
    ).get_json()
    serialized = json.dumps(payload).lower()

    for forbidden in (
        'injur',
        'manager trust',
        'closer',
        'health',
        'same-story',
        'same story',
        'confidence score',
        'fatigue score',
    ):
        assert forbidden not in serialized
