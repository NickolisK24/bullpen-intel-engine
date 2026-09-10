"""add canonical impact plans

Revision ID: c1d4e7a9b2f6
Revises: f9c2a7e4b1d6
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa


revision = 'c1d4e7a9b2f6'
down_revision = 'f9c2a7e4b1d6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'canonical_impact_plans',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('plan_fingerprint', sa.String(64), nullable=False),
        sa.Column('rules_version', sa.String(40), nullable=False),
        sa.Column('authority_class', sa.String(30), nullable=False),
        sa.Column('baseball_date', sa.Date(), nullable=False),
        sa.Column('correlation_id', sa.String(64)),
        sa.Column('affected_game_ids_json', sa.JSON(), nullable=False),
        sa.Column('affected_team_ids_json', sa.JSON(), nullable=False),
        sa.Column('affected_pitcher_ids_json', sa.JSON(), nullable=False),
        sa.Column('affected_domains_json', sa.JSON(), nullable=False),
        sa.Column('source_observation_ids_json', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('supersedes_live', sa.Boolean(), nullable=False),
        sa.Column('supersedes_plan_id', sa.Integer()),
        sa.Column('sync_run_id', sa.Integer()),
        sa.Column('dispatched_job_id', sa.Integer()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('dispatched_at', sa.DateTime()),
        sa.ForeignKeyConstraint(
            ['supersedes_plan_id'], ['canonical_impact_plans.id'], ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['dispatched_job_id'], ['sync_jobs.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('plan_fingerprint', name='uq_canonical_impact_plans_fingerprint'),
        sa.CheckConstraint(
            "authority_class IN ('live', 'final', 'corrected_final', "
            "'roster_authoritative', 'pregame_authoritative')",
            name='ck_canonical_impact_plans_authority',
        ),
        sa.CheckConstraint(
            "status IN ('planned', 'dispatched', 'superseded')",
            name='ck_canonical_impact_plans_status',
        ),
    )
    op.create_index('ix_canonical_impact_plans_date', 'canonical_impact_plans', ['baseball_date', 'id'])
    op.create_index('ix_canonical_impact_plans_authority', 'canonical_impact_plans', ['authority_class', 'id'])
    op.create_index('ix_canonical_impact_plans_correlation', 'canonical_impact_plans', ['correlation_id', 'id'])
    op.create_index('ix_canonical_impact_plans_sync_run', 'canonical_impact_plans', ['sync_run_id', 'id'])

    op.create_table(
        'canonical_impact_plan_mutations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('impact_plan_id', sa.Integer(), nullable=False),
        sa.Column('mutation_family', sa.String(40), nullable=False),
        sa.Column('source_mutation_id', sa.Integer(), nullable=False),
        sa.Column('source_mutation_type', sa.String(60), nullable=False),
        sa.Column('authority_class', sa.String(30), nullable=False),
        sa.Column('game_pk', sa.Integer()),
        sa.Column('team_id', sa.Integer()),
        sa.Column('pitcher_id', sa.Integer()),
        sa.Column('baseball_date', sa.Date(), nullable=False),
        sa.Column('source_observation_id', sa.Integer()),
        sa.Column('old_fact_identity', sa.String(160)),
        sa.Column('new_fact_identity', sa.String(160)),
        sa.Column('is_correction', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['impact_plan_id'], ['canonical_impact_plans.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['pitcher_id'], ['pitchers.id']),
        sa.ForeignKeyConstraint(['source_observation_id'], ['source_observations.id'], ondelete='RESTRICT'),
        sa.UniqueConstraint(
            'impact_plan_id', 'mutation_family', 'source_mutation_id',
            name='uq_canonical_impact_plan_mutation_ref',
        ),
    )
    op.create_index(
        'ix_canonical_impact_plan_mutations_source',
        'canonical_impact_plan_mutations', ['mutation_family', 'source_mutation_id'],
    )
    op.create_index(
        'ix_canonical_impact_plan_mutations_observation',
        'canonical_impact_plan_mutations', ['source_observation_id'],
    )

    op.create_table(
        'canonical_impact_plan_entities',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('impact_plan_id', sa.Integer(), nullable=False),
        sa.Column('entity_type', sa.String(20), nullable=False),
        sa.Column('entity_key', sa.String(80), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['impact_plan_id'], ['canonical_impact_plans.id'], ondelete='CASCADE'),
        sa.UniqueConstraint(
            'impact_plan_id', 'entity_type', 'entity_key',
            name='uq_canonical_impact_plan_entity',
        ),
        sa.CheckConstraint(
            "entity_type IN ('game', 'team', 'pitcher')",
            name='ck_canonical_impact_plan_entities_type',
        ),
    )
    op.create_index(
        'ix_canonical_impact_plan_entities_lookup',
        'canonical_impact_plan_entities', ['entity_type', 'entity_key', 'impact_plan_id'],
    )


def downgrade():
    op.drop_index('ix_canonical_impact_plan_entities_lookup', table_name='canonical_impact_plan_entities')
    op.drop_table('canonical_impact_plan_entities')
    op.drop_index('ix_canonical_impact_plan_mutations_observation', table_name='canonical_impact_plan_mutations')
    op.drop_index('ix_canonical_impact_plan_mutations_source', table_name='canonical_impact_plan_mutations')
    op.drop_table('canonical_impact_plan_mutations')
    op.drop_index('ix_canonical_impact_plans_sync_run', table_name='canonical_impact_plans')
    op.drop_index('ix_canonical_impact_plans_correlation', table_name='canonical_impact_plans')
    op.drop_index('ix_canonical_impact_plans_authority', table_name='canonical_impact_plans')
    op.drop_index('ix_canonical_impact_plans_date', table_name='canonical_impact_plans')
    op.drop_table('canonical_impact_plans')
