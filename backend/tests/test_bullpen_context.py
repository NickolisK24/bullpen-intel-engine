from datetime import date, timedelta

import pytest
from flask import Flask

from api.bullpen import bullpen_bp
from models.game_log import GameLog
from models.pitcher import Pitcher
import models.prospect  # noqa: F401
from services.bullpen_context import (
    BULLPEN_CONTEXT_SAMPLE_CAP,
    build_team_bullpen_context,
)
from utils.db import db


REF = date(2026, 6, 8)

ROTATION_CONTEXT_KEYS = {
    'context_available',
    'evidence_type',
    'window_days',
    'starter_avg_ip_last_7',
    'starter_avg_ip_prev_7',
    'starter_starts_last_7',
    'starter_starts_prev_7',
    'delta_ip',
    'trend',
    'windows',
}

USAGE_DEMAND_CONTEXT_KEYS = {
    'context_available',
    'evidence_type',
    'window_days',
    'bullpen_appearances_last_7',
    'bullpen_appearances_prev_7',
    'bullpen_pitches_last_7',
    'bullpen_pitches_prev_7',
    'appearance_delta',
    'pitch_delta',
    'appearance_pct_delta',
    'pitch_pct_delta',
    'null_start_rows_included_as_bullpen',
    'trend',
    'windows',
}


@pytest.fixture
def client():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    with app.app_context():
        db.create_all()
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            db.drop_all()


def _seed_pitcher(team_id, name, mlb_id):
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


def _seed_log(pitcher, days_ago, game_pk, innings, pitches=15, games_started=0):
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
        game_date=REF - timedelta(days=days_ago),
        innings_pitched=innings,
        pitches_thrown=pitches,
        games_started=games_started,
        game_type='R',
    ))
    db.session.commit()


def _seed_team_identity(team_id, mlb_id):
    return _seed_pitcher(team_id, f'Team {team_id} Pitcher', mlb_id)


def _assert_normalized_context_shapes(result):
    assert set(result['rotation_context']) == ROTATION_CONTEXT_KEYS
    assert set(result['usage_demand_context']) == USAGE_DEMAND_CONTEXT_KEYS


def test_no_data_team_returns_normalized_rotation_context_shape(client):
    with client.application.app_context():
        _seed_team_identity(116, 11601)

        context = build_team_bullpen_context(116)

    rotation = context['rotation_context']
    assert set(rotation) == ROTATION_CONTEXT_KEYS
    assert rotation['context_available'] is False
    assert rotation['window_days'] == 7
    assert rotation['starter_avg_ip_last_7'] is None
    assert rotation['starter_avg_ip_prev_7'] is None
    assert rotation['starter_starts_last_7'] == 0
    assert rotation['starter_starts_prev_7'] == 0
    assert rotation['delta_ip'] is None
    assert rotation['trend'] == 'insufficient_data'
    assert rotation['windows'] is None
    assert 'No stored game-log context was found for this team.' in context['limitations']


def test_no_data_team_returns_normalized_usage_demand_context_shape(client):
    with client.application.app_context():
        _seed_team_identity(117, 11701)

        context = build_team_bullpen_context(117)

    demand = context['usage_demand_context']
    assert set(demand) == USAGE_DEMAND_CONTEXT_KEYS
    assert demand['context_available'] is False
    assert demand['window_days'] == 7
    assert demand['bullpen_appearances_last_7'] == 0
    assert demand['bullpen_appearances_prev_7'] == 0
    assert demand['bullpen_pitches_last_7'] == 0
    assert demand['bullpen_pitches_prev_7'] == 0
    assert demand['appearance_delta'] == 0
    assert demand['pitch_delta'] == 0
    assert demand['appearance_pct_delta'] is None
    assert demand['pitch_pct_delta'] is None
    assert demand['null_start_rows_included_as_bullpen'] == 0
    assert demand['trend'] == 'insufficient_data'
    assert demand['windows'] is None
    assert 'No stored game-log context was found for this team.' in context['limitations']


def test_shorter_starter_outings_detected(client):
    with client.application.app_context():
        starter = _seed_pitcher(118, 'Shorter Starter', 11801)
        _seed_log(starter, 1, 118011, innings=4.2, pitches=82, games_started=1)
        _seed_log(starter, 3, 118012, innings=4.8, pitches=88, games_started=1)
        _seed_log(starter, 8, 118013, innings=6.0, pitches=96, games_started=1)
        _seed_log(starter, 10, 118014, innings=6.2, pitches=98, games_started=1)

        context = build_team_bullpen_context(118, reference_date=REF)

    rotation = context['rotation_context']
    _assert_normalized_context_shapes(context)
    assert rotation['context_available'] is True
    assert rotation['window_days'] == 7
    assert rotation['starter_avg_ip_last_7'] == 4.5
    assert rotation['starter_avg_ip_prev_7'] == 6.1
    assert rotation['trend'] == 'shorter_outings'


def test_longer_starter_outings_detected(client):
    with client.application.app_context():
        starter = _seed_pitcher(119, 'Longer Starter', 11901)
        _seed_log(starter, 1, 119011, innings=6.4, pitches=92, games_started=1)
        _seed_log(starter, 4, 119012, innings=6.0, pitches=90, games_started=1)
        _seed_log(starter, 8, 119013, innings=4.8, pitches=84, games_started=1)
        _seed_log(starter, 12, 119014, innings=5.0, pitches=86, games_started=1)

        context = build_team_bullpen_context(119, reference_date=REF)

    rotation = context['rotation_context']
    _assert_normalized_context_shapes(context)
    assert rotation['context_available'] is True
    assert rotation['window_days'] == 7
    assert rotation['starter_avg_ip_last_7'] == 6.2
    assert rotation['starter_avg_ip_prev_7'] == 4.9
    assert rotation['trend'] == 'longer_outings'


def test_rising_bullpen_demand_detected(client):
    with client.application.app_context():
        reliever = _seed_pitcher(120, 'Busy Reliever', 12001)
        for idx, days_ago in enumerate([0, 1, 2, 4]):
            _seed_log(reliever, days_ago, 120010 + idx, innings=1.0, pitches=18, games_started=0)
        for idx, days_ago in enumerate([8, 12]):
            _seed_log(reliever, days_ago, 120020 + idx, innings=1.0, pitches=12, games_started=0)

        context = build_team_bullpen_context(120, reference_date=REF)

    demand = context['usage_demand_context']
    _assert_normalized_context_shapes(context)
    assert demand['context_available'] is True
    assert demand['window_days'] == 7
    assert demand['bullpen_appearances_last_7'] == 4
    assert demand['bullpen_appearances_prev_7'] == 2
    assert demand['bullpen_pitches_last_7'] == 72
    assert demand['bullpen_pitches_prev_7'] == 24
    assert demand['trend'] == 'increasing_demand'


def test_falling_bullpen_demand_detected(client):
    with client.application.app_context():
        reliever = _seed_pitcher(121, 'Lighter Reliever', 12101)
        _seed_log(reliever, 1, 121011, innings=1.0, pitches=10, games_started=0)
        for idx, days_ago in enumerate([8, 9, 11, 13]):
            _seed_log(reliever, days_ago, 121020 + idx, innings=1.0, pitches=18, games_started=0)

        context = build_team_bullpen_context(121, reference_date=REF)

    demand = context['usage_demand_context']
    _assert_normalized_context_shapes(context)
    assert demand['context_available'] is True
    assert demand['window_days'] == 7
    assert demand['bullpen_appearances_last_7'] == 1
    assert demand['bullpen_appearances_prev_7'] == 4
    assert demand['bullpen_pitches_last_7'] == 10
    assert demand['bullpen_pitches_prev_7'] == 72
    assert demand['trend'] == 'decreasing_demand'


def test_league_sample_is_capped(client):
    with client.application.app_context():
        for offset in range(BULLPEN_CONTEXT_SAMPLE_CAP + 2):
            pitcher = _seed_team_identity(200 + offset, 20000 + offset)
            _seed_log(pitcher, 1, 200000 + offset, innings=1.0, games_started=0)

    response = client.get('/api/bullpen/context/diagnostic?mode=league_sample')

    assert response.status_code == 200
    body = response.get_json()
    assert body['mode'] == 'league_sample'
    assert body['sample_cap'] == BULLPEN_CONTEXT_SAMPLE_CAP
    assert len(body['results']) == BULLPEN_CONTEXT_SAMPLE_CAP
    assert len(body['sampled_team_ids']) == BULLPEN_CONTEXT_SAMPLE_CAP
    for result in body['results']:
        _assert_normalized_context_shapes(result)


def test_data_backed_and_no_data_contracts_have_the_same_shape(client):
    with client.application.app_context():
        no_data_pitcher = _seed_team_identity(122, 12201)
        data_pitcher = _seed_pitcher(123, 'Data Reliever', 12301)
        _seed_log(data_pitcher, 1, 123011, innings=1.0, pitches=16, games_started=0)

        no_data = build_team_bullpen_context(no_data_pitcher.team_id)
        data_backed = build_team_bullpen_context(data_pitcher.team_id, reference_date=REF)

    assert set(no_data['rotation_context']) == set(data_backed['rotation_context'])
    assert set(no_data['usage_demand_context']) == set(data_backed['usage_demand_context'])


def test_diagnostic_route_team_mode_returns_evidence_contract(client):
    with client.application.app_context():
        starter = _seed_pitcher(130, 'Context Starter', 13001)
        reliever = _seed_pitcher(130, 'Context Reliever', 13002)
        _seed_log(starter, 1, 130011, innings=5.0, pitches=84, games_started=1)
        _seed_log(starter, 8, 130012, innings=6.0, pitches=94, games_started=1)
        _seed_log(reliever, 1, 130021, innings=1.0, pitches=16, games_started=0)
        _seed_log(reliever, 8, 130022, innings=1.0, pitches=10, games_started=0)

    response = client.get('/api/bullpen/context/diagnostic?mode=team&team_id=130')

    assert response.status_code == 200
    body = response.get_json()
    assert body['capability'] == 'bullpen_context_engine_v1_diagnostic'
    assert body['ranking_applied'] is False
    assert body['selection_made'] is False
    assert body['mode'] == 'team'
    assert body['team_id'] == 130
    result = body['results'][0]
    _assert_normalized_context_shapes(result)
    assert result['team_id'] == 130
    assert result['rotation_context']['evidence_type'] == 'starter_innings_pitched'
    assert result['usage_demand_context']['evidence_type'] == 'bullpen_appearance_and_pitch_volume'
    assert result['availability_context'] == {
        'context_available': False,
        'reason': 'not_implemented',
        'data_source': None,
    }


def test_context_limitations_are_included(client):
    with client.application.app_context():
        pitcher = _seed_team_identity(140, 14001)
        _seed_log(pitcher, 1, 140011, innings=1.0, games_started=0)

    response = client.get('/api/bullpen/context/diagnostic?team_id=140')

    assert response.status_code == 200
    body = response.get_json()
    for limitation in [
        'Context is descriptive.',
        'Context is not causal proof.',
        'Context does not explain every bullpen state.',
        'Context does not override observations.',
    ]:
        assert limitation in body['limitations']
        assert limitation in body['results'][0]['limitations']
