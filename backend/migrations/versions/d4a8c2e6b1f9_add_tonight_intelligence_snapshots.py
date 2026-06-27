"""add tonight intelligence snapshots

Revision ID: d4a8c2e6b1f9
Revises: c5b1e9a2f7d4
Create Date: 2026-06-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4a8c2e6b1f9'
down_revision = 'c5b1e9a2f7d4'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'tonight_intelligence_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reference_date', sa.Date(), nullable=False),
        sa.Column('snapshot_version', sa.String(length=40), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('response_json', sa.JSON(), nullable=False),
        sa.Column('card_count', sa.Integer(), nullable=False),
        sa.Column('empty_reason', sa.String(length=60), nullable=True),
        sa.Column('source', sa.String(length=40), nullable=False),
        sa.Column('generated_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'reference_date', 'snapshot_version',
            name='uq_tonight_intelligence_snapshots_date_version',
        ),
    )
    with op.batch_alter_table('tonight_intelligence_snapshots', schema=None) as batch_op:
        batch_op.create_index(
            'ix_tonight_intelligence_snapshots_version_date',
            ['snapshot_version', 'reference_date'], unique=False)
        batch_op.create_index(
            'ix_tonight_intelligence_snapshots_reference_date',
            ['reference_date'], unique=False)


def downgrade():
    with op.batch_alter_table('tonight_intelligence_snapshots', schema=None) as batch_op:
        batch_op.drop_index('ix_tonight_intelligence_snapshots_reference_date')
        batch_op.drop_index('ix_tonight_intelligence_snapshots_version_date')
    op.drop_table('tonight_intelligence_snapshots')
