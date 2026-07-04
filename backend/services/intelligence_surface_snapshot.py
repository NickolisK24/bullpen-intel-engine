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

import copy
import hashlib
import logging
from datetime import date, datetime
from pathlib import Path
from time import perf_counter

from models.intelligence_surface_snapshot import IntelligenceSurfaceSnapshot
from services import slate_coverage
from services.intelligence_surface_service import (
    build_today_lead_story,
    resolve_default_reference_date,
)
from services.snapshot_read_guard import read_snapshot_first
from utils.db import db
from utils.time import utc_now_naive

logger = logging.getLogger(__name__)

# Stored alongside reference_date as the lookup key. Include a deterministic
# completed-game story-generation fingerprint so writer logic changes invalidate
# stale persisted prose without a data migration.
SNAPSHOT_FAMILY = 'intelligence_surface_v1'
SNAPSHOT_METADATA_KEY = '_snapshot_metadata'

_FINGERPRINTED_SOURCE_FILES = (
    'story_orchestrator/__init__.py',
    'story_orchestrator/story_orchestrator.py',
    'story_writers/base_story_writer.py',
    'story_writers/team_story_writer.py',
    'story_writers/dashboard_story_writer.py',
    'story_writers/morning_brief_writer.py',
    'services/coin_story_inspection.py',
    'services/evidence_composition_service.py',
    'services/editorial_voice_contract_v1.py',
    'services/narrative_context_service.py',
    'services/narrative_feed_builder.py',
    'utils/baseball_innings.py',
)


def _story_generation_fingerprint() -> str:
    backend_dir = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for rel_path in _FINGERPRINTED_SOURCE_FILES:
        path = backend_dir / rel_path
        digest.update(rel_path.encode('utf-8'))
        digest.update(b'\0')
        digest.update(path.read_bytes())
        digest.update(b'\0')
    return digest.hexdigest()[:12]


SNAPSHOT_WRITER_FINGERPRINT = _story_generation_fingerprint()
SNAPSHOT_VERSION = f'{SNAPSHOT_FAMILY}_{SNAPSHOT_WRITER_FINGERPRINT}'

SERVED_FROM_SNAPSHOT = 'snapshot'
SERVED_FROM_ON_DEMAND = 'on_demand'
SERVED_FROM_ON_DEMAND_FAILED = 'on_demand_failed'
EMPTY_LEAD_STORY_UNAVAILABLE = 'lead_story_unavailable'


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

    # No snapshot (or no resolvable date) — rebuild from current stored data.
    # Use the bounded selector for the public on-demand path so a deploy that
    # invalidates the writer fingerprint can warm the current snapshot without
    # rendering the entire completed-game slate inside the request.
    try:
        response = _public_response(build_today_lead_story(
            reference_date=resolved if resolved is not None else reference_date,
            current_date=current_date,
            bounded=True,
        ))
    except Exception:  # noqa: BLE001 - public endpoint must fail closed
        db.session.rollback()
        logger.exception(
            'Intelligence surface snapshot regeneration failed: '
            'reference_date=%s snapshot_version=%s fingerprint=%s.',
            resolved if resolved is not None else reference_date,
            SNAPSHOT_VERSION,
            SNAPSHOT_WRITER_FINGERPRINT,
        )
        response = _public_response(_regeneration_failed_response(
            resolved if resolved is not None else reference_date))
        _log_timing(SERVED_FROM_ON_DEMAND_FAILED, response, start)
        return response
    if persist:
        _safe_write_snapshot(response, source=SERVED_FROM_ON_DEMAND)
    _log_timing(SERVED_FROM_ON_DEMAND, response, start)
    return response


def generate_snapshot_for_date(
    reference_date,
    *,
    source,
    current_date=None,
    step_logger=None,
):
    """Build and store the snapshot for one explicit slate date.

    Used by postgame refresh after completed-game contexts are derived. Honors
    the date exactly (no future cap — postgame always passes a real slate date).
    Returns the built response. Raises on failure so the caller can decide how to
    report; postgame wraps this so a snapshot failure never breaks the refresh.
    """
    log = step_logger or logger
    started = perf_counter()
    log.info(
        'Intelligence surface snapshot build step starting for %s.',
        reference_date,
    )
    response = _public_response(build_today_lead_story(
        reference_date=reference_date, current_date=current_date))
    build_elapsed_ms = round((perf_counter() - started) * 1000, 1)
    log.info(
        'Intelligence surface snapshot build step completed for %s: '
        'status=%s candidates=%s publishable=%s elapsed_ms=%s.',
        reference_date,
        response.get('status'),
        response.get('candidates_considered'),
        response.get('publishable_candidates'),
        build_elapsed_ms,
    )

    write_started = perf_counter()
    log.info(
        'Intelligence surface snapshot write step starting for %s.',
        reference_date,
    )
    write_snapshot(response, source=source)
    log.info(
        'Intelligence surface snapshot write step completed for %s: '
        'elapsed_ms=%s.',
        reference_date,
        round((perf_counter() - write_started) * 1000, 1),
    )
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
    if row is None:
        return None
    if not _stored_response_is_current(row.response_json, version):
        logger.warning(
            'Ignoring stale intelligence surface snapshot: reference_date=%s '
            'version=%s expected_fingerprint=%s.',
            ref_date,
            version,
            SNAPSHOT_WRITER_FINGERPRINT,
        )
        return None
    return _public_response(row.response_json)


def write_snapshot(response, *, source, version=SNAPSHOT_VERSION):
    """Upsert the snapshot for ``response['reference_date']``.

    Returns the row, or None when the response has no slate date to key on (an
    empty database with no contexts at all — nothing worth caching).
    """
    ref_date = _as_date((response or {}).get('reference_date'))
    if ref_date is None:
        return None

    generated_at = utc_now_naive()
    stored_response = _stored_response(
        response,
        source=source,
        version=version,
        generated_at=generated_at,
    )
    lead = (stored_response.get('lead_story') or {}) if stored_response else {}
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
    row.response_json = stored_response
    row.lead_story_team_id = lead.get('team_id')
    row.lead_story_game_pk = lead.get('game_pk')
    row.candidates_considered = response.get('candidates_considered') or 0
    row.publishable_candidates = response.get('publishable_candidates') or 0
    row.empty_reason = response.get('empty_reason')
    row.errors = response.get('errors') or 0
    row.source = source
    row.generated_at = generated_at
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


def _stored_response(response, *, source, version, generated_at):
    payload = _public_response(response)
    payload[SNAPSHOT_METADATA_KEY] = {
        'snapshot_version': version,
        'snapshot_family': SNAPSHOT_FAMILY,
        'story_writer_fingerprint': SNAPSHOT_WRITER_FINGERPRINT,
        'source': source,
        'generated_at': generated_at.isoformat() if generated_at else None,
    }
    return payload


def _public_response(response):
    payload = copy.deepcopy(response or {})
    payload.pop(SNAPSHOT_METADATA_KEY, None)
    ref_date = _as_date(payload.get('reference_date'))
    if ref_date is None:
        return payload
    try:
        coverage = slate_coverage.compute_slate_coverage(ref_date)
    except Exception as exc:  # noqa: BLE001 - public metadata must fail closed
        db.session.rollback()
        logger.warning(
            'Could not compute intelligence surface slate coverage for %s: %s',
            ref_date,
            exc,
        )
        coverage = slate_coverage.unknown_slate_coverage(ref_date)
    freshness = dict(payload.get('freshness') or {})
    payload['freshness'] = slate_coverage.append_slate_coverage_to_freshness(
        freshness,
        coverage,
    )
    return payload


def _stored_response_is_current(response, version) -> bool:
    if not isinstance(response, dict):
        return False
    metadata = response.get(SNAPSHOT_METADATA_KEY)
    if not isinstance(metadata, dict):
        return False
    return (
        metadata.get('snapshot_version') == version
        and metadata.get('snapshot_family') == SNAPSHOT_FAMILY
        and metadata.get('story_writer_fingerprint') == SNAPSHOT_WRITER_FINGERPRINT
    )


def _regeneration_failed_response(reference_date):
    ref_date = _as_date(reference_date)
    return {
        'status': 'empty',
        'reference_date': ref_date.isoformat() if ref_date else None,
        'lead_story': None,
        'candidates_considered': 0,
        'publishable_candidates': 0,
        'errors': 1,
        'empty_reason': EMPTY_LEAD_STORY_UNAVAILABLE,
    }


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
