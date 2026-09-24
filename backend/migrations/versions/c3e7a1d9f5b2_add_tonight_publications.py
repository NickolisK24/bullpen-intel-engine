"""Add publication-bound, immutable Tonight v1 read-model rows.

Additive only: a new table. The legacy ``tonight_intelligence_snapshots``
table and its rows are untouched.

Revision ID: c3e7a1d9f5b2
Revises: b6c9d2e5f8a1
"""
from alembic import op
import sqlalchemy as sa

revision = 'c3e7a1d9f5b2'
down_revision = 'b6c9d2e5f8a1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'tonight_publications',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('contract', sa.String(40), nullable=False),
        sa.Column('reference_date', sa.Date(), nullable=False),
        sa.Column(
            'dashboard_snapshot_id', sa.Integer(),
            sa.ForeignKey('dashboard_snapshots.id'), nullable=False,
        ),
        sa.Column('sync_run_id', sa.Integer(), nullable=True),
        sa.Column('data_through', sa.Date(), nullable=False),
        sa.Column('availability_reference_date', sa.Date(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('content_sha256', sa.String(64), nullable=False),
        sa.Column('generated_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            'reference_date', 'dashboard_snapshot_id', 'contract',
            name='uq_tonight_publications_identity',
        ),
    )
    op.create_index(
        'ix_tonight_publications_contract', 'tonight_publications', ['contract'],
    )
    op.create_index(
        'ix_tonight_publications_reference_date', 'tonight_publications',
        ['reference_date'],
    )
    op.create_index(
        'ix_tonight_publications_dashboard_snapshot_id', 'tonight_publications',
        ['dashboard_snapshot_id'],
    )


def downgrade():
    op.drop_index('ix_tonight_publications_dashboard_snapshot_id', 'tonight_publications')
    op.drop_index('ix_tonight_publications_reference_date', 'tonight_publications')
    op.drop_index('ix_tonight_publications_contract', 'tonight_publications')
    op.drop_table('tonight_publications')
