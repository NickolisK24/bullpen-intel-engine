from utils.db import db
from datetime import datetime

class Pitcher(db.Model):
    __tablename__ = 'pitchers'

    id = db.Column(db.Integer, primary_key=True)
    mlb_id = db.Column(db.Integer, unique=True, nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    team_id = db.Column(db.Integer, nullable=False)
    team_name = db.Column(db.String(100))
    team_abbreviation = db.Column(db.String(10))
    position = db.Column(db.String(10), default='P')
    throws = db.Column(db.String(1))  # R or L
    age = db.Column(db.Integer)
    jersey_number = db.Column(db.String(5))
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    game_logs = db.relationship('GameLog', backref='pitcher', lazy=True, cascade='all, delete-orphan')
    fatigue_scores = db.relationship('FatigueScore', backref='pitcher', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        return {
            'id': self.id,
            'mlb_id': self.mlb_id,
            'full_name': self.full_name,
            'team_id': self.team_id,
            'team_name': self.team_name,
            'team_abbreviation': self.team_abbreviation,
            'position': self.position,
            'throws': self.throws,
            'age': self.age,
            'jersey_number': self.jersey_number,
            'active': self.active,
        }

    def __repr__(self):
        return f'<Pitcher {self.full_name} ({self.team_abbreviation})>'
