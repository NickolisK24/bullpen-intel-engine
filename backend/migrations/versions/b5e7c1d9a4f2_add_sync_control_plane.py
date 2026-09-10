"""add sync control-plane vocabulary, scope, lineage, and outcomes

Revision ID: b5e7c1d9a4f2
Revises: e8a4c2f9b1d6
Create Date: 2026-09-05
"""

from alembic import op
import sqlalchemy as sa


revision = 'b5e7c1d9a4f2'
down_revision = 'e8a4c2f9b1d6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('sync_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('run_type', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('trigger_type', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('baseball_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('source_domain', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('parent_sync_run_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('correlation_id', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('publication_id', sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column('source_reads', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('source_changes', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('canonical_mutations', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('affected_games', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('affected_teams', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('affected_pitchers', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('downstream_work_created', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('warnings_count', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('zero_mutation', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('outcome_json', sa.JSON(), nullable=True))
        batch_op.create_foreign_key(
            'fk_sync_runs_parent_sync_run_id_sync_runs',
            'sync_runs',
            ['parent_sync_run_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_index('ix_sync_runs_type_started', ['run_type', 'started_at'], unique=False)
        batch_op.create_index('ix_sync_runs_trigger_type', ['trigger_type'], unique=False)
        batch_op.create_index('ix_sync_runs_baseball_date', ['baseball_date'], unique=False)
        batch_op.create_index('ix_sync_runs_correlation_id', ['correlation_id'], unique=False)
        batch_op.create_index('ix_sync_runs_parent', ['parent_sync_run_id'], unique=False)
        batch_op.create_index('ix_sync_runs_source_domain', ['source_domain'], unique=False)

    op.create_table(
        'sync_run_scopes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sync_run_id', sa.Integer(), nullable=False),
        sa.Column('scope_type', sa.String(length=30), nullable=False),
        sa.Column('scope_key', sa.String(length=120), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['sync_run_id'],
            ['sync_runs.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'sync_run_id',
            'scope_type',
            'scope_key',
            name='uq_sync_run_scopes_run_type_key',
        ),
    )
    with op.batch_alter_table('sync_run_scopes', schema=None) as batch_op:
        batch_op.create_index(
            'ix_sync_run_scopes_type_key_run',
            ['scope_type', 'scope_key', 'sync_run_id'],
            unique=False,
        )

    with op.batch_alter_table('sync_failures', schema=None) as batch_op:
        batch_op.add_column(sa.Column('failure_class', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('stage', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('source_domain', sa.String(length=40), nullable=True))
        batch_op.add_column(sa.Column('retryable', sa.Boolean(), nullable=True))
        batch_op.create_index('ix_sync_failures_run_stage', ['sync_run_id', 'stage'], unique=False)
        batch_op.create_index('ix_sync_failures_class', ['failure_class'], unique=False)


def downgrade():
    with op.batch_alter_table('sync_failures', schema=None) as batch_op:
        batch_op.drop_index('ix_sync_failures_class')
        batch_op.drop_index('ix_sync_failures_run_stage')
        batch_op.drop_column('retryable')
        batch_op.drop_column('source_domain')
        batch_op.drop_column('stage')
        batch_op.drop_column('failure_class')

    with op.batch_alter_table('sync_run_scopes', schema=None) as batch_op:
        batch_op.drop_index('ix_sync_run_scopes_type_key_run')
    op.drop_table('sync_run_scopes')

    with op.batch_alter_table('sync_runs', schema=None) as batch_op:
        batch_op.drop_index('ix_sync_runs_source_domain')
        batch_op.drop_index('ix_sync_runs_parent')
        batch_op.drop_index('ix_sync_runs_correlation_id')
        batch_op.drop_index('ix_sync_runs_baseball_date')
        batch_op.drop_index('ix_sync_runs_trigger_type')
        batch_op.drop_index('ix_sync_runs_type_started')
        batch_op.drop_constraint(
            'fk_sync_runs_parent_sync_run_id_sync_runs',
            type_='foreignkey',
        )
        batch_op.drop_column('outcome_json')
        batch_op.drop_column('zero_mutation')
        batch_op.drop_column('warnings_count')
        batch_op.drop_column('downstream_work_created')
        batch_op.drop_column('affected_pitchers')
        batch_op.drop_column('affected_teams')
        batch_op.drop_column('affected_games')
        batch_op.drop_column('canonical_mutations')
        batch_op.drop_column('source_changes')
        batch_op.drop_column('source_reads')
        batch_op.drop_column('publication_id')
        batch_op.drop_column('correlation_id')
        batch_op.drop_column('parent_sync_run_id')
        batch_op.drop_column('source_domain')
        batch_op.drop_column('baseball_date')
        batch_op.drop_column('trigger_type')
        batch_op.drop_column('run_type')
