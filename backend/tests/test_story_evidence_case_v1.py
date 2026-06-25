"""Evidence Case (V2) tests.

The Evidence section must read as a short BUILT CASE rather than a concatenated
list: at most three sentences, strongest support first, no repeated fact, no tiny
delta dressed up as evidence, correct singular/plural grammar, consistent player
names across the story, and no prediction / blame / drama / internal / banned
language. The change is additive and deterministic, and existing stories still
pass Editorial Review.
"""

import copy

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
from services.story_writer_v1 import BANNED_TERMS, ROBOTIC_TERMS
from services.story_four_beat_interpreter_v1 import PUBLIC_BANNED_TERMS
from services.story_voice_library_v1 import BANNED_PUBLIC_LANGUAGE, DENIED_PUBLIC_PHRASES
from services.story_audit_preview_v1 import INTERNAL_TERMS
from services.editorial_review_v1 import (
    BLAME_PHRASES,
    CERTAINTY_PHRASES,
    DRAMA_PHRASES,
    INTERNAL_PHRASES,
    MULTI_IDEA_PHRASES,
    PREDICTION_PHRASES,
    RECAP_PHRASES,
    STATUS_PASS,
    review_story,
)
from services.story_intelligence_service_v1 import build_team_story
from services.story_feed import canonical_story_from_service_payload
from services.story_blueprint_v1 import SECTION_EVIDENCE, SECTION_ORDER, build_story_blueprint
from services.story_evidence_case_v1 import (
    CAPABILITY,
    MAX_SENTENCES,
    SUPPORTED_OBSERVATION_TYPES,
    build_evidence_case,
    evidence_case_report,
)

ALL_GUARDRAIL_LISTS = (
    BANNED_TERMS, ROBOTIC_TERMS, PUBLIC_BANNED_TERMS, BANNED_PUBLIC_LANGUAGE,
    DENIED_PUBLIC_PHRASES, INTERNAL_TERMS, PREDICTION_PHRASES, CERTAINTY_PHRASES,
    RECAP_PHRASES, BLAME_PHRASES, DRAMA_PHRASES, MULTI_IDEA_PHRASES, INTERNAL_PHRASES,
)


def _frame(observation_type, **sections):
    return {
        'team_id': 1, 'team_name': 'Test Club', 'team_abbreviation': 'TST',
        'observation_type': observation_type,
        'story_frame': sections,
    }


def _sentences(text):
    return [s for s in text.replace('!', '.').replace('?', '.').split('. ') if s.strip()]


# ── Curated case shape ────────────────────────────────────────────────────────

def test_evidence_is_a_short_single_paragraph_case():
    frame = _frame(
        TYPE_DEPTH_PRESSURE,
        observation_facts={'inactive_bullpen_arms_count': 4},
        baseline_facts={'active_bullpen_arms_count': 5},
        cause_facts={'il_bullpen_arms_count': 3},
    )
    text = build_evidence_case(frame)
    assert text  # built a case
    assert '\n' not in text  # single paragraph, not a stitched two-paragraph dump
    assert len(_sentences(text)) <= MAX_SENTENCES
    # Matches the desired editorial direction.
    assert '4 arms are outside the current plan, 3 of them on the IL.' in text
    assert 'roster looking deeper than the group the manager can actually use' in text


def test_unsupported_or_factless_frame_returns_empty():
    assert build_evidence_case({}) == ''
    assert build_evidence_case({'observation_type': 'nope', 'story_frame': {}}) == ''
    # Supported type but no facts -> only the generic meaning line (still a case),
    # never a crash.
    text = build_evidence_case(_frame(TYPE_DEPTH_PRESSURE))
    assert isinstance(text, str)


# ── No repeated fact ──────────────────────────────────────────────────────────

def test_no_repeated_fact():
    # Thin rotation frame: one starts figure, no early-entry, no coverage. The old
    # path repeated the 4.5 figure ("averaging 4.5" then "handoff is 4.5"); the
    # case states it once.
    frame = _frame(
        TYPE_ROTATION_PRESSURE,
        observation_facts={'rotation_avg_ip_7d': 4.5},
        cause_facts={},
    )
    text = build_evidence_case(frame)
    assert text.count('4.5') == 1
    sents = _sentences(text)
    assert len(sents) == len({s.strip().lower() for s in sents})  # no duplicate sentence


# ── Tiny deltas are omitted (prefer under-claiming) ───────────────────────────

def test_tiny_rotation_delta_is_omitted():
    # avg14 - avg7 = 0.1 (below threshold): no "shortened ... from" movement claim.
    frame = _frame(
        TYPE_ROTATION_PRESSURE,
        observation_facts={'rotation_avg_ip_7d': 5.5, 'rotation_avg_ip_14d': 5.6,
                           'early_bullpen_entry_rate': 45.0},
        cause_facts={'bullpen_coverage_ip_7d': 4.0},
    )
    text = build_evidence_case(frame)
    assert 'shortened' not in text
    assert 'from 5.6' not in text


def test_meaningful_rotation_delta_is_kept():
    frame = _frame(
        TYPE_ROTATION_PRESSURE,
        observation_facts={'rotation_avg_ip_7d': 4.4, 'rotation_avg_ip_14d': 5.6,
                           'early_bullpen_entry_rate': 66.0},
        cause_facts={'bullpen_coverage_ip_7d': 4.7},
    )
    text = build_evidence_case(frame)
    assert 'shortened to 4.4 innings from 5.6' in text


def test_tiny_concentration_delta_is_omitted():
    frame = _frame(
        TYPE_CONCENTRATION_PRESSURE,
        headline_facts={'top_three_relievers': ['A', 'B', 'C'], 'top_three_workload_share_10d': 74.0},
        baseline_facts={'top_three_share_delta_vs_league': 1.0},  # below 2.0
    )
    text = build_evidence_case(frame)
    assert 'points above' not in text


# ── Singular / plural grammar ─────────────────────────────────────────────────

def test_singular_plural_route_change():
    one = build_evidence_case(_frame(
        TYPE_CORE_TRANSITION,
        headline_facts={'current_operational_core': ['Bednar', 'Holderman', 'Stratton']},
        baseline_facts={'previous_operational_core': ['Bednar', 'Holderman', 'Hernandez']},
        cause_facts={'new_core_members': ['Stratton'], 'departed_core_members': ['Hernandez']},
    ))
    assert 'added Stratton' in one
    assert 'moved on from Hernandez' in one
    assert 'added arms are' not in one  # the old robotic seam is gone


def test_singular_plural_depth_and_trust():
    depth_one = build_evidence_case(_frame(
        TYPE_DEPTH_PRESSURE,
        observation_facts={'inactive_bullpen_arms_count': 1},
        cause_facts={'il_bullpen_arms_count': 1},
        baseline_facts={'active_bullpen_arms_count': 7},
    ))
    assert '1 arm is outside the current plan' in depth_one

    trust_one = build_evidence_case(_frame(
        TYPE_TRUST_LANE_PRESSURE,
        observation_facts={'available_arms_count': 6, 'clean_workload_options_count': 1},
        cause_facts={'clean_workload_options': [{'name': 'Leclerc'}]},
    ))
    assert 'only 1 is clean and rested' in trust_one
    trust_two = build_evidence_case(_frame(
        TYPE_TRUST_LANE_PRESSURE,
        observation_facts={'available_arms_count': 5, 'clean_workload_options_count': 2},
        cause_facts={'clean_workload_options': [{'name': 'Hader'}, {'name': 'Pressly'}]},
    ))
    assert 'only 2 are clean and rested' in trust_two


# ── No banned / unsupported language in any generated case ────────────────────

def test_all_generated_evidence_clears_guardrails():
    frames = [
        _frame(TYPE_ROTATION_PRESSURE,
               observation_facts={'rotation_avg_ip_7d': 4.4, 'rotation_avg_ip_14d': 5.6, 'early_bullpen_entry_rate': 66.0},
               cause_facts={'bullpen_coverage_ip_7d': 4.7}),
        _frame(TYPE_CONCENTRATION_PRESSURE,
               headline_facts={'top_three_relievers': ['Clase', 'Smith', 'Sandlin'], 'top_three_workload_share_10d': 76.0},
               baseline_facts={'top_three_share_delta_vs_league': 18.0}),
        _frame(TYPE_OPTIONALITY_STRENGTH,
               observation_facts={'practical_close_game_paths_count': 6, 'clean_workload_options_count': 6},
               cause_facts={'clean_workload_options': [{'name': 'Phillips'}, {'name': 'Vesia'}]}),
        _frame(TYPE_STABLE_CORE,
               headline_facts={'current_operational_core': ['A', 'B', 'C'], 'core_stability_pct': 92},
               baseline_facts={'previous_operational_core': ['A', 'B', 'C']}),
        _frame(TYPE_CORE_TRANSITION,
               headline_facts={'current_operational_core': ['Banks', 'Crochet', 'Fedde']},
               baseline_facts={'previous_operational_core': ['Bummer', 'Kopech', 'Graveman']},
               cause_facts={'new_core_members': ['Banks', 'Fedde'], 'departed_core_members': ['Bummer', 'Kopech']}),
        _frame(TYPE_DEPTH_PRESSURE,
               observation_facts={'inactive_bullpen_arms_count': 4},
               cause_facts={'il_bullpen_arms_count': 3}, baseline_facts={'active_bullpen_arms_count': 5}),
        _frame(TYPE_TRUST_LANE_PRESSURE,
               observation_facts={'available_arms_count': 6, 'clean_workload_options_count': 1},
               cause_facts={'clean_workload_options': [{'name': 'Leclerc'}]}),
        _frame(TYPE_BRIDGE_INSTABILITY,
               headline_facts={'current_operational_core': ['A', 'B', 'C'], 'volatile_middle_count': 4},
               observation_facts={'volatile_middle_count': 4, 'early_bullpen_entry_rate': 55.0, 'bullpen_coverage_ip_7d': 4.2}),
    ]
    assert {f['observation_type'] for f in frames} == set(SUPPORTED_OBSERVATION_TYPES)
    for frame in frames:
        text = build_evidence_case(frame).lower()
        assert text
        for terms in ALL_GUARDRAIL_LISTS:
            for term in terms:
                term = (term or '').lower()
                assert not (term and term in text), (frame['observation_type'], term, text)


# ── Determinism + immutability ────────────────────────────────────────────────

def test_evidence_case_is_deterministic_and_pure():
    frame = _frame(
        TYPE_CONCENTRATION_PRESSURE,
        headline_facts={'top_three_relievers': ['Clase', 'Smith', 'Sandlin'], 'top_three_workload_share_10d': 76.0},
        baseline_facts={'top_three_share_delta_vs_league': 18.0},
    )
    snapshot = copy.deepcopy(frame)
    assert build_evidence_case(frame) == build_evidence_case(frame)
    assert frame == snapshot  # never mutates the frame


# ── Integration with the real pipeline ────────────────────────────────────────

def _calm_context(team_id, name, abbr):
    return {
        'team_id': team_id, 'team': {'team_id': team_id, 'team_name': name, 'team_abbreviation': abbr},
        'reference_date': '2026-06-20', 'data_through_date': '2026-06-20',
        'rotation_context': {'context_available': True, 'rotation_avg_ip_7d': 5.8, 'rotation_avg_ip_14d': 5.8,
                             'rotation_ip_trend': -0.1, 'early_bullpen_entry_rate': 12.0, 'bullpen_coverage_ip_7d': 3.0,
                             'rotation_games_analyzed_7d': 6, 'rotation_games_analyzed_14d': 12},
        'bullpen_concentration_context': {'context_available': True, 'concentration_band': 'normal',
                                          'top_three_workload_share_10d': 58.0, 'league_top_three_workload_share_10d': 58.0,
                                          'top_three_share_delta_vs_league': 0.0, 'bullpen_workload_total_10d': 180,
                                          'top_three_relievers_10d': [{'name': 'Al'}, {'name': 'Bo'}, {'name': 'Cy'}],
                                          'league_team_count_10d': 30},
        'bullpen_optionality_context': {'context_available': True, 'optionality_band': 'narrow',
                                        'practical_close_game_paths_count': 3, 'available_arms_count': 3,
                                        'monitor_arms_count': 1, 'restricted_arms_count': 1, 'limited_arms_count': 1,
                                        'clean_workload_options': [{'name': 'Al'}], 'secondary_options': [{'name': 'Dy'}]},
        'role_stability_context': {'context_available': True, 'stability_band': 'mostly_stable',
                                   'current_operational_core': ['Al', 'Bo', 'Cy'], 'previous_operational_core': ['Al', 'Bo', 'Cy'],
                                   'core_retention_count': 3, 'core_stability_pct': 80, 'core_change_count': 0,
                                   'current_core_size': 3, 'previous_core_size': 3},
        'injury_context': {'context_available': True, 'depth_pressure_band': 'light', 'active_bullpen_arms_count': 8,
                           'inactive_bullpen_arms_count': 0, 'il_bullpen_arms_count': 0,
                           'non_il_inactive_bullpen_arms_count': 0, 'inactive_bullpen_share': 0.0,
                           'injury_context_confidence': 'high', 'inactive_bullpen_arms': []},
        'limitations': [],
    }


def _canonical_for(context):
    payload = build_team_story(context['team_id'], as_of_date='2026-06-20', team_context=context)
    return payload, canonical_story_from_service_payload(payload, date='2026-06-20')


def test_real_story_evidence_section_uses_the_case_builder():
    ctx = _calm_context(301, 'New York Yankees', 'NYY')
    ctx['injury_context'].update({'depth_pressure_band': 'heavy', 'active_bullpen_arms_count': 5,
                                  'inactive_bullpen_arms_count': 4, 'il_bullpen_arms_count': 3,
                                  'non_il_inactive_bullpen_arms_count': 1, 'inactive_bullpen_share': 36.0,
                                  'inactive_bullpen_arms': [{'name': n} for n in ['Holmes', 'Kahnle', 'Hamilton', 'Cousins']]})
    _, canon = _canonical_for(ctx)
    evidence = next(s for s in canon['blueprint'] if s['key'] == SECTION_EVIDENCE)
    assert evidence['source'] == 'evidence_case'
    assert '\n' not in evidence['text']
    assert 'on the IL' in evidence['text']
    # The old robotic itemizing is gone.
    assert 'It also includes' not in evidence['text']


def test_name_consistency_concentration_across_sections():
    # Workload trio differs from the operational core; the story must reference one
    # group across noticed / evidence / tomorrow, not two.
    ctx = _calm_context(302, 'Cleveland Guardians', 'CLE')
    ctx['bullpen_concentration_context'].update({
        'concentration_band': 'narrow', 'top_three_workload_share_10d': 76.0,
        'top_three_share_delta_vs_league': 18.0,
        'top_three_relievers_10d': [{'name': 'Clase'}, {'name': 'Smith'}, {'name': 'Sandlin'}],
    })
    # operational core is a DIFFERENT trio.
    ctx['role_stability_context'].update({'current_operational_core': ['Alvarez', 'Boone', 'Cruz']})
    _, canon = _canonical_for(ctx)
    sections = {s['key']: s['text'] for s in canon['blueprint']}
    evidence = sections[SECTION_EVIDENCE]
    tomorrow = sections['why_it_matters_tomorrow']
    noticed = sections['what_baseballos_noticed']
    for trio_text in (noticed, evidence, tomorrow):
        assert 'Clase' in trio_text
        # The other group must not bleed into the same-idea sections.
        assert 'Alvarez' not in trio_text and 'Boone' not in trio_text and 'Cruz' not in trio_text


def test_real_stories_still_pass_editorial_review_and_keep_blueprint_shape():
    cases = [
        ('rotation', lambda c: c['rotation_context'].update(
            {'rotation_avg_ip_7d': 4.4, 'rotation_ip_trend': -1.3, 'early_bullpen_entry_rate': 66.0, 'bullpen_coverage_ip_7d': 4.7})),
        ('trust', lambda c: c['bullpen_optionality_context'].update(
            {'available_arms_count': 6, 'monitor_arms_count': 3, 'limited_arms_count': 2,
             'clean_workload_options': [{'name': 'Leclerc'}],
             'secondary_options': [{'name': n} for n in ['Y', 'S', 'B', 'W', 'R']]})),
        ('bridge', lambda c: (c['role_stability_context'].update({'stability_band': 'stable', 'core_stability_pct': 90}),
                              c['bullpen_optionality_context'].update(
                                  {'available_arms_count': 3, 'monitor_arms_count': 2, 'limited_arms_count': 2,
                                   'clean_workload_options': [], 'secondary_options': [{'name': 'C'}, {'name': 'B'}]}),
                              c['rotation_context'].update({'early_bullpen_entry_rate': 55.0, 'bullpen_coverage_ip_7d': 4.2}))),
    ]
    for i, (label, mutate) in enumerate(cases):
        ctx = _calm_context(310 + i, f'Team {label}', f'T{i}')
        mutate(ctx)
        payload, canon = _canonical_for(ctx)
        assert canon['story_available'] is True, label
        assert [s['key'] for s in canon['blueprint']] == list(SECTION_ORDER), label
        report = review_story(canon)
        assert report['status'] == STATUS_PASS, (label, report['warnings'])


def test_real_pipeline_is_deterministic_with_case_builder():
    ctx = _calm_context(320, 'Texas Rangers', 'TEX')
    ctx['bullpen_optionality_context'].update(
        {'available_arms_count': 6, 'monitor_arms_count': 3, 'limited_arms_count': 2,
         'clean_workload_options': [{'name': 'Leclerc'}],
         'secondary_options': [{'name': n} for n in ['Y', 'S', 'B', 'W', 'R']]})
    _, a = _canonical_for(copy.deepcopy(ctx))
    _, b = _canonical_for(copy.deepcopy(ctx))
    assert a['blueprint'] == b['blueprint']


def test_blueprint_without_frame_falls_back_to_beats():
    # Backward-compatible: no frame -> Evidence reuses the baseline + cause beats.
    beats = [
        {'key': 'observation', 'label': 'x', 'text': 'The bullpen entered early.'},
        {'key': 'baseline', 'label': 'x', 'text': 'That is earlier than usual.'},
        {'key': 'cause', 'label': 'x', 'text': 'The starters are not going deep.'},
        {'key': 'constraint', 'label': 'x', 'text': 'More innings land on the bullpen.'},
    ]
    bp = {s['key']: s for s in build_story_blueprint(story_type='coverage_pressure', beats=beats, stable_parts=('x',))}
    assert bp[SECTION_EVIDENCE]['source'] == 'evidence'
    assert 'That is earlier than usual.' in bp[SECTION_EVIDENCE]['text']


def test_report():
    report = evidence_case_report()
    assert report['capability'] == CAPABILITY
    assert report['deterministic'] is True
    assert set(report['supported_observation_types']) == set(SUPPORTED_OBSERVATION_TYPES)
