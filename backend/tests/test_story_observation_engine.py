from services.story_observation_engine import (
    CAPABILITY,
    TYPE_CONCENTRATION_PRESSURE,
    TYPE_CORE_TRANSITION,
    TYPE_DEPTH_PRESSURE,
    TYPE_OPTIONALITY_STRENGTH,
    TYPE_ROTATION_PRESSURE,
    TYPE_STABLE_CORE,
    TYPE_TRUST_LANE_PRESSURE,
    build_story_observation_engine_v1,
    build_team_story_observation_payload,
    select_strongest_observation,
    select_top_observations,
)


def _trust_lane_optionality(*, clean=2, secondary=4, available=6, band='flexible', context_available=True):
    """A bullpen with an acceptable available board but a thin trusted/clean lane."""
    return {
        'context_available': context_available,
        'optionality_band': band,
        'practical_close_game_paths_count': max(available - 2, 0),
        'available_arms_count': available,
        'monitor_arms_count': 1,
        'restricted_arms_count': 0,
        'limited_arms_count': 0,
        'avoid_arms_count': 0,
        'unavailable_arms_count': 0,
        'clean_workload_options': [{'name': f'Clean {i + 1}'} for i in range(clean)],
        'secondary_options': [{'name': f'Flagged {i + 1}'} for i in range(secondary)],
    }


def _types(payload):
    return {item['type'] for item in payload['observations']}


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
        'limitations': ['Context is descriptive.'],
    }


def observation(payload, observation_type):
    return next(
        item for item in payload['observations']
        if item['type'] == observation_type
    )


def assert_structured_observation(item):
    assert set(item) == {
        'team_id',
        'team',
        'team_abbreviation',
        'type',
        'severity',
        'source_layers',
        'headline_inputs',
        'baseline_inputs',
        'cause_inputs',
        'constraint_inputs',
    }
    assert isinstance(item['headline_inputs'], dict)
    assert isinstance(item['baseline_inputs'], dict)
    assert isinstance(item['cause_inputs'], dict)
    assert isinstance(item['constraint_inputs'], dict)
    assert 'text' not in item
    assert 'story' not in item


def test_rotation_pressure_observation():
    payload = build_team_story_observation_payload(team_context(
        rotation={
            'rotation_avg_ip_7d': 4.4,
            'rotation_avg_ip_14d': 5.8,
            'rotation_ip_trend': -1.4,
            'early_bullpen_entry_rate': 33.0,
        },
    ))

    item = observation(payload, TYPE_ROTATION_PRESSURE)

    assert payload['capability'] == CAPABILITY
    assert item['severity'] == 'high'
    assert item['headline_inputs']['rotation_avg_ip_7d'] == 4.4
    assert item['headline_inputs']['rotation_avg_ip_14d'] == 5.8
    assert item['baseline_inputs']['rotation_trend_pressure_threshold'] == -0.5
    assert_structured_observation(item)


def test_concentration_pressure_observation():
    payload = build_team_story_observation_payload(team_context(
        concentration={
            'concentration_band': 'narrow',
            'top_three_workload_share_10d': 88.0,
            'top_three_share_delta_vs_league': 27.0,
        },
    ))

    item = observation(payload, TYPE_CONCENTRATION_PRESSURE)

    assert item['severity'] == 'high'
    assert item['headline_inputs']['top_three_workload_share_10d'] == 88.0
    assert item['baseline_inputs']['league_top_three_workload_share_10d'] == 58.0
    assert item['constraint_inputs']['current_operational_core'] == [
        'First Arm',
        'Second Arm',
        'Third Arm',
    ]
    assert_structured_observation(item)


def test_optionality_strength_observation():
    payload = build_team_story_observation_payload(team_context(
        optionality={
            'optionality_band': 'deep',
            'practical_close_game_paths_count': 6,
            'available_arms_count': 6,
            'clean_workload_options': [{'name': 'Clean One'}, {'name': 'Clean Two'}],
            'secondary_options': [],
        },
    ))

    item = observation(payload, TYPE_OPTIONALITY_STRENGTH)

    assert item['severity'] == 'high'
    assert item['headline_inputs']['optionality_band'] == 'deep'
    assert item['cause_inputs']['clean_workload_option_count'] == 2
    assert item['constraint_inputs']['unavailable_arms_count'] == 0
    assert_structured_observation(item)


def test_trust_lane_pressure_fires_when_clean_trusted_options_are_low():
    payload = build_team_story_observation_payload(team_context(
        optionality=_trust_lane_optionality(clean=2, secondary=4, available=6),
    ))

    item = observation(payload, TYPE_TRUST_LANE_PRESSURE)

    assert item['severity'] == 'medium'
    assert item['headline_inputs']['available_arms_count'] == 6
    assert item['headline_inputs']['clean_workload_options_count'] == 2
    assert item['headline_inputs']['secondary_options_count'] == 4
    assert_structured_observation(item)


def test_trust_lane_pressure_publishes_even_when_available_arms_look_acceptable():
    # Six available bodies reads as an acceptable board, yet only one is clean.
    payload = build_team_story_observation_payload(team_context(
        optionality=_trust_lane_optionality(clean=1, secondary=5, available=6),
    ))

    item = observation(payload, TYPE_TRUST_LANE_PRESSURE)
    assert item['severity'] == 'high'
    assert item['headline_inputs']['available_arms_count'] >= 4


def test_trust_lane_pressure_does_not_fire_when_trusted_depth_is_healthy():
    payload = build_team_story_observation_payload(team_context(
        optionality=_trust_lane_optionality(clean=4, secondary=4, available=8, band='deep'),
    ))

    assert TYPE_TRUST_LANE_PRESSURE not in _types(payload)


def test_trust_lane_pressure_does_not_fire_without_a_flagged_population():
    # Few flagged arms means the available count is not masking a thin lane.
    payload = build_team_story_observation_payload(team_context(
        optionality=_trust_lane_optionality(clean=2, secondary=1, available=4),
    ))

    assert TYPE_TRUST_LANE_PRESSURE not in _types(payload)


def test_trust_lane_pressure_requires_available_context():
    payload = build_team_story_observation_payload(team_context(
        optionality=_trust_lane_optionality(clean=1, secondary=5, available=6, context_available=False),
    ))

    assert TYPE_TRUST_LANE_PRESSURE not in _types(payload)


def test_stable_core_observation():
    payload = build_team_story_observation_payload(team_context(
        stability={
            'stability_band': 'stable',
            'core_retention_count': 3,
            'core_stability_pct': 100,
            'core_change_count': 0,
            'previous_operational_core': ['First Arm', 'Second Arm', 'Third Arm'],
            'new_core_members': [],
            'departed_core_members': [],
        },
    ))

    item = observation(payload, TYPE_STABLE_CORE)

    assert item['severity'] == 'medium'
    assert item['headline_inputs']['core_stability_pct'] == 100
    assert item['baseline_inputs']['previous_operational_core'] == [
        'First Arm',
        'Second Arm',
        'Third Arm',
    ]
    assert item['cause_inputs']['core_change_count'] == 0
    assert_structured_observation(item)


def test_core_transition_observation():
    payload = build_team_story_observation_payload(team_context(
        stability={
            'stability_band': 'rebuilding',
            'core_retention_count': 0,
            'core_stability_pct': 0,
            'core_change_count': 3,
            'new_core_members': ['Fifth Arm', 'Sixth Arm', 'Seventh Arm'],
            'departed_core_members': ['First Arm', 'Second Arm', 'Third Arm'],
        },
    ))

    item = observation(payload, TYPE_CORE_TRANSITION)

    assert item['severity'] == 'high'
    assert item['headline_inputs']['stability_band'] == 'rebuilding'
    assert item['cause_inputs']['new_core_members'] == [
        'Fifth Arm',
        'Sixth Arm',
        'Seventh Arm',
    ]
    assert_structured_observation(item)


def test_depth_pressure_observation():
    payload = build_team_story_observation_payload(team_context(
        injury={
            'depth_pressure_band': 'heavy',
            'inactive_bullpen_arms_count': 4,
            'il_bullpen_arms_count': 3,
            'non_il_inactive_bullpen_arms_count': 1,
            'inactive_bullpen_share': 36.4,
        },
    ))

    item = observation(payload, TYPE_DEPTH_PRESSURE)

    assert item['severity'] == 'high'
    assert item['headline_inputs']['inactive_bullpen_arms_count'] == 4
    assert item['cause_inputs']['il_bullpen_arms_count'] == 3
    assert item['baseline_inputs']['active_bullpen_arms_count'] == 7
    assert_structured_observation(item)


def test_team_with_multiple_observations_selects_strongest_internal_signal():
    payload = build_team_story_observation_payload(team_context(
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
    ))

    assert {
        item['type'] for item in payload['observations']
    } == {
        TYPE_ROTATION_PRESSURE,
        TYPE_CONCENTRATION_PRESSURE,
        TYPE_OPTIONALITY_STRENGTH,
    }
    assert payload['strongest_observation']['type'] == TYPE_CONCENTRATION_PRESSURE
    assert select_strongest_observation(payload['observations']) == payload['strongest_observation']


def test_top_observations_across_teams_are_internal_structured_outputs():
    team_one = build_team_story_observation_payload(team_context(
        team_id=1,
        team_name='Team One',
        rotation={'rotation_ip_trend': -1.2},
    ))
    team_two = build_team_story_observation_payload(team_context(
        team_id=2,
        team_name='Team Two',
        concentration={'concentration_band': 'concentrated'},
    ))
    team_three = build_team_story_observation_payload(team_context(
        team_id=3,
        team_name='Team Three',
        injury={'depth_pressure_band': 'heavy', 'inactive_bullpen_arms_count': 5},
    ))

    selected = select_top_observations([team_one, team_two, team_three], limit=2)
    engine = build_story_observation_engine_v1(
        team_contexts=[team_one_context := team_context(
            team_id=4,
            team_name='Team Four',
            stability={'stability_band': 'stable'},
        )],
        limit=5,
    )

    assert [item['type'] for item in selected] == [
        TYPE_ROTATION_PRESSURE,
        TYPE_DEPTH_PRESSURE,
    ]
    assert selected[0]['team'] == 'Team One'
    assert engine['capability'] == CAPABILITY
    assert engine['team_count'] == 1
    assert engine['teams'][0]['team_name'] == team_one_context['team']['team_name']
    assert engine['top_observations'][0]['type'] == TYPE_STABLE_CORE
    assert 'rank' not in selected[0]


def test_missing_context_returns_safe_neutral_payload():
    payload = build_team_story_observation_payload({
        'team_id': 500,
        'team': {'team_name': 'Missing Context Team', 'team_abbreviation': 'MCT'},
        'reference_date': None,
        'data_through_date': None,
        'limitations': ['No stored game-log context was found for this team.'],
    })

    assert payload['team_id'] == 500
    assert payload['observation_count'] == 0
    assert payload['observations'] == []
    assert payload['strongest_observation'] is None
    assert payload['limitations'] == ['No stored game-log context was found for this team.']


def test_neutral_context_does_not_trigger_observations():
    payload = build_team_story_observation_payload(team_context())

    assert payload['observation_count'] == 0
    assert payload['observations'] == []
    assert payload['strongest_observation'] is None
