"""add derived intelligence cohorts

Revision ID: d2e5f8a1c4b7
Revises: c1d4e7a9b2f6
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa


revision = 'd2e5f8a1c4b7'
down_revision = 'c1d4e7a9b2f6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'derived_intelligence_cohorts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('impact_plan_id', sa.Integer(), nullable=False),
        sa.Column('cohort_fingerprint', sa.String(64), nullable=False),
        sa.Column('schema_version', sa.String(40), nullable=False),
        sa.Column('authority_class', sa.String(30), nullable=False),
        sa.Column('baseball_date', sa.Date(), nullable=False),
        sa.Column('correlation_id', sa.String(64)),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('requested_domains_json', sa.JSON(), nullable=False),
        sa.Column('execution_domains_json', sa.JSON(), nullable=False),
        sa.Column('completed_domains_json', sa.JSON(), nullable=False),
        sa.Column('withheld_domains_json', sa.JSON(), nullable=False),
        sa.Column('affected_game_ids_json', sa.JSON(), nullable=False),
        sa.Column('affected_team_ids_json', sa.JSON(), nullable=False),
        sa.Column('affected_pitcher_ids_json', sa.JSON(), nullable=False),
        sa.Column('input_manifest_json', sa.JSON(), nullable=False),
        sa.Column('method_versions_json', sa.JSON(), nullable=False),
        sa.Column('predecessor_cohort_id', sa.Integer()),
        sa.Column('supersedes_cohort_id', sa.Integer()),
        sa.Column('sync_run_id', sa.Integer()),
        sa.Column('publication_job_id', sa.Integer()),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['impact_plan_id'], ['canonical_impact_plans.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['predecessor_cohort_id'], ['derived_intelligence_cohorts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['supersedes_cohort_id'], ['derived_intelligence_cohorts.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['publication_job_id'], ['sync_jobs.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('cohort_fingerprint', name='uq_derived_cohorts_fingerprint'),
        sa.CheckConstraint(
            "status IN ('running', 'complete', 'partial', 'stale', 'failed', 'superseded')",
            name='ck_derived_cohorts_status',
        ),
    )
    op.create_index('ix_derived_cohorts_date_status', 'derived_intelligence_cohorts', ['baseball_date', 'status'])
    op.create_index('ix_derived_cohorts_authority_status', 'derived_intelligence_cohorts', ['authority_class', 'status'])
    op.create_index('ix_derived_cohorts_correlation', 'derived_intelligence_cohorts', ['correlation_id', 'id'])

    op.create_table(
        'derived_intelligence_cohort_domains',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cohort_id', sa.Integer(), nullable=False),
        sa.Column('domain', sa.String(40), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('prerequisite', sa.Boolean(), nullable=False),
        sa.Column('method_version', sa.String(80)),
        sa.Column('result_summary_json', sa.JSON()),
        sa.Column('error_class', sa.String(120)),
        sa.Column('error_message', sa.Text()),
        sa.Column('started_at', sa.DateTime()),
        sa.Column('completed_at', sa.DateTime()),
        sa.ForeignKeyConstraint(['cohort_id'], ['derived_intelligence_cohorts.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('cohort_id', 'domain', name='uq_derived_cohort_domain'),
        sa.CheckConstraint(
            "status IN ('requested', 'prerequisite', 'succeeded', 'withheld', 'failed', 'skipped', 'stale')",
            name='ck_derived_cohort_domains_status',
        ),
    )
    op.create_index('ix_derived_cohort_domains_status', 'derived_intelligence_cohort_domains', ['status', 'domain'])

    op.create_table(
        'derived_cohort_inputs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cohort_id', sa.Integer(), nullable=False),
        sa.Column('input_type', sa.String(40), nullable=False),
        sa.Column('input_key', sa.String(160), nullable=False),
        sa.Column('input_version', sa.String(160), nullable=False),
        sa.Column('input_fingerprint', sa.String(64)),
        sa.Column('authority_class', sa.String(30), nullable=False),
        sa.Column('source_observation_id', sa.Integer()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['cohort_id'], ['derived_intelligence_cohorts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_observation_id'], ['source_observations.id'], ondelete='RESTRICT'),
        sa.UniqueConstraint('cohort_id', 'input_type', 'input_key', 'input_version', name='uq_derived_cohort_input'),
    )
    op.create_index('ix_derived_cohort_inputs_lookup', 'derived_cohort_inputs', ['input_type', 'input_key'])
    op.create_index('ix_derived_cohort_inputs_observation', 'derived_cohort_inputs', ['source_observation_id'])

    op.create_table(
        'derived_cohort_snapshots',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('cohort_id', sa.Integer(), nullable=False),
        sa.Column('entity_type', sa.String(20), nullable=False),
        sa.Column('entity_key', sa.String(80), nullable=False),
        sa.Column('snapshot_type', sa.String(40), nullable=False),
        sa.Column('baseball_date', sa.Date(), nullable=False),
        sa.Column('authority_class', sa.String(30), nullable=False),
        sa.Column('payload_schema_version', sa.Integer(), nullable=False),
        sa.Column('payload_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['cohort_id'], ['derived_intelligence_cohorts.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('cohort_id', 'entity_type', 'entity_key', 'snapshot_type', name='uq_derived_cohort_snapshot'),
        sa.CheckConstraint("entity_type IN ('pitcher', 'team', 'game')", name='ck_derived_cohort_snapshots_entity_type'),
    )
    op.create_index('ix_derived_cohort_snapshots_entity', 'derived_cohort_snapshots', ['entity_type', 'entity_key', 'baseball_date'])


def downgrade():
    op.drop_index('ix_derived_cohort_snapshots_entity', table_name='derived_cohort_snapshots')
    op.drop_table('derived_cohort_snapshots')
    op.drop_index('ix_derived_cohort_inputs_observation', table_name='derived_cohort_inputs')
    op.drop_index('ix_derived_cohort_inputs_lookup', table_name='derived_cohort_inputs')
    op.drop_table('derived_cohort_inputs')
    op.drop_index('ix_derived_cohort_domains_status', table_name='derived_intelligence_cohort_domains')
    op.drop_table('derived_intelligence_cohort_domains')
    op.drop_index('ix_derived_cohorts_correlation', table_name='derived_intelligence_cohorts')
    op.drop_index('ix_derived_cohorts_authority_status', table_name='derived_intelligence_cohorts')
    op.drop_index('ix_derived_cohorts_date_status', table_name='derived_intelligence_cohorts')
    op.drop_table('derived_intelligence_cohorts')
