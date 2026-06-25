"""Product interaction observation tests (Phase D2A-7).

Verifies story_interacted records only the fact of an explicit interaction with a
rendered story (which story, surface, interaction kind, and who) as an immutable,
append-only event — inferring nothing about engagement or understanding — and
changes no existing behavior.
"""

from urllib.parse import parse_qs, urlparse

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db
from utils import auth_email
from utils.auth_tokens import generate_tracking_token  # noqa: F401 (ensures token utils import)
from models.user import User
import models.pitcher  # noqa: F401  (registered so create_all builds the schema)
from models.product_event import ProductEvent
from api.auth import auth_bp
from api.product_events import product_bp
from services.product_events import STORY_INTERACTED


@pytest.fixture
def app():
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['APP_ENV'] = 'test'
    app.config['USER_AUTH_SECRET'] = 'd2a7-secret'
    app.config['MAGIC_LINK_TTL_SECONDS'] = 900
    app.config['AUTH_TOKEN_TTL_SECONDS'] = 3600
    app.config['FRONTEND_BASE_URL'] = 'http://localhost:5173'
    db.init_app(app)
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(product_bp, url_prefix='/api/product')
    with app.app_context():
        create_test_schema(app)
        auth_email.reset_outbox()
        try:
            yield app
        finally:
            db.session.remove()
            drop_test_schema(app)
            auth_email.reset_outbox()


@pytest.fixture
def client(app):
    return app.test_client()


def _bearer(client, email='fan@example.com'):
    client.post('/api/auth/request-link', json={'email': email})
    link = auth_email.outbox[-1]['link']
    token = parse_qs(urlparse(link).query)['token'][0]
    return client.post('/api/auth/verify', json={'token': token}).get_json()['token']


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


def _events(name=STORY_INTERACTED):
    return ProductEvent.query.filter_by(event_name=name).order_by(ProductEvent.id).all()


def _payload(**overrides):
    payload = {
        'team_id': 118, 'story_id': '118:2026-06-25',
        'story_type': 'coverage_pressure', 'surface': 'stories',
        'interaction_type': 'select',
    }
    payload.update(overrides)
    return payload


def test_story_interacted_anonymous_records_observation(app, client):
    resp = client.post('/api/product/story-interacted', json=_payload(anon_id='anon-9'))
    assert resp.status_code == 200 and resp.get_json()['ok'] is True
    with app.app_context():
        events = _events()
        assert len(events) == 1
        ev = events[0]
        assert ev.user_id is None and ev.anon_id == 'anon-9'
        assert ev.team_id == 118 and ev.source == 'stories'
        assert ev.payload == {
            'story_id': '118:2026-06-25',
            'story_type': 'coverage_pressure',
            'interaction_type': 'select',
        }


def test_story_interacted_authenticated_sets_user_id(app, client):
    token = _bearer(client, email='clicker@example.com')
    client.post('/api/product/story-interacted', json=_payload(), headers=_auth(token))
    with app.app_context():
        user = User.query.filter_by(email='clicker@example.com').one()
        assert _events()[-1].user_id == user.id


def test_story_interacted_normalizes_unknown_interaction_and_surface(app, client):
    client.post('/api/product/story-interacted',
                json=_payload(interaction_type='hover', surface='popup'))
    with app.app_context():
        ev = _events()[0]
        assert ev.source is None  # unknown surface not fabricated
        assert ev.payload['interaction_type'] is None  # unknown kind not fabricated


def test_story_interacted_empty_body_never_errors(app, client):
    assert client.post('/api/product/story-interacted').status_code == 200
    with app.app_context():
        ev = _events()[0]
        assert ev.team_id is None and ev.source is None
        assert ev.payload == {'story_id': None, 'story_type': None, 'interaction_type': None}


def test_story_interacted_is_append_only(app, client):
    # Each explicit interaction is its own immutable fact (backend never dedupes).
    client.post('/api/product/story-interacted', json=_payload())
    client.post('/api/product/story-interacted', json=_payload())
    with app.app_context():
        assert len(_events()) == 2
