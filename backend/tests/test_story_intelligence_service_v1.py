from copy import deepcopy
from datetime import date

from services.story_intelligence_service_v1 import (
    CAPABILITY,
    NEUTRAL_NO_OBSERVATIONS,
    NEUTRAL_NO_VALID_FRAME,
    STATE_NEUTRAL,
    STATE_STORY_AVAILABLE,
    build_story_intelligence_service_v1,
    build_team_story,
)
from services.story_observation_engine import (
    TYPE_CONCENTRATION_PRESSURE,
    TYPE_DEPTH_PRESSURE,
    TYPE_ROTATION_PRESSURE,
)
from services.story_writer_v1 import BANNED_TERMS, SECTION_KEYS


def team_context(
    *,
    team_id=118,
    team_name='Kansas City Royals',
    team_abbreviation='KC',
    rotation=None,
    concentration=None,
    optionality=None,
    stability=None,
    injury=None,
    limitations=None,
):
    return {
        'team_id': team_id,
        'team': {
            'team_id': team_id,
            'team_name': team_name,
            'team_abbreviation': team_abbreviation,
        },
        'reference_date': '2026-06-20',
        'data_through_date': '2026-06-20',
        'rotation_context': {
            'context_available': True,
            'rotation_avg_ip_7d': 5.7,
            'rotation_avg_ip_14d': 5.8,
            'rotation_ip_trend': -0.1,
            'early_bullpen_entry_rate': 10.0,
            'bullpen_coverage_ip_7d': 3.3,
            'rotation_games_analyzed_7d': 6,
            'rotation_games_analyzed_14d': 12,
            'rotation_early_bullpen_entry_games_14d': 1,
            **(rotation or {}),
        },
        'bullpen_concentration_context': {
            'concentration_band': 'normal',
            'top_three_workload_share_10d': 61.0,
            'league_top_three_workload_share_10d': 58.0,
            'top_three_share_delta_vs_league': 3.0,
            'bullpen_workload_total_10d': 180,
            'top_three_relievers_10d': [
                {'name': 'First Arm', 'pitches': 50, 'workload_share': 27.8},
                {'name': 'Second Arm', 'pitches': 35, 'workload_share': 19.4},
                {'name': 'Third Arm', 'pitches': 25, 'workload_share': 13.9},
            ],
            'league_team_count_10d': 30,
            **(concentration or {}),
        },
        'bullpen_optionality_context': {
            'optionality_band': 'narrow',
            'practical_close_game_paths_count': 3,
            'available_arms_count': 3,
            'monitor_arms_count': 1,
            'restricted_arms_count': 2,
            'limited_arms_count': 1,
            'avoid_arms_count': 1,
            'unavailable_arms_count': 0,
            'clean_workload_options': [{'name': 'Clean Arm'}],
            'secondary_options': [{'name': 'Monitor Arm'}],
            **(optionality or {}),
        },
        'role_stability_context': {
            'stability_band': 'mostly_stable',
            'current_operational_core': ['First Arm', 'Second Arm', 'Third Arm'],
            'previous_operational_core': ['First Arm', 'Second Arm', 'Fourth Arm'],
            'core_retention_count': 2,
            'core_stability_pct': 67,
            'core_change_count': 1,
            'new_core_members': ['Third Arm'],
            'departed_core_members': ['Fourth Arm'],
            'current_core_size': 3,
            'previous_core_size': 3,
            **(stability or {}),
        },
        'injury_context': {
            'depth_pressure_band': 'light',
            'active_bullpen_arms_count': 7,
            'inactive_bullpen_arms_count': 1,
            'il_bullpen_arms_count': 1,
            'non_il_inactive_bullpen_arms_count': 0,
            'inactive_bullpen_share': 12.5,
            'injury_context_confidence': 'high',
            'inactive_bullpen_arms': [{'name': 'Inactive Arm'}],
            'role_uncertain_inactive_count': 0,
            'unknown_roster_status_count': 0,
            **(injury or {}),
        },
        'limitations': list(limitations or []),
    }


def written_text(result):
    return ' '.join(
        value for value in (result.get('written_story') or {}).values()
        if value
    )


def assert_story_contract(result, observation_type):
    assert result['capability'] == CAPABILITY
    assert result['state'] == STATE_STORY_AVAILABLE
    assert result['story_available'] is True
    assert result['selected_observation']['type'] == observation_type
    assert result['construction_frame']['observation_type'] == observation_type
    assert tuple(result['written_story'].keys()) == SECTION_KEYS
    assert result['writer_output']['validation']['passed'] is True
    assert set(result['supporting_context']) == {
        'rotation_context',
        'bullpen_concentration_context',
        'bullpen_optionality_context',
        'role_stability_context',
        'injury_context',
    }


def assert_no_banned_language(result):
    text = written_text(result).lower()
    for term in BANNED_TERMS:
        assert term not in text


def test_build_team_story_runs_full_pipeline_from_context_fetch(monkeypatch):
    context = team_context(concentration={
        'concentration_band': 'narrow',
        'top_three_workload_share_10d': 94.0,
        'top_three_share_delta_vs_league': 36.0,
    })
    calls = []

    def fake_context(team_id, reference_date=None):
        calls.append((team_id, reference_date))
        return context

    monkeypatch.setattr(
        'services.story_intelligence_service_v1.build_team_bullpen_context',
        fake_context,
    )

    result = build_team_story(118, date(2026, 6, 20))

    assert calls == [(118, date(2026, 6, 20))]
    assert_story_contract(result, TYPE_CONCENTRATION_PRESSURE)
    assert result['team_name'] == 'Kansas City Royals'
    assert result['freshness']['data_through'] == '2026-06-20'
    assert '94%' in written_text(result)
    assert_no_banned_language(result)


def test_service_selection_uses_deterministic_product_order():
    context = team_context(
        rotation={
            'rotation_avg_ip_7d': 4.4,
            'rotation_avg_ip_14d': 5.8,
            'rotation_ip_trend': -1.4,
            'early_bullpen_entry_rate': 50.0,
            'bullpen_coverage_ip_7d': 4.8,
        },
        concentration={
            'concentration_band': 'narrow',
            'top_three_workload_share_10d': 88.0,
        },
        optionality={
            'optionality_band': 'deep',
            'practical_close_game_paths_count': 6,
        },
        injury={
            'depth_pressure_band': 'heavy',
            'active_bullpen_arms_count': 7,
            'inactive_bullpen_arms_count': 4,
            'il_bullpen_arms_count': 3,
            'non_il_inactive_bullpen_arms_count': 1,
        },
    )

    result = build_team_story(118, team_context=context)

    assert_story_contract(result, TYPE_DEPTH_PRESSURE)
    assert result['observation_count'] >= 3
    assert '4 inactive bullpen arms' in written_text(result)


def test_neutral_state_when_no_observations_exist():
    result = build_team_story(118, team_context=team_context())

    assert result['capability'] == CAPABILITY
    assert result['state'] == STATE_NEUTRAL
    assert result['story_available'] is False
    assert result['neutral_reason'] == NEUTRAL_NO_OBSERVATIONS
    assert result['selected_observation'] is None
    assert result['construction_frame'] is None
    assert result['written_story'] is None
    assert result['writer_output'] is None
    assert NEUTRAL_NO_OBSERVATIONS in result['limitations']


def test_incomplete_context_keeps_valid_story_with_limitations():
    context = team_context(
        concentration={
            'concentration_band': 'narrow',
            'top_three_workload_share_10d': 72.0,
            'league_top_three_workload_share_10d': None,
            'top_three_share_delta_vs_league': None,
        },
        rotation={
            'rotation_avg_ip_7d': None,
            'rotation_avg_ip_14d': None,
            'rotation_ip_trend': None,
        },
    )

    result = build_team_story(118, team_context=context)

    assert_story_contract(result, TYPE_CONCENTRATION_PRESSURE)
    assert result['construction_frame']['construction_confidence'] == 'medium'
    assert set(result['limitations']) >= {
        'missing_league_baseline',
        'missing_top_three_share_delta_vs_league',
        'missing_rotation_context',
    }
    assert result['written_story']['baseline_paragraph'] is None


def test_low_confidence_frame_returns_neutral_instead_of_forcing_story():
    context = team_context(concentration={
        'concentration_band': 'narrow',
        'top_three_relievers_10d': [],
        'top_three_workload_share_10d': None,
    })

    result = build_team_story(118, team_context=context)

    assert result['state'] == STATE_NEUTRAL
    assert result['story_available'] is False
    assert result['neutral_reason'] == NEUTRAL_NO_VALID_FRAME
    assert result['written_story'] is None
    assert NEUTRAL_NO_VALID_FRAME in result['limitations']


def test_service_does_not_mutate_context_or_state_change_flags():
    context = team_context(rotation={
        'rotation_avg_ip_7d': 4.1,
        'rotation_avg_ip_14d': 5.4,
        'rotation_ip_trend': -1.3,
        'early_bullpen_entry_rate': 50.0,
        'bullpen_coverage_ip_7d': 4.9,
    })
    original = deepcopy(context)

    result = build_team_story(118, team_context=context)

    assert context == original
    assert_story_contract(result, TYPE_ROTATION_PRESSURE)
    assert result['trust_metadata']['external_generation_used'] is False
    assert result['trust_metadata']['new_metrics_created'] is False
    assert result['trust_metadata']['context_formula_changes'] is False
    assert result['trust_metadata']['availability_changes'] is False
    assert result['trust_metadata']['fatigue_changes'] is False


def test_engine_payload_wraps_multiple_team_story_contracts():
    first = team_context(
        team_id=1,
        team_name='Team One',
        concentration={'concentration_band': 'narrow'},
    )
    second = team_context(
        team_id=2,
        team_name='Team Two',
    )

    result = build_story_intelligence_service_v1(team_contexts=[first, second])

    assert result['capability'] == CAPABILITY
    assert result['team_count'] == 2
    assert result['teams'][0]['state'] == STATE_STORY_AVAILABLE
    assert result['teams'][1]['state'] == STATE_NEUTRAL
    assert result['teams'][0]['selected_observation']['type'] == TYPE_CONCENTRATION_PRESSURE
