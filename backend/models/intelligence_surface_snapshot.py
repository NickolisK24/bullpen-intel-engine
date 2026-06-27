from utils.db import db
from utils.time import utc_now_naive


class IntelligenceSurfaceSnapshot(db.Model):
    """Precomputed GET /api/bullpen/intelligence/today response for one slate.

    The Intelligence Surface lead story is expensive to build on demand (resolve
    candidates, build StoryPackages, render writers, rank, serialize). Postgame
    refresh derives the completed-game contexts for a slate, then stores the
    finished endpoint response here keyed by ``reference_date`` and
    ``snapshot_version``. The public endpoint serves ``response_json`` verbatim
    when a snapshot exists and falls back to live generation when it does not, so
    the response contract is identical either way.

    Identity is (reference_date, snapshot_version): one published surface per
    slate per response shape. Bumping ``snapshot_version`` invalidates every
    stored snapshot without a data migration.
    """

    __tablename__ = 'intelligence_surface_snapshots'

    __table_args__ = (
        db.UniqueConstraint(
            'reference_date', 'snapshot_version',
            name='uq_intelligence_surface_snapshots_date_version',
        ),
        db.Index('ix_intelligence_surface_snapshots_version_date',
                 'snapshot_version', 'reference_date'),
    )

    id = db.Column(db.Integer, primary_key=True)

    # ── Identity / lookup ──────────────────────────────────────────────────────
    reference_date = db.Column(db.Date, nullable=False)
    snapshot_version = db.Column(db.String(40), nullable=False)

    # ── Served payload (the exact endpoint response) ───────────────────────────
    status = db.Column(db.String(20), nullable=False)        # 'ok' / 'empty'
    response_json = db.Column(db.JSON, nullable=False)

    # ── Denormalized summary (diagnostics / indexing; not served directly) ─────
    lead_story_team_id = db.Column(db.Integer, nullable=True)
    lead_story_game_pk = db.Column(db.Integer, nullable=True)
    candidates_considered = db.Column(db.Integer, nullable=False, default=0)
    publishable_candidates = db.Column(db.Integer, nullable=False, default=0)
    empty_reason = db.Column(db.String(60), nullable=True)
    errors = db.Column(db.Integer, nullable=False, default=0)

    # ── Provenance ─────────────────────────────────────────────────────────────
    source = db.Column(db.String(40), nullable=False, default='on_demand')
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
            'lead_story_team_id': self.lead_story_team_id,
            'lead_story_game_pk': self.lead_story_game_pk,
            'candidates_considered': self.candidates_considered,
            'publishable_candidates': self.publishable_candidates,
            'empty_reason': self.empty_reason,
            'errors': self.errors,
            'source': self.source,
            'generated_at': self.generated_at.isoformat() if self.generated_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return (
            f'<IntelligenceSurfaceSnapshot reference_date={self.reference_date} '
            f'status={self.status} version={self.snapshot_version}>'
        )
