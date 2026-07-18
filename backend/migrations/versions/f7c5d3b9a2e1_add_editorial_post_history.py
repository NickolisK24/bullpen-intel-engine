"""add editorial post history

Revision ID: f7c5d3b9a2e1
Revises: e6b4c2a8d1f3
Create Date: 2026-07-18
"""

from alembic import op
import sqlalchemy as sa


revision = 'f7c5d3b9a2e1'
down_revision = 'e6b4c2a8d1f3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'editorial_post_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('story_shape', sa.String(length=20), nullable=False),
        sa.Column('posted_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('editorial_post_history', schema=None) as batch_op:
        batch_op.create_index(
            'ix_editorial_post_history_team_posted',
            ['team_id', 'posted_at'],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table('editorial_post_history', schema=None) as batch_op:
        batch_op.drop_index('ix_editorial_post_history_team_posted')
    op.drop_table('editorial_post_history')
