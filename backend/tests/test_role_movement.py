"""Conservative observed role-movement semantics (ML-01)."""

from datetime import date

import pytest

from services import role_movement
from services.role_movement import classify_observed_role_movement


def _window(apps=3, late=0, entry_known=3, high=0, leverage_known=3,
            phase='regular_season'):
    return {
        'appearances': apps,
        'season_phase': phase,
        'eighth_or_later_appearances': late,
        'known_entry_appearances': entry_known,
        'high_leverage_appearances': high,
        'known_leverage_appearances': leverage_known,
    }


def _signal(result, name):
    return next(item for item in result['signals'] if item['name'] == name)


def test_later_and_higher_leverage_usage_is_descriptive_movement():
    result = classify_observed_role_movement(
        prior=_window(late=0, high=0), recent=_window(late=3, high=2),
    )
    assert result['status'] == 'complete'
    assert result['reason_code'] is None
    assert result['movement'] == 'later_or_higher_leverage'
    assert result['public_label'] == (
        'Recent deployment shifted toward later-inning, higher-leverage work.'
    )


def test_earlier_and_lower_leverage_usage_is_descriptive_movement():
    result = classify_observed_role_movement(
        prior=_window(late=3, high=3), recent=_window(late=0, high=1),
    )
    assert result['movement'] == 'earlier_or_lower_leverage'
    assert result['public_label'] == (
        'Recent deployment shifted toward earlier-inning, lower-leverage work.'
    )


def test_stable_usage_is_complete_but_authors_no_public_sentence():
    result = classify_observed_role_movement(
        prior=_window(apps=4, late=2, entry_known=4, high=2, leverage_known=4),
        recent=_window(apps=4, late=3, entry_known=4, high=2, leverage_known=4),
    )
    assert result['status'] == 'complete'
    assert result['movement'] == 'stable'
    assert result['public_label'] is None


def test_one_moving_signal_with_one_stable_signal_names_only_the_moved_dimension():
    result = classify_observed_role_movement(
        prior=_window(late=0, high=1), recent=_window(late=3, high=1),
    )
    assert result['movement'] == 'later_or_higher_leverage'
    assert result['public_label'] == 'Recent deployment shifted toward later-inning work.'
    assert _signal(result, 'high_recorded_leverage')['direction'] == 'stable'


def test_materiality_is_exactly_one_half_without_float_rounding():
    # 1/3 -> 5/6 is exactly 0.5: material.
    material = classify_observed_role_movement(
        prior=_window(late=1, entry_known=3, leverage_known=0),
        recent=_window(apps=6, late=5, entry_known=6, leverage_known=0),
    )
    assert material['movement'] == 'later_or_higher_leverage'
    # 1/3 -> 3/4 is 0.4167: not material.
    below = classify_observed_role_movement(
        prior=_window(late=1, entry_known=3, leverage_known=0),
        recent=_window(apps=4, late=3, entry_known=4, leverage_known=0),
    )
    assert below['movement'] == 'stable'
    # A single changed appearance among three can never be material.
    one = classify_observed_role_movement(
        prior=_window(late=1, leverage_known=0), recent=_window(late=2, leverage_known=0),
    )
    assert one['movement'] == 'stable'


@pytest.mark.parametrize('recent_apps,prior_apps,reason', [
    (2, 3, 'insufficient_recent_appearances'),
    (0, 5, 'insufficient_recent_appearances'),
    (3, 2, 'insufficient_prior_appearances'),
    (4, 0, 'insufficient_prior_appearances'),
])
def test_insufficient_appearances_withhold_instead_of_guessing(recent_apps, prior_apps, reason):
    result = classify_observed_role_movement(
        recent=_window(apps=recent_apps, entry_known=recent_apps, leverage_known=recent_apps),
        prior=_window(apps=prior_apps, entry_known=prior_apps, leverage_known=prior_apps),
    )
    assert result == {
        'contract': 'observed_role_movement_v1',
        'method_version': 'observed_role_movement_v1',
        'status': 'unavailable',
        'reason_code': reason,
        'movement': None,
        'public_label': None,
        'season_phase': None,
        'signals': [],
    }


def test_missing_entry_evidence_uses_only_recorded_leverage():
    result = classify_observed_role_movement(
        prior=_window(entry_known=0, high=0), recent=_window(entry_known=0, high=3),
    )
    assert _signal(result, 'eighth_or_later_entry')['status'] == 'unavailable'
    assert result['public_label'] == 'Recent deployment shifted toward higher-leverage work.'


def test_missing_leverage_evidence_never_claims_leverage_movement():
    result = classify_observed_role_movement(
        prior=_window(late=0, leverage_known=0), recent=_window(late=3, leverage_known=0),
    )
    assert _signal(result, 'high_recorded_leverage')['status'] == 'unavailable'
    assert result['public_label'] == 'Recent deployment shifted toward later-inning work.'
    assert 'leverage' not in result['public_label']


def test_both_evidence_families_unavailable_withhold():
    result = classify_observed_role_movement(
        prior=_window(entry_known=0, leverage_known=0),
        recent=_window(entry_known=0, leverage_known=0),
    )
    assert result['status'] == 'unavailable'
    assert result['reason_code'] == 'insufficient_comparable_deployment_evidence'
    assert result['movement'] is None


def test_partial_known_evidence_must_meet_the_minimum_on_its_own():
    # Three appearances, but only one known entry in the recent window: a
    # single appearance may not stand in for a 100% share.
    result = classify_observed_role_movement(
        prior=_window(late=0, entry_known=3, leverage_known=0),
        recent=_window(late=1, entry_known=1, leverage_known=0),
    )
    assert _signal(result, 'eighth_or_later_entry')['reason_code'] == 'insufficient_known_evidence'
    assert result['status'] == 'unavailable'


def test_conflicting_signals_withhold_rather_than_averaging():
    result = classify_observed_role_movement(
        prior=_window(late=0, high=3), recent=_window(late=3, high=0),
    )
    assert result['status'] == 'unavailable'
    assert result['reason_code'] == 'mixed_directional_evidence'
    assert result['public_label'] is None


@pytest.mark.parametrize('prior_phase,recent_phase', [
    ('regular_season', 'postseason'),
    ('postseason', 'regular_season'),
    ('mixed', 'postseason'),
    ('regular_season', 'mixed'),
    (None, 'regular_season'),
])
def test_season_phase_boundary_is_not_comparable(prior_phase, recent_phase):
    result = classify_observed_role_movement(
        prior=_window(late=0, phase=prior_phase), recent=_window(late=3, phase=recent_phase),
    )
    assert result['status'] == 'unavailable'
    assert result['reason_code'] == 'season_phase_boundary'


def test_postseason_windows_compare_within_the_postseason():
    result = classify_observed_role_movement(
        prior=_window(late=0, phase='postseason'), recent=_window(late=3, phase='postseason'),
    )
    assert result['status'] == 'complete'
    assert result['season_phase'] == 'postseason'


@pytest.mark.parametrize('bad', [None, -1, 1.0, '3', True])
def test_malformed_counts_are_unavailable_not_zero(bad):
    result = classify_observed_role_movement(
        prior=_window(late=bad, leverage_known=0), recent=_window(late=3, leverage_known=0),
    )
    assert result['status'] == 'unavailable'


def test_counts_above_known_denominator_are_rejected():
    result = classify_observed_role_movement(
        prior=_window(late=4, entry_known=3, leverage_known=0),
        recent=_window(late=0, leverage_known=0),
    )
    assert result['reason_code'] == 'insufficient_comparable_deployment_evidence'


@pytest.mark.parametrize('game_types,phase', [
    ((), None),
    (('R', 'R'), 'regular_season'),
    (('F',), 'postseason'),
    (('D', 'L', 'W'), 'postseason'),
    (('R', 'F'), 'mixed'),
])
def test_season_phase_groups_every_postseason_round(game_types, phase):
    assert role_movement.season_phase(game_types) == phase


def test_game_types_are_regular_season_and_mlb_postseason_rounds_only():
    assert role_movement.GAME_TYPES == frozenset({'R', 'F', 'D', 'L', 'W'})


def test_windows_are_adjacent_inclusive_seven_day_spans():
    assert role_movement.window_bounds(date(2026, 10, 6)) == (
        date(2026, 9, 30), date(2026, 10, 6), date(2026, 9, 23), date(2026, 9, 29),
    )


def test_public_copy_is_descriptive_and_never_names_a_job_or_future():
    forbidden = ('closer', 'promot', 'demot', 'trust', 'will ', 'next', 'depth chart', 'save')
    for label in role_movement._PUBLIC_LABELS.values():
        assert label.startswith('Recent deployment shifted toward ')
        for word in forbidden:
            assert word not in label.lower()
