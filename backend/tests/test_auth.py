"""
Tests for the admin-token guard on operational write endpoints
(backend/utils/auth.py) and the production config requirement.

No database, MLB API, or real sync logic runs here: the guard's reject paths
return before the view body executes, the "allowed" cases use a dummy view,
and the production-config check is exercised directly. Fast and isolated.
"""

import pytest
from flask import Flask, jsonify

from utils.auth import require_admin_token, ADMIN_TOKEN_HEADER


def _build_app(app_env='development', token=None):
    app = Flask(__name__)
    app.config['APP_ENV'] = app_env
    app.config['ADMIN_API_TOKEN'] = token

    @app.route('/protected', methods=['POST'])
    @require_admin_token
    def protected():
        return jsonify({'ok': True})

    return app


class TestRequireAdminToken:
    def test_configured_token_missing_header_is_401(self):
        res = _build_app(token='secret').test_client().post('/protected')
        assert res.status_code == 401
        assert 'error' in res.get_json()

    def test_configured_token_wrong_header_is_401(self):
        res = _build_app(token='secret').test_client().post(
            '/protected', headers={ADMIN_TOKEN_HEADER: 'wrong'})
        assert res.status_code == 401

    def test_configured_token_correct_header_passes(self):
        res = _build_app(token='secret').test_client().post(
            '/protected', headers={ADMIN_TOKEN_HEADER: 'secret'})
        assert res.status_code == 200
        assert res.get_json() == {'ok': True}

    def test_development_without_token_is_allowed(self):
        # Local dev convenience: no token configured → endpoint still works.
        res = _build_app(app_env='development', token=None).test_client().post('/protected')
        assert res.status_code == 200
        assert res.get_json() == {'ok': True}

    def test_production_without_token_is_blocked_at_runtime(self):
        # Defensive: even if a prod app somehow had no token, never expose it.
        res = _build_app(app_env='production', token=None).test_client().post('/protected')
        assert res.status_code == 403


class TestRealRouteWiring:
    """The guard is actually applied to the real write routes (and reads stay open)."""

    def _app(self, monkeypatch):
        from app import create_app
        monkeypatch.setenv('DATABASE_URL', 'sqlite:///:memory:')
        app = create_app('development')
        app.config['ADMIN_API_TOKEN'] = 'secret'   # require a token at runtime
        return app

    def test_sync_requires_token(self, monkeypatch):
        res = self._app(monkeypatch).test_client().post('/api/bullpen/sync')
        assert res.status_code == 401

    def test_recalculate_requires_token(self, monkeypatch):
        res = self._app(monkeypatch).test_client().post('/api/bullpen/fatigue/recalculate')
        assert res.status_code == 401

    def test_public_read_endpoint_needs_no_token(self, monkeypatch):
        # A protected token is configured, yet GET reads remain public.
        res = self._app(monkeypatch).test_client().get('/api/bullpen/sync/status')
        assert res.status_code == 200


class TestProductionConfigRequiresToken:
    def test_init_app_raises_without_admin_token(self, monkeypatch):
        from config import ProductionConfig
        monkeypatch.setenv('DATABASE_URL', 'postgresql://u:p@h/db')

        class FakeApp:
            config = {'SECRET_KEY': 'strong-value', 'ADMIN_API_TOKEN': None}

        with pytest.raises(RuntimeError, match='ADMIN_API_TOKEN'):
            ProductionConfig.init_app(FakeApp())

    def test_init_app_passes_with_full_config(self, monkeypatch):
        from config import ProductionConfig
        monkeypatch.setenv('DATABASE_URL', 'postgresql://u:p@h/db')

        class FakeApp:
            config = {'SECRET_KEY': 'strong-value', 'ADMIN_API_TOKEN': 'admin-secret'}

        # Should not raise.
        ProductionConfig.init_app(FakeApp())
