"""add dashboard snapshots

Revision ID: f4c2b8a9d1e3
Revises: d8f1a2b6c40e
Create Date: 2026-06-14 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f4c2b8a9d1e3'
down_revision = 'd8f1a2b6c40e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'dashboard_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('snapshot_type', sa.String(length=50), nullable=False),
        sa.Column('sync_run_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('payload_version', sa.Integer(), nullable=False),
        sa.Column('data_through', sa.Date(), nullable=True),
        sa.Column('availability_reference_date', sa.Date(), nullable=True),
        sa.Column('snapshot_generated_at', sa.DateTime(), nullable=False),
        sa.Column('source', sa.String(length=30), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('dashboard_snapshots', schema=None) as batch_op:
        batch_op.create_index(
            'ix_dashboard_snapshots_sync_run',
            ['sync_run_id'],
            unique=False,
        )
        batch_op.create_index(
            'ix_dashboard_snapshots_type_status_created',
            ['snapshot_type', 'status', 'created_at'],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table('dashboard_snapshots', schema=None) as batch_op:
        batch_op.drop_index('ix_dashboard_snapshots_type_status_created')
        batch_op.drop_index('ix_dashboard_snapshots_sync_run')
    op.drop_table('dashboard_snapshots')
