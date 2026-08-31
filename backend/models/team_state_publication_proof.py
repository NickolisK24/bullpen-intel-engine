"""Durable Team State proof for one trusted dashboard publication."""

from utils.db import db
from utils.time import utc_now_naive


class TeamStatePublicationProof(db.Model):
    __tablename__ = 'team_state_publication_proofs'
    __table_args__ = (
        db.UniqueConstraint('snapshot_id', name='uq_team_state_proof_snapshot'),
        db.CheckConstraint(
            "overall_verdict IN ('PASS', 'PASS_WITH_INCONCLUSIVE', 'FAIL')",
            name='ck_team_state_proof_verdict',
        ),
        db.Index('ix_team_state_proof_sync_run', 'sync_run_id'),
        db.Index('ix_team_state_proof_generated_at', 'generated_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    snapshot_id = db.Column(db.Integer, db.ForeignKey('dashboard_snapshots.id'), nullable=False)
    sync_run_id = db.Column(db.Integer, db.ForeignKey('sync_runs.id'), nullable=True)
    data_through = db.Column(db.Date, nullable=False)
    proof = db.Column(db.JSON, nullable=False)
    overall_verdict = db.Column(db.String(32), nullable=False)
    captured_team_count = db.Column(db.Integer, nullable=False)
    method_version = db.Column(db.String(64), nullable=True)
    publication_source = db.Column(db.String(120), nullable=True)
    generated_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    def to_dict(self):
        return {
            'id': self.id,
            'snapshot_id': self.snapshot_id,
            'sync_run_id': self.sync_run_id,
            'data_through': self.data_through.isoformat(),
            'proof': self.proof,
            'overall_verdict': self.overall_verdict,
            'captured_team_count': self.captured_team_count,
            'method_version': self.method_version,
            'publication_source': self.publication_source,
            'generated_at': self.generated_at.isoformat(),
        }
