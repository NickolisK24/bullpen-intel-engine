"""Server-side team following tests (Phase D1D).

Authenticated users can durably follow teams via /api/me/*; unauthenticated
requests are blocked there only, public endpoints stay anonymous-compatible, and
the primary-team rule is deterministic (first follow primary; one primary;
deleting primary promotes the earliest remaining or clears it).
"""

from urllib.parse import parse_qs, urlparse

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db
from utils import auth_email
from models.user import User, UserFollowedTeam
from models.pitcher import Pitcher
from api.auth import auth_bp
from api.me import me_bp
from api.bullpen import bullpen_bp


VALID_TEAMS = (118, 147, 121)
INVALID_TEAM = 999


@pytest.fixture
def app():
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['APP_ENV'] = 'test'
    app.config['USER_AUTH_SECRET'] = 'follow-test-secret'
    app.config['MAGIC_LINK_TTL_SECONDS'] = 900
    app.config['AUTH_TOKEN_TTL_SECONDS'] = 3600
    app.config['FRONTEND_BASE_URL'] = 'http://localhost:5173'
    db.init_app(app)
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(me_bp, url_prefix='/api/me')
    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    with app.app_context():
        create_test_schema(app)
        auth_email.reset_outbox()
        for idx, team_id in enumerate(VALID_TEAMS):
            db.session.add(Pitcher(
                mlb_id=900000 + idx,
                full_name=f'Seed Arm {team_id}',
                team_id=team_id,
                team_name=f'Team {team_id}',
                team_abbreviation=f'T{team_id}',
                active=True,
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


def _bearer(client, email='follower@example.com'):
    client.post('/api/auth/request-link', json={'email': email})
    link = auth_email.outbox[-1]['link']
    token = parse_qs(urlparse(link).query)['token'][0]
    return client.post('/api/auth/verify', json={'token': token}).get_json()['token']


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


def _primaries(body):
    return [t for t in body['teams'] if t['is_primary']]


# ── Auth gating ───────────────────────────────────────────────────────────────

def test_me_teams_requires_authentication(client):
    for method, kwargs in (
        ('get', {}),
        ('post', {'json': {'team_id': 118}}),
        ('delete', {}),
        ('put', {'json': {'team_id': 118}}),
    ):
        path = '/api/me/teams/118' if method == 'delete' else (
            '/api/me/primary-team' if method == 'put' else '/api/me/teams')
        resp = getattr(client, method)(path, **kwargs)
        assert resp.status_code == 401, (method, path)
        assert resp.get_json()['error'] == 'authentication_required'


def test_me_teams_rejects_invalid_bearer(client):
    resp = client.get('/api/me/teams', headers=_auth('not-a-real-token'))
    assert resp.status_code == 401


# ── Listing / following ───────────────────────────────────────────────────────

def test_authenticated_user_lists_empty_follows(client):
    token = _bearer(client)
    resp = client.get('/api/me/teams', headers=_auth(token))
    assert resp.status_code == 200
    assert resp.get_json() == {'teams': [], 'primary_team_id': None}


def test_first_follow_becomes_primary(client):
    token = _bearer(client)
    body = client.post('/api/me/teams', json={'team_id': 118}, headers=_auth(token)).get_json()
    assert [t['team_id'] for t in body['teams']] == [118]
    assert body['primary_team_id'] == 118


def test_duplicate_follow_is_idempotent(client):
    token = _bearer(client)
    client.post('/api/me/teams', json={'team_id': 118}, headers=_auth(token))
    body = client.post('/api/me/teams', json={'team_id': 118}, headers=_auth(token)).get_json()
    assert [t['team_id'] for t in body['teams']] == [118]
    assert len(_primaries(body)) == 1


def test_invalid_team_id_is_rejected(client):
    token = _bearer(client)
    assert client.post('/api/me/teams', json={'team_id': INVALID_TEAM},
                       headers=_auth(token)).status_code == 400
    assert client.post('/api/me/teams', json={'team_id': 'abc'},
                       headers=_auth(token)).status_code == 400
    assert client.post('/api/me/teams', json={},
                       headers=_auth(token)).status_code == 400


def test_second_follow_does_not_change_primary_unless_requested(client):
    token = _bearer(client)
    client.post('/api/me/teams', json={'team_id': 118}, headers=_auth(token))
    body = client.post('/api/me/teams', json={'team_id': 147}, headers=_auth(token)).get_json()
    assert sorted(t['team_id'] for t in body['teams']) == [118, 147]
    assert body['primary_team_id'] == 118
    assert len(_primaries(body)) == 1


def test_following_with_is_primary_moves_primary(client):
    token = _bearer(client)
    client.post('/api/me/teams', json={'team_id': 118}, headers=_auth(token))
    body = client.post('/api/me/teams', json={'team_id': 147, 'is_primary': True},
                       headers=_auth(token)).get_json()
    assert body['primary_team_id'] == 147
    assert len(_primaries(body)) == 1


# ── Primary-team management ───────────────────────────────────────────────────

def test_put_primary_team_for_followed_team(client):
    token = _bearer(client)
    client.post('/api/me/teams', json={'team_id': 118}, headers=_auth(token))
    client.post('/api/me/teams', json={'team_id': 147}, headers=_auth(token))
    body = client.put('/api/me/primary-team', json={'team_id': 147},
                      headers=_auth(token)).get_json()
    assert body['primary_team_id'] == 147
    assert len(_primaries(body)) == 1


def test_put_primary_team_follows_then_sets_when_not_followed(client):
    token = _bearer(client)
    body = client.put('/api/me/primary-team', json={'team_id': 121},
                      headers=_auth(token)).get_json()
    assert [t['team_id'] for t in body['teams']] == [121]
    assert body['primary_team_id'] == 121


def test_put_primary_rejects_invalid_team(client):
    token = _bearer(client)
    assert client.put('/api/me/primary-team', json={'team_id': INVALID_TEAM},
                      headers=_auth(token)).status_code == 400


# ── Unfollowing ───────────────────────────────────────────────────────────────

def test_delete_non_primary_keeps_primary(client):
    token = _bearer(client)
    client.post('/api/me/teams', json={'team_id': 118}, headers=_auth(token))   # primary
    client.post('/api/me/teams', json={'team_id': 147}, headers=_auth(token))
    body = client.delete('/api/me/teams/147', headers=_auth(token)).get_json()
    assert [t['team_id'] for t in body['teams']] == [118]
    assert body['primary_team_id'] == 118


def test_delete_primary_promotes_earliest_remaining(client):
    token = _bearer(client)
    client.post('/api/me/teams', json={'team_id': 118}, headers=_auth(token))   # primary, oldest
    client.post('/api/me/teams', json={'team_id': 147}, headers=_auth(token))
    client.post('/api/me/teams', json={'team_id': 121}, headers=_auth(token))
    body = client.delete('/api/me/teams/118', headers=_auth(token)).get_json()
    assert body['primary_team_id'] == 147  # earliest remaining
    assert len(_primaries(body)) == 1


def test_delete_last_team_clears_primary(client):
    token = _bearer(client)
    client.post('/api/me/teams', json={'team_id': 118}, headers=_auth(token))
    body = client.delete('/api/me/teams/118', headers=_auth(token)).get_json()
    assert body['teams'] == []
    assert body['primary_team_id'] is None


def test_delete_not_followed_team_is_idempotent(client):
    token = _bearer(client)
    client.post('/api/me/teams', json={'team_id': 118}, headers=_auth(token))
    body = client.delete('/api/me/teams/147', headers=_auth(token)).get_json()
    assert [t['team_id'] for t in body['teams']] == [118]
    assert body['primary_team_id'] == 118


def test_exactly_one_primary_invariant_holds_across_operations(client):
    token = _bearer(client)
    for team_id in VALID_TEAMS:
        body = client.post('/api/me/teams', json={'team_id': team_id},
                           headers=_auth(token)).get_json()
        assert len(_primaries(body)) == 1
    client.put('/api/me/primary-team', json={'team_id': 121}, headers=_auth(token))
    body = client.delete('/api/me/teams/121', headers=_auth(token)).get_json()
    assert len(_primaries(body)) == 1  # still exactly one after deleting the primary


# ── /api/auth/me includes following; persistence; anonymous compatibility ─────

def test_auth_me_includes_followed_teams_and_primary(client):
    token = _bearer(client, 'whoami@example.com')
    client.post('/api/me/teams', json={'team_id': 147}, headers=_auth(token))
    me = client.get('/api/auth/me', headers=_auth(token)).get_json()
    assert me['authenticated'] is True
    assert me['user']['primary_team_id'] == 147
    assert [t['team_id'] for t in me['user']['followed_teams']] == [147]


def test_following_persists_in_db(client, app):
    token = _bearer(client, 'persist@example.com')
    client.post('/api/me/teams', json={'team_id': 118}, headers=_auth(token))
    with app.app_context():
        user = User.query.filter_by(email='persist@example.com').first()
        rows = UserFollowedTeam.query.filter_by(user_id=user.id).all()
        assert [(r.team_id, r.is_primary) for r in rows] == [(118, True)]


def test_public_endpoint_remains_anonymous_compatible(client):
    resp = client.get('/api/bullpen/teams')
    assert resp.status_code == 200
    assert any(t['team_id'] == 118 for t in resp.get_json())
