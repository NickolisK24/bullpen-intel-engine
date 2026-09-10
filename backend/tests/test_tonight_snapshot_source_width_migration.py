"""The widening migration, proven against PostgreSQL enforcing each schema.

A Python-side length check cannot prove this migration. The production failure
was PostgreSQL refusing a value, so the regression has to be PostgreSQL
refusing a value — first on the old column, then accepting it on the new one.

The shared test database cannot be walked backward across the whole revision
history safely, so each case builds the table in its own isolated PostgreSQL
schema: the pre-revision shape comes from running the original creating
migration, and the repair comes from running the new revision's ``upgrade()``
against that same schema. Both are the real migration modules, executed through
real Alembic operations — not a hand-written approximation of what they do.
"""

import importlib.util
import uuid
from pathlib import Path

import psycopg2
import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

# Aliased on import: pytest would collect the helper as a test case otherwise.
from tests.db_config import test_database_url as _test_database_url
from tests.test_phase0e_exit_docs import EXPECTED_ALEMBIC_HEAD


VERSIONS = Path(__file__).resolve().parents[1] / 'migrations' / 'versions'
CREATING_REVISION = VERSIONS / 'd4a8c2e6b1f9_add_tonight_intelligence_snapshots.py'
WIDENING_REVISION = VERSIONS / 'c7f1b408d93a_widen_tonight_snapshot_source.py'

TABLE = 'tonight_intelligence_snapshots'
PRODUCTION_SOURCE = 'github_actions_morning:schedule_coherence'

pytestmark = pytest.mark.skipif(
    not _test_database_url().startswith('postgresql'),
    reason='The migration regression must run against PostgreSQL, not SQLite.',
)


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(module_path, name, connection, direction='upgrade'):
    module = _load(module_path, name)
    module.op = Operations(MigrationContext.configure(connection))
    getattr(module, direction)()


@pytest.fixture
def schema():
    """An isolated PostgreSQL schema holding only this table.

    Isolation is what makes it safe to build the pre-revision shape: nothing
    else in the test database is moved backward, and the schema is dropped
    whatever the test does.
    """
    engine = sa.create_engine(_test_database_url())
    name = f'tonight_width_{uuid.uuid4().hex[:12]}'
    with engine.begin() as connection:
        connection.execute(sa.text(f'CREATE SCHEMA "{name}"'))
    try:
        yield engine, name
    finally:
        with engine.begin() as connection:
            connection.execute(sa.text(f'DROP SCHEMA IF EXISTS "{name}" CASCADE'))
        engine.dispose()


def _at_previous_revision(engine, name):
    """Build the table exactly as the revision before the widening left it."""
    with engine.begin() as connection:
        connection.execute(sa.text(f'SET LOCAL search_path TO "{name}"'))
        _run(CREATING_REVISION, 'tonight_creating_revision', connection)


def _column_length(connection, name):
    return connection.execute(
        sa.text(
            'SELECT character_maximum_length FROM information_schema.columns '
            'WHERE table_schema = :schema AND table_name = :table '
            "AND column_name = 'source'"
        ),
        {'schema': name, 'table': TABLE},
    ).scalar()


def _insert(connection, name, *, source, reference_date='2026-08-02',
            version='tonight_v1'):
    connection.execute(
        sa.text(
            f'INSERT INTO "{name}".{TABLE} '
            '(reference_date, snapshot_version, status, response_json, '
            ' card_count, source, generated_at, created_at, updated_at) '
            "VALUES (:ref, :version, 'empty', '{}', 0, :source, "
            ' NOW(), NOW(), NOW())'
        ),
        {'ref': reference_date, 'version': version, 'source': source},
    )


def _update_source(connection, name, *, source, reference_date='2026-08-02'):
    connection.execute(
        sa.text(
            f'UPDATE "{name}".{TABLE} SET source = :source, updated_at = NOW() '
            'WHERE reference_date = :ref'
        ),
        {'source': source, 'ref': reference_date},
    )


def _source_values(connection, name):
    return [
        row[0] for row in connection.execute(
            sa.text(f'SELECT source FROM "{name}".{TABLE} ORDER BY id')
        )
    ]


# ── A. The old schema rejects the production value ──────────────────────────


def test_the_previous_revision_leaves_the_column_at_forty(schema):
    engine, name = schema
    _at_previous_revision(engine, name)
    with engine.connect() as connection:
        assert _column_length(connection, name) == 40


def test_the_old_column_rejects_the_forty_one_character_source_on_insert(schema):
    engine, name = schema
    _at_previous_revision(engine, name)

    with pytest.raises(sa.exc.DataError) as excinfo:
        with engine.begin() as connection:
            _insert(connection, name, source=PRODUCTION_SOURCE)

    assert isinstance(excinfo.value.orig, psycopg2.errors.StringDataRightTruncation)


def test_the_old_column_rejects_the_production_update_that_failed(schema):
    """The exact failing operation class: UPDATE of an existing row."""
    engine, name = schema
    _at_previous_revision(engine, name)
    with engine.begin() as connection:
        _insert(connection, name, source='on_demand')

    with pytest.raises(sa.exc.DataError) as excinfo:
        with engine.begin() as connection:
            _update_source(connection, name, source=PRODUCTION_SOURCE)

    assert isinstance(excinfo.value.orig, psycopg2.errors.StringDataRightTruncation)
    assert 'character varying(40)' in str(excinfo.value)


# ── B. The new schema accepts it ────────────────────────────────────────────


def test_the_migration_widens_the_column_to_the_governed_length(schema):
    engine, name = schema
    _at_previous_revision(engine, name)

    with engine.begin() as connection:
        connection.execute(sa.text(f'SET LOCAL search_path TO "{name}"'))
        _run(WIDENING_REVISION, 'tonight_widening_revision', connection)

    with engine.connect() as connection:
        assert _column_length(connection, name) == 128


def test_the_same_update_succeeds_after_the_migration(schema):
    engine, name = schema
    _at_previous_revision(engine, name)
    with engine.begin() as connection:
        _insert(connection, name, source='on_demand')
        connection.execute(sa.text(f'SET LOCAL search_path TO "{name}"'))
        _run(WIDENING_REVISION, 'tonight_widening_revision', connection)

    with engine.begin() as connection:
        _update_source(connection, name, source=PRODUCTION_SOURCE)

    with engine.connect() as connection:
        stored = _source_values(connection, name)
    assert stored == [PRODUCTION_SOURCE]
    assert len(stored[0]) == 41


# ── C. Migration integrity ──────────────────────────────────────────────────


def test_existing_values_survive_the_upgrade_unchanged(schema):
    engine, name = schema
    _at_previous_revision(engine, name)
    existing = ['on_demand', 'github_actions', 'intraday_repair']
    with engine.begin() as connection:
        for index, value in enumerate(existing):
            _insert(connection, name, source=value,
                    reference_date=f'2026-08-0{index + 1}')

    with engine.begin() as connection:
        connection.execute(sa.text(f'SET LOCAL search_path TO "{name}"'))
        _run(WIDENING_REVISION, 'tonight_widening_revision', connection)

    with engine.connect() as connection:
        assert _source_values(connection, name) == existing


def test_the_upgrade_preserves_nullability(schema):
    engine, name = schema
    _at_previous_revision(engine, name)
    with engine.begin() as connection:
        connection.execute(sa.text(f'SET LOCAL search_path TO "{name}"'))
        _run(WIDENING_REVISION, 'tonight_widening_revision', connection)

    with engine.connect() as connection:
        nullable = connection.execute(
            sa.text(
                'SELECT is_nullable FROM information_schema.columns '
                'WHERE table_schema = :schema AND table_name = :table '
                "AND column_name = 'source'"
            ),
            {'schema': name, 'table': TABLE},
        ).scalar()
    assert nullable == 'NO'


def test_the_upgrade_preserves_the_tables_indexes_and_constraint(schema):
    engine, name = schema
    _at_previous_revision(engine, name)
    with engine.connect() as connection:
        before = _index_names(connection, name)

    with engine.begin() as connection:
        connection.execute(sa.text(f'SET LOCAL search_path TO "{name}"'))
        _run(WIDENING_REVISION, 'tonight_widening_revision', connection)

    with engine.connect() as connection:
        assert _index_names(connection, name) == before


def _index_names(connection, name):
    return sorted(
        row[0] for row in connection.execute(
            sa.text(
                'SELECT indexname FROM pg_indexes '
                'WHERE schemaname = :schema AND tablename = :table'
            ),
            {'schema': name, 'table': TABLE},
        )
    )


# ── Downgrade refuses rather than corrupting ────────────────────────────────


def test_the_downgrade_refuses_when_a_row_would_be_truncated(schema):
    """Narrowing back is only safe when nothing is lost by it.

    A downgrade that silently truncated would destroy exactly the provenance
    this package exists to preserve, so it fails loudly instead.
    """
    engine, name = schema
    _at_previous_revision(engine, name)
    with engine.begin() as connection:
        connection.execute(sa.text(f'SET LOCAL search_path TO "{name}"'))
        _run(WIDENING_REVISION, 'tonight_widening_revision', connection)
        _insert(connection, name, source=PRODUCTION_SOURCE)

    with pytest.raises(RuntimeError) as excinfo:
        with engine.begin() as connection:
            connection.execute(sa.text(f'SET LOCAL search_path TO "{name}"'))
            _run(WIDENING_REVISION, 'tonight_widening_revision', connection,
                 direction='downgrade')

    message = str(excinfo.value)
    assert 'Refusing to narrow' in message
    assert 'silently truncated' in message

    with engine.connect() as connection:
        assert _column_length(connection, name) == 128
        assert _source_values(connection, name) == [PRODUCTION_SOURCE]


def test_the_downgrade_proceeds_when_every_value_still_fits(schema):
    engine, name = schema
    _at_previous_revision(engine, name)
    with engine.begin() as connection:
        connection.execute(sa.text(f'SET LOCAL search_path TO "{name}"'))
        _run(WIDENING_REVISION, 'tonight_widening_revision', connection)
        _insert(connection, name, source='on_demand')

    with engine.begin() as connection:
        connection.execute(sa.text(f'SET LOCAL search_path TO "{name}"'))
        _run(WIDENING_REVISION, 'tonight_widening_revision', connection,
             direction='downgrade')

    with engine.connect() as connection:
        assert _column_length(connection, name) == 40
        assert _source_values(connection, name) == ['on_demand']


# ── One head ────────────────────────────────────────────────────────────────


def test_the_revision_history_has_exactly_one_head():
    """A second head would make deployment order undefined."""
    import re

    revisions, downs = {}, set()
    for path in sorted(VERSIONS.glob('*.py')):
        text = path.read_text()
        revision = re.search(r"^revision\s*=\s*['\"]([^'\"]+)", text, re.M)
        if not revision:
            continue
        revisions[revision.group(1)] = path.name
        down = re.search(r'^down_revision\s*=\s*(.+)$', text, re.M)
        if down:
            downs.update(re.findall(r"['\"]([^'\"]+)['\"]", down.group(1)))

    heads = [revision for revision in revisions if revision not in downs]
    assert heads == [EXPECTED_ALEMBIC_HEAD], f'expected one head, found {heads}'


def test_the_widening_revision_follows_the_previous_head():
    module = _load(WIDENING_REVISION, 'tonight_widening_revision_meta')
    assert module.revision == 'c7f1b408d93a'
    assert module.down_revision == 'b9d4e17c3a80'


def test_the_migration_width_matches_the_application_constant():
    """The number in DDL and the number the model declares are the same.

    The migration cannot import application code, so agreement is asserted
    here rather than assumed.
    """
    from models.tonight_intelligence_snapshot import (
        TONIGHT_SNAPSHOT_SOURCE_MAX_LENGTH,
    )

    module = _load(WIDENING_REVISION, 'tonight_widening_revision_width')
    assert module.WIDENED_LENGTH == TONIGHT_SNAPSHOT_SOURCE_MAX_LENGTH
    assert module.PREVIOUS_LENGTH == 40
