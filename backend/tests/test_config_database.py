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
