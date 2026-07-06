from datetime import date, datetime
from types import SimpleNamespace

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import services.sync as sync_service
from services import sync_metadata
from utils.db import db
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.play_by_play_foundation import GamePlayByPlayEvent, PlayByPlayProcessedGame
from models.postgame_processed_game import PostgameProcessedGame
from models.sync_job import SyncJob
from models.sync_run import SyncRun
import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401


_DEFAULT_PBP = object()


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    monkeypatch.setattr(sync_service, 'recalculate_all_fatigue', lambda reference_date=None: 2)

    def fake_complete(sync_run_id, **kwargs):
        run = sync_metadata.finish_sync_run(
            sync_run_id,
            status=kwargs['final_status'],
            records_processed=kwargs.get('records_processed', 0),
            records_failed=kwargs.get('records_failed', 0),
            new_logs_added=kwargs.get('new_logs_added', 0),
            pitchers_updated=kwargs.get('pitchers_updated', 0),
            errors=kwargs.get('errors', 0),
            api_calls_made=kwargs.get('api_calls_made', 0),
            retries_used=kwargs.get('retries_used', 0),
            error_message=kwargs.get('error_message'),
            source=kwargs.get('source', 'test'),
            started_at=kwargs.get('started_at'),
            job_name=kwargs.get('job_name', sync_metadata.JOB_POSTGAME_REFRESH),
        )
        return run, SimpleNamespace(id=123)

    monkeypatch.setattr(sync_service, 'complete_sync_run_with_snapshot', fake_complete)

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


def _seed_pitchers():
    home = Pitcher(
        mlb_id=101,
        full_name='Home Reliever',
        team_id=1,
        team_abbreviation='HME',
        active=True,
    )
    away = Pitcher(
        mlb_id=202,
        full_name='Away Reliever',
        team_id=2,
        team_abbreviation='AWY',
        active=True,
    )
    db.session.add_all([home, away])
    db.session.commit()
    return home, away


def _game(game_pk=7001, status_code='F', detailed_state='Final', abstract_state='Final'):
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
            'home': {'team': {'id': 1, 'name': 'Home Club'}},
            'away': {'team': {'id': 2, 'name': 'Away Club'}},
        },
    }


def _boxscore():
    return {
        'teams': {
            'home': {
                'team': {'id': 1, 'name': 'Home Club'},
                'pitchers': [101],
                'players': {
                    'ID101': {
                        'person': {'fullName': 'Home Reliever'},
                        'stats': {
                            'pitching': {
                                'inningsPitched': '1.0',
                                'numberOfPitches': '14',
                                'strikes': '9',
                                'hits': '0',
                                'runs': '0',
                                'earnedRuns': '0',
                                'baseOnBalls': '0',
                                'strikeOuts': '2',
                                'homeRuns': '0',
                                'holds': '1',
                                'avgLI': '1.25',
                            },
                        },
                    },
                },
            },
            'away': {
                'team': {'id': 2, 'name': 'Away Club'},
                'pitchers': [202],
                'players': {
                    'ID202': {
                        'person': {'fullName': 'Away Reliever'},
                        'stats': {
                            'pitching': {
                                'inningsPitched': '0.2',
                                'numberOfPitches': '11',
                                'strikes': '7',
                                'hits': '1',
                                'runs': '0',
                                'earnedRuns': '0',
                                'baseOnBalls': '0',
                                'strikeOuts': '1',
                                'homeRuns': '0',
                                'saves': '1',
                                'leverageIndex': '1.9',
                            },
                        },
                    },
                },
            },
        },
    }


def _play_by_play():
    return {
        'allPlays': [
            {
                'playId': 'play-0',
                'about': {
                    'atBatIndex': 0,
                    'inning': 1,
                    'halfInning': 'top',
                    'outs': 0,
                    'isComplete': True,
                    'isScoringPlay': False,
                },
                'result': {
                    'eventType': 'field_out',
                    'homeScore': 0,
                    'awayScore': 0,
                },
                'matchup': {
                    'pitcher': {'id': 101},
                    'batter': {'id': 901},
                },
            },
            {
                'playId': 'play-1',
                'about': {
                    'atBatIndex': 1,
                    'inning': 1,
                    'halfInning': 'bottom',
                    'outs': 0,
                    'isComplete': True,
                    'isScoringPlay': False,
                },
                'result': {
                    'eventType': 'field_out',
                    'homeScore': 0,
                    'awayScore': 0,
                },
                'matchup': {
                    'pitcher': {'id': 202},
                    'batter': {'id': 902},
                },
            },
        ],
    }


def _patch_mlb(monkeypatch, schedule_games, boxscore=None, linescore=None,
               play_by_play=_DEFAULT_PBP):
    calls = {'schedule': 0, 'boxscore': [], 'linescore': [], 'play_by_play': []}

    def fake_schedule(start_date=None, end_date=None, team_id=None):
        calls['schedule'] += 1
        assert start_date == '2026-06-20'
        assert end_date == '2026-06-20'
        assert team_id is None
        return schedule_games

    def fake_boxscore(game_pk):
        calls['boxscore'].append(game_pk)
        return boxscore if boxscore is not None else _boxscore()

    def fake_linescore(game_pk):
        calls['linescore'].append(game_pk)
        return linescore

    def fake_play_by_play(game_pk):
        calls['play_by_play'].append(game_pk)
        return _play_by_play() if play_by_play is _DEFAULT_PBP else play_by_play

    monkeypatch.setattr(sync_service.mlb_client, 'get_schedule', fake_schedule)
    monkeypatch.setattr(sync_service.mlb_client, 'get_game_boxscore', fake_boxscore)
    monkeypatch.setattr(sync_service.mlb_client, 'get_game_linescore', fake_linescore)
    monkeypatch.setattr(sync_service.mlb_client, 'get_game_play_by_play', fake_play_by_play)
    sync_service.mlb_client.metrics.reset()
    return calls


def _run(app):
    return sync_service.run_postgame_refresh(
        app,
        schedule_date=date(2026, 6, 20),
        source='test',
    )


def test_completed_game_detection_uses_final_schedule_status():
    assert sync_service.is_completed_game(_game(status_code='F'))
    assert sync_service.is_completed_game(_game(status_code='O', detailed_state='Game Over'))
    assert not sync_service.is_completed_game(
        _game(status_code='I', detailed_state='In Progress', abstract_state='Final')
    )
    assert not sync_service.is_completed_game(
        _game(status_code='F', detailed_state='Postponed', abstract_state='Final')
    )
    assert not sync_service.is_completed_game(_game(status_code='I', detailed_state='In Progress', abstract_state='Live'))
    assert not sync_service.is_completed_game({'status': {'statusCode': 'F'}})


def test_postgame_refresh_processes_newly_completed_games(app, monkeypatch):
    with app.app_context():
        _seed_pitchers()
    unfinished = _game(7002, status_code='I', detailed_state='In Progress', abstract_state='Live')
    calls = _patch_mlb(monkeypatch, [_game(), unfinished])

    status = _run(app)

    with app.app_context():
        logs = GameLog.query.order_by(GameLog.pitcher_id).all()
        marker = PostgameProcessedGame.query.filter_by(mlb_game_pk=7001).one()
        pbp_marker = PlayByPlayProcessedGame.query.filter_by(mlb_game_pk=7001).one()
        run = SyncRun.query.order_by(SyncRun.id.desc()).first()
        payload = sync_metadata.build_sync_status_payload()

    assert status['status'] == 'success'
    assert status['completed_games_found'] == 1
    assert status['newly_completed_games'] == 1
    assert status['games_processed'] == 1
    assert status['new_logs_added'] == 2
    assert status['pitchers_touched'] == 2
    assert calls['boxscore'] == [7001]
    assert calls['play_by_play'] == [7001]
    assert len(logs) == 2
    assert {log.mlb_game_pk for log in logs} == {7001}
    assert [log.innings_pitched_outs for log in logs] == [3, 2]
    assert [log.games_started for log in logs] == [1, 1]
    assert marker.logs_added == 2
    assert marker.pitchers_touched == 2
    assert pbp_marker.processing_status == PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED
    assert pbp_marker.events_stored == 2
    assert run.job_name == sync_metadata.JOB_POSTGAME_REFRESH
    assert run.latest_game_date == date(2026, 6, 20)
    assert run.new_logs_added == 2
    assert payload['last_completed_game_refresh'] is not None
    assert payload['last_completed_game_refresh_run']['job_name'] == sync_metadata.JOB_POSTGAME_REFRESH


def test_postgame_refresh_publishes_public_snapshots_before_internal_stages(
    app,
    monkeypatch,
):
    events = []
    with app.app_context():
        _seed_pitchers()
    _patch_mlb(monkeypatch, [_game()])

    def fake_complete(sync_run_id, **kwargs):
        events.append('dashboard_snapshot_publish')
        run = sync_metadata.finish_sync_run(
            sync_run_id,
            status=kwargs['final_status'],
            records_processed=kwargs.get('records_processed', 0),
            records_failed=kwargs.get('records_failed', 0),
            new_logs_added=kwargs.get('new_logs_added', 0),
            pitchers_updated=kwargs.get('pitchers_updated', 0),
            errors=kwargs.get('errors', 0),
            api_calls_made=kwargs.get('api_calls_made', 0),
            retries_used=kwargs.get('retries_used', 0),
            error_message=kwargs.get('error_message'),
            source=kwargs.get('source', 'test'),
            started_at=kwargs.get('started_at'),
            job_name=kwargs.get('job_name', sync_metadata.JOB_POSTGAME_REFRESH),
            published_dashboard_snapshot_id=456,
        )
        return run, SimpleNamespace(id=456)

    def fake_completed_game_context(*args, **kwargs):
        kwargs['status']['completed_game_contexts_upserted'] += 1

    def fake_intelligence_snapshot(schedule_date, *, status, run_logger):
        events.append('intelligence_snapshot_publish')
        status['intelligence_snapshot'] = 'ok'

    monkeypatch.setattr(sync_service, 'complete_sync_run_with_snapshot', fake_complete)
    monkeypatch.setattr(
        sync_service,
        '_safe_generate_completed_game_context',
        fake_completed_game_context,
    )
    monkeypatch.setattr(
        sync_service,
        '_safe_generate_intelligence_surface_snapshot',
        fake_intelligence_snapshot,
    )
    monkeypatch.setattr(
        sync_service,
        '_safe_build_workload_recovery_evidence_stage',
        lambda *args, **kwargs: (
            events.append(sync_metadata.STAGE_WORKLOAD_EVIDENCE)
            or {'status': 'built'}
        ),
    )
    monkeypatch.setattr(
        sync_service,
        '_safe_build_composed_reads_stage',
        lambda *args, **kwargs: (
            events.append(sync_metadata.STAGE_COMPOSED_READS)
            or {'status': 'built'}
        ),
    )
    monkeypatch.setattr(
        sync_service,
        '_safe_run_legacy_read_reconciliation_audit_stage',
        lambda *args, **kwargs: (
            events.append(sync_service.STAGE_LEGACY_READ_RECONCILIATION_AUDIT)
            or {'status': 'completed'}
        ),
    )

    status = _run(app)

    assert status['status'] == sync_metadata.STATUS_SUCCESS
    assert status['dashboard_snapshot_id'] == 456
    assert status['intelligence_snapshot'] == 'ok'
    assert events == [
        'dashboard_snapshot_publish',
        'intelligence_snapshot_publish',
        sync_metadata.STAGE_WORKLOAD_EVIDENCE,
        sync_metadata.STAGE_COMPOSED_READS,
        sync_service.STAGE_LEGACY_READ_RECONCILIATION_AUDIT,
    ]
    with app.app_context():
        run = SyncRun.query.order_by(SyncRun.id.desc()).first()
        assert run.stage == sync_metadata.STAGE_PUBLISHED
        assert run.published_dashboard_snapshot_id == 456


def test_postgame_refresh_public_only_skips_internal_enrichment(app, monkeypatch):
    with app.app_context():
        _seed_pitchers()
    _patch_mlb(monkeypatch, [_game()])
    monkeypatch.setattr(
        sync_service,
        '_safe_build_workload_recovery_evidence_stage',
        lambda *args, **kwargs: pytest.fail('workload evidence should not run'),
    )
    monkeypatch.setattr(
        sync_service,
        '_safe_build_composed_reads_stage',
        lambda *args, **kwargs: pytest.fail('composed reads should not run'),
    )
    monkeypatch.setattr(
        sync_service,
        '_safe_run_legacy_read_reconciliation_audit_stage',
        lambda *args, **kwargs: pytest.fail('reconciliation audit should not run'),
    )

    status = sync_service.run_postgame_refresh(
        app,
        schedule_date=date(2026, 6, 20),
        source='test',
        include_internal_enrichment=False,
    )

    assert status['status'] == sync_metadata.STATUS_SUCCESS
    assert status['dashboard_snapshot_id'] == 123
    assert status['internal_enrichment'] == 'skipped_public_only'
    with app.app_context():
        run = SyncRun.query.order_by(SyncRun.id.desc()).first()
        assert run.job_name == sync_metadata.JOB_POSTGAME_REFRESH
        assert run.stage == sync_metadata.STAGE_PUBLISHED
        assert SyncJob.query.count() == 0


def test_postgame_refresh_is_idempotent_for_already_processed_games(app, monkeypatch):
    with app.app_context():
        _seed_pitchers()
    calls = _patch_mlb(monkeypatch, [_game()])

    first = _run(app)
    second = _run(app)

    with app.app_context():
        game_log_count = GameLog.query.count()
        marker_count = PostgameProcessedGame.query.count()
        postgame_runs = SyncRun.query.filter_by(job_name=sync_metadata.JOB_POSTGAME_REFRESH).count()

    assert first['new_logs_added'] == 2
    assert second['new_logs_added'] == 0
    assert second['games_already_processed'] == 1
    assert calls['boxscore'] == [7001]
    assert calls['play_by_play'] == [7001]
    assert game_log_count == 2
    assert marker_count == 1
    assert postgame_runs == 2


def test_postgame_refresh_retries_pbp_for_already_processed_game(app, monkeypatch):
    with app.app_context():
        _seed_pitchers()
        db.session.add(PostgameProcessedGame(
            mlb_game_pk=7001,
            game_date=date(2026, 6, 20),
            processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
            attempt_count=1,
            processed_at=datetime(2026, 6, 20, 23, 0, 0),
        ))
        db.session.commit()
    calls = _patch_mlb(monkeypatch, [_game()])

    status = _run(app)

    with app.app_context():
        game_log_count = GameLog.query.count()
        pbp_marker = PlayByPlayProcessedGame.query.filter_by(mlb_game_pk=7001).one()

    assert status['status'] == 'success'
    assert status['new_logs_added'] == 0
    assert status['games_already_processed'] == 1
    assert game_log_count == 0
    assert calls['boxscore'] == [7001]
    assert calls['play_by_play'] == [7001]
    assert pbp_marker.processing_status == PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED
    assert pbp_marker.events_stored == 2


def test_pbp_absence_does_not_change_postgame_refresh_status(app, monkeypatch):
    with app.app_context():
        _seed_pitchers()
    calls = _patch_mlb(monkeypatch, [_game()], play_by_play={'allPlays': []})

    status = _run(app)

    with app.app_context():
        postgame_marker = PostgameProcessedGame.query.filter_by(mlb_game_pk=7001).one()
        pbp_marker = PlayByPlayProcessedGame.query.filter_by(mlb_game_pk=7001).one()
        event_count = GamePlayByPlayEvent.query.count()

    assert status['status'] == 'success'
    assert status['new_logs_added'] == 2
    assert status['records_failed'] == 0
    assert calls['play_by_play'] == [7001]
    assert postgame_marker.processing_status == PostgameProcessedGame.STATUS_FULLY_PROCESSED
    assert pbp_marker.processing_status == PlayByPlayProcessedGame.STATUS_ABSENT
    assert event_count == 0


def test_postgame_refresh_skips_unfinished_games_without_boxscore(app, monkeypatch):
    with app.app_context():
        _seed_pitchers()
    unfinished = _game(7002, status_code='I', detailed_state='In Progress', abstract_state='Live')
    calls = _patch_mlb(monkeypatch, [unfinished])

    status = _run(app)

    with app.app_context():
        game_log_count = GameLog.query.count()
        marker_count = PostgameProcessedGame.query.count()
        run = SyncRun.query.order_by(SyncRun.id.desc()).first()

    assert status['status'] == 'success'
    assert status['completed_games_found'] == 0
    assert status['newly_completed_games'] == 0
    assert status['new_logs_added'] == 0
    assert calls['boxscore'] == []
    assert game_log_count == 0
    assert marker_count == 0
    assert run.job_name == sync_metadata.JOB_POSTGAME_REFRESH
    assert run.new_logs_added == 0


def test_existing_workload_row_is_not_duplicated_when_marker_is_missing(app, monkeypatch):
    with app.app_context():
        home, _away = _seed_pitchers()
        home_id = home.id
        db.session.add(GameLog(
            pitcher_id=home_id,
            mlb_game_pk=7001,
            game_date=date(2026, 6, 20),
            innings_pitched=1.0,
            innings_pitched_outs=3,
            pitches_thrown=12,
        ))
        db.session.commit()
    _patch_mlb(monkeypatch, [_game()])

    status = _run(app)

    with app.app_context():
        logs = GameLog.query.order_by(GameLog.pitcher_id).all()
        marker = PostgameProcessedGame.query.filter_by(mlb_game_pk=7001).one()

    assert status['new_logs_added'] == 1
    assert len(logs) == 2
    assert sum(1 for log in logs if log.pitcher_id == home_id and log.mlb_game_pk == 7001) == 1
    assert marker.logs_added == 1


def test_postgame_schedule_date_keeps_late_cleanup_on_prior_baseball_date():
    assert sync_service.postgame_schedule_date(datetime(2026, 6, 21, 6, 30)).isoformat() == '2026-06-20'
    assert sync_service.postgame_schedule_date(datetime(2026, 6, 20, 20, 0)).isoformat() == '2026-06-20'


# ── Observability: phase/per-game/summary logging ─────────────────────────────

def test_postgame_refresh_logs_per_game_and_final_summary(app, monkeypatch, caplog):
    import logging
    with app.app_context():
        _seed_pitchers()
    _patch_mlb(monkeypatch, [_game()])

    with caplog.at_level(logging.INFO, logger='baseballos.postgame_refresh'):
        status = _run(app)

    messages = [r.getMessage() for r in caplog.records]
    # Per-game elapsed/outcome line for the one processed game.
    assert any(
        'postgame_refresh game_done game_pk=7001 outcome=processed elapsed_ms=' in m
        for m in messages
    ), messages
    assert any(
        m.startswith('Postgame ingestion complete for 2026-06-20:')
        and 'processed=1' in m
        and 'logs_added=2' in m
        for m in messages
    ), messages
    assert any(
        m.startswith('Fatigue recalculation complete:')
        and 'pitchers_updated=2' in m
        and 'elapsed_ms=' in m
        for m in messages
    ), messages
    # Final summary line with the counters + elapsed_ms.
    assert any(
        m.startswith('postgame_refresh completed status=') and 'elapsed_ms=' in m
        and 'processed=1' in m
        for m in messages
    ), messages
    assert status['elapsed_ms'] >= 0
    assert status['games_skipped'] == 0


def test_intelligence_surface_snapshot_skipped_by_config(app, monkeypatch):
    """The expensive homepage rebuild can be skipped via env without affecting
    completed-game correctness (it is the optional tail)."""
    import services.intelligence_surface_snapshot as iss

    called = {'n': 0}
    monkeypatch.setattr(
        iss, 'generate_snapshot_for_date',
        lambda *a, **k: called.__setitem__('n', called['n'] + 1))
    monkeypatch.setenv('POSTGAME_REFRESH_SNAPSHOT', 'false')

    status = {}
    run_logger = sync_service.logging.getLogger('baseballos.postgame_refresh')
    with app.app_context():
        sync_service._safe_generate_intelligence_surface_snapshot(
            date(2026, 6, 20), status=status, run_logger=run_logger)

    assert called['n'] == 0
    assert status['intelligence_snapshot'] == 'skipped_by_config'


def test_intelligence_surface_snapshot_logs_start_and_elapsed(app, monkeypatch, caplog):
    import logging
    import services.intelligence_surface_snapshot as iss

    monkeypatch.delenv('POSTGAME_REFRESH_SNAPSHOT', raising=False)
    monkeypatch.setattr(
        iss, 'generate_snapshot_for_date',
        lambda *a, **k: {'status': 'ok', 'publishable_candidates': 1})

    status = {}
    run_logger = sync_service.logging.getLogger('baseballos.postgame_refresh')
    with caplog.at_level(logging.INFO, logger='baseballos.postgame_refresh'):
        with app.app_context():
            sync_service._safe_generate_intelligence_surface_snapshot(
                date(2026, 6, 20), status=status, run_logger=run_logger)

    messages = [r.getMessage() for r in caplog.records]
    assert any('Intelligence surface snapshot refresh starting' in m for m in messages), messages
    assert any(
        'Intelligence surface snapshot refresh completed' in m and 'elapsed_ms=' in m
        for m in messages
    ), messages
    assert status['intelligence_snapshot'] == 'ok'


def test_intelligence_surface_snapshot_timeout_is_logged_and_fail_soft(
    app,
    monkeypatch,
    caplog,
):
    import logging

    def _timeout(*args, **kwargs):
        raise sync_service._PostgameSnapshotTimeout(
            'Intelligence surface snapshot exceeded 0.25s')

    monkeypatch.delenv('POSTGAME_REFRESH_SNAPSHOT', raising=False)
    monkeypatch.setenv('POSTGAME_REFRESH_SNAPSHOT_TIMEOUT_SECONDS', '0.25')
    monkeypatch.setattr(
        sync_service,
        '_run_intelligence_surface_snapshot_with_timeout',
        _timeout,
    )

    status = {}
    run_logger = sync_service.logging.getLogger('baseballos.postgame_refresh')
    with caplog.at_level(logging.WARNING, logger='baseballos.postgame_refresh'):
        with app.app_context():
            sync_service._safe_generate_intelligence_surface_snapshot(
                date(2026, 6, 20), status=status, run_logger=run_logger)

    messages = [r.getMessage() for r in caplog.records]
    assert status['intelligence_snapshot'] == 'timed_out'
    assert status['intelligence_snapshot_error'] == (
        'Intelligence surface snapshot exceeded 0.25s')
    assert any(
        'Intelligence surface snapshot refresh timed out' in m
        and 'postgame refresh will continue' in m
        for m in messages
    ), messages


def test_postgame_sync_workflow_job_timeout_is_25_minutes():
    """Static guard: the sync job timeout must give the postgame path enough
    headroom for the homepage rebuild (regression lock for the 15m cancellation)."""
    from pathlib import Path

    workflow = Path(__file__).resolve().parents[2] / '.github/workflows/baseballos-sync.yml'
    text = workflow.read_text(encoding='utf-8').replace('\r\n', '\n')

    jobs_section = text.split('\njobs:\n', 1)[1]
    sync_body = jobs_section.split('  public-sync:\n', 1)[1]
    sync_lines = []
    for line in sync_body.splitlines():
        if line.startswith('  ') and not line.startswith('    '):
            break
        sync_lines.append(line)
    sync_block = '\n'.join(sync_lines)

    assert '    timeout-minutes: 25' in sync_block
    assert "    - cron: '0 10 * * *'" in text
    assert "    - cron: '0 2,4,6 * * *'" in text
    assert '\nconcurrency:\n  group: baseballos-sync\n  cancel-in-progress: false\n' in text
    assert '          - daily\n          - postgame\n' in text


def test_postgame_sync_workflow_warms_tonight_after_postgame_refresh():
    """Static guard: postgame runs must warm the Tonight snapshot after the
    completed-game refresh, while daily warming remains intact."""
    from pathlib import Path

    workflow = Path(__file__).resolve().parents[2] / '.github/workflows/baseballos-sync.yml'
    text = workflow.read_text(encoding='utf-8').replace('\r\n', '\n')

    daily_step = '      - name: Refresh schedule and warm Tonight\n'
    postgame_step = '      - name: Refresh schedule and warm Tonight after postgame\n'
    assert daily_step in text
    assert postgame_step in text
    assert text.index('      - name: Run direct postgame refresh\n') < text.index(postgame_step)
    assert text.index(postgame_step) < text.index('      - name: Verify dashboard snapshot cache\n')

    daily_block = text.split(daily_step, 1)[1].split('\n      - name:', 1)[0]
    postgame_block = text.split(postgame_step, 1)[1].split('\n      - name:', 1)[0]
    assert 'TONIGHT_REFRESH_COMMAND_TIMEOUT: 10m' in daily_block
    assert "TONIGHT_REFRESH_SCHEDULE_TIMEOUT_SECONDS: '180'" in daily_block
    assert "TONIGHT_REFRESH_WARM_TIMEOUT_SECONDS: '300'" in daily_block
    assert 'Refresh schedule and warm Tonight starting at' in daily_block
    assert 'Refresh schedule and warm Tonight completed at' in daily_block
    assert (
        'timeout --kill-after=30s "$TONIGHT_REFRESH_COMMAND_TIMEOUT" '
        'python backend/scripts/run_tonight_refresh.py --source github_actions'
    ) in daily_block

    assert "inputs.mode == 'postgame'" in postgame_block
    assert "github.event.schedule != '0 10 * * *'" in postgame_block
    assert 'TONIGHT_REFRESH_COMMAND_TIMEOUT: 10m' in postgame_block
    assert "TONIGHT_REFRESH_SCHEDULE_TIMEOUT_SECONDS: '180'" in postgame_block
    assert "TONIGHT_REFRESH_WARM_TIMEOUT_SECONDS: '300'" in postgame_block
    assert 'Refresh schedule and warm Tonight after postgame starting at' in postgame_block
    assert 'Refresh schedule and warm Tonight after postgame completed at' in postgame_block
    assert (
        'timeout --kill-after=30s "$TONIGHT_REFRESH_COMMAND_TIMEOUT" '
        'python backend/scripts/run_tonight_refresh.py --source github_actions_postgame'
    ) in postgame_block


def test_sync_workflow_direct_sync_steps_have_command_timeouts():
    """Static guard: long-running direct sync commands fail with named errors
    before the workflow job timeout is the only signal."""
    from pathlib import Path

    workflow = Path(__file__).resolve().parents[2] / '.github/workflows/baseballos-sync.yml'
    text = workflow.read_text(encoding='utf-8').replace('\r\n', '\n')

    daily_step = '      - name: Run direct daily sync\n'
    postgame_step = '      - name: Run direct postgame refresh\n'
    daily_block = text.split(daily_step, 1)[1].split('\n      - name:', 1)[0]
    postgame_block = text.split(postgame_step, 1)[1].split('\n      - name:', 1)[0]

    assert 'DAILY_SYNC_COMMAND_TIMEOUT: 20m' in daily_block
    assert 'Direct daily sync starting at' in daily_block
    assert 'Direct daily sync completed at' in daily_block
    assert (
        'timeout --kill-after=30s "$DAILY_SYNC_COMMAND_TIMEOUT" '
        'python backend/scripts/run_daily_sync.py --days-back 7 --source github_actions --public-only'
    ) in daily_block
    assert '::error::Direct daily sync timed out after $DAILY_SYNC_COMMAND_TIMEOUT.' in daily_block

    assert 'POSTGAME_REFRESH_COMMAND_TIMEOUT: 20m' in postgame_block
    assert 'Direct postgame refresh starting at' in postgame_block
    assert 'Direct postgame refresh completed at' in postgame_block
    assert (
        'timeout --kill-after=30s "$POSTGAME_REFRESH_COMMAND_TIMEOUT" '
        'python backend/scripts/run_postgame_refresh.py --source github_actions --public-only'
    ) in postgame_block
    assert (
        '::error::Direct postgame refresh timed out after $POSTGAME_REFRESH_COMMAND_TIMEOUT.'
        in postgame_block
    )


def test_sync_workflow_splits_public_and_internal_enrichment_jobs():
    from pathlib import Path

    workflow = Path(__file__).resolve().parents[2] / '.github/workflows/baseballos-sync.yml'
    text = workflow.read_text(encoding='utf-8').replace('\r\n', '\n')
    jobs_section = text.split('\njobs:\n', 1)[1]
    public_body = jobs_section.split('  public-sync:\n', 1)[1].split(
        '\n  internal-enrichment:\n',
        1,
    )[0]
    internal_body = jobs_section.split('  internal-enrichment:\n', 1)[1].split(
        '\n  static-team-story-preview:\n',
        1,
    )[0]
    static_body = jobs_section.split('  static-team-story-preview:\n', 1)[1]

    assert 'backend/scripts/run_daily_sync.py --days-back 7 --source github_actions --public-only' in public_body
    assert 'backend/scripts/run_postgame_refresh.py --source github_actions --public-only' in public_body
    assert 'backend/scripts/run_internal_enrichment.py' not in public_body
    assert 'continue-on-error: true' in internal_body
    assert 'needs: public-sync' in internal_body
    assert 'backend/scripts/run_internal_enrichment.py --mode daily --source github_actions_internal' in internal_body
    assert (
        'backend/scripts/run_internal_enrichment.py --mode postgame '
        '--source github_actions_internal --skip-backtest'
    ) in internal_body
    assert 'needs: public-sync' in static_body
    assert 'backend/scripts/export_team_story_pages.py' in static_body
