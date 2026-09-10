"""Durable SP-14 certification evidence and legacy transition decisions."""

from utils.db import db
from utils.time import utc_now_naive


class SyncCertificationRun(db.Model):
    __tablename__ = 'sync_certification_runs'
    __table_args__ = (
        db.UniqueConstraint('certification_key', name='uq_sync_certification_runs_key'),
        db.CheckConstraint(
            "status IN ('pending', 'passing', 'failed', 'blocked', 'certified')",
            name='ck_sync_certification_runs_status',
        ),
        db.CheckConstraint(
            "verdict IN ('GO', 'NO-GO') OR verdict IS NULL",
            name='ck_sync_certification_runs_verdict',
        ),
        db.Index('ix_sync_certification_runs_environment_created', 'environment', 'created_at'),
        db.Index('ix_sync_certification_runs_status_created', 'status', 'created_at'),
        db.Index('ix_sync_certification_runs_commit', 'integration_commit_sha'),
    )

    id = db.Column(db.Integer, primary_key=True)
    certification_key = db.Column(db.String(64), nullable=False)
    certification_version = db.Column(db.String(50), nullable=False)
    integration_commit_sha = db.Column(db.String(40), nullable=False)
    migration_head = db.Column(db.String(32), nullable=False)
    environment = db.Column(db.String(30), nullable=False)
    configuration_fingerprint = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')
    verdict = db.Column(db.String(10))
    gate_statuses_json = db.Column(db.JSON, nullable=False, default=dict)
    natural_proof_identifiers_json = db.Column(db.JSON, nullable=False, default=dict)
    production_identifiers_json = db.Column(db.JSON, nullable=False, default=dict)
    failures_json = db.Column(db.JSON, nullable=False, default=list)
    warnings_json = db.Column(db.JSON, nullable=False, default=list)
    sync_run_id = db.Column(db.Integer, db.ForeignKey('sync_runs.id', ondelete='SET NULL'))
    started_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    completed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)


class SyncCertificationCheck(db.Model):
    __tablename__ = 'sync_certification_checks'
    __table_args__ = (
        db.UniqueConstraint(
            'certification_run_id', 'gate_key', 'check_key',
            name='uq_sync_certification_checks_run_gate_check',
        ),
        db.CheckConstraint(
            "status IN ('passing', 'failed', 'blocked', 'warning', 'not_run')",
            name='ck_sync_certification_checks_status',
        ),
        db.Index('ix_sync_certification_checks_gate_status', 'gate_key', 'status'),
        db.Index('ix_sync_certification_checks_run', 'certification_run_id', 'gate_key'),
    )

    id = db.Column(db.Integer, primary_key=True)
    certification_run_id = db.Column(
        db.Integer,
        db.ForeignKey('sync_certification_runs.id', ondelete='CASCADE'),
        nullable=False,
    )
    gate_key = db.Column(db.String(10), nullable=False)
    check_key = db.Column(db.String(80), nullable=False)
    status = db.Column(db.String(20), nullable=False)
    critical = db.Column(db.Boolean, nullable=False, default=True)
    summary = db.Column(db.String(240), nullable=False)
    evidence_json = db.Column(db.JSON, nullable=False, default=dict)
    measured_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    certification_run = db.relationship(
        'SyncCertificationRun',
        backref=db.backref('checks', lazy='select', cascade='all, delete-orphan'),
    )


class SyncLegacyTransitionState(db.Model):
    __tablename__ = 'sync_legacy_transition_states'
    __table_args__ = (
        db.UniqueConstraint('responsibility_key', name='uq_sync_legacy_transition_responsibility'),
        db.CheckConstraint(
            "retirement_type IN ('RETAIN_AS_PRIMARY', 'RETAIN_AS_FALLBACK', "
            "'RETAIN_AS_VERIFIER', 'DISABLE', 'DELETE', 'DEFER_RETIREMENT')",
            name='ck_sync_legacy_transition_retirement_type',
        ),
        db.Index('ix_sync_legacy_transition_retirement', 'retirement_type', 'updated_at'),
        db.Index('ix_sync_legacy_transition_new_owner', 'new_owner'),
    )

    id = db.Column(db.Integer, primary_key=True)
    responsibility_key = db.Column(db.String(80), nullable=False)
    responsibility = db.Column(db.String(160), nullable=False)
    legacy_owner = db.Column(db.String(160), nullable=False)
    new_owner = db.Column(db.String(40), nullable=False)
    current_production_authority = db.Column(db.String(160), nullable=False)
    new_pipeline_readiness = db.Column(db.String(30), nullable=False)
    required_proof = db.Column(db.Text, nullable=False)
    retirement_condition = db.Column(db.Text, nullable=False)
    planned_transition_action = db.Column(db.Text, nullable=False)
    rollback_path = db.Column(db.Text, nullable=False)
    retirement_type = db.Column(db.String(30), nullable=False)
    evidence_json = db.Column(db.JSON, nullable=False, default=dict)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now_naive, onupdate=utc_now_naive,
    )
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
