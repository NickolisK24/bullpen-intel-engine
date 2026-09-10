"""Narrative structure checks (Phase C2C).

Communication-structure only: forward ("what it creates") beats now vary their
opening instead of every story reading "If X, then Y"; positive reads
(availability depth / stable core) close on a positive consequence rather than a
pressure clause; and continuity carries a human sentence (never the internal
state name). No selection, ranking, metric, or payload-shape change is asserted.
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
from services.story_writer_v1 import SECTION_KEYS, write_story_frame
from services.story_voice_library_v1 import (
    BANNED_PUBLIC_LANGUAGE,
    DENIED_PUBLIC_PHRASES,
    FORWARD_CLAUSE_LINES,
    contains_banned_public_language,
    contains_denied_public_phrase,
    looks_like_forward_clause,
)
from services.story_feed import (
    CONTINUITY_SENTENCES,
    LEAGUE_CONTINUITY_SENTENCES,
    build_league_context,
    build_story_continuity,
)


def _ctx(*, team_id=118, team_name='Kansas City Royals', rotation=None,
         concentration=None, optionality=None, stability=None, injury=None):
    return {
        'team_id': team_id,
        'team': {'team_id': team_id, 'team_name': team_name, 'team_abbreviation': 'KC'},
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


def _constraint(context, observation_type):
    payload = construct_team_story_frames(context)
    frame = next(f for f in payload['story_frames'] if f['observation_type'] == observation_type)
    output = write_story_frame(frame)
    assert tuple(output['written_observation'].keys()) == SECTION_KEYS  # payload shape unchanged
    return output['written_observation']['constraint_paragraph']


# ── 1. Forward beats vary; "If the next game…" no longer dominates ────────────

def test_forward_clause_openings_vary_across_teams():
    openings = set()
    for team_id in range(100, 140):
        constraint = _constraint(
            _ctx(team_id=team_id, team_name=f'Team {team_id}',
                 stability={'stability_band': 'rebuilding',
                            'current_operational_core': ['Fifth Arm', 'Sixth Arm', 'Seventh Arm'],
                            'previous_operational_core': ['First Arm', 'Second Arm', 'Third Arm'],
                            'new_core_members': ['Fifth Arm', 'Sixth Arm', 'Seventh Arm'],
                            'departed_core_members': ['First Arm', 'Second Arm', 'Third Arm'],
                            'core_retention_count': 0, 'core_stability_pct': 0, 'core_change_count': 3}),
            TYPE_CORE_TRANSITION,
        )
        assert looks_like_forward_clause(constraint)
        openings.add(constraint.split(',')[0].split(' ')[0:3].__str__())
    # The same archetype produces more than one opening shape across teams.
    assert len(openings) >= 2


def test_not_every_forward_clause_starts_with_if():
    starts_with_if = 0
    total = 0
    for team_id in range(100, 130):
        constraint = _constraint(
            _ctx(team_id=team_id, team_name=f'Team {team_id}',
                 rotation={'rotation_avg_ip_7d': 4.1, 'rotation_avg_ip_14d': 5.4,
                           'rotation_ip_trend': -1.3, 'early_bullpen_entry_rate': 50.0,
                           'bullpen_coverage_ip_7d': 4.9}),
            TYPE_ROTATION_PRESSURE,
        )
        total += 1
        if constraint.startswith('If '):
            starts_with_if += 1
    assert total > 0
    assert starts_with_if < total  # at least one team gets a non-"If" forward shape


def test_multiple_forward_shapes_are_defined_per_beat():
    for beat, forms in FORWARD_CLAUSE_LINES.items():
        assert len(forms) >= 2, beat
        # Not all of a beat's forward shapes open with "If".
        assert any(not form.startswith('If ') for form in forms), beat


# ── 2. Positive reads close on a positive consequence ─────────────────────────

POSITIVE_FORWARD_MARKERS = (
    'can lean on more than one rested arm',
    'rather than forced onto one arm',
    'real late-inning flexibility for the manager',
)


def test_optionality_strength_has_positive_forward_structure():
    constraint = _constraint(_ctx(optionality={
        'optionality_band': 'deep', 'practical_close_game_paths_count': 6,
        'available_arms_count': 7, 'clean_workload_options': [{'name': 'Clean One'}],
        'secondary_options': [{'name': 'Sec One'}],
    }), TYPE_OPTIONALITY_STRENGTH)
    assert looks_like_forward_clause(constraint)
    assert any(marker in constraint for marker in POSITIVE_FORWARD_MARKERS)
    # It is not borrowing the pressure scaffolding.
    assert 'fewer ways' not in constraint.lower()
    assert 'thinner than' not in constraint.lower()


def test_stable_core_has_positive_forward_structure():
    constraint = _constraint(_ctx(stability={
        'stability_band': 'stable',
        'current_operational_core': ['First Arm', 'Second Arm', 'Third Arm'],
        'previous_operational_core': ['First Arm', 'Second Arm', 'Third Arm'],
        'core_retention_count': 3, 'core_stability_pct': 100, 'core_change_count': 0,
    }), TYPE_STABLE_CORE)
    assert looks_like_forward_clause(constraint)
    assert any(marker in constraint for marker in POSITIVE_FORWARD_MARKERS)
    assert 'fewer ways' not in constraint.lower()


# ── 3. Pressure reads still close on a forward consequence ────────────────────

def test_pressure_families_still_have_forward_clause():
    cases = [
        (_ctx(optionality={'context_available': True, 'optionality_band': 'flexible',
                           'practical_close_game_paths_count': 4, 'available_arms_count': 6,
                           'monitor_arms_count': 1, 'restricted_arms_count': 0, 'limited_arms_count': 0,
                           'avoid_arms_count': 0, 'unavailable_arms_count': 0,
                           'clean_workload_options': [{'name': 'Clean 1'}],
                           'secondary_options': [{'name': f'Flagged {i + 1}'} for i in range(5)]}),
         TYPE_TRUST_LANE_PRESSURE),
        (_ctx(injury={'depth_pressure_band': 'heavy', 'active_bullpen_arms_count': 7,
                      'inactive_bullpen_arms_count': 4, 'il_bullpen_arms_count': 3,
                      'non_il_inactive_bullpen_arms_count': 1}), TYPE_DEPTH_PRESSURE),
        (_ctx(rotation={'rotation_avg_ip_7d': 5.4, 'rotation_avg_ip_14d': 5.5,
                        'rotation_ip_trend': -0.1, 'early_bullpen_entry_rate': 45.0,
                        'bullpen_coverage_ip_7d': 4.2},
              optionality={'context_available': True, 'optionality_band': 'narrow',
                           'practical_close_game_paths_count': 3, 'available_arms_count': 3,
                           'monitor_arms_count': 3, 'limited_arms_count': 1, 'restricted_arms_count': 1,
                           'avoid_arms_count': 0, 'unavailable_arms_count': 0,
                           'clean_workload_options': [{'name': 'Clean 1'}],
                           'secondary_options': [{'name': f'Mid {i + 1}'} for i in range(3)]},
              stability={'stability_band': 'stable',
                         'current_operational_core': ['Core One', 'Core Two', 'Core Three'],
                         'previous_operational_core': ['Core One', 'Core Two', 'Core Three'],
                         'core_retention_count': 3, 'core_stability_pct': 100,
                         'core_change_count': 0}), TYPE_BRIDGE_INSTABILITY),
    ]
    for context, observation_type in cases:
        assert looks_like_forward_clause(_constraint(context, observation_type))


# ── 4. Continuity carries a human sentence (never the state name) ─────────────

def _item(team_id, *, available=True, story_type='coverage_pressure', headline='H', date='2026-06-22'):
    return {
        'story_id': f'{team_id}:{date}', 'team_id': team_id, 'date': date,
        'story_available': available, 'story_type': story_type if available else None,
        'headline': headline if available else None,
    }


def test_continuity_renders_human_sentence_for_each_state():
    today = _item(1, headline='New')
    prior_same = _item(1, headline='New', date='2026-06-21')
    prior_diff_headline = _item(1, headline='Old', date='2026-06-21')
    prior_diff_type = _item(1, story_type='depth_constraint', date='2026-06-21')

    assert build_story_continuity(today, None)['sentence'] == 'This is new today.'
    assert build_story_continuity(today, prior_diff_headline)['sentence'] == \
        'This has carried over from the last read.'
    assert build_story_continuity(today, prior_same)['sentence'] == \
        'This reads the same as the last snapshot.'
    assert build_story_continuity(today, prior_diff_type)['sentence'] == \
        'The story has changed since the last read.'
    assert build_story_continuity(_item(1, available=False), prior_same)['sentence'] == \
        'This has eased since the last read.'
    # A suppressed story with no prior carries no continuity sentence.
    assert build_story_continuity(_item(1, available=False), None)['sentence'] is None


def test_continuity_sentence_never_exposes_internal_state_name():
    # The internal state tokens (e.g. "ongoing", "unchanged") must not be rendered
    # as prose; each sentence must read as a human sentence, not an enum label.
    internal_tokens = {'ongoing', 'unchanged', 'resolved', 'unavailable'}
    states = {'new', 'ongoing', 'changed', 'unchanged', 'resolved', 'unavailable'}
    for sentence in CONTINUITY_SENTENCES.values():
        if sentence is None:
            continue
        lowered = sentence.lower()
        assert sentence not in states            # not the bare state token
        assert lowered.endswith('.') and len(sentence.split()) >= 3
        assert internal_tokens.isdisjoint(lowered.replace('.', '').split())


def test_league_continuity_carries_sentence():
    feed_context = build_league_context(
        [], as_of_date='2026-06-22',
        prior_league_context={'mode': 'broadly_stable', 'as_of_date': '2026-06-21'},
    )
    cont = feed_context['continuity']
    assert cont['sentence'] in LEAGUE_CONTINUITY_SENTENCES.values()
    assert cont['sentence']


# ── 5. Governance preserved across new forward + continuity copy ──────────────

def test_forward_clause_lines_preserve_governance():
    for forms in FORWARD_CLAUSE_LINES.values():
        for form in forms:
            assert contains_denied_public_phrase(form) is False, form
            assert contains_banned_public_language(form) is False, form


def test_continuity_sentences_carry_no_banned_or_prediction_language():
    forbidden = (*BANNED_PUBLIC_LANGUAGE, *DENIED_PUBLIC_PHRASES, 'recommend', 'should', 'rank')
    sentences = [s for s in CONTINUITY_SENTENCES.values() if s]
    sentences += list(LEAGUE_CONTINUITY_SENTENCES.values())
    for sentence in sentences:
        lowered = sentence.lower()
        for term in forbidden:
            assert term not in lowered, (sentence, term)
