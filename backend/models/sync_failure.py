from utils.db import db
from utils.time import utc_now_naive


class SyncFailure(db.Model):
    """
    Dead-letter capture for records that could not be processed during a sync.

    Partial-failure semantics: one bad record (a poisoned pitcher game log, a
    failed per-entity API fetch) must not abort an entire team/league sync. The
    sync processes what succeeds, writes the failed entity here with enough
    context to retry it, and marks its run 'partial'. Nothing is silently
    dropped — every dead-letter is durable, queryable, and counted.
    """

    __tablename__ = 'sync_failures'

    __table_args__ = (
        db.Index('ix_sync_failures_resolved', 'resolved'),
        db.Index('ix_sync_failures_run', 'sync_run_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    # The run that produced this failure (nullable so a dead-letter can still be
    # recorded if the run row itself could not be persisted).
    sync_run_id = db.Column(db.Integer, db.ForeignKey('sync_runs.id'), nullable=True)
    job_name = db.Column(db.String(50), nullable=False, default='daily_sync')

    # What failed and how to retry it.
    entity_type = db.Column(db.String(50), nullable=False)
    entity_ref = db.Column(db.String(120))
    # Payload/identifier needed to retry the entity (e.g. pitcher_id, mlb_id,
    # season, game_pk). db.JSON maps to JSONB on Postgres and TEXT on SQLite.
    payload = db.Column(db.JSON)

    error = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    resolved = db.Column(db.Boolean, nullable=False, default=False)
    resolved_at = db.Column(db.DateTime)

    def to_dict(self):
        return {
            'id': self.id,
            'sync_run_id': self.sync_run_id,
            'job_name': self.job_name,
            'entity_type': self.entity_type,
            'entity_ref': self.entity_ref,
            'payload': self.payload,
            'error': self.error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'resolved': bool(self.resolved),
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
        }
