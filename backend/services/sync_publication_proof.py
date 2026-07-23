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


def build_candidate_publication_proof(
    snapshot_id,
    *,
    candidate_required: bool,
    snapshot_loader: Callable | None = None,
    served_snapshot_loader: Callable | None = None,
    availability_reason: Callable | None = None,
) -> dict:
    """Return a JSON-safe proof that the current run's candidate is serving.

    ``candidate_required`` is true for the daily sync and for postgame refreshes
    that changed workload. A no-change postgame pass is allowed to produce no new
    candidate because continuing to serve the prior trusted snapshot is correct.
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

    proof = {
        'status': PROOF_VERIFIED if not reason_codes else PROOF_FAILED,
        'verified': not reason_codes,
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
    return proof


def _failed_proof(*, snapshot_id, reason_codes) -> dict:
    return {
        'status': PROOF_FAILED,
        'verified': False,
        'candidate_required': True,
        'candidate_snapshot_id': snapshot_id,
        'served_snapshot_id': None,
        'reason_codes': _dedupe(reason_codes),
    }


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
