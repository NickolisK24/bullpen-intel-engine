"""Unit tests for the SC-03B-07 active-bullpen coverage contract (pure math)."""

import pytest

from services.team_readiness_coverage import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_UNKNOWN,
    DATA_STATE_FRESH,
    DATA_STATE_INCOMPLETE,
    DATA_STATE_MISSING,
    DATA_STATE_STALE,
    PARTIAL_COVERAGE_LIMITATION_CODE,
    assess_team_coverage,
)


def _assess(active, usable, **kw):
    unresolved = kw.pop('unresolved', active - usable)
    return assess_team_coverage(
        authority_complete=kw.pop('authority_complete', True),
        source_current=kw.pop('source_current', True),
        active_bullpen_count=active,
        usable_record_count=usable,
        unresolved_record_count=unresolved,
        **kw,
    )


# -- unknown fails closed --------------------------------------------------------


def test_no_authority_is_unknown_not_low():
    a = _assess(8, 8, authority_complete=False)
    assert a.confidence == CONFIDENCE_UNKNOWN
    assert a.data_state == DATA_STATE_MISSING


def test_zero_active_bullpen_is_unknown():
    a = _assess(0, 0)
    assert a.confidence == CONFIDENCE_UNKNOWN
    assert a.data_state == DATA_STATE_MISSING


# -- high ------------------------------------------------------------------------


def test_all_usable_is_high_fresh():
    a = _assess(8, 8)
    assert a.confidence == CONFIDENCE_HIGH
    assert a.data_state == DATA_STATE_FRESH
    assert a.coverage_limitation() is None


def test_small_but_complete_bullpen_is_high():
    a = _assess(5, 5)
    assert a.confidence == CONFIDENCE_HIGH


# -- medium (approved worked examples) -------------------------------------------


@pytest.mark.parametrize('active,usable', [(8, 6), (8, 7), (9, 7), (9, 8), (7, 6)])
def test_bounded_partial_is_medium_fresh(active, usable):
    a = _assess(active, usable)
    assert a.confidence == CONFIDENCE_MEDIUM
    assert a.data_state == DATA_STATE_FRESH
    lim = a.coverage_limitation()
    assert lim == {
        'code': PARTIAL_COVERAGE_LIMITATION_CODE,
        'active_bullpen_count': active,
        'usable_record_count': usable,
        'unresolved_record_count': active - usable,
    }


# -- low (insufficient coverage) -------------------------------------------------


@pytest.mark.parametrize('active,usable', [(8, 5), (9, 6), (7, 5)])
def test_insufficient_coverage_is_low_incomplete(active, usable):
    a = _assess(active, usable)
    assert a.confidence == CONFIDENCE_LOW
    assert a.data_state == DATA_STATE_INCOMPLETE


def test_five_arms_cannot_be_medium():
    # 5 arms, 4 usable: below the six-usable minimum -> low, never medium.
    a = _assess(5, 4)
    assert a.confidence == CONFIDENCE_LOW


def test_more_than_two_unresolved_cannot_be_medium():
    # 10 arms, 7 usable => 3 unresolved: fails the <=2 unresolved gate even though
    # 7 >= 6 and 70% ... (70% also fails 75%, but the unresolved gate is independent).
    a = _assess(10, 8)  # 8 usable, 2 unresolved, 80% -> medium
    assert a.confidence == CONFIDENCE_MEDIUM
    b = _assess(10, 7)  # 7 usable, 3 unresolved -> low
    assert b.confidence == CONFIDENCE_LOW


def test_seventy_five_percent_is_the_exact_boundary():
    # 8/6 = exactly 75% -> medium; 8/5 = 62.5% -> low.
    assert _assess(8, 6).confidence == CONFIDENCE_MEDIUM
    assert _assess(8, 5).confidence == CONFIDENCE_LOW


# -- source conditions dominate coverage -----------------------------------------


def test_material_conflict_is_low_even_when_fully_covered():
    a = _assess(8, 8, source_conflict=True)
    assert a.confidence == CONFIDENCE_LOW
    assert a.data_state == DATA_STATE_INCOMPLETE


def test_incomplete_source_window_is_low():
    a = _assess(8, 8, source_window_complete=False)
    assert a.confidence == CONFIDENCE_LOW
    assert a.data_state == DATA_STATE_INCOMPLETE


def test_stale_source_is_low_stale():
    a = _assess(8, 8, source_current=False)
    assert a.confidence == CONFIDENCE_LOW
    assert a.data_state == DATA_STATE_STALE


# -- determinism -----------------------------------------------------------------


def test_coverage_math_is_integer_deterministic():
    # No floats anywhere in the boundary decision.
    for active in range(1, 16):
        for usable in range(0, active + 1):
            a = _assess(active, usable)
            assert a.confidence in {
                CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW, CONFIDENCE_UNKNOWN,
            }
            # medium <=> approved gate
            if a.confidence == CONFIDENCE_MEDIUM:
                assert usable >= 6 and (active - usable) <= 2 and usable * 4 >= active * 3
                assert usable != active  # all-usable is high, not medium
