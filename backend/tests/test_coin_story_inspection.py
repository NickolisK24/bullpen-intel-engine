"""Tests for COIN internal story inspection (manual, read-only).

The inspection service builds a StoryPackage through the orchestrator and renders
the existing writers, respecting publishability and writer_targets by default.
Most tests inject a narrative feed (pure, no DB); one DB-backed test confirms the
real read path mutates nothing.
"""

import json

import pytest
from flask import Flask

from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)
from utils.db import db
from models.completed_game_context import CompletedGameContext

from services.narrative_feed_builder import build_narrative_feed
from services import coin_story_inspection
from services.todays_story_editorial_review import (
    build_todays_story_editorial_review,
    write_todays_story_editorial_review,
)


def _completed_ctx(**over):
    base = {
        'team_id': 1, 'game_pk': 700, 'confidence': 'HIGH',
        'bullpen_story_tag': 'lost_game_shape', 'game_shape_created': 'normal_start',
        'game_shape_protected': False, 'lead_protected': False, 'lead_lost': True,
        'comeback_completed': False, 'lead_when_bullpen_entered': 4,
        'bullpen_entry_inning': 7, 'bullpen_entry_score_for': 4,
        'bullpen_entry_score_against': 0, 'largest_lead': 4, 'largest_deficit': 0,
        'late_runs_allowed': 7, 'runs_allowed_innings_7_to_9': 5, 'turning_inning': 8,
        'starter_ip': 6.0,
    }
    base.update(over)
    return base


def _team_context(optionality_band='thin'):
    return {
        'team_id': 1,
        'bullpen_optionality_context': {
            'context_available': True, 'available_arms_count': 5,
            'clean_workload_options': [{'player_id': 1}], 'secondary_options': [],
            'practical_close_game_paths_count': 3, 'optionality_band': optionality_band,
        },
        'bullpen_concentration_context': {'concentration_band': 'normal', 'window_days': 10,
                                          'bullpen_workload_total_10d': 240},
        'rotation_context': {}, 'role_stability_context': {'stability_band': 'stable'},
        'injury_context': {'depth_pressure_band': 'moderate'},
    }


def _feed(completed=None, team=None):
    return build_narrative_feed(
        1,
        completed_game_context=completed if completed is not None else _completed_ctx(),
        team_context=team if team is not None else _team_context(),
    )


def _inspect(feed, **kwargs):
    return coin_story_inspection.inspect_team_story(1, narrative_feed=feed, **kwargs)


# ── Builds a package + renders allowed writers ────────────────────────────────

def test_inspection_builds_package_for_team():
    out = _inspect(_feed())
    assert out['team_id'] == 1
    assert out['game_pk'] == 700
    assert out['publishable'] is True
    assert out['publish_reason'] == 'critical_narrative'
    assert out['recommended_surface'] == 'multiple'
    assert out['safe_time_context'] == 'AFTER_MOST_RECENT_GAME'
    assert out['writer_targets'] == ['team_story', 'dashboard', 'morning_brief']
    assert 'package' in out


def test_publishable_renders_all_targeted_writers():
    out = _inspect(_feed())
    rendered = {d['writer'] for d in out['drafts']}
    assert rendered == {'team_story', 'dashboard', 'morning_brief'}
    for draft in out['drafts']:
        assert draft['headline'] and draft['body']
        assert draft['text'] == f"{draft['headline']}\n{draft['body']}"
        assert isinstance(draft['metadata'], dict)
        assert draft['is_internal_preview'] is False


# ── Unpublishable behavior ────────────────────────────────────────────────────

def _low_feed():
    return _feed(completed=_completed_ctx(confidence='LOW',
                                          bullpen_story_tag='insufficient_context'))


def test_unpublishable_renders_no_drafts_by_default():
    out = _inspect(_low_feed())
    assert out['publishable'] is False
    assert out['publish_reason'] == 'insufficient_confidence'
    assert out['writer_targets'] == []
    assert out['drafts'] == []


def test_include_unpublishable_renders_internal_preview():
    out = _inspect(_low_feed(), include_unpublishable=True)
    assert out['publishable'] is False
    rendered = {d['writer'] for d in out['drafts']}
    assert rendered == {'team_story', 'dashboard', 'morning_brief'}
    assert all(d['is_internal_preview'] is True for d in out['drafts'])
    # Low-confidence drafts must not invent detail.
    for d in out['drafts']:
        assert 'run' not in d['body'].lower() or 'detail' in d['body'].lower()


# ── Writer filtering ──────────────────────────────────────────────────────────

def test_writer_filter_renders_single_writer():
    out = _inspect(_feed(), writer='dashboard')
    assert [d['writer'] for d in out['drafts']] == ['dashboard']


def test_unknown_writer_is_rejected():
    with pytest.raises(ValueError):
        _inspect(_feed(), writer='carousel')


def test_selected_writer_outside_targets_not_rendered_by_default():
    # A MEDIUM story targets team_story + dashboard only (no morning_brief).
    feed = _feed(completed=_completed_ctx(
        confidence='MEDIUM', bullpen_story_tag='bullpen_overexposed',
        game_shape_created='short_start', lead_lost=None, lead_protected=None,
    ))
    assert 'morning_brief' not in feed.to_dict()  # sanity: feed has no targets concept
    default = _inspect(feed, writer='morning_brief')
    assert default['drafts'] == []                 # outside targets -> not rendered

    override = _inspect(feed, writer='morning_brief', include_unpublishable=True)
    assert [d['writer'] for d in override['drafts']] == ['morning_brief']
    assert override['drafts'][0]['is_internal_preview'] is True


# ── Output is JSON-serializable / pretty ──────────────────────────────────────

def test_output_is_json_serializable():
    out = _inspect(_feed())
    encoded = json.dumps(out, sort_keys=True)
    pretty = json.dumps(out, indent=2, sort_keys=True)
    assert json.loads(encoded) == json.loads(pretty)


def test_todays_story_live_review_artifact_generation_succeeds(tmp_path):
    contexts = [
        _completed_ctx(
            team_id=1,
            game_pk=701,
            game_date='2026-06-28',
            bullpen_story_tag='starter_covered_bullpen',
            lead_lost=None,
            lead_protected=None,
            late_runs_allowed=0,
            runs_allowed_innings_7_to_9=0,
            starter_name='Logan Webb',
            starter_ip=7.3333,
            starter_pitch_count=101,
        ),
        _completed_ctx(
            team_id=2,
            game_pk=702,
            game_date='2026-06-28',
            confidence='LOW',
            bullpen_story_tag='insufficient_context',
        ),
    ]

    def inspect(team_id, **kwargs):
        return coin_story_inspection.inspect_team_story(
            team_id,
            completed_game_context=kwargs.get('completed_game_context'),
            team_context=_team_context(),
        )

    report = build_todays_story_editorial_review(
        reference_date='2026-06-28',
        candidate_contexts=contexts,
        inspect_fn=inspect,
        generated_at='2026-06-29T00:00:00',
        artifact_path='artifacts/todays_story_editorial_review_E2C5D_live.md',
        review_label='E2C-5D Live',
    )
    output = write_todays_story_editorial_review(
        report,
        tmp_path / 'todays_story_editorial_review_E2C5D_live.md',
    )
    text = output.read_text(encoding='utf-8')

    assert report['completed_game_context_rows_reviewed'] == 2
    assert report['completed_game_publishable_stories'] == 1
    assert report['completed_game_fallback_or_unpublishable_rows'] == 1
    assert report['banned_language_scan']['status'] == 'pass'
    assert report['retired_phrase_scan']['status'] == 'pass'
    assert report['impossible_innings_scan']['status'] == 'pass'
    assert report['artifact'] == 'artifacts/todays_story_editorial_review_E2C5D_live.md'
    assert report['starter_covered_specificity_check']['status'] == 'pass'
    assert report['completed_game_fallback_status']['status'] == 'pass'
    assert 'Homepage Lead Story' in text
    assert 'E2C-5D Live' in text
    assert 'Retired Phrase Scan' in text
    assert 'Starter-Covered Bullpen Specificity Check' in text
    assert 'Completed-Game Fallback Status' in text
    assert 'Completed-Game Story Corpus' in text
    assert '7.1 IP' in text
    assert 'No draft rendered.' in text


# ── DB-backed: real read path mutates nothing ─────────────────────────────────

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


def test_real_read_path_makes_no_db_writes(app):
    with app.app_context():
        db.session.add(CompletedGameContext(
            team_id=1, game_pk=900, confidence='LOW',
            bullpen_story_tag='insufficient_context',
        ))
        db.session.commit()
        before = CompletedGameContext.query.count()

    # Inject team_context to avoid the heavy bullpen pipeline, but let the package
    # read the most-recent CompletedGameContext from the DB (the real read path).
    out = coin_story_inspection.inspect_team_story(
        1, app=app, team_context={'team_id': 1}, completed_game_context=None,
    )

    with app.app_context():
        after = CompletedGameContext.query.count()
    assert before == after            # no rows added, changed, or removed
    assert out['team_id'] == 1
