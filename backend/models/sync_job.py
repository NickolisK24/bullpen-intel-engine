from utils.db import db
from utils.time import utc_now_naive


class SyncJob(db.Model):
    __tablename__ = 'sync_jobs'

    __table_args__ = (
        db.UniqueConstraint(
            'job_name',
            'scope_key',
            'product_date',
            name='uq_sync_jobs_name_scope_date',
        ),
        db.Index('ix_sync_jobs_status', 'status'),
        db.Index('ix_sync_jobs_product_date', 'product_date'),
        db.Index('ix_sync_jobs_job_family', 'job_family'),
        db.Index('ix_sync_jobs_lane', 'lane'),
        db.Index('ix_sync_jobs_job_name', 'job_name'),
        db.Index('ix_sync_jobs_updated_at', 'updated_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    job_name = db.Column(db.String(80), nullable=False)
    job_family = db.Column(db.String(50), nullable=False)
    lane = db.Column(db.String(50), nullable=False, default='internal')
    scope_key = db.Column(db.String(160), nullable=False)
    product_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')
    attempts = db.Column(db.Integer, nullable=False, default=0)
    max_attempts = db.Column(db.Integer, nullable=False, default=3)
    started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    last_heartbeat_at = db.Column(db.DateTime)
    duration_ms = db.Column(db.Integer)
    error_message = db.Column(db.Text)
    error_type = db.Column(db.String(120))
    details_json = db.Column(db.JSON)
    sync_run_id = db.Column(db.Integer, db.ForeignKey('sync_runs.id'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now_naive,
        onupdate=utc_now_naive,
    )

    def to_dict(self):
        return {
            'id': self.id,
            'job_name': self.job_name,
            'job_family': self.job_family,
            'lane': self.lane,
            'scope_key': self.scope_key,
            'product_date': self.product_date.isoformat() if self.product_date else None,
            'status': self.status,
            'attempts': self.attempts or 0,
            'max_attempts': self.max_attempts or 0,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'last_heartbeat_at': (
                self.last_heartbeat_at.isoformat()
                if self.last_heartbeat_at else None
            ),
            'duration_ms': self.duration_ms,
            'error_message': self.error_message,
            'error_type': self.error_type,
            'details_json': self.details_json,
            'sync_run_id': self.sync_run_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
