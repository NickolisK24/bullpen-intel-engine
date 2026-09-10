import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / 'migrations' / 'versions' / 'e3f6a9b2d5c8_add_atomic_publications.py'
)


def _migration():
    spec = importlib.util.spec_from_file_location('atomic_publication_migration', MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_atomic_publication_migration_is_additive_and_round_trips():
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    for name in (
        'derived_intelligence_cohorts', 'derived_cohort_snapshots',
        'canonical_impact_plans', 'sync_runs',
    ):
        sa.Table(name, metadata, sa.Column('id', sa.Integer(), primary_key=True))
    metadata.create_all(engine)
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        operations = Operations(context)
        module = _migration()
        original = module.op
        module.op = operations
        try:
            module.upgrade()
            names = set(sa.inspect(connection).get_table_names())
            assert {
                'atomic_publications', 'atomic_publication_artifacts',
                'atomic_publication_current', 'atomic_publication_cache_handoffs',
            }.issubset(names)
            module.downgrade()
            names = set(sa.inspect(connection).get_table_names())
            assert 'atomic_publications' not in names
            assert {
                'derived_intelligence_cohorts', 'derived_cohort_snapshots',
                'canonical_impact_plans', 'sync_runs',
            }.issubset(names)
        finally:
            module.op = original
