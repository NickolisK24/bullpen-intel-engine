"""Observe what the database ownership fences suppressed (Postgres only).

Production PostgreSQL carries the ownership fences of migration
``e3f6a9b2c5d8`` (SYNC_PIPELINE.md §15A-15C). A fenced write from a session
without the matching ``baseballos.*`` ownership declaration is reverted inside
the database (or, for some inserts, refused), while the ORM still believes it
wrote the row. Each revert is logged in ``compatibility_write_events``.

Writers use this module so a canonical mutation the database discarded is
reported as suppressed, never as success. Only counts are read; event details
stay in the table.

Fence inventory (writer -> declaration):

* ``pitchers`` (``pitcher_projection``): ``baseballos.roster_owner`` = new team.
  Declared by ``roster_status_sync``, ``team_assignment_sync`` (official
  active/40-man confirmations) and ``intraday_identity_repair``.
* ``roster_status_snapshots`` (``roster_snapshot``): the same declaration;
  only runtime-observed rows are fenced. Declared by ``roster_status_sync``.
* ``scheduled_games`` / ``slate_games`` (``schedule``):
  ``baseballos.schedule_owners``. Declared by ``schedule_ingestion.ingest_games``,
  which every main schedule writer goes through.
* ``game_logs``, ``postgame_processed_games``, play-by-play tables
  (``final_compatibility``): ``baseballos.final_game_owner``. Not declared by
  main by design: a game with a current ``final_game_versions`` row belongs to
  the runtime's final owner, and main's compatibility write is superseded
  (``final_superseded``) or, for an insert, refused.
* ``player_transactions`` (``transaction``): ``baseballos.transaction_owner``.
  Not declared by main: a runtime-versioned transaction keeps its version.
* ``game_observation_states`` (``game_observation``): ordered by observation
  fingerprints and source times rather than by ownership.
"""

from __future__ import annotations

from sqlalchemy import text

from utils.db import db


SUPPRESSED_OUTCOMES = ('stale_suppressed', 'final_superseded')


def _available():
    try:
        if db.session.get_bind().dialect.name != 'postgresql':
            return False
        return bool(db.session.execute(
            text("SELECT to_regclass('public.compatibility_write_events') IS NOT NULL")
        ).scalar())
    except Exception:
        return False


def suppressed_writes_since(started_at, resource_types=None):
    """``{resource_type: count}`` of fence-suppressed writes since ``started_at``.

    ``None`` where the fences do not exist (non-Postgres or unmigrated schema),
    so a caller can tell "nothing was suppressed" from "cannot be observed".
    The window is time-based: a concurrent writer's suppressions in the same
    window are included.
    """
    if started_at is None or not _available():
        return None
    sql = (
        "SELECT resource_type, count(*) FROM compatibility_write_events "
        "WHERE created_at >= :since AND outcome = ANY(:outcomes)"
    )
    params = {'since': started_at, 'outcomes': list(SUPPRESSED_OUTCOMES)}
    if resource_types:
        sql += " AND resource_type = ANY(:types)"
        params['types'] = list(resource_types)
    sql += " GROUP BY resource_type"
    rows = db.session.execute(text(sql), params).all()
    return {resource_type: int(count) for resource_type, count in sorted(rows)}


def suppressed_write_count_since(started_at, resource_types=None):
    counts = suppressed_writes_since(started_at, resource_types)
    if counts is None:
        return None
    return sum(counts.values())
