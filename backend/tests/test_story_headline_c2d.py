"""Headline checks (Phase C2D).

Headline-only: the weak families (depth constraint, trust lane, bridge,
availability depth) read shorter, more concrete, and more positive where the
read is positive; the strong contrast headlines are preserved; systems words
(map / operational core / route / lane) are reduced; governance and payload
shape are unchanged. Headlines are the voice-library PURPOSE_OPENING forms.
"""

from services.story_construction_engine import construct_team_story_frames
from services.story_observation_engine import (
    TYPE_DEPTH_PRESSURE,
    TYPE_OPTIONALITY_STRENGTH,
    TYPE_ROTATION_PRESSURE,
)
from services.story_writer_v1 import SECTION_KEYS, write_story_frame
from services.story_voice_library_v1 import (
    BEAT_AVAILABILITY_DEPTH,
    BEAT_BRIDGE,
    BEAT_COVERAGE_PRESSURE,
    BEAT_DEPTH_CONSTRAINT,
    BEAT_ROUTE_CHANGE,
    BEAT_SUSTAINABILITY_QUESTION,
    BEAT_TRUST_LANE,
    PURPOSE_OPENING,
    VOICE_LIBRARY,
    approved_sentence_forms,
    contains_banned_public_language,
    contains_denied_public_phrase,
    render_voice_line,
)

TARGET_BEATS = (BEAT_DEPTH_CONSTRAINT, BEAT_TRUST_LANE, BEAT_BRIDGE, BEAT_AVAILABILITY_DEPTH)
LONG_FLAGGED_BEATS = (BEAT_TRUST_LANE, BEAT_BRIDGE)


def _ctx(*, team_id=118, team_name='Kansas City Royals', optionality=None, injury=None):
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
        },
        'bullpen_concentration_context': {
            'concentration_band': 'normal', 'top_three_workload_share_10d': 61.0,
            'league_top_three_workload_share_10d': 58.0, 'top_three_share_delta_vs_league': 3.0,
            'bullpen_workload_total_10d': 180,
            'top_three_relievers_10d': [{'name': 'First Arm'}, {'name': 'Second Arm'}, {'name': 'Third Arm'}],
            'league_team_count_10d': 30,
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


def _headline(context, observation_type):
    payload = construct_team_story_frames(context)
    frame = next(f for f in payload['story_frames'] if f['observation_type'] == observation_type)
    output = write_story_frame(frame)
    assert tuple(output['written_observation'].keys()) == SECTION_KEYS  # payload shape unchanged
    return output['written_observation']['headline']


# ── Generation still works ────────────────────────────────────────────────────

def test_each_public_beat_renders_a_governed_headline():
    for beat in (BEAT_COVERAGE_PRESSURE, BEAT_SUSTAINABILITY_QUESTION, BEAT_ROUTE_CHANGE,
                 *TARGET_BEATS):
        line = render_voice_line(
            beat, stable_parts=(1, beat, 'First Arm and Second Arm'),
            team='Test Team', possessive="Test Team's", names='First Arm and Second Arm',
        )
        assert line
        assert contains_denied_public_phrase(line) is False
        assert contains_banned_public_language(line) is False


def test_story_generation_still_produces_nonempty_headlines():
    for context, observation_type in (
        (_ctx(injury={'depth_pressure_band': 'heavy', 'active_bullpen_arms_count': 7,
                      'inactive_bullpen_arms_count': 4, 'il_bullpen_arms_count': 3,
                      'non_il_inactive_bullpen_arms_count': 1}), TYPE_DEPTH_PRESSURE),
        (_ctx(optionality={'optionality_band': 'deep', 'practical_close_game_paths_count': 6,
                           'available_arms_count': 7, 'clean_workload_options': [{'name': 'Clean One'}],
                           'secondary_options': [{'name': 'Sec One'}]}), TYPE_OPTIONALITY_STRENGTH),
        (_ctx(), TYPE_ROTATION_PRESSURE),
    ):
        headline = _headline(context, observation_type)
        assert headline and len(headline.split()) <= 14


# ── Weak families read shorter ────────────────────────────────────────────────

def test_target_beat_headlines_are_short_and_scannable():
    for beat in TARGET_BEATS:
        longest = max(len(form.split()) for form in approved_sentence_forms(beat))
        assert longest <= 14, (beat, longest)
    for beat in LONG_FLAGGED_BEATS:
        longest = max(len(form.split()) for form in approved_sentence_forms(beat))
        assert longest <= 13, (beat, longest)


# ── Reduced systems language, more baseball texture ───────────────────────────

def test_target_beats_drop_systems_jargon():
    for beat in TARGET_BEATS:
        for form in approved_sentence_forms(beat):
            lowered = form.lower()
            assert 'late-game map' not in lowered, form
            assert 'operational core' not in lowered, form
    # 'lane' is fully retired from the trust-lane openings in favor of plainer words.
    assert not any('lane' in form.lower() for form in approved_sentence_forms(BEAT_TRUST_LANE))


def test_target_beats_add_baseball_texture():
    pooled = ' '.join(
        form.lower()
        for beat in TARGET_BEATS
        for form in approved_sentence_forms(beat)
    )
    assert any(word in pooled for word in ('seventh', 'eighth', 'ninth', 'lead', 'save'))


# ── Strong patterns preserved ─────────────────────────────────────────────────

def test_strong_headline_patterns_are_preserved():
    coverage = approved_sentence_forms(BEAT_COVERAGE_PRESSURE)
    route = approved_sentence_forms(BEAT_ROUTE_CHANGE)
    assert 'The ERA tells one story; the workload tells another' in coverage
    assert 'The bullpen continues to bend toward {names}' in route
    assert 'When the game tightens, {names} still shape the first call' in route
    # The two strong bridge contrast headlines survive the trim.
    bridge = approved_sentence_forms(BEAT_BRIDGE)
    assert 'The late innings are covered; the bridge to them is the soft spot' in bridge
    assert 'The back of the bullpen is settled; the bridge to it is not' in bridge


# ── Positive headlines feel positive ──────────────────────────────────────────

def test_availability_headlines_read_positive():
    forms = approved_sentence_forms(BEAT_AVAILABILITY_DEPTH)
    negative = ('fewer', 'thin', 'thinner', 'narrow', 'pressure', 'short list', 'soft spot')
    for form in forms:
        lowered = form.lower()
        for term in negative:
            assert term not in lowered, (form, term)
    positive = ('rested', 'fresh', 'plenty', 'ready', 'choices', 'spare', 'deep', 'depth')
    assert sum(any(p in form.lower() for p in positive) for form in forms) >= 5


# ── Governance across every headline form ─────────────────────────────────────

def test_all_opening_forms_pass_governance():
    for beat, purposes in VOICE_LIBRARY.items():
        for form in purposes.get(PURPOSE_OPENING, ()):
            assert contains_denied_public_phrase(form) is False, form
            assert contains_banned_public_language(form) is False, form
            # Headlines never name a probability/prediction/ranking/recommendation.
            lowered = form.lower()
            for term in ('rank', 'should', 'recommend', 'projected', 'odds', 'guaranteed'):
                assert term not in lowered, (form, term)
