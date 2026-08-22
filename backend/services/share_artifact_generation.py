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

import inspect
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Mapping, Optional

from models.share_artifact_generation_audit import ShareArtifactGenerationAudit
from services.availability_reference_date import trusted_slate_reference_dates
from services.share_artifacts import (
    build_share_artifact_draft,
    find_published_equivalent,
    publish_share_artifact,
    verify_share_artifact_integrity,
)
from services.team_state_eligibility import evaluate_team_state_eligibility
from services.team_state_payload import (
    TEAM_STATE_LATEST,
    TeamStatePayloadError,
    build_team_state_payload,
)
from services.team_state_source import gather_team_state_source
from services.team_board_delta_substrate import (
    build_arm_read_capture,
    try_build_bullpen_membership_capture,
    try_build_deployment_profile_capture,
    try_build_rest_status_capture,
    try_build_rotation_impact_capture,
    try_build_workload_window_capture,
    try_stamp_prospective_snapshot,
)
from utils.db import db


logger = logging.getLogger(__name__)


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
    # Transient production-proof plumbing. The governed readiness payload that
    # produced this artifact, plus the two reference dates it was produced
    # against. The immutable artifact document deliberately carries none of this
    # (see services.team_state_payload), so the post-publication proof collector
    # would otherwise have no way to observe the runtime evidence vector without
    # recomputing it from later pitcher state. Deliberately absent from
    # ``to_dict()``: this is internal plumbing, not a response shape.
    readiness: Optional[Mapping[str, Any]] = None
    membership_reference_date: Optional[date] = None
    availability_reference_date: Optional[date] = None

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


_RESOLVE_FRESHNESS = object()


def resolve_readiness_reference_dates(
    source_snapshot, *, sync_status=None, snapshot_freshness=_RESOLVE_FRESHNESS,
) -> tuple:
    """The two governed reference dates one readiness read is produced against.

    Returns ``(membership_reference_date, availability_reference_date)``.

    These are different questions and they had been sharing one mutable local,
    which is how the published Team State came to classify arms a day earlier
    than the Team Board, the readiness route, and the calibration shadow — all
    three of which read at the canonical availability reference date.

    * **Membership** is asked on the trusted source's slate (``data_through``).
      The roster authority only resolves for the date its roster snapshot covers;
      once a slate goes final the global availability reference advances past it
      and the read strands as authority-missing (the run-471 progressive refusal
      and the run-476 all-30-team league refusal). Anchoring membership to the
      slate is that repair and it is preserved exactly.
    * **Availability** is asked on the slate plus one day, resolved by the
      canonical owner (``services.availability_reference_date``), because an
      availability read describes the bullpen a reader is about to watch.

    Applies to BOTH trusted sources — a team-progressive checkpoint
    (``subject_type='team_progressive'``) and a trusted/current league serving
    snapshot. Fails closed: with no trusted source, or a source carrying no
    usable ``data_through``, both values stay the live global reference date the
    unanchored read already used.

    ``snapshot_freshness`` lets a caller that has already resolved the serving
    freshness verdict hand it over rather than paying for a second resolution per
    team; omitted, it is resolved here.
    """
    from api.team_operations import _availability_reference_date, _sync_status_payload
    from models.share_artifact import SUBJECT_TYPE_TEAM_PROGRESSIVE
    from services.readiness_snapshot_freshness import serving_snapshot_freshness_authority

    if sync_status is None:
        sync_status = _sync_status_payload()
    if snapshot_freshness is _RESOLVE_FRESHNESS:
        snapshot_freshness = serving_snapshot_freshness_authority(source_snapshot)
    live_reference_date = _availability_reference_date(sync_status)

    is_trusted_source = (
        getattr(source_snapshot, 'subject_type', None) == SUBJECT_TYPE_TEAM_PROGRESSIVE
        or snapshot_freshness is not None
    )
    if not is_trusted_source:
        return live_reference_date, live_reference_date

    membership_reference_date, availability_reference_date = trusted_slate_reference_dates(
        getattr(source_snapshot, 'data_through', None)
    )
    if membership_reference_date is None or availability_reference_date is None:
        return live_reference_date, live_reference_date
    return membership_reference_date, availability_reference_date


def resolve_team_readiness_payload(
    team_id: int,
    *,
    requested_date: Optional[date] = None,
    session=None,
    source_snapshot=None,
    reference_dates_out: Optional[dict] = None,
    arm_reads_out: Optional[dict] = None,
) -> Optional[Mapping[str, Any]]:
    """Resolve the governed Team Operations readiness payload for a team.

    Reuses the exact production recipe behind ``GET
    /api/team-operations/bullpen-readiness`` (the same fatigue-row classification
    and ``assemble_bullpen_readiness`` assembler), so no readiness intelligence
    is duplicated here. Returns ``None`` when no current source inputs exist, so
    the eligibility engine refuses deterministically. Imports are deferred to
    avoid an import cycle with the api layer.

    ``source_snapshot`` optionally pins the serving trusted daily snapshot this read
    is produced from (the Share Artifact batch threads one shared validated
    snapshot). When it is a published, serving, trusted snapshot whose
    ``data_through`` is within the freshness window, the read's freshness is anchored
    to that snapshot's authoritative ``data_through`` instead of a live, global
    ``max(GameLog.game_date)`` recompute that can lag the snapshot. Fails closed: an
    untrusted / stale / non-serving snapshot (or none) keeps the prior conservative
    live freshness. Per-team coverage is untouched — a team whose own active-bullpen
    inputs are insufficient still degrades through the unchanged coverage classifier.

    The two reference dates this read is produced against come from
    :func:`resolve_readiness_reference_dates`: membership on the trusted source's
    slate, availability on the canonical next-day reference. They are distinct
    values and are never collapsed. ``reference_dates_out`` is an optional dict
    the caller supplies to receive the pair actually used, so the production-proof
    artifact records the dates this read classified at rather than re-deriving
    them afterwards. ``arm_reads_out`` receives the exact canonical public Arm
    Reads projected from the already-classified active-bullpen records in this
    same invocation; it never triggers another availability calculation.
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
        resolve_readiness_population,
    )
    from services.availability_snapshot import (
        CURRENT_AVAILABILITY_MODE,
        classify_latest_fatigue_rows,
        latest_fatigue_rows,
    )
    from services.readiness_snapshot_freshness import (
        anchor_sync_status_to_serving_snapshot,
        serving_snapshot_freshness_authority,
    )
    from team_operations import assemble_bullpen_readiness

    sync_status = _sync_status_payload()
    # Resolved once and shared: the reference-date split and the freshness anchor
    # below both need this verdict, and it is not free to compute per team.
    snapshot_freshness = serving_snapshot_freshness_authority(source_snapshot)
    membership_reference_date, availability_reference_date = (
        resolve_readiness_reference_dates(
            source_snapshot, sync_status=sync_status,
            snapshot_freshness=snapshot_freshness,
        )
    )
    if isinstance(reference_dates_out, dict):
        # Record the dates this read actually used, at the moment it used them, so
        # the production-proof artifact observes them instead of re-deriving them.
        reference_dates_out['membership_reference_date'] = membership_reference_date
        reference_dates_out['availability_reference_date'] = availability_reference_date
    if snapshot_freshness is not None:
        # Only the freshness VERDICT is anchored to the serving trusted snapshot, so a
        # current published snapshot is not reported stale merely because the live
        # global game-log recompute (judged against the wall-clock product date) trails
        # it. This is the exact reference-date mismatch that made every team stale.
        sync_status = anchor_sync_status_to_serving_snapshot(sync_status, snapshot_freshness)
    rows = tuple(latest_fatigue_rows(team_id=team_id, limit=TEAM_OPERATIONS_DEFAULT_LIMIT))
    records = tuple(
        _filter_records_by_team_abbreviation(
            classify_latest_fatigue_rows(
                rows,
                reference_date=availability_reference_date,
                mode=CURRENT_AVAILABILITY_MODE,
            ),
        )
    )
    if not records:
        return None

    generated_at = _generated_at(rows)
    # Team State describes the canonical current active bullpen. Starters,
    # injured-list arms, and off-active organizational depth carry fatigue
    # scores too, and before this correction a single one of them classified
    # Unavailable forced the whole team to operationally_stressed. They remain
    # visible as roster and off-active context on the Team Board; they simply do
    # not decide the active bullpen's state. Membership is resolved once and
    # shared with the trust classifier so the roster authority runs once.
    readiness_records, membership = resolve_readiness_population(
        records, team_id=team_id, reference_date=membership_reference_date,
    )
    if isinstance(arm_reads_out, dict):
        try:
            arm_reads_out.update(build_arm_read_capture(
                records=readiness_records,
                team_id=team_id,
                membership=membership,
                membership_reference_date=membership_reference_date,
                availability_reference_date=availability_reference_date,
            ))
        except Exception as exc:  # noqa: BLE001 - optional delta capture is fail closed
            arm_reads_out.clear()
            logger.warning(
                'Prospective Arm Read capture withheld team_id=%s reason=%s.',
                team_id,
                type(exc).__name__,
            )
    return assemble_bullpen_readiness(
        team=_team_payload_from_records(records, team_id=team_id),
        pitcher_records=tuple(_readiness_record(record) for record in readiness_records),
        trust_metadata=_team_operations_trust_metadata(
            records, sync_status=sync_status, generated_at=generated_at,
            team_id=team_id, reference_date=membership_reference_date, membership=membership,
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
            failure_code=None, reference_dates=None) -> TeamStateGenerationResult:
    snapshot = source.snapshot if source is not None else None
    reference_dates = reference_dates if isinstance(reference_dates, dict) else {}
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
        readiness=source.readiness if source is not None else None,
        membership_reference_date=reference_dates.get('membership_reference_date'),
        availability_reference_date=reference_dates.get('availability_reference_date'),
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


def _resolver_accepts(resolver, keyword: str) -> bool:
    """Whether ``resolver`` accepts ``keyword``.

    Lets the production resolver receive the shared serving snapshot for freshness
    anchoring, and the reference-date capture dict for the production proof, while
    injected/legacy resolvers (test doubles) keep their existing signature. Fails
    closed to False when the signature cannot be read.
    """
    try:
        parameters = inspect.signature(resolver).parameters
    except (TypeError, ValueError):
        return False
    if keyword in parameters:
        return True
    return any(
        param.kind == inspect.Parameter.VAR_KEYWORD for param in parameters.values()
    )


def _resolver_accepts_source_snapshot(resolver) -> bool:
    """Backwards-compatible alias for the ``source_snapshot`` probe."""
    return _resolver_accepts(resolver, 'source_snapshot')


def generate_team_state_artifact(
    team_id: int,
    *,
    requested_date: Optional[date] = None,
    actor: Optional[str] = None,
    request_source: Optional[str] = None,
    readiness_resolver=None,
    snapshot=None,
    source_authority=None,
    session=None,
) -> TeamStateGenerationResult:
    """Generate (or reuse, or refuse) a Team State Share Artifact for a team.

    Deterministic outcome: ``published`` / ``reused`` / ``refused`` /
    ``failed_closed``. Publication and its durable audit commit atomically;
    refusals and operational failures are also durably audited.

    ``snapshot`` optionally pins the trusted LEAGUE source snapshot authority. When
    omitted (the default and the single-team admin path), the latest published
    daily snapshot is resolved as before. A batch caller that has already
    resolved and validated one shared source snapshot passes it here so every
    team is generated against the identical authority instead of re-resolving it.

    ``source_authority`` supplies a pre-built team-scoped ``TeamStateSnapshotAuthority``
    directly — the seam used by progressive per-team publication, where the trusted
    source is a team progressive checkpoint (its own final-game evidence verdict),
    not a league snapshot. It takes precedence over ``snapshot`` for both the
    freshness anchor and the eligibility source authority, so a completed game can
    publish its two teams independently without any league snapshot. The entire
    readiness / eligibility / payload / publish / dedup / integrity path below is
    reused unchanged; only the trusted source object differs.
    """
    session = session or db.session
    resolver = readiness_resolver or resolve_team_readiness_payload

    # 1. Resolve the governed readiness payload (operational error -> fail closed).
    #    Thread the trusted source (team-scoped authority when progressive, else the
    #    shared league serving snapshot) so the resolver anchors the read's freshness
    #    to the source it is generated from. Passed only when the resolver accepts it,
    #    so injected/legacy resolvers keep working unchanged.
    freshness_source = source_authority if source_authority is not None else snapshot
    resolver_kwargs = {'requested_date': requested_date, 'session': session}
    if _resolver_accepts(resolver, 'source_snapshot'):
        resolver_kwargs['source_snapshot'] = freshness_source
    # Capture the two reference dates the read is actually produced against, so the
    # production proof observes them rather than re-deriving them after the fact.
    reference_dates: dict = {}
    if _resolver_accepts(resolver, 'reference_dates_out'):
        resolver_kwargs['reference_dates_out'] = reference_dates
    arm_read_capture: dict = {}
    if _resolver_accepts(resolver, 'arm_reads_out'):
        resolver_kwargs['arm_reads_out'] = arm_read_capture
    try:
        readiness = resolver(team_id, **resolver_kwargs)
    except Exception:
        return _fail_closed(
            session, team_id=team_id, requested_date=requested_date,
            failure_code=FAILURE_READINESS_RESOLUTION, actor=actor, request_source=request_source,
        )

    # 2. Gather the governed source (snapshot/team-scoped authority + team + readiness).
    try:
        source = gather_team_state_source(
            team_id, readiness_payload=readiness, snapshot=snapshot,
            source_authority=source_authority,
            requested_date=requested_date, session=session,
        )
    except Exception:
        return _fail_closed(
            session, team_id=team_id, requested_date=requested_date,
            failure_code=FAILURE_SOURCE_GATHER, actor=actor, request_source=request_source,
        )

    # 3. Deterministic eligibility (stamped with the version we will publish).
    eligibility = evaluate_team_state_eligibility(source, payload_version=TEAM_STATE_LATEST)

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
            reference_dates=reference_dates,
        )

    # 5. Eligible -> build canonical payload, publish (dedup), verify, audit;
    #    publication + audit commit atomically.
    try:
        payload = build_team_state_payload(source, version=TEAM_STATE_LATEST)
        kwargs = payload.to_share_artifact_kwargs()
        # Stamp the DURABLE source-authority discriminator into the artifact's
        # immutable identity. subject_type/subject_key are part of the equivalence +
        # integrity contract, so a team-progressive artifact records that its trusted
        # source is a team progressive checkpoint (not a league snapshot) and can
        # never be confused with a league artifact even if their numeric
        # source_snapshot_id values collide. League generation leaves both None, so
        # legacy/league artifacts keep their exact prior identity and dedup behavior.
        kwargs['subject_type'] = source.snapshot.subject_type
        kwargs['subject_key'] = source.snapshot.subject_key
        draft = build_share_artifact_draft(session=session, **kwargs)
        existing = find_published_equivalent(draft.equivalence_key, session=session)
        artifact = publish_share_artifact(draft, dedup=True, session=session)
        verify_share_artifact_integrity(artifact)  # fail closed on tamper/mismatch
        created_new = existing is None
        reused_existing = existing is not None
        outcome = OUTCOME_REUSED if reused_existing else OUTCOME_PUBLISHED
        # TB-09A is prospective: capture comparison authority only beside a newly
        # created immutable artifact. Reused historical artifacts are deliberately
        # not backfilled. Capture is fail-closed for comparison but non-blocking for
        # the already-authoritative Share Artifact publication.
        if created_new:
            workload_window_capture = try_build_workload_window_capture(
                snapshot=snapshot,
                team_id=team_id,
            ) if snapshot is not None else None
            rotation_impact_capture = try_build_rotation_impact_capture(
                snapshot=snapshot,
                team_id=team_id,
            ) if snapshot is not None else None
            bullpen_membership_capture = try_build_bullpen_membership_capture(
                snapshot=snapshot,
                team_id=team_id,
            ) if snapshot is not None else None
            deployment_profile_capture = try_build_deployment_profile_capture(
                snapshot=snapshot,
                team_id=team_id,
            ) if snapshot is not None else None
            rest_status_capture = try_build_rest_status_capture(
                snapshot=snapshot,
                team_id=team_id,
            ) if snapshot is not None else None
            try_stamp_prospective_snapshot(
                source=source,
                readiness=readiness,
                artifact=artifact,
                arm_read_capture=arm_read_capture or None,
                workload_window_capture=workload_window_capture,
                rotation_impact_capture=rotation_impact_capture,
                bullpen_membership_capture=bullpen_membership_capture,
                deployment_profile_capture=deployment_profile_capture,
                rest_status_capture=rest_status_capture,
                session=session,
            )
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
        reference_dates=reference_dates,
    )
