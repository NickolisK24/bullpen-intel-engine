"""
Deploy-correctness proof tests for the freshness chain.

These pin the rule that a code deploy (which wipes backend/logs/sync_status.json,
an ephemeral, gitignored cache) must NOT make healthy data look stale. Durable
sync_runs metadata is authoritative; the cache file is never consulted for
freshness reporting.

Scenarios mirror the task:
  A. Durable healthy sync + cache file MISSING       -> current/healthy
  B. Durable healthy sync + cache file CONFLICTING   -> durable wins
  C. No durable metadata + no cache                  -> honest fallback, no crash
  D. Durable sync FAILED                             -> degraded, not hidden

Plus: the dashboard endpoint consumes the SAME durable freshness source, and no
endpoint reports a snapshot while durable-healthy metadata exists.

In-memory SQLite, no Postgres / MLB / network.
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import services.sync as sync_service
from services.availability_reference_date import (
    product_availability_reference_date,
    product_current_date,
)
from utils.db import db
from models.pitcher import Pitcher
from models.game_log import GameLog
from models.fatigue_score import FatigueScore
from models.sync_run import SyncRun
import models.prospect  # noqa: F401  (register on db.metadata)
from api.bullpen import bullpen_bp


@pytest.fixture
def client(tmp_path, monkeypatch):
    # STATUS_FILE points at a path that does not exist, exactly like a fresh
    # container after deploy. Public freshness reporting must not read it.
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')

    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    with app.app_context():
        create_test_schema(app)
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            drop_test_schema(app)


def _seed_healthy_durable_sync(app, recent_days=3, source='github_actions'):
    """A successful durable sync_runs row + recent game/fatigue data in the DB."""
    with app.app_context():
        pitcher = Pitcher(mlb_id=1, full_name='A', team_id=1, active=True)
        db.session.add(pitcher)
        db.session.commit()
        game_day = date.today() - timedelta(days=recent_days)
        synced_at = datetime.utcnow()
        db.session.add(GameLog(pitcher_id=pitcher.id, mlb_game_pk=10, game_date=game_day,
                               pitches_thrown=12, innings_pitched=1.0,
                               innings_pitched_outs=3))
        db.session.add(FatigueScore(pitcher_id=pitcher.id, raw_score=20.0,
                                    risk_level='LOW', calculated_at=synced_at))
        db.session.add(SyncRun(
            started_at=synced_at - timedelta(seconds=40),
            completed_at=synced_at,
            status='success',
            source=source,
            latest_game_date=game_day,
            latest_workload_date=game_day,
            latest_fatigue_calculated_at=synced_at,
            records_processed=120, new_logs_added=120, pitchers_updated=428, errors=0,
            created_at=synced_at - timedelta(seconds=40),
        ))
        db.session.commit()
        return game_day


def _write_cache(status='never', last_sync='2020-01-01T00:00:00', message='stale deploy-local cache'):
    sync_service.write_status({
        'last_sync': last_sync,
        'status': status,
        'pitchers_updated': 0,
        'new_logs_added': 0,
        'errors': 0,
        'message': message,
        'finished_at': last_sync,
    })


def _fixed_datetime_class(fixed_utc):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_utc.replace(tzinfo=None)
            return fixed_utc.astimezone(tz)

    return FixedDateTime


def _host_local_date_class(host_today):
    class HostLocalDate(date):
        @classmethod
        def today(cls):
            return host_today

    return HostLocalDate


# ── Scenario A — durable healthy, cache file missing ───────────────────────

class TestScenarioA_MissingCache:
    def test_status_stays_current_when_cache_file_is_missing(self, client):
        _seed_healthy_durable_sync(client.application)
        body = client.get('/api/bullpen/sync/status').get_json()

        assert body['status'] == 'success'
        assert body['last_successful_sync'] is not None
        assert body['freshness']['is_current'] is True
        # No "snapshot/never" framing despite the missing local file.
        assert body['freshness']['limitations'] == []

    def test_dashboard_stays_current_when_cache_file_is_missing(self, client):
        _seed_healthy_durable_sync(client.application)
        dash = client.get('/api/bullpen/dashboard').get_json()

        assert dash['freshness']['is_current'] is True
        assert dash['freshness']['sync_status'] == 'success'
        assert dash['freshness']['last_successful_sync'] is not None


# ── Scenario B — durable healthy, cache file stale/conflicting ─────────────

class TestScenarioB_ConflictingCache:
    def test_durable_success_overrides_a_stale_cache_file(self, client):
        # A deploy could leave behind (or a prior failure could write) a cache
        # file that says 'never'/stale. Durable health must still win.
        _write_cache(status='never', last_sync='2020-01-01T00:00:00')
        _seed_healthy_durable_sync(client.application)

        body = client.get('/api/bullpen/sync/status').get_json()
        assert body['status'] == 'success'                 # not 'never'
        assert body['freshness']['is_current'] is True
        assert body['last_successful_sync'] is not None

    def test_durable_success_overrides_a_failed_cache_file(self, client):
        _write_cache(status='failed', last_sync='2020-01-01T00:00:00', message='old failure')
        _seed_healthy_durable_sync(client.application)

        body = client.get('/api/bullpen/sync/status').get_json()
        assert body['status'] == 'success'
        assert body['message'] != 'old failure'


# ── Scenario C — no durable metadata, no cache ─────────────────────────────

class TestScenarioC_NoMetadata:
    def test_graceful_honest_fallback_without_crash(self, client):
        body = client.get('/api/bullpen/sync/status').get_json()
        assert body['status'] == 'never'
        assert body['last_successful_sync'] is None
        assert body['freshness']['is_current'] is False
        assert body['freshness']['label'] == 'No baseball workload data loaded.'

        dash = client.get('/api/bullpen/dashboard')
        assert dash.status_code == 200
        assert dash.get_json()['freshness']['is_current'] is False


# ── Scenario D — durable sync failed ───────────────────────────────────────

class TestScenarioD_FailedSync:
    def test_failed_latest_sync_is_degraded_not_hidden(self, client):
        game_day = _seed_healthy_durable_sync(client.application)  # earlier success
        # A later failed run on top of the earlier success.
        with client.application.app_context():
            db.session.add(SyncRun(
                started_at=datetime.utcnow() + timedelta(minutes=1),
                completed_at=datetime.utcnow() + timedelta(minutes=1, seconds=30),
                status='failed', source='github_actions', errors=1,
                error_message='MLB API unavailable',
                created_at=datetime.utcnow() + timedelta(minutes=1),
            ))
            db.session.commit()

        body = client.get('/api/bullpen/sync/status').get_json()
        assert body['status'] == 'failed'                  # honest, not 'success'/'snapshot'
        assert body['message'] == 'MLB API unavailable'
        # The earlier successful sync is preserved, not erased.
        assert body['last_successful_sync'] is not None
        assert any('latest sync attempt failed' in lim.lower()
                   for lim in body['freshness']['limitations'])


# ── Cross-endpoint consistency ─────────────────────────────────────────────

class TestSharedFreshnessSource:
    def test_dashboard_and_status_agree_on_durable_freshness(self, client):
        _seed_healthy_durable_sync(client.application)
        status = client.get('/api/bullpen/sync/status').get_json()
        dash = client.get('/api/bullpen/dashboard').get_json()

        assert dash['freshness']['is_current'] == status['freshness']['is_current']
        assert dash['freshness']['sync_status'] == status['status']
        assert dash['freshness']['data_through'] == status['data']['latest_game_date']
        assert dash['freshness']['last_successful_sync'] == status['last_successful_sync']

    def test_no_endpoint_reports_snapshot_when_durable_healthy(self, client):
        # is_current True on both endpoints => SeasonBanner isLive is True =>
        # the UI never shows "<year> End-of-Season Snapshot" for healthy data.
        _seed_healthy_durable_sync(client.application)
        status = client.get('/api/bullpen/sync/status').get_json()
        dash = client.get('/api/bullpen/dashboard').get_json()

        assert status['freshness']['is_current'] is True
        assert dash['freshness']['is_current'] is True
        assert dash['freshness']['sync_status'] in ('success', 'ok')

    def test_write_cutoff_and_read_reference_share_product_day(self, client, monkeypatch):
        fixed_utc = datetime(2026, 6, 10, 3, 30, tzinfo=timezone.utc)
        product_day = product_current_date(now=fixed_utc)

        monkeypatch.setattr(sync_service, 'datetime', _fixed_datetime_class(fixed_utc))
        monkeypatch.setattr(
            sync_service,
            'date',
            _host_local_date_class(date(2099, 1, 1)),
        )
        monkeypatch.setattr(
            sync_service.mlb_client,
            'get_pitcher_game_logs',
            lambda mlb_id, season=None: [],
        )

        with client.application.app_context():
            db.session.add(Pitcher(
                mlb_id=901001,
                full_name='Freshness Timezone Reliever',
                team_id=1,
                active=True,
            ))
            db.session.commit()
            result = sync_service.sync_recent_logs(days_back=7)

        read_reference = product_availability_reference_date(
            latest_workload_date=product_day - timedelta(days=1),
            latest_game_date=product_day - timedelta(days=1),
        )

        assert result['reference_date'] == product_day.isoformat()
        assert result['cutoff'] == (product_day - timedelta(days=7)).isoformat()
        assert read_reference == product_day
