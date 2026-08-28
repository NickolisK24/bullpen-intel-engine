"""add persisted PBP observation order

Revision ID: b4e7c9d2a1f6
Revises: f1c2d3e4a5b6
Create Date: 2026-08-28 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'b4e7c9d2a1f6'
down_revision = 'f1c2d3e4a5b6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('play_by_play_processed_games', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'accepted_pitch_observation_sequence', sa.Integer(), nullable=True,
        ))
        batch_op.add_column(sa.Column(
            'accepted_pitch_source_authority', sa.String(length=100), nullable=True,
        ))


def downgrade():
    with op.batch_alter_table('play_by_play_processed_games', schema=None) as batch_op:
        batch_op.drop_column('accepted_pitch_source_authority')
        batch_op.drop_column('accepted_pitch_observation_sequence')
