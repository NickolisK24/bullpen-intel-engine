"""add SP-14 sync certification evidence

Revision ID: c9d4e6f8a1b2
Revises: b7d3e9f1a5c2
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa


revision = 'c9d4e6f8a1b2'
down_revision = 'b7d3e9f1a5c2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'sync_certification_runs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('certification_key', sa.String(64), nullable=False),
        sa.Column('certification_version', sa.String(50), nullable=False),
        sa.Column('integration_commit_sha', sa.String(40), nullable=False),
        sa.Column('migration_head', sa.String(32), nullable=False),
        sa.Column('environment', sa.String(30), nullable=False),
        sa.Column('configuration_fingerprint', sa.String(64), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('verdict', sa.String(10)),
        sa.Column('gate_statuses_json', sa.JSON(), nullable=False),
        sa.Column('natural_proof_identifiers_json', sa.JSON(), nullable=False),
        sa.Column('production_identifiers_json', sa.JSON(), nullable=False),
        sa.Column('failures_json', sa.JSON(), nullable=False),
        sa.Column('warnings_json', sa.JSON(), nullable=False),
        sa.Column('sync_run_id', sa.Integer()),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('certification_key', name='uq_sync_certification_runs_key'),
        sa.CheckConstraint(
            "status IN ('pending', 'passing', 'failed', 'blocked', 'certified')",
            name='ck_sync_certification_runs_status',
        ),
        sa.CheckConstraint(
            "verdict IN ('GO', 'NO-GO') OR verdict IS NULL",
            name='ck_sync_certification_runs_verdict',
        ),
    )
    op.create_index('ix_sync_certification_runs_environment_created', 'sync_certification_runs', ['environment', 'created_at'])
    op.create_index('ix_sync_certification_runs_status_created', 'sync_certification_runs', ['status', 'created_at'])
    op.create_index('ix_sync_certification_runs_commit', 'sync_certification_runs', ['integration_commit_sha'])

    op.create_table(
        'sync_certification_checks',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('certification_run_id', sa.Integer(), nullable=False),
        sa.Column('gate_key', sa.String(10), nullable=False),
        sa.Column('check_key', sa.String(80), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('critical', sa.Boolean(), nullable=False),
        sa.Column('summary', sa.String(240), nullable=False),
        sa.Column('evidence_json', sa.JSON(), nullable=False),
        sa.Column('measured_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['certification_run_id'], ['sync_certification_runs.id'], ondelete='CASCADE'),
        sa.UniqueConstraint(
            'certification_run_id', 'gate_key', 'check_key',
            name='uq_sync_certification_checks_run_gate_check',
        ),
        sa.CheckConstraint(
            "status IN ('passing', 'failed', 'blocked', 'warning', 'not_run')",
            name='ck_sync_certification_checks_status',
        ),
    )
    op.create_index('ix_sync_certification_checks_gate_status', 'sync_certification_checks', ['gate_key', 'status'])
    op.create_index('ix_sync_certification_checks_run', 'sync_certification_checks', ['certification_run_id', 'gate_key'])

    op.create_table(
        'sync_legacy_transition_states',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('responsibility_key', sa.String(80), nullable=False),
        sa.Column('responsibility', sa.String(160), nullable=False),
        sa.Column('legacy_owner', sa.String(160), nullable=False),
        sa.Column('new_owner', sa.String(40), nullable=False),
        sa.Column('current_production_authority', sa.String(160), nullable=False),
        sa.Column('new_pipeline_readiness', sa.String(30), nullable=False),
        sa.Column('required_proof', sa.Text(), nullable=False),
        sa.Column('retirement_condition', sa.Text(), nullable=False),
        sa.Column('planned_transition_action', sa.Text(), nullable=False),
        sa.Column('rollback_path', sa.Text(), nullable=False),
        sa.Column('retirement_type', sa.String(30), nullable=False),
        sa.Column('evidence_json', sa.JSON(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('responsibility_key', name='uq_sync_legacy_transition_responsibility'),
        sa.CheckConstraint(
            "retirement_type IN ('RETAIN_AS_PRIMARY', 'RETAIN_AS_FALLBACK', "
            "'RETAIN_AS_VERIFIER', 'DISABLE', 'DELETE', 'DEFER_RETIREMENT')",
            name='ck_sync_legacy_transition_retirement_type',
        ),
    )
    op.create_index('ix_sync_legacy_transition_retirement', 'sync_legacy_transition_states', ['retirement_type', 'updated_at'])
    op.create_index('ix_sync_legacy_transition_new_owner', 'sync_legacy_transition_states', ['new_owner'])


def downgrade():
    op.drop_index('ix_sync_legacy_transition_new_owner', table_name='sync_legacy_transition_states')
    op.drop_index('ix_sync_legacy_transition_retirement', table_name='sync_legacy_transition_states')
    op.drop_table('sync_legacy_transition_states')
    op.drop_index('ix_sync_certification_checks_run', table_name='sync_certification_checks')
    op.drop_index('ix_sync_certification_checks_gate_status', table_name='sync_certification_checks')
    op.drop_table('sync_certification_checks')
    op.drop_index('ix_sync_certification_runs_commit', table_name='sync_certification_runs')
    op.drop_index('ix_sync_certification_runs_status_created', table_name='sync_certification_runs')
    op.drop_index('ix_sync_certification_runs_environment_created', table_name='sync_certification_runs')
    op.drop_table('sync_certification_runs')
