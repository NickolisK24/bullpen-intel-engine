"""Tests for the fail-closed snapshot read guard.

The guard wraps the indexed snapshot lookups so a transient Postgres connection
failure (e.g. Render's ``SSL SYSCALL error: EOF detected`` on a stale pooled
connection) rolls back the session, logs with context, and raises
``SnapshotReadUnavailable`` — distinct from a cache miss — without leaking the
raw DB error.
"""

from datetime import date

import pytest
from flask import Flask
from sqlalchemy.exc import OperationalError
from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)

from services.snapshot_read_guard import SnapshotReadUnavailable, read_snapshot_first
from utils.db import db
from models.tonight_intelligence_snapshot import TonightIntelligenceSnapshot
import models.pitcher  # noqa: F401  (full model registry for create_all)
import models.game_log  # noqa: F401
import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401

_REF = date(2026, 6, 28)


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


class _FailingQuery:
    """A query whose .first() raises, simulating a dead DB connection."""

    def __init__(self, exc):
        self._exc = exc

    def first(self):
        raise self._exc


class _StubQuery:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


def _operational_error():
    # Mirrors how SQLAlchemy wraps a psycopg2 connection EOF.
    return OperationalError(
        'SELECT 1', {}, Exception('SSL SYSCALL error: EOF detected'))


def test_read_failure_rolls_back_session_and_raises_unavailable(app):
    with app.app_context():
        # A pending insert makes the session dirty; the guard must roll it back
        # so the failed transaction does not poison the next request.
        db.session.add(TonightIntelligenceSnapshot(
            reference_date=_REF, snapshot_version='tonight_v1'))
        assert len(db.session.new) == 1

        with pytest.raises(SnapshotReadUnavailable) as info:
            read_snapshot_first(
                _FailingQuery(_operational_error()),
                snapshot_type='tonight',
                reference_date=_REF,
                snapshot_version='tonight_v1',
            )

        # Rolled back: the pending insert is gone.
        assert len(db.session.new) == 0

    err = info.value
    assert err.snapshot_type == 'tonight'
    assert err.reference_date == _REF
    assert err.snapshot_version == 'tonight_v1'


def test_read_failure_does_not_leak_raw_db_error_text(app):
    with app.app_context():
        with pytest.raises(SnapshotReadUnavailable) as info:
            read_snapshot_first(
                _FailingQuery(_operational_error()),
                snapshot_type='intelligence_surface',
                reference_date=_REF,
                snapshot_version='intelligence_surface_v1',
            )
    text = str(info.value)
    assert 'SSL SYSCALL' not in text
    assert 'OperationalError' not in text


def test_successful_read_returns_row(app):
    sentinel = object()
    with app.app_context():
        result = read_snapshot_first(
            _StubQuery(sentinel),
            snapshot_type='tonight',
            reference_date=_REF,
            snapshot_version='tonight_v1',
        )
    assert result is sentinel


def test_cache_miss_returns_none_not_error(app):
    with app.app_context():
        result = read_snapshot_first(
            _StubQuery(None),
            snapshot_type='tonight',
            reference_date=_REF,
            snapshot_version='tonight_v1',
        )
    assert result is None
