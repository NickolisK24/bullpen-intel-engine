from services.story_construction_engine import construct_story_frame, construct_team_story_frames
from services.story_observation_engine import (
    TYPE_CONCENTRATION_PRESSURE,
    TYPE_CORE_TRANSITION,
    TYPE_DEPTH_PRESSURE,
    TYPE_OPTIONALITY_STRENGTH,
    TYPE_ROTATION_PRESSURE,
    TYPE_STABLE_CORE,
)
from services.story_writer_v1 import (
    BANNED_TERMS,
    CAPABILITY,
    SECTION_KEYS,
    build_story_writer_v1,
    write_story_frame,
    write_team_story_frames,
)


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
        'limitations': [],
    }


def frame_for(context, observation_type):
    payload = construct_team_story_frames(context)
    return next(
        frame for frame in payload['story_frames']
        if frame['observation_type'] == observation_type
    )


def written_text(output):
    return ' '.join(
        value for value in output['written_observation'].values()
        if value
    )


def assert_writer_shape(output, observation_type):
    assert output['capability'] == CAPABILITY
    assert output['observation_type'] == observation_type
    assert tuple(output['written_observation'].keys()) == SECTION_KEYS
    assert output['source_frame']['observation_type'] == observation_type
    assert output['validation']['passed'] is True


def assert_no_banned_language(output):
    text = written_text(output).lower()
    for term in BANNED_TERMS:
        assert term not in text


def test_writer_outputs_rotation_pressure_observation():
    frame = frame_for(team_context(rotation={
        'rotation_avg_ip_7d': 4.1,
        'rotation_avg_ip_14d': 5.4,
        'rotation_ip_trend': -1.3,
        'early_bullpen_entry_rate': 50.0,
        'bullpen_coverage_ip_7d': 4.9,
    }), TYPE_ROTATION_PRESSURE)

    output = write_story_frame(frame)

    assert_writer_shape(output, TYPE_ROTATION_PRESSURE)
    text = written_text(output)
    assert 'Kansas City Royals' in text
    assert '4.1 innings' in text
    assert '5.4 starter innings' in text
    assert '4.9 innings per game' in text
    assert output['written_observation']['constraint_paragraph'].startswith('If similar game conditions occur')


def test_writer_outputs_concentration_pressure_observation():
    frame = frame_for(team_context(
        concentration={
            'concentration_band': 'narrow',
            'top_three_workload_share_10d': 94.0,
            'top_three_share_delta_vs_league': 36.0,
            'bullpen_workload_total_10d': 240,
        },
        rotation={
            'rotation_avg_ip_7d': 4.6,
            'rotation_avg_ip_14d': 5.9,
            'rotation_ip_trend': -1.3,
            'early_bullpen_entry_rate': 42.0,
        },
    ), TYPE_CONCENTRATION_PRESSURE)

    output = write_story_frame(frame)

    assert_writer_shape(output, TYPE_CONCENTRATION_PRESSURE)
    text = written_text(output)
    assert 'First Arm, Second Arm, and Third Arm' in text
    assert '94%' in text
    assert '58%' in text
    assert '36 percentage points' in text
    assert 'current operational core' not in text.lower()


def test_writer_outputs_optionality_strength_observation():
    frame = frame_for(team_context(optionality={
        'optionality_band': 'deep',
        'practical_close_game_paths_count': 6,
        'available_arms_count': 7,
        'clean_workload_options': [{'name': 'Clean One'}, {'name': 'Clean Two'}],
        'secondary_options': [{'name': 'Secondary One'}],
    }), TYPE_OPTIONALITY_STRENGTH)

    output = write_story_frame(frame)

    assert_writer_shape(output, TYPE_OPTIONALITY_STRENGTH)
    text = written_text(output)
    assert 'multiple usable routes' in text
    assert '6 practical close-game paths' in text
    assert '7 available arms' in text
    assert '2 clean workload options' in text


def test_writer_outputs_stable_core_observation():
    frame = frame_for(team_context(stability={
        'stability_band': 'stable',
        'current_operational_core': ['First Arm', 'Second Arm', 'Third Arm'],
        'previous_operational_core': ['First Arm', 'Second Arm', 'Third Arm'],
        'core_retention_count': 3,
        'core_stability_pct': 100,
        'core_change_count': 0,
    }), TYPE_STABLE_CORE)

    output = write_story_frame(frame)

    assert_writer_shape(output, TYPE_STABLE_CORE)
    text = written_text(output)
    assert 'held together' in text
    assert 'First Arm, Second Arm, and Third Arm' in text
    assert '100%' in text
    assert '3-arm core' in text


def test_writer_outputs_core_transition_observation():
    frame = frame_for(team_context(stability={
        'stability_band': 'rebuilding',
        'current_operational_core': ['Fifth Arm', 'Sixth Arm', 'Seventh Arm'],
        'previous_operational_core': ['First Arm', 'Second Arm', 'Third Arm'],
        'new_core_members': ['Fifth Arm', 'Sixth Arm', 'Seventh Arm'],
        'departed_core_members': ['First Arm', 'Second Arm', 'Third Arm'],
        'core_retention_count': 0,
        'core_stability_pct': 0,
        'core_change_count': 3,
    }), TYPE_CORE_TRANSITION)

    output = write_story_frame(frame)

    assert_writer_shape(output, TYPE_CORE_TRANSITION)
    text = written_text(output)
    assert 'core is changing' in text
    assert '3 core changes' in text
    assert 'Fifth Arm, Sixth Arm, and Seventh Arm' in text
    assert '0 retained members' in text


def test_writer_outputs_depth_pressure_observation():
    frame = frame_for(team_context(injury={
        'depth_pressure_band': 'heavy',
        'active_bullpen_arms_count': 7,
        'inactive_bullpen_arms_count': 4,
        'il_bullpen_arms_count': 3,
        'non_il_inactive_bullpen_arms_count': 1,
        'inactive_bullpen_share': 36.4,
        'injury_context_confidence': 'high',
    }), TYPE_DEPTH_PRESSURE)

    output = write_story_frame(frame)

    assert_writer_shape(output, TYPE_DEPTH_PRESSURE)
    text = written_text(output)
    assert 'depth is under pressure' in text
    assert '4 inactive bullpen arms' in text
    assert '3 IL arms' in text
    assert '1 non-IL inactive arm' in text


def test_writer_is_deterministic_for_same_frame():
    frame = frame_for(team_context(concentration={'concentration_band': 'narrow'}), TYPE_CONCENTRATION_PRESSURE)

    first = write_story_frame(frame)
    second = write_story_frame(frame)

    assert first == second


def test_writer_does_not_invent_unavailable_facts():
    context = team_context(concentration={
        'concentration_band': 'narrow',
        'top_three_relievers_10d': [
            {'name': 'Only Arm', 'pitches': 50, 'workload_share': 50.0},
        ],
        'top_three_workload_share_10d': 50.0,
        'league_top_three_workload_share_10d': None,
        'top_three_share_delta_vs_league': None,
    })
    frame = frame_for(context, TYPE_CONCENTRATION_PRESSURE)

    output = write_story_frame(frame)
    text = written_text(output)

    assert 'Only Arm' in text
    assert '58%' not in text
    assert '36 percentage points' not in text
    assert output['written_observation']['baseline_paragraph'] is None


def test_writer_banned_language_does_not_appear_in_written_text():
    frame = frame_for(team_context(
        rotation={
            'rotation_avg_ip_7d': 4.1,
            'rotation_avg_ip_14d': 5.4,
            'rotation_ip_trend': -1.3,
        },
        concentration={'concentration_band': 'narrow'},
    ), TYPE_CONCENTRATION_PRESSURE)

    output = write_story_frame(frame)

    assert_no_banned_language(output)
    assert output['validation']['contains_banned_language'] is False


def test_missing_optional_frame_fields_degrade_gracefully():
    frame = construct_story_frame(
        {
            'type': TYPE_OPTIONALITY_STRENGTH,
            'severity': 'medium',
            'team_id': 118,
            'team': 'Kansas City Royals',
        },
        team_context(
            concentration={
                'concentration_band': None,
                'top_three_workload_share_10d': None,
            },
            optionality={
                'optionality_band': 'deep',
                'practical_close_game_paths_count': 6,
                'available_arms_count': None,
                'clean_workload_options': [],
                'secondary_options': [],
            },
        ),
    )

    output = write_story_frame(frame)

    assert_writer_shape(output, TYPE_OPTIONALITY_STRENGTH)
    assert output['written_observation']['baseline_paragraph'] is None
    assert output['written_observation']['cause_paragraph'] is None
    assert '6 practical close-game paths' in written_text(output)


def test_team_and_engine_writer_payloads():
    context = team_context(
        concentration={'concentration_band': 'narrow'},
        optionality={'optionality_band': 'deep', 'practical_close_game_paths_count': 6},
    )
    construction_payload = construct_team_story_frames(context)

    team_output = write_team_story_frames(construction_payload)
    engine_output = build_story_writer_v1(construction_payloads=[construction_payload])

    assert team_output['written_count'] == 2
    assert team_output['strongest_written_observation']['observation_type'] == TYPE_CONCENTRATION_PRESSURE
    assert engine_output['capability'] == CAPABILITY
    assert engine_output['team_count'] == 1
    assert engine_output['teams'][0]['written_count'] == 2
    assert all('prediction' not in item for item in engine_output['limitations'])
    assert all('ranking' not in item for item in engine_output['limitations'])
    assert all('scoring' not in item for item in engine_output['limitations'])
