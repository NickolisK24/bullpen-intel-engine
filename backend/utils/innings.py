from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


class InvalidInningsNotation(ValueError):
    """Raised when an MLB innings value cannot be represented as whole outs."""


def parse_mlb_innings_to_outs(value: Any) -> int:
    """
    Convert MLB innings notation to total outs.

    MLB stores the digit after the decimal as outs, not tenths:
    2.1 is seven outs, and 2.2 is eight outs.
    """
    if value is None:
        return 0

    text = str(value).strip()
    if text == '':
        return 0
    if text.startswith('-'):
        raise InvalidInningsNotation(f'Innings value must not be negative: {value!r}')

    if '.' in text:
        whole_text, outs_text = text.split('.', 1)
        if outs_text == '':
            outs_text = '0'
        if not outs_text.isdigit() or not whole_text.isdigit():
            raise InvalidInningsNotation(f'Invalid MLB innings value: {value!r}')
        outs_digit = int(outs_text[0])
        if any(char != '0' for char in outs_text[1:]):
            raise InvalidInningsNotation(f'Invalid MLB innings value: {value!r}')
    else:
        if not text.isdigit():
            raise InvalidInningsNotation(f'Invalid MLB innings value: {value!r}')
        whole_text = text
        outs_digit = 0

    if outs_digit not in (0, 1, 2):
        raise InvalidInningsNotation(f'Invalid outs digit in MLB innings value: {value!r}')

    return int(whole_text or 0) * 3 + outs_digit


def outs_to_decimal_innings(outs: Any) -> float:
    if outs is None:
        return 0.0
    try:
        parsed = int(outs)
    except (TypeError, ValueError) as exc:
        raise InvalidInningsNotation(f'Outs value must be an integer: {outs!r}') from exc
    if parsed < 0:
        raise InvalidInningsNotation(f'Outs value must not be negative: {outs!r}')
    return parsed / 3.0


def decimal_innings_to_outs(value: Any, *, tolerance: float = 1e-6) -> int | None:
    """
    Convert canonical decimal innings to outs.

    This is a compatibility fallback for tests and old in-memory objects that do
    not carry innings_pitched_outs. It expects decimals such as 0.333333 or
    0.666667, not MLB box-score notation.
    """
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if numeric < 0:
        return None

    outs = int(round(numeric * 3))
    if math.isclose(numeric, outs_to_decimal_innings(outs), abs_tol=tolerance):
        return outs
    return outs


def log_innings_outs(log: Any) -> int | None:
    outs = getattr(log, 'innings_pitched_outs', None)
    if outs is not None:
        try:
            parsed = int(outs)
        except (TypeError, ValueError):
            return None
        return parsed if parsed >= 0 else None
    return decimal_innings_to_outs(getattr(log, 'innings_pitched', None))


def log_innings_decimal(log: Any) -> float | None:
    outs = log_innings_outs(log)
    if outs is None:
        return None
    return outs_to_decimal_innings(outs)


def sum_log_outs(logs) -> int:
    total = 0
    for log in logs or []:
        outs = log_innings_outs(log)
        if outs is not None:
            total += outs
    return total


def sum_log_innings_decimal(logs) -> float:
    return outs_to_decimal_innings(sum_log_outs(logs))


@dataclass(frozen=True)
class ExistingInningsClassification:
    state: str
    outs: int | None


def classify_existing_decimal_innings(
    value: Any,
    *,
    tolerance: float = 1e-6,
) -> ExistingInningsClassification:
    """
    Classify stored innings_pitched during the one-time backfill.

    Legacy MLB notation has fractional parts near .0, .1, or .2. Canonical
    decimal innings have fractional parts near .0, .333333, or .666667.
    Unexpected fractions are flagged for review.
    """
    if value is None:
        return ExistingInningsClassification('missing', None)
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return ExistingInningsClassification('anomalous', None)
    if numeric < 0:
        return ExistingInningsClassification('anomalous', None)

    whole = math.floor(numeric + tolerance)
    fraction = numeric - whole
    if fraction < 0 and math.isclose(fraction, 0.0, abs_tol=tolerance):
        fraction = 0.0

    legacy_fractions = ((0.0, 0), (0.1, 1), (0.2, 2))
    for expected, outs_digit in legacy_fractions:
        if math.isclose(fraction, expected, abs_tol=tolerance):
            return ExistingInningsClassification('legacy', whole * 3 + outs_digit)

    canonical_fractions = ((1.0 / 3.0, 1), (2.0 / 3.0, 2))
    for expected, outs_digit in canonical_fractions:
        if math.isclose(fraction, expected, abs_tol=tolerance):
            return ExistingInningsClassification('canonical', whole * 3 + outs_digit)

    return ExistingInningsClassification('anomalous', None)
