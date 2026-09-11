"""Bounded operator evidence for suppressed compatibility mutations."""

from utils.db import db
from utils.time import utc_now_naive


class CompatibilityWriteEvent(db.Model):
    __tablename__ = 'compatibility_write_events'
    __table_args__ = (
        db.Index('ix_compatibility_write_events_created', 'created_at'),
        db.Index('ix_compatibility_write_events_resource', 'resource_type', 'resource_key', 'created_at'),
    )

    id = db.Column(db.BigInteger().with_variant(db.Integer, 'sqlite'), primary_key=True)
    resource_type = db.Column(db.String(40), nullable=False)
    resource_key = db.Column(db.String(100), nullable=False)
    outcome = db.Column(db.String(60), nullable=False)
    details_json = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
