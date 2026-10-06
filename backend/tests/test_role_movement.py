"""Tests for conservative observed role movement semantics."""

from services.role_movement import classify_observed_role_movement


def _window(
    apps=3,
    late=0,
    entry_known=3,
    high=0,
    leverage_known=3,
):
    return {
        "appearances": apps,
        "eighth_or_later_appearances": late,
        "known_entry_appearances": entry_known,
        "high_leverage_appearances": high,
        "known_leverage_appearances": leverage_known,
    }


def test_more_late_and_high_leverage_usage_is_descriptive_movement():
    result = classify_observed_role_movement(
        prior=_window(late=0, high=0),
        recent=_window(late=3, high=2),
    )
    assert result["status"] == "complete"
    assert result["movement"] == "later_or_higher_leverage"
    assert "shifted toward later or higher-leverage work" in result["public_label"]


def test_less_late_and_high_leverage_usage_is_descriptive_movement():
    result = classify_observed_role_movement(
        prior=_window(late=3, high=3),
        recent=_window(late=0, high=1),
    )
    assert result["status"] == "complete"
    assert result["movement"] == "earlier_or_lower_leverage"


def test_small_share_changes_remain_stable():
    result = classify_observed_role_movement(
        prior=_window(apps=4, late=2, entry_known=4, high=2, leverage_known=4),
        recent=_window(apps=4, late=3, entry_known=4, high=2, leverage_known=4),
    )
    assert result["status"] == "complete"
    assert result["movement"] == "stable"


def test_sparse_windows_withhold_instead_of_guessing():
    result = classify_observed_role_movement(
        prior=_window(apps=1, late=1, entry_known=1, high=1, leverage_known=1),
        recent=_window(),
    )
    assert result == {
        "contract": "observed_role_movement_v1",
        "method_version": "observed_role_movement_v1",
        "status": "unavailable",
        "reason_code": "insufficient_appearances",
    }


def test_missing_leverage_can_use_complete_entry_evidence_without_fabricating_li():
    result = classify_observed_role_movement(
        prior=_window(late=0, entry_known=3, high=0, leverage_known=0),
        recent=_window(late=3, entry_known=3, high=0, leverage_known=0),
    )
    assert result["status"] == "complete"
    assert result["movement"] == "later_or_higher_leverage"
    leverage = next(item for item in result["signals"] if item["name"] == "high_leverage_share")
    assert leverage["status"] == "unavailable"


def test_mixed_directional_evidence_withholds_public_movement():
    result = classify_observed_role_movement(
        prior=_window(late=0, high=3),
        recent=_window(late=3, high=0),
    )
    assert result["status"] == "unavailable"
    assert result["reason_code"] == "mixed_directional_evidence"


def test_invalid_known_counts_are_unavailable_not_zero():
    result = classify_observed_role_movement(
        prior=_window(late=0, entry_known=0, high=0, leverage_known=0),
        recent=_window(late=0, entry_known=0, high=0, leverage_known=0),
    )
    assert result["status"] == "unavailable"
    assert result["reason_code"] == "insufficient_comparable_deployment_evidence"
