from datetime import date, datetime

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.roster_readiness_fixture import seed_roster_readiness_snapshots

import api.bullpen as bullpen_api
import models.prospect  # noqa: F401
import services.availability as availability_service
import services.availability_snapshot as availability_snapshot
import services.bullpen_eligibility as bullpen_eligibility
import services.bullpen_population as bullpen_population
import services.game_context as game_context
import services.pitcher_role as pitcher_role
import services.sync_metadata as sync_metadata
import services.sync as sync_service
from api.bullpen import bullpen_bp
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.sync_run import SyncRun
from services.availability_reference_date import (
    PRODUCT_TIMEZONE_UTC_FALLBACK_LIMITATION,
    product_availability_reference_date,
    product_current_date,
    resolve_product_day,
)
from services.availability_snapshot import classify_latest_fatigue_rows, latest_fatigue_rows
from services.roster_status import STATUS_ACTIVE
from utils.db import db


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')

    @app.before_request
    def _seed_ready_roster_snapshots_for_reference_date_tests():
        seed_roster_readiness_snapshots()

    with app.app_context():
        create_test_schema(app)
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            drop_test_schema(app)


def _runtime_date(runtime_day):
    class RuntimeDate(date):
        @classmethod
        def today(cls):
            return runtime_day

    return RuntimeDate


def _set_runtime_today(monkeypatch, runtime_day):
    runtime_date = _runtime_date(runtime_day)
    for module in (
        bullpen_api,
        availability_service,
        availability_snapshot,
        bullpen_eligibility,
        bullpen_population,
        game_context,
        pitcher_role,
    ):
        if hasattr(module, 'date'):
            monkeypatch.setattr(module, 'date', runtime_date)
    monkeypatch.setattr(sync_metadata, 'product_current_date', lambda: runtime_day)


def _seed_reference_date_case():
    pitcher = Pitcher(
        mlb_id=900001,
        full_name='Reference Date Reliever',
        team_id=1,
        team_name='Reference Team',
        team_abbreviation='REF',
        active=True,
        roster_status=STATUS_ACTIVE,
        roster_status_source='test_fixture',
        roster_status_updated_at=datetime(2026, 6, 8, 12, 0, 0),
    )
    db.session.add(pitcher)
    db.session.commit()
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=900010,
        game_date=date(2026, 6, 6),
        pitches_thrown=10,
        innings_pitched=1.0,
        innings_pitched_outs=3,
        games_started=0,
        game_type='R',
    ))
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=900011,
        game_date=date(2026, 6, 7),
        pitches_thrown=50,
        innings_pitched=1.0,
        innings_pitched_outs=3,
        games_started=0,
        game_type='R',
    ))
    db.session.add(FatigueScore(
        pitcher_id=pitcher.id,
        raw_score=10.0,
        risk_level='LOW',
        calculated_at=datetime(2026, 6, 6, 23, 0, 0),
    ))
    db.session.add(FatigueScore(
        pitcher_id=pitcher.id,
        raw_score=10.0,
        risk_level='LOW',
        calculated_at=datetime(2026, 6, 8, 12, 0, 0),
    ))
    db.session.add(SyncRun(
        started_at=datetime(2026, 6, 8, 11, 43, 0),
        completed_at=datetime(2026, 6, 8, 11, 43, 43),
        status='success',
        source='github_actions',
        latest_game_date=date(2026, 6, 7),
        latest_workload_date=date(2026, 6, 7),
        latest_fatigue_calculated_at=datetime(2026, 6, 8, 12, 0, 0),
        pitchers_updated=1,
        errors=0,
        created_at=datetime(2026, 6, 8, 11, 43, 0),
    ))
    db.session.commit()
    return pitcher


def _status_counts(records):
    counts = {}
    for record in records:
        status = record['availability']['availability_status']
        counts[status] = counts.get(status, 0) + 1
    return counts


def test_product_availability_reference_date_uses_latest_workload_plus_one_day():
    assert product_availability_reference_date(
        latest_workload_date=date(2026, 6, 7),
        latest_game_date=date(2026, 6, 7),
    ) == date(2026, 6, 8)


def test_product_current_date_uses_product_timezone_not_utc_midnight():
    current = datetime.fromisoformat('2026-06-09T01:22:01+00:00')
    assert product_current_date(now=current) == date(2026, 6, 8)


def test_product_day_resolver_covers_et_midnight_boundaries():
    before_midnight = datetime.fromisoformat('2026-06-10T03:30:00+00:00')
    after_midnight = datetime.fromisoformat('2026-06-10T04:30:00+00:00')

    assert resolve_product_day(before_midnight).calendar_date == date(2026, 6, 9)
    assert resolve_product_day(after_midnight).calendar_date == date(2026, 6, 10)


def test_product_day_resolver_records_utc_fallback_limitation():
    current = datetime.fromisoformat('2026-06-10T03:30:00+00:00')
    resolved = resolve_product_day(current, timezone_name='Missing/Timezone')

    assert resolved.calendar_date == date(2026, 6, 10)
    assert resolved.timezone_name == 'UTC'
    assert resolved.limitations == (PRODUCT_TIMEZONE_UTC_FALLBACK_LIMITATION,)


def test_dashboard_uses_data_derived_reference_date_not_runtime_today(client, monkeypatch):
    with client.application.app_context():
        _seed_reference_date_case()
        rows = latest_fatigue_rows()
        june8_counts = _status_counts(
            classify_latest_fatigue_rows(rows, reference_date=date(2026, 6, 8))
        )
        june9_counts = _status_counts(
            classify_latest_fatigue_rows(rows, reference_date=date(2026, 6, 9))
        )

    assert june8_counts != june9_counts
    assert june8_counts['Unavailable'] == 1
    assert june9_counts.get('Unavailable', 0) == 0

    _set_runtime_today(monkeypatch, date(2026, 6, 9))
    dashboard = client.get('/api/bullpen/dashboard').get_json()

    assert dashboard['freshness']['availability_reference_date'] == '2026-06-08'
    assert dashboard['availability_summary']['statuses']['Unavailable'] == 1
    assert dashboard['availability_summary']['statuses'].get('Limited', 0) == 0


def test_team_board_detail_and_changes_share_product_reference_date(client, monkeypatch):
    with client.application.app_context():
        pitcher = _seed_reference_date_case()
        pitcher_id = pitcher.id

    _set_runtime_today(monkeypatch, date(2026, 6, 9))
    board = client.get('/api/bullpen/teams/1/board').get_json()
    card = [card for group in board['groups'] for card in group['pitchers']][0]
    detail = client.get(f'/api/bullpen/fatigue/{pitcher_id}').get_json()
    bullpen = client.get('/api/bullpen/teams/1/bullpen?include_stale=true').get_json()
    changes = client.get('/api/bullpen/teams/1/changes').get_json()

    assert board['freshness']['availability_reference_date'] == '2026-06-08'
    assert board['context']['metrics']['unavailable'] == 1
    assert board['stress']['state'] == board['context']['health']['state']
    assert card['availability_status'] == 'Unavailable'
    assert detail['availability']['inputs']['reference_date'] == '2026-06-08'
    assert bullpen[0]['availability']['inputs']['reference_date'] == '2026-06-08'
    assert changes['comparison']['current_game_date'] == '2026-06-07'

    _set_runtime_today(monkeypatch, date(2026, 6, 8))
    board_again = client.get('/api/bullpen/teams/1/board').get_json()
    changes_again = client.get('/api/bullpen/teams/1/changes').get_json()

    assert board_again['context']['metrics'] == board['context']['metrics']
    assert changes_again['comparison'] == changes['comparison']
    assert changes_again['state'] == changes['state']


def test_metadata_unavailable_fails_closed_without_current_freshness_claim(client, monkeypatch):
    with client.application.app_context():
        _seed_reference_date_case()

    def raise_metadata_error():
        raise RuntimeError('metadata unavailable')

    monkeypatch.setattr(
        bullpen_api.sync_metadata,
        'build_sync_status_payload',
        raise_metadata_error,
    )

    dashboard = client.get('/api/bullpen/dashboard').get_json()

    assert dashboard['freshness']['freshness_state'] == 'metadata_unavailable'
    assert dashboard['freshness']['is_current'] is False
    assert dashboard['freshness']['reason_codes'] == ['durable_sync_metadata_unavailable']
