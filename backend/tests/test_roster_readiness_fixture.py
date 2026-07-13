from datetime import datetime

import pytest
from flask import Flask, jsonify

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.roster_readiness_fixture import seed_roster_readiness_snapshots
from models.pitcher import Pitcher
from models.roster_status_snapshot import RosterStatusSnapshot
from models.sync_run import SyncRun
import models.prospect  # noqa: F401
import services.sync_metadata as sync_metadata
from services.roster_status import STATUS_ACTIVE
from utils.db import db


@pytest.fixture
def app():
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


def _seed_pitcher(name='Roster Ready Arm', *, mlb_id=900001, team_id=900):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=team_id,
        team_name=f'Team {team_id}',
        team_abbreviation=f'T{team_id}',
        position='P',
        active=True,
        roster_status=STATUS_ACTIVE,
        roster_status_source='test_fixture',
        roster_status_updated_at=datetime(2026, 7, 12, 12, 0, 0),
    )
    db.session.add(pitcher)
    db.session.commit()
    return pitcher


def test_roster_readiness_fixture_uses_real_sync_run_provenance(app):
    with app.app_context():
        _seed_pitcher()

        seed_roster_readiness_snapshots()

        snapshot = RosterStatusSnapshot.query.one()
        run = db.session.get(SyncRun, snapshot.sync_run_id)

        assert run is not None
        assert snapshot.sync_run_id == run.id
        assert run.job_name == 'roster_status_snapshot_fixture'
        assert run.status == 'success'
        assert run.stage == 'roster_status'
        assert run.source == 'roster_readiness_fixture'
        assert run.completed_at is not None
        assert sync_metadata.latest_sync_run() is None
        assert sync_metadata.latest_successful_sync_run() is None


def test_roster_readiness_fixture_before_request_path_keeps_session_usable(app):
    @app.before_request
    def _seed_ready_roster_snapshots():
        seed_roster_readiness_snapshots()

    @app.get('/probe')
    def _probe():
        return jsonify({
            'snapshots': RosterStatusSnapshot.query.count(),
            'sync_runs': SyncRun.query.count(),
        })

    with app.app_context():
        _seed_pitcher()

    response = app.test_client().get('/probe')

    assert response.status_code == 200
    assert response.get_json() == {
        'snapshots': 1,
        'sync_runs': 1,
    }
    with app.app_context():
        snapshot = RosterStatusSnapshot.query.one()
        assert db.session.get(SyncRun, snapshot.sync_run_id) is not None
