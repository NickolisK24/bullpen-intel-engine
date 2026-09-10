import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import sqlalchemy as sa


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / 'migrations' / 'versions' / 'd2e5f8a1c4b7_add_derived_intelligence_cohorts.py'
)


def _migration():
    spec = importlib.util.spec_from_file_location('derived_cohort_migration', MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_derived_cohort_migration_is_additive_and_round_trips():
    engine = sa.create_engine('sqlite://')
    metadata = sa.MetaData()
    for name in ('canonical_impact_plans', 'sync_runs', 'sync_jobs', 'source_observations'):
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
                'derived_intelligence_cohorts', 'derived_intelligence_cohort_domains',
                'derived_cohort_inputs', 'derived_cohort_snapshots',
            }.issubset(names)
            module.downgrade()
            names = set(sa.inspect(connection).get_table_names())
            assert 'derived_intelligence_cohorts' not in names
            assert {'canonical_impact_plans', 'sync_runs', 'sync_jobs', 'source_observations'}.issubset(names)
        finally:
            module.op = original
