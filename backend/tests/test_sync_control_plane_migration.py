import importlib.util
from datetime import datetime
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / 'migrations'
    / 'versions'
    / 'b5e7c1d9a4f2_add_sync_control_plane.py'
)


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        'sync_control_plane_migration', MIGRATION_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(connection, operation):
    module = _load_migration()
    module.op = Operations(MigrationContext.configure(connection))
    getattr(module, operation)()


def _legacy_schema(engine):
    metadata = sa.MetaData()
    sync_runs = sa.Table(
        'sync_runs',
        metadata,
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('job_name', sa.String(50), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
    )
    sa.Table(
        'sync_failures',
        metadata,
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('sync_run_id', sa.Integer(), nullable=True),
        sa.Column('resolved', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    metadata.create_all(engine)
    return sync_runs


def test_migration_is_additive_preserves_rows_and_downgrades():
    engine = sa.create_engine('sqlite:///:memory:')
    sync_runs = _legacy_schema(engine)

    with engine.begin() as connection:
        connection.execute(sync_runs.insert().values(
            id=7,
            job_name='existing_daily_sync',
            started_at=datetime(2026, 9, 4, 10, 0, 0),
        ))
        _run(connection, 'upgrade')

        inspector = sa.inspect(connection)
        run_columns = {column['name'] for column in inspector.get_columns('sync_runs')}
        failure_columns = {
            column['name'] for column in inspector.get_columns('sync_failures')
        }
        assert {
            'run_type', 'trigger_type', 'baseball_date', 'source_domain',
            'parent_sync_run_id', 'correlation_id', 'publication_id',
            'source_reads', 'source_changes', 'canonical_mutations',
            'affected_games', 'affected_teams', 'affected_pitchers',
            'downstream_work_created', 'warnings_count', 'zero_mutation',
            'outcome_json',
        } <= run_columns
        assert {'failure_class', 'stage', 'source_domain', 'retryable'} <= failure_columns
        assert 'sync_run_scopes' in inspector.get_table_names()

        existing = connection.execute(sa.text(
            'SELECT id, job_name, run_type, source_reads, canonical_mutations '
            'FROM sync_runs WHERE id = 7'
        )).one()
        assert tuple(existing) == (7, 'existing_daily_sync', None, 0, 0)

        _run(connection, 'downgrade')
        inspector = sa.inspect(connection)
        downgraded_columns = {
            column['name'] for column in inspector.get_columns('sync_runs')
        }
        assert 'run_type' not in downgraded_columns
        assert 'sync_run_scopes' not in inspector.get_table_names()
        assert connection.execute(
            sa.text('SELECT job_name FROM sync_runs WHERE id = 7')
        ).scalar_one() == 'existing_daily_sync'
