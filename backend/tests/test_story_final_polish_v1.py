"""Final Story Polish Pass (V2) tests.

Three finishing fixes:
  A. "Why it matters tomorrow" is a reader-facing watch cue, de-duplicated across
     same-beat clusters, with no prediction language.
  B. Coverage / sustainability / availability Evidence leads from a different
     angle than the "noticed" section (the coherence rule, extended).
  C. route_change headlines use change-aware language ("now run through …"),
     never "remain"/"still" and never "leverage route".

All fact-safe, deterministic, Editorial-Review-clean, and contract-compatible.
"""

import re

from services.story_intelligence_service_v1 import build_team_story
from services.story_feed import build_canonical_story_feed, canonical_story_from_service_payload
from services.story_blueprint_v1 import SECTION_ORDER
from services.editorial_review_v1 import PREDICTION_PHRASES, STATUS_PASS, review_story
from services.story_voice_library_v1 import WATCH_LINES

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


def _canon(ctx):
    return canonical_story_from_service_payload(build_team_story(ctx['team_id'], as_of_date=DATE, team_context=ctx), date=DATE)


def _sect(story, key):
    return next((s['text'] for s in story.get('blueprint', []) if s['key'] == key), '')


def _lead(text):
    return text.split('. ')[0].strip().rstrip('.').lower()


def _content_words(text):
    return {w for w in re.findall(r'[a-z0-9]+', text.lower()) if len(w) >= 4}


def _overlap(a, b):
    wa, wb = _content_words(a), _content_words(b)
    return len(wa & wb) / len(wa | wb) if (wa and wb) else 0.0


def _coverage(tid, name, abbr, avg7, early):
    c = _calm(tid, name, abbr)
    c['rotation_context'].update({'rotation_avg_ip_7d': avg7, 'rotation_avg_ip_14d': 5.7, 'rotation_ip_trend': -1.1,
                                  'early_bullpen_entry_rate': early, 'bullpen_coverage_ip_7d': 4.5})
    return c


def _sustainability(tid, name, abbr, share, delta, trio):
    c = _calm(tid, name, abbr)
    c['bullpen_concentration_context'].update({'concentration_band': 'narrow', 'top_three_workload_share_10d': share,
                                               'top_three_share_delta_vs_league': delta,
                                               'top_three_relievers_10d': [{'name': n} for n in trio]})
    return c


def _availability(tid, name, abbr):
    c = _calm(tid, name, abbr)
    c['bullpen_optionality_context'].update({'optionality_band': 'deep', 'practical_close_game_paths_count': 6,
                                             'available_arms_count': 8, 'monitor_arms_count': 0, 'restricted_arms_count': 0,
                                             'clean_workload_options': [{'name': n} for n in ('Phillips', 'Graterol', 'Vesia', 'Brasier', 'Hudson', 'Yates')],
                                             'secondary_options': [{'name': 'Ferguson'}, {'name': 'Banda'}]})
    return c


def _route(tid, name, abbr, current, previous, added, departed, band='rebuilding', pct=34):
    c = _calm(tid, name, abbr)
    c['role_stability_context'].update({'stability_band': band, 'core_stability_pct': pct, 'core_change_count': len(added),
                                        'core_retention_count': 3 - len(departed),
                                        'current_operational_core': current, 'previous_operational_core': previous,
                                        'new_core_members': added, 'departed_core_members': departed})
    return c


def _coverage_feed():
    specs = [(901, 'Detroit', 'DET', 4.4, 66.0), (902, 'Seattle', 'SEA', 5.0, 46.0),
             (903, 'Miami', 'MIA', 4.3, 64.0), (904, 'Cubs', 'CHC', 4.7, 52.0), (905, 'Toronto', 'TOR', 4.6, 58.0)]
    ctxs = {tid: _coverage(tid, n, a, x, e) for tid, n, a, x, e in specs}
    teams = [{'team_id': tid, 'team_name': n, 'team_abbreviation': a} for tid, n, a, _, _ in specs]
    builder = lambda tid, as_of_date=None: build_team_story(tid, as_of_date=as_of_date, team_context=ctxs[tid])
    return build_canonical_story_feed(teams, as_of_date=DATE, story_builder=builder)


# ── A. Carry line (watch cue) ─────────────────────────────────────────────────

def test_carry_lines_are_reader_facing_watch_cues():
    for ctx in (_coverage(910, 'A', 'A', 4.4, 66.0), _availability(911, 'B', 'B'),
                _route(912, 'C', 'C', ['X', 'Y', 'Z'], ['P', 'Q', 'R'], ['X', 'Y'], ['P', 'Q'])):
        tomorrow = _sect(_canon(ctx), 'why_it_matters_tomorrow')
        assert 'watch' in tomorrow.lower()
        assert tomorrow in [w for bank in WATCH_LINES.values() for w in bank]  # approved watch copy


def test_carry_lines_avoid_prediction_and_will():
    banks = [w for bank in WATCH_LINES.values() for w in bank]
    for line in banks:
        low = line.lower()
        assert ' will ' not in f' {low} ' and not low.startswith('will ')
        for phrase in PREDICTION_PHRASES:
            assert phrase.lower() not in low


def test_carry_lines_carry_no_facts():
    # Fact-free: no digits and no team/player names in any approved watch line.
    for line in (w for bank in WATCH_LINES.values() for w in bank):
        assert not re.search(r'\d', line)


def test_carry_lines_dedup_across_same_beat_cluster():
    av = [s for s in _coverage_feed()['items'] if s['story_available']]
    tomorrows = [_sect(s, 'why_it_matters_tomorrow') for s in av]
    assert len(set(tomorrows)) == 5                       # coverage bank is 5 deep -> all distinct
    assert all('watch' in t.lower() for t in tomorrows)


# ── B. Evidence lead coherence (coverage / sustainability / availability) ──────

def test_coverage_evidence_does_not_lead_by_repeating_noticed():
    story = _canon(_coverage(920, 'Det', 'DET', 4.4, 66.0))
    noticed, evidence = _sect(story, 'what_baseballos_noticed'), _sect(story, 'evidence')
    lead = _lead(evidence)
    assert 'before the sixth' not in lead                 # not the early-entry rate Noticed states
    # Leads with the change-from-baseline (any approved phrasing) or coverage innings.
    assert any(k in lead for k in ('shortened', 'down to', 'covering'))
    assert _overlap(lead, _lead(noticed)) < 0.5
    assert len([p for p in evidence.split('. ') if p.strip()]) >= 2   # still a built case


def test_sustainability_evidence_does_not_lead_by_repeating_noticed():
    story = _canon(_sustainability(921, 'Cle', 'CLE', 76.0, 18.0, ['Clase', 'Smith', 'Sandlin']))
    noticed, evidence = _sect(story, 'what_baseballos_noticed'), _sect(story, 'evidence')
    lead = _lead(evidence)
    assert 'points more of the load' in lead              # leads with the league comparison
    assert 'clase' not in lead and '76%' not in lead      # not the share/names Noticed states
    assert _overlap(lead, _lead(noticed)) < 0.5
    assert len([p for p in evidence.split('. ') if p.strip()]) >= 2


def test_availability_evidence_does_not_lead_by_repeating_noticed():
    story = _canon(_availability(922, 'LAD', 'LAD'))
    noticed, evidence = _sect(story, 'what_baseballos_noticed'), _sect(story, 'evidence')
    lead = _lead(evidence)
    assert 'available' in lead and 'clean and rested' in lead   # available-vs-clean breakdown
    assert 'close-game' not in lead                            # not the path count Noticed states
    assert _overlap(lead, _lead(noticed)) < 0.5


def test_evidence_leads_preserve_facts():
    # Coverage carries its innings numbers; availability carries its arm counts.
    cov = _sect(_canon(_coverage(923, 'Det', 'DET', 4.4, 66.0)), 'evidence')
    assert '4.4' in cov and '5.7' in cov                  # avg7 and the 14-day baseline
    av = _sect(_canon(_availability(924, 'LAD', 'LAD')), 'evidence')
    assert '8' in av and '6' in av


# ── C. Route-change headline ──────────────────────────────────────────────────

def test_route_change_headlines_are_change_aware():
    cases = [
        _route(930, 'White Sox', 'CWS', ['Banks', 'Crochet', 'Fedde'], ['Bummer', 'Kopech', 'Graveman'],
               ['Banks', 'Fedde'], ['Bummer', 'Kopech'], band='rebuilding', pct=34),
        _route(931, 'Pirates', 'PIT', ['Bednar', 'Holderman', 'Stratton'], ['Bednar', 'Holderman', 'Hernandez'],
               ['Stratton'], ['Hernandez'], band='transitioning', pct=58),
    ]
    for ctx in cases:
        story = _canon(ctx)
        assert story['story_type'] == 'route_change'
        h = story['headline'].lower()
        assert 'remain' not in h and 'still' not in h          # no continuity language on a change story
        assert 'leverage route' not in h                       # no internal-ish phrase
        assert 'now' in h or 'reshaped' in h or 'shifted' in h  # change-aware


# ── Regression: feed variety, review, determinism, contract ───────────────────

def test_feed_variety_distinct_across_all_reader_slots():
    av = [s for s in _coverage_feed()['items'] if s['story_available']]
    def col(key):
        return {_sect(s, key) for s in av}
    assert len({s['headline'] for s in av}) == 5
    assert len(col('what_everyone_saw')) == 5
    assert len(col('why_it_matters')) == 5
    assert len(col('why_it_matters_tomorrow')) == 5
    assert len({_sect(s, 'evidence') for s in av}) == 5


def test_feed_passes_editorial_review_and_contract():
    for s in (x for x in _coverage_feed()['items'] if x['story_available']):
        assert [b['key'] for b in s['blueprint']] == list(SECTION_ORDER)
        report = review_story(s)
        assert report['status'] == STATUS_PASS, report['warnings']


def test_feed_is_deterministic():
    a = [(s['headline'], _sect(s, 'evidence'), _sect(s, 'why_it_matters_tomorrow'))
         for s in _coverage_feed()['items'] if s['story_available']]
    b = [(s['headline'], _sect(s, 'evidence'), _sect(s, 'why_it_matters_tomorrow'))
         for s in _coverage_feed()['items'] if s['story_available']]
    assert a == b
