"""add pitcher hot filter indexes

Revision ID: d3b9a6f4c2e1
Revises: a4d7c9e2b6f1
Create Date: 2026-06-15 00:00:00.000000
"""

from alembic import op


revision = 'd3b9a6f4c2e1'
down_revision = 'a4d7c9e2b6f1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index(
        'ix_pitchers_team_active',
        'pitchers',
        ['team_id', 'active'],
        unique=False,
    )


def downgrade():
    op.drop_index('ix_pitchers_team_active', table_name='pitchers')
