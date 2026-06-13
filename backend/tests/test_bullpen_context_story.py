from datetime import date, timedelta

import pytest
from flask import Flask

import models.prospect  # noqa: F401
import services.sync as sync_service
from api.bullpen import bullpen_bp
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from services.bullpen_context_story import (
    TYPE_ROTATION_LENGTH,
    TYPE_USAGE_DEMAND,
    build_dashboard_story_context,
    build_team_story_context,
)
from services.roster_status import STATUS_ACTIVE
from utils.db import db
from utils.time import utc_now_naive


REF = date(2026, 6, 8)


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


def _seed_pitcher(team_id, name, mlb_id, raw_score=None):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=team_id,
        team_name=f'Team {team_id}',
        team_abbreviation=f'T{team_id}',
        active=True,
        roster_status=STATUS_ACTIVE,
        roster_status_source='test_fixture',
        roster_status_updated_at=utc_now_naive(),
    )
    db.session.add(pitcher)
    db.session.commit()
    if raw_score is not None:
        db.session.add(FatigueScore(
            pitcher_id=pitcher.id,
            raw_score=raw_score,
            risk_level='LOW',
            calculated_at=utc_now_naive(),
        ))
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


def test_rotation_context_emitted_for_shorter_starter_outings(client):
    with client.application.app_context():
        starter = _seed_pitcher(118, 'Shorter Starter', 11801)
        _seed_log(starter, 1, 118011, innings=4.2, pitches=82, games_started=1)
        _seed_log(starter, 3, 118012, innings=4.8, pitches=88, games_started=1)
        _seed_log(starter, 8, 118013, innings=6.0, pitches=96, games_started=1)
        _seed_log(starter, 10, 118014, innings=6.2, pitches=98, games_started=1)

        context = build_team_story_context(118)

    rotation = context['by_type'][TYPE_ROTATION_LENGTH]
    assert rotation['context']['type'] == TYPE_ROTATION_LENGTH
    assert rotation['context']['evidence']['trend'] == 'shorter_outings'
    assert rotation['context_note'] == (
        "Team 118's starters have averaged 4.5 innings over the last 7 days, "
        'down from 6.1 the week before, leaving more innings for the bullpen in those games.'
    )


def test_usage_demand_context_emitted_for_rising_usage(client):
    with client.application.app_context():
        reliever = _seed_pitcher(120, 'Busy Reliever', 12001)
        for idx, days_ago in enumerate([0, 1, 2, 4]):
            _seed_log(reliever, days_ago, 120010 + idx, innings=1.0, pitches=18, games_started=0)
        for idx, days_ago in enumerate([8, 12]):
            _seed_log(reliever, days_ago, 120020 + idx, innings=1.0, pitches=12, games_started=0)

        context = build_team_story_context(120)

    usage = context['by_type'][TYPE_USAGE_DEMAND]
    assert usage['context']['type'] == TYPE_USAGE_DEMAND
    assert usage['context']['evidence']['trend'] == 'increasing_demand'
    assert usage['context_note'] == (
        'Recent bullpen work has picked up: 4 appearances and 72 pitches over the last 7 days, '
        'up from 2 appearances and 24 pitches the week before.'
    )


def test_usage_demand_context_emitted_for_easing_usage(client):
    with client.application.app_context():
        reliever = _seed_pitcher(121, 'Easing Reliever', 12101)
        _seed_log(reliever, 1, 121011, innings=1.0, pitches=10, games_started=0)
        for idx, days_ago in enumerate([8, 9, 11, 13]):
            _seed_log(reliever, days_ago, 121020 + idx, innings=1.0, pitches=18, games_started=0)

        context = build_team_story_context(121)

    usage = context['by_type'][TYPE_USAGE_DEMAND]
    assert usage['context']['type'] == TYPE_USAGE_DEMAND
    assert usage['context']['evidence']['trend'] == 'decreasing_demand'
    assert usage['context_note'] == (
        'Recent bullpen work has eased: 1 appearance and 10 pitches over the last 7 days, '
        'down from 4 appearances and 72 pitches the week before.'
    )


def test_insufficient_data_context_is_suppressed(client):
    with client.application.app_context():
        _seed_pitcher(122, 'No Context Arm', 12201)

        context = build_team_story_context(122)

    assert context is None


def test_dashboard_story_context_keeps_story_safe_contract(client):
    with client.application.app_context():
        reliever = _seed_pitcher(123, 'Demand Reliever', 12301)
        for idx, days_ago in enumerate([0, 1, 2, 4]):
            _seed_log(reliever, days_ago, 123010 + idx, innings=1.0, pitches=18, games_started=0)
        for idx, days_ago in enumerate([8, 12]):
            _seed_log(reliever, days_ago, 123020 + idx, innings=1.0, pitches=12, games_started=0)

        payload = build_dashboard_story_context([123, 123, None])

    assert payload['capability'] == 'bullpen_context_story_v1'
    assert set(payload['teams']) == {'123'}
    team = payload['teams']['123']
    assert team['context_note']
    assert team['by_type'][TYPE_USAGE_DEMAND]['context']['evidence']['trend'] == 'increasing_demand'


def test_dashboard_route_includes_story_context_for_landscape_teams(client):
    with client.application.app_context():
        reliever = _seed_pitcher(124, 'Landscape Reliever', 12401, raw_score=45)
        for idx, days_ago in enumerate([0, 1, 2, 4]):
            _seed_log(reliever, days_ago, 124010 + idx, innings=1.0, pitches=18, games_started=0)
        for idx, days_ago in enumerate([8, 12]):
            _seed_log(reliever, days_ago, 124020 + idx, innings=1.0, pitches=12, games_started=0)

    body = client.get('/api/bullpen/dashboard').get_json()

    assert body['ranking_applied'] is False
    assert body['selection_made'] is False
    assert body['story_context']['capability'] == 'bullpen_context_story_v1'
    assert set(body['story_context']['teams']) == {'124'}
    team = body['story_context']['teams']['124']
    assert team['context']['type'] == TYPE_USAGE_DEMAND
    assert 'Recent bullpen work has picked up' in team['context_note']
