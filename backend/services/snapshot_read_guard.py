"""Fail-closed guard for cached snapshot reads.

The intelligence snapshot layers (Tonight, Intelligence Surface) look up a
precomputed response by an indexed ``(reference_date, snapshot_version)`` key.
On Render's managed Postgres a pooled connection can be closed underneath the
app (idle cutoff, brief network blip, failover), and the next query that reuses
it fails with ``psycopg2.OperationalError: SSL SYSCALL error: EOF detected``.

This guard wraps the read so that such a transient connection failure:

* does not propagate as a raw DBAPI error,
* does not leave a dirty session for the next request on the worker, and
* is never mistaken for a normal cache *miss* (which would trigger an
  expensive synchronous rebuild on the request path).

A cache *miss* (no row) still returns ``None`` exactly as before. A cache *read
failure* raises :class:`SnapshotReadUnavailable`, which the public endpoints
already turn into their honest unavailable envelope (HTTP 503) without leaking
the underlying error or rebuilding.
"""

from __future__ import annotations

import logging

from sqlalchemy.exc import OperationalError

from utils.db import db

logger = logging.getLogger(__name__)


class SnapshotReadUnavailable(Exception):
    """A snapshot read failed at the database connection level (not a miss).

    Distinct from a cache miss so callers can fail closed (return an honest
    unavailable state) instead of attempting an expensive synchronous rebuild
    on a connection that is already broken.
    """

    def __init__(self, snapshot_type, reference_date, snapshot_version):
        self.snapshot_type = snapshot_type
        self.reference_date = reference_date
        self.snapshot_version = snapshot_version
        super().__init__(
            f'{snapshot_type} snapshot read unavailable for '
            f'reference_date={reference_date} snapshot_version={snapshot_version}'
        )


def read_snapshot_first(query, *, snapshot_type, reference_date, snapshot_version):
    """Run ``query.first()`` for a snapshot lookup, failing closed on a DB error.

    Returns the row (or ``None`` on a normal miss). On a transient
    connection-level ``OperationalError`` it rolls back the session, logs a
    warning with context, and raises :class:`SnapshotReadUnavailable` so the
    caller fails fast instead of rebuilding on a broken connection.
    """
    try:
        return query.first()
    except OperationalError as exc:
        # The connection is already broken; roll back so the failed transaction
        # does not poison the next request handled by this worker. Never let a
        # rollback problem mask the original read failure.
        try:
            db.session.rollback()
        except Exception:  # noqa: BLE001 — best-effort cleanup
            logger.warning(
                'snapshot read rollback failed snapshot_type=%s reference_date=%s '
                'snapshot_version=%s',
                snapshot_type, reference_date, snapshot_version,
            )
        logger.warning(
            'snapshot read failed snapshot_type=%s reference_date=%s '
            'snapshot_version=%s operation=read_snapshot error=%s',
            snapshot_type, reference_date, snapshot_version, type(exc).__name__,
        )
        raise SnapshotReadUnavailable(
            snapshot_type, reference_date, snapshot_version) from exc
