"""Canonical operational read model for Share Artifact generation health
(Share Cards SC-03B-03).

This is observability only. It reads and summarizes the existing authoritative
durable records — it recalculates no baseball intelligence, invokes no
generation, writes nothing, and creates no Product Intelligence events. It owns
one thing: turning the immutable Share Artifacts, the durable generation audit,
the canonical team directory, the trusted snapshot authority, and the integrity
verifier into a deterministic operator view.

Authoritative sources it reuses (never re-implements):
- immutable Share Artifacts + lifecycle vocabulary   (models.share_artifact, repository)
- durable generation audit + outcome/reason codes    (models.share_artifact_generation_audit)
- canonical team universe + names                     (services.team_directory)
- latest trusted published snapshot authority         (services.team_state_source)
- integrity verification                              (services.share_artifacts)
- automatic-generation configuration                  (app config, SC-03B-02)

Coverage is always tied to ONE source snapshot authority: a team is accounted for
the selected snapshot only by a terminal generation audit for that same snapshot,
or an equivalent published artifact tied to that same source snapshot. An
artifact from another snapshot or product date never satisfies coverage, and
there is no silent fallback to an older artifact.
"""

from __future__ import annotations

from typing import Optional

from models.share_artifact import (
    LIFECYCLE_DRAFT,
    LIFECYCLE_PUBLISHED,
)
from models.share_artifact_generation_audit import ShareArtifactGenerationAudit
from services.share_artifact_batch_generation import (
    BATCH_OUTCOME_FAILED,
    BATCH_OUTCOME_GENERATED,
    BATCH_OUTCOME_REFUSED,
    BATCH_OUTCOME_REUSED,
)
from services.share_artifact_integrity import ShareArtifactIntegrityError
from services.share_artifact_repository import (
    audits_for_snapshot,
    list_generation_audits,
    list_recent_team_state_artifacts,
    list_team_state_artifacts_for_snapshot,
)
from services.share_artifacts import verify_share_artifact_integrity
from services.team_directory import valid_team_directory
from services.team_state_source import resolve_latest_trusted_snapshot


# Terminal coverage state for a canonical team against the selected snapshot.
# generated / reused / refused / failed reuse the batch vocabulary; missing is
# operations-only (no terminal result and no equivalent published artifact).
COVERAGE_GENERATED = BATCH_OUTCOME_GENERATED
COVERAGE_REUSED = BATCH_OUTCOME_REUSED
COVERAGE_REFUSED = BATCH_OUTCOME_REFUSED
COVERAGE_FAILED = BATCH_OUTCOME_FAILED
COVERAGE_MISSING = 'missing'

# Per-artifact integrity state.
INTEGRITY_VERIFIED = 'verified'
INTEGRITY_MISMATCH = 'mismatch'
INTEGRITY_ERROR = 'error'
INTEGRITY_NOT_APPLICABLE = 'not_applicable'

# Plain, non-numeric operational status (no health score).
STATUS_COMPLETE = 'complete'
STATUS_COMPLETE_WITH_REFUSALS = 'complete_with_refusals'
STATUS_DEGRADED = 'degraded'
STATUS_INCOMPLETE = 'incomplete'
STATUS_DISABLED = 'disabled'
STATUS_UNAVAILABLE = 'unavailable'

# Default / max bounded read sizes.
DEFAULT_LIST_LIMIT = 25
MAX_LIST_LIMIT = 100

_AUDIT_OUTCOME_TO_COVERAGE = {
    ShareArtifactGenerationAudit.OUTCOME_PUBLISHED: COVERAGE_GENERATED,
    ShareArtifactGenerationAudit.OUTCOME_REUSED: COVERAGE_REUSED,
    ShareArtifactGenerationAudit.OUTCOME_REFUSED: COVERAGE_REFUSED,
    ShareArtifactGenerationAudit.OUTCOME_FAILED_CLOSED: COVERAGE_FAILED,
}


class ShareArtifactOperationsError(Exception):
    """The operator read model detected impossible accounting.

    Raised instead of presenting a plausible-but-wrong summary, so a coverage bug
    fails closed rather than misleading the operator.
    """


# ---------------------------------------------------------------------------
# Config + integrity helpers
# ---------------------------------------------------------------------------


def autogeneration_enabled() -> bool:
    """Whether automatic post-publication generation (SC-03B-02) is enabled."""
    try:
        from flask import current_app
        return bool(current_app.config.get('SHARE_ARTIFACT_AUTOGENERATION_ENABLED', False))
    except Exception:
        return False


def _integrity_state(artifact) -> str:
    """Verify one artifact's integrity, never mutating it. Bounded per call."""
    if artifact is None:
        return INTEGRITY_NOT_APPLICABLE
    if artifact.lifecycle_state == LIFECYCLE_DRAFT:
        # A draft has no integrity hash by design — not a failure.
        return INTEGRITY_NOT_APPLICABLE
    try:
        verify_share_artifact_integrity(artifact)
        return INTEGRITY_VERIFIED
    except ShareArtifactIntegrityError:
        return INTEGRITY_MISMATCH
    except Exception:
        return INTEGRITY_ERROR


def _coerce_limit(limit) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return DEFAULT_LIST_LIMIT
    if value <= 0:
        return DEFAULT_LIST_LIMIT
    return min(value, MAX_LIST_LIMIT)


def _coerce_offset(offset) -> int:
    try:
        value = int(offset)
    except (TypeError, ValueError):
        return 0
    return max(0, value)


# ---------------------------------------------------------------------------
# Workstream B — coverage overview for the latest trusted snapshot
# ---------------------------------------------------------------------------


def build_coverage_overview(*, session=None) -> dict:
    """Deterministic coverage view for the latest canonical trusted snapshot."""
    enabled = autogeneration_enabled()
    snapshot, authority = resolve_latest_trusted_snapshot()

    if not authority.is_present or not authority.is_trusted:
        return {
            'status': STATUS_UNAVAILABLE,
            'autogeneration_enabled': enabled,
            'reason': (authority.unavailable_reason or 'no_trusted_snapshot'),
            'source_snapshot_id': authority.snapshot_id,
            'product_date': _iso(authority.data_through),
            'snapshot_published_at': _iso(authority.published_at),
            'canonical_team_count': 0,
            'accounted_team_count': 0,
            'generated_team_count': 0,
            'reused_team_count': 0,
            'refused_team_count': 0,
            'failed_team_count': 0,
            'missing_team_count': 0,
            'integrity_failure_count': 0,
            'integrity_error_count': 0,
            'artifact_count': 0,
            'teams': [],
        }

    source_snapshot_id = authority.snapshot_id
    product_date = authority.data_through

    directory = valid_team_directory()
    canonical_team_ids = sorted(directory.keys())

    # Most-recent terminal audit per team for THIS snapshot (audits arrive already
    # ordered team asc, created_at desc, so the first per team is the latest).
    latest_audit_by_team = {}
    for audit in audits_for_snapshot(source_snapshot_id, session=session):
        latest_audit_by_team.setdefault(audit.team_id, audit)

    # Published artifacts tied to this same source snapshot authority.
    artifacts = list_team_state_artifacts_for_snapshot(
        source_snapshot_id, lifecycle_state=LIFECYCLE_PUBLISHED, session=session,
    )
    artifact_by_team = {}
    for artifact in artifacts:
        artifact_by_team.setdefault(artifact.team_id, artifact)

    teams = []
    counts = {
        COVERAGE_GENERATED: 0, COVERAGE_REUSED: 0, COVERAGE_REFUSED: 0,
        COVERAGE_FAILED: 0, COVERAGE_MISSING: 0,
    }
    integrity_failures = 0
    integrity_errors = 0

    for team_id in canonical_team_ids:
        entry = directory[team_id]
        audit = latest_audit_by_team.get(team_id)
        artifact = artifact_by_team.get(team_id)

        public_id = None
        reason_code = None
        failure_code = None
        attempt_at = None

        if audit is not None:
            state = _AUDIT_OUTCOME_TO_COVERAGE.get(audit.outcome, COVERAGE_FAILED)
            attempt_at = _iso(audit.created_at)
            if state in (COVERAGE_GENERATED, COVERAGE_REUSED):
                public_id = audit.artifact_public_id
            elif state == COVERAGE_REFUSED:
                reason_code = _first(audit.blocking_conditions) or _first(audit.reasons)
            elif state == COVERAGE_FAILED:
                failure_code = audit.failure_code
        elif artifact is not None:
            # Defensive: a published artifact tied to this authority with no audit
            # is still accounted for (never missing).
            state = COVERAGE_GENERATED
            public_id = artifact.public_id
        else:
            state = COVERAGE_MISSING

        # Integrity only meaningfully applies to an accounted, published artifact.
        if state in (COVERAGE_GENERATED, COVERAGE_REUSED) and artifact is not None:
            integrity_state = _integrity_state(artifact)
        else:
            integrity_state = INTEGRITY_NOT_APPLICABLE
        if integrity_state == INTEGRITY_MISMATCH:
            integrity_failures += 1
        elif integrity_state == INTEGRITY_ERROR:
            integrity_errors += 1

        if state not in counts:
            # Fail closed on an unexpected/uncounted coverage state rather than
            # silently dropping a team from the accounting.
            raise ShareArtifactOperationsError(f'unexpected coverage state: {state!r}')
        counts[state] += 1
        teams.append({
            'team_id': team_id,
            'team_name': entry.get('team_name'),
            'team_abbreviation': entry.get('team_abbreviation'),
            'state': state,
            'public_id': public_id,
            'reason_code': reason_code,
            'failure_code': failure_code,
            'attempt_at': attempt_at,
            'integrity_state': integrity_state,
            'source_snapshot_id': source_snapshot_id,
            'product_date': _iso(product_date),
        })

    canonical_team_count = len(canonical_team_ids)
    generated = counts[COVERAGE_GENERATED]
    reused = counts[COVERAGE_REUSED]
    refused = counts[COVERAGE_REFUSED]
    failed = counts[COVERAGE_FAILED]
    missing = counts[COVERAGE_MISSING]
    accounted = generated + reused + refused + failed

    # Accounting invariants — fail closed on the impossible.
    if canonical_team_count != accounted + missing:
        raise ShareArtifactOperationsError(
            'coverage invariant violated: canonical_team_count '
            f'{canonical_team_count} != accounted {accounted} + missing {missing}'
        )
    if accounted != generated + reused + refused + failed:
        raise ShareArtifactOperationsError(
            'coverage invariant violated: accounted_team_count '
            f'{accounted} != generated+reused+refused+failed'
        )

    status = _derive_status(
        enabled=enabled, missing=missing, failed=failed,
        integrity_failures=integrity_failures + integrity_errors, refused=refused,
    )

    return {
        'status': status,
        'autogeneration_enabled': enabled,
        'source_snapshot_id': source_snapshot_id,
        'product_date': _iso(product_date),
        'snapshot_published_at': _iso(authority.published_at),
        'canonical_team_count': canonical_team_count,
        'accounted_team_count': accounted,
        'generated_team_count': generated,
        'reused_team_count': reused,
        'refused_team_count': refused,
        'failed_team_count': failed,
        'missing_team_count': missing,
        'integrity_failure_count': integrity_failures,
        'integrity_error_count': integrity_errors,
        'artifact_count': len(artifacts),
        'teams': teams,
    }


def _derive_status(*, enabled, missing, failed, integrity_failures, refused) -> str:
    if not enabled:
        return STATUS_DISABLED
    if missing > 0:
        return STATUS_INCOMPLETE
    if failed > 0 or integrity_failures > 0:
        return STATUS_DEGRADED
    if refused > 0:
        return STATUS_COMPLETE_WITH_REFUSALS
    return STATUS_COMPLETE


# ---------------------------------------------------------------------------
# Workstream C — recent artifacts (bounded, safe projection)
# ---------------------------------------------------------------------------


def list_operational_artifacts(
    *, team_id: Optional[int] = None, limit=DEFAULT_LIST_LIMIT, offset=0, session=None,
) -> dict:
    """Bounded, newest-first recent immutable artifacts for the operator surface.

    Safe projection only — never the raw payload JSON. Integrity is verified for
    the returned page only (bounded)."""
    safe_limit = _coerce_limit(limit)
    safe_offset = _coerce_offset(offset)
    rows = list_recent_team_state_artifacts(
        team_id=team_id, include_non_published=True,
        limit=safe_limit, offset=safe_offset, session=session,
    )
    directory = valid_team_directory()
    artifacts = [_artifact_view(row, directory) for row in rows]
    return {
        'artifacts': artifacts,
        'limit': safe_limit,
        'offset': safe_offset,
        'count': len(artifacts),
        'team_id': team_id,
    }


def _artifact_view(artifact, directory) -> dict:
    entry = directory.get(artifact.team_id, {})
    return {
        'public_id': artifact.public_id,
        'artifact_type': artifact.artifact_type,
        'team_id': artifact.team_id,
        'team_name': entry.get('team_name'),
        'team_abbreviation': entry.get('team_abbreviation'),
        'product_date': _iso(artifact.product_date),
        'source_snapshot_id': artifact.source_snapshot_id,
        'lifecycle_state': artifact.lifecycle_state,
        'schema_version': artifact.schema_version,
        'render_version': artifact.render_version,
        'integrity_state': _integrity_state(artifact),
        'created_at': _iso(artifact.created_at),
        'published_at': _iso(artifact.published_at),
        'superseded_at': _iso(artifact.superseded_at),
        'withdrawn_at': _iso(artifact.withdrawn_at),
    }


# ---------------------------------------------------------------------------
# Workstream D — recent generation audits (bounded, safe projection)
# ---------------------------------------------------------------------------


def list_operational_audits(
    *, team_id: Optional[int] = None, outcome: Optional[str] = None,
    source_snapshot_id: Optional[int] = None, product_date=None,
    limit=DEFAULT_LIST_LIMIT, offset=0, session=None,
) -> dict:
    """Bounded, newest-first recent generation audit attempts.

    Column-based filters only; ``outcome`` is validated against the governed set.
    The audit ``to_dict`` already carries only governed, non-sensitive fields (no
    stack traces)."""
    safe_limit = _coerce_limit(limit)
    safe_offset = _coerce_offset(offset)
    if outcome is not None and outcome not in ShareArtifactGenerationAudit.OUTCOMES:
        raise ShareArtifactOperationsError(f'invalid_outcome_filter:{outcome!r}')
    rows = list_generation_audits(
        team_id=team_id, outcome=outcome, source_snapshot_id=source_snapshot_id,
        product_date=product_date, limit=safe_limit, offset=safe_offset, session=session,
    )
    return {
        'audits': [_audit_view(row) for row in rows],
        'limit': safe_limit,
        'offset': safe_offset,
        'count': len(rows),
        'filters': {
            'team_id': team_id,
            'outcome': outcome,
            'source_snapshot_id': source_snapshot_id,
            'product_date': _iso(product_date),
        },
    }


def _audit_view(audit) -> dict:
    # The model's to_dict is already a safe, governed projection; surface the
    # first refusal reason as a convenience without dropping the full history.
    view = audit.to_dict()
    view['reason_code'] = _first(audit.blocking_conditions) or _first(audit.reasons)
    return view


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _iso(value):
    return value.isoformat() if value is not None else None


def _first(values):
    if not values:
        return None
    for value in values:
        if value:
            return value
    return None
