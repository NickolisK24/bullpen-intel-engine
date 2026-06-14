from datetime import date, datetime, timedelta

import pytest
from flask import Flask

import api.bullpen as bullpen_api
import services.sync as sync_service
from models.dashboard_snapshot import DashboardSnapshot
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.sync_run import SyncRun
import models.prospect  # noqa: F401
from services import dashboard_snapshot
from services.roster_status import STATUS_ACTIVE
from utils.db import db
from utils.time import utc_now_naive


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(bullpen_api.bullpen_bp, url_prefix='/api/bullpen')
    with app.app_context():
        db.create_all()
        try:
            yield app
        finally:
            db.session.remove()
            db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


def _sync_scaffolding():
    return {
        'pitchers_refreshed': 0,
        'pitchers_changed': 0,
        'reassigned_count': 0,
        'no_organization_count': 0,
        'unknown_count': 0,
        'errors': 0,
        'by_status': {},
    }


def _seed_dashboard_data():
    workload_date = date.today() - timedelta(days=1)
    pitcher = Pitcher(
        mlb_id=101,
        full_name='Snapshot Reliever',
        team_id=1,
        team_name='Snapshot Club',
        team_abbreviation='SC',
        active=True,
        roster_status=STATUS_ACTIVE,
        roster_status_source='test_fixture',
        roster_status_updated_at=utc_now_naive(),
    )
    db.session.add(pitcher)
    db.session.commit()
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=1010,
        game_date=workload_date,
        games_started=0,
        innings_pitched=1.0,
        pitches_thrown=14,
        game_type='R',
    ))
    db.session.add(FatigueScore(
        pitcher_id=pitcher.id,
        raw_score=12.0,
        risk_level='LOW',
        calculated_at=utc_now_naive(),
    ))
    db.session.add(SyncRun(
        started_at=utc_now_naive() - timedelta(minutes=2),
        completed_at=utc_now_naive() - timedelta(minutes=1),
        status='success',
        source='manual',
        latest_game_date=workload_date,
        latest_workload_date=workload_date,
        latest_fatigue_calculated_at=utc_now_naive(),
        records_processed=1,
        new_logs_added=1,
        pitchers_updated=1,
        errors=0,
        created_at=utc_now_naive() - timedelta(minutes=2),
    ))
    db.session.commit()
    return workload_date


def _minimal_dashboard_payload():
    return {
        'capability': 'bullpen_dashboard',
        'generated_at': utc_now_naive().isoformat(),
        'ranking_applied': False,
        'selection_made': False,
        'scope': 'all_tracked_bullpens',
        'context': {},
        'roles': {'order': [], 'counts': {}, 'total': 0},
        'landscape': {},
        'continuity': {'capability': 'bullpen_continuity_v1', 'teams': {}, 'limitations': []},
        'story_context': {
            'capability': 'bullpen_context_story_v1',
            'teams': {},
            'limitations': [],
        },
        'freshness': {
            'data_through': None,
            'availability_reference_date': None,
            'reference_date': date.today().isoformat(),
            'sync_status': 'never',
            'last_successful_sync': None,
        },
        'availability_summary': {},
    }


class TestDashboardSnapshotService:
    def test_model_table_accepts_json_payload(self, app):
        with app.app_context():
            snapshot = DashboardSnapshot(
                snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
                status=dashboard_snapshot.SNAPSHOT_STATUS_READY,
                payload={'capability': 'bullpen_dashboard'},
                payload_version=dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION,
                snapshot_generated_at=utc_now_naive(),
                source='test',
            )
            db.session.add(snapshot)
            db.session.commit()

            row = DashboardSnapshot.query.one()
            assert row.payload['capability'] == 'bullpen_dashboard'
            assert row.status == 'ready'

    def test_store_dashboard_snapshot_persists_contract_metadata(self, app):
        with app.app_context():
            _seed_dashboard_data()
            payload = bullpen_api.build_bullpen_dashboard_payload()
            snapshot = dashboard_snapshot.store_dashboard_snapshot(
                payload,
                sync_run_id=1,
                source='test',
            )

            assert snapshot.status == 'ready'
            assert snapshot.payload_version == dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION
            assert snapshot.data_through is not None
            assert snapshot.availability_reference_date is not None
            assert snapshot.payload['capability'] == 'bullpen_dashboard'

    def test_latest_ready_snapshot_ignores_failed_rows(self, app):
        with app.app_context():
            old_ready = DashboardSnapshot(
                snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
                status=dashboard_snapshot.SNAPSHOT_STATUS_READY,
                payload={'name': 'old'},
                payload_version=dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION,
                snapshot_generated_at=utc_now_naive() - timedelta(minutes=10),
                source='test',
            )
            failed = DashboardSnapshot(
                snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
                status=dashboard_snapshot.SNAPSHOT_STATUS_FAILED,
                payload=None,
                payload_version=dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION,
                snapshot_generated_at=utc_now_naive(),
                source='test',
                error_message='failed build',
            )
            newer_ready = DashboardSnapshot(
                snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
                status=dashboard_snapshot.SNAPSHOT_STATUS_READY,
                payload={'name': 'new'},
                payload_version=dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION,
                snapshot_generated_at=utc_now_naive() - timedelta(minutes=1),
                source='test',
            )
            db.session.add_all([old_ready, failed, newer_ready])
            db.session.commit()

            snapshot = dashboard_snapshot.get_latest_dashboard_snapshot()
            assert snapshot.payload['name'] == 'new'

    def test_build_dashboard_snapshot_records_failed_status(self, app):
        with app.app_context():
            snapshot = dashboard_snapshot.build_dashboard_snapshot(
                lambda: (_ for _ in ()).throw(RuntimeError('builder failed')),
                sync_run_id=123,
                source='test',
            )

            assert snapshot.status == dashboard_snapshot.SNAPSHOT_STATUS_FAILED
            assert snapshot.sync_run_id == 123
            assert 'builder failed' in snapshot.error_message


class TestDashboardRouteSnapshotBehavior:
    def test_dashboard_route_serves_valid_cache_without_live_builder(self, client, monkeypatch):
        with client.application.app_context():
            _seed_dashboard_data()
            payload = bullpen_api.build_bullpen_dashboard_payload()
            dashboard_snapshot.store_dashboard_snapshot(payload, sync_run_id=1, source='test')
        client.application.config['APP_ENV'] = 'production'

        def fail_live_builder():
            raise AssertionError('live builder should not run')

        monkeypatch.setattr(bullpen_api, 'build_bullpen_dashboard_payload', fail_live_builder)

        response = client.get('/api/bullpen/dashboard')
        assert response.status_code == 200
        body = response.get_json()
        assert body['capability'] == 'bullpen_dashboard'
        assert body['snapshot']['served_from'] == 'cache'
        assert body['snapshot']['payload_version'] == 1

    def test_dashboard_route_falls_back_when_cache_missing(self, client, monkeypatch):
        monkeypatch.setattr(
            bullpen_api,
            'build_bullpen_dashboard_payload',
            _minimal_dashboard_payload,
        )

        response = client.get('/api/bullpen/dashboard')
        assert response.status_code == 200
        body = response.get_json()
        assert body['capability'] == 'bullpen_dashboard'
        assert body['snapshot']['served_from'] == 'live_fallback'
        assert body['ranking_applied'] is False
        assert body['selection_made'] is False

    def test_dashboard_route_returns_degraded_response_when_production_cache_missing(
        self,
        client,
        monkeypatch,
    ):
        client.application.config['APP_ENV'] = 'production'

        monkeypatch.setattr(
            bullpen_api,
            'build_bullpen_dashboard_payload',
            lambda: pytest.fail('production cache miss must not run live builder'),
        )

        response = client.get('/api/bullpen/dashboard')
        assert response.status_code == 200
        body = response.get_json()
        assert body['capability'] == 'bullpen_dashboard'
        assert body['status'] == 'snapshot_unavailable'
        assert body['reason'] == 'dashboard_snapshot_missing'
        assert body['snapshot']['served_from'] == 'snapshot_unavailable'
        assert body['ranking_applied'] is False
        assert body['selection_made'] is False

    def test_dashboard_route_falls_back_when_latest_snapshot_failed(self, client, monkeypatch):
        with client.application.app_context():
            dashboard_snapshot.mark_dashboard_snapshot_failed(
                RuntimeError('snapshot failed'),
                sync_run_id=10,
                source='test',
            )
        monkeypatch.setattr(
            bullpen_api,
            'build_bullpen_dashboard_payload',
            _minimal_dashboard_payload,
        )

        body = client.get('/api/bullpen/dashboard').get_json()
        assert body['snapshot']['served_from'] == 'live_fallback'

    def test_dashboard_route_returns_degraded_response_when_production_snapshot_failed(
        self,
        client,
        monkeypatch,
    ):
        client.application.config['APP_ENV'] = 'production'
        with client.application.app_context():
            dashboard_snapshot.mark_dashboard_snapshot_failed(
                RuntimeError('snapshot failed'),
                sync_run_id=10,
                source='test',
            )
        monkeypatch.setattr(
            bullpen_api,
            'build_bullpen_dashboard_payload',
            lambda: pytest.fail('production failed snapshot must not run live builder'),
        )

        body = client.get('/api/bullpen/dashboard').get_json()
        assert body['status'] == 'snapshot_unavailable'
        assert body['reason'] == 'dashboard_snapshot_not_ready'
        assert body['snapshot']['served_from'] == 'snapshot_unavailable'

    def test_public_payload_remains_backward_compatible(self, client):
        body = client.get('/api/bullpen/dashboard').get_json()
        for key in (
            'capability',
            'generated_at',
            'ranking_applied',
            'selection_made',
            'scope',
            'context',
            'roles',
            'landscape',
            'continuity',
            'story_context',
            'freshness',
            'availability_summary',
        ):
            assert key in body
        assert body['snapshot']['served_from'] in ('cache', 'live_fallback')


class TestSyncSnapshotIntegration:
    def test_successful_manual_sync_does_not_build_dashboard_snapshot_inline(self, client, monkeypatch):
        monkeypatch.setattr(sync_service, 'sync_team_assignments', _sync_scaffolding)
        monkeypatch.setattr(sync_service, 'sync_roster_statuses', _sync_scaffolding)
        monkeypatch.setattr(sync_service, 'sync_recent_logs', lambda **kwargs: {
            'new_logs_added': 0,
            'pitchers_touched': 0,
            'errors': 0,
            'records_failed': 0,
            'days_back': 7,
            'season': date.today().year,
            'cutoff': date.today().isoformat(),
        })
        monkeypatch.setattr(sync_service, 'recalculate_all_fatigue', lambda: 1)
        monkeypatch.setattr(
            dashboard_snapshot,
            'build_bullpen_dashboard_snapshot',
            lambda **kwargs: pytest.fail('manual sync must not build dashboard snapshots inline'),
        )

        with client.application.app_context():
            _seed_dashboard_data()

        response = client.post('/api/bullpen/sync', json={'days_back': 7})
        assert response.status_code == 200

        with client.application.app_context():
            snapshot = DashboardSnapshot.query.order_by(DashboardSnapshot.id.desc()).first()
            assert snapshot is None

    def test_successful_scheduled_sync_does_not_build_dashboard_snapshot_inline(self, app, monkeypatch):
        monkeypatch.setattr(sync_service, 'sync_team_assignments', _sync_scaffolding)
        monkeypatch.setattr(sync_service, 'sync_roster_statuses', _sync_scaffolding)
        monkeypatch.setattr(sync_service, 'sync_recent_logs', lambda **kwargs: {
            'new_logs_added': 0,
            'pitchers_touched': 0,
            'errors': 0,
            'records_failed': 0,
            'days_back': 7,
            'season': date.today().year,
            'cutoff': date.today().isoformat(),
        })
        monkeypatch.setattr(sync_service, 'recalculate_all_fatigue', lambda: 1)
        monkeypatch.setattr(
            dashboard_snapshot,
            'build_bullpen_dashboard_snapshot',
            lambda **kwargs: pytest.fail('scheduled sync must not build dashboard snapshots inline'),
        )

        status = sync_service.run_daily_sync(app, days_back=7)
        assert status['status'] == 'success'

        with app.app_context():
            snapshot = DashboardSnapshot.query.order_by(DashboardSnapshot.id.desc()).first()
            assert snapshot is None
