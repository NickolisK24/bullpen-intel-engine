from datetime import date, datetime, timedelta

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


def _schedule_game(
    game_pk,
    game_date,
    *,
    status='final',
    status_code=None,
    home_id=116,
    away_id=142,
    **linkage,
):
    base_kwargs = {
        'game_date': game_date,
        'status_code': status_code,
        'status_state': status,
    }
    base_kwargs.update(linkage)
    db.session.add_all([
        ScheduledGame(
            team_id=home_id,
            game_pk=game_pk,
            home_away='home',
            opponent_team_id=away_id,
            **base_kwargs,
        ),
        ScheduledGame(
            team_id=away_id,
            game_pk=game_pk,
            home_away='away',
            opponent_team_id=home_id,
            **base_kwargs,
        ),
    ])


def _marker(
    game_pk,
    game_date,
    *,
    status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
    **kwargs,
):
    payload = {
        'mlb_game_pk': game_pk,
        'game_date': game_date,
        'processing_status': status,
        'processed_at': None,
    }
    payload.update(kwargs)
    db.session.add(PostgameProcessedGame(**payload))


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


def test_diagnostics_identify_missing_and_incomplete_postgame_markers(app):
    slate_date = date(2026, 7, 3)
    last_attempted_at = datetime(2026, 7, 4, 5, 10, 0)
    with app.app_context():
        _schedule_game(
            2001,
            slate_date,
            status_code='F',
            home_id=116,
            away_id=142,
        )
        _schedule_game(
            2002,
            slate_date,
            status_code='F',
            home_id=121,
            away_id=147,
        )
        _marker(
            2001,
            slate_date,
            status=PostgameProcessedGame.STATUS_INCOMPLETE,
            incomplete_reason='pitcher_resolution_failures',
            attempt_count=2,
            pitching_lines_seen=6,
            pitcher_resolution_failures=1,
            correction_attempts_failed=1,
            last_attempted_at=last_attempted_at,
        )
        db.session.commit()

        coverage = slate_coverage.compute_slate_coverage(
            slate_date,
            include_diagnostics=True,
        )

    diagnostics = coverage['diagnostics']
    blockers = diagnostics['postgame_blockers']
    assert diagnostics['slate_date'] == '2026-07-03'
    assert diagnostics['reason_codes'] == [
        'final_games_not_fully_ingested',
        'postgame_markers_incomplete',
        'validations_failed',
    ]
    assert diagnostics['failure_domains'] == [
        'postgame_markers',
        'pitcher_resolution',
        'validations',
    ]
    assert diagnostics['schedule_known'] is True
    assert diagnostics['scheduled_game_count'] == 2
    assert diagnostics['final_game_count'] == 2
    assert diagnostics['failed_game_pks'] == [2001, 2002]
    assert diagnostics['failed_team_ids'] == [116, 121, 142, 147]
    assert diagnostics['postgame_blocker_reason_counts'] == {
        'incomplete_marker': 1,
        'missing_marker': 1,
    }
    assert diagnostics['postgame_blocker_incomplete_reason_counts'] == {
        'pitcher_resolution_failures': 1,
    }
    assert diagnostics['postgame_blocker_count'] == 2
    assert [blocker['mlb_game_pk'] for blocker in blockers] == [2001, 2002]
    assert coverage['complete_enough_to_publish'] is False
    assert coverage['reason_codes'] == [
        'final_games_not_fully_ingested',
        'postgame_markers_incomplete',
        'validations_failed',
    ]

    incomplete = blockers[0]
    assert incomplete['reason_code'] == 'incomplete_marker'
    assert incomplete['diagnostic_domain'] == 'postgame_markers'
    assert incomplete['marker_status'] == PostgameProcessedGame.STATUS_INCOMPLETE
    assert incomplete['incomplete_reason'] == 'pitcher_resolution_failures'
    assert incomplete['attempt_count'] == 2
    assert incomplete['pitching_lines_seen'] == 6
    assert incomplete['pitcher_resolution_failures'] == 1
    assert incomplete['correction_attempts_failed'] == 1
    assert incomplete['last_attempted_at'] == '2026-07-04T05:10:00'
    assert incomplete['game_status'] == 'F'
    assert incomplete['status_state'] == ScheduledGame.STATE_FINAL
    assert incomplete['away_team'] == 142
    assert incomplete['home_team'] == 116

    missing = blockers[1]
    assert missing['reason_code'] == 'missing_marker'
    assert missing['marker_status'] == 'missing'
    assert missing['incomplete_reason'] is None
    assert missing['attempt_count'] == 0
    assert missing['pitching_lines_seen'] == 0
    assert missing['pitcher_resolution_failures'] == 0
    assert missing['correction_attempts_failed'] == 0
    assert missing['away_team'] == 147
    assert missing['home_team'] == 121


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

        coverage = slate_coverage.compute_slate_coverage(
            slate_date,
            include_diagnostics=True,
        )

    assert coverage['games_failed'] == 1
    assert coverage['marker_counts']['failed'] == 1
    assert coverage['complete_enough_to_publish'] is False
    assert 'postgame_markers_failed' in coverage['reason_codes']
    assert coverage['diagnostics']['postgame_blockers'][0]['reason_code'] == 'failed_marker'


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
        coverage = slate_coverage.compute_slate_coverage(
            date(2026, 6, 25),
            include_diagnostics=True,
        )

    assert coverage['coverage_known'] is False
    assert coverage['complete_enough_to_publish'] is False
    assert coverage['reason_codes'] == [
        'schedule_missing',
        'validations_failed',
    ]
    diagnostics = coverage['diagnostics']
    assert diagnostics['failure_domains'] == ['schedule', 'validations']
    assert diagnostics['schedule_known'] is False
    assert diagnostics['scheduled_game_count'] == 0
    assert diagnostics['failed_game_pks'] == []


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

        coverage = slate_coverage.compute_slate_coverage(
            slate_date,
            include_diagnostics=True,
        )

    assert coverage['games_suspended'] == 1
    assert coverage['games_final'] == 0
    assert coverage['games_fully_ingested'] == 0
    assert coverage['games_incomplete'] == 1
    assert coverage['complete_enough_to_publish'] is False
    assert 'suspended_games_not_final' in coverage['reason_codes']
    assert coverage['diagnostics']['failure_domains'] == ['finality', 'validations']
    assert coverage['diagnostics']['non_final_game_count'] == 1
    assert coverage['diagnostics']['non_final_games'][0]['mlb_game_pk'] == 1001


def test_unresolved_resumed_linkage_blocks_completeness(app):
    slate_date = date(2026, 7, 4)
    with app.app_context():
        _schedule_game(
            2001,
            slate_date,
            resumed_from_game_pk=1001,
            original_product_date=None,
            resumed_product_date=slate_date,
        )
        _marker(2001, slate_date)
        db.session.commit()

        coverage = slate_coverage.compute_slate_coverage(slate_date)

    assert coverage['games_unresolved'] == 1
    assert coverage['games_final'] == 0
    assert coverage['games_fully_ingested'] == 0
    assert coverage['complete_enough_to_publish'] is False
    assert 'resumed_linkage_unresolved' in coverage['reason_codes']
    assert 'completeness_unknown' in coverage['reason_codes']


def test_resolved_resumed_linkage_counts_once_on_resumed_product_day(app):
    original_date = date(2026, 6, 20)
    resumed_date = date(2026, 7, 4)
    with app.app_context():
        _schedule_game(
            2001,
            resumed_date,
            resumed_from_game_pk=1001,
            original_product_date=original_date,
            resumed_product_date=resumed_date,
        )
        _marker(2001, resumed_date)
        db.session.commit()

        coverage = slate_coverage.compute_slate_coverage(resumed_date)

    assert coverage['games_scheduled'] == 1
    assert coverage['games_unresolved'] == 0
    assert coverage['games_final'] == 1
    assert coverage['games_fully_ingested'] == 1
    assert coverage['complete_enough_to_publish'] is True
