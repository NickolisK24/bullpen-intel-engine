"""Tests for the COIN internal review corpus generator (manual, read-only).

The generator batches the existing inspection path across teams and shapes the
results into JSON and Markdown review artifacts. Tests inject an inspection
function (wrapping the real inspection with per-team feeds) so they stay pure,
and cover defaults, overrides, shape, drafts gating, per-team failure, filters,
and the no-mutation guarantee.
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
from services.coin_story_inspection import inspect_team_story
from services import coin_story_corpus
from services.coin_story_corpus import DEFAULT_TEAM_IDS, generate_corpus, render_markdown


def _completed_ctx(team_id, **over):
    base = {
        'team_id': team_id, 'game_pk': 700 + team_id, 'confidence': 'HIGH',
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


def _team_context(team_id):
    return {
        'team_id': team_id,
        'bullpen_optionality_context': {
            'context_available': True, 'available_arms_count': 5,
            'clean_workload_options': [{'player_id': 1}], 'secondary_options': [],
            'practical_close_game_paths_count': 3, 'optionality_band': 'thin',
        },
        'bullpen_concentration_context': {'concentration_band': 'normal', 'window_days': 10,
                                          'bullpen_workload_total_10d': 240},
        'rotation_context': {}, 'role_stability_context': {'stability_band': 'stable'},
        'injury_context': {'depth_pressure_band': 'moderate'},
    }


def _feed(team_id, completed_over=None):
    completed = _completed_ctx(team_id, **(completed_over or {}))
    return build_narrative_feed(team_id, completed_game_context=completed,
                                team_context=_team_context(team_id))


def _inspect_fn(feeds_by_team, *, fail_teams=()):
    """An inspect_fn that injects a per-team feed (and can fail chosen teams)."""
    def inspect(team_id, **kwargs):
        if team_id in fail_teams:
            raise RuntimeError(f'synthetic failure for {team_id}')
        kwargs.pop('app', None)
        return inspect_team_story(team_id, narrative_feed=feeds_by_team[team_id], **kwargs)
    return inspect


# ── Defaults / overrides ──────────────────────────────────────────────────────

def test_default_teams_are_the_four_targets():
    assert DEFAULT_TEAM_IDS == [137, 133, 139, 147]


def test_default_teams_used_when_none_provided():
    feeds = {tid: _feed(tid) for tid in DEFAULT_TEAM_IDS}
    corpus = generate_corpus(None, inspect_fn=_inspect_fn(feeds), generated_at='2026-06-20')
    assert corpus['team_ids'] == [137, 133, 139, 147]
    assert [e['team_id'] for e in corpus['entries']] == [137, 133, 139, 147]
    assert all(TEAM_label in coin_story_corpus.TEAM_LABELS for TEAM_label in (137, 133, 139, 147))


def test_explicit_team_ids_override_defaults():
    feeds = {137: _feed(137), 133: _feed(133)}
    corpus = generate_corpus([137, 133], inspect_fn=_inspect_fn(feeds))
    assert corpus['team_ids'] == [137, 133]


# ── JSON shape ────────────────────────────────────────────────────────────────

def test_generates_json_corpus_shape():
    feeds = {137: _feed(137)}
    corpus = generate_corpus([137], inspect_fn=_inspect_fn(feeds), generated_at='2026-06-20')
    assert set(corpus) == {'generated_at', 'reference_date', 'team_ids',
                           'include_unpublishable', 'writer_filter', 'entries'}
    entry = corpus['entries'][0]
    for key in ('team_id', 'game_pk', 'publishable', 'publish_reason', 'confidence',
                'story_priority', 'game_importance', 'recommended_surface',
                'safe_time_context', 'writer_targets', 'package', 'drafts', 'error'):
        assert key in entry
    # Whole corpus is JSON-serializable.
    assert json.loads(json.dumps(corpus, sort_keys=True))['team_ids'] == [137]


def test_publishable_team_includes_drafts():
    feeds = {137: _feed(137)}
    corpus = generate_corpus([137], inspect_fn=_inspect_fn(feeds))
    entry = corpus['entries'][0]
    assert entry['publishable'] is True
    assert {d['writer'] for d in entry['drafts']} == {'team_story', 'dashboard', 'morning_brief'}


def test_unpublishable_team_has_no_drafts_by_default():
    feeds = {137: _feed(137, completed_over={'confidence': 'LOW',
                                             'bullpen_story_tag': 'insufficient_context'})}
    corpus = generate_corpus([137], inspect_fn=_inspect_fn(feeds))
    entry = corpus['entries'][0]
    assert entry['publishable'] is False
    assert entry['drafts'] == []


def test_include_unpublishable_renders_preview():
    feeds = {137: _feed(137, completed_over={'confidence': 'LOW',
                                             'bullpen_story_tag': 'insufficient_context'})}
    corpus = generate_corpus([137], inspect_fn=_inspect_fn(feeds), include_unpublishable=True)
    entry = corpus['entries'][0]
    assert entry['drafts']
    assert all(d['is_internal_preview'] for d in entry['drafts'])


def test_writer_filter_is_passed_through():
    feeds = {137: _feed(137)}
    corpus = generate_corpus([137], writer='dashboard', inspect_fn=_inspect_fn(feeds))
    assert corpus['writer_filter'] == 'dashboard'
    assert [d['writer'] for d in corpus['entries'][0]['drafts']] == ['dashboard']


# ── Failure handling ──────────────────────────────────────────────────────────

def test_one_team_failure_does_not_fail_whole_corpus():
    feeds = {137: _feed(137), 139: _feed(139)}
    corpus = generate_corpus([137, 999, 139],
                             inspect_fn=_inspect_fn(feeds, fail_teams=(999,)))
    entries = {e['team_id']: e for e in corpus['entries']}
    assert entries[999]['error'] is not None
    assert entries[999]['drafts'] == []
    assert entries[137]['error'] is None
    assert entries[139]['error'] is None


def test_strict_mode_reraises():
    feeds = {137: _feed(137)}
    with pytest.raises(RuntimeError):
        generate_corpus([137, 999], strict=True,
                        inspect_fn=_inspect_fn(feeds, fail_teams=(999,)))


# ── Markdown ──────────────────────────────────────────────────────────────────

def test_generates_markdown_corpus_shape():
    feeds = {137: _feed(137)}
    corpus = generate_corpus([137], inspect_fn=_inspect_fn(feeds), generated_at='2026-06-20')
    md = render_markdown(corpus)
    assert md.startswith('# COIN Story Corpus')
    assert 'Generated at: 2026-06-20' in md
    assert '## Team 137 — Giants' in md
    assert '### Team Story' in md
    assert '### Dashboard' in md
    assert '### Morning Brief' in md
    assert 'Publishable: True' in md


def test_markdown_reports_no_draft_and_errors():
    feeds = {137: _feed(137, completed_over={'confidence': 'LOW',
                                             'bullpen_story_tag': 'insufficient_context'})}
    corpus = generate_corpus([137, 999],
                             inspect_fn=_inspect_fn(feeds, fail_teams=(999,)))
    md = render_markdown(corpus)
    assert 'No draft rendered.' in md          # unpublishable 137 has no drafts
    assert 'Error: ' in md                      # 999 failed


def test_write_artifacts_to_disk(tmp_path):
    feeds = {137: _feed(137)}
    corpus = generate_corpus([137], inspect_fn=_inspect_fn(feeds))
    json_path = tmp_path / 'corpus.json'
    md_path = tmp_path / 'corpus.md'
    coin_story_corpus.write_corpus_json(corpus, json_path, pretty=True)
    coin_story_corpus.write_corpus_markdown(corpus, md_path)
    assert json.loads(json_path.read_text())['team_ids'] == [137]
    assert md_path.read_text().startswith('# COIN Story Corpus')


# ── No DB mutation (real read path) ───────────────────────────────────────────

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
            team_id=137, game_pk=900, confidence='LOW',
            bullpen_story_tag='insufficient_context',
        ))
        db.session.commit()
        before = CompletedGameContext.query.count()

    # Inject team_context to skip the heavy bullpen pipeline, but let each team's
    # package read the latest CompletedGameContext from the DB (the real path).
    def inspect(team_id, **kwargs):
        kwargs.pop('completed_game_context', None)
        return inspect_team_story(team_id, team_context={'team_id': team_id}, **kwargs)

    corpus = generate_corpus([137], app=app, inspect_fn=inspect)

    with app.app_context():
        after = CompletedGameContext.query.count()
    assert before == after
    assert corpus['entries'][0]['team_id'] == 137
