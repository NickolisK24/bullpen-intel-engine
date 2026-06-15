from utils.db import db
from utils.time import utc_now_naive


class AvailabilityBacktestResult(db.Model):
    __tablename__ = 'availability_backtest_results'

    __table_args__ = (
        db.Index(
            'ix_availability_backtest_method_computed',
            'method_version',
            'computed_at',
        ),
        db.Index(
            'ix_availability_backtest_season_tier',
            'season',
            'tier',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    method_version = db.Column(db.String(80), nullable=False)
    cadence = db.Column(db.String(80), nullable=False)
    computed_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    data_through = db.Column(db.Date, nullable=True)
    season = db.Column(db.Integer, nullable=False)
    window_label = db.Column(db.String(50), nullable=False)
    window_start = db.Column(db.Date, nullable=True)
    window_end = db.Column(db.Date, nullable=True)
    tier = db.Column(db.String(20), nullable=False)
    tier_order = db.Column(db.Integer, nullable=False)
    sample_size = db.Column(db.Integer, nullable=False, default=0)
    next_day_appearances = db.Column(db.Integer, nullable=False, default=0)
    next_day_rate = db.Column(db.Float, nullable=False, default=0.0)
    no_appearance_days = db.Column(db.Integer, nullable=False, default=0)
    no_appearance_tier_flips = db.Column(db.Integer, nullable=False, default=0)
    no_appearance_tier_flip_rate = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    def to_dict(self):
        return {
            'id': self.id,
            'method_version': self.method_version,
            'cadence': self.cadence,
            'computed_at': self.computed_at.isoformat() if self.computed_at else None,
            'data_through': self.data_through.isoformat() if self.data_through else None,
            'season': self.season,
            'window_label': self.window_label,
            'window_start': self.window_start.isoformat() if self.window_start else None,
            'window_end': self.window_end.isoformat() if self.window_end else None,
            'tier': self.tier,
            'tier_order': self.tier_order,
            'sample_size': self.sample_size,
            'next_day_appearances': self.next_day_appearances,
            'next_day_rate': self.next_day_rate,
            'no_appearance_days': self.no_appearance_days,
            'no_appearance_tier_flips': self.no_appearance_tier_flips,
            'no_appearance_tier_flip_rate': self.no_appearance_tier_flip_rate,
            'created_at': self.created_at.isoformat() if self.created_at else None,
        }
