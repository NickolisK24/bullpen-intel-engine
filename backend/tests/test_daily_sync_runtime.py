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
from types import SimpleNamespace

import pytest
from flask import Flask
from sqlalchemy import event

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.prospect  # noqa: F401
import services.sync as sync_service
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.pitcher_season_ledger_coverage import PitcherSeasonLedgerCoverage
from models.scheduled_game import ScheduledGame
from models.sync_failure import SyncFailure
from services import sync_metadata
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
            'strikeOuts': 2, 'homeRuns': 0, 'gamesStarted': 0,
        },
    }


def _schedule_api_game(game_pk, game_date):
    return {
        'gamePk': game_pk,
        'gameType': 'R',
        'officialDate': game_date.isoformat(),
        'status': {
            'statusCode': 'F',
            'detailedState': 'Final',
            'abstractGameState': 'Final',
        },
        'teams': {
            'home': {'team': {'id': 108, 'name': 'Home Club'}},
            'away': {'team': {'id': 111, 'name': 'Away Club'}},
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
        games_started=0,
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


def test_runtime_budget_reserves_headroom_after_slow_pre_ingestion(monkeypatch):
    monkeypatch.setenv('DAILY_SYNC_TOTAL_BUDGET_SECONDS', '1080')
    monkeypatch.setenv('DAILY_SYNC_FINAL_PHASE_RESERVE_SECONDS', '300')
    monkeypatch.setenv('DAILY_SYNC_INGESTION_BUDGET_SECONDS', '720')
    monkeypatch.setattr(sync_service.time, 'monotonic', lambda: 1250.0)

    budget = sync_service._daily_sync_runtime_budget(1000.0)

    assert budget['elapsed_before_ingestion_seconds'] == 250.0
    assert budget['remaining_total_seconds'] == 830.0
    assert budget['budget_after_reserve_seconds'] == 530.0
    assert budget['ingestion_budget_seconds'] == 530.0


def test_runtime_budget_returns_zero_when_final_phase_reserve_is_gone(monkeypatch):
    monkeypatch.setenv('DAILY_SYNC_TOTAL_BUDGET_SECONDS', '1080')
    monkeypatch.setenv('DAILY_SYNC_FINAL_PHASE_RESERVE_SECONDS', '300')
    monkeypatch.setenv('DAILY_SYNC_INGESTION_BUDGET_SECONDS', '720')
    monkeypatch.setattr(sync_service.time, 'monotonic', lambda: 1790.0)

    budget = sync_service._daily_sync_runtime_budget(1000.0)

    assert budget['remaining_total_seconds'] == 290.0
    assert budget['budget_after_reserve_seconds'] == 0.0
    assert budget['ingestion_budget_seconds'] == 0.0


def test_daily_sync_clean_partial_finishes_snapshot_and_metadata(app, monkeypatch):
    captured = {}
    monkeypatch.setattr(sync_service, '_sync_schedule_finality_preflight_enabled', lambda: False)
    monkeypatch.setattr(sync_service, '_daily_sync_runtime_budget', lambda started: {
        'total_budget_seconds': 1080.0,
        'stage_budget_cap_seconds': 720.0,
        'final_phase_reserve_seconds': 300.0,
        'elapsed_before_ingestion_seconds': 900.0,
        'remaining_total_seconds': 180.0,
        'budget_after_reserve_seconds': 0.0,
        'ingestion_budget_seconds': 0.0,
    })
    monkeypatch.setattr(sync_service, 'resolve_product_day', lambda started: SimpleNamespace(
        calendar_date=REFERENCE_DATE,
        limitations=(),
    ))
    monkeypatch.setattr(sync_service, 'sync_team_assignments', lambda: {
        'pitchers_refreshed': 1,
        'pitchers_changed': 0,
        'reassigned_count': 0,
        'no_organization_count': 0,
        'unknown_count': 0,
        'errors': 0,
        'by_status': {'ASSIGNED': 1},
        'error_details': [],
    })
    monkeypatch.setattr(sync_service, 'sync_roster_statuses', lambda **_kwargs: {
        'pitchers_refreshed': 1,
        'pitchers_changed': 0,
        'unknown_count': 0,
        'records_failed': 0,
        'errors': 0,
        'error_details': [],
    })
    monkeypatch.setattr(sync_service, 'sync_transactions', lambda **_kwargs: {
        'records_fetched': 0,
        'records_stored': 0,
        'unknown_type_count': 0,
        'records_failed': 0,
        'errors': 0,
        'error_details': [],
    })

    def fake_sync_recent_logs(**kwargs):
        captured['time_budget_seconds'] = kwargs['time_budget_seconds']
        return {
            'new_logs_added': 0,
            'logs_corrected': 0,
            'logs_unchanged': 0,
            'pitchers_touched': 0,
            'pitchers_total': 777,
            'errors': 0,
            'records_failed': 493,
            'correction_attempts_failed': 0,
            'unresolved_finality': 0,
            'splits_seen': 0,
            'splits_skipped': {},
            'lane_health': 'budget_exhausted',
            'budget_exhausted_pitchers': 493,
            'fetch_seconds': 21.8,
            'process_seconds': 760.0,
        }

    monkeypatch.setattr(sync_service, 'sync_recent_logs', fake_sync_recent_logs)
    monkeypatch.setattr(sync_service, 'recalculate_all_fatigue', lambda: 2)
    monkeypatch.setattr(sync_service, 'complete_sync_run_with_snapshot',
                        lambda *args, **kwargs: (SimpleNamespace(id=1), SimpleNamespace(id=88)))

    status = sync_service.run_daily_sync(
        app,
        days_back=7,
        include_internal_enrichment=False,
    )

    assert captured['time_budget_seconds'] == 0.0
    assert status['status'] == sync_metadata.STATUS_PARTIAL
    assert status['runtime_budget']['ingestion_budget_seconds'] == 0.0
    assert status['budget_exhausted_pitchers'] == 493
    assert status['dashboard_snapshot_id'] == 88
    assert status['finished_at']


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


def test_daily_coverage_reconciles_only_current_window_targets(app, monkeypatch):
    with app.app_context():
        pitcher = _seed_pitcher(700600, 'Targeted Coverage Starter')
        _seed_final(824800, date(2026, 6, 15))
        _seed_final(824930, JULY_6)
        _seed_row(pitcher, 824800, date(2026, 6, 15))
        _seed_row(pitcher, 824930, JULY_6)
        db.session.commit()
        monkeypatch.setattr(
            mlb_client,
            'get_pitcher_game_logs',
            lambda mlb_id, season=None: [
                _split(824800, date(2026, 6, 15)),
                _split(824930, JULY_6),
            ],
        )

        result = sync_service.sync_recent_logs(
            days_back=7,
            reference_date=REFERENCE_DATE,
        )
        coverage_rows = PitcherSeasonLedgerCoverage.query.all()

    assert result['ledger_coverage_records'] == 1
    assert len(coverage_rows) == 1
    assert coverage_rows[0].target_game_pk == 824930
    assert coverage_rows[0].coverage_status == PitcherSeasonLedgerCoverage.STATUS_COMPLETE


def test_daily_finality_preflight_runs_before_statusless_ingestion(app, monkeypatch):
    with app.app_context():
        pitcher = _seed_pitcher(700700, 'Delayed Finality Reliever')
        db.session.commit()

    monkeypatch.setenv('DAILY_SYNC_SCHEDULE_FINALITY_PREFLIGHT', 'true')
    monkeypatch.setattr(sync_service, 'resolve_product_day', lambda started: SimpleNamespace(
        calendar_date=REFERENCE_DATE,
        limitations=(),
    ))
    monkeypatch.setattr(
        sync_service.schedule_ingestion.mlb_client,
        'get_schedule',
        lambda start_date=None, end_date=None, team_id=None: [
            _schedule_api_game(824940, JULY_6)
        ],
    )
    monkeypatch.setattr(sync_service, 'sync_team_assignments', lambda: {
        'pitchers_refreshed': 1,
        'pitchers_changed': 0,
        'reassigned_count': 0,
        'no_organization_count': 0,
        'unknown_count': 0,
        'errors': 0,
        'by_status': {'ASSIGNED': 1},
        'error_details': [],
    })
    monkeypatch.setattr(sync_service, 'sync_roster_statuses', lambda **_kwargs: {
        'pitchers_refreshed': 1,
        'pitchers_changed': 0,
        'unknown_count': 0,
        'records_failed': 0,
        'errors': 0,
        'error_details': [],
    })
    monkeypatch.setattr(sync_service, 'sync_transactions', lambda **_kwargs: {
        'records_fetched': 0,
        'records_stored': 0,
        'unknown_type_count': 0,
        'records_failed': 0,
        'errors': 0,
        'error_details': [],
    })
    monkeypatch.setattr(
        mlb_client,
        'get_pitcher_game_logs',
        lambda mlb_id, season=None: [_split(824940, JULY_6)],
    )
    monkeypatch.setattr(mlb_client, 'get_game_pitching_lines', lambda pk: [])
    monkeypatch.setattr(sync_service, 'recalculate_all_fatigue', lambda: 2)
    monkeypatch.setattr(sync_service, 'complete_sync_run_with_snapshot',
                        lambda *args, **kwargs: (SimpleNamespace(id=1), SimpleNamespace(id=88)))

    status = sync_service.run_daily_sync(
        app,
        days_back=7,
        include_internal_enrichment=False,
    )

    with app.app_context():
        log = GameLog.query.filter_by(mlb_game_pk=824940).one()
        schedule_states = {
            row.status_state
            for row in ScheduledGame.query.filter_by(game_pk=824940).all()
        }

    assert status['status'] == sync_metadata.STATUS_SUCCESS
    assert status['schedule_finality_preflight']['status'] == 'ok'
    assert log.game_date == JULY_6
    assert schedule_states == {ScheduledGame.STATE_FINAL}


def test_daily_finality_preflight_failure_finishes_clean_partial(app, monkeypatch):
    monkeypatch.setenv('DAILY_SYNC_SCHEDULE_FINALITY_PREFLIGHT', 'true')
    monkeypatch.setattr(sync_service, 'resolve_product_day', lambda started: SimpleNamespace(
        calendar_date=REFERENCE_DATE,
        limitations=(),
    ))
    monkeypatch.setattr(
        sync_service.schedule_ingestion.mlb_client,
        'get_schedule',
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError('schedule unavailable')),
    )
    monkeypatch.setattr(sync_service, 'sync_team_assignments', lambda: {
        'pitchers_refreshed': 1,
        'pitchers_changed': 0,
        'reassigned_count': 0,
        'no_organization_count': 0,
        'unknown_count': 0,
        'errors': 0,
        'by_status': {'ASSIGNED': 1},
        'error_details': [],
    })
    monkeypatch.setattr(sync_service, 'sync_roster_statuses', lambda **_kwargs: {
        'pitchers_refreshed': 1,
        'pitchers_changed': 0,
        'unknown_count': 0,
        'records_failed': 0,
        'errors': 0,
        'error_details': [],
    })
    monkeypatch.setattr(sync_service, 'sync_transactions', lambda **_kwargs: {
        'records_fetched': 0,
        'records_stored': 0,
        'unknown_type_count': 0,
        'records_failed': 0,
        'errors': 0,
        'error_details': [],
    })
    monkeypatch.setattr(sync_service, 'sync_recent_logs', lambda **kwargs: {
        'new_logs_added': 0,
        'logs_corrected': 0,
        'logs_unchanged': 0,
        'pitchers_touched': 0,
        'pitchers_total': 0,
        'errors': 0,
        'records_failed': 0,
        'correction_attempts_failed': 0,
        'unresolved_finality': 0,
        'splits_seen': 0,
        'splits_skipped': {},
        'lane_health': 'no_window_splits',
        'budget_exhausted_pitchers': 0,
        'fetch_seconds': 0.0,
        'process_seconds': 0.0,
    })
    monkeypatch.setattr(sync_service, 'recalculate_all_fatigue', lambda: 0)
    monkeypatch.setattr(sync_service, 'complete_sync_run_with_snapshot',
                        lambda *args, **kwargs: (SimpleNamespace(id=1), SimpleNamespace(id=88)))

    status = sync_service.run_daily_sync(
        app,
        days_back=7,
        include_internal_enrichment=False,
    )

    assert status['status'] == sync_metadata.STATUS_PARTIAL
    assert status['schedule_finality_preflight']['status'] == 'failed'
    assert status['slate_schedule_refresh']['status'] == 'failed'
    assert status['records_failed'] == 2
    assert status['dashboard_snapshot_id'] == 88


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
