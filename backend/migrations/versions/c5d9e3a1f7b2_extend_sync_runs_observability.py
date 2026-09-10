"""extend sync_runs with pipeline observability columns

Adds job_name, records_failed, api_calls_made, and retries_used to the
existing sync_runs table so every sync job records partial-failure counts and
retry pressure alongside the durable run it already writes. The 'partial'
status is a new allowed value in the existing string column and needs no
schema change.

Revision ID: c5d9e3a1f7b2
Revises: b7e2a1c4f8d3
Create Date: 2026-06-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c5d9e3a1f7b2'
down_revision = 'b7e2a1c4f8d3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('sync_runs', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('job_name', sa.String(length=50), nullable=False,
                      server_default='daily_sync')
        )
        batch_op.add_column(sa.Column('records_failed', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('api_calls_made', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('retries_used', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('sync_runs', schema=None) as batch_op:
        batch_op.drop_column('retries_used')
        batch_op.drop_column('api_calls_made')
        batch_op.drop_column('records_failed')
        batch_op.drop_column('job_name')
