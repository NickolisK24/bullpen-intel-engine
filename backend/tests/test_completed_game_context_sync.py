"""Sync-integration tests for Completed Game Context (COIN Phase 3).

These exercise the postgame refresh end to end with a faked MLB client: a
completed game should produce two derived context rows (one per team), re-runs
must not duplicate them, and a context-extraction failure must never break the
refresh or undo the ingested game logs. No raw play-by-play is persisted.
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
import services.sync as sync_service
from services import sync_metadata
from models.completed_game_context import CompletedGameContext
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.sync_failure import SyncFailure
import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401


SCHEDULE_DATE = date(2026, 6, 20)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def app(monkeypatch):
    monkeypatch.setattr(sync_service, 'recalculate_all_fatigue', lambda reference_date=None: 0)

    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        _seed_pitchers()
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _seed_pitchers():
    db.session.add_all([
        Pitcher(mlb_id=11, full_name='Home Starter', team_id=1, team_abbreviation='HME', active=True),
        Pitcher(mlb_id=12, full_name='Home Reliever', team_id=1, team_abbreviation='HME', active=True),
        Pitcher(mlb_id=21, full_name='Away Starter', team_id=2, team_abbreviation='AWY', active=True),
        Pitcher(mlb_id=22, full_name='Away Reliever', team_id=2, team_abbreviation='AWY', active=True),
    ])
    db.session.commit()


def _game(game_pk=7001, status_code='F', detailed_state='Final', abstract_state='Final',
          home_score=3, away_score=1):
    return {
        'gamePk': game_pk,
        'gameType': 'R',
        'officialDate': '2026-06-20',
        'status': {
            'statusCode': status_code,
            'detailedState': detailed_state,
            'abstractGameState': abstract_state,
        },
        'teams': {
            'home': {'team': {'id': 1, 'name': 'Home Club'}, 'score': home_score},
            'away': {'team': {'id': 2, 'name': 'Away Club'}, 'score': away_score},
        },
    }


def _pitcher_stat(name, games_started, innings, pitches):
    return {
        'person': {'fullName': name},
        'stats': {'pitching': {
            'inningsPitched': innings,
            'numberOfPitches': pitches,
            'gamesStarted': games_started,
            'runs': '0',
        }},
    }


def _boxscore():
    return {
        'teams': {
            'home': {
                'team': {'id': 1, 'name': 'Home Club'},
                'pitchers': [11, 12],
                'players': {
                    'ID11': _pitcher_stat('Home Starter', 1, '6.0', '92'),
                    'ID12': _pitcher_stat('Home Reliever', 0, '3.0', '20'),
                },
            },
            'away': {
                'team': {'id': 2, 'name': 'Away Club'},
                'pitchers': [21, 22],
                'players': {
                    'ID21': _pitcher_stat('Away Starter', 1, '4.0', '70'),
                    'ID22': _pitcher_stat('Away Reliever', 0, '6.0', '55'),
                },
            },
        },
    }


def _linescore():
    return {
        'innings': [
            {'num': 1, 'home': {'runs': 1}, 'away': {'runs': 0}},
            {'num': 2, 'home': {'runs': 2}, 'away': {'runs': 0}},
            {'num': 7, 'home': {'runs': 0}, 'away': {'runs': 1}},
        ],
        'teams': {'home': {'runs': 3}, 'away': {'runs': 1}},
    }


def _play_by_play():
    plays = [
        (6, 'top', 1, 3, 11),    # home starter's last batter, up 3-1
        (7, 'top', 1, 3, 12),    # reliever enters
        (8, 'top', 1, 3, 12),
        (9, 'top', 1, 3, 12),    # final 3-1 home
    ]
    return {
        'allPlays': [
            {
                'about': {'inning': i, 'halfInning': h, 'isComplete': True},
                'result': {'awayScore': a, 'homeScore': hm},
                'matchup': {'pitcher': {'id': pid}},
            }
            for (i, h, a, hm, pid) in plays
        ]
    }


def _patch_mlb(monkeypatch, schedule_games, *, boxscore=None, linescore=None,
               play_by_play=None):
    def fake_schedule(start_date=None, end_date=None, team_id=None):
        return schedule_games

    monkeypatch.setattr(sync_service.mlb_client, 'get_schedule', fake_schedule)
    monkeypatch.setattr(sync_service.mlb_client, 'get_game_boxscore',
                        lambda game_pk: boxscore if boxscore is not None else _boxscore())
    monkeypatch.setattr(sync_service.mlb_client, 'get_game_linescore',
                        lambda game_pk: linescore)
    monkeypatch.setattr(sync_service.mlb_client, 'get_game_play_by_play',
                        lambda game_pk: play_by_play)
    sync_service.mlb_client.metrics.reset()


def _run(app):
    return sync_service.run_postgame_refresh(app, schedule_date=SCHEDULE_DATE, source='test')


def _contexts():
    return {c.team_id: c for c in CompletedGameContext.query.all()}


# ── Confidence tiers driven by available data ─────────────────────────────────

def test_boxscore_only_refresh_yields_low_confidence_for_both_teams(app, monkeypatch):
    _patch_mlb(monkeypatch, [_game()])  # no linescore, no play-by-play

    status = _run(app)

    with app.app_context():
        rows = _contexts()
    assert status['completed_game_contexts_upserted'] == 2
    assert set(rows) == {1, 2}
    for ctx in rows.values():
        assert ctx.confidence == 'LOW'
        assert ctx.bullpen_story_tag == 'insufficient_context'
        assert ctx.final_score_for is None
        assert ctx.game_shape_created is None


def test_linescore_refresh_yields_medium_confidence(app, monkeypatch):
    _patch_mlb(monkeypatch, [_game()], linescore=_linescore())

    _run(app)

    with app.app_context():
        home = _contexts()[1]
    assert home.confidence == 'MEDIUM'
    assert home.final_score_for == 3
    assert home.final_score_against == 1
    assert home.game_shape_created == 'normal_start'
    assert home.bullpen_entry_score_for is None   # needs play-by-play


def test_play_by_play_refresh_yields_high_confidence_with_handoff(app, monkeypatch):
    _patch_mlb(monkeypatch, [_game()], linescore=_linescore(), play_by_play=_play_by_play())

    _run(app)

    with app.app_context():
        home = _contexts()[1]
    assert home.confidence == 'HIGH'
    assert home.bullpen_entry_inning == 7
    assert home.lead_when_bullpen_entered == 2
    assert home.lead_protected is True
    assert home.bullpen_story_tag == 'protected_game_shape'


# ── Idempotency ───────────────────────────────────────────────────────────────

def test_refresh_context_is_idempotent_across_reruns(app, monkeypatch):
    _patch_mlb(monkeypatch, [_game()], linescore=_linescore())

    first = _run(app)
    second = _run(app)

    with app.app_context():
        count = CompletedGameContext.query.count()
    assert first['completed_game_contexts_upserted'] == 2
    # Second run sees the game as already processed → no new/duplicate rows.
    assert second['games_already_processed'] == 1
    assert second['completed_game_contexts_upserted'] == 0
    assert count == 2


# ── Fail-closed ───────────────────────────────────────────────────────────────

def test_context_failure_does_not_break_refresh_or_logs(app, monkeypatch):
    _patch_mlb(monkeypatch, [_game()], linescore=_linescore())

    def boom(context):
        raise RuntimeError('synthetic context failure')

    monkeypatch.setattr(sync_service, 'upsert_completed_game_context', boom)

    status = _run(app)

    with app.app_context():
        log_count = GameLog.query.count()
        marker = PostgameProcessedGame.query.filter_by(mlb_game_pk=7001).one()
        context_count = CompletedGameContext.query.count()
        failures = SyncFailure.query.filter_by(
            entity_type=sync_service.POSTGAME_CONTEXT_FAILURE_ENTITY_TYPE
        ).all()

    # Refresh itself succeeded and ingested the game logs.
    assert status['status'] == 'success'
    assert status['new_logs_added'] == 4
    assert log_count == 4
    assert marker.logs_added == 4
    # Context failed closed: no partial rows, error counted, dead-letter recorded.
    assert context_count == 0
    assert status['completed_game_context_errors'] == 1
    assert len(failures) == 1


# ── Storage discipline / no raw play-by-play ──────────────────────────────────

def test_raw_play_by_play_is_not_persisted(app, monkeypatch):
    _patch_mlb(monkeypatch, [_game()], linescore=_linescore(), play_by_play=_play_by_play())

    _run(app)

    with app.app_context():
        columns = {c.name for c in CompletedGameContext.__table__.columns}
        home = _contexts()[1]
    # No column stores raw play-by-play / linescore blobs.
    assert 'plays' not in columns
    assert 'play_by_play' not in columns
    assert 'linescore' not in columns
    assert not hasattr(home, 'plays')


# ── Doubleheaders, non-final games, extra innings ─────────────────────────────

def test_doubleheader_games_stay_separate_by_game_pk(app, monkeypatch):
    games = [_game(game_pk=7001), _game(game_pk=7002)]
    _patch_mlb(monkeypatch, games, linescore=_linescore())

    _run(app)

    with app.app_context():
        pairs = {(c.team_id, c.game_pk) for c in CompletedGameContext.query.all()}
    assert pairs == {(1, 7001), (2, 7001), (1, 7002), (2, 7002)}


def test_non_final_game_produces_no_context(app, monkeypatch):
    unfinished = _game(status_code='I', detailed_state='In Progress', abstract_state='Live')
    _patch_mlb(monkeypatch, [unfinished], linescore=_linescore())

    status = _run(app)

    with app.app_context():
        count = CompletedGameContext.query.count()
    assert status['newly_completed_games'] == 0
    assert count == 0


def test_extra_innings_keep_7_to_9_window_separate(app, monkeypatch):
    extra_pbp = {
        'allPlays': [
            {'about': {'inning': 8, 'halfInning': 'top', 'isComplete': True},
             'result': {'awayScore': 1, 'homeScore': 2}, 'matchup': {'pitcher': {'id': 12}}},
            {'about': {'inning': 10, 'halfInning': 'top', 'isComplete': True},
             'result': {'awayScore': 2, 'homeScore': 2}, 'matchup': {'pitcher': {'id': 12}}},
            {'about': {'inning': 10, 'halfInning': 'bottom', 'isComplete': True},
             'result': {'awayScore': 2, 'homeScore': 3}, 'matchup': {'pitcher': {'id': 12}}},
        ]
    }
    _patch_mlb(monkeypatch, [_game(home_score=3, away_score=2)],
               linescore=_linescore(), play_by_play=extra_pbp)

    _run(app)

    with app.app_context():
        home = _contexts()[1]
    assert home.confidence == 'HIGH'
    assert home.runs_allowed_innings_7_to_9 == 1   # only the 8th counts
    assert home.late_runs_allowed == 2             # 8th + 10th
