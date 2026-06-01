"""
Tests for the enriched GET /api/bullpen/sync/status endpoint.

The endpoint now reports the real data snapshot (latest game date + log count)
alongside the file-based sync status, so the dashboard can tell a loaded
historical snapshot apart from a genuinely empty / never-synced system.

Runs against in-memory SQLite (no Postgres / MLB / network). The sync status
file is pointed at an empty temp path so read_status() returns the 'never'
sentinel deterministically — i.e. we simulate "data loaded via seed, no sync".
"""

from datetime import date

import pytest
from flask import Flask

import services.sync as sync_service
from utils.db import db
from models.pitcher import Pitcher
from models.game_log import GameLog
import models.fatigue_score  # noqa: F401  (register on db.metadata)
import models.prospect        # noqa: F401  (register on db.metadata)
from api.bullpen import bullpen_bp


@pytest.fixture
def client(tmp_path, monkeypatch):
    # No real sync_status.json → read_status() returns the 'never' sentinel.
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')

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
        assert body['status'] == 'never'
        # ...but the data snapshot is reported honestly from the DB.
        assert body['data']['game_logs'] == 2
        assert body['data']['latest_game_date'] == '2025-09-10'

    def test_reports_empty_when_no_data_and_no_sync(self, client):
        res = client.get('/api/bullpen/sync/status')
        assert res.status_code == 200
        body = res.get_json()
        assert body['last_sync'] is None
        assert body['data']['game_logs'] == 0
        assert body['data']['latest_game_date'] is None
