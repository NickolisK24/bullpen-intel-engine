"""
Runtime-safety regressions for the daily gameLog ingestion stage.

The 2026-07-08 production timeout (exit 124 after 20m) was caused by
per-split database round trips against the remote Postgres: one SELECT per
in-window split per pitcher plus per-pitcher dead-letter resolution UPDATEs.
These tests pin the batched behavior (one window prefetch, one boxscore fetch
per game, no per-pitcher resolution queries without a prior failure) and the
soft time budget that finishes the stage cleanly as partial instead of dying
to the workflow's hard timeout.
"""

from datetime import date

import pytest
from flask import Flask
from sqlalchemy import event

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.prospect  # noqa: F401
import services.sync as sync_service
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from models.sync_failure import SyncFailure
from services.mlb_api import MlbApiMetrics, mlb_client, normalize_endpoint_template
from utils.db import db


REFERENCE_DATE = date(2026, 7, 8)
JULY_5 = date(2026, 7, 5)
JULY_6 = date(2026, 7, 6)


def _split(pk, game_date, pitches=15):
    return {
        'game': {'gamePk': pk, 'gameType': 'R'},
        'date': game_date.isoformat(),
        'opponent': {'id': 111, 'name': 'Boston Red Sox'},
        'stat': {
            'inningsPitched': '1.0', 'numberOfPitches': pitches, 'strikes': 8,
            'hits': 1, 'runs': 0, 'earnedRuns': 0, 'baseOnBalls': 0,
            'strikeOuts': 2, 'homeRuns': 0,
        },
    }


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        create_test_schema(app)
        try:
            yield app
        finally:
            db.session.remove()
            drop_test_schema(app)


def _seed_pitcher(mlb_id, name):
    pitcher = Pitcher(mlb_id=mlb_id, full_name=name, team_id=108,
                      team_abbreviation='LAA', active=True)
    db.session.add(pitcher)
    db.session.flush()
    return pitcher


def _seed_final(pk, game_date):
    db.session.add(ScheduledGame(
        team_id=108, game_pk=pk, game_date=game_date,
        status_state=ScheduledGame.STATE_FINAL, status_code='F',
        game_type='R', home_away='away', opponent_team_id=111,
    ))


def _seed_row(pitcher, pk, game_date, pitches=15):
    # Field-for-field identical to _split() so a re-sync is 'unchanged'.
    db.session.add(GameLog(
        pitcher_id=pitcher.id, mlb_game_pk=pk, game_date=game_date,
        opponent='Boston Red Sox',
        innings_pitched=1.0, innings_pitched_outs=3, pitches_thrown=pitches,
        strikes=8, hits_allowed=1, strikeouts=2,
    ))


def _count_game_log_selects(statements):
    return sum(
        1 for statement in statements
        if statement.lstrip().upper().startswith('SELECT')
        and 'game_logs' in statement
    )


def test_window_rows_are_prefetched_in_one_select(app, monkeypatch):
    """N pitchers with existing window rows must cost one game_logs SELECT
    total, not one per split (the production timeout signature)."""
    with app.app_context():
        pitchers = [_seed_pitcher(700100 + i, f'Reliever {i}') for i in range(5)]
        for i, pitcher in enumerate(pitchers):
            _seed_final(824900 + i, JULY_5)
            _seed_row(pitcher, 824900 + i, JULY_5)
        db.session.commit()

        splits_by_id = {
            pitcher.mlb_id: [_split(824900 + i, JULY_5)]
            for i, pitcher in enumerate(pitchers)
        }
        monkeypatch.setattr(
            mlb_client, 'get_pitcher_game_logs',
            lambda mlb_id, season=None: splits_by_id.get(mlb_id, []),
        )

        statements = []

        def track(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        engine = db.session.get_bind()
        event.listen(engine, 'before_cursor_execute', track)
        try:
            result = sync_service.sync_recent_logs(
                days_back=7, reference_date=REFERENCE_DATE,
            )
        finally:
            event.remove(engine, 'before_cursor_execute', track)

    assert result['logs_unchanged'] == 5
    assert result['lane_health'] == 'ok'
    assert _count_game_log_selects(statements) == 1


def test_map_miss_still_queries_before_insert(app, monkeypatch):
    """A split for a game with no window row still inserts exactly once."""
    with app.app_context():
        pitcher = _seed_pitcher(700200, 'New Work Reliever')
        _seed_final(824910, JULY_6)
        db.session.commit()
        monkeypatch.setattr(
            mlb_client, 'get_pitcher_game_logs',
            lambda mlb_id, season=None: [_split(824910, JULY_6)],
        )
        monkeypatch.setattr(mlb_client, 'get_game_pitching_lines', lambda pk: [])

        result = sync_service.sync_recent_logs(
            days_back=7, reference_date=REFERENCE_DATE,
        )
        rows = GameLog.query.filter_by(mlb_game_pk=824910).all()

    assert result['new_logs_added'] == 1
    assert len(rows) == 1


def test_leverage_boxscore_fetched_once_per_game(app, monkeypatch):
    """Two pitchers inserting from the same game share one boxscore fetch."""
    with app.app_context():
        first = _seed_pitcher(700300, 'Shared Game A')
        second = _seed_pitcher(700301, 'Shared Game B')
        _seed_final(824920, JULY_6)
        db.session.commit()

        boxscore_calls = []

        def fake_lines(game_pk):
            boxscore_calls.append(game_pk)
            return []

        monkeypatch.setattr(mlb_client, 'get_game_pitching_lines', fake_lines)
        monkeypatch.setattr(
            mlb_client, 'get_pitcher_game_logs',
            lambda mlb_id, season=None: [_split(824920, JULY_6)],
        )

        result = sync_service.sync_recent_logs(
            days_back=7, reference_date=REFERENCE_DATE,
        )

    assert result['new_logs_added'] == 2
    assert boxscore_calls == [824920]


def test_time_budget_dead_letters_remaining_pitchers(app, monkeypatch):
    """Budget exhaustion finishes cleanly as partial: remaining pitchers are
    dead-lettered and counted, never silently absorbed."""
    with app.app_context():
        for i in range(4):
            _seed_pitcher(700400 + i, f'Budgeted Reliever {i}')
        db.session.commit()
        monkeypatch.setattr(
            mlb_client, 'get_pitcher_game_logs',
            lambda mlb_id, season=None: [],
        )

        result = sync_service.sync_recent_logs(
            days_back=7, reference_date=REFERENCE_DATE,
            time_budget_seconds=0,
        )
        budget_failures = SyncFailure.query.filter_by(
            entity_type=sync_service.DAILY_GAME_LOG_BUDGET_FAILURE_ENTITY_TYPE
        ).all()

    assert result['budget_exhausted_pitchers'] == 4
    assert result['records_failed'] == 4
    assert result['lane_health'] == 'budget_exhausted'
    assert len(budget_failures) == 1
    assert budget_failures[0].payload['pitchers_remaining'] == 4
    assert budget_failures[0].payload['pitchers_processed'] == 0


def test_budget_env_default_and_override(monkeypatch):
    monkeypatch.delenv('DAILY_SYNC_INGESTION_BUDGET_SECONDS', raising=False)
    assert sync_service._daily_sync_ingestion_budget_seconds() == (
        sync_service.DAILY_SYNC_DEFAULT_INGESTION_BUDGET_SECONDS
    )
    monkeypatch.setenv('DAILY_SYNC_INGESTION_BUDGET_SECONDS', '300')
    assert sync_service._daily_sync_ingestion_budget_seconds() == 300.0
    monkeypatch.setenv('DAILY_SYNC_INGESTION_BUDGET_SECONDS', '0')
    assert sync_service._daily_sync_ingestion_budget_seconds() is None
    monkeypatch.setenv('DAILY_SYNC_INGESTION_BUDGET_SECONDS', 'junk')
    assert sync_service._daily_sync_ingestion_budget_seconds() == (
        sync_service.DAILY_SYNC_DEFAULT_INGESTION_BUDGET_SECONDS
    )


def test_resolution_updates_only_run_for_prior_failures(app, monkeypatch):
    """resolve_entity_failures must not fire one UPDATE per healthy pitcher."""
    with app.app_context():
        healthy = _seed_pitcher(700500, 'Healthy Reliever')
        flagged = _seed_pitcher(700501, 'Previously Failed Reliever')
        healthy_mlb_id, flagged_mlb_id = healthy.mlb_id, flagged.mlb_id
        db.session.add(SyncFailure(
            entity_type=sync_service.PITCHER_GAME_LOG_FAILURE_ENTITY_TYPE,
            entity_ref=str(flagged_mlb_id),
            job_name=sync_service.sync_metadata.JOB_DAILY_SYNC,
            error='old fetch failure',
            resolved=False,
        ))
        db.session.commit()

        resolved_refs = []
        real_resolve = sync_service.dead_letter.resolve_entity_failures

        def tracking_resolve(entity_type, entity_ref, **kwargs):
            resolved_refs.append(str(entity_ref))
            return real_resolve(entity_type, entity_ref, **kwargs)

        monkeypatch.setattr(
            sync_service.dead_letter, 'resolve_entity_failures', tracking_resolve,
        )
        monkeypatch.setattr(
            mlb_client, 'get_pitcher_game_logs', lambda mlb_id, season=None: [],
        )

        sync_service.sync_recent_logs(days_back=7, reference_date=REFERENCE_DATE)

        remaining = SyncFailure.query.filter_by(resolved=False).count()

    assert resolved_refs == [str(flagged_mlb_id)]
    assert remaining == 0
    assert str(healthy_mlb_id) not in resolved_refs


def test_metrics_by_endpoint_normalization():
    metrics = MlbApiMetrics()
    metrics.record_endpoint_call('/people/694363/stats', 57.0)
    metrics.record_endpoint_call('/people/700501/stats', 43.0)
    metrics.record_endpoint_call('/teams/108/roster', 60.5)
    snapshot = metrics.snapshot()
    assert snapshot['by_endpoint']['/people/{id}/stats']['calls'] == 2
    assert snapshot['by_endpoint']['/people/{id}/stats']['latency_ms'] == 100.0
    assert snapshot['by_endpoint']['/teams/{id}/roster']['calls'] == 1
    assert normalize_endpoint_template('/game/824600/boxscore') == '/game/{id}/boxscore'
    metrics.reset()
    assert metrics.snapshot()['by_endpoint'] == {}
