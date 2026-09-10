"""Regression tests for the test-database engine lifecycle in ``tests/db_config``.

These prove the fix for the suite-wide PostgreSQL connection leak: each backend
test builds a fresh Flask app + SQLAlchemy engine, and without disposing the
engine its pooled connection is never released, so connections accumulate across
the whole test process and eventually exhaust the server
(``FATAL: sorry, too many clients already``). ``drop_test_schema`` now disposes
the test app's engines on teardown; these tests verify that disposal is complete,
correctly ordered, exception-safe, target-guarded, and that many sequential
app/engine lifecycles no longer retain connections.
"""

import flask
import pytest
from sqlalchemy import create_engine, text

from utils.db import db
from tests import db_config
from tests.db_config import (
    assert_disposable_test_target,
    configure_test_database,
    create_test_schema,
    dispose_test_database_engines,
    drop_test_schema,
    is_disposable_test_target,
)

_DISPOSABLE_URL = db_config.test_database_url()


def _is_postgres_target():
    return _DISPOSABLE_URL.startswith('postgres://') or _DISPOSABLE_URL.startswith('postgresql://')


requires_postgres = pytest.mark.skipif(
    not _is_postgres_target(),
    reason='requires a disposable PostgreSQL test target',
)


def _fresh_app(name='lifecycle-test'):
    app = flask.Flask(name)
    configure_test_database(app)
    db.init_app(app)
    return app


def _spy_dispose(engine):
    """Wrap ``engine.dispose`` with a call counter; returns the engine."""
    engine._dispose_calls = 0
    real = engine.dispose

    def counted(*args, **kwargs):
        engine._dispose_calls += 1
        return real(*args, **kwargs)

    engine.dispose = counted
    return engine


# 1. Disposes the default engine.
def test_dispose_disposes_default_engine():
    app = _fresh_app()
    with app.app_context():
        create_test_schema(app)
        engine = _spy_dispose(db.engine)
        dispose_test_database_engines(app)
        assert engine._dispose_calls == 1
        drop_test_schema(app)


# 2. Disposes every engine reported for the app (default + binds), each once.
def test_dispose_disposes_all_reported_engines(monkeypatch):
    app = _fresh_app()
    with app.app_context():
        create_test_schema(app)
        default_engine = _spy_dispose(db.engine)
        # A second distinct engine standing in for a configured bind, without
        # polluting the shared db.metadatas with a session-wide bind key.
        bound_engine = _spy_dispose(create_engine(_DISPOSABLE_URL))
        monkeypatch.setattr(db_config, '_test_app_engines',
                            lambda _app: [default_engine, bound_engine])
        dispose_test_database_engines(app)
        assert default_engine._dispose_calls == 1
        assert bound_engine._dispose_calls == 1
        monkeypatch.undo()
        drop_test_schema(app)


# 3. Deduplicates repeated references to the same engine (dispose exactly once).
def test_dispose_deduplicates_same_engine(monkeypatch):
    app = _fresh_app()
    with app.app_context():
        create_test_schema(app)
        engine = _spy_dispose(db.engine)
        monkeypatch.setattr(db_config, '_test_app_engines', lambda _app: [engine, engine])
        dispose_test_database_engines(app)
        assert engine._dispose_calls == 1
        monkeypatch.undo()
        drop_test_schema(app)


# 4. Removes the scoped session before disposing engines.
def test_dispose_removes_session_before_disposing(monkeypatch):
    app = _fresh_app()
    with app.app_context():
        create_test_schema(app)
        events = []
        real_remove = db.session.remove
        monkeypatch.setattr(db.session, 'remove',
                            lambda *a, **k: (events.append('remove'), real_remove(*a, **k))[1])
        engine = db.engine
        real_dispose = engine.dispose
        engine.dispose = lambda *a, **k: (events.append('dispose'), real_dispose(*a, **k))[1]
        dispose_test_database_engines(app)
        assert events and events[0] == 'remove'
        assert 'dispose' in events
        assert events.index('remove') < events.index('dispose')
        monkeypatch.undo()
        drop_test_schema(app)


# 5. drop_test_schema disposes engines after a successful db.drop_all.
def test_drop_test_schema_disposes_after_successful_drop_all():
    app = _fresh_app()
    with app.app_context():
        create_test_schema(app)
        engine = _spy_dispose(db.engine)
        drop_test_schema(app)
        assert engine._dispose_calls == 1


# 6. drop_test_schema still disposes engines when db.drop_all raises.
def test_drop_test_schema_disposes_even_when_drop_all_raises(monkeypatch):
    app = _fresh_app()
    with app.app_context():
        create_test_schema(app)
        engine = _spy_dispose(db.engine)

        def boom():
            raise RuntimeError('drop_all failure')

        monkeypatch.setattr(db, 'drop_all', boom)
        with pytest.raises(RuntimeError, match='drop_all failure'):
            drop_test_schema(app)
        # Disposal happened in the finally block despite the failure.
        assert engine._dispose_calls == 1
        monkeypatch.undo()
        drop_test_schema(app)


# 7. Disposal is safe when no engine was ever initialized for the app.
def test_dispose_safe_when_no_engine_initialized():
    app = flask.Flask('never-initialized')
    configure_test_database(app)
    # No db.init_app(app); no engine exists for this app.
    dispose_test_database_engines(app)  # must not raise


# 8. SQLite in-memory lifecycle remains passing.
def test_sqlite_in_memory_lifecycle():
    app = flask.Flask('sqlite-mem')
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    assert is_disposable_test_target('sqlite://')
    db.init_app(app)
    with app.app_context():
        db.create_all()
        assert db.session.execute(text('SELECT 1')).scalar() == 1
        db.session.remove()
        engine = _spy_dispose(db.engine)
        dispose_test_database_engines(app)
        assert engine._dispose_calls == 1


# 9. PostgreSQL lifecycle remains passing.
@requires_postgres
def test_postgres_lifecycle():
    app = _fresh_app('pg-lifecycle')
    with app.app_context():
        create_test_schema(app)
        assert db.session.execute(text('SELECT 1')).scalar() == 1
        db.session.remove()
        drop_test_schema(app)


# 10. Disposable-target validation remains enforced, and disposal never touches a
#     non-disposable engine.
def test_disposable_target_validation_enforced():
    with pytest.raises(RuntimeError):
        assert_disposable_test_target(
            'postgresql://user:pw@prod-db.internal:5432/baseballos',
            operation='unit test',
        )
    assert not is_disposable_test_target('postgresql://user:pw@prod-db.internal:5432/baseballos')


def test_dispose_skips_non_disposable_engine(monkeypatch):
    app = _fresh_app()
    with app.app_context():
        create_test_schema(app)
        # A production-looking engine (never connected — create_engine is lazy)
        # must never be disposed by the test helper.
        prod_engine = _spy_dispose(
            create_engine('postgresql://user:pw@prod-db.internal:5432/baseballos')
        )
        try:
            monkeypatch.setattr(db_config, '_test_app_engines', lambda _app: [prod_engine])
            dispose_test_database_engines(app)
            assert prod_engine._dispose_calls == 0  # skipped: not a disposable target
        finally:
            monkeypatch.undo()
            drop_test_schema(app)


# 11. Repeated app/schema lifecycles do not retain pooled connections. The
#     PostgreSQL run holds references to every created app so DISPOSAL — not
#     garbage collection — is what releases the connections; > 110 sequential
#     lifecycles complete without exhausting the server.
@requires_postgres
def test_repeated_lifecycle_does_not_exhaust_postgres_connections():
    retained_apps = []
    cycles = 115
    for i in range(cycles):
        app = _fresh_app(f'repeat-{i}')
        retained_apps.append(app)  # keep a strong ref so GC cannot mask the leak
        with app.app_context():
            create_test_schema(app)
            db.session.execute(text('SELECT 1'))
            db.session.remove()
            drop_test_schema(app)  # disposes this app's engine
    assert len(retained_apps) == cycles


def test_repeated_lifecycle_disposes_each_engine_sqlite():
    # Deterministic non-Postgres proof: every cycle's engine is disposed even
    # while all app references are retained.
    retained = []
    for i in range(8):
        app = flask.Flask(f'sqlite-repeat-{i}')
        app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
        db.init_app(app)
        retained.append(app)
        with app.app_context():
            db.create_all()
            db.session.execute(text('SELECT 1'))
            db.session.remove()
            engine = _spy_dispose(db.engine)
            dispose_test_database_engines(app)
            assert engine._dispose_calls == 1
    assert len(retained) == 8
