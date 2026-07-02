"""V4 product-loop analytics event tests.

The V4.0 analytics foundation extends the owned Product Intelligence log with
current-surface events only. These tests keep the generic ingestion route
allowlisted, anonymous-safe, and fault-isolated from product behavior.
"""

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db
import models.game_log  # noqa: F401  (registered before Pitcher relationship config)
import models.fatigue_score  # noqa: F401  (registered before Pitcher relationship config)
import models.pitcher  # noqa: F401  (registered so create_all builds the schema)
from models.product_event import ProductEvent
from api.product_events import product_bp
from services.product_events import (
    APP_VIEWED,
    CANONICAL_PRODUCT_EVENTS,
    HOMEPAGE_VIEWED,
    SOCIAL_OUTBOUND_CLICKED,
    TEAM_SURFACE_VIEWED,
    V4_PRODUCT_EVENTS,
    V4_RESERVED_EVENT_NAMES,
)


@pytest.fixture
def app():
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['APP_ENV'] = 'test'
    db.init_app(app)
    app.register_blueprint(product_bp, url_prefix='/api/product')
    with app.app_context():
        create_test_schema(app)
        try:
            yield app
        finally:
            db.session.remove()
            drop_test_schema(app)


@pytest.fixture
def client(app):
    return app.test_client()


def _events(name=None):
    query = ProductEvent.query
    if name is not None:
        query = query.filter_by(event_name=name)
    return query.order_by(ProductEvent.id).all()


def test_v4_product_events_are_canonical_but_reserved_events_are_not_live():
    for name in V4_PRODUCT_EVENTS:
        assert name in CANONICAL_PRODUCT_EVENTS

    for name in V4_RESERVED_EVENT_NAMES:
        assert name not in V4_PRODUCT_EVENTS
        assert name not in CANONICAL_PRODUCT_EVENTS


def test_product_event_records_anonymous_route_observation(app, client):
    resp = client.post('/api/product/event', json={
        'event_name': HOMEPAGE_VIEWED,
        'anon_id': 'anon-v4',
        'source': 'app',
        'surface': 'home',
        'route': '/',
        'freshness_state': 'current',
    })

    assert resp.status_code == 200 and resp.get_json()['ok'] is True
    with app.app_context():
        events = _events(HOMEPAGE_VIEWED)
        assert len(events) == 1
        ev = events[0]
        assert ev.user_id is None
        assert ev.anon_id == 'anon-v4'
        assert ev.source == 'app'
        assert ev.payload == {
            'surface': 'home',
            'route': '/',
            'freshness_state': 'current',
        }


def test_product_event_records_team_and_player_context(app, client):
    client.post('/api/product/event', json={
        'event_name': TEAM_SURFACE_VIEWED,
        'team_id': '137',
        'source': 'team_selector',
        'surface': 'bullpen',
        'route': '/bullpen',
        'team_abbrev': 'sf',
        'player_id': '657277',
    })

    with app.app_context():
        ev = _events(TEAM_SURFACE_VIEWED)[0]
        assert ev.team_id == 137
        assert ev.source == 'team_selector'
        assert ev.payload == {
            'surface': 'bullpen',
            'route': '/bullpen',
            'team_abbrev': 'SF',
            'player_id': 657277,
        }


def test_product_event_ignores_unknown_and_reserved_events(app, client):
    assert client.post('/api/product/event', json={'event_name': 'story_engaged'}).status_code == 200
    assert client.post('/api/product/event', json={'event_name': 'feedback_intent_clicked'}).status_code == 200
    assert client.post('/api/product/event').status_code == 200

    with app.app_context():
        assert _events() == []


def test_product_event_drops_unsafe_optional_properties(app, client):
    client.post('/api/product/event', json={
        'event_name': SOCIAL_OUTBOUND_CLICKED,
        'anon_id': 'fan@example.com',
        'source': 'fan@example.com',
        'surface': 'footer',
        'route': 'mailto:baseballoshq@gmail.com',
        'team_abbrev': 'too-long',
        'player_id': 'not-a-player',
        'freshness_state': 'current state',
    })

    with app.app_context():
        ev = _events(SOCIAL_OUTBOUND_CLICKED)[0]
        assert ev.anon_id is None
        assert ev.source is None
        assert ev.payload == {'surface': 'footer'}


def test_app_viewed_constant_remains_stable():
    assert APP_VIEWED == 'app_viewed'
