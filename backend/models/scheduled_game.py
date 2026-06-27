from utils.db import db
from utils.time import utc_now_naive


class ScheduledGame(db.Model):
    """One team's view of one MLB game — past, present, OR future.

    Unlike game_logs / completed_game_contexts / postgame_processed_games (all of
    which are strictly about games already played), this table stores the rolling
    MLB schedule, including games not yet played. It is the durable foundation for
    forward-looking schedule context (off days, consecutive games, games ahead).

    Identity is (team_id, game_pk): one row per team per game, so a single MLB game
    produces two rows (home and away). ``team_id`` follows the project-wide
    convention of a plain integer (there is no teams table).

    Status is stored two ways: the raw MLB ``status_code`` is preserved verbatim,
    and ``status_state`` is a conservative normalization into a small, stable set
    (scheduled / final / postponed / suspended / other) so downstream consumers do
    not have to reason about every MLB status string.
    """

    __tablename__ = 'scheduled_games'

    # Normalized status states — deliberately small and stable.
    STATE_SCHEDULED = 'scheduled'
    STATE_FINAL = 'final'
    STATE_POSTPONED = 'postponed'
    STATE_SUSPENDED = 'suspended'
    STATE_OTHER = 'other'

    __table_args__ = (
        db.UniqueConstraint('team_id', 'game_pk',
                            name='uq_scheduled_games_team_game'),
        db.Index('ix_scheduled_games_team_date', 'team_id', 'game_date'),
        db.Index('ix_scheduled_games_game_date', 'game_date'),
        db.Index('ix_scheduled_games_status_state', 'status_state'),
    )

    id = db.Column(db.Integer, primary_key=True)

    # ── Identity ───────────────────────────────────────────────────────────────
    team_id = db.Column(db.Integer, nullable=False)
    game_pk = db.Column(db.Integer, nullable=False)

    # ── When ───────────────────────────────────────────────────────────────────
    game_date = db.Column(db.Date, nullable=False)
    game_datetime = db.Column(db.DateTime, nullable=True)  # naive UTC start time

    # ── Matchup (this team's perspective) ──────────────────────────────────────
    opponent_team_id = db.Column(db.Integer, nullable=True)
    home_away = db.Column(db.String(10), nullable=True)  # 'home' / 'away'
    game_type = db.Column(db.String(2), nullable=True)   # 'R' / 'S' / 'P' / ...

    # ── Status ─────────────────────────────────────────────────────────────────
    status_code = db.Column(db.String(10), nullable=True)   # raw MLB statusCode
    status_state = db.Column(db.String(20), nullable=False,  # normalized
                             default=STATE_OTHER)

    # ── Doubleheader / series ──────────────────────────────────────────────────
    doubleheader = db.Column(db.String(2), nullable=True)   # raw MLB 'N'/'Y'/'S'
    game_number = db.Column(db.Integer, nullable=True)
    series_game_number = db.Column(db.Integer, nullable=True)
    games_in_series = db.Column(db.Integer, nullable=True)

    # ── Provenance ─────────────────────────────────────────────────────────────
    source = db.Column(db.String(40), nullable=False, default='schedule_ingestion')
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now_naive, onupdate=utc_now_naive
    )

    # Columns the ingestion service is allowed to overwrite on re-ingest. Identity
    # columns (team_id, game_pk) and created_at are never rewritten.
    MUTABLE_COLUMNS = (
        'game_date',
        'game_datetime',
        'opponent_team_id',
        'home_away',
        'game_type',
        'status_code',
        'status_state',
        'doubleheader',
        'game_number',
        'series_game_number',
        'games_in_series',
        'source',
    )

    def to_dict(self):
        return {
            'id': self.id,
            'team_id': self.team_id,
            'game_pk': self.game_pk,
            'game_date': self.game_date.isoformat() if self.game_date else None,
            'game_datetime': self.game_datetime.isoformat() if self.game_datetime else None,
            'opponent_team_id': self.opponent_team_id,
            'home_away': self.home_away,
            'game_type': self.game_type,
            'status_code': self.status_code,
            'status_state': self.status_state,
            'doubleheader': self.doubleheader,
            'game_number': self.game_number,
            'series_game_number': self.series_game_number,
            'games_in_series': self.games_in_series,
            'source': self.source,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return (
            f'<ScheduledGame team_id={self.team_id} game_pk={self.game_pk} '
            f'date={self.game_date} state={self.status_state}>'
        )
