"""Internal repository / query layer for Team State Share Artifacts and their
generation audit (Share Cards SC-03A).

This is deterministic, internal query support for generation and the later
cutover. No public-serving behavior lives here. Two safety rules govern every
getter that returns an artifact for consumption:

* it verifies the artifact's SC-01 integrity hash and fails closed
  (``ShareArtifactIntegrityError``) on any mismatch, and
* it never serves a withdrawn (or superseded) artifact as the active one, and
  never silently substitutes a different artifact when an exact query was asked.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from models.share_artifact import (
    FROZEN_LIFECYCLE_STATES,
    LIFECYCLE_PUBLISHED,
    ShareArtifact,
)
from models.share_artifact_generation_audit import ShareArtifactGenerationAudit
from services.share_artifacts import verify_share_artifact_integrity
from services.team_state_payload import TEAM_STATE_ARTIFACT_TYPE
from utils.db import db


def _verify_or_fail(artifact: Optional[ShareArtifact], verify: bool) -> Optional[ShareArtifact]:
    """Verify integrity of a published/frozen artifact; fail closed on mismatch."""
    if verify and artifact is not None and artifact.lifecycle_state in FROZEN_LIFECYCLE_STATES:
        verify_share_artifact_integrity(artifact)  # raises ShareArtifactIntegrityError
    return artifact


def _team_state_query(session):
    return session.query(ShareArtifact).filter(
        ShareArtifact.artifact_type == TEAM_STATE_ARTIFACT_TYPE
    )


def get_share_artifact_by_public_id(
    public_id: str,
    *,
    require_active: bool = False,
    verify: bool = True,
    session=None,
) -> Optional[ShareArtifact]:
    """Fetch a share artifact by its opaque public_id.

    With ``require_active`` only a published artifact is returned (a withdrawn or
    superseded artifact yields ``None`` — it is never served as active).
    """
    session = session or db.session
    artifact = (
        session.query(ShareArtifact)
        .filter(ShareArtifact.public_id == public_id)
        .one_or_none()
    )
    if artifact is None:
        return None
    if require_active and artifact.lifecycle_state != LIFECYCLE_PUBLISHED:
        return None
    return _verify_or_fail(artifact, verify)


def get_latest_published_team_state_artifact(
    team_id: int,
    *,
    verify: bool = True,
    session=None,
) -> Optional[ShareArtifact]:
    """The most recently published Team State artifact for a team, or ``None``."""
    session = session or db.session
    artifact = (
        _team_state_query(session)
        .filter(
            ShareArtifact.team_id == team_id,
            ShareArtifact.lifecycle_state == LIFECYCLE_PUBLISHED,
        )
        .order_by(ShareArtifact.published_at.desc(), ShareArtifact.id.desc())
        .first()
    )
    return _verify_or_fail(artifact, verify)


def get_team_state_artifact_for_date(
    team_id: int,
    product_date: date,
    *,
    verify: bool = True,
    session=None,
) -> Optional[ShareArtifact]:
    """The published Team State artifact for an exact team + product date.

    Returns ``None`` when there is no exact match — it never substitutes a
    different date's artifact.
    """
    session = session or db.session
    artifact = (
        _team_state_query(session)
        .filter(
            ShareArtifact.team_id == team_id,
            ShareArtifact.product_date == product_date,
            ShareArtifact.lifecycle_state == LIFECYCLE_PUBLISHED,
        )
        .order_by(ShareArtifact.published_at.desc(), ShareArtifact.id.desc())
        .first()
    )
    return _verify_or_fail(artifact, verify)


def get_team_state_artifact_for_version(
    team_id: int,
    render_version: str,
    *,
    verify: bool = True,
    session=None,
) -> Optional[ShareArtifact]:
    """The most recently published Team State artifact for a team + render version."""
    session = session or db.session
    artifact = (
        _team_state_query(session)
        .filter(
            ShareArtifact.team_id == team_id,
            ShareArtifact.render_version == render_version,
            ShareArtifact.lifecycle_state == LIFECYCLE_PUBLISHED,
        )
        .order_by(ShareArtifact.published_at.desc(), ShareArtifact.id.desc())
        .first()
    )
    return _verify_or_fail(artifact, verify)


def list_recent_team_state_artifacts(
    *,
    team_id: Optional[int] = None,
    include_non_published: bool = False,
    limit: int = 20,
    offset: int = 0,
    session=None,
) -> list:
    """List recent Team State artifacts (metadata inspection, not consumption).

    Integrity is not verified per row here; callers that serve an artifact's
    content must re-fetch it through a verifying getter above. ``offset`` supports
    bounded pagination for internal operator reads.
    """
    session = session or db.session
    query = _team_state_query(session)
    if team_id is not None:
        query = query.filter(ShareArtifact.team_id == team_id)
    if not include_non_published:
        query = query.filter(ShareArtifact.lifecycle_state == LIFECYCLE_PUBLISHED)
    return (
        query.order_by(ShareArtifact.created_at.desc(), ShareArtifact.id.desc())
        .offset(max(0, offset))
        .limit(limit)
        .all()
    )


def list_team_state_artifacts_for_snapshot(
    source_snapshot_id: int,
    *,
    lifecycle_state: Optional[str] = LIFECYCLE_PUBLISHED,
    session=None,
) -> list:
    """All Team State artifacts tied to one source snapshot authority.

    Used by the operator coverage read to account each canonical team against the
    selected snapshot (never a different snapshot/date). Defaults to published
    artifacts; pass ``lifecycle_state=None`` for every lifecycle state.
    """
    session = session or db.session
    query = _team_state_query(session).filter(
        ShareArtifact.source_snapshot_id == source_snapshot_id
    )
    if lifecycle_state is not None:
        query = query.filter(ShareArtifact.lifecycle_state == lifecycle_state)
    return (
        query.order_by(ShareArtifact.published_at.desc(), ShareArtifact.id.desc())
        .all()
    )


def inspect_share_artifact_lifecycle(public_id: str, *, session=None) -> Optional[dict]:
    """Return lifecycle/authority metadata for an artifact without asserting it
    is active (no integrity verification — this is an operator inspection)."""
    session = session or db.session
    artifact = (
        session.query(ShareArtifact)
        .filter(ShareArtifact.public_id == public_id)
        .one_or_none()
    )
    if artifact is None:
        return None
    return {
        'public_id': artifact.public_id,
        'artifact_type': artifact.artifact_type,
        'team_id': artifact.team_id,
        'lifecycle_state': artifact.lifecycle_state,
        'render_version': artifact.render_version,
        'schema_version': artifact.schema_version,
        'source_snapshot_id': artifact.source_snapshot_id,
        'source_sync_run_id': artifact.source_sync_run_id,
        'product_date': artifact.product_date.isoformat() if artifact.product_date else None,
        'integrity_hash': artifact.integrity_hash,
        'published_at': artifact.published_at.isoformat() if artifact.published_at else None,
        'superseded_at': artifact.superseded_at.isoformat() if artifact.superseded_at else None,
        'withdrawn_at': artifact.withdrawn_at.isoformat() if artifact.withdrawn_at else None,
    }


def list_generation_audits(
    *,
    team_id: Optional[int] = None,
    outcome: Optional[str] = None,
    source_snapshot_id: Optional[int] = None,
    product_date: Optional[date] = None,
    limit: int = 50,
    offset: int = 0,
    session=None,
) -> list:
    """List recent generation audit attempts, newest first.

    Column-based operator filters (``team_id`` / ``outcome`` /
    ``source_snapshot_id`` / ``product_date`` on the resolved date) and bounded
    ``offset`` pagination. Reason-code filtering is intentionally not offered here
    (reasons are stored as JSON, not an indexed column)."""
    session = session or db.session
    query = session.query(ShareArtifactGenerationAudit)
    if team_id is not None:
        query = query.filter(ShareArtifactGenerationAudit.team_id == team_id)
    if outcome is not None:
        query = query.filter(ShareArtifactGenerationAudit.outcome == outcome)
    if source_snapshot_id is not None:
        query = query.filter(
            ShareArtifactGenerationAudit.source_snapshot_id == source_snapshot_id
        )
    if product_date is not None:
        query = query.filter(
            ShareArtifactGenerationAudit.resolved_product_date == product_date
        )
    return (
        query.order_by(
            ShareArtifactGenerationAudit.created_at.desc(),
            ShareArtifactGenerationAudit.id.desc(),
        )
        .offset(max(0, offset))
        .limit(limit)
        .all()
    )


def audits_for_snapshot(source_snapshot_id: int, *, session=None) -> list:
    """Every generation audit tied to one source snapshot authority, newest first.

    Unbounded by snapshot (a snapshot has at most a few attempts per team) so the
    coverage read can select each team's most-recent terminal attempt."""
    session = session or db.session
    return (
        session.query(ShareArtifactGenerationAudit)
        .filter(ShareArtifactGenerationAudit.source_snapshot_id == source_snapshot_id)
        .order_by(
            ShareArtifactGenerationAudit.team_id.asc(),
            ShareArtifactGenerationAudit.created_at.desc(),
            ShareArtifactGenerationAudit.id.desc(),
        )
        .all()
    )
