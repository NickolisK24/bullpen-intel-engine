from datetime import date

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from services import sync as sync_service
from services.postgame_recovery import (
    MISSING_APPEARANCE_ROWS_REASON,
    reset_fully_processed_markers_without_appearance_rows,
)
from utils.db import db


SLATE_DATE = date(2026, 7, 23)


@pytest.fixture
def app():
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


def _game(game_pk):
    return {
        'gamePk': game_pk,
        'officialDate': SLATE_DATE.isoformat(),
        'status': {
            'statusCode': 'F',
            'detailedState': 'Final',
            'abstractGameState': 'Final',
        },
    }


def _marker(game_pk):
    return PostgameProcessedGame(
        mlb_game_pk=game_pk,
        game_date=SLATE_DATE,
        processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
        attempt_count=1,
        pitching_lines_seen=8,
        logs_added=8,
    )


def test_closed_marker_without_appearance_rows_is_reopened_and_selected(app):
    with app.app_context():
        marker = _marker(823042)
        db.session.add(marker)
        db.session.commit()

        result = reset_fully_processed_markers_without_appearance_rows(
            schedule_dates=[SLATE_DATE],
        )
        db.session.refresh(marker)
        pending, counts = sync_service._unprocessed_completed_games([_game(823042)])

        assert result['status'] == 'reset'
        assert result['markers_reset'] == 1
        assert result['reset_game_pks'] == [823042]
        assert marker.processing_status == PostgameProcessedGame.STATUS_INCOMPLETE
        assert marker.attempt_count == 0
        assert marker.incomplete_reason == MISSING_APPEARANCE_ROWS_REASON
        assert marker.processed_at is None
        assert [game['gamePk'] for game in pending] == [823042]
        assert counts['retryable_incomplete'] == 1
        assert counts['fully_processed'] == 0


def test_closed_marker_with_appearance_rows_remains_closed(app):
    with app.app_context():
        pitcher = Pitcher(
            mlb_id=999001,
            full_name='Represented Pitcher',
            team_id=109,
            team_abbreviation='ARI',
            position='P',
            active=True,
        )
        marker = _marker(823043)
        db.session.add_all([pitcher, marker])
        db.session.flush()
        db.session.add(GameLog(
            pitcher_id=pitcher.id,
            mlb_game_pk=823043,
            game_date=SLATE_DATE,
            innings_pitched=1.0,
            innings_pitched_outs=3,
        ))
        db.session.commit()

        result = reset_fully_processed_markers_without_appearance_rows(
            schedule_dates=[SLATE_DATE],
        )
        db.session.refresh(marker)
        pending, counts = sync_service._unprocessed_completed_games([_game(823043)])

        assert result['status'] == 'no_inconsistent_markers'
        assert result['markers_reset'] == 0
        assert marker.processing_status == PostgameProcessedGame.STATUS_FULLY_PROCESSED
        assert pending == []
        assert counts['fully_processed'] == 1


def test_recovery_is_bounded_to_requested_schedule_dates(app):
    other_date = date(2026, 7, 22)
    with app.app_context():
        marker = PostgameProcessedGame(
            mlb_game_pk=823044,
            game_date=other_date,
            processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
            attempt_count=1,
            pitching_lines_seen=7,
            logs_added=7,
        )
        db.session.add(marker)
        db.session.commit()

        result = reset_fully_processed_markers_without_appearance_rows(
            schedule_dates=[SLATE_DATE],
        )
        db.session.refresh(marker)

        assert result['markers_reset'] == 0
        assert marker.processing_status == PostgameProcessedGame.STATUS_FULLY_PROCESSED
