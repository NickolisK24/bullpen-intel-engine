"""Immutable SP-11 publication generations and their atomic current pointer."""

from utils.db import db
from utils.time import utc_now_naive


class AtomicPublication(db.Model):
    __tablename__ = 'atomic_publications'
    __table_args__ = (
        db.UniqueConstraint('publication_fingerprint', name='uq_atomic_publication_fingerprint'),
        db.UniqueConstraint('cohort_id', name='uq_atomic_publication_cohort'),
        db.CheckConstraint(
            "status IN ('preparing', 'ready', 'published', 'failed', 'superseded')",
            name='ck_atomic_publication_status',
        ),
        db.CheckConstraint(
            "completeness IN ('complete', 'partial', 'withheld')",
            name='ck_atomic_publication_completeness',
        ),
        db.Index('ix_atomic_publications_date_status', 'baseball_date', 'status'),
        db.Index('ix_atomic_publications_authority_status', 'authority_class', 'status'),
        db.Index('ix_atomic_publications_correlation', 'correlation_id', 'id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    publication_fingerprint = db.Column(db.String(64), nullable=False)
    schema_version = db.Column(db.String(40), nullable=False)
    predecessor_publication_id = db.Column(
        db.Integer, db.ForeignKey('atomic_publications.id', ondelete='SET NULL'),
    )
    cohort_id = db.Column(
        db.Integer,
        db.ForeignKey('derived_intelligence_cohorts.id', ondelete='RESTRICT'),
        nullable=False,
    )
    impact_plan_id = db.Column(
        db.Integer, db.ForeignKey('canonical_impact_plans.id', ondelete='RESTRICT'),
        nullable=False,
    )
    baseball_date = db.Column(db.Date, nullable=False)
    authority_class = db.Column(db.String(30), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='preparing')
    completeness = db.Column(db.String(20), nullable=False, default='withheld')
    source_data_through = db.Column(db.DateTime, nullable=False)
    affected_game_ids_json = db.Column(db.JSON, nullable=False, default=list)
    affected_team_ids_json = db.Column(db.JSON, nullable=False, default=list)
    affected_pitcher_ids_json = db.Column(db.JSON, nullable=False, default=list)
    completed_domains_json = db.Column(db.JSON, nullable=False, default=list)
    withheld_domains_json = db.Column(db.JSON, nullable=False, default=list)
    method_versions_json = db.Column(db.JSON, nullable=False, default=dict)
    input_manifest_fingerprint = db.Column(db.String(64), nullable=False)
    correlation_id = db.Column(db.String(64))
    sync_run_id = db.Column(db.Integer, db.ForeignKey('sync_runs.id', ondelete='SET NULL'))
    artifact_created_count = db.Column(db.Integer, nullable=False, default=0)
    artifact_inherited_count = db.Column(db.Integer, nullable=False, default=0)
    preparation_duration_ms = db.Column(db.Integer)
    pointer_switch_duration_ms = db.Column(db.Integer)
    validation_failure_reason = db.Column(db.String(200))
    published_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)


class AtomicPublicationArtifact(db.Model):
    __tablename__ = 'atomic_publication_artifacts'
    __table_args__ = (
        db.UniqueConstraint(
            'publication_id', 'artifact_type', 'entity_type', 'entity_key',
            name='uq_atomic_publication_artifact_key',
        ),
        db.CheckConstraint(
            "entity_type IN ('pitcher', 'team', 'game', 'league')",
            name='ck_atomic_publication_artifact_entity_type',
        ),
        db.CheckConstraint(
            '(source_snapshot_id IS NOT NULL) != (inherited_from_artifact_id IS NOT NULL)',
            name='ck_atomic_publication_artifact_one_source',
        ),
        db.Index(
            'ix_atomic_publication_artifact_lookup',
            'publication_id', 'artifact_type', 'entity_type', 'entity_key',
        ),
        db.Index(
            'ix_atomic_publication_artifact_entity_history',
            'entity_type', 'entity_key', 'publication_id',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    publication_id = db.Column(
        db.Integer, db.ForeignKey('atomic_publications.id', ondelete='CASCADE'), nullable=False,
    )
    artifact_type = db.Column(db.String(50), nullable=False)
    entity_type = db.Column(db.String(20), nullable=False)
    entity_key = db.Column(db.String(80), nullable=False)
    source_cohort_id = db.Column(
        db.Integer,
        db.ForeignKey('derived_intelligence_cohorts.id', ondelete='RESTRICT'),
        nullable=False,
    )
    source_snapshot_id = db.Column(
        db.Integer, db.ForeignKey('derived_cohort_snapshots.id', ondelete='RESTRICT'),
    )
    inherited_from_artifact_id = db.Column(
        db.Integer, db.ForeignKey('atomic_publication_artifacts.id', ondelete='RESTRICT'),
    )
    schema_version = db.Column(db.String(40), nullable=False)
    payload_fingerprint = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)


class AtomicPublicationCurrent(db.Model):
    __tablename__ = 'atomic_publication_current'
    __table_args__ = (
        db.CheckConstraint('singleton_id = 1', name='ck_atomic_publication_current_singleton'),
    )

    singleton_id = db.Column(db.Integer, primary_key=True, default=1)
    publication_id = db.Column(
        db.Integer, db.ForeignKey('atomic_publications.id', ondelete='RESTRICT'), nullable=False,
        unique=True,
    )
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)


class AtomicPublicationCacheHandoff(db.Model):
    __tablename__ = 'atomic_publication_cache_handoffs'
    __table_args__ = (
        db.UniqueConstraint('publication_id', name='uq_atomic_publication_cache_handoff'),
        db.CheckConstraint(
            "status IN ('pending', 'complete', 'retry_wait', 'not_configured')",
            name='ck_atomic_publication_cache_handoff_status',
        ),
        db.Index('ix_atomic_publication_cache_handoff_status', 'status', 'updated_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    publication_id = db.Column(
        db.Integer, db.ForeignKey('atomic_publications.id', ondelete='CASCADE'), nullable=False,
    )
    status = db.Column(db.String(20), nullable=False, default='pending')
    cache_keys_json = db.Column(db.JSON, nullable=False, default=list)
    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    last_error_class = db.Column(db.String(120))
    last_error = db.Column(db.Text)
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
