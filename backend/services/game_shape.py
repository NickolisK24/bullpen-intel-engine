"""Game Shape classification infrastructure.

BaseballOS understands pitchers but not the *shape* of a game. Openers, bulk
followers, and bullpen games are invisible to the rotation/bullpen metrics,
which distorts starter averages and bullpen-burden reads. This module adds a
deterministic, game-level classifier built only on data available today
(``games_started`` and recorded outs per appearance).

It is infrastructure only: it classifies and exposes metadata. It does not
change any metric, average, story, or UI. Metric integration belongs to a later
phase.

Classification is per game (one team's pitching lines for one ``mlb_game_pk``),
never per pitcher.
"""

from __future__ import annotations

from typing import Any

from utils.games_started import RELIEF, START, games_started_state
from utils.innings import outs_to_decimal_innings


CAPABILITY = 'game_shape_v1'
VERSION = '2026-06-23.v1'

# ── Game Shape vocabulary ────────────────────────────────────────────────────
SHAPE_NORMAL_START = 'normal_start'
SHAPE_SHORT_START = 'short_start'
SHAPE_OPENER_BULK_GAME = 'opener_bulk_game'
SHAPE_BULLPEN_GAME = 'bullpen_game'
SHAPE_SUSPENDED_RESUMED_GAME = 'suspended_resumed_game'
SHAPE_INJURY_EARLY_EXIT = 'injury_early_exit'
SHAPE_UNKNOWN = 'unknown'

GAME_SHAPES = frozenset({
    SHAPE_NORMAL_START,
    SHAPE_SHORT_START,
    SHAPE_OPENER_BULK_GAME,
    SHAPE_BULLPEN_GAME,
    SHAPE_SUSPENDED_RESUMED_GAME,
    SHAPE_INJURY_EARLY_EXIT,
    SHAPE_UNKNOWN,
})

# Shapes the MVP can reliably detect from stored game logs today. The remaining
# vocabulary values are defined for the C3G+ roadmap but are not yet inferred
# (see DETECTION_GAPS) and currently resolve to other shapes or UNKNOWN.
DETECTABLE_GAME_SHAPES = frozenset({
    SHAPE_NORMAL_START,
    SHAPE_SHORT_START,
    SHAPE_OPENER_BULK_GAME,
    SHAPE_BULLPEN_GAME,
    SHAPE_UNKNOWN,
})

DETECTION_GAPS = {
    SHAPE_SUSPENDED_RESUMED_GAME: (
        'Suspended/resumed games are not detectable: game logs store no game '
        'status and no link between the original and resumed game.'
    ),
    SHAPE_INJURY_EARLY_EXIT: (
        'Injury/early-exit starts are not distinguishable from tactical short '
        'starts: game logs carry no exit-reason signal, so both read as a short '
        'start.'
    ),
}

# ── Deterministic thresholds (outs-based) ────────────────────────────────────
# A start of five-plus innings reads as a normal start; this mirrors
# rotation_context.EARLY_BULLPEN_ENTRY_OUTS (15 outs).
NORMAL_START_MIN_OUTS = 15
# A credited start this short reads as opener usage; mirrors
# role_authority.OPENER_MAX_AVG_START_IP (2.0 IP = 6 outs).
OPENER_MAX_OUTS = 6
# A follower covering three-plus innings behind an opener reads as the bulk arm.
BULK_FOLLOWER_MIN_OUTS = 9

SHORT_START_LIMITATION = (
    'A short start cannot be separated from an injury/early exit without an '
    'exit-reason signal.'
)


def _value(log: Any, name: str, default=None):
    if isinstance(log, dict):
        return log.get(name, default)
    return getattr(log, name, default)


def _state(log: Any) -> str:
    try:
        return games_started_state(_value(log, 'games_started'))
    except Exception:
        # Malformed gamesStarted values never invent a start/relief role.
        return 'unknown'


def _outs(log: Any) -> int | None:
    raw = _value(log, 'innings_pitched_outs')
    if raw is None:
        return None
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _ip(outs: int | None):
    if outs is None:
        return None
    return outs_to_decimal_innings(outs)


def _result(shape, reason, *, starter_outs=None, bullpen_outs=0, start_count=0,
            relief_count=0, unknown_count=0, evidence=None, limitations=None):
    return {
        'shape': shape,
        'reason': reason,
        'starter_outs': starter_outs,
        'bullpen_outs': bullpen_outs,
        'start_count': start_count,
        'relief_count': relief_count,
        'unknown_count': unknown_count,
        'evidence': list(evidence or []),
        'limitations': list(limitations or []),
    }


def classify_game_shape(game_logs) -> dict[str, Any]:
    """Classify the shape of one team's game from its pitching lines.

    Deterministic and conservative: incomplete or conflicting inputs resolve to
    ``UNKNOWN`` rather than guessing. Returns a serializable payload with the
    shape, the reason, the underlying counts, and any limitations.
    """
    logs = list(game_logs or [])
    if not logs:
        return _result(SHAPE_UNKNOWN, 'no_game_logs')

    start_outs: list[int] = []
    relief_outs: list[int] = []
    missing_start_innings = 0
    missing_relief_innings = 0
    unknown_split = 0

    for log in logs:
        state = _state(log)
        outs = _outs(log)
        if state == START:
            if outs is None:
                missing_start_innings += 1
            else:
                start_outs.append(outs)
        elif state == RELIEF:
            if outs is None:
                missing_relief_innings += 1
            else:
                relief_outs.append(outs)
        else:
            unknown_split += 1

    start_count = len(start_outs) + missing_start_innings
    relief_count = len(relief_outs) + missing_relief_innings
    bullpen_outs = sum(relief_outs)
    base_counts = {
        'start_count': start_count,
        'relief_count': relief_count,
        'unknown_count': unknown_split,
        'bullpen_outs': bullpen_outs,
    }

    # Conflicting or incomplete starter data cannot anchor a shape.
    if missing_start_innings:
        return _result(SHAPE_UNKNOWN, 'missing_starter_innings', **base_counts)
    if unknown_split:
        return _result(SHAPE_UNKNOWN, 'unknown_start_rows', **base_counts)
    if len(start_outs) > 1:
        return _result(SHAPE_UNKNOWN, 'multiple_starters', **base_counts)

    if len(start_outs) == 0:
        if relief_outs:
            return _result(
                SHAPE_BULLPEN_GAME, 'no_qualifying_starter',
                evidence=[f'{relief_count} relief appearance(s) and no credited starter.'],
                **base_counts,
            )
        return _result(SHAPE_UNKNOWN, 'no_pitching_data', **base_counts)

    starter_outs = start_outs[0]
    max_relief_outs = max(relief_outs) if relief_outs else 0
    starter_ip = _ip(starter_outs)
    evidence = [f'Starter recorded {starter_outs} out(s) ({starter_ip:.1f} IP).']
    limitations = []
    if missing_relief_innings:
        limitations.append(
            'Some relief appearances are missing recorded outs, so bulk-follower '
            'length may be understated.'
        )

    if starter_outs <= OPENER_MAX_OUTS and max_relief_outs >= BULK_FOLLOWER_MIN_OUTS:
        evidence.append(
            f'A follower covered {max_relief_outs} out(s) '
            f'({_ip(max_relief_outs):.1f} IP) behind a short starter.'
        )
        return _result(
            SHAPE_OPENER_BULK_GAME, 'opener_with_bulk_follower',
            starter_outs=starter_outs, evidence=evidence, limitations=limitations,
            **base_counts,
        )

    if starter_outs >= NORMAL_START_MIN_OUTS:
        return _result(
            SHAPE_NORMAL_START, 'starter_length_at_or_above_threshold',
            starter_outs=starter_outs, evidence=evidence, limitations=limitations,
            **base_counts,
        )

    limitations.append(SHORT_START_LIMITATION)
    return _result(
        SHAPE_SHORT_START, 'starter_length_below_threshold',
        starter_outs=starter_outs, evidence=evidence, limitations=limitations,
        **base_counts,
    )


def game_shape_of(game_logs) -> str:
    """Return only the classified shape constant for one game's logs."""
    return classify_game_shape(game_logs)['shape']
