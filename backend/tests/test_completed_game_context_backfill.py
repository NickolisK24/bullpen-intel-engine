"""Tests for the Completed Game Context backfill (COIN).

The backfill derives context for already-processed historical games (which the
normal refresh skips). These use a faked MLB client and seeded
``postgame_processed_games`` markers to cover candidate identification, the
existing-context skip, force/dry-run, idempotency, per-game fail-closed handling,
the date/team/limit filters, and the no-raw-play-by-play guarantee.
"""

from datetime import date

import pytest
from flask import Flask

from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)
from utils.db import db
import services.completed_game_context_backfill as backfill
import services.sync as sync_service
from services.mlb_api import mlb_client
from models.completed_game_context import CompletedGameContext
from models.postgame_processed_game import PostgameProcessedGame
import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
import models.pitcher  # noqa: F401
import models.game_log  # noqa: F401
import models.sync_run  # noqa: F401

D1 = date(2026, 6, 20)
D2 = date(2026, 6, 21)


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


# ── Seed helpers ──────────────────────────────────────────────────────────────

def _marker(game_pk, game_date, home_id=1, away_id=2):
    return PostgameProcessedGame(
        mlb_game_pk=game_pk, game_date=game_date,
        home_team_id=home_id, away_team_id=away_id, logs_added=2, pitchers_touched=2,
    )


def _seed_markers(markers):
    db.session.add_all(markers)
    db.session.commit()


def _context_row(game_pk, team_id, confidence='LOW'):
    return CompletedGameContext(
        team_id=team_id, game_pk=game_pk, game_date=D1,
        confidence=confidence, bullpen_story_tag='insufficient_context',
    )


def _schedule_game(game_pk, game_date, home_id=1, away_id=2):
    return {
        'gamePk': game_pk,
        'gameType': 'R',
        'officialDate': game_date.isoformat(),
        'status': {'statusCode': 'F', 'detailedState': 'Final', 'abstractGameState': 'Final'},
        'teams': {
            'home': {'team': {'id': home_id, 'name': f'Team {home_id}'}, 'score': 3},
            'away': {'team': {'id': away_id, 'name': f'Team {away_id}'}, 'score': 1},
        },
    }


def _boxscore(home_id=1, away_id=2):
    def side(team_id, pid, name):
        return {
            'team': {'id': team_id, 'name': f'Team {team_id}'},
            'pitchers': [pid],
            'players': {f'ID{pid}': {
                'person': {'fullName': name},
                'stats': {'pitching': {'inningsPitched': '6.0', 'numberOfPitches': '90',
                                       'gamesStarted': 1, 'runs': '1'}},
            }},
        }
    return {'teams': {'home': side(home_id, 11, 'Home SP'),
                      'away': side(away_id, 21, 'Away SP')}}


def _patch_mlb(monkeypatch, games_by_date, *, boxscore_for=None,
               linescore=None, play_by_play=None, boxscore_raises=()):
    def fake_schedule(start_date=None, end_date=None, team_id=None):
        return games_by_date.get(start_date, [])

    def fake_boxscore(game_pk):
        if game_pk in boxscore_raises:
            raise RuntimeError(f'synthetic boxscore failure for {game_pk}')
        return (boxscore_for or {}).get(game_pk) or _boxscore()

    monkeypatch.setattr(mlb_client, 'get_schedule', fake_schedule)
    monkeypatch.setattr(mlb_client, 'get_game_boxscore', fake_boxscore)
    monkeypatch.setattr(mlb_client, 'get_game_linescore', lambda game_pk: linescore)
    monkeypatch.setattr(mlb_client, 'get_game_play_by_play', lambda game_pk: play_by_play)


def _run(app, **kwargs):
    return backfill.run_backfill(app, **kwargs)


def _context_count(game_pk=None):
    q = CompletedGameContext.query
    if game_pk is not None:
        q = q.filter_by(game_pk=game_pk)
    return q.count()


# ── Guardrail ─────────────────────────────────────────────────────────────────

def test_requires_explicit_range_or_limit(app):
    with pytest.raises(ValueError):
        _run(app)


# ── Candidate identification + dry run ────────────────────────────────────────

def test_dry_run_identifies_candidates_and_writes_nothing(app, monkeypatch):
    with app.app_context():
        _seed_markers([_marker(7001, D1), _marker(7002, D1)])
    _patch_mlb(monkeypatch, {D1.isoformat(): [_schedule_game(7001, D1), _schedule_game(7002, D1)]})

    summary = _run(app, start_date=D1, end_date=D1, dry_run=True)

    assert summary['candidate_games'] == 2
    assert summary['would_process'] == 2
    assert summary['skipped_existing'] == 0
    assert summary['contexts_upserted'] == 0
    with app.app_context():
        assert _context_count() == 0


# ── Successful backfill ───────────────────────────────────────────────────────

def test_successful_backfill_upserts_two_contexts(app, monkeypatch):
    with app.app_context():
        _seed_markers([_marker(7001, D1)])
    _patch_mlb(monkeypatch, {D1.isoformat(): [_schedule_game(7001, D1)]})

    summary = _run(app, start_date=D1, end_date=D1)

    assert summary['contexts_upserted'] == 2
    assert summary['games_succeeded'] == 1
    with app.app_context():
        teams = {c.team_id for c in CompletedGameContext.query.filter_by(game_pk=7001).all()}
    assert teams == {1, 2}


# ── Skip existing / force ─────────────────────────────────────────────────────

def test_skips_games_with_existing_two_team_context(app, monkeypatch):
    with app.app_context():
        _seed_markers([_marker(7001, D1), _marker(7002, D1)])
        db.session.add_all([_context_row(7001, 1), _context_row(7001, 2)])
        db.session.commit()
    _patch_mlb(monkeypatch, {D1.isoformat(): [_schedule_game(7001, D1), _schedule_game(7002, D1)]})

    summary = _run(app, start_date=D1, end_date=D1)

    assert summary['skipped_existing'] == 1     # 7001 already covered
    assert summary['games_succeeded'] == 1      # only 7002 processed
    with app.app_context():
        assert _context_count(7002) == 2


def test_force_reprocesses_existing_without_duplicating(app, monkeypatch):
    with app.app_context():
        _seed_markers([_marker(7001, D1)])
        db.session.add_all([_context_row(7001, 1), _context_row(7001, 2)])
        db.session.commit()
    _patch_mlb(monkeypatch, {D1.isoformat(): [_schedule_game(7001, D1)]})

    summary = _run(app, start_date=D1, end_date=D1, force=True)

    assert summary['skipped_existing'] == 0
    assert summary['games_succeeded'] == 1
    assert summary['contexts_upserted'] == 2
    with app.app_context():
        assert _context_count(7001) == 2        # updated, not duplicated


# ── Idempotency ───────────────────────────────────────────────────────────────

def test_rerun_is_idempotent(app, monkeypatch):
    with app.app_context():
        _seed_markers([_marker(7001, D1)])
    _patch_mlb(monkeypatch, {D1.isoformat(): [_schedule_game(7001, D1)]})

    first = _run(app, start_date=D1, end_date=D1)
    second = _run(app, start_date=D1, end_date=D1)

    assert first['games_succeeded'] == 1
    assert second['skipped_existing'] == 1
    assert second['contexts_upserted'] == 0
    with app.app_context():
        assert _context_count(7001) == 2


# ── Per-game fail-closed ──────────────────────────────────────────────────────

def test_failed_game_does_not_stop_backfill(app, monkeypatch):
    with app.app_context():
        _seed_markers([_marker(7001, D1), _marker(7002, D1)])
    _patch_mlb(
        monkeypatch,
        {D1.isoformat(): [_schedule_game(7001, D1), _schedule_game(7002, D1)]},
        boxscore_raises=(7001,),
    )

    summary = _run(app, start_date=D1, end_date=D1)

    assert summary['games_failed'] == 1
    assert summary['games_succeeded'] == 1
    assert {f['game_pk'] for f in summary['failures']} == {7001}
    with app.app_context():
        assert _context_count(7002) == 2
        assert _context_count(7001) == 0        # no partial context written


def test_missing_schedule_game_is_skipped_not_fatal(app, monkeypatch):
    with app.app_context():
        _seed_markers([_marker(7001, D1)])
    _patch_mlb(monkeypatch, {D1.isoformat(): []})  # schedule returns no match

    summary = _run(app, start_date=D1, end_date=D1)

    assert summary['skipped_missing_data'] == 1
    assert summary['contexts_upserted'] == 0
    assert summary['games_failed'] == 0


# ── Filters ───────────────────────────────────────────────────────────────────

def test_team_id_filter(app, monkeypatch):
    with app.app_context():
        _seed_markers([_marker(7001, D1, home_id=1, away_id=2),
                       _marker(7003, D1, home_id=3, away_id=4)])
    _patch_mlb(monkeypatch, {D1.isoformat(): [
        _schedule_game(7001, D1, 1, 2), _schedule_game(7003, D1, 3, 4)]})

    summary = _run(app, start_date=D1, end_date=D1, team_id=3)

    assert summary['candidate_games'] == 1
    with app.app_context():
        assert _context_count(7003) == 2
        assert _context_count(7001) == 0


def test_date_range_filter(app, monkeypatch):
    with app.app_context():
        _seed_markers([_marker(7001, D1), _marker(7005, D2)])
    _patch_mlb(monkeypatch, {
        D1.isoformat(): [_schedule_game(7001, D1)],
        D2.isoformat(): [_schedule_game(7005, D2)],
    })

    summary = _run(app, start_date=D2, end_date=D2)

    assert summary['candidate_games'] == 1
    with app.app_context():
        assert _context_count(7005) == 2
        assert _context_count(7001) == 0


def test_limit_bounds_candidates(app, monkeypatch):
    with app.app_context():
        _seed_markers([_marker(7001, D1), _marker(7002, D1), _marker(7003, D1)])
    _patch_mlb(monkeypatch, {D1.isoformat(): [
        _schedule_game(7001, D1), _schedule_game(7002, D1), _schedule_game(7003, D1)]})

    summary = _run(app, limit=1)

    assert summary['candidate_games'] == 1
    assert summary['games_succeeded'] == 1


# ── No raw play-by-play persisted ─────────────────────────────────────────────

def test_raw_play_by_play_is_not_persisted(app, monkeypatch):
    pbp = {'allPlays': [
        {'about': {'inning': 6, 'halfInning': 'top', 'isComplete': True},
         'result': {'awayScore': 1, 'homeScore': 3}, 'matchup': {'pitcher': {'id': 11}}},
        {'about': {'inning': 7, 'halfInning': 'top', 'isComplete': True},
         'result': {'awayScore': 1, 'homeScore': 3}, 'matchup': {'pitcher': {'id': 12}}},
    ]}
    with app.app_context():
        _seed_markers([_marker(7001, D1)])
    _patch_mlb(monkeypatch, {D1.isoformat(): [_schedule_game(7001, D1)]}, play_by_play=pbp)

    _run(app, start_date=D1, end_date=D1)

    with app.app_context():
        columns = {c.name for c in CompletedGameContext.__table__.columns}
        assert 'plays' not in columns and 'play_by_play' not in columns
        assert _context_count(7001) == 2
