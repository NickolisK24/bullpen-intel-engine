"""Feed Variety Pass (V2) tests.

The coordinator de-duplicates high-visibility phrasing (headline / opener /
lesson) across the assembled feed using approved voice-library alternates only:
deterministic, fact-preserving, guardrail-clean, and conservative (it never
touches a name-bearing line and never invents copy). Same-beat stories may still
share structure once the approved alternatives run out.
"""

import copy

from services.story_voice_library_v1 import (
    BANNED_PUBLIC_LANGUAGE,
    DENIED_PUBLIC_PHRASES,
    LESSON_LINES,
    PURPOSE_LESSON,
    PURPOSE_OPENING,
    PURPOSE_SURFACE,
    SURFACE_FRAMING_LINES,
    approved_sentence_forms,
)
from services.story_writer_v1 import BANNED_TERMS, ROBOTIC_TERMS
from services.story_four_beat_interpreter_v1 import PUBLIC_BANNED_TERMS
from services.story_audit_preview_v1 import INTERNAL_TERMS
from services.editorial_review_v1 import (
    BLAME_PHRASES,
    CERTAINTY_PHRASES,
    DRAMA_PHRASES,
    MULTI_IDEA_PHRASES,
    PREDICTION_PHRASES,
    RECAP_PHRASES,
    STATUS_PASS,
    review_story,
)
from services.story_intelligence_service_v1 import build_team_story
from services.story_feed import build_canonical_story_feed
from services.story_blueprint_v1 import SECTION_ORDER
from services import story_feed_variety_v1 as fv
from services.story_feed_variety_v1 import (
    CAPABILITY,
    SLOT_SAW,
    SLOT_WHY,
    apply_feed_variety,
    feed_variety_report,
)

ALL_GUARDRAIL_LISTS = (
    BANNED_TERMS, ROBOTIC_TERMS, PUBLIC_BANNED_TERMS, BANNED_PUBLIC_LANGUAGE,
    DENIED_PUBLIC_PHRASES, INTERNAL_TERMS, PREDICTION_PHRASES, CERTAINTY_PHRASES,
    RECAP_PHRASES, BLAME_PHRASES, DRAMA_PHRASES, MULTI_IDEA_PHRASES,
)


def _item(story_id, beat, headline, saw, why, *, evidence='The facts stay put.'):
    team = f'Team {story_id}'
    return {
        'story_id': story_id, 'team_id': story_id, 'team_name': team, 'team_abbreviation': 'TM',
        'story_available': True, 'story_type': beat,
        'headline': headline,
        'share_title': f'{team} bullpen: {beat}',   # team+label form, not headline-derived
        'blueprint': [
            {'key': 'what_everyone_saw', 'label': 'What everyone saw', 'text': saw, 'source': 'framing'},
            {'key': 'what_baseballos_noticed', 'label': 'x', 'text': 'BaseballOS noticed something.', 'source': 'observation'},
            {'key': 'evidence', 'label': 'Evidence', 'text': evidence, 'source': 'evidence_case'},
            {'key': 'why_it_matters', 'label': 'Why it matters', 'text': why, 'source': 'lesson'},
            {'key': 'why_it_matters_tomorrow', 'label': 'x', 'text': 'Tomorrow line.', 'source': 'constraint'},
        ],
    }


def _saw(item):
    return next(s['text'] for s in item['blueprint'] if s['key'] == SLOT_SAW)


def _why(item):
    return next(s['text'] for s in item['blueprint'] if s['key'] == SLOT_WHY)


def _evidence(item):
    return next(s['text'] for s in item['blueprint'] if s['key'] == 'evidence')


def _slotfree_openings(beat):
    return [f for f in approved_sentence_forms(beat, PURPOSE_OPENING) if '{' not in f]


# ── Determinism + immutability ────────────────────────────────────────────────

def test_same_feed_produces_identical_output():
    beat = 'coverage_pressure'
    saw0 = SURFACE_FRAMING_LINES[beat][0]
    items = [_item(i, beat, f'Headline {i}', saw0, LESSON_LINES[beat][0]) for i in range(1, 5)]
    a = apply_feed_variety(items)
    b = apply_feed_variety(items)
    assert a == b


def test_does_not_mutate_input():
    beat = 'coverage_pressure'
    items = [_item(i, beat, 'Same headline', SURFACE_FRAMING_LINES[beat][0], LESSON_LINES[beat][0]) for i in range(1, 4)]
    snapshot = copy.deepcopy(items)
    apply_feed_variety(items)
    assert items == snapshot


# ── Duplicate avoidance when alternatives exist ───────────────────────────────

def test_duplicate_opener_avoided():
    beat = 'coverage_pressure'
    saw0 = SURFACE_FRAMING_LINES[beat][0]
    items = [_item(i, beat, f'H{i}', saw0, f'L{i}') for i in range(1, 4)]
    out = apply_feed_variety(items)
    openers = [_saw(s) for s in out]
    assert len(set(openers)) == 3                         # all distinct
    assert all(o in SURFACE_FRAMING_LINES[beat] for o in openers)  # approved copy only


def test_duplicate_lesson_avoided():
    beat = 'coverage_pressure'
    why0 = LESSON_LINES[beat][0]
    items = [_item(i, beat, f'H{i}', f'S{i}', why0) for i in range(1, 4)]
    out = apply_feed_variety(items)
    lessons = [_why(s) for s in out]
    assert len(set(lessons)) == 3
    assert all(line in LESSON_LINES[beat] for line in lessons)


def test_duplicate_headline_avoided_for_generic_lines():
    beat = 'coverage_pressure'
    slotfree = _slotfree_openings(beat)
    assert len(slotfree) >= 2
    dup = slotfree[0]
    items = [_item(i, beat, dup, f'S{i}', f'L{i}') for i in range(1, 4)]
    out = apply_feed_variety(items)
    heads = [s['headline'] for s in out]
    assert len(set(heads)) == 3
    # Each headline is an approved opening rendered for that team (slot-free or
    # team-only) — never invented copy.
    for s in out:
        assert s['headline'] in fv._renderable_candidates(beat, PURPOSE_OPENING, fv._team_slots(s))


# ── Conservative behavior ─────────────────────────────────────────────────────

def test_name_bearing_headline_is_left_untouched():
    # A headline that is not an approved team-only form (it carries names) must
    # never be swapped or stripped, even on an exact collision.
    beat = 'route_change'
    named = 'Smith and Jones still shape the first call'
    items = [_item(i, beat, named, f'S{i}', f'L{i}') for i in range(1, 3)]
    out = apply_feed_variety(items)
    assert [s['headline'] for s in out] == [named, named]  # unchanged duplicate, no fabrication


def test_shares_structure_when_alternatives_exhausted():
    beat = 'coverage_pressure'
    saw0 = SURFACE_FRAMING_LINES[beat][0]
    pool = len(SURFACE_FRAMING_LINES[beat])
    items = [_item(i, beat, f'H{i}', saw0, f'L{i}') for i in range(1, pool + 3)]
    out = apply_feed_variety(items)
    openers = [_saw(s) for s in out]
    assert len(set(openers)) == pool                      # used every approved alternative
    assert len(openers) > pool                            # and some necessarily repeat


# ── Facts are never changed ───────────────────────────────────────────────────

def test_evidence_and_facts_are_never_changed():
    beat = 'coverage_pressure'
    saw0 = SURFACE_FRAMING_LINES[beat][0]
    items = [_item(i, beat, 'Same headline text here', saw0, LESSON_LINES[beat][0],
                   evidence=f'The bullpen covered {i} innings.') for i in range(1, 4)]
    out = apply_feed_variety(items)
    for original, varied in zip(items, out):
        assert _evidence(varied) == _evidence(original)   # the case (facts) is untouched
        assert varied['story_type'] == original['story_type']


# ── Guardrails + editorial review ─────────────────────────────────────────────

def test_varied_lines_clear_guardrails():
    beat = 'coverage_pressure'
    saw0 = SURFACE_FRAMING_LINES[beat][0]
    items = [_item(i, beat, _slotfree_openings(beat)[0], saw0, LESSON_LINES[beat][0]) for i in range(1, 6)]
    out = apply_feed_variety(items)
    texts = [s['headline'] for s in out] + [_saw(s) for s in out] + [_why(s) for s in out]
    for text in texts:
        low = text.lower()
        for terms in ALL_GUARDRAIL_LISTS:
            for term in terms:
                term = (term or '').lower()
                assert not (term and term in low), (term, text)


# ── Integration with the real pipeline ────────────────────────────────────────

def _calm(tid, name, abbr):
    return {
        'team_id': tid, 'team': {'team_id': tid, 'team_name': name, 'team_abbreviation': abbr},
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
                           'inactive_bullpen_arms_count': 0, 'il_bullpen_arms_count': 0, 'non_il_inactive_bullpen_arms_count': 0,
                           'inactive_bullpen_share': 0.0, 'injury_context_confidence': 'high', 'inactive_bullpen_arms': []},
        'limitations': [],
    }


def _coverage_feed():
    specs = [(501, 'Detroit Tigers', 'DET', 4.4, 66.0), (502, 'Seattle Mariners', 'SEA', 5.0, 46.0),
             (503, 'Miami Marlins', 'MIA', 4.3, 64.0), (504, 'Texas Rangers', 'TEX', 4.7, 52.0),
             (505, 'Chicago Cubs', 'CHC', 4.6, 58.0)]
    ctxs = {}
    teams = []
    for tid, name, abbr, avg7, early in specs:
        c = _calm(tid, name, abbr)
        c['rotation_context'].update({'rotation_avg_ip_7d': avg7, 'rotation_avg_ip_14d': 5.7, 'rotation_ip_trend': -1.1,
                                      'early_bullpen_entry_rate': early, 'bullpen_coverage_ip_7d': 4.5})
        ctxs[tid] = c
        teams.append({'team_id': tid, 'team_name': name, 'team_abbreviation': abbr})
    builder = lambda tid, as_of_date=None: build_team_story(tid, as_of_date=as_of_date, team_context=ctxs[tid])
    return build_canonical_story_feed(teams, as_of_date='2026-06-20', story_builder=builder)


def test_real_feed_diversifies_same_beat_cards():
    feed = _coverage_feed()
    available = [s for s in feed['items'] if s['story_available']]
    assert len(available) == 5
    assert len({s['headline'] for s in available}) == 5
    assert len({_saw(s) for s in available}) == 5
    assert len({_why(s) for s in available}) == 5


def test_real_feed_is_deterministic():
    a = _coverage_feed()
    b = _coverage_feed()
    a_items = [(s['headline'], _saw(s), _why(s), _evidence(s)) for s in a['items'] if s['story_available']]
    b_items = [(s['headline'], _saw(s), _why(s), _evidence(s)) for s in b['items'] if s['story_available']]
    assert a_items == b_items


def test_real_feed_still_passes_editorial_review_and_keeps_contract():
    feed = _coverage_feed()
    for story in feed['items']:
        if not story['story_available']:
            continue
        assert [s['key'] for s in story['blueprint']] == list(SECTION_ORDER)
        report = review_story(story)
        assert report['status'] == STATUS_PASS, report['warnings']


def test_report():
    report = feed_variety_report()
    assert report['capability'] == CAPABILITY
    assert report['deterministic'] is True
    assert report['changes_facts'] is False
