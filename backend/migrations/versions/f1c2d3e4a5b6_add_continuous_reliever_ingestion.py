"""add continuous reliever ingestion foundation

Revision ID: f1c2d3e4a5b6
Revises: a6d4e8c1f2b7
Create Date: 2026-08-28 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'f1c2d3e4a5b6'
down_revision = 'a6d4e8c1f2b7'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('game_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('hit_batters', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('wild_pitches', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('source_authority', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('source_endpoint', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('source_revision', sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column('source_acquired_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('source_sync_run_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            'fk_game_logs_source_sync_run_id_sync_runs',
            'sync_runs', ['source_sync_run_id'], ['id'],
        )

    op.create_table(
        'game_pitch_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('mlb_game_pk', sa.Integer(), nullable=False),
        sa.Column('at_bat_index', sa.Integer(), nullable=False),
        sa.Column('play_event_index', sa.Integer(), nullable=False),
        sa.Column('source_play_id', sa.String(length=80), nullable=True),
        sa.Column('pitch_number', sa.Integer(), nullable=True),
        sa.Column('game_date', sa.Date(), nullable=False),
        sa.Column('game_type', sa.String(length=2), nullable=True),
        sa.Column('inning', sa.Integer(), nullable=True),
        sa.Column('half_inning', sa.String(length=10), nullable=True),
        sa.Column('outs_after_pitch', sa.Integer(), nullable=True),
        sa.Column('balls_after_pitch', sa.Integer(), nullable=True),
        sa.Column('strikes_after_pitch', sa.Integer(), nullable=True),
        sa.Column('pitcher_mlb_id', sa.Integer(), nullable=False),
        sa.Column('pitcher_id', sa.Integer(), nullable=False),
        sa.Column('batter_mlb_id', sa.Integer(), nullable=True),
        sa.Column('batting_team_id', sa.Integer(), nullable=True),
        sa.Column('fielding_team_id', sa.Integer(), nullable=False),
        sa.Column('pitch_type_code', sa.String(length=12), nullable=True),
        sa.Column('pitch_type_description', sa.String(length=60), nullable=True),
        sa.Column('call_code', sa.String(length=12), nullable=True),
        sa.Column('call_description', sa.String(length=80), nullable=True),
        sa.Column('is_ball', sa.Boolean(), nullable=True),
        sa.Column('is_strike', sa.Boolean(), nullable=True),
        sa.Column('is_in_play', sa.Boolean(), nullable=True),
        sa.Column('is_out', sa.Boolean(), nullable=True),
        sa.Column('start_speed', sa.Float(), nullable=True),
        sa.Column('end_speed', sa.Float(), nullable=True),
        sa.Column('spin_rate', sa.Float(), nullable=True),
        sa.Column('spin_direction', sa.Float(), nullable=True),
        sa.Column('extension', sa.Float(), nullable=True),
        sa.Column('plate_time', sa.Float(), nullable=True),
        sa.Column('zone', sa.Integer(), nullable=True),
        sa.Column('plate_x', sa.Float(), nullable=True),
        sa.Column('plate_z', sa.Float(), nullable=True),
        sa.Column('strike_zone_top', sa.Float(), nullable=True),
        sa.Column('strike_zone_bottom', sa.Float(), nullable=True),
        sa.Column('release_position_x', sa.Float(), nullable=True),
        sa.Column('release_position_y', sa.Float(), nullable=True),
        sa.Column('release_position_z', sa.Float(), nullable=True),
        sa.Column('initial_velocity_x', sa.Float(), nullable=True),
        sa.Column('initial_velocity_y', sa.Float(), nullable=True),
        sa.Column('initial_velocity_z', sa.Float(), nullable=True),
        sa.Column('acceleration_x', sa.Float(), nullable=True),
        sa.Column('acceleration_y', sa.Float(), nullable=True),
        sa.Column('acceleration_z', sa.Float(), nullable=True),
        sa.Column('pfx_x', sa.Float(), nullable=True),
        sa.Column('pfx_z', sa.Float(), nullable=True),
        sa.Column('break_angle', sa.Float(), nullable=True),
        sa.Column('break_horizontal', sa.Float(), nullable=True),
        sa.Column('break_length', sa.Float(), nullable=True),
        sa.Column('break_vertical', sa.Float(), nullable=True),
        sa.Column('break_vertical_induced', sa.Float(), nullable=True),
        sa.Column('batted_ball_event_type', sa.String(length=60), nullable=True),
        sa.Column('batted_ball_trajectory', sa.String(length=40), nullable=True),
        sa.Column('batted_ball_hardness', sa.String(length=20), nullable=True),
        sa.Column('launch_speed', sa.Float(), nullable=True),
        sa.Column('launch_angle', sa.Float(), nullable=True),
        sa.Column('total_distance', sa.Float(), nullable=True),
        sa.Column('hit_location', sa.String(length=12), nullable=True),
        sa.Column('source', sa.String(length=100), nullable=False),
        sa.Column('source_endpoint', sa.String(length=100), nullable=False),
        sa.Column('source_revision', sa.String(length=64), nullable=False),
        sa.Column('event_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('sync_run_id', sa.Integer(), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(), nullable=False),
        sa.Column('last_corrected_at', sa.DateTime(), nullable=True),
        sa.Column('correction_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('correction_source', sa.String(length=100), nullable=True),
        sa.Column('is_current', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('superseded_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "half_inning IS NULL OR half_inning IN ('top', 'bottom')",
            name='ck_game_pitch_events_half_inning',
        ),
        sa.CheckConstraint(
            '(is_current = true AND superseded_at IS NULL) OR '
            '(is_current = false AND superseded_at IS NOT NULL)',
            name='ck_game_pitch_events_current_state',
        ),
        sa.ForeignKeyConstraint(['pitcher_id'], ['pitchers.id']),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'mlb_game_pk', 'at_bat_index', 'play_event_index',
            name='uq_game_pitch_events_game_at_bat_event',
        ),
    )
    op.create_index(
        'ix_game_pitch_events_game_order', 'game_pitch_events',
        ['mlb_game_pk', 'at_bat_index', 'play_event_index'], unique=False,
    )
    op.create_index(
        'ix_game_pitch_events_pitcher_date', 'game_pitch_events',
        ['pitcher_id', 'game_date'], unique=False,
    )
    op.create_index(
        'ix_game_pitch_events_team_date', 'game_pitch_events',
        ['fielding_team_id', 'game_date'], unique=False,
    )

    with op.batch_alter_table('play_by_play_processed_games', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pitches_seen', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('pitches_stored', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('current_pitch_count', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('pitch_fingerprint', sa.String(length=64), nullable=True))


def downgrade():
    with op.batch_alter_table('play_by_play_processed_games', schema=None) as batch_op:
        batch_op.drop_column('pitch_fingerprint')
        batch_op.drop_column('current_pitch_count')
        batch_op.drop_column('pitches_stored')
        batch_op.drop_column('pitches_seen')

    op.drop_index('ix_game_pitch_events_team_date', table_name='game_pitch_events')
    op.drop_index('ix_game_pitch_events_pitcher_date', table_name='game_pitch_events')
    op.drop_index('ix_game_pitch_events_game_order', table_name='game_pitch_events')
    op.drop_table('game_pitch_events')

    with op.batch_alter_table('game_logs', schema=None) as batch_op:
        batch_op.drop_constraint(
            'fk_game_logs_source_sync_run_id_sync_runs', type_='foreignkey',
        )
        batch_op.drop_column('source_sync_run_id')
        batch_op.drop_column('source_acquired_at')
        batch_op.drop_column('source_revision')
        batch_op.drop_column('source_endpoint')
        batch_op.drop_column('source_authority')
        batch_op.drop_column('wild_pitches')
        batch_op.drop_column('hit_batters')
