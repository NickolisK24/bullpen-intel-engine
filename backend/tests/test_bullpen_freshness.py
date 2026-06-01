from datetime import date, datetime, timedelta

import pytest
from flask import Flask

from utils.db import db
from models.pitcher import Pitcher
from models.game_log import GameLog
from models.fatigue_score import FatigueScore
import models.prospect  # noqa: F401  (register on db.metadata)
from api.bullpen import ACTIVE_WINDOW_DAYS, bullpen_bp


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


def _add_scored_pitcher(days_since_last_game, team_id=1, risk_level='HIGH', raw_score=72.0):
    pitcher = Pitcher(
        mlb_id=1000 + days_since_last_game + team_id,
        full_name=f'Pitcher {days_since_last_game}',
        team_id=team_id,
        team_name='Test Club',
        team_abbreviation='TST',
        active=True,
    )
    db.session.add(pitcher)
    db.session.commit()

    game_date = date.today() - timedelta(days=days_since_last_game)
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=2000 + days_since_last_game + team_id,
        game_date=game_date,
        pitches_thrown=18,
        innings_pitched=1.0,
    ))
    db.session.add(FatigueScore(
        pitcher_id=pitcher.id,
        calculated_at=datetime.utcnow(),
        raw_score=raw_score,
        pitch_count_score=50.0,
        rest_days_score=30.0,
        appearances_score=20.0,
        innings_score=10.0,
        leverage_score=0.0,
        days_since_last_appearance=days_since_last_game,
        appearances_last_7=1,
        appearances_last_14=1,
        pitches_last_7_days=18,
        innings_last_7_days=1.0,
        risk_level=risk_level,
    ))
    db.session.commit()
    return pitcher


class TestBullpenFreshness:
    def test_legacy_fatigue_response_stays_array(self, client):
        with client.application.app_context():
            _add_scored_pitcher(days_since_last_game=1)

        res = client.get('/api/bullpen/fatigue?include_stale=false')

        assert res.status_code == 200
        assert isinstance(res.get_json(), list)
        assert len(res.get_json()) == 1

    def test_metadata_explains_stale_filtered_empty_list(self, client):
        stale_days = ACTIVE_WINDOW_DAYS + 10
        with client.application.app_context():
            _add_scored_pitcher(days_since_last_game=stale_days)

        current = client.get('/api/bullpen/fatigue?limit=750&include_stale=false&with_meta=true')
        inclusive = client.get('/api/bullpen/fatigue?limit=750&include_stale=true&with_meta=true')

        assert current.status_code == 200
        body = current.get_json()
        assert body['data'] == []
        assert body['meta']['total_game_logs'] == 1
        assert body['meta']['total_scored_pitchers'] == 1
        assert body['meta']['filtered_scored_pitchers'] == 1
        assert body['meta']['fresh_filtered_pitchers'] == 0
        assert body['meta']['stale_filtered_pitchers'] == 1

        inclusive_body = inclusive.get_json()
        assert len(inclusive_body['data']) == 1
        assert inclusive_body['meta']['filtered_scored_pitchers'] == 1
        assert inclusive_body['meta']['fresh_filtered_pitchers'] == 0

    def test_dashboard_overview_counts_stale_scores(self, client):
        with client.application.app_context():
            _add_scored_pitcher(days_since_last_game=ACTIVE_WINDOW_DAYS + 10)

        res = client.get('/api/bullpen/stats/overview')

        assert res.status_code == 200
        body = res.get_json()
        assert body['total_pitchers'] == 1
        assert body['total_game_logs'] == 1
        assert body['scored_pitchers'] == 1
        assert body['risk_breakdown']['HIGH'] == 1
