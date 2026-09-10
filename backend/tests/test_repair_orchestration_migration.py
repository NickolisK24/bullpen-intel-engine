import importlib.util
from pathlib import Path

import sqlalchemy as sa


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / 'migrations' / 'versions' / 'b7d3e9f1a5c2_add_repair_orchestration.py'
)


def _migration():
    spec = importlib.util.spec_from_file_location('sp13_migration', MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_repair_migration_upgrade_and_downgrade(monkeypatch):
    engine = sa.create_engine('sqlite:///:memory:')
    metadata = sa.MetaData()
    sa.Table('sync_runs', metadata, sa.Column('id', sa.Integer, primary_key=True))
    sa.Table('sync_jobs', metadata, sa.Column('id', sa.Integer, primary_key=True))
    sa.Table(
        'canonical_impact_plans', metadata,
        sa.Column('id', sa.Integer, primary_key=True),
    )
    metadata.create_all(engine)
    migration = _migration()
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        monkeypatch.setattr(migration, 'op', operations)
        migration.upgrade()
        names = set(sa.inspect(connection).get_table_names())
        assert {'repair_requests', 'repair_request_chunks', 'repair_request_blockers'} <= names
        columns = {row['name'] for row in sa.inspect(connection).get_columns('canonical_impact_plans')}
        assert {'repair_request_id', 'replay_kind', 'method_versions_override_json', 'publication_mode'} <= columns
        migration.downgrade()
        names = set(sa.inspect(connection).get_table_names())
        assert 'repair_requests' not in names
        columns = {row['name'] for row in sa.inspect(connection).get_columns('canonical_impact_plans')}
        assert 'repair_request_id' not in columns
