"""add pitcher team assignment authority

Revision ID: a83d4f6b9c21
Revises: 6e2b1a4c9d8f
Create Date: 2026-06-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a83d4f6b9c21'
down_revision = '6e2b1a4c9d8f'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('pitchers', schema=None) as batch_op:
        batch_op.add_column(sa.Column('team_assignment_status', sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column('team_assignment_source', sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column('team_assignment_updated_at', sa.DateTime(), nullable=True))
        batch_op.alter_column('team_id', existing_type=sa.Integer(), nullable=True)


def downgrade():
    op.execute("UPDATE pitchers SET team_id = 0 WHERE team_id IS NULL")
    with op.batch_alter_table('pitchers', schema=None) as batch_op:
        batch_op.alter_column('team_id', existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column('team_assignment_updated_at')
        batch_op.drop_column('team_assignment_source')
        batch_op.drop_column('team_assignment_status')
