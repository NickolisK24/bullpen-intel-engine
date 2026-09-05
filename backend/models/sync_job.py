from utils.db import db
from utils.time import utc_now_naive


class SyncJob(db.Model):
    __tablename__ = 'sync_jobs'

    __table_args__ = (
        db.Index('ix_sync_jobs_status', 'status'),
        db.Index('ix_sync_jobs_product_date', 'product_date'),
        db.Index('ix_sync_jobs_job_family', 'job_family'),
        db.Index('ix_sync_jobs_lane', 'lane'),
        db.Index('ix_sync_jobs_job_name', 'job_name'),
        db.Index('ix_sync_jobs_updated_at', 'updated_at'),
        db.Index(
            'ix_sync_jobs_claim_ready',
            'lane',
            'status',
            'priority',
            'available_at',
            'created_at',
            'id',
        ),
        db.Index(
            'ix_sync_jobs_lease_expiry',
            'lane',
            'status',
            'lease_until',
        ),
        db.Index(
            'uq_sync_jobs_active_dedupe_key',
            'dedupe_key',
            unique=True,
            postgresql_where=db.text(
                "dedupe_key IS NOT NULL AND status IN "
                "('pending', 'running', 'retry_wait')"
            ),
            sqlite_where=db.text(
                "dedupe_key IS NOT NULL AND status IN "
                "('pending', 'running', 'retry_wait')"
            ),
        ),
        db.CheckConstraint(
            'priority >= 0 AND priority <= 1000',
            name='ck_sync_jobs_priority_range',
        ),
        db.CheckConstraint(
            'attempts >= 0 AND max_attempts > 0',
            name='ck_sync_jobs_attempt_bounds',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    job_name = db.Column(db.String(80), nullable=False)
    job_family = db.Column(db.String(50), nullable=False)
    lane = db.Column(db.String(50), nullable=False, default='internal')
    scope_type = db.Column(db.String(30), nullable=True)
    scope_key = db.Column(db.String(160), nullable=False)
    product_date = db.Column(db.Date, nullable=False)
    payload_schema_version = db.Column(db.Integer, nullable=True)
    dedupe_key = db.Column(db.String(255), nullable=True)
    priority = db.Column(db.Integer, nullable=False, default=100)
    status = db.Column(db.String(20), nullable=False, default='pending')
    attempts = db.Column(db.Integer, nullable=False, default=0)
    max_attempts = db.Column(db.Integer, nullable=False, default=3)
    first_available_at = db.Column(db.DateTime, nullable=True)
    available_at = db.Column(db.DateTime, nullable=True, default=utc_now_naive)
    started_at = db.Column(db.DateTime)
    claimed_at = db.Column(db.DateTime)
    lease_until = db.Column(db.DateTime)
    worker_id = db.Column(db.String(120))
    claim_token = db.Column(db.String(36))
    completed_at = db.Column(db.DateTime)
    dead_at = db.Column(db.DateTime)
    last_heartbeat_at = db.Column(db.DateTime)
    duration_ms = db.Column(db.Integer)
    error_message = db.Column(db.Text)
    error_type = db.Column(db.String(120))
    details_json = db.Column(db.JSON)
    result_json = db.Column(db.JSON)
    sync_run_id = db.Column(db.Integer, db.ForeignKey('sync_runs.id'), nullable=True)
    parent_job_id = db.Column(
        db.Integer,
        db.ForeignKey('sync_jobs.id', ondelete='SET NULL'),
        nullable=True,
    )
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now_naive,
        onupdate=utc_now_naive,
    )

    parent = db.relationship(
        'SyncJob',
        remote_side=[id],
        backref=db.backref('children', lazy='dynamic'),
        foreign_keys=[parent_job_id],
    )

    def to_dict(self):
        return {
            'id': self.id,
            'job_name': self.job_name,
            'job_family': self.job_family,
            'lane': self.lane,
            'scope_type': self.scope_type,
            'scope_key': self.scope_key,
            'product_date': self.product_date.isoformat() if self.product_date else None,
            'payload_schema_version': self.payload_schema_version,
            'dedupe_key': self.dedupe_key,
            'priority': self.priority,
            'status': self.status,
            'attempts': self.attempts or 0,
            'max_attempts': self.max_attempts or 0,
            'first_available_at': (
                self.first_available_at.isoformat()
                if self.first_available_at else None
            ),
            'available_at': (
                self.available_at.isoformat() if self.available_at else None
            ),
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'claimed_at': self.claimed_at.isoformat() if self.claimed_at else None,
            'lease_until': self.lease_until.isoformat() if self.lease_until else None,
            'worker_id': self.worker_id,
            'claim_token': self.claim_token,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'dead_at': self.dead_at.isoformat() if self.dead_at else None,
            'last_heartbeat_at': (
                self.last_heartbeat_at.isoformat()
                if self.last_heartbeat_at else None
            ),
            'duration_ms': self.duration_ms,
            'error_message': self.error_message,
            'error_type': self.error_type,
            'details_json': self.details_json,
            'result_json': self.result_json,
            'sync_run_id': self.sync_run_id,
            'parent_job_id': self.parent_job_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }


class SyncJobAttempt(db.Model):
    """Compact append-only lease/attempt history for one durable job."""

    __tablename__ = 'sync_job_attempts'

    __table_args__ = (
        db.UniqueConstraint(
            'sync_job_id',
            'attempt_number',
            name='uq_sync_job_attempts_job_number',
        ),
        db.Index(
            'ix_sync_job_attempts_job_claimed',
            'sync_job_id',
            'claimed_at',
        ),
        db.Index('ix_sync_job_attempts_claim_token', 'claim_token'),
    )

    id = db.Column(db.Integer, primary_key=True)
    sync_job_id = db.Column(
        db.Integer,
        db.ForeignKey('sync_jobs.id', ondelete='CASCADE'),
        nullable=False,
    )
    attempt_number = db.Column(db.Integer, nullable=False)
    worker_id = db.Column(db.String(120), nullable=False)
    claim_token = db.Column(db.String(36), nullable=False)
    claimed_at = db.Column(db.DateTime, nullable=False)
    lease_until = db.Column(db.DateTime, nullable=False)
    finished_at = db.Column(db.DateTime)
    outcome = db.Column(db.String(30))
    retryable = db.Column(db.Boolean)
    error_message = db.Column(db.Text)
    error_type = db.Column(db.String(120))

    job = db.relationship(
        'SyncJob',
        backref=db.backref('attempt_history', lazy='dynamic'),
        foreign_keys=[sync_job_id],
    )

    def to_dict(self):
        return {
            'id': self.id,
            'sync_job_id': self.sync_job_id,
            'attempt_number': self.attempt_number,
            'worker_id': self.worker_id,
            'claim_token': self.claim_token,
            'claimed_at': self.claimed_at.isoformat() if self.claimed_at else None,
            'lease_until': self.lease_until.isoformat() if self.lease_until else None,
            'finished_at': self.finished_at.isoformat() if self.finished_at else None,
            'outcome': self.outcome,
            'retryable': self.retryable,
            'error_message': self.error_message,
            'error_type': self.error_type,
        }
