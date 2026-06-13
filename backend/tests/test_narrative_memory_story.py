import json

from services.narrative_memory_story import (
    story_safe_pitcher_usage_trend,
    story_safe_workload_concentration,
    story_safe_workload_easing,
)


def _contract(state, capability='test_continuity', window_days=10, evidence=None):
    return {
        'capability': capability,
        'state': state,
        'window_days': window_days,
        'window_start': '2026-06-03',
        'window_end': '2026-06-12',
        'data_through_date': '2026-06-12',
        'evidence': evidence or {},
        'limitations': ['Test limitation.'],
    }


def test_strong_workload_concentration_creates_story_safe_note():
    result = story_safe_workload_concentration(110, _contract(
        'concentrated',
        evidence={
            'bullpen_appearances': 10,
            'observed_bullpen_games': 6,
            'top_two_pitchers': [
                {'pitcher_id': 1, 'pitcher_name': 'Core Arm One', 'appearances': 5},
                {'pitcher_id': 2, 'pitcher_name': 'Core Arm Two', 'appearances': 3},
            ],
            'top_two_appearance_share': 0.8,
            'core_arm_appearance_share': 0.8,
        },
    ))

    assert result['team_id'] == 110
    assert result['continuity']['type'] == 'workload_concentration'
    assert result['continuity']['data_through_date'] == '2026-06-12'
    assert 'handled 8 of 10 bullpen appearances' in result['continuity_note']
    assert 'Narrative Memory' not in json.dumps(result)


def test_workload_easing_creates_story_safe_note():
    result = story_safe_workload_easing(111, _contract(
        'workload_easing',
        window_days=14,
        evidence={
            'prior_segment': {'appearances': 8, 'rested_options': 1},
            'recent_segment': {'appearances': 3, 'rested_options': 4},
            'workload_easing_signal_count': 3,
        },
    ))

    assert result['continuity']['type'] == 'workload_easing'
    assert result['continuity']['window_days'] == 14
    assert result['continuity_note'] == (
        'Bullpen flexibility has improved over the last 14 days: rested options rose '
        'from 1 to 4, while recent appearances dropped from 8 to 3.'
    )


def test_weak_or_sparse_continuity_suppresses_story_note():
    sparse = story_safe_workload_concentration(112, _contract(
        'concentrated',
        evidence={
            'bullpen_appearances': 4,
            'observed_bullpen_games': 2,
            'top_two_pitchers': [{'pitcher_id': 1, 'pitcher_name': 'Arm', 'appearances': 4}],
            'top_two_appearance_share': 1.0,
            'core_arm_appearance_share': 1.0,
        },
    ))
    one_signal = story_safe_workload_easing(112, _contract(
        'workload_easing',
        window_days=14,
        evidence={
            'prior_segment': {'appearances': 5, 'rested_options': 2},
            'recent_segment': {'appearances': 4, 'rested_options': 2},
            'workload_easing_signal_count': 1,
        },
    ))

    assert sparse is None
    assert one_signal is None


def test_pitcher_usage_trend_note_is_factual_and_safe():
    result = story_safe_pitcher_usage_trend(113, _contract(
        'accelerating',
        evidence={
            'pitcher_id': 7,
            'pitcher_name': 'Recent Arm',
            'appearance_frequency': [
                {'game_window': 6, 'observed_games': 6, 'appearances': 4},
            ],
        },
    ))

    assert result['continuity']['type'] == 'pitcher_usage_trend'
    assert result['continuity_note'] == 'Recent Arm has appeared in 4 of the last 6 observed bullpen games.'
    serialized = json.dumps(result).lower()
    for forbidden in (
        'narrative memory',
        'developing for',
        'algorithm',
        'model',
        'fatigue score',
        'confidence score',
        'health',
        'manager trust',
        'closer',
    ):
        assert forbidden not in serialized
