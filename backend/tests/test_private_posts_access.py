import pytest
from flask import Flask

from api.private_posts import private_posts_bp
from models.user import User
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.auth_tokens import generate_bearer_token
from utils.db import db
from utils.time import utc_now_naive


@pytest.fixture
def app():
    app = Flask(__name__)
    configure_test_database(app)
    app.config['APP_ENV'] = 'test'
    app.config['USER_AUTH_SECRET'] = 'private-posts-test-secret'
    app.config['AUTH_TOKEN_TTL_SECONDS'] = 3600
    app.config['PRIVATE_POSTING_BOARD_ALLOWED_EMAILS'] = 'owner@example.com'
    db.init_app(app)
    app.register_blueprint(private_posts_bp, url_prefix='/api/private-posts')
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


def _bearer(app, email):
    with app.app_context():
        user = User(
            email=email,
            email_verified_at=utc_now_naive(),
            last_login_at=utc_now_naive(),
        )
        db.session.add(user)
        db.session.commit()
        return generate_bearer_token(user)


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


def test_private_posts_dashboard_requires_authentication(client, monkeypatch):
    monkeypatch.setattr(
        'api.private_posts.bullpen_dashboard_response_payload',
        lambda: {'unexpected': True},
    )

    response = client.get('/api/private-posts/dashboard')

    assert response.status_code == 401
    assert response.get_json() == {'error': 'authentication_required'}


def test_private_posts_dashboard_rejects_authenticated_user_outside_allowlist(
    app,
    client,
    monkeypatch,
):
    monkeypatch.setattr(
        'api.private_posts.bullpen_dashboard_response_payload',
        lambda: {'unexpected': True},
    )
    token = _bearer(app, 'reader@example.com')

    response = client.get('/api/private-posts/dashboard', headers=_auth(token))

    assert response.status_code == 403
    assert response.get_json() == {'error': 'posting_board_forbidden'}


def test_private_posts_dashboard_allows_authorized_user(app, client, monkeypatch):
    monkeypatch.setattr(
        'api.private_posts.bullpen_dashboard_response_payload',
        lambda: {
            'capability': 'bullpen_dashboard',
            'stories': {'items': []},
            'ranking_applied': False,
            'selection_made': False,
        },
    )
    token = _bearer(app, 'OWNER@EXAMPLE.COM')

    response = client.get('/api/private-posts/dashboard', headers=_auth(token))

    assert response.status_code == 200
    assert response.get_json() == {
        'capability': 'bullpen_dashboard',
        'stories': {'items': []},
        'ranking_applied': False,
        'selection_made': False,
    }


def test_private_posts_dashboard_fails_closed_without_allowlist(app, client):
    app.config['PRIVATE_POSTING_BOARD_ALLOWED_EMAILS'] = ''
    token = _bearer(app, 'owner@example.com')

    response = client.get('/api/private-posts/dashboard', headers=_auth(token))

    assert response.status_code == 403
    assert response.get_json() == {'error': 'posting_board_forbidden'}


def test_private_posts_dashboard_is_registered_on_real_app(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')

    from app import create_app

    real_app = create_app('development')
    response = real_app.test_client().get('/api/private-posts/dashboard')

    assert response.status_code == 401
    assert response.get_json() == {'error': 'authentication_required'}
