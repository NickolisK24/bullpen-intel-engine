"""add final game reconciliation

Revision ID: e8b4c2d6f1a9
Revises: a6d2e8f4b1c7
Create Date: 2026-09-09
"""

from alembic import op
import sqlalchemy as sa


revision = 'e8b4c2d6f1a9'
down_revision = 'a6d2e8f4b1c7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'final_game_versions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('game_pk', sa.Integer(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('predecessor_version_id', sa.Integer()),
        sa.Column('baseball_date', sa.Date(), nullable=False),
        sa.Column('game_type', sa.String(2)),
        sa.Column('home_team_id', sa.Integer(), nullable=False),
        sa.Column('away_team_id', sa.Integer(), nullable=False),
        sa.Column('home_score', sa.Integer()),
        sa.Column('away_score', sa.Integer()),
        sa.Column('innings_played', sa.Integer()),
        sa.Column('extra_innings', sa.Boolean()),
        sa.Column('game_number', sa.Integer()),
        sa.Column('doubleheader', sa.String(2)),
        sa.Column('fact_fingerprint', sa.String(64), nullable=False),
        sa.Column('fingerprint_version', sa.String(40), nullable=False),
        sa.Column('core_completeness', sa.String(20), nullable=False),
        sa.Column('pbp_completeness', sa.String(20), nullable=False),
        sa.Column('finality_observation_id', sa.Integer(), nullable=False),
        sa.Column('boxscore_observation_id', sa.Integer(), nullable=False),
        sa.Column('play_by_play_observation_id', sa.Integer()),
        sa.Column('sync_run_id', sa.Integer()),
        sa.Column('is_current', sa.Boolean(), nullable=False),
        sa.Column('superseded_at', sa.DateTime()),
        sa.Column('observed_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['predecessor_version_id'], ['final_game_versions.id'], ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['finality_observation_id'], ['source_observations.id'], ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['boxscore_observation_id'], ['source_observations.id'], ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['play_by_play_observation_id'], ['source_observations.id'], ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('game_pk', 'version_number', name='uq_final_game_versions_game_version'),
        sa.CheckConstraint('version_number > 0', name='ck_final_game_versions_number'),
        sa.CheckConstraint("core_completeness = 'complete'", name='ck_final_game_versions_core_complete'),
        sa.CheckConstraint(
            "pbp_completeness IN ('complete', 'partial', 'unknown', 'failed')",
            name='ck_final_game_versions_pbp_completeness',
        ),
    )
    op.create_index('ix_final_game_versions_game_created', 'final_game_versions', ['game_pk', 'created_at'])
    op.create_index('ix_final_game_versions_date_game', 'final_game_versions', ['baseball_date', 'game_pk'])
    op.create_index('ix_final_game_versions_boxscore_observation', 'final_game_versions', ['boxscore_observation_id'])
    op.create_index('ix_final_game_versions_pbp_observation', 'final_game_versions', ['play_by_play_observation_id'])
    op.create_index(
        'uq_final_game_versions_current_game', 'final_game_versions', ['game_pk'],
        unique=True, postgresql_where=sa.text('is_current'), sqlite_where=sa.text('is_current = 1'),
    )

    op.create_table(
        'final_pitching_appearance_versions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('final_game_version_id', sa.Integer(), nullable=False),
        sa.Column('game_log_id', sa.Integer()),
        sa.Column('game_pk', sa.Integer(), nullable=False),
        sa.Column('baseball_date', sa.Date(), nullable=False),
        sa.Column('pitcher_id', sa.Integer(), nullable=False),
        sa.Column('pitcher_mlb_id', sa.Integer(), nullable=False),
        sa.Column('team_id_at_appearance', sa.Integer(), nullable=False),
        sa.Column('opponent_team_id', sa.Integer()),
        sa.Column('side', sa.String(10), nullable=False),
        sa.Column('appearance_role', sa.String(10), nullable=False),
        sa.Column('appearance_order', sa.Integer()),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('predecessor_version_id', sa.Integer()),
        sa.Column('outs_recorded', sa.Integer(), nullable=False),
        sa.Column('pitches_thrown', sa.Integer()),
        sa.Column('strikes', sa.Integer()),
        sa.Column('balls', sa.Integer()),
        sa.Column('batters_faced', sa.Integer()),
        sa.Column('hits_allowed', sa.Integer()),
        sa.Column('runs_allowed', sa.Integer()),
        sa.Column('earned_runs', sa.Integer()),
        sa.Column('walks', sa.Integer()),
        sa.Column('strikeouts', sa.Integer()),
        sa.Column('home_runs_allowed', sa.Integer()),
        sa.Column('hit_batters', sa.Integer()),
        sa.Column('wild_pitches', sa.Integer()),
        sa.Column('balks', sa.Integer()),
        sa.Column('games_finished', sa.Integer()),
        sa.Column('inherited_runners', sa.Integer()),
        sa.Column('inherited_runners_scored', sa.Integer()),
        sa.Column('save_situation', sa.Boolean()),
        sa.Column('hold', sa.Boolean()),
        sa.Column('blown_save', sa.Boolean()),
        sa.Column('win', sa.Boolean()),
        sa.Column('loss', sa.Boolean()),
        sa.Column('save', sa.Boolean()),
        sa.Column('entry_inning', sa.Integer()),
        sa.Column('entry_half', sa.String(10)),
        sa.Column('entry_outs', sa.Integer()),
        sa.Column('entry_home_score', sa.Integer()),
        sa.Column('entry_away_score', sa.Integer()),
        sa.Column('entry_base_state', sa.JSON()),
        sa.Column('inherited_runners_context', sa.Integer()),
        sa.Column('exit_inning', sa.Integer()),
        sa.Column('exit_half', sa.String(10)),
        sa.Column('exit_outs', sa.Integer()),
        sa.Column('exit_home_score', sa.Integer()),
        sa.Column('exit_away_score', sa.Integer()),
        sa.Column('context_completeness', sa.String(20), nullable=False),
        sa.Column('fact_fingerprint', sa.String(64), nullable=False),
        sa.Column('fingerprint_version', sa.String(40), nullable=False),
        sa.Column('boxscore_observation_id', sa.Integer(), nullable=False),
        sa.Column('play_by_play_observation_id', sa.Integer()),
        sa.Column('sync_run_id', sa.Integer()),
        sa.Column('is_current', sa.Boolean(), nullable=False),
        sa.Column('superseded_at', sa.DateTime()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['final_game_version_id'], ['final_game_versions.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['game_log_id'], ['game_logs.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['pitcher_id'], ['pitchers.id']),
        sa.ForeignKeyConstraint(['predecessor_version_id'], ['final_pitching_appearance_versions.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['boxscore_observation_id'], ['source_observations.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['play_by_play_observation_id'], ['source_observations.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('game_pk', 'pitcher_id', 'version_number', name='uq_final_appearance_versions_game_pitcher_version'),
        sa.CheckConstraint('version_number > 0', name='ck_final_appearance_versions_number'),
        sa.CheckConstraint("appearance_role IN ('starter', 'reliever')", name='ck_final_appearance_versions_role'),
        sa.CheckConstraint('outs_recorded >= 0', name='ck_final_appearance_versions_outs'),
    )
    op.create_index('ix_final_appearance_versions_pitcher_date', 'final_pitching_appearance_versions', ['pitcher_id', 'baseball_date'])
    op.create_index('ix_final_appearance_versions_team_date', 'final_pitching_appearance_versions', ['team_id_at_appearance', 'baseball_date'])
    op.create_index('ix_final_appearance_versions_game_order', 'final_pitching_appearance_versions', ['game_pk', 'team_id_at_appearance', 'appearance_order'])
    op.create_index('ix_final_appearance_versions_boxscore_observation', 'final_pitching_appearance_versions', ['boxscore_observation_id'])
    op.create_index('ix_final_appearance_versions_pbp_observation', 'final_pitching_appearance_versions', ['play_by_play_observation_id'])
    op.create_index(
        'uq_final_appearance_versions_current', 'final_pitching_appearance_versions',
        ['game_pk', 'pitcher_id'], unique=True,
        postgresql_where=sa.text('is_current'), sqlite_where=sa.text('is_current = 1'),
    )

    op.create_table(
        'final_game_mutations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('mutation_key', sa.String(120), nullable=False),
        sa.Column('mutation_type', sa.String(50), nullable=False),
        sa.Column('final_game_version_id', sa.Integer(), nullable=False),
        sa.Column('old_appearance_version_id', sa.Integer()),
        sa.Column('new_appearance_version_id', sa.Integer()),
        sa.Column('game_pk', sa.Integer(), nullable=False),
        sa.Column('baseball_date', sa.Date(), nullable=False),
        sa.Column('team_id', sa.Integer()),
        sa.Column('pitcher_id', sa.Integer()),
        sa.Column('pitcher_mlb_id', sa.Integer()),
        sa.Column('source_observation_id', sa.Integer(), nullable=False),
        sa.Column('sync_run_id', sa.Integer()),
        sa.Column('details_json', sa.JSON()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['final_game_version_id'], ['final_game_versions.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['old_appearance_version_id'], ['final_pitching_appearance_versions.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['new_appearance_version_id'], ['final_pitching_appearance_versions.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['pitcher_id'], ['pitchers.id']),
        sa.ForeignKeyConstraint(['source_observation_id'], ['source_observations.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id'], ondelete='SET NULL'),
        sa.UniqueConstraint('mutation_key', name='uq_final_game_mutations_key'),
        sa.CheckConstraint(
            "mutation_type IN ('final_game_ingested', 'starter_appearance_added', "
            "'reliever_appearance_added', 'pitching_line_corrected', "
            "'appearance_context_corrected', 'final_play_by_play_corrected', "
            "'final_game_context_corrected')",
            name='ck_final_game_mutations_type',
        ),
    )
    op.create_index('ix_final_game_mutations_game_date', 'final_game_mutations', ['game_pk', 'baseball_date'])
    op.create_index('ix_final_game_mutations_team_date', 'final_game_mutations', ['team_id', 'baseball_date'])
    op.create_index('ix_final_game_mutations_pitcher_date', 'final_game_mutations', ['pitcher_id', 'baseball_date'])
    op.create_index('ix_final_game_mutations_sync_run', 'final_game_mutations', ['sync_run_id', 'id'])


def downgrade():
    op.drop_index('ix_final_game_mutations_sync_run', table_name='final_game_mutations')
    op.drop_index('ix_final_game_mutations_pitcher_date', table_name='final_game_mutations')
    op.drop_index('ix_final_game_mutations_team_date', table_name='final_game_mutations')
    op.drop_index('ix_final_game_mutations_game_date', table_name='final_game_mutations')
    op.drop_table('final_game_mutations')
    op.drop_index('uq_final_appearance_versions_current', table_name='final_pitching_appearance_versions')
    op.drop_index('ix_final_appearance_versions_pbp_observation', table_name='final_pitching_appearance_versions')
    op.drop_index('ix_final_appearance_versions_boxscore_observation', table_name='final_pitching_appearance_versions')
    op.drop_index('ix_final_appearance_versions_game_order', table_name='final_pitching_appearance_versions')
    op.drop_index('ix_final_appearance_versions_team_date', table_name='final_pitching_appearance_versions')
    op.drop_index('ix_final_appearance_versions_pitcher_date', table_name='final_pitching_appearance_versions')
    op.drop_table('final_pitching_appearance_versions')
    op.drop_index('uq_final_game_versions_current_game', table_name='final_game_versions')
    op.drop_index('ix_final_game_versions_pbp_observation', table_name='final_game_versions')
    op.drop_index('ix_final_game_versions_boxscore_observation', table_name='final_game_versions')
    op.drop_index('ix_final_game_versions_date_game', table_name='final_game_versions')
    op.drop_index('ix_final_game_versions_game_created', table_name='final_game_versions')
    op.drop_table('final_game_versions')
