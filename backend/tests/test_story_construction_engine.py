from services.story_construction_engine import (
    CAPABILITY,
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    build_story_construction_engine_v1,
    construct_story_frame,
    construct_team_story_frames,
)
from services.story_observation_engine import (
    TYPE_CONCENTRATION_PRESSURE,
    TYPE_CORE_TRANSITION,
    TYPE_DEPTH_PRESSURE,
    TYPE_OPTIONALITY_STRENGTH,
    TYPE_ROTATION_PRESSURE,
    TYPE_STABLE_CORE,
    build_team_story_observation_payload,
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


def single_frame(context, observation_type):
    payload = construct_team_story_frames(context)
    return next(
        frame for frame in payload['story_frames']
        if frame['observation_type'] == observation_type
    )


def assert_frame_shape(frame, observation_type):
    assert set(frame) == {
        'team_id',
        'team_name',
        'team_abbreviation',
        'observation_type',
        'severity',
        'story_frame',
        'source_context',
        'construction_confidence',
        'limitations',
    }
    assert frame['observation_type'] == observation_type
    assert set(frame['story_frame']) == {
        'headline_facts',
        'observation_facts',
        'baseline_facts',
        'cause_facts',
        'interpretation_facts',
        'constraint_facts',
    }
    assert set(frame['source_context']) == {
        'rotation_context',
        'bullpen_concentration_context',
        'bullpen_optionality_context',
        'role_stability_context',
        'injury_context',
    }


def assert_no_prose_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            assert key not in {'text', 'story_text', 'sentence', 'prose', 'headline'}
            assert_no_prose_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            assert_no_prose_keys(nested)


def test_construction_frame_for_rotation_pressure():
    context = team_context(rotation={
        'rotation_avg_ip_7d': 4.1,
        'rotation_avg_ip_14d': 5.4,
        'rotation_ip_trend': -1.3,
        'early_bullpen_entry_rate': 50.0,
        'bullpen_coverage_ip_7d': 4.9,
    })

    frame = single_frame(context, TYPE_ROTATION_PRESSURE)

    assert_frame_shape(frame, TYPE_ROTATION_PRESSURE)
    assert frame['construction_confidence'] == CONFIDENCE_HIGH
    story_frame = frame['story_frame']
    assert story_frame['headline_facts']['rotation_avg_ip_7d'] == 4.1
    assert story_frame['baseline_facts']['rotation_avg_ip_14d'] == 5.4
    assert story_frame['cause_facts']['bullpen_coverage_ip_7d'] == 4.9
    assert story_frame['constraint_facts']['rotation_games_analyzed_14d'] == 12


def test_construction_frame_for_concentration_pressure():
    context = team_context(
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
    )

    frame = single_frame(context, TYPE_CONCENTRATION_PRESSURE)

    assert frame['construction_confidence'] == CONFIDENCE_HIGH
    story_frame = frame['story_frame']
    assert story_frame['headline_facts']['top_three_relievers'] == [
        'First Arm',
        'Second Arm',
        'Third Arm',
    ]
    assert story_frame['observation_facts']['bullpen_workload_total_10d'] == 240
    assert story_frame['baseline_facts']['league_top_three_workload_share_10d'] == 58.0
    assert story_frame['cause_facts']['rotation_ip_trend'] == -1.3
    assert story_frame['constraint_facts']['current_operational_core'] == [
        'First Arm',
        'Second Arm',
        'Third Arm',
    ]


def test_construction_frame_for_optionality_strength():
    context = team_context(optionality={
        'optionality_band': 'deep',
        'practical_close_game_paths_count': 6,
        'available_arms_count': 7,
        'clean_workload_options': [{'name': 'Clean One'}, {'name': 'Clean Two'}],
        'secondary_options': [{'name': 'Secondary One'}],
    })

    frame = single_frame(context, TYPE_OPTIONALITY_STRENGTH)

    assert frame['construction_confidence'] == CONFIDENCE_HIGH
    story_frame = frame['story_frame']
    assert story_frame['headline_facts']['practical_close_game_paths_count'] == 6
    assert story_frame['observation_facts']['clean_workload_options_count'] == 2
    assert story_frame['cause_facts']['secondary_options'] == [{'name': 'Secondary One'}]
    assert story_frame['interpretation_facts']['concentration_band'] == 'normal'


def test_construction_frame_for_stable_core():
    context = team_context(stability={
        'stability_band': 'stable',
        'current_operational_core': ['First Arm', 'Second Arm', 'Third Arm'],
        'previous_operational_core': ['First Arm', 'Second Arm', 'Third Arm'],
        'core_retention_count': 3,
        'core_stability_pct': 100,
        'core_change_count': 0,
    })

    frame = single_frame(context, TYPE_STABLE_CORE)

    assert frame['construction_confidence'] == CONFIDENCE_HIGH
    story_frame = frame['story_frame']
    assert story_frame['headline_facts']['current_operational_core'] == [
        'First Arm',
        'Second Arm',
        'Third Arm',
    ]
    assert story_frame['observation_facts']['core_stability_pct'] == 100
    assert story_frame['baseline_facts']['previous_operational_core'] == [
        'First Arm',
        'Second Arm',
        'Third Arm',
    ]
    assert story_frame['interpretation_facts']['concentration_band'] == 'normal'


def test_construction_frame_for_core_transition():
    context = team_context(stability={
        'stability_band': 'rebuilding',
        'current_operational_core': ['Fifth Arm', 'Sixth Arm', 'Seventh Arm'],
        'previous_operational_core': ['First Arm', 'Second Arm', 'Third Arm'],
        'new_core_members': ['Fifth Arm', 'Sixth Arm', 'Seventh Arm'],
        'departed_core_members': ['First Arm', 'Second Arm', 'Third Arm'],
        'core_retention_count': 0,
        'core_stability_pct': 0,
        'core_change_count': 3,
    })

    frame = single_frame(context, TYPE_CORE_TRANSITION)

    assert frame['construction_confidence'] == CONFIDENCE_HIGH
    story_frame = frame['story_frame']
    assert story_frame['headline_facts']['new_core_members'] == [
        'Fifth Arm',
        'Sixth Arm',
        'Seventh Arm',
    ]
    assert story_frame['baseline_facts']['previous_operational_core'] == [
        'First Arm',
        'Second Arm',
        'Third Arm',
    ]
    assert story_frame['cause_facts']['departed_core_members'] == [
        'First Arm',
        'Second Arm',
        'Third Arm',
    ]


def test_construction_frame_for_depth_pressure():
    context = team_context(injury={
        'depth_pressure_band': 'heavy',
        'active_bullpen_arms_count': 7,
        'inactive_bullpen_arms_count': 4,
        'il_bullpen_arms_count': 3,
        'non_il_inactive_bullpen_arms_count': 1,
        'inactive_bullpen_share': 36.4,
        'injury_context_confidence': 'high',
    })

    frame = single_frame(context, TYPE_DEPTH_PRESSURE)

    assert frame['construction_confidence'] == CONFIDENCE_HIGH
    story_frame = frame['story_frame']
    assert story_frame['headline_facts']['inactive_bullpen_arms_count'] == 4
    assert story_frame['baseline_facts']['active_bullpen_arms_count'] == 7
    assert story_frame['cause_facts']['il_bullpen_arms_count'] == 3
    assert story_frame['constraint_facts']['injury_context_confidence'] == 'high'


def test_medium_confidence_and_limitations_when_supporting_facts_are_missing():
    context = team_context(
        concentration={
            'concentration_band': 'concentrated',
            'top_three_workload_share_10d': 70.0,
            'league_top_three_workload_share_10d': None,
            'top_three_share_delta_vs_league': None,
        },
        rotation={
            'rotation_avg_ip_7d': None,
            'rotation_avg_ip_14d': None,
            'rotation_ip_trend': None,
        },
    )

    frame = single_frame(context, TYPE_CONCENTRATION_PRESSURE)

    assert frame['construction_confidence'] == CONFIDENCE_MEDIUM
    assert set(frame['limitations']) >= {
        'missing_league_baseline',
        'missing_top_three_share_delta_vs_league',
        'missing_rotation_context',
    }


def test_low_confidence_when_required_observation_facts_are_missing():
    context = team_context(concentration={
        'concentration_band': 'narrow',
        'top_three_relievers_10d': [],
        'top_three_workload_share_10d': None,
    })
    observation = {
        'type': TYPE_CONCENTRATION_PRESSURE,
        'severity': 'high',
        'team_id': 118,
        'team': 'Kansas City Royals',
    }

    frame = construct_story_frame(observation, context)

    assert frame['construction_confidence'] == CONFIDENCE_LOW
    assert set(frame['limitations']) >= {
        'missing_top_three_relievers',
        'missing_top_three_workload_share_10d',
    }


def test_low_injury_context_confidence_emits_limitation():
    context = team_context(injury={
        'depth_pressure_band': 'moderate',
        'inactive_bullpen_arms_count': 3,
        'il_bullpen_arms_count': 2,
        'injury_context_confidence': 'low',
    })

    frame = single_frame(context, TYPE_DEPTH_PRESSURE)

    assert frame['construction_confidence'] == CONFIDENCE_MEDIUM
    assert 'low_injury_context_confidence' in frame['limitations']


def test_source_context_is_preserved():
    context = team_context(concentration={'concentration_band': 'narrow'})

    frame = single_frame(context, TYPE_CONCENTRATION_PRESSURE)

    assert frame['source_context']['rotation_context'] == context['rotation_context']
    assert frame['source_context']['bullpen_concentration_context'] == (
        context['bullpen_concentration_context']
    )
    assert frame['source_context']['bullpen_optionality_context'] == (
        context['bullpen_optionality_context']
    )
    assert frame['source_context']['role_stability_context'] == context['role_stability_context']
    assert frame['source_context']['injury_context'] == context['injury_context']


def test_safe_output_with_partial_context():
    payload = construct_team_story_frames({
        'team_id': 500,
        'team': {'team_name': 'Partial Context Team', 'team_abbreviation': 'PCT'},
        'reference_date': None,
        'data_through_date': None,
    })

    assert payload['capability'] == CAPABILITY
    assert payload['frame_count'] == 0
    assert payload['story_frames'] == []
    assert payload['strongest_story_frame'] is None


def test_multiple_observations_for_same_team_and_engine_payload():
    context = team_context(
        rotation={
            'rotation_avg_ip_7d': 4.7,
            'rotation_avg_ip_14d': 5.3,
            'rotation_ip_trend': -0.6,
            'early_bullpen_entry_rate': 45.0,
        },
        concentration={
            'concentration_band': 'narrow',
            'top_three_workload_share_10d': 86.0,
        },
        optionality={
            'optionality_band': 'deep',
            'practical_close_game_paths_count': 6,
        },
    )

    payload = construct_team_story_frames(context)
    engine = build_story_construction_engine_v1(team_contexts=[context])

    assert payload['frame_count'] == 3
    assert {
        frame['observation_type'] for frame in payload['story_frames']
    } == {
        TYPE_ROTATION_PRESSURE,
        TYPE_CONCENTRATION_PRESSURE,
        TYPE_OPTIONALITY_STRENGTH,
    }
    assert payload['strongest_story_frame']['observation_type'] == TYPE_CONCENTRATION_PRESSURE
    assert engine['team_count'] == 1
    assert engine['teams'][0]['strongest_story_frame']['observation_type'] == (
        TYPE_CONCENTRATION_PRESSURE
    )
    assert engine['limitations'] == [
        'structured_story_frames_only',
        'no_prose_generation',
        'no_predictions_or_scoring_changes',
    ]


def test_construction_consumes_observation_payload_when_supplied():
    context = team_context(stability={'stability_band': 'stable'})
    observation_payload = build_team_story_observation_payload(context)

    payload = construct_team_story_frames(context, observation_payload=observation_payload)

    assert payload['frame_count'] == 1
    assert payload['story_frames'][0]['observation_type'] == TYPE_STABLE_CORE


def test_no_prose_sentence_generation():
    context = team_context(concentration={'concentration_band': 'narrow'})

    payload = construct_team_story_frames(context)

    assert_no_prose_keys(payload)
    for frame in payload['story_frames']:
        assert 'story_text' not in frame
        assert 'headline' not in frame['story_frame']
