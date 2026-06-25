"""Blueprint Coherence Pass (V2) tests.

Three intra-story fixes from the Post-Variety Calibration:
  1. Evidence no longer restates the "What BaseballOS noticed" lead (trust_lane,
     bridge, stable-core / availability) — it supports the insight from a
     different angle.
  2. depth_constraint headlines never feature inactive / IL arms as the group a
     long game "gets back to."
  3. "Why it matters tomorrow" carry lines are reader-facing: one clean clause,
     no six-name pileups, no prediction language.

All while preserving facts, the feed variety pass, Editorial Review, determinism,
and the canonical feed contract.
"""

import copy

from services.story_intelligence_service_v1 import build_team_story
from services.story_feed import build_canonical_story_feed, canonical_story_from_service_payload
from services.story_blueprint_v1 import SECTION_ORDER
from services.editorial_review_v1 import (
    PREDICTION_PHRASES,
    STATUS_PASS,
    review_story,
)
from services.story_voice_library_v1 import (
    BANNED_PUBLIC_LANGUAGE,
    DENIED_PUBLIC_PHRASES,
)
from services.story_writer_v1 import BANNED_TERMS, ROBOTIC_TERMS
from services.story_four_beat_interpreter_v1 import PUBLIC_BANNED_TERMS
from services.story_audit_preview_v1 import INTERNAL_TERMS

DATE = '2026-06-20'


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


def _nm(*xs):
    return [{'name': x} for x in xs]


def _canon(ctx):
    payload = build_team_story(ctx['team_id'], as_of_date=DATE, team_context=ctx)
    return canonical_story_from_service_payload(payload, date=DATE)


def _sect(story, key):
    return next((s['text'] for s in story.get('blueprint', []) if s['key'] == key), '')


def _first_sentence(text):
    return text.split('. ')[0].strip().rstrip('.').lower()


def _content_words(text):
    return {w for w in ''.join(c if c.isalnum() else ' ' for c in text.lower()).split() if len(w) >= 4}


def _overlap(a, b):
    wa, wb = _content_words(a), _content_words(b)
    return len(wa & wb) / len(wa | wb) if (wa and wb) else 0.0


# Context builders for each beat under test ────────────────────────────────────

def _trust_ctx(tid=701, name='Texas Rangers', abbr='TEX'):
    c = _calm(tid, name, abbr)
    c['bullpen_optionality_context'].update(
        {'available_arms_count': 6, 'practical_close_game_paths_count': 4, 'monitor_arms_count': 3, 'limited_arms_count': 2,
         'clean_workload_options': _nm('Leclerc'), 'secondary_options': _nm('Yates', 'Sborz', 'Burke', 'Winn', 'Robertson')})
    return c


def _bridge_ctx(tid=702, name='Baltimore Orioles', abbr='BAL'):
    c = _calm(tid, name, abbr)
    c['rotation_context'].update({'early_bullpen_entry_rate': 55.0, 'bullpen_coverage_ip_7d': 4.2, 'rotation_ip_trend': -0.3})
    c['role_stability_context'].update({'stability_band': 'stable', 'core_stability_pct': 90, 'core_retention_count': 3})
    c['bullpen_optionality_context'].update(
        {'available_arms_count': 3, 'monitor_arms_count': 2, 'limited_arms_count': 2,
         'clean_workload_options': [], 'secondary_options': _nm('Coulombe', 'Baker')})
    return c


def _stable_ctx(tid=703, name='Atlanta Braves', abbr='ATL'):
    c = _calm(tid, name, abbr)
    c['role_stability_context'].update({'stability_band': 'stable', 'core_stability_pct': 92, 'core_retention_count': 3})
    return c


def _depth_ctx(tid=704, name='New York Yankees', abbr='NYY'):
    c = _calm(tid, name, abbr)
    c['injury_context'].update({'depth_pressure_band': 'heavy', 'active_bullpen_arms_count': 5,
                                'inactive_bullpen_arms_count': 4, 'il_bullpen_arms_count': 3, 'non_il_inactive_bullpen_arms_count': 1,
                                'inactive_bullpen_share': 36.0, 'inactive_bullpen_arms': _nm('Holmes', 'Kahnle', 'Hamilton', 'Cousins')})
    return c


def _availability_ctx(tid=705, name='Los Angeles Dodgers', abbr='LAD'):
    c = _calm(tid, name, abbr)
    c['bullpen_optionality_context'].update(
        {'optionality_band': 'deep', 'practical_close_game_paths_count': 6, 'available_arms_count': 8,
         'monitor_arms_count': 0, 'restricted_arms_count': 0,
         'clean_workload_options': _nm('Phillips', 'Graterol', 'Vesia', 'Brasier', 'Hudson', 'Yates'),
         'secondary_options': _nm('Ferguson', 'Banda')})
    return c


# ── Problem 1: Evidence does not repeat the noticed lead ──────────────────────

def test_trust_evidence_lead_differs_from_noticed():
    story = _canon(_trust_ctx())
    noticed, evidence = _sect(story, 'what_baseballos_noticed'), _sect(story, 'evidence')
    lead = _first_sentence(evidence)
    assert 'leclerc' in lead                                              # leads with WHO...
    assert 'available' not in lead and 'clean and rested' not in lead     # ...not the noticed count contrast
    assert _overlap(lead, _first_sentence(noticed)) < 0.5
    assert 'Leclerc' in evidence                                          # support preserved


def test_bridge_evidence_lead_differs_from_noticed():
    story = _canon(_bridge_ctx())
    noticed, evidence = _sect(story, 'what_baseballos_noticed'), _sect(story, 'evidence')
    lead = _first_sentence(evidence)
    assert 'bridge' in lead or 'rested' in lead                          # leads with the clean-arm angle
    assert 'is settled, but the path to it runs through' not in evidence  # not the noticed sentence
    assert '%' not in lead                                               # not the noticed early-entry rate
    assert _overlap(lead, _first_sentence(noticed)) < 0.5
    assert 'innings a game just to reach them' in evidence                # support preserved (coverage)


def test_stable_core_evidence_drops_duplicate_line():
    story = _canon(_stable_ctx())
    noticed, evidence = _sect(story, 'what_baseballos_noticed'), _sect(story, 'evidence')
    assert 'It is the same trusted group as before' in noticed            # the line lives in noticed
    assert 'It is the same trusted group as before' not in evidence       # and is not repeated in evidence
    assert '92%' in evidence                                              # support preserved


def test_each_fixed_beat_evidence_has_support():
    for ctx in (_trust_ctx(), _bridge_ctx(), _stable_ctx()):
        evidence = _sect(_canon(ctx), 'evidence')
        assert evidence and len(evidence.split('. ')) >= 2                # a real built case, not a lone line


# ── Problem 2: Depth headline never names inactive / IL arms ──────────────────

def test_depth_headline_excludes_inactive_arms():
    story = _canon(_depth_ctx())
    headline = story['headline']
    for name in ('Holmes', 'Kahnle', 'Hamilton', 'Cousins'):
        assert name not in headline
    # The evidence/observation still report the depth honestly.
    assert 'on the IL' in _sect(story, 'evidence')


def test_depth_headline_uses_a_non_name_form():
    # Across several depth teams, no headline should ever name the inactive arms.
    for i, names in enumerate([('Bautista', 'Finnegan'), ('Romano', 'Cimber', 'Walsh'), ('Maton',)]):
        c = _calm(720 + i, f'River City {i}', f'RC{i}')
        c['injury_context'].update({'depth_pressure_band': 'heavy', 'active_bullpen_arms_count': 5,
                                    'inactive_bullpen_arms_count': len(names), 'il_bullpen_arms_count': 1,
                                    'non_il_inactive_bullpen_arms_count': 1, 'inactive_bullpen_share': 30.0,
                                    'inactive_bullpen_arms': _nm(*names)})
        headline = _canon(c)['headline']
        for name in names:
            assert name not in headline


# ── Problem 3: Carry lines are reader-facing ──────────────────────────────────

_AVAIL_NAMES = ('Phillips', 'Graterol', 'Vesia', 'Brasier', 'Hudson', 'Yates')


def test_availability_carry_line_caps_names():
    # Guarantee: with six clean options, the carry line never names more than the
    # first three (some teams' carry form names none — also fine).
    named_somewhere = False
    for tid in range(750, 790):
        tomorrow = _sect(_canon(_availability_ctx(tid, f'Deep Pen {tid}', f'DP{tid % 100}')), 'why_it_matters_tomorrow')
        listed = [n for n in _AVAIL_NAMES if n in tomorrow]
        assert len(listed) <= 3, (tid, tomorrow)
        if listed:
            # When the carry line does name the group, it is the first three only.
            assert set(listed) == {'Phillips', 'Graterol', 'Vesia'}, (tid, tomorrow)
            named_somewhere = True
    assert named_somewhere  # the cap is actually exercised, not just vacuously true


def test_depth_carry_line_is_a_single_clean_clause():
    tomorrow = _sect(_canon(_depth_ctx()), 'why_it_matters_tomorrow')
    sentences = [s for s in tomorrow.split('. ') if s.strip()]
    assert len(sentences) == 1                                            # no multi-clause bolt-on
    assert 'little room to maneuver' not in tomorrow                      # the band-phrase appendage is gone


def test_carry_lines_avoid_prediction_language():
    for ctx in (_trust_ctx(), _bridge_ctx(), _stable_ctx(), _depth_ctx(), _availability_ctx()):
        tomorrow = _sect(_canon(ctx), 'why_it_matters_tomorrow').lower()
        assert ' will ' not in f' {tomorrow} ' and not tomorrow.startswith('will ')
        for phrase in PREDICTION_PHRASES:
            assert phrase.lower() not in tomorrow


# ── Guardrails on all reader-facing text for the fixed beats ──────────────────

def test_fixed_beats_clear_all_guardrails():
    lists = (BANNED_TERMS, ROBOTIC_TERMS, PUBLIC_BANNED_TERMS, BANNED_PUBLIC_LANGUAGE,
             DENIED_PUBLIC_PHRASES, INTERNAL_TERMS)
    for ctx in (_trust_ctx(), _bridge_ctx(), _stable_ctx(), _depth_ctx(), _availability_ctx()):
        story = _canon(ctx)
        texts = [story['headline']] + [s['text'] for s in story['blueprint']]
        for text in texts:
            low = text.lower()
            for terms in lists:
                for term in terms:
                    term = (term or '').lower()
                    assert not (term and term in low), (term, text)


# ── Regression: feed variety, editorial review, determinism, contract ─────────

def _coverage_feed():
    specs = [(741, 'Detroit Tigers', 'DET', 4.4, 66.0), (742, 'Seattle Mariners', 'SEA', 5.0, 46.0),
             (743, 'Miami Marlins', 'MIA', 4.3, 64.0), (744, 'Chicago Cubs', 'CHC', 4.7, 52.0)]
    ctxs, teams = {}, []
    for tid, name, abbr, avg7, early in specs:
        c = _calm(tid, name, abbr)
        c['rotation_context'].update({'rotation_avg_ip_7d': avg7, 'rotation_avg_ip_14d': 5.7, 'rotation_ip_trend': -1.1,
                                      'early_bullpen_entry_rate': early, 'bullpen_coverage_ip_7d': 4.5})
        ctxs[tid] = c
        teams.append({'team_id': tid, 'team_name': name, 'team_abbreviation': abbr})
    builder = lambda tid, as_of_date=None: build_team_story(tid, as_of_date=as_of_date, team_context=ctxs[tid])
    return build_canonical_story_feed(teams, as_of_date=DATE, story_builder=builder)


def test_feed_variety_still_works():
    av = [s for s in _coverage_feed()['items'] if s['story_available']]
    assert len(av) == 4
    assert len({s['headline'] for s in av}) == 4
    assert len({_sect(s, 'what_everyone_saw') for s in av}) == 4
    assert len({_sect(s, 'why_it_matters') for s in av}) == 4


def test_editorial_review_still_passes_for_fixed_beats():
    for ctx in (_trust_ctx(), _bridge_ctx(), _stable_ctx(), _depth_ctx(), _availability_ctx()):
        story = _canon(ctx)
        assert [s['key'] for s in story['blueprint']] == list(SECTION_ORDER)
        report = review_story(story)
        assert report['status'] == STATUS_PASS, (ctx['team_id'], report['warnings'])


def test_determinism_preserved():
    assert _canon(_bridge_ctx()) == _canon(_bridge_ctx())
    a = [s['headline'] for s in _coverage_feed()['items'] if s['story_available']]
    b = [s['headline'] for s in _coverage_feed()['items'] if s['story_available']]
    assert a == b


def test_does_not_mutate_context():
    ctx = _trust_ctx()
    snapshot = copy.deepcopy(ctx)
    _canon(ctx)
    assert ctx == snapshot
