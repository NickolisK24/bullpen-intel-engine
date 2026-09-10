from types import SimpleNamespace

import pytest

from services.innings_backfill import (
    resolve_missing_innings_outs,
)
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


def test_missing_outs_repair_resolves_legacy_notation():
    row = SimpleNamespace(innings_pitched=1.1)

    repair = resolve_missing_innings_outs(row)

    assert repair.state == 'legacy'
    assert repair.outs == 4
    assert repair.innings_pitched == pytest.approx(4 / 3)


def test_missing_outs_repair_flags_anomalous_fraction():
    row = SimpleNamespace(innings_pitched=1.5)

    repair = resolve_missing_innings_outs(row)

    assert repair.state == 'anomalous'
    assert repair.outs is None
    assert repair.innings_pitched is None
