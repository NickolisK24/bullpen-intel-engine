"""WP-0.2 (EOS-009): backup dump, isolated restore, and verification rehearsal.

Runs the real pg_dump/pg_restore round trip between two disposable databases
on the test server. It never connects to a production database.
"""

import os
import shutil
import uuid
from urllib.parse import urlsplit, urlunsplit

import pytest

from scripts import database_restore_rehearsal as rehearsal

pytestmark = pytest.mark.skipif(
    not (shutil.which('pg_dump') and shutil.which('pg_restore')),
    reason='PostgreSQL client tools are not installed',
)


def _server_url():
    url = os.environ.get('TEST_DATABASE_URL') or os.environ.get('DATABASE_URL') or ''
    if not url.startswith('postgres'):
        pytest.skip('restore rehearsal needs a PostgreSQL test server')
    return url


def _with_database(url, name):
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f'/{name}', parts.query, parts.fragment))


@pytest.fixture
def databases():
    import psycopg2

    server = _server_url()
    suffix = uuid.uuid4().hex[:8]
    names = {
        'source': f'wp02_rehearsal_source_{suffix}_test',
        'target': f'wp02_restore_rehearsal_{suffix}_test',
        'unsafe': f'wp02_copy_{suffix}_test',
    }
    admin = psycopg2.connect(server)
    admin.autocommit = True
    with admin.cursor() as cursor:
        for name in names.values():
            cursor.execute(f'CREATE DATABASE "{name}"')
    urls = {key: _with_database(server, name) for key, name in names.items()}
    try:
        yield urls
    finally:
        with admin.cursor() as cursor:
            for name in names.values():
                cursor.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.close()


def _seed_source(url):
    import psycopg2

    connection = psycopg2.connect(url)
    with connection, connection.cursor() as cursor:
        cursor.execute('CREATE TABLE alembic_version (version_num varchar(32) PRIMARY KEY)')
        cursor.execute("INSERT INTO alembic_version VALUES ('e3f6a9b2c5d8')")
        for table, rows in (('game_logs', 7), ('scheduled_games', 5), ('share_artifacts', 3)):
            cursor.execute(f'CREATE TABLE {table} (id serial PRIMARY KEY, note text)')
            cursor.execute(
                f'INSERT INTO {table} (note) SELECT %s FROM generate_series(1, %s)',
                (table, rows),
            )
    connection.close()


def test_dump_restore_and_verify_round_trip(databases, tmp_path):
    _seed_source(databases['source'])
    manifest, manifest_path = rehearsal.dump(databases['source'], tmp_path / 'baseballos.dump')
    assert manifest['table_counts']['game_logs'] == 7
    assert manifest['alembic_head'] == ['e3f6a9b2c5d8']
    # Tables this fixture does not create are reported, never skipped.
    assert 'pitchers' in manifest['missing_tables']
    assert len(manifest['dump_sha256']) == 64

    rehearsal.restore(databases['target'], tmp_path / 'baseballos.dump', source_url=databases['source'])
    result = rehearsal.verify(databases['target'], manifest_path, source_url=databases['source'])
    assert result['differences'] == {}
    assert result['table_counts']['share_artifacts'] == 3
    # Missing canonical tables keep the rehearsal from claiming success.
    assert result['verified'] is False
    assert 'pitchers' in result['missing_tables']


def test_verification_detects_lost_rows(databases, tmp_path):
    import psycopg2

    _seed_source(databases['source'])
    _, manifest_path = rehearsal.dump(databases['source'], tmp_path / 'baseballos.dump')
    rehearsal.restore(databases['target'], tmp_path / 'baseballos.dump')
    connection = psycopg2.connect(databases['target'])
    with connection, connection.cursor() as cursor:
        cursor.execute('DELETE FROM game_logs WHERE id = 1')
    connection.close()
    result = rehearsal.verify(databases['target'], manifest_path)
    assert result['differences']['game_logs'] == {'dumped': 7, 'restored': 6}


def test_restore_refuses_unsafe_targets(databases, tmp_path):
    _seed_source(databases['source'])
    rehearsal.dump(databases['source'], tmp_path / 'baseballos.dump')
    dump_file = tmp_path / 'baseballos.dump'

    with pytest.raises(rehearsal.RehearsalRefused, match='not named as a scratch database'):
        rehearsal.restore(databases['unsafe'], dump_file)
    with pytest.raises(rehearsal.RehearsalRefused, match='source or the configured application database'):
        rehearsal.require_safe_target(databases['target'], source_url=databases['target'])
    rehearsal.restore(databases['target'], dump_file)
    with pytest.raises(rehearsal.RehearsalRefused, match='not empty'):
        rehearsal.restore(databases['target'], dump_file)


def test_restore_refuses_the_configured_application_database(monkeypatch):
    target = 'postgresql://u@db.example.invalid:5432/baseballos_restore_rehearsal'
    monkeypatch.setenv('DATABASE_URL', target)
    with pytest.raises(rehearsal.RehearsalRefused):
        rehearsal.require_safe_target(target)


def test_output_never_contains_credentials():
    url = 'postgresql://reader:s3cr3t-value@db.example.invalid:6543/baseballos'
    assert rehearsal.describe(url) == 'db.example.invalid:6543/baseballos'
    assert 's3cr3t' not in rehearsal.describe(url)
