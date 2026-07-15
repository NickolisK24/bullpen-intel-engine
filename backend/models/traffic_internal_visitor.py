from utils.db import db
from utils.time import utc_now_naive


class TrafficInternalVisitor(db.Model):
    """Pseudonymous visitor ids excluded from external-traffic reporting."""

    __tablename__ = 'traffic_internal_visitors'

    __table_args__ = (
        db.Index('ix_traffic_internal_visitors_visitor_id', 'visitor_id', unique=True),
    )

    id = db.Column(db.Integer, primary_key=True)
    visitor_id = db.Column(db.String(36), nullable=False)
    registered_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    registered_by_user_id = db.Column(db.Integer)
    registration_source = db.Column(
        db.String(32),
        nullable=False,
        default='authenticated_email_allowlist',
    )
