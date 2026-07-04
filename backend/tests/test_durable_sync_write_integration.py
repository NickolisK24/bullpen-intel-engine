"""
Durable sync-write integration tests.

These pin the production-correctness rule: every successful OR failed sync must
leave a durable row in sync_runs, and /api/bullpen/sync/status must then prefer
that durable row over the legacy cache file. The MLB pull and fatigue recompute
are mocked so the tests exercise the real endpoint wiring without network.

In-memory SQLite, no Postgres / MLB / network.
"""

from datetime import date, datetime, timedelta

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import services.sync as sync_service
from services import sync_metadata
from utils.db import db
from models.pitcher import Pitcher
from models.game_log import GameLog
from models.fatigue_score import FatigueScore
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from models.sync_run import SyncRun
import models.prospect  # noqa: F401
from api.bullpen import bullpen_bp


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    # Mock the network/heavy work so the endpoint's durable wiring is what's tested.
    monkeypatch.setattr(sync_service, 'sync_recent_logs',
                        lambda days_back=7, sync_run_id=None, **kw: {
                            'new_logs_added': 3, 'pitchers_touched': 2,
                            'errors': 0, 'records_failed': 0})
    monkeypatch.setattr(sync_service, 'recalculate_all_fatigue', lambda reference_date=None: 5)
    monkeypatch.setattr(sync_service, 'sync_team_assignments', lambda: {
        'pitchers_refreshed': 1,
        'pitchers_changed': 0,
        'reassigned_count': 0,
        'no_organization_count': 0,
        'unknown_count': 0,
        'errors': 0,
        'by_status': {'ASSIGNED': 1},
    })
    monkeypatch.setattr(sync_service, 'sync_roster_statuses', lambda **_kwargs: {
        'pitchers_refreshed': 1,
        'pitchers_changed': 1,
        'unknown_count': 0,
        'records_failed': 0,
        'errors': 0,
        'by_status': {'ACTIVE': 1},
    })
    monkeypatch.setattr(sync_service, 'sync_transactions', lambda **_kwargs: {
        'records_fetched': 0,
        'records_stored': 0,
        'unknown_type_count': 0,
        'records_failed': 0,
        'errors': 0,
        'error_details': [],
    })

    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    with app.app_context():
        create_test_schema(app)
        # Recent data so collect_data_metadata() has something current to record.
        pitcher = Pitcher(mlb_id=1, full_name='A', team_id=1, active=True)
        db.session.add(pitcher)
        db.session.commit()
        db.session.add(GameLog(pitcher_id=pitcher.id, mlb_game_pk=10,
                               game_date=date.today() - timedelta(days=3),
                               innings_pitched=1.0, innings_pitched_outs=3,
                               pitches_thrown=12))
        game_day = date.today() - timedelta(days=3)
        db.session.add_all([
            ScheduledGame(
                team_id=116,
                game_pk=10,
                game_date=game_day,
                status_state='final',
                home_away='home',
                opponent_team_id=142,
            ),
            ScheduledGame(
                team_id=142,
                game_pk=10,
                game_date=game_day,
                status_state='final',
                home_away='away',
                opponent_team_id=116,
            ),
        ])
        db.session.add(PostgameProcessedGame(
            mlb_game_pk=10,
            game_date=game_day,
            processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
        ))
        db.session.add(FatigueScore(pitcher_id=pitcher.id, raw_score=20.0,
                                    risk_level='LOW', calculated_at=datetime.utcnow()))
        db.session.commit()
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            drop_test_schema(app)


def _count_runs(client):
    with client.application.app_context():
        return db.session.query(db.func.count(SyncRun.id)).scalar()


def _latest_run(client):
    with client.application.app_context():
        return SyncRun.query.order_by(SyncRun.id.desc()).first()


# ── 1 & 2: successful manual sync writes and fully populates a durable row ──

class TestSuccessfulSync:
    def test_manual_sync_writes_a_sync_runs_row(self, client):
        res = client.post('/api/bullpen/sync', json={'days_back': 7})
        assert res.status_code == 200
        body = res.get_json()
        assert body['sync_run_persisted'] is True
        assert body['sync_run_id'] is not None
        assert body['team_assignments_refreshed'] == 1
        assert body['roster_statuses_refreshed'] == 1
        assert _count_runs(client) >= 1

    def test_successful_sync_updates_all_fields(self, client):
        client.post('/api/bullpen/sync', json={'days_back': 7})
        run = _latest_run(client)
        assert run.status == 'success'
        assert run.started_at is not None
        assert run.completed_at is not None
        assert run.latest_game_date == date.today() - timedelta(days=3)
        assert run.latest_workload_date == date.today() - timedelta(days=3)
        assert run.latest_fatigue_calculated_at is not None
        assert run.records_processed == 3
        assert run.new_logs_added == 3
        assert run.pitchers_updated == 5
        assert run.errors == 0


# ── 3: a failed sync still writes/updates a durable row ────────────────────

class TestFailedSync:
    def test_failed_sync_writes_durable_failed_row(self, client, monkeypatch):
        def boom(days_back=7, sync_run_id=None, **kw):
            raise RuntimeError('MLB API unavailable')
        monkeypatch.setattr(sync_service, 'sync_recent_logs', boom)

        res = client.post('/api/bullpen/sync', json={'days_back': 7})
        assert res.status_code == 500
        run = _latest_run(client)
        assert run is not None
        assert run.status == 'failed'
        assert run.error_message == 'MLB API unavailable'
        assert run.completed_at is not None
        assert _count_runs(client) >= 1


# ── 4: self-heal when the start row never persisted ────────────────────────

class TestSelfHeal:
    def test_durable_row_written_even_if_start_returns_none(self, client, monkeypatch):
        # Simulate start_sync_run silently failing in prod (the exact symptom:
        # source=legacy_status_file, id=null, count=0).
        monkeypatch.setattr(sync_metadata, 'start_sync_run', lambda **kwargs: None)

        res = client.post('/api/bullpen/sync', json={'days_back': 7})
        assert res.status_code == 200
        assert res.get_json()['sync_run_persisted'] is True
        # finish_sync_run self-healed a durable row despite the missing start.
        assert _count_runs(client) >= 1

        status = client.get('/api/bullpen/sync/status').get_json()
        assert status['metadata_source'] == 'sync_runs'
        assert status['sync']['id'] is not None


# ── 5: cache-file failure must not block the durable write ─────────────────

class TestCacheFileIsNotTheGate:
    def test_status_file_failure_does_not_prevent_durable_row(self, client, monkeypatch):
        def explode(_status):
            raise RuntimeError('read-only filesystem')
        monkeypatch.setattr(sync_service, 'write_status', explode)

        # The durable write happens before the (now-failing) cache write, so the
        # row persists regardless of the file outcome.
        try:
            client.post('/api/bullpen/sync', json={'days_back': 7})
        except RuntimeError:
            pass
        run = _latest_run(client)
        assert run is not None
        assert run.status == 'success'
        assert _count_runs(client) >= 1


# ── 6: /sync/status prefers sync_runs over the legacy file ─────────────────

class TestStatusPrefersDurable:
    def test_status_reports_sync_runs_source_after_sync(self, client):
        # Pre-seed a conflicting legacy cache file to make sure durable wins.
        with client.application.app_context():
            sync_service.write_status({'last_sync': '2020-01-01T00:00:00', 'status': 'never',
                                       'pitchers_updated': 0, 'new_logs_added': 0, 'errors': 0,
                                       'message': 'stale'})
        client.post('/api/bullpen/sync', json={'days_back': 7})

        status = client.get('/api/bullpen/sync/status').get_json()
        assert status['metadata_source'] == 'sync_runs'
        assert status['sync'] is not None
        assert status['sync']['id'] is not None
        assert status['sync']['source'] != 'legacy_status_file'
        assert status['status'] == 'success'


# ── 7: no regression to dashboard freshness ────────────────────────────────

class TestNoFreshnessRegression:
    def test_dashboard_reports_current_after_sync(self, client):
        client.post('/api/bullpen/sync', json={'days_back': 7})
        dash = client.get('/api/bullpen/dashboard').get_json()
        assert dash['freshness']['is_current'] is True
        assert dash['freshness']['sync_status'] == 'success'
        assert dash['freshness']['last_successful_sync'] is not None
