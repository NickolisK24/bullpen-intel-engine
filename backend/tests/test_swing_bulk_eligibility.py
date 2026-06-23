"""Tests for behavior-aware Swing/Bulk eligibility detection (Phase C3C).

These exercise the refinement in isolation, the end-to-end composition with the
Role Authority engine, and the fail-closed / starter-protection guarantees.
The refinement only relabels eligibility_type and enriches evidence/limitations;
it never changes the engine's eligible, role, or status.
"""

from datetime import date, timedelta
from types import SimpleNamespace

from services.bullpen_eligibility import evaluate_bullpen_eligibility
from services.bullpen_eligibility_vocabulary import (
    ELIGIBILITY_EXCLUDED,
    ELIGIBILITY_NORMAL_RELIEF,
    ELIGIBILITY_STARTER_PROTECTED,
    ELIGIBILITY_SWING_BULK_RELIEF,
    ELIGIBILITY_UNKNOWN_LIMITED,
    normalize_eligibility,
)
from services.role_authority import (
    ROLE_AMBIGUOUS,
    ROLE_RELIEVER,
    ROLE_STARTER,
    classify_role,
)
from services.swing_bulk_eligibility import (
    BULK_RELIEF_MIN_INNINGS,
    NO_PROBABLE_STARTER_LIMITATION,
    refine_swing_bulk_eligibility,
    swing_bulk_signals,
)

REF = date(2026, 6, 6)


class _Log:
    def __init__(self, outs, games_started, days_ago=1, game_type='R'):
        self.innings_pitched_outs = outs
        self.innings_pitched = outs / 3.0
        self.games_started = games_started
        self.game_date = REF - timedelta(days=days_ago)
        self.game_type = game_type


def _pitcher(position='P', active=True):
    return SimpleNamespace(position=position, active=active)


def _normalized(role=None, status=None, eligible=True, **extra):
    payload = {'eligible': eligible, 'confidence': 'medium', 'reason': 'engine reason'}
    if role is not None:
        payload['role'] = role
    if status is not None:
        payload['status'] = status
    payload.update(extra)
    return normalize_eligibility(payload)


# Recent windows (most-recent-first ordering is handled internally).
RELIEF_ONLY = [_Log(3, 0, 1), _Log(4, 0, 3), _Log(3, 0, 5)]            # 3 short relief outings
MIXED = [_Log(3, 0, 1), _Log(3, 0, 3), _Log(18, 1, 6), _Log(18, 1, 9)]  # 2 relief, 2 starts
BULK_ONLY = [_Log(12, 0, 1), _Log(3, 0, 4)]                            # one 4.0 IP relief outing
STARTER = [_Log(18, 1, 1), _Log(18, 1, 6), _Log(18, 1, 11), _Log(18, 1, 16)]


# ── Refinement: preservation guarantees ─────────────────────────────────────

def test_true_reliever_remains_normal_relief():
    refined = refine_swing_bulk_eligibility(
        _normalized(role=ROLE_RELIEVER, status='role_reliever'), RELIEF_ONLY,
    )
    assert refined['eligibility_type'] == ELIGIBILITY_NORMAL_RELIEF
    assert refined['eligible'] is True
    assert 'swing_bulk' not in refined


def test_relief_only_with_sufficient_usage_is_normal_relief():
    many_relief = [_Log(3, 0, day) for day in (1, 3, 5, 7, 9)]
    refined = refine_swing_bulk_eligibility(
        _normalized(role=ROLE_RELIEVER, status='role_reliever'), many_relief,
    )
    assert refined['eligibility_type'] == ELIGIBILITY_NORMAL_RELIEF


def test_clear_starter_payload_is_left_untouched():
    payload = _normalized(role=ROLE_STARTER, status='role_starter', eligible=False)
    refined = refine_swing_bulk_eligibility(payload, STARTER)
    assert refined['eligibility_type'] == ELIGIBILITY_STARTER_PROTECTED
    assert refined['eligible'] is False
    assert refined == payload


def test_recent_starter_with_one_relief_is_not_promoted():
    # A clear starter who made one relief appearance stays Starter Protected and
    # ineligible; it must not be relabeled swing/bulk or made eligible.
    payload = _normalized(role=ROLE_STARTER, status='role_starter', eligible=False)
    logs = STARTER + [_Log(3, 0, 2)]
    refined = refine_swing_bulk_eligibility(payload, logs)
    assert refined['eligibility_type'] == ELIGIBILITY_STARTER_PROTECTED
    assert refined['eligible'] is False


# ── Refinement: detection ────────────────────────────────────────────────────

def test_mixed_start_and_relief_becomes_swing_bulk():
    refined = refine_swing_bulk_eligibility(
        _normalized(role=ROLE_RELIEVER, status='role_reliever'), MIXED,
    )
    assert refined['eligibility_type'] == ELIGIBILITY_SWING_BULK_RELIEF
    assert refined['eligible'] is True  # unchanged
    assert refined['swing_bulk']['mixed_usage'] is True
    assert any('Mixed recent usage' in line for line in refined['evidence'])


def test_bulk_length_relief_becomes_swing_bulk():
    refined = refine_swing_bulk_eligibility(
        _normalized(role=ROLE_RELIEVER, status='role_reliever'), BULK_ONLY,
    )
    assert refined['eligibility_type'] == ELIGIBILITY_SWING_BULK_RELIEF
    assert refined['swing_bulk']['bulk_relief'] is True
    assert any('Bulk relief outing' in line for line in refined['evidence'])


def test_ambiguous_role_stays_swing_bulk_and_preserves_role():
    payload = _normalized(
        role=ROLE_AMBIGUOUS, status='role_ambiguous',
        limitations=['Swing/ambiguous role caveat.'],
    )
    refined = refine_swing_bulk_eligibility(payload, MIXED)
    assert refined['eligibility_type'] == ELIGIBILITY_SWING_BULK_RELIEF
    assert refined['role'] == ROLE_AMBIGUOUS          # role preserved
    assert refined['eligible'] is True
    assert 'Swing/ambiguous role caveat.' in refined['limitations']


def test_no_probable_starter_limitation_is_added():
    refined = refine_swing_bulk_eligibility(
        _normalized(role=ROLE_RELIEVER, status='role_reliever'), MIXED,
    )
    assert NO_PROBABLE_STARTER_LIMITATION in refined['limitations']


# ── Refinement: fail-closed / non-refinable inputs ──────────────────────────

def test_missing_or_malformed_eligibility_is_unchanged():
    assert refine_swing_bulk_eligibility(None, MIXED) is None
    assert refine_swing_bulk_eligibility('garbage', MIXED) == 'garbage'

    unknown = normalize_eligibility(None)  # C3B fail-closed default
    refined = refine_swing_bulk_eligibility(unknown, MIXED)
    assert refined['eligibility_type'] == ELIGIBILITY_UNKNOWN_LIMITED
    assert refined['eligible'] is False
    assert 'swing_bulk' not in refined


def test_excluded_payload_is_left_untouched():
    payload = _normalized(status='inactive', eligible=False)
    assert payload['eligibility_type'] == ELIGIBILITY_EXCLUDED
    refined = refine_swing_bulk_eligibility(payload, BULK_ONLY)
    assert refined == payload


# ── Signals ──────────────────────────────────────────────────────────────────

def test_swing_bulk_signals_are_deterministic():
    signals = swing_bulk_signals(MIXED)
    assert signals['recent_starts'] == 2
    assert signals['recent_relief_appearances'] == 2
    assert signals['mixed_usage'] is True
    assert signals['start_share'] == 0.5
    assert signals['recent_relief_after_starts'] is True
    assert signals['avg_start_innings'] == 6.0

    bulk = swing_bulk_signals(BULK_ONLY)
    assert bulk['bulk_relief'] is True
    assert bulk['bulk_relief_innings'] == [4.0]
    assert bulk['mixed_usage'] is False


# ── End-to-end with the Role Authority engine ───────────────────────────────

def test_engine_to_refinement_mixed_pitcher_is_swing_bulk():
    result = refine_swing_bulk_eligibility(
        normalize_eligibility(classify_role(_pitcher(), MIXED, reference_date=REF)),
        MIXED,
    )
    assert result['eligibility_type'] == ELIGIBILITY_SWING_BULK_RELIEF
    assert result['eligible'] is True


def test_engine_to_refinement_clear_starter_stays_protected():
    result = refine_swing_bulk_eligibility(
        normalize_eligibility(classify_role(_pitcher(), STARTER, reference_date=REF)),
        STARTER,
    )
    assert result['eligibility_type'] == ELIGIBILITY_STARTER_PROTECTED
    assert result['eligible'] is False


def test_engine_to_refinement_true_reliever_stays_normal():
    result = refine_swing_bulk_eligibility(
        normalize_eligibility(classify_role(_pitcher(), RELIEF_ONLY, reference_date=REF)),
        RELIEF_ONLY,
    )
    assert result['eligibility_type'] == ELIGIBILITY_NORMAL_RELIEF
    assert result['eligible'] is True


def test_legacy_engine_clear_starter_stays_protected():
    starter = evaluate_bullpen_eligibility(_pitcher(), STARTER, reference_date=REF)
    result = refine_swing_bulk_eligibility(normalize_eligibility(starter), STARTER)
    assert result['eligibility_type'] == ELIGIBILITY_STARTER_PROTECTED
    assert result['eligible'] is False


# ── Population wiring (runs only where the app stack is importable) ──────────

def test_population_layer_applies_refinement():
    import pytest
    pytest.importorskip('flask_sqlalchemy')
    from services.bullpen_population import _eligibility_for

    swing = _eligibility_for(_pitcher(), MIXED, {}, REF, use_role_authority=True)
    assert swing['eligibility_type'] == ELIGIBILITY_SWING_BULK_RELIEF
    assert swing['eligible'] is True
    assert 'swing_bulk' in swing

    starter = _eligibility_for(_pitcher(), STARTER, {}, REF, use_role_authority=True)
    assert starter['eligibility_type'] == ELIGIBILITY_STARTER_PROTECTED
    assert starter['eligible'] is False
