"""Tests for the Story Writers (COIN Phase 4).

Writers are translators: each consumes one NarrativeFeed and renders prose with
no baseball reasoning. These build real feeds (via the Phase 3.75 builder with
injected context) and assert translation, governance (feed-only, deterministic),
respect for confidence and safe-time framing, and that the fail-closed path never
invents detail.
"""

import os
import re

from services.narrative_feed_builder import build_narrative_feed
from story_writers import (
    DashboardStoryWriter,
    MorningBriefWriter,
    StoryDraft,
    TeamStoryWriter,
)

_WRITERS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            'story_writers')
_FORBIDDEN_FUTURE = ('tomorrow', 'tonight', 'next game', 'next week', 'upcoming', 'series')


def _completed_ctx(**over):
    base = {
        'team_id': 1,
        'game_pk': 700,
        'confidence': 'HIGH',
        'bullpen_story_tag': 'lost_game_shape',
        'game_shape_created': 'normal_start',
        'game_shape_protected': False,
        'lead_protected': False,
        'lead_lost': True,
        'comeback_completed': False,
        'lead_when_bullpen_entered': 4,
        'deficit_when_bullpen_entered': None,
        'bullpen_entry_inning': 7,
        'bullpen_entry_score_for': 4,
        'bullpen_entry_score_against': 0,
        'starter_exit_score_for': 4,
        'starter_exit_score_against': 0,
        'largest_lead': 4,
        'largest_deficit': 0,
        'late_runs_allowed': 7,
        'runs_allowed_innings_7_to_9': 5,
        'turning_inning': 8,
        'starter_ip': 6.0,
    }
    base.update(over)
    return base


def _team_context(*, optionality_band='thin', concentration_band='normal',
                  available_arms_count=5):
    return {
        'team_id': 1,
        'bullpen_optionality_context': {
            'context_available': True,
            'available_arms_count': available_arms_count,
            'limited_arms_count': 1,
            'unavailable_arms_count': 1,
            'clean_workload_options': [{'player_id': 1}, {'player_id': 2}],
            'secondary_options': [{'player_id': 4}],
            'practical_close_game_paths_count': 3,
            'optionality_band': optionality_band,
        },
        'bullpen_concentration_context': {
            'bullpen_workload_total_10d': 240,
            'top_three_workload_share_10d': 48.0,
            'concentration_band': concentration_band,
            'window_days': 10,
        },
        'rotation_context': {'bullpen_coverage_ip_7d': 9.5},
        'role_stability_context': {'stability_band': 'stable'},
        'injury_context': {'depth_pressure_band': 'moderate'},
    }


def _feed(completed=None, team=None):
    return build_narrative_feed(
        1,
        completed_game_context=completed if completed is not None else _completed_ctx(),
        team_context=team if team is not None else _team_context(),
    )


def _low_feed():
    return build_narrative_feed(
        1,
        completed_game_context=_completed_ctx(confidence='LOW',
                                              bullpen_story_tag='insufficient_context'),
        team_context=_team_context(),
    )


# ── Consumes only the feed (object or dict) ───────────────────────────────────

def test_writer_accepts_feed_object_or_its_dict_identically():
    feed = _feed()
    from_obj = TeamStoryWriter(feed).write().to_dict()
    from_dict = TeamStoryWriter(feed.to_dict()).write().to_dict()
    assert from_obj == from_dict


def test_writer_rejects_non_feed_input():
    import pytest
    with pytest.raises(TypeError):
        TeamStoryWriter(42).write()


# ── Governance: no engine/DB access inside writers ────────────────────────────

def test_writer_modules_do_not_import_engines_or_database():
    forbidden = ('from services', 'import services', 'from models', 'import models',
                 'utils.db', 'from app', 'import app')
    for name in os.listdir(_WRITERS_DIR):
        if not name.endswith('.py'):
            continue
        source = open(os.path.join(_WRITERS_DIR, name), encoding='utf-8').read()
        for token in forbidden:
            assert token not in source, f'{name} references {token!r}'


# ── Different writers, different styles from one feed ─────────────────────────

def test_writers_render_the_same_feed_in_different_styles():
    feed = _feed()
    team = TeamStoryWriter(feed).write()
    dashboard = DashboardStoryWriter(feed).write()
    brief = MorningBriefWriter(feed).write()

    assert team.writer == 'team_story'
    assert dashboard.writer == 'dashboard'
    assert brief.writer == 'morning_brief'
    bodies = {team.body, dashboard.body, brief.body}
    assert len(bodies) == 3                       # all distinct
    assert len(dashboard.body) < len(team.body)   # dashboard is the most concise
    assert brief.headline.startswith('Bullpen note:')
    assert 'Available arms: 5.' in brief.body


# ── Translation reflects the feed's facts ─────────────────────────────────────

def test_team_story_translates_lost_game_shape_facts():
    # A bare feed (no evidence_blocks) composes from the narrative facts: the
    # numbers read as words and the lead slips away in the late innings.
    draft = TeamStoryWriter(_feed()).write()
    assert draft.headline == 'Lead surrendered late'
    assert draft.body.startswith('After their most recent game,')
    assert 'four-run lead' in draft.body
    assert 'seven runs' in draft.body
    assert 'slipped away in the late innings' in draft.body


def test_protected_uses_feed_headline_key():
    feed = _feed(completed=_completed_ctx(
        bullpen_story_tag='protected_game_shape',
        lead_protected=True, lead_lost=False,
        largest_lead=2, late_runs_allowed=0, runs_allowed_innings_7_to_9=0,
    ))
    # headline_key becomes bullpen_stabilized (protected + zero late runs).
    assert feed.headline_key == 'bullpen_stabilized'
    assert TeamStoryWriter(feed).write().headline == 'Bullpen slammed the door'


# ── Confidence respected: LOW never invents ───────────────────────────────────

def test_low_confidence_never_invents_detail():
    feed = _low_feed()
    for writer_cls in (TeamStoryWriter, DashboardStoryWriter, MorningBriefWriter):
        draft = writer_cls(feed).write()
        text = draft.text
        assert draft.confidence == 'LOW'
        # No fabricated scores, leads, or innings.
        assert not re.search(r'\d+-run', text)
        assert 'lead' not in text.lower() or 'detail' in text.lower()
        assert 'inning' not in text.lower()
    # Team writer falls back to the neutral headline.
    assert TeamStoryWriter(feed).write().headline == 'Not enough detail yet'


# ── Safe time context respected ───────────────────────────────────────────────

def test_safe_time_after_most_recent_game_prefix():
    draft = TeamStoryWriter(_feed()).write()
    assert draft.safe_time_context == 'AFTER_MOST_RECENT_GAME'
    assert draft.body.startswith('After their most recent game,')


def test_safe_time_current_status_prefix_on_low_confidence():
    draft = TeamStoryWriter(_low_feed()).write()
    assert draft.safe_time_context == 'CURRENT_STATUS'
    assert draft.body.startswith('Currently,')


def test_no_future_language_across_story_shapes():
    shapes = [
        _completed_ctx(),  # lost
        _completed_ctx(bullpen_story_tag='protected_game_shape', lead_protected=True,
                       lead_lost=False, largest_lead=2, late_runs_allowed=1),
        _completed_ctx(bullpen_story_tag='bullpen_kept_team_alive', comeback_completed=True,
                       lead_lost=None, lead_protected=None, deficit_when_bullpen_entered=4,
                       largest_deficit=4),
        _completed_ctx(confidence='MEDIUM', bullpen_story_tag='bullpen_overexposed',
                       game_shape_created='short_start', lead_lost=None, lead_protected=None),
        _completed_ctx(confidence='LOW', bullpen_story_tag='insufficient_context'),
    ]
    for completed in shapes:
        feed = _feed(completed=completed)
        for writer_cls in (TeamStoryWriter, DashboardStoryWriter, MorningBriefWriter):
            text = writer_cls(feed).write().text.lower()
            for term in _FORBIDDEN_FUTURE:
                assert term not in text, (completed['bullpen_story_tag'], term)


# ── Determinism ───────────────────────────────────────────────────────────────

def test_same_feed_always_produces_identical_story():
    feed = _feed()
    for writer_cls in (TeamStoryWriter, DashboardStoryWriter, MorningBriefWriter):
        first = writer_cls(feed).write().to_dict()
        second = writer_cls(feed).write().to_dict()
        assert first == second


def test_draft_is_a_story_draft_with_governance_metadata():
    draft = TeamStoryWriter(_feed()).write()
    assert isinstance(draft, StoryDraft)
    assert draft.story_priority == 'CRITICAL'
    assert draft.recommended_story_focus  # carried from the feed, not computed here
    assert draft.team_id == 1 and draft.game_pk == 700
