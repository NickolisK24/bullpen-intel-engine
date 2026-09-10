"""add SP-13 repair orchestration

Revision ID: b7d3e9f1a5c2
Revises: f1a4c8d2e6b9
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa


revision = 'b7d3e9f1a5c2'
down_revision = 'f1a4c8d2e6b9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'repair_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('request_key', sa.String(36), nullable=False),
        sa.Column('request_fingerprint', sa.String(64), nullable=False),
        sa.Column('active_dedupe_key', sa.String(255)),
        sa.Column('schema_version', sa.String(40), nullable=False),
        sa.Column('plan_version', sa.String(40), nullable=False),
        sa.Column('mode', sa.String(30), nullable=False),
        sa.Column('status', sa.String(30), nullable=False),
        sa.Column('requested_scope_type', sa.String(30), nullable=False),
        sa.Column('scope_json', sa.JSON(), nullable=False),
        sa.Column('baseball_date_start', sa.Date(), nullable=False),
        sa.Column('baseball_date_end', sa.Date(), nullable=False),
        sa.Column('source_domain', sa.String(40), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('requested_by', sa.String(120), nullable=False),
        sa.Column('trigger_type', sa.String(30), nullable=False),
        sa.Column('dry_run', sa.Boolean(), nullable=False),
        sa.Column('requested_rules_version', sa.String(40)),
        sa.Column('requested_method_versions_json', sa.JSON(), nullable=False),
        sa.Column('correlation_id', sa.String(36), nullable=False),
        sa.Column('root_sync_run_id', sa.Integer()),
        sa.Column('root_job_id', sa.Integer()),
        sa.Column('check_job_id', sa.Integer()),
        sa.Column('plan_fingerprint', sa.String(64)),
        sa.Column('plan_json', sa.JSON(), nullable=False),
        sa.Column('estimated_counts_json', sa.JSON(), nullable=False),
        sa.Column('outcome_json', sa.JSON(), nullable=False),
        sa.Column('failure_reason', sa.Text()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime()),
        sa.Column('completed_at', sa.DateTime()),
        sa.Column('cancelled_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['root_sync_run_id'], ['sync_runs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['root_job_id'], ['sync_jobs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['check_job_id'], ['sync_jobs.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('request_key', name='uq_repair_requests_key'),
        sa.CheckConstraint(
            "mode IN ('targeted_repair', 'historical_backfill', 'full_reconciliation', "
            "'method_replay', 'rule_replay')", name='ck_repair_requests_mode',
        ),
        sa.CheckConstraint(
            "status IN ('planned', 'running', 'blocked', 'completed', "
            "'completed_partial', 'failed', 'cancelled')",
            name='ck_repair_requests_status',
        ),
    )
    op.create_index('ix_repair_requests_status_created', 'repair_requests', ['status', 'created_at'])
    op.create_index('ix_repair_requests_dates', 'repair_requests', ['baseball_date_start', 'baseball_date_end'])
    op.create_index('ix_repair_requests_correlation', 'repair_requests', ['correlation_id'])
    op.create_index(
        'uq_repair_requests_active_dedupe', 'repair_requests', ['active_dedupe_key'], unique=True,
        postgresql_where=sa.text(
            "active_dedupe_key IS NOT NULL AND status IN ('planned', 'running', 'blocked')"
        ),
        sqlite_where=sa.text(
            "active_dedupe_key IS NOT NULL AND status IN ('planned', 'running', 'blocked')"
        ),
    )

    op.create_table(
        'repair_request_chunks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('repair_request_id', sa.Integer(), nullable=False),
        sa.Column('chunk_key', sa.String(160), nullable=False),
        sa.Column('chunk_order', sa.Integer(), nullable=False),
        sa.Column('owner_package', sa.String(20), nullable=False),
        sa.Column('baseball_date_start', sa.Date(), nullable=False),
        sa.Column('baseball_date_end', sa.Date(), nullable=False),
        sa.Column('scope_json', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('child_job_ids_json', sa.JSON(), nullable=False),
        sa.Column('outcome_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime()),
        sa.Column('completed_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['repair_request_id'], ['repair_requests.id'], ondelete='CASCADE'),
        sa.UniqueConstraint(
            'repair_request_id', 'chunk_key', name='uq_repair_request_chunks_key',
        ),
        sa.CheckConstraint(
            "status IN ('planned', 'dispatched', 'running', 'succeeded', "
            "'blocked', 'failed', 'cancelled')", name='ck_repair_request_chunks_status',
        ),
    )
    op.create_index('ix_repair_request_chunks_status', 'repair_request_chunks', ['repair_request_id', 'status'])
    op.create_index('ix_repair_request_chunks_dates', 'repair_request_chunks', ['baseball_date_start', 'baseball_date_end'])

    op.create_table(
        'repair_request_blockers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('repair_request_id', sa.Integer(), nullable=False),
        sa.Column('blocker_type', sa.String(50), nullable=False),
        sa.Column('entity_type', sa.String(30), nullable=False),
        sa.Column('entity_key', sa.String(160), nullable=False),
        sa.Column('retryable', sa.Boolean(), nullable=False),
        sa.Column('details_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['repair_request_id'], ['repair_requests.id'], ondelete='CASCADE'),
        sa.UniqueConstraint(
            'repair_request_id', 'blocker_type', 'entity_type', 'entity_key',
            name='uq_repair_request_blockers_identity',
        ),
    )
    op.create_index('ix_repair_request_blockers_type', 'repair_request_blockers', ['blocker_type', 'repair_request_id'])

    with op.batch_alter_table('canonical_impact_plans') as batch:
        batch.add_column(sa.Column('repair_request_id', sa.Integer()))
        batch.add_column(sa.Column('replay_kind', sa.String(20)))
        batch.add_column(sa.Column('replay_from_plan_id', sa.Integer()))
        batch.add_column(sa.Column('method_versions_override_json', sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
        batch.add_column(sa.Column('publication_mode', sa.String(20), nullable=False, server_default='current'))
        batch.create_foreign_key('fk_impact_plan_repair_request', 'repair_requests', ['repair_request_id'], ['id'], ondelete='SET NULL')
        batch.create_foreign_key('fk_impact_plan_replay_source', 'canonical_impact_plans', ['replay_from_plan_id'], ['id'], ondelete='SET NULL')
        batch.create_check_constraint(
            'ck_canonical_impact_plans_publication_mode',
            "publication_mode IN ('current', 'historical')",
        )
    op.create_index(
        'ix_canonical_impact_plans_repair', 'canonical_impact_plans',
        ['repair_request_id', 'id'],
    )


def downgrade():
    op.drop_index('ix_canonical_impact_plans_repair', table_name='canonical_impact_plans')
    with op.batch_alter_table('canonical_impact_plans') as batch:
        batch.drop_constraint('ck_canonical_impact_plans_publication_mode', type_='check')
        batch.drop_constraint('fk_impact_plan_replay_source', type_='foreignkey')
        batch.drop_constraint('fk_impact_plan_repair_request', type_='foreignkey')
        batch.drop_column('publication_mode')
        batch.drop_column('method_versions_override_json')
        batch.drop_column('replay_from_plan_id')
        batch.drop_column('replay_kind')
        batch.drop_column('repair_request_id')
    op.drop_index('ix_repair_request_blockers_type', table_name='repair_request_blockers')
    op.drop_table('repair_request_blockers')
    op.drop_index('ix_repair_request_chunks_dates', table_name='repair_request_chunks')
    op.drop_index('ix_repair_request_chunks_status', table_name='repair_request_chunks')
    op.drop_table('repair_request_chunks')
    op.drop_index('uq_repair_requests_active_dedupe', table_name='repair_requests')
    op.drop_index('ix_repair_requests_correlation', table_name='repair_requests')
    op.drop_index('ix_repair_requests_dates', table_name='repair_requests')
    op.drop_index('ix_repair_requests_status_created', table_name='repair_requests')
    op.drop_table('repair_requests')
