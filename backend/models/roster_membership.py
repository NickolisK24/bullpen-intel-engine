from utils.db import db
from utils.time import utc_now_naive


class RosterMembershipInterval(db.Model):
    """Version-aware authoritative roster membership at player/team/type grain."""

    __tablename__ = 'roster_membership_intervals'
    __table_args__ = (
        db.CheckConstraint(
            "membership_type IN ('active_roster', 'forty_man_roster', "
            "'organization', 'minor_assignment', 'public_inactive', "
            "'rehab_assignment')",
            name='ck_roster_membership_intervals_type',
        ),
        db.CheckConstraint(
            "start_precision IN ('date', 'timestamp') AND "
            "(end_precision IS NULL OR end_precision IN ('date', 'timestamp'))",
            name='ck_roster_membership_intervals_precision',
        ),
        db.CheckConstraint(
            'effective_end_date IS NULL OR effective_end_date >= effective_start_date',
            name='ck_roster_membership_intervals_date_order',
        ),
        db.Index(
            'uq_roster_membership_intervals_current_open_player_type',
            'pitcher_id',
            'membership_type',
            unique=True,
            postgresql_where=db.text(
                'effective_end_date IS NULL AND is_current_version = true'
            ),
            sqlite_where=db.text(
                'effective_end_date IS NULL AND is_current_version = 1'
            ),
        ),
        db.Index(
            'ix_roster_membership_intervals_team_type_open',
            'team_id', 'membership_type', 'effective_end_date',
        ),
        db.Index(
            'ix_roster_membership_intervals_pitcher_dates',
            'pitcher_id', 'effective_start_date', 'effective_end_date',
        ),
        db.Index(
            'ix_roster_membership_intervals_opened_observation',
            'opened_by_observation_id',
        ),
        db.Index(
            'ix_roster_membership_intervals_closed_observation',
            'closed_by_observation_id',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    pitcher_id = db.Column(db.Integer, db.ForeignKey('pitchers.id'), nullable=False)
    player_mlb_id = db.Column(db.Integer, nullable=False)
    team_id = db.Column(db.Integer, nullable=False)
    organization_id = db.Column(db.Integer)
    membership_type = db.Column(db.String(30), nullable=False)
    effective_start_date = db.Column(db.Date, nullable=False)
    effective_start_at = db.Column(db.DateTime)
    effective_end_date = db.Column(db.Date)
    effective_end_at = db.Column(db.DateTime)
    start_precision = db.Column(db.String(20), nullable=False, default='date')
    end_precision = db.Column(db.String(20))
    authority_type = db.Column(db.String(60), nullable=False)
    opened_by_observation_id = db.Column(
        db.Integer,
        db.ForeignKey('source_observations.id', ondelete='RESTRICT'),
        nullable=False,
    )
    closed_by_observation_id = db.Column(
        db.Integer,
        db.ForeignKey('source_observations.id', ondelete='RESTRICT'),
    )
    opened_by_transaction_id = db.Column(
        db.Integer,
        db.ForeignKey('player_transactions.id', ondelete='SET NULL'),
    )
    closed_by_transaction_id = db.Column(
        db.Integer,
        db.ForeignKey('player_transactions.id', ondelete='SET NULL'),
    )
    is_current_version = db.Column(db.Boolean, nullable=False, default=True)
    supersedes_interval_id = db.Column(
        db.Integer,
        db.ForeignKey('roster_membership_intervals.id', ondelete='RESTRICT'),
    )
    correction_reason = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now_naive,
        onupdate=utc_now_naive,
    )

    pitcher = db.relationship('Pitcher')
    opened_by_observation = db.relationship(
        'SourceObservation', foreign_keys=[opened_by_observation_id]
    )
    closed_by_observation = db.relationship(
        'SourceObservation', foreign_keys=[closed_by_observation_id]
    )
    supersedes = db.relationship(
        'RosterMembershipInterval', remote_side=[id], foreign_keys=[supersedes_interval_id]
    )


class RosterMembershipMutation(db.Model):
    """Append-only change fact for later SP-09 impact processing."""

    __tablename__ = 'roster_membership_mutations'
    __table_args__ = (
        db.CheckConstraint(
            "mutation_type IN ('membership_opened', 'membership_closed', "
            "'membership_corrected')",
            name='ck_roster_membership_mutations_type',
        ),
        db.Index('ix_roster_membership_mutations_team_date', 'team_id', 'baseball_date'),
        db.Index('ix_roster_membership_mutations_pitcher_date', 'pitcher_id', 'baseball_date'),
        db.Index('ix_roster_membership_mutations_observation', 'source_observation_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    interval_id = db.Column(
        db.Integer,
        db.ForeignKey('roster_membership_intervals.id', ondelete='RESTRICT'),
        nullable=False,
    )
    pitcher_id = db.Column(db.Integer, db.ForeignKey('pitchers.id'), nullable=False)
    player_mlb_id = db.Column(db.Integer, nullable=False)
    team_id = db.Column(db.Integer, nullable=False)
    membership_type = db.Column(db.String(30), nullable=False)
    mutation_type = db.Column(db.String(30), nullable=False)
    baseball_date = db.Column(db.Date, nullable=False)
    effective_at = db.Column(db.DateTime)
    precision = db.Column(db.String(20), nullable=False, default='date')
    source_observation_id = db.Column(
        db.Integer,
        db.ForeignKey('source_observations.id', ondelete='RESTRICT'),
        nullable=True,
    )
    player_transaction_id = db.Column(
        db.Integer,
        db.ForeignKey('player_transactions.id', ondelete='SET NULL'),
    )
    sync_run_id = db.Column(db.Integer, db.ForeignKey('sync_runs.id', ondelete='SET NULL'))
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    interval = db.relationship('RosterMembershipInterval')


class PlayerTransactionVersion(db.Model):
    """Append-only canonical transaction facts before any later correction."""

    __tablename__ = 'player_transaction_versions'
    __table_args__ = (
        db.UniqueConstraint(
            'player_transaction_id', 'version_number',
            name='uq_player_transaction_versions_transaction_version',
        ),
        db.UniqueConstraint(
            'player_transaction_id', 'fact_fingerprint',
            name='uq_player_transaction_versions_transaction_fingerprint',
        ),
        db.Index('ix_player_transaction_versions_observation', 'source_observation_id'),
        db.CheckConstraint('version_number > 0', name='ck_player_transaction_versions_number'),
    )

    id = db.Column(db.Integer, primary_key=True)
    player_transaction_id = db.Column(
        db.Integer,
        db.ForeignKey('player_transactions.id', ondelete='RESTRICT'),
        nullable=False,
    )
    version_number = db.Column(db.Integer, nullable=False)
    predecessor_version_id = db.Column(
        db.Integer,
        db.ForeignKey('player_transaction_versions.id', ondelete='RESTRICT'),
    )
    source_observation_id = db.Column(
        db.Integer,
        db.ForeignKey('source_observations.id', ondelete='RESTRICT'),
        nullable=False,
    )
    fact_fingerprint = db.Column(db.String(64), nullable=False)
    fact_schema_version = db.Column(db.Integer, nullable=False, default=1)
    fact_json = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    transaction = db.relationship('PlayerTransaction')
    predecessor = db.relationship(
        'PlayerTransactionVersion', remote_side=[id], foreign_keys=[predecessor_version_id]
    )
