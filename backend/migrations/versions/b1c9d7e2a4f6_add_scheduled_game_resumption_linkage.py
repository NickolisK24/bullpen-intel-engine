"""add scheduled game resumption linkage

Revision ID: b1c9d7e2a4f6
Revises: c2f6a9d8e4b1
Create Date: 2026-07-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b1c9d7e2a4f6'
down_revision = 'c2f6a9d8e4b1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('scheduled_games', schema=None) as batch_op:
        batch_op.add_column(sa.Column('original_game_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('original_product_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('resumed_game_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('resumed_product_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('resumed_from_game_pk', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('resumed_to_game_pk', sa.Integer(), nullable=True))
        batch_op.create_index(
            'ix_scheduled_games_resumed_from_game_pk',
            ['resumed_from_game_pk'],
            unique=False,
        )
        batch_op.create_index(
            'ix_scheduled_games_resumed_to_game_pk',
            ['resumed_to_game_pk'],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table('scheduled_games', schema=None) as batch_op:
        batch_op.drop_index('ix_scheduled_games_resumed_to_game_pk')
        batch_op.drop_index('ix_scheduled_games_resumed_from_game_pk')
        batch_op.drop_column('resumed_to_game_pk')
        batch_op.drop_column('resumed_from_game_pk')
        batch_op.drop_column('resumed_product_date')
        batch_op.drop_column('resumed_game_date')
        batch_op.drop_column('original_product_date')
        batch_op.drop_column('original_game_date')
