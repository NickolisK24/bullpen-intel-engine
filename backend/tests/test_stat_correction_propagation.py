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
from utils.db import db


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    monkeypatch.setattr(mlb_client, 'get_game_pitching_lines', lambda game_pk: [])
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        create_test_schema(app)
        pitcher = Pitcher(
            mlb_id=101,
            full_name='Correction Reliever',
            team_id=1,
            team_abbreviation='COR',
            active=True,
        )
        db.session.add(pitcher)
        db.session.commit()
        try:
            yield app
        finally:
            db.session.remove()
            drop_test_schema(app)


def _status(status_code='F', detailed_state='Final', abstract_state='Final'):
    return {
        'statusCode': status_code,
        'detailedState': detailed_state,
        'abstractGameState': abstract_state,
    }


def _daily_stat(**overrides):
    stat = {
        'inningsPitched': '1.0',
        'numberOfPitches': 12,
        'strikes': 8,
        'hits': 0,
        'runs': 0,
        'earnedRuns': 0,
        'baseOnBalls': 0,
        'strikeOuts': 2,
        'homeRuns': 0,
        'gamesStarted': 0,
        'holds': 1,
    }
    missing = set(overrides.pop('missing', ()))
    stat.update(overrides)
    for key in missing:
        stat.pop(key, None)
    return stat


def _split(game_pk, *, stat=None, game_date=date(2026, 6, 10)):
    return {
        'game': {
            'gamePk': game_pk,
            'gameType': 'R',
            'status': _status(),
        },
        'date': game_date.isoformat(),
        'opponent': {'id': 2, 'name': 'Opponent Club'},
        'stat': stat if stat is not None else _daily_stat(),
    }


def _game(game_pk=9901):
    return {
        'gamePk': game_pk,
        'gameType': 'R',
        'officialDate': '2026-06-10',
        'status': _status(),
        'teams': {
            'home': {'team': {'id': 1, 'name': 'Correction Club'}},
            'away': {'team': {'id': 2, 'name': 'Opponent Club'}},
        },
    }


def _boxscore(stat):
    return {
        'teams': {
            'home': {
                'team': {'id': 1, 'name': 'Correction Club'},
                'pitchers': [101],
                'players': {
                    'ID101': {
                        'person': {'fullName': 'Correction Reliever'},
                        'stats': {'pitching': stat},
                    },
                },
            },
            'away': {
                'team': {'id': 2, 'name': 'Opponent Club'},
                'pitchers': [],
                'players': {},
            },
        },
    }


def _pitcher():
    return Pitcher.query.filter_by(mlb_id=101).one()


def _seed_log(*, game_pk=9901, pitches=12, strikes=8, walks=0, strikeouts=2, runs=0):
    pitcher = _pitcher()
    log = GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
        game_date=date(2026, 6, 10),
        game_type='R',
        opponent='Opponent Club',
        opponent_abbreviation='OPP',
        games_started=0,
        innings_pitched=1.0,
        innings_pitched_outs=3,
        pitches_thrown=pitches,
        strikes=strikes,
        hits_allowed=0,
        runs_allowed=runs,
        earned_runs=runs,
        walks=walks,
        strikeouts=strikeouts,
        home_runs_allowed=0,
        hold=True,
    )
    db.session.add(log)
    db.session.commit()
    return log


def test_daily_correction_updates_existing_pitch_count_and_provenance(app, monkeypatch):
    with app.app_context():
        _seed_log(game_pk=9901, pitches=12)
        sync_run_id = sync_metadata.start_sync_run(source='test')
        monkeypatch.setattr(
            mlb_client,
            'get_pitcher_game_logs',
            lambda mlb_id, season=None: [
                _split(9901, stat=_daily_stat(numberOfPitches=27, strikes=18))
            ],
        )

        result = sync_service.sync_recent_logs(
            days_back=7,
            reference_date=date(2026, 6, 10),
            sync_run_id=sync_run_id,
        )
        log = GameLog.query.filter_by(mlb_game_pk=9901).one()
        log_count = GameLog.query.count()
        failure_count = SyncFailure.query.count()

    assert result['new_logs_added'] == 0
    assert result['logs_corrected'] == 1
    assert log_count == 1
    assert failure_count == 0
    assert log.pitches_thrown == 27
    assert log.strikes == 18
    assert log.stat_correction_count == 1
    assert log.last_stat_correction_source == sync_service.DAILY_GAME_LOG_CORRECTION_SOURCE
    assert log.last_stat_correction_sync_run_id == sync_run_id
    assert log.last_stat_correction_at is not None


def test_daily_correction_updates_revised_rate_stats(app, monkeypatch):
    with app.app_context():
        _seed_log(game_pk=9902, pitches=16, walks=0, strikeouts=1, runs=0)
        monkeypatch.setattr(
            mlb_client,
            'get_pitcher_game_logs',
            lambda mlb_id, season=None: [
                _split(
                    9902,
                    stat=_daily_stat(
                        numberOfPitches=16,
                        baseOnBalls=2,
                        strikeOuts=3,
                        runs=1,
                        earnedRuns=1,
                    ),
                )
            ],
        )

        result = sync_service.sync_recent_logs(
            days_back=7,
            reference_date=date(2026, 6, 10),
        )
        log = GameLog.query.filter_by(mlb_game_pk=9902).one()

    assert result['logs_corrected'] == 1
    assert log.walks == 2
    assert log.strikeouts == 3
    assert log.runs_allowed == 1
    assert log.earned_runs == 1
    assert log.pitches_thrown == 16
    assert log.stat_correction_count == 1


def test_daily_identical_authoritative_line_is_noop(app, monkeypatch):
    with app.app_context():
        _seed_log(game_pk=9903, pitches=12, strikes=8, walks=0, strikeouts=2)
        monkeypatch.setattr(
            mlb_client,
            'get_pitcher_game_logs',
            lambda mlb_id, season=None: [_split(9903, stat=_daily_stat())],
        )

        result = sync_service.sync_recent_logs(
            days_back=7,
            reference_date=date(2026, 6, 10),
        )
        log = GameLog.query.filter_by(mlb_game_pk=9903).one()
        failure_count = SyncFailure.query.count()

    assert result['new_logs_added'] == 0
    assert result['logs_corrected'] == 0
    assert result['records_failed'] == 0
    assert log.stat_correction_count == 0
    assert log.last_stat_correction_at is None
    assert failure_count == 0


def test_daily_partial_source_does_not_overwrite_existing_good_data(app, monkeypatch):
    with app.app_context():
        _seed_log(game_pk=9904, pitches=18, strikes=12, walks=1, strikeouts=4, runs=0)
        sync_run_id = sync_metadata.start_sync_run(source='test')
        monkeypatch.setattr(
            mlb_client,
            'get_pitcher_game_logs',
            lambda mlb_id, season=None: [
                _split(
                    9904,
                    stat={
                        'inningsPitched': '1.0',
                        'numberOfPitches': 1,
                    },
                )
            ],
        )

        result = sync_service.sync_recent_logs(
            days_back=7,
            reference_date=date(2026, 6, 10),
            sync_run_id=sync_run_id,
        )
        log = GameLog.query.filter_by(mlb_game_pk=9904).one()
        failure = SyncFailure.query.one()

    assert result['logs_corrected'] == 0
    assert result['records_failed'] == 1
    assert result['correction_attempts_failed'] == 1
    assert log.pitches_thrown == 18
    assert log.strikes == 12
    assert log.walks == 1
    assert log.strikeouts == 4
    assert log.stat_correction_count == 0
    assert failure.entity_type == sync_service.GAME_LOG_CORRECTION_FAILURE_ENTITY_TYPE
    assert failure.job_name == sync_metadata.JOB_DAILY_SYNC
    assert failure.payload['reason'] == 'partial_source_line'
    assert 'strikes' in failure.payload['missing_keys']


def test_daily_complete_source_without_pitch_count_corrects_to_unknown(app, monkeypatch):
    with app.app_context():
        _seed_log(game_pk=9905, pitches=18, strikes=12, walks=1, strikeouts=4, runs=0)
        monkeypatch.setattr(
            mlb_client,
            'get_pitcher_game_logs',
            lambda mlb_id, season=None: [
                _split(
                    9905,
                    stat=_daily_stat(
                        missing=('numberOfPitches', 'holds'),
                        strikes=12,
                        baseOnBalls=1,
                        strikeOuts=4,
                    ),
                )
            ],
        )

        result = sync_service.sync_recent_logs(
            days_back=7,
            reference_date=date(2026, 6, 10),
        )
        log = GameLog.query.filter_by(mlb_game_pk=9905).one()

    assert result['logs_corrected'] == 1
    assert log.pitches_thrown is None
    assert log.hold is True
    assert log.stat_correction_count == 1


def test_postgame_boxscore_correction_updates_existing_row(app, monkeypatch):
    with app.app_context():
        _seed_log(game_pk=9906, pitches=12, strikes=8)
        stat = _daily_stat(numberOfPitches=31, strikes=20, avgLI='1.7')
        monkeypatch.setattr(
            mlb_client,
            'get_game_boxscore',
            lambda game_pk: _boxscore(stat),
        )

        result = sync_service.process_completed_game_for_postgame_refresh(
            _game(9906),
            schedule_date=date(2026, 6, 10),
        )
        db.session.commit()
        log = GameLog.query.filter_by(mlb_game_pk=9906).one()
        marker = PostgameProcessedGame.query.filter_by(mlb_game_pk=9906).one()

    assert result['logs_added'] == 0
    assert result['logs_corrected'] == 1
    assert result['correction_attempts_failed'] == 0
    assert result['pitchers_touched'] == 1
    assert log.pitches_thrown == 31
    assert log.strikes == 20
    assert log.leverage_index == 1.7
    assert log.last_stat_correction_source == sync_service.POSTGAME_BOXSCORE_CORRECTION_SOURCE
    assert marker.logs_added == 0
    assert marker.pitchers_touched == 1


def test_postgame_partial_boxscore_correction_is_dead_lettered(app, monkeypatch):
    with app.app_context():
        _seed_log(game_pk=9907, pitches=22, strikes=14)
        monkeypatch.setattr(
            mlb_client,
            'get_game_boxscore',
            lambda game_pk: _boxscore({
                'inningsPitched': '1.0',
                'numberOfPitches': 1,
            }),
        )

        result = sync_service.process_completed_game_for_postgame_refresh(
            _game(9907),
            schedule_date=date(2026, 6, 10),
        )
        db.session.commit()
        log = GameLog.query.filter_by(mlb_game_pk=9907).one()
        failure = SyncFailure.query.one()

    assert result['logs_added'] == 0
    assert result['logs_corrected'] == 0
    assert result['correction_attempts_failed'] == 1
    assert log.pitches_thrown == 22
    assert log.strikes == 14
    assert log.stat_correction_count == 0
    assert failure.entity_type == sync_service.GAME_LOG_CORRECTION_FAILURE_ENTITY_TYPE
    assert failure.job_name == sync_metadata.JOB_POSTGAME_REFRESH
