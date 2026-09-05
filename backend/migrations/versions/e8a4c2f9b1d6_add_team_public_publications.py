"""add dormant per-team public publication storage

Revision ID: e8a4c2f9b1d6
Revises: d5a8c2f7e1b4
Create Date: 2026-09-04
"""

from alembic import op
import sqlalchemy as sa


revision = 'e8a4c2f9b1d6'
down_revision = 'd5a8c2f7e1b4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'team_public_publications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('publication_id', sa.String(length=64), nullable=False),
        sa.Column('authority_version', sa.String(length=64), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('source_type', sa.String(length=40), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('predecessor_publication_id', sa.Integer(), nullable=True),
        sa.Column('cohort_id', sa.String(length=64), nullable=False),
        sa.Column('represented_date', sa.Date(), nullable=False),
        sa.Column('data_through', sa.Date(), nullable=False),
        sa.Column('availability_reference_date', sa.Date(), nullable=False),
        sa.Column('generated_at', sa.DateTime(), nullable=False),
        sa.Column('source_published_at', sa.DateTime(), nullable=False),
        sa.Column('source_sync_run_id', sa.Integer(), nullable=False),
        sa.Column('source_dashboard_snapshot_id', sa.Integer(), nullable=True),
        sa.Column('source_game_pks', sa.JSON(), nullable=False),
        sa.Column('source_observation_fingerprints', sa.JSON(), nullable=False),
        sa.Column('payload_schema_version', sa.Integer(), nullable=False),
        sa.Column('method_versions', sa.JSON(), nullable=False),
        sa.Column('canonical_fingerprints', sa.JSON(), nullable=False),
        sa.Column('package_digest', sa.String(length=64), nullable=False),
        sa.Column('trust_status', sa.String(length=20), nullable=False),
        sa.Column('completeness_status', sa.String(length=20), nullable=False),
        sa.Column('is_correction', sa.Boolean(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('team_id > 0', name='ck_team_public_publication_team_positive'),
        sa.CheckConstraint('sequence > 0', name='ck_team_public_publication_sequence_positive'),
        sa.CheckConstraint(
            'payload_schema_version > 0',
            name='ck_team_public_publication_payload_schema_positive',
        ),
        sa.CheckConstraint(
            'length(publication_id) = 64',
            name='ck_team_public_publication_id_digest_length',
        ),
        sa.CheckConstraint(
            'length(cohort_id) = 64',
            name='ck_team_public_publication_cohort_length',
        ),
        sa.CheckConstraint(
            'length(package_digest) = 64',
            name='ck_team_public_publication_digest_length',
        ),
        sa.CheckConstraint(
            "source_type IN ('league_dashboard_team_slice', 'continuous_team')",
            name='ck_team_public_publication_source_type',
        ),
        sa.CheckConstraint(
            "trust_status IN ('trusted')",
            name='ck_team_public_publication_trust_status',
        ),
        sa.CheckConstraint(
            "completeness_status IN ('complete')",
            name='ck_team_public_publication_completeness_status',
        ),
        sa.CheckConstraint(
            'predecessor_publication_id IS NULL OR predecessor_publication_id != id',
            name='ck_team_public_publication_predecessor_not_self',
        ),
        sa.CheckConstraint(
            "source_type != 'league_dashboard_team_slice' "
            'OR source_dashboard_snapshot_id IS NOT NULL',
            name='ck_team_public_publication_league_snapshot_required',
        ),
        sa.ForeignKeyConstraint(
            ['predecessor_publication_id'], ['team_public_publications.id']
        ),
        sa.ForeignKeyConstraint(['source_sync_run_id'], ['sync_runs.id']),
        sa.ForeignKeyConstraint(
            ['source_dashboard_snapshot_id'], ['dashboard_snapshots.id']
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('publication_id'),
        sa.UniqueConstraint(
            'team_id', 'sequence', name='uq_team_public_publication_team_sequence'
        ),
        sa.UniqueConstraint(
            'team_id', 'source_type', 'source_dashboard_snapshot_id',
            name='uq_team_public_publication_league_source',
        ),
    )
    op.create_index(
        'ix_team_public_publication_team_created',
        'team_public_publications',
        ['team_id', 'created_at'],
    )
    op.create_index(
        'ix_team_public_publication_cohort',
        'team_public_publications',
        ['cohort_id'],
    )
    op.create_index(
        'ix_team_public_publication_source_snapshot',
        'team_public_publications',
        ['source_dashboard_snapshot_id'],
    )

    op.create_table(
        'team_public_current_pointers',
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('current_publication_id', sa.Integer(), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('authority_generation', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('team_id > 0', name='ck_team_public_pointer_team_positive'),
        sa.CheckConstraint('sequence > 0', name='ck_team_public_pointer_sequence_positive'),
        sa.CheckConstraint(
            'authority_generation > 0',
            name='ck_team_public_pointer_generation_positive',
        ),
        sa.ForeignKeyConstraint(
            ['current_publication_id'], ['team_public_publications.id']
        ),
        sa.PrimaryKeyConstraint('team_id'),
        sa.UniqueConstraint(
            'current_publication_id', name='uq_team_public_pointer_publication'
        ),
    )
    op.create_index(
        'ix_team_public_pointer_updated',
        'team_public_current_pointers',
        ['updated_at'],
    )


def downgrade():
    op.drop_index(
        'ix_team_public_pointer_updated', table_name='team_public_current_pointers'
    )
    op.drop_table('team_public_current_pointers')
    op.drop_index(
        'ix_team_public_publication_source_snapshot',
        table_name='team_public_publications',
    )
    op.drop_index(
        'ix_team_public_publication_cohort', table_name='team_public_publications'
    )
    op.drop_index(
        'ix_team_public_publication_team_created',
        table_name='team_public_publications',
    )
    op.drop_table('team_public_publications')
