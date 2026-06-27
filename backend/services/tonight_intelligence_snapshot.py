"""Tonight intelligence snapshot layer (performance).

The Tonight cards are expensive to build on demand (schedule contexts for every
team, a bullpen context per playing team, candidate selection, envelope shaping).
This caches the finished public ``GET /api/bullpen/intelligence/tonight`` response
per slate and serves it back quickly, falling back to live generation when no
snapshot exists. The served payload is exactly what the builder produces, so the
public response contract is unchanged either way.

Mirrors the Intelligence Surface snapshot layer. Nothing here changes candidate
selection, signals, or copy — it only caches the builder's output. Pregame and
separate from the COIN completed-game stories.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from time import perf_counter

from models.tonight_intelligence_snapshot import TonightIntelligenceSnapshot
from services.availability_reference_date import product_current_date
from services.tonight_intelligence_service import serve_tonight
from utils.db import db
from utils.time import utc_now_naive

logger = logging.getLogger(__name__)

# Bump to invalidate every stored snapshot without a data migration.
TONIGHT_SNAPSHOT_VERSION = 'tonight_v1'

SERVED_FROM_SNAPSHOT = 'snapshot'
SERVED_FROM_ON_DEMAND = 'on_demand'


def serve_tonight_cached(reference_date=None, *, current_date=None, limit=None,
                         persist=True):
    """Cache-aware entry point for the Tonight endpoint.

    Resolves the slate (the product current day by default), returns a stored
    snapshot when one exists for that date, otherwise builds live and (best
    effort) stores the result. Must run inside an app context. Returns the public
    envelope — identical shape whether served from snapshot or built on demand.
    """
    start = perf_counter()
    ref = _resolve_reference_date(reference_date, current_date)

    cached = read_snapshot(ref)
    if cached is not None:
        _log_timing(SERVED_FROM_SNAPSHOT, cached, start)
        return cached

    build_kwargs = {} if limit is None else {'limit': limit}
    response = serve_tonight(ref, **build_kwargs)
    if persist:
        _safe_write_snapshot(response, source=SERVED_FROM_ON_DEMAND)
    _log_timing(SERVED_FROM_ON_DEMAND, response, start)
    return response


def generate_tonight_snapshot_for_date(reference_date, *, source, limit=None):
    """Build and store the Tonight snapshot for one explicit slate date.

    A warming helper that schedule ingestion / a pregame sync can call later so
    the homepage's first visitor hits a warm cache. Returns the built response.
    """
    build_kwargs = {} if limit is None else {'limit': limit}
    response = serve_tonight(_as_date(reference_date), **build_kwargs)
    write_snapshot(response, source=source)
    return response


# ── Storage ───────────────────────────────────────────────────────────────────

def read_snapshot(reference_date, version=TONIGHT_SNAPSHOT_VERSION):
    """Return the stored response_json for a slate, or None when absent."""
    ref_date = _as_date(reference_date)
    if ref_date is None:
        return None
    row = (
        TonightIntelligenceSnapshot.query
        .filter_by(reference_date=ref_date, snapshot_version=version)
        .first()
    )
    return row.response_json if row is not None else None


def write_snapshot(response, *, source, version=TONIGHT_SNAPSHOT_VERSION):
    """Upsert the snapshot for ``response['reference_date']``.

    Returns the row, or None when the response has no slate date to key on. Empty
    responses (status='empty', a real date) are cached too; error responses are
    not routed here, so they are never stored.
    """
    ref_date = _as_date((response or {}).get('reference_date'))
    if ref_date is None:
        return None

    row = (
        TonightIntelligenceSnapshot.query
        .filter_by(reference_date=ref_date, snapshot_version=version)
        .first()
    )
    if row is None:
        row = TonightIntelligenceSnapshot(
            reference_date=ref_date, snapshot_version=version)
        db.session.add(row)

    row.status = response.get('status')
    row.response_json = response
    row.card_count = response.get('card_count') or 0
    row.empty_reason = response.get('empty_reason')
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
        logger.warning('Tonight snapshot write failed', exc_info=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _resolve_reference_date(reference_date, current_date):
    if reference_date is not None:
        return _as_date(reference_date)
    if current_date is not None:
        return _as_date(current_date)
    return product_current_date()


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
        'tonight_intelligence served_from=%s reference_date=%s elapsed_ms=%s '
        'status=%s card_count=%s',
        served_from, response.get('reference_date'), elapsed_ms,
        response.get('status'), response.get('card_count'),
    )
