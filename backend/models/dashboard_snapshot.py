from utils.db import db
from utils.time import utc_now_naive


class DashboardSnapshot(db.Model):
    __tablename__ = 'dashboard_snapshots'

    __table_args__ = (
        db.Index('ix_dashboard_snapshots_type_status_created',
                 'snapshot_type', 'status', 'created_at'),
        db.Index('ix_dashboard_snapshots_sync_run', 'sync_run_id'),
        db.Index('ix_dashboard_snapshots_type_published',
                 'snapshot_type', 'is_published', 'status', 'payload_version'),
    )

    id = db.Column(db.Integer, primary_key=True)
    snapshot_type = db.Column(db.String(50), nullable=False)
    sync_run_id = db.Column(db.Integer, db.ForeignKey('sync_runs.id'), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='ready')
    is_published = db.Column(db.Boolean, nullable=False, default=False)
    published_at = db.Column(db.DateTime)
    payload = db.Column(db.JSON)
    payload_version = db.Column(db.Integer, nullable=False, default=1)
    data_through = db.Column(db.Date)
    availability_reference_date = db.Column(db.Date)
    snapshot_generated_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    source = db.Column(db.String(30), nullable=False, default='sync')
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now_naive,
        onupdate=utc_now_naive,
    )
    error_message = db.Column(db.Text)

    def to_dict(self):
        return {
            'id': self.id,
            'snapshot_type': self.snapshot_type,
            'sync_run_id': self.sync_run_id,
            'status': self.status,
            'is_published': bool(self.is_published),
            'published_at': self.published_at.isoformat() if self.published_at else None,
            'payload_version': self.payload_version,
            'data_through': self.data_through.isoformat() if self.data_through else None,
            'availability_reference_date': (
                self.availability_reference_date.isoformat()
                if self.availability_reference_date
                else None
            ),
            'snapshot_generated_at': (
                self.snapshot_generated_at.isoformat()
                if self.snapshot_generated_at
                else None
            ),
            'source': self.source,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'error_message': self.error_message,
        }
