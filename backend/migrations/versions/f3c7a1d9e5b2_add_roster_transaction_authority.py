"""add roster and transaction authority history

Revision ID: f3c7a1d9e5b2
Revises: e8b4f1a2c6d9
Create Date: 2026-09-07
"""

from alembic import op
import sqlalchemy as sa


revision = 'f3c7a1d9e5b2'
down_revision = 'e8b4f1a2c6d9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('player_transactions') as batch_op:
        batch_op.add_column(sa.Column('transaction_type_description', sa.String(255)))
        batch_op.add_column(sa.Column('source_observation_id', sa.Integer()))
        batch_op.add_column(sa.Column(
            'current_version_number', sa.Integer(), nullable=False, server_default='0',
        ))
        batch_op.create_foreign_key(
            'fk_player_transactions_source_observation',
            'source_observations',
            ['source_observation_id'],
            ['id'],
            ondelete='SET NULL',
        )

    with op.batch_alter_table('roster_status_snapshots') as batch_op:
        batch_op.add_column(sa.Column('active_roster_observation_id', sa.Integer()))
        batch_op.add_column(sa.Column('forty_man_roster_observation_id', sa.Integer()))
        batch_op.create_foreign_key(
            'fk_roster_status_snapshots_active_observation',
            'source_observations',
            ['active_roster_observation_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_foreign_key(
            'fk_roster_status_snapshots_forty_man_observation',
            'source_observations',
            ['forty_man_roster_observation_id'],
            ['id'],
            ondelete='SET NULL',
        )

    op.create_table(
        'roster_membership_intervals',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('pitcher_id', sa.Integer(), nullable=False),
        sa.Column('player_mlb_id', sa.Integer(), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('organization_id', sa.Integer()),
        sa.Column('membership_type', sa.String(30), nullable=False),
        sa.Column('effective_start_date', sa.Date(), nullable=False),
        sa.Column('effective_start_at', sa.DateTime()),
        sa.Column('effective_end_date', sa.Date()),
        sa.Column('effective_end_at', sa.DateTime()),
        sa.Column('start_precision', sa.String(20), nullable=False, server_default='date'),
        sa.Column('end_precision', sa.String(20)),
        sa.Column('authority_type', sa.String(60), nullable=False),
        sa.Column('opened_by_observation_id', sa.Integer(), nullable=False),
        sa.Column('closed_by_observation_id', sa.Integer()),
        sa.Column('opened_by_transaction_id', sa.Integer()),
        sa.Column('closed_by_transaction_id', sa.Integer()),
        sa.Column('is_current_version', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('supersedes_interval_id', sa.Integer()),
        sa.Column('correction_reason', sa.String(255)),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['pitcher_id'], ['pitchers.id']),
        sa.ForeignKeyConstraint(
            ['opened_by_observation_id'], ['source_observations.id'], ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['closed_by_observation_id'], ['source_observations.id'], ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['opened_by_transaction_id'], ['player_transactions.id'], ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['closed_by_transaction_id'], ['player_transactions.id'], ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['supersedes_interval_id'], ['roster_membership_intervals.id'], ondelete='RESTRICT',
        ),
        sa.CheckConstraint(
            "membership_type IN ('active_roster', 'forty_man_roster', "
            "'organization', 'minor_assignment', 'public_inactive', "
            "'rehab_assignment')",
            name='ck_roster_membership_intervals_type',
        ),
        sa.CheckConstraint(
            "start_precision IN ('date', 'timestamp') AND "
            "(end_precision IS NULL OR end_precision IN ('date', 'timestamp'))",
            name='ck_roster_membership_intervals_precision',
        ),
        sa.CheckConstraint(
            'effective_end_date IS NULL OR effective_end_date >= effective_start_date',
            name='ck_roster_membership_intervals_date_order',
        ),
    )
    op.create_index(
        'uq_roster_membership_intervals_current_open_player_type',
        'roster_membership_intervals',
        ['pitcher_id', 'membership_type'],
        unique=True,
        postgresql_where=sa.text(
            'effective_end_date IS NULL AND is_current_version = true'
        ),
        sqlite_where=sa.text(
            'effective_end_date IS NULL AND is_current_version = 1'
        ),
    )
    op.create_index(
        'ix_roster_membership_intervals_team_type_open',
        'roster_membership_intervals',
        ['team_id', 'membership_type', 'effective_end_date'],
    )
    op.create_index(
        'ix_roster_membership_intervals_pitcher_dates',
        'roster_membership_intervals',
        ['pitcher_id', 'effective_start_date', 'effective_end_date'],
    )
    op.create_index(
        'ix_roster_membership_intervals_opened_observation',
        'roster_membership_intervals', ['opened_by_observation_id'],
    )
    op.create_index(
        'ix_roster_membership_intervals_closed_observation',
        'roster_membership_intervals', ['closed_by_observation_id'],
    )

    op.create_table(
        'roster_membership_mutations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('interval_id', sa.Integer(), nullable=False),
        sa.Column('pitcher_id', sa.Integer(), nullable=False),
        sa.Column('player_mlb_id', sa.Integer(), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('membership_type', sa.String(30), nullable=False),
        sa.Column('mutation_type', sa.String(30), nullable=False),
        sa.Column('baseball_date', sa.Date(), nullable=False),
        sa.Column('effective_at', sa.DateTime()),
        sa.Column('precision', sa.String(20), nullable=False, server_default='date'),
        sa.Column('source_observation_id', sa.Integer(), nullable=False),
        sa.Column('player_transaction_id', sa.Integer()),
        sa.Column('sync_run_id', sa.Integer()),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['interval_id'], ['roster_membership_intervals.id'], ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(['pitcher_id'], ['pitchers.id']),
        sa.ForeignKeyConstraint(
            ['source_observation_id'], ['source_observations.id'], ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['player_transaction_id'], ['player_transactions.id'], ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id'], ondelete='SET NULL'),
        sa.CheckConstraint(
            "mutation_type IN ('membership_opened', 'membership_closed', "
            "'membership_corrected')",
            name='ck_roster_membership_mutations_type',
        ),
    )
    op.create_index(
        'ix_roster_membership_mutations_team_date',
        'roster_membership_mutations', ['team_id', 'baseball_date'],
    )
    op.create_index(
        'ix_roster_membership_mutations_pitcher_date',
        'roster_membership_mutations', ['pitcher_id', 'baseball_date'],
    )
    op.create_index(
        'ix_roster_membership_mutations_observation',
        'roster_membership_mutations', ['source_observation_id'],
    )

    op.create_table(
        'player_transaction_versions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('player_transaction_id', sa.Integer(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('predecessor_version_id', sa.Integer()),
        sa.Column('source_observation_id', sa.Integer()),
        sa.Column('fact_fingerprint', sa.String(64), nullable=False),
        sa.Column('fact_schema_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('fact_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ['player_transaction_id'], ['player_transactions.id'], ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['predecessor_version_id'], ['player_transaction_versions.id'], ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['source_observation_id'], ['source_observations.id'], ondelete='RESTRICT',
        ),
        sa.UniqueConstraint(
            'player_transaction_id', 'version_number',
            name='uq_player_transaction_versions_transaction_version',
        ),
        sa.UniqueConstraint(
            'player_transaction_id', 'fact_fingerprint',
            name='uq_player_transaction_versions_transaction_fingerprint',
        ),
        sa.CheckConstraint(
            'version_number > 0', name='ck_player_transaction_versions_number',
        ),
    )
    op.create_index(
        'ix_player_transaction_versions_observation',
        'player_transaction_versions', ['source_observation_id'],
    )


def downgrade():
    op.drop_index(
        'ix_player_transaction_versions_observation',
        table_name='player_transaction_versions',
    )
    op.drop_table('player_transaction_versions')
    op.drop_index(
        'ix_roster_membership_mutations_observation',
        table_name='roster_membership_mutations',
    )
    op.drop_index(
        'ix_roster_membership_mutations_pitcher_date',
        table_name='roster_membership_mutations',
    )
    op.drop_index(
        'ix_roster_membership_mutations_team_date',
        table_name='roster_membership_mutations',
    )
    op.drop_table('roster_membership_mutations')
    op.drop_index(
        'ix_roster_membership_intervals_closed_observation',
        table_name='roster_membership_intervals',
    )
    op.drop_index(
        'ix_roster_membership_intervals_opened_observation',
        table_name='roster_membership_intervals',
    )
    op.drop_index(
        'ix_roster_membership_intervals_pitcher_dates',
        table_name='roster_membership_intervals',
    )
    op.drop_index(
        'ix_roster_membership_intervals_team_type_open',
        table_name='roster_membership_intervals',
    )
    op.drop_index(
        'uq_roster_membership_intervals_current_open_player_type',
        table_name='roster_membership_intervals',
    )
    op.drop_table('roster_membership_intervals')

    with op.batch_alter_table('roster_status_snapshots') as batch_op:
        batch_op.drop_constraint(
            'fk_roster_status_snapshots_forty_man_observation', type_='foreignkey',
        )
        batch_op.drop_constraint(
            'fk_roster_status_snapshots_active_observation', type_='foreignkey',
        )
        batch_op.drop_column('forty_man_roster_observation_id')
        batch_op.drop_column('active_roster_observation_id')

    with op.batch_alter_table('player_transactions') as batch_op:
        batch_op.drop_constraint(
            'fk_player_transactions_source_observation', type_='foreignkey',
        )
        batch_op.drop_column('current_version_number')
        batch_op.drop_column('source_observation_id')
        batch_op.drop_column('transaction_type_description')
