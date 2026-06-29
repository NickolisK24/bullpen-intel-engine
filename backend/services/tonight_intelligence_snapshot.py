"""Tonight intelligence snapshot layer (performance).

The Tonight cards are expensive to build on demand (schedule contexts for every
team, a bullpen context per playing team, candidate selection, envelope shaping).
This caches the finished public ``GET /api/bullpen/intelligence/tonight`` response
per slate and serves it back quickly. Callers that can afford the work may fall
back to live generation when no snapshot exists; public serving paths route that
fallback through a timeout so a cold cache cannot hang the homepage. The served
payload matches the builder output when a snapshot or live build is available,
with a small snapshot metadata block added for freshness/provenance.

Mirrors the Intelligence Surface snapshot layer. Nothing here changes candidate
selection, signals, or copy — it only caches the builder's output. Pregame and
separate from the COIN completed-game stories.
"""

from __future__ import annotations

import logging
import os
import signal
import threading
from datetime import date, datetime
from time import perf_counter

from models.tonight_intelligence_snapshot import TonightIntelligenceSnapshot
from services.availability_reference_date import product_current_date
from services.snapshot_read_guard import read_snapshot_first
from services.tonight_intelligence_service import serve_tonight
from utils.db import db
from utils.time import utc_now_naive

logger = logging.getLogger(__name__)

# Bump to invalidate every stored snapshot without a data migration.
TONIGHT_SNAPSHOT_VERSION = 'tonight_v1'

SERVED_FROM_SNAPSHOT = 'snapshot'
SERVED_FROM_ON_DEMAND = 'on_demand'
SERVED_FROM_LIVE_TIMEOUT = 'live_build_timeout'
SERVED_FROM_LIVE_FAILED = 'live_build_failed'
EMPTY_LIVE_BUILD_TIMEOUT = 'tonight_live_build_timeout'
EMPTY_SNAPSHOT_BUILD_UNAVAILABLE = 'tonight_snapshot_build_unavailable'
DEFAULT_LIVE_BUILD_TIMEOUT_SECONDS = 8.0


class TonightLiveBuildTimeout(TimeoutError):
    """Raised when the bounded public live fallback exceeds its budget."""


def serve_tonight_cached(reference_date=None, *, current_date=None, limit=None,
                         persist=True, build_on_miss=True,
                         live_build_timeout_seconds=None):
    """Cache-aware entry point for the Tonight endpoint.

    Resolves the slate (the product current day by default), returns a stored
    snapshot when one exists for that date, otherwise builds live with an
    explicit timeout and (best effort) stores the result when ``build_on_miss``
    is true. Public request paths keep availability through this bounded live
    fallback without relying on an unbounded cold build. Must run inside an app
    context. Returns the public envelope.
    """
    start = perf_counter()
    ref = _resolve_reference_date(reference_date, current_date)

    cached_row = read_snapshot_row(ref)
    if cached_row is not None:
        cached = _with_snapshot_metadata(
            cached_row.response_json,
            served_from=SERVED_FROM_SNAPSHOT,
            source=cached_row.source,
            generated_at=cached_row.generated_at,
        )
        _log_timing(SERVED_FROM_SNAPSHOT, cached, start)
        return cached

    if not build_on_miss:
        response = _unavailable_response(
            ref,
            EMPTY_SNAPSHOT_BUILD_UNAVAILABLE,
            served_from=SERVED_FROM_LIVE_FAILED,
        )
        _log_timing(SERVED_FROM_LIVE_FAILED, response, start)
        return response

    build_kwargs = {} if limit is None else {'limit': limit}
    timeout_seconds = _resolve_live_build_timeout_seconds(live_build_timeout_seconds)
    try:
        response = _run_live_build_with_timeout(ref, build_kwargs, timeout_seconds)
    except TonightLiveBuildTimeout as exc:
        db.session.rollback()
        response = _unavailable_response(
            ref,
            EMPTY_LIVE_BUILD_TIMEOUT,
            served_from=SERVED_FROM_LIVE_TIMEOUT,
        )
        logger.warning(
            'Tonight live build timed out for reference_date=%s after %ss: %s',
            _date_iso(ref), timeout_seconds, exc,
        )
        _log_timing(SERVED_FROM_LIVE_TIMEOUT, response, start)
        return response
    except Exception as exc:  # noqa: BLE001 - live fallback must fail soft
        db.session.rollback()
        response = _unavailable_response(
            ref,
            EMPTY_SNAPSHOT_BUILD_UNAVAILABLE,
            served_from=SERVED_FROM_LIVE_FAILED,
        )
        logger.warning(
            'Tonight live build failed for reference_date=%s: %s',
            _date_iso(ref), exc,
            exc_info=True,
        )
        _log_timing(SERVED_FROM_LIVE_FAILED, response, start)
        return response

    generated_at = utc_now_naive()
    if persist:
        _safe_write_snapshot(
            response,
            source=SERVED_FROM_ON_DEMAND,
            generated_at=generated_at,
        )
    served = _with_snapshot_metadata(
        response,
        served_from=SERVED_FROM_ON_DEMAND,
        source=SERVED_FROM_ON_DEMAND,
        generated_at=generated_at,
    )
    _log_timing(SERVED_FROM_ON_DEMAND, served, start)
    return served


def generate_tonight_snapshot_for_date(reference_date, *, source, limit=None):
    """Build and store the Tonight snapshot for one explicit slate date.

    A warming helper that schedule ingestion / a pregame sync can call later so
    the homepage's first visitor hits a warm cache. Returns the built response.
    """
    build_kwargs = {} if limit is None else {'limit': limit}
    generated_at = utc_now_naive()
    response = serve_tonight(_as_date(reference_date), **build_kwargs)
    write_snapshot(response, source=source, generated_at=generated_at)
    return _with_snapshot_metadata(
        response,
        served_from=source,
        source=source,
        generated_at=generated_at,
    )


# ── Storage ───────────────────────────────────────────────────────────────────

def read_snapshot(reference_date, version=TONIGHT_SNAPSHOT_VERSION):
    """Return the stored response_json for a slate, or None when absent.

    A normal miss (no stored row) returns None. A transient DB connection
    failure raises SnapshotReadUnavailable (it is not a miss), so the caller
    fails closed instead of rebuilding on a broken connection.
    """
    row = read_snapshot_row(reference_date, version=version)
    return row.response_json if row is not None else None


def read_snapshot_row(reference_date, version=TONIGHT_SNAPSHOT_VERSION):
    """Return the stored Tonight snapshot row, or None when absent."""
    ref_date = _as_date(reference_date)
    if ref_date is None:
        return None
    query = (
        TonightIntelligenceSnapshot.query
        .filter_by(reference_date=ref_date, snapshot_version=version)
    )
    return read_snapshot_first(
        query,
        snapshot_type='tonight',
        reference_date=ref_date,
        snapshot_version=version,
    )


def write_snapshot(response, *, source, version=TONIGHT_SNAPSHOT_VERSION,
                   generated_at=None):
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

    generated_at = generated_at or utc_now_naive()

    row.status = response.get('status')
    row.response_json = _with_snapshot_metadata(
        response,
        source=source,
        generated_at=generated_at,
    )
    row.card_count = response.get('card_count') or 0
    row.empty_reason = response.get('empty_reason')
    row.source = source
    row.generated_at = generated_at
    db.session.commit()
    return row


def _safe_write_snapshot(response, *, source, generated_at=None):
    """Persist a snapshot without ever breaking the serving path."""
    try:
        write_snapshot(response, source=source, generated_at=generated_at)
    except Exception:  # noqa: BLE001 — caching is best-effort, never fatal
        db.session.rollback()
        logger.warning('Tonight snapshot write failed', exc_info=True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _unavailable_response(reference_date, empty_reason, *, served_from):
    generated_at = utc_now_naive()
    response = {
        'status': 'empty',
        'reference_date': _date_iso(reference_date),
        'cards': [],
        'card_count': 0,
        'empty_reason': empty_reason,
        'limitations': ['Tonight watch is temporarily unavailable.'],
    }
    return _with_snapshot_metadata(
        response,
        served_from=served_from,
        source=SERVED_FROM_ON_DEMAND,
        generated_at=generated_at,
    )


def _with_snapshot_metadata(response, *, served_from=None, source=None,
                            generated_at=None):
    out = dict(response or {})
    metadata = dict(out.get('snapshot') or {})
    if served_from:
        metadata['served_from'] = served_from
    if source:
        metadata['source'] = source
    if generated_at:
        metadata['generated_at'] = _datetime_iso(generated_at)
    if metadata:
        out['snapshot'] = metadata
    return out


def _resolve_live_build_timeout_seconds(value=None):
    raw = value
    if raw is None:
        raw = os.environ.get(
            'TONIGHT_LIVE_BUILD_TIMEOUT_SECONDS',
            str(DEFAULT_LIVE_BUILD_TIMEOUT_SECONDS),
        )
    try:
        seconds = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_LIVE_BUILD_TIMEOUT_SECONDS
    return seconds if seconds > 0 else None


def _run_live_build_with_timeout(reference_date, build_kwargs, timeout_seconds):
    """Run the public cache-miss build with a best-effort hard timeout.

    Production runs on Unix where ``setitimer`` can interrupt a synchronous
    worker before the browser-facing request hangs. Environments without signal
    timers fall back to the direct call; lower-level DB/API timeouts still apply
    there, and tests monkeypatch this seam for deterministic timeout coverage.
    """
    if not timeout_seconds or not _signal_timeout_available():
        return serve_tonight(reference_date, **build_kwargs)

    def _timeout_handler(signum, frame):  # noqa: ARG001
        raise TonightLiveBuildTimeout(
            f'Tonight live build exceeded {timeout_seconds}s')

    previous_handler = signal.getsignal(signal.SIGALRM)
    try:
        signal.signal(signal.SIGALRM, _timeout_handler)
        signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
        return serve_tonight(reference_date, **build_kwargs)
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def _signal_timeout_available():
    return (
        threading.current_thread() is threading.main_thread()
        and hasattr(signal, 'SIGALRM')
        and hasattr(signal, 'ITIMER_REAL')
        and hasattr(signal, 'setitimer')
    )


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


def _date_iso(value):
    ref = _as_date(value)
    return ref.isoformat() if ref is not None else None


def _datetime_iso(value):
    if value is None:
        return None
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)


def _log_timing(served_from, response, start):
    elapsed_ms = round((perf_counter() - start) * 1000, 1)
    response = response or {}
    logger.info(
        'tonight_intelligence served_from=%s reference_date=%s elapsed_ms=%s '
        'status=%s card_count=%s',
        served_from, response.get('reference_date'), elapsed_ms,
        response.get('status'), response.get('card_count'),
    )
