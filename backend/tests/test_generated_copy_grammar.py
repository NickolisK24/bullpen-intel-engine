"""Grammar and determinism contracts for BaseballOS-generated public copy.

Two composition defects are pinned here, each fixed structurally at its owner
rather than patched in the rendered sentence:

1. **Time framing.** One prefix served two kinds of sentence. "After their most
   recent game, Merrill Kelly worked 6.0 innings" is temporally wrong -- he
   worked them *in* the game. In-game narratives now take an in-game framing,
   and a sentence that already names the starter and his innings carries no
   prefix at all, because it has located the game by itself.

2. **What Changed context.** Secondary phrases are independent clauses
   ("coverage also stabilized"), so they cannot follow "including", which needs
   a noun phrase -- that produced "...including coverage also stabilized." The
   multi-item frame now introduces the clause with a colon.

The determinism cases are the load-bearing ones: this package changed *which*
deterministic wording is chosen, never *whether* the wording is deterministic.
No randomness was introduced anywhere.
"""

from services.what_changed_since_yesterday import (
    CHANGE_COVERAGE_SAFETY,
    CHANGE_IDENTITY,
    CHANGE_RESOURCE_HEALTH,
    CHANGE_RESTED_OPTIONS,
    CHANGE_TRUST_STRUCTURE,
    CHANGE_USABLE_DEPTH,
)
from services.what_changed_since_yesterday_copy import _context
from story_writers import DashboardStoryWriter, MorningBriefWriter, TeamStoryWriter
from story_orchestrator import build_story_package


# ── fixtures ────────────────────────────────────────────────────────────────

def _completed(**over):
    base = {
        'team_id': 1, 'game_pk': 700, 'confidence': 'HIGH',
        'bullpen_story_tag': 'lost_game_shape', 'game_shape_created': 'normal_start',
        'team_name': 'the Giants', 'lead_protected': False, 'lead_lost': True,
        'lead_when_bullpen_entered': 4, 'bullpen_entry_inning': 7,
        'bullpen_entry_score_for': 6, 'bullpen_entry_score_against': 2,
        'largest_lead': 4, 'largest_deficit': 3, 'late_runs_allowed': 7,
        'runs_allowed_innings_7_to_9': 7, 'turning_inning': 8,
        'starter_name': 'Landen Roupp', 'starter_ip': 6.0, 'starter_pitch_count': 95,
        'starter_exit_inning': 6,
        'key_relief_appearances': [
            {'name': 'Ryan Walker', 'innings': 0.2, 'runs_allowed': 4},
            {'name': 'Tyler Rogers', 'innings': 1.0, 'runs_allowed': 3},
        ],
    }
    base.update(over)
    return base


def _team_ctx():
    return {
        'team_id': 1,
        'bullpen_optionality_context': {
            'context_available': True, 'available_arms_count': 3,
            'clean_workload_options': [
                {'player_id': 0, 'name': 'Erik Miller', 'availability': 'Available'},
            ],
            'secondary_options': [], 'practical_close_game_paths_count': 2,
            'optionality_band': 'thin',
        },
        'bullpen_concentration_context': {'concentration_band': 'concentrated', 'window_days': 10},
        'rotation_context': {}, 'role_stability_context': {'stability_band': 'stable'},
        'injury_context': {'depth_pressure_band': 'moderate'},
    }


def _draft(writer=TeamStoryWriter, **over):
    package = build_story_package(
        over.get('team_id', 1),
        completed_game_context=_completed(**over),
        team_context=_team_ctx(),
    )
    return writer(package).write()


NARRATIVES = (
    dict(bullpen_story_tag='lost_game_shape', lead_lost=True, lead_protected=False),
    dict(bullpen_story_tag='protected_game_shape', lead_lost=False, lead_protected=True,
         late_runs_allowed=0, runs_allowed_innings_7_to_9=0),
    dict(bullpen_story_tag='bullpen_kept_team_alive', lead_lost=False, lead_protected=False,
         largest_deficit=3, lead_when_bullpen_entered=None),
    dict(bullpen_story_tag='bullpen_overexposed', starter_ip=2.0, starter_exit_inning=3,
         lead_lost=False, lead_protected=False),
    dict(bullpen_story_tag='starter_covered_bullpen', starter_ip=8.0, starter_exit_inning=8,
         late_runs_allowed=0, lead_lost=False, lead_protected=True),
    dict(bullpen_story_tag='late_pressure_accumulated', lead_lost=False, lead_protected=False),
)
WRITERS = (TeamStoryWriter, DashboardStoryWriter, MorningBriefWriter)


# ── time-prefix grammar ─────────────────────────────────────────────────────

def test_no_story_says_a_starter_worked_innings_after_the_game():
    """The audit's sentence: the innings happened in the game, not after it."""
    for writer in WRITERS:
        for narrative in NARRATIVES:
            body = _draft(writer, **narrative).body
            assert 'After their most recent game' not in body, (writer.__name__, body)


def test_an_in_game_narrative_uses_in_game_framing_or_none():
    for writer in WRITERS:
        for narrative in NARRATIVES:
            body = _draft(writer, **narrative).body
            if 'most recent game' in body:
                assert body.startswith('In their most recent game,'), body


def test_a_starter_anchored_opener_carries_no_time_prefix():
    """A sentence naming the starter and his innings has located the game."""
    body = _draft(TeamStoryWriter).body
    assert body.startswith('Landen Roupp gave the Giants'), body
    assert 'most recent game' not in body.split('.')[0], body


def test_the_time_prefix_is_still_gated_on_safe_time_context():
    """Narrowing the prefix must not let writers invent temporal framing."""
    draft = _draft(TeamStoryWriter)
    assert draft.safe_time_context == 'AFTER_MOST_RECENT_GAME'
    for forbidden in ('tomorrow', 'tonight', 'next game', 'upcoming'):
        assert forbidden not in draft.body.lower()


def test_the_shared_opener_no_longer_dominates_the_corpus():
    """Pathological collapse guard, not a uniqueness quota.

    Before this package 61% of rendered stories opened with one identical
    clause. Different narratives should not all sound like the same sentence.
    """
    openers = []
    for writer in WRITERS:
        for index, narrative in enumerate(NARRATIVES):
            over = dict(narrative)
            over['game_pk'] = 7000 + index
            openers.append(_draft(writer, **over).body.split(',')[0])
    most_common = max(openers.count(opener) for opener in openers)
    assert most_common / len(openers) <= 0.55, (
        f'{most_common}/{len(openers)} stories share one opener'
    )


# ── What Changed composition ────────────────────────────────────────────────

def _change(change_type, direction, count=5):
    return {
        'change_type': change_type,
        'change_direction': direction,
        'previous_value': 1,
        'current_value': count,
    }


def test_zero_context_items_produce_no_sentence():
    top = _change(CHANGE_RESTED_OPTIONS, 'increased')
    assert _context([top], top) is None


def test_one_context_item_reads_as_a_clause_after_a_colon():
    top = _change(CHANGE_RESTED_OPTIONS, 'increased')
    other = _change(CHANGE_COVERAGE_SAFETY, 'improved')
    text = _context([top, other], top)
    assert text == 'There is another meaningful shift here: coverage also stabilized.'


def test_two_context_items_do_not_say_including_a_clause():
    top = _change(CHANGE_RESTED_OPTIONS, 'increased')
    others = [_change(CHANGE_COVERAGE_SAFETY, 'improved'), _change(CHANGE_USABLE_DEPTH, 'increased')]
    text = _context([top, *others], top)
    assert 'including coverage also stabilized' not in text
    assert text == (
        'There are two other meaningful shifts here: coverage also stabilized.'
    )


def test_three_context_items_stay_grammatical():
    top = _change(CHANGE_RESTED_OPTIONS, 'increased')
    others = [
        _change(CHANGE_COVERAGE_SAFETY, 'improved'),
        _change(CHANGE_USABLE_DEPTH, 'increased'),
        _change(CHANGE_TRUST_STRUCTURE, 'expanded'),
    ]
    text = _context([top, *others], top)
    assert ', including ' not in text
    assert text.startswith('There are ')
    assert text.endswith('.')


def test_no_context_sentence_ever_puts_a_clause_after_including():
    """Every phrase in the table is an independent clause, so none may."""
    top = _change(CHANGE_RESTED_OPTIONS, 'increased')
    families = (
        (CHANGE_RESTED_OPTIONS, 'decreased'), (CHANGE_USABLE_DEPTH, 'increased'),
        (CHANGE_USABLE_DEPTH, 'decreased'), (CHANGE_COVERAGE_SAFETY, 'improved'),
        (CHANGE_COVERAGE_SAFETY, 'worsened'), (CHANGE_TRUST_STRUCTURE, 'expanded'),
        (CHANGE_TRUST_STRUCTURE, 'narrowed'), (CHANGE_RESOURCE_HEALTH, 'improved'),
        (CHANGE_RESOURCE_HEALTH, 'worsened'), (CHANGE_IDENTITY, 'changed'),
    )
    for change_type, direction in families:
        for extra in (1, 2, 3):
            others = [_change(change_type, direction)] * extra
            text = _context([top, *others], top)
            assert text is None or ', including ' not in text, (change_type, direction, text)


# ── determinism (mandatory) ─────────────────────────────────────────────────

def test_identical_input_yields_byte_identical_story_across_repeats():
    for writer in WRITERS:
        for narrative in NARRATIVES:
            runs = [_draft(writer, **narrative).body for _ in range(3)]
            assert runs[0] == runs[1] == runs[2], (writer.__name__, runs)


def test_identical_input_yields_byte_identical_headline_across_repeats():
    for writer in WRITERS:
        runs = [_draft(writer).headline for _ in range(3)]
        assert len(set(runs)) == 1, runs


def test_identical_input_yields_byte_identical_what_changed_context():
    top = _change(CHANGE_RESTED_OPTIONS, 'increased')
    others = [_change(CHANGE_COVERAGE_SAFETY, 'improved'), _change(CHANGE_USABLE_DEPTH, 'increased')]
    runs = [_context([top, *others], top) for _ in range(3)]
    assert len(set(runs)) == 1, runs


def test_the_writers_introduce_no_randomness():
    """A structural check: variant selection stays hash-of-evidence based."""
    import story_writers.base_story_writer as base
    source = open(base.__file__, encoding='utf-8').read()
    for banned in ('import random', 'random.choice', 'random.shuffle', 'shuffle('):
        assert banned not in source, banned
