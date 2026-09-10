"""add traffic evidence context

Revision ID: b2e7c4a9d1f3
Revises: a9e4c7d2f1b6
Create Date: 2026-07-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'b2e7c4a9d1f3'
down_revision = 'a9e4c7d2f1b6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('traffic_page_views', schema=None) as batch_op:
        batch_op.add_column(sa.Column('team_a_ref', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('team_b_ref', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('entry_source', sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column('evidence_target', sa.String(length=32), nullable=True))

    op.create_index(
        'ix_traffic_page_views_occurred_entry_source',
        'traffic_page_views',
        ['occurred_at', 'entry_source'],
    )
    op.create_index(
        'ix_traffic_page_views_occurred_evidence_target',
        'traffic_page_views',
        ['occurred_at', 'evidence_target'],
    )
    op.create_index(
        'ix_traffic_page_views_occurred_comparison_pair',
        'traffic_page_views',
        ['occurred_at', 'team_a_ref', 'team_b_ref'],
    )


def downgrade():
    op.drop_index('ix_traffic_page_views_occurred_comparison_pair', table_name='traffic_page_views')
    op.drop_index('ix_traffic_page_views_occurred_evidence_target', table_name='traffic_page_views')
    op.drop_index('ix_traffic_page_views_occurred_entry_source', table_name='traffic_page_views')

    with op.batch_alter_table('traffic_page_views', schema=None) as batch_op:
        batch_op.drop_column('evidence_target')
        batch_op.drop_column('entry_source')
        batch_op.drop_column('team_b_ref')
        batch_op.drop_column('team_a_ref')
