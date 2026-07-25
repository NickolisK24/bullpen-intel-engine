"""add team progressive publications

Creates the immutable team-scoped source-authority checkpoint used by progressive
Team State Share Artifact publication. An individual Team State artifact may publish
after that team's own completed game and required evidence pass the canonical trust
gates, without waiting for the entire league slate to be final. This checkpoint IS
that team-scoped trusted source (it supplies the artifact's non-null
source_snapshot_id, which has no FK to dashboard_snapshots). The league
dashboard_snapshots table and its all-or-nothing gates are unchanged.

Revision ID: b3d9f1a7c2e5
Revises: e2b8d5a3c9f1
Create Date: 2026-07-25
"""

from alembic import op
import sqlalchemy as sa


revision = 'b3d9f1a7c2e5'
down_revision = 'e2b8d5a3c9f1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'team_progressive_publications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('trigger_type', sa.String(length=40), nullable=False),
        sa.Column('trigger_game_pk', sa.Integer(), nullable=True),
        sa.Column('official_game_date', sa.Date(), nullable=True),
        sa.Column('data_through', sa.Date(), nullable=False),
        sa.Column('availability_reference_date', sa.Date(), nullable=True),
        sa.Column('source_sync_run_id', sa.Integer(), nullable=True),
        sa.Column('game_final', sa.Boolean(), nullable=False),
        sa.Column('ledger_complete', sa.Boolean(), nullable=False),
        sa.Column('evidence_complete', sa.Boolean(), nullable=False),
        sa.Column('trusted', sa.Boolean(), nullable=False),
        sa.Column('unavailable_reason', sa.String(length=80), nullable=True),
        sa.Column('evidence_revision', sa.String(length=80), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('trusted', 'withheld')",
            name='ck_team_progressive_status',
        ),
        # DB-enforced idempotency: one checkpoint per (team, triggering game,
        # evidence revision). Prevents duplicate checkpoints (and duplicate
        # artifacts) under a concurrent postgame race on the same final game.
        sa.UniqueConstraint(
            'team_id', 'trigger_game_pk', 'evidence_revision',
            name='uq_team_progressive_team_game_revision',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('team_progressive_publications', schema=None) as batch_op:
        batch_op.create_index('ix_team_progressive_team', ['team_id'], unique=False)
        batch_op.create_index('ix_team_progressive_game', ['trigger_game_pk'], unique=False)
        batch_op.create_index(
            'ix_team_progressive_team_game', ['team_id', 'trigger_game_pk'], unique=False,
        )
        batch_op.create_index('ix_team_progressive_created', ['created_at'], unique=False)


def downgrade():
    with op.batch_alter_table('team_progressive_publications', schema=None) as batch_op:
        batch_op.drop_index('ix_team_progressive_created')
        batch_op.drop_index('ix_team_progressive_team_game')
        batch_op.drop_index('ix_team_progressive_game')
        batch_op.drop_index('ix_team_progressive_team')
        batch_op.drop_constraint('uq_team_progressive_team_game_revision', type_='unique')
    op.drop_table('team_progressive_publications')
