"""add game_log games_started (role authority v1)

Captures the authoritative MLB ``gamesStarted`` signal per appearance so bullpen
role can be derived from real starts instead of innings-pitched heuristics.

Additive, nullable, migration-safe, and backfillable. Existing rows remain valid
(null = start unknown); no existing columns are removed.

Revision ID: b7e2a1c4f8d3
Revises: a83d4f6b9c21
Create Date: 2026-06-09 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7e2a1c4f8d3'
down_revision = 'a83d4f6b9c21'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('game_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('games_started', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('game_logs', schema=None) as batch_op:
        batch_op.drop_column('games_started')
