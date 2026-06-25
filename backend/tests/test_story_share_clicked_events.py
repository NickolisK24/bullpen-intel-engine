"""Story share-click observation tests (Phase V3-3).

Verifies story_share_clicked is recorded as an immutable, append-only observation
through the owned generic /story-event endpoint — the share-INTENT fact from a
story context (which story, team, surface, who, and the team-scoped share_target)
— and that adding it to the allowlist neither breaks the other story-event names
nor the legacy story_viewed / story_interacted endpoints.
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
    STORY_SHARE_CLICKED,
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
    app.config['USER_AUTH_SECRET'] = 'v33-secret'
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


def _share_payload(**overrides):
    payload = {
        'event_name': 'story_share_clicked',
        'team_id': 158, 'story_id': '158:2026-06-22',
        'story_type': 'coverage_pressure', 'surface': 'stories',
        'share_target': 'team',
    }
    payload.update(overrides)
    return payload


# ── vocabulary + allowlist ────────────────────────────────────────────────────

def test_story_share_clicked_is_canonical():
    assert STORY_SHARE_CLICKED == 'story_share_clicked'
    assert STORY_SHARE_CLICKED in CANONICAL_PRODUCT_EVENTS


def test_story_event_allowlist_holds_all_v3_names():
    for name in (STORY_IMPRESSION, STORY_TEAM_BOARD_OPENED, STORY_SHARE_CLICKED):
        assert name in STORY_EVENT_NAMES


# ── story_share_clicked (owned, anonymous-safe, via /story-event) ──────────────

def test_share_clicked_anonymous_records_observation_with_share_target(app, client):
    resp = client.post('/api/product/story-event', json=_share_payload(anon_id='anon-33'))
    assert resp.status_code == 200 and resp.get_json()['ok'] is True
    with app.app_context():
        events = _events(STORY_SHARE_CLICKED)
        assert len(events) == 1
        ev = events[0]
        assert ev.user_id is None and ev.anon_id == 'anon-33'
        assert ev.team_id == 158 and ev.source == STORY_SURFACE_STORIES
        assert ev.payload == {
            'story_id': '158:2026-06-22',
            'story_type': 'coverage_pressure',
            'share_target': 'team',
        }


def test_share_clicked_authenticated_sets_user_id(app, client):
    token = _bearer(client, email='reader@example.com')
    client.post('/api/product/story-event', json=_share_payload(), headers=_auth(token))
    with app.app_context():
        user = User.query.filter_by(email='reader@example.com').one()
        ev = _events(STORY_SHARE_CLICKED)[-1]
        assert ev.user_id == user.id and ev.team_id == 158
        assert ev.payload['share_target'] == 'team'


def test_share_clicked_unknown_surface_is_none(app, client):
    client.post('/api/product/story-event', json=_share_payload(surface='popup_banner'))
    with app.app_context():
        assert _events(STORY_SHARE_CLICKED)[0].source is None  # not fabricated


def test_share_clicked_unknown_share_target_is_dropped(app, client):
    # An unrecognized share_target is not fabricated — the payload omits it.
    client.post('/api/product/story-event', json=_share_payload(share_target='galaxy'))
    with app.app_context():
        ev = _events(STORY_SHARE_CLICKED)[0]
        assert ev.payload == {'story_id': '158:2026-06-22', 'story_type': 'coverage_pressure'}


def test_share_clicked_caps_field_lengths(app, client):
    client.post('/api/product/story-event',
                json=_share_payload(story_id='x' * 200, story_type='y' * 200))
    with app.app_context():
        ev = _events(STORY_SHARE_CLICKED)[0]
        assert len(ev.payload['story_id']) == 64 and len(ev.payload['story_type']) == 64
        assert ev.payload['share_target'] == 'team'


def test_share_clicked_is_append_only_per_click(app, client):
    payload = _share_payload()
    client.post('/api/product/story-event', json=payload)
    client.post('/api/product/story-event', json=payload)
    with app.app_context():
        assert len(_events(STORY_SHARE_CLICKED)) == 2


def test_story_event_still_ignores_unknown_event_name(app, client):
    resp = client.post('/api/product/story-event', json=_share_payload(event_name='story_engaged'))
    assert resp.status_code == 200 and resp.get_json()['ok'] is True
    with app.app_context():
        assert _events() == []  # nothing fabricated


# ── other story-event names keep their minimal shape (no share_target) ─────────

def test_impression_and_team_board_keep_minimal_payload(app, client):
    client.post('/api/product/story-event',
                json={'event_name': 'story_impression', 'team_id': 137,
                      'story_id': '137:2026-06-22', 'story_type': 'availability_depth',
                      'surface': 'home'})
    client.post('/api/product/story-event',
                json={'event_name': 'story_team_board_opened', 'team_id': 137,
                      'story_id': '137:2026-06-22', 'story_type': 'availability_depth',
                      'surface': 'home'})
    with app.app_context():
        for name in (STORY_IMPRESSION, STORY_TEAM_BOARD_OPENED):
            ev = _events(name)[0]
            assert ev.payload == {'story_id': '137:2026-06-22', 'story_type': 'availability_depth'}
            assert 'share_target' not in ev.payload


# ── legacy contracts preserved (V3-3 is additive) ─────────────────────────────

def test_legacy_story_viewed_endpoint_still_records(app, client):
    resp = client.post('/api/product/story-viewed',
                       json={'team_id': 158, 'story_id': '158:2026-06-22',
                             'story_type': 'coverage_pressure', 'surface': 'stories'})
    assert resp.status_code == 200
    with app.app_context():
        events = _events(STORY_VIEWED)
        assert len(events) == 1
        assert events[0].payload == {'story_id': '158:2026-06-22', 'story_type': 'coverage_pressure'}
