"""
Regression tests for the daily gameLog lane's finality resolution.

The MLB gameLog endpoint returns splits whose `game` object carries no
`status` block. The lane must resolve finality from the scheduled_games
ledger instead of silently dropping every split (the failure mode that hid
the missed July 4, 2026 slate). An appearance may be skipped only when the
schedule proves the game is not final; anything unprovable is dead-lettered.
"""

from datetime import date

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.prospect  # noqa: F401
import services.sync as sync_service
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from models.sync_failure import SyncFailure
from services.mlb_api import mlb_client
from utils.db import db


NATERA_MLB_ID = 696519
REFERENCE_DATE = date(2026, 7, 5)
JULY_2 = date(2026, 7, 2)
JULY_4 = date(2026, 7, 4)


def _statusless_split(pk, game_date, *, stat_overrides=None):
    stat = {
        'inningsPitched': '1.0',
        'strikes': 8,
        'numberOfPitches': 15,
        'hits': 1,
        'runs': 0,
        'earnedRuns': 0,
        'baseOnBalls': 0,
        'strikeOuts': 2,
        'homeRuns': 0,
    }
    stat.update(stat_overrides or {})
    return {
        # Production shape: gamePk + gameType only, no status block.
        'game': {'gamePk': pk, 'gameType': 'R'},
        'date': game_date.isoformat(),
        'opponent': {'id': 111, 'name': 'Boston Red Sox'},
        'stat': stat,
    }


def _statused_split(pk, game_date, status_code='F', detailed='Final', abstract='Final'):
    split = _statusless_split(pk, game_date)
    split['game']['status'] = {
        'statusCode': status_code,
        'detailedState': detailed,
        'abstractGameState': abstract,
    }
    return split


def _scheduled_game(pk, game_date, state, *, team_id=108, opponent_id=111, **extra):
    return ScheduledGame(
        team_id=team_id,
        game_pk=pk,
        game_date=game_date,
        opponent_team_id=opponent_id,
        home_away='away',
        game_type='R',
        status_code='F' if state == ScheduledGame.STATE_FINAL else 'S',
        status_state=state,
        source='test',
        **extra,
    )


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
            mlb_id=NATERA_MLB_ID,
            full_name='Samy Natera Jr.',
            team_id=108,
            team_abbreviation='LAA',
            active=True,
        )
        db.session.add(pitcher)
        db.session.commit()
        try:
            yield app
        finally:
            db.session.remove()
            drop_test_schema(app)


def _run_sync(monkeypatch, splits, days_back=7):
    monkeypatch.setattr(
        mlb_client, 'get_pitcher_game_logs', lambda mlb_id, season=None: splits
    )
    return sync_service.sync_recent_logs(
        days_back=days_back, reference_date=REFERENCE_DATE
    )


def test_statusless_split_with_final_schedule_is_ingested(app, monkeypatch):
    """Samy Natera reproduction: July 2 stored, July 4 statusless split +
    final schedule row → the July 4 appearance must land."""
    with app.app_context():
        pitcher = Pitcher.query.filter_by(mlb_id=NATERA_MLB_ID).one()
        db.session.add(GameLog(
            pitcher_id=pitcher.id,
            mlb_game_pk=824001,
            game_date=JULY_2,
            innings_pitched=1.0,
            innings_pitched_outs=3,
        ))
        db.session.add(_scheduled_game(824600, JULY_4, ScheduledGame.STATE_FINAL))
        db.session.commit()

        result = _run_sync(monkeypatch, [_statusless_split(824600, JULY_4)])

        rows = (
            GameLog.query.filter_by(pitcher_id=pitcher.id)
            .order_by(GameLog.game_date)
            .all()
        )

    assert result['new_logs_added'] == 1
    assert result['records_failed'] == 0
    assert result['unresolved_finality'] == 0
    assert result['lane_health'] == 'ok'
    assert [row.game_date for row in rows] == [JULY_2, JULY_4]
    assert rows[-1].mlb_game_pk == 824600


def test_statusless_split_with_non_final_schedule_is_skipped_for_retry(app, monkeypatch):
    with app.app_context():
        db.session.add(_scheduled_game(824601, JULY_4, ScheduledGame.STATE_SCHEDULED))
        db.session.add(_scheduled_game(824602, JULY_4, ScheduledGame.STATE_FINAL))
        db.session.commit()

        result = _run_sync(monkeypatch, [
            _statusless_split(824601, JULY_4),
            _statusless_split(824602, JULY_4),
        ])

        stored = [row.mlb_game_pk for row in GameLog.query.all()]

    assert stored == [824602]
    assert result['new_logs_added'] == 1
    assert result['splits_skipped']['not_completed'] == 1
    # Determinately non-final is a clean retry-later skip, not a failure.
    assert result['records_failed'] == 0
    assert result['unresolved_finality'] == 0


def test_statusless_split_with_suspended_schedule_is_not_ingested(app, monkeypatch):
    with app.app_context():
        db.session.add(
            _scheduled_game(824603, JULY_4, ScheduledGame.STATE_SUSPENDED)
        )
        db.session.add(_scheduled_game(824604, JULY_4, ScheduledGame.STATE_FINAL))
        db.session.commit()

        result = _run_sync(monkeypatch, [
            _statusless_split(824603, JULY_4),
            _statusless_split(824604, JULY_4),
        ])

        stored = [row.mlb_game_pk for row in GameLog.query.all()]

    assert stored == [824604]
    assert result['splits_skipped']['not_completed'] == 1


def test_statusless_split_without_schedule_coverage_is_dead_lettered(app, monkeypatch):
    """Unknown finality must never disappear silently: dead-letter + counted."""
    with app.app_context():
        db.session.add(_scheduled_game(824606, JULY_4, ScheduledGame.STATE_FINAL))
        db.session.commit()

        result = _run_sync(monkeypatch, [
            _statusless_split(824605, JULY_4),  # no scheduled_games row
            _statusless_split(824606, JULY_4),
        ])

        stored = [row.mlb_game_pk for row in GameLog.query.all()]
        failures = SyncFailure.query.filter_by(
            entity_type=sync_service.GAME_LOG_UNRESOLVED_FINALITY_ENTITY_TYPE
        ).all()

    assert stored == [824606]
    assert result['unresolved_finality'] == 1
    assert result['records_failed'] == 1
    assert len(failures) == 1
    assert failures[0].entity_ref == '824605'
    assert failures[0].payload['mlb_id'] == NATERA_MLB_ID
    assert failures[0].payload['game_date'] == JULY_4.isoformat()


def test_correction_lane_flows_through_statusless_split(app, monkeypatch):
    """MLB stat revisions must reach existing rows via statusless splits."""
    with app.app_context():
        pitcher = Pitcher.query.filter_by(mlb_id=NATERA_MLB_ID).one()
        db.session.add(GameLog(
            pitcher_id=pitcher.id,
            mlb_game_pk=824607,
            game_date=JULY_4,
            innings_pitched=1.0,
            innings_pitched_outs=3,
            pitches_thrown=15,
            strikeouts=1,
        ))
        db.session.add(_scheduled_game(824607, JULY_4, ScheduledGame.STATE_FINAL))
        db.session.commit()

        result = _run_sync(monkeypatch, [
            _statusless_split(
                824607,
                JULY_4,
                stat_overrides={'numberOfPitches': 18, 'strikeOuts': 3},
            ),
        ])

        row = GameLog.query.filter_by(mlb_game_pk=824607).one()

    assert result['logs_corrected'] == 1
    assert row.pitches_thrown == 18
    assert row.strikeouts == 3
    assert row.stat_correction_count == 1
    assert row.last_stat_correction_source == 'daily_game_log'


def test_statused_final_split_still_ingests_without_schedule_rows(app, monkeypatch):
    """Splits that carry their own final status keep working unchanged."""
    with app.app_context():
        result = _run_sync(monkeypatch, [_statused_split(824608, JULY_4)])
        stored = [row.mlb_game_pk for row in GameLog.query.all()]

    assert stored == [824608]
    assert result['new_logs_added'] == 1
    assert result['lane_health'] == 'ok'


def test_statused_non_final_split_still_skipped(app, monkeypatch):
    with app.app_context():
        db.session.add(_scheduled_game(824610, JULY_4, ScheduledGame.STATE_FINAL))
        db.session.commit()
        result = _run_sync(monkeypatch, [
            _statused_split(824609, JULY_4, 'I', 'In Progress', 'Live'),
            _statusless_split(824610, JULY_4),
        ])
        stored = [row.mlb_game_pk for row in GameLog.query.all()]

    assert stored == [824610]
    assert result['splits_skipped']['not_completed'] == 1


def test_lane_health_canary_fires_when_every_window_split_drops(app, monkeypatch):
    """If every in-window split is dropped, the run must not look healthy."""
    with app.app_context():
        result = _run_sync(monkeypatch, [
            _statusless_split(824611, JULY_4),  # unknown finality
            _statusless_split(824612, JULY_4),  # unknown finality
        ])
        lane_failures = SyncFailure.query.filter_by(
            entity_type=sync_service.DAILY_GAME_LOG_LANE_FAILURE_ENTITY_TYPE
        ).all()

    assert result['new_logs_added'] == 0
    assert result['lane_health'] == 'all_window_splits_dropped'
    # 2 unresolved-finality records + 1 lane-health record.
    assert result['records_failed'] == 3
    assert len(lane_failures) == 1
    assert lane_failures[0].payload['ingestable_splits'] == 2


def test_before_cutoff_splits_do_not_trigger_canary(app, monkeypatch):
    """Offseason shape: whole-season splits older than the window are quiet."""
    with app.app_context():
        result = _run_sync(monkeypatch, [
            _statusless_split(824613, date(2026, 5, 1)),
            _statusless_split(824614, date(2026, 5, 2)),
        ])

    assert result['new_logs_added'] == 0
    assert result['records_failed'] == 0
    assert result['lane_health'] == 'no_window_splits'
    assert result['splits_skipped']['before_cutoff'] == 2
