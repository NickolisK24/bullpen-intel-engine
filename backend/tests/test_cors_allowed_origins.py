"""CORS allowed-origins tests.

The browser frontend calls the backend cross-origin, so the production
frontend domains must be on the backend's CORS allowlist or requests fail with
"Failed to fetch". These tests pin the canonical custom domain and the legacy
Vercel domain as allowed, confirm an unknown origin is not, and confirm the
CORS_ORIGINS env var can add origins without a code change.
"""

import importlib
import os

import pytest


def _make_app(monkeypatch, cors_origins=None):
    monkeypatch.setenv('APP_ENV', 'test')
    if cors_origins is None:
        monkeypatch.delenv('CORS_ORIGINS', raising=False)
    else:
        monkeypatch.setenv('CORS_ORIGINS', cors_origins)
    # create_app reads the (possibly patched) env at call time.
    app_module = importlib.import_module('app')
    return app_module.create_app('test')


def _allow_origin_for(app, origin):
    client = app.test_client()
    resp = client.get('/api/health', headers={'Origin': origin})
    assert resp.status_code == 200
    return resp.headers.get('Access-Control-Allow-Origin')


@pytest.mark.parametrize('origin', [
    'https://baseballos.app',         # canonical custom domain (the fix)
    'https://baseballos.vercel.app',  # legacy domain, kept during transition
    'http://localhost:5173',          # local dev
])
def test_production_and_dev_origins_are_allowed(monkeypatch, origin):
    app = _make_app(monkeypatch)
    assert _allow_origin_for(app, origin) == origin


def test_unknown_origin_is_not_allowed(monkeypatch):
    app = _make_app(monkeypatch)
    assert _allow_origin_for(app, 'https://not-baseballos.example.com') is None


def test_cors_origins_env_var_extends_allowlist(monkeypatch):
    extra = 'https://preview-baseballos.example.com'
    app = _make_app(monkeypatch, cors_origins=extra)
    assert _allow_origin_for(app, extra) == extra
    # The baked-in production domain is still allowed alongside env additions.
    assert _allow_origin_for(app, 'https://baseballos.app') == 'https://baseballos.app'
