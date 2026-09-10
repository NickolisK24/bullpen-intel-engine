"""add game log correction provenance

Revision ID: f6a2c9d8e1b3
Revises: e3b7a9c4d2f6
Create Date: 2026-07-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'f6a2c9d8e1b3'
down_revision = 'e3b7a9c4d2f6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('game_logs', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'stat_correction_count',
            sa.Integer(),
            nullable=False,
            server_default='0',
        ))
        batch_op.add_column(sa.Column(
            'last_stat_correction_at',
            sa.DateTime(),
            nullable=True,
        ))
        batch_op.add_column(sa.Column(
            'last_stat_correction_source',
            sa.String(length=40),
            nullable=True,
        ))
        batch_op.add_column(sa.Column(
            'last_stat_correction_sync_run_id',
            sa.Integer(),
            nullable=True,
        ))


def downgrade():
    with op.batch_alter_table('game_logs', schema=None) as batch_op:
        batch_op.drop_column('last_stat_correction_sync_run_id')
        batch_op.drop_column('last_stat_correction_source')
        batch_op.drop_column('last_stat_correction_at')
        batch_op.drop_column('stat_correction_count')
