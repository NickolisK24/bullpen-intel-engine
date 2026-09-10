from sqlalchemy import text

from utils.db import db
from utils.time import utc_now_naive


class ProvisionalPitchingAppearanceState(db.Model):
    """Current provisional live-feed view of one pitcher's game appearance."""

    __tablename__ = 'provisional_pitching_appearance_states'
    __table_args__ = (
        db.UniqueConstraint('game_pk', 'pitcher_id', name='uq_live_appearance_game_pitcher'),
        db.CheckConstraint("authority_state = 'live'", name='ck_live_appearance_authority'),
        db.CheckConstraint("appearance_role IN ('starter', 'reliever')", name='ck_live_appearance_role'),
        db.CheckConstraint("outing_status IN ('active', 'closed', 'unknown')", name='ck_live_appearance_outing'),
        db.CheckConstraint('outs_recorded >= 0', name='ck_live_appearance_outs'),
        db.Index('ix_live_appearance_game_order', 'game_pk', 'team_id_at_appearance', 'appearance_order'),
        db.Index('ix_live_appearance_team_date', 'team_id_at_appearance', 'baseball_date'),
        db.Index('ix_live_appearance_source_observation', 'latest_observation_id'),
        db.Index(
            'ix_live_appearance_active_game', 'game_pk', 'team_id_at_appearance',
            postgresql_where=text("outing_status = 'active' AND is_current"),
            sqlite_where=text("outing_status = 'active' AND is_current = 1"),
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    game_pk = db.Column(db.Integer, nullable=False)
    baseball_date = db.Column(db.Date, nullable=False)
    pitcher_id = db.Column(db.Integer, db.ForeignKey('pitchers.id'), nullable=False)
    pitcher_mlb_id = db.Column(db.Integer, nullable=False)
    team_id_at_appearance = db.Column(db.Integer, nullable=False)
    opponent_team_id = db.Column(db.Integer)
    side = db.Column(db.String(10), nullable=False)
    appearance_role = db.Column(db.String(10), nullable=False)
    appearance_order = db.Column(db.Integer)
    outing_status = db.Column(db.String(10), nullable=False)
    pitches_thrown = db.Column(db.Integer)
    strikes = db.Column(db.Integer)
    balls = db.Column(db.Integer)
    outs_recorded = db.Column(db.Integer, nullable=False, default=0)
    batters_faced = db.Column(db.Integer)
    hits_allowed = db.Column(db.Integer)
    runs_allowed = db.Column(db.Integer)
    earned_runs = db.Column(db.Integer)
    walks = db.Column(db.Integer)
    strikeouts = db.Column(db.Integer)
    home_runs_allowed = db.Column(db.Integer)
    current_inning = db.Column(db.Integer)
    current_half = db.Column(db.String(10))
    entry_inning = db.Column(db.Integer)
    entry_half = db.Column(db.String(10))
    entry_outs = db.Column(db.Integer)
    entry_home_score = db.Column(db.Integer)
    entry_away_score = db.Column(db.Integer)
    entry_base_state = db.Column(db.JSON)
    inherited_runners = db.Column(db.Integer)
    first_observation_id = db.Column(db.Integer, db.ForeignKey('source_observations.id', ondelete='RESTRICT'), nullable=False)
    latest_observation_id = db.Column(db.Integer, db.ForeignKey('source_observations.id', ondelete='RESTRICT'), nullable=False)
    latest_source_observed_at = db.Column(db.DateTime)
    fact_fingerprint = db.Column(db.String(64), nullable=False)
    fingerprint_version = db.Column(db.String(40), nullable=False)
    completeness = db.Column(db.String(32), nullable=False)
    authority_state = db.Column(db.String(12), nullable=False, default='live')
    is_current = db.Column(db.Boolean, nullable=False, default=True)
    superseded_by_final_game_version_id = db.Column(db.Integer, db.ForeignKey('final_game_versions.id', ondelete='SET NULL'))
    superseded_at = db.Column(db.DateTime)
    first_seen_at = db.Column(db.DateTime, nullable=False)
    latest_seen_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive, onupdate=utc_now_naive)


class LiveGameMutation(db.Model):
    """Append-only meaningful provisional delta for SP-09 handoff."""

    __tablename__ = 'live_game_mutations'
    __table_args__ = (
        db.UniqueConstraint('mutation_key', name='uq_live_game_mutations_key'),
        db.CheckConstraint("authority_state = 'live'", name='ck_live_mutation_authority'),
        db.Index('ix_live_mutations_game_date', 'game_pk', 'baseball_date'),
        db.Index('ix_live_mutations_team_date', 'team_id', 'baseball_date'),
        db.Index('ix_live_mutations_pitcher_date', 'pitcher_id', 'baseball_date'),
        db.Index('ix_live_mutations_source_observation', 'source_observation_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    mutation_key = db.Column(db.String(160), nullable=False)
    mutation_type = db.Column(db.String(50), nullable=False)
    game_pk = db.Column(db.Integer, nullable=False)
    baseball_date = db.Column(db.Date, nullable=False)
    team_id = db.Column(db.Integer)
    pitcher_id = db.Column(db.Integer, db.ForeignKey('pitchers.id'))
    pitcher_mlb_id = db.Column(db.Integer)
    source_observation_id = db.Column(db.Integer, db.ForeignKey('source_observations.id', ondelete='RESTRICT'), nullable=False)
    sync_run_id = db.Column(db.Integer, db.ForeignKey('sync_runs.id', ondelete='SET NULL'))
    old_fingerprint = db.Column(db.String(64))
    new_fingerprint = db.Column(db.String(64))
    old_state_json = db.Column(db.JSON)
    new_state_json = db.Column(db.JSON)
    authority_state = db.Column(db.String(12), nullable=False, default='live')
    is_correction = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
