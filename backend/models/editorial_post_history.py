from utils.db import db
from utils.time import utc_now_naive


class EditorialPostHistory(db.Model):
    """Minimum internal history used only to diversify editorial ranking."""

    __tablename__ = 'editorial_post_history'
    __table_args__ = (
        db.Index('ix_editorial_post_history_team_posted', 'team_id', 'posted_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, nullable=False)
    story_shape = db.Column(db.String(20), nullable=False)
    posted_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    def to_dict(self):
        return {
            'id': self.id,
            'team_id': self.team_id,
            'story_shape': self.story_shape,
            'posted_at': self.posted_at.isoformat() + 'Z' if self.posted_at else None,
        }
