from utils.db import db
from datetime import datetime

class GameLog(db.Model):
    __tablename__ = 'game_logs'

    id = db.Column(db.Integer, primary_key=True)
    pitcher_id = db.Column(db.Integer, db.ForeignKey('pitchers.id'), nullable=False)
    mlb_game_pk = db.Column(db.Integer, nullable=False)
    game_date = db.Column(db.Date, nullable=False)
    opponent = db.Column(db.String(50))
    opponent_abbreviation = db.Column(db.String(10))

    # Pitching stats for this appearance
    innings_pitched = db.Column(db.Float, default=0.0)
    pitches_thrown = db.Column(db.Integer, default=0)
    strikes = db.Column(db.Integer, default=0)
    hits_allowed = db.Column(db.Integer, default=0)
    runs_allowed = db.Column(db.Integer, default=0)
    earned_runs = db.Column(db.Integer, default=0)
    walks = db.Column(db.Integer, default=0)
    strikeouts = db.Column(db.Integer, default=0)
    home_runs_allowed = db.Column(db.Integer, default=0)

    # Context
    leverage_index = db.Column(db.Float)  # High leverage = higher fatigue weight
    inherited_runners = db.Column(db.Integer, default=0)
    inherited_runners_scored = db.Column(db.Integer, default=0)
    save_situation = db.Column(db.Boolean, default=False)
    hold = db.Column(db.Boolean, default=False)
    blown_save = db.Column(db.Boolean, default=False)
    win = db.Column(db.Boolean, default=False)
    loss = db.Column(db.Boolean, default=False)
    save = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'pitcher_id': self.pitcher_id,
            'mlb_game_pk': self.mlb_game_pk,
            'game_date': str(self.game_date),
            'opponent': self.opponent,
            'opponent_abbreviation': self.opponent_abbreviation,
            'innings_pitched': self.innings_pitched,
            'pitches_thrown': self.pitches_thrown,
            'strikes': self.strikes,
            'hits_allowed': self.hits_allowed,
            'runs_allowed': self.runs_allowed,
            'earned_runs': self.earned_runs,
            'walks': self.walks,
            'strikeouts': self.strikeouts,
            'home_runs_allowed': self.home_runs_allowed,
            'leverage_index': self.leverage_index,
            'save_situation': self.save_situation,
            'hold': self.hold,
            'blown_save': self.blown_save,
            'win': self.win,
            'loss': self.loss,
            'save': self.save,
        }

    def __repr__(self):
        return f'<GameLog pitcher_id={self.pitcher_id} date={self.game_date}>'
