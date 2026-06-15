from datetime import date

import pytest
from flask import Flask

from models.game_log import GameLog
from models.pitcher import Pitcher
from services.innings_backfill import (
    backfill_game_log_innings_outs,
    count_raw_mlb_fraction_rows,
)
from utils.db import db
from utils.innings import (
    InvalidInningsNotation,
    outs_to_decimal_innings,
    parse_mlb_innings_to_outs,
    sum_log_innings_decimal,
)


class LogStub:
    def __init__(self, outs):
        self.innings_pitched_outs = outs
        self.innings_pitched = outs_to_decimal_innings(outs)


@pytest.mark.parametrize(
    ('raw', 'outs', 'decimal'),
    [
        ('0.0', 0, 0.0),
        ('0.1', 1, 1 / 3),
        ('0.2', 2, 2 / 3),
        ('1.0', 3, 1.0),
        ('2.1', 7, 2 + 1 / 3),
        ('2.2', 8, 2 + 2 / 3),
    ],
)
def test_parse_mlb_innings_notation_to_outs(raw, outs, decimal):
    assert parse_mlb_innings_to_outs(raw) == outs
    assert outs_to_decimal_innings(outs) == pytest.approx(decimal)


def test_parse_mlb_innings_rejects_out_of_range_out_digit():
    with pytest.raises(InvalidInningsNotation):
        parse_mlb_innings_to_outs('1.3')


def test_aggregation_sums_outs_before_decimal_conversion():
    logs = [LogStub(2), LogStub(2), LogStub(2)]

    assert sum_log_innings_decimal(logs) == 2.0


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    flask_app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(flask_app)

    with flask_app.app_context():
        db.create_all()
        pitcher = Pitcher(mlb_id=1, full_name='Reliever A', active=True)
        db.session.add(pitcher)
        db.session.commit()
        yield flask_app
        db.session.remove()
        db.drop_all()


def _game_log(game_pk, innings_pitched):
    return GameLog(
        pitcher_id=1,
        mlb_game_pk=game_pk,
        game_date=date(2026, 6, 1),
        game_type='R',
        innings_pitched=innings_pitched,
        pitches_thrown=10,
    )


def test_backfill_converts_legacy_notation_and_is_idempotent(app):
    with app.app_context():
        db.session.add_all([
            _game_log(1001, 0.1),
            _game_log(1002, 0.2),
            _game_log(1003, 1.0),
            _game_log(1004, 1 / 3),
            _game_log(1005, 1.5),
        ])
        db.session.commit()

        stats = backfill_game_log_innings_outs(db.session, apply=True)

        assert stats.rows_converted == 3
        assert stats.rows_decimal_corrected == 2
        assert stats.rows_already_canonical == 1
        assert stats.rows_flagged_anomalous == 1
        assert stats.aggregate_ip_before == pytest.approx(3.1333333333333333)
        assert stats.aggregate_ip_after == pytest.approx(3.833333333333333)
        assert count_raw_mlb_fraction_rows(db.session) == 0

        rows = {
            log.mlb_game_pk: log
            for log in GameLog.query.order_by(GameLog.mlb_game_pk).all()
        }
        assert rows[1001].innings_pitched_outs == 1
        assert rows[1001].innings_pitched == pytest.approx(1 / 3)
        assert rows[1002].innings_pitched_outs == 2
        assert rows[1002].innings_pitched == pytest.approx(2 / 3)
        assert rows[1003].innings_pitched_outs == 3
        assert rows[1003].innings_pitched == pytest.approx(1.0)
        assert rows[1004].innings_pitched_outs == 1
        assert rows[1004].innings_pitched == pytest.approx(1 / 3)
        assert rows[1005].innings_pitched_outs is None
        assert rows[1005].innings_pitched == pytest.approx(1.5)

        second = backfill_game_log_innings_outs(db.session, apply=True)
        assert second.rows_converted == 0
        assert second.rows_already_canonical == 4
        assert second.rows_flagged_anomalous == 1
        assert count_raw_mlb_fraction_rows(db.session) == 0
