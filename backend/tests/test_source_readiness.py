from datetime import date, datetime

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

from models.dashboard_snapshot import DashboardSnapshot
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from models.sync_run import SyncRun
from models.sync_failure import SyncFailure
from services import slate_coverage, source_readiness, sync_metadata
from utils.db import db
import models.prospect  # noqa: F401  (full model registry for create_all)


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


def test_classify_ready_source():
    readiness = source_readiness.classify_source_readiness(
        'fixture',
        last_successful_at=date(2026, 6, 1),
        last_attempted_at=datetime(2026, 6, 1, 12, 0, 0),
        stale_after_days=2,
        reference_date=date(2026, 6, 2),
        sync_run_id=10,
        source='test',
    )

    assert readiness.status == source_readiness.READY
    assert readiness.fail_closed is False
    assert readiness.to_dict()['sync_run_id'] == 10


@pytest.mark.parametrize(
    ('kwargs', 'expected_status', 'expected_reason'),
    [
        ({}, source_readiness.NEVER_FETCHED, 'source_never_fetched'),
        (
            {'last_attempted_at': datetime(2026, 6, 1, 12, 0, 0)},
            source_readiness.UNAVAILABLE,
            'source_unavailable',
        ),
        (
            {
                'last_successful_at': date(2026, 6, 1),
                'last_attempted_at': datetime(2026, 6, 1, 12, 0, 0),
                'stale_after_days': 2,
                'reference_date': date(2026, 6, 5),
            },
            source_readiness.STALE,
            'source_stale',
        ),
        (
            {
                'last_successful_at': date(2026, 6, 1),
                'dead_letter_count': 1,
                'reference_date': date(2026, 6, 2),
            },
            source_readiness.DEGRADED,
            'dead_letters_unresolved',
        ),
        (
            {
                'last_successful_at': date(2026, 6, 1),
                'provenance_present': False,
                'reference_date': date(2026, 6, 2),
            },
            source_readiness.UNAVAILABLE,
            'provenance_missing',
        ),
    ],
)
def test_non_ready_states_fail_closed(kwargs, expected_status, expected_reason):
    readiness = source_readiness.classify_source_readiness('fixture', **kwargs)

    assert readiness.status == expected_status
    assert readiness.fail_closed is True
    assert expected_reason in readiness.reason_codes


def test_source_readiness_payload_reports_existing_foundations(app):
    with app.app_context():
        pitcher = Pitcher(
            mlb_id=1,
            full_name='A',
            team_id=116,
            active=True,
            roster_status='ACTIVE',
            roster_status_source='mlb_stats_api',
            roster_status_updated_at=datetime(2026, 6, 2, 9, 0, 0),
        )
        db.session.add(pitcher)
        db.session.commit()
        db.session.add(GameLog(
            pitcher_id=pitcher.id,
            mlb_game_pk=31,
            game_date=date(2026, 6, 1),
            innings_pitched=1.0,
            innings_pitched_outs=3,
        ))
        db.session.add(FatigueScore(
            pitcher_id=pitcher.id,
            raw_score=42.0,
            calculated_at=datetime(2026, 6, 2, 9, 0, 0),
        ))
        db.session.add_all([
            ScheduledGame(
                team_id=116,
                game_pk=31,
                game_date=date(2026, 6, 1),
                status_state='final',
                home_away='home',
                opponent_team_id=142,
            ),
            ScheduledGame(
                team_id=142,
                game_pk=31,
                game_date=date(2026, 6, 1),
                status_state='final',
                home_away='away',
                opponent_team_id=116,
            ),
        ])
        db.session.add(PostgameProcessedGame(
            mlb_game_pk=31,
            game_date=date(2026, 6, 1),
            processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
        ))
        run = SyncRun(
            job_name='daily_sync',
            started_at=datetime(2026, 6, 2, 8, 59, 0),
            completed_at=datetime(2026, 6, 2, 9, 1, 0),
            status='success',
            source='github_actions',
            latest_game_date=date(2026, 6, 1),
            latest_workload_date=date(2026, 6, 1),
            latest_fatigue_calculated_at=datetime(2026, 6, 2, 9, 0, 0),
        )
        db.session.add(run)
        db.session.commit()
        db.session.add(DashboardSnapshot(
            snapshot_type='bullpen_dashboard',
            sync_run_id=run.id,
            status='ready',
            is_published=True,
            payload={},
            data_through=date(2026, 6, 1),
            availability_reference_date=date(2026, 6, 2),
            snapshot_generated_at=datetime(2026, 6, 2, 9, 2, 0),
            source='sync',
        ))
        db.session.commit()

        coverage = slate_coverage.compute_slate_coverage(date(2026, 6, 1))
        payload = source_readiness.source_readiness_payload(
            metadata=sync_metadata.collect_data_metadata(),
            sync_status='success',
            slate_coverage_payload=coverage,
            reference_date=date(2026, 6, 2),
        )

    assert payload['overall_status'] == source_readiness.READY
    assert payload['fail_closed'] is False
    families = payload['families']
    assert families['finality_authority']['status'] == source_readiness.READY
    assert families['statsapi_core']['status'] == source_readiness.READY
    assert families['game_logs']['status'] == source_readiness.READY
    assert families['slate_coverage']['status'] == source_readiness.READY
    assert families['dashboard_snapshots']['status'] == source_readiness.READY
    assert families['roster_status_current']['status'] == source_readiness.READY


def test_source_readiness_payload_blocks_incomplete_slate(app):
    with app.app_context():
        db.session.add(SyncRun(
            job_name='daily_sync',
            started_at=datetime(2026, 6, 2, 8, 59, 0),
            completed_at=datetime(2026, 6, 2, 9, 1, 0),
            status='success',
            source='github_actions',
        ))
        db.session.add(SyncFailure(
            job_name='daily_sync',
            entity_type='pitcher_game_logs',
            entity_ref='1',
            error='shape failure',
            resolved=False,
        ))
        db.session.commit()
        coverage = slate_coverage.unknown_slate_coverage(date(2026, 6, 1))
        payload = source_readiness.source_readiness_payload(
            metadata={},
            sync_status='success',
            slate_coverage_payload=coverage,
            reference_date=date(2026, 6, 2),
        )

    assert payload['fail_closed'] is True
    assert 'slate_coverage' in payload['blocking_source_families']
    assert payload['families']['slate_coverage']['status'] == source_readiness.DEGRADED
    assert payload['families']['game_logs']['status'] != source_readiness.READY
