from datetime import date, datetime, timedelta

import pytest
from flask import Flask
from tests.db_config import configure_test_database
from sqlalchemy import inspect

import services.sync as sync_service
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.sync_run import SyncRun
import models.prospect  # noqa: F401  (register on db.metadata)
from services.availability import ACTIVE_WINDOW_DAYS
from services.roster_status import STATUS_ACTIVE
from api.bullpen import bullpen_bp
from utils.db import db


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


def _pitcher(
    name,
    mlb_id,
    team_id=1,
    active=True,
    position='P',
    roster_status=STATUS_ACTIVE,
):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=team_id,
        team_name='Test Club',
        team_abbreviation='TST',
        position=position,
        active=active,
        roster_status=roster_status,
        roster_status_source='test_fixture' if roster_status else None,
        roster_status_updated_at=datetime.utcnow() if roster_status else None,
    )
    db.session.add(pitcher)
    db.session.commit()
    return pitcher


def _log(pitcher, game_date, game_pk, pitches=12, innings=1.0, hold=False, save=False):
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
        game_date=game_date,
        pitches_thrown=pitches,
        innings_pitched=innings,
        innings_pitched_outs=round(innings * 3),
        games_started=1 if innings >= 3 else 0,
        hold=hold,
        save=save,
        game_type='R',
    ))
    db.session.commit()


def _score(pitcher, raw_score, calculated_on, hour=12):
    db.session.add(FatigueScore(
        pitcher_id=pitcher.id,
        calculated_at=datetime(
            calculated_on.year,
            calculated_on.month,
            calculated_on.day,
            hour,
            0,
            0,
        ),
        raw_score=raw_score,
        risk_level='LOW',
    ))
    db.session.commit()


def _successful_sync(game_date, started_offset=0):
    synced_at = datetime.utcnow() + timedelta(minutes=started_offset)
    db.session.add(SyncRun(
        started_at=synced_at - timedelta(seconds=40),
        completed_at=synced_at,
        status='success',
        source='github_actions',
        latest_game_date=game_date,
        latest_workload_date=game_date,
        latest_fatigue_calculated_at=synced_at,
        records_processed=12,
        new_logs_added=2,
        pitchers_updated=2,
        errors=0,
        created_at=synced_at - timedelta(seconds=40),
    ))
    db.session.commit()


def _failed_sync(started_offset=5):
    failed_at = datetime.utcnow() + timedelta(minutes=started_offset)
    db.session.add(SyncRun(
        started_at=failed_at,
        completed_at=failed_at + timedelta(seconds=20),
        status='failed',
        source='github_actions',
        errors=1,
        error_message='MLB API unavailable',
        created_at=failed_at,
    ))
    db.session.commit()


def _recent_dates():
    current = date.today() - timedelta(days=1)
    anchor = current - timedelta(days=1)
    return anchor, current


def _change_ids(body, change_type=None):
    changes = body.get('pitcher_changes') or []
    if change_type:
        changes = [change for change in changes if change['type'] == change_type]
    return {change['pitcher_id'] for change in changes}


class TestTeamChangesEndpoint:
    def test_changes_state_emits_status_change_and_new_appearance(self, client):
        anchor, current = _recent_dates()
        with client.application.app_context():
            pitcher = _pitcher('Shift Arm', mlb_id=101)
            _log(pitcher, anchor, 1010, pitches=6)
            _log(pitcher, current, 1011, pitches=24)
            _score(pitcher, 43.0, anchor)
            _score(pitcher, 65.0, current)
            _successful_sync(current)

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['capability'] == 'what_changed_since_last_game'
        assert body['ranking_applied'] is False
        assert body['selection_made'] is False
        assert body['state'] == 'changes'
        assert body['comparison']['anchor_game_date'] == anchor.isoformat()
        assert body['comparison']['current_game_date'] == current.isoformat()
        assert body['comparison']['label'] == (
            f'Compared with TST: {anchor:%b} {anchor.day} -> {current:%b} {current.day}'
        )

        status_changes = [
            change for change in body['pitcher_changes']
            if change['type'] == 'status_change'
        ]
        appearances = [
            change for change in body['pitcher_changes']
            if change['type'] == 'appearance'
        ]
        assert status_changes == [{
            'type': 'status_change',
            'pitcher_id': status_changes[0]['pitcher_id'],
            'pitcher_name': 'Shift Arm',
            'from_status': 'Monitor',
            'to_status': 'Limited',
            'summary': 'Shift Arm moved from Monitor to Limited.',
        }]
        assert appearances[0]['pitcher_name'] == 'Shift Arm'
        assert appearances[0]['pitches'] == 24
        assert 'Pitched' in appearances[0]['summary']
        assert '24 pitches' in appearances[0]['summary']

    def test_no_changes_state_ignores_fatigue_drift_without_label_change(self, client):
        anchor, current = _recent_dates()
        with client.application.app_context():
            stable = _pitcher('Stable Arm', mlb_id=102)
            marker = _pitcher('Inactive Game Marker', mlb_id=103, active=False)
            _log(stable, anchor, 1020, pitches=12)
            _log(marker, current, 1030, pitches=12)
            _score(stable, 43.0, anchor)
            _score(stable, 45.0, current)
            _successful_sync(current)

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['state'] == 'no_changes'
        assert body['pitcher_changes'] == []
        assert body['team_summary'] is None

    def test_no_baseline_state_when_team_has_only_one_completed_game_date(self, client):
        current = date.today() - timedelta(days=1)
        with client.application.app_context():
            pitcher = _pitcher('First Game Arm', mlb_id=104)
            _log(pitcher, current, 1040, pitches=18)
            _score(pitcher, 42.0, current)
            _successful_sync(current)

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['state'] == 'no_baseline'
        assert body['pitcher_changes'] == []
        assert body['state_reason_codes'] == ['previous_team_game_missing']

    def test_stale_state_does_not_compute_deltas(self, client):
        current = date.today() - timedelta(days=ACTIVE_WINDOW_DAYS + 5)
        anchor = current - timedelta(days=1)
        with client.application.app_context():
            pitcher = _pitcher('Old Shift Arm', mlb_id=105)
            _log(pitcher, anchor, 1050, pitches=12)
            _log(pitcher, current, 1051, pitches=35)
            _score(pitcher, 43.0, anchor)
            _score(pitcher, 80.0, current)
            _successful_sync(current)

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['state'] == 'stale'
        assert body['pitcher_changes'] == []
        assert body['team_summary'] is None
        assert 'workload_data_not_current' in body['state_reason_codes']

    def test_sync_metadata_unavailable_fails_closed_without_deltas(self, client):
        anchor, current = _recent_dates()
        with client.application.app_context():
            pitcher = _pitcher('No Metadata Arm', mlb_id=106)
            _log(pitcher, anchor, 1060, pitches=12)
            _log(pitcher, current, 1061, pitches=35)
            _score(pitcher, 43.0, anchor)
            _score(pitcher, 80.0, current)

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['state'] == 'stale'
        assert body['pitcher_changes'] == []
        assert 'durable_sync_metadata_unavailable' in body['state_reason_codes']
        assert 'successful_sync_missing' in body['state_reason_codes']

    def test_latest_sync_failure_is_reported_when_current_data_is_comparable(self, client):
        anchor, current = _recent_dates()
        with client.application.app_context():
            stable = _pitcher('Failure Window Arm', mlb_id=107)
            marker = _pitcher('Failed Sync Marker', mlb_id=108, active=False)
            _log(stable, anchor, 1070, pitches=12)
            _log(marker, current, 1080, pitches=12)
            _score(stable, 43.0, anchor)
            _score(stable, 45.0, current)
            _successful_sync(current)
            _failed_sync()

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['state'] == 'no_changes'
        assert body['freshness']['sync_status'] == 'failed'
        assert any('latest sync attempt failed' in limitation.lower()
                   for limitation in body['limitations'])

    def test_endpoint_does_not_require_new_tables(self, client):
        with client.application.app_context():
            table_names = set(inspect(db.engine).get_table_names())

        assert 'availability_snapshots' not in table_names
        assert 'team_change_snapshots' not in table_names
        assert 'what_changed_events' not in table_names

        res = client.get('/api/bullpen/teams/1/changes')
        assert res.status_code == 200

    def test_clear_starter_is_excluded_while_reliever_appearance_remains(self, client):
        anchor, current = _recent_dates()
        with client.application.app_context():
            starter = _pitcher('Clear Starter', mlb_id=201, position='SP')
            reliever = _pitcher('Bullpen Reliever', mlb_id=202)

            _log(starter, anchor, 2010, pitches=92, innings=6.0)
            _log(starter, current, 2011, pitches=88, innings=6.0)
            _score(starter, 35.0, anchor)
            _score(starter, 80.0, current)

            _log(reliever, anchor, 2020, pitches=8, innings=1.0, hold=True)
            _log(reliever, current, 2021, pitches=18, innings=1.0, hold=True)
            _score(reliever, 30.0, anchor)
            _score(reliever, 42.0, current)
            _successful_sync(current)
            reliever_id = reliever.id

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        change_names = {change['pitcher_name'] for change in body['pitcher_changes']}
        assert 'Clear Starter' not in change_names
        assert 'Bullpen Reliever' in change_names
        assert _change_ids(body, 'appearance') == {reliever_id}

    def test_board_and_changes_use_same_default_eligible_population(self, client):
        anchor, current = _recent_dates()
        with client.application.app_context():
            starter = _pitcher('Board Starter', mlb_id=211, position='SP')
            reliever = _pitcher('Board Reliever', mlb_id=212)
            _log(starter, anchor, 2110, pitches=80, innings=5.0)
            _log(starter, current, 2111, pitches=82, innings=5.0)
            _score(starter, 30.0, anchor)
            _score(starter, 65.0, current)

            _log(reliever, anchor, 2120, pitches=8, innings=1.0, hold=True)
            _log(reliever, current, 2121, pitches=20, innings=1.0, hold=True)
            _score(reliever, 30.0, anchor)
            _score(reliever, 45.0, current)
            _successful_sync(current)

        board = client.get('/api/bullpen/teams/1/board').get_json()
        changes = client.get('/api/bullpen/teams/1/changes').get_json()

        board_ids = {
            card['pitcher_id']
            for group in board['groups']
            for card in group['pitchers']
        }
        assert board_ids == _change_ids(changes, 'appearance')

    def test_team_summary_is_suppressed_until_current_counts_are_board_safe(self, client):
        anchor, current = _recent_dates()
        with client.application.app_context():
            stable = _pitcher('Stable Current Reliever', mlb_id=215)
            new_arm = _pitcher('New Current Reliever', mlb_id=216)

            _log(stable, anchor, 2150, pitches=6, innings=1.0, hold=True)
            _log(stable, current, 2151, pitches=8, innings=1.0, hold=True)
            _score(stable, 20.0, anchor)
            _score(stable, 22.0, current)

            _log(new_arm, current, 2160, pitches=7, innings=1.0, hold=True)
            _score(new_arm, 21.0, current)
            _successful_sync(current)

        board = client.get('/api/bullpen/teams/1/board').get_json()
        changes = client.get('/api/bullpen/teams/1/changes').get_json()

        assert board['total_pitchers'] == 2
        assert changes['team_summary'] is None
        assert 'Available arms' not in str(changes)
        assert _change_ids(changes, 'appearance') == {
            card['pitcher_id']
            for group in board['groups']
            for card in group['pitchers']
        }

    def test_roster_inactive_reliever_is_excluded_from_changes(self, client):
        anchor, current = _recent_dates()
        with client.application.app_context():
            il_arm = _pitcher('Unavailable Reliever', mlb_id=221, roster_status='IL_15')
            _log(il_arm, anchor, 2210, pitches=8, innings=1.0, hold=True)
            _log(il_arm, current, 2211, pitches=18, innings=1.0, hold=True)
            _score(il_arm, 30.0, anchor)
            _score(il_arm, 65.0, current)
            _successful_sync(current)

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert 'Unavailable Reliever' not in {
            change['pitcher_name'] for change in body['pitcher_changes']
        }

    def test_team_date_inference_uses_unfiltered_team_game_evidence(self, client):
        anchor, current = _recent_dates()
        with client.application.app_context():
            reliever = _pitcher('Date Reliever', mlb_id=231)
            starter = _pitcher('Date Starter', mlb_id=232, position='SP')
            _log(reliever, anchor, 2310, pitches=12, innings=1.0, hold=True)
            _score(reliever, 35.0, anchor)
            _score(reliever, 36.0, current)

            _log(starter, current, 2320, pitches=88, innings=6.0)
            _score(starter, 30.0, current)
            _successful_sync(current)

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['comparison']['current_game_date'] == current.isoformat()
        assert body['comparison']['anchor_game_date'] == anchor.isoformat()
        assert body['pitcher_changes'] == []

    def test_team_local_current_date_reports_when_team_trails_league_data(self, client):
        anchor, current = _recent_dates()
        league_current = current + timedelta(days=1)
        with client.application.app_context():
            reliever = _pitcher('Behind Reliever', mlb_id=241, team_id=1)
            _log(reliever, anchor, 2410, pitches=8, innings=1.0, hold=True)
            _log(reliever, current, 2411, pitches=18, innings=1.0, hold=True)
            _score(reliever, 30.0, anchor)
            _score(reliever, 45.0, current)

            league_marker = _pitcher('League Marker', mlb_id=242, team_id=2)
            _log(league_marker, league_current, 2420, pitches=12, innings=1.0)
            _successful_sync(league_current)

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['state'] == 'changes'
        assert body['comparison']['current_game_date'] == current.isoformat()
        assert body['comparison']['global_latest_game_date'] == league_current.isoformat()
        assert body['comparison']['team_data_behind_league'] is True
        assert 'team_data_behind_league' in body['state_reason_codes']
        assert any(
            f'TST latest game data is {current:%b} {current.day}' in limitation
            and f'league data is current through {league_current:%b} {league_current.day}' in limitation
            for limitation in body['limitations']
        )
