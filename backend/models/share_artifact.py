"""Immutable Share Artifact domain models (Share Cards — sprint SC-01).

A *share artifact* is the durable, immutable record of a shareable unit of
BaseballOS intelligence: the domain object a later rendering phase will turn
into a card image / Open Graph surface. This module intentionally contains
**no rendering, no image generation, and no web surface**. SC-01 exists only to
make it impossible for future code to treat a published card as mutable
marketing copy.

Canonical identity and authority fields:

* ``public_id`` — the opaque, externally-referenceable public identifier for an
  artifact (the canonical domain/API name; persisted on the ``public_id``
  column).
* ``team_id`` — the team the artifact is about (Team State V1 subject).
* ``source_snapshot_id`` — the trusted, published snapshot that authorized
  generation. Required on every artifact; captured as a durable reference so
  the immutable card records exactly which trusted source produced it.
* ``source_sync_run_id`` — an optional sync-run reference for traceability.

Versioning uses semantic contract identifier strings:

* ``schema_version`` — e.g. ``"1.0.0"`` (the normalized document contract).
* ``render_version`` — e.g. ``"team-state-1.0.0"`` (the render contract the
  payload targets).

The generic ``subject_type`` / ``subject_key`` columns are retained only as
additive, future extensibility; they never replace the explicit V1 ``team_id``
and trusted-source authority fields.

Domain guarantees, enforced here at the ORM layer:

* A published artifact's substance — its identity, authority references,
  payload, cited evidence, captured timestamps, render version, and trust
  metadata — is frozen. After publication only lifecycle transitions
  (``supersede`` / ``withdraw``) remain legal.
* Illegal lifecycle transitions fail closed at flush time.
* Assets (the eventual rendered representations) are append-only children that
  a later rendering phase attaches; SC-01 creates the table but renders
  nothing and never populates image bytes.

Lifecycle-analytics note: any future emission of share-lifecycle signals reuses
the existing Product Intelligence / first-party measurement system. This module
deliberately introduces **no** second analytics subsystem and emits no events.
"""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm.attributes import get_history

from utils.db import db
from utils.time import utc_now_naive


# Semantic version of the normalized integrity/equivalence document contract.
# Bumping it deliberately invalidates the integrity hash and equivalence key of
# every artifact minted under a prior structure, so it must change only when the
# normalized document shape changes.
SHARE_ARTIFACT_SCHEMA_VERSION = '1.0.0'


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

LIFECYCLE_DRAFT = 'draft'
LIFECYCLE_PUBLISHED = 'published'
LIFECYCLE_SUPERSEDED = 'superseded'
LIFECYCLE_WITHDRAWN = 'withdrawn'

LIFECYCLE_STATES = (
    LIFECYCLE_DRAFT,
    LIFECYCLE_PUBLISHED,
    LIFECYCLE_SUPERSEDED,
    LIFECYCLE_WITHDRAWN,
)

# States in which the artifact's substance is frozen and only lifecycle
# transitions remain legal.
FROZEN_LIFECYCLE_STATES = frozenset({
    LIFECYCLE_PUBLISHED,
    LIFECYCLE_SUPERSEDED,
    LIFECYCLE_WITHDRAWN,
})

# The only legal lifecycle transitions. Absence from this map means terminal.
LIFECYCLE_TRANSITIONS = {
    LIFECYCLE_DRAFT: frozenset({LIFECYCLE_PUBLISHED, LIFECYCLE_WITHDRAWN}),
    LIFECYCLE_PUBLISHED: frozenset({LIFECYCLE_SUPERSEDED, LIFECYCLE_WITHDRAWN}),
    LIFECYCLE_SUPERSEDED: frozenset({LIFECYCLE_WITHDRAWN}),
    LIFECYCLE_WITHDRAWN: frozenset(),
}

# Column attributes that become immutable once an artifact reaches a frozen
# lifecycle state. Lifecycle columns (``lifecycle_state``, ``superseded_at``,
# ``withdrawn_at``, ``withdrawn_reason``, ``updated_at``) are intentionally
# absent so the legal transitions can still be recorded.
FROZEN_ARTIFACT_ATTRIBUTES = frozenset({
    'public_id',
    'artifact_type',
    'render_version',
    'team_id',
    'source_snapshot_id',
    'source_sync_run_id',
    'subject_type',
    'subject_key',
    'product_date',
    'payload',
    'trust_metadata',
    'integrity_hash',
    'equivalence_key',
    'source',
    'schema_version',
    'created_at',
    'published_at',
})


class ShareArtifactImmutableError(Exception):
    """Raised when code attempts to mutate frozen state on a published artifact."""


class ShareArtifactLifecycleError(Exception):
    """Raised when an illegal share-artifact lifecycle transition is attempted."""


def _iso(value):
    return value.isoformat() if value is not None else None


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ShareArtifact(db.Model):
    """An immutable, shareable unit of intelligence.

    A draft is fully mutable. Once published its substance is frozen forever;
    only supersede/withdraw lifecycle transitions remain legal.
    """

    __tablename__ = 'share_artifacts'

    __table_args__ = (
        db.UniqueConstraint('public_id', name='uq_share_artifacts_public_id'),
        db.CheckConstraint(
            "lifecycle_state IN ('draft', 'published', 'superseded', 'withdrawn')",
            name='ck_share_artifacts_lifecycle_state',
        ),
        db.Index('ix_share_artifacts_team', 'team_id'),
        db.Index('ix_share_artifacts_team_state', 'team_id', 'lifecycle_state'),
        db.Index('ix_share_artifacts_source_snapshot', 'source_snapshot_id'),
        db.Index('ix_share_artifacts_type_team', 'artifact_type', 'team_id'),
        db.Index(
            'ix_share_artifacts_equivalence_state',
            'equivalence_key', 'lifecycle_state',
        ),
        db.Index('ix_share_artifacts_lifecycle_state', 'lifecycle_state'),
        db.Index('ix_share_artifacts_product_date', 'product_date'),
    )

    id = db.Column(db.Integer, primary_key=True)

    # Opaque, externally-referenceable public identity (public_id contract).
    public_id = db.Column(db.String(64), nullable=False)

    # The kind of card and the render contract version its payload targets.
    artifact_type = db.Column(db.String(80), nullable=False)
    render_version = db.Column(db.String(64), nullable=False)

    # Explicit V1 subject + trusted-source authority.
    team_id = db.Column(db.Integer, nullable=False)
    source_snapshot_id = db.Column(db.Integer, nullable=False)
    source_sync_run_id = db.Column(
        db.Integer, db.ForeignKey('sync_runs.id'), nullable=True,
    )

    # Additive, future extensibility only — never a substitute for team_id.
    subject_type = db.Column(db.String(40), nullable=True)
    subject_key = db.Column(db.String(200), nullable=True)
    product_date = db.Column(db.Date, nullable=True)

    lifecycle_state = db.Column(
        db.String(20), nullable=False, default=LIFECYCLE_DRAFT,
    )

    # Normalized card content and captured trust posture. Frozen at publish.
    payload = db.Column(db.JSON, nullable=False)
    trust_metadata = db.Column(db.JSON, nullable=False, default=dict)

    # Deterministic fingerprints. ``equivalence_key`` is available from draft
    # time and drives deduplication; ``integrity_hash`` binds the published
    # instance (including its published timestamp) and is set at publish.
    equivalence_key = db.Column(db.String(64), nullable=False)
    integrity_hash = db.Column(db.String(64), nullable=True)

    source = db.Column(db.String(120), nullable=False)
    schema_version = db.Column(
        db.String(20), nullable=False, default=SHARE_ARTIFACT_SCHEMA_VERSION,
    )

    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now_naive, onupdate=utc_now_naive,
    )
    published_at = db.Column(db.DateTime, nullable=True)
    superseded_at = db.Column(db.DateTime, nullable=True)
    withdrawn_at = db.Column(db.DateTime, nullable=True)
    withdrawn_reason = db.Column(db.String(200), nullable=True)

    evidence = db.relationship(
        'ShareArtifactEvidence',
        backref='share_artifact',
        cascade='all, delete-orphan',
        lazy='selectin',
        order_by='ShareArtifactEvidence.sort_index',
    )
    assets = db.relationship(
        'ShareArtifactAsset',
        backref='share_artifact',
        cascade='all, delete-orphan',
        lazy='selectin',
        order_by='ShareArtifactAsset.sort_index',
    )
    outgoing_relations = db.relationship(
        'ShareArtifactRelation',
        foreign_keys='ShareArtifactRelation.source_artifact_id',
        backref='source_artifact',
        cascade='all, delete-orphan',
        lazy='selectin',
    )
    incoming_relations = db.relationship(
        'ShareArtifactRelation',
        foreign_keys='ShareArtifactRelation.target_artifact_id',
        backref='target_artifact',
        lazy='selectin',
    )

    @property
    def is_draft(self) -> bool:
        return self.lifecycle_state == LIFECYCLE_DRAFT

    @property
    def is_published(self) -> bool:
        return self.lifecycle_state == LIFECYCLE_PUBLISHED

    @property
    def is_frozen(self) -> bool:
        """True once the artifact's substance can no longer change."""
        return self.lifecycle_state in FROZEN_LIFECYCLE_STATES

    def can_transition_to(self, new_state: str) -> bool:
        return new_state in LIFECYCLE_TRANSITIONS.get(self.lifecycle_state, frozenset())

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'public_id': self.public_id,
            'artifact_type': self.artifact_type,
            'render_version': self.render_version,
            'team_id': self.team_id,
            'source_snapshot_id': self.source_snapshot_id,
            'source_sync_run_id': self.source_sync_run_id,
            'subject_type': self.subject_type,
            'subject_key': self.subject_key,
            'product_date': _iso(self.product_date),
            'lifecycle_state': self.lifecycle_state,
            'payload': self.payload,
            'trust_metadata': dict(self.trust_metadata or {}),
            'equivalence_key': self.equivalence_key,
            'integrity_hash': self.integrity_hash,
            'source': self.source,
            'schema_version': self.schema_version,
            'created_at': _iso(self.created_at),
            'updated_at': _iso(self.updated_at),
            'published_at': _iso(self.published_at),
            'superseded_at': _iso(self.superseded_at),
            'withdrawn_at': _iso(self.withdrawn_at),
            'withdrawn_reason': self.withdrawn_reason,
            'evidence': [item.to_dict() for item in self.evidence],
            'assets': [asset.to_dict() for asset in self.assets],
        }


class ShareArtifactEvidence(db.Model):
    """An immutable snapshot of one piece of evidence backing a share artifact.

    Evidence is captured *by value* (an ``evidence_key`` plus a frozen
    ``snapshot`` of the cited values), so a published artifact stays valid and
    self-contained even if the upstream evidence object is later recomputed or
    removed. ``evidence_object_id`` is a soft, non-enforced pointer for
    provenance only.
    """

    __tablename__ = 'share_artifact_evidence'

    __table_args__ = (
        db.UniqueConstraint(
            'share_artifact_id', 'sort_index',
            name='uq_share_artifact_evidence_order',
        ),
        db.Index('ix_share_artifact_evidence_artifact', 'share_artifact_id'),
        db.Index('ix_share_artifact_evidence_key', 'evidence_key'),
    )

    id = db.Column(db.Integer, primary_key=True)
    share_artifact_id = db.Column(
        db.Integer,
        db.ForeignKey('share_artifacts.id'),
        nullable=False,
    )
    evidence_key = db.Column(db.String(220), nullable=False)
    role = db.Column(db.String(60), nullable=False, default='supporting_evidence')
    claim = db.Column(db.Text, nullable=True)
    completeness_state = db.Column(db.String(20), nullable=True)
    snapshot = db.Column(db.JSON, nullable=True)
    evidence_object_id = db.Column(db.Integer, nullable=True)
    sort_index = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'share_artifact_id': self.share_artifact_id,
            'evidence_key': self.evidence_key,
            'role': self.role,
            'claim': self.claim,
            'completeness_state': self.completeness_state,
            'snapshot': self.snapshot,
            'evidence_object_id': self.evidence_object_id,
            'sort_index': self.sort_index,
            'created_at': _iso(self.created_at),
        }


class ShareArtifactAsset(db.Model):
    """A rendered representation of a share artifact.

    SC-01 creates this table as the forward hook for the rendering phase but
    never populates image bytes. Assets are append-only children: a later
    rendering phase attaches them, and each row is immutable once created.
    Because assets are attached *after* publication they are deliberately not
    part of the artifact's integrity hash.
    """

    __tablename__ = 'share_artifact_assets'

    __table_args__ = (
        db.UniqueConstraint(
            'share_artifact_id', 'asset_role', 'render_version',
            name='uq_share_artifact_assets_role_version',
        ),
        db.Index('ix_share_artifact_assets_artifact', 'share_artifact_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    share_artifact_id = db.Column(
        db.Integer,
        db.ForeignKey('share_artifacts.id'),
        nullable=False,
    )
    asset_role = db.Column(db.String(60), nullable=False)
    media_type = db.Column(db.String(80), nullable=False)
    render_version = db.Column(db.String(64), nullable=False)
    content_hash = db.Column(db.String(64), nullable=True)
    storage_uri = db.Column(db.String(500), nullable=True)
    width = db.Column(db.Integer, nullable=True)
    height = db.Column(db.Integer, nullable=True)
    byte_size = db.Column(db.Integer, nullable=True)
    asset_metadata = db.Column(db.JSON, nullable=True)
    sort_index = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'share_artifact_id': self.share_artifact_id,
            'asset_role': self.asset_role,
            'media_type': self.media_type,
            'render_version': self.render_version,
            'content_hash': self.content_hash,
            'storage_uri': self.storage_uri,
            'width': self.width,
            'height': self.height,
            'byte_size': self.byte_size,
            'asset_metadata': self.asset_metadata,
            'sort_index': self.sort_index,
            'created_at': _iso(self.created_at),
        }


class ShareArtifactRelation(db.Model):
    """A directed, immutable edge between two share artifacts.

    The canonical use is ``supersedes`` (a newer artifact supersedes an older
    one), but the table also models ``derived_from`` and ``variant_of`` edges
    so the artifact graph can grow without schema churn.
    """

    __tablename__ = 'share_artifact_relations'

    RELATION_SUPERSEDES = 'supersedes'
    RELATION_DERIVED_FROM = 'derived_from'
    RELATION_VARIANT_OF = 'variant_of'
    RELATION_TYPES = (RELATION_SUPERSEDES, RELATION_DERIVED_FROM, RELATION_VARIANT_OF)

    __table_args__ = (
        db.UniqueConstraint(
            'source_artifact_id', 'target_artifact_id', 'relation_type',
            name='uq_share_artifact_relations_edge',
        ),
        db.CheckConstraint(
            "relation_type IN ('supersedes', 'derived_from', 'variant_of')",
            name='ck_share_artifact_relations_type',
        ),
        db.CheckConstraint(
            'source_artifact_id <> target_artifact_id',
            name='ck_share_artifact_relations_no_self',
        ),
        db.Index('ix_share_artifact_relations_source', 'source_artifact_id'),
        db.Index('ix_share_artifact_relations_target', 'target_artifact_id'),
        db.Index('ix_share_artifact_relations_type', 'relation_type'),
    )

    id = db.Column(db.Integer, primary_key=True)
    source_artifact_id = db.Column(
        db.Integer,
        db.ForeignKey('share_artifacts.id'),
        nullable=False,
    )
    target_artifact_id = db.Column(
        db.Integer,
        db.ForeignKey('share_artifacts.id'),
        nullable=False,
    )
    relation_type = db.Column(db.String(40), nullable=False)
    relation_metadata = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'source_artifact_id': self.source_artifact_id,
            'target_artifact_id': self.target_artifact_id,
            'relation_type': self.relation_type,
            'relation_metadata': self.relation_metadata,
            'created_at': _iso(self.created_at),
        }


# ---------------------------------------------------------------------------
# Immutability + lifecycle enforcement (fail closed at flush time)
# ---------------------------------------------------------------------------


def _changed_column_keys(target) -> set:
    """Return the set of mapped column keys with a pending value change."""
    state = sa_inspect(target)
    changed = set()
    for attr in state.mapper.column_attrs:
        if get_history(target, attr.key).has_changes():
            changed.add(attr.key)
    return changed


def _previous_lifecycle_state(target) -> str:
    """The persisted lifecycle state before the pending flush."""
    history = get_history(target, 'lifecycle_state')
    if history.deleted:
        return history.deleted[0]
    return target.lifecycle_state


@event.listens_for(ShareArtifact, 'before_update')
def _share_artifact_before_update(mapper, connection, target):
    changed = _changed_column_keys(target)
    if not changed:
        return

    previous_state = _previous_lifecycle_state(target)
    new_state = target.lifecycle_state

    # 1. Only legal lifecycle transitions are permitted.
    if new_state != previous_state:
        legal = LIFECYCLE_TRANSITIONS.get(previous_state, frozenset())
        if new_state not in legal:
            raise ShareArtifactLifecycleError(
                f'illegal share artifact transition {previous_state!r} -> '
                f'{new_state!r} (public_id={target.public_id!r})'
            )

    # 2. Once frozen, no substantive column may change.
    if previous_state in FROZEN_LIFECYCLE_STATES:
        illegal = sorted(changed & FROZEN_ARTIFACT_ATTRIBUTES)
        if illegal:
            raise ShareArtifactImmutableError(
                f'immutable field(s) {illegal} changed on {previous_state} '
                f'share artifact (public_id={target.public_id!r})'
            )


@event.listens_for(ShareArtifact, 'before_delete')
def _share_artifact_before_delete(mapper, connection, target):
    if target.lifecycle_state in FROZEN_LIFECYCLE_STATES:
        raise ShareArtifactImmutableError(
            f'{target.lifecycle_state} share artifact cannot be deleted '
            f'(public_id={target.public_id!r})'
        )


@event.listens_for(ShareArtifactEvidence, 'before_insert')
def _share_artifact_evidence_before_insert(mapper, connection, target):
    # Evidence is part of an artifact's frozen substance: it may only be
    # attached while the artifact is still a draft.
    artifact = target.share_artifact
    if artifact is not None and artifact.lifecycle_state != LIFECYCLE_DRAFT:
        raise ShareArtifactImmutableError(
            'evidence can only be attached while the share artifact is a draft'
        )


@event.listens_for(ShareArtifactEvidence, 'before_update')
def _share_artifact_evidence_before_update(mapper, connection, target):
    if _changed_column_keys(target):
        raise ShareArtifactImmutableError(
            'share_artifact_evidence rows are immutable once created'
        )


@event.listens_for(ShareArtifactEvidence, 'before_delete')
def _share_artifact_evidence_before_delete(mapper, connection, target):
    artifact = target.share_artifact
    if artifact is not None and artifact.lifecycle_state in FROZEN_LIFECYCLE_STATES:
        raise ShareArtifactImmutableError(
            'evidence of a published share artifact cannot be deleted'
        )


@event.listens_for(ShareArtifactAsset, 'before_insert')
def _share_artifact_asset_before_insert(mapper, connection, target):
    # Assets are the one child a later rendering phase may attach after
    # publication, but never to a superseded or withdrawn artifact.
    artifact = target.share_artifact
    if artifact is not None and artifact.lifecycle_state in (
        LIFECYCLE_SUPERSEDED, LIFECYCLE_WITHDRAWN,
    ):
        raise ShareArtifactImmutableError(
            'assets cannot be attached to a superseded or withdrawn share artifact'
        )


@event.listens_for(ShareArtifactAsset, 'before_update')
def _share_artifact_asset_before_update(mapper, connection, target):
    if _changed_column_keys(target):
        raise ShareArtifactImmutableError(
            'share_artifact_asset rows are immutable once created'
        )


@event.listens_for(ShareArtifactAsset, 'before_delete')
def _share_artifact_asset_before_delete(mapper, connection, target):
    artifact = target.share_artifact
    if artifact is not None and artifact.lifecycle_state in FROZEN_LIFECYCLE_STATES:
        raise ShareArtifactImmutableError(
            'assets of a published share artifact cannot be deleted'
        )


@event.listens_for(ShareArtifactRelation, 'before_update')
def _share_artifact_relation_before_update(mapper, connection, target):
    if _changed_column_keys(target):
        raise ShareArtifactImmutableError(
            'share_artifact_relation rows are immutable once created'
        )
