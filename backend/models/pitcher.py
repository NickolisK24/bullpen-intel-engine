from utils.db import db
from utils.time import utc_now_naive

class Pitcher(db.Model):
    __tablename__ = 'pitchers'
    __table_args__ = (
        db.Index('ix_pitchers_team_active', 'team_id', 'active'),
    )

    id = db.Column(db.Integer, primary_key=True)
    mlb_id = db.Column(db.Integer, unique=True, nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    team_id = db.Column(db.Integer, nullable=True)
    team_name = db.Column(db.String(100))
    team_abbreviation = db.Column(db.String(10))
    team_assignment_status = db.Column(db.String(30))
    team_assignment_source = db.Column(db.String(100))
    team_assignment_updated_at = db.Column(db.DateTime)
    position = db.Column(db.String(10), default='P')
    throws = db.Column(db.String(1))  # R or L
    age = db.Column(db.Integer)
    jersey_number = db.Column(db.String(5))
    active = db.Column(db.Boolean, default=True)
    roster_status = db.Column(db.String(30))
    roster_status_source = db.Column(db.String(100))
    roster_status_raw_code = db.Column(db.String(30))
    roster_status_raw_description = db.Column(db.String(100))
    roster_status_updated_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=utc_now_naive)
    updated_at = db.Column(db.DateTime, default=utc_now_naive, onupdate=utc_now_naive)

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
            'team_assignment_status': self.team_assignment_status,
            'team_assignment_source': self.team_assignment_source,
            'team_assignment_updated_at': (
                self.team_assignment_updated_at.isoformat()
                if self.team_assignment_updated_at else None
            ),
            'position': self.position,
            'throws': self.throws,
            'age': self.age,
            'jersey_number': self.jersey_number,
            'active': self.active,
            'roster_status': self.roster_status,
            'roster_status_source': self.roster_status_source,
            'roster_status_raw_code': self.roster_status_raw_code,
            'roster_status_raw_description': self.roster_status_raw_description,
            'roster_status_updated_at': (
                self.roster_status_updated_at.isoformat()
                if self.roster_status_updated_at else None
            ),
        }

    def __repr__(self):
        return f'<Pitcher {self.full_name} ({self.team_abbreviation})>'
