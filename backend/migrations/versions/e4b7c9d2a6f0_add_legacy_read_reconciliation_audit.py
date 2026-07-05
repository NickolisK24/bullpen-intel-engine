"""add legacy read reconciliation audit

Revision ID: e4b7c9d2a6f0
Revises: a9d4e7c2f6b1
Create Date: 2026-07-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'e4b7c9d2a6f0'
down_revision = 'a9d4e7c2f6b1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'legacy_read_divergences',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('subject_type', sa.String(length=40), nullable=False),
        sa.Column('subject_id', sa.String(length=80), nullable=False),
        sa.Column('product_date', sa.Date(), nullable=False),
        sa.Column('category', sa.String(length=80), nullable=False),
        sa.Column('is_material', sa.Boolean(), nullable=False, server_default='0'),
        sa.Column('escalation_state', sa.String(length=40), nullable=False),
        sa.Column('legacy_capture', sa.JSON(), nullable=False),
        sa.Column('read_capture', sa.JSON(), nullable=False),
        sa.Column('comparison_basis', sa.String(length=200), nullable=False),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('source', sa.String(length=100), nullable=False),
        sa.Column('sync_run_id', sa.Integer(), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(), nullable=False),
        sa.Column('last_corrected_at', sa.DateTime(), nullable=True),
        sa.Column('correction_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('correction_source', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "subject_type IN ('pitcher_day', 'team_day')",
            name='ck_legacy_read_divergences_subject_type',
        ),
        sa.CheckConstraint(
            "escalation_state IN ('recorded', 'escalation_recommended')",
            name='ck_legacy_read_divergences_escalation_state',
        ),
        sa.CheckConstraint(
            "category IN ("
            "'legacy_label_present_read_missing',"
            "'read_present_legacy_label_missing',"
            "'legacy_actionable_label_on_degraded_read',"
            "'legacy_confident_on_stale_inputs',"
            "'legacy_state_contradicts_stored_fact',"
            "'legacy_team_aggregate_on_degraded_team_read',"
            "'legacy_team_count_contradicts_composition'"
            ")",
            name='ck_legacy_read_divergences_category',
        ),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'subject_type',
            'subject_id',
            'product_date',
            'category',
            name='uq_legacy_read_divergences_subject_date_category',
        ),
    )
    op.create_index(
        'ix_legacy_read_divergences_category',
        'legacy_read_divergences',
        ['category', 'product_date'],
        unique=False,
    )
    op.create_index(
        'ix_legacy_read_divergences_subject_date',
        'legacy_read_divergences',
        ['subject_type', 'product_date'],
        unique=False,
    )

    op.create_table(
        'legacy_read_audit_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('product_date', sa.Date(), nullable=False),
        sa.Column('subject_type', sa.String(length=40), nullable=False),
        sa.Column('subjects_compared', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('aligned_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('divergence_count_by_category', sa.JSON(), nullable=False),
        sa.Column('skipped_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('run_status', sa.String(length=40), nullable=False),
        sa.Column('structural_findings', sa.JSON(), nullable=False),
        sa.Column('source', sa.String(length=100), nullable=False),
        sa.Column('sync_run_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "subject_type IN ('pitcher_day', 'team_day')",
            name='ck_legacy_read_audit_runs_subject_type',
        ),
        sa.CheckConstraint(
            "run_status IN ('completed', 'skipped_reads_missing', 'skipped_legacy_missing')",
            name='ck_legacy_read_audit_runs_status',
        ),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'product_date',
            'subject_type',
            name='uq_legacy_read_audit_runs_date_subject',
        ),
    )
    op.create_index(
        'ix_legacy_read_audit_runs_date',
        'legacy_read_audit_runs',
        ['product_date'],
        unique=False,
    )


def downgrade():
    op.drop_index(
        'ix_legacy_read_audit_runs_date',
        table_name='legacy_read_audit_runs',
    )
    op.drop_table('legacy_read_audit_runs')
    op.drop_index(
        'ix_legacy_read_divergences_subject_date',
        table_name='legacy_read_divergences',
    )
    op.drop_index(
        'ix_legacy_read_divergences_category',
        table_name='legacy_read_divergences',
    )
    op.drop_table('legacy_read_divergences')
