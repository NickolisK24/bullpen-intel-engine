"""add game log team-at-appearance authority

Foundation 1 of 6 (bullpen performance context). Adds the durable, correction-safe
team-at-appearance authority to game_logs: the MLB team a pitcher REPRESENTED in a
game, resolved from official game-side evidence and never from the pitcher's mutable
current Pitcher.team_id.

Purely additive and fail-open on read: the new columns are all nullable, historical
rows are intentionally NOT backfilled here (Step 2 owns the 2026 backfill), and no
existing row is modified. A NULL appearance_team_status reads as "unresolved" and is
excluded from future team-season aggregation. Indexes support that future
aggregation. One Alembic head is preserved; downgrade is independently reversible.

Revision ID: a4f1c7e9b3d2
Revises: b3d9f1a7c2e5
Create Date: 2026-07-26
"""

from alembic import op
import sqlalchemy as sa


revision = 'a4f1c7e9b3d2'
down_revision = 'b3d9f1a7c2e5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('game_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('appearance_team_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('appearance_team_source', sa.String(length=60), nullable=True))
        batch_op.add_column(sa.Column('appearance_team_status', sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column('appearance_team_reason', sa.String(length=80), nullable=True))
        batch_op.create_index(
            'ix_game_log_appearance_team_date',
            ['appearance_team_id', 'game_date'],
            unique=False,
        )
        batch_op.create_index(
            'ix_game_log_game_pk_appearance_team',
            ['mlb_game_pk', 'appearance_team_id'],
            unique=False,
        )
        # Stored-state invariant: valid status vocabulary AND a valid status<->team_id
        # combination. A resolved row must carry a team id; an unresolved/conflict row
        # and a legacy (NULL-status) row must carry none. Enforced at the database so a
        # conflict can never retain a silently-selected team.
        batch_op.create_check_constraint(
            'ck_game_logs_appearance_team_status',
            "(appearance_team_status IS NULL AND appearance_team_id IS NULL) OR "
            "(appearance_team_status = 'resolved' AND appearance_team_id IS NOT NULL) OR "
            "(appearance_team_status IN ('unresolved', 'conflict') "
            "AND appearance_team_id IS NULL)",
        )


def downgrade():
    with op.batch_alter_table('game_logs', schema=None) as batch_op:
        batch_op.drop_constraint('ck_game_logs_appearance_team_status', type_='check')
        batch_op.drop_index('ix_game_log_game_pk_appearance_team')
        batch_op.drop_index('ix_game_log_appearance_team_date')
        batch_op.drop_column('appearance_team_reason')
        batch_op.drop_column('appearance_team_status')
        batch_op.drop_column('appearance_team_source')
        batch_op.drop_column('appearance_team_id')
