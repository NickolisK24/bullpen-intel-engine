from datetime import date, timedelta

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from services import slate_coverage
from utils.db import db


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


def _schedule_game(game_pk, game_date, *, status='final', home_id=116, away_id=142):
    db.session.add_all([
        ScheduledGame(
            team_id=home_id,
            game_pk=game_pk,
            game_date=game_date,
            status_state=status,
            home_away='home',
            opponent_team_id=away_id,
        ),
        ScheduledGame(
            team_id=away_id,
            game_pk=game_pk,
            game_date=game_date,
            status_state=status,
            home_away='away',
            opponent_team_id=home_id,
        ),
    ])


def _marker(game_pk, game_date, *, status=PostgameProcessedGame.STATUS_FULLY_PROCESSED):
    db.session.add(PostgameProcessedGame(
        mlb_game_pk=game_pk,
        game_date=game_date,
        processing_status=status,
        processed_at=None,
    ))


def test_full_slate_complete_counts_scheduled_final_and_ingested_games(app):
    slate_date = date(2026, 6, 25)
    with app.app_context():
        _schedule_game(1001, slate_date)
        _schedule_game(1002, slate_date)
        _marker(1001, slate_date)
        _marker(1002, slate_date)
        db.session.commit()

        coverage = slate_coverage.compute_slate_coverage(slate_date)

    assert coverage['games_scheduled'] == 2
    assert coverage['games_final'] == 2
    assert coverage['games_fully_ingested'] == 2
    assert coverage['games_incomplete'] == 0
    assert coverage['validations_passed'] is True
    assert coverage['complete_enough_to_publish'] is True
    assert coverage['reason_codes'] == ['slate_complete']


def test_final_games_without_full_markers_are_incomplete(app):
    slate_date = date(2026, 6, 25)
    with app.app_context():
        _schedule_game(1001, slate_date)
        db.session.commit()

        coverage = slate_coverage.compute_slate_coverage(slate_date)

    assert coverage['games_final'] == 1
    assert coverage['games_fully_ingested'] == 0
    assert coverage['games_incomplete'] == 1
    assert coverage['complete_enough_to_publish'] is False
    assert 'final_games_not_fully_ingested' in coverage['reason_codes']
    assert 'postgame_markers_incomplete' in coverage['reason_codes']


def test_incomplete_postgame_marker_degrades_slate(app):
    slate_date = date(2026, 6, 25)
    with app.app_context():
        _schedule_game(1001, slate_date)
        _marker(
            1001,
            slate_date,
            status=PostgameProcessedGame.STATUS_INCOMPLETE,
        )
        db.session.commit()

        coverage = slate_coverage.compute_slate_coverage(slate_date)

    assert coverage['marker_counts']['incomplete'] == 1
    assert coverage['complete_enough_to_publish'] is False
    assert 'postgame_markers_incomplete' in coverage['reason_codes']


def test_failed_postgame_marker_is_visible_and_not_publishable(app):
    slate_date = date(2026, 6, 25)
    with app.app_context():
        _schedule_game(1001, slate_date)
        _marker(
            1001,
            slate_date,
            status=PostgameProcessedGame.STATUS_FAILED,
        )
        db.session.commit()

        coverage = slate_coverage.compute_slate_coverage(slate_date)

    assert coverage['games_failed'] == 1
    assert coverage['marker_counts']['failed'] == 1
    assert coverage['complete_enough_to_publish'] is False
    assert 'postgame_markers_failed' in coverage['reason_codes']


def test_partial_sync_degrades_even_when_counts_are_complete(app):
    slate_date = date(2026, 6, 25)
    with app.app_context():
        _schedule_game(1001, slate_date)
        _marker(1001, slate_date)
        db.session.commit()

        coverage = slate_coverage.compute_slate_coverage(
            slate_date,
            sync_status='partial',
        )

    assert coverage['games_fully_ingested'] == 1
    assert coverage['validations_passed'] is False
    assert coverage['complete_enough_to_publish'] is False
    assert 'partial_sync' in coverage['reason_codes']


def test_schedule_missing_fails_closed_during_season(app):
    with app.app_context():
        coverage = slate_coverage.compute_slate_coverage(date(2026, 6, 25))

    assert coverage['coverage_known'] is False
    assert coverage['complete_enough_to_publish'] is False
    assert coverage['reason_codes'] == [
        'schedule_missing',
        'validations_failed',
    ]


def test_zero_game_offseason_slate_is_complete_by_definition(app):
    with app.app_context():
        coverage = slate_coverage.compute_slate_coverage(date(2026, 1, 10))

    assert coverage['games_scheduled'] == 0
    assert coverage['games_included'] == 0
    assert coverage['validations_passed'] is True
    assert coverage['complete_enough_to_publish'] is True
    assert coverage['reason_codes'] == ['no_scheduled_games', 'slate_complete']


def test_zero_game_off_day_with_nearby_schedule_is_complete_by_definition(app):
    slate_date = date(2026, 6, 25)
    with app.app_context():
        _schedule_game(1001, slate_date - timedelta(days=1), status='final')
        _marker(1001, slate_date - timedelta(days=1))
        db.session.commit()

        coverage = slate_coverage.compute_slate_coverage(slate_date)

    assert coverage['games_scheduled'] == 0
    assert coverage['validations_passed'] is True
    assert coverage['complete_enough_to_publish'] is True
    assert coverage['reason_codes'] == ['no_scheduled_games', 'slate_complete']


def test_doubleheader_counts_both_games(app):
    slate_date = date(2026, 6, 25)
    with app.app_context():
        _schedule_game(1001, slate_date)
        _schedule_game(1002, slate_date)
        _marker(1001, slate_date)
        _marker(1002, slate_date)
        db.session.commit()

        coverage = slate_coverage.compute_slate_coverage(slate_date)

    assert coverage['games_scheduled'] == 2
    assert coverage['games_final'] == 2
    assert coverage['games_fully_ingested'] == 2
    assert coverage['complete_enough_to_publish'] is True


def test_postponed_games_do_not_block_completeness(app):
    slate_date = date(2026, 6, 25)
    with app.app_context():
        _schedule_game(1001, slate_date)
        _marker(1001, slate_date)
        _schedule_game(1002, slate_date, status=ScheduledGame.STATE_POSTPONED)
        db.session.commit()

        coverage = slate_coverage.compute_slate_coverage(slate_date)

    assert coverage['games_scheduled'] == 2
    assert coverage['games_postponed'] == 1
    assert coverage['games_included'] == 1
    assert coverage['complete_enough_to_publish'] is True


def test_suspended_games_do_not_count_as_fully_ingested(app):
    slate_date = date(2026, 6, 25)
    with app.app_context():
        _schedule_game(1001, slate_date, status=ScheduledGame.STATE_SUSPENDED)
        _marker(1001, slate_date)
        db.session.commit()

        coverage = slate_coverage.compute_slate_coverage(slate_date)

    assert coverage['games_suspended'] == 1
    assert coverage['games_final'] == 0
    assert coverage['games_fully_ingested'] == 0
    assert coverage['games_incomplete'] == 1
    assert coverage['complete_enough_to_publish'] is False
    assert 'suspended_games_not_final' in coverage['reason_codes']
