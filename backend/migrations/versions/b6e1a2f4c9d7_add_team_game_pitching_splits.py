"""add team game pitching splits

Revision ID: b6e1a2f4c9d7
Revises: a2f4c6d8e9b1
Create Date: 2026-07-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'b6e1a2f4c9d7'
down_revision = 'a2f4c6d8e9b1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'team_game_pitching_splits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('mlb_game_pk', sa.Integer(), nullable=False),
        sa.Column('game_date', sa.Date(), nullable=False),
        sa.Column('game_type', sa.String(length=2), nullable=True),
        sa.Column('opponent_team_id', sa.Integer(), nullable=True),
        sa.Column('home_away', sa.String(length=10), nullable=True),
        sa.Column('starter_pitcher_id', sa.Integer(), nullable=True),
        sa.Column('starter_mlb_id', sa.Integer(), nullable=True),
        sa.Column('starter_identity_status', sa.String(length=20), nullable=False),
        sa.Column('starter_outs_recorded', sa.Integer(), nullable=True),
        sa.Column('starter_pitches_thrown', sa.Integer(), nullable=True),
        sa.Column('starter_batters_faced', sa.Integer(), nullable=True),
        sa.Column('starter_balls', sa.Integer(), nullable=True),
        sa.Column('starter_games_started', sa.Integer(), nullable=True),
        sa.Column('bullpen_outs_recorded', sa.Integer(), nullable=True),
        sa.Column('bullpen_pitches_thrown', sa.Integer(), nullable=True),
        sa.Column('bullpen_batters_faced', sa.Integer(), nullable=True),
        sa.Column('bullpen_balls', sa.Integer(), nullable=True),
        sa.Column('relievers_used_count', sa.Integer(), nullable=True),
        sa.Column('total_team_outs', sa.Integer(), nullable=True),
        sa.Column('total_team_pitches', sa.Integer(), nullable=True),
        sa.Column('total_team_batters_faced', sa.Integer(), nullable=True),
        sa.Column('total_team_balls', sa.Integer(), nullable=True),
        sa.Column('split_completeness_status', sa.String(length=20), nullable=False),
        sa.Column('split_reason_codes', sa.JSON(), nullable=True),
        sa.Column('off_day_before', sa.Boolean(), nullable=True),
        sa.Column('off_day_after', sa.Boolean(), nullable=True),
        sa.Column('consecutive_game_day_count_entering', sa.Integer(), nullable=True),
        sa.Column('series_game_number', sa.Integer(), nullable=True),
        sa.Column('games_in_series', sa.Integer(), nullable=True),
        sa.Column('doubleheader_flag', sa.Boolean(), nullable=True),
        sa.Column('doubleheader_code', sa.String(length=2), nullable=True),
        sa.Column('game_number', sa.Integer(), nullable=True),
        sa.Column('postponed_or_makeup_indicator', sa.Boolean(), nullable=True),
        sa.Column('suspended_resumed_linkage_status', sa.String(length=20), nullable=False),
        sa.Column('extra_inning_indicator', sa.Boolean(), nullable=True),
        sa.Column('calendar_context_status', sa.String(length=20), nullable=False),
        sa.Column('calendar_reason_codes', sa.JSON(), nullable=True),
        sa.Column('source', sa.String(length=100), nullable=False),
        sa.Column('sync_run_id', sa.Integer(), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(), nullable=False),
        sa.Column('last_corrected_at', sa.DateTime(), nullable=True),
        sa.Column('correction_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('correction_source', sa.String(length=100), nullable=True),
        sa.Column('last_derived_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "starter_identity_status IN ('known', 'unknown', 'ambiguous')",
            name='ck_team_game_pitching_splits_starter_status',
        ),
        sa.CheckConstraint(
            "split_completeness_status IN ('complete', 'partial', 'unknown')",
            name='ck_team_game_pitching_splits_split_status',
        ),
        sa.CheckConstraint(
            "calendar_context_status IN ('complete', 'partial', 'unknown')",
            name='ck_team_game_pitching_splits_calendar_status',
        ),
        sa.CheckConstraint(
            "suspended_resumed_linkage_status IN ('none', 'resolved', 'ambiguous')",
            name='ck_team_game_pitching_splits_linkage_status',
        ),
        sa.ForeignKeyConstraint(['starter_pitcher_id'], ['pitchers.id']),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'team_id',
            'mlb_game_pk',
            name='uq_team_game_pitching_splits_team_game',
        ),
    )
    op.create_index(
        'ix_team_game_pitching_splits_calendar_status',
        'team_game_pitching_splits',
        ['calendar_context_status'],
        unique=False,
    )
    op.create_index(
        'ix_team_game_pitching_splits_game_pk',
        'team_game_pitching_splits',
        ['mlb_game_pk'],
        unique=False,
    )
    op.create_index(
        'ix_team_game_pitching_splits_split_status',
        'team_game_pitching_splits',
        ['split_completeness_status'],
        unique=False,
    )
    op.create_index(
        'ix_team_game_pitching_splits_team_date',
        'team_game_pitching_splits',
        ['team_id', 'game_date'],
        unique=False,
    )


def downgrade():
    op.drop_index(
        'ix_team_game_pitching_splits_team_date',
        table_name='team_game_pitching_splits',
    )
    op.drop_index(
        'ix_team_game_pitching_splits_split_status',
        table_name='team_game_pitching_splits',
    )
    op.drop_index(
        'ix_team_game_pitching_splits_game_pk',
        table_name='team_game_pitching_splits',
    )
    op.drop_index(
        'ix_team_game_pitching_splits_calendar_status',
        table_name='team_game_pitching_splits',
    )
    op.drop_table('team_game_pitching_splits')
