"""Repository and lifecycle service for the immutable Share Artifact domain
(Share Cards — sprint SC-01).

This module is the sanctioned way to create, publish, deduplicate, supersede,
withdraw, and verify share artifacts. It orchestrates the models in
``models.share_artifact`` and the pure hashing in
``services.share_artifact_integrity``; the ORM-level immutability guards in the
model module are the fail-closed backstop beneath it.

Scope reminder (SC-01): domain only. No rendering, no image bytes, no routes,
no analytics event emission, and no Team State eligibility logic (that is SC-02).
Callers supply the ``team_id``, the authorizing ``source_snapshot_id``, and the
already-composed payload; this service persists them immutably.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from models.share_artifact import (
    LIFECYCLE_DRAFT,
    LIFECYCLE_PUBLISHED,
    LIFECYCLE_SUPERSEDED,
    LIFECYCLE_WITHDRAWN,
    LIFECYCLE_TRANSITIONS,
    SHARE_ARTIFACT_SCHEMA_VERSION,
    ShareArtifact,
    ShareArtifactAsset,
    ShareArtifactEvidence,
    ShareArtifactLifecycleError,
    ShareArtifactRelation,
)
from services.share_artifact_integrity import (
    ShareArtifactIntegrityError,
    compute_equivalence_key,
    compute_integrity_hash,
    to_json_safe,
)
from utils.db import db
from utils.time import utc_now_naive


DEFAULT_SOURCE = 'share_cards:sc01'

# The Team State V1 render contract identifier. Callers may override it, but V1
# artifacts target this render version by default.
DEFAULT_RENDER_VERSION = 'team-state-1.0.0'


class ShareArtifactBuildError(ValueError):
    """Raised when a share-artifact build request violates the domain contract."""


@dataclass(frozen=True)
class ShareArtifactEvidenceInput:
    """A caller-supplied piece of evidence to freeze into a share artifact."""

    evidence_key: str
    role: str = 'supporting_evidence'
    claim: Optional[str] = None
    completeness_state: Optional[str] = None
    snapshot: Optional[Mapping[str, Any]] = None
    evidence_object_id: Optional[int] = None


@dataclass(frozen=True)
class ShareArtifactAssetInput:
    """A caller-supplied rendered-asset descriptor.

    SC-01 stores descriptors only; it never generates image bytes. ``content_hash``
    and ``storage_uri`` stay ``None`` until a later rendering phase fills them.
    """

    asset_role: str
    media_type: str
    render_version: Optional[str] = None
    content_hash: Optional[str] = None
    storage_uri: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    byte_size: Optional[int] = None
    asset_metadata: Optional[Mapping[str, Any]] = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _require_text(value, field_name):
    if not isinstance(value, str) or not value.strip():
        raise ShareArtifactBuildError(f'{field_name} must be a non-empty string')
    return value


def _require_int(value, field_name, *, allow_none=False):
    if value is None:
        if allow_none:
            return None
        raise ShareArtifactBuildError(f'{field_name} is required')
    if not isinstance(value, int) or isinstance(value, bool):
        raise ShareArtifactBuildError(f'{field_name} must be an integer')
    return value


def _coerce_evidence_inputs(evidence) -> tuple:
    coerced = []
    for item in evidence or ():
        if isinstance(item, ShareArtifactEvidenceInput):
            coerced.append(item)
        elif isinstance(item, Mapping):
            coerced.append(ShareArtifactEvidenceInput(**item))
        else:
            raise ShareArtifactBuildError(
                'evidence items must be ShareArtifactEvidenceInput or mappings'
            )
    for item in coerced:
        _require_text(item.evidence_key, 'evidence_key')
        _require_text(item.role, 'role')
    return tuple(coerced)


def _coerce_asset_inputs(assets) -> tuple:
    coerced = []
    for item in assets or ():
        if isinstance(item, ShareArtifactAssetInput):
            coerced.append(item)
        elif isinstance(item, Mapping):
            coerced.append(ShareArtifactAssetInput(**item))
        else:
            raise ShareArtifactBuildError(
                'asset items must be ShareArtifactAssetInput or mappings'
            )
    for item in coerced:
        _require_text(item.asset_role, 'asset_role')
        _require_text(item.media_type, 'media_type')
    return tuple(coerced)


def _evidence_input_dicts(evidence_inputs: Sequence[ShareArtifactEvidenceInput]) -> list:
    """Convert evidence inputs to the dict form used for hashing and rows.

    Deterministic ``sort_index`` values are assigned by input position, so
    evidence order is part of an artifact's identity.
    """
    dicts = []
    for index, item in enumerate(evidence_inputs):
        dicts.append({
            'evidence_key': item.evidence_key,
            'role': item.role,
            'claim': item.claim,
            'completeness_state': item.completeness_state,
            'snapshot': to_json_safe(item.snapshot) if item.snapshot is not None else None,
            'evidence_object_id': item.evidence_object_id,
            'sort_index': index,
        })
    return dicts


def _evidence_rows_as_dicts(rows) -> list:
    return [
        {
            'evidence_key': row.evidence_key,
            'role': row.role,
            'claim': row.claim,
            'completeness_state': row.completeness_state,
            'snapshot': row.snapshot,
            'sort_index': row.sort_index,
        }
        for row in rows
    ]


def _equivalence_kwargs_from_fields(
    *, artifact_type, render_version, team_id, source_snapshot_id,
    subject_type, subject_key, product_date, payload, evidence_entries,
    trust_metadata, schema_version,
) -> dict:
    return {
        'artifact_type': artifact_type,
        'render_version': render_version,
        'team_id': team_id,
        'source_snapshot_id': source_snapshot_id,
        'subject_type': subject_type,
        'subject_key': subject_key,
        'product_date': product_date,
        'payload': payload,
        'evidence_entries': evidence_entries,
        'trust_metadata': trust_metadata,
        'schema_version': schema_version,
    }


def _artifact_equivalence_kwargs(artifact: ShareArtifact) -> dict:
    return _equivalence_kwargs_from_fields(
        artifact_type=artifact.artifact_type,
        render_version=artifact.render_version,
        team_id=artifact.team_id,
        source_snapshot_id=artifact.source_snapshot_id,
        subject_type=artifact.subject_type,
        subject_key=artifact.subject_key,
        product_date=artifact.product_date,
        payload=artifact.payload,
        evidence_entries=_evidence_rows_as_dicts(artifact.evidence),
        trust_metadata=artifact.trust_metadata,
        schema_version=artifact.schema_version,
    )


def _compute_integrity_hash_for(artifact: ShareArtifact, *, published_at=None) -> str:
    published = published_at if published_at is not None else artifact.published_at
    return compute_integrity_hash(
        public_id=artifact.public_id,
        published_at=published,
        source_sync_run_id=artifact.source_sync_run_id,
        **_artifact_equivalence_kwargs(artifact),
    )


def _asset_row_from_input(
    asset_input: ShareArtifactAssetInput,
    default_render_version: str,
    sort_index: int,
) -> ShareArtifactAsset:
    render_version = asset_input.render_version or default_render_version
    return ShareArtifactAsset(
        asset_role=asset_input.asset_role,
        media_type=asset_input.media_type,
        render_version=render_version,
        content_hash=asset_input.content_hash,
        storage_uri=asset_input.storage_uri,
        width=asset_input.width,
        height=asset_input.height,
        byte_size=asset_input.byte_size,
        asset_metadata=(
            to_json_safe(asset_input.asset_metadata)
            if asset_input.asset_metadata is not None else None
        ),
        sort_index=sort_index,
    )


# ---------------------------------------------------------------------------
# Public API — deduplication lookups
# ---------------------------------------------------------------------------


def find_published_equivalent(equivalence_key: str, *, session=None) -> Optional[ShareArtifact]:
    """Return the canonical published artifact for ``equivalence_key``, if any.

    At most one published artifact exists per equivalence key (publication
    enforces this); the earliest is returned deterministically.
    """
    session = session or db.session
    return (
        session.query(ShareArtifact)
        .filter(
            ShareArtifact.equivalence_key == equivalence_key,
            ShareArtifact.lifecycle_state == LIFECYCLE_PUBLISHED,
        )
        .order_by(ShareArtifact.id.asc())
        .first()
    )


# ---------------------------------------------------------------------------
# Public API — build / publish
# ---------------------------------------------------------------------------


def build_share_artifact_draft(
    *,
    artifact_type: str,
    team_id: int,
    source_snapshot_id: int,
    payload: Mapping[str, Any],
    render_version: str = DEFAULT_RENDER_VERSION,
    source_sync_run_id: Optional[int] = None,
    subject_type: Optional[str] = None,
    subject_key: Optional[str] = None,
    product_date=None,
    evidence: Sequence = (),
    trust_metadata: Optional[Mapping[str, Any]] = None,
    assets: Sequence = (),
    source: str = DEFAULT_SOURCE,
    session=None,
) -> ShareArtifact:
    """Build, stage, and flush a mutable draft share artifact (not published)."""
    session = session or db.session

    _require_text(artifact_type, 'artifact_type')
    _require_text(render_version, 'render_version')
    _require_text(source, 'source')
    team_id = _require_int(team_id, 'team_id')
    source_snapshot_id = _require_int(source_snapshot_id, 'source_snapshot_id')
    source_sync_run_id = _require_int(
        source_sync_run_id, 'source_sync_run_id', allow_none=True,
    )
    if not isinstance(payload, Mapping):
        raise ShareArtifactBuildError('payload must be a mapping')
    if subject_type is not None:
        _require_text(subject_type, 'subject_type')
    if subject_key is not None:
        _require_text(subject_key, 'subject_key')

    evidence_inputs = _coerce_evidence_inputs(evidence)
    asset_inputs = _coerce_asset_inputs(assets)
    evidence_dicts = _evidence_input_dicts(evidence_inputs)
    normalized_payload = to_json_safe(payload)
    normalized_trust = to_json_safe(trust_metadata or {})

    equivalence_key = compute_equivalence_key(
        **_equivalence_kwargs_from_fields(
            artifact_type=artifact_type,
            render_version=render_version,
            team_id=team_id,
            source_snapshot_id=source_snapshot_id,
            subject_type=subject_type,
            subject_key=subject_key,
            product_date=product_date,
            payload=normalized_payload,
            evidence_entries=evidence_dicts,
            trust_metadata=normalized_trust,
            schema_version=SHARE_ARTIFACT_SCHEMA_VERSION,
        )
    )

    artifact = ShareArtifact(
        public_id=uuid.uuid4().hex,
        artifact_type=artifact_type,
        render_version=render_version,
        team_id=team_id,
        source_snapshot_id=source_snapshot_id,
        source_sync_run_id=source_sync_run_id,
        subject_type=subject_type,
        subject_key=subject_key,
        product_date=product_date,
        lifecycle_state=LIFECYCLE_DRAFT,
        payload=normalized_payload,
        trust_metadata=normalized_trust,
        equivalence_key=equivalence_key,
        integrity_hash=None,
        source=source,
        schema_version=SHARE_ARTIFACT_SCHEMA_VERSION,
    )

    for entry in evidence_dicts:
        artifact.evidence.append(ShareArtifactEvidence(
            evidence_key=entry['evidence_key'],
            role=entry['role'],
            claim=entry['claim'],
            completeness_state=entry['completeness_state'],
            snapshot=entry['snapshot'],
            evidence_object_id=entry['evidence_object_id'],
            sort_index=entry['sort_index'],
        ))

    for index, asset_input in enumerate(asset_inputs):
        artifact.assets.append(
            _asset_row_from_input(asset_input, render_version, index)
        )

    session.add(artifact)
    session.flush()
    return artifact


def publish_share_artifact(
    artifact: ShareArtifact,
    *,
    published_at=None,
    dedup: bool = True,
    session=None,
) -> ShareArtifact:
    """Publish a draft artifact, sealing its content behind an integrity hash.

    If ``dedup`` is set and a published artifact with the same equivalence key
    already exists, the draft is discarded and the existing published artifact
    is returned instead — equivalent artifacts never duplicate.
    """
    session = session or db.session

    if artifact.lifecycle_state == LIFECYCLE_PUBLISHED:
        return artifact
    if artifact.lifecycle_state != LIFECYCLE_DRAFT:
        raise ShareArtifactLifecycleError(
            f'cannot publish artifact in state {artifact.lifecycle_state!r}'
        )

    if dedup:
        existing = find_published_equivalent(artifact.equivalence_key, session=session)
        if existing is not None and existing.id != artifact.id:
            session.delete(artifact)
            session.flush()
            return existing

    published_at = published_at or utc_now_naive()
    artifact.published_at = published_at
    artifact.lifecycle_state = LIFECYCLE_PUBLISHED
    artifact.integrity_hash = _compute_integrity_hash_for(
        artifact, published_at=published_at,
    )
    session.flush()
    return artifact


def publish_new_share_artifact(
    *,
    artifact_type: str,
    team_id: int,
    source_snapshot_id: int,
    payload: Mapping[str, Any],
    render_version: str = DEFAULT_RENDER_VERSION,
    source_sync_run_id: Optional[int] = None,
    subject_type: Optional[str] = None,
    subject_key: Optional[str] = None,
    product_date=None,
    evidence: Sequence = (),
    trust_metadata: Optional[Mapping[str, Any]] = None,
    assets: Sequence = (),
    source: str = DEFAULT_SOURCE,
    published_at=None,
    session=None,
) -> ShareArtifact:
    """Build and publish an artifact, returning an existing equivalent if one
    is already published.

    This is the deduplicating front door: it computes the equivalence key up
    front and short-circuits to the canonical published artifact without
    minting a throwaway draft.
    """
    session = session or db.session

    _require_text(artifact_type, 'artifact_type')
    _require_text(render_version, 'render_version')
    team_id = _require_int(team_id, 'team_id')
    source_snapshot_id = _require_int(source_snapshot_id, 'source_snapshot_id')
    source_sync_run_id = _require_int(
        source_sync_run_id, 'source_sync_run_id', allow_none=True,
    )
    if not isinstance(payload, Mapping):
        raise ShareArtifactBuildError('payload must be a mapping')
    if subject_type is not None:
        _require_text(subject_type, 'subject_type')
    if subject_key is not None:
        _require_text(subject_key, 'subject_key')

    evidence_inputs = _coerce_evidence_inputs(evidence)
    evidence_dicts = _evidence_input_dicts(evidence_inputs)
    equivalence_key = compute_equivalence_key(
        **_equivalence_kwargs_from_fields(
            artifact_type=artifact_type,
            render_version=render_version,
            team_id=team_id,
            source_snapshot_id=source_snapshot_id,
            subject_type=subject_type,
            subject_key=subject_key,
            product_date=product_date,
            payload=to_json_safe(payload),
            evidence_entries=evidence_dicts,
            trust_metadata=to_json_safe(trust_metadata or {}),
            schema_version=SHARE_ARTIFACT_SCHEMA_VERSION,
        )
    )

    existing = find_published_equivalent(equivalence_key, session=session)
    if existing is not None:
        return existing

    draft = build_share_artifact_draft(
        artifact_type=artifact_type,
        team_id=team_id,
        source_snapshot_id=source_snapshot_id,
        payload=payload,
        render_version=render_version,
        source_sync_run_id=source_sync_run_id,
        subject_type=subject_type,
        subject_key=subject_key,
        product_date=product_date,
        evidence=evidence_inputs,
        trust_metadata=trust_metadata,
        assets=assets,
        source=source,
        session=session,
    )
    return publish_share_artifact(
        draft, published_at=published_at, dedup=True, session=session,
    )


# ---------------------------------------------------------------------------
# Public API — lifecycle transitions
# ---------------------------------------------------------------------------


def supersede_share_artifact(
    previous: ShareArtifact,
    replacement: ShareArtifact,
    *,
    relation_metadata: Optional[Mapping[str, Any]] = None,
    superseded_at=None,
    session=None,
) -> ShareArtifactRelation:
    """Mark ``previous`` superseded by the published ``replacement``.

    Records the directed ``supersedes`` relation (replacement -> previous) and
    returns it. Both artifacts must be published; a superseded artifact keeps
    its frozen content and integrity hash.
    """
    session = session or db.session

    if previous.lifecycle_state != LIFECYCLE_PUBLISHED:
        raise ShareArtifactLifecycleError(
            f'only a published artifact can be superseded '
            f'(got {previous.lifecycle_state!r})'
        )
    if replacement.lifecycle_state != LIFECYCLE_PUBLISHED:
        raise ShareArtifactLifecycleError(
            'replacement artifact must be published before it can supersede another'
        )
    if replacement.id == previous.id:
        raise ShareArtifactLifecycleError('an artifact cannot supersede itself')

    previous.lifecycle_state = LIFECYCLE_SUPERSEDED
    previous.superseded_at = superseded_at or utc_now_naive()

    relation = ShareArtifactRelation(
        source_artifact_id=replacement.id,
        target_artifact_id=previous.id,
        relation_type=ShareArtifactRelation.RELATION_SUPERSEDES,
        relation_metadata=(
            to_json_safe(relation_metadata) if relation_metadata is not None else None
        ),
    )
    session.add(relation)
    session.flush()
    return relation


def withdraw_share_artifact(
    artifact: ShareArtifact,
    *,
    reason: Optional[str] = None,
    withdrawn_at=None,
    session=None,
) -> ShareArtifact:
    """Withdraw an artifact. Legal from draft, published, or superseded."""
    session = session or db.session

    if artifact.lifecycle_state == LIFECYCLE_WITHDRAWN:
        return artifact
    if LIFECYCLE_WITHDRAWN not in LIFECYCLE_TRANSITIONS.get(
        artifact.lifecycle_state, frozenset()
    ):
        raise ShareArtifactLifecycleError(
            f'cannot withdraw artifact in state {artifact.lifecycle_state!r}'
        )

    artifact.lifecycle_state = LIFECYCLE_WITHDRAWN
    artifact.withdrawn_at = withdrawn_at or utc_now_naive()
    if reason is not None:
        artifact.withdrawn_reason = reason
    session.flush()
    return artifact


# ---------------------------------------------------------------------------
# Public API — assets (append-only; forward hook for the rendering phase)
# ---------------------------------------------------------------------------


def attach_share_artifact_asset(
    artifact: ShareArtifact,
    asset_input: ShareArtifactAssetInput,
    *,
    session=None,
) -> ShareArtifactAsset:
    """Append an immutable asset descriptor to a draft or published artifact.

    Assets are the one thing that may be added after publication (the rendering
    phase attaches them), which is why they are excluded from the integrity
    hash. Superseded and withdrawn artifacts reject new assets.
    """
    session = session or db.session

    if not isinstance(asset_input, ShareArtifactAssetInput):
        if isinstance(asset_input, Mapping):
            asset_input = ShareArtifactAssetInput(**asset_input)
        else:
            raise ShareArtifactBuildError(
                'asset_input must be a ShareArtifactAssetInput or mapping'
            )
    _require_text(asset_input.asset_role, 'asset_role')
    _require_text(asset_input.media_type, 'media_type')

    if artifact.lifecycle_state not in (LIFECYCLE_DRAFT, LIFECYCLE_PUBLISHED):
        raise ShareArtifactLifecycleError(
            f'cannot attach assets to artifact in state {artifact.lifecycle_state!r}'
        )

    asset = _asset_row_from_input(
        asset_input, artifact.render_version, len(artifact.assets),
    )
    artifact.assets.append(asset)
    session.flush()
    return asset


# ---------------------------------------------------------------------------
# Public API — integrity verification (fail closed)
# ---------------------------------------------------------------------------


def verify_share_artifact_integrity(artifact: ShareArtifact) -> bool:
    """Recompute and verify a published artifact's integrity hash.

    Returns ``True`` when the stored hash matches the artifact's content; raises
    ``ShareArtifactIntegrityError`` otherwise. Drafts have no integrity hash and
    are rejected. This is a fail-closed check: callers must treat any raise as a
    refusal to trust the artifact.
    """
    if artifact.lifecycle_state == LIFECYCLE_DRAFT:
        raise ShareArtifactIntegrityError(
            'draft artifacts have no integrity hash to verify'
        )
    if not artifact.integrity_hash:
        raise ShareArtifactIntegrityError(
            f'share artifact {artifact.public_id!r} is missing an integrity hash'
        )

    expected = _compute_integrity_hash_for(artifact)
    if expected != artifact.integrity_hash:
        raise ShareArtifactIntegrityError(
            f'integrity mismatch for share artifact {artifact.public_id!r}'
        )
    return True
