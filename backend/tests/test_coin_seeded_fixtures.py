"""Tests for COIN seeded fixture corpus mode (review-only).

Seeded mode runs deterministic CompletedGameContext fixtures through the real
COIN pipeline so story quality can be reviewed without a populated database.
These cover the fixture-to-story mapping, the SEEDED_FIXTURE_REVIEW marker and
warning, the no-DB / no-MLB guarantees, and that non-seeded behavior is intact.
"""

import json

from services import coin_story_corpus
from services.coin_story_corpus import generate_corpus, render_markdown
from services.coin_seeded_fixtures import (
    MODE_SEEDED_FIXTURE_REVIEW,
    SEEDED_FIXTURES,
    SEEDED_REVIEW_WARNING,
    SEEDED_TEAM_IDS,
)


def _seeded():
    return generate_corpus(seeded=True, generated_at='2026-06-25')


def _entries_by_team(corpus):
    return {e['team_id']: e for e in corpus['entries']}


# ── Defaults / completeness ───────────────────────────────────────────────────

def test_seeded_mode_uses_the_four_review_teams():
    assert SEEDED_TEAM_IDS == [137, 133, 139, 147]
    corpus = _seeded()
    assert corpus['team_ids'] == [137, 133, 139, 147]
    assert [e['team_id'] for e in corpus['entries']] == [137, 133, 139, 147]


def test_all_seeded_entries_are_generated_without_error():
    corpus = _seeded()
    assert len(corpus['entries']) == 4
    assert all(e['error'] is None for e in corpus['entries'])


# ── Expected stories match actual package stories ─────────────────────────────

def test_expected_primary_stories_match_actual():
    entries = _entries_by_team(_seeded())
    for fixture in SEEDED_FIXTURES:
        entry = entries[fixture['team_id']]
        assert entry['expected_primary_story'] == fixture['expected_primary_story']
        assert entry['primary_story'] == fixture['expected_primary_story']
        assert entry['fixture_name'] == fixture['fixture_name']


def test_seeded_giants_is_publishable_lost_game_shape():
    e = _entries_by_team(_seeded())[137]
    assert e['primary_story'] == 'lost_game_shape'
    assert e['publishable'] is True
    assert {d['writer'] for d in e['drafts']} == {'team_story', 'dashboard', 'morning_brief'}


def test_seeded_athletics_is_publishable_bullpen_kept_team_alive():
    e = _entries_by_team(_seeded())[133]
    assert e['primary_story'] == 'bullpen_kept_team_alive'
    assert e['publishable'] is True


def test_seeded_rays_is_publishable_protected_game_shape():
    e = _entries_by_team(_seeded())[139]
    assert e['primary_story'] == 'protected_game_shape'
    assert e['publishable'] is True


def test_seeded_yankees_is_publishable_bullpen_overexposed():
    e = _entries_by_team(_seeded())[147]
    assert e['primary_story'] == 'bullpen_overexposed'
    assert e['publishable'] is True
    # MEDIUM story: no morning brief target.
    assert {d['writer'] for d in e['drafts']} == {'team_story', 'dashboard'}


# ── Mode marker / Markdown warning ────────────────────────────────────────────

def test_seeded_json_has_mode_marker():
    corpus = _seeded()
    assert corpus['mode'] == MODE_SEEDED_FIXTURE_REVIEW
    assert json.loads(json.dumps(corpus, sort_keys=True))['mode'] == MODE_SEEDED_FIXTURE_REVIEW


def test_seeded_markdown_has_mode_and_warning():
    md = render_markdown(_seeded())
    assert '# COIN Story Corpus' in md
    assert f'Mode: {MODE_SEEDED_FIXTURE_REVIEW}' in md
    assert SEEDED_REVIEW_WARNING in md
    assert 'Fixture: giants_lost_game_shape' in md
    assert 'Expected primary story: lost_game_shape' in md


def test_seeded_markdown_renders_real_prose():
    md = render_markdown(_seeded())
    # The Giants draft should reflect the seeded facts (4-run lead, 7 late runs).
    assert '4-run lead' in md
    assert '7 runs' in md


# ── No DB read / no MLB fetch ─────────────────────────────────────────────────

def test_seeded_mode_reads_no_database(monkeypatch):
    # If seeded mode touched the DB or built live intelligence, these would fire.
    import services.narrative_feed_builder as feed_builder

    def _boom(*args, **kwargs):
        raise AssertionError('seeded mode must not read the database')

    monkeypatch.setattr(feed_builder, '_load_latest_completed_game_context', _boom)
    monkeypatch.setattr(feed_builder, '_load_team_context', _boom)

    corpus = _seeded()  # no app passed; fully injected
    assert len(corpus['entries']) == 4
    assert all(e['error'] is None for e in corpus['entries'])


def test_seeded_mode_makes_no_mlb_calls(monkeypatch):
    from services.mlb_api import mlb_client

    def _boom(*args, **kwargs):
        raise AssertionError('seeded mode must not fetch MLB data')

    for name in ('get_schedule', 'get_game_boxscore', 'get_game_linescore',
                 'get_game_play_by_play', 'get_pitcher_game_logs'):
        monkeypatch.setattr(mlb_client, name, _boom)

    corpus = _seeded()
    assert all(e['error'] is None for e in corpus['entries'])


# ── Non-seeded behavior unchanged ─────────────────────────────────────────────

def test_non_seeded_corpus_shape_is_unchanged():
    # A pure non-seeded corpus (stub inspect_fn) keeps the original 6-key shape.
    def stub(team_id, **kwargs):
        return {
            'team_id': team_id, 'game_pk': None, 'publishable': False,
            'publish_reason': 'no_completed_context', 'confidence': 'LOW',
            'story_priority': 'LOW', 'game_importance': 'LOW',
            'recommended_surface': 'none', 'safe_time_context': 'CURRENT_STATUS',
            'writer_targets': [], 'package': {'primary_story': 'insufficient_context'},
            'drafts': [],
        }
    corpus = generate_corpus([137], inspect_fn=stub, generated_at='2026-06-25')
    assert 'mode' not in corpus
    assert set(corpus) == {'generated_at', 'reference_date', 'team_ids',
                           'include_unpublishable', 'writer_filter', 'entries'}
    assert 'fixture_name' not in corpus['entries'][0]
