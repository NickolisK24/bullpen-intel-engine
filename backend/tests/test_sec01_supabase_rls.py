"""SEC-01: deny-by-default row level security for Supabase/PostgREST.

The PostgreSQL proof reproduces Supabase's access model on a disposable
database:

- a non-superuser, non-BYPASSRLS login role owns the schema and runs the
  migrations, like Supabase's ``postgres`` role;
- the ``anon`` and ``authenticated`` PostgREST client roles receive
  Supabase's default table grants;
- ``service_role`` is BYPASSRLS.

Untrusted access is exercised the way PostgREST does it, with SET ROLE.
"""

import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from tests.db_config import assert_disposable_test_target, test_database_url as database_url


BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
MIGRATION_PATH = BACKEND / 'migrations/versions/e5b9c3a7d1f4_enable_rls_deny_by_default.py'
PREVIOUS_HEAD = 'c3e7a1d9f5b2'
SEC01_HEAD = 'e5b9c3a7d1f4'
CLIENT_ROLES = ('anon', 'authenticated')
HARDENED_CONFIG = ['search_path=public, pg_temp']
# Policies are deny-by-default: no table has a direct-access contract.
EXPECTED_POLICIES = set()


def _migration():
    spec = importlib.util.spec_from_file_location('sec01_rls_migration', MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SEC01 = _migration()


# ── Static inventory ────────────────────────────────────────────────────────

def test_classification_is_a_complete_disjoint_partition_of_the_schema():
    categories = (
        SEC01.STRICT_INTERNAL_TABLES, SEC01.USER_PRIVATE_TABLES,
        SEC01.PUBLIC_PRODUCT_TABLES, SEC01.METADATA_TABLES,
    )
    names = [name for category in categories for name in category]
    assert len(names) == len(set(names)) == 89
    assert set(names) == set(SEC01.PROTECTED_TABLES)
    assert (len(SEC01.STRICT_INTERNAL_TABLES), len(SEC01.USER_PRIVATE_TABLES),
            len(SEC01.PUBLIC_PRODUCT_TABLES), len(SEC01.METADATA_TABLES)) == (43, 6, 39, 1)
    for table in ('users', 'user_followed_teams', 'audience_subscribers',
                  'traffic_internal_visitors', 'traffic_page_views', 'traffic_share_actions'):
        assert table in SEC01.USER_PRIVATE_TABLES


def test_every_migration_defined_function_has_a_hardened_search_path():
    defined = set()
    for path in (BACKEND / 'migrations/versions').glob('*.py'):
        defined |= set(re.findall(
            r'CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(?:public\.)?(\w+)\s*\(',
            path.read_text(encoding='utf-8'), re.I,
        ))
    hardened = {signature.split('(')[0] for signature in SEC01.FUNCTION_SIGNATURES}
    assert defined == hardened
    assert len(hardened) == 9


def test_no_client_talks_to_supabase_directly():
    package = json.loads((ROOT / 'frontend/package.json').read_text(encoding='utf-8'))
    dependencies = {**package.get('dependencies', {}), **package.get('devDependencies', {})}
    assert not any('supabase' in name or 'postgrest' in name for name in dependencies)
    pattern = re.compile(
        r'supabase-js|createClient\(|SUPABASE_(?:URL|ANON|SERVICE)|VITE_SUPABASE|'
        r'NEXT_PUBLIC_SUPABASE|\.supabase\.co/rest|/rest/v1/|service_role_key', re.I,
    )
    roots = [ROOT / 'frontend/src', ROOT / 'backend', ROOT / '.github']
    offenders = []
    for root in roots:
        for path in root.rglob('*'):
            if (not path.is_file() or 'node_modules' in path.parts or '__pycache__' in path.parts
                    or path.suffix not in {'.js', '.jsx', '.ts', '.tsx', '.py', '.yml', '.yaml', '.sh'}
                    or path.resolve() == Path(__file__).resolve()):
                continue
            if pattern.search(path.read_text(encoding='utf-8', errors='ignore')):
                offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_migration_never_forces_rls_or_creates_policies():
    source = MIGRATION_PATH.read_text(encoding='utf-8')
    assert 'FORCE ROW LEVEL SECURITY' not in source
    assert 'CREATE POLICY' not in source.upper()
    assert 'GRANT ALL' in source.split('def downgrade')[1]  # rollback restores exposure only there


# ── PostgreSQL proof ────────────────────────────────────────────────────────

def _admin_url():
    url = database_url()
    assert_disposable_test_target(url, operation='SEC-01 RLS proof')
    parsed = make_url(url)
    if parsed.get_backend_name() != 'postgresql':
        pytest.skip('Real PostgreSQL required; CI backend shards provide it')
    return parsed


def _ensure_role(connection, name, attributes):
    exists = connection.execute(text('SELECT 1 FROM pg_roles WHERE rolname=:n'), {'n': name}).first()
    if exists:
        return
    try:
        connection.exec_driver_sql(f'CREATE ROLE {name} {attributes}')
    except DBAPIError as exc:  # another shard created it concurrently
        if 'already exists' not in str(exc):
            raise


@pytest.fixture
def supabase_like_database():
    parsed = _admin_url()
    suffix = uuid.uuid4().hex[:10]
    owner = f'sec01_owner_{suffix}'
    password = uuid.uuid4().hex
    name = f'sec01_rls_test_{suffix}'
    admin = create_engine(parsed.set(database='postgres'), isolation_level='AUTOCOMMIT')
    extra_roles = []
    with admin.connect() as connection:
        _ensure_role(connection, 'anon', 'NOLOGIN NOINHERIT')
        _ensure_role(connection, 'authenticated', 'NOLOGIN NOINHERIT')
        _ensure_role(connection, 'service_role', 'NOLOGIN NOINHERIT BYPASSRLS')
        connection.exec_driver_sql(
            f"CREATE ROLE {owner} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE PASSWORD '{password}'")
        connection.exec_driver_sql(f'CREATE DATABASE "{name}" OWNER {owner}')
    owner_url = parsed.set(database=name, username=owner, password=password)
    superuser_url = parsed.set(database=name)
    owner_engine = create_engine(owner_url, isolation_level='AUTOCOMMIT')
    with owner_engine.connect() as connection:
        # Supabase's defaults expose every new public table to PostgREST roles.
        connection.exec_driver_sql(
            'GRANT USAGE ON SCHEMA public TO anon, authenticated, service_role')
        connection.exec_driver_sql(
            'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
            'GRANT ALL ON TABLES TO anon, authenticated, service_role')
        connection.exec_driver_sql(
            'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
            'GRANT ALL ON SEQUENCES TO anon, authenticated, service_role')
    try:
        yield {
            'owner': owner,
            'owner_url': owner_url.render_as_string(hide_password=False),
            'owner_engine': owner_engine,
            'superuser_engine': create_engine(superuser_url),
            'admin': admin,
            'extra_roles': extra_roles,
        }
    finally:
        owner_engine.dispose()
        with admin.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            for role in extra_roles + [owner]:
                connection.exec_driver_sql(f'DROP ROLE IF EXISTS {role}')
        admin.dispose()


def _flask(url, *args, check=True):
    env = {**os.environ, 'APP_ENV': 'production', 'AUTO_SYNC': 'false',
           'DATABASE_URL': url, 'TEST_DATABASE_URL': url,
           'DATABASE_MIGRATION_MODE': 'owner', 'RENDER_GIT_BRANCH': 'main',
           'SECRET_KEY': 'isolated-sec01-test-secret-key-32-characters',
           'ADMIN_API_TOKEN': 'isolated-sec01-test-admin-token-32-characters',
           'SYNC_PIPELINE_SHADOW_MODE': 'false'}
    env.pop('GITHUB_REF', None)
    env.pop('SKIP_STARTUP_MIGRATIONS', None)
    result = subprocess.run([sys.executable, '-m', 'flask', '--app', 'app', 'db', *args],
                            cwd=BACKEND, env=env, capture_output=True, text=True, timeout=300)
    if check:
        assert result.returncode == 0, result.stdout + result.stderr
    return result


def _public_tables(connection):
    return connection.execute(text(
        "SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity FROM pg_class c "
        "JOIN pg_namespace n ON n.oid=c.relnamespace "
        "WHERE n.nspname='public' AND c.relkind IN ('r','p') ORDER BY 1"
    )).all()


def _functions(connection):
    return connection.execute(text(
        "SELECT p.proname, p.prosrc, p.proconfig, p.prosecdef FROM pg_proc p "
        "JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' ORDER BY 1"
    )).all()


def _head(connection):
    return connection.execute(text('SELECT version_num FROM alembic_version')).scalar_one()


def _as_role(engine, role, statement, params=None):
    """Run one statement as a PostgREST role; return rows/rowcount or the error."""
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.exec_driver_sql(f'SET LOCAL ROLE {role}')
            result = connection.execute(text(statement), params or {})
            outcome = result.all() if result.returns_rows else result.rowcount
        except DBAPIError as exc:
            outcome = exc.orig.__class__.__name__ + ': ' + str(exc.orig).splitlines()[0]
        finally:
            transaction.rollback()
    return outcome


def _seed(engine):
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO users(email, created_at) VALUES ('owner-seed@example.com', now())"))
        connection.execute(text(
            "INSERT INTO sync_runs(started_at, status, source, created_at) "
            "VALUES (now(), 'success', 'sec01_seed', now())"))
        connection.execute(text(
            "INSERT INTO slate_games(game_pk, game_date_et, game_time_utc, home_team_id, "
            "away_team_id, normalized_state, last_synced) "
            "VALUES (990001, current_date, now(), 1, 2, 'upcoming', now())"))


def test_rls_denies_postgrest_roles_and_preserves_the_owner(supabase_like_database):
    ctx = supabase_like_database
    owner_url, owner_engine = ctx['owner_url'], ctx['owner_engine']
    superuser = ctx['superuser_engine']

    # Before: reproduce the advisor finding on the previous head.
    _flask(owner_url, 'upgrade', PREVIOUS_HEAD)
    _seed(owner_engine)
    with owner_engine.connect() as connection:
        before_tables = _public_tables(connection)
        before_functions = _functions(connection)
    assert len(before_tables) == 89
    assert not any(row.relrowsecurity for row in before_tables)
    assert all(row.proconfig is None and row.prosecdef is False for row in before_functions)
    assert _as_role(superuser, 'anon', 'SELECT email FROM users') == [('owner-seed@example.com',)]
    assert _as_role(superuser, 'authenticated',
                    "INSERT INTO sync_runs(started_at,status,source,created_at) "
                    "VALUES (now(),'x','anon',now())") == 1

    # Guard: a trusted-looking role that RLS would silently restrict blocks the
    # migration, and nothing changes.
    rogue = f'sec01_reader_{uuid.uuid4().hex[:10]}'
    ctx['extra_roles'].append(rogue)
    with ctx['admin'].connect() as connection:
        connection.exec_driver_sql(f'CREATE ROLE {rogue} LOGIN NOSUPERUSER NOBYPASSRLS')
    with superuser.begin() as connection:
        connection.exec_driver_sql(f'GRANT SELECT ON sync_runs TO {rogue}')
    refused = _flask(owner_url, 'upgrade', check=False)
    assert refused.returncode != 0
    assert 'sec01_rls_would_restrict_trusted_roles' in refused.stderr and rogue in refused.stderr
    with owner_engine.connect() as connection:
        assert _head(connection) == PREVIOUS_HEAD
        assert _public_tables(connection) == before_tables
        assert _functions(connection) == before_functions
    with superuser.begin() as connection:
        connection.exec_driver_sql(f'REVOKE ALL ON sync_runs FROM {rogue}')

    # service_role holds Supabase's default grants but is BYPASSRLS, so it never
    # blocks the guard.
    result = _flask(owner_url, 'upgrade', SEC01_HEAD)
    assert f'{PREVIOUS_HEAD} -> {SEC01_HEAD}' in result.stderr

    with owner_engine.connect() as connection:
        after_tables = _public_tables(connection)
        after_functions = _functions(connection)
        assert _head(connection) == SEC01_HEAD
        # Schema-wide guard: every public table, including any future one.
        assert [row.relname for row in after_tables if not row.relrowsecurity] == []
        assert [row.relname for row in after_tables if row.relforcerowsecurity] == []
        policies = set(connection.execute(text(
            "SELECT tablename, policyname FROM pg_policies WHERE schemaname='public'")).all())
        assert policies == EXPECTED_POLICIES
        # Grant inventory: no client-role or PUBLIC table privileges remain.
        client_grants = connection.execute(text(
            "SELECT c.relname, r.rolname FROM pg_class c "
            "JOIN pg_namespace n ON n.oid=c.relnamespace "
            "CROSS JOIN pg_roles r WHERE n.nspname='public' AND c.relkind='r' "
            "AND r.rolname = ANY(:roles) AND (has_table_privilege(r.oid, c.oid, "
            "'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER') "
            "OR has_any_column_privilege(r.oid, c.oid, 'SELECT,INSERT,UPDATE,REFERENCES'))"),
            {'roles': list(CLIENT_ROLES)}).all()
        assert client_grants == []
        client_sequence_grants = connection.execute(text(
            "SELECT s.relname, r.rolname FROM pg_class s "
            "JOIN pg_namespace n ON n.oid=s.relnamespace CROSS JOIN pg_roles r "
            "WHERE n.nspname='public' AND s.relkind='S' AND r.rolname = ANY(:roles) "
            "AND has_sequence_privilege(r.oid, s.oid, 'USAGE,SELECT,UPDATE')"),
            {'roles': list(CLIENT_ROLES)}).all()
        assert client_sequence_grants == []
        public_grants = connection.execute(text(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace, "
            "aclexplode(coalesce(c.relacl, acldefault('r', c.relowner))) acl "
            "WHERE n.nspname='public' AND c.relkind='r' AND acl.grantee = 0")).all()
        assert public_grants == []
    assert [row.relname for row in after_tables] == [row.relname for row in before_tables]
    # Function search paths are pinned; bodies and invoker security unchanged.
    assert [(row.proname, row.prosrc, row.prosecdef) for row in after_functions] == [
        (row.proname, row.prosrc, row.prosecdef) for row in before_functions]
    assert all(row.proconfig == HARDENED_CONFIG for row in after_functions)
    assert len(after_functions) == 9

    # Untrusted PostgREST roles: every table denies SELECT, and writes fail.
    for role in CLIENT_ROLES:
        for table in SEC01.PROTECTED_TABLES:
            outcome = _as_role(superuser, role, f'SELECT 1 FROM "{table}" LIMIT 1')
            assert isinstance(outcome, str) and 'permission denied' in outcome, (role, table, outcome)
        assert 'permission denied' in _as_role(
            superuser, role, "INSERT INTO users(email, created_at) VALUES ('x@example.com', now())")
        assert 'permission denied' in _as_role(superuser, role, "UPDATE users SET email='x'")
        assert 'permission denied' in _as_role(superuser, role, 'DELETE FROM sync_runs')

    # RLS is an independent layer: even if a grant were re-added, a client role
    # sees no rows and cannot write without an explicit policy.
    with superuser.connect() as connection:
        transaction = connection.begin()
        connection.exec_driver_sql('GRANT SELECT, INSERT, UPDATE, DELETE ON users TO anon')
        connection.exec_driver_sql('SET LOCAL ROLE anon')
        assert connection.execute(text('SELECT count(*) FROM users')).scalar_one() == 0
        assert connection.execute(text("UPDATE users SET email='x'")).rowcount == 0
        assert connection.execute(text('DELETE FROM users')).rowcount == 0
        savepoint = connection.begin_nested()
        with pytest.raises(DBAPIError, match='row-level security'):
            connection.execute(text(
                "INSERT INTO users(id, email, created_at) VALUES (999999, 'rls@example.com', now())"))
        savepoint.rollback()
        transaction.rollback()

    # The owner (the backend role) is exempt: full read and write, with the
    # guard triggers still resolving their unqualified tables.
    with owner_engine.begin() as connection:
        assert connection.execute(text('SELECT count(*) FROM users')).scalar_one() == 1
        connection.execute(text(
            "INSERT INTO users(email, created_at) VALUES ('owner-write@example.com', now())"))
        assert connection.execute(text(
            "UPDATE users SET last_login_at=now() WHERE email='owner-write@example.com'")).rowcount == 1
        assert connection.execute(text(
            "UPDATE slate_games SET normalized_state='live' WHERE game_pk=990001")).rowcount == 1
        connection.execute(text(
            "INSERT INTO sync_runs(started_at,status,source,created_at) "
            "VALUES (now(),'success','owner',now())"))
        assert connection.execute(text(
            "DELETE FROM users WHERE email='owner-write@example.com'")).rowcount == 1
        assert connection.execute(text('SELECT count(*) FROM sync_runs')).scalar_one() == 2
    # BYPASSRLS service_role keeps its access.
    assert _as_role(superuser, 'service_role', 'SELECT count(*) FROM users') == [(1,)]

    # Downgrade restores the previous exposure exactly; upgrade reapplies.
    _flask(owner_url, 'downgrade', PREVIOUS_HEAD)
    with owner_engine.connect() as connection:
        assert _public_tables(connection) == before_tables
        assert _functions(connection) == before_functions
    assert _as_role(superuser, 'anon', 'SELECT count(*) FROM users') == [(1,)]
    assert _as_role(superuser, 'anon',
                    "INSERT INTO users(email, created_at) VALUES ('restored@example.com', now())") == 1
    _flask(owner_url, 'upgrade', SEC01_HEAD)
    with owner_engine.connect() as connection:
        assert _public_tables(connection) == after_tables
        assert _head(connection) == SEC01_HEAD
    assert 'permission denied' in _as_role(superuser, 'anon', 'SELECT 1 FROM users')


def test_clean_database_migrates_to_rls_head_without_client_roles_present():
    # CI and local databases have no Supabase roles: RLS still applies to every
    # table and the grant step is a no-op.
    parsed = _admin_url()
    name = f'sec01_clean_test_{uuid.uuid4().hex[:10]}'
    admin = create_engine(parsed.set(database='postgres'), isolation_level='AUTOCOMMIT')
    with admin.connect() as connection:
        connection.exec_driver_sql(f'CREATE DATABASE "{name}"')
    url = parsed.set(database=name)
    try:
        rendered = url.render_as_string(hide_password=False)
        engine = create_engine(url)
        _flask(rendered, 'upgrade', SEC01_HEAD)
        with engine.connect() as connection:
            # The explicit list is exactly the schema SEC-01 was written for.
            assert {row.relname for row in _public_tables(connection)} == set(SEC01.PROTECTED_TABLES)
        _flask(rendered, 'upgrade')
        with engine.connect() as connection:
            # Schema-wide guard at head: a later migration that adds a public
            # table must enable RLS on it too.
            tables = _public_tables(connection)
            assert [row.relname for row in tables if not row.relrowsecurity] == []
            assert [row.relname for row in tables if row.relforcerowsecurity] == []
            assert all(row.proconfig == HARDENED_CONFIG for row in _functions(connection))
            assert set(connection.execute(text(
                "SELECT tablename, policyname FROM pg_policies WHERE schemaname='public'"
            )).all()) == EXPECTED_POLICIES
        engine.dispose()
    finally:
        with admin.connect() as connection:
            connection.exec_driver_sql(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        admin.dispose()
