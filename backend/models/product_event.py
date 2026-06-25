"""Canonical product event log (Phase D2A-1).

The single, append-only source of truth for Product Intelligence. Every row is an
immutable fact — a thing that happened, stamped with when it happened. Current
state (open counts, return timestamps, opt-in status, …) is never stored here; it
stays derived in its own tables (``digest_deliveries``, ``User.notification_prefs``).
Rows are only ever inserted — never updated or deleted — so history cannot be
rewritten.

This table holds measurement only — never message content and never intelligence
(no scoring, no derived status). It is intentionally decoupled: the actor / entity
references (``user_id``, ``team_id``, ``run_id``, ``delivery_id``) are plain
integers, NOT foreign keys, so the log survives deletion of the things it
references and a delete elsewhere never cascades into a historical fact.

D2A-1 canonicalizes the existing digest lifecycle into this log. Later phases read
from it; they do not change how it is written.
"""

from utils.db import db
from utils.time import utc_now_naive


# Stamped on every event so the payload shape can evolve without rewriting or
# misreading older facts. Bump only when an event payload changes incompatibly.
EVENT_SCHEMA_VERSION = 1


class ProductEvent(db.Model):
    """One immutable Product Intelligence fact (append-only)."""
    __tablename__ = 'product_events'

    __table_args__ = (
        # Query shapes expected for the next ~12 months: a funnel/metric for one
        # event type over a time range (composite), everything in a time range
        # (occurred_at), and one user's history (user_id). Kept deliberately lean
        # — this is a high-write, append-only table.
        db.Index('ix_product_events_occurred_at', 'occurred_at'),
        db.Index('ix_product_events_user', 'user_id'),
        db.Index('ix_product_events_name_occurred', 'event_name', 'occurred_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    event_name = db.Column(db.String(64), nullable=False)
    # When the fact actually occurred (UTC, naive — matching every other column).
    occurred_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    schema_version = db.Column(db.Integer, nullable=False, default=EVENT_SCHEMA_VERSION)

    # Actor (nullable: some facts are pre-auth or system-level). Plain integer /
    # opaque id — deliberately NOT a foreign key (see module docstring).
    user_id = db.Column(db.Integer)
    anon_id = db.Column(db.String(64))

    # Entity references (all nullable, all plain integers — not foreign keys).
    team_id = db.Column(db.Integer)
    run_id = db.Column(db.Integer)
    delivery_id = db.Column(db.Integer)

    # Where the fact originated + event-specific payload (JSON-safe primitives).
    source = db.Column(db.String(32))
    payload = db.Column(db.JSON)

    # When the row was written (audit only; equals occurred_at for live events).
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    def to_dict(self):
        return {
            'id': self.id,
            'event_name': self.event_name,
            'occurred_at': self.occurred_at.isoformat() if self.occurred_at else None,
            'schema_version': self.schema_version,
            'user_id': self.user_id,
            'anon_id': self.anon_id,
            'team_id': self.team_id,
            'run_id': self.run_id,
            'delivery_id': self.delivery_id,
            'source': self.source,
            'payload': self.payload or {},
        }
