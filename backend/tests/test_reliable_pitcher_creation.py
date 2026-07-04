from datetime import date

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
import models.sync_run  # noqa: F401
import services.sync as sync_service
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.sync_failure import SyncFailure
from services import sync_metadata
from services.mlb_api import mlb_client
from services.roster_status import STATUS_ACTIVE, STATUS_MINORS
from utils.db import db


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        create_test_schema(app)
        try:
            yield app
        finally:
            db.session.remove()
            drop_test_schema(app)


def _status():
    return {
        'statusCode': 'F',
        'detailedState': 'Final',
        'abstractGameState': 'Final',
    }


def _game(game_pk=8101):
    return {
        'gamePk': game_pk,
        'gameType': 'R',
        'officialDate': '2026-06-20',
        'status': _status(),
        'teams': {
            'home': {'team': {'id': 1, 'name': 'Home Club', 'abbreviation': 'HME'}},
            'away': {'team': {'id': 2, 'name': 'Away Club', 'abbreviation': 'AWY'}},
        },
    }


def _stat(**overrides):
    stat = {
        'inningsPitched': '1.0',
        'numberOfPitches': 14,
        'strikes': 9,
        'hits': 0,
        'runs': 0,
        'earnedRuns': 0,
        'baseOnBalls': 0,
        'strikeOuts': 2,
        'homeRuns': 0,
        'holds': 1,
        'avgLI': '1.25',
    }
    stat.update(overrides)
    return stat


def _player(player_id, *, name='New Reliever', stats=None, person_id=None, position='P'):
    return {
        'person': {
            'id': person_id if person_id is not None else player_id,
            'fullName': name,
            'primaryPosition': {'abbreviation': position},
        },
        'stats': {'pitching': stats if stats is not None else _stat()},
    }


def _boxscore(
    *,
    player_id=303,
    name='New Reliever',
    stats=None,
    person_id=None,
    position='P',
    team_id=1,
    team_name='Home Club',
    team_abbreviation='HME',
):
    return {
        'teams': {
            'home': {
                'team': {
                    'id': team_id,
                    'name': team_name,
                    'abbreviation': team_abbreviation,
                },
                'pitchers': [player_id],
                'players': {
                    f'ID{player_id}': _player(
                        player_id,
                        name=name,
                        stats=stats,
                        person_id=person_id,
                        position=position,
                    ),
                },
            },
            'away': {
                'team': {'id': 2, 'name': 'Away Club', 'abbreviation': 'AWY'},
                'pitchers': [],
                'players': {},
            },
        },
    }


def _delete_marker(game_pk):
    marker = PostgameProcessedGame.query.filter_by(mlb_game_pk=game_pk).one()
    db.session.delete(marker)
    db.session.commit()


def test_unknown_postgame_pitcher_is_created_and_not_duplicated(app, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(
            mlb_client,
            'get_game_boxscore',
            lambda game_pk: _boxscore(player_id=303, name='New Reliever'),
        )

        first = sync_service.process_completed_game_for_postgame_refresh(
            _game(8101),
            schedule_date=date(2026, 6, 20),
        )
        db.session.commit()
        _delete_marker(8101)

        second = sync_service.process_completed_game_for_postgame_refresh(
            _game(8101),
            schedule_date=date(2026, 6, 20),
        )
        db.session.commit()
        pitcher = Pitcher.query.filter_by(mlb_id=303).one()
        logs = GameLog.query.filter_by(pitcher_id=pitcher.id, mlb_game_pk=8101).all()
        pitcher_count = Pitcher.query.filter_by(mlb_id=303).count()
        failure_count = SyncFailure.query.count()
        pitcher_payload = {
            'full_name': pitcher.full_name,
            'active': pitcher.active,
            'team_id': pitcher.team_id,
            'team_abbreviation': pitcher.team_abbreviation,
            'team_assignment_status': pitcher.team_assignment_status,
            'roster_status': pitcher.roster_status,
        }

    assert first['pitchers_created'] == 1
    assert first['logs_added'] == 1
    assert second['pitchers_created'] == 0
    assert second['logs_added'] == 0
    assert second['logs_corrected'] == 0
    assert pitcher_payload['full_name'] == 'New Reliever'
    assert pitcher_payload['active'] is True
    assert pitcher_payload['team_id'] == 1
    assert pitcher_payload['team_abbreviation'] == 'HME'
    assert pitcher_payload['team_assignment_status'] == 'ASSIGNED'
    assert pitcher_payload['roster_status'] == STATUS_ACTIVE
    assert len(logs) == 1
    assert pitcher_count == 1
    assert failure_count == 0


def test_inactive_pitcher_is_reactivated_from_authoritative_final_line(app, monkeypatch):
    with app.app_context():
        pitcher = Pitcher(
            mlb_id=404,
            full_name='Stale Reliever',
            team_id=9,
            team_name='Old Club',
            team_abbreviation='OLD',
            team_assignment_status='NO_ORGANIZATION',
            team_assignment_source='test:stale',
            position='P',
            active=False,
            roster_status=STATUS_MINORS,
        )
        db.session.add(pitcher)
        db.session.commit()
        monkeypatch.setattr(
            mlb_client,
            'get_game_boxscore',
            lambda game_pk: _boxscore(player_id=404, name='Stale Reliever'),
        )

        result = sync_service.process_completed_game_for_postgame_refresh(
            _game(8102),
            schedule_date=date(2026, 6, 20),
        )
        db.session.commit()
        refreshed = Pitcher.query.filter_by(mlb_id=404).one()
        log = GameLog.query.filter_by(pitcher_id=refreshed.id, mlb_game_pk=8102).one()
        pitcher_payload = {
            'active': refreshed.active,
            'team_id': refreshed.team_id,
            'team_name': refreshed.team_name,
            'team_abbreviation': refreshed.team_abbreviation,
            'team_assignment_status': refreshed.team_assignment_status,
            'roster_status': refreshed.roster_status,
        }
        pitches_thrown = log.pitches_thrown

    assert result['pitchers_created'] == 0
    assert result['pitchers_reactivated'] == 1
    assert result['logs_added'] == 1
    assert pitcher_payload['active'] is True
    assert pitcher_payload['team_id'] == 1
    assert pitcher_payload['team_name'] == 'Home Club'
    assert pitcher_payload['team_abbreviation'] == 'HME'
    assert pitcher_payload['team_assignment_status'] == 'ASSIGNED'
    assert pitcher_payload['roster_status'] == STATUS_ACTIVE
    assert pitches_thrown == 14


def test_invalid_player_id_pitching_line_is_dead_lettered(app, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(
            mlb_client,
            'get_game_boxscore',
            lambda game_pk: _boxscore(
                player_id='BAD',
                name='Unresolved Reliever',
                person_id=None,
            ),
        )

        result = sync_service.process_completed_game_for_postgame_refresh(
            _game(8103),
            schedule_date=date(2026, 6, 20),
        )
        db.session.commit()
        failure = SyncFailure.query.one()
        pitcher_count = Pitcher.query.count()
        log_count = GameLog.query.count()
        failure_entity_type = failure.entity_type
        failure_job_name = failure.job_name
        failure_payload = failure.payload

    assert result['pitcher_resolution_failures'] == 1
    assert result['logs_added'] == 0
    assert pitcher_count == 0
    assert log_count == 0
    assert failure_entity_type == sync_service.PITCHER_RESOLUTION_FAILURE_ENTITY_TYPE
    assert failure_job_name == sync_metadata.JOB_POSTGAME_REFRESH
    assert failure_payload['reason'] == 'missing_or_invalid_player_id'
    assert failure_payload['player_id'] == 'BAD'


def test_conflicting_team_assignment_is_dead_lettered(app, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(
            mlb_client,
            'get_game_boxscore',
            lambda game_pk: _boxscore(
                player_id=505,
                name='Conflicted Reliever',
                team_id=99,
                team_name='Wrong Club',
                team_abbreviation='WRG',
            ),
        )

        result = sync_service.process_completed_game_for_postgame_refresh(
            _game(8104),
            schedule_date=date(2026, 6, 20),
        )
        db.session.commit()
        failure = SyncFailure.query.one()
        pitcher_count = Pitcher.query.count()
        log_count = GameLog.query.count()
        failure_entity_type = failure.entity_type
        failure_payload = failure.payload

    assert result['pitcher_resolution_failures'] == 1
    assert result['logs_added'] == 0
    assert pitcher_count == 0
    assert log_count == 0
    assert failure_entity_type == sync_service.PITCHER_RESOLUTION_FAILURE_ENTITY_TYPE
    assert failure_payload['reason'] == 'conflicting_team_assignment'
    assert failure_payload['team_id'] == 99


def test_created_pitcher_flows_into_stat_correction_upsert(app, monkeypatch):
    with app.app_context():
        boxscores = [
            _boxscore(player_id=606, name='Corrected Reliever', stats=_stat(numberOfPitches=14)),
            _boxscore(
                player_id=606,
                name='Corrected Reliever',
                stats=_stat(numberOfPitches=27, strikes=18),
            ),
            _boxscore(
                player_id=606,
                name='Corrected Reliever',
                stats=_stat(numberOfPitches=27, strikes=18),
            ),
        ]

        def fake_boxscore(game_pk):
            return boxscores.pop(0)

        monkeypatch.setattr(mlb_client, 'get_game_boxscore', fake_boxscore)

        first = sync_service.process_completed_game_for_postgame_refresh(
            _game(8105),
            schedule_date=date(2026, 6, 20),
        )
        db.session.commit()
        _delete_marker(8105)

        second = sync_service.process_completed_game_for_postgame_refresh(
            _game(8105),
            schedule_date=date(2026, 6, 20),
        )
        db.session.commit()
        _delete_marker(8105)

        third = sync_service.process_completed_game_for_postgame_refresh(
            _game(8105),
            schedule_date=date(2026, 6, 20),
        )
        db.session.commit()
        pitcher = Pitcher.query.filter_by(mlb_id=606).one()
        log = GameLog.query.filter_by(pitcher_id=pitcher.id, mlb_game_pk=8105).one()
        pitcher_count = Pitcher.query.filter_by(mlb_id=606).count()
        log_count = GameLog.query.filter_by(pitcher_id=pitcher.id, mlb_game_pk=8105).count()
        log_payload = {
            'pitches_thrown': log.pitches_thrown,
            'strikes': log.strikes,
            'stat_correction_count': log.stat_correction_count,
            'last_stat_correction_source': log.last_stat_correction_source,
        }

    assert first['pitchers_created'] == 1
    assert first['logs_added'] == 1
    assert second['pitchers_created'] == 0
    assert second['logs_added'] == 0
    assert second['logs_corrected'] == 1
    assert third['logs_added'] == 0
    assert third['logs_corrected'] == 0
    assert pitcher_count == 1
    assert log_count == 1
    assert log_payload['pitches_thrown'] == 27
    assert log_payload['strikes'] == 18
    assert log_payload['stat_correction_count'] == 1
    assert (
        log_payload['last_stat_correction_source']
        == sync_service.POSTGAME_BOXSCORE_CORRECTION_SOURCE
    )
