"""add pitcher raw roster status

Revision ID: 4b8d2f1a9c63
Revises: d3b9a6f4c2e1
Create Date: 2026-06-17 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = '4b8d2f1a9c63'
down_revision = 'd3b9a6f4c2e1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pitchers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('roster_status_raw_code', sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column('roster_status_raw_description', sa.String(length=100), nullable=True))


def downgrade():
    with op.batch_alter_table('pitchers', schema=None) as batch_op:
        batch_op.drop_column('roster_status_raw_description')
        batch_op.drop_column('roster_status_raw_code')
