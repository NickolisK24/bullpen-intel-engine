from datetime import date, datetime

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

from models.dashboard_snapshot import DashboardSnapshot
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from models.sync_run import SyncRun
from scripts import diagnose_slate_coverage
from services import sync_metadata
from utils.db import db
import services.source_readiness  # noqa: F401  (register readiness models before create_all)


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


def _pitcher():
    pitcher = Pitcher(
        mlb_id=9001,
        full_name='Fixture Pitcher',
        team_id=116,
        active=True,
    )
    db.session.add(pitcher)
    db.session.flush()
    return pitcher


def _schedule_game(game_pk, game_date, *, home_id=116, away_id=142, status='final'):
    db.session.add_all([
        ScheduledGame(
            team_id=home_id,
            game_pk=game_pk,
            game_date=game_date,
            status_code='F' if status == ScheduledGame.STATE_FINAL else None,
            status_state=status,
            home_away='home',
            opponent_team_id=away_id,
        ),
        ScheduledGame(
            team_id=away_id,
            game_pk=game_pk,
            game_date=game_date,
            status_code='F' if status == ScheduledGame.STATE_FINAL else None,
            status_state=status,
            home_away='away',
            opponent_team_id=home_id,
        ),
    ])


def _postgame_marker(
    game_pk,
    game_date,
    *,
    status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
    home_id=116,
    away_id=142,
    **kwargs,
):
    payload = {
        'mlb_game_pk': game_pk,
        'game_date': game_date,
        'home_team_id': home_id,
        'away_team_id': away_id,
        'processing_status': status,
    }
    payload.update(kwargs)
    db.session.add(PostgameProcessedGame(**payload))


def _sync_run(game_date, *, status=sync_metadata.STATUS_SUCCESS):
    run = SyncRun(
        job_name=sync_metadata.JOB_POSTGAME_REFRESH,
        started_at=datetime(2026, 7, 6, 4, 0, 0),
        completed_at=datetime(2026, 7, 6, 4, 2, 0),
        status=status,
        source=sync_metadata.SOURCE_GITHUB_ACTIONS,
        latest_game_date=game_date,
        latest_workload_date=game_date,
        latest_fatigue_calculated_at=datetime(2026, 7, 6, 4, 1, 0),
        created_at=datetime(2026, 7, 6, 4, 0, 0),
    )
    db.session.add(run)
    db.session.flush()
    return run


def _published_snapshot(data_through, *, sync_run_id):
    db.session.add(DashboardSnapshot(
        snapshot_type='bullpen_dashboard',
        sync_run_id=sync_run_id,
        status='ready',
        is_published=True,
        published_at=datetime(2026, 7, 4, 4, 0, 0),
        payload_version=1,
        payload={
            'freshness': {
                'data_through': data_through.isoformat(),
                'latest_workload_date': data_through.isoformat(),
                'availability_reference_date': (data_through).isoformat(),
                'sync_status': sync_metadata.STATUS_SUCCESS,
                'is_current': True,
                'freshness_state': 'current',
                'slate_coverage': {
                    'slate_date': data_through.isoformat(),
                    'validations_passed': True,
                    'complete_enough_to_publish': True,
                    'reason_codes': ['slate_complete'],
                },
            },
        },
        data_through=data_through,
        availability_reference_date=data_through,
        snapshot_generated_at=datetime(2026, 7, 4, 4, 0, 0),
        source='test',
    ))


def test_arg_parser_accepts_target_slate_without_importing_app():
    args = diagnose_slate_coverage._parse_args([
        '--slate-date',
        '2026-07-05',
        '--reference-date',
        '2026-07-06',
        '--compact',
    ])

    assert args.slate_date == '2026-07-05'
    assert args.reference_date == '2026-07-06'
    assert args.compact is True


def test_report_identifies_incomplete_july_5_slate_and_public_data_through(app):
    slate_date = date(2026, 7, 5)
    with app.app_context():
        pitcher = _pitcher()
        db.session.add(GameLog(
            pitcher_id=pitcher.id,
            mlb_game_pk=9501,
            game_date=slate_date,
            innings_pitched=1.0,
            innings_pitched_outs=3,
        ))
        _schedule_game(9501, slate_date, home_id=116, away_id=142)
        _schedule_game(9502, slate_date, home_id=121, away_id=147)
        _postgame_marker(
            9501,
            slate_date,
            status=PostgameProcessedGame.STATUS_INCOMPLETE,
            home_id=116,
            away_id=142,
            incomplete_reason='pitcher_resolution_failures',
            attempt_count=2,
            pitching_lines_seen=6,
            pitcher_resolution_failures=1,
            correction_attempts_failed=1,
            last_attempted_at=datetime(2026, 7, 6, 4, 5, 0),
        )
        run = _sync_run(slate_date)
        _published_snapshot(date(2026, 7, 3), sync_run_id=run.id)
        db.session.commit()

        report = diagnose_slate_coverage.build_report(
            slate_date=slate_date,
            reference_date=date(2026, 7, 6),
        )

    assert report['latest_checked_date'] == '2026-07-05'
    assert report['latest_checked_baseball_date'] == '2026-07-05'
    assert report['latest_published_public_data_through'] == '2026-07-03'
    assert report['failed_slate_date'] == '2026-07-05'
    assert report['publishable'] is False
    assert report['freshness']['freshness_state'] == 'incomplete'
    assert report['slate_coverage']['complete_enough_to_publish'] is False
    assert report['slate_coverage']['games_final'] == 2
    assert report['slate_coverage']['games_fully_ingested'] == 0
    assert report['failure_domains'] == [
        'postgame_markers',
        'pitcher_resolution',
        'validations',
    ]
    assert report['failed_game_pks'] == [9501, 9502]
    assert report['failed_team_ids'] == [116, 121, 142, 147]
    assert report['postgame_blocker_reason_counts'] == {
        'incomplete_marker': 1,
        'missing_marker': 1,
    }
    assert report['postgame_blocker_incomplete_reason_counts'] == {
        'pitcher_resolution_failures': 1,
    }
    assert [game['mlb_game_pk'] for game in report['failed_games']] == [9501, 9502]
    assert report['failed_games'][0]['incomplete_reason'] == 'pitcher_resolution_failures'
    assert report['failed_games'][0]['pitcher_resolution_failures'] == 1
    assert report['failed_games'][1]['marker_status'] == 'missing'
    assert 'slate_coverage' in report['source_readiness']['blocking_source_families']


def test_report_has_no_failed_slate_when_target_slate_is_complete(app):
    slate_date = date(2026, 7, 5)
    with app.app_context():
        pitcher = _pitcher()
        db.session.add(GameLog(
            pitcher_id=pitcher.id,
            mlb_game_pk=9601,
            game_date=slate_date,
            innings_pitched=1.0,
            innings_pitched_outs=3,
        ))
        _schedule_game(9601, slate_date, home_id=116, away_id=142)
        _postgame_marker(9601, slate_date, home_id=116, away_id=142)
        run = _sync_run(slate_date)
        _published_snapshot(slate_date, sync_run_id=run.id)
        db.session.commit()

        report = diagnose_slate_coverage.build_report(
            slate_date=slate_date,
            reference_date=date(2026, 7, 6),
        )

    assert report['publishable'] is True
    assert report['failed_slate_date'] is None
    assert report['failed_game_pks'] == []
    assert report['failed_games'] == []
    assert report['slate_coverage']['reason_codes'] == ['slate_complete']
