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
from models.traffic_share_action import TrafficShareAction
from services.traffic_share_actions import normalize_share_action, record_share_action
from utils.db import db


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / 'migrations' / 'versions' / 'c4f8a2d6e9b3_add_traffic_share_actions.py'
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
        'event_id': str(uuid.uuid4()),
        'visitor_id': str(uuid.uuid4()),
        'session_id': str(uuid.uuid4()),
        'surface': 'bullpen_board',
        'card_type': 'team',
        'action': 'copy_link',
        'team_ref': 'BOS',
        'evidence_target': 'team_read',
        'data_through': '2026-07-15',
        'site_host': 'baseballos.app',
    }
    result.update(changes)
    return result


def test_valid_team_action_and_duplicate_event_are_idempotent(traffic_app):
    body = payload()
    client = traffic_app.test_client()
    assert client.post('/api/traffic/share-action', json=body).status_code == 202
    assert client.post('/api/traffic/share-action', json=body).status_code == 202
    with traffic_app.app_context():
        row = TrafficShareAction.query.one()
        assert row.team_ref == 'BOS'
        assert row.data_through.isoformat() == '2026-07-15'
        assert row.schema_version == 1


def test_valid_comparison_preserves_visible_order():
    normalized = normalize_share_action(payload(
        surface='compare_bullpens', card_type='comparison', action='native_card_share',
        team_ref=None, team_a_ref='NYY', team_b_ref='BOS',
        evidence_target='comparison_evidence', data_through=None,
    ))
    assert normalized['team_a_ref'] == 'NYY'
    assert normalized['team_b_ref'] == 'BOS'
    assert normalized['team_ref'] is None


def test_valid_story_link_only_action():
    normalized = normalize_share_action(payload(
        surface='stories', card_type='link_only', action='native_link_share',
        evidence_target='team_read', data_through=None,
    ))
    assert normalized['surface'] == 'stories'
    assert normalized['card_type'] == 'link_only'


@pytest.mark.parametrize('changes', [
    {'action': 'opened_menu'},
    {'card_type': 'pitcher'},
    {'surface': 'dashboard'},
    {'evidence_target': 'raw-hash'},
    {'site_host': 'preview.baseballos.app'},
    {'arbitrary_url': 'https://example.com'},
    {'share_text': 'private'},
    {'recipient': 'fan@example.com'},
    {'platform': 'social-network'},
])
def test_unknown_unbounded_or_noncanonical_values_are_rejected(changes):
    assert normalize_share_action(payload(**changes)) is None


@pytest.mark.parametrize('changes', [
    {'team_a_ref': 'NYY'},
    {'surface': 'compare_bullpens', 'card_type': 'comparison', 'team_ref': 'BOS', 'team_a_ref': 'BOS', 'team_b_ref': 'NYY'},
    {'surface': 'compare_bullpens', 'card_type': 'comparison', 'team_ref': None, 'team_a_ref': 'BOS', 'team_b_ref': None},
    {'surface': 'compare_bullpens', 'card_type': 'comparison', 'team_ref': None, 'team_a_ref': 'BOS', 'team_b_ref': 'BOS'},
    {'surface': 'stories', 'card_type': 'link_only', 'action': 'download_card'},
    {'surface': 'stories', 'card_type': 'link_only', 'action': 'native_card_share'},
])
def test_incompatible_subject_or_action_combinations_are_rejected(changes):
    assert normalize_share_action(payload(**changes)) is None


def test_bot_and_device_classification_are_reused():
    bot = normalize_share_action(payload(), user_agent='Googlebot/2.1')
    mobile = normalize_share_action(payload(), user_agent='Mozilla/5.0 (iPhone) Mobile')
    assert bot['is_bot'] is True
    assert mobile['device_class'] == 'mobile'


def test_internal_browser_registration_is_reused(traffic_app):
    with traffic_app.app_context():
        visitor_id = str(uuid.uuid4())
        user = SimpleNamespace(id=9, email='FOUNDER@example.com')
        assert record_share_action(
            payload(visitor_id=visitor_id),
            current_user=user,
            internal_emails='founder@example.com',
        ) == 'inserted'
        db.session.commit()
        assert TrafficInternalVisitor.query.one().visitor_id == visitor_id


def test_context_migration_creates_share_table_without_touching_page_views():
    engine = sa.create_engine('sqlite:///:memory:')
    metadata = sa.MetaData()
    page_views = sa.Table(
        'traffic_page_views', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('view_id', sa.String(36), nullable=False),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(page_views.insert().values(id=1, view_id='existing-page-view'))

    spec = importlib.util.spec_from_file_location('share_action_migration', MIGRATION_PATH)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        inspector = sa.inspect(connection)
        assert 'traffic_share_actions' in inspector.get_table_names()
        columns = {column['name'] for column in inspector.get_columns('traffic_share_actions')}
        assert {
            'event_id', 'visitor_id', 'session_id', 'surface', 'card_type', 'action',
            'team_ref', 'team_a_ref', 'team_b_ref', 'evidence_target', 'data_through',
            'site_host', 'device_class', 'is_bot', 'schema_version',
        } <= columns
        assert connection.execute(sa.select(page_views.c.view_id)).scalar_one() == 'existing-page-view'
        indexes = {index['name'] for index in inspector.get_indexes('traffic_share_actions')}
        assert 'ix_traffic_share_actions_event_id' in indexes

        migration.downgrade()
        assert 'traffic_share_actions' not in sa.inspect(connection).get_table_names()
