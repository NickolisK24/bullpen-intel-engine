"""add sync jobs

Revision ID: fa9c1d2e3b47
Revises: e4b7c9d2a6f0
Create Date: 2026-07-06 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'fa9c1d2e3b47'
down_revision = 'e4b7c9d2a6f0'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'sync_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('job_name', sa.String(length=80), nullable=False),
        sa.Column('job_family', sa.String(length=50), nullable=False),
        sa.Column('lane', sa.String(length=50), nullable=False),
        sa.Column('scope_key', sa.String(length=160), nullable=False),
        sa.Column('product_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('last_heartbeat_at', sa.DateTime(), nullable=True),
        sa.Column('duration_ms', sa.Integer(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('error_type', sa.String(length=120), nullable=True),
        sa.Column('details_json', sa.JSON(), nullable=True),
        sa.Column('sync_run_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'job_name',
            'scope_key',
            'product_date',
            name='uq_sync_jobs_name_scope_date',
        ),
    )
    with op.batch_alter_table('sync_jobs', schema=None) as batch_op:
        batch_op.create_index('ix_sync_jobs_status', ['status'], unique=False)
        batch_op.create_index('ix_sync_jobs_product_date', ['product_date'], unique=False)
        batch_op.create_index('ix_sync_jobs_job_family', ['job_family'], unique=False)
        batch_op.create_index('ix_sync_jobs_lane', ['lane'], unique=False)
        batch_op.create_index('ix_sync_jobs_job_name', ['job_name'], unique=False)
        batch_op.create_index('ix_sync_jobs_updated_at', ['updated_at'], unique=False)


def downgrade():
    with op.batch_alter_table('sync_jobs', schema=None) as batch_op:
        batch_op.drop_index('ix_sync_jobs_updated_at')
        batch_op.drop_index('ix_sync_jobs_job_name')
        batch_op.drop_index('ix_sync_jobs_lane')
        batch_op.drop_index('ix_sync_jobs_job_family')
        batch_op.drop_index('ix_sync_jobs_product_date')
        batch_op.drop_index('ix_sync_jobs_status')
    op.drop_table('sync_jobs')
