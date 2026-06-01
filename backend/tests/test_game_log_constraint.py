"""
Database-level tests for the game_logs uniqueness constraint
(uq_game_logs_pitcher_game on pitcher_id + mlb_game_pk).

These run against an in-memory SQLite database created from the models'
metadata via db.create_all(), so they exercise the real constraint defined on
the model (the same one the Alembic migration adds for PostgreSQL) without
needing a Postgres server, the MLB API, or network access.
"""

from datetime import date

import pytest
from flask import Flask
from sqlalchemy.exc import IntegrityError

from utils.db import db
from models.pitcher import Pitcher
from models.game_log import GameLog
import models.fatigue_score  # noqa: F401  (register on db.metadata)
import models.prospect        # noqa: F401  (register on db.metadata)


@pytest.fixture
def app_ctx():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        db.create_all()
        try:
            yield app
        finally:
            db.session.remove()
            db.drop_all()


def _add_pitcher(mlb_id):
    p = Pitcher(mlb_id=mlb_id, full_name=f'Pitcher {mlb_id}', team_id=1, active=True)
    db.session.add(p)
    db.session.commit()
    return p


def _log(pitcher_id, game_pk, day=1):
    return GameLog(pitcher_id=pitcher_id, mlb_game_pk=game_pk,
                   game_date=date(2024, 9, day))


class TestGameLogUniqueness:
    def test_same_pitcher_same_game_is_rejected(self, app_ctx):
        p = _add_pitcher(1)
        db.session.add(_log(p.id, 100))
        db.session.commit()

        # Same pitcher + same game = the same appearance ingested twice.
        db.session.add(_log(p.id, 100))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()

        assert GameLog.query.filter_by(pitcher_id=p.id, mlb_game_pk=100).count() == 1

    def test_same_pitcher_different_game_is_allowed(self, app_ctx):
        p = _add_pitcher(1)
        db.session.add(_log(p.id, 100, day=1))
        db.session.add(_log(p.id, 101, day=2))
        db.session.commit()
        assert GameLog.query.filter_by(pitcher_id=p.id).count() == 2

    def test_different_pitcher_same_game_is_allowed(self, app_ctx):
        # Both teams' pitchers share a gamePk, so the same game across different
        # pitchers must be allowed — that's why the key is the pair, not game_pk.
        p1 = _add_pitcher(1)
        p2 = _add_pitcher(2)
        db.session.add(_log(p1.id, 100))
        db.session.add(_log(p2.id, 100))
        db.session.commit()
        assert GameLog.query.filter_by(mlb_game_pk=100).count() == 2
