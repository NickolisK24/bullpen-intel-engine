from datetime import date
from types import SimpleNamespace

import pytest
from flask import Flask
from tests.db_config import configure_test_database
from sqlalchemy.exc import IntegrityError

from models.game_log import GameLog
from models.pitcher import Pitcher
from services.bullpen_eligibility import evaluate_bullpen_eligibility
from services.games_started_backfill import backfill_games_started
from utils.db import db
from utils.games_started import (
    InvalidGamesStartedValue,
    games_started_state,
    log_games_started_state,
    parse_games_started,
)
from utils.innings import outs_to_decimal_innings, parse_mlb_innings_to_outs


class LogStub:
    def __init__(self, games_started, innings='1.0'):
        outs = parse_mlb_innings_to_outs(innings)
        self.games_started = games_started
        self.innings_pitched = outs_to_decimal_innings(outs)
        self.innings_pitched_outs = outs
        self.game_date = date(2026, 6, 1)
        self.game_type = 'R'
        self.save = False
        self.hold = False


class FakeClient:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def get_pitcher_game_logs(self, mlb_id, season=None):
        self.calls.append((mlb_id, season))
        return self.payloads.get((mlb_id, season), [])


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    db.init_app(flask_app)

    with flask_app.app_context():
        db.create_all()
        try:
            yield flask_app
        finally:
            db.session.remove()
            db.drop_all()


def _split(game_pk, games_started):
    return {
        'game': {'gamePk': game_pk},
        'stat': {'gamesStarted': games_started},
    }


def _pitcher(mlb_id, name):
    pitcher = Pitcher(mlb_id=mlb_id, full_name=name, active=True, position='P')
    db.session.add(pitcher)
    db.session.commit()
    return pitcher


def _game_log(pitcher, game_pk, day=1, games_started=None):
    return GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
        game_date=date(2026, 6, day),
        game_type='R',
        innings_pitched=1.0,
        innings_pitched_outs=3,
        pitches_thrown=12,
        games_started=games_started,
    )


def test_games_started_parser_is_three_state():
    assert parse_games_started('0') == 0
    assert parse_games_started(1) == 1
    assert parse_games_started(None) is None
    assert games_started_state(0) == 'relief'
    assert games_started_state(1) == 'start'
    assert games_started_state(None) == 'unknown'
    assert log_games_started_state(SimpleNamespace(games_started=None)) == 'unknown'
    with pytest.raises(InvalidGamesStartedValue):
        parse_games_started(2)


def test_bullpen_eligibility_does_not_treat_null_as_relief():
    pitcher = SimpleNamespace(position='P', active=True)

    unknown = evaluate_bullpen_eligibility(
        pitcher,
        [LogStub(None)],
        reference_date=date(2026, 6, 8),
    )
    relief = evaluate_bullpen_eligibility(
        pitcher,
        [LogStub(0)],
        reference_date=date(2026, 6, 8),
    )
    start = evaluate_bullpen_eligibility(
        pitcher,
        [LogStub(1)],
        reference_date=date(2026, 6, 8),
    )

    assert unknown['eligible'] is False
    assert unknown['status'] == 'uncertain_bullpen_relevance'
    assert relief['eligible'] is True
    assert relief['status'] == 'bullpen_relevant'
    assert start['eligible'] is False
    assert start['status'] == 'clear_starter'


def test_games_started_backfill_is_null_only_and_idempotent(app, tmp_path):
    with app.app_context():
        resolved_pitcher = _pitcher(101, 'Resolved Pitcher')
        unresolved_pitcher = _pitcher(102, 'Unresolved Pitcher')
        db.session.add_all([
            _game_log(resolved_pitcher, 1001, day=1),
            _game_log(resolved_pitcher, 1002, day=2),
            _game_log(resolved_pitcher, 1003, day=3, games_started=0),
            _game_log(unresolved_pitcher, 2001, day=1),
        ])
        db.session.commit()
        client = FakeClient({
            (101, 2026): [_split(1001, 1), _split(1002, 0), _split(1003, 1)],
            (102, 2026): [_split(9999, 0)],
        })
        checkpoint = tmp_path / 'games_started_checkpoint.json'

        first = backfill_games_started(
            session=db.session,
            client=client,
            checkpoint_path=checkpoint,
            apply=True,
        )
        assert first['rows_resolved'] == 2
        assert first['rows_unresolved'] == 1
        assert first['rows_still_null_after'] == 1

        rows = {
            row.mlb_game_pk: row
            for row in GameLog.query.order_by(GameLog.mlb_game_pk).all()
        }
        assert rows[1001].games_started == 1
        assert rows[1002].games_started == 0
        assert rows[1003].games_started == 0
        assert rows[2001].games_started is None

        second = backfill_games_started(
            session=db.session,
            client=client,
            checkpoint_path=checkpoint,
            apply=True,
        )
        assert second['rows_resolved'] == 0
        assert second['rows_still_null_after'] == 1


def test_game_log_rejects_invalid_games_started_value(app):
    with app.app_context():
        pitcher = _pitcher(201, 'Constraint Pitcher')
        db.session.add(_game_log(pitcher, 3001, games_started=2))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()
