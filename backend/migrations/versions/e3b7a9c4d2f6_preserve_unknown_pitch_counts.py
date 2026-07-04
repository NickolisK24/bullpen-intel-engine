"""preserve unknown pitch counts

Revision ID: e3b7a9c4d2f6
Revises: d4a8c2e6b1f9
Create Date: 2026-07-03 22:20:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'e3b7a9c4d2f6'
down_revision = 'd4a8c2e6b1f9'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('game_logs', schema=None) as batch_op:
        batch_op.alter_column(
            'pitches_thrown',
            existing_type=sa.Integer(),
            nullable=True,
            server_default=None,
            existing_nullable=True,
        )


def downgrade():
    with op.batch_alter_table('game_logs', schema=None) as batch_op:
        batch_op.alter_column(
            'pitches_thrown',
            existing_type=sa.Integer(),
            nullable=True,
            server_default=sa.text('0'),
            existing_nullable=True,
        )
