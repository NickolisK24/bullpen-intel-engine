from utils.db import db
from utils.time import utc_now_naive


class PlayerTransaction(db.Model):
    __tablename__ = 'player_transactions'
    __correction_policy_name__ = 'player_transaction_corrections'
    __correction_identity_fields__ = ('transaction_key',)
    __correction_sensitive_fields__ = (
        'transaction_key',
        'transaction_id',
        'pitcher_id',
        'player_mlb_id',
        'from_team_id',
        'to_team_id',
        'transaction_date',
        'effective_date',
        'resolution_date',
        'transaction_type_code',
        'normalized_category',
        'is_il_placement',
        'is_il_activation',
        'il_list_type',
        'retroactive_date',
        'roster_snapshot_alignment',
        'alignment_reason_code',
        'explanatory_linkage_eligible',
        'source',
        'source_endpoint',
        'source_query_start_date',
        'source_query_end_date',
    )

    __table_args__ = (
        db.UniqueConstraint(
            'transaction_key',
            name='uq_player_transactions_transaction_key',
        ),
        db.Index('ix_player_transactions_player_date', 'player_mlb_id', 'transaction_date'),
        db.Index('ix_player_transactions_pitcher_date', 'pitcher_id', 'transaction_date'),
        db.Index('ix_player_transactions_to_team_date', 'to_team_id', 'transaction_date'),
        db.CheckConstraint(
            "normalized_category IN ("
            "'recall', 'option', 'il_placement', 'il_activation', "
            "'roster_activation', 'roster_deactivation', 'trade', 'dfa', "
            "'outright', 'release', 'contract_selection', 'suspension', "
            "'bereavement', 'paternity', 'restricted', 'unknown')",
            name='ck_player_transactions_normalized_category',
        ),
        db.CheckConstraint(
            "roster_snapshot_alignment IN ("
            "'aligned', 'misaligned', 'unknown', 'no_snapshot', 'not_applicable')",
            name='ck_player_transactions_roster_alignment',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    transaction_key = db.Column(db.String(160), nullable=False)
    transaction_id = db.Column(db.String(80))
    pitcher_id = db.Column(db.Integer, db.ForeignKey('pitchers.id'), nullable=True)
    player_mlb_id = db.Column(db.Integer, nullable=False)
    from_team_id = db.Column(db.Integer)
    to_team_id = db.Column(db.Integer)
    transaction_date = db.Column(db.Date, nullable=False)
    effective_date = db.Column(db.Date)
    resolution_date = db.Column(db.Date)
    transaction_type_code = db.Column(db.String(40))
    normalized_category = db.Column(db.String(40), nullable=False, default='unknown')
    is_il_placement = db.Column(db.Boolean, nullable=False, default=False)
    is_il_activation = db.Column(db.Boolean, nullable=False, default=False)
    il_list_type = db.Column(db.String(20))
    retroactive_date = db.Column(db.Date)
    roster_snapshot_alignment = db.Column(db.String(30), nullable=False, default='unknown')
    alignment_reason_code = db.Column(db.String(60))
    explanatory_linkage_eligible = db.Column(db.Boolean, nullable=False, default=False)

    source = db.Column(db.String(100), nullable=False)
    source_endpoint = db.Column(db.String(100), nullable=False)
    source_query_start_date = db.Column(db.Date, nullable=False)
    source_query_end_date = db.Column(db.Date, nullable=False)
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
            'transaction_key': self.transaction_key,
            'transaction_id': self.transaction_id,
            'pitcher_id': self.pitcher_id,
            'player_mlb_id': self.player_mlb_id,
            'from_team_id': self.from_team_id,
            'to_team_id': self.to_team_id,
            'transaction_date': _iso(self.transaction_date),
            'effective_date': _iso(self.effective_date),
            'resolution_date': _iso(self.resolution_date),
            'transaction_type_code': self.transaction_type_code,
            'normalized_category': self.normalized_category,
            'is_il_placement': bool(self.is_il_placement),
            'is_il_activation': bool(self.is_il_activation),
            'il_list_type': self.il_list_type,
            'retroactive_date': _iso(self.retroactive_date),
            'roster_snapshot_alignment': self.roster_snapshot_alignment,
            'alignment_reason_code': self.alignment_reason_code,
            'explanatory_linkage_eligible': bool(self.explanatory_linkage_eligible),
            'source': self.source,
            'source_endpoint': self.source_endpoint,
            'source_query_start_date': _iso(self.source_query_start_date),
            'source_query_end_date': _iso(self.source_query_end_date),
            'sync_run_id': self.sync_run_id,
            'first_seen_at': _iso(self.first_seen_at),
            'last_corrected_at': _iso(self.last_corrected_at),
            'correction_count': self.correction_count or 0,
            'correction_source': self.correction_source,
            'created_at': _iso(self.created_at),
            'updated_at': _iso(self.updated_at),
        }


class PlayerTransactionSyncWindow(db.Model):
    __tablename__ = 'player_transaction_sync_windows'

    __table_args__ = (
        db.Index(
            'ix_player_transaction_sync_windows_query_end',
            'source_query_end_date',
            'attempted_at',
        ),
        db.Index(
            'ix_player_transaction_sync_windows_status',
            'status',
            'attempted_at',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(100), nullable=False)
    source_endpoint = db.Column(db.String(100), nullable=False)
    source_query_start_date = db.Column(db.Date, nullable=False)
    source_query_end_date = db.Column(db.Date, nullable=False)
    attempted_at = db.Column(db.DateTime, nullable=False)
    successful_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), nullable=False)
    records_fetched = db.Column(db.Integer, nullable=False, default=0)
    records_stored = db.Column(db.Integer, nullable=False, default=0)
    records_created = db.Column(db.Integer, nullable=False, default=0)
    records_corrected = db.Column(db.Integer, nullable=False, default=0)
    records_unchanged = db.Column(db.Integer, nullable=False, default=0)
    unknown_type_count = db.Column(db.Integer, nullable=False, default=0)
    alignment_unknown_count = db.Column(db.Integer, nullable=False, default=0)
    alignment_misaligned_count = db.Column(db.Integer, nullable=False, default=0)
    alignment_no_snapshot_count = db.Column(db.Integer, nullable=False, default=0)
    records_failed = db.Column(db.Integer, nullable=False, default=0)
    sync_run_id = db.Column(db.Integer, db.ForeignKey('sync_runs.id'), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    def to_dict(self):
        return {
            'id': self.id,
            'source': self.source,
            'source_endpoint': self.source_endpoint,
            'source_query_start_date': _iso(self.source_query_start_date),
            'source_query_end_date': _iso(self.source_query_end_date),
            'attempted_at': _iso(self.attempted_at),
            'successful_at': _iso(self.successful_at),
            'status': self.status,
            'records_fetched': self.records_fetched or 0,
            'records_stored': self.records_stored or 0,
            'records_created': self.records_created or 0,
            'records_corrected': self.records_corrected or 0,
            'records_unchanged': self.records_unchanged or 0,
            'unknown_type_count': self.unknown_type_count or 0,
            'alignment_unknown_count': self.alignment_unknown_count or 0,
            'alignment_misaligned_count': self.alignment_misaligned_count or 0,
            'alignment_no_snapshot_count': self.alignment_no_snapshot_count or 0,
            'records_failed': self.records_failed or 0,
            'sync_run_id': self.sync_run_id,
            'created_at': _iso(self.created_at),
        }


def _iso(value):
    return value.isoformat() if value is not None else None
