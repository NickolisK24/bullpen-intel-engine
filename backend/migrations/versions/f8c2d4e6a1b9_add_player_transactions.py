"""add player transactions

Revision ID: f8c2d4e6a1b9
Revises: e1a9c4d7b6f2
Create Date: 2026-07-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'f8c2d4e6a1b9'
down_revision = 'e1a9c4d7b6f2'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'player_transactions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('transaction_key', sa.String(length=160), nullable=False),
        sa.Column('transaction_id', sa.String(length=80), nullable=True),
        sa.Column('pitcher_id', sa.Integer(), nullable=True),
        sa.Column('player_mlb_id', sa.Integer(), nullable=False),
        sa.Column('from_team_id', sa.Integer(), nullable=True),
        sa.Column('to_team_id', sa.Integer(), nullable=True),
        sa.Column('transaction_date', sa.Date(), nullable=False),
        sa.Column('effective_date', sa.Date(), nullable=True),
        sa.Column('resolution_date', sa.Date(), nullable=True),
        sa.Column('transaction_type_code', sa.String(length=40), nullable=True),
        sa.Column('normalized_category', sa.String(length=40), nullable=False),
        sa.Column('is_il_placement', sa.Boolean(), nullable=False),
        sa.Column('is_il_activation', sa.Boolean(), nullable=False),
        sa.Column('il_list_type', sa.String(length=20), nullable=True),
        sa.Column('retroactive_date', sa.Date(), nullable=True),
        sa.Column('roster_snapshot_alignment', sa.String(length=30), nullable=False),
        sa.Column('alignment_reason_code', sa.String(length=60), nullable=True),
        sa.Column('explanatory_linkage_eligible', sa.Boolean(), nullable=False),
        sa.Column('source', sa.String(length=100), nullable=False),
        sa.Column('source_endpoint', sa.String(length=100), nullable=False),
        sa.Column('source_query_start_date', sa.Date(), nullable=False),
        sa.Column('source_query_end_date', sa.Date(), nullable=False),
        sa.Column('sync_run_id', sa.Integer(), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(), nullable=False),
        sa.Column('last_corrected_at', sa.DateTime(), nullable=True),
        sa.Column('correction_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('correction_source', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "normalized_category IN ("
            "'recall', 'option', 'il_placement', 'il_activation', "
            "'roster_activation', 'roster_deactivation', 'trade', 'dfa', "
            "'outright', 'release', 'contract_selection', 'suspension', "
            "'bereavement', 'paternity', 'restricted', 'unknown')",
            name='ck_player_transactions_normalized_category',
        ),
        sa.CheckConstraint(
            "roster_snapshot_alignment IN ("
            "'aligned', 'misaligned', 'unknown', 'no_snapshot', 'not_applicable')",
            name='ck_player_transactions_roster_alignment',
        ),
        sa.ForeignKeyConstraint(['pitcher_id'], ['pitchers.id']),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'transaction_key',
            name='uq_player_transactions_transaction_key',
        ),
    )
    op.create_index(
        'ix_player_transactions_pitcher_date',
        'player_transactions',
        ['pitcher_id', 'transaction_date'],
        unique=False,
    )
    op.create_index(
        'ix_player_transactions_player_date',
        'player_transactions',
        ['player_mlb_id', 'transaction_date'],
        unique=False,
    )
    op.create_index(
        'ix_player_transactions_to_team_date',
        'player_transactions',
        ['to_team_id', 'transaction_date'],
        unique=False,
    )

    op.create_table(
        'player_transaction_sync_windows',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=100), nullable=False),
        sa.Column('source_endpoint', sa.String(length=100), nullable=False),
        sa.Column('source_query_start_date', sa.Date(), nullable=False),
        sa.Column('source_query_end_date', sa.Date(), nullable=False),
        sa.Column('attempted_at', sa.DateTime(), nullable=False),
        sa.Column('successful_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('records_fetched', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('records_stored', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('records_created', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('records_corrected', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('records_unchanged', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('unknown_type_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('alignment_unknown_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('alignment_misaligned_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('alignment_no_snapshot_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('records_failed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sync_run_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_player_transaction_sync_windows_query_end',
        'player_transaction_sync_windows',
        ['source_query_end_date', 'attempted_at'],
        unique=False,
    )
    op.create_index(
        'ix_player_transaction_sync_windows_status',
        'player_transaction_sync_windows',
        ['status', 'attempted_at'],
        unique=False,
    )


def downgrade():
    op.drop_index(
        'ix_player_transaction_sync_windows_status',
        table_name='player_transaction_sync_windows',
    )
    op.drop_index(
        'ix_player_transaction_sync_windows_query_end',
        table_name='player_transaction_sync_windows',
    )
    op.drop_table('player_transaction_sync_windows')
    op.drop_index(
        'ix_player_transactions_to_team_date',
        table_name='player_transactions',
    )
    op.drop_index(
        'ix_player_transactions_player_date',
        table_name='player_transactions',
    )
    op.drop_index(
        'ix_player_transactions_pitcher_date',
        table_name='player_transactions',
    )
    op.drop_table('player_transactions')
