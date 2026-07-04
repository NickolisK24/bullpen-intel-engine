"""add unknown safe boxscore fields

Revision ID: d6b8f3a1c9e7
Revises: b1c9d7e2a4f6
Create Date: 2026-07-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'd6b8f3a1c9e7'
down_revision = 'b1c9d7e2a4f6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('game_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('batters_faced', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('balls', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('games_finished', sa.Integer(), nullable=True))
        batch_op.alter_column(
            'inherited_runners',
            existing_type=sa.Integer(),
            nullable=True,
            server_default=None,
            existing_nullable=True,
        )
        batch_op.alter_column(
            'inherited_runners_scored',
            existing_type=sa.Integer(),
            nullable=True,
            server_default=None,
            existing_nullable=True,
        )

    op.execute(sa.text('UPDATE game_logs SET inherited_runners = NULL WHERE inherited_runners = 0'))
    op.execute(sa.text(
        'UPDATE game_logs '
        'SET inherited_runners_scored = NULL '
        'WHERE inherited_runners_scored = 0'
    ))


def downgrade():
    op.execute(sa.text('UPDATE game_logs SET inherited_runners = 0 WHERE inherited_runners IS NULL'))
    op.execute(sa.text(
        'UPDATE game_logs '
        'SET inherited_runners_scored = 0 '
        'WHERE inherited_runners_scored IS NULL'
    ))
    with op.batch_alter_table('game_logs', schema=None) as batch_op:
        batch_op.alter_column(
            'inherited_runners_scored',
            existing_type=sa.Integer(),
            nullable=True,
            server_default=sa.text('0'),
            existing_nullable=True,
        )
        batch_op.alter_column(
            'inherited_runners',
            existing_type=sa.Integer(),
            nullable=True,
            server_default=sa.text('0'),
            existing_nullable=True,
        )
        batch_op.drop_column('games_finished')
        batch_op.drop_column('balls')
        batch_op.drop_column('batters_faced')
