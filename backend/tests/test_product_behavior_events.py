"""Product behavior foundation tests (Phase D2A-2).

Verifies the three owned product-behavior events — today_loaded, signed_in,
followed_team_changed — are recorded as immutable facts in the canonical Product
Event log, integrate with the D2A-1 foundation, and change no existing behavior.
"""

from urllib.parse import parse_qs, urlparse

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db
from utils import auth_email
from models.user import User
from models.pitcher import Pitcher
from models.product_event import ProductEvent
from api.auth import auth_bp
from api.me import me_bp
from api.product_events import product_bp
from services.product_events import (
    FOLLOWED_TEAM_CHANGED,
    SIGNED_IN,
    SOURCE_APP,
    SOURCE_DIGEST,
    SOURCE_DIRECT,
    SOURCE_SIGN_IN,
    TODAY_LOADED,
)


VALID_TEAMS = (118, 147, 121)


@pytest.fixture
def app():
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['APP_ENV'] = 'test'
    app.config['USER_AUTH_SECRET'] = 'd2a2-secret'
    app.config['MAGIC_LINK_TTL_SECONDS'] = 900
    app.config['AUTH_TOKEN_TTL_SECONDS'] = 3600
    app.config['FRONTEND_BASE_URL'] = 'http://localhost:5173'
    db.init_app(app)
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(me_bp, url_prefix='/api/me')
    app.register_blueprint(product_bp, url_prefix='/api/product')
    with app.app_context():
        create_test_schema(app)
        auth_email.reset_outbox()
        for idx, team_id in enumerate(VALID_TEAMS):
            db.session.add(Pitcher(
                mlb_id=900000 + idx, full_name=f'Seed Arm {team_id}', team_id=team_id,
                team_name=f'Team {team_id}', team_abbreviation=f'T{team_id}', active=True,
            ))
        db.session.commit()
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


def _magic_token(client, email):
    client.post('/api/auth/request-link', json={'email': email})
    link = auth_email.outbox[-1]['link']
    return parse_qs(urlparse(link).query)['token'][0]


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


def _events(name=None):
    query = ProductEvent.query
    if name is not None:
        query = query.filter_by(event_name=name)
    return query.order_by(ProductEvent.id).all()


# ── today_loaded (owned, anonymous-safe ingestion) ────────────────────────────

def test_today_loaded_anonymous_records_event(app, client):
    resp = client.post('/api/product/today-loaded',
                       json={'team_id': 118, 'source': 'digest', 'anon_id': 'anon-123'})
    assert resp.status_code == 200 and resp.get_json()['ok'] is True
    with app.app_context():
        events = _events(TODAY_LOADED)
        assert len(events) == 1
        ev = events[0]
        assert ev.user_id is None and ev.anon_id == 'anon-123'
        assert ev.team_id == 118 and ev.source == SOURCE_DIGEST


def test_today_loaded_authenticated_sets_user_id(app, client):
    token = _bearer(client, email='auth@example.com')
    resp = client.post('/api/product/today-loaded', json={'team_id': 147},
                       headers=_auth(token))
    assert resp.status_code == 200
    with app.app_context():
        user = User.query.filter_by(email='auth@example.com').one()
        ev = _events(TODAY_LOADED)[-1]
        assert ev.user_id == user.id and ev.team_id == 147
        assert ev.source == SOURCE_DIRECT  # no source supplied -> default


def test_today_loaded_normalizes_unknown_source_and_empty_body(app, client):
    # Unknown source collapses to 'direct'; an empty/garbage body never errors.
    assert client.post('/api/product/today-loaded',
                       json={'source': 'facebook_ad'}).status_code == 200
    assert client.post('/api/product/today-loaded').status_code == 200
    with app.app_context():
        events = _events(TODAY_LOADED)
        assert len(events) == 2
        assert all(ev.source == SOURCE_DIRECT for ev in events)
        assert events[1].team_id is None and events[1].anon_id is None


def test_today_loaded_caps_anon_id_length(app, client):
    client.post('/api/product/today-loaded', json={'anon_id': 'x' * 200})
    with app.app_context():
        assert len(_events(TODAY_LOADED)[0].anon_id) == 64


# ── signed_in (bridge anonymous -> authenticated) ─────────────────────────────

def test_sign_in_records_signed_in_event(app, client):
    _bearer(client, email='newcomer@example.com')
    with app.app_context():
        user = User.query.filter_by(email='newcomer@example.com').one()
        events = _events(SIGNED_IN)
        assert len(events) == 1
        assert events[0].user_id == user.id and events[0].source == SOURCE_SIGN_IN
        assert events[0].payload['new_user'] is True


def test_sign_in_with_anon_id_bridges(app, client):
    token = _magic_token(client, 'bridge@example.com')
    resp = client.post('/api/auth/verify', json={'token': token, 'anon_id': 'anon-xyz'})
    assert resp.status_code == 200
    with app.app_context():
        ev = _events(SIGNED_IN)[-1]
        assert ev.anon_id == 'anon-xyz'  # pre-auth behavior can now be bridged


def test_repeat_sign_in_is_not_new_user(app, client):
    _bearer(client, email='repeat@example.com')          # first sign-in
    second = _magic_token(client, 'repeat@example.com')
    client.post('/api/auth/verify', json={'token': second})  # second sign-in
    with app.app_context():
        events = _events(SIGNED_IN)
        assert len(events) == 2
        assert events[0].payload['new_user'] is True
        assert events[1].payload['new_user'] is False


# ── followed_team_changed (observe preference changes) ─────────────────────────

def test_follow_records_followed_team_changed(app, client):
    token = _bearer(client)
    client.post('/api/me/teams', json={'team_id': 118}, headers=_auth(token))
    with app.app_context():
        events = _events(FOLLOWED_TEAM_CHANGED)
        assert len(events) == 1
        ev = events[0]
        assert ev.team_id == 118 and ev.source == SOURCE_APP
        assert ev.payload['action'] == 'follow'
        assert ev.payload['prior_primary_team_id'] is None
        assert ev.payload['primary_team_id'] == 118  # first follow becomes primary


def test_idempotent_follow_records_single_event(app, client):
    token = _bearer(client)
    client.post('/api/me/teams', json={'team_id': 118}, headers=_auth(token))
    client.post('/api/me/teams', json={'team_id': 118}, headers=_auth(token))  # no-op
    with app.app_context():
        assert len(_events(FOLLOWED_TEAM_CHANGED)) == 1


def test_unfollow_records_event(app, client):
    token = _bearer(client)
    client.post('/api/me/teams', json={'team_id': 118}, headers=_auth(token))
    client.delete('/api/me/teams/118', headers=_auth(token))
    with app.app_context():
        unfollows = [e for e in _events(FOLLOWED_TEAM_CHANGED) if e.payload['action'] == 'unfollow']
        assert len(unfollows) == 1
        assert unfollows[0].payload['prior_primary_team_id'] == 118
        assert unfollows[0].payload['primary_team_id'] is None


def test_set_primary_records_event(app, client):
    token = _bearer(client)
    client.post('/api/me/teams', json={'team_id': 118}, headers=_auth(token))  # primary 118
    client.post('/api/me/teams', json={'team_id': 147}, headers=_auth(token))  # secondary
    client.put('/api/me/primary-team', json={'team_id': 147}, headers=_auth(token))
    with app.app_context():
        set_primaries = [e for e in _events(FOLLOWED_TEAM_CHANGED)
                         if e.payload['action'] == 'set_primary']
        assert len(set_primaries) == 1
        assert set_primaries[0].payload['prior_primary_team_id'] == 118
        assert set_primaries[0].payload['primary_team_id'] == 147


def test_set_primary_to_current_primary_records_no_event(app, client):
    token = _bearer(client)
    client.post('/api/me/teams', json={'team_id': 118}, headers=_auth(token))  # primary 118
    client.put('/api/me/primary-team', json={'team_id': 118}, headers=_auth(token))  # no-op
    with app.app_context():
        # Only the initial follow event exists; the redundant set-primary is a no-op.
        actions = [e.payload['action'] for e in _events(FOLLOWED_TEAM_CHANGED)]
        assert actions == ['follow']


# ── Existing behavior unchanged ───────────────────────────────────────────────

def test_following_response_contract_unchanged(app, client):
    token = _bearer(client)
    body = client.post('/api/me/teams', json={'team_id': 118}, headers=_auth(token)).get_json()
    # The /api/me/teams contract is exactly as before — telemetry is additive only.
    assert body == {'teams': [{'team_id': 118, 'is_primary': True}], 'primary_team_id': 118}
