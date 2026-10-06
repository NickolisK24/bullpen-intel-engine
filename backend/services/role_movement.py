"""Governed descriptive reliever role-movement classification.

V1 compares two adjacent seven-calendar-day windows of one pitcher's official
relief appearances for one team. It describes completed usage only. It does
not infer manager intent, future availability, health, quality, or a
depth-chart job.

This module is the single owner of role-movement meaning: windows, minimum
evidence, materiality, season-phase comparability, and public copy. Callers
supply already-authoritative per-window counts.
"""

from datetime import timedelta

from services.schedule_absence import POSTSEASON_GAME_TYPES


CONTRACT = 'observed_role_movement_v1'
METHOD_VERSION = 'observed_role_movement_v1'

WINDOW_DAYS = 7
MIN_APPEARANCES_PER_WINDOW = 3
LATE_ENTRY_INNING_MIN = 8

REGULAR_SEASON_GAME_TYPE = 'R'
GAME_TYPES = frozenset({REGULAR_SEASON_GAME_TYPE}) | POSTSEASON_GAME_TYPES

PHASE_REGULAR_SEASON = 'regular_season'
PHASE_POSTSEASON = 'postseason'
PHASE_MIXED = 'mixed'

SIGNAL_LATE_ENTRY = 'eighth_or_later_entry'
SIGNAL_HIGH_LEVERAGE = 'high_recorded_leverage'

MOVEMENT_LATER_OR_HIGHER = 'later_or_higher_leverage'
MOVEMENT_EARLIER_OR_LOWER = 'earlier_or_lower_leverage'
MOVEMENT_STABLE = 'stable'

_PUBLIC_LABELS = {
    ('higher', frozenset({SIGNAL_LATE_ENTRY, SIGNAL_HIGH_LEVERAGE})):
        'Recent deployment shifted toward later-inning, higher-leverage work.',
    ('higher', frozenset({SIGNAL_LATE_ENTRY})):
        'Recent deployment shifted toward later-inning work.',
    ('higher', frozenset({SIGNAL_HIGH_LEVERAGE})):
        'Recent deployment shifted toward higher-leverage work.',
    ('lower', frozenset({SIGNAL_LATE_ENTRY, SIGNAL_HIGH_LEVERAGE})):
        'Recent deployment shifted toward earlier-inning, lower-leverage work.',
    ('lower', frozenset({SIGNAL_LATE_ENTRY})):
        'Recent deployment shifted toward earlier-inning work.',
    ('lower', frozenset({SIGNAL_HIGH_LEVERAGE})):
        'Recent deployment shifted toward lower-leverage work.',
}


def window_bounds(anchor):
    """Inclusive (recent_start, recent_end, prior_start, prior_end) for D."""
    recent_start = anchor - timedelta(days=WINDOW_DAYS - 1)
    prior_end = recent_start - timedelta(days=1)
    prior_start = prior_end - timedelta(days=WINDOW_DAYS - 1)
    return recent_start, anchor, prior_start, prior_end


def season_phase(game_types):
    """One season phase for a window's game types; None for an empty window."""
    phases = {
        PHASE_REGULAR_SEASON if game_type == REGULAR_SEASON_GAME_TYPE else PHASE_POSTSEASON
        for game_type in game_types
    }
    if not phases:
        return None
    return phases.pop() if len(phases) == 1 else PHASE_MIXED


def _count(value):
    return value if type(value) is int and value >= 0 else None


def _signal(name, recent, prior, count_key, known_key):
    rc, rk = _count(recent.get(count_key)), _count(recent.get(known_key))
    pc, pk = _count(prior.get(count_key)), _count(prior.get(known_key))
    if (
        None in (rc, rk, pc, pk)
        or rc > rk or pc > pk
        or rk < MIN_APPEARANCES_PER_WINDOW
        or pk < MIN_APPEARANCES_PER_WINDOW
    ):
        return {
            'name': name,
            'status': 'unavailable',
            'reason_code': 'insufficient_known_evidence',
            'direction': None,
        }
    # Material when the share moves by at least one half: rc/rk - pc/pk >= 1/2,
    # evaluated in exact integer arithmetic rather than rounded floats.
    difference = 2 * (rc * pk - pc * rk)
    if difference >= rk * pk:
        direction = 'higher'
    elif -difference >= rk * pk:
        direction = 'lower'
    else:
        direction = 'stable'
    return {'name': name, 'status': 'complete', 'reason_code': None, 'direction': direction}


def _result(status, *, reason_code=None, movement=None, public_label=None,
            signals=None, phase=None):
    return {
        'contract': CONTRACT,
        'method_version': METHOD_VERSION,
        'status': status,
        'reason_code': reason_code,
        'movement': movement,
        'public_label': public_label,
        'season_phase': phase,
        'signals': signals or [],
    }


def classify_observed_role_movement(*, recent, prior):
    """Classify movement from already-authoritative per-window counts.

    Required window keys: ``appearances``, ``season_phase``,
    ``eighth_or_later_appearances``, ``known_entry_appearances``,
    ``high_leverage_appearances``, ``known_leverage_appearances``.
    """
    recent_apps = _count(recent.get('appearances'))
    prior_apps = _count(prior.get('appearances'))
    if recent_apps is None or recent_apps < MIN_APPEARANCES_PER_WINDOW:
        return _result('unavailable', reason_code='insufficient_recent_appearances')
    if prior_apps is None or prior_apps < MIN_APPEARANCES_PER_WINDOW:
        return _result('unavailable', reason_code='insufficient_prior_appearances')

    phase = recent.get('season_phase')
    if phase not in (PHASE_REGULAR_SEASON, PHASE_POSTSEASON) or prior.get('season_phase') != phase:
        return _result('unavailable', reason_code='season_phase_boundary')

    signals = [
        _signal(SIGNAL_LATE_ENTRY, recent, prior,
                'eighth_or_later_appearances', 'known_entry_appearances'),
        _signal(SIGNAL_HIGH_LEVERAGE, recent, prior,
                'high_leverage_appearances', 'known_leverage_appearances'),
    ]
    complete = [signal for signal in signals if signal['status'] == 'complete']
    if not complete:
        return _result(
            'unavailable',
            reason_code='insufficient_comparable_deployment_evidence',
            signals=signals, phase=phase,
        )

    directions = {signal['direction'] for signal in complete} - {'stable'}
    if len(directions) > 1:
        return _result(
            'unavailable', reason_code='mixed_directional_evidence',
            signals=signals, phase=phase,
        )
    if not directions:
        return _result('complete', movement=MOVEMENT_STABLE, signals=signals, phase=phase)

    direction = directions.pop()
    moved = frozenset(
        signal['name'] for signal in complete if signal['direction'] == direction
    )
    return _result(
        'complete',
        movement=MOVEMENT_LATER_OR_HIGHER if direction == 'higher' else MOVEMENT_EARLIER_OR_LOWER,
        public_label=_PUBLIC_LABELS[(direction, moved)],
        signals=signals,
        phase=phase,
    )
