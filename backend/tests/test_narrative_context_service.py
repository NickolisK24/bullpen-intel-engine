"""Tests for the Narrative Context Engine (COIN Phase 3.5).

The engine is pure and deterministic: it reads a CompletedGameContext (here,
plain dicts mirroring the model) and returns structured, prose-free intelligence.
These cover each story shape, priority/importance rules, observation and fact
derivation, fail-closed behavior, determinism, and the absence of any prose.
"""

import re

from services.narrative_context_service import (
    CONTEXT_TYPE_COMPLETED_GAME,
    HEADLINE_BULLPEN_STABILIZED,
    IMPORTANCE_HIGH,
    IMPORTANCE_LOW,
    IMPORTANCE_MEDIUM,
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    STORY_VERSION,
    build_narrative_context,
    build_narrative_contexts,
)


_IDENTIFIER = re.compile(r'^[a-z0-9_]+$')
_ENUM = re.compile(r'^[A-Z]+$')


def _ctx(**over):
    """A completed-game context dict; defaults are all-null, override per test."""
    base = {
        'team_id': 1,
        'game_pk': 700,
        'confidence': 'HIGH',
        'bullpen_story_tag': None,
        'game_shape_created': None,
        'game_shape_protected': None,
        'lead_protected': None,
        'lead_lost': None,
        'comeback_completed': None,
        'lead_when_bullpen_entered': None,
        'deficit_when_bullpen_entered': None,
        'bullpen_entry_inning': None,
        'bullpen_entry_score_for': None,
        'bullpen_entry_score_against': None,
        'starter_exit_score_for': None,
        'starter_exit_score_against': None,
        'largest_lead': None,
        'largest_deficit': None,
        'late_runs_allowed': None,
        'runs_allowed_innings_7_to_9': None,
        'turning_inning': None,
        'starter_ip': None,
    }
    base.update(over)
    return base


def _lost_game_shape_ctx():
    return _ctx(
        bullpen_story_tag='lost_game_shape',
        game_shape_created='normal_start',
        game_shape_protected=False,
        lead_protected=False,
        lead_lost=True,
        lead_when_bullpen_entered=4,
        bullpen_entry_inning=7,
        bullpen_entry_score_for=4,
        bullpen_entry_score_against=0,
        starter_exit_score_for=4,
        starter_exit_score_against=0,
        largest_lead=4,
        largest_deficit=0,
        late_runs_allowed=7,
        runs_allowed_innings_7_to_9=5,
        turning_inning=8,
        starter_ip=6.0,
    )


# ── Lost game shape ───────────────────────────────────────────────────────────

def test_lost_game_shape_is_critical_with_late_pressure_secondary():
    nc = build_narrative_context(_lost_game_shape_ctx())
    assert nc.primary_story == 'lost_game_shape'
    assert nc.secondary_story == 'late_pressure_accumulated'
    assert nc.story_priority == PRIORITY_CRITICAL
    assert nc.confidence == 'HIGH'
    assert nc.headline_key == 'lost_game_shape'
    assert nc.summary_key == 'game_shape_not_protected'
    assert nc.game_importance == IMPORTANCE_HIGH
    assert nc.context_type == CONTEXT_TYPE_COMPLETED_GAME
    assert nc.story_version == STORY_VERSION

    assert 'starter_created_game_shape' in nc.supporting_observations
    assert 'lead_entering_bullpen' in nc.supporting_observations
    assert 'bullpen_lost_lead' in nc.supporting_observations
    assert 'multiple_late_runs' in nc.supporting_observations
    assert 'turning_point_identified' in nc.supporting_observations
    assert 'bullpen_preserved_lead' not in nc.supporting_observations

    assert nc.supporting_facts['largest_lead'] == 4
    assert nc.supporting_facts['late_runs_allowed'] == 7
    assert nc.supporting_facts['bullpen_entry_inning'] == 7
    assert nc.supporting_facts['lead_lost'] is True
    assert nc.supporting_facts['game_shape_created'] == 'normal_start'


# ── Protected game shape ──────────────────────────────────────────────────────

def test_protected_clean_hold_uses_bullpen_stabilized_headline():
    nc = build_narrative_context(_ctx(
        bullpen_story_tag='protected_game_shape',
        game_shape_created='normal_start',
        game_shape_protected=True,
        lead_protected=True,
        lead_lost=False,
        lead_when_bullpen_entered=2,
        bullpen_entry_inning=7,
        bullpen_entry_score_for=3,
        bullpen_entry_score_against=1,
        largest_lead=2,
        largest_deficit=0,
        late_runs_allowed=0,
        runs_allowed_innings_7_to_9=0,
        starter_ip=6.0,
    ))
    assert nc.primary_story == 'protected_game_shape'
    assert nc.story_priority == PRIORITY_HIGH
    assert nc.headline_key == HEADLINE_BULLPEN_STABILIZED
    assert nc.summary_key == 'game_shape_protected'
    assert nc.game_importance == IMPORTANCE_MEDIUM
    assert 'bullpen_preserved_lead' in nc.supporting_observations
    assert nc.supporting_facts['lead_protected'] is True


# ── Bullpen kept team alive ───────────────────────────────────────────────────

def test_bullpen_kept_team_alive_major_comeback_escalates_to_critical():
    nc = build_narrative_context(_ctx(
        bullpen_story_tag='bullpen_kept_team_alive',
        game_shape_created='normal_start',
        comeback_completed=True,
        deficit_when_bullpen_entered=4,
        bullpen_entry_inning=6,
        bullpen_entry_score_for=0,
        bullpen_entry_score_against=4,
        largest_lead=1,
        largest_deficit=4,
        late_runs_allowed=0,
        runs_allowed_innings_7_to_9=0,
        starter_ip=5.0,
    ))
    assert nc.primary_story == 'bullpen_kept_team_alive'
    assert nc.story_priority == PRIORITY_CRITICAL   # 4-run deficit erased
    assert nc.game_importance == IMPORTANCE_HIGH
    assert 'deficit_entering_bullpen' in nc.supporting_observations
    assert 'comeback_completed' in nc.supporting_observations


def test_bullpen_kept_team_alive_small_comeback_stays_high():
    nc = build_narrative_context(_ctx(
        bullpen_story_tag='bullpen_kept_team_alive',
        game_shape_created='normal_start',
        comeback_completed=True,
        deficit_when_bullpen_entered=1,
        largest_lead=1,
        largest_deficit=1,
        late_runs_allowed=0,
        runs_allowed_innings_7_to_9=0,
        starter_ip=5.0,
    ))
    assert nc.story_priority == PRIORITY_HIGH


# ── Bullpen overexposed (MEDIUM confidence) ───────────────────────────────────

def test_bullpen_overexposed_is_medium_priority():
    nc = build_narrative_context(_ctx(
        confidence='MEDIUM',
        bullpen_story_tag='bullpen_overexposed',
        game_shape_created='short_start',
        late_runs_allowed=1,
        runs_allowed_innings_7_to_9=1,
        starter_ip=3.0,
    ))
    assert nc.primary_story == 'bullpen_overexposed'
    assert nc.story_priority == PRIORITY_MEDIUM
    assert nc.headline_key == 'bullpen_overexposed'
    assert nc.summary_key == 'bullpen_carried_heavy_load'
    assert 'bullpen_worked_long' in nc.supporting_observations
    assert 'starter_created_game_shape' not in nc.supporting_observations
    assert nc.game_importance == IMPORTANCE_LOW


# ── Starter covered bullpen ───────────────────────────────────────────────────

def test_starter_covered_bullpen_uses_starter_carried_headline():
    nc = build_narrative_context(_ctx(
        confidence='MEDIUM',
        bullpen_story_tag='starter_covered_bullpen',
        game_shape_created='normal_start',
        late_runs_allowed=0,
        runs_allowed_innings_7_to_9=0,
        starter_ip=7.0,
    ))
    assert nc.primary_story == 'starter_covered_bullpen'
    assert nc.story_priority == PRIORITY_MEDIUM
    assert nc.headline_key == 'starter_carried_game'
    assert nc.summary_key == 'starter_limited_bullpen_exposure'
    assert 'deep_start' in nc.supporting_observations


# ── Fail-closed paths ─────────────────────────────────────────────────────────

def test_insufficient_context_tag_is_passed_through_as_insufficient():
    nc = build_narrative_context(_ctx(
        confidence='LOW', bullpen_story_tag='insufficient_context'
    ))
    assert nc.primary_story == 'insufficient_context'
    assert nc.story_priority == PRIORITY_LOW
    assert nc.secondary_story is None
    assert nc.supporting_observations == []
    assert nc.supporting_facts == {}


def test_low_confidence_fails_closed_even_with_a_real_tag():
    # A would-be CRITICAL story, but LOW confidence collapses it.
    ctx = _lost_game_shape_ctx()
    ctx['confidence'] = 'LOW'
    nc = build_narrative_context(ctx)
    assert nc.primary_story == 'insufficient_context'
    assert nc.story_priority == PRIORITY_LOW
    assert nc.game_importance == IMPORTANCE_LOW
    assert nc.supporting_observations == []
    assert nc.supporting_facts == {}
    assert nc.confidence == 'LOW'   # original confidence preserved


def test_none_context_fails_closed():
    nc = build_narrative_context(None)
    assert nc.primary_story == 'insufficient_context'
    assert nc.team_id is None and nc.game_pk is None


def test_unknown_tag_fails_closed():
    nc = build_narrative_context(_ctx(bullpen_story_tag='something_new'))
    assert nc.primary_story == 'insufficient_context'


# ── Priority ordering ─────────────────────────────────────────────────────────

def test_priority_ordering_across_story_types():
    cases = {
        'lost_game_shape': PRIORITY_CRITICAL,
        'protected_game_shape': PRIORITY_HIGH,
        'late_pressure_accumulated': PRIORITY_HIGH,
        'bullpen_overexposed': PRIORITY_MEDIUM,
        'starter_covered_bullpen': PRIORITY_MEDIUM,
    }
    ranks = {PRIORITY_CRITICAL: 3, PRIORITY_HIGH: 2, PRIORITY_MEDIUM: 1, PRIORITY_LOW: 0}
    for tag, expected in cases.items():
        nc = build_narrative_context(_ctx(
            confidence='HIGH', bullpen_story_tag=tag, game_shape_created='normal_start'
        ))
        assert nc.story_priority == expected, tag
    # CRITICAL outranks HIGH outranks MEDIUM outranks LOW.
    assert ranks[PRIORITY_CRITICAL] > ranks[PRIORITY_HIGH] > ranks[PRIORITY_MEDIUM] > ranks[PRIORITY_LOW]


# ── Supporting facts discipline ───────────────────────────────────────────────

def test_supporting_facts_only_include_known_values():
    nc = build_narrative_context(_ctx(
        confidence='MEDIUM',
        bullpen_story_tag='late_pressure_accumulated',
        game_shape_created='normal_start',
        largest_lead=2,
        largest_deficit=0,
        late_runs_allowed=3,
        runs_allowed_innings_7_to_9=3,
        starter_ip=5.0,
    ))
    facts = nc.supporting_facts
    # Present values appear...
    assert facts['largest_lead'] == 2
    assert facts['runs_allowed_innings_7_to_9'] == 3
    assert facts['game_shape_created'] == 'normal_start'
    # ...null fields never leak in.
    assert 'bullpen_entry_inning' not in facts
    assert 'turning_inning' not in facts
    assert 'lead_protected' not in facts


# ── Determinism ───────────────────────────────────────────────────────────────

def test_engine_is_deterministic():
    ctx = _lost_game_shape_ctx()
    first = build_narrative_context(ctx).to_dict()
    second = build_narrative_context(ctx).to_dict()
    first.pop('generated_at')
    second.pop('generated_at')
    assert first == second


def test_batch_helper_maps_each_context():
    results = build_narrative_contexts([
        _lost_game_shape_ctx(),
        _ctx(confidence='LOW', bullpen_story_tag='insufficient_context'),
    ])
    assert [r.primary_story for r in results] == ['lost_game_shape', 'insufficient_context']


# ── No prose generation ───────────────────────────────────────────────────────

def test_outputs_are_identifiers_not_prose():
    nc = build_narrative_context(_lost_game_shape_ctx())
    for key_value in (nc.primary_story, nc.secondary_story, nc.headline_key, nc.summary_key):
        assert key_value is None or _IDENTIFIER.match(key_value), key_value
    for obs in nc.supporting_observations:
        assert _IDENTIFIER.match(obs), obs
    for enum_value in (nc.story_priority, nc.confidence, nc.game_importance):
        assert _ENUM.match(enum_value), enum_value
    # Facts carry only structured primitives, never sentences.
    for value in nc.supporting_facts.values():
        assert isinstance(value, (int, bool, str))
        if isinstance(value, str):
            assert ' ' not in value
