"""
Tests for authoritative roster-status ingestion from MLB roster endpoints.

These use fake MLB roster payloads and in-memory SQLite; no network calls.
"""

from datetime import date, datetime, timedelta

import pytest
from flask import Flask
from tests.db_config import configure_test_database

import models.prospect  # noqa: F401
import services.sync as sync_service
from api.bullpen import bullpen_bp
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from services.roster_status import (
    STATUS_40_MAN_ONLY,
    STATUS_ACTIVE,
    STATUS_DFA,
    STATUS_IL_15,
    STATUS_IL_60,
    STATUS_MINORS,
    STATUS_NON_ROSTER,
    STATUS_OPTIONED,
    STATUS_UNKNOWN,
)
from services.roster_status_sync import (
    ROSTER_TYPE_40_MAN,
    ROSTER_TYPE_ACTIVE,
    ROSTER_TYPE_FULL,
    ROSTER_TYPE_NON_ROSTER,
    classify_roster_evidence,
    sync_roster_statuses,
)
from utils.db import db


class FakeRosterClient:
    def __init__(self, rosters):
        self.rosters = rosters
        self.calls = []

    def get_team_roster(self, team_id, roster_type='pitchers', **_kwargs):
        self.calls.append((team_id, roster_type))
        return list(self.rosters.get((team_id, roster_type), []))


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


def roster_entry(player_id, name, position='P', status=None):
    entry = {
        'person': {'id': player_id, 'fullName': name},
        'position': {'abbreviation': position},
    }
    if status is not None:
        entry['status'] = status
    return entry


def seed_pitcher(name, mlb_id, team_id=113, days_ago=1, innings=1.0):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=team_id,
        team_name=f'Team {team_id}',
        team_abbreviation='CIN' if team_id == 113 else f'T{team_id}',
        position='P',
        active=True,
    )
    db.session.add(pitcher)
    db.session.commit()
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=mlb_id * 10,
        game_date=date.today() - timedelta(days=days_ago),
        pitches_thrown=12,
        innings_pitched=innings,
        innings_pitched_outs=round(innings * 3),
        games_started=1 if innings >= 3 else 0,
        game_type='R',
    ))
    db.session.add(FatigueScore(
        pitcher_id=pitcher.id,
        raw_score=10.0,
        risk_level='LOW',
        calculated_at=datetime.utcnow(),
    ))
    db.session.commit()
    return pitcher


def reds_rosters():
    return {
        (113, ROSTER_TYPE_ACTIVE): [
            roster_entry(11320, 'Reds Active Relief Context', status={'code': 'A', 'description': 'Active'}),
            roster_entry(668881, 'Hunter Greene', status={'code': 'A', 'description': 'Active'}),
            roster_entry(671096, 'Andrew Abbott', status={'code': 'A', 'description': 'Active'}),
            roster_entry(666157, 'Nick Lodolo', status={'code': 'A', 'description': 'Active'}),
            roster_entry(663903, 'Brady Singer', status={'code': 'A', 'description': 'Active'}),
        ],
        (113, ROSTER_TYPE_40_MAN): [
            roster_entry(11320, 'Reds Active Relief Context', status={'code': 'A', 'description': 'Active'}),
            roster_entry(668881, 'Hunter Greene', status={'code': 'A', 'description': 'Active'}),
            roster_entry(671096, 'Andrew Abbott', status={'code': 'A', 'description': 'Active'}),
            roster_entry(666157, 'Nick Lodolo', status={'code': 'A', 'description': 'Active'}),
            roster_entry(663903, 'Brady Singer', status={'code': 'A', 'description': 'Active'}),
            roster_entry(668933, 'Graham Ashcraft', status={'code': 'D60', 'description': '60-day IL'}),
            roster_entry(572955, 'Pierce Johnson', status={'code': 'D15', 'description': '15-day IL'}),
            roster_entry(641941, 'Emilio Pagan', status={'code': 'D15', 'description': '15-day IL'}),
            roster_entry(695076, 'Rhett Lowder', status='Optioned to minors'),
            roster_entry(663886, 'Brandon Williamson', status='Designated for assignment'),
            roster_entry(700002, '40-man Context Pitcher'),
        ],
        (113, ROSTER_TYPE_FULL): [
            roster_entry(11320, 'Reds Active Relief Context', status='Active'),
            roster_entry(668881, 'Hunter Greene', status='Active'),
            roster_entry(671096, 'Andrew Abbott', status='Active'),
            roster_entry(666157, 'Nick Lodolo', status='Active'),
            roster_entry(663903, 'Brady Singer', status='Active'),
            roster_entry(668933, 'Graham Ashcraft', status='60-day injured list'),
            roster_entry(572955, 'Pierce Johnson', status='15-day injured list'),
            roster_entry(641941, 'Emilio Pagan', status='15-day injured list'),
            roster_entry(683175, 'Connor Phillips'),
            roster_entry(683742, 'Jose Franco', status='Minors'),
            roster_entry(810001, 'Chase Burns'),
            roster_entry(695076, 'Rhett Lowder', status='Optioned to minors'),
            roster_entry(663886, 'Brandon Williamson', status='Designated for assignment'),
        ],
        (113, ROSTER_TYPE_NON_ROSTER): [
            roster_entry(700001, 'Non Roster Pitcher'),
        ],
    }


def test_classifies_merged_roster_evidence_by_precedence():
    assert classify_roster_evidence({
        'roster_types': {ROSTER_TYPE_ACTIVE, ROSTER_TYPE_FULL},
        'raw_statuses': [(ROSTER_TYPE_FULL, 'Minors')],
    })['status'] == STATUS_ACTIVE
    assert classify_roster_evidence({
        'roster_types': {ROSTER_TYPE_FULL},
        'raw_statuses': [],
    })['status'] == STATUS_MINORS
    full_roster_active = classify_roster_evidence({
        'roster_types': {ROSTER_TYPE_FULL},
        'raw_statuses': [(ROSTER_TYPE_FULL, 'Active')],
    })
    assert full_roster_active['status'] == STATUS_MINORS
    assert full_roster_active['source'] == 'mlb_stats_api:roster_sync:fullRoster'
    assert classify_roster_evidence({
        'roster_types': {ROSTER_TYPE_NON_ROSTER},
        'raw_statuses': [],
    })['status'] == STATUS_NON_ROSTER
    assert classify_roster_evidence({
        'roster_types': {ROSTER_TYPE_40_MAN},
        'raw_statuses': [],
    })['status'] == STATUS_40_MAN_ONLY


def test_sync_persists_authoritative_roster_statuses(client):
    with client.application.app_context():
        seed_pitcher('Reds Active Relief Context', 11320)
        seed_pitcher('Hunter Greene', 668881)
        seed_pitcher('Andrew Abbott', 671096)
        seed_pitcher('Nick Lodolo', 666157)
        seed_pitcher('Brady Singer', 663903)
        seed_pitcher('Graham Ashcraft', 668933)
        seed_pitcher('Pierce Johnson', 572955)
        seed_pitcher('Emilio Pagan', 641941)
        seed_pitcher('Connor Phillips', 683175)
        seed_pitcher('Jose Franco', 683742)
        seed_pitcher('Chase Burns', 810001)
        seed_pitcher('Rhett Lowder', 695076)
        seed_pitcher('Brandon Williamson', 663886)
        seed_pitcher('Non Roster Pitcher', 700001)
        seed_pitcher('40-man Context Pitcher', 700002)
        seed_pitcher('Missing Roster Arm', 999999)

        result = sync_roster_statuses(
            team_ids=[113],
            client=FakeRosterClient(reds_rosters()),
            timestamp=datetime(2026, 6, 7, 12, 0, 0),
        )

        by_name = {pitcher.full_name: pitcher for pitcher in Pitcher.query.all()}

    assert result['teams_processed'] == 1
    assert result['pitchers_refreshed'] == 16
    assert result['by_status'][STATUS_ACTIVE] == 5
    assert result['by_status'][STATUS_IL_60] == 1
    assert result['by_status'][STATUS_IL_15] == 2
    assert result['by_status'][STATUS_MINORS] == 3
    assert result['by_status'][STATUS_OPTIONED] == 1
    assert result['by_status'][STATUS_DFA] == 1
    assert result['by_status'][STATUS_NON_ROSTER] == 1
    assert result['by_status'][STATUS_40_MAN_ONLY] == 1
    assert result['by_status'][STATUS_UNKNOWN] == 1
    assert by_name['Reds Active Relief Context'].roster_status == STATUS_ACTIVE
    assert by_name['Hunter Greene'].roster_status == STATUS_ACTIVE
    assert by_name['Andrew Abbott'].roster_status == STATUS_ACTIVE
    assert by_name['Nick Lodolo'].roster_status == STATUS_ACTIVE
    assert by_name['Brady Singer'].roster_status == STATUS_ACTIVE
    assert by_name['Graham Ashcraft'].roster_status == STATUS_IL_60
    assert by_name['Pierce Johnson'].roster_status == STATUS_IL_15
    assert by_name['Emilio Pagan'].roster_status == STATUS_IL_15
    assert by_name['Connor Phillips'].roster_status == STATUS_MINORS
    assert by_name['Jose Franco'].roster_status == STATUS_MINORS
    assert by_name['Chase Burns'].roster_status == STATUS_MINORS
    assert by_name['Rhett Lowder'].roster_status == STATUS_OPTIONED
    assert by_name['Brandon Williamson'].roster_status == STATUS_DFA
    assert by_name['Non Roster Pitcher'].roster_status == STATUS_NON_ROSTER
    assert by_name['40-man Context Pitcher'].roster_status == STATUS_40_MAN_ONLY
    assert by_name['Missing Roster Arm'].roster_status == STATUS_UNKNOWN
    assert by_name['Graham Ashcraft'].roster_status_source == 'mlb_stats_api:roster_sync:40Man'
    assert by_name['Missing Roster Arm'].roster_status_source == 'mlb_stats_api:roster_sync:unavailable'
    assert by_name['Graham Ashcraft'].roster_status_updated_at == datetime(2026, 6, 7, 12, 0, 0)


def test_roster_sync_feeds_default_board_filtering_and_context_labels(client):
    with client.application.app_context():
        seed_pitcher('Reds Active Relief Context', 11320)
        seed_pitcher('Graham Ashcraft', 668933)
        seed_pitcher('Pierce Johnson', 572955)
        seed_pitcher('Connor Phillips', 683175)
        seed_pitcher('Jose Franco', 683742)
        sync_roster_statuses(team_ids=[113], client=FakeRosterClient(reds_rosters()))

    default_body = client.get('/api/bullpen/teams/113/board').get_json()
    default_cards = [card for group in default_body['groups'] for card in group['pitchers']]
    assert [card['name'] for card in default_cards] == ['Reds Active Relief Context']
    assert default_body['roster_status']['excluded_inactive_count'] == 4

    context_body = client.get('/api/bullpen/teams/113/board?include_stale=true').get_json()
    context_cards = [card for group in context_body['groups'] for card in group['pitchers']]
    by_name = {card['name']: card for card in context_cards}

    assert by_name['Graham Ashcraft']['roster_status']['label'] == 'IL-60'
    assert by_name['Pierce Johnson']['roster_status']['label'] == 'IL-15'
    assert by_name['Connor Phillips']['roster_status']['label'] == 'Minors'
    assert by_name['Jose Franco']['roster_status']['label'] == 'Minors'
    assert all(card['availability_status'] != 'Available' for name, card in by_name.items() if name != 'Reds Active Relief Context')
