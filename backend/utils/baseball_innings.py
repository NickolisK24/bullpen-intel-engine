"""Baseball innings formatting helpers.

Public baseball prose and evidence use thirds-of-an-inning notation: the digit
after the decimal is outs recorded, not a base-10 fraction.
"""

from __future__ import annotations

from math import floor, isfinite
from typing import Any


_BASEBALL_OUT_FRACTIONS = {
    0: 0.0,
    1: 0.1,
    2: 0.2,
}


def format_baseball_innings(value: Any) -> str | None:
    """Return innings in baseball notation, e.g. ``7.3333`` -> ``"7.1"``.

    Inputs in already-rendered baseball notation (``2.1`` / ``0.2``) are kept
    as-is. Decimal inning values from calculation layers are converted to the
    nearest out so public copy never emits impossible forms like ``5.7``.
    """

    if value is None or isinstance(value, bool):
        return None
    try:
        innings = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(innings) or innings < 0:
        return None

    whole = int(floor(innings))
    fraction = innings - whole
    if _close(fraction, 0.0) or _close(fraction, 1.0):
        if _close(fraction, 1.0):
            whole += 1
        return f'{whole}.0'

    # Some existing fixtures and upstream feeds already store baseball notation
    # as floats. Preserve those exact one-/two-out markers.
    if _close(fraction, 0.1):
        return f'{whole}.1'
    if _close(fraction, 0.2):
        return f'{whole}.2'

    outs = int(round(fraction * 3))
    if outs <= 0:
        return f'{whole}.0'
    if outs >= 3:
        return f'{whole + 1}.0'
    return f'{whole}.{outs}'


def _close(left: float, right: float) -> bool:
    return abs(left - right) < 0.001


__all__ = ['format_baseball_innings']
