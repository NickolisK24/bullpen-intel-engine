from utils.db import db
from utils.time import utc_now_naive


class TeamGamePitchingSplit(db.Model):
    __tablename__ = 'team_game_pitching_splits'
    __correction_policy_name__ = 'team_game_pitching_split_corrections'
    __correction_identity_fields__ = ('team_id', 'mlb_game_pk')
    __correction_sensitive_fields__ = (
        'team_id',
        'mlb_game_pk',
        'game_date',
        'game_type',
        'opponent_team_id',
        'home_away',
        'starter_pitcher_id',
        'starter_mlb_id',
        'starter_identity_status',
        'starter_outs_recorded',
        'starter_pitches_thrown',
        'starter_batters_faced',
        'starter_balls',
        'starter_games_started',
        'bullpen_outs_recorded',
        'bullpen_pitches_thrown',
        'bullpen_batters_faced',
        'bullpen_balls',
        'relievers_used_count',
        'total_team_outs',
        'total_team_pitches',
        'total_team_batters_faced',
        'total_team_balls',
        'split_completeness_status',
        'split_reason_codes',
        'off_day_before',
        'off_day_after',
        'consecutive_game_day_count_entering',
        'series_game_number',
        'games_in_series',
        'doubleheader_flag',
        'doubleheader_code',
        'game_number',
        'postponed_or_makeup_indicator',
        'suspended_resumed_linkage_status',
        'extra_inning_indicator',
        'calendar_context_status',
        'calendar_reason_codes',
        'source',
    )

    STATUS_COMPLETE = 'complete'
    STATUS_PARTIAL = 'partial'
    STATUS_UNKNOWN = 'unknown'

    STARTER_KNOWN = 'known'
    STARTER_UNKNOWN = 'unknown'
    STARTER_AMBIGUOUS = 'ambiguous'

    LINKAGE_NONE = 'none'
    LINKAGE_RESOLVED = 'resolved'
    LINKAGE_AMBIGUOUS = 'ambiguous'

    __table_args__ = (
        db.UniqueConstraint(
            'team_id',
            'mlb_game_pk',
            name='uq_team_game_pitching_splits_team_game',
        ),
        db.Index('ix_team_game_pitching_splits_team_date', 'team_id', 'game_date'),
        db.Index('ix_team_game_pitching_splits_game_pk', 'mlb_game_pk'),
        db.Index('ix_team_game_pitching_splits_split_status', 'split_completeness_status'),
        db.Index('ix_team_game_pitching_splits_calendar_status', 'calendar_context_status'),
        db.CheckConstraint(
            "starter_identity_status IN ('known', 'unknown', 'ambiguous')",
            name='ck_team_game_pitching_splits_starter_status',
        ),
        db.CheckConstraint(
            "split_completeness_status IN ('complete', 'partial', 'unknown')",
            name='ck_team_game_pitching_splits_split_status',
        ),
        db.CheckConstraint(
            "calendar_context_status IN ('complete', 'partial', 'unknown')",
            name='ck_team_game_pitching_splits_calendar_status',
        ),
        db.CheckConstraint(
            "suspended_resumed_linkage_status IN ('none', 'resolved', 'ambiguous')",
            name='ck_team_game_pitching_splits_linkage_status',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, nullable=False)
    mlb_game_pk = db.Column(db.Integer, nullable=False)
    game_date = db.Column(db.Date, nullable=False)
    game_type = db.Column(db.String(2))
    opponent_team_id = db.Column(db.Integer)
    home_away = db.Column(db.String(10))

    starter_pitcher_id = db.Column(db.Integer, db.ForeignKey('pitchers.id'), nullable=True)
    starter_mlb_id = db.Column(db.Integer)
    starter_identity_status = db.Column(db.String(20), nullable=False)
    starter_outs_recorded = db.Column(db.Integer)
    starter_pitches_thrown = db.Column(db.Integer)
    starter_batters_faced = db.Column(db.Integer)
    starter_balls = db.Column(db.Integer)
    starter_games_started = db.Column(db.Integer)

    bullpen_outs_recorded = db.Column(db.Integer)
    bullpen_pitches_thrown = db.Column(db.Integer)
    bullpen_batters_faced = db.Column(db.Integer)
    bullpen_balls = db.Column(db.Integer)
    relievers_used_count = db.Column(db.Integer)

    total_team_outs = db.Column(db.Integer)
    total_team_pitches = db.Column(db.Integer)
    total_team_batters_faced = db.Column(db.Integer)
    total_team_balls = db.Column(db.Integer)
    split_completeness_status = db.Column(db.String(20), nullable=False)
    split_reason_codes = db.Column(db.JSON)

    off_day_before = db.Column(db.Boolean)
    off_day_after = db.Column(db.Boolean)
    consecutive_game_day_count_entering = db.Column(db.Integer)
    series_game_number = db.Column(db.Integer)
    games_in_series = db.Column(db.Integer)
    doubleheader_flag = db.Column(db.Boolean)
    doubleheader_code = db.Column(db.String(2))
    game_number = db.Column(db.Integer)
    postponed_or_makeup_indicator = db.Column(db.Boolean)
    suspended_resumed_linkage_status = db.Column(db.String(20), nullable=False)
    extra_inning_indicator = db.Column(db.Boolean)
    calendar_context_status = db.Column(db.String(20), nullable=False)
    calendar_reason_codes = db.Column(db.JSON)

    source = db.Column(db.String(100), nullable=False)
    sync_run_id = db.Column(db.Integer, db.ForeignKey('sync_runs.id'), nullable=True)
    first_seen_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    last_corrected_at = db.Column(db.DateTime)
    correction_count = db.Column(db.Integer, nullable=False, default=0)
    correction_source = db.Column(db.String(100))
    last_derived_at = db.Column(db.DateTime)
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
            'team_id': self.team_id,
            'mlb_game_pk': self.mlb_game_pk,
            'game_date': _iso(self.game_date),
            'game_type': self.game_type,
            'opponent_team_id': self.opponent_team_id,
            'home_away': self.home_away,
            'starter_pitcher_id': self.starter_pitcher_id,
            'starter_mlb_id': self.starter_mlb_id,
            'starter_identity_status': self.starter_identity_status,
            'starter_outs_recorded': self.starter_outs_recorded,
            'starter_pitches_thrown': self.starter_pitches_thrown,
            'starter_batters_faced': self.starter_batters_faced,
            'starter_balls': self.starter_balls,
            'starter_games_started': self.starter_games_started,
            'bullpen_outs_recorded': self.bullpen_outs_recorded,
            'bullpen_pitches_thrown': self.bullpen_pitches_thrown,
            'bullpen_batters_faced': self.bullpen_batters_faced,
            'bullpen_balls': self.bullpen_balls,
            'relievers_used_count': self.relievers_used_count,
            'total_team_outs': self.total_team_outs,
            'total_team_pitches': self.total_team_pitches,
            'total_team_batters_faced': self.total_team_batters_faced,
            'total_team_balls': self.total_team_balls,
            'split_completeness_status': self.split_completeness_status,
            'split_reason_codes': list(self.split_reason_codes or []),
            'off_day_before': self.off_day_before,
            'off_day_after': self.off_day_after,
            'consecutive_game_day_count_entering': self.consecutive_game_day_count_entering,
            'series_game_number': self.series_game_number,
            'games_in_series': self.games_in_series,
            'doubleheader_flag': self.doubleheader_flag,
            'doubleheader_code': self.doubleheader_code,
            'game_number': self.game_number,
            'postponed_or_makeup_indicator': self.postponed_or_makeup_indicator,
            'suspended_resumed_linkage_status': self.suspended_resumed_linkage_status,
            'extra_inning_indicator': self.extra_inning_indicator,
            'calendar_context_status': self.calendar_context_status,
            'calendar_reason_codes': list(self.calendar_reason_codes or []),
            'source': self.source,
            'sync_run_id': self.sync_run_id,
            'first_seen_at': _iso(self.first_seen_at),
            'last_corrected_at': _iso(self.last_corrected_at),
            'correction_count': self.correction_count or 0,
            'correction_source': self.correction_source,
            'last_derived_at': _iso(self.last_derived_at),
            'created_at': _iso(self.created_at),
            'updated_at': _iso(self.updated_at),
        }


def _iso(value):
    return value.isoformat() if value is not None else None
