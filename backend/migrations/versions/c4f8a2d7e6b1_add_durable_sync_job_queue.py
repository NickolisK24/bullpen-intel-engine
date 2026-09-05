"""add durable sync job queue leases, dedupe, and attempts

Revision ID: c4f8a2d7e6b1
Revises: b5e7c1d9a4f2
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa


revision = 'c4f8a2d7e6b1'
down_revision = 'b5e7c1d9a4f2'
branch_labels = None
depends_on = None


ACTIVE_DEDUPE_PREDICATE = (
    "dedupe_key IS NOT NULL AND status IN "
    "('pending', 'running', 'retry_wait')"
)


def upgrade():
    with op.batch_alter_table('sync_jobs', schema=None) as batch_op:
        batch_op.drop_constraint(
            'uq_sync_jobs_name_scope_date',
            type_='unique',
        )
        batch_op.add_column(sa.Column('scope_type', sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column('payload_schema_version', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('dedupe_key', sa.String(length=255), nullable=True))
        batch_op.add_column(
            sa.Column('priority', sa.Integer(), nullable=False, server_default='100')
        )
        batch_op.add_column(sa.Column('first_available_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('available_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('claimed_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('lease_until', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('worker_id', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('claim_token', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('dead_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('result_json', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('parent_job_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_sync_jobs_parent_job_id_sync_jobs',
            'sync_jobs',
            ['parent_job_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_check_constraint(
            'ck_sync_jobs_priority_range',
            'priority >= 0 AND priority <= 1000',
        )
        batch_op.create_check_constraint(
            'ck_sync_jobs_attempt_bounds',
            'attempts >= 0 AND max_attempts > 0',
        )

    op.create_index(
        'ix_sync_jobs_claim_ready',
        'sync_jobs',
        ['lane', 'status', 'priority', 'available_at', 'created_at', 'id'],
        unique=False,
    )
    op.create_index(
        'ix_sync_jobs_lease_expiry',
        'sync_jobs',
        ['lane', 'status', 'lease_until'],
        unique=False,
    )
    op.create_index(
        'uq_sync_jobs_active_dedupe_key',
        'sync_jobs',
        ['dedupe_key'],
        unique=True,
        postgresql_where=sa.text(ACTIVE_DEDUPE_PREDICATE),
        sqlite_where=sa.text(ACTIVE_DEDUPE_PREDICATE),
    )

    op.create_table(
        'sync_job_attempts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sync_job_id', sa.Integer(), nullable=False),
        sa.Column('attempt_number', sa.Integer(), nullable=False),
        sa.Column('worker_id', sa.String(length=120), nullable=False),
        sa.Column('claim_token', sa.String(length=36), nullable=False),
        sa.Column('claimed_at', sa.DateTime(), nullable=False),
        sa.Column('lease_until', sa.DateTime(), nullable=False),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('outcome', sa.String(length=30), nullable=True),
        sa.Column('retryable', sa.Boolean(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('error_type', sa.String(length=120), nullable=True),
        sa.ForeignKeyConstraint(
            ['sync_job_id'],
            ['sync_jobs.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'sync_job_id',
            'attempt_number',
            name='uq_sync_job_attempts_job_number',
        ),
    )
    op.create_index(
        'ix_sync_job_attempts_job_claimed',
        'sync_job_attempts',
        ['sync_job_id', 'claimed_at'],
        unique=False,
    )
    op.create_index(
        'ix_sync_job_attempts_claim_token',
        'sync_job_attempts',
        ['claim_token'],
        unique=False,
    )


def downgrade():
    op.drop_index(
        'ix_sync_job_attempts_claim_token',
        table_name='sync_job_attempts',
    )
    op.drop_index(
        'ix_sync_job_attempts_job_claimed',
        table_name='sync_job_attempts',
    )
    op.drop_table('sync_job_attempts')

    op.drop_index('uq_sync_jobs_active_dedupe_key', table_name='sync_jobs')
    op.drop_index('ix_sync_jobs_lease_expiry', table_name='sync_jobs')
    op.drop_index('ix_sync_jobs_claim_ready', table_name='sync_jobs')

    with op.batch_alter_table('sync_jobs', schema=None) as batch_op:
        batch_op.drop_constraint(
            'ck_sync_jobs_attempt_bounds',
            type_='check',
        )
        batch_op.drop_constraint(
            'ck_sync_jobs_priority_range',
            type_='check',
        )
        batch_op.drop_constraint(
            'fk_sync_jobs_parent_job_id_sync_jobs',
            type_='foreignkey',
        )
        batch_op.drop_column('parent_job_id')
        batch_op.drop_column('result_json')
        batch_op.drop_column('dead_at')
        batch_op.drop_column('claim_token')
        batch_op.drop_column('worker_id')
        batch_op.drop_column('lease_until')
        batch_op.drop_column('claimed_at')
        batch_op.drop_column('available_at')
        batch_op.drop_column('first_available_at')
        batch_op.drop_column('priority')
        batch_op.drop_column('dedupe_key')
        batch_op.drop_column('payload_schema_version')
        batch_op.drop_column('scope_type')
        batch_op.create_unique_constraint(
            'uq_sync_jobs_name_scope_date',
            ['job_name', 'scope_key', 'product_date'],
        )
