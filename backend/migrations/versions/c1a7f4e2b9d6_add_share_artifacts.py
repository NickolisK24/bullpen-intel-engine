"""add immutable share artifact domain

Creates the Share Cards SC-01 domain: share_artifacts and its evidence, asset,
and relation child tables. Domain only — no rendering, routes, or analytics.

Revision ID: c1a7f4e2b9d6
Revises: a1d8e4c6b2f0
Create Date: 2026-07-23
"""

from alembic import op
import sqlalchemy as sa


revision = 'c1a7f4e2b9d6'
down_revision = 'a1d8e4c6b2f0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'share_artifacts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('artifact_uid', sa.String(length=36), nullable=False),
        sa.Column('artifact_type', sa.String(length=80), nullable=False),
        sa.Column('render_version', sa.Integer(), nullable=False),
        sa.Column('subject_type', sa.String(length=40), nullable=False),
        sa.Column('subject_key', sa.String(length=200), nullable=False),
        sa.Column('product_date', sa.Date(), nullable=True),
        sa.Column('lifecycle_state', sa.String(length=20), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('trust_metadata', sa.JSON(), nullable=False),
        sa.Column('equivalence_key', sa.String(length=64), nullable=False),
        sa.Column('integrity_hash', sa.String(length=64), nullable=True),
        sa.Column('source', sa.String(length=120), nullable=False),
        sa.Column('schema_version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('published_at', sa.DateTime(), nullable=True),
        sa.Column('superseded_at', sa.DateTime(), nullable=True),
        sa.Column('withdrawn_at', sa.DateTime(), nullable=True),
        sa.Column('withdrawn_reason', sa.String(length=200), nullable=True),
        sa.CheckConstraint(
            "lifecycle_state IN ('draft', 'published', 'superseded', 'withdrawn')",
            name='ck_share_artifacts_lifecycle_state',
        ),
        sa.CheckConstraint(
            'render_version >= 1',
            name='ck_share_artifacts_render_version',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('artifact_uid', name='uq_share_artifacts_artifact_uid'),
    )
    with op.batch_alter_table('share_artifacts', schema=None) as batch_op:
        batch_op.create_index(
            'ix_share_artifacts_type_subject',
            ['artifact_type', 'subject_type', 'subject_key'],
            unique=False,
        )
        batch_op.create_index(
            'ix_share_artifacts_equivalence_state',
            ['equivalence_key', 'lifecycle_state'],
            unique=False,
        )
        batch_op.create_index(
            'ix_share_artifacts_lifecycle_state', ['lifecycle_state'], unique=False,
        )
        batch_op.create_index(
            'ix_share_artifacts_product_date', ['product_date'], unique=False,
        )

    op.create_table(
        'share_artifact_evidence',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('share_artifact_id', sa.Integer(), nullable=False),
        sa.Column('evidence_key', sa.String(length=220), nullable=False),
        sa.Column('role', sa.String(length=60), nullable=False),
        sa.Column('claim', sa.Text(), nullable=True),
        sa.Column('completeness_state', sa.String(length=20), nullable=True),
        sa.Column('snapshot', sa.JSON(), nullable=True),
        sa.Column('evidence_object_id', sa.Integer(), nullable=True),
        sa.Column('sort_index', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['share_artifact_id'], ['share_artifacts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'share_artifact_id', 'sort_index',
            name='uq_share_artifact_evidence_order',
        ),
    )
    with op.batch_alter_table('share_artifact_evidence', schema=None) as batch_op:
        batch_op.create_index(
            'ix_share_artifact_evidence_artifact', ['share_artifact_id'], unique=False,
        )
        batch_op.create_index(
            'ix_share_artifact_evidence_key', ['evidence_key'], unique=False,
        )

    op.create_table(
        'share_artifact_assets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('share_artifact_id', sa.Integer(), nullable=False),
        sa.Column('asset_role', sa.String(length=60), nullable=False),
        sa.Column('media_type', sa.String(length=80), nullable=False),
        sa.Column('render_version', sa.Integer(), nullable=False),
        sa.Column('content_hash', sa.String(length=64), nullable=True),
        sa.Column('storage_uri', sa.String(length=500), nullable=True),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('byte_size', sa.Integer(), nullable=True),
        sa.Column('asset_metadata', sa.JSON(), nullable=True),
        sa.Column('sort_index', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            'render_version >= 1',
            name='ck_share_artifact_assets_render_version',
        ),
        sa.ForeignKeyConstraint(['share_artifact_id'], ['share_artifacts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'share_artifact_id', 'asset_role', 'render_version',
            name='uq_share_artifact_assets_role_version',
        ),
    )
    with op.batch_alter_table('share_artifact_assets', schema=None) as batch_op:
        batch_op.create_index(
            'ix_share_artifact_assets_artifact', ['share_artifact_id'], unique=False,
        )

    op.create_table(
        'share_artifact_relations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_artifact_id', sa.Integer(), nullable=False),
        sa.Column('target_artifact_id', sa.Integer(), nullable=False),
        sa.Column('relation_type', sa.String(length=40), nullable=False),
        sa.Column('relation_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "relation_type IN ('supersedes', 'derived_from', 'variant_of')",
            name='ck_share_artifact_relations_type',
        ),
        sa.CheckConstraint(
            'source_artifact_id <> target_artifact_id',
            name='ck_share_artifact_relations_no_self',
        ),
        sa.ForeignKeyConstraint(['source_artifact_id'], ['share_artifacts.id']),
        sa.ForeignKeyConstraint(['target_artifact_id'], ['share_artifacts.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'source_artifact_id', 'target_artifact_id', 'relation_type',
            name='uq_share_artifact_relations_edge',
        ),
    )
    with op.batch_alter_table('share_artifact_relations', schema=None) as batch_op:
        batch_op.create_index(
            'ix_share_artifact_relations_source', ['source_artifact_id'], unique=False,
        )
        batch_op.create_index(
            'ix_share_artifact_relations_target', ['target_artifact_id'], unique=False,
        )
        batch_op.create_index(
            'ix_share_artifact_relations_type', ['relation_type'], unique=False,
        )


def downgrade():
    with op.batch_alter_table('share_artifact_relations', schema=None) as batch_op:
        batch_op.drop_index('ix_share_artifact_relations_type')
        batch_op.drop_index('ix_share_artifact_relations_target')
        batch_op.drop_index('ix_share_artifact_relations_source')
    op.drop_table('share_artifact_relations')

    with op.batch_alter_table('share_artifact_assets', schema=None) as batch_op:
        batch_op.drop_index('ix_share_artifact_assets_artifact')
    op.drop_table('share_artifact_assets')

    with op.batch_alter_table('share_artifact_evidence', schema=None) as batch_op:
        batch_op.drop_index('ix_share_artifact_evidence_key')
        batch_op.drop_index('ix_share_artifact_evidence_artifact')
    op.drop_table('share_artifact_evidence')

    with op.batch_alter_table('share_artifacts', schema=None) as batch_op:
        batch_op.drop_index('ix_share_artifacts_product_date')
        batch_op.drop_index('ix_share_artifacts_lifecycle_state')
        batch_op.drop_index('ix_share_artifacts_equivalence_state')
        batch_op.drop_index('ix_share_artifacts_type_subject')
    op.drop_table('share_artifacts')
