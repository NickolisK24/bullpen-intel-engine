from utils.db import db
from utils.time import utc_now_naive


class RosterStatusSnapshot(db.Model):
    __tablename__ = 'roster_status_snapshots'
    __correction_policy_name__ = 'roster_status_snapshot_corrections'
    __correction_identity_fields__ = (
        'pitcher_id',
        'mlb_id',
        'team_id',
        'snapshot_date',
    )
    __correction_sensitive_fields__ = (
        'pitcher_id',
        'mlb_id',
        'team_id',
        'snapshot_date',
        'roster_status',
        'active_roster',
        'forty_man_roster',
        'position_code',
        'position_name',
        'position_type',
        'two_way_eligible',
        'roster_status_raw',
        'roster_status_raw_code',
        'roster_status_raw_description',
        'source',
    )

    __table_args__ = (
        db.UniqueConstraint(
            'pitcher_id',
            'snapshot_date',
            name='uq_roster_status_snapshots_pitcher_date',
        ),
        db.Index('ix_roster_status_snapshots_team_date', 'team_id', 'snapshot_date'),
        db.Index('ix_roster_status_snapshots_mlb_date', 'mlb_id', 'snapshot_date'),
    )

    id = db.Column(db.Integer, primary_key=True)
    pitcher_id = db.Column(db.Integer, db.ForeignKey('pitchers.id'), nullable=False)
    mlb_id = db.Column(db.Integer, nullable=False)
    team_id = db.Column(db.Integer, nullable=False)
    snapshot_date = db.Column(db.Date, nullable=False)

    roster_status = db.Column(db.String(30), nullable=False)
    active_roster = db.Column(db.Boolean, nullable=True)
    forty_man_roster = db.Column(db.Boolean, nullable=True)
    position_code = db.Column(db.String(10))
    position_name = db.Column(db.String(50))
    position_type = db.Column(db.String(30))
    two_way_eligible = db.Column(db.Boolean, nullable=True)
    roster_status_raw = db.Column(db.String(100))
    roster_status_raw_code = db.Column(db.String(30))
    roster_status_raw_description = db.Column(db.String(100))

    source = db.Column(db.String(100), nullable=False)
    sync_run_id = db.Column(db.Integer, db.ForeignKey('sync_runs.id'), nullable=True)
    first_seen_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    last_corrected_at = db.Column(db.DateTime)
    correction_count = db.Column(db.Integer, nullable=False, default=0)
    correction_source = db.Column(db.String(100))
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
            'mlb_id': self.mlb_id,
            'team_id': self.team_id,
            'snapshot_date': self.snapshot_date.isoformat() if self.snapshot_date else None,
            'roster_status': self.roster_status,
            'active_roster': self.active_roster,
            'forty_man_roster': self.forty_man_roster,
            'position_code': self.position_code,
            'position_name': self.position_name,
            'position_type': self.position_type,
            'two_way_eligible': self.two_way_eligible,
            'roster_status_raw': self.roster_status_raw,
            'roster_status_raw_code': self.roster_status_raw_code,
            'roster_status_raw_description': self.roster_status_raw_description,
            'source': self.source,
            'sync_run_id': self.sync_run_id,
            'first_seen_at': self.first_seen_at.isoformat() if self.first_seen_at else None,
            'last_corrected_at': (
                self.last_corrected_at.isoformat() if self.last_corrected_at else None
            ),
            'correction_count': self.correction_count or 0,
            'correction_source': self.correction_source,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
