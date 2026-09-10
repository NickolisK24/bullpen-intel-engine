"""Tests for the browser-safe authenticated Share Artifact operations endpoints
(Share Cards SC-03B-03B).

Proves the operator page's read endpoints reuse the existing browser-safe internal
gate (signed-in user Bearer session + founder email allowlist) — never the admin
token — while sharing the exact SC-03B-03A operational read service, validation,
and vocabulary. Read-only, fail-closed, sanitized, no-store.
"""

from types import SimpleNamespace

import pytest
from flask import Flask

from models.share_artifact import ShareArtifact
from services.team_state_payload import TEAM_STATE_ARTIFACT_TYPE
from tests.test_share_artifact_batch_generation import (
    PRODUCT_DATE,
    SNAPSHOT_ID,
    _install_snapshot,
    _seed_teams,
)
from tests.test_share_artifact_operations import _audit, _generate
from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)
from utils.db import db

import api.share_artifact_operations_browser as browser_api


FOUNDER = SimpleNamespace(id=1, email=' FOUNDER@example.com ')  # allowlisted (normalized)
FAN = SimpleNamespace(id=2, email='fan@example.com')            # not allowlisted

BROWSER = '/api/internal-browser/share-artifacts/operations'
ADMIN = '/api/internal/share-artifacts/operations'


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['APP_ENV'] = 'test'
    flask_app.config['ADMIN_API_TOKEN'] = 'admin-secret'
    flask_app.config['TRAFFIC_INTERNAL_EMAILS'] = 'founder@example.com'
    flask_app.config['SHARE_ARTIFACT_AUTOGENERATION_ENABLED'] = True
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


@pytest.fixture
def client(app):
    from api.share_artifact_operations_browser import share_artifact_operations_browser_bp
    from api.share_artifacts_admin import share_artifacts_admin_bp
    app.register_blueprint(
        share_artifact_operations_browser_bp,
        url_prefix='/api/internal-browser/share-artifacts',
    )
    app.register_blueprint(
        share_artifacts_admin_bp, url_prefix='/api/internal/share-artifacts',
    )
    return app.test_client()


def _as_user(monkeypatch, user):
    monkeypatch.setattr(browser_api, 'resolve_current_user', lambda *a, **k: user)


def _populate():
    _seed_teams((101, 102))
    _install_snapshot_default = None
    _generate(101)  # one real published artifact + audit
    _audit(102, 'refused', blocking=('data_limited',))


# 3 — unauthenticated request is denied (fail closed).
def test_unauthenticated_denied(client, monkeypatch):
    _as_user(monkeypatch, None)
    for path in ('overview', 'artifacts', 'audits'):
        resp = client.get(f'{BROWSER}/{path}')
        assert resp.status_code == 401
        assert resp.get_json()['error'] == 'authentication_required'


# 4 — authenticated but unauthorized (not on the allowlist) is denied.
def test_authenticated_but_unauthorized_denied(client, monkeypatch):
    _as_user(monkeypatch, FAN)
    for path in ('overview', 'artifacts', 'audits'):
        resp = client.get(f'{BROWSER}/{path}')
        assert resp.status_code == 403
        assert resp.get_json()['error'] == 'operations_forbidden'


# 2 / 6 / 8 — authorized founder reads the overview; no admin token needed.
def test_authorized_founder_reads_overview(client, monkeypatch):
    _install_snapshot(monkeypatch)
    _populate()
    _as_user(monkeypatch, FOUNDER)
    resp = client.get(f'{BROWSER}/overview')  # no X-Admin-Token header
    assert resp.status_code == 200
    body = resp.get_json()
    # Same view-model contract as the SC-03B-03A service.
    for key in ('status', 'canonical_team_count', 'accounted_team_count',
                'generated_team_count', 'missing_team_count', 'autogeneration_enabled', 'teams'):
        assert key in body
    assert body['canonical_team_count'] == body['accounted_team_count'] + body['missing_team_count']


# 9 — browser + admin boundaries return identical payloads (shared service, no dup).
def test_browser_and_admin_return_identical_overview(client, monkeypatch):
    _install_snapshot(monkeypatch)
    _populate()
    _as_user(monkeypatch, FOUNDER)
    browser_body = client.get(f'{BROWSER}/overview').get_json()
    admin_body = client.get(f'{ADMIN}/overview', headers={'X-Admin-Token': 'admin-secret'}).get_json()
    assert browser_body == admin_body


# 16 — authenticated responses are no-store / private (never publicly cached).
def test_authenticated_responses_are_no_store(client, monkeypatch):
    _install_snapshot(monkeypatch)
    _as_user(monkeypatch, FOUNDER)
    for path in ('overview', 'artifacts', 'audits'):
        resp = client.get(f'{BROWSER}/{path}')
        assert resp.status_code == 200
        assert 'no-store' in resp.headers.get('Cache-Control', '')


# 10 / 11 / 12 — read-only: GET only, no generation, no mutation.
def test_endpoints_are_read_only(app, client, monkeypatch):
    _install_snapshot(monkeypatch)
    _populate()
    before = ShareArtifact.query.filter(
        ShareArtifact.artifact_type == TEAM_STATE_ARTIFACT_TYPE
    ).count()
    _as_user(monkeypatch, FOUNDER)
    # No mutation methods exist on the browser routes.
    assert client.post(f'{BROWSER}/overview').status_code == 405
    assert client.delete(f'{BROWSER}/artifacts').status_code == 405
    # Reads never create artifacts.
    client.get(f'{BROWSER}/overview')
    client.get(f'{BROWSER}/artifacts')
    after = ShareArtifact.query.filter(
        ShareArtifact.artifact_type == TEAM_STATE_ARTIFACT_TYPE
    ).count()
    assert before == after


# 13 — raw payload JSON is not returned in the artifact list.
def test_no_raw_payload_in_artifact_list(client, monkeypatch):
    _install_snapshot(monkeypatch)
    _populate()
    _as_user(monkeypatch, FOUNDER)
    body = client.get(f'{BROWSER}/artifacts').get_json()
    for row in body['artifacts']:
        assert 'payload' not in row


# 15 — pagination/filter validation is preserved from SC-03B-03A.
def test_validation_preserved(client, monkeypatch):
    _install_snapshot(monkeypatch)
    _as_user(monkeypatch, FOUNDER)
    assert client.get(f'{BROWSER}/artifacts?limit=abc').status_code == 400
    assert client.get(f'{BROWSER}/audits?outcome=bogus').status_code == 400
    assert client.get(f'{BROWSER}/audits?product_date=nope').status_code == 400
    # A valid clamp still succeeds.
    ok = client.get(f'{BROWSER}/artifacts?limit=99999')
    assert ok.status_code == 200 and ok.get_json()['limit'] == 100


# 14 — errors are sanitized (no stack traces / raw exceptions).
def test_errors_are_sanitized(client, monkeypatch):
    _install_snapshot(monkeypatch)
    _as_user(monkeypatch, FOUNDER)
    import services.share_artifact_operations as ops

    def _boom():
        raise RuntimeError('kaboom secret internals')

    monkeypatch.setattr(
        'api.share_artifact_operations_api.build_coverage_overview', _boom, raising=False,
    )
    # Force the service to raise inside the shared builder path.
    monkeypatch.setattr(ops, 'build_coverage_overview', _boom)
    resp = client.get(f'{BROWSER}/overview')
    assert resp.status_code == 503
    assert resp.get_json() == {'error': 'internal_error'}


# 6 / 7 — no X-Admin-Token is required from the browser; the dedicated allowlist
# override also works.
def test_dedicated_allowlist_override(app, client, monkeypatch):
    app.config['SHARE_ARTIFACT_OPERATIONS_EMAILS'] = 'ops@example.com'
    _install_snapshot(monkeypatch)
    # The founder (only on TRAFFIC_INTERNAL_EMAILS) is now NOT authorized...
    _as_user(monkeypatch, FOUNDER)
    assert client.get(f'{BROWSER}/overview').status_code == 403
    # ...but the dedicated ops email is.
    _as_user(monkeypatch, SimpleNamespace(id=3, email='ops@example.com'))
    assert client.get(f'{BROWSER}/overview').status_code == 200


# 17 / 18 — no public route; admin-token endpoints remain protected + unchanged.
def test_no_public_route_and_admin_still_protected(client, monkeypatch):
    _install_snapshot(monkeypatch)
    _as_user(monkeypatch, FOUNDER)
    # Browser boundary is internal.
    assert client.get(f'{BROWSER}/overview').status_code == 200
    # Admin boundary still requires the admin token (browser session does not help it).
    assert client.get(f'{ADMIN}/overview').status_code == 401
    assert client.get(f'{ADMIN}/overview', headers={'X-Admin-Token': 'admin-secret'}).status_code == 200


# The browser module never imports/uses the admin token.
def test_browser_module_has_no_admin_token():
    from pathlib import Path
    src = Path(browser_api.__file__).read_text(encoding='utf-8')
    assert 'ADMIN_API_TOKEN' not in src
    assert 'X-Admin-Token' not in src
    assert 'require_admin_token' not in src
