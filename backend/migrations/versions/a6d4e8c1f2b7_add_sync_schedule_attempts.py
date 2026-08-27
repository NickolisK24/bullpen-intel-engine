"""add durable sync schedule attempts

Revision ID: a6d4e8c1f2b7
Revises: f3c8a1d7e5b2
Create Date: 2026-08-27 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'a6d4e8c1f2b7'
down_revision = 'f3c8a1d7e5b2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'sync_schedule_attempts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('mode', sa.String(length=20), nullable=False),
        sa.Column('source', sa.String(length=30), nullable=False),
        sa.Column('intended_window', sa.String(length=60), nullable=False),
        sa.Column('scheduled_for', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('outcome', sa.String(length=30), nullable=False),
        sa.Column('sync_run_id', sa.Integer(), nullable=True),
        sa.Column('snapshot_before_id', sa.Integer(), nullable=True),
        sa.Column('snapshot_after_id', sa.Integer(), nullable=True),
        sa.Column('publication_outcome', sa.String(length=50), nullable=True),
        sa.Column('recovery_reason', sa.Text(), nullable=True),
        sa.Column('operator', sa.String(length=100), nullable=True),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_sync_schedule_attempts_source_started', 'sync_schedule_attempts',
        ['source', 'started_at'], unique=False,
    )
    op.create_index(
        'ix_sync_schedule_attempts_window', 'sync_schedule_attempts',
        ['mode', 'intended_window', 'outcome'], unique=False,
    )


def downgrade():
    op.drop_index('ix_sync_schedule_attempts_window', table_name='sync_schedule_attempts')
    op.drop_index('ix_sync_schedule_attempts_source_started', table_name='sync_schedule_attempts')
    op.drop_table('sync_schedule_attempts')
