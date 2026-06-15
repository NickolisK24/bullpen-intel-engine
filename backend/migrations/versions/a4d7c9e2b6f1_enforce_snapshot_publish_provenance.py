"""enforce snapshot publish provenance

Revision ID: a4d7c9e2b6f1
Revises: f2a9c7d1e8b5
Create Date: 2026-06-15 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = 'a4d7c9e2b6f1'
down_revision = 'f2a9c7d1e8b5'
branch_labels = None
depends_on = None


PUBLISHED_REQUIRES_SYNC_RUN = (
    'is_published IS NOT TRUE OR sync_run_id IS NOT NULL'
)


def _row_value(row, key):
    try:
        return row._mapping[key]
    except AttributeError:
        return getattr(row, key)


def _repair_published_snapshot_provenance(connection):
    snapshot_types = connection.execute(sa.text("""
        SELECT DISTINCT snapshot_type
        FROM dashboard_snapshots
        WHERE is_published IS TRUE
          AND sync_run_id IS NULL
    """)).fetchall()

    for row in snapshot_types:
        snapshot_type = _row_value(row, 'snapshot_type')
        candidate = connection.execute(
            sa.text("""
                SELECT id
                FROM dashboard_snapshots
                WHERE snapshot_type = :snapshot_type
                  AND status = 'ready'
                  AND payload_version = 1
                  AND sync_run_id IS NOT NULL
                ORDER BY snapshot_generated_at DESC NULLS LAST, id DESC
                LIMIT 1
            """),
            {'snapshot_type': snapshot_type},
        ).fetchone()
        if candidate is None:
            raise RuntimeError(
                'Cannot enforce published snapshot provenance: '
                f'no sync-authored ready snapshot exists for {snapshot_type}.'
            )

        snapshot_id = _row_value(candidate, 'id')
        connection.execute(
            sa.text("""
                UPDATE dashboard_snapshots
                SET is_published = false
                WHERE snapshot_type = :snapshot_type
                  AND is_published IS TRUE
            """),
            {'snapshot_type': snapshot_type},
        )
        connection.execute(
            sa.text("""
                UPDATE dashboard_snapshots
                SET is_published = true,
                    status = 'ready',
                    published_at = COALESCE(
                        published_at,
                        snapshot_generated_at,
                        created_at,
                        CURRENT_TIMESTAMP
                    )
                WHERE id = :snapshot_id
            """),
            {'snapshot_id': snapshot_id},
        )


def _repair_dangling_sync_pointers(connection):
    dangling = connection.execute(sa.text("""
        SELECT sr.id AS sync_run_id,
               sr.published_dashboard_snapshot_id AS dangling_snapshot_id,
               ds.snapshot_type AS snapshot_type
        FROM sync_runs sr
        JOIN dashboard_snapshots ds
          ON ds.id = sr.published_dashboard_snapshot_id
        WHERE sr.published_dashboard_snapshot_id IS NOT NULL
          AND ds.is_published IS NOT TRUE
    """)).fetchall()

    for row in dangling:
        snapshot_type = _row_value(row, 'snapshot_type')
        replacement = connection.execute(
            sa.text("""
                SELECT id
                FROM dashboard_snapshots
                WHERE snapshot_type = :snapshot_type
                  AND is_published IS TRUE
                  AND sync_run_id IS NOT NULL
                ORDER BY published_at DESC NULLS LAST,
                         snapshot_generated_at DESC NULLS LAST,
                         id DESC
                LIMIT 1
            """),
            {'snapshot_type': snapshot_type},
        ).fetchone()
        if replacement is None:
            raise RuntimeError(
                'Cannot repair dangling sync snapshot pointer: '
                f'no published sync-authored snapshot exists for {snapshot_type}.'
            )

        connection.execute(
            sa.text("""
                UPDATE sync_runs
                SET published_dashboard_snapshot_id = :snapshot_id
                WHERE id = :sync_run_id
            """),
            {
                'sync_run_id': _row_value(row, 'sync_run_id'),
                'snapshot_id': _row_value(replacement, 'id'),
            },
        )


def upgrade():
    connection = op.get_bind()
    _repair_published_snapshot_provenance(connection)
    _repair_dangling_sync_pointers(connection)
    connection.execute(sa.text("""
        UPDATE sync_runs
        SET stage = 'legacy_completed_without_publish'
        WHERE status IN ('success', 'partial')
          AND stage = 'completed'
          AND published_dashboard_snapshot_id IS NULL
    """))

    with op.batch_alter_table('dashboard_snapshots', schema=None) as batch_op:
        batch_op.create_check_constraint(
            'ck_dashboard_snapshots_published_requires_sync_run',
            PUBLISHED_REQUIRES_SYNC_RUN,
        )


def downgrade():
    with op.batch_alter_table('dashboard_snapshots', schema=None) as batch_op:
        batch_op.drop_constraint(
            'ck_dashboard_snapshots_published_requires_sync_run',
            type_='check',
        )
