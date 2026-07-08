"""
Regression tests for postgame trailing-date lookback recovery.

A crashed overnight postgame run (the July 4-5, 2026 mapper-error incident)
must self-heal: the next scheduled run sweeps trailing slate dates and
processes any completed game that never got a fully-processed marker.
"""

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import services.sync as sync_service
from services import sync_metadata
from utils.db import db
from models.game_log import GameLog
from models.play_by_play_foundation import PlayByPlayProcessedGame
from models.postgame_processed_game import PostgameProcessedGame
import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401


SLATE_OLD = date(2026, 7, 3)
SLATE_MISSED = date(2026, 7, 4)
SLATE_TONIGHT = date(2026, 7, 5)


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    monkeypatch.setattr(sync_service, 'recalculate_all_fatigue', lambda reference_date=None: 1)

    def fake_complete(sync_run_id, **kwargs):
        run = sync_metadata.finish_sync_run(
            sync_run_id,
            status=kwargs['final_status'],
            records_processed=kwargs.get('records_processed', 0),
            records_failed=kwargs.get('records_failed', 0),
            source=kwargs.get('source', 'test'),
            started_at=kwargs.get('started_at'),
            job_name=kwargs.get('job_name', sync_metadata.JOB_POSTGAME_REFRESH),
        )
        return run, SimpleNamespace(id=321)

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


def _game(game_pk, official_date):
    return {
        'gamePk': game_pk,
        'gameType': 'R',
        'officialDate': official_date.isoformat(),
        'status': {
            'statusCode': 'F',
            'detailedState': 'Final',
            'abstractGameState': 'Final',
        },
        'teams': {
            'home': {'team': {'id': 1, 'name': 'Home Club'}},
            'away': {'team': {'id': 2, 'name': 'Away Club'}},
        },
    }


def _boxscore(pitcher_id, name):
    return {
        'teams': {
            'home': {
                'team': {'id': 1, 'name': 'Home Club'},
                'pitchers': [pitcher_id],
                'players': {
                    f'ID{pitcher_id}': {
                        'person': {'id': pitcher_id, 'fullName': name},
                        'stats': {
                            'pitching': {
                                'inningsPitched': '1.0',
                                'numberOfPitches': '14',
                                'strikes': '9',
                                'hits': '0',
                                'runs': '0',
                                'earnedRuns': '0',
                                'baseOnBalls': '0',
                                'strikeOuts': '2',
                                'homeRuns': '0',
                            },
                        },
                    },
                },
            },
            'away': {
                'team': {'id': 2, 'name': 'Away Club'},
                'pitchers': [],
                'players': {},
            },
        },
    }


def _patch_mlb(monkeypatch, games_by_date, boxscores_by_game_pk):
    calls = {'schedule_dates': [], 'boxscore': []}

    def fake_schedule(start_date=None, end_date=None, team_id=None):
        assert start_date == end_date
        calls['schedule_dates'].append(start_date)
        return games_by_date.get(start_date, [])

    def fake_boxscore(game_pk):
        calls['boxscore'].append(game_pk)
        return boxscores_by_game_pk[game_pk]

    monkeypatch.setattr(sync_service.mlb_client, 'get_schedule', fake_schedule)
    monkeypatch.setattr(sync_service.mlb_client, 'get_game_boxscore', fake_boxscore)
    monkeypatch.setattr(sync_service.mlb_client, 'get_game_linescore', lambda game_pk: None)
    monkeypatch.setattr(sync_service.mlb_client, 'get_game_play_by_play', lambda game_pk: None)
    sync_service.mlb_client.metrics.reset()
    return calls


def test_postgame_schedule_dates_sweep_oldest_first():
    # 23:00 ET on July 5 → primary slate July 5, sweeping two days back.
    now = datetime(2026, 7, 6, 3, 0, tzinfo=timezone.utc)
    assert sync_service.postgame_schedule_dates(now, lookback_days=2) == [
        SLATE_OLD, SLATE_MISSED, SLATE_TONIGHT,
    ]
    # 01:00 ET on July 6 (hour < cutoff) still anchors to the July 5 slate.
    late = datetime(2026, 7, 6, 5, 0, tzinfo=timezone.utc)
    assert sync_service.postgame_schedule_dates(late, lookback_days=1) == [
        SLATE_MISSED, SLATE_TONIGHT,
    ]


def test_postgame_lookback_days_env_override(monkeypatch):
    monkeypatch.setenv('POSTGAME_LOOKBACK_DAYS', '4')
    assert sync_service._postgame_lookback_days() == 4
    monkeypatch.setenv('POSTGAME_LOOKBACK_DAYS', 'garbage')
    assert (
        sync_service._postgame_lookback_days()
        == sync_service.POSTGAME_DEFAULT_LOOKBACK_DAYS
    )
    monkeypatch.setenv('POSTGAME_LOOKBACK_DAYS', '-3')
    assert sync_service._postgame_lookback_days() == 0


def test_lookback_recovers_missed_slate(app, monkeypatch):
    """Replay after a missed postgame night: the crashed July 4 slate is
    swept and ingested by the next run alongside tonight's slate."""
    monkeypatch.setattr(
        sync_service,
        'postgame_schedule_dates',
        lambda now=None, lookback_days=None: [SLATE_OLD, SLATE_MISSED, SLATE_TONIGHT],
    )
    games_by_date = {
        SLATE_MISSED.isoformat(): [_game(824600, SLATE_MISSED)],
        SLATE_TONIGHT.isoformat(): [_game(824700, SLATE_TONIGHT)],
    }
    boxscores = {
        824600: _boxscore(696519, 'Samy Natera Jr.'),
        824700: _boxscore(555555, 'Tonight Reliever'),
    }
    calls = _patch_mlb(monkeypatch, games_by_date, boxscores)

    status = sync_service.run_postgame_refresh(app, source='test')

    assert status['status'] == sync_metadata.STATUS_SUCCESS
    assert status['schedule_dates'] == [
        SLATE_OLD.isoformat(), SLATE_MISSED.isoformat(), SLATE_TONIGHT.isoformat(),
    ]
    assert status['schedule_date'] == SLATE_TONIGHT.isoformat()
    assert status['completed_games_found'] == 2
    assert status['games_processed'] == 2
    assert sorted(calls['boxscore'][:2]) == [824600, 824700]

    with app.app_context():
        recovered = GameLog.query.filter_by(mlb_game_pk=824600).one()
        assert recovered.game_date == SLATE_MISSED
        assert GameLog.query.filter_by(mlb_game_pk=824700).count() == 1
        markers = {
            marker.mlb_game_pk: marker
            for marker in PostgameProcessedGame.query.all()
        }
        assert markers[824600].processing_status == (
            PostgameProcessedGame.STATUS_FULLY_PROCESSED
        )
        assert markers[824600].game_date == SLATE_MISSED


def test_lookback_skips_fully_processed_old_slates_without_refetch(app, monkeypatch):
    """Re-sweeping an already-ingested slate must not refetch its boxscores."""
    monkeypatch.setattr(
        sync_service,
        'postgame_schedule_dates',
        lambda now=None, lookback_days=None: [SLATE_MISSED, SLATE_TONIGHT],
    )
    with app.app_context():
        db.session.add(PostgameProcessedGame(
            mlb_game_pk=824600,
            game_date=SLATE_MISSED,
            processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
            attempt_count=1,
        ))
        db.session.add(PlayByPlayProcessedGame(
            mlb_game_pk=824600,
            game_date=SLATE_MISSED,
            processing_status=PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED,
            attempt_count=1,
            source='test',
            source_endpoint='test',
        ))
        db.session.commit()

    games_by_date = {
        SLATE_MISSED.isoformat(): [_game(824600, SLATE_MISSED)],
        SLATE_TONIGHT.isoformat(): [_game(824700, SLATE_TONIGHT)],
    }
    boxscores = {824700: _boxscore(555555, 'Tonight Reliever')}
    calls = _patch_mlb(monkeypatch, games_by_date, boxscores)

    status = sync_service.run_postgame_refresh(app, source='test')

    assert status['games_already_processed'] == 1
    assert status['games_processed'] == 1
    assert 824600 not in calls['boxscore']


def test_explicit_schedule_date_restricts_sweep(app, monkeypatch):
    """Manual replays (--date) inspect exactly the requested slate."""
    games_by_date = {
        SLATE_MISSED.isoformat(): [_game(824600, SLATE_MISSED)],
    }
    boxscores = {824600: _boxscore(696519, 'Samy Natera Jr.')}
    calls = _patch_mlb(monkeypatch, games_by_date, boxscores)

    status = sync_service.run_postgame_refresh(
        app, schedule_date=SLATE_MISSED, source='test',
    )

    assert calls['schedule_dates'] == [SLATE_MISSED.isoformat()]
    assert status['schedule_dates'] == [SLATE_MISSED.isoformat()]
    assert status['games_processed'] == 1
    with app.app_context():
        assert GameLog.query.filter_by(mlb_game_pk=824600).count() == 1
