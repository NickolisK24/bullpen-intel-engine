"""add pregame context authority

Revision ID: a6d2e8f4b1c7
Revises: f3c7a1d9e5b2
Create Date: 2026-09-08
"""

from alembic import op
import sqlalchemy as sa


revision = 'a6d2e8f4b1c7'
down_revision = 'f3c7a1d9e5b2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'game_pregame_context_versions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('game_pk', sa.Integer(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('predecessor_version_id', sa.Integer()),
        sa.Column('baseball_date', sa.Date(), nullable=False),
        sa.Column('scheduled_at', sa.DateTime()),
        sa.Column('home_team_id', sa.Integer(), nullable=False),
        sa.Column('away_team_id', sa.Integer(), nullable=False),
        sa.Column('home_probable_pitcher_mlb_id', sa.Integer()),
        sa.Column('away_probable_pitcher_mlb_id', sa.Integer()),
        sa.Column('home_probable_pitcher_id', sa.Integer()),
        sa.Column('away_probable_pitcher_id', sa.Integer()),
        sa.Column('home_probable_pitcher_name', sa.String(100)),
        sa.Column('away_probable_pitcher_name', sa.String(100)),
        sa.Column('venue_id', sa.Integer()),
        sa.Column('venue_name', sa.String(120)),
        sa.Column('game_type', sa.String(2)),
        sa.Column('game_number', sa.Integer()),
        sa.Column('doubleheader', sa.String(2)),
        sa.Column('resumed_from_game_pk', sa.Integer()),
        sa.Column('context_fingerprint', sa.String(64), nullable=False),
        sa.Column('fingerprint_version', sa.String(40), nullable=False),
        sa.Column('source_observation_id', sa.Integer(), nullable=False),
        sa.Column('completeness', sa.String(20), nullable=False),
        sa.Column('observed_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['predecessor_version_id'], ['game_pregame_context_versions.id'],
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(['home_probable_pitcher_id'], ['pitchers.id']),
        sa.ForeignKeyConstraint(['away_probable_pitcher_id'], ['pitchers.id']),
        sa.ForeignKeyConstraint(
            ['source_observation_id'], ['source_observations.id'],
            ondelete='RESTRICT',
        ),
        sa.UniqueConstraint(
            'game_pk', 'version_number',
            name='uq_game_pregame_context_versions_game_version',
        ),
        sa.UniqueConstraint(
            'game_pk', 'source_observation_id', 'fingerprint_version',
            name='uq_game_pregame_context_versions_game_observation',
        ),
        sa.CheckConstraint(
            'version_number > 0', name='ck_game_pregame_context_versions_number',
        ),
        sa.CheckConstraint(
            "completeness = 'complete'",
            name='ck_game_pregame_context_versions_complete',
        ),
    )
    op.create_index(
        'ix_game_pregame_context_versions_game_created',
        'game_pregame_context_versions', ['game_pk', 'created_at'],
    )
    op.create_index(
        'ix_game_pregame_context_versions_observation',
        'game_pregame_context_versions', ['source_observation_id'],
    )
    op.create_index(
        'ix_game_pregame_context_versions_baseball_date',
        'game_pregame_context_versions', ['baseball_date', 'game_pk'],
    )

    op.create_table(
        'pregame_context_mutations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('context_version_id', sa.Integer(), nullable=False),
        sa.Column('game_pk', sa.Integer(), nullable=False),
        sa.Column('baseball_date', sa.Date(), nullable=False),
        sa.Column('team_id', sa.Integer()),
        sa.Column('side', sa.String(10), nullable=False),
        sa.Column('mutation_type', sa.String(40), nullable=False),
        sa.Column('old_probable_pitcher_mlb_id', sa.Integer()),
        sa.Column('new_probable_pitcher_mlb_id', sa.Integer()),
        sa.Column('source_observation_id', sa.Integer(), nullable=False),
        sa.Column('sync_run_id', sa.Integer()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['context_version_id'], ['game_pregame_context_versions.id'],
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['source_observation_id'], ['source_observations.id'],
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['sync_run_id'], ['sync_runs.id'], ondelete='SET NULL',
        ),
        sa.UniqueConstraint(
            'context_version_id', 'mutation_type', 'side',
            name='uq_pregame_context_mutations_version_type_side',
        ),
        sa.CheckConstraint(
            "mutation_type IN ('pregame_context_discovered', "
            "'probable_starter_added', 'probable_starter_changed', "
            "'probable_starter_removed', 'pregame_context_changed')",
            name='ck_pregame_context_mutations_type',
        ),
        sa.CheckConstraint(
            "side IN ('game', 'home', 'away')",
            name='ck_pregame_context_mutations_side',
        ),
    )
    op.create_index(
        'ix_pregame_context_mutations_game_date',
        'pregame_context_mutations', ['game_pk', 'baseball_date'],
    )
    op.create_index(
        'ix_pregame_context_mutations_team_date',
        'pregame_context_mutations', ['team_id', 'baseball_date'],
    )
    op.create_index(
        'ix_pregame_context_mutations_observation',
        'pregame_context_mutations', ['source_observation_id'],
    )

    with op.batch_alter_table('scheduled_games') as batch_op:
        batch_op.add_column(sa.Column('home_probable_pitcher_mlb_id', sa.Integer()))
        batch_op.add_column(sa.Column('away_probable_pitcher_mlb_id', sa.Integer()))
        batch_op.add_column(sa.Column('home_probable_pitcher_name', sa.String(100)))
        batch_op.add_column(sa.Column('away_probable_pitcher_name', sa.String(100)))
        batch_op.add_column(sa.Column('pregame_context_observation_id', sa.Integer()))
        batch_op.add_column(sa.Column('pregame_context_version_id', sa.Integer()))
        batch_op.add_column(sa.Column('pregame_context_fingerprint', sa.String(64)))
        batch_op.add_column(sa.Column('pregame_context_version', sa.Integer()))
        batch_op.add_column(sa.Column('pregame_context_completeness', sa.String(20)))
        batch_op.add_column(sa.Column('pregame_context_updated_at', sa.DateTime()))
        batch_op.add_column(sa.Column('next_pregame_poll_at', sa.DateTime()))
        batch_op.add_column(sa.Column('pregame_policy_version', sa.String(40)))
        batch_op.create_foreign_key(
            'fk_scheduled_games_pregame_observation',
            'source_observations', ['pregame_context_observation_id'], ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_foreign_key(
            'fk_scheduled_games_pregame_version',
            'game_pregame_context_versions', ['pregame_context_version_id'], ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_index(
            'ix_scheduled_games_next_pregame_poll_at', ['next_pregame_poll_at'],
        )
        batch_op.create_index(
            'ix_scheduled_games_home_probable_pitcher',
            ['home_probable_pitcher_mlb_id'],
        )
        batch_op.create_index(
            'ix_scheduled_games_away_probable_pitcher',
            ['away_probable_pitcher_mlb_id'],
        )
        batch_op.create_index(
            'ix_scheduled_games_pregame_observation',
            ['pregame_context_observation_id'],
        )


def downgrade():
    with op.batch_alter_table('scheduled_games') as batch_op:
        batch_op.drop_index('ix_scheduled_games_pregame_observation')
        batch_op.drop_index('ix_scheduled_games_away_probable_pitcher')
        batch_op.drop_index('ix_scheduled_games_home_probable_pitcher')
        batch_op.drop_index('ix_scheduled_games_next_pregame_poll_at')
        batch_op.drop_constraint('fk_scheduled_games_pregame_version', type_='foreignkey')
        batch_op.drop_constraint('fk_scheduled_games_pregame_observation', type_='foreignkey')
        batch_op.drop_column('pregame_policy_version')
        batch_op.drop_column('next_pregame_poll_at')
        batch_op.drop_column('pregame_context_updated_at')
        batch_op.drop_column('pregame_context_completeness')
        batch_op.drop_column('pregame_context_version')
        batch_op.drop_column('pregame_context_fingerprint')
        batch_op.drop_column('pregame_context_version_id')
        batch_op.drop_column('pregame_context_observation_id')
        batch_op.drop_column('away_probable_pitcher_name')
        batch_op.drop_column('home_probable_pitcher_name')
        batch_op.drop_column('away_probable_pitcher_mlb_id')
        batch_op.drop_column('home_probable_pitcher_mlb_id')

    op.drop_index(
        'ix_pregame_context_mutations_observation',
        table_name='pregame_context_mutations',
    )
    op.drop_index(
        'ix_pregame_context_mutations_team_date',
        table_name='pregame_context_mutations',
    )
    op.drop_index(
        'ix_pregame_context_mutations_game_date',
        table_name='pregame_context_mutations',
    )
    op.drop_table('pregame_context_mutations')
    op.drop_index(
        'ix_game_pregame_context_versions_baseball_date',
        table_name='game_pregame_context_versions',
    )
    op.drop_index(
        'ix_game_pregame_context_versions_observation',
        table_name='game_pregame_context_versions',
    )
    op.drop_index(
        'ix_game_pregame_context_versions_game_created',
        table_name='game_pregame_context_versions',
    )
    op.drop_table('game_pregame_context_versions')
