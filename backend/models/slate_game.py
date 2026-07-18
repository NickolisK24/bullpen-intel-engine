from utils.db import db
from utils.time import utc_now_naive


class SlateGame(db.Model):
    """Game-centric MLB schedule authority used by private postability reads."""

    __tablename__ = 'slate_games'

    STATE_UPCOMING = 'upcoming'
    STATE_LIVE = 'live'
    STATE_COMPLETED = 'completed'
    STATE_UNCERTAIN = 'uncertain'
    STATE_CANCELLED = 'cancelled'

    __table_args__ = (
        db.Index('ix_slate_games_game_date_et', 'game_date_et'),
        db.Index('ix_slate_games_normalized_state', 'normalized_state'),
        db.Index('ix_slate_games_home_team_date', 'home_team_id', 'game_date_et'),
        db.Index('ix_slate_games_away_team_date', 'away_team_id', 'game_date_et'),
    )

    game_pk = db.Column(db.Integer, primary_key=True)
    game_date_et = db.Column(db.Date, nullable=False)
    game_time_utc = db.Column(db.DateTime, nullable=False)
    home_team_id = db.Column(db.Integer, nullable=False)
    away_team_id = db.Column(db.Integer, nullable=False)

    status_abstract = db.Column(db.String(40), nullable=True)
    status_detailed = db.Column(db.String(80), nullable=True)
    status_code = db.Column(db.String(10), nullable=True)
    normalized_state = db.Column(
        db.String(20), nullable=False, default=STATE_UNCERTAIN
    )

    # MLB uses N/Y/S; preserve the source flag so split doubleheaders remain
    # distinguishable without collapsing either game's row.
    doubleheader_flag = db.Column(db.String(2), nullable=True)
    game_number = db.Column(db.Integer, nullable=True)
    scheduled_innings = db.Column(db.Integer, nullable=True)
    last_synced = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    MUTABLE_COLUMNS = (
        'game_date_et',
        'game_time_utc',
        'home_team_id',
        'away_team_id',
        'status_abstract',
        'status_detailed',
        'status_code',
        'normalized_state',
        'doubleheader_flag',
        'game_number',
        'scheduled_innings',
        'last_synced',
    )

    def to_dict(self):
        return {
            'game_pk': self.game_pk,
            'game_date_et': (
                self.game_date_et.isoformat() if self.game_date_et else None
            ),
            'game_time_utc': (
                self.game_time_utc.isoformat() + 'Z' if self.game_time_utc else None
            ),
            'home_team_id': self.home_team_id,
            'away_team_id': self.away_team_id,
            'status': {
                'abstract': self.status_abstract,
                'detailed': self.status_detailed,
                'code': self.status_code,
                'normalized': self.normalized_state,
            },
            'doubleheader_flag': self.doubleheader_flag,
            'game_number': self.game_number,
            'scheduled_innings': self.scheduled_innings,
            'last_synced': (
                self.last_synced.isoformat() + 'Z' if self.last_synced else None
            ),
        }
