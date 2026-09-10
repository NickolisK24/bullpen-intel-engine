"""add live game delta authority

Revision ID: f9c2a7e4b1d6
Revises: e8b4c2d6f1a9
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa


revision = 'f9c2a7e4b1d6'
down_revision = 'e8b4c2d6f1a9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('game_observation_states', sa.Column('live_bullpen_fingerprint', sa.String(64)))
    op.add_column('game_observation_states', sa.Column('next_live_poll_at', sa.DateTime()))
    op.add_column('game_observation_states', sa.Column('live_polling_policy_version', sa.String(40)))
    op.create_index('ix_game_observation_states_next_live_poll', 'game_observation_states', ['next_live_poll_at'])

    op.create_table(
        'provisional_pitching_appearance_states',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('game_pk', sa.Integer(), nullable=False),
        sa.Column('baseball_date', sa.Date(), nullable=False),
        sa.Column('pitcher_id', sa.Integer(), nullable=False),
        sa.Column('pitcher_mlb_id', sa.Integer(), nullable=False),
        sa.Column('team_id_at_appearance', sa.Integer(), nullable=False),
        sa.Column('opponent_team_id', sa.Integer()),
        sa.Column('side', sa.String(10), nullable=False),
        sa.Column('appearance_role', sa.String(10), nullable=False),
        sa.Column('appearance_order', sa.Integer()),
        sa.Column('outing_status', sa.String(10), nullable=False),
        sa.Column('pitches_thrown', sa.Integer()), sa.Column('strikes', sa.Integer()),
        sa.Column('balls', sa.Integer()), sa.Column('outs_recorded', sa.Integer(), nullable=False),
        sa.Column('batters_faced', sa.Integer()), sa.Column('hits_allowed', sa.Integer()),
        sa.Column('runs_allowed', sa.Integer()), sa.Column('earned_runs', sa.Integer()),
        sa.Column('walks', sa.Integer()), sa.Column('strikeouts', sa.Integer()),
        sa.Column('home_runs_allowed', sa.Integer()), sa.Column('current_inning', sa.Integer()),
        sa.Column('current_half', sa.String(10)), sa.Column('entry_inning', sa.Integer()),
        sa.Column('entry_half', sa.String(10)), sa.Column('entry_outs', sa.Integer()),
        sa.Column('entry_home_score', sa.Integer()), sa.Column('entry_away_score', sa.Integer()),
        sa.Column('entry_base_state', sa.JSON()), sa.Column('inherited_runners', sa.Integer()),
        sa.Column('first_observation_id', sa.Integer(), nullable=False),
        sa.Column('latest_observation_id', sa.Integer(), nullable=False),
        sa.Column('latest_source_observed_at', sa.DateTime()),
        sa.Column('fact_fingerprint', sa.String(64), nullable=False),
        sa.Column('fingerprint_version', sa.String(40), nullable=False),
        sa.Column('completeness', sa.String(32), nullable=False),
        sa.Column('authority_state', sa.String(12), nullable=False),
        sa.Column('is_current', sa.Boolean(), nullable=False),
        sa.Column('superseded_by_final_game_version_id', sa.Integer()),
        sa.Column('superseded_at', sa.DateTime()),
        sa.Column('first_seen_at', sa.DateTime(), nullable=False),
        sa.Column('latest_seen_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['pitcher_id'], ['pitchers.id']),
        sa.ForeignKeyConstraint(['first_observation_id'], ['source_observations.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['latest_observation_id'], ['source_observations.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['superseded_by_final_game_version_id'], ['final_game_versions.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('game_pk', 'pitcher_id', name='uq_live_appearance_game_pitcher'),
        sa.CheckConstraint("authority_state = 'live'", name='ck_live_appearance_authority'),
        sa.CheckConstraint("appearance_role IN ('starter', 'reliever')", name='ck_live_appearance_role'),
        sa.CheckConstraint("outing_status IN ('active', 'closed', 'unknown')", name='ck_live_appearance_outing'),
        sa.CheckConstraint('outs_recorded >= 0', name='ck_live_appearance_outs'),
    )
    op.create_index('ix_live_appearance_game_order', 'provisional_pitching_appearance_states', ['game_pk', 'team_id_at_appearance', 'appearance_order'])
    op.create_index('ix_live_appearance_team_date', 'provisional_pitching_appearance_states', ['team_id_at_appearance', 'baseball_date'])
    op.create_index('ix_live_appearance_source_observation', 'provisional_pitching_appearance_states', ['latest_observation_id'])
    op.create_index('ix_live_appearance_active_game', 'provisional_pitching_appearance_states', ['game_pk', 'team_id_at_appearance'], postgresql_where=sa.text("outing_status = 'active' AND is_current"), sqlite_where=sa.text("outing_status = 'active' AND is_current = 1"))

    op.create_table(
        'live_game_mutations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('mutation_key', sa.String(160), nullable=False),
        sa.Column('mutation_type', sa.String(50), nullable=False),
        sa.Column('game_pk', sa.Integer(), nullable=False), sa.Column('baseball_date', sa.Date(), nullable=False),
        sa.Column('team_id', sa.Integer()), sa.Column('pitcher_id', sa.Integer()),
        sa.Column('pitcher_mlb_id', sa.Integer()), sa.Column('source_observation_id', sa.Integer(), nullable=False),
        sa.Column('sync_run_id', sa.Integer()), sa.Column('old_fingerprint', sa.String(64)),
        sa.Column('new_fingerprint', sa.String(64)), sa.Column('old_state_json', sa.JSON()),
        sa.Column('new_state_json', sa.JSON()), sa.Column('authority_state', sa.String(12), nullable=False),
        sa.Column('is_correction', sa.Boolean(), nullable=False), sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['pitcher_id'], ['pitchers.id']),
        sa.ForeignKeyConstraint(['source_observation_id'], ['source_observations.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('mutation_key', name='uq_live_game_mutations_key'),
        sa.CheckConstraint("authority_state = 'live'", name='ck_live_mutation_authority'),
    )
    op.create_index('ix_live_mutations_game_date', 'live_game_mutations', ['game_pk', 'baseball_date'])
    op.create_index('ix_live_mutations_team_date', 'live_game_mutations', ['team_id', 'baseball_date'])
    op.create_index('ix_live_mutations_pitcher_date', 'live_game_mutations', ['pitcher_id', 'baseball_date'])
    op.create_index('ix_live_mutations_source_observation', 'live_game_mutations', ['source_observation_id'])


def downgrade():
    for name in ('ix_live_mutations_source_observation', 'ix_live_mutations_pitcher_date', 'ix_live_mutations_team_date', 'ix_live_mutations_game_date'):
        op.drop_index(name, table_name='live_game_mutations')
    op.drop_table('live_game_mutations')
    for name in ('ix_live_appearance_active_game', 'ix_live_appearance_source_observation', 'ix_live_appearance_team_date', 'ix_live_appearance_game_order'):
        op.drop_index(name, table_name='provisional_pitching_appearance_states')
    op.drop_table('provisional_pitching_appearance_states')
    op.drop_index('ix_game_observation_states_next_live_poll', table_name='game_observation_states')
    op.drop_column('game_observation_states', 'live_polling_policy_version')
    op.drop_column('game_observation_states', 'next_live_poll_at')
    op.drop_column('game_observation_states', 'live_bullpen_fingerprint')
