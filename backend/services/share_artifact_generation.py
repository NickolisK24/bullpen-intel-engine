"""Governed Team State Share Artifact generation orchestration (Share Cards
SC-03A).

This is the authoritative production path that replaces any ad-hoc/legacy card
composition. It orchestrates already-approved components — it neither
regenerates intelligence nor introduces a second deduplication algorithm:

    trusted published snapshot
      -> existing governed Team Operations readiness payload  (resolve_team_readiness_payload)
      -> SC-02 team state source                              (gather_team_state_source)
      -> SC-02 eligibility                                    (evaluate_team_state_eligibility)
      -> SC-02 canonical payload                              (build_team_state_payload)
      -> SC-01 immutable Share Artifact publication           (build_share_artifact_draft / publish_share_artifact)

Every attempt is recorded in the durable generation audit, and publication plus
its audit outcome are committed atomically so no untraceable artifact can exist.
The service fails closed on any operational error and never reports success on a
rollback.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Optional

from models.share_artifact_generation_audit import ShareArtifactGenerationAudit
from services.share_artifacts import (
    build_share_artifact_draft,
    find_published_equivalent,
    publish_share_artifact,
    verify_share_artifact_integrity,
)
from services.team_state_eligibility import evaluate_team_state_eligibility
from services.team_state_payload import (
    TeamStatePayloadError,
    build_team_state_payload,
)
from services.team_state_source import gather_team_state_source
from utils.db import db


# Governed generation outcome codes.
OUTCOME_PUBLISHED = ShareArtifactGenerationAudit.OUTCOME_PUBLISHED
OUTCOME_REUSED = ShareArtifactGenerationAudit.OUTCOME_REUSED
OUTCOME_REFUSED = ShareArtifactGenerationAudit.OUTCOME_REFUSED
OUTCOME_FAILED_CLOSED = ShareArtifactGenerationAudit.OUTCOME_FAILED_CLOSED

# Governed, non-sensitive failure codes for fail-closed operational errors.
FAILURE_READINESS_RESOLUTION = 'readiness_resolution_error'
FAILURE_SOURCE_GATHER = 'source_gather_error'
FAILURE_PAYLOAD_BUILD = 'payload_build_error'
FAILURE_PUBLICATION = 'publication_error'
FAILURE_INTEGRITY = 'integrity_verification_failed'
FAILURE_PERSISTENCE = 'persistence_error'


@dataclass(frozen=True)
class TeamStateGenerationResult:
    """Deterministic result of a Team State generation attempt."""

    outcome: str
    eligible: bool
    created_new: bool
    reused_existing: bool
    team_id: int
    requested_date: Optional[date]
    product_date: Optional[date]
    source_snapshot_id: Optional[int]
    source_sync_run_id: Optional[int]
    payload_version: Optional[str]
    public_id: Optional[str]
    blocking_conditions: tuple
    reasons: tuple
    audit_id: Optional[int]
    failure_code: Optional[str]
    artifact: Optional[Any] = None

    @property
    def published(self) -> bool:
        return self.outcome == OUTCOME_PUBLISHED

    @property
    def refused(self) -> bool:
        return self.outcome == OUTCOME_REFUSED

    @property
    def failed_closed(self) -> bool:
        return self.outcome == OUTCOME_FAILED_CLOSED

    def to_dict(self) -> dict:
        return {
            'outcome': self.outcome,
            'eligible': self.eligible,
            'created_new': self.created_new,
            'reused_existing': self.reused_existing,
            'team_id': self.team_id,
            'requested_date': self.requested_date.isoformat() if self.requested_date else None,
            'product_date': self.product_date.isoformat() if self.product_date else None,
            'source_snapshot_id': self.source_snapshot_id,
            'source_sync_run_id': self.source_sync_run_id,
            'payload_version': self.payload_version,
            'public_id': self.public_id,
            'blocking_conditions': list(self.blocking_conditions),
            'reasons': list(self.reasons),
            'audit_id': self.audit_id,
            'failure_code': self.failure_code,
        }


# ---------------------------------------------------------------------------
# Production readiness resolver — reuses the existing Team Operations pipeline
# ---------------------------------------------------------------------------


def resolve_team_readiness_payload(
    team_id: int,
    *,
    requested_date: Optional[date] = None,
    session=None,
) -> Optional[Mapping[str, Any]]:
    """Resolve the governed Team Operations readiness payload for a team.

    Reuses the exact production recipe behind ``GET
    /api/team-operations/bullpen-readiness`` (the same fatigue-row classification
    and ``assemble_bullpen_readiness`` assembler), so no readiness intelligence
    is duplicated here. Returns ``None`` when no current source inputs exist, so
    the eligibility engine refuses deterministically. Imports are deferred to
    avoid an import cycle with the api layer.
    """
    from api.team_operations import (
        TEAM_OPERATIONS_DEFAULT_LIMIT,
        _availability_reference_date,
        _filter_records_by_team_abbreviation,
        _generated_at,
        _readiness_record,
        _sync_status_payload,
        _team_operations_freshness_metadata,
        _team_operations_trust_metadata,
        _team_payload_from_records,
    )
    from services.availability_snapshot import (
        CURRENT_AVAILABILITY_MODE,
        classify_latest_fatigue_rows,
        latest_fatigue_rows,
    )
    from team_operations import assemble_bullpen_readiness

    sync_status = _sync_status_payload()
    reference_date = _availability_reference_date(sync_status)
    rows = tuple(latest_fatigue_rows(team_id=team_id, limit=TEAM_OPERATIONS_DEFAULT_LIMIT))
    records = tuple(
        _filter_records_by_team_abbreviation(
            classify_latest_fatigue_rows(
                rows,
                reference_date=reference_date,
                mode=CURRENT_AVAILABILITY_MODE,
            ),
        )
    )
    if not records:
        return None

    generated_at = _generated_at(rows)
    return assemble_bullpen_readiness(
        team=_team_payload_from_records(records, team_id=team_id),
        pitcher_records=tuple(_readiness_record(record) for record in records),
        trust_metadata=_team_operations_trust_metadata(
            records, sync_status=sync_status, generated_at=generated_at,
        ),
        freshness=_team_operations_freshness_metadata(
            records, sync_status=sync_status, generated_at=generated_at,
        ),
        generated_at=generated_at,
    )


# ---------------------------------------------------------------------------
# Audit helpers
# ---------------------------------------------------------------------------


def _record_audit(
    session,
    *,
    outcome,
    team_id,
    requested_date,
    resolved_date=None,
    source_snapshot_id=None,
    source_sync_run_id=None,
    payload_version=None,
    eligible=False,
    blocking_conditions=(),
    reasons=(),
    artifact=None,
    created_new=False,
    reused_existing=False,
    actor=None,
    request_source=None,
    failure_code=None,
) -> ShareArtifactGenerationAudit:
    audit = ShareArtifactGenerationAudit(
        team_id=team_id,
        requested_product_date=requested_date,
        resolved_product_date=resolved_date,
        source_snapshot_id=source_snapshot_id,
        source_sync_run_id=source_sync_run_id,
        payload_version=payload_version,
        outcome=outcome,
        eligible=eligible,
        blocking_conditions=list(blocking_conditions or []),
        reasons=list(reasons or []),
        share_artifact_id=artifact.id if artifact is not None else None,
        artifact_public_id=artifact.public_id if artifact is not None else None,
        created_new=created_new,
        reused_existing=reused_existing,
        actor=actor,
        request_source=request_source,
        failure_code=failure_code,
    )
    session.add(audit)
    session.flush()
    return audit


def _result(outcome, *, team_id, requested_date, eligibility=None, source=None,
            artifact=None, created_new=False, reused_existing=False, audit=None,
            failure_code=None) -> TeamStateGenerationResult:
    snapshot = source.snapshot if source is not None else None
    return TeamStateGenerationResult(
        outcome=outcome,
        eligible=eligibility.eligible if eligibility is not None else False,
        created_new=created_new,
        reused_existing=reused_existing,
        team_id=team_id,
        requested_date=requested_date,
        product_date=snapshot.data_through if snapshot is not None else None,
        source_snapshot_id=snapshot.snapshot_id if snapshot is not None else None,
        source_sync_run_id=snapshot.sync_run_id if snapshot is not None else None,
        payload_version=eligibility.payload_version if eligibility is not None else None,
        public_id=artifact.public_id if artifact is not None else None,
        blocking_conditions=eligibility.blocking_conditions if eligibility is not None else (),
        reasons=eligibility.reasons if eligibility is not None else (),
        audit_id=audit.id if audit is not None else None,
        failure_code=failure_code,
        artifact=artifact,
    )


def _fail_closed(
    session, *, team_id, requested_date, failure_code,
    eligibility=None, source=None, actor=None, request_source=None,
) -> TeamStateGenerationResult:
    """Roll back any partial work and record a durable failed-closed attempt."""
    session.rollback()
    snapshot = source.snapshot if source is not None else None
    audit = None
    try:
        audit = _record_audit(
            session,
            outcome=OUTCOME_FAILED_CLOSED,
            team_id=team_id,
            requested_date=requested_date,
            resolved_date=snapshot.data_through if snapshot is not None else None,
            source_snapshot_id=snapshot.snapshot_id if snapshot is not None else None,
            source_sync_run_id=snapshot.sync_run_id if snapshot is not None else None,
            payload_version=eligibility.payload_version if eligibility is not None else None,
            eligible=eligibility.eligible if eligibility is not None else False,
            blocking_conditions=eligibility.blocking_conditions if eligibility is not None else (),
            reasons=eligibility.reasons if eligibility is not None else (),
            actor=actor,
            request_source=request_source,
            failure_code=failure_code,
        )
        session.commit()
    except Exception:
        session.rollback()
        audit = None
    return _result(
        OUTCOME_FAILED_CLOSED,
        team_id=team_id,
        requested_date=requested_date,
        eligibility=eligibility,
        source=source,
        audit=audit,
        failure_code=failure_code,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_team_state_artifact(
    team_id: int,
    *,
    requested_date: Optional[date] = None,
    actor: Optional[str] = None,
    request_source: Optional[str] = None,
    readiness_resolver=None,
    snapshot=None,
    session=None,
) -> TeamStateGenerationResult:
    """Generate (or reuse, or refuse) a Team State Share Artifact for a team.

    Deterministic outcome: ``published`` / ``reused`` / ``refused`` /
    ``failed_closed``. Publication and its durable audit commit atomically;
    refusals and operational failures are also durably audited.

    ``snapshot`` optionally pins the trusted source snapshot authority. When
    omitted (the default and the single-team admin path), the latest published
    daily snapshot is resolved as before. A batch caller that has already
    resolved and validated one shared source snapshot passes it here so every
    team is generated against the identical authority instead of re-resolving it.
    """
    session = session or db.session
    resolver = readiness_resolver or resolve_team_readiness_payload

    # 1. Resolve the governed readiness payload (operational error -> fail closed).
    try:
        readiness = resolver(team_id, requested_date=requested_date, session=session)
    except Exception:
        return _fail_closed(
            session, team_id=team_id, requested_date=requested_date,
            failure_code=FAILURE_READINESS_RESOLUTION, actor=actor, request_source=request_source,
        )

    # 2. Gather the governed source (snapshot authority + team + readiness).
    try:
        source = gather_team_state_source(
            team_id, readiness_payload=readiness, snapshot=snapshot,
            requested_date=requested_date, session=session,
        )
    except Exception:
        return _fail_closed(
            session, team_id=team_id, requested_date=requested_date,
            failure_code=FAILURE_SOURCE_GATHER, actor=actor, request_source=request_source,
        )

    # 3. Deterministic eligibility.
    eligibility = evaluate_team_state_eligibility(source)

    # 4. Refused -> durably audit the refusal, no publication.
    if not eligibility.eligible:
        try:
            audit = _record_audit(
                session,
                outcome=OUTCOME_REFUSED,
                team_id=team_id,
                requested_date=requested_date,
                resolved_date=source.snapshot.data_through,
                source_snapshot_id=source.snapshot.snapshot_id,
                source_sync_run_id=source.snapshot.sync_run_id,
                payload_version=eligibility.payload_version,
                eligible=False,
                blocking_conditions=eligibility.blocking_conditions,
                reasons=eligibility.reasons,
                actor=actor,
                request_source=request_source,
            )
            session.commit()
        except Exception:
            return _fail_closed(
                session, team_id=team_id, requested_date=requested_date,
                failure_code=FAILURE_PERSISTENCE, eligibility=eligibility, source=source,
                actor=actor, request_source=request_source,
            )
        return _result(
            OUTCOME_REFUSED, team_id=team_id, requested_date=requested_date,
            eligibility=eligibility, source=source, audit=audit,
        )

    # 5. Eligible -> build canonical payload, publish (dedup), verify, audit;
    #    publication + audit commit atomically.
    try:
        payload = build_team_state_payload(source)
        kwargs = payload.to_share_artifact_kwargs()
        draft = build_share_artifact_draft(session=session, **kwargs)
        existing = find_published_equivalent(draft.equivalence_key, session=session)
        artifact = publish_share_artifact(draft, dedup=True, session=session)
        verify_share_artifact_integrity(artifact)  # fail closed on tamper/mismatch
        created_new = existing is None
        reused_existing = existing is not None
        outcome = OUTCOME_REUSED if reused_existing else OUTCOME_PUBLISHED
        audit = _record_audit(
            session,
            outcome=outcome,
            team_id=team_id,
            requested_date=requested_date,
            resolved_date=source.snapshot.data_through,
            source_snapshot_id=source.snapshot.snapshot_id,
            source_sync_run_id=source.snapshot.sync_run_id,
            payload_version=eligibility.payload_version,
            eligible=True,
            blocking_conditions=(),
            reasons=eligibility.reasons,
            artifact=artifact,
            created_new=created_new,
            reused_existing=reused_existing,
            actor=actor,
            request_source=request_source,
        )
        session.commit()
    except TeamStatePayloadError:
        return _fail_closed(
            session, team_id=team_id, requested_date=requested_date,
            failure_code=FAILURE_PAYLOAD_BUILD, eligibility=eligibility, source=source,
            actor=actor, request_source=request_source,
        )
    except Exception:
        return _fail_closed(
            session, team_id=team_id, requested_date=requested_date,
            failure_code=FAILURE_PUBLICATION, eligibility=eligibility, source=source,
            actor=actor, request_source=request_source,
        )

    return _result(
        outcome, team_id=team_id, requested_date=requested_date,
        eligibility=eligibility, source=source, artifact=artifact,
        created_new=created_new, reused_existing=reused_existing, audit=audit,
    )
