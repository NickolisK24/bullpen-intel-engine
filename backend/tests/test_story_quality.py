"""Tests for the Story Quality contract (scoring + gating).

Pure unit tests - the scorer has no DB or app dependency. Story objects below
mirror the shape the deployed four-beat feed and narrative-memory continuity
notes actually produce, including the specific known-good (Detroit, Cardinals)
and known-weak (KC flagship, White Sox) cards called out in the contract.
"""

from copy import deepcopy

import pytest

from services.story_quality import (
    DEFAULT_STORY_QUALITY_CONFIG,
    RULE_BASELINE_ANCHOR,
    RULE_FORWARD_CONSTRAINT,
    RULE_NAMED_ARMS,
    RULE_NO_REDUNDANT_RESTATEMENT,
    RULE_STATED_CAUSE,
    VERSION,
    StoryQualityConfig,
    apply_story_quality_gate,
    build_story_quality_debug_dump,
    four_beat_story_view,
    score_continuity_note,
    score_four_beat_story,
    summarize_scorecards,
)


# ── Representative story fixtures (modeled on the real producers) ──────────────

def detroit_story():
    """Known-good: names arms, forward constraint, no redundancy."""
    return {
        'story_id': '116:sustainability_question',
        'rule_key': 'sustainability_question',
        'team_id': 116,
        'team_name': 'Tigers',
        'team_abbreviation': 'DET',
        'title': "Detroit's next tight inning may find the same relief pocket",
        'story_voice': {
            'observation_type': 'run_prevention_stress',
            'pitcher_names': ['Will Vest', 'Tyler Holton', 'Kyle Finnegan'],
            'human_frame': (
                "If tonight gets tight, Tigers' strong ERA may still have to pass "
                "through Will Vest and Tyler Holton."
            ),
            'evidence_sentence': (
                "A 3.40 season ERA gives Tigers results, but the recent route still "
                "runs through Will Vest and Tyler Holton."
            ),
            'consequence_sentence': (
                "A close game can still ask the same pocket of arms to carry the leverage."
            ),
        },
        'story_evidence': {
            'pitcher_names': ['Will Vest', 'Tyler Holton', 'Kyle Finnegan'],
            'evidence_statement': (
                "A 3.40 season ERA gives Tigers results, but the recent route still "
                "runs through Will Vest and Tyler Holton."
            ),
            'consequence_statement': (
                "That keeps the read in play if the next tight inning has to move back "
                "through Will Vest and Tyler Holton."
            ),
            'consequence_category': 'heavier_workload_concentration',
        },
        'narrative': (
            "Detroit's results still look sturdy, but the workload underneath still "
            "matters. The biggest relief pockets have been finding the same arms."
        ),
        'lead_fields': {'top_workload_names': ['Will Vest', 'Tyler Holton']},
        'computed': {'top_workload_names': ['Will Vest', 'Tyler Holton']},
    }


def cardinals_story():
    """Known-good: roster-movement cause distinguished from leverage center."""
    return {
        'story_id': '138:pressure_distribution',
        'rule_key': 'pressure_distribution',
        'team_id': 138,
        'team_name': 'Cardinals',
        'team_abbreviation': 'STL',
        'title': "Cardinals' bullpen mix changed without moving the leverage center",
        'story_voice': {
            'observation_type': 'change',
            'pitcher_names': ['Ryan Helsley', 'JoJo Romero'],
            'human_frame': (
                "Cardinals have one recently reintroduced reliever back into the "
                "bullpen, but Ryan Helsley and JoJo Romero still anchor the current "
                "late-game route."
            ),
            'evidence_sentence': (
                "Cardinals have one recently reintroduced reliever back into the "
                "bullpen, but Ryan Helsley and JoJo Romero still anchor the current "
                "late-game route."
            ),
            'consequence_sentence': (
                "The roster movement matters less than who still sits at the center "
                "of the leverage route."
            ),
        },
        'story_evidence': {
            'pitcher_names': ['Ryan Helsley', 'JoJo Romero'],
            'evidence_statement': (
                "Cardinals have one recently reintroduced reliever back into the "
                "bullpen, but Ryan Helsley and JoJo Romero still anchor the current "
                "late-game route."
            ),
            'consequence_statement': (
                "If the next close route tightens, it still runs through Ryan Helsley "
                "and JoJo Romero."
            ),
            'consequence_category': 'more_stable_bullpen_shape',
        },
        'narrative': (
            "Cardinals' bullpen has looked more settled over the recent games. A "
            "fresh arm adds depth without changing who finishes."
        ),
        'lead_fields': {'top_workload_names': ['Ryan Helsley', 'JoJo Romero']},
        'computed': {'top_workload_names': ['Ryan Helsley', 'JoJo Romero']},
    }


def white_sox_story():
    """Known-weak: adjacent sentences restate each other (dependency/center)."""
    return {
        'story_id': '145:stress_transfer',
        'rule_key': 'stress_transfer',
        'team_id': 145,
        'team_name': 'White Sox',
        'team_abbreviation': 'CWS',
        'title': 'The dependency point in the relief workload',
        'story_voice': {
            'observation_type': 'workload_concentration',
            'pitcher_names': ['Garrett Crochet', 'Michael Kopech'],
            'human_frame': (
                "Garrett Crochet and Michael Kopech are the dependency point in White "
                "Sox' recent relief workload."
            ),
            'evidence_sentence': (
                "Garrett Crochet and Michael Kopech are the center of White Sox' recent "
                "relief workload, taking 61% of the pitches."
            ),
            'consequence_sentence': (
                "The next tight inning still points back toward Garrett Crochet and "
                "Michael Kopech before the rest of the bullpen."
            ),
        },
        'story_evidence': {
            'pitcher_names': ['Garrett Crochet', 'Michael Kopech'],
            'evidence_statement': (
                "Garrett Crochet and Michael Kopech are the center of White Sox' recent "
                "relief workload, taking 61% of the pitches."
            ),
            'consequence_statement': (
                "The next tight inning still points back toward Garrett Crochet and "
                "Michael Kopech before the rest of the bullpen."
            ),
            'consequence_category': 'heavier_workload_concentration',
        },
        'narrative': (
            "White Sox' relief work is less about the full list and more about who "
            "keeps getting the ball."
        ),
        'lead_fields': {'top_workload_names': ['Garrett Crochet', 'Michael Kopech']},
    }


def kc_flagship_note():
    """Known-weak: no names, no cause, bare 94%, no constraint."""
    return {
        'team_id': 118,
        'team_name': 'Royals',
        'team_abbreviation': 'KC',
        'continuity_note': (
            'The same core relievers have carried 94% of the bullpen work over the '
            'last 10 days.'
        ),
        'continuity': {
            'type': 'workload_concentration',
            'window_days': 10,
            'evidence': {'core_arm_appearance_share': 0.94},
        },
    }


# ── Known-good vs known-weak separation (Phase 2 validation) ───────────────────

def test_known_good_cards_score_high():
    detroit = score_four_beat_story(detroit_story())
    cardinals = score_four_beat_story(cardinals_story())
    assert cardinals['rules_passed'] == 5
    assert cardinals['score'] == 100.0
    # Detroit names arms, ends on a constraint, and avoids redundancy.
    assert detroit['rules'][RULE_NAMED_ARMS]['passed']
    assert detroit['rules'][RULE_FORWARD_CONSTRAINT]['passed']
    assert detroit['rules'][RULE_NO_REDUNDANT_RESTATEMENT]['passed']
    assert detroit['rules_passed'] >= 3
    assert not detroit['hard_fail']


def test_known_weak_cards_score_low():
    white_sox = score_four_beat_story(white_sox_story())
    kc = score_continuity_note(kc_flagship_note())
    assert white_sox['rules_passed'] <= 2
    assert kc['rules_passed'] <= 1


def test_weak_scores_below_good_scores():
    detroit = score_four_beat_story(detroit_story())['score']
    cardinals = score_four_beat_story(cardinals_story())['score']
    white_sox = score_four_beat_story(white_sox_story())['score']
    kc = score_continuity_note(kc_flagship_note())['score']
    assert min(detroit, cardinals) > max(white_sox, kc)


# ── Rule 1: named arms ────────────────────────────────────────────────────────

def test_named_arms_passes_with_two_relievers():
    card = score_four_beat_story(detroit_story())
    assert card['rules'][RULE_NAMED_ARMS]['passed']


def test_named_arms_fails_without_names():
    kc = score_continuity_note(kc_flagship_note())
    assert not kc['rules'][RULE_NAMED_ARMS]['passed']
    assert 'no reliever names' in kc['rules'][RULE_NAMED_ARMS]['reason']


def test_named_arms_fails_with_only_one_name():
    story = detroit_story()
    one_name = ['Will Vest']
    story['story_evidence']['pitcher_names'] = one_name
    story['story_voice']['pitcher_names'] = one_name
    story['lead_fields'] = {'top_workload_names': one_name}
    story['computed'] = {'top_workload_names': one_name}
    story['story_voice']['human_frame'] = (
        "If tonight gets tight, Tigers' strong ERA may still have to pass through Will Vest."
    )
    story['story_evidence']['evidence_statement'] = (
        "The recent route still runs through Will Vest."
    )
    story['story_evidence']['consequence_statement'] = (
        "That stays in play if the next tight inning comes back to Will Vest."
    )
    story['narrative'] = "Detroit keeps leaning on one arm."
    card = score_four_beat_story(story)
    assert not card['rules'][RULE_NAMED_ARMS]['passed']


# ── Rule 2: stated cause ──────────────────────────────────────────────────────

def test_stated_cause_passes_on_roster_movement():
    card = score_four_beat_story(cardinals_story())
    assert card['rules'][RULE_STATED_CAUSE]['passed']


def test_stated_cause_passes_on_short_starts():
    story = cardinals_story()
    story['story_evidence']['evidence_statement'] = (
        "Starters have averaged 3.9 innings over the last week, down from 5.4, so "
        "Ryan Helsley and JoJo Romero keep inheriting the game early."
    )
    story['story_voice']['human_frame'] = story['story_evidence']['evidence_statement']
    story['story_voice']['evidence_sentence'] = story['story_evidence']['evidence_statement']
    card = score_four_beat_story(story)
    assert card['rules'][RULE_STATED_CAUSE]['passed']


def test_stated_cause_fails_on_circular_concentration():
    card = score_four_beat_story(white_sox_story())
    assert not card['rules'][RULE_STATED_CAUSE]['passed']
    kc = score_continuity_note(kc_flagship_note())
    assert not kc['rules'][RULE_STATED_CAUSE]['passed']


# ── Rule 3: baseline where it sharpens (conditional) ──────────────────────────

def test_baseline_auto_passes_when_no_bare_figure():
    card = score_four_beat_story(cardinals_story())
    assert card['rules'][RULE_BASELINE_ANCHOR]['passed']
    assert card['rules'][RULE_BASELINE_ANCHOR]['applicable'] is False


def test_baseline_fails_on_bare_percentage():
    card = score_four_beat_story(white_sox_story())
    assert not card['rules'][RULE_BASELINE_ANCHOR]['passed']


def test_baseline_passes_when_percentage_anchored():
    story = white_sox_story()
    anchored = (
        "Garrett Crochet and Michael Kopech have taken 61% of recent relief pitches, "
        "well above the league-typical 57%."
    )
    story['story_evidence']['evidence_statement'] = anchored
    story['story_voice']['evidence_sentence'] = anchored
    # Remove the redundant human_frame restatement for a clean baseline check.
    story['story_voice']['human_frame'] = (
        "Garrett Crochet and Michael Kopech are doing the heavy lifting."
    )
    card = score_four_beat_story(story)
    assert card['rules'][RULE_BASELINE_ANCHOR]['passed']


def test_baseline_treats_n_of_m_as_self_anchored():
    note = {
        'team_id': 1,
        'team_name': 'Test',
        'continuity_note': (
            'First Arm and Second Arm handled 8 of 12 bullpen appearances over the '
            'last 10 days.'
        ),
        'continuity': {
            'type': 'workload_concentration',
            'window_days': 10,
            'evidence': {
                'top_two_pitchers': [
                    {'pitcher_name': 'First Arm'},
                    {'pitcher_name': 'Second Arm'},
                ],
            },
        },
    }
    card = score_continuity_note(note)
    # "8 of 12" carries its own denominator, so the baseline rule should not fail it.
    assert card['rules'][RULE_BASELINE_ANCHOR]['passed']


# ── Rule 4: forward constraint + forecast ban ─────────────────────────────────

def test_forward_constraint_present():
    card = score_four_beat_story(detroit_story())
    assert card['rules'][RULE_FORWARD_CONSTRAINT]['passed']


def test_forecast_language_is_hard_fail():
    story = cardinals_story()
    story['story_evidence']['consequence_statement'] = (
        "Ryan Helsley will likely be unavailable and is favored to close tonight."
    )
    story['story_voice']['consequence_sentence'] = story['story_evidence']['consequence_statement']
    card = score_four_beat_story(story)
    assert card['hard_fail'] is True
    assert not card['rules'][RULE_FORWARD_CONSTRAINT]['passed']
    assert card['meets_threshold'] is False


def test_reliever_named_will_does_not_trip_forecast():
    # "Will Vest" must not register as the future-tense banned term "will".
    card = score_four_beat_story(detroit_story())
    assert card['hard_fail'] is False


def test_missing_constraint_fails_without_hard_fail():
    kc = score_continuity_note(kc_flagship_note())
    assert not kc['rules'][RULE_FORWARD_CONSTRAINT]['passed']
    assert kc['hard_fail'] is False


# ── Rule 5: no redundant restatement ──────────────────────────────────────────

def test_redundant_adjacent_sentences_flagged():
    card = score_four_beat_story(white_sox_story())
    assert not card['rules'][RULE_NO_REDUNDANT_RESTATEMENT]['passed']
    detail = card['rules'][RULE_NO_REDUNDANT_RESTATEMENT]['detail']
    assert detail['flagged_pairs']


def test_non_redundant_story_passes():
    card = score_four_beat_story(cardinals_story())
    assert card['rules'][RULE_NO_REDUNDANT_RESTATEMENT]['passed']


def test_single_sentence_auto_passes_redundancy():
    kc = score_continuity_note(kc_flagship_note())
    assert kc['rules'][RULE_NO_REDUNDANT_RESTATEMENT]['passed']
    assert kc['rules'][RULE_NO_REDUNDANT_RESTATEMENT]['applicable'] is False


# ── Gate: report-only (default) vs enforcement ────────────────────────────────

def test_report_only_publishes_everything():
    stories = [detroit_story(), white_sox_story()]
    published, held, summary = apply_story_quality_gate(stories, DEFAULT_STORY_QUALITY_CONFIG)
    assert len(published) == 2
    assert held == []
    assert summary['mode'] == 'report_only'
    assert summary['gate_enabled'] is False
    # The scorecard is still attached for inspection.
    assert all('story_quality' in story for story in published)
    # And the summary still reports what *would* be held.
    assert summary['below_threshold_count'] >= 1


def test_report_only_is_backward_compatible_order_and_membership():
    stories = [detroit_story(), white_sox_story(), cardinals_story()]
    original_ids = [s['story_id'] for s in stories]
    published, held, _ = apply_story_quality_gate(stories, DEFAULT_STORY_QUALITY_CONFIG)
    assert [s['story_id'] for s in published] == original_ids
    assert held == []


def test_enforcement_holds_weak_stories():
    config = StoryQualityConfig(gate_enabled=True, gate_threshold=60.0)
    stories = [detroit_story(), cardinals_story(), white_sox_story()]
    published, held, summary = apply_story_quality_gate(stories, config)
    published_ids = {s['story_id'] for s in published}
    held_ids = {h['story_id'] for h in held}
    assert '145:stress_transfer' in held_ids  # White Sox held
    assert '138:pressure_distribution' in published_ids  # Cardinals published
    assert summary['mode'] == 'enforcing'
    assert summary['held_count'] == len(held)


def test_enforcement_holds_hard_fail_regardless_of_threshold():
    config = StoryQualityConfig(gate_enabled=True, gate_threshold=0.0)
    story = cardinals_story()
    story['story_evidence']['consequence_statement'] = "Helsley is favored at -150 odds."
    story['story_voice']['consequence_sentence'] = story['story_evidence']['consequence_statement']
    published, held, _ = apply_story_quality_gate([story], config)
    assert published == []
    assert len(held) == 1
    assert held[0]['hard_fail'] is True


# ── Config tunability ─────────────────────────────────────────────────────────

def test_threshold_is_configurable():
    # White Sox scores 40 - unambiguously below a strict threshold and above a
    # lenient one (independent of the stated_cause widening).
    strict = StoryQualityConfig(gate_enabled=True, gate_threshold=100.0)
    published, held, _ = apply_story_quality_gate([white_sox_story()], strict)
    assert published == []  # held under a strict threshold
    lenient = StoryQualityConfig(gate_enabled=True, gate_threshold=20.0)
    published2, held2, _ = apply_story_quality_gate([white_sox_story()], lenient)
    assert len(published2) == 1


def test_min_named_arms_is_configurable():
    story = detroit_story()
    one_name = ['Will Vest']
    story['story_evidence']['pitcher_names'] = one_name
    story['story_voice']['pitcher_names'] = one_name
    story['lead_fields'] = {'top_workload_names': one_name}
    story['computed'] = {'top_workload_names': one_name}
    story['story_voice']['human_frame'] = "Will Vest carries the route."
    story['story_evidence']['evidence_statement'] = "Will Vest carries the route."
    story['narrative'] = "One arm."
    relaxed = StoryQualityConfig(min_named_arms=1)
    card = score_four_beat_story(story, relaxed)
    assert card['rules'][RULE_NAMED_ARMS]['passed']


def test_from_app_config_reads_flags():
    config = StoryQualityConfig.from_app_config({
        'STORY_QUALITY_GATE_ENABLED': True,
        'STORY_QUALITY_GATE_THRESHOLD': 80,
    })
    assert config.gate_enabled is True
    assert config.gate_threshold == 80.0


def test_default_config_is_report_only():
    assert DEFAULT_STORY_QUALITY_CONFIG.gate_enabled is False


# ── Determinism + structure ───────────────────────────────────────────────────

def test_scoring_is_deterministic():
    story = detroit_story()
    first = score_four_beat_story(story)
    second = score_four_beat_story(deepcopy(story))
    assert first['score'] == second['score']
    assert first['rules_passed'] == second['rules_passed']


def test_scorecard_has_reason_per_rule():
    card = score_four_beat_story(white_sox_story())
    for rule_key, result in card['rules'].items():
        assert result['reason']
        assert 'passed' in result


def test_fail_reasons_identify_killing_rules():
    card = score_four_beat_story(white_sox_story())
    joined = ' '.join(card['fail_reasons'])
    assert RULE_NO_REDUNDANT_RESTATEMENT in joined


def test_summary_distribution_and_rule_fail_counts():
    cards = [
        score_four_beat_story(detroit_story()),
        score_four_beat_story(cardinals_story()),
        score_four_beat_story(white_sox_story()),
    ]
    summary = summarize_scorecards(cards, DEFAULT_STORY_QUALITY_CONFIG)
    assert summary['scored_count'] == 3
    assert sum(summary['score_distribution_by_rules_passed'].values()) == 3
    assert summary['rule_fail_counts'][RULE_NO_REDUNDANT_RESTATEMENT] >= 1


# ── Debug dump ────────────────────────────────────────────────────────────────

def test_debug_dump_per_team():
    stories = [detroit_story(), white_sox_story()]
    published, _, summary = apply_story_quality_gate(stories, DEFAULT_STORY_QUALITY_CONFIG)
    feed = {'items': published, 'story_quality': summary}
    dump = build_story_quality_debug_dump(feed, team_id=145)
    assert dump['story_count'] == 1
    row = dump['stories'][0]
    assert row['team_abbreviation'] == 'CWS'
    assert row['rules']  # full rule-by-rule scorecard present
    assert row['fail_reasons']


def test_four_beat_view_assembles_voice_triple():
    view = four_beat_story_view(white_sox_story())
    assert view.reliever_set
    # The dependency/center restatement should both be present as body sentences.
    body = view.body_text.lower()
    assert 'dependency point' in body
    assert 'center of' in body


# ── Fix #1: metric-divergence framing (stated_cause widening) ──────────────────
#
# Real narratives from the report-only 30-team snapshot (data through 2026-06-20).
# Divergence = a results metric (ERA / run prevention / results) contrasted
# against a concentrated workload. It must earn stated_cause; a workload-only
# restatement must not. "Before" behavior is simulated by disabling the
# divergence recognizer via config (empty results terms).

_DIVERGENCE_OFF = StoryQualityConfig(divergence_results_terms=())


def _snapshot_four_beat(*, story_id, team_id, team_name, team_abbr, names,
                        title, human_frame, evidence, consequence, narrative,
                        category='heavier_workload_concentration',
                        rule_key='sustainability_question'):
    return {
        'story_id': story_id,
        'rule_key': rule_key,
        'team_id': team_id,
        'team_name': team_name,
        'team_abbreviation': team_abbr,
        'title': title,
        'story_voice': {
            'observation_type': 'run_prevention_stress',
            'pitcher_names': list(names),
            'human_frame': human_frame,
            'evidence_sentence': evidence,
            'consequence_sentence': consequence,
        },
        'story_evidence': {
            'pitcher_names': list(names),
            'evidence_statement': evidence,
            'consequence_statement': consequence,
            'consequence_category': category,
        },
        'narrative': narrative,
        'lead_fields': {'top_workload_names': list(names)},
        'computed': {'top_workload_names': list(names)},
    }


def san_diego_story():  # 135 — divergence (ERA vs. pitches-per)
    return _snapshot_four_beat(
        story_id='135:sustainability_question',
        team_id=135, team_name='San Diego Padres', team_abbr='SD',
        names=['Robert Suarez', 'Jeremiah Estrada'],
        title="San Diego's ERA is steadier than the workload",
        human_frame=(
            "San Diego Padres' run prevention has held up, but the workload is "
            "tighter than the ERA alone shows."
        ),
        evidence=(
            "Robert Suarez and Jeremiah Estrada have kept San Diego Padres' run "
            "prevention strong with a 2.24 ERA, but the recent workload is still "
            "31.2 pitches per participating reliever."
        ),
        consequence=(
            "The ERA is carrying a steadier public read than the recent workload "
            "shape deserves."
        ),
        narrative="San Diego's relief work keeps landing in the same place.",
    )


def miami_story():  # 146 — divergence (ERA vs. workload, "not as broad")
    return _snapshot_four_beat(
        story_id='146:sustainability_question',
        team_id=146, team_name='Miami Marlins', team_abbr='MIA',
        names=['Cade Gibson', 'John King', 'Tyler Zuber'],
        title="Miami's run prevention rides a narrow workload",
        human_frame=(
            "Miami Marlins have good run prevention and a workload still "
            "concentrated around the same relief pocket."
        ),
        evidence=(
            "Miami Marlins have a 2.92 bullpen ERA, but Cade Gibson, John King, "
            "and Tyler Zuber remain tied to a 32.4-pitch recent workload per "
            "participating reliever."
        ),
        consequence=(
            "The run prevention is real, but the workload underneath is not as broad."
        ),
        narrative="Miami's results still look good on the surface.",
    )


def detroit_divergence_story():  # 116 — divergence (ERA vs. route/pitches-per)
    return _snapshot_four_beat(
        story_id='116:sustainability_question',
        team_id=116, team_name='Detroit Tigers', team_abbr='DET',
        names=['Kyle Finnegan', 'Tyler Holton', 'Will Vest'],
        title="Detroit's ERA outruns the route underneath it",
        human_frame=(
            "If tonight gets tight, Detroit Tigers' strong ERA may still have to "
            "pass through Kyle Finnegan and Tyler Holton."
        ),
        evidence=(
            "A 1.93 season ERA gives Detroit Tigers results, but the recent route "
            "still runs through Kyle Finnegan, Tyler Holton, and Will Vest at 26 "
            "pitches per participating reliever."
        ),
        consequence=(
            "A close game can still ask the same pocket of arms to carry the leverage."
        ),
        narrative="Detroit's results still look clean in the box score.",
    )


def chicago_white_sox_story():  # 145 — workload only (must stay circular/fail, score 20)
    return _snapshot_four_beat(
        story_id='145:stress_transfer',
        team_id=145, team_name='Chicago White Sox', team_abbr='CWS',
        names=['Joe Rock', 'Trevor Richards', 'Chris Murphy'],
        title='The dependency point in the relief workload',
        human_frame=(
            "Joe Rock, Trevor Richards, and Chris Murphy are the dependency point "
            "in Chicago White Sox's recent relief workload."
        ),
        evidence=(
            "Joe Rock, Trevor Richards, and Chris Murphy are the center of Chicago "
            "White Sox's recent relief workload, taking 69% of the pitches."
        ),
        consequence=(
            "The workload shape gives the first group less distance from another "
            "leverage pocket."
        ),
        narrative="Chicago White Sox's relief work keeps landing on the same names.",
        rule_key='stress_transfer',
    )


def continuity_109_note():  # single-sentence workload restatement (must stay failing)
    return {
        'team_id': 109,
        'team_name': 'Arizona Diamondbacks',
        'team_abbreviation': 'AZ',
        'continuity_note': (
            'The same core relievers have carried 85% of the bullpen work over the '
            'last 10 days.'
        ),
        'continuity': {
            'type': 'workload_concentration',
            'window_days': 10,
            'evidence': {'core_arm_appearance_share': 0.85},
        },
    }


def toronto_upstream_story():  # 141 — passes via reintroduction (regression guard)
    return _snapshot_four_beat(
        story_id='141:pressure_distribution',
        team_id=141, team_name='Toronto Blue Jays', team_abbr='TOR',
        names=['Jeff Hoffman', 'Chad Green'],
        title="Toronto's mix changed without moving the center",
        human_frame=(
            "Toronto Blue Jays have one recently reintroduced reliever back into "
            "the bullpen, but Jeff Hoffman and Chad Green still anchor the current "
            "late-game route."
        ),
        evidence=(
            "Toronto Blue Jays reintroduced one reliever, but Jeff Hoffman and "
            "Chad Green still anchor the late-game route."
        ),
        consequence=(
            "If the next close route tightens, it still runs through Jeff Hoffman "
            "and Chad Green."
        ),
        narrative="Toronto's bullpen has looked steadier lately.",
        category='more_stable_bullpen_shape',
        rule_key='pressure_distribution',
    )


# Must NOW PASS stated_cause via divergence (were false negatives):

def test_san_diego_divergence_now_passes():
    before = score_four_beat_story(san_diego_story(), _DIVERGENCE_OFF)
    after = score_four_beat_story(san_diego_story())
    assert not before['rules'][RULE_STATED_CAUSE]['passed']
    assert after['rules'][RULE_STATED_CAUSE]['passed']
    assert after['rules'][RULE_STATED_CAUSE]['detail']['pattern'] == 'divergence'
    assert 'metric-divergence' in after['rules'][RULE_STATED_CAUSE]['reason']
    assert before['score'] == 40.0 and after['score'] == 60.0


def test_miami_divergence_now_passes():
    before = score_four_beat_story(miami_story(), _DIVERGENCE_OFF)
    after = score_four_beat_story(miami_story())
    assert not before['rules'][RULE_STATED_CAUSE]['passed']
    assert after['rules'][RULE_STATED_CAUSE]['passed']
    assert after['rules'][RULE_STATED_CAUSE]['detail']['pattern'] == 'divergence'
    assert before['score'] == 60.0 and after['score'] == 80.0


def test_detroit_divergence_now_passes():
    before = score_four_beat_story(detroit_divergence_story(), _DIVERGENCE_OFF)
    after = score_four_beat_story(detroit_divergence_story())
    assert not before['rules'][RULE_STATED_CAUSE]['passed']
    assert after['rules'][RULE_STATED_CAUSE]['passed']
    assert after['rules'][RULE_STATED_CAUSE]['detail']['pattern'] == 'divergence'
    assert before['score'] == 60.0 and after['score'] == 80.0


# Must STILL FAIL stated_cause (the two-dimensions boundary):

def test_chicago_white_sox_stays_circular_and_score_20():
    before = score_four_beat_story(chicago_white_sox_story(), _DIVERGENCE_OFF)
    after = score_four_beat_story(chicago_white_sox_story())
    assert not before['rules'][RULE_STATED_CAUSE]['passed']
    assert not after['rules'][RULE_STATED_CAUSE]['passed']
    # Workload-only restatement earns no divergence credit; card stays at 20.
    assert before['score'] == 20.0 and after['score'] == 20.0


def test_continuity_85_pct_stays_failing():
    before = score_continuity_note(continuity_109_note(), _DIVERGENCE_OFF)
    after = score_continuity_note(continuity_109_note())
    assert not before['rules'][RULE_STATED_CAUSE]['passed']
    assert not after['rules'][RULE_STATED_CAUSE]['passed']
    assert before['score'] == after['score']


# Must remain UNCHANGED (upstream cause; reason stays upstream, not divergence):

def test_toronto_unchanged_via_upstream_cause():
    after = score_four_beat_story(toronto_upstream_story())
    cause = after['rules'][RULE_STATED_CAUSE]
    assert cause['passed']
    assert cause['detail']['pattern'] == 'upstream_cause'
    assert 'upstream cause cited' in cause['reason']
    # Disabling divergence must not change Toronto (it passes via upstream).
    before = score_four_beat_story(toronto_upstream_story(), _DIVERGENCE_OFF)
    assert before['rules'][RULE_STATED_CAUSE]['passed']
    assert before['rules'][RULE_STATED_CAUSE]['detail']['pattern'] == 'upstream_cause'


def test_divergence_requires_two_contrasted_dimensions():
    # A results+workload contrast passes; stripping the results dimension fails.
    story = miami_story()
    assert score_four_beat_story(story)['rules'][RULE_STATED_CAUSE]['passed']
    workload_only = miami_story()
    # Remove every results-dimension token, leaving only workload restatement.
    for field in ('human_frame', 'evidence_sentence', 'consequence_sentence'):
        text = workload_only['story_voice'][field]
        text = text.replace('run prevention', 'usage').replace('ERA', 'usage')
        workload_only['story_voice'][field] = text
    ev = workload_only['story_evidence']
    ev['evidence_statement'] = ev['evidence_statement'].replace('ERA', 'usage')
    ev['consequence_statement'] = ev['consequence_statement'].replace(
        'run prevention', 'usage'
    )
    workload_only['narrative'] = workload_only['narrative'].replace('results', 'usage')
    assert not score_four_beat_story(workload_only)['rules'][RULE_STATED_CAUSE]['passed']


def test_scorer_version_bumped():
    assert VERSION == '2026-06-21.v2'


def test_divergence_snapshot_average_rises():
    """Before/after over the snapshot cards: the three divergence flips lift the
    average and shift the rules-passed distribution upward; CWS/continuity hold."""
    four_beat = [
        san_diego_story(),
        miami_story(),
        detroit_divergence_story(),
        chicago_white_sox_story(),
        toronto_upstream_story(),
    ]
    note = continuity_109_note()

    before = [score_four_beat_story(s, _DIVERGENCE_OFF) for s in four_beat]
    before.append(score_continuity_note(note, _DIVERGENCE_OFF))
    after = [score_four_beat_story(s) for s in four_beat]
    after.append(score_continuity_note(note))

    before_summary = summarize_scorecards(before, _DIVERGENCE_OFF)
    after_summary = summarize_scorecards(after, DEFAULT_STORY_QUALITY_CONFIG)

    assert after_summary['average_score'] > before_summary['average_score']
    # Exactly three stories gained a rule (SD, MIA, DET); the rest are unchanged.
    gained = sum(
        1 for b, a in zip(before, after) if a['rules_passed'] == b['rules_passed'] + 1
    )
    assert gained == 3
    unchanged = sum(
        1 for b, a in zip(before, after) if a['rules_passed'] == b['rules_passed']
    )
    assert unchanged == len(after) - 3
