from utils.db import db
from utils.time import utc_now_naive


class PitcherSeasonLedgerCoverage(db.Model):
    __tablename__ = 'pitcher_season_ledger_coverage'

    STATUS_COMPLETE = 'complete'
    STATUS_INCOMPLETE = 'incomplete'
    STATUS_UNKNOWN = 'unknown'

    __table_args__ = (
        db.UniqueConstraint(
            'pitcher_id',
            'season',
            'game_type',
            'target_game_pk',
            name='uq_pitcher_season_ledger_coverage_target',
        ),
        db.CheckConstraint(
            "coverage_status IN ('complete', 'incomplete', 'unknown')",
            name='ck_pitcher_season_ledger_coverage_status',
        ),
        db.Index(
            'ix_pitcher_season_ledger_coverage_lookup',
            'pitcher_id',
            'season',
            'game_type',
            'target_game_pk',
        ),
        db.Index(
            'ix_pitcher_season_ledger_coverage_status',
            'coverage_status',
            'covered_through_date',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    pitcher_id = db.Column(db.Integer, db.ForeignKey('pitchers.id'), nullable=False)
    pitcher_mlb_id = db.Column(db.Integer, nullable=False)
    season = db.Column(db.Integer, nullable=False)
    game_type = db.Column(db.String(2), nullable=False, default='R')
    target_game_pk = db.Column(db.Integer, nullable=False)
    covered_through_date = db.Column(db.Date, nullable=False)

    source_appearance_count = db.Column(db.Integer, nullable=False, default=0)
    source_games_started_count = db.Column(db.Integer, nullable=False, default=0)
    stored_appearance_count = db.Column(db.Integer, nullable=False, default=0)
    stored_games_started_count = db.Column(db.Integer, nullable=False, default=0)
    source_manifest_fingerprint = db.Column(db.String(64), nullable=False)
    stored_manifest_fingerprint = db.Column(db.String(64), nullable=False)
    coverage_status = db.Column(db.String(20), nullable=False, default=STATUS_UNKNOWN)
    reason_codes = db.Column(db.JSON, nullable=False, default=list)

    verified_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    sync_run_id = db.Column(db.Integer, db.ForeignKey('sync_runs.id'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now_naive,
        onupdate=utc_now_naive,
    )

    def to_dict(self):
        return {
            'id': self.id,
            'pitcher_id': self.pitcher_id,
            'pitcher_mlb_id': self.pitcher_mlb_id,
            'season': self.season,
            'game_type': self.game_type,
            'target_game_pk': self.target_game_pk,
            'covered_through_date': (
                self.covered_through_date.isoformat()
                if self.covered_through_date else None
            ),
            'source_appearance_count': self.source_appearance_count or 0,
            'source_games_started_count': self.source_games_started_count or 0,
            'stored_appearance_count': self.stored_appearance_count or 0,
            'stored_games_started_count': self.stored_games_started_count or 0,
            'source_manifest_fingerprint': self.source_manifest_fingerprint,
            'stored_manifest_fingerprint': self.stored_manifest_fingerprint,
            'coverage_status': self.coverage_status,
            'reason_codes': list(self.reason_codes or []),
            'verified_at': self.verified_at.isoformat() if self.verified_at else None,
            'sync_run_id': self.sync_run_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
