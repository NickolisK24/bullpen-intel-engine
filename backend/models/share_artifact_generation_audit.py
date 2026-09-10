"""Durable internal audit of Team State Share Artifact generation attempts
(Share Cards SC-03A).

Every governed generation attempt — whether it published a new artifact, reused
an equivalent one, was refused by SC-02 eligibility, or failed closed on an
operational error — is recorded here so generation is fully traceable. The row
captures only deterministic, governed information (no free-form copy, no
sensitive stack traces). It is an internal operator record; it is not a public
engagement-analytics event and it is not a second analytics subsystem.
"""

from utils.db import db
from utils.time import utc_now_naive


class ShareArtifactGenerationAudit(db.Model):
    __tablename__ = 'share_artifact_generation_audits'

    OUTCOME_PUBLISHED = 'published'
    OUTCOME_REUSED = 'reused'
    OUTCOME_REFUSED = 'refused'
    OUTCOME_FAILED_CLOSED = 'failed_closed'
    OUTCOMES = (OUTCOME_PUBLISHED, OUTCOME_REUSED, OUTCOME_REFUSED, OUTCOME_FAILED_CLOSED)

    __table_args__ = (
        db.CheckConstraint(
            "outcome IN ('published', 'reused', 'refused', 'failed_closed')",
            name='ck_sa_gen_audits_outcome',
        ),
        db.Index('ix_sa_gen_audits_team', 'team_id'),
        db.Index('ix_sa_gen_audits_team_created', 'team_id', 'created_at'),
        db.Index('ix_sa_gen_audits_outcome', 'outcome'),
        db.Index('ix_sa_gen_audits_artifact', 'share_artifact_id'),
    )

    id = db.Column(db.Integer, primary_key=True)

    team_id = db.Column(db.Integer, nullable=False)
    requested_product_date = db.Column(db.Date, nullable=True)
    resolved_product_date = db.Column(db.Date, nullable=True)

    source_snapshot_id = db.Column(db.Integer, nullable=True)
    source_sync_run_id = db.Column(db.Integer, nullable=True)
    payload_version = db.Column(db.String(64), nullable=True)

    outcome = db.Column(db.String(20), nullable=False)
    eligible = db.Column(db.Boolean, nullable=False, default=False)
    blocking_conditions = db.Column(db.JSON, nullable=True)
    reasons = db.Column(db.JSON, nullable=True)

    # Linkage to the resulting immutable artifact (present only for
    # published/reused outcomes). Soft FK to share_artifacts; published
    # artifacts are never deletable, so the reference stays durable.
    share_artifact_id = db.Column(
        db.Integer, db.ForeignKey('share_artifacts.id'), nullable=True,
    )
    artifact_public_id = db.Column(db.String(64), nullable=True)
    created_new = db.Column(db.Boolean, nullable=False, default=False)
    reused_existing = db.Column(db.Boolean, nullable=False, default=False)

    # Governed provenance of the attempt (actor/source category only — never
    # sensitive identifiers). ``failure_code`` is a governed, non-sensitive code
    # for fail-closed operational errors; raw stack traces are never stored.
    request_source = db.Column(db.String(60), nullable=True)
    actor = db.Column(db.String(120), nullable=True)
    failure_code = db.Column(db.String(80), nullable=True)

    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'team_id': self.team_id,
            'requested_product_date': _iso(self.requested_product_date),
            'resolved_product_date': _iso(self.resolved_product_date),
            'source_snapshot_id': self.source_snapshot_id,
            'source_sync_run_id': self.source_sync_run_id,
            'payload_version': self.payload_version,
            'outcome': self.outcome,
            'eligible': self.eligible,
            'blocking_conditions': list(self.blocking_conditions or []),
            'reasons': list(self.reasons or []),
            'share_artifact_id': self.share_artifact_id,
            'artifact_public_id': self.artifact_public_id,
            'created_new': self.created_new,
            'reused_existing': self.reused_existing,
            'request_source': self.request_source,
            'actor': self.actor,
            'failure_code': self.failure_code,
            'created_at': _iso(self.created_at),
        }


def _iso(value):
    return value.isoformat() if value is not None else None
