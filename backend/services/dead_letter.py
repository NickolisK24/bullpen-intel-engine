"""
Dead-letter capture for the ingestion pipeline.

Thin, deterministic helpers over the sync_failures table. Recording a failure
is best-effort-durable: it flushes its own row so a later rollback of the main
sync work cannot silently erase the dead-letter, but it never raises back into
the sync loop — capturing a failure must not itself abort the run.
"""

import logging

from sqlalchemy.exc import SQLAlchemyError

from models.sync_failure import SyncFailure
from utils.db import db
from utils.time import utc_now_naive


logger = logging.getLogger('baseballos.dead_letter')


def record_failure(
    entity_type,
    error,
    *,
    entity_ref=None,
    payload=None,
    sync_run_id=None,
    job_name='daily_sync',
):
    """
    Persist a dead-letter row for one failed entity and return it (or None if
    the write itself failed).

    Structured log line on every capture so the failure is traceable even if
    the DB write later rolls back.
    """
    logger.warning(
        'dead_letter capture job=%s entity_type=%s entity_ref=%s run_id=%s error=%s',
        job_name, entity_type, entity_ref, sync_run_id, error,
    )
    try:
        failure = SyncFailure(
            sync_run_id=sync_run_id,
            job_name=job_name,
            entity_type=entity_type,
            entity_ref=str(entity_ref) if entity_ref is not None else None,
            payload=payload,
            error=str(error) if error is not None else None,
            created_at=utc_now_naive(),
            resolved=False,
        )
        db.session.add(failure)
        # Flush (not commit) so the row participates in the surrounding sync
        # transaction's commit, but is materialized immediately for id/queries.
        db.session.flush()
        return failure
    except SQLAlchemyError as exc:
        logger.error('Could not persist dead-letter row: %s', exc)
        return None


def unresolved_count():
    """Number of dead-letters still awaiting resolution. Never raises."""
    try:
        return (
            db.session.query(db.func.count(SyncFailure.id))
            .filter(SyncFailure.resolved.is_(False))
            .scalar()
            or 0
        )
    except SQLAlchemyError:
        db.session.rollback()
        logger.warning('Could not count unresolved dead-letters.')
        return 0


def unresolved_failures(limit=50):
    """Return the most recent unresolved dead-letters. Never raises."""
    try:
        return (
            SyncFailure.query
            .filter(SyncFailure.resolved.is_(False))
            .order_by(SyncFailure.created_at.desc(), SyncFailure.id.desc())
            .limit(limit)
            .all()
        )
    except SQLAlchemyError:
        db.session.rollback()
        logger.warning('Could not read unresolved dead-letters.')
        return []


def resolve(failure_id):
    """Mark a dead-letter resolved. Returns True on success."""
    try:
        failure = db.session.get(SyncFailure, failure_id)
        if failure is None:
            return False
        failure.resolved = True
        failure.resolved_at = utc_now_naive()
        db.session.commit()
        return True
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.error('Could not resolve dead-letter %s: %s', failure_id, exc)
        return False


def resolve_entity_failures(entity_type, entity_ref, job_name='daily_sync'):
    """
    Mark unresolved failures for one retryable entity as resolved.

    The caller owns the surrounding commit so this helper can run inside a sync
    transaction without adding a new commit boundary.
    """
    if entity_ref is None:
        return 0
    try:
        rows = (
            SyncFailure.query
            .filter_by(
                entity_type=entity_type,
                entity_ref=str(entity_ref),
                job_name=job_name,
                resolved=False,
            )
            .all()
        )
        if not rows:
            return 0
        resolved_at = utc_now_naive()
        for row in rows:
            row.resolved = True
            row.resolved_at = resolved_at
            db.session.add(row)
        db.session.flush()
        return len(rows)
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.error(
            'Could not resolve dead-letter entity_type=%s entity_ref=%s: %s',
            entity_type,
            entity_ref,
            exc,
        )
        return 0
