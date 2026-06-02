from datetime import datetime

from utils.db import db


class SyncRun(db.Model):
    __tablename__ = 'sync_runs'

    __table_args__ = (
        db.Index('ix_sync_runs_started_at', 'started_at'),
        db.Index('ix_sync_runs_status_completed', 'status', 'completed_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), nullable=False, default='running')
    source = db.Column(db.String(30), nullable=False, default='manual')

    latest_game_date = db.Column(db.Date)
    latest_workload_date = db.Column(db.Date)
    latest_fatigue_calculated_at = db.Column(db.DateTime)

    records_processed = db.Column(db.Integer, default=0)
    new_logs_added = db.Column(db.Integer, default=0)
    pitchers_updated = db.Column(db.Integer, default=0)
    errors = db.Column(db.Integer, default=0)
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'status': self.status,
            'source': self.source,
            'latest_game_date': self.latest_game_date.isoformat() if self.latest_game_date else None,
            'latest_workload_date': self.latest_workload_date.isoformat() if self.latest_workload_date else None,
            'latest_fatigue_calculated_at': self.latest_fatigue_calculated_at.isoformat() if self.latest_fatigue_calculated_at else None,
            'records_processed': self.records_processed or 0,
            'new_logs_added': self.new_logs_added or 0,
            'pitchers_updated': self.pitchers_updated or 0,
            'errors': self.errors or 0,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
