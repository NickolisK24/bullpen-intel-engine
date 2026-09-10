from utils.db import db
from utils.time import utc_now_naive


class GamePregameContextVersion(db.Model):
    """Append-only official pregame context for one MLB game revision."""

    __tablename__ = 'game_pregame_context_versions'
    __table_args__ = (
        db.UniqueConstraint(
            'game_pk', 'version_number',
            name='uq_game_pregame_context_versions_game_version',
        ),
        db.UniqueConstraint(
            'game_pk', 'source_observation_id', 'fingerprint_version',
            name='uq_game_pregame_context_versions_game_observation',
        ),
        db.CheckConstraint(
            'version_number > 0', name='ck_game_pregame_context_versions_number',
        ),
        db.CheckConstraint(
            "completeness = 'complete'",
            name='ck_game_pregame_context_versions_complete',
        ),
        db.Index(
            'ix_game_pregame_context_versions_game_created',
            'game_pk', 'created_at',
        ),
        db.Index(
            'ix_game_pregame_context_versions_observation',
            'source_observation_id',
        ),
        db.Index(
            'ix_game_pregame_context_versions_baseball_date',
            'baseball_date', 'game_pk',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    game_pk = db.Column(db.Integer, nullable=False)
    version_number = db.Column(db.Integer, nullable=False)
    predecessor_version_id = db.Column(
        db.Integer,
        db.ForeignKey('game_pregame_context_versions.id', ondelete='RESTRICT'),
    )
    baseball_date = db.Column(db.Date, nullable=False)
    scheduled_at = db.Column(db.DateTime)
    home_team_id = db.Column(db.Integer, nullable=False)
    away_team_id = db.Column(db.Integer, nullable=False)
    home_probable_pitcher_mlb_id = db.Column(db.Integer)
    away_probable_pitcher_mlb_id = db.Column(db.Integer)
    home_probable_pitcher_id = db.Column(db.Integer, db.ForeignKey('pitchers.id'))
    away_probable_pitcher_id = db.Column(db.Integer, db.ForeignKey('pitchers.id'))
    home_probable_pitcher_name = db.Column(db.String(100))
    away_probable_pitcher_name = db.Column(db.String(100))
    venue_id = db.Column(db.Integer)
    venue_name = db.Column(db.String(120))
    game_type = db.Column(db.String(2))
    game_number = db.Column(db.Integer)
    doubleheader = db.Column(db.String(2))
    resumed_from_game_pk = db.Column(db.Integer)
    context_fingerprint = db.Column(db.String(64), nullable=False)
    fingerprint_version = db.Column(db.String(40), nullable=False)
    source_observation_id = db.Column(
        db.Integer,
        db.ForeignKey('source_observations.id', ondelete='RESTRICT'),
        nullable=False,
    )
    completeness = db.Column(db.String(20), nullable=False)
    observed_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    predecessor = db.relationship(
        'GamePregameContextVersion',
        remote_side=[id],
        foreign_keys=[predecessor_version_id],
    )
    source_observation = db.relationship('SourceObservation')
    home_probable_pitcher = db.relationship('Pitcher', foreign_keys=[home_probable_pitcher_id])
    away_probable_pitcher = db.relationship('Pitcher', foreign_keys=[away_probable_pitcher_id])


class PregameContextMutation(db.Model):
    """Structured pregame change fact retained for SP-09 impact planning."""

    __tablename__ = 'pregame_context_mutations'
    __table_args__ = (
        db.UniqueConstraint(
            'context_version_id', 'mutation_type', 'side',
            name='uq_pregame_context_mutations_version_type_side',
        ),
        db.CheckConstraint(
            "mutation_type IN ('pregame_context_discovered', "
            "'probable_starter_added', 'probable_starter_changed', "
            "'probable_starter_removed', 'pregame_context_changed')",
            name='ck_pregame_context_mutations_type',
        ),
        db.CheckConstraint(
            "side IN ('game', 'home', 'away')",
            name='ck_pregame_context_mutations_side',
        ),
        db.Index(
            'ix_pregame_context_mutations_game_date',
            'game_pk', 'baseball_date',
        ),
        db.Index(
            'ix_pregame_context_mutations_team_date',
            'team_id', 'baseball_date',
        ),
        db.Index(
            'ix_pregame_context_mutations_observation',
            'source_observation_id',
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    context_version_id = db.Column(
        db.Integer,
        db.ForeignKey('game_pregame_context_versions.id', ondelete='RESTRICT'),
        nullable=False,
    )
    game_pk = db.Column(db.Integer, nullable=False)
    baseball_date = db.Column(db.Date, nullable=False)
    team_id = db.Column(db.Integer)
    side = db.Column(db.String(10), nullable=False)
    mutation_type = db.Column(db.String(40), nullable=False)
    old_probable_pitcher_mlb_id = db.Column(db.Integer)
    new_probable_pitcher_mlb_id = db.Column(db.Integer)
    source_observation_id = db.Column(
        db.Integer,
        db.ForeignKey('source_observations.id', ondelete='RESTRICT'),
        nullable=False,
    )
    sync_run_id = db.Column(
        db.Integer,
        db.ForeignKey('sync_runs.id', ondelete='SET NULL'),
    )
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

    context_version = db.relationship('GamePregameContextVersion')
