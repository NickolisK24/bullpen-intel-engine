"""add traffic share actions

Revision ID: c4f8a2d6e9b3
Revises: b2e7c4a9d1f3
Create Date: 2026-07-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'c4f8a2d6e9b3'
down_revision = 'b2e7c4a9d1f3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'traffic_share_actions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.String(length=36), nullable=False),
        sa.Column('visitor_id', sa.String(length=36), nullable=False),
        sa.Column('session_id', sa.String(length=36), nullable=False),
        sa.Column('occurred_at', sa.DateTime(), nullable=False),
        sa.Column('surface', sa.String(length=32), nullable=False),
        sa.Column('card_type', sa.String(length=16), nullable=False),
        sa.Column('action', sa.String(length=24), nullable=False),
        sa.Column('team_ref', sa.String(length=16), nullable=True),
        sa.Column('team_a_ref', sa.String(length=16), nullable=True),
        sa.Column('team_b_ref', sa.String(length=16), nullable=True),
        sa.Column('evidence_target', sa.String(length=32), nullable=True),
        sa.Column('data_through', sa.Date(), nullable=True),
        sa.Column('site_host', sa.String(length=253), nullable=False),
        sa.Column('device_class', sa.String(length=16), nullable=False),
        sa.Column('is_bot', sa.Boolean(), nullable=False),
        sa.Column('schema_version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_traffic_share_actions_event_id', 'traffic_share_actions', ['event_id'], unique=True)
    op.create_index('ix_traffic_share_actions_occurred_at', 'traffic_share_actions', ['occurred_at'])
    op.create_index(
        'ix_traffic_share_actions_occurred_action', 'traffic_share_actions', ['occurred_at', 'action'],
    )
    op.create_index(
        'ix_traffic_share_actions_occurred_card_type', 'traffic_share_actions', ['occurred_at', 'card_type'],
    )
    op.create_index(
        'ix_traffic_share_actions_occurred_team', 'traffic_share_actions', ['occurred_at', 'team_ref'],
    )
    op.create_index(
        'ix_traffic_share_actions_occurred_comparison_pair',
        'traffic_share_actions',
        ['occurred_at', 'team_a_ref', 'team_b_ref'],
    )


def downgrade():
    op.drop_table('traffic_share_actions')
