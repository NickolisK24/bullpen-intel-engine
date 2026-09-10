"""add game log innings outs

Revision ID: 0f7a2c9d8e61
Revises: f4c2b8a9d1e3
Create Date: 2026-06-15 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0f7a2c9d8e61'
down_revision = 'f4c2b8a9d1e3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('game_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('innings_pitched_outs', sa.Integer(), nullable=True))
        batch_op.create_check_constraint(
            'ck_game_logs_innings_pitched_outs_nonnegative',
            'innings_pitched_outs IS NULL OR innings_pitched_outs >= 0',
        )


def downgrade():
    with op.batch_alter_table('game_logs', schema=None) as batch_op:
        batch_op.drop_constraint(
            'ck_game_logs_innings_pitched_outs_nonnegative',
            type_='check',
        )
        batch_op.drop_column('innings_pitched_outs')
