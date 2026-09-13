"""Truthful history promotion on fresh and already-migrated PostgreSQL."""

import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import urlopen
import uuid

from alembic.script import ScriptDirectory
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from tests.db_config import assert_disposable_test_target, test_database_url as database_url


BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
MANIFEST = json.loads((BACKEND / 'migrations/production_lineage.json').read_text())
TARGET = MANIFEST['target_revision']


def test_history_is_single_linear_extension_with_distinct_revision_ids(tmp_path):
    revisions = {}
    for path in (BACKEND / 'migrations/versions').glob('*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == 'revision' for target in node.targets
            ):
                revision = ast.literal_eval(node.value)
                assert revision not in revisions, (revision, path, revisions.get(revision))
                revisions[revision] = path.name
    script = ScriptDirectory(str(BACKEND / 'migrations'))
    assert script.get_heads() == [TARGET]
    assert script.get_bases() == ['3b06397ddc6b']
    assert not any(revision.is_merge_point or revision.is_branch_point
                   for revision in script.walk_revisions())
    promoted = {row['revision'] for row in MANIFEST['migrations']}
    assert len(promoted) == 16
    extension = list(script.iterate_revisions(TARGET, MANIFEST['common_revision']))
    assert {revision.revision for revision in extension} == promoted
    assert all(isinstance(revision.down_revision, str) for revision in extension)
    assert script.get_revision('e3f6a9b2c5d8').down_revision == 'd2e5f8a1b4c7'
    assert script.get_revision('e3f6a9b2d5c8').down_revision == 'd2e5f8a1c4b7'
    original = tmp_path / 'main_graph'
    (original / 'versions').mkdir(parents=True)
    for revision, name in revisions.items():
        if revision not in promoted:
            shutil.copyfile(BACKEND / 'migrations/versions' / name, original / 'versions' / name)
    assert ScriptDirectory(str(original)).get_heads() == [MANIFEST['common_revision']]


def test_promoted_historical_definitions_are_immutable_and_standalone():
    for row in MANIFEST['migrations']:
        content = (ROOT / row['path']).read_text(encoding='utf-8')
        assert hashlib.sha256(content.encode()).hexdigest() == row['sha256']
        tree = ast.parse(content)
        imports = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom))]
        assert len(imports) == 2
        assert ast.unparse(imports[0]) == 'from alembic import op'
        assert ast.unparse(imports[1]) == 'import sqlalchemy as sa'
        assignments = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
                       if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                       and node.targets[0].id in ('revision', 'down_revision')}
        assert assignments['revision'] == row['revision']
        assert assignments['down_revision'] == row['down_revision']


def test_runtime_promotion_is_strictly_bounded():
    # Freeze this historical promotion's scope. Comparing the original base to
    # today's checkout would incorrectly prohibit all subsequent runtime fixes.
    promotion_commit = '04adf7932416136bb220ffcb207f84c6e6e17acc'
    paths = subprocess.check_output(
        ['git', 'diff', '--name-only', MANIFEST['main_base'], promotion_commit, '--',
         'backend/models', 'backend/api', 'backend/services', 'frontend'],
        cwd=ROOT, text=True,
    ).splitlines()
    assert set(paths) <= {'backend/services/migration_authority.py'}
    assert not (BACKEND / 'services/sync_pipeline_shadow.py').exists()


@pytest.fixture
def postgres_databases():
    url = database_url()
    assert_disposable_test_target(url, operation='lineage migration proof')
    parsed = make_url(url)
    if parsed.get_backend_name() != 'postgresql':
        pytest.skip('Real PostgreSQL required; CI backend shards provide it')
    admin = create_engine(parsed.set(database='postgres'), isolation_level='AUTOCOMMIT')
    names = [f'lineage_{case}_test_{uuid.uuid4().hex[:12]}' for case in ('fresh', 'existing')]
    created = []
    try:
        with admin.connect() as connection:
            for name in names:
                connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
                created.append(name)
        yield [parsed.set(database=name).render_as_string(hide_password=False) for name in names]
    finally:
        with admin.connect() as connection:
            for name in created:
                connection.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
        admin.dispose()


def _env(url):
    env = {**os.environ, 'APP_ENV': 'production', 'AUTO_SYNC': 'false',
           'DATABASE_URL': url, 'TEST_DATABASE_URL': url,
           'DATABASE_MIGRATION_MODE': 'owner', 'RENDER_GIT_BRANCH': 'main',
           'SECRET_KEY': 'isolated-lineage-test-secret-key-32-characters',
           'ADMIN_API_TOKEN': 'isolated-lineage-test-admin-token-32-characters',
           'SYNC_PIPELINE_SHADOW_MODE': 'false'}
    env.pop('GITHUB_REF', None)
    env.pop('SKIP_STARTUP_MIGRATIONS', None)
    return env


def _flask(url, *args):
    result = subprocess.run([sys.executable, '-m', 'flask', '--app', 'app', 'db', *args],
                            cwd=BACKEND, env=_env(url), capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def _fingerprint(url):
    engine = create_engine(url)
    with engine.connect() as connection:
        tables = list(connection.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
        )).scalars())
        contents = {table: connection.execute(text(
            'SELECT md5(coalesce(string_agg(to_jsonb(t)::text,\'\' ORDER BY to_jsonb(t)::text),\'\')) '
            f'FROM "{table}" t'
        )).scalar_one() for table in tables}
        columns = connection.execute(text(
            "SELECT table_name,column_name,udt_name,is_nullable,column_default "
            "FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name,ordinal_position"
        )).all()
        indexes = connection.execute(text(
            "SELECT tablename,indexname,indexdef FROM pg_indexes WHERE schemaname='public' ORDER BY tablename,indexname"
        )).all()
        constraints = connection.execute(text(
            "SELECT c.relname,con.conname,pg_get_constraintdef(con.oid) FROM pg_constraint con "
            "JOIN pg_class c ON c.oid=con.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace "
            "WHERE n.nspname='public' ORDER BY c.relname,con.conname"
        )).all()
        functions = connection.execute(text(
            "SELECT proname,prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname='public' ORDER BY proname"
        )).all()
        triggers = connection.execute(text(
            "SELECT pg_get_triggerdef(t.oid) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
            "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' "
            "AND NOT t.tgisinternal ORDER BY c.relname,t.tgname"
        )).all()
    engine.dispose()
    return contents, columns, indexes, constraints, functions, triggers


def _seed(url):
    engine = create_engine(url)
    with engine.begin() as c:
        run_id = c.execute(text("INSERT INTO sync_runs(started_at,status,source,created_at) "
                                "VALUES(now(),'success','lineage_proof',now()) RETURNING id")).scalar_one()
        c.execute(text("INSERT INTO sync_failures(sync_run_id,job_name,entity_type,created_at,resolved) "
                       "VALUES(:id,'lineage_proof','fixture',now(),false)"), {'id': run_id})
        c.execute(text("INSERT INTO sync_run_scopes(sync_run_id,scope_type,scope_key,created_at) "
                       "VALUES(:id,'baseball_date','2026-09-10',now())"), {'id': run_id})
        c.execute(text("INSERT INTO source_payload_artifacts(content_hash,hash_algorithm,payload_schema_version,"
                       "payload_kind,storage_format,payload_json,payload_bytes,created_at) "
                       "VALUES(:hash,'sha256',1,'fixture','json',:payload,17,now())"),
                  {'hash': 'a' * 64, 'payload': json.dumps({'preserve': True})})
        c.execute(text("INSERT INTO compatibility_write_events(resource_type,resource_key,outcome,details_json,created_at) "
                       "VALUES('fixture','preserved','stale_suppressed',:payload,now())"), {'payload': json.dumps({'preserve': True})})
    engine.dispose()


def test_fresh_and_existing_postgres_preserve_history_data_and_normal_startup(postgres_databases, tmp_path):
    fresh, existing = postgres_databases
    # Build production-shaped state by genuinely applying the frozen history,
    # never by assigning a revision to pre-created model tables.
    historical = tmp_path / 'historical_migrations'
    shutil.copytree(BACKEND / 'migrations', historical, ignore=shutil.ignore_patterns('__pycache__'))
    old = _flask(existing, 'upgrade', '--directory', str(historical), TARGET)
    assert 'Running upgrade' in old.stderr
    _seed(existing)
    before = _fingerprint(existing)
    assert len(before[0]) == 88
    assert all(before[0][name] != hashlib.md5(b'').hexdigest() for name in (
        'sync_runs', 'sync_failures', 'sync_run_scopes', 'source_payload_artifacts',
        'compatibility_write_events'))
    current = _flask(existing, 'current')
    assert TARGET + ' (head)' in current.stdout
    for _ in range(2):
        result = _flask(existing, 'upgrade')
        assert 'Running upgrade' not in result.stderr
        assert _fingerprint(existing) == before
    result = _flask(fresh, 'upgrade')
    assert 'Running upgrade' in result.stderr
    assert _flask(fresh, 'heads').stdout.strip().endswith(TARGET + ' (head)')
    assert TARGET + ' (head)' in _flask(fresh, 'current').stdout
    assert _flask(fresh, 'history').returncode == 0
    # Production main runtime, real migrations and real Daily Edition helper.
    # The custom server probe exits instead of leaving a background web process.
    probe = tmp_path / 'server_probe.py'
    probe.write_text("from app import app\nr=app.test_client().get('/api/health')\n"
                     "assert r.status_code==200 and r.json['status']=='ok'\n"
                     "print('MAIN_RUNTIME_SERVER_READY')\n")
    bash = 'C:/Program Files/Git/bin/bash.exe' if os.name == 'nt' else shutil.which('bash')
    assert bash, 'Bash required for the production startup proof'
    env = _env(existing)
    env['PYTHONPATH'] = str(BACKEND)
    result = subprocess.run([bash, str(BACKEND / 'scripts/render_start.sh'), sys.executable, str(probe)],
                            cwd=BACKEND, env=env, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    output = result.stdout
    assert 'emergency_skip=false' in output and 'explicitly skipped' not in output
    assert output.index('current_heads=') < output.index('Applying database migrations')
    assert output.index('Applying database migrations') < output.index('Daily Edition preparation completed')
    assert output.index('Daily Edition preparation completed') < output.index('MAIN_RUNTIME_SERVER_READY')
    assert 'no_trusted_publication' in output
    assert _fingerprint(existing) == before
    if os.name != 'nt':
        _prove_gunicorn(tmp_path, env)
        assert _fingerprint(existing) == before


def _prove_gunicorn(tmp_path, env):
    # Exercise the actual default production server on Linux (including CI).
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    log = tmp_path / 'gunicorn.log'
    with log.open('w') as output:
        process = subprocess.Popen(
            ['bash', str(BACKEND / 'scripts/render_start.sh')], cwd=BACKEND,
            env={**env, 'PORT': str(port)}, stdout=output, stderr=output,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                assert process.poll() is None, log.read_text()
                try:
                    with urlopen(f'http://127.0.0.1:{port}/api/health', timeout=2) as response:
                        assert response.status == 200
                        assert json.load(response)['status'] == 'ok'
                    break
                except OSError:
                    time.sleep(0.2)
            else:
                pytest.fail(log.read_text())
        finally:
            process.terminate()
            process.wait(timeout=15)
    logs = log.read_text()
    assert logs.index('emergency_skip=false') < logs.index('Applying database migrations')
    assert logs.index('Daily Edition preparation completed') < logs.index('Starting gunicorn')
    assert 'Running upgrade' not in logs
    assert not any(error in logs for error in ('UndefinedTable', 'UndefinedColumn', "Can't locate revision", 'ERROR'))
