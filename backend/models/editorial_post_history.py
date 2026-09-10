import json

from utils.db import db
from utils.time import utc_now_naive


class EditorialPostHistory(db.Model):
    """Private posting receipt and repetition input for slate editorial reads."""

    __tablename__ = 'editorial_post_history'
    __table_args__ = (
        db.Index('ix_editorial_post_history_team_posted', 'team_id', 'posted_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, nullable=False)
    story_shape = db.Column(db.String(20), nullable=False)
    posted_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    platform = db.Column(db.String(20), nullable=True)
    team_ids_json = db.Column(db.Text, nullable=True)
    game_pks_json = db.Column(db.Text, nullable=True)
    candidate_id = db.Column(db.String(160), nullable=True, index=True)
    evidence_reference = db.Column(db.String(64), nullable=True)
    evidence_snapshot_json = db.Column(db.Text, nullable=True)
    generated_draft_text = db.Column(db.Text, nullable=True)
    final_post_text = db.Column(db.Text, nullable=True)
    external_post_url = db.Column(db.Text, nullable=True)
    score_version = db.Column(db.String(40), nullable=True)
    source_briefing_date = db.Column(db.Date, nullable=True)

    @staticmethod
    def _loads(value, fallback):
        if not value:
            return fallback
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return fallback

    def to_dict(self):
        return {
            'id': self.id,
            'team_id': self.team_id,
            'story_shape': self.story_shape,
            'posted_at': self.posted_at.isoformat() + 'Z' if self.posted_at else None,
            'platform': self.platform,
            'team_ids': self._loads(self.team_ids_json, [self.team_id]),
            'game_pks': self._loads(self.game_pks_json, []),
            'candidate_id': self.candidate_id,
            'evidence_reference': self.evidence_reference,
            'generated_draft_text': self.generated_draft_text,
            'final_post_text': self.final_post_text,
            'external_post_url': self.external_post_url,
            'score_version': self.score_version,
            'source_briefing_date': self.source_briefing_date.isoformat() if self.source_briefing_date else None,
        }
