"""
Freshness degradation classification tests.

Covers the fresh / stale / unavailable boundaries of the fail-closed
degradation tier. Pure functions — no DB or network.
"""

from services.sync_metadata import (
    DEGRADATION_FRESH,
    DEGRADATION_MISSING,
    DEGRADATION_STALE,
    DEGRADATION_UNAVAILABLE,
    build_degradation_block,
    classify_freshness_degradation,
)


STALE_AFTER = 14
UNAVAILABLE_AFTER = 30


def _classify(age):
    return classify_freshness_degradation(age, STALE_AFTER, UNAVAILABLE_AFTER)


class TestBoundaries:
    def test_below_stale_is_fresh(self):
        assert _classify(0) == DEGRADATION_FRESH
        assert _classify(13) == DEGRADATION_FRESH

    def test_at_stale_threshold_is_stale(self):
        # Inclusive at the degrading edge — no silent gap.
        assert _classify(14) == DEGRADATION_STALE

    def test_between_thresholds_is_stale(self):
        assert _classify(15) == DEGRADATION_STALE
        assert _classify(29) == DEGRADATION_STALE

    def test_at_unavailable_threshold_fails_closed(self):
        assert _classify(30) == DEGRADATION_UNAVAILABLE

    def test_beyond_unavailable_threshold_fails_closed(self):
        assert _classify(31) == DEGRADATION_UNAVAILABLE
        assert _classify(400) == DEGRADATION_UNAVAILABLE

    def test_missing_data_is_missing(self):
        assert _classify(None) == DEGRADATION_MISSING


class TestDegradationBlock:
    def test_fresh_block_is_not_fail_closed(self):
        block = build_degradation_block(5)
        assert block['state'] == DEGRADATION_FRESH
        assert block['fail_closed'] is False
        assert block['stale_after_days'] == STALE_AFTER
        assert block['unavailable_after_days'] == UNAVAILABLE_AFTER

    def test_stale_block_is_not_fail_closed(self):
        block = build_degradation_block(20)
        assert block['state'] == DEGRADATION_STALE
        assert block['fail_closed'] is False

    def test_unavailable_block_fails_closed(self):
        block = build_degradation_block(45)
        assert block['state'] == DEGRADATION_UNAVAILABLE
        assert block['fail_closed'] is True

    def test_missing_block_fails_closed(self):
        block = build_degradation_block(None)
        assert block['state'] == DEGRADATION_MISSING
        assert block['fail_closed'] is True
