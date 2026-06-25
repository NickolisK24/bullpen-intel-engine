"""Evidence Body Variety Pass (V2) tests.

Reduce cross-story repetition inside the Evidence section without changing facts:
  - fact-identical LEAD phrasings diversify same-beat leads (per-story choice);
  - the fact-free MEANING sentence is de-duplicated across the feed by the
    coordinator (guaranteed distinct up to bank size).

Numbers, names, claims, severity, and the canonical contract are all preserved;
output stays deterministic and Editorial Review still passes.
"""

import copy
import re

from services.story_observation_engine import (
    TYPE_BRIDGE_INSTABILITY,
    TYPE_DEPTH_PRESSURE,
    TYPE_ROTATION_PRESSURE,
    TYPE_TRUST_LANE_PRESSURE,
)
from services.story_evidence_case_v1 import (
    MAX_SENTENCES,
    MEANING_VARIANTS,
    build_evidence_case,
    evidence_case_report,
)
from services.story_intelligence_service_v1 import build_team_story
from services.story_feed import build_canonical_story_feed, canonical_story_from_service_payload
from services.story_blueprint_v1 import SECTION_ORDER
from services.editorial_review_v1 import STATUS_PASS, review_story

DATE = '2026-06-20'
_ALL_MEANINGS = {m for bank in MEANING_VARIANTS.values() for m in bank}


def _frame(observation_type, **sections):
    return {'team_id': 1, 'team_name': 'Test', 'team_abbreviation': 'T',
            'observation_type': observation_type, 'story_frame': sections}


def _cov_frame():
    return _frame(TYPE_ROTATION_PRESSURE,
                  observation_facts={'rotation_avg_ip_7d': 4.4, 'rotation_avg_ip_14d': 5.6, 'early_bullpen_entry_rate': 66.0},
                  cause_facts={'bullpen_coverage_ip_7d': 4.7})


def _trust_frame():
    return _frame(TYPE_TRUST_LANE_PRESSURE,
                  observation_facts={'available_arms_count': 6, 'clean_workload_options_count': 1, 'secondary_options_count': 5},
                  cause_facts={'clean_workload_options': [{'name': 'Leclerc'}]})


def _nums(text):
    return sorted(re.findall(r'\d+(?:\.\d+)?', text))


def _lead(text):
    return text.split('. ')[0].strip().rstrip('.')


def _evidence(story):
    return next((s['text'] for s in story.get('blueprint', []) if s['key'] == 'evidence'), '')


def _noticed(story):
    return next((s['text'] for s in story.get('blueprint', []) if s['key'] == 'what_baseballos_noticed'), '')


def _meaning_of(text):
    for sent in [p.strip().rstrip('.') for p in text.split('. ') if p.strip()]:
        if sent in _ALL_MEANINGS:
            return sent
    return ''


# ── Lead + meaning variants engage ────────────────────────────────────────────

def test_evidence_lead_diversifies_across_keys():
    leads = {_lead(build_evidence_case(_cov_frame(), variety_key=(f'{i}:d',))) for i in range(25)}
    assert len(leads) >= 2                          # the lead has alternatives and they are used


def test_evidence_meaning_diversifies_across_keys():
    meanings = {_meaning_of(build_evidence_case(_cov_frame(), variety_key=(f'{i}:d',))) for i in range(25)}
    assert len(meanings) >= 3


def test_no_variety_key_is_canonical_variant():
    # Backward-compatible: variant 0 (canonical) when no key is supplied.
    text = build_evidence_case(_cov_frame())
    assert text.startswith('The bullpen has been entering before the sixth in 66% of recent games')
    assert _meaning_of(text) == MEANING_VARIANTS[TYPE_ROTATION_PRESSURE][0]


# ── Facts / numbers / names never change ──────────────────────────────────────

def test_numbers_unchanged_across_lead_and_meaning_variants():
    base = _nums(build_evidence_case(_cov_frame(), variety_key=('0:d',)))
    for i in range(25):
        assert _nums(build_evidence_case(_cov_frame(), variety_key=(f'{i}:d',))) == base


def test_names_and_numbers_unchanged_for_trust():
    base = build_evidence_case(_trust_frame(), variety_key=('0:d',))
    base_nums = _nums(base)
    for i in range(25):
        text = build_evidence_case(_trust_frame(), variety_key=(f'{i}:d',))
        assert 'Leclerc' in text                    # the named arm is always present
        assert _nums(text) == base_nums             # the secondary count never changes


def test_evidence_stays_within_three_sentences():
    for i in range(15):
        for frame in (_cov_frame(), _trust_frame()):
            text = build_evidence_case(frame, variety_key=(f'{i}:d',))
            assert len([p for p in text.split('. ') if p.strip()]) <= MAX_SENTENCES


# ── Feed-level meaning de-duplication ─────────────────────────────────────────

def _calm(tid, name, abbr):
    return {
        'team_id': tid, 'team': {'team_id': tid, 'team_name': name, 'team_abbreviation': abbr},
        'reference_date': DATE, 'data_through_date': DATE,
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


def _coverage_cluster():
    specs = [(801, 'Detroit', 'DET', 4.4, 66.0), (802, 'Seattle', 'SEA', 5.0, 46.0),
             (803, 'Miami', 'MIA', 4.3, 64.0), (804, 'Chicago', 'CHC', 4.7, 52.0),
             (805, 'Toronto', 'TOR', 4.6, 58.0)]
    ctxs, teams = {}, []
    for tid, name, abbr, avg7, early in specs:
        c = _calm(tid, name, abbr)
        c['rotation_context'].update({'rotation_avg_ip_7d': avg7, 'rotation_avg_ip_14d': 5.7, 'rotation_ip_trend': -1.1,
                                      'early_bullpen_entry_rate': early, 'bullpen_coverage_ip_7d': 4.5})
        ctxs[tid] = c
        teams.append({'team_id': tid, 'team_name': name, 'team_abbreviation': abbr})
    builder = lambda tid, as_of_date=None: build_team_story(tid, as_of_date=as_of_date, team_context=ctxs[tid])
    return teams, ctxs, builder


def test_feed_dedups_evidence_meanings_across_a_cluster():
    teams, ctxs, builder = _coverage_cluster()
    # Without the coordinator (each story built independently) meanings collide.
    raw = [canonical_story_from_service_payload(builder(t['team_id']), team=t, date=DATE) for t in teams]
    raw_distinct = len({_meaning_of(_evidence(s)) for s in raw})
    # With the coordinator, the feed assembles distinct meanings (bank is 5 deep).
    feed = build_canonical_story_feed(teams, as_of_date=DATE, story_builder=builder)
    av = [s for s in feed['items'] if s['story_available']]
    feed_distinct = len({_meaning_of(_evidence(s)) for s in av})
    assert len(av) == 5
    assert feed_distinct == 5
    assert feed_distinct >= raw_distinct          # the coordinator only ever improves diversity


def test_feed_evidence_meaning_dedup_preserves_facts():
    teams, ctxs, builder = _coverage_cluster()
    feed = build_canonical_story_feed(teams, as_of_date=DATE, story_builder=builder)
    for s in (x for x in feed['items'] if x['story_available']):
        # The meaning sentence carries no numbers; the facts live in the lead/
        # corroborating sentences and must survive the swap.
        evidence = _evidence(s)
        assert _meaning_of(evidence) in _ALL_MEANINGS
        assert _nums(evidence)                     # the case still carries its numbers


# ── Regression: determinism, no-noticed-repeat, review, feed variety, contract ─

def test_same_feed_produces_identical_output():
    teams, ctxs, builder = _coverage_cluster()
    a = build_canonical_story_feed(teams, as_of_date=DATE, story_builder=builder)
    b = build_canonical_story_feed(teams, as_of_date=DATE, story_builder=builder)
    a_ev = [_evidence(s) for s in a['items'] if s['story_available']]
    b_ev = [_evidence(s) for s in b['items'] if s['story_available']]
    assert a_ev == b_ev


def test_feed_variety_headline_opener_lesson_still_distinct():
    teams, ctxs, builder = _coverage_cluster()
    av = [s for s in build_canonical_story_feed(teams, as_of_date=DATE, story_builder=builder)['items'] if s['story_available']]
    assert len({s['headline'] for s in av}) == 5
    assert len({next(x['text'] for x in s['blueprint'] if x['key'] == 'what_everyone_saw') for s in av}) == 5
    assert len({next(x['text'] for x in s['blueprint'] if x['key'] == 'why_it_matters') for s in av}) == 5


def test_evidence_still_does_not_repeat_noticed():
    # Coherence-pass guarantee holds after variety: trust + bridge leads differ
    # from their noticed lead.
    trust_ctx = _calm(810, 'Texas', 'TEX')
    trust_ctx['bullpen_optionality_context'].update(
        {'available_arms_count': 6, 'monitor_arms_count': 3, 'limited_arms_count': 2,
         'clean_workload_options': [{'name': 'Leclerc'}],
         'secondary_options': [{'name': n} for n in ('Y', 'S', 'B', 'W', 'R')]})
    bridge_ctx = _calm(811, 'Baltimore', 'BAL')
    bridge_ctx['rotation_context'].update({'early_bullpen_entry_rate': 55.0, 'bullpen_coverage_ip_7d': 4.2})
    bridge_ctx['role_stability_context'].update({'stability_band': 'stable', 'core_stability_pct': 90})
    bridge_ctx['bullpen_optionality_context'].update(
        {'available_arms_count': 3, 'monitor_arms_count': 2, 'limited_arms_count': 2,
         'clean_workload_options': [], 'secondary_options': [{'name': 'C'}, {'name': 'B'}]})
    for ctx in (trust_ctx, bridge_ctx):
        story = canonical_story_from_service_payload(
            build_team_story(ctx['team_id'], as_of_date=DATE, team_context=ctx), date=DATE)
        assert _lead(_evidence(story)) != _lead(_noticed(story))


def test_feed_still_passes_editorial_review_and_contract():
    teams, ctxs, builder = _coverage_cluster()
    for s in (x for x in build_canonical_story_feed(teams, as_of_date=DATE, story_builder=builder)['items'] if x['story_available']):
        assert [b['key'] for b in s['blueprint']] == list(SECTION_ORDER)
        report = review_story(s)
        assert report['status'] == STATUS_PASS, report['warnings']


def test_build_evidence_case_does_not_mutate_frame():
    frame = _cov_frame()
    snapshot = copy.deepcopy(frame)
    build_evidence_case(frame, variety_key=('7:d',))
    assert frame == snapshot


def test_report_exposes_lead_and_meaning_variants():
    report = evidence_case_report()
    assert report['lead_variant_slots']
    assert all(count >= 2 for count in report['lead_variant_slots'].values())
    assert report['meaning_variant_counts'][TYPE_ROTATION_PRESSURE] >= 5
