from services.story_construction_engine import construct_story_frame, construct_team_story_frames
from services.story_observation_engine import (
    TYPE_BRIDGE_INSTABILITY,
    TYPE_CONCENTRATION_PRESSURE,
    TYPE_CORE_TRANSITION,
    TYPE_DEPTH_PRESSURE,
    TYPE_OPTIONALITY_STRENGTH,
    TYPE_ROTATION_PRESSURE,
    TYPE_STABLE_CORE,
    TYPE_TRUST_LANE_PRESSURE,
)
from services.story_writer_v1 import (
    BANNED_TERMS,
    CAPABILITY,
    ROBOTIC_TERMS,
    SECTION_KEYS,
    build_story_writer_v1,
    write_story_frame,
    write_team_story_frames,
)
from services.story_voice_library_v1 import contains_denied_public_phrase


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


def assert_no_robotic_language(output):
    text = written_text(output).lower()
    for term in ROBOTIC_TERMS:
        assert term not in text
    assert contains_denied_public_phrase(text) is False


def assert_quality_sections(output):
    written = output['written_observation']
    assert written['headline']
    assert written['observation_paragraph']
    assert written['baseline_paragraph']
    assert written['cause_paragraph']
    assert written['constraint_paragraph']
    assert_no_banned_language(output)
    assert_no_robotic_language(output)
    assert output['validation']['contains_banned_language'] is False
    assert output['validation']['contains_robotic_language'] is False


def _trust_lane_optionality(*, clean=1, secondary=5, available=6, band='flexible'):
    return {
        'context_available': True,
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


def _bridge_inputs(*, early=45.0, coverage=4.2, monitor=3, limited=1, clean=1, available=3):
    return dict(
        rotation={
            'rotation_avg_ip_7d': 5.4, 'rotation_avg_ip_14d': 5.5, 'rotation_ip_trend': -0.1,
            'early_bullpen_entry_rate': early, 'bullpen_coverage_ip_7d': coverage,
        },
        optionality={
            'context_available': True, 'optionality_band': 'narrow',
            'practical_close_game_paths_count': 3, 'available_arms_count': available,
            'monitor_arms_count': monitor, 'limited_arms_count': limited, 'restricted_arms_count': limited,
            'avoid_arms_count': 0, 'unavailable_arms_count': 0,
            'clean_workload_options': [{'name': f'Clean {i + 1}'} for i in range(clean)],
            'secondary_options': [{'name': f'Mid {i + 1}'} for i in range(max(monitor, 1))],
        },
        stability={
            'stability_band': 'stable',
            'current_operational_core': ['Core One', 'Core Two', 'Core Three'],
            'previous_operational_core': ['Core One', 'Core Two', 'Core Three'],
            'core_retention_count': 3, 'core_stability_pct': 100, 'core_change_count': 0,
            'new_core_members': [], 'departed_core_members': [],
            'current_core_size': 3, 'previous_core_size': 3,
        },
    )


def test_writer_outputs_bridge_instability_observation():
    frame = frame_for(team_context(**_bridge_inputs()), TYPE_BRIDGE_INSTABILITY)
    output = write_story_frame(frame)

    assert_writer_shape(output, TYPE_BRIDGE_INSTABILITY)
    assert_quality_sections(output)
    text = written_text(output)
    assert 'settled' in text.lower()
    assert 'bridge' in text.lower() or 'middle' in text.lower()
    assert output['written_observation']['constraint_paragraph'].startswith('If ')


def _bridge_inputs_with_coverage(coverage_read):
    inputs = _bridge_inputs()
    if coverage_read is not None:
        inputs['rotation'] = {**inputs['rotation'], 'coverage_baseline_read': coverage_read}
    return inputs


def test_writer_voices_bullpen_coverage_above_norm_baseline():
    frame = frame_for(
        team_context(**_bridge_inputs_with_coverage(
            {'available': True, 'metric': 'bullpen_coverage_ip_7d', 'comparison': 'above_average'},
        )),
        TYPE_BRIDGE_INSTABILITY,
    )

    text = written_text(write_story_frame(frame))

    assert 'innings a game on the way there' in text
    assert 'above the league norm for recent bullpen coverage' in text


def test_writer_voices_bullpen_coverage_heavy_baseline():
    frame = frame_for(
        team_context(**_bridge_inputs_with_coverage(
            {'available': True, 'metric': 'bullpen_coverage_ip_7d', 'comparison': 'among_highest'},
        )),
        TYPE_BRIDGE_INSTABILITY,
    )

    text = written_text(write_story_frame(frame))

    assert 'among the heavier recent bullpen-coverage workloads' in text


def test_writer_bridge_without_coverage_read_keeps_existing_copy():
    frame = frame_for(team_context(**_bridge_inputs()), TYPE_BRIDGE_INSTABILITY)

    text = written_text(write_story_frame(frame))

    assert 'innings a game on the way there' in text
    assert 'league norm for recent bullpen coverage' not in text


def test_writer_bridge_guarded_coverage_read_keeps_existing_copy():
    frame = frame_for(
        team_context(**_bridge_inputs_with_coverage(
            {'available': False, 'comparison': 'insufficient_sample'},
        )),
        TYPE_BRIDGE_INSTABILITY,
    )

    text = written_text(write_story_frame(frame))

    # Guarded coverage read -> existing bridge copy preserved, no league sentence.
    assert 'innings a game on the way there' in text
    assert 'league norm for recent bullpen coverage' not in text


def test_bullpen_coverage_baseline_language_has_no_ranking_or_recommendation_terms():
    from services.story_writer_v1 import _COVERAGE_BASELINE_SENTENCE

    forbidden = (
        'highest', 'lowest', '#1', 'top-ranked', 'league-leading', 'most overworked', 'least overworked',
        'best', 'worst', 'rank', 'recommend', 'should', 'likely to', 'projected', 'predict', 'will ',
    )
    for sentence in _COVERAGE_BASELINE_SENTENCE.values():
        lowered = sentence.lower()
        for term in forbidden:
            assert term not in lowered, (sentence, term)


def test_writer_outputs_trust_lane_pressure_observation():
    frame = frame_for(
        team_context(optionality=_trust_lane_optionality(clean=1, secondary=5, available=6)),
        TYPE_TRUST_LANE_PRESSURE,
    )
    output = write_story_frame(frame)

    assert_writer_shape(output, TYPE_TRUST_LANE_PRESSURE)
    assert_quality_sections(output)
    text = written_text(output)
    assert '6 available arms' in text
    assert 'trusted' in text.lower()
    assert output['written_observation']['constraint_paragraph'].startswith('If ')


def test_writer_trust_lane_handles_zero_clean_options():
    # The strongest case: an acceptable board with no clean arms at all.
    frame = frame_for(
        team_context(optionality=_trust_lane_optionality(clean=0, secondary=5, available=5)),
        TYPE_TRUST_LANE_PRESSURE,
    )
    output = write_story_frame(frame)

    assert_writer_shape(output, TYPE_TRUST_LANE_PRESSURE)
    assert_quality_sections(output)
    assert 'none of them come in clean' in written_text(output).lower()


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
    assert "Royals's" not in text
    assert '4.1 innings' in text
    assert '5.4 starter innings' in text
    assert 'starters are not covering as many innings as the recent baseline' in text.lower()
    assert '4.9 bullpen innings per game' in text
    assert 'handing the game to the bullpen earlier' in text
    assert output['written_observation']['constraint_paragraph'].startswith('If short starts continue')
    assert_quality_sections(output)


def _rotation_pressure_rotation(*, comparison=None, available=True):
    rotation = {
        'rotation_avg_ip_7d': 4.1,
        'rotation_avg_ip_14d': 5.4,
        'rotation_ip_trend': -1.3,
        'early_bullpen_entry_rate': 50.0,
        'bullpen_coverage_ip_7d': 4.9,
    }
    if comparison is not None or available is False:
        read = {'available': available, 'comparison': comparison}
        if available:
            read['metric'] = 'rotation_avg_ip_7d'
        rotation['baseline_read'] = read
    return rotation


def test_writer_voices_rotation_length_below_norm_baseline():
    frame = frame_for(
        team_context(rotation=_rotation_pressure_rotation(comparison='below_average')),
        TYPE_ROTATION_PRESSURE,
    )

    text = written_text(write_story_frame(frame))

    assert 'shorter than the league norm for starter length' in text
    # The league read anchors the seven-day value, so the restate line is dropped.
    assert 'seven-day handoff' not in text


def test_writer_voices_rotation_length_above_norm_baseline():
    frame = frame_for(
        team_context(rotation=_rotation_pressure_rotation(comparison='above_average')),
        TYPE_ROTATION_PRESSURE,
    )

    text = written_text(write_story_frame(frame))

    assert 'longer than the league norm for starter length' in text


def test_writer_rotation_without_baseline_read_keeps_existing_copy():
    frame = frame_for(
        team_context(rotation=_rotation_pressure_rotation()),
        TYPE_ROTATION_PRESSURE,
    )

    text = written_text(write_story_frame(frame))

    assert 'The current seven-day handoff is 4.1 innings' in text
    assert 'league norm' not in text


def test_writer_rotation_guarded_baseline_keeps_existing_copy():
    frame = frame_for(
        team_context(rotation=_rotation_pressure_rotation(comparison='insufficient_sample', available=False)),
        TYPE_ROTATION_PRESSURE,
    )

    text = written_text(write_story_frame(frame))

    # Guarded read -> existing rotation copy preserved, no forced league comparison.
    assert 'The current seven-day handoff is 4.1 innings' in text
    assert 'league norm' not in text


def test_rotation_length_baseline_language_has_no_ranking_or_recommendation_terms():
    from services.story_writer_v1 import _ROTATION_LENGTH_BASELINE_SENTENCE

    forbidden = (
        'highest', 'lowest', 'longest', 'shortest', '#1', 'top-ranked', 'league-leading',
        'most', 'best', 'worst', 'rank', 'recommend', 'should', 'likely to', 'projected', 'predict', 'will ',
    )
    for sentence in _ROTATION_LENGTH_BASELINE_SENTENCE.values():
        lowered = sentence.lower()
        for term in forbidden:
            assert term not in lowered, (sentence, term)


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
    assert 'meaningful innings are bunching around a smaller group' in text
    assert 'The same arms are carrying the meaningful work' in text
    assert 'If this pattern continues, the margin for spreading the work stays thin' in text
    assert 'current operational core' not in text.lower()
    assert_quality_sections(output)


def test_writer_voices_distribution_aware_baseline_when_available():
    frame = frame_for(team_context(concentration={
        'concentration_band': 'narrow',
        'top_three_workload_share_10d': 94.0,
        'league_top_three_workload_share_10d': 58.0,
        'top_three_share_delta_vs_league': 36.0,
        'bullpen_workload_total_10d': 240,
        'baseline_read': {'available': True, 'metric': 'top_share', 'comparison': 'among_highest'},
    }), TYPE_CONCENTRATION_PRESSURE)

    text = written_text(write_story_frame(frame))

    assert 'among the more concentrated workloads in baseball recently' in text
    # The distribution-aware read replaces the raw league-average line (no stacking).
    assert 'The league comparison is' not in text
    assert '36 percentage points' not in text


def test_writer_voices_well_above_average_baseline():
    frame = frame_for(team_context(concentration={
        'concentration_band': 'concentrated',
        'top_three_workload_share_10d': 65.0,
        'league_top_three_workload_share_10d': 48.0,
        'top_three_share_delta_vs_league': 17.0,
        'bullpen_workload_total_10d': 200,
        'baseline_read': {'available': True, 'metric': 'top_share', 'comparison': 'well_above_average'},
    }), TYPE_CONCENTRATION_PRESSURE)

    text = written_text(write_story_frame(frame))

    assert 'well above the league norm' in text


def test_writer_falls_back_to_league_average_when_baseline_guarded():
    frame = frame_for(team_context(concentration={
        'concentration_band': 'narrow',
        'top_three_workload_share_10d': 94.0,
        'league_top_three_workload_share_10d': 58.0,
        'top_three_share_delta_vs_league': 36.0,
        'bullpen_workload_total_10d': 240,
        'baseline_read': {'available': False, 'comparison': 'insufficient_sample'},
    }), TYPE_CONCENTRATION_PRESSURE)

    text = written_text(write_story_frame(frame))

    # Guarded read -> existing behavior preserved, no distribution-aware sentence.
    assert '58%' in text
    assert 'league norm' not in text
    assert 'among the more concentrated' not in text


def test_baseline_story_language_has_no_ranking_or_recommendation_terms():
    from services.story_writer_v1 import _CONCENTRATION_BASELINE_SENTENCE

    forbidden = (
        'highest', '#1', 'top-ranked', 'league-leading', 'most concentrated',
        'worst', 'best', 'rank', 'recommend', 'should', 'predict', 'will ',
    )
    for sentence in _CONCENTRATION_BASELINE_SENTENCE.values():
        lowered = sentence.lower()
        for term in forbidden:
            assert term not in lowered, (sentence, term)


def _concentration_with_lead_arm(lead_arm_read):
    concentration = {
        'concentration_band': 'narrow',
        'top_three_workload_share_10d': 94.0,
        'league_top_three_workload_share_10d': 58.0,
        'top_three_share_delta_vs_league': 36.0,
        'bullpen_workload_total_10d': 240,
        'baseline_read': {'available': True, 'metric': 'top_share', 'comparison': 'among_highest'},
    }
    if lead_arm_read is not None:
        concentration['top_one_workload_share_10d'] = 48.0
        concentration['lead_arm_baseline_read'] = lead_arm_read
    return concentration


def test_writer_voices_lead_arm_baseline_as_secondary_read():
    frame = frame_for(
        team_context(concentration=_concentration_with_lead_arm(
            {'available': True, 'metric': 'top_one_share', 'comparison': 'above_average'},
        )),
        TYPE_CONCENTRATION_PRESSURE,
    )

    text = written_text(write_story_frame(frame))

    # Primary top-three read stays; lead-arm read is layered as a secondary line.
    assert 'among the more concentrated workloads in baseball recently' in text
    assert 'The lead arm is carrying more of the workload than a typical bullpen' in text


def test_writer_omits_lead_arm_sentence_when_read_absent():
    frame = frame_for(
        team_context(concentration=_concentration_with_lead_arm(None)),
        TYPE_CONCENTRATION_PRESSURE,
    )

    text = written_text(write_story_frame(frame))

    assert 'among the more concentrated workloads in baseball recently' in text
    assert 'lead arm' not in text.lower()


def test_writer_omits_lead_arm_sentence_when_read_guarded():
    frame = frame_for(
        team_context(concentration=_concentration_with_lead_arm(
            {'available': False, 'comparison': 'insufficient_sample'},
        )),
        TYPE_CONCENTRATION_PRESSURE,
    )

    text = written_text(write_story_frame(frame))

    # Guarded lead-arm read -> existing C1E copy preserved, no lead-arm sentence.
    assert 'among the more concentrated workloads in baseball recently' in text
    assert 'lead arm' not in text.lower()


def test_lead_arm_baseline_language_has_no_ranking_or_recommendation_terms():
    from services.story_writer_v1 import _LEAD_ARM_BASELINE_SENTENCE

    forbidden = (
        'highest', 'lowest', '#1', 'top-ranked', 'league-leading', 'most used', 'least used',
        'best', 'worst', 'rank', 'recommend', 'should', 'likely to', 'projected', 'predict', 'will ',
    )
    for sentence in _LEAD_ARM_BASELINE_SENTENCE.values():
        lowered = sentence.lower()
        for term in forbidden:
            assert term not in lowered, (sentence, term)


def test_writer_voices_clean_options_below_norm_baseline():
    optionality = _trust_lane_optionality(clean=1, secondary=5, available=6)
    optionality['baseline_read'] = {
        'available': True, 'metric': 'clean_trusted_options', 'comparison': 'below_average',
    }
    frame = frame_for(team_context(optionality=optionality), TYPE_TRUST_LANE_PRESSURE)

    text = written_text(write_story_frame(frame))

    assert 'thinner than the league norm' in text
    # The distribution-aware read replaces the board-vs-lane comparison line.
    assert 'The comparison point is the' not in text


def test_writer_voices_deeper_clean_options_baseline():
    optionality = _trust_lane_optionality(clean=1, secondary=5, available=6)
    optionality['baseline_read'] = {
        'available': True, 'metric': 'clean_trusted_options', 'comparison': 'above_average',
    }
    frame = frame_for(team_context(optionality=optionality), TYPE_TRUST_LANE_PRESSURE)

    text = written_text(write_story_frame(frame))

    assert 'deeper than the league norm' in text


def test_writer_falls_back_to_board_comparison_when_clean_options_baseline_guarded():
    optionality = _trust_lane_optionality(clean=1, secondary=5, available=6)
    optionality['baseline_read'] = {'available': False, 'comparison': 'insufficient_sample'}
    frame = frame_for(team_context(optionality=optionality), TYPE_TRUST_LANE_PRESSURE)

    text = written_text(write_story_frame(frame))

    # Guarded read -> existing behavior preserved, no distribution-aware sentence.
    assert 'The comparison point is the 6-arm available board' in text
    assert 'league norm' not in text


def test_writer_trust_lane_without_baseline_read_keeps_board_comparison():
    # No baseline_read at all (legacy frame) still produces the board comparison.
    frame = frame_for(
        team_context(optionality=_trust_lane_optionality(clean=1, secondary=5, available=6)),
        TYPE_TRUST_LANE_PRESSURE,
    )

    text = written_text(write_story_frame(frame))

    assert 'The comparison point is the 6-arm available board' in text
    assert 'league norm' not in text


def test_clean_options_baseline_language_has_no_ranking_or_recommendation_terms():
    from services.story_writer_v1 import _CLEAN_OPTIONS_BASELINE_SENTENCE

    forbidden = (
        'highest', 'deepest', '#1', 'top-ranked', 'league-leading', 'most',
        'worst', 'best', 'rank', 'recommend', 'should', 'predict', 'will ',
    )
    for sentence in _CLEAN_OPTIONS_BASELINE_SENTENCE.values():
        lowered = sentence.lower()
        for term in forbidden:
            assert term not in lowered, (sentence, term)


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
    assert '6 close-game choices' in text
    assert '7 available arms' in text
    assert '2 clean workload options' not in text
    assert '2 low-workload late-inning choices' in text
    assert 'clearest late-inning choices include Clean One and Clean Two' in text
    assert 'multiple late-inning options rather than force one route' in text
    assert_quality_sections(output)


def _optionality_strength_optionality(*, comparison=None, available=True):
    optionality = {
        'optionality_band': 'deep',
        'practical_close_game_paths_count': 6,
        'available_arms_count': 7,
        'clean_workload_options': [{'name': 'Clean One'}, {'name': 'Clean Two'}],
        'secondary_options': [{'name': 'Secondary One'}],
    }
    if comparison is not None or available is False:
        read = {'available': available, 'comparison': comparison}
        if available:
            read['metric'] = 'clean_trusted_options'
        optionality['baseline_read'] = read
    return optionality


def test_writer_voices_optionality_depth_above_norm_baseline():
    frame = frame_for(
        team_context(optionality=_optionality_strength_optionality(comparison='above_average')),
        TYPE_OPTIONALITY_STRENGTH,
    )

    text = written_text(write_story_frame(frame))

    # The internal clean-count line is enriched with a league depth read.
    assert '2 low-workload late-inning choices' in text
    assert 'deeper than the league norm' in text


def test_writer_voices_optionality_depth_among_highest_baseline():
    frame = frame_for(
        team_context(optionality=_optionality_strength_optionality(comparison='among_highest')),
        TYPE_OPTIONALITY_STRENGTH,
    )

    text = written_text(write_story_frame(frame))

    assert 'among the deeper clean-options groups in baseball' in text


def test_writer_optionality_strength_without_baseline_read_keeps_existing_copy():
    frame = frame_for(
        team_context(optionality=_optionality_strength_optionality()),
        TYPE_OPTIONALITY_STRENGTH,
    )

    text = written_text(write_story_frame(frame))

    assert '2 low-workload late-inning choices' in text
    assert 'league norm' not in text
    assert 'among the deeper' not in text


def test_writer_optionality_strength_guarded_baseline_keeps_existing_copy():
    frame = frame_for(
        team_context(optionality=_optionality_strength_optionality(comparison='insufficient_sample', available=False)),
        TYPE_OPTIONALITY_STRENGTH,
    )

    text = written_text(write_story_frame(frame))

    # Guarded read -> existing positive copy preserved, no forced league comparison.
    assert '2 low-workload late-inning choices' in text
    assert 'league norm' not in text
    assert 'among the deeper' not in text


def test_optionality_depth_baseline_language_has_no_ranking_or_recommendation_terms():
    from services.story_writer_v1 import _OPTIONALITY_DEPTH_BASELINE_SENTENCE

    forbidden = (
        'highest', 'lowest', 'deepest', '#1', 'top-ranked', 'league-leading', 'most',
        'worst', 'best', 'rank', 'recommend', 'should', 'likely to', 'projected', 'predict', 'will ',
    )
    for sentence in _OPTIONALITY_DEPTH_BASELINE_SENTENCE.values():
        lowered = sentence.lower()
        for term in forbidden:
            assert term not in lowered, (sentence, term)


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
    assert 'First Arm, Second Arm, and Third Arm' in text
    assert '100%' in text
    assert 'route points back through First Arm, Second Arm, and Third Arm' in text
    assert_quality_sections(output)


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
    assert '3-spot change from the prior route' in text
    assert 'Fifth Arm, Sixth Arm, and Seventh Arm' in text
    assert '0 arms from that baseline' in text
    assert 'The added arms are' in text
    assert 'route points back through Fifth Arm, Sixth Arm, and Seventh Arm' in text
    assert_quality_sections(output)


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
    assert 'For Kansas City Royals, the roster shows 7 bullpen arms, but 4 relievers are not part of the current game plan' in text
    assert 'Inactive Arm' in text
    assert "{'name':" not in text
    assert '3 IL arms' in text
    assert '1 non-IL inactive arm' in text
    assert 'fewer ways to cover the late innings than the roster count suggests' in text
    assert_quality_sections(output)


def test_writer_handles_sox_team_possessives_from_real_audit():
    teams = [
        ('Boston Red Sox', "Boston Red Sox' bullpen"),
        ('Chicago White Sox', "Chicago White Sox' bullpen"),
    ]
    for team_name, expected in teams:
        frame = frame_for(
            team_context(
                team_name=team_name,
                injury={
                    'depth_pressure_band': 'heavy',
                    'active_bullpen_arms_count': 9,
                    'inactive_bullpen_arms_count': 13,
                    'il_bullpen_arms_count': 6,
                    'non_il_inactive_bullpen_arms_count': 7,
                },
            ),
            TYPE_DEPTH_PRESSURE,
        )

        output = write_story_frame(frame)
        text = written_text(output)

        assert "Sox'" in text or team_name in text
        assert "Sox's" not in text
        assert_quality_sections(output)


def test_writer_is_deterministic_for_same_frame():
    frame = frame_for(team_context(concentration={'concentration_band': 'narrow'}), TYPE_CONCENTRATION_PRESSURE)

    first = write_story_frame(frame)
    second = write_story_frame(frame)

    assert first == second


def test_writer_varies_openings_inside_same_public_archetype_without_randomness():
    first_outputs = []
    second_outputs = []
    for team_id in range(100, 130):
        frame = frame_for(
            team_context(
                team_id=team_id,
                team_name=f'Voice Team {team_id}',
                team_abbreviation=f'V{team_id}',
                stability={
                    'stability_band': 'stable',
                    'current_operational_core': ['First Arm', 'Second Arm'],
                    'previous_operational_core': ['First Arm', 'Second Arm'],
                    'core_retention_count': 2,
                    'core_stability_pct': 100,
                    'core_change_count': 0,
                },
            ),
            TYPE_STABLE_CORE,
        )
        first_outputs.append(write_story_frame(frame)['written_observation']['headline'])
        second_outputs.append(write_story_frame(frame)['written_observation']['headline'])

    assert first_outputs == second_outputs
    assert len(set(first_outputs)) >= 5
    for headline in first_outputs:
        assert contains_denied_public_phrase(headline) is False


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
    assert_no_robotic_language(output)
    assert output['validation']['contains_banned_language'] is False
    assert output['validation']['contains_robotic_language'] is False


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
    text = written_text(output)
    assert '6 close-game choices' in text
    assert '0 unavailable arms' not in text


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
