"""WP-1: durable publication outcome on the owning sync run.

A Dashboard candidate withheld by the Team State publication proof is rolled
back with its publication transaction, so its evidence disappeared with it and
the run kept only a one-line reason. This adds one nullable JSON column,
``sync_runs.publication_outcome``, which the sync-completion path writes after
the publication transaction has settled, in its own commit.

Additive only: no existing row, column, index, constraint, function, trigger or
access-control setting changes. ``sync_runs`` already carries SEC-01 row level
security, which applies to the new column unchanged. Existing rows read NULL.

Revision ID: d4a8f2c6e9b3
Revises: e5b9c3a7d1f4
"""
from alembic import op
import sqlalchemy as sa


revision = 'd4a8f2c6e9b3'
down_revision = 'e5b9c3a7d1f4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('sync_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('publication_outcome', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('sync_runs', schema=None) as batch_op:
        batch_op.drop_column('publication_outcome')
