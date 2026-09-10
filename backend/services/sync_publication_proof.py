"""Current-run dashboard publication proof.

A healthy previously published dashboard snapshot must never make a new sync look
successful when that sync's candidate was withheld, failed, or was not selected
for serving. This module gives command-line sync runners one fail-closed verdict
that ties the candidate snapshot produced by the run to the snapshot currently
served by the dashboard authority.
"""

from __future__ import annotations

from typing import Callable


PROOF_VERIFIED = 'verified'
PROOF_NO_CANDIDATE_EXPECTED = 'no_candidate_expected'
PROOF_FAILED = 'failed'

# League-publication classification (postgame active-slate semantics). It NEVER
# rewrites ``verified`` — a pending candidate stays honestly unverified — but tells a
# runner whether the candidate is pending only because an otherwise-complete slate
# still contains non-final games (expected during an active slate) or whether the
# withholding is a genuine failure.
LEAGUE_PUBLICATION_PUBLISHED = 'published'
LEAGUE_PUBLICATION_EXPECTED_PENDING_ACTIVE_SLATE = 'expected_pending_active_slate'
LEAGUE_PUBLICATION_FAILED = 'failed'

# Slate-coverage reasons that mean "the slate simply still has non-final games" —
# an expected active-slate pending, not a publication failure.
_ACTIVE_SLATE_NON_FINAL_REASONS = frozenset({
    'scheduled_games_not_final',
    'suspended_games_not_final',
})
# Slate-coverage reasons that are ALWAYS a genuine withholding failure, never an
# expected active-slate pending — a real gap in schedule/ingestion/markers/trust.
_GENUINE_WITHHOLDING_REASONS = frozenset({
    'schedule_missing',
    'no_scheduled_games',
    'final_games_not_fully_ingested',
    'postgame_markers_incomplete',
    'postgame_markers_failed',
    'partial_sync',
})


def build_candidate_publication_proof(
    snapshot_id,
    *,
    candidate_required: bool,
    snapshot_loader: Callable | None = None,
    served_snapshot_loader: Callable | None = None,
    availability_reason: Callable | None = None,
    publication_critical: dict | None = None,
    sync_status: str | None = None,
) -> dict:
    """Return a JSON-safe proof that the current run's candidate is serving.

    ``candidate_required`` is true for the daily sync and for postgame refreshes
    that changed workload. A no-change postgame pass is allowed to produce no new
    candidate because continuing to serve the prior trusted snapshot is correct.

    When supplied, ``publication_critical`` (the daily sync's publication-critical
    completeness result) and ``sync_status`` are attached so the proof EXPLAINS why
    publication was allowed or withheld — in particular, that an overall ``partial``
    SyncRun may still publish a trusted candidate when every publication-critical
    requirement is complete and only best-effort maintenance was deferred.
    """
    if snapshot_loader is None or served_snapshot_loader is None or availability_reason is None:
        from models.dashboard_snapshot import DashboardSnapshot
        from services import dashboard_snapshot as dashboard_snapshot_service
        from utils.db import db

        snapshot_loader = snapshot_loader or (
            lambda candidate_id: db.session.get(DashboardSnapshot, candidate_id)
        )
        served_snapshot_loader = (
            served_snapshot_loader
            or dashboard_snapshot_service.get_latest_valid_dashboard_snapshot
        )
        availability_reason = (
            availability_reason
            or dashboard_snapshot_service.snapshot_unavailable_reason
        )

    normalized_id = _positive_int(snapshot_id)
    if normalized_id is None:
        if candidate_required:
            return _failed_proof(
                snapshot_id=None,
                reason_codes=['candidate_snapshot_missing'],
            )
        return {
            'status': PROOF_NO_CANDIDATE_EXPECTED,
            'verified': True,
            'candidate_required': False,
            'candidate_snapshot_id': None,
            'served_snapshot_id': _snapshot_id(served_snapshot_loader()),
            'league_publication_status': LEAGUE_PUBLICATION_PUBLISHED,
            'reason_codes': [],
        }

    candidate = snapshot_loader(normalized_id)
    if candidate is None:
        return _failed_proof(
            snapshot_id=normalized_id,
            reason_codes=['candidate_snapshot_not_found'],
        )

    served = served_snapshot_loader()
    candidate_reason = availability_reason(candidate)
    reason_codes = []
    if getattr(candidate, 'status', None) != 'ready':
        reason_codes.append('candidate_snapshot_not_ready')
    if getattr(candidate, 'is_published', False) is not True:
        reason_codes.append('candidate_snapshot_not_published')
    if getattr(candidate, 'published_at', None) is None:
        reason_codes.append('candidate_snapshot_published_at_missing')
    if candidate_reason is not None:
        reason_codes.append(str(candidate_reason))
    if served is None:
        reason_codes.append('served_snapshot_missing')
    elif _snapshot_id(served) != normalized_id:
        reason_codes.append('candidate_not_selected_for_serving')

    verified = not reason_codes
    proof = {
        'status': PROOF_VERIFIED if verified else PROOF_FAILED,
        'verified': verified,
        'league_publication_status': _classify_league_publication_status(
            verified=verified, candidate=candidate,
        ),
        'candidate_required': bool(candidate_required),
        'candidate_snapshot_id': normalized_id,
        'served_snapshot_id': _snapshot_id(served),
        'candidate_sync_run_id': getattr(candidate, 'sync_run_id', None),
        'candidate_status': getattr(candidate, 'status', None),
        'candidate_is_published': bool(getattr(candidate, 'is_published', False)),
        'candidate_published_at': _iso(getattr(candidate, 'published_at', None)),
        'candidate_data_through': _iso(getattr(candidate, 'data_through', None)),
        'candidate_availability_reference_date': _iso(
            getattr(candidate, 'availability_reference_date', None)
        ),
        'reason_codes': _dedupe(reason_codes),
    }
    if publication_critical is not None:
        proof['publication_critical'] = publication_critical
    if sync_status is not None:
        proof['sync_status'] = sync_status
    return proof


def _failed_proof(*, snapshot_id, reason_codes) -> dict:
    return {
        'status': PROOF_FAILED,
        'verified': False,
        'league_publication_status': LEAGUE_PUBLICATION_FAILED,
        'candidate_required': True,
        'candidate_snapshot_id': snapshot_id,
        'served_snapshot_id': None,
        'reason_codes': _dedupe(reason_codes),
    }


def _classify_league_publication_status(*, verified, candidate) -> str:
    """Classify WHY the league candidate did or did not publish.

    ``published`` when the candidate verified as serving. Otherwise it inspects the
    candidate's DETAILED slate-coverage object (never just the top-level reason
    string): ``expected_pending_active_slate`` only when the schedule is known, every
    final game is fully ingested (no failed/incomplete/missing markers), and the sole
    reason the slate is incomplete is that non-final games remain; any genuine
    schedule/ingestion/marker/trust gap is ``failed`` (fail closed)."""
    if verified:
        return LEAGUE_PUBLICATION_PUBLISHED
    if _is_expected_active_slate_pending(_candidate_slate_coverage(candidate)):
        return LEAGUE_PUBLICATION_EXPECTED_PENDING_ACTIVE_SLATE
    return LEAGUE_PUBLICATION_FAILED


def _candidate_slate_coverage(candidate):
    payload = getattr(candidate, 'payload', None)
    if not isinstance(payload, dict):
        return None
    freshness = payload.get('freshness')
    if not isinstance(freshness, dict):
        return None
    coverage = freshness.get('slate_coverage')
    return coverage if isinstance(coverage, dict) else None


def _is_expected_active_slate_pending(coverage) -> bool:
    if not coverage or coverage.get('coverage_known') is not True:
        return False
    reason_codes = set(coverage.get('reason_codes') or [])
    # Any genuine withholding reason disqualifies expected-pending (fail closed).
    if reason_codes & _GENUINE_WITHHOLDING_REASONS:
        return False
    # It must actually be pending because non-final games remain.
    if not (reason_codes & _ACTIVE_SLATE_NON_FINAL_REASONS):
        return False
    # A known schedule with at least one scheduled game.
    if int(coverage.get('games_scheduled') or 0) <= 0:
        return False
    # Every final game fully ingested; no failed/incomplete/missing postgame markers.
    markers = coverage.get('marker_counts') or {}
    if markers.get('failed') or markers.get('incomplete') or markers.get('missing'):
        return False
    if int(coverage.get('games_final') or 0) != int(coverage.get('games_fully_ingested') or 0):
        return False
    return True


def _snapshot_id(snapshot):
    return getattr(snapshot, 'id', None) if snapshot is not None else None


def _positive_int(value):
    if isinstance(value, bool) or value in (None, ''):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _iso(value):
    if value is None:
        return None
    return value.isoformat() if hasattr(value, 'isoformat') else str(value)


def _dedupe(values):
    return list(dict.fromkeys(value for value in values if value))
