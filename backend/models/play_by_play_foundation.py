from utils.db import db
from utils.time import utc_now_naive


class GamePlayByPlayEvent(db.Model):
    __tablename__ = 'game_play_by_play_events'
    __correction_policy_name__ = 'game_play_by_play_event_corrections'
    __correction_identity_fields__ = ('mlb_game_pk', 'event_index')
    __correction_sensitive_fields__ = (
        'mlb_game_pk',
        'event_index',
        'source_play_id',
        'at_bat_index',
        'game_date',
        'game_type',
        'home_team_id',
        'away_team_id',
        'event_type',
        'event_type_code',
        'inning',
        'half_inning',
        'is_top_inning',
        'outs_at_event',
        'home_score_at_event',
        'away_score_at_event',
        'pitcher_mlb_id',
        'pitcher_id',
        'batter_mlb_id',
        'batting_team_id',
        'fielding_team_id',
        'is_pitching_change',
        'is_scoring_play',
        'is_mound_visit',
        'source',
        'source_endpoint',
    )

    __table_args__ = (
        db.UniqueConstraint(
            'mlb_game_pk',
            'event_index',
            name='uq_game_play_by_play_events_game_event',
        ),
        db.Index('ix_game_play_by_play_events_game_order', 'mlb_game_pk', 'event_index'),
        db.Index('ix_game_play_by_play_events_game_date', 'game_date'),
        db.Index('ix_game_play_by_play_events_pitcher', 'pitcher_mlb_id'),
        db.CheckConstraint(
            "half_inning IS NULL OR half_inning IN ('top', 'bottom')",
            name='ck_game_play_by_play_events_half_inning',
        ),
        db.CheckConstraint(
            "event_type IN ("
            "'plate_appearance', 'pitching_change', 'scoring_play', "
            "'mound_visit', 'unknown')",
            name='ck_game_play_by_play_events_event_type',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    mlb_game_pk = db.Column(db.Integer, nullable=False)
    event_index = db.Column(db.Integer, nullable=False)
    source_play_id = db.Column(db.String(80))
    at_bat_index = db.Column(db.Integer)
    game_date = db.Column(db.Date, nullable=False)
    game_type = db.Column(db.String(2))
    home_team_id = db.Column(db.Integer, nullable=False)
    away_team_id = db.Column(db.Integer, nullable=False)
    event_type = db.Column(db.String(30), nullable=False, default='unknown')
    event_type_code = db.Column(db.String(40))
    inning = db.Column(db.Integer)
    half_inning = db.Column(db.String(10))
    is_top_inning = db.Column(db.Boolean)
    outs_at_event = db.Column(db.Integer)
    home_score_at_event = db.Column(db.Integer)
    away_score_at_event = db.Column(db.Integer)
    pitcher_mlb_id = db.Column(db.Integer)
    pitcher_id = db.Column(db.Integer, db.ForeignKey('pitchers.id'), nullable=True)
    batter_mlb_id = db.Column(db.Integer)
    batting_team_id = db.Column(db.Integer)
    fielding_team_id = db.Column(db.Integer)
    is_pitching_change = db.Column(db.Boolean, nullable=False, default=False)
    is_scoring_play = db.Column(db.Boolean, nullable=False, default=False)
    is_mound_visit = db.Column(db.Boolean, nullable=False, default=False)

    source = db.Column(db.String(100), nullable=False)
    source_endpoint = db.Column(db.String(100), nullable=False)
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
            'mlb_game_pk': self.mlb_game_pk,
            'event_index': self.event_index,
            'source_play_id': self.source_play_id,
            'at_bat_index': self.at_bat_index,
            'game_date': _iso(self.game_date),
            'game_type': self.game_type,
            'home_team_id': self.home_team_id,
            'away_team_id': self.away_team_id,
            'event_type': self.event_type,
            'event_type_code': self.event_type_code,
            'inning': self.inning,
            'half_inning': self.half_inning,
            'is_top_inning': self.is_top_inning,
            'outs_at_event': self.outs_at_event,
            'home_score_at_event': self.home_score_at_event,
            'away_score_at_event': self.away_score_at_event,
            'pitcher_mlb_id': self.pitcher_mlb_id,
            'pitcher_id': self.pitcher_id,
            'batter_mlb_id': self.batter_mlb_id,
            'batting_team_id': self.batting_team_id,
            'fielding_team_id': self.fielding_team_id,
            'is_pitching_change': bool(self.is_pitching_change),
            'is_scoring_play': bool(self.is_scoring_play),
            'is_mound_visit': bool(self.is_mound_visit),
            'source': self.source,
            'source_endpoint': self.source_endpoint,
            'sync_run_id': self.sync_run_id,
            'first_seen_at': _iso(self.first_seen_at),
            'last_corrected_at': _iso(self.last_corrected_at),
            'correction_count': self.correction_count or 0,
            'correction_source': self.correction_source,
            'created_at': _iso(self.created_at),
            'updated_at': _iso(self.updated_at),
        }


class PlayByPlayProcessedGame(db.Model):
    __tablename__ = 'play_by_play_processed_games'
    __correction_policy_name__ = 'play_by_play_processed_game_corrections'
    __correction_identity_fields__ = ('mlb_game_pk',)
    __correction_sensitive_fields__ = (
        'mlb_game_pk',
        'game_date',
        'game_type',
        'home_team_id',
        'away_team_id',
        'final_state',
        'processing_status',
        'attempt_count',
        'incomplete_reason',
        'events_seen',
        'events_stored',
        'pitcher_events_seen',
        'unresolved_pitcher_count',
        'reconciliation_mismatch_count',
        'event_fingerprint',
        'source',
        'source_endpoint',
    )

    STATUS_FULLY_PROCESSED = 'fully_processed'
    STATUS_INCOMPLETE = 'incomplete'
    STATUS_FAILED = 'failed'
    STATUS_ABSENT = 'absent'
    STATUS_AMBIGUOUS = 'ambiguous'

    __table_args__ = (
        db.UniqueConstraint(
            'mlb_game_pk',
            name='uq_play_by_play_processed_games_game_pk',
        ),
        db.Index('ix_play_by_play_processed_games_game_date', 'game_date'),
        db.Index('ix_play_by_play_processed_games_status', 'processing_status'),
        db.Index('ix_play_by_play_processed_games_attempted', 'last_attempted_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    mlb_game_pk = db.Column(db.Integer, nullable=False)
    game_date = db.Column(db.Date, nullable=False)
    game_type = db.Column(db.String(2))
    home_team_id = db.Column(db.Integer)
    away_team_id = db.Column(db.Integer)
    final_state = db.Column(db.String(80))
    processing_status = db.Column(db.String(32), nullable=False)
    attempt_count = db.Column(db.Integer, nullable=False, default=0)
    last_attempted_at = db.Column(db.DateTime)
    incomplete_reason = db.Column(db.String(120))
    events_seen = db.Column(db.Integer, nullable=False, default=0)
    events_stored = db.Column(db.Integer, nullable=False, default=0)
    pitcher_events_seen = db.Column(db.Integer, nullable=False, default=0)
    unresolved_pitcher_count = db.Column(db.Integer, nullable=False, default=0)
    reconciliation_mismatch_count = db.Column(db.Integer, nullable=False, default=0)
    event_fingerprint = db.Column(db.String(64))
    source = db.Column(db.String(100), nullable=False)
    source_endpoint = db.Column(db.String(100), nullable=False)
    sync_run_id = db.Column(db.Integer, db.ForeignKey('sync_runs.id'), nullable=True)
    first_seen_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    last_corrected_at = db.Column(db.DateTime)
    correction_count = db.Column(db.Integer, nullable=False, default=0)
    correction_source = db.Column(db.String(100))
    processed_at = db.Column(db.DateTime)
    failed_at = db.Column(db.DateTime)
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
            'mlb_game_pk': self.mlb_game_pk,
            'game_date': _iso(self.game_date),
            'game_type': self.game_type,
            'home_team_id': self.home_team_id,
            'away_team_id': self.away_team_id,
            'final_state': self.final_state,
            'processing_status': self.processing_status,
            'attempt_count': self.attempt_count or 0,
            'last_attempted_at': _iso(self.last_attempted_at),
            'incomplete_reason': self.incomplete_reason,
            'events_seen': self.events_seen or 0,
            'events_stored': self.events_stored or 0,
            'pitcher_events_seen': self.pitcher_events_seen or 0,
            'unresolved_pitcher_count': self.unresolved_pitcher_count or 0,
            'reconciliation_mismatch_count': self.reconciliation_mismatch_count or 0,
            'event_fingerprint': self.event_fingerprint,
            'source': self.source,
            'source_endpoint': self.source_endpoint,
            'sync_run_id': self.sync_run_id,
            'first_seen_at': _iso(self.first_seen_at),
            'last_corrected_at': _iso(self.last_corrected_at),
            'correction_count': self.correction_count or 0,
            'correction_source': self.correction_source,
            'processed_at': _iso(self.processed_at),
            'failed_at': _iso(self.failed_at),
            'created_at': _iso(self.created_at),
            'updated_at': _iso(self.updated_at),
        }


def _iso(value):
    return value.isoformat() if value is not None else None
