"""Magic-link authentication tests (Phase D1C).

Covers stateless, passwordless auth: request-link (generic, normalizing,
account-creating), verify (token -> bearer, sets verification), bearer-token
resolution on /api/auth/me, safe rejection of invalid/expired/cross-purpose
tokens, logout, and that existing routes stay anonymous-compatible. No sign-in
UI, following API, notifications, or onboarding are exercised.
"""

from urllib.parse import parse_qs, urlparse

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db
from utils import auth_email
from utils.auth_tokens import (
    generate_magic_link_token,
    normalize_email,
    verify_bearer_token,
    verify_magic_link_token,
)
from models.user import User
import models.pitcher  # noqa: F401  (registered so create_all builds it for the compat check)
from api.auth import auth_bp
from api.bullpen import bullpen_bp


@pytest.fixture
def app():
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['APP_ENV'] = 'test'
    app.config['USER_AUTH_SECRET'] = 'unit-test-secret'
    app.config['MAGIC_LINK_TTL_SECONDS'] = 900
    app.config['AUTH_TOKEN_TTL_SECONDS'] = 3600
    app.config['FRONTEND_BASE_URL'] = 'http://localhost:5173'
    db.init_app(app)
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
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


def _token_from_outbox():
    assert auth_email.outbox, 'expected a magic-link email to be captured'
    link = auth_email.outbox[-1]['link']
    return parse_qs(urlparse(link).query).get('token', [None])[0]


def _sign_in(client, email='fan@example.com'):
    client.post('/api/auth/request-link', json={'email': email})
    token = _token_from_outbox()
    resp = client.post('/api/auth/verify', json={'token': token})
    assert resp.status_code == 200
    return resp.get_json()['token']


# ── request-link ──────────────────────────────────────────────────────────────

def test_request_link_normalizes_email_and_creates_user(client, app):
    resp = client.post('/api/auth/request-link', json={'email': '  Fan@Example.COM '})
    assert resp.status_code == 200
    assert resp.get_json()['ok'] is True
    with app.app_context():
        assert User.query.filter_by(email='fan@example.com').count() == 1
    assert auth_email.outbox[-1]['email'] == 'fan@example.com'


def test_request_link_returns_generic_success_and_never_returns_token(client):
    resp = client.post('/api/auth/request-link', json={'email': 'someone@example.com'})
    body = resp.get_json()
    assert body == {'ok': True, 'message': body['message']}  # only ok + message
    assert 'token' not in body and 'link' not in body


def test_request_link_invalid_email_is_generic_and_creates_nothing(client, app):
    resp = client.post('/api/auth/request-link', json={'email': 'not-an-email'})
    assert resp.status_code == 200
    assert resp.get_json()['ok'] is True
    with app.app_context():
        assert User.query.count() == 0
    assert auth_email.outbox == []  # no email sent for an unusable address


def test_request_link_is_idempotent_for_same_email(client, app):
    client.post('/api/auth/request-link', json={'email': 'dup@example.com'})
    client.post('/api/auth/request-link', json={'email': 'dup@example.com'})
    with app.app_context():
        assert User.query.filter_by(email='dup@example.com').count() == 1


# ── verify ──────────────────────────────────────────────────────────────────

def test_verify_valid_token_returns_bearer_and_user(client):
    client.post('/api/auth/request-link', json={'email': 'verify@example.com'})
    resp = client.post('/api/auth/verify', json={'token': _token_from_outbox()})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['token']
    assert body['user']['email'] == 'verify@example.com'
    assert body['user']['email_verified'] is True


def test_verify_sets_email_verified_and_last_login(client, app):
    client.post('/api/auth/request-link', json={'email': 'stamp@example.com'})
    client.post('/api/auth/verify', json={'token': _token_from_outbox()})
    with app.app_context():
        user = User.query.filter_by(email='stamp@example.com').first()
        assert user.email_verified_at is not None
        assert user.last_login_at is not None


def test_verify_invalid_token_is_rejected(client):
    resp = client.post('/api/auth/verify', json={'token': 'garbage.token.value'})
    assert resp.status_code == 401
    assert resp.get_json()['error'] == 'invalid_or_expired_token'


def test_verify_expired_token_is_rejected(client):
    client.post('/api/auth/request-link', json={'email': 'expired@example.com'})
    token = _token_from_outbox()
    client.application.config['MAGIC_LINK_TTL_SECONDS'] = -1  # any token now reads expired
    resp = client.post('/api/auth/verify', json={'token': token})
    assert resp.status_code == 401


# ── /api/auth/me ──────────────────────────────────────────────────────────────

def test_me_anonymous_without_token(client):
    resp = client.get('/api/auth/me')
    assert resp.status_code == 200
    assert resp.get_json() == {'authenticated': False, 'user': None}


def test_me_resolves_authenticated_user_with_bearer(client):
    bearer = _sign_in(client, 'me@example.com')
    resp = client.get('/api/auth/me', headers={'Authorization': f'Bearer {bearer}'})
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['authenticated'] is True
    assert body['user']['email'] == 'me@example.com'


def test_me_with_invalid_bearer_stays_anonymous(client):
    resp = client.get('/api/auth/me', headers={'Authorization': 'Bearer not-a-real-token'})
    assert resp.status_code == 200
    assert resp.get_json()['authenticated'] is False


# ── Token purpose separation (cross-purpose tokens rejected) ──────────────────

def test_magic_link_token_is_not_accepted_as_bearer(client):
    client.post('/api/auth/request-link', json={'email': 'cross@example.com'})
    magic = _token_from_outbox()
    resp = client.get('/api/auth/me', headers={'Authorization': f'Bearer {magic}'})
    assert resp.get_json()['authenticated'] is False


def test_bearer_token_is_not_accepted_as_magic_link(client):
    bearer = _sign_in(client, 'cross2@example.com')
    resp = client.post('/api/auth/verify', json={'token': bearer})
    assert resp.status_code == 401


# ── logout ────────────────────────────────────────────────────────────────────

def test_logout_returns_success(client):
    resp = client.post('/api/auth/logout')
    assert resp.status_code == 200
    assert resp.get_json()['ok'] is True


# ── Token utilities ───────────────────────────────────────────────────────────

def test_token_utilities_roundtrip_and_expiry(app):
    with app.app_context():
        magic = generate_magic_link_token('u@example.com')
        assert verify_magic_link_token(magic) == 'u@example.com'
        assert verify_magic_link_token(magic, max_age=-1) is None  # expired
        assert verify_magic_link_token('bad') is None

        user = User(email='b@example.com')
        db.session.add(user)
        db.session.commit()
        bearer = generate_bearer_token_for(user)
        claims = verify_bearer_token(bearer)
        assert claims['uid'] == user.id and claims['email'] == 'b@example.com'
        assert verify_bearer_token(bearer, max_age=-1) is None


def generate_bearer_token_for(user):
    from utils.auth_tokens import generate_bearer_token
    return generate_bearer_token(user)


def test_normalize_email_rules():
    assert normalize_email('  A@B.com ') == 'a@b.com'
    assert normalize_email('no-at-sign') is None
    assert normalize_email('a@b') is None  # no domain dot
    assert normalize_email('a b@c.com') is None  # space
    assert normalize_email(None) is None


# ── No passwords / no sessions table; existing routes anonymous-compatible ────

def test_no_password_or_session_tables_added(app):
    with app.app_context():
        tables = set(db.inspect(db.engine).get_table_names())
    assert 'users' in tables and 'user_followed_teams' in tables
    assert 'sessions' not in tables and 'passwords' not in tables
    user_columns = {c.name for c in User.__table__.columns}
    assert not any('password' in c for c in user_columns)


def test_existing_routes_remain_anonymous_compatible(client):
    # An existing public endpoint still serves anonymously with auth registered.
    resp = client.get('/api/bullpen/teams')
    assert resp.status_code == 200
