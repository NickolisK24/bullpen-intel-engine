"""
Tests for the league-wide bullpen dashboard endpoint (GET /api/bullpen/dashboard).

It must reuse existing systems (availability summary, Team Context Layer, usage
roles) without ranking/selection, and stay resilient when empty.
"""

from datetime import date, datetime, timedelta

import pytest
from flask import Flask

import services.sync as sync_service
from services.pitcher_role import ROLE_KEYS
from utils.db import db
from models.pitcher import Pitcher
from models.game_log import GameLog
from models.fatigue_score import FatigueScore
import models.prospect  # noqa: F401
from api.bullpen import bullpen_bp


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


def _seed_pitcher(name, team_id, mlb_id, raw_score=10.0, innings=1.0, days_ago=1):
    pitcher = Pitcher(mlb_id=mlb_id, full_name=name, team_id=team_id,
                      team_name=f'Team {team_id}', team_abbreviation=f'T{team_id}', active=True)
    db.session.add(pitcher)
    db.session.commit()
    db.session.add(GameLog(pitcher_id=pitcher.id, mlb_game_pk=mlb_id * 10,
                           game_date=date.today() - timedelta(days=days_ago),
                           pitches_thrown=12, innings_pitched=innings))
    db.session.add(FatigueScore(pitcher_id=pitcher.id, raw_score=raw_score,
                                risk_level='LOW', calculated_at=datetime.utcnow()))
    db.session.commit()
    return pitcher


class TestDashboardEndpoint:
    def test_empty_system_returns_stable_shape(self, client):
        body = client.get('/api/bullpen/dashboard').get_json()
        assert body['capability'] == 'bullpen_dashboard'
        assert body['ranking_applied'] is False
        assert body['selection_made'] is False
        assert body['context']['health']['state'] == 'no_data'
        assert body['roles']['total'] == 0
        assert set(body['roles']['counts']) == set(ROLE_KEYS)

    def test_aggregates_context_and_roles_across_teams(self, client):
        with client.application.app_context():
            _seed_pitcher('A One', team_id=1, mlb_id=1)
            _seed_pitcher('A Two', team_id=1, mlb_id=2)
            _seed_pitcher('B One', team_id=2, mlb_id=3)

        body = client.get('/api/bullpen/dashboard').get_json()
        # League-wide context comes from the availability summary counts.
        assert body['context']['metrics']['total_relievers'] >= 1
        assert body['context']['health']['state'] in (
            'manageable', 'monitoring', 'elevated', 'constrained', 'no_data',
        )
        # Roles sum to the scored-pitcher set.
        assert body['roles']['total'] == sum(body['roles']['counts'].values())
        # Freshness/data-through is present for the hero.
        assert 'data_through' in body['freshness']

    def test_no_governance_or_ranking_fields_leak(self, client):
        with client.application.app_context():
            _seed_pitcher('Solo', team_id=1, mlb_id=1)
        body = client.get('/api/bullpen/dashboard').get_json()
        assert 'ranking_applied' not in body['context']
        assert 'selection_made' not in body['context']
        assert body['availability_summary']['total_pitchers'] >= 0
