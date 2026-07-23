from datetime import date, datetime

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.postgame_processed_game import PostgameProcessedGame
from services.postgame_recovery import reset_failed_postgame_markers
from utils.db import db


SLATE_DATE = date(2026, 7, 20)


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


def _marker(game_pk, *, game_date=SLATE_DATE, status=PostgameProcessedGame.STATUS_FAILED):
    return PostgameProcessedGame(
        mlb_game_pk=game_pk,
        game_date=game_date,
        processing_status=status,
        attempt_count=3,
        last_attempted_at=datetime(2026, 7, 21, 4, 0, 0),
        incomplete_reason='empty_pitching_data',
        pitching_lines_seen=0,
        pitcher_resolution_failures=0,
        correction_attempts_failed=0,
        failed_at=datetime(2026, 7, 21, 4, 0, 0),
        sync_run_id=None,
    )


def test_recovery_requires_a_bounded_selector(app):
    with app.app_context():
        with pytest.raises(ValueError, match='schedule_date or game_pks'):
            reset_failed_postgame_markers()


def test_recovery_resets_only_failed_markers_on_selected_date(app):
    with app.app_context():
        db.session.add_all([
            _marker(7001),
            _marker(7002, status=PostgameProcessedGame.STATUS_FULLY_PROCESSED),
            _marker(7003, game_date=date(2026, 7, 19)),
        ])
        db.session.commit()

        result = reset_failed_postgame_markers(schedule_date=SLATE_DATE)

        recovered = PostgameProcessedGame.query.filter_by(mlb_game_pk=7001).one()
        completed = PostgameProcessedGame.query.filter_by(mlb_game_pk=7002).one()
        other_date = PostgameProcessedGame.query.filter_by(mlb_game_pk=7003).one()

        assert result['status'] == 'reset'
        assert result['markers_reset'] == 1
        assert result['reset_game_pks'] == [7001]
        assert recovered.processing_status == PostgameProcessedGame.STATUS_INCOMPLETE
        assert recovered.attempt_count == 0
        assert recovered.last_attempted_at is None
        assert recovered.failed_at is None
        assert recovered.processed_at is None
        assert recovered.incomplete_reason == 'empty_pitching_data'
        assert completed.processing_status == PostgameProcessedGame.STATUS_FULLY_PROCESSED
        assert other_date.processing_status == PostgameProcessedGame.STATUS_FAILED


def test_recovery_game_pk_filter_uses_and_semantics(app):
    with app.app_context():
        db.session.add_all([_marker(7101), _marker(7102)])
        db.session.commit()

        result = reset_failed_postgame_markers(
            schedule_date=SLATE_DATE,
            game_pks=[7102, 9999],
        )

        untouched = PostgameProcessedGame.query.filter_by(mlb_game_pk=7101).one()
        recovered = PostgameProcessedGame.query.filter_by(mlb_game_pk=7102).one()
        assert result['markers_reset'] == 1
        assert result['reset_game_pks'] == [7102]
        assert untouched.processing_status == PostgameProcessedGame.STATUS_FAILED
        assert recovered.processing_status == PostgameProcessedGame.STATUS_INCOMPLETE


def test_recovery_reports_no_match_without_mutation(app):
    with app.app_context():
        db.session.add(_marker(7201))
        db.session.commit()

        result = reset_failed_postgame_markers(
            schedule_date=SLATE_DATE,
            game_pks=[9999],
        )

        marker = PostgameProcessedGame.query.filter_by(mlb_game_pk=7201).one()
        assert result['status'] == 'no_matching_failed_markers'
        assert result['markers_reset'] == 0
        assert marker.processing_status == PostgameProcessedGame.STATUS_FAILED
        assert marker.attempt_count == 3
