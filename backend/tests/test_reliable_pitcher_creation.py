from datetime import date, datetime

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
from services.bullpen_population import eligible_bullpen_pitcher_contexts
from services import sync_metadata
from services.mlb_api import mlb_client
from services.roster_status import STATUS_IL_15, STATUS_MINORS, STATUS_UNKNOWN
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


def _game(game_pk=8101, *, status=None):
    return {
        'gamePk': game_pk,
        'gameType': 'R',
        'officialDate': '2026-06-20',
        'status': status or _status(),
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
    primary_position = (
        position
        if isinstance(position, dict)
        else {'abbreviation': position}
    )
    return {
        'person': {
            'id': person_id if person_id is not None else player_id,
            'fullName': name,
            'primaryPosition': primary_position,
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
    assert pitcher_payload['roster_status'] == STATUS_UNKNOWN
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
    assert pitcher_payload['roster_status'] == STATUS_UNKNOWN
    assert pitches_thrown == 14


def test_postgame_line_does_not_override_official_inactive_roster_status(app, monkeypatch):
    with app.app_context():
        pitcher = Pitcher(
            mlb_id=405,
            full_name='Official IL Reliever',
            team_id=1,
            team_name='Home Club',
            team_abbreviation='HME',
            team_assignment_status='ASSIGNED',
            team_assignment_source='mlb_stats_api:team_assignment_sync:active',
            team_assignment_updated_at=datetime(2026, 6, 20, 10, 0, 0),
            position='P',
            active=True,
            roster_status=STATUS_IL_15,
            roster_status_source='mlb_stats_api:roster_sync:fullRoster',
            roster_status_updated_at=datetime(2026, 6, 20, 10, 0, 0),
        )
        db.session.add(pitcher)
        db.session.commit()
        monkeypatch.setattr(
            mlb_client,
            'get_game_boxscore',
            lambda game_pk: _boxscore(player_id=405, name='Official IL Reliever'),
        )

        result = sync_service.process_completed_game_for_postgame_refresh(
            _game(8107),
            schedule_date=date(2026, 6, 20),
        )
        db.session.commit()
        refreshed = Pitcher.query.filter_by(mlb_id=405).one()
        log = GameLog.query.filter_by(pitcher_id=refreshed.id, mlb_game_pk=8107).one()

    assert result['logs_added'] == 1
    assert log.pitches_thrown == 14
    assert refreshed.roster_status == STATUS_IL_15
    assert refreshed.roster_status_source == 'mlb_stats_api:roster_sync:fullRoster'


def test_authoritative_two_way_pitching_line_ingests_without_bullpen_overclaim(
    app,
    monkeypatch,
):
    with app.app_context():
        stats = _stat(
            inningsPitched='5.0',
            numberOfPitches=87,
            holds=0,
            gamesStarted=1,
        )
        boxscores = [
            _boxscore(
                player_id=660271,
                name='Shohei Ohtani',
                stats=stats,
                position={
                    'code': 'O',
                    'name': 'Designated Hitter',
                    'abbreviation': 'DH',
                },
                team_id=1,
                team_name='Los Angeles Dodgers',
                team_abbreviation='LAD',
            ),
            _boxscore(
                player_id=660271,
                name='Shohei Ohtani',
                stats=stats,
                position={
                    'code': 'O',
                    'name': 'Designated Hitter',
                    'abbreviation': 'DH',
                },
                team_id=1,
                team_name='Los Angeles Dodgers',
                team_abbreviation='LAD',
            ),
        ]
        monkeypatch.setattr(
            mlb_client,
            'get_game_boxscore',
            lambda game_pk: boxscores.pop(0),
        )

        first = sync_service.process_completed_game_for_postgame_refresh(
            _game(823933),
            schedule_date=date(2026, 6, 20),
        )
        db.session.commit()
        _delete_marker(823933)
        second = sync_service.process_completed_game_for_postgame_refresh(
            _game(823933),
            schedule_date=date(2026, 6, 20),
        )
        db.session.commit()

        pitcher = Pitcher.query.filter_by(mlb_id=660271).one()
        log = GameLog.query.filter_by(pitcher_id=pitcher.id, mlb_game_pk=823933).one()
        contexts = eligible_bullpen_pitcher_contexts(
            [pitcher],
            logs_by_pitcher={pitcher.id: [log]},
            reference_date=date(2026, 6, 21),
        )
        failure_count = SyncFailure.query.count()
        pitcher_count = Pitcher.query.filter_by(mlb_id=660271).count()
        log_count = GameLog.query.filter_by(
            pitcher_id=pitcher.id,
            mlb_game_pk=823933,
        ).count()
        pitcher_payload = {
            'full_name': pitcher.full_name,
            'position': pitcher.position,
            'roster_status': pitcher.roster_status,
            'roster_status_raw_description': pitcher.roster_status_raw_description,
        }
        log_payload = {
            'games_started': log.games_started,
            'pitches_thrown': log.pitches_thrown,
        }

    assert first['pitcher_resolution_failures'] == 0
    assert first['logs_added'] == 1
    assert first['position_overrides_from_pitching_line'] == 1
    assert second['pitcher_resolution_failures'] == 0
    assert second['logs_added'] == 0
    assert second['logs_corrected'] == 0
    assert second['position_overrides_from_pitching_line'] == 1
    assert failure_count == 0
    assert pitcher_count == 1
    assert log_count == 1
    assert pitcher_payload['full_name'] == 'Shohei Ohtani'
    assert pitcher_payload['position'] == 'DH'
    assert pitcher_payload['roster_status'] == STATUS_UNKNOWN
    assert (
        pitcher_payload['roster_status_raw_description']
        == 'Final-game pitching line; current roster status unverified; position_override_from_pitching_line'
    )
    assert log_payload['games_started'] == 1
    assert log_payload['pitches_thrown'] == 87
    assert contexts == []


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


def test_conflicting_player_identity_is_dead_lettered(app, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(
            mlb_client,
            'get_game_boxscore',
            lambda game_pk: _boxscore(
                player_id=707,
                person_id=808,
                name='Conflicted Identity',
            ),
        )

        result = sync_service.process_completed_game_for_postgame_refresh(
            _game(8106),
            schedule_date=date(2026, 6, 20),
        )
        db.session.commit()
        failure = SyncFailure.query.one()
        pitcher_count = Pitcher.query.count()
        log_count = GameLog.query.count()

    assert result['pitcher_resolution_failures'] == 1
    assert result['logs_added'] == 0
    assert pitcher_count == 0
    assert log_count == 0
    assert failure.entity_type == sync_service.PITCHER_RESOLUTION_FAILURE_ENTITY_TYPE
    assert failure.payload['reason'] == 'conflicting_player_identity'
    assert failure.payload['player_id'] == 707
    assert failure.payload['person_id'] == 808


def test_missing_player_name_is_dead_lettered(app, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(
            mlb_client,
            'get_game_boxscore',
            lambda game_pk: _boxscore(player_id=909, name=None),
        )

        result = sync_service.process_completed_game_for_postgame_refresh(
            _game(8107),
            schedule_date=date(2026, 6, 20),
        )
        db.session.commit()
        failure = SyncFailure.query.one()
        pitcher_count = Pitcher.query.count()
        log_count = GameLog.query.count()

    assert result['pitcher_resolution_failures'] == 1
    assert result['logs_added'] == 0
    assert pitcher_count == 0
    assert log_count == 0
    assert failure.entity_type == sync_service.PITCHER_RESOLUTION_FAILURE_ENTITY_TYPE
    assert failure.payload['reason'] == 'missing_player_name'
    assert failure.payload['player_id'] == 909


def test_non_final_non_pitcher_line_still_fails_closed(app):
    with app.app_context():
        line = {
            'player_id': 1009,
            'person_id': 1009,
            'name': 'Position Player',
            'side': 'home',
            'team_id': 1,
            'team': 'Home Club',
            'position': 'DH',
            'source': sync_service.POSTGAME_PITCHER_RESOLUTION_SOURCE,
            'authority': sync_service.POSTGAME_PITCHING_LINE_AUTHORITY,
            'stats': _stat(numberOfPitches=12),
        }

        result = sync_service.resolve_pitcher_for_authoritative_line(
            line,
            _game(
                8108,
                status={
                    'statusCode': 'I',
                    'detailedState': 'In Progress',
                    'abstractGameState': 'Live',
                },
            ),
        )
        db.session.commit()
        failure = SyncFailure.query.one()
        pitcher_count = Pitcher.query.count()

    assert result['pitcher'] is None
    assert result['reason'] == 'non_pitcher_position'
    assert pitcher_count == 0
    assert failure.entity_type == sync_service.PITCHER_RESOLUTION_FAILURE_ENTITY_TYPE
    assert failure.payload['reason'] == 'non_pitcher_position'


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
