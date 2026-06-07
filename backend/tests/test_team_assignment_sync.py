"""
Tests for authoritative team-assignment synchronization.

These use fake MLB roster/player payloads and in-memory SQLite; no network calls.
Names in the regression fixture are examples only and are not implementation keys.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta

import pytest
from flask import Flask

import models.prospect  # noqa: F401
import services.sync as sync_service
from api.bullpen import bullpen_bp
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from services.roster_status import STATUS_ACTIVE, STATUS_UNKNOWN
from services.roster_status_sync import (
    ROSTER_TYPE_ACTIVE,
    ROSTER_TYPE_FULL,
    sync_roster_statuses,
)
from services.team_assignment_sync import (
    TEAM_ASSIGNMENT_ASSIGNED,
    TEAM_ASSIGNMENT_NO_ORGANIZATION,
    TEAM_ASSIGNMENT_UNKNOWN,
    sync_team_assignments,
)
from utils.db import db


TEAM_FIXTURES = {
    110: ('Baltimore Orioles', 'BAL'),
    116: ('Detroit Tigers', 'DET'),
    120: ('Washington Nationals', 'WSH'),
    121: ('New York Mets', 'NYM'),
    134: ('Pittsburgh Pirates', 'PIT'),
    137: ('San Francisco Giants', 'SF'),
    141: ('Toronto Blue Jays', 'TOR'),
    142: ('Minnesota Twins', 'MIN'),
    143: ('Philadelphia Phillies', 'PHI'),
    145: ('Chicago White Sox', 'CWS'),
}


class FakeAssignmentClient:
    def __init__(self, rosters=None, player_info=None, teams=None):
        self.rosters = rosters or {}
        self.player_info = player_info or {}
        self.teams = teams or [
            {'id': team_id, 'name': name, 'abbreviation': abbreviation}
            for team_id, (name, abbreviation) in TEAM_FIXTURES.items()
        ]

    def get_all_teams(self):
        return list(self.teams)

    def get_team_roster(self, team_id, roster_type='pitchers', **_kwargs):
        return list(self.rosters.get((team_id, roster_type), []))

    def get_player_info(self, player_id):
        return self.player_info.get(player_id)


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


def roster_entry(player_id, name, position='P', status=None):
    entry = {
        'person': {'id': player_id, 'fullName': name},
        'position': {'abbreviation': position},
    }
    if status is not None:
        entry['status'] = status
    return entry


def seed_pitcher(name, mlb_id, team_id, position='RP', days_ago=1, raw_score=10.0):
    team_name, team_abbreviation = TEAM_FIXTURES.get(team_id, (f'Team {team_id}', f'T{team_id}'))
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=team_id,
        team_name=team_name,
        team_abbreviation=team_abbreviation,
        position=position,
        active=True,
    )
    db.session.add(pitcher)
    db.session.commit()
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=mlb_id * 10,
        game_date=date.today() - timedelta(days=days_ago),
        pitches_thrown=12,
        innings_pitched=1.0,
        game_type='R',
    ))
    db.session.add(FatigueScore(
        pitcher_id=pitcher.id,
        raw_score=raw_score,
        risk_level='LOW',
        calculated_at=datetime.utcnow(),
    ))
    db.session.commit()
    return pitcher


def _board_names(payload):
    return [
        card['name']
        for group in payload['groups']
        for card in group['pitchers']
    ]


def test_reassignment_after_trade_updates_pitcher_before_roster_status(client):
    with client.application.app_context():
        pitcher = seed_pitcher('Connor Seabold', 900001, team_id=116)
        fake = FakeAssignmentClient(rosters={
            (141, ROSTER_TYPE_ACTIVE): [
                roster_entry(900001, 'Connor Seabold', status={'code': 'A', 'description': 'Active'}),
            ],
        })

        assignment = sync_team_assignments(
            client=fake,
            timestamp=datetime(2026, 6, 7, 12, 0, 0),
        )
        roster = sync_roster_statuses(
            client=fake,
            timestamp=datetime(2026, 6, 7, 12, 1, 0),
        )
        updated = db.session.get(Pitcher, pitcher.id)

    assert assignment['reassigned_count'] == 1
    assert updated.team_id == 141
    assert updated.team_name == 'Toronto Blue Jays'
    assert updated.team_abbreviation == 'TOR'
    assert updated.team_assignment_status == TEAM_ASSIGNMENT_ASSIGNED
    assert updated.team_assignment_source == 'mlb_stats_api:team_assignment_sync:active'
    assert roster['teams_processed'] == 1
    assert updated.roster_status == STATUS_ACTIVE


def test_waiver_claim_and_signing_can_correct_stale_ownership(client):
    with client.application.app_context():
        justin = seed_pitcher('Justin Lawrence', 900002, team_id=134)
        trevor = seed_pitcher('Trevor Richards', 900003, team_id=143)
        fake = FakeAssignmentClient(
            rosters={
                (142, ROSTER_TYPE_ACTIVE): [
                    roster_entry(900002, 'Justin Lawrence', status='Active'),
                ],
            },
            player_info={
                900003: {
                    'fullName': 'Trevor Richards',
                    'currentTeam': {'id': 145, 'name': 'Chicago White Sox'},
                },
            },
        )

        result = sync_team_assignments(client=fake)
        updated_justin = db.session.get(Pitcher, justin.id)
        updated_trevor = db.session.get(Pitcher, trevor.id)

    assert result['reassigned_count'] == 2
    assert updated_justin.team_id == 142
    assert updated_justin.team_abbreviation == 'MIN'
    assert updated_trevor.team_id == 145
    assert updated_trevor.team_abbreviation == 'CWS'
    assert updated_trevor.team_assignment_source == 'mlb_stats_api:team_assignment_sync:people:currentTeam'


def test_released_free_agent_handling_clears_stale_team(client):
    with client.application.app_context():
        pitcher = seed_pitcher('Ryan Borucki', 900004, team_id=137)
        fake = FakeAssignmentClient(player_info={
            900004: {
                'fullName': 'Ryan Borucki',
                'status': {'description': 'Free Agent'},
            },
        })

        result = sync_team_assignments(client=fake)
        updated = db.session.get(Pitcher, pitcher.id)

    assert result['no_organization_count'] == 1
    assert result['cleared_team_count'] == 1
    assert updated.team_assignment_status == TEAM_ASSIGNMENT_NO_ORGANIZATION
    assert updated.team_id is None
    assert updated.team_name is None
    assert updated.team_abbreviation is None
    assert updated.active is False
    assert updated.roster_status == STATUS_UNKNOWN
    assert updated.roster_status_source == 'mlb_stats_api:team_assignment_sync:people:status'


def test_bullpen_board_and_dashboard_use_corrected_ownership(client):
    with client.application.app_context():
        seed_pitcher('Joel Kuhnel', 900005, team_id=116)
        fake = FakeAssignmentClient(rosters={
            (141, ROSTER_TYPE_ACTIVE): [
                roster_entry(900005, 'Joel Kuhnel', status='Active'),
            ],
        })
        sync_team_assignments(client=fake)

    old_board = client.get('/api/bullpen/teams/116/board?include_stale=true').get_json()
    new_board = client.get('/api/bullpen/teams/141/board').get_json()
    dashboard = client.get('/api/bullpen/dashboard').get_json()

    assert 'Joel Kuhnel' not in _board_names(old_board)
    assert 'Joel Kuhnel' in _board_names(new_board)

    landscape_team_ids = {
        entry['team_id']
        for key in ('constrained_bullpens', 'available_bullpens', 'monitoring_concentration')
        for entry in dashboard['landscape'][key]
    }
    assert 116 not in landscape_team_ids
    assert 141 in landscape_team_ids


def test_regression_examples_resolve_without_name_based_logic(client):
    examples = [
        ('Joel Kuhnel', 900101, 116, 141),
        ('Connor Seabold', 900102, 116, 145),
        ('Simeon Woods Richardson', 900103, 116, 142),
        ('Craig Kimbrel', 900104, 110, None),
        ('Trevor Richards', 900105, 143, 145),
        ('Justin Lawrence', 900106, 134, 142),
        ('Ryan Borucki', 900107, 137, None),
        ('Matt Pushard', 900108, 143, 'unknown'),
        ('Yeondrys Gomez', 900109, 116, 120),
        ('Cionel Pérez', 900110, 110, 121),
    ]
    rosters = defaultdict(list)
    player_info = {
        900104: {'fullName': 'Craig Kimbrel', 'status': {'description': 'Released'}},
        900107: {'fullName': 'Ryan Borucki', 'status': {'description': 'Free Agent'}},
        900108: {'fullName': 'Matt Pushard', 'status': {'description': 'Unknown'}},
    }

    with client.application.app_context():
        for name, mlb_id, old_team_id, expected_team_id in examples:
            seed_pitcher(name, mlb_id, team_id=old_team_id)
            if isinstance(expected_team_id, int):
                roster_type = ROSTER_TYPE_FULL if name == 'Trevor Richards' else ROSTER_TYPE_ACTIVE
                rosters[(expected_team_id, roster_type)].append(roster_entry(mlb_id, name, status='Active'))

        result = sync_team_assignments(
            client=FakeAssignmentClient(rosters=dict(rosters), player_info=player_info)
        )
        by_name = {pitcher.full_name: pitcher for pitcher in Pitcher.query.all()}

    assert result['by_status'][TEAM_ASSIGNMENT_ASSIGNED] == 7
    assert result['by_status'][TEAM_ASSIGNMENT_NO_ORGANIZATION] == 2
    assert result['by_status'][TEAM_ASSIGNMENT_UNKNOWN] == 1
    assert by_name['Joel Kuhnel'].team_id == 141
    assert by_name['Connor Seabold'].team_id == 145
    assert by_name['Simeon Woods Richardson'].team_id == 142
    assert by_name['Trevor Richards'].team_id == 145
    assert by_name['Justin Lawrence'].team_id == 142
    assert by_name['Yeondrys Gomez'].team_id == 120
    assert by_name['Cionel Pérez'].team_id == 121
    assert by_name['Craig Kimbrel'].team_id is None
    assert by_name['Ryan Borucki'].team_id is None
    assert by_name['Matt Pushard'].team_assignment_status == TEAM_ASSIGNMENT_UNKNOWN


def test_unknown_ownership_fails_closed_instead_of_retaining_stale_team(client):
    with client.application.app_context():
        pitcher = seed_pitcher('Matt Pushard', 900006, team_id=143)
        fake = FakeAssignmentClient(player_info={
            900006: {
                'fullName': 'Matt Pushard',
                'status': {'description': 'Unknown'},
            },
        })

        result = sync_team_assignments(client=fake)
        updated = db.session.get(Pitcher, pitcher.id)

    assert result['unknown_count'] == 1
    assert updated.team_assignment_status == TEAM_ASSIGNMENT_UNKNOWN
    assert updated.team_assignment_source == 'mlb_stats_api:team_assignment_sync:unavailable'
    assert updated.team_id is None
    assert updated.active is False
    assert updated.roster_status == STATUS_UNKNOWN
