"""Product understanding observation tests (Phase D2A-3).

Verifies story_viewed is recorded as an immutable, append-only observation in the
canonical Product Event log — the presentation fact only (which story, team,
surface, and who), with no inference of engagement / understanding / completion —
and that it changes no existing behavior.
"""

from urllib.parse import parse_qs, urlparse

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db
from utils import auth_email
from models.user import User
import models.pitcher  # noqa: F401  (registered so create_all builds the schema)
from models.product_event import ProductEvent
from api.auth import auth_bp
from api.product_events import product_bp
from services.product_events import (
    SIGNED_IN,
    STORY_SURFACE_HOME,
    STORY_VIEWED,
)


@pytest.fixture
def app():
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['APP_ENV'] = 'test'
    app.config['USER_AUTH_SECRET'] = 'd2a3-secret'
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


def _events(name=None):
    query = ProductEvent.query
    if name is not None:
        query = query.filter_by(event_name=name)
    return query.order_by(ProductEvent.id).all()


def _story_payload(**overrides):
    payload = {
        'team_id': 118, 'story_id': '118:2026-06-22',
        'story_type': 'coverage_pressure', 'surface': 'home',
    }
    payload.update(overrides)
    return payload


# ── story_viewed (owned, anonymous-safe observation) ──────────────────────────

def test_story_viewed_anonymous_records_observation(app, client):
    resp = client.post('/api/product/story-viewed',
                       json=_story_payload(anon_id='anon-77'))
    assert resp.status_code == 200 and resp.get_json()['ok'] is True
    with app.app_context():
        events = _events(STORY_VIEWED)
        assert len(events) == 1
        ev = events[0]
        assert ev.user_id is None and ev.anon_id == 'anon-77'
        assert ev.team_id == 118 and ev.source == STORY_SURFACE_HOME
        assert ev.payload == {'story_id': '118:2026-06-22', 'story_type': 'coverage_pressure'}


def test_story_viewed_authenticated_sets_user_id(app, client):
    token = _bearer(client, email='reader@example.com')
    client.post('/api/product/story-viewed', json=_story_payload(), headers=_auth(token))
    with app.app_context():
        user = User.query.filter_by(email='reader@example.com').one()
        ev = _events(STORY_VIEWED)[-1]
        assert ev.user_id == user.id and ev.team_id == 118


def test_story_viewed_unknown_surface_is_none(app, client):
    client.post('/api/product/story-viewed', json=_story_payload(surface='popup_banner'))
    with app.app_context():
        assert _events(STORY_VIEWED)[0].source is None  # not fabricated


def test_story_viewed_empty_body_never_errors(app, client):
    assert client.post('/api/product/story-viewed').status_code == 200
    with app.app_context():
        ev = _events(STORY_VIEWED)[0]
        assert ev.team_id is None and ev.source is None
        assert ev.payload == {'story_id': None, 'story_type': None}


def test_story_viewed_caps_field_lengths(app, client):
    client.post('/api/product/story-viewed',
                json=_story_payload(story_id='x' * 200, story_type='y' * 200))
    with app.app_context():
        ev = _events(STORY_VIEWED)[0]
        assert len(ev.payload['story_id']) == 64 and len(ev.payload['story_type']) == 64


def test_story_viewed_is_append_only(app, client):
    # The same story presented twice is two immutable facts — no dedup, no mutation.
    payload = _story_payload()
    client.post('/api/product/story-viewed', json=payload)
    client.post('/api/product/story-viewed', json=payload)
    with app.app_context():
        assert len(_events(STORY_VIEWED)) == 2


def test_story_viewed_does_not_emit_other_events(app, client):
    # Observation only: a story view never produces a signed_in or any other event.
    client.post('/api/product/story-viewed', json=_story_payload())
    with app.app_context():
        assert [e.event_name for e in _events()] == [STORY_VIEWED]
        assert _events(SIGNED_IN) == []
