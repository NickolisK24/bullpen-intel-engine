from sqlalchemy import text

from utils.db import db
from utils.time import utc_now_naive


class FinalGameVersion(db.Model):
    """Append-only canonical final-game reconciliation generation."""

    __tablename__ = 'final_game_versions'
    __table_args__ = (
        db.UniqueConstraint(
            'game_pk', 'version_number', name='uq_final_game_versions_game_version',
        ),
        db.CheckConstraint('version_number > 0', name='ck_final_game_versions_number'),
        db.CheckConstraint(
            "core_completeness = 'complete'",
            name='ck_final_game_versions_core_complete',
        ),
        db.CheckConstraint(
            "pbp_completeness IN ('complete', 'partial', 'unknown', 'failed')",
            name='ck_final_game_versions_pbp_completeness',
        ),
        db.Index('ix_final_game_versions_game_created', 'game_pk', 'created_at'),
        db.Index('ix_final_game_versions_date_game', 'baseball_date', 'game_pk'),
        db.Index('ix_final_game_versions_boxscore_observation', 'boxscore_observation_id'),
        db.Index('ix_final_game_versions_pbp_observation', 'play_by_play_observation_id'),
        db.Index(
            'uq_final_game_versions_current_game',
            'game_pk',
            unique=True,
            postgresql_where=text('is_current'),
            sqlite_where=text('is_current = 1'),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    game_pk = db.Column(db.Integer, nullable=False)
    version_number = db.Column(db.Integer, nullable=False)
    predecessor_version_id = db.Column(
        db.Integer,
        db.ForeignKey('final_game_versions.id', ondelete='RESTRICT'),
    )
    baseball_date = db.Column(db.Date, nullable=False)
    game_type = db.Column(db.String(2))
    home_team_id = db.Column(db.Integer, nullable=False)
    away_team_id = db.Column(db.Integer, nullable=False)
    home_score = db.Column(db.Integer)
    away_score = db.Column(db.Integer)
    innings_played = db.Column(db.Integer)
    extra_innings = db.Column(db.Boolean)
    game_number = db.Column(db.Integer)
    doubleheader = db.Column(db.String(2))
    fact_fingerprint = db.Column(db.String(64), nullable=False)
    fingerprint_version = db.Column(db.String(40), nullable=False)
    core_completeness = db.Column(db.String(20), nullable=False)
    pbp_completeness = db.Column(db.String(20), nullable=False)
    finality_observation_id = db.Column(
        db.Integer,
        db.ForeignKey('source_observations.id', ondelete='RESTRICT'),
        nullable=False,
    )
    boxscore_observation_id = db.Column(
        db.Integer,
        db.ForeignKey('source_observations.id', ondelete='RESTRICT'),
        nullable=False,
    )
    play_by_play_observation_id = db.Column(
        db.Integer,
        db.ForeignKey('source_observations.id', ondelete='RESTRICT'),
    )
    sync_run_id = db.Column(
        db.Integer, db.ForeignKey('sync_runs.id', ondelete='SET NULL'),
    )
    is_current = db.Column(db.Boolean, nullable=False, default=True)
    superseded_at = db.Column(db.DateTime)
    observed_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    predecessor = db.relationship(
        'FinalGameVersion', remote_side=[id], foreign_keys=[predecessor_version_id],
    )


class FinalPitchingAppearanceVersion(db.Model):
    """Immutable official pitching line and optional final-PBP context."""

    __tablename__ = 'final_pitching_appearance_versions'
    __table_args__ = (
        db.UniqueConstraint(
            'game_pk', 'pitcher_id', 'version_number',
            name='uq_final_appearance_versions_game_pitcher_version',
        ),
        db.CheckConstraint('version_number > 0', name='ck_final_appearance_versions_number'),
        db.CheckConstraint(
            "appearance_role IN ('starter', 'reliever')",
            name='ck_final_appearance_versions_role',
        ),
        db.CheckConstraint('outs_recorded >= 0', name='ck_final_appearance_versions_outs'),
        db.Index(
            'ix_final_appearance_versions_pitcher_date', 'pitcher_id', 'baseball_date',
        ),
        db.Index(
            'ix_final_appearance_versions_team_date', 'team_id_at_appearance', 'baseball_date',
        ),
        db.Index('ix_final_appearance_versions_game_order', 'game_pk', 'team_id_at_appearance', 'appearance_order'),
        db.Index('ix_final_appearance_versions_boxscore_observation', 'boxscore_observation_id'),
        db.Index('ix_final_appearance_versions_pbp_observation', 'play_by_play_observation_id'),
        db.Index(
            'uq_final_appearance_versions_current',
            'game_pk', 'pitcher_id',
            unique=True,
            postgresql_where=text('is_current'),
            sqlite_where=text('is_current = 1'),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    final_game_version_id = db.Column(
        db.Integer,
        db.ForeignKey('final_game_versions.id', ondelete='RESTRICT'),
        nullable=False,
    )
    game_log_id = db.Column(
        db.Integer, db.ForeignKey('game_logs.id', ondelete='SET NULL'), nullable=True,
    )
    game_pk = db.Column(db.Integer, nullable=False)
    baseball_date = db.Column(db.Date, nullable=False)
    pitcher_id = db.Column(db.Integer, db.ForeignKey('pitchers.id'), nullable=False)
    pitcher_mlb_id = db.Column(db.Integer, nullable=False)
    team_id_at_appearance = db.Column(db.Integer, nullable=False)
    opponent_team_id = db.Column(db.Integer)
    side = db.Column(db.String(10), nullable=False)
    appearance_role = db.Column(db.String(10), nullable=False)
    appearance_order = db.Column(db.Integer)
    version_number = db.Column(db.Integer, nullable=False)
    predecessor_version_id = db.Column(
        db.Integer,
        db.ForeignKey('final_pitching_appearance_versions.id', ondelete='RESTRICT'),
    )

    outs_recorded = db.Column(db.Integer, nullable=False)
    pitches_thrown = db.Column(db.Integer)
    strikes = db.Column(db.Integer)
    balls = db.Column(db.Integer)
    batters_faced = db.Column(db.Integer)
    hits_allowed = db.Column(db.Integer)
    runs_allowed = db.Column(db.Integer)
    earned_runs = db.Column(db.Integer)
    walks = db.Column(db.Integer)
    strikeouts = db.Column(db.Integer)
    home_runs_allowed = db.Column(db.Integer)
    hit_batters = db.Column(db.Integer)
    wild_pitches = db.Column(db.Integer)
    balks = db.Column(db.Integer)
    games_finished = db.Column(db.Integer)
    inherited_runners = db.Column(db.Integer)
    inherited_runners_scored = db.Column(db.Integer)
    save_situation = db.Column(db.Boolean)
    hold = db.Column(db.Boolean)
    blown_save = db.Column(db.Boolean)
    win = db.Column(db.Boolean)
    loss = db.Column(db.Boolean)
    save = db.Column(db.Boolean)

    entry_inning = db.Column(db.Integer)
    entry_half = db.Column(db.String(10))
    entry_outs = db.Column(db.Integer)
    entry_home_score = db.Column(db.Integer)
    entry_away_score = db.Column(db.Integer)
    entry_base_state = db.Column(db.JSON)
    inherited_runners_context = db.Column(db.Integer)
    exit_inning = db.Column(db.Integer)
    exit_half = db.Column(db.String(10))
    exit_outs = db.Column(db.Integer)
    exit_home_score = db.Column(db.Integer)
    exit_away_score = db.Column(db.Integer)
    context_completeness = db.Column(db.String(20), nullable=False)

    fact_fingerprint = db.Column(db.String(64), nullable=False)
    fingerprint_version = db.Column(db.String(40), nullable=False)
    boxscore_observation_id = db.Column(
        db.Integer,
        db.ForeignKey('source_observations.id', ondelete='RESTRICT'),
        nullable=False,
    )
    play_by_play_observation_id = db.Column(
        db.Integer,
        db.ForeignKey('source_observations.id', ondelete='RESTRICT'),
    )
    sync_run_id = db.Column(
        db.Integer, db.ForeignKey('sync_runs.id', ondelete='SET NULL'),
    )
    is_current = db.Column(db.Boolean, nullable=False, default=True)
    superseded_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    predecessor = db.relationship(
        'FinalPitchingAppearanceVersion',
        remote_side=[id],
        foreign_keys=[predecessor_version_id],
    )


class FinalGameMutation(db.Model):
    """Structured canonical final mutation retained for SP-09 impact mapping."""

    __tablename__ = 'final_game_mutations'
    __table_args__ = (
        db.UniqueConstraint('mutation_key', name='uq_final_game_mutations_key'),
        db.CheckConstraint(
            "mutation_type IN ('final_game_ingested', 'starter_appearance_added', "
            "'reliever_appearance_added', 'pitching_line_corrected', "
            "'appearance_context_corrected', 'final_play_by_play_corrected', "
            "'final_game_context_corrected')",
            name='ck_final_game_mutations_type',
        ),
        db.Index('ix_final_game_mutations_game_date', 'game_pk', 'baseball_date'),
        db.Index('ix_final_game_mutations_team_date', 'team_id', 'baseball_date'),
        db.Index('ix_final_game_mutations_pitcher_date', 'pitcher_id', 'baseball_date'),
        db.Index('ix_final_game_mutations_sync_run', 'sync_run_id', 'id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    mutation_key = db.Column(db.String(120), nullable=False)
    mutation_type = db.Column(db.String(50), nullable=False)
    final_game_version_id = db.Column(
        db.Integer,
        db.ForeignKey('final_game_versions.id', ondelete='RESTRICT'),
        nullable=False,
    )
    old_appearance_version_id = db.Column(
        db.Integer,
        db.ForeignKey('final_pitching_appearance_versions.id', ondelete='RESTRICT'),
    )
    new_appearance_version_id = db.Column(
        db.Integer,
        db.ForeignKey('final_pitching_appearance_versions.id', ondelete='RESTRICT'),
    )
    game_pk = db.Column(db.Integer, nullable=False)
    baseball_date = db.Column(db.Date, nullable=False)
    team_id = db.Column(db.Integer)
    pitcher_id = db.Column(db.Integer, db.ForeignKey('pitchers.id'))
    pitcher_mlb_id = db.Column(db.Integer)
    source_observation_id = db.Column(
        db.Integer,
        db.ForeignKey('source_observations.id', ondelete='RESTRICT'),
        nullable=False,
    )
    sync_run_id = db.Column(
        db.Integer, db.ForeignKey('sync_runs.id', ondelete='SET NULL'),
    )
    details_json = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
