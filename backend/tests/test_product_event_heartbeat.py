"""Operator heartbeat tests (Phase D2A-7).

GET /api/system/product-event-heartbeat gives the operator a per-event
Name / Count / Most-Recent view so a stopped beacon (count 0 or stale timestamp)
is obvious. Admin-gated; operational verification only.
"""

from datetime import datetime, timedelta

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.auth import ADMIN_TOKEN_HEADER
from utils.db import db
from models.product_event import ProductEvent
from services.product_events import (
    CANONICAL_PRODUCT_EVENTS,
    DIGEST_COMPLAINT,
    STORY_INTERACTED,
    TODAY_LOADED,
)


@pytest.fixture
def app():
    from api.system import system_bp

    app = Flask(__name__)
    configure_test_database(app)
    app.config['APP_ENV'] = 'test'
    app.config['ADMIN_API_TOKEN'] = 'admin-secret'
    db.init_app(app)
    app.register_blueprint(system_bp, url_prefix='/api/system')
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


def _headers():
    return {ADMIN_TOKEN_HEADER: 'admin-secret'}


def _add(event_name, *, minutes_ago=0):
    db.session.add(ProductEvent(
        event_name=event_name,
        occurred_at=datetime(2026, 6, 25, 12, 0, 0) - timedelta(minutes=minutes_ago),
    ))
    db.session.commit()


def test_heartbeat_requires_admin_token(client):
    assert client.get('/api/system/product-event-heartbeat').status_code == 401


def test_heartbeat_lists_all_canonical_events_with_counts(app, client):
    with app.app_context():
        _add(TODAY_LOADED, minutes_ago=5)
        _add(TODAY_LOADED, minutes_ago=1)
        _add(STORY_INTERACTED, minutes_ago=2)

    resp = client.get('/api/system/product-event-heartbeat', headers=_headers())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['capability'] == 'product_intelligence_heartbeat'

    by_name = {row['event_name']: row for row in body['events']}
    # Every canonical event is present, so a never-seen event is visibly at zero.
    for name in CANONICAL_PRODUCT_EVENTS:
        assert name in by_name

    assert by_name[TODAY_LOADED]['count'] == 2
    assert by_name[TODAY_LOADED]['most_recent'] == '2026-06-25T11:59:00Z'  # newest of the two
    assert by_name[STORY_INTERACTED]['count'] == 1
    # An event with no rows reads as not-flowing.
    assert by_name[DIGEST_COMPLAINT]['count'] == 0
    assert by_name[DIGEST_COMPLAINT]['most_recent'] is None
