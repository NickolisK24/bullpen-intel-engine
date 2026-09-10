"""add share story context

Revision ID: d7e4f1a8c2b6
Revises: c4f8a2d6e9b3
Create Date: 2026-07-16 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'd7e4f1a8c2b6'
down_revision = 'c4f8a2d6e9b3'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'traffic_share_actions',
        sa.Column('card_version', sa.String(length=32), nullable=True),
    )
    op.add_column(
        'traffic_share_actions',
        sa.Column('story_angle', sa.String(length=48), nullable=True),
    )
    op.create_index(
        'ix_traffic_share_actions_occurred_card_version',
        'traffic_share_actions',
        ['occurred_at', 'card_version'],
    )
    op.create_index(
        'ix_traffic_share_actions_occurred_story_angle',
        'traffic_share_actions',
        ['occurred_at', 'story_angle'],
    )


def downgrade():
    op.drop_index('ix_traffic_share_actions_occurred_story_angle', table_name='traffic_share_actions')
    op.drop_index('ix_traffic_share_actions_occurred_card_version', table_name='traffic_share_actions')
    op.drop_column('traffic_share_actions', 'story_angle')
    op.drop_column('traffic_share_actions', 'card_version')
