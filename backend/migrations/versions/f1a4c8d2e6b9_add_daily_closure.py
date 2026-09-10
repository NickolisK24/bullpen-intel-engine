"""add SP-12 daily closure ledger

Revision ID: f1a4c8d2e6b9
Revises: e3f6a9b2d5c8
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa


revision = 'f1a4c8d2e6b9'
down_revision = 'e3f6a9b2d5c8'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'baseball_date_closures',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('baseball_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('current_version_number', sa.Integer(), nullable=False),
        sa.Column('expected_games', sa.Integer(), nullable=False),
        sa.Column('resolved_games', sa.Integer(), nullable=False),
        sa.Column('final_games', sa.Integer(), nullable=False),
        sa.Column('reconciled_final_games', sa.Integer(), nullable=False),
        sa.Column('unresolved_games', sa.Integer(), nullable=False),
        sa.Column('expected_teams', sa.Integer(), nullable=False),
        sa.Column('reconciled_rosters', sa.Integer(), nullable=False),
        sa.Column('transaction_completeness', sa.String(20), nullable=False),
        sa.Column('pending_jobs', sa.Integer(), nullable=False),
        sa.Column('failed_jobs', sa.Integer(), nullable=False),
        sa.Column('required_publications_complete', sa.Boolean(), nullable=False),
        sa.Column('optional_enrichment_outstanding', sa.Boolean(), nullable=False),
        sa.Column('source_data_through', sa.DateTime()),
        sa.Column('closure_fingerprint', sa.String(64)),
        sa.Column('closure_schema_version', sa.String(40), nullable=False),
        sa.Column('recheck_policy_version', sa.String(40), nullable=False),
        sa.Column('next_check_at', sa.DateTime()),
        sa.Column('first_checked_at', sa.DateTime()),
        sa.Column('closed_at', sa.DateTime()),
        sa.Column('reopened_at', sa.DateTime()),
        sa.Column('reopened_count', sa.Integer(), nullable=False),
        sa.Column('publication_id', sa.Integer()),
        sa.Column('sync_run_id', sa.Integer()),
        sa.Column('metrics_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['publication_id'], ['atomic_publications.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('baseball_date', name='uq_baseball_date_closures_date'),
        sa.CheckConstraint(
            "status IN ('open', 'checking', 'blocked', 'closed', 'reopened', 'failed')",
            name='ck_baseball_date_closures_status',
        ),
    )
    op.create_index('ix_baseball_date_closures_status_date', 'baseball_date_closures', ['status', 'baseball_date'])
    op.create_index('ix_baseball_date_closures_reopened', 'baseball_date_closures', ['reopened_at', 'baseball_date'])
    op.create_index('ix_baseball_date_closures_publication', 'baseball_date_closures', ['publication_id'])
    op.create_table(
        'baseball_date_closure_versions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('closure_id', sa.Integer(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('predecessor_version_id', sa.Integer()),
        sa.Column('baseball_date', sa.Date(), nullable=False),
        sa.Column('event_type', sa.String(20), nullable=False),
        sa.Column('closure_fingerprint', sa.String(64), nullable=False),
        sa.Column('publication_id', sa.Integer()),
        sa.Column('evidence_json', sa.JSON(), nullable=False),
        sa.Column('sync_run_id', sa.Integer()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['closure_id'], ['baseball_date_closures.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['predecessor_version_id'], ['baseball_date_closure_versions.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['publication_id'], ['atomic_publications.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('closure_id', 'version_number', name='uq_baseball_date_closure_versions_number'),
        sa.CheckConstraint('version_number > 0', name='ck_baseball_date_closure_versions_number'),
        sa.CheckConstraint("event_type IN ('closed', 'reopened')", name='ck_baseball_date_closure_versions_event'),
    )
    op.create_index('ix_baseball_date_closure_versions_date', 'baseball_date_closure_versions', ['baseball_date', 'version_number'])
    op.create_index('ix_baseball_date_closure_versions_fingerprint', 'baseball_date_closure_versions', ['closure_fingerprint'])
    op.create_table(
        'baseball_date_closure_blockers',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('closure_id', sa.Integer(), nullable=False),
        sa.Column('blocker_type', sa.String(50), nullable=False),
        sa.Column('entity_type', sa.String(30), nullable=False),
        sa.Column('entity_key', sa.String(120), nullable=False),
        sa.Column('retryable', sa.Boolean(), nullable=False),
        sa.Column('details_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['closure_id'], ['baseball_date_closures.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('closure_id', 'blocker_type', 'entity_type', 'entity_key', name='uq_baseball_date_closure_blocker'),
    )
    op.create_index('ix_baseball_date_closure_blockers_type', 'baseball_date_closure_blockers', ['blocker_type', 'closure_id'])


def downgrade():
    op.drop_index('ix_baseball_date_closure_blockers_type', table_name='baseball_date_closure_blockers')
    op.drop_table('baseball_date_closure_blockers')
    op.drop_index('ix_baseball_date_closure_versions_fingerprint', table_name='baseball_date_closure_versions')
    op.drop_index('ix_baseball_date_closure_versions_date', table_name='baseball_date_closure_versions')
    op.drop_table('baseball_date_closure_versions')
    op.drop_index('ix_baseball_date_closures_publication', table_name='baseball_date_closures')
    op.drop_index('ix_baseball_date_closures_reopened', table_name='baseball_date_closures')
    op.drop_index('ix_baseball_date_closures_status_date', table_name='baseball_date_closures')
    op.drop_table('baseball_date_closures')
