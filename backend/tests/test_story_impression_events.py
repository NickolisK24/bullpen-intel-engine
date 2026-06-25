"""Story impression observation tests (Phase V3-1).

Verifies story_impression is recorded as an immutable, append-only observation in
the canonical Product Event log — the on-screen presentation fact only (which
story, team, surface, and who), with no inference of engagement / dwell / reading
/ understanding — through the owned generic /story-event ingestion endpoint, and
that it neither breaks nor changes the legacy story_viewed contract.
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
    CANONICAL_PRODUCT_EVENTS,
    STORY_IMPRESSION,
    STORY_SURFACE_HOME,
    STORY_VIEWED,
)


@pytest.fixture
def app():
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['APP_ENV'] = 'test'
    app.config['USER_AUTH_SECRET'] = 'v31-secret'
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


def _impression_payload(**overrides):
    payload = {
        'event_name': 'story_impression',
        'team_id': 118, 'story_id': '118:2026-06-22',
        'story_type': 'coverage_pressure', 'surface': 'home',
    }
    payload.update(overrides)
    return payload


# ── story_impression vocabulary ───────────────────────────────────────────────

def test_story_impression_is_canonical():
    assert STORY_IMPRESSION == 'story_impression'
    assert STORY_IMPRESSION in CANONICAL_PRODUCT_EVENTS


# ── story_impression (owned, anonymous-safe observation via /story-event) ──────

def test_story_impression_anonymous_records_observation(app, client):
    resp = client.post('/api/product/story-event',
                       json=_impression_payload(anon_id='anon-88'))
    assert resp.status_code == 200 and resp.get_json()['ok'] is True
    with app.app_context():
        events = _events(STORY_IMPRESSION)
        assert len(events) == 1
        ev = events[0]
        assert ev.user_id is None and ev.anon_id == 'anon-88'
        assert ev.team_id == 118 and ev.source == STORY_SURFACE_HOME
        assert ev.payload == {'story_id': '118:2026-06-22', 'story_type': 'coverage_pressure'}


def test_story_impression_authenticated_sets_user_id(app, client):
    token = _bearer(client, email='reader@example.com')
    client.post('/api/product/story-event', json=_impression_payload(), headers=_auth(token))
    with app.app_context():
        user = User.query.filter_by(email='reader@example.com').one()
        ev = _events(STORY_IMPRESSION)[-1]
        assert ev.user_id == user.id and ev.team_id == 118


def test_story_impression_unknown_surface_is_none(app, client):
    client.post('/api/product/story-event', json=_impression_payload(surface='popup_banner'))
    with app.app_context():
        assert _events(STORY_IMPRESSION)[0].source is None  # not fabricated


def test_story_impression_caps_field_lengths(app, client):
    client.post('/api/product/story-event',
                json=_impression_payload(story_id='x' * 200, story_type='y' * 200))
    with app.app_context():
        ev = _events(STORY_IMPRESSION)[0]
        assert len(ev.payload['story_id']) == 64 and len(ev.payload['story_type']) == 64


def test_story_impression_is_append_only(app, client):
    # The same card appearing twice is two immutable facts — no dedup, no mutation.
    payload = _impression_payload()
    client.post('/api/product/story-event', json=payload)
    client.post('/api/product/story-event', json=payload)
    with app.app_context():
        assert len(_events(STORY_IMPRESSION)) == 2


# ── allowlist + best-effort, always-200 conventions ───────────────────────────

def test_story_event_ignores_unknown_event_name(app, client):
    # A disallowed event_name records nothing, but the beacon still succeeds (200).
    resp = client.post('/api/product/story-event',
                       json=_impression_payload(event_name='story_engaged'))
    assert resp.status_code == 200 and resp.get_json()['ok'] is True
    with app.app_context():
        assert _events() == []  # nothing fabricated


def test_story_event_missing_event_name_records_nothing(app, client):
    resp = client.post('/api/product/story-event',
                       json={'team_id': 118, 'story_id': 's', 'story_type': 'coverage_pressure'})
    assert resp.status_code == 200
    with app.app_context():
        assert _events() == []


def test_story_event_empty_body_never_errors(app, client):
    # No body -> no event_name -> nothing recorded, still 200 (best-effort).
    assert client.post('/api/product/story-event').status_code == 200
    with app.app_context():
        assert _events() == []


# ── legacy contract preserved (V3-1 is additive) ──────────────────────────────

def test_legacy_story_viewed_endpoint_still_records(app, client):
    resp = client.post('/api/product/story-viewed',
                       json={'team_id': 118, 'story_id': '118:2026-06-22',
                             'story_type': 'coverage_pressure', 'surface': 'stories',
                             'anon_id': 'anon-9'})
    assert resp.status_code == 200
    with app.app_context():
        events = _events(STORY_VIEWED)
        assert len(events) == 1
        assert events[0].source == 'stories'
        assert events[0].payload == {'story_id': '118:2026-06-22', 'story_type': 'coverage_pressure'}
