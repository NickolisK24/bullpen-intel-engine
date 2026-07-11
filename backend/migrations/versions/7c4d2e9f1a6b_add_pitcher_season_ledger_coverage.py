"""add pitcher season ledger coverage

Revision ID: 7c4d2e9f1a6b
Revises: 2f7b9c1a5d43
Create Date: 2026-07-10 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '7c4d2e9f1a6b'
down_revision = '2f7b9c1a5d43'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'pitcher_season_ledger_coverage',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pitcher_id', sa.Integer(), nullable=False),
        sa.Column('pitcher_mlb_id', sa.Integer(), nullable=False),
        sa.Column('season', sa.Integer(), nullable=False),
        sa.Column('game_type', sa.String(length=2), nullable=False),
        sa.Column('target_game_pk', sa.Integer(), nullable=False),
        sa.Column('covered_through_date', sa.Date(), nullable=False),
        sa.Column('source_appearance_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('source_games_started_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('stored_appearance_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('stored_games_started_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('source_manifest_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('stored_manifest_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('coverage_status', sa.String(length=20), nullable=False, server_default='unknown'),
        sa.Column('reason_codes', sa.JSON(), nullable=False, server_default='[]'),
        sa.Column('verified_at', sa.DateTime(), nullable=False),
        sa.Column('sync_run_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "coverage_status IN ('complete', 'incomplete', 'unknown')",
            name='ck_pitcher_season_ledger_coverage_status',
        ),
        sa.ForeignKeyConstraint(['pitcher_id'], ['pitchers.id']),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'pitcher_id',
            'season',
            'game_type',
            'target_game_pk',
            name='uq_pitcher_season_ledger_coverage_target',
        ),
    )
    op.create_index(
        'ix_pitcher_season_ledger_coverage_lookup',
        'pitcher_season_ledger_coverage',
        ['pitcher_id', 'season', 'game_type', 'target_game_pk'],
        unique=False,
    )
    op.create_index(
        'ix_pitcher_season_ledger_coverage_status',
        'pitcher_season_ledger_coverage',
        ['coverage_status', 'covered_through_date'],
        unique=False,
    )


def downgrade():
    op.drop_index(
        'ix_pitcher_season_ledger_coverage_status',
        table_name='pitcher_season_ledger_coverage',
    )
    op.drop_index(
        'ix_pitcher_season_ledger_coverage_lookup',
        table_name='pitcher_season_ledger_coverage',
    )
    op.drop_table('pitcher_season_ledger_coverage')
