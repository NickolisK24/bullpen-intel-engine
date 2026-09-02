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
import json
import logging
from datetime import date, datetime
from pathlib import Path
from time import perf_counter

from models.intelligence_surface_snapshot import IntelligenceSurfaceSnapshot
from services import slate_coverage
from services.intelligence_surface_service import (
    EMPTY_CLAIM_EVIDENCE_WITHHELD,
    build_today_lead_story,
    resolve_default_reference_date,
)
from services.daily_edition_publication_gate import (
    GATE_VERSION,
    STATUS_PASS as GATE_STATUS_PASS,
    event_consequence_is_compatible,
    rendered_team_story_consequence,
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
CLAIM_EVIDENCE_DIGEST_KEY = 'claim_evidence_digest'

_CLAIM_CONTEXT_FIELDS = (
    'team_id',
    'game_pk',
    'game_date',
    'home_away',
    'bullpen_story_tag',
    'confidence',
    'final_score_for',
    'final_score_against',
    'bullpen_entry_inning',
    'bullpen_entry_score_for',
    'bullpen_entry_score_against',
    'lead_when_bullpen_entered',
    'deficit_when_bullpen_entered',
    'largest_lead',
    'largest_deficit',
    'late_runs_allowed',
    'runs_allowed_innings_7_to_9',
    'lead_protected',
    'lead_lost',
    'comeback_completed',
    'turning_inning',
    'game_shape_created',
    'game_shape_protected',
)

_FINGERPRINTED_SOURCE_FILES = (
    'story_orchestrator/__init__.py',
    'story_orchestrator/story_orchestrator.py',
    'story_writers/base_story_writer.py',
    'story_writers/team_story_writer.py',
    'story_writers/dashboard_story_writer.py',
    'story_writers/morning_brief_writer.py',
    'services/coin_story_inspection.py',
    'services/daily_edition_publication_gate.py',
    'services/evidence_composition_service.py',
    'services/editorial_voice_contract_v1.py',
    'services/intelligence_surface_service.py',
    'services/narrative_context_service.py',
    'services/narrative_feed_builder.py',
    'services/today_relief_appearance_evidence.py',
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
    if (response or {}).get('empty_reason') == EMPTY_CLAIM_EVIDENCE_WITHHELD:
        # Missing claim linkage can be repaired after the completed context was
        # written.  Do not turn that retryable evidence gap into a durable empty
        # response that survives the repair.
        return None
    if (
        (response or {}).get('lead_story') is None
        and isinstance((response or {}).get('errors'), int)
        and not isinstance((response or {}).get('errors'), bool)
        and (response or {}).get('errors') > 0
    ):
        # A bounded rebuild can temporarily lose every candidate when a current
        # dependency cannot be read.  Preserve any previously valid snapshot so
        # the next request can validate it again after the dependency recovers.
        return None

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
    claim_evidence_digest = _response_claim_evidence_digest(payload)
    payload[SNAPSHOT_METADATA_KEY] = {
        'snapshot_version': version,
        'snapshot_family': SNAPSHOT_FAMILY,
        'story_writer_fingerprint': SNAPSHOT_WRITER_FINGERPRINT,
        'source': source,
        'generated_at': generated_at.isoformat() if generated_at else None,
        CLAIM_EVIDENCE_DIGEST_KEY: claim_evidence_digest,
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
    metadata_is_current = (
        metadata.get('snapshot_version') == version
        and metadata.get('snapshot_family') == SNAPSHOT_FAMILY
        and metadata.get('story_writer_fingerprint') == SNAPSHOT_WRITER_FINGERPRINT
    )
    if not metadata_is_current:
        return False
    stored_digest = _response_claim_evidence_digest(response)
    if stored_digest is None:
        return True
    return (
        metadata.get(CLAIM_EVIDENCE_DIGEST_KEY) == stored_digest
        and _current_claim_evidence_digest(response) == stored_digest
        and _current_consequence_matches(response)
    )


def _response_claim_evidence_digest(response) -> str | None:
    lead = (response or {}).get('lead_story')
    lead = lead if isinstance(lead, dict) else {}
    identity = lead.get('publication_identity')
    identity = identity if isinstance(identity, dict) else {}
    if identity.get('semantic_gate_version') != GATE_VERSION:
        return None
    package = lead.get('package')
    package = package if isinstance(package, dict) else {}
    context = package.get('completed_game_context')
    context = context if isinstance(context, dict) else {}
    claim_evidence = lead.get('claim_evidence')
    claim_evidence = claim_evidence if isinstance(claim_evidence, dict) else {}
    return _claim_evidence_digest(
        context,
        claim_evidence.get('relief_appearances'),
    )


def _current_claim_evidence_digest(response) -> str | None:
    lead = (response or {}).get('lead_story')
    lead = lead if isinstance(lead, dict) else {}
    team_id = lead.get('team_id')
    game_pk = lead.get('game_pk')
    if team_id is None or game_pk is None:
        return None

    from models.completed_game_context import CompletedGameContext
    from services.today_relief_appearance_evidence import (
        enrich_today_contexts_with_relief_appearances,
    )

    row = (
        CompletedGameContext.query
        .filter_by(team_id=team_id, game_pk=game_pk)
        .first()
    )
    if row is None:
        return None
    context = row.to_dict()
    [enriched] = enrich_today_contexts_with_relief_appearances([context])
    return _claim_evidence_digest(
        enriched,
        enriched.get('key_relief_appearances'),
    )


def _current_consequence_matches(response) -> bool:
    """Require the cached consequence to match the current governed state."""
    lead = (response or {}).get('lead_story')
    lead = lead if isinstance(lead, dict) else {}
    package = lead.get('package')
    package = package if isinstance(package, dict) else {}
    selection = lead.get('selection')
    selection = selection if isinstance(selection, dict) else {}
    semantic_gate = selection.get('semantic_gate')
    semantic_gate = semantic_gate if isinstance(semantic_gate, dict) else {}

    team_id = lead.get('team_id')
    reference_date = _as_date((response or {}).get('reference_date'))
    primary = package.get('primary_story')
    if (
        team_id is None
        or reference_date is None
        or not isinstance(primary, str)
        or not primary
        or semantic_gate.get('status') != GATE_STATUS_PASS
        or semantic_gate.get('version') != GATE_VERSION
        or 'consequence_key' not in semantic_gate
    ):
        return False

    try:
        from services.bullpen_context import build_team_bullpen_context

        team_context = build_team_bullpen_context(
            team_id,
            reference_date=reference_date,
        )
    except Exception as exc:  # noqa: BLE001 - stale public prose must fail closed
        db.session.rollback()
        logger.warning(
            'Could not validate current Daily Edition consequence for team %s '
            'on %s: %s',
            team_id,
            reference_date,
            exc,
        )
        return False

    if (
        not isinstance(team_context, dict)
        or team_context.get('team_id') != team_id
    ):
        return False

    current_package = dict(package)
    current_package['availability_snapshot'] = team_context.get(
        'bullpen_optionality_context'
    )
    current_package['workload_snapshot'] = team_context.get(
        'bullpen_concentration_context'
    )
    current_key = rendered_team_story_consequence(current_package)
    return (
        current_key == semantic_gate.get('consequence_key')
        and event_consequence_is_compatible(primary, current_key)
    )


def _claim_evidence_digest(context, appearances) -> str:
    context = context if isinstance(context, dict) else {}
    appearances = appearances if isinstance(appearances, list) else []
    basis = {
        'context': {
            key: context.get(key)
            for key in _CLAIM_CONTEXT_FIELDS
        },
        'relief_appearances': _normalized_digest_appearances(appearances),
    }
    return hashlib.sha256(
        json.dumps(basis, sort_keys=True, separators=(',', ':'), default=str)
        .encode('utf-8')
    ).hexdigest()[:20]


def _normalized_digest_appearances(appearances) -> list:
    """Treat omitted and explicit-null optional receipt fields identically."""
    return [
        {
            key: value
            for key, value in appearance.items()
            if value is not None
        }
        if isinstance(appearance, dict)
        else appearance
        for appearance in appearances
    ]


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
