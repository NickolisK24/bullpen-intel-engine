from utils.db import db
from datetime import datetime

class FatigueScore(db.Model):
    __tablename__ = 'fatigue_scores'

    # ── Index for fast latest-score lookups ───────────────────────────────────
    __table_args__ = (
        db.Index('ix_fatigue_pitcher_calc', 'pitcher_id', 'calculated_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    pitcher_id = db.Column(db.Integer, db.ForeignKey('pitchers.id'), nullable=False)
    calculated_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Score components (each 0-100)
    raw_score = db.Column(db.Float, nullable=False)
    pitch_count_score = db.Column(db.Float)
    rest_days_score = db.Column(db.Float)
    appearances_score = db.Column(db.Float)
    leverage_score = db.Column(db.Float)
    innings_score = db.Column(db.Float)

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