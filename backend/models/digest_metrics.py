"""Digest metrics & return-tracking models (Phase D2E).

Durable storage for measuring the D2 return loop — distinct from logs so the
question "is the digest actually bringing users back?" can be answered. Two
tables:

  • digest_runs       — one row per ``run_digest_job`` execution (the per-run
    aggregate: considered / sent / suppressed / skipped / errors).
  • digest_deliveries — one row per eligible per-user decision (a real send or
    an engine-level suppression). Sent rows carry the open / click / return
    tracking state used to compute open-, click-, and return-rates.

These tables hold measurement only — never intelligence and never message
content. High-volume pre-composition skips (not opted in, unverified) are
counted on the run row but are not persisted as delivery rows.
"""

from utils.db import db
from utils.time import utc_now_naive


# Delivery outcomes that are persisted as a digest_deliveries row.
STATUS_SENT = 'sent'
STATUS_SUPPRESSED = 'suppressed'

DEFAULT_DIGEST_TYPE = 'team_digest_v1'


class DigestRun(db.Model):
    """Aggregate metrics for a single digest job run."""
    __tablename__ = 'digest_runs'

    id = db.Column(db.Integer, primary_key=True)
    started_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    finished_at = db.Column(db.DateTime)
    dry_run = db.Column(db.Boolean, nullable=False, default=False)
    # ISO date (YYYY-MM-DD) the run was evaluated against, or null.
    reference_date = db.Column(db.String(10))
    considered = db.Column(db.Integer, nullable=False, default=0)
    sent = db.Column(db.Integer, nullable=False, default=0)
    suppressed = db.Column(db.Integer, nullable=False, default=0)
    skipped = db.Column(db.Integer, nullable=False, default=0)
    errors = db.Column(db.Integer, nullable=False, default=0)
    # {"suppressed_by_reason": {...}, "skipped_by_reason": {...}}
    breakdown = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    def to_dict(self):
        return {
            'id': self.id,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'finished_at': self.finished_at.isoformat() if self.finished_at else None,
            'dry_run': bool(self.dry_run),
            'reference_date': self.reference_date,
            'considered': self.considered,
            'sent': self.sent,
            'suppressed': self.suppressed,
            'skipped': self.skipped,
            'errors': self.errors,
            'breakdown': self.breakdown or {},
        }


class DigestDelivery(db.Model):
    """A single per-user digest decision and its engagement / return state."""
    __tablename__ = 'digest_deliveries'

    __table_args__ = (
        db.Index('ix_digest_deliveries_user', 'user_id'),
        db.Index('ix_digest_deliveries_status', 'status'),
        db.Index('ix_digest_deliveries_run', 'run_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    run_id = db.Column(db.Integer, db.ForeignKey('digest_runs.id', ondelete='SET NULL'))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'))
    team_id = db.Column(db.Integer)
    digest_type = db.Column(db.String(64), nullable=False, default=DEFAULT_DIGEST_TYPE)
    status = db.Column(db.String(16), nullable=False)          # sent | suppressed
    reason = db.Column(db.String(64))                          # suppression reason, if any

    sent_at = db.Column(db.DateTime)
    opened_at = db.Column(db.DateTime)                         # first open
    open_count = db.Column(db.Integer, nullable=False, default=0)
    clicked_at = db.Column(db.DateTime)                       # first click
    click_count = db.Column(db.Integer, nullable=False, default=0)
    returned_at = db.Column(db.DateTime)                      # first_return_after_digest
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    def to_dict(self):
        return {
            'id': self.id,
            'run_id': self.run_id,
            'user_id': self.user_id,
            'team_id': self.team_id,
            'digest_type': self.digest_type,
            'status': self.status,
            'reason': self.reason,
            'sent_at': self.sent_at.isoformat() if self.sent_at else None,
            'opened_at': self.opened_at.isoformat() if self.opened_at else None,
            'open_count': self.open_count,
            'clicked_at': self.clicked_at.isoformat() if self.clicked_at else None,
            'click_count': self.click_count,
            'returned_at': self.returned_at.isoformat() if self.returned_at else None,
        }
