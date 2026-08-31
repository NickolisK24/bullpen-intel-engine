"""add durable Team State publication proofs

Revision ID: d5a8c2f7e1b4
Revises: c6d8e1f3a5b7
Create Date: 2026-08-31 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'd5a8c2f7e1b4'
down_revision = 'c6d8e1f3a5b7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'team_state_publication_proofs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('snapshot_id', sa.Integer(), nullable=False),
        sa.Column('sync_run_id', sa.Integer(), nullable=True),
        sa.Column('data_through', sa.Date(), nullable=False),
        sa.Column('proof', sa.JSON(), nullable=False),
        sa.Column('overall_verdict', sa.String(length=32), nullable=False),
        sa.Column('captured_team_count', sa.Integer(), nullable=False),
        sa.Column('method_version', sa.String(length=64), nullable=True),
        sa.Column('publication_source', sa.String(length=120), nullable=True),
        sa.Column('generated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "overall_verdict IN ('PASS', 'PASS_WITH_INCONCLUSIVE', 'FAIL')",
            name='ck_team_state_proof_verdict',
        ),
        sa.ForeignKeyConstraint(['snapshot_id'], ['dashboard_snapshots.id']),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('snapshot_id', name='uq_team_state_proof_snapshot'),
    )
    op.create_index('ix_team_state_proof_sync_run', 'team_state_publication_proofs', ['sync_run_id'])
    op.create_index('ix_team_state_proof_generated_at', 'team_state_publication_proofs', ['generated_at'])


def downgrade():
    op.drop_index('ix_team_state_proof_generated_at', table_name='team_state_publication_proofs')
    op.drop_index('ix_team_state_proof_sync_run', table_name='team_state_publication_proofs')
    op.drop_table('team_state_publication_proofs')
