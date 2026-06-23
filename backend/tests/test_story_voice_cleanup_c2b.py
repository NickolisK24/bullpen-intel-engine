"""Voice cleanup checks (Phase C2B).

Communication-only: the voice layer and stock writer lines should no longer
repeat "The comparison point is …" (it duplicates the feed beat label), should
not drop raw band enum words into prose, should keep the "thinner than the …
count suggests" idea to a small number of governed variants, and should give
positive reads (availability depth / stable core) a genuinely positive voice.
No metric, selection, ranking, or payload-shape change is asserted here.
"""

from services.story_construction_engine import construct_team_story_frames
from services.story_observation_engine import (
    TYPE_BRIDGE_INSTABILITY,
    TYPE_CORE_TRANSITION,
    TYPE_DEPTH_PRESSURE,
    TYPE_OPTIONALITY_STRENGTH,
    TYPE_ROTATION_PRESSURE,
    TYPE_STABLE_CORE,
    TYPE_TRUST_LANE_PRESSURE,
)
from services.story_writer_v1 import (
    SECTION_KEYS,
    _CONCENTRATION_BAND_SENTENCE,
    _DEPTH_PRESSURE_BAND_SENTENCE,
    _OPTIONALITY_BAND_SENTENCE,
    write_story_frame,
)
from services.story_voice_library_v1 import (
    BEAT_AVAILABILITY_DEPTH,
    BEAT_DEPTH_CONSTRAINT,
    BEAT_TRUST_LANE,
    approved_sentence_forms,
    contains_banned_public_language,
    contains_denied_public_phrase,
)


def _ctx(*, team_name='Kansas City Royals', rotation=None, concentration=None,
         optionality=None, stability=None, injury=None):
    return {
        'team_id': 118,
        'team': {'team_id': 118, 'team_name': team_name, 'team_abbreviation': 'KC'},
        'reference_date': '2026-06-20',
        'data_through_date': '2026-06-20',
        'rotation_context': {
            'context_available': True,
            'rotation_avg_ip_7d': 5.7, 'rotation_avg_ip_14d': 5.8, 'rotation_ip_trend': -0.1,
            'early_bullpen_entry_rate': 10.0, 'bullpen_coverage_ip_7d': 3.3,
            'rotation_games_analyzed_7d': 6, 'rotation_games_analyzed_14d': 12,
            'rotation_early_bullpen_entry_games_14d': 1,
            **(rotation or {}),
        },
        'bullpen_concentration_context': {
            'concentration_band': 'normal', 'top_three_workload_share_10d': 61.0,
            'league_top_three_workload_share_10d': 58.0, 'top_three_share_delta_vs_league': 3.0,
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
            'optionality_band': 'narrow', 'practical_close_game_paths_count': 3,
            'available_arms_count': 3, 'monitor_arms_count': 1, 'restricted_arms_count': 2,
            'limited_arms_count': 1, 'avoid_arms_count': 1, 'unavailable_arms_count': 0,
            'clean_workload_options': [{'name': 'Clean Arm'}],
            'secondary_options': [{'name': 'Monitor Arm'}],
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
            'injury_context_confidence': 'high',
            'inactive_bullpen_arms': [{'name': 'Inactive Arm'}],
            'role_uncertain_inactive_count': 0, 'unknown_roster_status_count': 0,
            **(injury or {}),
        },
        'limitations': [],
    }


def _frame(context, observation_type):
    payload = construct_team_story_frames(context)
    return next(
        frame for frame in payload['story_frames']
        if frame['observation_type'] == observation_type
    )


def _text(context, observation_type):
    output = write_story_frame(_frame(context, observation_type))
    written = output['written_observation']
    # Payload shape is unchanged: the same four sections plus headline.
    assert tuple(written.keys()) == SECTION_KEYS
    return ' '.join(v for v in written.values() if v)


# ── 1. "The comparison point is …" is gone from generated prose ───────────────

def test_comparison_point_phrase_removed_from_all_families():
    cases = [
        (_ctx(rotation={'rotation_avg_ip_7d': 4.1, 'rotation_avg_ip_14d': 5.4,
                        'rotation_ip_trend': -1.3, 'early_bullpen_entry_rate': 50.0,
                        'bullpen_coverage_ip_7d': 4.9}), TYPE_ROTATION_PRESSURE),
        (_ctx(stability={'stability_band': 'rebuilding',
                         'current_operational_core': ['Fifth Arm', 'Sixth Arm'],
                         'previous_operational_core': ['First Arm', 'Second Arm'],
                         'new_core_members': ['Fifth Arm', 'Sixth Arm'],
                         'departed_core_members': ['First Arm', 'Second Arm'],
                         'core_retention_count': 0, 'core_stability_pct': 0,
                         'core_change_count': 2}), TYPE_CORE_TRANSITION),
        (_ctx(optionality={'context_available': True, 'optionality_band': 'flexible',
                           'practical_close_game_paths_count': 4,
                           'available_arms_count': 6, 'monitor_arms_count': 1,
                           'restricted_arms_count': 0, 'limited_arms_count': 0,
                           'avoid_arms_count': 0, 'unavailable_arms_count': 0,
                           'clean_workload_options': [{'name': 'Clean 1'}],
                           'secondary_options': [{'name': f'Flagged {i + 1}'} for i in range(5)]}),
         TYPE_TRUST_LANE_PRESSURE),
        (_ctx(rotation={'rotation_avg_ip_7d': 5.4, 'rotation_avg_ip_14d': 5.5,
                        'rotation_ip_trend': -0.1, 'early_bullpen_entry_rate': 45.0,
                        'bullpen_coverage_ip_7d': 4.2},
              optionality={'context_available': True, 'optionality_band': 'narrow',
                           'practical_close_game_paths_count': 3, 'available_arms_count': 3,
                           'monitor_arms_count': 3, 'limited_arms_count': 1,
                           'restricted_arms_count': 1, 'avoid_arms_count': 0,
                           'unavailable_arms_count': 0,
                           'clean_workload_options': [{'name': 'Clean 1'}],
                           'secondary_options': [{'name': f'Mid {i + 1}'} for i in range(3)]},
              stability={'stability_band': 'stable',
                         'current_operational_core': ['Core One', 'Core Two', 'Core Three'],
                         'previous_operational_core': ['Core One', 'Core Two', 'Core Three'],
                         'core_retention_count': 3, 'core_stability_pct': 100,
                         'core_change_count': 0}), TYPE_BRIDGE_INSTABILITY),
    ]
    for context, observation_type in cases:
        text = _text(context, observation_type)
        assert 'comparison point' not in text.lower()


# ── 2. Raw band drop-ins replaced with human phrasing ─────────────────────────

def test_optionality_band_reads_as_human_sentence_not_enum():
    text = _text(_ctx(optionality={
        'optionality_band': 'deep', 'practical_close_game_paths_count': 6,
        'available_arms_count': 7, 'clean_workload_options': [{'name': 'Clean One'}],
        'secondary_options': [{'name': 'Sec One'}],
    }), TYPE_OPTIONALITY_STRENGTH)
    assert 'the late-game map deep' not in text.lower()
    assert _OPTIONALITY_BAND_SENTENCE['deep'] in text


def test_depth_band_reads_as_human_sentence_not_enum():
    text = _text(_ctx(injury={
        'depth_pressure_band': 'heavy', 'active_bullpen_arms_count': 7,
        'inactive_bullpen_arms_count': 4, 'il_bullpen_arms_count': 3,
        'non_il_inactive_bullpen_arms_count': 1, 'inactive_bullpen_share': 36.4,
    }), TYPE_DEPTH_PRESSURE)
    assert 'late-inning depth heavy' not in text.lower()
    assert _DEPTH_PRESSURE_BAND_SENTENCE['heavy'] in text


def test_workload_pattern_enum_phrase_removed():
    text = _text(_ctx(stability={
        'stability_band': 'stable',
        'current_operational_core': ['First Arm', 'Second Arm', 'Third Arm'],
        'previous_operational_core': ['First Arm', 'Second Arm', 'Third Arm'],
        'core_retention_count': 3, 'core_stability_pct': 100, 'core_change_count': 0,
    }), TYPE_STABLE_CORE)
    assert 'the workload pattern is' not in text.lower()


# ── 3. Positive reads sound positive ──────────────────────────────────────────

def test_stable_core_positive_voice_reads_naturally():
    text = _text(_ctx(stability={
        'stability_band': 'stable',
        'current_operational_core': ['First Arm', 'Second Arm', 'Third Arm'],
        'previous_operational_core': ['First Arm', 'Second Arm', 'Third Arm'],
        'core_retention_count': 3, 'core_stability_pct': 100, 'core_change_count': 0,
    }), TYPE_STABLE_CORE)
    assert 'the late innings still run through' in text.lower()
    assert 'the same arms have handled 100% of the recent late-inning work' in text.lower()
    assert 'route overlap' not in text.lower()
    assert '100%' in text


def test_optionality_strength_positive_band_phrase_present():
    text = _text(_ctx(optionality={
        'optionality_band': 'deep', 'practical_close_game_paths_count': 6,
        'available_arms_count': 7, 'clean_workload_options': [{'name': 'Clean One'}],
        'secondary_options': [{'name': 'Sec One'}],
    }), TYPE_OPTIONALITY_STRENGTH)
    assert 'room to work the late innings' in text.lower()


def test_availability_depth_has_positive_opening_forms():
    forms = approved_sentence_forms(BEAT_AVAILABILITY_DEPTH)
    assert any('rested' in form for form in forms)
    assert any('mix and match' in form or 'more than one way' in form for form in forms)


# ── 4. Repetition reduced, governance preserved ───────────────────────────────

def test_depth_constraint_openings_trimmed_but_keep_named_pressure_points():
    forms = approved_sentence_forms(BEAT_DEPTH_CONSTRAINT)
    assert 5 <= len(forms) <= 8
    assert any('{names}' in form and 'pressure point' in form for form in forms)
    assert any('{names}' in form and 'late-game map' in form for form in forms)
    assert any('{names}' in form and 'roster count' in form for form in forms)


def test_thinner_than_count_repetition_reduced_in_trust_lane_forms():
    forms = approved_sentence_forms(BEAT_TRUST_LANE)
    suggests = [form for form in forms if 'thinner than the' in form and 'suggests' in form.lower()]
    # At most one governed "thinner than the … suggests" opening remains, and the
    # roster-count variant of it is gone (depth constraint owns roster-count copy).
    assert len(suggests) <= 1
    assert not any('roster count suggests' in form for form in forms)


def test_new_voice_forms_preserve_governance():
    for beat in (BEAT_DEPTH_CONSTRAINT, BEAT_TRUST_LANE, BEAT_AVAILABILITY_DEPTH):
        for form in approved_sentence_forms(beat):
            assert contains_denied_public_phrase(form) is False
            assert contains_banned_public_language(form) is False


def test_band_sentence_maps_carry_no_banned_or_ranking_language():
    forbidden = (
        'bet', 'odds', 'probability', 'projected', 'predict', 'rank', 'should',
        'best', 'worst', 'highest', 'lowest', 'will ',
    )
    for mapping in (_OPTIONALITY_BAND_SENTENCE, _CONCENTRATION_BAND_SENTENCE,
                    _DEPTH_PRESSURE_BAND_SENTENCE):
        for sentence in mapping.values():
            lowered = sentence.lower()
            for term in forbidden:
                assert term not in lowered, (sentence, term)
