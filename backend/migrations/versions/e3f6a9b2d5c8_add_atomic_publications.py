"""add atomic publication generations

Revision ID: e3f6a9b2d5c8
Revises: d2e5f8a1c4b7
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa


revision = 'e3f6a9b2d5c8'
down_revision = 'd2e5f8a1c4b7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'atomic_publications',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('publication_fingerprint', sa.String(64), nullable=False),
        sa.Column('schema_version', sa.String(40), nullable=False),
        sa.Column('predecessor_publication_id', sa.Integer()),
        sa.Column('cohort_id', sa.Integer(), nullable=False),
        sa.Column('impact_plan_id', sa.Integer(), nullable=False),
        sa.Column('baseball_date', sa.Date(), nullable=False),
        sa.Column('authority_class', sa.String(30), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('completeness', sa.String(20), nullable=False),
        sa.Column('source_data_through', sa.DateTime(), nullable=False),
        sa.Column('affected_game_ids_json', sa.JSON(), nullable=False),
        sa.Column('affected_team_ids_json', sa.JSON(), nullable=False),
        sa.Column('affected_pitcher_ids_json', sa.JSON(), nullable=False),
        sa.Column('completed_domains_json', sa.JSON(), nullable=False),
        sa.Column('withheld_domains_json', sa.JSON(), nullable=False),
        sa.Column('method_versions_json', sa.JSON(), nullable=False),
        sa.Column('input_manifest_fingerprint', sa.String(64), nullable=False),
        sa.Column('correlation_id', sa.String(64)),
        sa.Column('sync_run_id', sa.Integer()),
        sa.Column('artifact_created_count', sa.Integer(), nullable=False),
        sa.Column('artifact_inherited_count', sa.Integer(), nullable=False),
        sa.Column('preparation_duration_ms', sa.Integer()),
        sa.Column('pointer_switch_duration_ms', sa.Integer()),
        sa.Column('validation_failure_reason', sa.String(200)),
        sa.Column('published_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['predecessor_publication_id'], ['atomic_publications.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['cohort_id'], ['derived_intelligence_cohorts.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['impact_plan_id'], ['canonical_impact_plans.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('publication_fingerprint', name='uq_atomic_publication_fingerprint'),
        sa.UniqueConstraint('cohort_id', name='uq_atomic_publication_cohort'),
        sa.CheckConstraint(
            "status IN ('preparing', 'ready', 'published', 'failed', 'superseded')",
            name='ck_atomic_publication_status',
        ),
        sa.CheckConstraint(
            "completeness IN ('complete', 'partial', 'withheld')",
            name='ck_atomic_publication_completeness',
        ),
    )
    op.create_index('ix_atomic_publications_date_status', 'atomic_publications', ['baseball_date', 'status'])
    op.create_index('ix_atomic_publications_authority_status', 'atomic_publications', ['authority_class', 'status'])
    op.create_index('ix_atomic_publications_correlation', 'atomic_publications', ['correlation_id', 'id'])

    op.create_table(
        'atomic_publication_artifacts',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('publication_id', sa.Integer(), nullable=False),
        sa.Column('artifact_type', sa.String(50), nullable=False),
        sa.Column('entity_type', sa.String(20), nullable=False),
        sa.Column('entity_key', sa.String(80), nullable=False),
        sa.Column('source_cohort_id', sa.Integer(), nullable=False),
        sa.Column('source_snapshot_id', sa.Integer()),
        sa.Column('inherited_from_artifact_id', sa.Integer()),
        sa.Column('schema_version', sa.String(40), nullable=False),
        sa.Column('payload_fingerprint', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['publication_id'], ['atomic_publications.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_cohort_id'], ['derived_intelligence_cohorts.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['source_snapshot_id'], ['derived_cohort_snapshots.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['inherited_from_artifact_id'], ['atomic_publication_artifacts.id'], ondelete='RESTRICT'),
        sa.UniqueConstraint('publication_id', 'artifact_type', 'entity_type', 'entity_key', name='uq_atomic_publication_artifact_key'),
        sa.CheckConstraint("entity_type IN ('pitcher', 'team', 'game', 'league')", name='ck_atomic_publication_artifact_entity_type'),
        sa.CheckConstraint('(source_snapshot_id IS NOT NULL) != (inherited_from_artifact_id IS NOT NULL)', name='ck_atomic_publication_artifact_one_source'),
    )
    op.create_index('ix_atomic_publication_artifact_lookup', 'atomic_publication_artifacts', ['publication_id', 'artifact_type', 'entity_type', 'entity_key'])
    op.create_index('ix_atomic_publication_artifact_entity_history', 'atomic_publication_artifacts', ['entity_type', 'entity_key', 'publication_id'])

    op.create_table(
        'atomic_publication_current',
        sa.Column('singleton_id', sa.Integer(), primary_key=True),
        sa.Column('publication_id', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['publication_id'], ['atomic_publications.id'], ondelete='RESTRICT'),
        sa.UniqueConstraint('publication_id'),
        sa.CheckConstraint('singleton_id = 1', name='ck_atomic_publication_current_singleton'),
    )

    op.create_table(
        'atomic_publication_cache_handoffs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('publication_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('cache_keys_json', sa.JSON(), nullable=False),
        sa.Column('attempt_count', sa.Integer(), nullable=False),
        sa.Column('last_error_class', sa.String(120)),
        sa.Column('last_error', sa.Text()),
        sa.Column('completed_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['publication_id'], ['atomic_publications.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('publication_id', name='uq_atomic_publication_cache_handoff'),
        sa.CheckConstraint("status IN ('pending', 'complete', 'retry_wait', 'not_configured')", name='ck_atomic_publication_cache_handoff_status'),
    )
    op.create_index('ix_atomic_publication_cache_handoff_status', 'atomic_publication_cache_handoffs', ['status', 'updated_at'])


def downgrade():
    op.drop_index('ix_atomic_publication_cache_handoff_status', table_name='atomic_publication_cache_handoffs')
    op.drop_table('atomic_publication_cache_handoffs')
    op.drop_table('atomic_publication_current')
    op.drop_index('ix_atomic_publication_artifact_entity_history', table_name='atomic_publication_artifacts')
    op.drop_index('ix_atomic_publication_artifact_lookup', table_name='atomic_publication_artifacts')
    op.drop_table('atomic_publication_artifacts')
    op.drop_index('ix_atomic_publications_correlation', table_name='atomic_publications')
    op.drop_index('ix_atomic_publications_authority_status', table_name='atomic_publications')
    op.drop_index('ix_atomic_publications_date_status', table_name='atomic_publications')
    op.drop_table('atomic_publications')
