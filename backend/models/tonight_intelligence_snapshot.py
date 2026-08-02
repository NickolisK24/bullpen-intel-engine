from utils.db import db
from utils.time import utc_now_naive


# The one governed width for Tonight snapshot provenance, owned here because the
# column is the thing being bounded. Every validator and the model itself read
# this constant; the Alembic revision that widened the column states the same
# number in DDL, and a PostgreSQL test asserts the live column matches it, so
# the two cannot drift silently.
#
# Sized from real composition, not guessed. The production value
# ``github_actions_morning:schedule_coherence`` is 41 characters — one past the
# original 40 — and the same lane's default source composes to 41 as well, so
# the failure was structural rather than specific to one workflow input. 128
# keeps the field finite and governed while leaving room for foreseeable
# ``source:purpose`` composition; an unbounded TEXT column would trade one
# silent failure for an unbounded one, and 41 or 42 would leave the next
# composed purpose to rediscover this incident.
TONIGHT_SNAPSHOT_SOURCE_MAX_LENGTH = 128


class TonightIntelligenceSnapshot(db.Model):
    """Precomputed GET /api/bullpen/intelligence/tonight response for one slate.

    The Tonight cards are expensive to build on demand (resolve schedule contexts
    for every team, build each playing team's bullpen context, select candidates,
    shape the public envelope). This stores the finished public response per slate
    keyed by ``reference_date`` and ``snapshot_version``. The endpoint serves
    ``response_json`` with lightweight request-time provenance when a snapshot
    exists and falls back to bounded live generation when it does not.

    Mirrors the Intelligence Surface snapshot pattern; it is a dedicated table
    because the Tonight response shape (cards) differs from the lead-story shape.
    Identity is (reference_date, snapshot_version): one published Tonight surface
    per slate per response shape.
    """

    __tablename__ = 'tonight_intelligence_snapshots'

    __table_args__ = (
        db.UniqueConstraint(
            'reference_date', 'snapshot_version',
            name='uq_tonight_intelligence_snapshots_date_version',
        ),
        db.Index('ix_tonight_intelligence_snapshots_version_date',
                 'snapshot_version', 'reference_date'),
        db.Index('ix_tonight_intelligence_snapshots_reference_date',
                 'reference_date'),
    )

    id = db.Column(db.Integer, primary_key=True)

    # ── Identity / lookup ──────────────────────────────────────────────────────
    reference_date = db.Column(db.Date, nullable=False)
    snapshot_version = db.Column(db.String(40), nullable=False)

    # ── Served payload (the exact public endpoint response) ────────────────────
    status = db.Column(db.String(20), nullable=False)        # 'ok' / 'empty'
    response_json = db.Column(db.JSON, nullable=False)

    # ── Denormalized summary (diagnostics; not served directly) ────────────────
    card_count = db.Column(db.Integer, nullable=False, default=0)
    empty_reason = db.Column(db.String(60), nullable=True)

    # ── Provenance ─────────────────────────────────────────────────────────────
    source = db.Column(
        db.String(TONIGHT_SNAPSHOT_SOURCE_MAX_LENGTH),
        nullable=False, default='on_demand',
    )
    generated_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now_naive, onupdate=utc_now_naive
    )

    def to_dict(self):
        return {
            'id': self.id,
            'reference_date': self.reference_date.isoformat() if self.reference_date else None,
            'snapshot_version': self.snapshot_version,
            'status': self.status,
            'response_json': self.response_json,
            'card_count': self.card_count,
            'empty_reason': self.empty_reason,
            'source': self.source,
            'generated_at': self.generated_at.isoformat() if self.generated_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return (
            f'<TonightIntelligenceSnapshot reference_date={self.reference_date} '
            f'status={self.status} version={self.snapshot_version}>'
        )
