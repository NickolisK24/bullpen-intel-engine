"""Per-appearance leverage role classification (additive, story-ready).

Phase 0 of the Story Quality work found that a per-appearance leverage *role*
is not surfaced to the Story Writer or the Bullpen Context Engine, even though
the raw signal already exists on every game-log row:

    * ``GameLog.leverage_index`` - average leverage index, populated from the MLB
      boxscore (``avgLeverageIndex``) during sync.
    * ``GameLog.save_situation`` / ``hold`` / ``blown_save`` - categorical
      high-leverage markers used as a fallback when the index is missing.

``pitcher_role`` already consumes the *average* leverage index per pitcher, but
nothing buckets an individual appearance as high- vs. low-leverage, which is the
distinction needed to say *how* a reintroduced arm re-entered (the low-leverage
door vs. the close) - the read that made the Cardinals card land.

This module is intentionally additive: it reads existing fields only, adds no
new data source, computes no true leverage index, and changes no existing
output. It buckets the leverage already recorded so a story writer can surface
appearance-level leverage role when it wants to.
"""

from __future__ import annotations

from services.workload_appearance import is_workload_appearance_log


CAPABILITY = 'appearance_leverage_v1'
VERSION = '2026-06-21.v1'

# Thresholds mirror services.pitcher_role (HIGH_LEVERAGE = 1.5) so the two
# surfaces agree on what "high leverage" means. The low boundary brackets
# mop-up / long-relief outings; anything between reads as medium leverage.
HIGH_LEVERAGE_INDEX = 1.5
LOW_LEVERAGE_INDEX = 0.85

ROLE_HIGH = 'high_leverage'
ROLE_MEDIUM = 'medium_leverage'
ROLE_LOW = 'low_leverage'
ROLE_UNKNOWN = 'unknown'

BASIS_INDEX = 'leverage_index'
BASIS_SAVE_HOLD = 'save_or_hold_flag'
BASIS_NONE = 'no_leverage_signal'


def _value(log, name, default=None):
    if isinstance(log, dict):
        return log.get(name, default)
    return getattr(log, name, default)


def _float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _flag(log, name):
    return bool(_value(log, name, False))


def classify_appearance_leverage(log) -> dict:
    """Classify a single appearance as high / medium / low leverage.

    Uses the recorded leverage index first; falls back to save/hold/blown-save
    flags when the index is missing; returns ``unknown`` when neither is present.
    """
    leverage_index = _float(_value(log, 'leverage_index'))
    if leverage_index is not None:
        if leverage_index >= HIGH_LEVERAGE_INDEX:
            role = ROLE_HIGH
        elif leverage_index <= LOW_LEVERAGE_INDEX:
            role = ROLE_LOW
        else:
            role = ROLE_MEDIUM
        return {
            'role': role,
            'leverage_index': round(leverage_index, 2),
            'basis': BASIS_INDEX,
            'is_high_leverage': role == ROLE_HIGH,
            'is_low_leverage': role == ROLE_LOW,
        }

    if _flag(log, 'save_situation') or _flag(log, 'hold') or _flag(log, 'blown_save'):
        return {
            'role': ROLE_HIGH,
            'leverage_index': None,
            'basis': BASIS_SAVE_HOLD,
            'is_high_leverage': True,
            'is_low_leverage': False,
        }

    return {
        'role': ROLE_UNKNOWN,
        'leverage_index': None,
        'basis': BASIS_NONE,
        'is_high_leverage': False,
        'is_low_leverage': False,
    }


def _sort_key(log):
    game_date = _value(log, 'game_date')
    return (game_date is not None, str(game_date or ''))


def summarize_reliever_leverage(logs) -> dict:
    """Summarize appearance-level leverage role across a reliever's outings.

    Only valid workload appearances are counted. The summary is descriptive (no
    prediction, ranking, or role authority) and is shaped for a story writer to
    answer "how did this arm enter recently - the close or the low-leverage
    door?".
    """
    appearances = [log for log in (logs or []) if is_workload_appearance_log(log)]
    appearances.sort(key=_sort_key)

    classifications = [classify_appearance_leverage(log) for log in appearances]
    counts = {
        ROLE_HIGH: 0,
        ROLE_MEDIUM: 0,
        ROLE_LOW: 0,
        ROLE_UNKNOWN: 0,
    }
    for item in classifications:
        counts[item['role']] = counts.get(item['role'], 0) + 1

    known = counts[ROLE_HIGH] + counts[ROLE_MEDIUM] + counts[ROLE_LOW]
    high_share = round(counts[ROLE_HIGH] / known, 2) if known else None
    most_recent = classifications[-1] if classifications else None

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'appearances': len(appearances),
        'classified_appearances': known,
        'high_leverage_count': counts[ROLE_HIGH],
        'medium_leverage_count': counts[ROLE_MEDIUM],
        'low_leverage_count': counts[ROLE_LOW],
        'unknown_leverage_count': counts[ROLE_UNKNOWN],
        'high_leverage_share': high_share,
        'most_recent_role': most_recent['role'] if most_recent else ROLE_UNKNOWN,
        'most_recent_basis': most_recent['basis'] if most_recent else BASIS_NONE,
        # The role of the latest appearance answers how a reintroduced arm
        # re-entered: a low-leverage door vs. the close.
        'reentered_low_leverage': bool(most_recent and most_recent['is_low_leverage']),
        'reentered_high_leverage': bool(most_recent and most_recent['is_high_leverage']),
    }


__all__ = [
    'CAPABILITY',
    'VERSION',
    'HIGH_LEVERAGE_INDEX',
    'LOW_LEVERAGE_INDEX',
    'ROLE_HIGH',
    'ROLE_MEDIUM',
    'ROLE_LOW',
    'ROLE_UNKNOWN',
    'classify_appearance_leverage',
    'summarize_reliever_leverage',
]
