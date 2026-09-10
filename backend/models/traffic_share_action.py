from utils.db import db
from utils.time import utc_now_naive


class TrafficShareAction(db.Model):
    """One completed, privacy-bounded evidence sharing action."""

    __tablename__ = 'traffic_share_actions'

    __table_args__ = (
        db.Index('ix_traffic_share_actions_event_id', 'event_id', unique=True),
        db.Index('ix_traffic_share_actions_occurred_at', 'occurred_at'),
        db.Index('ix_traffic_share_actions_occurred_action', 'occurred_at', 'action'),
        db.Index('ix_traffic_share_actions_occurred_card_type', 'occurred_at', 'card_type'),
        db.Index('ix_traffic_share_actions_occurred_team', 'occurred_at', 'team_ref'),
        db.Index(
            'ix_traffic_share_actions_occurred_comparison_pair',
            'occurred_at', 'team_a_ref', 'team_b_ref',
        ),
        db.Index('ix_traffic_share_actions_occurred_card_version', 'occurred_at', 'card_version'),
        db.Index('ix_traffic_share_actions_occurred_story_angle', 'occurred_at', 'story_angle'),
    )

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(36), nullable=False)
    visitor_id = db.Column(db.String(36), nullable=False)
    session_id = db.Column(db.String(36), nullable=False)
    occurred_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    surface = db.Column(db.String(32), nullable=False)
    card_type = db.Column(db.String(16), nullable=False)
    action = db.Column(db.String(24), nullable=False)
    team_ref = db.Column(db.String(16))
    team_a_ref = db.Column(db.String(16))
    team_b_ref = db.Column(db.String(16))
    evidence_target = db.Column(db.String(32))
    card_version = db.Column(db.String(32))
    story_angle = db.Column(db.String(48))
    data_through = db.Column(db.Date)
    site_host = db.Column(db.String(253), nullable=False)
    device_class = db.Column(db.String(16), nullable=False, default='unknown')
    is_bot = db.Column(db.Boolean, nullable=False, default=False)
    schema_version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
