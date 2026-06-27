"""add scheduled games

Revision ID: c5b1e9a2f7d4
Revises: a7f2c1d4e9b6
Create Date: 2026-06-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c5b1e9a2f7d4'
down_revision = 'a7f2c1d4e9b6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'scheduled_games',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('game_pk', sa.Integer(), nullable=False),
        sa.Column('game_date', sa.Date(), nullable=False),
        sa.Column('game_datetime', sa.DateTime(), nullable=True),
        sa.Column('opponent_team_id', sa.Integer(), nullable=True),
        sa.Column('home_away', sa.String(length=10), nullable=True),
        sa.Column('game_type', sa.String(length=2), nullable=True),
        sa.Column('status_code', sa.String(length=10), nullable=True),
        sa.Column('status_state', sa.String(length=20), nullable=False),
        sa.Column('doubleheader', sa.String(length=2), nullable=True),
        sa.Column('game_number', sa.Integer(), nullable=True),
        sa.Column('series_game_number', sa.Integer(), nullable=True),
        sa.Column('games_in_series', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(length=40), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_id', 'game_pk',
                            name='uq_scheduled_games_team_game'),
    )
    with op.batch_alter_table('scheduled_games', schema=None) as batch_op:
        batch_op.create_index('ix_scheduled_games_team_date',
                              ['team_id', 'game_date'], unique=False)
        batch_op.create_index('ix_scheduled_games_game_date',
                              ['game_date'], unique=False)
        batch_op.create_index('ix_scheduled_games_status_state',
                              ['status_state'], unique=False)


def downgrade():
    with op.batch_alter_table('scheduled_games', schema=None) as batch_op:
        batch_op.drop_index('ix_scheduled_games_status_state')
        batch_op.drop_index('ix_scheduled_games_game_date')
        batch_op.drop_index('ix_scheduled_games_team_date')
    op.drop_table('scheduled_games')
