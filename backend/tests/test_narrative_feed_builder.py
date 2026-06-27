"""Tests for the Narrative Feed Builder (COIN Phase 3.75).

The builder assembles one deterministic editorial brief from already-derived
intelligence. Most tests inject the completed-game context and team context
directly (keeping the builder pure and free of DB / engine recomputation) and
assert the packaging, the recommended focus, and the safe time framing. One
DB-backed test exercises the real "no data" read path.
"""

import re

import pytest
from flask import Flask

from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)
from utils.db import db
from models.completed_game_context import CompletedGameContext  # noqa: F401 (registers table)

from services.narrative_feed_builder import (
    FEED_VERSION,
    FOCUS_GAME_CONTEXT,
    FOCUS_INSUFFICIENT_CONTEXT,
    FOCUS_LATE_INNING_EXECUTION,
    FOCUS_MULTIPLE_STORYLINES,
    FOCUS_WORKLOAD_PRESSURE,
    TIME_AFTER_MOST_RECENT_GAME,
    TIME_CURRENT_STATUS,
    TIME_INSUFFICIENT_CONTEXT,
    build_narrative_feed,
)


_IDENTIFIER = re.compile(r'^[a-z0-9_]+$')
_ENUM = re.compile(r'^[A-Z_]+$')


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


def _team_context(*, optionality_band='insufficient_data', concentration_band='normal'):
    return {
        'team_id': 1,
        'team': {'team_id': 1, 'team_name': 'Home Club', 'team_abbreviation': 'HME'},
        'reference_date': '2026-06-20',
        'bullpen_optionality_context': {
            'context_available': True,
            'available_arms_count': 5,
            'monitor_arms_count': 1,
            'limited_arms_count': 1,
            'restricted_arms_count': 2,
            'unavailable_arms_count': 1,
            'unknown_status_count': 0,
            'clean_workload_options': [{'player_id': 1}, {'player_id': 2}, {'player_id': 3}],
            'secondary_options': [{'player_id': 4}],
            'practical_close_game_paths_count': 3,
            'optionality_band': optionality_band,
        },
        'bullpen_concentration_context': {
            'bullpen_workload_total_10d': 240,
            'bullpen_workload_appearances_10d': 22,
            'top_three_workload_share_10d': 48.0,
            'concentration_band': concentration_band,
            'window_days': 10,
        },
        'rotation_context': {
            'bullpen_coverage_ip_7d': 9.5,
            'early_bullpen_entry_rate': 0.3,
        },
        'role_stability_context': {
            'stability_band': 'stable',
            'core_retention_count': 3,
        },
        'injury_context': {
            'depth_pressure_band': 'moderate',
            'inactive_bullpen_arms_count': 1,
        },
    }


# ── Complete feed assembly ────────────────────────────────────────────────────

def test_complete_feed_builds_with_all_layers():
    feed = build_narrative_feed(
        1, completed_game_context=_completed_ctx(), team_context=_team_context()
    )
    assert feed.team_id == 1
    assert feed.game_pk == 700
    assert feed.feed_version == FEED_VERSION
    assert feed.confidence == 'HIGH'
    assert feed.primary_narrative == 'lost_game_shape'
    assert feed.secondary_narrative == 'late_pressure_accumulated'
    assert feed.story_priority == 'CRITICAL'
    assert feed.headline_key == 'lost_game_shape'
    assert feed.summary_key == 'game_shape_not_protected'
    assert feed.generated_at is not None


def test_feed_embeds_narrative_context_and_completed_context():
    feed = build_narrative_feed(
        1, completed_game_context=_completed_ctx(), team_context=_team_context()
    )
    assert feed.narrative_context['primary_story'] == 'lost_game_shape'
    assert feed.narrative_context['primary_story'] == feed.primary_narrative
    # Top-level mirrors are consistent with the embedded narrative context.
    assert feed.supporting_observations == feed.narrative_context['supporting_observations']
    assert feed.supporting_facts == feed.narrative_context['supporting_facts']
    assert feed.completed_game_context['game_pk'] == 700


# ── Snapshot packaging (read, do not recompute) ───────────────────────────────

def test_availability_snapshot_is_read_from_optionality_layer():
    feed = build_narrative_feed(
        1, completed_game_context=_completed_ctx(), team_context=_team_context()
    )
    snap = feed.availability_snapshot
    assert snap['context_available'] is True
    assert snap['available_arms_count'] == 5
    assert snap['limited_arms_count'] == 1
    assert snap['unavailable_arms_count'] == 1


def test_workload_snapshot_is_read_from_concentration_and_rotation():
    feed = build_narrative_feed(
        1, completed_game_context=_completed_ctx(), team_context=_team_context()
    )
    snap = feed.workload_snapshot
    assert snap['bullpen_workload_total_10d'] == 240
    assert snap['top_three_workload_share_10d'] == 48.0
    assert snap['concentration_band'] == 'normal'
    assert snap['bullpen_coverage_ip_7d'] == 9.5


def test_bullpen_snapshot_is_read_from_optionality_stability_injury():
    feed = build_narrative_feed(
        1, completed_game_context=_completed_ctx(), team_context=_team_context()
    )
    snap = feed.bullpen_snapshot
    assert snap['clean_options_count'] == 3
    assert snap['secondary_options_count'] == 1
    assert snap['practical_close_game_paths_count'] == 3
    assert snap['stability_band'] == 'stable'
    assert snap['depth_pressure_band'] == 'moderate'


def test_no_additional_intelligence_is_created():
    # Every snapshot value must match its source field verbatim (pure packaging).
    team_context = _team_context()
    feed = build_narrative_feed(1, completed_game_context=_completed_ctx(),
                                team_context=team_context)
    opt = team_context['bullpen_optionality_context']
    conc = team_context['bullpen_concentration_context']
    assert feed.availability_snapshot['available_arms_count'] == opt['available_arms_count']
    assert feed.workload_snapshot['bullpen_workload_total_10d'] == conc['bullpen_workload_total_10d']
    assert feed.bullpen_snapshot['practical_close_game_paths_count'] == opt['practical_close_game_paths_count']


def test_missing_team_context_yields_empty_snapshots_not_an_error():
    feed = build_narrative_feed(1, completed_game_context=_completed_ctx(), team_context={})
    assert feed.availability_snapshot['context_available'] is False
    assert feed.availability_snapshot['available_arms_count'] is None
    assert feed.workload_snapshot['concentration_band'] is None
    assert feed.bullpen_snapshot['clean_options_count'] is None
    # The game narrative still stands on its own.
    assert feed.primary_narrative == 'lost_game_shape'


# ── Recommended story focus ───────────────────────────────────────────────────

def test_focus_is_game_context_for_a_clean_game_story():
    feed = build_narrative_feed(
        1, completed_game_context=_completed_ctx(), team_context=_team_context()
    )
    assert feed.recommended_story_focus == FOCUS_GAME_CONTEXT


def test_focus_is_multiple_storylines_when_bullpen_state_also_notable():
    feed = build_narrative_feed(
        1,
        completed_game_context=_completed_ctx(),
        team_context=_team_context(optionality_band='thin'),
    )
    assert feed.recommended_story_focus == FOCUS_MULTIPLE_STORYLINES


def test_focus_maps_late_pressure_to_late_inning_execution():
    feed = build_narrative_feed(
        1,
        completed_game_context=_completed_ctx(
            bullpen_story_tag='late_pressure_accumulated', lead_lost=None, lead_protected=None
        ),
        team_context=_team_context(),
    )
    assert feed.recommended_story_focus == FOCUS_LATE_INNING_EXECUTION


def test_focus_maps_overexposed_to_workload_pressure():
    feed = build_narrative_feed(
        1,
        completed_game_context=_completed_ctx(
            confidence='MEDIUM', bullpen_story_tag='bullpen_overexposed',
            game_shape_created='short_start', lead_lost=None, lead_protected=None,
        ),
        team_context=_team_context(),
    )
    assert feed.recommended_story_focus == FOCUS_WORKLOAD_PRESSURE


# ── Safe time context ─────────────────────────────────────────────────────────

def test_safe_time_is_after_most_recent_game_for_valid_narrative():
    feed = build_narrative_feed(
        1, completed_game_context=_completed_ctx(), team_context=_team_context()
    )
    assert feed.safe_time_context == TIME_AFTER_MOST_RECENT_GAME


def test_safe_time_is_current_status_for_low_confidence():
    feed = build_narrative_feed(
        1,
        completed_game_context=_completed_ctx(confidence='LOW',
                                              bullpen_story_tag='insufficient_context'),
        team_context=_team_context(),
    )
    assert feed.recommended_story_focus == FOCUS_INSUFFICIENT_CONTEXT
    assert feed.safe_time_context == TIME_CURRENT_STATUS


# ── Determinism + no prose ────────────────────────────────────────────────────

def test_feed_is_deterministic():
    ctx, team = _completed_ctx(), _team_context()
    first = build_narrative_feed(1, completed_game_context=ctx, team_context=team).to_dict()
    second = build_narrative_feed(1, completed_game_context=ctx, team_context=team).to_dict()
    for payload in (first, second):
        payload.pop('generated_at')
        payload['narrative_context'].pop('generated_at')
    assert first == second


def test_feed_outputs_are_identifiers_not_prose():
    feed = build_narrative_feed(
        1, completed_game_context=_completed_ctx(), team_context=_team_context()
    )
    for value in (feed.primary_narrative, feed.secondary_narrative,
                  feed.headline_key, feed.summary_key, feed.recommended_story_focus):
        assert value is None or _IDENTIFIER.match(value), value
    for value in (feed.story_priority, feed.confidence, feed.game_importance,
                  feed.safe_time_context):
        assert _ENUM.match(value), value
    for obs in feed.supporting_observations:
        assert _IDENTIFIER.match(obs), obs


# ── DB-backed: real "no data" read path ───────────────────────────────────────

@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def test_no_completed_context_in_db_fails_closed(app):
    # No CompletedGameContext rows exist; team_context injected as empty.
    feed = build_narrative_feed(1, completed_game_context=None, team_context={})
    assert feed.primary_narrative == 'insufficient_context'
    assert feed.recommended_story_focus == FOCUS_INSUFFICIENT_CONTEXT
    assert feed.safe_time_context == TIME_INSUFFICIENT_CONTEXT
    assert feed.completed_game_context is None
