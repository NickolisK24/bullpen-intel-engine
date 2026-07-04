from datetime import date

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

from models.pitcher import Pitcher
from models.play_by_play_foundation import (
    GamePlayByPlayEvent,
    PlayByPlayProcessedGame,
)
from models.sync_failure import SyncFailure
from services.play_by_play_foundation import (
    FINAL_PBP_RECONCILIATION_ENTITY_TYPE,
    process_final_play_by_play_foundation,
)
from utils.db import db
import models.sync_run  # noqa: F401


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


def _seed_pitchers():
    pitchers = [
        Pitcher(mlb_id=101, full_name='Home Starter', team_id=1, active=True),
        Pitcher(mlb_id=303, full_name='Home Reliever', team_id=1, active=True),
        Pitcher(mlb_id=202, full_name='Away Starter', team_id=2, active=True),
    ]
    db.session.add_all(pitchers)
    db.session.commit()
    return pitchers


def _game(status_code='F', detailed_state='Final', abstract_state='Final', game_pk=7001):
    return {
        'gamePk': game_pk,
        'gameType': 'R',
        'officialDate': '2026-06-20',
        'status': {
            'statusCode': status_code,
            'detailedState': detailed_state,
            'abstractGameState': abstract_state,
        },
        'teams': {
            'home': {'team': {'id': 1, 'name': 'Home Club'}},
            'away': {'team': {'id': 2, 'name': 'Away Club'}},
        },
    }


def _boxscore(home_pitchers=None, away_pitchers=None):
    home_pitchers = home_pitchers or [101, 303]
    away_pitchers = away_pitchers or [202]
    return {
        'teams': {
            'home': {
                'team': {'id': 1, 'name': 'Home Club'},
                'pitchers': home_pitchers,
                'players': {
                    f'ID{pid}': {
                        'person': {'id': pid, 'fullName': f'Pitcher {pid}'},
                        'stats': {'pitching': {'inningsPitched': '1.0'}},
                    }
                    for pid in home_pitchers
                },
            },
            'away': {
                'team': {'id': 2, 'name': 'Away Club'},
                'pitchers': away_pitchers,
                'players': {
                    f'ID{pid}': {
                        'person': {'id': pid, 'fullName': f'Pitcher {pid}'},
                        'stats': {'pitching': {'inningsPitched': '1.0'}},
                    }
                    for pid in away_pitchers
                },
            },
        },
    }


def _play_by_play(home_score_last=1):
    return {
        'allPlays': [
            _play(0, 1, 'top', 101, home_score=0, away_score=0),
            _play(1, 1, 'bottom', 202, home_score=0, away_score=0),
            _play(2, 2, 'top', 303, home_score=0, away_score=0),
            _play(
                3,
                2,
                'bottom',
                202,
                home_score=home_score_last,
                away_score=0,
                scoring=True,
                event_type='single',
            ),
        ],
    }


def _play(
    at_bat_index,
    inning,
    half,
    pitcher_id,
    *,
    home_score,
    away_score,
    scoring=False,
    event_type='field_out',
):
    matchup = {'batter': {'id': 900 + at_bat_index}}
    if pitcher_id is not None:
        matchup['pitcher'] = {'id': pitcher_id}
    return {
        'playId': f'play-{at_bat_index}',
        'about': {
            'atBatIndex': at_bat_index,
            'inning': inning,
            'halfInning': half,
            'outs': at_bat_index % 3,
            'isComplete': True,
            'isScoringPlay': scoring,
        },
        'result': {
            'eventType': event_type,
            'homeScore': home_score,
            'awayScore': away_score,
            'description': 'Free text should not be persisted',
        },
        'matchup': matchup,
    }


def _process(game=None, boxscore=None, play_by_play=None):
    return process_final_play_by_play_foundation(
        game or _game(),
        boxscore=boxscore if boxscore is not None else _boxscore(),
        play_by_play=play_by_play if play_by_play is not None else _play_by_play(),
        game_date=date(2026, 6, 20),
        sync_run_id=None,
    )


def test_finality_certified_game_stores_normalized_typed_pbp_rows(app):
    with app.app_context():
        _seed_pitchers()
        result = _process()
        db.session.commit()

        rows = GamePlayByPlayEvent.query.order_by(GamePlayByPlayEvent.event_index).all()
        marker = PlayByPlayProcessedGame.query.filter_by(mlb_game_pk=7001).one()

    assert result['processing_status'] == PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED
    assert marker.processing_status == PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED
    assert marker.events_stored == 4
    assert [row.event_index for row in rows] == [0, 1, 2, 3]
    assert rows[2].event_type == 'pitching_change'
    assert rows[2].is_pitching_change is True
    assert rows[3].is_scoring_play is True
    assert rows[0].pitcher_id is not None
    assert not hasattr(rows[0], 'raw_json')
    assert not hasattr(rows[0], 'description')


def test_non_final_game_writes_no_pbp_rows_or_marker(app):
    with app.app_context():
        _seed_pitchers()
        result = _process(
            game=_game(status_code='I', detailed_state='In Progress', abstract_state='Live')
        )
        db.session.commit()

        assert result['skipped'] is True
        assert GamePlayByPlayEvent.query.count() == 0
        assert PlayByPlayProcessedGame.query.count() == 0


def test_finalish_but_not_usable_game_writes_no_pbp_rows(app):
    with app.app_context():
        _seed_pitchers()
        result = _process(boxscore={'teams': {}})
        db.session.commit()

        assert result['skipped'] is True
        assert result['finality_state'] == 'final_pending_data'
        assert GamePlayByPlayEvent.query.count() == 0
        assert PlayByPlayProcessedGame.query.count() == 0


def test_missing_game_pk_writes_no_pbp_rows_or_marker(app):
    with app.app_context():
        _seed_pitchers()
        game = _game()
        game.pop('gamePk')
        result = _process(game=game)
        db.session.commit()

        assert result['skipped'] is True
        assert GamePlayByPlayEvent.query.count() == 0
        assert PlayByPlayProcessedGame.query.count() == 0
        assert SyncFailure.query.filter_by(entity_type='final_pbp_identity').count() == 1


def test_missing_pbp_creates_absent_marker(app):
    with app.app_context():
        _seed_pitchers()
        result = process_final_play_by_play_foundation(
            _game(),
            boxscore=_boxscore(),
            play_by_play=None,
            game_date=date(2026, 6, 20),
        )
        db.session.commit()
        marker = PlayByPlayProcessedGame.query.filter_by(mlb_game_pk=7001).one()

    assert result['processing_status'] == PlayByPlayProcessedGame.STATUS_ABSENT
    assert marker.processing_status == PlayByPlayProcessedGame.STATUS_ABSENT
    assert marker.incomplete_reason == 'play_by_play_absent'
    assert marker.events_stored == 0


def test_ambiguous_pbp_creates_ambiguous_marker(app):
    with app.app_context():
        _seed_pitchers()
        ambiguous = {'allPlays': [_play(0, 1, 'top', 101, home_score=0, away_score=0)]}
        ambiguous['allPlays'][0]['result'].pop('homeScore')
        result = _process(play_by_play=ambiguous)
        db.session.commit()
        marker = PlayByPlayProcessedGame.query.filter_by(mlb_game_pk=7001).one()
        event_count = GamePlayByPlayEvent.query.count()

    assert result['processing_status'] == PlayByPlayProcessedGame.STATUS_AMBIGUOUS
    assert marker.incomplete_reason == 'missing_required_play_state'
    assert event_count == 0


def test_repeated_process_is_idempotent(app):
    with app.app_context():
        _seed_pitchers()
        first = _process()
        db.session.commit()
        marker = PlayByPlayProcessedGame.query.filter_by(mlb_game_pk=7001).one()
        fingerprint = marker.event_fingerprint
        row_ids = [row.id for row in GamePlayByPlayEvent.query.order_by(GamePlayByPlayEvent.id)]

        second = _process()
        db.session.commit()
        marker = PlayByPlayProcessedGame.query.filter_by(mlb_game_pk=7001).one()
        row_ids_after = [row.id for row in GamePlayByPlayEvent.query.order_by(GamePlayByPlayEvent.id)]

    assert first['events_stored'] == 4
    assert second['events_stored'] == 4
    assert second['rows_rebuilt'] is False
    assert marker.event_fingerprint == fingerprint
    assert marker.correction_count == 0
    assert row_ids_after == row_ids


def test_corrected_final_pbp_rebuilds_with_provenance(app):
    with app.app_context():
        _seed_pitchers()
        _process()
        db.session.commit()

        result = _process(play_by_play=_play_by_play(home_score_last=2))
        db.session.commit()
        marker = PlayByPlayProcessedGame.query.filter_by(mlb_game_pk=7001).one()
        final_event = GamePlayByPlayEvent.query.filter_by(event_index=3).one()

    assert result['corrected'] is True
    assert result['rows_rebuilt'] is True
    assert marker.correction_count == 1
    assert marker.correction_source == 'final_play_by_play_rebuild'
    assert final_event.home_score_at_event == 2
    assert final_event.correction_count == 1


def test_unknown_pitcher_identity_fails_closed(app):
    with app.app_context():
        _seed_pitchers()
        pbp = _play_by_play()
        pbp['allPlays'][2] = _play(2, 2, 'top', None, home_score=0, away_score=0)
        result = _process(play_by_play=pbp, boxscore=_boxscore(home_pitchers=[101]))
        db.session.commit()
        marker = PlayByPlayProcessedGame.query.filter_by(mlb_game_pk=7001).one()

    assert result['processing_status'] == PlayByPlayProcessedGame.STATUS_INCOMPLETE
    assert marker.incomplete_reason == 'unknown_pitcher_identity'
    assert marker.unresolved_pitcher_count == 1


def test_reconciliation_mismatch_marks_incomplete_and_dead_letters(app):
    with app.app_context():
        _seed_pitchers()
        result = _process(boxscore=_boxscore(home_pitchers=[101, 303, 404]))
        db.session.commit()
        marker = PlayByPlayProcessedGame.query.filter_by(mlb_game_pk=7001).one()
        failure = SyncFailure.query.filter_by(
            entity_type=FINAL_PBP_RECONCILIATION_ENTITY_TYPE,
            entity_ref='7001',
        ).one()

    assert result['processing_status'] == PlayByPlayProcessedGame.STATUS_INCOMPLETE
    assert marker.incomplete_reason == 'pitcher_reconciliation_mismatch'
    assert marker.reconciliation_mismatch_count == 1
    assert failure.payload['missing_boxscore_pitcher_ids'] == [404]


def test_retry_limit_moves_missing_pbp_to_failed(app):
    with app.app_context():
        _seed_pitchers()
        for _ in range(3):
            process_final_play_by_play_foundation(
                _game(),
                boxscore=_boxscore(),
                play_by_play=None,
                game_date=date(2026, 6, 20),
            )
            db.session.commit()
        marker = PlayByPlayProcessedGame.query.filter_by(mlb_game_pk=7001).one()

    assert marker.processing_status == PlayByPlayProcessedGame.STATUS_FAILED
    assert marker.attempt_count == 3
    assert marker.failed_at is not None
