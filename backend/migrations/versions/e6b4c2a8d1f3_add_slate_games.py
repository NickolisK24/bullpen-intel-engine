"""add slate games

Revision ID: e6b4c2a8d1f3
Revises: d7e4f1a8c2b6
Create Date: 2026-07-18
"""

from alembic import op
import sqlalchemy as sa


revision = 'e6b4c2a8d1f3'
down_revision = 'd7e4f1a8c2b6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'slate_games',
        sa.Column('game_pk', sa.Integer(), nullable=False),
        sa.Column('game_date_et', sa.Date(), nullable=False),
        sa.Column('game_time_utc', sa.DateTime(), nullable=False),
        sa.Column('home_team_id', sa.Integer(), nullable=False),
        sa.Column('away_team_id', sa.Integer(), nullable=False),
        sa.Column('status_abstract', sa.String(length=40), nullable=True),
        sa.Column('status_detailed', sa.String(length=80), nullable=True),
        sa.Column('status_code', sa.String(length=10), nullable=True),
        sa.Column('normalized_state', sa.String(length=20), nullable=False),
        sa.Column('doubleheader_flag', sa.String(length=2), nullable=True),
        sa.Column('game_number', sa.Integer(), nullable=True),
        sa.Column('scheduled_innings', sa.Integer(), nullable=True),
        sa.Column('last_synced', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('game_pk'),
    )
    with op.batch_alter_table('slate_games', schema=None) as batch_op:
        batch_op.create_index(
            'ix_slate_games_game_date_et', ['game_date_et'], unique=False
        )
        batch_op.create_index(
            'ix_slate_games_normalized_state', ['normalized_state'], unique=False
        )
        batch_op.create_index(
            'ix_slate_games_home_team_date',
            ['home_team_id', 'game_date_et'],
            unique=False,
        )
        batch_op.create_index(
            'ix_slate_games_away_team_date',
            ['away_team_id', 'game_date_et'],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table('slate_games', schema=None) as batch_op:
        batch_op.drop_index('ix_slate_games_away_team_date')
        batch_op.drop_index('ix_slate_games_home_team_date')
        batch_op.drop_index('ix_slate_games_normalized_state')
        batch_op.drop_index('ix_slate_games_game_date_et')
    op.drop_table('slate_games')
