"""Behavior-aware Swing/Bulk eligibility detection.

Phase C3B mapped Role Authority "Ambiguous" onto the ``SWING_BULK_RELIEF``
eligibility type as a flat relabel. This module makes Swing/Bulk a meaningful
internal classification by inspecting the recent game-log window the engines
already use, attaching concrete evidence, and recording the limitation that the
read is retrospective (no probable-starter or scheduled-role data).

It is descriptive and conservative:

* It NEVER changes an engine's ``eligible`` decision, ``role``, or ``status`` —
  only the descriptive ``eligibility_type`` plus evidence and limitations.
* It only upgrades ``NORMAL_RELIEF`` -> ``SWING_BULK_RELIEF`` when the recent
  window shows genuine mixed start/relief usage or a bulk-length relief outing,
  and it enriches payloads already typed ``SWING_BULK_RELIEF``.
* ``STARTER_PROTECTED``, ``EXCLUDED`` and ``UNKNOWN_LIMITED`` payloads are left
  untouched, so rotation arms are never promoted into bullpen depth and missing
  or malformed eligibility stays fail-closed.

No new external data source is used and no probable-starter feed is required.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from services.bullpen_eligibility_vocabulary import (
    ELIGIBILITY_NORMAL_RELIEF,
    ELIGIBILITY_SWING_BULK_RELIEF,
)
from services.role_authority import STARTER_SHARE
from utils.games_started import RELIEF, START, games_started_state
from utils.innings import log_innings_decimal


# Innings at/above which a relief appearance reads as bulk (starter-length) work.
BULK_RELIEF_MIN_INNINGS = 3.0
# Known-start share at/above which a pitcher is a clear starter and must not be
# reclassified as swing/bulk. Mirrors role_authority.STARTER_SHARE.
CLEAR_STARTER_SHARE = STARTER_SHARE

NO_PROBABLE_STARTER_LIMITATION = (
    'Swing/bulk role is inferred from retrospective gamesStarted usage only; no '
    'probable-starter or scheduled-role data is used.'
)

# The eligibility types this module is allowed to act on. Everything else is
# preserved exactly as received.
_REFINABLE_TYPES = frozenset({
    ELIGIBILITY_NORMAL_RELIEF,
    ELIGIBILITY_SWING_BULK_RELIEF,
})


def _log_date(log: Any) -> date:
    return getattr(log, 'game_date', None) or date.min


def _ordered_logs(logs):
    return sorted(list(logs or []), key=_log_date, reverse=True)


def swing_bulk_signals(logs) -> dict[str, Any]:
    """Compute deterministic swing/bulk signals from a recent log window.

    The caller supplies the window (the same recent logs the role engines use).
    Only known start/relief rows feed the start-share and usage signals; rows
    missing gamesStarted are counted separately and never invent a role.
    """
    ordered = _ordered_logs(logs)
    starts = 0
    relief = 0
    unknown = 0
    start_innings: list[float] = []
    bulk_relief_innings: list[float] = []
    states_in_order: list[str] = []

    for log in ordered:
        state = games_started_state(getattr(log, 'games_started', None))
        innings = log_innings_decimal(log)
        if state == START:
            starts += 1
            states_in_order.append(START)
            if innings is not None:
                start_innings.append(innings)
        elif state == RELIEF:
            relief += 1
            states_in_order.append(RELIEF)
            if innings is not None and innings >= BULK_RELIEF_MIN_INNINGS:
                bulk_relief_innings.append(round(innings, 1))

        else:
            unknown += 1

    known = starts + relief
    start_share = round(starts / known, 2) if known else None
    avg_start_innings = round(sum(start_innings) / len(start_innings), 1) if start_innings else None

    # Recent relief after prior starts: most recent known appearance is relief
    # while an earlier appearance in the window was a start.
    recent_relief_after_starts = (
        START in states_in_order
        and states_in_order[0] == RELIEF
    )

    return {
        'recent_starts': starts,
        'recent_relief_appearances': relief,
        'unknown_split_appearances': unknown,
        'known_appearances': known,
        'start_share': start_share,
        'avg_start_innings': avg_start_innings,
        'bulk_relief_innings': bulk_relief_innings,
        'mixed_usage': starts >= 1 and relief >= 1,
        'bulk_relief': len(bulk_relief_innings) >= 1,
        'recent_relief_after_starts': recent_relief_after_starts,
    }


def _evidence_for(signals: dict[str, Any]) -> list[str]:
    evidence = [
        f"{signals['recent_starts']} recent start(s) in the role window.",
        f"{signals['recent_relief_appearances']} recent relief appearance(s) in the role window.",
    ]
    if signals['mixed_usage']:
        evidence.append('Mixed recent usage: both starting and relief appearances in the role window.')
    if signals['recent_relief_after_starts']:
        evidence.append('Most recent appearance is relief following earlier start(s) in the window.')
    if signals['bulk_relief']:
        joined = ', '.join(f'{value:.1f}' for value in signals['bulk_relief_innings'])
        evidence.append(
            f"Bulk relief outing(s) of starter length (>= {BULK_RELIEF_MIN_INNINGS:.1f} IP): {joined}."
        )
    if signals['avg_start_innings'] is not None:
        evidence.append(f"Average start length {signals['avg_start_innings']:.1f} IP.")
    return evidence


def _reason_for(signals: dict[str, Any], engine_reason: str | None) -> str:
    if signals['mixed_usage']:
        return 'Mixed starting and relief usage in the recent window (swing/bulk role).'
    if signals['bulk_relief']:
        return 'Bulk relief outing(s) of starter length in the recent window.'
    return engine_reason or 'Swing/bulk role inferred from ambiguous recent usage.'


def _merge(existing, additions) -> list:
    merged = list(existing or [])
    for item in additions:
        if item not in merged:
            merged.append(item)
    return merged


def refine_swing_bulk_eligibility(eligibility: Any, logs) -> Any:
    """Refine a normalized eligibility payload with swing/bulk classification.

    Returns the payload unchanged for non-dict input, for eligibility types this
    module does not act on, and when no swing/bulk signal is present. When it
    does act it sets ``eligibility_type`` to ``SWING_BULK_RELIEF`` and attaches
    structured signals, evidence, and the no-probable-starter limitation. It
    never alters ``eligible``, ``role``, or ``status``.
    """
    if not isinstance(eligibility, dict):
        return eligibility

    base_type = eligibility.get('eligibility_type')
    if base_type not in _REFINABLE_TYPES:
        return eligibility

    signals = swing_bulk_signals(logs)
    already_swing = base_type == ELIGIBILITY_SWING_BULK_RELIEF
    is_clear_starter = (
        signals['start_share'] is not None
        and signals['start_share'] >= CLEAR_STARTER_SHARE
    )
    detected = (signals['mixed_usage'] or signals['bulk_relief']) and not is_clear_starter

    if not (already_swing or detected):
        return eligibility

    refined = dict(eligibility)
    refined['eligibility_type'] = ELIGIBILITY_SWING_BULK_RELIEF
    refined['swing_bulk'] = signals
    refined['reason'] = _reason_for(signals, eligibility.get('reason'))
    refined['evidence'] = _merge(eligibility.get('evidence'), _evidence_for(signals))
    refined['limitations'] = _merge(eligibility.get('limitations'), [NO_PROBABLE_STARTER_LIMITATION])
    return refined
