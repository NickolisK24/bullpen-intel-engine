import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


_MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / 'migrations'
    / 'versions'
    / 'd6b8f3a1c9e7_add_unknown_safe_boxscore_fields.py'
)


def _load_migration():
    spec = importlib.util.spec_from_file_location('boxscore_field_migration', _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run_upgrade(connection):
    module = _load_migration()
    context = MigrationContext.configure(connection)
    module.op = Operations(context)
    module.upgrade()


def _columns(connection):
    return {
        row._mapping['name']: row._mapping
        for row in connection.execute(sa.text('PRAGMA table_info(game_logs)'))
    }


def test_boxscore_field_migration_adds_nullable_columns_and_repairs_fabricated_zeroes():
    engine = sa.create_engine('sqlite:///:memory:')
    metadata = sa.MetaData()
    table = sa.Table(
        'game_logs',
        metadata,
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('inherited_runners', sa.Integer(), nullable=True, server_default=sa.text('0')),
        sa.Column('inherited_runners_scored', sa.Integer(), nullable=True, server_default=sa.text('0')),
        sa.Column('strikes', sa.Integer(), nullable=True),
        sa.Column('home_runs_allowed', sa.Integer(), nullable=True),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(table.insert(), [
            {
                'id': 1,
                'inherited_runners': 0,
                'inherited_runners_scored': 0,
                'strikes': 0,
                'home_runs_allowed': 0,
            },
            {
                'id': 2,
                'inherited_runners': 3,
                'inherited_runners_scored': 1,
                'strikes': 0,
                'home_runs_allowed': 0,
            },
        ])

        _run_upgrade(connection)

        columns = _columns(connection)
        for column_name in ('batters_faced', 'balls', 'games_finished'):
            assert column_name in columns
            assert columns[column_name]['notnull'] == 0
            assert columns[column_name]['dflt_value'] is None
        assert columns['inherited_runners']['notnull'] == 0
        assert columns['inherited_runners']['dflt_value'] is None
        assert columns['inherited_runners_scored']['notnull'] == 0
        assert columns['inherited_runners_scored']['dflt_value'] is None

        rows = [
            dict(row._mapping)
            for row in connection.execute(sa.text(
                'SELECT id, inherited_runners, inherited_runners_scored, '
                'strikes, home_runs_allowed '
                'FROM game_logs ORDER BY id'
            ))
        ]

    assert rows[0]['inherited_runners'] is None
    assert rows[0]['inherited_runners_scored'] is None
    assert rows[1]['inherited_runners'] == 3
    assert rows[1]['inherited_runners_scored'] == 1
    assert rows[0]['strikes'] == 0
    assert rows[0]['home_runs_allowed'] == 0
