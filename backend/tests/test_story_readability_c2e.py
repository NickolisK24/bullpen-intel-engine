"""Readability / metric-density checks (Phase C2E).

Readability-only: beats carry fewer competing numbers (one meaningful number per
beat where practical), analyst phrasing ("percentage points above baseline",
"route overlap") is gone, and the longest families are trimmed — without losing
the key facts or changing payload shape, beat structure, or governance.
"""

import re

from services.story_construction_engine import construct_team_story_frames
from services.story_observation_engine import (
    TYPE_BRIDGE_INSTABILITY,
    TYPE_CONCENTRATION_PRESSURE,
    TYPE_ROTATION_PRESSURE,
    TYPE_TRUST_LANE_PRESSURE,
)
from services.story_writer_v1 import (
    BANNED_TERMS,
    ROBOTIC_TERMS,
    SECTION_KEYS,
    write_story_frame,
)


def _ctx(*, team_id=118, team_name='Kansas City Royals', rotation=None,
         concentration=None, optionality=None, stability=None, injury=None):
    return {
        'team_id': team_id,
        'team': {'team_id': team_id, 'team_name': team_name, 'team_abbreviation': 'KC'},
        'reference_date': '2026-06-20',
        'data_through_date': '2026-06-20',
        'rotation_context': {
            'context_available': True, 'rotation_avg_ip_7d': 4.1, 'rotation_avg_ip_14d': 5.4,
            'rotation_ip_trend': -1.3, 'early_bullpen_entry_rate': 50.0, 'bullpen_coverage_ip_7d': 4.9,
            'rotation_games_analyzed_7d': 6, 'rotation_games_analyzed_14d': 12,
            'rotation_early_bullpen_entry_games_14d': 5,
            **(rotation or {}),
        },
        'bullpen_concentration_context': {
            'concentration_band': 'narrow', 'top_three_workload_share_10d': 94.0,
            'league_top_three_workload_share_10d': 58.0, 'top_three_share_delta_vs_league': 36.0,
            'bullpen_workload_total_10d': 240,
            'top_three_relievers_10d': [{'name': 'First Arm'}, {'name': 'Second Arm'}, {'name': 'Third Arm'}],
            'league_team_count_10d': 30,
            **(concentration or {}),
        },
        'bullpen_optionality_context': {
            'optionality_band': 'narrow', 'practical_close_game_paths_count': 3,
            'available_arms_count': 3, 'monitor_arms_count': 1, 'restricted_arms_count': 2,
            'limited_arms_count': 1, 'avoid_arms_count': 1, 'unavailable_arms_count': 0,
            'clean_workload_options': [{'name': 'Clean Arm'}], 'secondary_options': [{'name': 'Monitor Arm'}],
            **(optionality or {}),
        },
        'role_stability_context': {
            'stability_band': 'mostly_stable',
            'current_operational_core': ['First Arm', 'Second Arm', 'Third Arm'],
            'previous_operational_core': ['First Arm', 'Second Arm', 'Fourth Arm'],
            'core_retention_count': 2, 'core_stability_pct': 67, 'core_change_count': 1,
            'new_core_members': ['Third Arm'], 'departed_core_members': ['Fourth Arm'],
            'current_core_size': 3, 'previous_core_size': 3,
            **(stability or {}),
        },
        'injury_context': {
            'depth_pressure_band': 'light', 'active_bullpen_arms_count': 7,
            'inactive_bullpen_arms_count': 1, 'il_bullpen_arms_count': 1,
            'non_il_inactive_bullpen_arms_count': 0, 'inactive_bullpen_share': 12.5,
            'injury_context_confidence': 'high', 'inactive_bullpen_arms': [{'name': 'Inactive Arm'}],
            'role_uncertain_inactive_count': 0, 'unknown_roster_status_count': 0,
            **(injury or {}),
        },
        'limitations': [],
    }


def _trust_lane_optionality():
    return {
        'context_available': True, 'optionality_band': 'flexible',
        'practical_close_game_paths_count': 4, 'available_arms_count': 6,
        'monitor_arms_count': 1, 'restricted_arms_count': 0, 'limited_arms_count': 0,
        'avoid_arms_count': 0, 'unavailable_arms_count': 0,
        'clean_workload_options': [{'name': 'Clean 1'}],
        'secondary_options': [{'name': f'Flagged {i + 1}'} for i in range(5)],
    }


def _bridge_inputs():
    return dict(
        rotation={'rotation_avg_ip_7d': 5.4, 'rotation_avg_ip_14d': 5.5, 'rotation_ip_trend': -0.1,
                  'early_bullpen_entry_rate': 45.0, 'bullpen_coverage_ip_7d': 4.2},
        optionality={'context_available': True, 'optionality_band': 'narrow',
                     'practical_close_game_paths_count': 3, 'available_arms_count': 3,
                     'monitor_arms_count': 3, 'limited_arms_count': 1, 'restricted_arms_count': 1,
                     'avoid_arms_count': 0, 'unavailable_arms_count': 0,
                     'clean_workload_options': [{'name': 'Clean 1'}],
                     'secondary_options': [{'name': f'Mid {i + 1}'} for i in range(3)]},
        stability={'stability_band': 'stable',
                   'current_operational_core': ['Core One', 'Core Two', 'Core Three'],
                   'previous_operational_core': ['Core One', 'Core Two', 'Core Three'],
                   'core_retention_count': 3, 'core_stability_pct': 100, 'core_change_count': 0},
    )


def _written(context, observation_type):
    payload = construct_team_story_frames(context)
    frame = next(f for f in payload['story_frames'] if f['observation_type'] == observation_type)
    output = write_story_frame(frame)
    assert tuple(output['written_observation'].keys()) == SECTION_KEYS  # payload shape unchanged
    return output['written_observation']


def _nums(paragraph):
    # Decimal-aware: "4.1" is one number, not two.
    return re.findall(r'\d+\.?\d*', paragraph or '')


def _text(written):
    return ' '.join(v for v in written.values() if v)


# ── Metric stacking reduced ───────────────────────────────────────────────────

def test_concentration_beats_hold_one_number_each():
    written = _written(_ctx(), TYPE_CONCENTRATION_PRESSURE)
    # No beat stacks multiple percentages, and the share/league beats carry one each.
    for beat in ('observation_paragraph', 'baseline_paragraph', 'cause_paragraph'):
        assert written[beat].count('%') <= 1, (beat, written[beat])
    text = _text(written)
    # Key facts preserved: team share and league share both still read.
    assert '94%' in text
    assert '58%' in text
    # The secondary pitch-window count and the delta line are gone.
    assert 'pitch bullpen window' not in text
    assert 'percentage points' not in text


def test_rotation_observation_is_not_overstacked():
    written = _written(_ctx(), TYPE_ROTATION_PRESSURE)
    assert len(_nums(written['observation_paragraph'])) <= 2
    assert 'from the two-week mark' not in _text(written)
    text = _text(written)
    # Substance preserved: starter length and the bullpen-coverage cost still read.
    assert '4.1 innings' in text
    assert '4.9 bullpen innings per game' in text


def test_trust_lane_baseline_holds_one_comparison():
    written = _written(_ctx(optionality=_trust_lane_optionality()), TYPE_TRUST_LANE_PRESSURE)
    assert 'workload-flagged' not in _text(written)
    assert len(_nums(written['baseline_paragraph'])) <= 1
    # The board-vs-clean contrast that carries the point is still in the observation.
    assert '6 available arms' in _text(written)


def test_bridge_baseline_is_condensed():
    written = _written(_ctx(**_bridge_inputs()), TYPE_BRIDGE_INSTABILITY)
    text = _text(written)
    assert 'clean middle option' not in text
    assert 'clean middle options' not in text
    # The coverage-burden number that carries the point is preserved.
    assert 'innings a game on the way there' in text
    assert 'settled' in text.lower()


# ── Analyst phrasing reduced ──────────────────────────────────────────────────

def test_analyst_phrasing_is_gone_across_families():
    cases = [
        (_ctx(), TYPE_CONCENTRATION_PRESSURE),
        (_ctx(), TYPE_ROTATION_PRESSURE),
        (_ctx(optionality=_trust_lane_optionality()), TYPE_TRUST_LANE_PRESSURE),
        (_ctx(**_bridge_inputs()), TYPE_BRIDGE_INSTABILITY),
    ]
    for context, observation_type in cases:
        text = _text(_written(context, observation_type)).lower()
        assert 'percentage points' not in text
        assert 'route overlap' not in text
        assert 'workload-flagged' not in text


# ── Scanability: the point is in the first sentence ───────────────────────────

def test_observation_leads_with_the_point():
    for context, observation_type in (
        (_ctx(), TYPE_CONCENTRATION_PRESSURE),
        (_ctx(), TYPE_ROTATION_PRESSURE),
    ):
        observation = _written(context, observation_type)['observation_paragraph']
        first_sentence = observation.split('. ')[0]
        assert first_sentence
        assert len(first_sentence.split()) <= 16  # scannable opening


# ── Payload shape, structure, and governance preserved ────────────────────────

def test_shape_structure_and_governance_preserved():
    cases = [
        (_ctx(), TYPE_CONCENTRATION_PRESSURE),
        (_ctx(), TYPE_ROTATION_PRESSURE),
        (_ctx(optionality=_trust_lane_optionality()), TYPE_TRUST_LANE_PRESSURE),
        (_ctx(**_bridge_inputs()), TYPE_BRIDGE_INSTABILITY),
    ]
    for context, observation_type in cases:
        written = _written(context, observation_type)
        # Every beat still present and non-empty (no structure collapse).
        for beat in SECTION_KEYS:
            assert written[beat], (observation_type, beat)
        text = _text(written).lower()
        for term in (*BANNED_TERMS, *ROBOTIC_TERMS):
            assert term not in text, (observation_type, term)
