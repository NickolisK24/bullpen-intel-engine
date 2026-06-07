"""
Player Detail availability must match roster-adjusted board semantics.

The detail response can expose workload evidence, but its primary availability
status must include roster-status overrides.
"""

from datetime import date, timedelta

import pytest
from flask import Flask

import models.prospect  # noqa: F401
import services.sync as sync_service
from api.bullpen import bullpen_bp
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from services.roster_status import STATUS_ACTIVE, STATUS_IL_15, STATUS_IL_60
from utils.db import db
from utils.time import utc_now_naive


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
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


def seed_pitcher(name, mlb_id, roster_status, risk_level='LOW', raw_score=12.0):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=113,
        team_name='Cincinnati Reds',
        team_abbreviation='CIN',
        position='RP',
        active=True,
        roster_status=roster_status,
        roster_status_source='test_fixture',
        roster_status_updated_at=utc_now_naive(),
    )
    db.session.add(pitcher)
    db.session.commit()
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=mlb_id * 10,
        game_date=date.today() - timedelta(days=3),
        pitches_thrown=8,
        innings_pitched=1.0,
        game_type='R',
    ))
    db.session.add(FatigueScore(
        pitcher_id=pitcher.id,
        calculated_at=utc_now_naive(),
        raw_score=raw_score,
        pitch_count_score=10.0,
        rest_days_score=10.0,
        appearances_score=10.0,
        innings_score=10.0,
        days_since_last_appearance=3,
        appearances_last_7=1,
        appearances_last_14=1,
        pitches_last_7_days=8,
        innings_last_7_days=1.0,
        risk_level=risk_level,
    ))
    db.session.commit()
    return pitcher


def test_player_detail_il_60_final_availability_matches_board_override(client):
    with client.application.app_context():
        pitcher = seed_pitcher('Graham Ashcraft', 668933, STATUS_IL_60)
        pitcher_id = pitcher.id

    detail = client.get(f'/api/bullpen/fatigue/{pitcher_id}').get_json()

    assert detail['availability']['availability_status'] == 'Unavailable'
    assert detail['availability']['roster_status']['label'] == 'IL-60'
    assert detail['workload_signal']['availability_status'] == 'Available'
    assert any('Roster status: IL-60.' in reason for reason in detail['availability']['reasons'])
    assert any('not available for bullpen planning' in limitation for limitation in detail['availability']['limitations'])


def test_player_detail_il_15_final_availability_is_unavailable_not_workload_only(client):
    with client.application.app_context():
        pagan = seed_pitcher('Emilio Pagan', 641941, STATUS_IL_15, risk_level='MODERATE', raw_score=48.0)
        johnson = seed_pitcher('Pierce Johnson', 572955, STATUS_IL_15, raw_score=18.0)
        pagan_id = pagan.id
        johnson_id = johnson.id

    pagan_detail = client.get(f'/api/bullpen/fatigue/{pagan_id}').get_json()
    johnson_detail = client.get(f'/api/bullpen/fatigue/{johnson_id}').get_json()

    assert pagan_detail['availability']['availability_status'] == 'Unavailable'
    assert pagan_detail['availability']['roster_status']['label'] == 'IL-15'
    assert pagan_detail['workload_signal']['availability_status'] == 'Monitor'
    assert johnson_detail['availability']['availability_status'] == 'Unavailable'
    assert johnson_detail['availability']['roster_status']['label'] == 'IL-15'
    assert johnson_detail['workload_signal']['availability_status'] == 'Available'


def test_player_detail_active_pitcher_final_availability_matches_workload_signal(client):
    with client.application.app_context():
        pitcher = seed_pitcher('Brock Burke', 656271, STATUS_ACTIVE, raw_score=18.0)
        pitcher_id = pitcher.id

    detail = client.get(f'/api/bullpen/fatigue/{pitcher_id}').get_json()

    assert detail['availability']['availability_status'] == detail['workload_signal']['availability_status']
    assert detail['availability']['availability_status'] == 'Available'
    assert detail['availability']['roster_status']['label'] == 'Active MLB'
