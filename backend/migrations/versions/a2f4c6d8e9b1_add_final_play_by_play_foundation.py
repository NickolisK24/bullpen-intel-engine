"""add final play by play foundation

Revision ID: a2f4c6d8e9b1
Revises: f8c2d4e6a1b9
Create Date: 2026-07-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'a2f4c6d8e9b1'
down_revision = 'f8c2d4e6a1b9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'game_play_by_play_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('mlb_game_pk', sa.Integer(), nullable=False),
        sa.Column('event_index', sa.Integer(), nullable=False),
        sa.Column('source_play_id', sa.String(length=80), nullable=True),
        sa.Column('at_bat_index', sa.Integer(), nullable=True),
        sa.Column('game_date', sa.Date(), nullable=False),
        sa.Column('game_type', sa.String(length=2), nullable=True),
        sa.Column('home_team_id', sa.Integer(), nullable=False),
        sa.Column('away_team_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(length=30), nullable=False),
        sa.Column('event_type_code', sa.String(length=40), nullable=True),
        sa.Column('inning', sa.Integer(), nullable=True),
        sa.Column('half_inning', sa.String(length=10), nullable=True),
        sa.Column('is_top_inning', sa.Boolean(), nullable=True),
        sa.Column('outs_at_event', sa.Integer(), nullable=True),
        sa.Column('home_score_at_event', sa.Integer(), nullable=True),
        sa.Column('away_score_at_event', sa.Integer(), nullable=True),
        sa.Column('pitcher_mlb_id', sa.Integer(), nullable=True),
        sa.Column('pitcher_id', sa.Integer(), nullable=True),
        sa.Column('batter_mlb_id', sa.Integer(), nullable=True),
        sa.Column('batting_team_id', sa.Integer(), nullable=True),
        sa.Column('fielding_team_id', sa.Integer(), nullable=True),
        sa.Column('is_pitching_change', sa.Boolean(), nullable=False),
        sa.Column('is_scoring_play', sa.Boolean(), nullable=False),
        sa.Column('is_mound_visit', sa.Boolean(), nullable=False),
        sa.Column('source', sa.String(length=100), nullable=False),
        sa.Column('source_endpoint', sa.String(length=100), nullable=False),
        sa.Column('sync_run_id', sa.Integer(), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(), nullable=False),
        sa.Column('last_corrected_at', sa.DateTime(), nullable=True),
        sa.Column('correction_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('correction_source', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "half_inning IS NULL OR half_inning IN ('top', 'bottom')",
            name='ck_game_play_by_play_events_half_inning',
        ),
        sa.CheckConstraint(
            "event_type IN ("
            "'plate_appearance', 'pitching_change', 'scoring_play', "
            "'mound_visit', 'unknown')",
            name='ck_game_play_by_play_events_event_type',
        ),
        sa.ForeignKeyConstraint(['pitcher_id'], ['pitchers.id']),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'mlb_game_pk',
            'event_index',
            name='uq_game_play_by_play_events_game_event',
        ),
    )
    op.create_index(
        'ix_game_play_by_play_events_game_date',
        'game_play_by_play_events',
        ['game_date'],
        unique=False,
    )
    op.create_index(
        'ix_game_play_by_play_events_game_order',
        'game_play_by_play_events',
        ['mlb_game_pk', 'event_index'],
        unique=False,
    )
    op.create_index(
        'ix_game_play_by_play_events_pitcher',
        'game_play_by_play_events',
        ['pitcher_mlb_id'],
        unique=False,
    )

    op.create_table(
        'play_by_play_processed_games',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('mlb_game_pk', sa.Integer(), nullable=False),
        sa.Column('game_date', sa.Date(), nullable=False),
        sa.Column('game_type', sa.String(length=2), nullable=True),
        sa.Column('home_team_id', sa.Integer(), nullable=True),
        sa.Column('away_team_id', sa.Integer(), nullable=True),
        sa.Column('final_state', sa.String(length=80), nullable=True),
        sa.Column('processing_status', sa.String(length=32), nullable=False),
        sa.Column('attempt_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_attempted_at', sa.DateTime(), nullable=True),
        sa.Column('incomplete_reason', sa.String(length=120), nullable=True),
        sa.Column('events_seen', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('events_stored', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('pitcher_events_seen', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unresolved_pitcher_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('reconciliation_mismatch_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('event_fingerprint', sa.String(length=64), nullable=True),
        sa.Column('source', sa.String(length=100), nullable=False),
        sa.Column('source_endpoint', sa.String(length=100), nullable=False),
        sa.Column('sync_run_id', sa.Integer(), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(), nullable=False),
        sa.Column('last_corrected_at', sa.DateTime(), nullable=True),
        sa.Column('correction_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('correction_source', sa.String(length=100), nullable=True),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('failed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'mlb_game_pk',
            name='uq_play_by_play_processed_games_game_pk',
        ),
    )
    op.create_index(
        'ix_play_by_play_processed_games_attempted',
        'play_by_play_processed_games',
        ['last_attempted_at'],
        unique=False,
    )
    op.create_index(
        'ix_play_by_play_processed_games_game_date',
        'play_by_play_processed_games',
        ['game_date'],
        unique=False,
    )
    op.create_index(
        'ix_play_by_play_processed_games_status',
        'play_by_play_processed_games',
        ['processing_status'],
        unique=False,
    )


def downgrade():
    op.drop_index(
        'ix_play_by_play_processed_games_status',
        table_name='play_by_play_processed_games',
    )
    op.drop_index(
        'ix_play_by_play_processed_games_game_date',
        table_name='play_by_play_processed_games',
    )
    op.drop_index(
        'ix_play_by_play_processed_games_attempted',
        table_name='play_by_play_processed_games',
    )
    op.drop_table('play_by_play_processed_games')
    op.drop_index(
        'ix_game_play_by_play_events_pitcher',
        table_name='game_play_by_play_events',
    )
    op.drop_index(
        'ix_game_play_by_play_events_game_order',
        table_name='game_play_by_play_events',
    )
    op.drop_index(
        'ix_game_play_by_play_events_game_date',
        table_name='game_play_by_play_events',
    )
    op.drop_table('game_play_by_play_events')
