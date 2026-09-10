from utils.db import db
from utils.time import utc_now_naive


class SyncScheduleAttempt(db.Model):
    """Durable scheduler request evidence, including safe no-op attempts."""

    __tablename__ = 'sync_schedule_attempts'
    __table_args__ = (
        db.Index('ix_sync_schedule_attempts_window', 'mode', 'intended_window', 'outcome'),
        db.Index('ix_sync_schedule_attempts_source_started', 'source', 'started_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    mode = db.Column(db.String(20), nullable=False)
    source = db.Column(db.String(30), nullable=False)
    intended_window = db.Column(db.String(60), nullable=False)
    scheduled_for = db.Column(db.DateTime, nullable=False)
    started_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    completed_at = db.Column(db.DateTime)
    outcome = db.Column(db.String(30), nullable=False, default='running')
    sync_run_id = db.Column(db.Integer, db.ForeignKey('sync_runs.id'), nullable=True)
    snapshot_before_id = db.Column(db.Integer, nullable=True)
    snapshot_after_id = db.Column(db.Integer, nullable=True)
    publication_outcome = db.Column(db.String(50), nullable=True)
    recovery_reason = db.Column(db.Text, nullable=True)
    operator = db.Column(db.String(100), nullable=True)
    failure_reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    def to_dict(self):
        return {
            'id': self.id,
            'mode': self.mode,
            'source': self.source,
            'intended_window': self.intended_window,
            'scheduled_for': self.scheduled_for.isoformat() if self.scheduled_for else None,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'outcome': self.outcome,
            'sync_run_id': self.sync_run_id,
            'snapshot_before_id': self.snapshot_before_id,
            'snapshot_after_id': self.snapshot_after_id,
            'publication_outcome': self.publication_outcome,
            'recovery_reason': self.recovery_reason,
            'operator': self.operator,
            'failure_reason': self.failure_reason,
        }
