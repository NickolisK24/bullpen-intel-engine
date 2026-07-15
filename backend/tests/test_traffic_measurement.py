import importlib.util
from pathlib import Path
from types import SimpleNamespace
import uuid

from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import Flask
import pytest
import sqlalchemy as sa

from api.traffic import traffic_bp
from models.traffic_internal_visitor import TrafficInternalVisitor
from models.traffic_page_view import TrafficPageView
from services.traffic_measurement import (
    classify_device,
    is_known_bot,
    normalize_entry_source,
    normalize_evidence_target,
    normalize_page_view,
    record_page_view,
)
from utils.db import db


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / 'migrations' / 'versions' / 'a9e4c7d2f1b6_add_trusted_external_traffic.py'
)
CONTEXT_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / 'migrations' / 'versions' / 'b2e7c4a9d1f3_add_traffic_evidence_context.py'
)


@pytest.fixture
def traffic_app():
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        TRAFFIC_INTERNAL_EMAILS='founder@example.com',
    )
    db.init_app(app)
    app.register_blueprint(traffic_bp, url_prefix='/api/traffic')
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def payload(**changes):
    result = {
        'view_id': str(uuid.uuid4()),
        'visitor_id': str(uuid.uuid4()),
        'session_id': str(uuid.uuid4()),
        'route': '/dashboard',
        'surface': 'dashboard',
        'site_host': 'baseballos.app',
    }
    result.update(changes)
    return result


def test_valid_insert_and_duplicate_are_idempotent(traffic_app):
    client = traffic_app.test_client()
    body = payload()
    assert client.post('/api/traffic/page-view', json=body).status_code == 202
    assert client.post('/api/traffic/page-view', json=body).status_code == 202
    with traffic_app.app_context():
        rows = TrafficPageView.query.all()
        assert len(rows) == 1
        assert rows[0].occurred_at is not None
        assert rows[0].surface == 'dashboard'
        assert rows[0].schema_version == 2


@pytest.mark.parametrize('sensitive_value', [
    'fan@example.com',
    'campaign\nAuthorization: Bearer abc',
    'Bearer abcdefghijklmnop',
    'access_token=abcdefgh',
    'client-secret-value',
    'password=hunter2',
    'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signaturevalue',
    'sk-live_abcdefghijklmnopqrstuvwxyz',
    'AKIAABCDEFGHIJKLMNOP',
])
def test_sensitive_utm_values_are_omitted_from_stored_rows(traffic_app, sensitive_value):
    body = payload(
        utm_source='newsletter',
        utm_medium=sensitive_value,
        utm_campaign=sensitive_value,
        utm_content=sensitive_value,
    )
    assert traffic_app.test_client().post('/api/traffic/page-view', json=body).status_code == 202
    with traffic_app.app_context():
        row = TrafficPageView.query.one()
        assert row.utm_source == 'newsletter'
        assert row.utm_medium is None
        assert row.utm_campaign is None
        assert row.utm_content is None


@pytest.mark.parametrize('changes', [
    {'view_id': 'invalid'},
    {'route': '/admin', 'surface': 'dashboard'},
    {'route': '/dashboard?secret=1'},
    {'surface': 'free_form'},
    {'arbitrary': {'unsafe': True}},
    {'site_host': 'baseballos.vercel.app'},
])
def test_invalid_or_unsafe_input_records_nothing(traffic_app, changes):
    response = traffic_app.test_client().post('/api/traffic/page-view', json=payload(**changes))
    assert response.status_code == 202
    with traffic_app.app_context():
        assert TrafficPageView.query.count() == 0


def test_surface_allowlist_and_safe_comparison_context():
    normalized = normalize_page_view(payload(
        route='/bullpen', surface='compare_bullpens', view_mode='compare',
        team_a_ref='nyy', team_b_ref='bos', evidence_target='comparison_read',
    ))
    assert normalized['team_ref'] is None
    assert normalized['team_a_ref'] == 'NYY'
    assert normalized['team_b_ref'] == 'BOS'
    assert normalized['evidence_target'] == 'comparison_read'
    assert normalize_page_view(payload(
        route='/bullpen', surface='compare_bullpens', view_mode='unknown',
    )) is None


@pytest.mark.parametrize(('evidence_target', 'team_ref', 'pitcher_id'), [
    ('team_read', 'BOS', None),
    ('team_relief_work', 'BOS', None),
    ('pitcher_lanes', 'BOS', None),
    ('pitcher_detail', 'BOS', '123'),
])
def test_valid_board_evidence_context(evidence_target, team_ref, pitcher_id):
    normalized = normalize_page_view(payload(
        route='/bullpen', surface='bullpen_board', view_mode='board',
        team_ref=team_ref, pitcher_id=pitcher_id, evidence_target=evidence_target,
        entry_source='DASHBOARD',
    ))
    assert normalized['team_ref'] == 'BOS'
    assert normalized['pitcher_id'] == (123 if pitcher_id else None)
    assert normalized['entry_source'] == 'dashboard'
    assert normalized['evidence_target'] == evidence_target


def test_comparison_visible_order_is_preserved_and_same_team_is_narrowed():
    reverse = normalize_page_view(payload(
        route='/bullpen', surface='compare_bullpens', view_mode='compare',
        team_a_ref='NYY', team_b_ref='BOS', evidence_target='comparison_evidence',
    ))
    assert (reverse['team_a_ref'], reverse['team_b_ref']) == ('NYY', 'BOS')

    same = normalize_page_view(payload(
        route='/bullpen', surface='compare_bullpens', view_mode='compare',
        team_a_ref='BOS', team_b_ref='bos',
    ))
    assert same['team_a_ref'] is None
    assert same['team_b_ref'] is None


@pytest.mark.parametrize('changes', [
    {'route': '/bullpen', 'surface': 'bullpen_board', 'view_mode': 'board', 'team_ref': 'BOS', 'evidence_target': 'comparison_read'},
    {'route': '/bullpen', 'surface': 'compare_bullpens', 'view_mode': 'compare', 'team_a_ref': 'BOS', 'team_b_ref': 'NYY', 'evidence_target': 'team_read'},
    {'route': '/bullpen', 'surface': 'all_pitchers', 'view_mode': 'pitchers', 'evidence_target': 'pitcher_detail'},
    {'route': '/bullpen', 'surface': 'bullpen_board', 'view_mode': 'board', 'evidence_target': 'unknown'},
    {'route': '/bullpen', 'surface': 'compare_bullpens', 'view_mode': 'compare', 'team_ref': 'BOS'},
    {'route': '/bullpen', 'surface': 'all_pitchers', 'view_mode': 'pitchers', 'pitcher_id': 123},
])
def test_incompatible_bullpen_context_is_rejected(changes):
    assert normalize_page_view(payload(**changes)) is None


def test_bounded_entry_source_and_evidence_normalizers():
    for source in ('today', 'dashboard', 'landscape', 'stories', 'comparison', 'all_pitchers', 'pitcher_search', 'share', 'share_link', 'share_card'):
        assert normalize_entry_source(source.upper()) == source
    assert normalize_entry_source('private') is None
    assert normalize_evidence_target('TEAM_RELIEF_WORK') == 'team_relief_work'
    assert normalize_evidence_target('raw-hash') is None


def test_unknown_entry_source_is_dropped_but_non_bullpen_context_is_rejected():
    board = normalize_page_view(payload(
        route='/bullpen', surface='bullpen_board', view_mode='board', entry_source='private',
    ))
    assert board['entry_source'] is None
    assert normalize_page_view(payload(entry_source='dashboard')) is None
    assert normalize_page_view(payload(evidence_target='team_read')) is None


def test_bot_and_coarse_device_classification():
    assert is_known_bot('Googlebot/2.1') is True
    assert is_known_bot('Mozilla/5.0') is False
    assert classify_device('Mozilla/5.0 (iPhone) Mobile') == 'mobile'
    assert classify_device('Mozilla/5.0 (iPad)') == 'tablet'
    assert classify_device('Mozilla/5.0 (Windows NT 10.0)') == 'desktop'
    assert classify_device('curl/8') == 'unknown'


def test_allowlisted_user_registration_is_idempotent_and_anonymous_stays_external(traffic_app):
    with traffic_app.app_context():
        visitor_id = str(uuid.uuid4())
        user = SimpleNamespace(id=9, email=' FOUNDER@example.com ')
        first = payload(visitor_id=visitor_id)
        second = payload(visitor_id=visitor_id)
        assert record_page_view(first, current_user=user, internal_emails='founder@example.com') == 'inserted'
        db.session.commit()
        assert record_page_view(second, current_user=user, internal_emails='founder@example.com') == 'inserted'
        db.session.commit()
        assert TrafficInternalVisitor.query.count() == 1
        internal = TrafficInternalVisitor.query.one()
        assert internal.visitor_id == visitor_id
        assert internal.registered_by_user_id == 9
        assert not hasattr(internal, 'email')

        assert record_page_view(payload(), current_user=None, internal_emails='founder@example.com') == 'inserted'
        db.session.commit()
        assert TrafficInternalVisitor.query.count() == 1


def test_fault_isolation_always_returns_202(traffic_app, monkeypatch):
    import api.traffic as traffic_api

    monkeypatch.setattr(traffic_api, 'record_page_view', lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('write failed')))
    response = traffic_app.test_client().post('/api/traffic/page-view', json=payload())
    assert response.status_code == 202


def test_migration_upgrade_and_downgrade_restore_expected_shapes():
    engine = sa.create_engine('sqlite:///:memory:')
    metadata = sa.MetaData()
    sa.Table(
        'users', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('notification_prefs', sa.JSON),
    )
    sa.Table('digest_runs', metadata, sa.Column('id', sa.Integer, primary_key=True))
    sa.Table('digest_deliveries', metadata, sa.Column('id', sa.Integer, primary_key=True))
    sa.Table('product_events', metadata, sa.Column('id', sa.Integer, primary_key=True))
    metadata.create_all(engine)

    spec = importlib.util.spec_from_file_location('trusted_traffic_migration', MIGRATION_PATH)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        inspector = sa.inspect(connection)
        tables = set(inspector.get_table_names())
        assert {'traffic_internal_visitors', 'traffic_page_views'} <= tables
        assert {'product_events', 'digest_deliveries', 'digest_runs'}.isdisjoint(tables)
        assert 'notification_prefs' not in {column['name'] for column in inspector.get_columns('users')}
        page_columns = {column['name'] for column in inspector.get_columns('traffic_page_views')}
        assert {'view_id', 'visitor_id', 'session_id', 'occurred_at', 'site_host', 'is_bot'} <= page_columns

        migration.downgrade()
        inspector = sa.inspect(connection)
        tables = set(inspector.get_table_names())
        assert {'product_events', 'digest_deliveries', 'digest_runs'} <= tables
        assert {'traffic_internal_visitors', 'traffic_page_views'}.isdisjoint(tables)
        assert 'notification_prefs' in {column['name'] for column in inspector.get_columns('users')}


def test_context_migration_adds_nullable_fields_and_useful_indexes():
    engine = sa.create_engine('sqlite:///:memory:')
    metadata = sa.MetaData()
    sa.Table(
        'traffic_page_views', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('occurred_at', sa.DateTime, nullable=False),
    )
    metadata.create_all(engine)

    spec = importlib.util.spec_from_file_location('traffic_context_migration', CONTEXT_MIGRATION_PATH)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        inspector = sa.inspect(connection)
        columns = {column['name']: column for column in inspector.get_columns('traffic_page_views')}
        for name in ('team_a_ref', 'team_b_ref', 'entry_source', 'evidence_target'):
            assert columns[name]['nullable'] is True
        indexes = {index['name'] for index in inspector.get_indexes('traffic_page_views')}
        assert {
            'ix_traffic_page_views_occurred_entry_source',
            'ix_traffic_page_views_occurred_evidence_target',
            'ix_traffic_page_views_occurred_comparison_pair',
        } <= indexes

        migration.downgrade()
        remaining = {column['name'] for column in sa.inspect(connection).get_columns('traffic_page_views')}
        assert {'team_a_ref', 'team_b_ref', 'entry_source', 'evidence_target'}.isdisjoint(remaining)
