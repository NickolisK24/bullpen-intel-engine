from datetime import date
from types import SimpleNamespace

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
import services.sync as sync_service
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.sync_failure import SyncFailure
from services import sync_metadata
from utils.db import db


SCHEDULE_DATE = date(2026, 6, 20)


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    monkeypatch.setattr(sync_service, 'recalculate_all_fatigue', lambda reference_date=None: 2)
    monkeypatch.setenv('POSTGAME_REFRESH_SNAPSHOT', 'false')

    def fake_complete(sync_run_id, **kwargs):
        run = sync_metadata.finish_sync_run(
            sync_run_id,
            status=kwargs['final_status'],
            records_processed=kwargs.get('records_processed', 0),
            records_failed=kwargs.get('records_failed', 0),
            new_logs_added=kwargs.get('new_logs_added', 0),
            pitchers_updated=kwargs.get('pitchers_updated', 0),
            errors=kwargs.get('errors', 0),
            api_calls_made=kwargs.get('api_calls_made', 0),
            retries_used=kwargs.get('retries_used', 0),
            error_message=kwargs.get('error_message'),
            source=kwargs.get('source', 'test'),
            started_at=kwargs.get('started_at'),
            job_name=kwargs.get('job_name', sync_metadata.JOB_POSTGAME_REFRESH),
        )
        return run, SimpleNamespace(id=123)

    monkeypatch.setattr(sync_service, 'complete_sync_run_with_snapshot', fake_complete)

    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _game(game_pk=7001):
    return {
        'gamePk': game_pk,
        'gameType': 'R',
        'officialDate': SCHEDULE_DATE.isoformat(),
        'status': {
            'statusCode': 'F',
            'detailedState': 'Final',
            'abstractGameState': 'Final',
        },
        'teams': {
            'home': {'team': {'id': 1, 'name': 'Home Club', 'abbreviation': 'HME'}},
            'away': {'team': {'id': 2, 'name': 'Away Club', 'abbreviation': 'AWY'}},
        },
    }


def _seed_pitchers():
    db.session.add_all([
        Pitcher(
            mlb_id=101,
            full_name='Home Reliever',
            team_id=1,
            team_abbreviation='HME',
            position='P',
            active=True,
        ),
        Pitcher(
            mlb_id=202,
            full_name='Away Reliever',
            team_id=2,
            team_abbreviation='AWY',
            position='P',
            active=True,
        ),
    ])
    db.session.commit()


def _stat(**overrides):
    stat = {
        'inningsPitched': '1.0',
        'numberOfPitches': '14',
        'strikes': '9',
        'hits': '0',
        'runs': '0',
        'earnedRuns': '0',
        'baseOnBalls': '0',
        'strikeOuts': '2',
        'homeRuns': '0',
        'holds': '1',
        'avgLI': '1.25',
    }
    stat.update(overrides)
    return stat


def _player(player_id, *, name, stats=None, person_id=None):
    return {
        'person': {
            'id': person_id if person_id is not None else player_id,
            'fullName': name,
            'primaryPosition': {'abbreviation': 'P'},
        },
        'stats': {'pitching': stats if stats is not None else _stat()},
    }


def _valid_boxscore():
    return {
        'teams': {
            'home': {
                'team': {'id': 1, 'name': 'Home Club', 'abbreviation': 'HME'},
                'pitchers': [101],
                'players': {
                    'ID101': _player(101, name='Home Reliever'),
                },
            },
            'away': {
                'team': {'id': 2, 'name': 'Away Club', 'abbreviation': 'AWY'},
                'pitchers': [202],
                'players': {
                    'ID202': _player(
                        202,
                        name='Away Reliever',
                        stats=_stat(inningsPitched='0.2', numberOfPitches='11'),
                    ),
                },
            },
        },
    }


def _empty_boxscore():
    return {
        'teams': {
            'home': {
                'team': {'id': 1, 'name': 'Home Club', 'abbreviation': 'HME'},
                'pitchers': [],
                'players': {},
            },
            'away': {
                'team': {'id': 2, 'name': 'Away Club', 'abbreviation': 'AWY'},
                'pitchers': [],
                'players': {},
            },
        },
    }


def _partial_unresolved_boxscore():
    boxscore = _valid_boxscore()
    boxscore['teams']['away']['pitchers'] = ['BAD']
    boxscore['teams']['away']['players'] = {
        'IDBAD': _player(
            'BAD',
            name='Unresolved Reliever',
            person_id=None,
            stats=_stat(inningsPitched='0.2', numberOfPitches='11'),
        ),
    }
    return boxscore


def _patch_mlb(monkeypatch, *, boxscores):
    calls = {'schedule': 0, 'boxscore': []}
    queued_boxscores = list(boxscores)

    def fake_schedule(start_date=None, end_date=None, team_id=None):
        calls['schedule'] += 1
        assert start_date == SCHEDULE_DATE.isoformat()
        assert end_date == SCHEDULE_DATE.isoformat()
        assert team_id is None
        return [_game()]

    def fake_boxscore(game_pk):
        calls['boxscore'].append(game_pk)
        if queued_boxscores:
            next_boxscore = queued_boxscores.pop(0)
            return next_boxscore() if callable(next_boxscore) else next_boxscore
        return _valid_boxscore()

    monkeypatch.setattr(sync_service.mlb_client, 'get_schedule', fake_schedule)
    monkeypatch.setattr(sync_service.mlb_client, 'get_game_boxscore', fake_boxscore)
    monkeypatch.setattr(sync_service.mlb_client, 'get_game_linescore', lambda game_pk: None)
    monkeypatch.setattr(sync_service.mlb_client, 'get_game_play_by_play', lambda game_pk: None)
    sync_service.mlb_client.metrics.reset()
    return calls


def _run(app):
    return sync_service.run_postgame_refresh(
        app,
        schedule_date=SCHEDULE_DATE,
        source='test',
    )


def _marker_payload():
    marker = PostgameProcessedGame.query.filter_by(mlb_game_pk=7001).one()
    return {
        'processing_status': marker.processing_status,
        'attempt_count': marker.attempt_count,
        'incomplete_reason': marker.incomplete_reason,
        'pitching_lines_seen': marker.pitching_lines_seen,
        'pitcher_resolution_failures': marker.pitcher_resolution_failures,
        'processed_at': marker.processed_at,
        'failed_at': marker.failed_at,
    }


def test_empty_final_boxscore_remains_retryable_and_later_closes(app, monkeypatch):
    with app.app_context():
        _seed_pitchers()
    calls = _patch_mlb(monkeypatch, boxscores=[_empty_boxscore, _valid_boxscore])

    first = _run(app)
    with app.app_context():
        first_marker = _marker_payload()
        first_log_count = GameLog.query.count()

    second = _run(app)
    with app.app_context():
        final_marker = _marker_payload()
        logs = GameLog.query.order_by(GameLog.pitcher_id).all()

    assert first['status'] == sync_metadata.STATUS_FAILED
    assert first['games_incomplete'] == 1
    assert first['records_failed'] == 1
    assert first_marker['processing_status'] == sync_service.POSTGAME_MARKER_STATUS_INCOMPLETE
    assert first_marker['attempt_count'] == 1
    assert first_marker['incomplete_reason'] == 'empty_pitching_data'
    assert first_marker['pitching_lines_seen'] == 0
    assert first_marker['processed_at'] is None
    assert first_log_count == 0
    assert second['status'] == sync_metadata.STATUS_SUCCESS
    assert second['games_retryable_incomplete'] == 1
    assert second['games_processed'] == 1
    assert second['new_logs_added'] == 2
    assert final_marker['processing_status'] == sync_service.POSTGAME_MARKER_STATUS_FULLY_PROCESSED
    assert final_marker['attempt_count'] == 2
    assert final_marker['incomplete_reason'] is None
    assert final_marker['processed_at'] is not None
    assert len(logs) == 2
    assert calls['boxscore'] == [7001, 7001]


def test_partial_unresolved_boxscore_retries_without_duplicate_logs(app, monkeypatch):
    with app.app_context():
        _seed_pitchers()
    calls = _patch_mlb(
        monkeypatch,
        boxscores=[_partial_unresolved_boxscore, _partial_unresolved_boxscore],
    )

    first = _run(app)
    second = _run(app)

    with app.app_context():
        marker = _marker_payload()
        logs = GameLog.query.all()
        failures = SyncFailure.query.filter_by(
            entity_type=sync_service.PITCHER_RESOLUTION_FAILURE_ENTITY_TYPE
        ).all()

    assert first['new_logs_added'] == 1
    assert first['pitcher_resolution_failures'] == 1
    assert second['new_logs_added'] == 0
    assert second['pitcher_resolution_failures'] == 1
    assert marker['processing_status'] == sync_service.POSTGAME_MARKER_STATUS_INCOMPLETE
    assert marker['attempt_count'] == 2
    assert marker['incomplete_reason'] == 'pitcher_resolution_failures'
    assert marker['pitching_lines_seen'] == 2
    assert marker['pitcher_resolution_failures'] == 1
    assert len(logs) == 1
    assert len(failures) == 2
    assert calls['boxscore'] == [7001, 7001]


def test_fully_ingested_game_is_closed_and_not_reprocessed(app, monkeypatch):
    with app.app_context():
        _seed_pitchers()
    calls = _patch_mlb(monkeypatch, boxscores=[_valid_boxscore])

    first = _run(app)
    second = _run(app)

    with app.app_context():
        marker = _marker_payload()
        log_count = GameLog.query.count()

    assert first['status'] == sync_metadata.STATUS_SUCCESS
    assert first['games_processed'] == 1
    assert first['new_logs_added'] == 2
    assert marker['processing_status'] == sync_service.POSTGAME_MARKER_STATUS_FULLY_PROCESSED
    assert marker['attempt_count'] == 1
    assert marker['incomplete_reason'] is None
    assert marker['pitching_lines_seen'] == 2
    assert second['new_logs_added'] == 0
    assert second['games_already_processed'] == 1
    assert log_count == 2
    assert calls['boxscore'] == [7001]


def test_repeated_incomplete_attempts_stop_at_visible_failed_marker(app, monkeypatch):
    with app.app_context():
        _seed_pitchers()
    calls = _patch_mlb(
        monkeypatch,
        boxscores=[_empty_boxscore, _empty_boxscore, _empty_boxscore],
    )

    first = _run(app)
    second = _run(app)
    third = _run(app)
    fourth = _run(app)

    with app.app_context():
        marker = _marker_payload()
        failures = SyncFailure.query.filter_by(
            entity_type=sync_service.POSTGAME_GAME_FAILURE_ENTITY_TYPE
        ).all()
        log_count = GameLog.query.count()

    assert first['games_incomplete'] == 1
    assert second['games_retryable_incomplete'] == 1
    assert third['postgame_retry_exhausted'] == 1
    assert marker['processing_status'] == sync_service.POSTGAME_MARKER_STATUS_FAILED
    assert marker['attempt_count'] == sync_service.POSTGAME_MARKER_RETRY_LIMIT
    assert marker['incomplete_reason'] == 'empty_pitching_data'
    assert marker['failed_at'] is not None
    assert len(failures) == 1
    assert failures[0].payload['retry_limit'] == sync_service.POSTGAME_MARKER_RETRY_LIMIT
    assert fourth['newly_completed_games'] == 0
    assert fourth['games_failed_markers'] == 1
    assert log_count == 0
    assert calls['boxscore'] == [7001, 7001, 7001]
