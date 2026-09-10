from utils.db import db
from utils.time import utc_now_naive


class DerivedIntelligenceCohort(db.Model):
    """Immutable candidate package produced from one canonical impact plan."""

    __tablename__ = 'derived_intelligence_cohorts'
    __table_args__ = (
        db.UniqueConstraint('cohort_fingerprint', name='uq_derived_cohorts_fingerprint'),
        db.CheckConstraint(
            "status IN ('running', 'complete', 'partial', 'stale', 'failed', 'superseded')",
            name='ck_derived_cohorts_status',
        ),
        db.Index('ix_derived_cohorts_date_status', 'baseball_date', 'status'),
        db.Index('ix_derived_cohorts_authority_status', 'authority_class', 'status'),
        db.Index('ix_derived_cohorts_correlation', 'correlation_id', 'id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    impact_plan_id = db.Column(
        db.Integer,
        db.ForeignKey('canonical_impact_plans.id', ondelete='RESTRICT'),
        nullable=False,
    )
    cohort_fingerprint = db.Column(db.String(64), nullable=False)
    schema_version = db.Column(db.String(40), nullable=False)
    authority_class = db.Column(db.String(30), nullable=False)
    baseball_date = db.Column(db.Date, nullable=False)
    correlation_id = db.Column(db.String(64))
    status = db.Column(db.String(20), nullable=False, default='running')
    requested_domains_json = db.Column(db.JSON, nullable=False, default=list)
    execution_domains_json = db.Column(db.JSON, nullable=False, default=list)
    completed_domains_json = db.Column(db.JSON, nullable=False, default=list)
    withheld_domains_json = db.Column(db.JSON, nullable=False, default=list)
    affected_game_ids_json = db.Column(db.JSON, nullable=False, default=list)
    affected_team_ids_json = db.Column(db.JSON, nullable=False, default=list)
    affected_pitcher_ids_json = db.Column(db.JSON, nullable=False, default=list)
    input_manifest_json = db.Column(db.JSON, nullable=False, default=list)
    method_versions_json = db.Column(db.JSON, nullable=False, default=dict)
    predecessor_cohort_id = db.Column(
        db.Integer, db.ForeignKey('derived_intelligence_cohorts.id', ondelete='SET NULL'),
    )
    supersedes_cohort_id = db.Column(
        db.Integer, db.ForeignKey('derived_intelligence_cohorts.id', ondelete='SET NULL'),
    )
    sync_run_id = db.Column(db.Integer, db.ForeignKey('sync_runs.id', ondelete='SET NULL'))
    publication_job_id = db.Column(db.Integer, db.ForeignKey('sync_jobs.id', ondelete='SET NULL'))
    started_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)


class DerivedIntelligenceCohortDomain(db.Model):
    """Per-domain execution evidence and failure isolation."""

    __tablename__ = 'derived_intelligence_cohort_domains'
    __table_args__ = (
        db.UniqueConstraint('cohort_id', 'domain', name='uq_derived_cohort_domain'),
        db.CheckConstraint(
            "status IN ('requested', 'prerequisite', 'succeeded', 'withheld', 'failed', 'skipped', 'stale')",
            name='ck_derived_cohort_domains_status',
        ),
        db.Index('ix_derived_cohort_domains_status', 'status', 'domain'),
    )

    id = db.Column(db.Integer, primary_key=True)
    cohort_id = db.Column(
        db.Integer,
        db.ForeignKey('derived_intelligence_cohorts.id', ondelete='CASCADE'),
        nullable=False,
    )
    domain = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    prerequisite = db.Column(db.Boolean, nullable=False, default=False)
    method_version = db.Column(db.String(80))
    result_summary_json = db.Column(db.JSON)
    error_class = db.Column(db.String(120))
    error_message = db.Column(db.Text)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)


class DerivedCohortInput(db.Model):
    """Queryable immutable watermark entry for a derived cohort."""

    __tablename__ = 'derived_cohort_inputs'
    __table_args__ = (
        db.UniqueConstraint(
            'cohort_id', 'input_type', 'input_key', 'input_version',
            name='uq_derived_cohort_input',
        ),
        db.Index('ix_derived_cohort_inputs_lookup', 'input_type', 'input_key'),
        db.Index('ix_derived_cohort_inputs_observation', 'source_observation_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    cohort_id = db.Column(
        db.Integer,
        db.ForeignKey('derived_intelligence_cohorts.id', ondelete='CASCADE'),
        nullable=False,
    )
    input_type = db.Column(db.String(40), nullable=False)
    input_key = db.Column(db.String(160), nullable=False)
    input_version = db.Column(db.String(160), nullable=False)
    input_fingerprint = db.Column(db.String(64))
    authority_class = db.Column(db.String(30), nullable=False)
    source_observation_id = db.Column(
        db.Integer, db.ForeignKey('source_observations.id', ondelete='RESTRICT'),
    )
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)


class DerivedCohortSnapshot(db.Model):
    """Cohort-bound candidate snapshot; never a public/current pointer."""

    __tablename__ = 'derived_cohort_snapshots'
    __table_args__ = (
        db.UniqueConstraint(
            'cohort_id', 'entity_type', 'entity_key', 'snapshot_type',
            name='uq_derived_cohort_snapshot',
        ),
        db.CheckConstraint(
            "entity_type IN ('pitcher', 'team', 'game')",
            name='ck_derived_cohort_snapshots_entity_type',
        ),
        db.Index(
            'ix_derived_cohort_snapshots_entity',
            'entity_type', 'entity_key', 'baseball_date',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    cohort_id = db.Column(
        db.Integer,
        db.ForeignKey('derived_intelligence_cohorts.id', ondelete='CASCADE'),
        nullable=False,
    )
    entity_type = db.Column(db.String(20), nullable=False)
    entity_key = db.Column(db.String(80), nullable=False)
    snapshot_type = db.Column(db.String(40), nullable=False)
    baseball_date = db.Column(db.Date, nullable=False)
    authority_class = db.Column(db.String(30), nullable=False)
    payload_schema_version = db.Column(db.Integer, nullable=False, default=1)
    payload_json = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
