import importlib.util
from datetime import date, datetime
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / 'migrations'
    / 'versions'
    / 'c4f8a2d7e6b1_add_durable_sync_job_queue.py'
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        'durable_sync_job_queue_migration', MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(connection, operation):
    module = _load_migration()
    module.op = Operations(MigrationContext.configure(connection))
    getattr(module, operation)()


def _current_schema(engine):
    metadata = sa.MetaData()
    sa.Table(
        'sync_runs',
        metadata,
        sa.Column('id', sa.Integer(), primary_key=True),
    )
    jobs = sa.Table(
        'sync_jobs',
        metadata,
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('job_name', sa.String(80), nullable=False),
        sa.Column('job_family', sa.String(50), nullable=False),
        sa.Column('lane', sa.String(50), nullable=False),
        sa.Column('scope_key', sa.String(160), nullable=False),
        sa.Column('product_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('started_at', sa.DateTime()),
        sa.Column('completed_at', sa.DateTime()),
        sa.Column('last_heartbeat_at', sa.DateTime()),
        sa.Column('duration_ms', sa.Integer()),
        sa.Column('error_message', sa.Text()),
        sa.Column('error_type', sa.String(120)),
        sa.Column('details_json', sa.JSON()),
        sa.Column('sync_run_id', sa.Integer(), sa.ForeignKey('sync_runs.id')),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            'job_name', 'scope_key', 'product_date',
            name='uq_sync_jobs_name_scope_date',
        ),
    )
    metadata.create_all(engine)
    return jobs


def test_migration_preserves_existing_jobs_and_round_trips():
    engine = sa.create_engine('sqlite:///:memory:')
    jobs = _current_schema(engine)
    now = datetime(2026, 9, 5, 12, 0, 0)

    with engine.begin() as connection:
        connection.execute(jobs.insert().values(
            id=9,
            job_name='workload_evidence',
            job_family='phase0d_evidence',
            lane='internal',
            scope_key='product_date:2026-09-05',
            product_date=date(2026, 9, 5),
            status='succeeded',
            attempts=1,
            max_attempts=3,
            created_at=now,
            updated_at=now,
        ))
        _run(connection, 'upgrade')

        inspector = sa.inspect(connection)
        columns = {row['name'] for row in inspector.get_columns('sync_jobs')}
        assert {
            'scope_type', 'payload_schema_version', 'dedupe_key', 'priority',
            'first_available_at', 'available_at', 'claimed_at', 'lease_until', 'worker_id',
            'claim_token', 'dead_at', 'result_json', 'parent_job_id',
        } <= columns
        assert 'sync_job_attempts' in inspector.get_table_names()
        indexes = {row['name'] for row in inspector.get_indexes('sync_jobs')}
        assert {
            'ix_sync_jobs_claim_ready',
            'ix_sync_jobs_lease_expiry',
            'uq_sync_jobs_active_dedupe_key',
        } <= indexes

        preserved = connection.execute(sa.text(
            'SELECT id, job_name, status, attempts, priority, dedupe_key '
            'FROM sync_jobs WHERE id = 9'
        )).one()
        assert tuple(preserved) == (
            9, 'workload_evidence', 'succeeded', 1, 100, None,
        )

        _run(connection, 'downgrade')
        inspector = sa.inspect(connection)
        assert 'sync_job_attempts' not in inspector.get_table_names()
        assert 'dedupe_key' not in {
            row['name'] for row in inspector.get_columns('sync_jobs')
        }
        assert connection.execute(sa.text(
            'SELECT job_name FROM sync_jobs WHERE id = 9'
        )).scalar_one() == 'workload_evidence'
