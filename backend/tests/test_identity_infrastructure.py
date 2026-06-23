"""Identity infrastructure tests (Phase D1B).

Foundation only: the User and UserFollowedTeam models, the /api/auth/me contract
(anonymous until D1C), and the auth-utility scaffolding. No authentication flow,
magic link, following API, or frontend behavior is exercised here.
"""

import ast
import glob
import os
import re
from datetime import datetime
from types import SimpleNamespace

import pytest
from flask import Flask
from sqlalchemy.exc import IntegrityError

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db
from utils.identity import (
    anonymous_identity,
    bearer_token,
    identity_for,
    resolve_current_user,
)
from models.user import User, UserFollowedTeam
from api.auth import auth_bp


MIGRATIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'migrations', 'versions',
)
IDENTITY_REVISION = 'c7f3a1e9d2b4'
PRIOR_HEAD = 'a6d4e9c2f1b8'


@pytest.fixture
def app():
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(auth_bp, url_prefix='/api/auth')
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


# ── Schema parity: db.create_all builds the identity tables ───────────────────

def test_identity_tables_exist_after_create_all(app):
    tables = set(db.inspect(db.engine).get_table_names())
    assert 'users' in tables
    assert 'user_followed_teams' in tables


# ── User model ────────────────────────────────────────────────────────────────

def test_user_model_defaults_and_to_dict(app):
    user = User(email='fan@example.com')
    db.session.add(user)
    db.session.commit()

    assert user.id is not None
    assert isinstance(user.created_at, datetime)
    assert user.email_verified_at is None
    assert user.onboarded_at is None
    assert user.notification_prefs is None
    assert user.last_login_at is None

    payload = user.to_dict()
    assert payload['email'] == 'fan@example.com'
    assert payload['email_verified'] is False
    assert payload['onboarded'] is False
    assert payload['followed_teams'] == []


def test_user_email_uniqueness_is_enforced(app):
    db.session.add(User(email='dup@example.com'))
    db.session.commit()
    db.session.add(User(email='dup@example.com'))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


# ── UserFollowedTeam model ────────────────────────────────────────────────────

def test_followed_team_create_and_to_dict(app):
    user = User(email='follow@example.com')
    db.session.add(user)
    db.session.commit()

    follow = UserFollowedTeam(user_id=user.id, team_id=118, is_primary=True)
    db.session.add(follow)
    db.session.commit()

    assert follow.to_dict() == {'team_id': 118, 'is_primary': True}
    assert [t.team_id for t in user.followed_teams] == [118]


def test_followed_team_unique_user_team_pair(app):
    user = User(email='unique@example.com')
    db.session.add(user)
    db.session.commit()

    db.session.add(UserFollowedTeam(user_id=user.id, team_id=118))
    db.session.commit()
    db.session.add(UserFollowedTeam(user_id=user.id, team_id=118))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_same_team_can_be_followed_by_different_users(app):
    a = User(email='a@example.com')
    b = User(email='b@example.com')
    db.session.add_all([a, b])
    db.session.commit()
    db.session.add(UserFollowedTeam(user_id=a.id, team_id=147))
    db.session.add(UserFollowedTeam(user_id=b.id, team_id=147))
    db.session.commit()  # no uniqueness violation across users
    assert UserFollowedTeam.query.filter_by(team_id=147).count() == 2


def test_deleting_user_cascades_followed_teams(app):
    user = User(email='cascade@example.com')
    db.session.add(user)
    db.session.commit()
    db.session.add_all([
        UserFollowedTeam(user_id=user.id, team_id=118),
        UserFollowedTeam(user_id=user.id, team_id=147),
    ])
    db.session.commit()
    assert UserFollowedTeam.query.count() == 2

    db.session.delete(user)
    db.session.commit()
    assert UserFollowedTeam.query.count() == 0


# ── Auth utility scaffolding (no verification yet) ────────────────────────────

def test_bearer_token_extraction():
    assert bearer_token(SimpleNamespace(headers={'Authorization': 'Bearer abc123'})) == 'abc123'
    assert bearer_token(SimpleNamespace(headers={'Authorization': 'Token abc123'})) is None
    assert bearer_token(SimpleNamespace(headers={})) is None
    assert bearer_token(SimpleNamespace(headers={'Authorization': 'Bearer '})) is None


def test_resolve_current_user_is_anonymous_for_an_unverifiable_token(app):
    # D1C verifies bearer tokens, but a bogus/unsigned token still resolves to
    # anonymous (never raises), keeping anonymous-safe endpoints anonymous-safe.
    with app.app_context():
        assert resolve_current_user(
            SimpleNamespace(headers={'Authorization': 'Bearer not-a-signed-token'})
        ) is None


def test_identity_payload_shapes():
    assert anonymous_identity() == {'authenticated': False, 'user': None}
    assert identity_for(None) == {'authenticated': False, 'user': None}
    user = User(email='id@example.com')
    payload = identity_for(user)
    assert payload['authenticated'] is True
    assert payload['user']['email'] == 'id@example.com'


# ── GET /api/auth/me ──────────────────────────────────────────────────────────

def test_auth_me_returns_anonymous_without_auth(client):
    resp = client.get('/api/auth/me')
    assert resp.status_code == 200
    assert resp.get_json() == {'authenticated': False, 'user': None}


def test_auth_me_treats_an_invalid_bearer_as_anonymous(client):
    # A bogus bearer token must never authenticate; /api/auth/me stays anonymous.
    resp = client.get('/api/auth/me', headers={'Authorization': 'Bearer anything'})
    assert resp.status_code == 200
    assert resp.get_json()['authenticated'] is False


# ── Migration integrity (static; tests build schema via create_all) ───────────

def _migration_file():
    matches = glob.glob(os.path.join(MIGRATIONS_DIR, f'{IDENTITY_REVISION}_*.py'))
    assert len(matches) == 1, matches
    return matches[0]


def test_identity_migration_is_well_formed_and_chains_off_prior_head():
    source = open(_migration_file()).read()
    ast.parse(source)  # parses cleanly
    assert f"revision = '{IDENTITY_REVISION}'" in source
    assert f"down_revision = '{PRIOR_HEAD}'" in source
    assert 'def upgrade' in source and 'def downgrade' in source
    for token in ("'users'", "'user_followed_teams'", 'uq_user_followed_teams_user_team',
                  'ix_users_email'):
        assert token in source, token


def test_migrations_have_a_single_linear_head():
    # The migration history must stay linear (exactly one head, no divergent
    # branches). The identity migration remains part of that chain; later phases
    # (e.g. digest metrics) extend it, advancing the head past identity.
    revisions = {}
    for path in glob.glob(os.path.join(MIGRATIONS_DIR, '*.py')):
        text = open(path).read()
        rev = re.search(r"^revision\s*=\s*['\"]([^'\"]+)", text, re.M)
        down = re.search(r"^down_revision\s*=\s*['\"]?([^'\"\n]+)", text, re.M)
        if rev:
            revisions[rev.group(1)] = (down.group(1).strip() if down else None)
    referenced = {d for d in revisions.values() if d and d != 'None'}
    heads = set(revisions) - referenced
    assert len(heads) == 1, f'expected a single alembic head, found: {heads}'
    assert IDENTITY_REVISION in revisions
