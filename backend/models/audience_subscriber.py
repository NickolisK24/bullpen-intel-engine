from utils.db import db
from utils.time import utc_now_naive


AUDIENCE_SUBSCRIBER_STATUS_SUBSCRIBED = 'subscribed'


class AudienceSubscriber(db.Model):
    """Durable email capture for the public BaseballOS audience.

    This is intentionally separate from users, team following, digest
    preferences, and delivery metrics. It records only the signup channel and
    the welcome-email attempt state needed for the public capture form.
    """
    __tablename__ = 'audience_subscribers'

    __table_args__ = (
        db.Index(
            'ix_audience_subscribers_email_normalized',
            'email_normalized',
            unique=True,
        ),
        db.Index('ix_audience_subscribers_status', 'status'),
    )

    id = db.Column(db.Integer, primary_key=True)
    email_normalized = db.Column(db.String(320), nullable=False)
    email_original = db.Column(db.String(320))
    source = db.Column(db.String(64), nullable=False, default='unknown')
    status = db.Column(
        db.String(32),
        nullable=False,
        default=AUDIENCE_SUBSCRIBER_STATUS_SUBSCRIBED,
    )
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now_naive,
        onupdate=utc_now_naive,
    )
    welcome_sent_at = db.Column(db.DateTime)
    last_welcome_error = db.Column(db.String(128))
