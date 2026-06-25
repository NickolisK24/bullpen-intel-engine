from datetime import datetime, timedelta

import pytest
from flask import Flask

from models.product_event import ProductEvent
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.auth import ADMIN_TOKEN_HEADER
from utils.db import db


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


def _add_event(
    *,
    event_name='today_loaded',
    minutes_ago=0,
    user_id=None,
    anon_id=None,
    team_id=None,
    source='direct',
    payload=None,
):
    event = ProductEvent(
        event_name=event_name,
        occurred_at=datetime(2026, 6, 24, 12, 0, 0) - timedelta(minutes=minutes_ago),
        user_id=user_id,
        anon_id=anon_id,
        team_id=team_id,
        source=source,
        payload=payload,
    )
    db.session.add(event)
    db.session.commit()
    return event


def test_product_events_admin_endpoint_requires_token(client):
    assert client.get('/api/system/product-events').status_code == 401
    assert client.get(
        '/api/system/product-events',
        headers={ADMIN_TOKEN_HEADER: 'wrong'},
    ).status_code == 401


def test_product_events_admin_endpoint_returns_recent_sanitized_rows(app, client):
    with app.app_context():
        _add_event(
            event_name='today_loaded',
            user_id=7,
            anon_id='anon:client-123',
            team_id=118,
            source='digest',
            payload={'email': 'fan@example.com', 'new_user': True},
        )

    resp = client.get('/api/system/product-events', headers=_headers())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['capability'] == 'product_intelligence_events'
    assert body['limit'] == 25
    assert body['filters'] == {'event_name': None}
    assert len(body['events']) == 1

    row = body['events'][0]
    assert row['event_name'] == 'today_loaded'
    assert row['occurred_at'] == '2026-06-24T12:00:00Z'
    assert row['user_id'] == 7
    assert row['anon_id_present'] is True
    assert 'anon_id' not in row
    assert row['team_id'] == 118
    assert row['source'] == 'digest'
    assert row['payload_summary']['email'] == '[redacted]'
    assert row['payload_summary']['new_user'] is True
    assert 'fan@example.com' not in str(body)


def test_product_events_admin_endpoint_filters_limits_and_orders(app, client):
    with app.app_context():
        _add_event(event_name='today_loaded', minutes_ago=5, team_id=118)
        latest_story = _add_event(
            event_name='story_viewed',
            minutes_ago=1,
            team_id=110,
            source='home',
            payload={'story_id': '110:2026-06-24', 'story_type': 'coverage_pressure'},
        )
        latest_story_id = latest_story.id
        _add_event(event_name='story_viewed', minutes_ago=3, team_id=147, source='stories')

    resp = client.get(
        '/api/system/product-events?event_name=story_viewed&limit=1',
        headers=_headers(),
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['limit'] == 1
    assert body['filters'] == {'event_name': 'story_viewed'}
    assert [row['id'] for row in body['events']] == [latest_story_id]
    assert body['events'][0]['payload_summary'] == {
        'story_id': '110:2026-06-24',
        'story_type': 'coverage_pressure',
    }


def test_product_events_admin_endpoint_clamps_limit(app, client):
    with app.app_context():
        _add_event(event_name='signed_in')

    too_large = client.get('/api/system/product-events?limit=999', headers=_headers())
    invalid = client.get('/api/system/product-events?limit=not-a-number', headers=_headers())

    assert too_large.status_code == 200
    assert too_large.get_json()['limit'] == 100
    assert invalid.status_code == 200
    assert invalid.get_json()['limit'] == 25
