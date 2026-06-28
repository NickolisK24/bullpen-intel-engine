"""Intelligence Surface snapshot layer (performance).

The Intelligence Surface lead story is expensive to build on demand (resolve
candidate contexts, build StoryPackages, render writers, rank, serialize). This
layer stores the finished GET /api/bullpen/intelligence/today response per slate
and serves it back quickly, falling back to live generation when no snapshot
exists. The served payload is the exact response the builder produces, so the
public response contract is unchanged either way.

Postgame refresh calls ``generate_snapshot_for_date`` after it derives a slate's
completed-game contexts, keeping the stored snapshot fresh. Nothing here changes
ranking, publishability, or story content — it only caches the builder's output.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from time import perf_counter

from models.intelligence_surface_snapshot import IntelligenceSurfaceSnapshot
from services.intelligence_surface_service import (
    build_today_lead_story,
    resolve_default_reference_date,
)
from services.snapshot_read_guard import read_snapshot_first
from utils.db import db
from utils.time import utc_now_naive

logger = logging.getLogger(__name__)

# Bump to invalidate every stored snapshot without a data migration (e.g. if the
# response shape changes). Stored alongside reference_date as the lookup key.
SNAPSHOT_VERSION = 'intelligence_surface_v1'

SERVED_FROM_SNAPSHOT = 'snapshot'
SERVED_FROM_ON_DEMAND = 'on_demand'


def serve_today_lead_story(
    *,
    reference_date=None,
    current_date=None,
    persist=True,
):
    """Cache-aware entry point for the public endpoint.

    Resolves the slate the builder would use, returns a stored snapshot when one
    exists for that date, otherwise builds live and (best-effort) stores the
    result. Read path is the common case and avoids all story work. Must run
    inside an app context. Returns the endpoint response dict — identical shape
    whether served from snapshot or built on demand.
    """
    start = perf_counter()

    resolved = resolve_default_reference_date(reference_date, current_date)
    if resolved is not None:
        cached = read_snapshot(resolved)
        if cached is not None:
            _log_timing(SERVED_FROM_SNAPSHOT, cached, start)
            return cached

    # No snapshot (or no resolvable date) — fall back to live generation.
    response = build_today_lead_story(
        reference_date=resolved if resolved is not None else reference_date,
        current_date=current_date,
    )
    if persist:
        _safe_write_snapshot(response, source=SERVED_FROM_ON_DEMAND)
    _log_timing(SERVED_FROM_ON_DEMAND, response, start)
    return response


def generate_snapshot_for_date(reference_date, *, source, current_date=None):
    """Build and store the snapshot for one explicit slate date.

    Used by postgame refresh after completed-game contexts are derived. Honors
    the date exactly (no future cap — postgame always passes a real slate date).
    Returns the built response. Raises on failure so the caller can decide how to
    report; postgame wraps this so a snapshot failure never breaks the refresh.
    """
    response = build_today_lead_story(
        reference_date=reference_date, current_date=current_date)
    write_snapshot(response, source=source)
    return response


# ── Storage ───────────────────────────────────────────────────────────────────

def read_snapshot(reference_date, version=SNAPSHOT_VERSION):
    """Return the stored response_json for a slate, or None when absent.

    A normal miss (no stored row) returns None. A transient DB connection
    failure raises SnapshotReadUnavailable (it is not a miss), so the caller
    fails closed instead of rebuilding on a broken connection.
    """
    ref_date = _as_date(reference_date)
    if ref_date is None:
        return None
    query = (
        IntelligenceSurfaceSnapshot.query
        .filter_by(reference_date=ref_date, snapshot_version=version)
    )
    row = read_snapshot_first(
        query,
        snapshot_type='intelligence_surface',
        reference_date=ref_date,
        snapshot_version=version,
    )
    return row.response_json if row is not None else None


def write_snapshot(response, *, source, version=SNAPSHOT_VERSION):
    """Upsert the snapshot for ``response['reference_date']``.

    Returns the row, or None when the response has no slate date to key on (an
    empty database with no contexts at all — nothing worth caching).
    """
    ref_date = _as_date((response or {}).get('reference_date'))
    if ref_date is None:
        return None

    lead = (response.get('lead_story') or {}) if response else {}
    row = (
        IntelligenceSurfaceSnapshot.query
        .filter_by(reference_date=ref_date, snapshot_version=version)
        .first()
    )
    if row is None:
        row = IntelligenceSurfaceSnapshot(
            reference_date=ref_date, snapshot_version=version)
        db.session.add(row)

    row.status = response.get('status')
    row.response_json = response
    row.lead_story_team_id = lead.get('team_id')
    row.lead_story_game_pk = lead.get('game_pk')
    row.candidates_considered = response.get('candidates_considered') or 0
    row.publishable_candidates = response.get('publishable_candidates') or 0
    row.empty_reason = response.get('empty_reason')
    row.errors = response.get('errors') or 0
    row.source = source
    row.generated_at = utc_now_naive()
    db.session.commit()
    return row


def _safe_write_snapshot(response, *, source):
    """Persist a snapshot without ever breaking the serving path."""
    try:
        write_snapshot(response, source=source)
    except Exception:  # noqa: BLE001 — caching is best-effort, never fatal
        db.session.rollback()
        logger.warning('Intelligence surface snapshot write failed', exc_info=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _as_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def _log_timing(served_from, response, start):
    elapsed_ms = round((perf_counter() - start) * 1000, 1)
    response = response or {}
    logger.info(
        'intelligence_surface served_from=%s reference_date=%s elapsed_ms=%s '
        'status=%s publishable_candidates=%s',
        served_from,
        response.get('reference_date'),
        elapsed_ms,
        response.get('status'),
        response.get('publishable_candidates'),
    )
