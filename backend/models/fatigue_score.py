from utils.db import db
from datetime import datetime

class FatigueScore(db.Model):
    __tablename__ = 'fatigue_scores'

    id = db.Column(db.Integer, primary_key=True)
    pitcher_id = db.Column(db.Integer, db.ForeignKey('pitchers.id'), nullable=False)
    calculated_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Score components (each 0-100)
    raw_score = db.Column(db.Float, nullable=False)         # Final weighted score
    pitch_count_score = db.Column(db.Float)                  # Based on pitches last 7 days
    rest_days_score = db.Column(db.Float)                    # Days since last appearance
    appearances_score = db.Column(db.Float)                  # Appearances in last 7/14 days
    leverage_score = db.Column(db.Float)                     # High-leverage workload
    innings_score = db.Column(db.Float)                      # Innings in rolling window

    # Supporting data used in calculation
    days_since_last_appearance = db.Column(db.Integer)
    appearances_last_7 = db.Column(db.Integer, default=0)
    appearances_last_14 = db.Column(db.Integer, default=0)
    pitches_last_7_days = db.Column(db.Integer, default=0)
    innings_last_7_days = db.Column(db.Float, default=0.0)
    avg_leverage_last_7 = db.Column(db.Float)

    # Risk tier
    risk_level = db.Column(db.String(10))  # 'LOW', 'MODERATE', 'HIGH', 'CRITICAL'

    def to_dict(self):
        return {
            'id': self.id,
            'pitcher_id': self.pitcher_id,
            'calculated_at': self.calculated_at.isoformat(),
            'raw_score': round(self.raw_score, 1),
            'pitch_count_score': round(self.pitch_count_score or 0, 1),
            'rest_days_score': round(self.rest_days_score or 0, 1),
            'appearances_score': round(self.appearances_score or 0, 1),
            'leverage_score': round(self.leverage_score or 0, 1),
            'innings_score': round(self.innings_score or 0, 1),
            'days_since_last_appearance': self.days_since_last_appearance,
            'appearances_last_7': self.appearances_last_7,
            'appearances_last_14': self.appearances_last_14,
            'pitches_last_7_days': self.pitches_last_7_days,
            'innings_last_7_days': self.innings_last_7_days,
            'avg_leverage_last_7': self.avg_leverage_last_7,
            'risk_level': self.risk_level,
        }

    def __repr__(self):
        return f'<FatigueScore pitcher_id={self.pitcher_id} score={self.raw_score} risk={self.risk_level}>'
