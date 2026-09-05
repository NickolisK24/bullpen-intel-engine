"""Dormant D-058 per-team public publication storage.

Package 1 stores immutable team publication packages and one backend-owned current
pointer per team.  No public reader consumes either table yet.
"""

from sqlalchemy import event

from utils.db import db
from utils.time import utc_now_naive


class TeamPublicPublication(db.Model):
    __tablename__ = 'team_public_publications'

    SOURCE_LEAGUE_DASHBOARD = 'league_dashboard_team_slice'
    SOURCE_CONTINUOUS_TEAM = 'continuous_team'
    TRUST_TRUSTED = 'trusted'
    COMPLETENESS_COMPLETE = 'complete'

    __table_args__ = (
        db.CheckConstraint('team_id > 0', name='ck_team_public_publication_team_positive'),
        db.CheckConstraint('sequence > 0', name='ck_team_public_publication_sequence_positive'),
        db.CheckConstraint(
            'payload_schema_version > 0',
            name='ck_team_public_publication_payload_schema_positive',
        ),
        db.CheckConstraint(
            'length(publication_id) = 64',
            name='ck_team_public_publication_id_digest_length',
        ),
        db.CheckConstraint(
            'length(cohort_id) = 64',
            name='ck_team_public_publication_cohort_length',
        ),
        db.CheckConstraint(
            'length(package_digest) = 64',
            name='ck_team_public_publication_digest_length',
        ),
        db.CheckConstraint(
            "source_type IN ('league_dashboard_team_slice', 'continuous_team')",
            name='ck_team_public_publication_source_type',
        ),
        db.CheckConstraint(
            "trust_status IN ('trusted')",
            name='ck_team_public_publication_trust_status',
        ),
        db.CheckConstraint(
            "completeness_status IN ('complete')",
            name='ck_team_public_publication_completeness_status',
        ),
        db.CheckConstraint(
            'predecessor_publication_id IS NULL OR predecessor_publication_id != id',
            name='ck_team_public_publication_predecessor_not_self',
        ),
        db.CheckConstraint(
            "source_type != 'league_dashboard_team_slice' "
            'OR source_dashboard_snapshot_id IS NOT NULL',
            name='ck_team_public_publication_league_snapshot_required',
        ),
        db.UniqueConstraint(
            'team_id', 'sequence', name='uq_team_public_publication_team_sequence',
        ),
        db.UniqueConstraint(
            'team_id', 'source_type', 'source_dashboard_snapshot_id',
            name='uq_team_public_publication_league_source',
        ),
        db.Index('ix_team_public_publication_team_created', 'team_id', 'created_at'),
        db.Index('ix_team_public_publication_cohort', 'cohort_id'),
        db.Index('ix_team_public_publication_source_snapshot', 'source_dashboard_snapshot_id'),
    )

    id = db.Column(db.Integer, primary_key=True)
    publication_id = db.Column(db.String(64), nullable=False, unique=True)
    authority_version = db.Column(db.String(64), nullable=False)
    team_id = db.Column(db.Integer, nullable=False)
    source_type = db.Column(db.String(40), nullable=False)
    sequence = db.Column(db.Integer, nullable=False)
    predecessor_publication_id = db.Column(
        db.Integer,
        db.ForeignKey('team_public_publications.id'),
        nullable=True,
    )
    cohort_id = db.Column(db.String(64), nullable=False)
    represented_date = db.Column(db.Date, nullable=False)
    data_through = db.Column(db.Date, nullable=False)
    availability_reference_date = db.Column(db.Date, nullable=False)
    generated_at = db.Column(db.DateTime, nullable=False)
    source_published_at = db.Column(db.DateTime, nullable=False)
    source_sync_run_id = db.Column(
        db.Integer,
        db.ForeignKey('sync_runs.id'),
        nullable=False,
    )
    source_dashboard_snapshot_id = db.Column(
        db.Integer,
        db.ForeignKey('dashboard_snapshots.id'),
        nullable=True,
    )
    source_game_pks = db.Column(db.JSON, nullable=False)
    source_observation_fingerprints = db.Column(db.JSON, nullable=False)
    payload_schema_version = db.Column(db.Integer, nullable=False)
    method_versions = db.Column(db.JSON, nullable=False)
    canonical_fingerprints = db.Column(db.JSON, nullable=False)
    package_digest = db.Column(db.String(64), nullable=False)
    trust_status = db.Column(db.String(20), nullable=False)
    completeness_status = db.Column(db.String(20), nullable=False)
    is_correction = db.Column(db.Boolean, nullable=False, default=False)
    payload = db.Column(db.JSON, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)


class TeamPublicCurrentPointer(db.Model):
    __tablename__ = 'team_public_current_pointers'

    __table_args__ = (
        db.CheckConstraint('team_id > 0', name='ck_team_public_pointer_team_positive'),
        db.CheckConstraint('sequence > 0', name='ck_team_public_pointer_sequence_positive'),
        db.CheckConstraint(
            'authority_generation > 0',
            name='ck_team_public_pointer_generation_positive',
        ),
        db.UniqueConstraint(
            'current_publication_id', name='uq_team_public_pointer_publication',
        ),
        db.Index('ix_team_public_pointer_updated', 'updated_at'),
    )

    team_id = db.Column(db.Integer, primary_key=True)
    current_publication_id = db.Column(
        db.Integer,
        db.ForeignKey('team_public_publications.id'),
        nullable=False,
    )
    sequence = db.Column(db.Integer, nullable=False)
    authority_generation = db.Column(db.Integer, nullable=False, default=1)
    updated_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)


@event.listens_for(TeamPublicPublication, 'before_update')
def _prevent_team_publication_update(_mapper, _connection, _target):
    raise ValueError('team_public_publication_immutable')


@event.listens_for(TeamPublicPublication, 'before_delete')
def _prevent_team_publication_delete(_mapper, _connection, _target):
    raise ValueError('team_public_publication_immutable')
