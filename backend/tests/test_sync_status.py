"""
Tests for the enriched GET /api/bullpen/sync/status endpoint.

The endpoint now reports the real data snapshot (latest game date + log count)
alongside durable sync metadata, so the dashboard can tell sync timestamps
apart from data-through dates.

Runs against in-memory SQLite (no Postgres / MLB / network). The sync status
file is pointed at an empty temp path so durable metadata is the authority.
"""

from datetime import date, datetime

import pytest
from flask import Flask

import services.sync as sync_service
from services import sync_metadata
from utils.db import db
from models.pitcher import Pitcher
from models.game_log import GameLog
from models.fatigue_score import FatigueScore
from models.sync_run import SyncRun
import models.prospect        # noqa: F401  (register on db.metadata)
from api.bullpen import bullpen_bp


@pytest.fixture
def client(tmp_path, monkeypatch):
    # No real sync_status.json. The status endpoint must not depend on it.
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    monkeypatch.setattr(sync_metadata, 'product_current_date', lambda: date(2026, 6, 1))

    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    with app.app_context():
        db.create_all()
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            db.drop_all()


class TestSyncStatusSnapshot:
    def test_reports_snapshot_when_data_present_but_no_sync(self, client):
        with client.application.app_context():
            p = Pitcher(mlb_id=1, full_name='A', team_id=1, active=True)
            db.session.add(p)
            db.session.commit()
            db.session.add(GameLog(pitcher_id=p.id, mlb_game_pk=10, game_date=date(2025, 9, 1)))
            db.session.add(GameLog(pitcher_id=p.id, mlb_game_pk=11, game_date=date(2025, 9, 10)))
            db.session.commit()

        res = client.get('/api/bullpen/sync/status')
        assert res.status_code == 200
        body = res.get_json()

        # No sync has run...
        assert body['last_sync'] is None
        assert body['status'] == 'metadata_unavailable'
        assert body['sync_authority'] == 'sync_runs'
        assert body['metadata_source'] == 'none'
        # ...but the data snapshot is reported honestly from the DB.
        assert body['data']['game_logs'] == 2
        assert body['data']['latest_game_date'] == '2025-09-10'
        assert body['data']['latest_workload_date'] == '2025-09-10'
        assert body['freshness']['freshness_state'] == 'stale'
        assert body['freshness']['is_stale'] is True
        assert body['freshness']['data_age_days'] is not None
        # Data this old is past the hard unavailable threshold, so the
        # fail-closed degradation tier surfaces an explicit reason code.
        assert body['freshness']['reason_codes'] == [
            'durable_sync_metadata_unavailable',
            'successful_sync_missing',
            'fatigue_timestamp_missing',
            'workload_data_outside_active_window',
            'workload_data_unavailable',
        ]
        assert body['freshness']['limitations'] == [
            'Sync metadata unavailable; data coverage is based on game logs.',
            'No durable successful sync timestamp is available.',
            'No fatigue calculation timestamp is available.',
            'Latest game date is outside the 14-day freshness window.',
            'Latest workload data is older than the 30-day availability '
            'threshold; availability is failing closed.',
        ]
        assert body['freshness']['degradation']['state'] == 'unavailable'
        assert body['freshness']['degradation']['fail_closed'] is True

    def test_reports_empty_when_no_data_and_no_sync(self, client):
        res = client.get('/api/bullpen/sync/status')
        assert res.status_code == 200
        body = res.get_json()
        assert body['last_sync'] is None
        assert body['last_successful_sync'] is None
        assert body['status'] == 'never'
        assert body['sync_authority'] == 'sync_runs'
        assert body['metadata_source'] == 'none'
        assert body['data']['game_logs'] == 0
        assert body['data']['latest_game_date'] is None
        assert body['data']['latest_workload_date'] is None
        assert body['data']['latest_fatigue_calculated_at'] is None
        assert body['freshness']['label'] == 'No baseball workload data loaded.'
        assert body['freshness']['freshness_state'] == 'missing'
        assert body['freshness']['is_stale'] is False
        assert body['freshness']['reason_codes'] == ['workload_data_missing']

    def test_reports_sync_timestamp_and_snapshot_date_together(self, client):
        with client.application.app_context():
            p = Pitcher(mlb_id=1, full_name='A', team_id=1, active=True)
            db.session.add(p)
            db.session.commit()
            db.session.add(GameLog(pitcher_id=p.id, mlb_game_pk=31, game_date=date(2026, 5, 31)))
            db.session.add(FatigueScore(
                pitcher_id=p.id,
                raw_score=42.0,
                calculated_at=datetime(2026, 6, 1, 21, 39, 55),
            ))
            db.session.add(SyncRun(
                started_at=datetime(2026, 6, 1, 21, 39, 12),
                completed_at=datetime(2026, 6, 1, 21, 39, 56),
                status='success',
                source='github_actions',
                latest_game_date=date(2026, 5, 31),
                latest_workload_date=date(2026, 5, 31),
                latest_fatigue_calculated_at=datetime(2026, 6, 1, 21, 39, 55),
                records_processed=120,
                new_logs_added=120,
                pitchers_updated=428,
                errors=0,
                created_at=datetime(2026, 6, 1, 21, 39, 12),
            ))
            db.session.commit()

        res = client.get('/api/bullpen/sync/status')
        assert res.status_code == 200
        body = res.get_json()

        assert body['status'] == 'success'
        assert body['sync_authority'] == 'sync_runs'
        assert body['metadata_source'] == 'sync_runs'
        assert body['last_sync'] == '2026-06-01T21:39:12'
        assert body['last_successful_sync'] == '2026-06-01T21:39:56'
        assert body['pitchers_updated'] == 428
        assert body['new_logs_added'] == 120
        assert body['data']['game_logs'] == 1
        assert body['data']['latest_game_date'] == '2026-05-31'
        assert body['data']['latest_workload_date'] == '2026-05-31'
        assert body['data']['latest_fatigue_calculated_at'] == '2026-06-01T21:39:55'
        assert body['freshness']['is_current'] is True
        assert body['freshness']['is_stale'] is False
        assert body['freshness']['freshness_state'] == 'current'
        assert body['freshness']['reason_codes'] == []
        assert body['freshness']['limitations'] == []
        assert body['sync']['source'] == 'github_actions'
        assert body['last_successful_sync_run']['status'] == 'success'

    def test_reports_failed_sync_without_hiding_last_successful_sync(self, client):
        with client.application.app_context():
            p = Pitcher(mlb_id=1, full_name='A', team_id=1, active=True)
            db.session.add(p)
            db.session.commit()
            db.session.add(GameLog(pitcher_id=p.id, mlb_game_pk=31, game_date=date(2026, 5, 31)))
            db.session.add(FatigueScore(
                pitcher_id=p.id,
                raw_score=42.0,
                calculated_at=datetime(2026, 6, 1, 21, 39, 55),
            ))
            db.session.add(SyncRun(
                started_at=datetime(2026, 6, 1, 21, 39, 12),
                completed_at=datetime(2026, 6, 1, 21, 39, 56),
                status='success',
                source='github_actions',
                created_at=datetime(2026, 6, 1, 21, 39, 12),
            ))
            db.session.add(SyncRun(
                started_at=datetime(2026, 6, 2, 10, 0, 0),
                completed_at=datetime(2026, 6, 2, 10, 0, 30),
                status='failed',
                source='github_actions',
                errors=1,
                error_message='MLB API unavailable',
                created_at=datetime(2026, 6, 2, 10, 0, 0),
            ))
            db.session.commit()

        res = client.get('/api/bullpen/sync/status')
        assert res.status_code == 200
        body = res.get_json()

        assert body['status'] == 'failed'
        assert body['last_sync'] == '2026-06-02T10:00:00'
        assert body['last_successful_sync'] == '2026-06-01T21:39:56'
        assert body['message'] == 'MLB API unavailable'
        assert body['freshness']['reason_codes'] == ['latest_sync_failed']
        assert 'The latest sync attempt failed; data may reflect an earlier successful sync.' in body['freshness']['limitations']

    def test_local_cache_file_is_not_used_without_durable_metadata(self, client):
        sync_service.write_status({
            'last_sync': '2026-06-01T12:00:00',
            'status': 'success',
            'pitchers_updated': 999,
            'new_logs_added': 999,
            'errors': 0,
            'message': 'cache should not be authoritative',
            'finished_at': '2026-06-01T12:01:00',
        })

        with client.application.app_context():
            p = Pitcher(mlb_id=1, full_name='A', team_id=1, active=True)
            db.session.add(p)
            db.session.commit()
            db.session.add(GameLog(pitcher_id=p.id, mlb_game_pk=31, game_date=date(2026, 5, 31)))
            db.session.commit()

        res = client.get('/api/bullpen/sync/status')
        assert res.status_code == 200
        body = res.get_json()

        assert body['status'] == 'metadata_unavailable'
        assert body['metadata_source'] == 'none'
        assert body['sync_authority'] == 'sync_runs'
        assert body['last_sync'] is None
        assert body['last_successful_sync'] is None
        assert body['pitchers_updated'] == 0
        assert body['message'] != 'cache should not be authoritative'
        assert body['freshness']['reason_codes'] == [
            'durable_sync_metadata_unavailable',
            'successful_sync_missing',
            'fatigue_timestamp_missing',
        ]

    def test_durable_metadata_overrides_a_conflicting_cache_file(self, client):
        """Durable sync_runs is authoritative; the JSON file is cache-only.

        Regression guard for the freshness finding in
        backend/reports/data_freshness_validation_summary.md: a stale or
        conflicting backend/logs/sync_status.json must never override durable
        metadata, and a successful durable sync must never report
        status: never / last_sync: null.
        """
        # A stale, conflicting cache file that (pre-fix) would have driven the
        # endpoint. It claims an old failed sync from a different day.
        sync_service.write_status({
            'last_sync': '2026-05-20T03:00:00',
            'status': 'failed',
            'pitchers_updated': 0,
            'new_logs_added': 0,
            'errors': 9,
            'message': 'stale cache file should not win',
            'finished_at': '2026-05-20T03:01:00',
        })

        with client.application.app_context():
            p = Pitcher(mlb_id=1, full_name='A', team_id=1, active=True)
            db.session.add(p)
            db.session.commit()
            db.session.add(GameLog(pitcher_id=p.id, mlb_game_pk=31, game_date=date(2026, 5, 31)))
            db.session.add(FatigueScore(
                pitcher_id=p.id,
                raw_score=42.0,
                calculated_at=datetime(2026, 6, 1, 21, 39, 55),
            ))
            db.session.add(SyncRun(
                started_at=datetime(2026, 6, 1, 21, 39, 12),
                completed_at=datetime(2026, 6, 1, 21, 39, 56),
                status='success',
                source='github_actions',
                latest_game_date=date(2026, 5, 31),
                latest_workload_date=date(2026, 5, 31),
                latest_fatigue_calculated_at=datetime(2026, 6, 1, 21, 39, 55),
                pitchers_updated=428,
                created_at=datetime(2026, 6, 1, 21, 39, 12),
            ))
            db.session.commit()

        res = client.get('/api/bullpen/sync/status')
        assert res.status_code == 200
        body = res.get_json()

        # Durable metadata wins; the conflicting cache file is ignored.
        assert body['status'] == 'success'
        assert body['last_sync'] == '2026-06-01T21:39:12'
        assert body['last_successful_sync'] == '2026-06-01T21:39:56'
        assert body['pitchers_updated'] == 428
        assert body['errors'] == 0
        assert body['message'] != 'stale cache file should not win'
        # The reported invariant — never null/never when durable metadata exists.
        assert body['last_sync'] is not None
        assert body['status'] != 'never'

    def test_sync_metadata_service_persists_start_and_completion(self, client):
        with client.application.app_context():
            p = Pitcher(mlb_id=1, full_name='A', team_id=1, active=True)
            db.session.add(p)
            db.session.commit()
            db.session.add(GameLog(pitcher_id=p.id, mlb_game_pk=31, game_date=date(2026, 5, 31)))
            db.session.add(FatigueScore(
                pitcher_id=p.id,
                raw_score=42.0,
                calculated_at=datetime(2026, 6, 1, 21, 39, 55),
            ))
            db.session.commit()

            run_id = sync_metadata.start_sync_run(
                source='test',
                started_at=datetime(2026, 6, 1, 21, 39, 12),
            )
            run = db.session.get(SyncRun, run_id)
            assert run.status == 'running'

            sync_metadata.finish_sync_run(
                run_id,
                status='success',
                completed_at=datetime(2026, 6, 1, 21, 39, 56),
                records_processed=120,
                new_logs_added=120,
                pitchers_updated=428,
            )
            run = db.session.get(SyncRun, run_id)

            assert run.status == 'success'
            assert run.latest_game_date == date(2026, 5, 31)
            assert run.latest_workload_date == date(2026, 5, 31)
            assert run.latest_fatigue_calculated_at == datetime(2026, 6, 1, 21, 39, 55)
            assert run.records_processed == 120
            assert run.pitchers_updated == 428
