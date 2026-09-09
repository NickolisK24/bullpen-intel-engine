from utils.db import db
from utils.time import utc_now_naive


class CanonicalImpactPlan(db.Model):
    """Durable, authority-aware plan produced from one mutation cohort."""

    __tablename__ = 'canonical_impact_plans'
    __table_args__ = (
        db.UniqueConstraint('plan_fingerprint', name='uq_canonical_impact_plans_fingerprint'),
        db.CheckConstraint(
            "authority_class IN ('live', 'final', 'corrected_final', "
            "'roster_authoritative', 'pregame_authoritative')",
            name='ck_canonical_impact_plans_authority',
        ),
        db.CheckConstraint(
            "status IN ('planned', 'dispatched', 'superseded')",
            name='ck_canonical_impact_plans_status',
        ),
        db.CheckConstraint(
            "publication_mode IN ('current', 'historical')",
            name='ck_canonical_impact_plans_publication_mode',
        ),
        db.Index('ix_canonical_impact_plans_date', 'baseball_date', 'id'),
        db.Index('ix_canonical_impact_plans_authority', 'authority_class', 'id'),
        db.Index('ix_canonical_impact_plans_correlation', 'correlation_id', 'id'),
        db.Index('ix_canonical_impact_plans_sync_run', 'sync_run_id', 'id'),
        db.Index('ix_canonical_impact_plans_repair', 'repair_request_id', 'id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    plan_fingerprint = db.Column(db.String(64), nullable=False)
    rules_version = db.Column(db.String(40), nullable=False)
    authority_class = db.Column(db.String(30), nullable=False)
    baseball_date = db.Column(db.Date, nullable=False)
    correlation_id = db.Column(db.String(64))
    affected_game_ids_json = db.Column(db.JSON, nullable=False, default=list)
    affected_team_ids_json = db.Column(db.JSON, nullable=False, default=list)
    affected_pitcher_ids_json = db.Column(db.JSON, nullable=False, default=list)
    affected_domains_json = db.Column(db.JSON, nullable=False, default=list)
    source_observation_ids_json = db.Column(db.JSON, nullable=False, default=list)
    status = db.Column(db.String(20), nullable=False, default='planned')
    supersedes_live = db.Column(db.Boolean, nullable=False, default=False)
    supersedes_plan_id = db.Column(
        db.Integer,
        db.ForeignKey('canonical_impact_plans.id', ondelete='SET NULL'),
    )
    sync_run_id = db.Column(
        db.Integer,
        db.ForeignKey('sync_runs.id', ondelete='SET NULL'),
    )
    dispatched_job_id = db.Column(
        db.Integer,
        db.ForeignKey('sync_jobs.id', ondelete='SET NULL'),
    )
    repair_request_id = db.Column(
        db.Integer,
        db.ForeignKey('repair_requests.id', ondelete='SET NULL'),
    )
    replay_kind = db.Column(db.String(20))
    replay_from_plan_id = db.Column(
        db.Integer,
        db.ForeignKey('canonical_impact_plans.id', ondelete='SET NULL'),
    )
    method_versions_override_json = db.Column(db.JSON, nullable=False, default=dict)
    publication_mode = db.Column(db.String(20), nullable=False, default='current')
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    dispatched_at = db.Column(db.DateTime)

    supersedes_plan = db.relationship(
        'CanonicalImpactPlan',
        remote_side=[id],
        foreign_keys=[supersedes_plan_id],
    )
    replay_from_plan = db.relationship(
        'CanonicalImpactPlan', remote_side=[id], foreign_keys=[replay_from_plan_id],
    )


class CanonicalImpactPlanMutation(db.Model):
    """Polymorphic reference to one immutable source mutation row."""

    __tablename__ = 'canonical_impact_plan_mutations'
    __table_args__ = (
        db.UniqueConstraint(
            'impact_plan_id', 'mutation_family', 'source_mutation_id',
            name='uq_canonical_impact_plan_mutation_ref',
        ),
        db.Index(
            'ix_canonical_impact_plan_mutations_source',
            'mutation_family', 'source_mutation_id',
        ),
        db.Index(
            'ix_canonical_impact_plan_mutations_observation',
            'source_observation_id',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    impact_plan_id = db.Column(
        db.Integer,
        db.ForeignKey('canonical_impact_plans.id', ondelete='CASCADE'),
        nullable=False,
    )
    mutation_family = db.Column(db.String(40), nullable=False)
    source_mutation_id = db.Column(db.Integer, nullable=False)
    source_mutation_type = db.Column(db.String(60), nullable=False)
    authority_class = db.Column(db.String(30), nullable=False)
    game_pk = db.Column(db.Integer)
    team_id = db.Column(db.Integer)
    pitcher_id = db.Column(db.Integer, db.ForeignKey('pitchers.id'))
    baseball_date = db.Column(db.Date, nullable=False)
    source_observation_id = db.Column(
        db.Integer,
        db.ForeignKey('source_observations.id', ondelete='RESTRICT'),
    )
    old_fact_identity = db.Column(db.String(160))
    new_fact_identity = db.Column(db.String(160))
    is_correction = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    impact_plan = db.relationship(
        'CanonicalImpactPlan',
        backref=db.backref('mutation_refs', lazy='select'),
    )


class CanonicalImpactPlanEntity(db.Model):
    """Queryable, deduplicated entity scope for an impact plan."""

    __tablename__ = 'canonical_impact_plan_entities'
    __table_args__ = (
        db.UniqueConstraint(
            'impact_plan_id', 'entity_type', 'entity_key',
            name='uq_canonical_impact_plan_entity',
        ),
        db.CheckConstraint(
            "entity_type IN ('game', 'team', 'pitcher')",
            name='ck_canonical_impact_plan_entities_type',
        ),
        db.Index(
            'ix_canonical_impact_plan_entities_lookup',
            'entity_type', 'entity_key', 'impact_plan_id',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    impact_plan_id = db.Column(
        db.Integer,
        db.ForeignKey('canonical_impact_plans.id', ondelete='CASCADE'),
        nullable=False,
    )
    entity_type = db.Column(db.String(20), nullable=False)
    entity_key = db.Column(db.String(80), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    impact_plan = db.relationship(
        'CanonicalImpactPlan',
        backref=db.backref('entity_refs', lazy='select'),
    )
