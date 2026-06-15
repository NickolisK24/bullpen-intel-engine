"""publish consistent sync dashboard snapshots

Revision ID: f2a9c7d1e8b5
Revises: e9a7c6d5b4f3
Create Date: 2026-06-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'f2a9c7d1e8b5'
down_revision = 'e9a7c6d5b4f3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('dashboard_snapshots', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_published', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('published_at', sa.DateTime(), nullable=True))
        batch_op.create_index(
            'ix_dashboard_snapshots_type_published',
            ['snapshot_type', 'is_published', 'status', 'payload_version'],
            unique=False,
        )

    connection = op.get_bind()
    latest_ready = connection.execute(sa.text("""
        SELECT snapshot_type, MAX(id) AS snapshot_id
        FROM dashboard_snapshots
        WHERE status = 'ready' AND payload_version = 1
        GROUP BY snapshot_type
    """)).fetchall()
    for row in latest_ready:
        connection.execute(
            sa.text("""
                UPDATE dashboard_snapshots
                SET is_published = 1,
                    published_at = COALESCE(snapshot_generated_at, created_at)
                WHERE id = :snapshot_id
            """),
            {'snapshot_id': row.snapshot_id},
        )

    with op.batch_alter_table('sync_runs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('stage', sa.String(length=50), nullable=False, server_default='completed'))
        batch_op.add_column(sa.Column('failed_stage', sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column('published_dashboard_snapshot_id', sa.Integer(), nullable=True))


def downgrade():
    with op.batch_alter_table('sync_runs', schema=None) as batch_op:
        batch_op.drop_column('published_dashboard_snapshot_id')
        batch_op.drop_column('failed_stage')
        batch_op.drop_column('stage')

    with op.batch_alter_table('dashboard_snapshots', schema=None) as batch_op:
        batch_op.drop_index('ix_dashboard_snapshots_type_published')
        batch_op.drop_column('published_at')
        batch_op.drop_column('is_published')
