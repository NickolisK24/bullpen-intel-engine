"""SP-12 whole-league morning evidence and reopenable date closure."""

from utils.db import db
from utils.time import utc_now_naive


class BaseballDateClosure(db.Model):
    __tablename__ = 'baseball_date_closures'
    __table_args__ = (
        db.UniqueConstraint('baseball_date', name='uq_baseball_date_closures_date'),
        db.CheckConstraint(
            "status IN ('open', 'checking', 'blocked', 'closed', 'reopened', 'failed')",
            name='ck_baseball_date_closures_status',
        ),
        db.Index('ix_baseball_date_closures_status_date', 'status', 'baseball_date'),
        db.Index('ix_baseball_date_closures_reopened', 'reopened_at', 'baseball_date'),
        db.Index('ix_baseball_date_closures_publication', 'publication_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    baseball_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='open')
    current_version_number = db.Column(db.Integer, nullable=False, default=0)
    expected_games = db.Column(db.Integer, nullable=False, default=0)
    resolved_games = db.Column(db.Integer, nullable=False, default=0)
    final_games = db.Column(db.Integer, nullable=False, default=0)
    reconciled_final_games = db.Column(db.Integer, nullable=False, default=0)
    unresolved_games = db.Column(db.Integer, nullable=False, default=0)
    expected_teams = db.Column(db.Integer, nullable=False, default=30)
    reconciled_rosters = db.Column(db.Integer, nullable=False, default=0)
    transaction_completeness = db.Column(db.String(20), nullable=False, default='unknown')
    pending_jobs = db.Column(db.Integer, nullable=False, default=0)
    failed_jobs = db.Column(db.Integer, nullable=False, default=0)
    required_publications_complete = db.Column(db.Boolean, nullable=False, default=False)
    optional_enrichment_outstanding = db.Column(db.Boolean, nullable=False, default=False)
    source_data_through = db.Column(db.DateTime)
    closure_fingerprint = db.Column(db.String(64))
    closure_schema_version = db.Column(db.String(40), nullable=False)
    recheck_policy_version = db.Column(db.String(40), nullable=False)
    next_check_at = db.Column(db.DateTime)
    first_checked_at = db.Column(db.DateTime)
    closed_at = db.Column(db.DateTime)
    reopened_at = db.Column(db.DateTime)
    reopened_count = db.Column(db.Integer, nullable=False, default=0)
    publication_id = db.Column(
        db.Integer, db.ForeignKey('atomic_publications.id', ondelete='SET NULL'),
    )
    sync_run_id = db.Column(db.Integer, db.ForeignKey('sync_runs.id', ondelete='SET NULL'))
    metrics_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now_naive, onupdate=utc_now_naive,
    )


class BaseballDateClosureVersion(db.Model):
    __tablename__ = 'baseball_date_closure_versions'
    __table_args__ = (
        db.UniqueConstraint(
            'closure_id', 'version_number', name='uq_baseball_date_closure_versions_number',
        ),
        db.CheckConstraint('version_number > 0', name='ck_baseball_date_closure_versions_number'),
        db.CheckConstraint(
            "event_type IN ('closed', 'reopened')",
            name='ck_baseball_date_closure_versions_event',
        ),
        db.Index('ix_baseball_date_closure_versions_date', 'baseball_date', 'version_number'),
        db.Index('ix_baseball_date_closure_versions_fingerprint', 'closure_fingerprint'),
    )

    id = db.Column(db.Integer, primary_key=True)
    closure_id = db.Column(
        db.Integer, db.ForeignKey('baseball_date_closures.id', ondelete='CASCADE'), nullable=False,
    )
    version_number = db.Column(db.Integer, nullable=False)
    predecessor_version_id = db.Column(
        db.Integer, db.ForeignKey('baseball_date_closure_versions.id', ondelete='RESTRICT'),
    )
    baseball_date = db.Column(db.Date, nullable=False)
    event_type = db.Column(db.String(20), nullable=False)
    closure_fingerprint = db.Column(db.String(64), nullable=False)
    publication_id = db.Column(
        db.Integer, db.ForeignKey('atomic_publications.id', ondelete='SET NULL'),
    )
    evidence_json = db.Column(db.JSON, nullable=False)
    sync_run_id = db.Column(db.Integer, db.ForeignKey('sync_runs.id', ondelete='SET NULL'))
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    predecessor = db.relationship(
        'BaseballDateClosureVersion', remote_side=[id], foreign_keys=[predecessor_version_id],
    )


class BaseballDateClosureBlocker(db.Model):
    __tablename__ = 'baseball_date_closure_blockers'
    __table_args__ = (
        db.UniqueConstraint(
            'closure_id', 'blocker_type', 'entity_type', 'entity_key',
            name='uq_baseball_date_closure_blocker',
        ),
        db.Index('ix_baseball_date_closure_blockers_type', 'blocker_type', 'closure_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    closure_id = db.Column(
        db.Integer, db.ForeignKey('baseball_date_closures.id', ondelete='CASCADE'), nullable=False,
    )
    blocker_type = db.Column(db.String(50), nullable=False)
    entity_type = db.Column(db.String(30), nullable=False, default='baseball_date')
    entity_key = db.Column(db.String(120), nullable=False)
    retryable = db.Column(db.Boolean, nullable=False, default=True)
    details_json = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
