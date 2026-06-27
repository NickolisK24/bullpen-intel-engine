"""add intelligence surface snapshots

Revision ID: a7f2c1d4e9b6
Revises: b9e4c1f7a2d6
Create Date: 2026-06-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a7f2c1d4e9b6'
down_revision = 'b9e4c1f7a2d6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'intelligence_surface_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reference_date', sa.Date(), nullable=False),
        sa.Column('snapshot_version', sa.String(length=40), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('response_json', sa.JSON(), nullable=False),
        sa.Column('lead_story_team_id', sa.Integer(), nullable=True),
        sa.Column('lead_story_game_pk', sa.Integer(), nullable=True),
        sa.Column('candidates_considered', sa.Integer(), nullable=False),
        sa.Column('publishable_candidates', sa.Integer(), nullable=False),
        sa.Column('empty_reason', sa.String(length=60), nullable=True),
        sa.Column('errors', sa.Integer(), nullable=False),
        sa.Column('source', sa.String(length=40), nullable=False),
        sa.Column('generated_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'reference_date', 'snapshot_version',
            name='uq_intelligence_surface_snapshots_date_version',
        ),
    )
    with op.batch_alter_table('intelligence_surface_snapshots', schema=None) as batch_op:
        batch_op.create_index(
            'ix_intelligence_surface_snapshots_version_date',
            ['snapshot_version', 'reference_date'],
            unique=False,
        )


def downgrade():
    with op.batch_alter_table('intelligence_surface_snapshots', schema=None) as batch_op:
        batch_op.drop_index('ix_intelligence_surface_snapshots_version_date')
    op.drop_table('intelligence_surface_snapshots')
