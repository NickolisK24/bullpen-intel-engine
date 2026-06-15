"""add games_started check constraint

Revision ID: 91c4a77f2d9b
Revises: 0f7a2c9d8e61
Create Date: 2026-06-15 00:00:00.000000
"""

from alembic import op


revision = '91c4a77f2d9b'
down_revision = '0f7a2c9d8e61'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('game_logs') as batch_op:
        batch_op.create_check_constraint(
            'ck_game_logs_games_started_valid',
            'games_started IS NULL OR games_started IN (0, 1)',
        )


def downgrade():
    with op.batch_alter_table('game_logs') as batch_op:
        batch_op.drop_constraint(
            'ck_game_logs_games_started_valid',
            type_='check',
        )
