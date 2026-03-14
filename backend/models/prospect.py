from utils.db import db
from datetime import datetime

class Prospect(db.Model):
    __tablename__ = 'prospects'

    id = db.Column(db.Integer, primary_key=True)
    mlb_id = db.Column(db.Integer, unique=True)
    full_name = db.Column(db.String(100), nullable=False)
    team_id = db.Column(db.Integer)
    team_name = db.Column(db.String(100))
    team_abbreviation = db.Column(db.String(10))

    # Identity
    position = db.Column(db.String(10))
    bats = db.Column(db.String(1))
    throws = db.Column(db.String(1))
    age = db.Column(db.Integer)
    birth_date = db.Column(db.Date)
    nationality = db.Column(db.String(50))

    # Development level
    current_level = db.Column(db.String(10))  # ROK, A, A+, AA, AAA, MLB
    eta_year = db.Column(db.Integer)           # Projected MLB ETA

    # Scouting grades (20-80 scale)
    hit_grade = db.Column(db.Integer)
    power_grade = db.Column(db.Integer)
    speed_grade = db.Column(db.Integer)
    field_grade = db.Column(db.Integer)
    arm_grade = db.Column(db.Integer)
    overall_grade = db.Column(db.Integer)

    # Current season stats (updated periodically)
    games_played = db.Column(db.Integer, default=0)
    at_bats = db.Column(db.Integer, default=0)
    batting_average = db.Column(db.Float)
    on_base_pct = db.Column(db.Float)
    slugging_pct = db.Column(db.Float)
    ops = db.Column(db.Float)
    home_runs = db.Column(db.Integer, default=0)
    rbi = db.Column(db.Integer, default=0)
    stolen_bases = db.Column(db.Integer, default=0)
    strikeout_rate = db.Column(db.Float)
    walk_rate = db.Column(db.Float)

    # For pitching prospects
    era = db.Column(db.Float)
    whip = db.Column(db.Float)
    innings_pitched = db.Column(db.Float)
    k_per_9 = db.Column(db.Float)
    bb_per_9 = db.Column(db.Float)
    fip = db.Column(db.Float)

    # Meta
    notes = db.Column(db.Text)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'mlb_id': self.mlb_id,
            'full_name': self.full_name,
            'team_name': self.team_name,
            'team_abbreviation': self.team_abbreviation,
            'position': self.position,
            'bats': self.bats,
            'throws': self.throws,
            'age': self.age,
            'current_level': self.current_level,
            'eta_year': self.eta_year,
            'grades': {
                'hit': self.hit_grade,
                'power': self.power_grade,
                'speed': self.speed_grade,
                'field': self.field_grade,
                'arm': self.arm_grade,
                'overall': self.overall_grade,
            },
            'stats': {
                'games_played': self.games_played,
                'batting_average': self.batting_average,
                'on_base_pct': self.on_base_pct,
                'slugging_pct': self.slugging_pct,
                'ops': self.ops,
                'home_runs': self.home_runs,
                'rbi': self.rbi,
                'stolen_bases': self.stolen_bases,
                'strikeout_rate': self.strikeout_rate,
                'walk_rate': self.walk_rate,
                'era': self.era,
                'whip': self.whip,
                'k_per_9': self.k_per_9,
                'bb_per_9': self.bb_per_9,
            },
            'notes': self.notes,
            'active': self.active,
        }

    def __repr__(self):
        return f'<Prospect {self.full_name} ({self.team_abbreviation}) - {self.current_level}>'
