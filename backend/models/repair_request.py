"""Governed SP-13 repair, backfill, and replay requests."""

from utils.db import db
from utils.time import utc_now_naive


class RepairRequest(db.Model):
    __tablename__ = 'repair_requests'
    __table_args__ = (
        db.UniqueConstraint('request_key', name='uq_repair_requests_key'),
        db.CheckConstraint(
            "mode IN ('targeted_repair', 'historical_backfill', "
            "'full_reconciliation', 'method_replay', 'rule_replay')",
            name='ck_repair_requests_mode',
        ),
        db.CheckConstraint(
            "status IN ('planned', 'running', 'blocked', 'completed', "
            "'completed_partial', 'failed', 'cancelled')",
            name='ck_repair_requests_status',
        ),
        db.Index('ix_repair_requests_status_created', 'status', 'created_at'),
        db.Index('ix_repair_requests_dates', 'baseball_date_start', 'baseball_date_end'),
        db.Index('ix_repair_requests_correlation', 'correlation_id'),
        db.Index(
            'uq_repair_requests_active_dedupe', 'active_dedupe_key', unique=True,
            postgresql_where=db.text(
                "active_dedupe_key IS NOT NULL AND status IN ('planned', 'running', 'blocked')"
            ),
            sqlite_where=db.text(
                "active_dedupe_key IS NOT NULL AND status IN ('planned', 'running', 'blocked')"
            ),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    request_key = db.Column(db.String(36), nullable=False)
    request_fingerprint = db.Column(db.String(64), nullable=False)
    active_dedupe_key = db.Column(db.String(255))
    schema_version = db.Column(db.String(40), nullable=False)
    plan_version = db.Column(db.String(40), nullable=False)
    mode = db.Column(db.String(30), nullable=False)
    status = db.Column(db.String(30), nullable=False, default='planned')
    requested_scope_type = db.Column(db.String(30), nullable=False)
    scope_json = db.Column(db.JSON, nullable=False)
    baseball_date_start = db.Column(db.Date, nullable=False)
    baseball_date_end = db.Column(db.Date, nullable=False)
    source_domain = db.Column(db.String(40), nullable=False)
    reason = db.Column(db.Text, nullable=False)
    requested_by = db.Column(db.String(120), nullable=False)
    trigger_type = db.Column(db.String(30), nullable=False)
    dry_run = db.Column(db.Boolean, nullable=False, default=True)
    requested_rules_version = db.Column(db.String(40))
    requested_method_versions_json = db.Column(db.JSON, nullable=False, default=dict)
    correlation_id = db.Column(db.String(36), nullable=False)
    root_sync_run_id = db.Column(db.Integer, db.ForeignKey('sync_runs.id', ondelete='SET NULL'))
    root_job_id = db.Column(db.Integer, db.ForeignKey('sync_jobs.id', ondelete='SET NULL'))
    check_job_id = db.Column(db.Integer, db.ForeignKey('sync_jobs.id', ondelete='SET NULL'))
    plan_fingerprint = db.Column(db.String(64))
    plan_json = db.Column(db.JSON, nullable=False, default=dict)
    estimated_counts_json = db.Column(db.JSON, nullable=False, default=dict)
    outcome_json = db.Column(db.JSON, nullable=False, default=dict)
    failure_reason = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    cancelled_at = db.Column(db.DateTime)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now_naive, onupdate=utc_now_naive,
    )


class RepairRequestChunk(db.Model):
    __tablename__ = 'repair_request_chunks'
    __table_args__ = (
        db.UniqueConstraint('repair_request_id', 'chunk_key', name='uq_repair_request_chunks_key'),
        db.CheckConstraint(
            "status IN ('planned', 'dispatched', 'running', 'succeeded', "
            "'blocked', 'failed', 'cancelled')",
            name='ck_repair_request_chunks_status',
        ),
        db.Index('ix_repair_request_chunks_status', 'repair_request_id', 'status'),
        db.Index('ix_repair_request_chunks_dates', 'baseball_date_start', 'baseball_date_end'),
    )

    id = db.Column(db.Integer, primary_key=True)
    repair_request_id = db.Column(
        db.Integer, db.ForeignKey('repair_requests.id', ondelete='CASCADE'), nullable=False,
    )
    chunk_key = db.Column(db.String(160), nullable=False)
    chunk_order = db.Column(db.Integer, nullable=False)
    owner_package = db.Column(db.String(20), nullable=False)
    baseball_date_start = db.Column(db.Date, nullable=False)
    baseball_date_end = db.Column(db.Date, nullable=False)
    scope_json = db.Column(db.JSON, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='planned')
    child_job_ids_json = db.Column(db.JSON, nullable=False, default=list)
    outcome_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now_naive, onupdate=utc_now_naive,
    )

    request = db.relationship(
        'RepairRequest', backref=db.backref('chunks', lazy='select', cascade='all, delete-orphan'),
    )


class RepairRequestBlocker(db.Model):
    __tablename__ = 'repair_request_blockers'
    __table_args__ = (
        db.UniqueConstraint(
            'repair_request_id', 'blocker_type', 'entity_type', 'entity_key',
            name='uq_repair_request_blockers_identity',
        ),
        db.Index('ix_repair_request_blockers_type', 'blocker_type', 'repair_request_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    repair_request_id = db.Column(
        db.Integer, db.ForeignKey('repair_requests.id', ondelete='CASCADE'), nullable=False,
    )
    blocker_type = db.Column(db.String(50), nullable=False)
    entity_type = db.Column(db.String(30), nullable=False)
    entity_key = db.Column(db.String(160), nullable=False)
    retryable = db.Column(db.Boolean, nullable=False, default=True)
    details_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    request = db.relationship(
        'RepairRequest', backref=db.backref('blockers', lazy='select', cascade='all, delete-orphan'),
    )
