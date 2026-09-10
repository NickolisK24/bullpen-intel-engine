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
