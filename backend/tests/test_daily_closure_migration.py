import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa


MIGRATION_PATH = Path(__file__).resolve().parents[1] / 'migrations' / 'versions' / 'f1a4c8d2e6b9_add_daily_closure.py'


def test_daily_closure_migration_is_additive_and_round_trips():
    spec = importlib.util.spec_from_file_location('daily_closure_migration', MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    for name in ('atomic_publications', 'sync_runs'):
        sa.Table(name, metadata, sa.Column('id', sa.Integer(), primary_key=True))
    metadata.create_all(engine)
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        original = module.op
        module.op = operations
        try:
            module.upgrade()
            names = set(sa.inspect(connection).get_table_names())
            assert {
                'baseball_date_closures', 'baseball_date_closure_versions',
                'baseball_date_closure_blockers',
            }.issubset(names)
            module.downgrade()
            names = set(sa.inspect(connection).get_table_names())
            assert 'baseball_date_closures' not in names
            assert {'atomic_publications', 'sync_runs'}.issubset(names)
        finally:
            module.op = original
