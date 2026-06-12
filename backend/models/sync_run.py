from utils.db import db
from utils.time import utc_now_naive


class SyncRun(db.Model):
    __tablename__ = 'sync_runs'

    __table_args__ = (
        db.Index('ix_sync_runs_started_at', 'started_at'),
        db.Index('ix_sync_runs_status_completed', 'status', 'completed_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    # Name of the sync job that produced this row. Defaults to the combined
    # daily refresh; lets pipeline observability group runs by job.
    job_name = db.Column(db.String(50), nullable=False, default='daily_sync')
    started_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    # completed_at is the spec's "finished_at" (kept under its established name
    # for backward compatibility with existing callers and tests).
    completed_at = db.Column(db.DateTime)
    # status is one of: running / success / partial / failed.
    status = db.Column(db.String(20), nullable=False, default='running')
    source = db.Column(db.String(30), nullable=False, default='manual')

    latest_game_date = db.Column(db.Date)
    latest_workload_date = db.Column(db.Date)
    latest_fatigue_calculated_at = db.Column(db.DateTime)

    records_processed = db.Column(db.Integer, default=0)
    # Number of records that could not be processed and were dead-lettered.
    records_failed = db.Column(db.Integer, default=0)
    new_logs_added = db.Column(db.Integer, default=0)
    pitchers_updated = db.Column(db.Integer, default=0)
    errors = db.Column(db.Integer, default=0)
    # MLB API calls made and retries consumed during the run (from the client
    # metrics accumulator) — pipeline observability for retry pressure.
    api_calls_made = db.Column(db.Integer, default=0)
    retries_used = db.Column(db.Integer, default=0)
    # error_message is the spec's "error_summary" (kept under its established
    # name for backward compatibility).
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    def to_dict(self):
        return {
            'id': self.id,
            'job_name': self.job_name,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            # Spec-facing alias so consumers can read either name.
            'finished_at': self.completed_at.isoformat() if self.completed_at else None,
            'status': self.status,
            'source': self.source,
            'latest_game_date': self.latest_game_date.isoformat() if self.latest_game_date else None,
            'latest_workload_date': self.latest_workload_date.isoformat() if self.latest_workload_date else None,
            'latest_fatigue_calculated_at': self.latest_fatigue_calculated_at.isoformat() if self.latest_fatigue_calculated_at else None,
            'records_processed': self.records_processed or 0,
            'records_failed': self.records_failed or 0,
            'new_logs_added': self.new_logs_added or 0,
            'pitchers_updated': self.pitchers_updated or 0,
            'errors': self.errors or 0,
            'api_calls_made': self.api_calls_made or 0,
            'retries_used': self.retries_used or 0,
            'error_message': self.error_message,
            'error_summary': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
