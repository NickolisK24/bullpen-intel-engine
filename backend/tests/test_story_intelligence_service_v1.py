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
from services.story_four_beat_interpreter_v1 import (
    BEAT_COVERAGE_PRESSURE,
    BEAT_DEPTH_CONSTRAINT,
    BEAT_ROUTE_CHANGE,
    BEAT_SUSTAINABILITY_QUESTION,
    observation_public_beat_map,
)
from services.story_observation_engine import (
    TYPE_CONCENTRATION_PRESSURE,
    TYPE_CORE_TRANSITION,
    TYPE_DEPTH_PRESSURE,
    TYPE_OPTIONALITY_STRENGTH,
    TYPE_ROTATION_PRESSURE,
    TYPE_STABLE_CORE,
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


PUBLIC_BEATS = {
    BEAT_ROUTE_CHANGE,
    BEAT_COVERAGE_PRESSURE,
    BEAT_DEPTH_CONSTRAINT,
    BEAT_SUSTAINABILITY_QUESTION,
}


def assert_story_contract(result, observation_type, public_story_type=None):
    assert result['capability'] == CAPABILITY
    assert result['state'] == STATE_STORY_AVAILABLE
    assert result['story_available'] is True
    assert result['selected_observation']['type'] == observation_type
    assert result['construction_frame']['observation_type'] == observation_type
    assert result['story_type'] == (public_story_type or observation_public_beat_map()[observation_type])
    assert result['story_type'] in PUBLIC_BEATS
    assert result['story_type'] != observation_type
    assert result['public_story_beat']['internal_observation_type'] == observation_type
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
    for term in ['will win', 'expected to win', 'projected', 'probability', 'odds', 'lock', 'guaranteed']:
        assert term not in text


def assert_forward_clause(result):
    constraint = (result.get('written_story') or {}).get('constraint_paragraph') or ''
    assert constraint.startswith('If '), constraint


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
    assert result['story_type'] == BEAT_SUSTAINABILITY_QUESTION
    assert_forward_clause(result)
    assert_no_banned_language(result)


def test_depth_pressure_does_not_automatically_override_specific_active_story():
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

    assert_story_contract(result, TYPE_ROTATION_PRESSURE, BEAT_COVERAGE_PRESSURE)
    assert result['observation_count'] >= 3
    assert 'The starters are not covering as many innings as the recent baseline' in written_text(result)
    assert 'Shorter starts are pushing 4.8 bullpen innings per game into the relief group' in written_text(result)
    assert_forward_clause(result)


def test_coverage_pressure_wins_over_depth_and_route_when_short_starts_are_strongest():
    context = team_context(
        rotation={
            'rotation_avg_ip_7d': 2.4,
            'rotation_avg_ip_14d': 3.0,
            'rotation_ip_trend': -0.6,
            'early_bullpen_entry_rate': 82.0,
            'bullpen_coverage_ip_7d': 5.7,
        },
        stability={
            'stability_band': 'transitioning',
            'current_operational_core': ['Fifth Arm', 'Sixth Arm', 'Seventh Arm'],
            'previous_operational_core': ['First Arm', 'Second Arm', 'Third Arm'],
            'new_core_members': ['Fifth Arm', 'Sixth Arm'],
            'departed_core_members': ['First Arm', 'Second Arm'],
            'core_retention_count': 1,
            'core_stability_pct': 33,
            'core_change_count': 2,
        },
        injury={
            'depth_pressure_band': 'heavy',
            'active_bullpen_arms_count': 7,
            'inactive_bullpen_arms_count': 6,
            'il_bullpen_arms_count': 3,
            'non_il_inactive_bullpen_arms_count': 3,
        },
    )

    result = build_team_story(118, team_context=context)

    assert_story_contract(result, TYPE_ROTATION_PRESSURE, BEAT_COVERAGE_PRESSURE)
    assert result['selection_metadata']['selected_profile']['selection_strength'] >= 7
    assert 'The rotation has been handing the game to the bullpen earlier' in written_text(result)
    assert_forward_clause(result)


def test_sustainability_question_wins_when_usage_concentration_is_strongest():
    context = team_context(
        rotation={
            'rotation_avg_ip_7d': 5.8,
            'rotation_avg_ip_14d': 5.7,
            'rotation_ip_trend': 0.1,
            'early_bullpen_entry_rate': 10.0,
            'bullpen_coverage_ip_7d': 3.0,
        },
        concentration={
            'concentration_band': 'narrow',
            'top_three_workload_share_10d': 94.0,
            'top_three_share_delta_vs_league': 36.0,
        },
        optionality={
            'optionality_band': 'narrow',
            'practical_close_game_paths_count': 2,
            'available_arms_count': 3,
            'clean_workload_options': [{'name': 'Clean Arm'}],
        },
        injury={
            'depth_pressure_band': 'heavy',
            'active_bullpen_arms_count': 7,
            'inactive_bullpen_arms_count': 6,
            'il_bullpen_arms_count': 3,
            'non_il_inactive_bullpen_arms_count': 3,
        },
    )

    result = build_team_story(118, team_context=context)

    assert_story_contract(result, TYPE_CONCENTRATION_PRESSURE, BEAT_SUSTAINABILITY_QUESTION)
    assert result['selection_metadata']['selected_profile']['selection_strength'] >= 8
    assert 'First Arm, Second Arm, and Third Arm' in written_text(result)
    assert_forward_clause(result)


def test_severe_depth_pressure_can_still_win_over_weaker_active_story():
    context = team_context(
        rotation={
            'rotation_avg_ip_7d': 4.9,
            'rotation_avg_ip_14d': 5.5,
            'rotation_ip_trend': -0.6,
            'early_bullpen_entry_rate': 45.0,
        },
        concentration={
            'concentration_band': 'concentrated',
            'top_three_workload_share_10d': 72.0,
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

    assert_story_contract(result, TYPE_DEPTH_PRESSURE, BEAT_DEPTH_CONSTRAINT)
    assert '4 bullpen arms outside the active route' in written_text(result)
    assert_forward_clause(result)


def test_context_specific_tiebreak_prefers_core_transition_over_depth_pressure():
    context = team_context(
        stability={
            'stability_band': 'rebuilding',
            'current_operational_core': ['Fifth Arm', 'Sixth Arm', 'Seventh Arm'],
            'previous_operational_core': ['First Arm', 'Second Arm', 'Third Arm'],
            'new_core_members': ['Fifth Arm', 'Sixth Arm', 'Seventh Arm'],
            'departed_core_members': ['First Arm', 'Second Arm', 'Third Arm'],
            'core_retention_count': 0,
            'core_stability_pct': 0,
            'core_change_count': 3,
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

    assert_story_contract(result, TYPE_CORE_TRANSITION, BEAT_ROUTE_CHANGE)
    assert 'The route has changed, now running through Fifth Arm, Sixth Arm, and Seventh Arm.' in written_text(result)
    assert_forward_clause(result)


def test_route_change_can_explain_roster_change_with_held_route():
    context = team_context(
        stability={
            'stability_band': 'transitioning',
            'current_operational_core': ['First Arm', 'Second Arm', 'Third Arm'],
            'previous_operational_core': ['First Arm', 'Second Arm', 'Fourth Arm'],
            'new_core_members': ['Third Arm'],
            'departed_core_members': ['Fourth Arm'],
            'core_retention_count': 2,
            'core_stability_pct': 67,
            'core_change_count': 1,
        },
        injury={
            'depth_pressure_band': 'light',
            'active_bullpen_arms_count': 7,
            'inactive_bullpen_arms_count': 1,
            'il_bullpen_arms_count': 1,
            'non_il_inactive_bullpen_arms_count': 0,
        },
    )

    result = build_team_story(118, team_context=context)

    assert_story_contract(result, TYPE_CORE_TRANSITION, BEAT_ROUTE_CHANGE)
    assert 'The roster changed while the route still runs through First Arm, Second Arm, and Third Arm.' in written_text(result)
    assert_forward_clause(result)


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
    assert result['story_type'] is None
    assert result['public_story_beat'] is None
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

    assert_story_contract(result, TYPE_CONCENTRATION_PRESSURE, BEAT_SUSTAINABILITY_QUESTION)
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
    assert_story_contract(result, TYPE_ROTATION_PRESSURE, BEAT_COVERAGE_PRESSURE)
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
    assert result['teams'][0]['story_type'] == BEAT_SUSTAINABILITY_QUESTION


def test_every_internal_observation_maps_to_one_public_beat():
    mapping = observation_public_beat_map()

    assert set(mapping) == {
        TYPE_ROTATION_PRESSURE,
        TYPE_CONCENTRATION_PRESSURE,
        TYPE_OPTIONALITY_STRENGTH,
        TYPE_STABLE_CORE,
        TYPE_CORE_TRANSITION,
        TYPE_DEPTH_PRESSURE,
    }
    assert set(mapping.values()) <= PUBLIC_BEATS
    assert mapping[TYPE_CORE_TRANSITION] == BEAT_ROUTE_CHANGE
    assert mapping[TYPE_STABLE_CORE] == BEAT_ROUTE_CHANGE
    assert mapping[TYPE_ROTATION_PRESSURE] == BEAT_COVERAGE_PRESSURE
    assert mapping[TYPE_DEPTH_PRESSURE] == BEAT_DEPTH_CONSTRAINT
    assert mapping[TYPE_CONCENTRATION_PRESSURE] == BEAT_SUSTAINABILITY_QUESTION
    assert mapping[TYPE_OPTIONALITY_STRENGTH] == BEAT_SUSTAINABILITY_QUESTION


def test_short_start_cause_maps_to_coverage_pressure():
    result = build_team_story(118, team_context=team_context(
        concentration={
            'concentration_band': 'narrow',
            'top_three_workload_share_10d': 88.0,
        },
        rotation={
            'rotation_avg_ip_7d': 4.4,
            'rotation_avg_ip_14d': 5.8,
            'rotation_ip_trend': -1.4,
            'early_bullpen_entry_rate': 50.0,
            'bullpen_coverage_ip_7d': 4.8,
        },
    ))

    assert_story_contract(result, TYPE_ROTATION_PRESSURE, BEAT_COVERAGE_PRESSURE)
    assert 'The starters are not covering as many innings as the recent baseline' in written_text(result)
    assert_forward_clause(result)


def test_public_story_type_never_exposes_internal_observation_snake_case():
    internal_types = {
        TYPE_ROTATION_PRESSURE,
        TYPE_CONCENTRATION_PRESSURE,
        TYPE_OPTIONALITY_STRENGTH,
        TYPE_STABLE_CORE,
        TYPE_CORE_TRANSITION,
        TYPE_DEPTH_PRESSURE,
    }
    result = build_team_story(118, team_context=team_context(
        concentration={'concentration_band': 'narrow', 'top_three_workload_share_10d': 91.0},
    ))

    assert result['story_type'] in PUBLIC_BEATS
    assert result['story_type'] not in internal_types
    assert result['selected_observation']['type'] in internal_types
    assert result['public_story_beat']['internal_observation_type'] == result['selected_observation']['type']


def test_story_names_arms_and_keeps_baseline_when_evidence_exists():
    result = build_team_story(118, team_context=team_context(
        concentration={'concentration_band': 'narrow', 'top_three_workload_share_10d': 91.0},
    ))
    text = written_text(result)

    assert 'First Arm, Second Arm, and Third Arm' in text
    assert result['written_story']['baseline_paragraph']
    assert 'league comparison' in result['written_story']['baseline_paragraph']
    assert_forward_clause(result)
    assert_no_banned_language(result)


def test_depth_constraint_names_inactive_arms_when_present():
    result = build_team_story(118, team_context=team_context(
        injury={
            'depth_pressure_band': 'heavy',
            'inactive_bullpen_arms_count': 4,
            'il_bullpen_arms_count': 3,
            'non_il_inactive_bullpen_arms_count': 1,
            'inactive_bullpen_arms': [{'name': 'Inactive Arm'}, {'name': 'Depth Arm'}],
        },
        rotation={'rotation_ip_trend': 0.0, 'early_bullpen_entry_rate': 10.0},
        concentration={'concentration_band': 'normal'},
    ))

    assert_story_contract(result, TYPE_DEPTH_PRESSURE, BEAT_DEPTH_CONSTRAINT)
    assert 'Inactive Arm' in written_text(result)
    assert "{'name':" not in written_text(result)
    assert_forward_clause(result)
