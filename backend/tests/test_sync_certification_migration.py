import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / 'migrations' / 'versions' / 'c9d4e6f8a1b2_add_sync_certification.py'
)


def _migration():
    spec = importlib.util.spec_from_file_location('sp14_migration', MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_certification_migration_upgrade_and_downgrade(monkeypatch):
    engine = sa.create_engine('sqlite:///:memory:')
    metadata = sa.MetaData()
    sa.Table('sync_runs', metadata, sa.Column('id', sa.Integer, primary_key=True))
    metadata.create_all(engine)
    migration = _migration()
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        monkeypatch.setattr(migration, 'op', operations)
        migration.upgrade()
        names = set(sa.inspect(connection).get_table_names())
        assert {
            'sync_certification_runs', 'sync_certification_checks',
            'sync_legacy_transition_states',
        } <= names
        migration.downgrade()
        names = set(sa.inspect(connection).get_table_names())
        assert 'sync_certification_runs' not in names
        assert 'sync_certification_checks' not in names
        assert 'sync_legacy_transition_states' not in names
