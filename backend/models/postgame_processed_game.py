from utils.db import db
from utils.time import utc_now_naive


class PostgameProcessedGame(db.Model):
    __tablename__ = 'postgame_processed_games'

    __table_args__ = (
        db.UniqueConstraint('mlb_game_pk', name='uq_postgame_processed_games_game_pk'),
        db.Index('ix_postgame_processed_games_game_date', 'game_date'),
        db.Index('ix_postgame_processed_games_processed_at', 'processed_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    mlb_game_pk = db.Column(db.Integer, nullable=False)
    game_date = db.Column(db.Date, nullable=False)
    game_type = db.Column(db.String(2), nullable=True)
    home_team_id = db.Column(db.Integer, nullable=True)
    away_team_id = db.Column(db.Integer, nullable=True)
    final_state = db.Column(db.String(80), nullable=True)
    logs_added = db.Column(db.Integer, nullable=False, default=0)
    pitchers_touched = db.Column(db.Integer, nullable=False, default=0)
    sync_run_id = db.Column(db.Integer, db.ForeignKey('sync_runs.id'), nullable=True)
    processed_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    def to_dict(self):
        return {
            'id': self.id,
            'mlb_game_pk': self.mlb_game_pk,
            'game_date': self.game_date.isoformat() if self.game_date else None,
            'game_type': self.game_type,
            'home_team_id': self.home_team_id,
            'away_team_id': self.away_team_id,
            'final_state': self.final_state,
            'logs_added': self.logs_added or 0,
            'pitchers_touched': self.pitchers_touched or 0,
            'sync_run_id': self.sync_run_id,
            'processed_at': self.processed_at.isoformat() if self.processed_at else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
