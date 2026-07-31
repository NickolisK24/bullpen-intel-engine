"""Foundation 3C — game-level publication completeness proof."""

from datetime import date, datetime

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.game_ingestion_work_item import GameIngestionWorkItem
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from services import game_ingestion_completeness as completeness
from utils.db import db


REFERENCE = date(2026, 7, 29)


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


def _schedule(game_pk, *, game_date=REFERENCE, state=ScheduledGame.STATE_FINAL,
              away_state=None):
    for team_id, opponent_id, side, side_state in (
        (147, 111, 'home', state),
        (111, 147, 'away', away_state or state),
    ):
        db.session.add(ScheduledGame(
            team_id=team_id, game_pk=game_pk, game_date=game_date,
            opponent_team_id=opponent_id, home_away=side, game_type='R',
            status_code='F', status_state=side_state,
        ))


def _completed_item(game_pk, *, rows=2, represented_date=REFERENCE, corrections=0):
    db.session.add(GameIngestionWorkItem(
        mlb_game_pk=game_pk,
        represented_date=represented_date,
        game_date=represented_date,
        candidate_reason=GameIngestionWorkItem.REASON_NEWLY_FINAL,
        criticality=GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL,
        status=GameIngestionWorkItem.STATUS_COMPLETED,
        attempt_count=1,
        rows_expected=rows,
        rows_reconciled=rows,
        correction_count=corrections,
        completed_at=datetime(2026, 7, 29, 6, 0, 0),
        source_revision=f'rev-{game_pk}',
    ))


def _unresolved_item(game_pk, *, status, error_class=None,
                     criticality=GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL):
    db.session.add(GameIngestionWorkItem(
        mlb_game_pk=game_pk,
        represented_date=REFERENCE,
        game_date=REFERENCE,
        candidate_reason=GameIngestionWorkItem.REASON_NEWLY_FINAL,
        criticality=criticality,
        status=status,
        attempt_count=1,
        error_class=error_class,
    ))


def _appearance_rows(game_pk, count, *, start_mlb_id):
    for offset in range(count):
        pitcher = Pitcher(
            mlb_id=start_mlb_id + offset,
            full_name=f'Arm {start_mlb_id + offset}',
            team_id=147, team_abbreviation='TST', position='P', active=True,
        )
        db.session.add(pitcher)
        db.session.flush()
        db.session.add(GameLog(
            pitcher_id=pitcher.id, mlb_game_pk=game_pk, game_date=REFERENCE,
            innings_pitched=1.0, innings_pitched_outs=3,
        ))


def _proof():
    return completeness.build_game_ingestion_completeness(REFERENCE)


def test_complete_final_game_coverage_publishes(app):
    with app.app_context():
        _schedule(920001)
        _completed_item(920001, rows=2)
        _appearance_rows(920001, 2, start_mlb_id=6001)
        db.session.commit()

        proof = _proof()

        assert proof['publication_complete'] is True
        assert proof['decision_reasons'] == [completeness.REASON_COMPLETE]
        assert proof['completed_final_games'] == 1
        assert proof['critical_appearance_rows_expected'] == 2
        assert proof['critical_appearance_rows_reconciled'] == 2


def test_one_unresolved_critical_game_withholds(app):
    with app.app_context():
        _schedule(920002)
        _completed_item(920002, rows=1)
        _appearance_rows(920002, 1, start_mlb_id=6010)
        _schedule(920003)
        db.session.commit()

        proof = _proof()

        assert proof['publication_complete'] is False
        assert completeness.REASON_UNRESOLVED_FINAL_GAMES in proof['decision_reasons']
        assert proof['unresolved_final_games'] == 1


def test_a_retryable_critical_failure_withholds(app):
    with app.app_context():
        _schedule(920004)
        _unresolved_item(
            920004, status=GameIngestionWorkItem.STATUS_RETRYABLE_FAILURE,
            error_class='game_fetch_failed',
        )
        db.session.commit()

        proof = _proof()

        assert proof['publication_complete'] is False
        assert completeness.REASON_CRITICAL_FAILURE_UNRESOLVED in (
            proof['decision_reasons']
        )


def test_a_terminal_critical_failure_withholds(app):
    with app.app_context():
        _schedule(920005)
        _unresolved_item(
            920005, status=GameIngestionWorkItem.STATUS_TERMINAL_FAILURE,
            error_class='payload_invalid',
        )
        db.session.commit()

        proof = _proof()

        assert proof['publication_complete'] is False
        assert completeness.REASON_TERMINAL_CRITICAL_FAILURE in (
            proof['decision_reasons']
        )
        assert proof['terminal_failure_games'] == 1


def test_a_finality_conflict_withholds(app):
    with app.app_context():
        _schedule(920006, away_state=ScheduledGame.STATE_SCHEDULED)
        db.session.commit()

        proof = _proof()

        assert proof['publication_complete'] is False
        assert completeness.REASON_FINALITY_CONFLICT in proof['decision_reasons']
        assert proof['finality_conflicts'] == 1


def test_a_schedule_authority_gap_withholds(app):
    with app.app_context():
        _unresolved_item(
            920007, status=GameIngestionWorkItem.STATUS_RETRYABLE_FAILURE,
        )
        db.session.commit()

        proof = _proof()

        assert proof['publication_complete'] is False
        assert completeness.REASON_SCHEDULE_AUTHORITY_MISSING in (
            proof['decision_reasons']
        )


def test_a_material_pending_correction_withholds(app):
    with app.app_context():
        _schedule(920008)
        _unresolved_item(
            920008,
            status=GameIngestionWorkItem.STATUS_RETRYABLE_FAILURE,
            error_class='correction_conflict',
        )
        db.session.commit()

        proof = _proof()

        assert proof['publication_complete'] is False
        assert completeness.REASON_CORRECTION_PENDING in proof['decision_reasons']
        assert proof['correction_pending_games'] == 1


def test_a_routine_correction_recheck_does_not_withhold(app):
    with app.app_context():
        _schedule(920009)
        _completed_item(920009, rows=2, corrections=1)
        _appearance_rows(920009, 2, start_mlb_id=6020)
        db.session.commit()

        proof = _proof()

        # The game IS complete at its last known revision; a scheduled
        # correction re-check is not evidence that anything changed.
        assert proof['publication_complete'] is True
        assert proof['corrected_games_reconciled'] == 1


def test_expected_and_reconciled_counts_must_match(app):
    with app.app_context():
        _schedule(920010)
        _completed_item(920010, rows=3)
        _appearance_rows(920010, 2, start_mlb_id=6030)  # one row is missing
        db.session.commit()

        proof = _proof()

        assert proof['publication_complete'] is False
        assert completeness.REASON_APPEARANCE_ROWS_UNRECONCILED in (
            proof['decision_reasons']
        )
        assert proof['critical_appearance_rows_expected'] == 3
        assert proof['critical_appearance_rows_reconciled'] == 2


def test_a_best_effort_only_backlog_does_not_block(app):
    with app.app_context():
        _schedule(920011)
        _completed_item(920011, rows=1)
        _appearance_rows(920011, 1, start_mlb_id=6040)
        _unresolved_item(
            920012,
            status=GameIngestionWorkItem.STATUS_RETRYABLE_FAILURE,
            criticality=GameIngestionWorkItem.CRITICALITY_BEST_EFFORT,
        )
        db.session.commit()

        proof = _proof()

        assert proof['publication_complete'] is True


def test_a_non_final_game_in_the_window_does_not_withhold(app):
    with app.app_context():
        _schedule(920013)
        _completed_item(920013, rows=1)
        _appearance_rows(920013, 1, start_mlb_id=6050)
        _schedule(920014, state=ScheduledGame.STATE_SCHEDULED)
        db.session.commit()

        proof = _proof()

        # A game that is not final yet is not an unresolved final game.
        assert proof['publication_complete'] is True


def test_an_empty_lane_withholds_rather_than_claiming_completeness(app):
    with app.app_context():
        _schedule(920015)
        db.session.commit()

        proof = _proof()

        assert proof['publication_complete'] is False
        assert proof['completed_final_games'] == 0


def test_the_proof_exposes_every_required_field(app):
    with app.app_context():
        _schedule(920016)
        _completed_item(920016, rows=1)
        _appearance_rows(920016, 1, start_mlb_id=6060)
        db.session.commit()

        proof = _proof()

        for field in (
            'represented_date', 'expected_final_games', 'completed_final_games',
            'unresolved_final_games', 'corrected_games_reconciled',
            'critical_appearance_rows_expected',
            'critical_appearance_rows_reconciled', 'finality_conflicts',
            'schedule_authority_missing', 'publication_complete',
            'decision_reasons',
        ):
            assert field in proof, field
