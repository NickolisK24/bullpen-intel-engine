"""add postgame processed games

Revision ID: a6d4e9c2f1b8
Revises: 4b8d2f1a9c63
Create Date: 2026-06-20 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'a6d4e9c2f1b8'
down_revision = '4b8d2f1a9c63'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'postgame_processed_games',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('mlb_game_pk', sa.Integer(), nullable=False),
        sa.Column('game_date', sa.Date(), nullable=False),
        sa.Column('game_type', sa.String(length=2), nullable=True),
        sa.Column('home_team_id', sa.Integer(), nullable=True),
        sa.Column('away_team_id', sa.Integer(), nullable=True),
        sa.Column('final_state', sa.String(length=80), nullable=True),
        sa.Column('logs_added', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('pitchers_touched', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sync_run_id', sa.Integer(), nullable=True),
        sa.Column('processed_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('mlb_game_pk', name='uq_postgame_processed_games_game_pk'),
    )
    with op.batch_alter_table('postgame_processed_games', schema=None) as batch_op:
        batch_op.create_index(
            'ix_postgame_processed_games_game_date',
            ['game_date'],
            unique=False,
        )
        batch_op.create_index(
            'ix_postgame_processed_games_processed_at',
            ['processed_at'],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table('postgame_processed_games', schema=None) as batch_op:
        batch_op.drop_index('ix_postgame_processed_games_processed_at')
        batch_op.drop_index('ix_postgame_processed_games_game_date')
    op.drop_table('postgame_processed_games')
