"""add sync runs

Revision ID: 41f4f9a8d6c2
Revises: 9f3c1a7b2d4e
Create Date: 2026-06-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '41f4f9a8d6c2'
down_revision = '9f3c1a7b2d4e'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'sync_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('source', sa.String(length=30), nullable=False),
        sa.Column('latest_game_date', sa.Date(), nullable=True),
        sa.Column('latest_workload_date', sa.Date(), nullable=True),
        sa.Column('latest_fatigue_calculated_at', sa.DateTime(), nullable=True),
        sa.Column('records_processed', sa.Integer(), nullable=True),
        sa.Column('new_logs_added', sa.Integer(), nullable=True),
        sa.Column('pitchers_updated', sa.Integer(), nullable=True),
        sa.Column('errors', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('sync_runs', schema=None) as batch_op:
        batch_op.create_index('ix_sync_runs_started_at', ['started_at'], unique=False)
        batch_op.create_index('ix_sync_runs_status_completed', ['status', 'completed_at'], unique=False)


def downgrade():
    with op.batch_alter_table('sync_runs', schema=None) as batch_op:
        batch_op.drop_index('ix_sync_runs_status_completed')
        batch_op.drop_index('ix_sync_runs_started_at')
    op.drop_table('sync_runs')
