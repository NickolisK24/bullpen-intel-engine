import importlib
import os

import pytest


class FakeApp:
    def __init__(self, app_env='development'):
        self.config = {
            'APP_ENV': app_env,
            'SECRET_KEY': 'strong-value',
            'ADMIN_API_TOKEN': 'admin-secret',
        }


def test_development_config_requires_explicit_database_url(monkeypatch):
    from config import DevelopmentConfig

    monkeypatch.delenv('DATABASE_URL', raising=False)
    app = FakeApp('development')

    with pytest.raises(RuntimeError, match='DATABASE_URL is not set'):
        DevelopmentConfig.init_app(app)


def test_development_config_rejects_non_local_database_url(monkeypatch):
    from config import DevelopmentConfig

    monkeypatch.setenv('DATABASE_URL', 'postgresql://user:pass@db.example.com/baseballos')
    app = FakeApp('development')

    with pytest.raises(RuntimeError, match='local database'):
        DevelopmentConfig.init_app(app)


def test_development_config_accepts_explicit_local_database_url(monkeypatch):
    from config import DevelopmentConfig

    monkeypatch.setenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/baseballos')
    app = FakeApp('development')

    DevelopmentConfig.init_app(app)

    assert app.config['SQLALCHEMY_DATABASE_URI'] == (
        'postgresql://postgres:postgres@localhost:5432/baseballos'
    )


def test_testing_config_uses_disposable_test_database_url(monkeypatch):
    from config import TestingConfig

    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.setenv('TEST_DATABASE_URL', 'sqlite:///:memory:')
    app = FakeApp('test')

    TestingConfig.init_app(app)

    assert app.config['SQLALCHEMY_DATABASE_URI'] == 'sqlite:///:memory:'


def test_testing_config_requires_explicit_test_database_url(monkeypatch):
    from config import TestingConfig

    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.delenv('TEST_DATABASE_URL', raising=False)
    app = FakeApp('test')

    with pytest.raises(RuntimeError, match='DATABASE_URL is not set'):
        TestingConfig.init_app(app)


def test_production_config_accepts_explicit_remote_database_url(monkeypatch):
    from config import ProductionConfig

    monkeypatch.setenv('DATABASE_URL', 'postgresql://user:pass@db.example.com/baseballos')
    app = FakeApp('production')

    ProductionConfig.init_app(app)

    assert app.config['SQLALCHEMY_DATABASE_URI'] == (
        'postgresql://user:pass@db.example.com/baseballos'
    )


def _reload_config_with_env(public, backend):
    """Reload the config module with the two origin vars set/cleared.

    PUBLIC_API_BASE_URL is resolved at class-definition time, so the env must be
    in place before the module is (re)imported. Caller is responsible for
    restoring the environment and reloading once more.
    """
    import config as config_module

    for name, value in (('PUBLIC_API_BASE_URL', public), ('BACKEND_BASE_URL', backend)):
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
    return importlib.reload(config_module).Config


def test_public_api_base_url_falls_back_to_backend_base_url():
    """Regression: the backend public origin must resolve from BACKEND_BASE_URL
    when PUBLIC_API_BASE_URL is unset.

    The operator sets BACKEND_BASE_URL on the host; the tracking/unsubscribe URL
    builders read PUBLIC_API_BASE_URL. Without this fallback that key is empty
    and the email's open/click links become host-less, which mail clients render
    as the invalid http:///api/digest/click. PUBLIC_API_BASE_URL still wins when
    both are present.
    """
    saved_public = os.environ.get('PUBLIC_API_BASE_URL')
    saved_backend = os.environ.get('BACKEND_BASE_URL')
    try:
        cfg = _reload_config_with_env(None, 'https://baseballos-api.onrender.com')
        assert cfg.PUBLIC_API_BASE_URL == 'https://baseballos-api.onrender.com'

        cfg = _reload_config_with_env('https://api.example.com', 'https://baseballos-api.onrender.com')
        assert cfg.PUBLIC_API_BASE_URL == 'https://api.example.com'

        cfg = _reload_config_with_env(None, None)
        assert cfg.PUBLIC_API_BASE_URL == ''
    finally:
        _reload_config_with_env(saved_public, saved_backend)


# ── SQLAlchemy engine options (stale-connection hardening) ────────────────────

def test_engine_options_for_postgres_url_harden_pool():
    """Postgres connections get pre-ping, recycle, and bounded timeouts so a
    stale/dead Render connection is detected before use and a stuck query fails
    fast instead of hanging a worker to SIGKILL."""
    from config import _engine_options_for_url

    opts = _engine_options_for_url(
        'postgresql://u:p@db.example.com:5432/baseballos')
    assert opts['pool_pre_ping'] is True
    assert opts['pool_recycle'] == 300
    assert opts['pool_timeout'] == 30
    connect_args = opts['connect_args']
    assert connect_args['connect_timeout'] == 10
    assert connect_args['options'] == '-c statement_timeout=15000'
    assert connect_args['keepalives'] == 1


def test_engine_options_for_sqlite_url_are_empty():
    """SQLite (local/test) keeps the default behavior — the psycopg2 connect_args
    do not apply, so test environments are unaffected."""
    from config import _engine_options_for_url

    assert _engine_options_for_url('sqlite:///:memory:') == {}
    assert _engine_options_for_url('sqlite:////tmp/test.db') == {}


def test_production_config_sets_pool_pre_ping(monkeypatch):
    """Wiring check: production init flows the hardened engine options into the
    app config (read by Flask-SQLAlchemy at db.init_app)."""
    from config import ProductionConfig

    monkeypatch.setenv(
        'DATABASE_URL', 'postgresql://u:p@db.example.com:5432/baseballos')
    app = FakeApp('production')
    app.config['SECRET_KEY'] = 'strong-value'
    app.config['ADMIN_API_TOKEN'] = 'admin-secret'

    ProductionConfig.init_app(app)

    opts = app.config['SQLALCHEMY_ENGINE_OPTIONS']
    assert opts['pool_pre_ping'] is True
    assert opts['pool_recycle'] == 300
    assert opts['connect_args']['options'] == '-c statement_timeout=15000'
