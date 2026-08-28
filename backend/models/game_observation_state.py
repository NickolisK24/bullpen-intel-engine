from utils.db import db
from utils.time import utc_now_naive


class GameObservationState(db.Model):
    """Latest accepted, canonicalized MLB live-feed observation for one game."""

    __tablename__ = 'game_observation_states'

    __table_args__ = (
        db.UniqueConstraint('mlb_game_pk', name='uq_game_observation_states_game_pk'),
        db.Index('ix_game_observation_states_finality', 'finality_state'),
        db.Index('ix_game_observation_states_source_observed', 'source_observed_at'),
    )

    id = db.Column(db.Integer, primary_key=True)
    mlb_game_pk = db.Column(db.Integer, nullable=False)
    observation_fingerprint = db.Column(db.String(64), nullable=False)
    observation = db.Column(db.JSON, nullable=False)
    source_authority = db.Column(db.String(100), nullable=False)
    source_endpoint = db.Column(db.String(120), nullable=False)
    # Upstream MLB feed revision evidence. Never populated from local fetch time.
    source_observed_at = db.Column(db.DateTime, nullable=True)
    finality_state = db.Column(db.String(40), nullable=False)
    previous_observation_fingerprint = db.Column(db.String(64), nullable=True)
    last_classification = db.Column(db.String(40), nullable=False)
    last_change_summary = db.Column(db.JSON, nullable=True)
    accepted_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    updated_at = db.Column(
        db.DateTime, nullable=False, default=utc_now_naive, onupdate=utc_now_naive,
    )
