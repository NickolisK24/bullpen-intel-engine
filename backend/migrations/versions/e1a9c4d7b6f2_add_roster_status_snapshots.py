"""add roster status snapshots

Revision ID: e1a9c4d7b6f2
Revises: d6b8f3a1c9e7
Create Date: 2026-07-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'e1a9c4d7b6f2'
down_revision = 'd6b8f3a1c9e7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'roster_status_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('pitcher_id', sa.Integer(), nullable=False),
        sa.Column('mlb_id', sa.Integer(), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('snapshot_date', sa.Date(), nullable=False),
        sa.Column('roster_status', sa.String(length=30), nullable=False),
        sa.Column('active_roster', sa.Boolean(), nullable=True),
        sa.Column('forty_man_roster', sa.Boolean(), nullable=True),
        sa.Column('position_code', sa.String(length=10), nullable=True),
        sa.Column('position_name', sa.String(length=50), nullable=True),
        sa.Column('position_type', sa.String(length=30), nullable=True),
        sa.Column('two_way_eligible', sa.Boolean(), nullable=True),
        sa.Column('roster_status_raw', sa.String(length=100), nullable=True),
        sa.Column('roster_status_raw_code', sa.String(length=30), nullable=True),
        sa.Column('roster_status_raw_description', sa.String(length=100), nullable=True),
        sa.Column('source', sa.String(length=100), nullable=False),
        sa.Column('sync_run_id', sa.Integer(), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(), nullable=False),
        sa.Column('last_corrected_at', sa.DateTime(), nullable=True),
        sa.Column('correction_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('correction_source', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['pitcher_id'], ['pitchers.id']),
        sa.ForeignKeyConstraint(['sync_run_id'], ['sync_runs.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'pitcher_id',
            'snapshot_date',
            name='uq_roster_status_snapshots_pitcher_date',
        ),
    )
    op.create_index(
        'ix_roster_status_snapshots_mlb_date',
        'roster_status_snapshots',
        ['mlb_id', 'snapshot_date'],
        unique=False,
    )
    op.create_index(
        'ix_roster_status_snapshots_team_date',
        'roster_status_snapshots',
        ['team_id', 'snapshot_date'],
        unique=False,
    )


def downgrade():
    op.drop_index(
        'ix_roster_status_snapshots_team_date',
        table_name='roster_status_snapshots',
    )
    op.drop_index(
        'ix_roster_status_snapshots_mlb_date',
        table_name='roster_status_snapshots',
    )
    op.drop_table('roster_status_snapshots')
