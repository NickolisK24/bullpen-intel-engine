"""
Tests for the schedule / game-context adapter (services/game_context.py) and its
endpoints: Today's Game Context and Tonight's Bullpen Landscape.

Everything is derived from stored game logs / availability — no live network.
In-memory SQLite, no Postgres / MLB.
"""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from flask import Flask
from tests.db_config import configure_test_database

import services.sync as sync_service
from services.game_context import build_landscape, build_team_game_context
from utils.db import db
from models.pitcher import Pitcher
from models.game_log import GameLog
from models.fatigue_score import FatigueScore
import models.prospect  # noqa: F401
from api.bullpen import bullpen_bp

FORBIDDEN_TERMS = (
    'best bullpen', 'worst bullpen', 'best ', 'worst ', 'recommended', 'recommendation',
    'prediction', 'predict', 'advantage', 'should use', 'expected winner', 'matchup advice',
)


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    app = Flask(__name__)
    configure_test_database(app)
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


def _seed_team_with_game(team_id, mlb_id, opponent='Rivals', opp_abbr='RIV', days_ago=2):
    pitcher = Pitcher(mlb_id=mlb_id, full_name=f'P{mlb_id}', team_id=team_id,
                      team_name=f'Team {team_id}', team_abbreviation=f'T{team_id}', active=True)
    db.session.add(pitcher)
    db.session.commit()
    db.session.add(GameLog(pitcher_id=pitcher.id, mlb_game_pk=mlb_id * 100,
                           game_date=date.today() - timedelta(days=days_ago),
                           opponent=opponent, opponent_abbreviation=opp_abbr,
                           pitches_thrown=12, innings_pitched=1.0,
                           innings_pitched_outs=3))
    db.session.add(FatigueScore(pitcher_id=pitcher.id, raw_score=20.0,
                                risk_level='LOW', calculated_at=datetime.utcnow()))
    db.session.commit()
    return pitcher


def _fake_record(team_id, status):
    pitcher = SimpleNamespace(team_id=team_id, team_name=f'Team {team_id}',
                              team_abbreviation=f'T{team_id}')
    return {'pitcher': pitcher, 'availability': {'availability_status': status}}


def _no_forbidden_language(blob):
    low = blob.lower()
    return not any(term in low for term in FORBIDDEN_TERMS)


# ── Team game context ──────────────────────────────────────────────────────

class TestTeamGameContext:
    def test_stored_game_log_state_with_opponent(self, client):
        with client.application.app_context():
            _seed_team_with_game(1, mlb_id=1, opponent='Rivals', opp_abbr='RIV', days_ago=2)
            ctx = build_team_game_context(1)
        assert ctx['state'] == 'stored_game_log'
        assert ctx['available'] is True
        assert ctx['data_source'] == 'game_log'
        assert ctx['opponent'] == 'Rivals'
        assert ctx['opponent_abbreviation'] == 'RIV'
        assert ctx['data_state'] == 'historical'
        assert ctx['confidence'] == 'medium'
        # Home/away and scheduled time are never in the stored data.
        assert ctx['home_away'] is None
        assert ctx['scheduled_time'] is None
        assert 'home_away' in ctx['missing_fields']
        assert 'scheduled_time' in ctx['missing_fields']
        assert ctx['source_label'] == 'Stored game-log context'

    def test_no_game_found_when_team_has_no_logs(self, client):
        with client.application.app_context():
            p = Pitcher(mlb_id=9, full_name='X', team_id=5, team_name='Team 5',
                        team_abbreviation='T5', active=True)
            db.session.add(p)
            db.session.commit()
            ctx = build_team_game_context(5)
        assert ctx['state'] == 'no_game_found'
        assert ctx['available'] is False
        assert ctx['message'] == 'No game found in the stored game log for this date.'
        assert ctx['data_state'] == 'unavailable'

    def test_unavailable_when_team_unknown(self, client):
        ctx = build_team_game_context(999)
        assert ctx['state'] == 'unavailable'
        assert ctx['message'] == 'Schedule context unavailable.'
        assert ctx['confidence'] == 'none'

    def test_stale_game_lowers_confidence(self, client):
        with client.application.app_context():
            _seed_team_with_game(2, mlb_id=2, days_ago=40)
            ctx = build_team_game_context(2)
        assert ctx['data_state'] == 'stale'
        assert ctx['confidence'] == 'low'

    def test_endpoint_returns_game_context(self, client):
        with client.application.app_context():
            _seed_team_with_game(1, mlb_id=1)
        res = client.get('/api/bullpen/teams/1/game-context')
        assert res.status_code == 200
        body = res.get_json()
        assert body['capability'] == 'team_game_context'
        assert _no_forbidden_language(str(body))


# ── Landscape ──────────────────────────────────────────────────────────────

class TestLandscape:
    def test_response_shape_and_governance(self, client):
        with client.application.app_context():
            payload = build_landscape(reference_date=date.today())
        for key in ('reference_date', 'teams_evaluated', 'games', 'constrained_bullpens',
                    'available_bullpens', 'monitoring_concentration', 'notes', 'freshness'):
            assert key in payload, f'missing {key}'
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False
        assert payload['capability'] == 'tonights_bullpen_landscape'

    def test_descriptive_sorting_is_deterministic(self, client):
        # Team 1: 3 restricted; Team 2: 1 restricted; Team 3: all available.
        records = (
            [_fake_record(1, 'Avoid')] * 2 + [_fake_record(1, 'Unavailable')]
            + [_fake_record(1, 'Available')]
            + [_fake_record(2, 'Avoid')] + [_fake_record(2, 'Available')] * 4
            + [_fake_record(3, 'Available')] * 5
        )
        with client.application.app_context():
            payload = build_landscape(records=records, reference_date=date.today())

        constrained = payload['constrained_bullpens']
        assert constrained[0]['team_id'] == 1          # most restricted first (count)
        assert constrained[0]['restricted'] == 3
        # Only teams with restriction appear.
        assert all(entry['restricted'] > 0 for entry in constrained)

        available = payload['available_bullpens']
        assert available[0]['team_id'] in (2, 3)       # most available arms
        assert available[0]['available'] == 5

    def test_constrained_team_never_also_headlines_available(self, client):
        # The reconciliation invariant for the user's "healthiest AND most
        # constrained at the same time" question. Team 1 carries a deep pen
        # (six available arms) but is genuinely constrained (four restricted
        # of ten → constrained shape). On raw count alone it would top BOTH
        # columns; the health-state gate must keep it out of the available
        # frame so the two opposing public reads stay mutually exclusive.
        records = (
            [_fake_record(1, 'Avoid')] * 3 + [_fake_record(1, 'Unavailable')]
            + [_fake_record(1, 'Available')] * 6
            + [_fake_record(2, 'Available')] * 4
        )
        with client.application.app_context():
            payload = build_landscape(records=records, reference_date=date.today())

        constrained = payload['constrained_bullpens']
        constrained_ids = {e['team_id'] for e in constrained}
        available_ids = {e['team_id'] for e in payload['available_bullpens']}

        # Team 1 has the most available arms in absolute terms (6 vs 4) yet is
        # the constrained-shape club, so it must headline only the constrained
        # frame and stay out of the available frame.
        assert any(e['team_id'] == 1 and e['available'] == 6 for e in constrained)
        assert 1 in constrained_ids
        assert 1 not in available_ids
        # No team may appear in both opposing frames.
        assert constrained_ids.isdisjoint(available_ids)
        # The available frame still surfaces the genuinely healthy club.
        assert 2 in available_ids

    def test_manageable_team_with_one_restricted_arm_is_not_constrained_headline(self, client):
        # Inverse direction: a healthy club with a single restricted arm used to
        # leak into the constrained column purely because restricted > 0. Its
        # reconciled shape is manageable, so it must headline available only.
        records = (
            [_fake_record(1, 'Available')] * 9 + [_fake_record(1, 'Avoid')]
            + [_fake_record(2, 'Avoid')] * 3 + [_fake_record(2, 'Unavailable')] * 2
        )
        with client.application.app_context():
            payload = build_landscape(records=records, reference_date=date.today())

        constrained_ids = {e['team_id'] for e in payload['constrained_bullpens']}
        available_ids = {e['team_id'] for e in payload['available_bullpens']}

        assert 1 in available_ids
        assert 1 not in constrained_ids
        # Every constrained-frame entry is genuinely a constrained-shape pen.
        assert all(e['health_state'] == 'constrained'
                   for e in payload['constrained_bullpens'])
        assert constrained_ids.isdisjoint(available_ids)

    def test_no_forbidden_language_in_payload(self, client):
        records = [_fake_record(1, 'Avoid'), _fake_record(1, 'Monitor'), _fake_record(2, 'Available')]
        with client.application.app_context():
            payload = build_landscape(records=records, reference_date=date.today())
        assert _no_forbidden_language(str(payload))
        # Notes explicitly frame this as bullpen context, not a ranking/forecast.
        assert any('bullpen context' in note.lower() for note in payload['notes'])
        assert any('not a league ranking' in note.lower() for note in payload['notes'])

    def test_games_block_reports_stored_anchor(self, client):
        with client.application.app_context():
            _seed_team_with_game(1, mlb_id=1, days_ago=3)
            payload = build_landscape(reference_date=date.today())
        games = payload['games']
        assert games['available'] is True
        assert games['as_of_date'] == (date.today() - timedelta(days=3)).isoformat()
        assert games['today_count'] == 0               # historical sample → no game today
        assert games['data_state'] == 'historical'

    def test_endpoint_and_dashboard_expose_landscape(self, client):
        with client.application.app_context():
            _seed_team_with_game(1, mlb_id=1)
            _seed_team_with_game(2, mlb_id=2)

        res = client.get('/api/bullpen/landscape')
        assert res.status_code == 200
        assert res.get_json()['capability'] == 'tonights_bullpen_landscape'

        dash = client.get('/api/bullpen/dashboard').get_json()
        assert 'landscape' in dash
        assert dash['landscape']['capability'] == 'tonights_bullpen_landscape'
        assert _no_forbidden_language(str(dash['landscape']))
