from utils.db import db
from utils.time import utc_now_naive


class TrafficPageView(db.Model):
    """One canonical public-surface view with privacy-bounded acquisition data."""

    __tablename__ = 'traffic_page_views'

    __table_args__ = (
        db.Index('ix_traffic_page_views_view_id', 'view_id', unique=True),
        db.Index('ix_traffic_page_views_occurred_at', 'occurred_at'),
        db.Index('ix_traffic_page_views_visitor_occurred', 'visitor_id', 'occurred_at'),
        db.Index('ix_traffic_page_views_session_occurred', 'session_id', 'occurred_at'),
        db.Index('ix_traffic_page_views_route_occurred', 'route', 'occurred_at'),
        db.Index('ix_traffic_page_views_site_host_occurred', 'site_host', 'occurred_at'),
        db.Index('ix_traffic_page_views_bot_occurred', 'is_bot', 'occurred_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    view_id = db.Column(db.String(36), nullable=False)
    visitor_id = db.Column(db.String(36), nullable=False)
    session_id = db.Column(db.String(36), nullable=False)
    occurred_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    route = db.Column(db.String(256), nullable=False)
    surface = db.Column(db.String(32), nullable=False)
    view_mode = db.Column(db.String(16))
    team_ref = db.Column(db.String(16))
    pitcher_id = db.Column(db.Integer)
    referrer_domain = db.Column(db.String(253))
    utm_source = db.Column(db.String(64))
    utm_medium = db.Column(db.String(64))
    utm_campaign = db.Column(db.String(128))
    utm_content = db.Column(db.String(128))
    site_host = db.Column(db.String(253), nullable=False)
    device_class = db.Column(db.String(16), nullable=False, default='unknown')
    is_bot = db.Column(db.Boolean, nullable=False, default=False)
    schema_version = db.Column(db.Integer, nullable=False, default=1)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
