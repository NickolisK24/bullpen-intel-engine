from utils.db import db
from utils.time import utc_now_naive


class User(db.Model):
    """A BaseballOS user identity.

    Identity infrastructure only (Phase D1B): this table exists so future
    authentication (D1C) and server-side team following (D1D) have a durable,
    cross-device account to attach to. It is deliberately isolated from the
    baseball intelligence models and carries only what a magic-link account
    needs — no password column (magic-link auth is added in D1C) and no sessions
    table (bearer tokens are stateless and signed).
    """
    __tablename__ = 'users'

    __table_args__ = (
        db.Index('ix_users_email', 'email', unique=True),
    )

    id = db.Column(db.Integer, primary_key=True)
    # Lowercased email is both the identity and the channel a future digest (D2)
    # will use. Normalization (lowercasing) is the caller's responsibility; the
    # column only guarantees uniqueness.
    email = db.Column(db.String(320), nullable=False)
    email_verified_at = db.Column(db.DateTime)
    onboarded_at = db.Column(db.DateTime)
    # Reserved for D2 notification preferences so that phase needs no migration.
    # Null means "defaults apply". Holds preferences only — never intelligence.
    notification_prefs = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    last_login_at = db.Column(db.DateTime)

    followed_teams = db.relationship(
        'UserFollowedTeam',
        back_populates='user',
        cascade='all, delete-orphan',
        order_by='UserFollowedTeam.created_at',
    )

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'email_verified': self.email_verified_at is not None,
            'onboarded': self.onboarded_at is not None,
            'followed_teams': [team.to_dict() for team in self.followed_teams],
        }


class UserFollowedTeam(db.Model):
    """A team a user follows.

    The data model supports many teams per user from the start so a later UX
    decision (lead with one "primary" team vs. show all) needs no migration.
    ``team_id`` is the MLB team id used across the app (pitchers/endpoints);
    teams are not a DB model, so this is a plain integer validated against
    /api/bullpen/teams rather than a foreign key to a teams table.
    """
    __tablename__ = 'user_followed_teams'

    __table_args__ = (
        db.UniqueConstraint('user_id', 'team_id', name='uq_user_followed_teams_user_team'),
        db.Index('ix_user_followed_teams_user', 'user_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False,
    )
    team_id = db.Column(db.Integer, nullable=False)
    is_primary = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    user = db.relationship('User', back_populates='followed_teams')

    def to_dict(self):
        return {
            'team_id': self.team_id,
            'is_primary': bool(self.is_primary),
        }
