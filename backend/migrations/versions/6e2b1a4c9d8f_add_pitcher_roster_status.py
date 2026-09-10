"""add pitcher roster status

Revision ID: 6e2b1a4c9d8f
Revises: 41f4f9a8d6c2
Create Date: 2026-06-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6e2b1a4c9d8f'
down_revision = '41f4f9a8d6c2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pitchers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('roster_status', sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column('roster_status_source', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('roster_status_updated_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('pitchers', schema=None) as batch_op:
        batch_op.drop_column('roster_status_updated_at')
        batch_op.drop_column('roster_status_source')
        batch_op.drop_column('roster_status')
