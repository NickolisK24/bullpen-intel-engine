"""Retain a continuous candidate's dependency signature atomically.

Revision ID: b6c9d2e5f8a1
Revises: a5b8c1d4e7f0
"""
from alembic import op
import sqlalchemy as sa

revision = 'b6c9d2e5f8a1'
down_revision = 'a5b8c1d4e7f0'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('dashboard_snapshots', sa.Column('build_dependency_signature', sa.String(64)))


def downgrade():
    op.drop_column('dashboard_snapshots', 'build_dependency_signature')
