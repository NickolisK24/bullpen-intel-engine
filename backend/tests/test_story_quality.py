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
    strict = StoryQualityConfig(gate_enabled=True, gate_threshold=100.0)
    published, held, _ = apply_story_quality_gate([detroit_story()], strict)
    assert published == []  # Detroit is < 100 and is held under a strict threshold
    lenient = StoryQualityConfig(gate_enabled=True, gate_threshold=20.0)
    published2, held2, _ = apply_story_quality_gate([detroit_story()], lenient)
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
