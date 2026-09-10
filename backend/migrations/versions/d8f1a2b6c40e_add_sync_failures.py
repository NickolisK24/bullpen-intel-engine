"""add sync_failures dead-letter table

Durable dead-letter capture for records that fail during a sync. One bad
record no longer aborts a whole sync: the failed entity is recorded here with
enough payload to retry it, and the run is marked 'partial'.

Revision ID: d8f1a2b6c40e
Revises: c5d9e3a1f7b2
Create Date: 2026-06-12 00:00:01.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd8f1a2b6c40e'
down_revision = 'c5d9e3a1f7b2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'sync_failures',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sync_run_id', sa.Integer(), nullable=True),
        sa.Column('job_name', sa.String(length=50), nullable=False,
                  server_default='daily_sync'),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('entity_ref', sa.String(length=120), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('resolved', sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column('resolved_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('sync_failures', schema=None) as batch_op:
        batch_op.create_index('ix_sync_failures_resolved', ['resolved'], unique=False)
        batch_op.create_index('ix_sync_failures_run', ['sync_run_id'], unique=False)


def downgrade():
    with op.batch_alter_table('sync_failures', schema=None) as batch_op:
        batch_op.drop_index('ix_sync_failures_run')
        batch_op.drop_index('ix_sync_failures_resolved')
    op.drop_table('sync_failures')
