"""Story team-board open observation tests (Phase V3-2).

Verifies story_team_board_opened is recorded as an immutable, append-only
observation through the owned generic /story-event endpoint — the high-intent
story → Team Board conversion fact only (which story, team, surface, and who) —
and that adding it to the allowlist neither breaks the legacy story_viewed /
story_interacted endpoints nor the existing story_impression seam.
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
    STORY_EVENT_NAMES,
    STORY_IMPRESSION,
    STORY_INTERACTED,
    STORY_SURFACE_STORIES,
    STORY_TEAM_BOARD_OPENED,
    STORY_VIEWED,
)


@pytest.fixture
def app():
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['APP_ENV'] = 'test'
    app.config['USER_AUTH_SECRET'] = 'v32-secret'
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


def _open_payload(**overrides):
    payload = {
        'event_name': 'story_team_board_opened',
        'team_id': 158, 'story_id': '158:2026-06-22',
        'story_type': 'coverage_pressure', 'surface': 'stories',
    }
    payload.update(overrides)
    return payload


# ── vocabulary + allowlist ────────────────────────────────────────────────────

def test_story_team_board_opened_is_canonical():
    assert STORY_TEAM_BOARD_OPENED == 'story_team_board_opened'
    assert STORY_TEAM_BOARD_OPENED in CANONICAL_PRODUCT_EVENTS


def test_story_event_allowlist_holds_both_v3_names():
    assert STORY_IMPRESSION in STORY_EVENT_NAMES
    assert STORY_TEAM_BOARD_OPENED in STORY_EVENT_NAMES


# ── story_team_board_opened (owned, anonymous-safe, via /story-event) ──────────

def test_team_board_opened_anonymous_records_observation(app, client):
    resp = client.post('/api/product/story-event', json=_open_payload(anon_id='anon-21'))
    assert resp.status_code == 200 and resp.get_json()['ok'] is True
    with app.app_context():
        events = _events(STORY_TEAM_BOARD_OPENED)
        assert len(events) == 1
        ev = events[0]
        assert ev.user_id is None and ev.anon_id == 'anon-21'
        assert ev.team_id == 158 and ev.source == STORY_SURFACE_STORIES
        assert ev.payload == {'story_id': '158:2026-06-22', 'story_type': 'coverage_pressure'}


def test_team_board_opened_authenticated_sets_user_id(app, client):
    token = _bearer(client, email='reader@example.com')
    client.post('/api/product/story-event', json=_open_payload(), headers=_auth(token))
    with app.app_context():
        user = User.query.filter_by(email='reader@example.com').one()
        ev = _events(STORY_TEAM_BOARD_OPENED)[-1]
        assert ev.user_id == user.id and ev.team_id == 158


def test_team_board_opened_unknown_surface_is_none(app, client):
    client.post('/api/product/story-event', json=_open_payload(surface='popup_banner'))
    with app.app_context():
        assert _events(STORY_TEAM_BOARD_OPENED)[0].source is None  # not fabricated


def test_team_board_opened_caps_field_lengths(app, client):
    client.post('/api/product/story-event',
                json=_open_payload(story_id='x' * 200, story_type='y' * 200))
    with app.app_context():
        ev = _events(STORY_TEAM_BOARD_OPENED)[0]
        assert len(ev.payload['story_id']) == 64 and len(ev.payload['story_type']) == 64


def test_team_board_opened_is_append_only_per_click(app, client):
    # Each click is a distinct intent signal — two opens are two immutable facts.
    payload = _open_payload()
    client.post('/api/product/story-event', json=payload)
    client.post('/api/product/story-event', json=payload)
    with app.app_context():
        assert len(_events(STORY_TEAM_BOARD_OPENED)) == 2


def test_story_event_still_ignores_unknown_event_name(app, client):
    resp = client.post('/api/product/story-event', json=_open_payload(event_name='story_engaged'))
    assert resp.status_code == 200 and resp.get_json()['ok'] is True
    with app.app_context():
        assert _events() == []  # nothing fabricated


def test_story_impression_still_recorded_through_the_seam(app, client):
    client.post('/api/product/story-event',
                json={'event_name': 'story_impression', 'team_id': 137,
                      'story_id': '137:2026-06-22', 'story_type': 'availability_depth',
                      'surface': 'home'})
    with app.app_context():
        assert len(_events(STORY_IMPRESSION)) == 1


# ── legacy contracts preserved (V3-2 is additive) ─────────────────────────────

def test_legacy_story_viewed_and_interacted_endpoints_still_record(app, client):
    client.post('/api/product/story-viewed',
                json={'team_id': 158, 'story_id': '158:2026-06-22',
                      'story_type': 'coverage_pressure', 'surface': 'stories'})
    client.post('/api/product/story-interacted',
                json={'team_id': 158, 'story_id': '158:2026-06-22',
                      'story_type': 'coverage_pressure', 'surface': 'stories',
                      'interaction_type': 'select'})
    with app.app_context():
        assert len(_events(STORY_VIEWED)) == 1
        interacted = _events(STORY_INTERACTED)
        assert len(interacted) == 1
        assert interacted[0].payload['interaction_type'] == 'select'
