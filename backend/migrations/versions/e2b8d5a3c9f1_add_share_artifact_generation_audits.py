"""add share artifact generation audits

Creates the SC-03A durable internal audit of Team State Share Artifact
generation attempts (published / reused / refused / failed_closed). Internal
operator record only — not a public analytics event.

Revision ID: e2b8d5a3c9f1
Revises: c1a7f4e2b9d6
Create Date: 2026-07-23
"""

from alembic import op
import sqlalchemy as sa


revision = 'e2b8d5a3c9f1'
down_revision = 'c1a7f4e2b9d6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'share_artifact_generation_audits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('requested_product_date', sa.Date(), nullable=True),
        sa.Column('resolved_product_date', sa.Date(), nullable=True),
        sa.Column('source_snapshot_id', sa.Integer(), nullable=True),
        sa.Column('source_sync_run_id', sa.Integer(), nullable=True),
        sa.Column('payload_version', sa.String(length=64), nullable=True),
        sa.Column('outcome', sa.String(length=20), nullable=False),
        sa.Column('eligible', sa.Boolean(), nullable=False),
        sa.Column('blocking_conditions', sa.JSON(), nullable=True),
        sa.Column('reasons', sa.JSON(), nullable=True),
        sa.Column('share_artifact_id', sa.Integer(), nullable=True),
        sa.Column('artifact_public_id', sa.String(length=64), nullable=True),
        sa.Column('created_new', sa.Boolean(), nullable=False),
        sa.Column('reused_existing', sa.Boolean(), nullable=False),
        sa.Column('request_source', sa.String(length=60), nullable=True),
        sa.Column('actor', sa.String(length=120), nullable=True),
        sa.Column('failure_code', sa.String(length=80), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('published', 'reused', 'refused', 'failed_closed')",
            name='ck_sa_gen_audits_outcome',
        ),
        sa.ForeignKeyConstraint(['share_artifact_id'], ['share_artifacts.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('share_artifact_generation_audits', schema=None) as batch_op:
        batch_op.create_index('ix_sa_gen_audits_team', ['team_id'], unique=False)
        batch_op.create_index(
            'ix_sa_gen_audits_team_created', ['team_id', 'created_at'], unique=False,
        )
        batch_op.create_index('ix_sa_gen_audits_outcome', ['outcome'], unique=False)
        batch_op.create_index(
            'ix_sa_gen_audits_artifact', ['share_artifact_id'], unique=False,
        )


def downgrade():
    with op.batch_alter_table('share_artifact_generation_audits', schema=None) as batch_op:
        batch_op.drop_index('ix_sa_gen_audits_artifact')
        batch_op.drop_index('ix_sa_gen_audits_outcome')
        batch_op.drop_index('ix_sa_gen_audits_team_created')
        batch_op.drop_index('ix_sa_gen_audits_team')
    op.drop_table('share_artifact_generation_audits')
