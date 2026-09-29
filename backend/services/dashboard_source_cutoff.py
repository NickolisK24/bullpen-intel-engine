"""Bounded read of the served Dashboard score cutoff.

The served fatigue-score cutoff is the ``snapshot_generated_at`` of the latest
valid published Dashboard snapshot. Deciding it needs the publication metadata
and the frozen ``freshness`` block only, never the comprehensive payload.

Loading the ORM row made the database driver transfer and parse the entire
multi-megabyte payload on every lookup. During a Daily Primary publication the
Team State proof resolves Roster Authority for every team, so that parse ran
dozens of times inside the peak-memory window and pushed the 512 MiB cron over
its limit (daily-primary-memory-incident-2026-09-29).

This helper selects the same row (the same filters and ordering as
``dashboard_snapshot.get_latest_dashboard_snapshot``), applies the same
``snapshot_current_enough`` validity rule to a metadata-plus-freshness
projection, and keeps the same failure behavior: a database error rolls back,
logs, and yields no cutoff.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

from sqlalchemy.exc import SQLAlchemyError

from models.dashboard_snapshot import DashboardSnapshot
from services import dashboard_snapshot as dashboard_snapshot_service
from utils.db import db

logger = logging.getLogger(__name__)

# The only payload domain ``snapshot_unavailable_reason`` reads: freshness
# carries data_through, availability_reference_date and slate_coverage.
VALIDITY_PAYLOAD_KEY = 'freshness'


def latest_valid_snapshot_source():
    """The latest valid published Dashboard snapshot as a payload-free projection.

    Returns ``None`` on a miss, on an invalid latest snapshot, or on a
    database error, exactly as ``get_latest_valid_dashboard_snapshot`` does.
    The returned object carries the publication metadata and a ``payload``
    holding only the freshness block used for validity.
    """
    snapshot_type = dashboard_snapshot_service.SNAPSHOT_TYPE_BULLPEN_DASHBOARD
    query = dashboard_snapshot_service._latest_dashboard_snapshot_query(
        snapshot_type,
    ).with_entities(
        DashboardSnapshot.id,
        DashboardSnapshot.snapshot_type,
        DashboardSnapshot.sync_run_id,
        DashboardSnapshot.status,
        DashboardSnapshot.error_message,
        DashboardSnapshot.is_published,
        DashboardSnapshot.published_at,
        DashboardSnapshot.payload_version,
        DashboardSnapshot.data_through,
        DashboardSnapshot.availability_reference_date,
        DashboardSnapshot.snapshot_generated_at,
        DashboardSnapshot.payload[VALIDITY_PAYLOAD_KEY].label('payload_freshness'),
    )
    try:
        row = query.first()
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.warning('Could not read dashboard snapshot: %s', exc)
        return None
    if row is None:
        return None
    payload = {}
    if row.payload_freshness is not None:
        payload[VALIDITY_PAYLOAD_KEY] = row.payload_freshness
    source = SimpleNamespace(
        id=row.id,
        snapshot_type=row.snapshot_type,
        sync_run_id=row.sync_run_id,
        status=row.status,
        error_message=row.error_message,
        is_published=bool(row.is_published),
        published_at=row.published_at,
        payload_version=row.payload_version,
        data_through=row.data_through,
        availability_reference_date=row.availability_reference_date,
        snapshot_generated_at=row.snapshot_generated_at,
        payload=payload,
    )
    if dashboard_snapshot_service.snapshot_current_enough(source):
        return source
    return None
