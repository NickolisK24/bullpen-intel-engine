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
    source_authority_type,
)
from models.share_artifact_generation_audit import ShareArtifactGenerationAudit
from models.team_progressive_publication import TeamProgressivePublication
from services.share_artifact_batch_generation import (
    BATCH_OUTCOME_FAILED,
    BATCH_OUTCOME_GENERATED,
    BATCH_OUTCOME_REFUSED,
    BATCH_OUTCOME_REUSED,
)
from services.share_artifact_integrity import ShareArtifactIntegrityError
from services.share_artifact_repository import (
    audits_for_snapshot,
    get_share_artifact_by_public_id,
    list_generation_audits,
    list_recent_team_state_artifacts,
    list_team_state_artifacts_for_snapshot,
)
from services.share_artifacts import verify_share_artifact_integrity
from services.team_directory import valid_team_directory
from services.team_state_source import resolve_latest_trusted_snapshot
from utils.db import db


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

    # This overview is LEAGUE-snapshot coverage. A team-progressive artifact/audit
    # is a different publication authority; exclude that scope by its DURABLE
    # discriminator (never by the bare numeric id) so a checkpoint id that happens to
    # equal this league snapshot id can never inflate or corrupt league coverage.
    # Most-recent terminal audit per team for THIS snapshot (audits arrive already
    # ordered team asc, created_at desc, so the first per team is the latest).
    latest_audit_by_team = {}
    for audit in audits_for_snapshot(
        source_snapshot_id,
        exclude_request_source=TeamProgressivePublication.REQUEST_SOURCE,
        session=session,
    ):
        latest_audit_by_team.setdefault(audit.team_id, audit)

    # Published artifacts tied to this same source snapshot authority.
    artifacts = list_team_state_artifacts_for_snapshot(
        source_snapshot_id, lifecycle_state=LIFECYCLE_PUBLISHED,
        exclude_subject_type=TeamProgressivePublication.SCOPE, session=session,
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


# ---------------------------------------------------------------------------
# Workstream B2 — latest team-progressive publication event (SC-04B v1.2)
# ---------------------------------------------------------------------------
#
# A progressive event is a DIFFERENT publication authority than the league batch:
# one team's completed game publishes that team's artifact progressively, off its
# own immutable checkpoint (never a league snapshot). This summary is deliberately
# SEPARATE from ``build_coverage_overview`` — its counts describe the teams of one
# trigger game and are NEVER combined with the all-or-nothing league batch counts.
# Artifacts are scoped by the DURABLE ``subject_type`` discriminator; the
# progressive ``request_source`` is used only as event/audit context, never as the
# scope authority. A missing event returns cleanly (``has_event=False``), never an
# error.


PROGRESSIVE_STATUS_NONE = 'no_event'
PROGRESSIVE_STATUS_COMPLETE = 'complete'
PROGRESSIVE_STATUS_COMPLETE_WITH_REFUSALS = 'complete_with_refusals'
PROGRESSIVE_STATUS_DEGRADED = 'degraded'
PROGRESSIVE_STATUS_INCOMPLETE = 'incomplete'


def _empty_progressive_event() -> dict:
    return {
        'has_event': False,
        'status': PROGRESSIVE_STATUS_NONE,
        'request_source': TeamProgressivePublication.REQUEST_SOURCE,
        'trigger_game_pk': None,
        'official_game_date': None,
        'event_at': None,
        'checkpoint_ids': [],
        'team_count': 0,
        'attempted_team_count': 0,
        'generated_team_count': 0,
        'reused_team_count': 0,
        'refused_team_count': 0,
        'failed_team_count': 0,
        'missing_team_count': 0,
        'integrity_failure_count': 0,
        'integrity_error_count': 0,
        'teams': [],
    }


def _latest_progressive_checkpoints(session):
    """The latest progressive event's per-team checkpoints (newest trigger game).

    The event is the most-recent trigger game; within it each team is represented by
    its single newest checkpoint (a genuine evidence correction mints a new
    checkpoint, so the newest is authoritative). Returns ``(trigger_game_pk,
    [checkpoints...])`` or ``(None, [])`` when no progressive event exists.
    """
    latest = (
        session.query(TeamProgressivePublication)
        .order_by(
            TeamProgressivePublication.created_at.desc(),
            TeamProgressivePublication.id.desc(),
        )
        .first()
    )
    if latest is None:
        return None, []

    trigger_game_pk = latest.trigger_game_pk
    query = session.query(TeamProgressivePublication)
    if trigger_game_pk is None:
        # A future non-game reconciliation checkpoint (null trigger game) — the event
        # is exactly that one checkpoint, not a whole game's teams.
        return trigger_game_pk, [latest]

    rows = (
        query.filter(TeamProgressivePublication.trigger_game_pk == trigger_game_pk)
        .order_by(
            TeamProgressivePublication.team_id.asc(),
            TeamProgressivePublication.created_at.desc(),
            TeamProgressivePublication.id.desc(),
        )
        .all()
    )
    newest_by_team = {}
    for checkpoint in rows:
        newest_by_team.setdefault(checkpoint.team_id, checkpoint)
    return trigger_game_pk, [newest_by_team[tid] for tid in sorted(newest_by_team)]


def _terminal_progressive_audit(checkpoint_id, session):
    """The latest terminal progressive audit for one checkpoint id, or None.

    Filters to the progressive request source so a league-batch audit that shares a
    numeric source id can never be mistaken for this checkpoint's attempt — the
    checkpoint id is the artifact's ``source_snapshot_id`` for a progressive artifact.
    """
    for audit in audits_for_snapshot(checkpoint_id, session=session):
        if audit.request_source == TeamProgressivePublication.REQUEST_SOURCE:
            return audit
    return None


def build_latest_progressive_event(*, session=None) -> dict:
    """Deterministic summary of the LATEST team-progressive publication event.

    Reports the trigger game, its date, the teams involved, their checkpoint ids,
    per-team outcome (generated / reused / refused / failed / missing), public ids,
    and integrity — all for ONE progressive event, never combined with the league
    batch. Fails closed to an empty (``has_event=False``) result if no progressive
    event exists.
    """
    session = session or db.session
    trigger_game_pk, checkpoints = _latest_progressive_checkpoints(session)
    if not checkpoints:
        return _empty_progressive_event()

    directory = valid_team_directory()
    teams = []
    counts = {
        COVERAGE_GENERATED: 0, COVERAGE_REUSED: 0, COVERAGE_REFUSED: 0,
        COVERAGE_FAILED: 0, COVERAGE_MISSING: 0,
    }
    integrity_failures = 0
    integrity_errors = 0
    event_at = None
    official_game_date = None

    for checkpoint in checkpoints:
        if checkpoint.created_at is not None and (
            event_at is None or checkpoint.created_at.isoformat() > event_at
        ):
            event_at = checkpoint.created_at.isoformat()
        if checkpoint.official_game_date is not None:
            official_game_date = _iso(checkpoint.official_game_date)

        audit = _terminal_progressive_audit(checkpoint.id, session)
        public_id = None
        reason_code = None
        failure_code = None
        attempt_at = None
        integrity_state = INTEGRITY_NOT_APPLICABLE

        if audit is not None:
            state = _AUDIT_OUTCOME_TO_COVERAGE.get(audit.outcome, COVERAGE_FAILED)
            attempt_at = _iso(audit.created_at)
            if state in (COVERAGE_GENERATED, COVERAGE_REUSED):
                public_id = audit.artifact_public_id
                artifact = (
                    get_share_artifact_by_public_id(public_id, verify=False, session=session)
                    if public_id else None
                )
                integrity_state = _integrity_state(artifact)
            elif state == COVERAGE_REFUSED:
                reason_code = _first(audit.blocking_conditions) or _first(audit.reasons)
            elif state == COVERAGE_FAILED:
                failure_code = audit.failure_code
        else:
            state = COVERAGE_MISSING

        if integrity_state == INTEGRITY_MISMATCH:
            integrity_failures += 1
        elif integrity_state == INTEGRITY_ERROR:
            integrity_errors += 1

        if state not in counts:
            raise ShareArtifactOperationsError(f'unexpected progressive state: {state!r}')
        counts[state] += 1

        entry = directory.get(checkpoint.team_id, {})
        teams.append({
            'team_id': checkpoint.team_id,
            'team_name': entry.get('team_name'),
            'team_abbreviation': entry.get('team_abbreviation'),
            'checkpoint_id': checkpoint.id,
            'checkpoint_status': checkpoint.status,
            'checkpoint_trusted': bool(checkpoint.trusted),
            'unavailable_reason': checkpoint.unavailable_reason,
            'state': state,
            'public_id': public_id,
            'reason_code': reason_code,
            'failure_code': failure_code,
            'attempt_at': attempt_at,
            'integrity_state': integrity_state,
            'data_through': _iso(checkpoint.data_through),
        })

    generated = counts[COVERAGE_GENERATED]
    reused = counts[COVERAGE_REUSED]
    refused = counts[COVERAGE_REFUSED]
    failed = counts[COVERAGE_FAILED]
    missing = counts[COVERAGE_MISSING]
    team_count = len(teams)
    attempted = generated + reused + refused + failed

    if team_count != attempted + missing:
        raise ShareArtifactOperationsError(
            'progressive invariant violated: team_count '
            f'{team_count} != attempted {attempted} + missing {missing}'
        )

    status = _derive_progressive_status(
        missing=missing, failed=failed,
        integrity_failures=integrity_failures + integrity_errors, refused=refused,
    )

    return {
        'has_event': True,
        'status': status,
        'request_source': TeamProgressivePublication.REQUEST_SOURCE,
        'trigger_game_pk': trigger_game_pk,
        'official_game_date': official_game_date,
        'event_at': event_at,
        'checkpoint_ids': [checkpoint.id for checkpoint in checkpoints],
        'team_count': team_count,
        'attempted_team_count': attempted,
        'generated_team_count': generated,
        'reused_team_count': reused,
        'refused_team_count': refused,
        'failed_team_count': failed,
        'missing_team_count': missing,
        'integrity_failure_count': integrity_failures,
        'integrity_error_count': integrity_errors,
        'teams': teams,
    }


def _derive_progressive_status(*, missing, failed, integrity_failures, refused) -> str:
    if failed > 0 or integrity_failures > 0:
        return PROGRESSIVE_STATUS_DEGRADED
    if missing > 0:
        return PROGRESSIVE_STATUS_INCOMPLETE
    if refused > 0:
        return PROGRESSIVE_STATUS_COMPLETE_WITH_REFUSALS
    return PROGRESSIVE_STATUS_COMPLETE


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
        # Durable source-authority type (league_snapshot vs team_progressive), read
        # from the artifact's immutable discriminator — never inferred from the id.
        'source_authority_type': source_authority_type(artifact),
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
