"""Schema authority contracts; all database fixtures are disposable."""

import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

import pytest
import yaml

from scripts import database_migrations as command
from services import migration_authority as authority


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / 'backend'
SHA = 'a' * 40


@pytest.fixture
def environment(monkeypatch):
    for key in ('DATABASE_MIGRATION_MODE', 'SKIP_STARTUP_MIGRATIONS',
                'SYNC_PIPELINE_SHADOW_MODE', 'GITHUB_REF', 'RENDER_GIT_BRANCH'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('APP_ENV', 'test')
    return monkeypatch


@pytest.mark.parametrize('value', authority.MODES)
def test_modes_are_exact(value):
    assert authority.migration_mode({authority.MODE_KEY: value}) == value


@pytest.mark.parametrize('value', [None, '', 'OWNER', 'Owner', 'true', '1', 'yes',
                                  ' owner', 'owner ', 'verify-only', 'whatever'])
def test_invalid_or_missing_modes_refuse(value):
    env = {} if value is None else {authority.MODE_KEY: value}
    with pytest.raises(authority.MigrationAuthorityError):
        authority.migration_mode(env)


@pytest.mark.parametrize('mode', [None, 'verify_only', 'disabled'])
def test_mutation_requires_explicit_owner(mode):
    env = {} if mode is None else {authority.MODE_KEY: mode}
    with pytest.raises(authority.MigrationAuthorityError):
        authority.require_owner(env)


@pytest.mark.parametrize('extra', [
    {'APP_ENV': 'production'},
    {'APP_ENV': 'production', 'GITHUB_REF': 'refs/heads/feat/sync-pipeline'},
    {'APP_ENV': 'production', 'RENDER_GIT_BRANCH': 'feat/sync-pipeline'},
    {'APP_ENV': 'production', 'GITHUB_REF': 'refs/heads/main', 'SYNC_PIPELINE_SHADOW_MODE': 'true'},
])
def test_production_or_shadow_cannot_self_authorize(extra):
    with pytest.raises(authority.MigrationAuthorityError):
        authority.require_owner({authority.MODE_KEY: 'owner', **extra})


def test_explicit_production_owner_requires_main():
    assert authority.require_owner({authority.MODE_KEY: 'owner', 'APP_ENV': 'production',
                                    'RENDER_GIT_BRANCH': 'main'}) == 'owner'


@pytest.mark.parametrize('skip', [None, 'false', '', 'True', 'TRUE', 'yes', '1', 'whatever', ' true', 'true '])
def test_non_true_skip_does_not_bypass_migrations(environment, skip, monkeypatch):
    monkeypatch.setenv(authority.MODE_KEY, 'owner')
    if skip is not None:
        monkeypatch.setenv('SKIP_STARTUP_MIGRATIONS', skip)
    calls = []
    monkeypatch.setattr(command, 'target_head', lambda: 'expected')
    monkeypatch.setattr(command, 'current_heads', lambda: ('expected',))
    monkeypatch.setattr(command, 'upgrade', lambda target: calls.append(target))
    assert command.main(['startup']) == 0
    assert calls == ['expected']


@pytest.mark.parametrize('mode', [None, 'owner', 'verify_only', 'disabled'])
def test_emergency_skip_neither_reads_nor_upgrades(environment, mode, monkeypatch, capsys):
    if mode is not None:
        monkeypatch.setenv(authority.MODE_KEY, mode)
    monkeypatch.setenv('SKIP_STARTUP_MIGRATIONS', 'true')
    monkeypatch.setattr(command, 'current_heads', lambda: pytest.fail('read'))
    monkeypatch.setattr(command, 'upgrade', lambda target: pytest.fail('upgrade'))
    assert command.main(['startup']) == 0
    assert 'WARNING: startup database migrations explicitly skipped' in capsys.readouterr().out
    if mode != 'owner':
        with pytest.raises(authority.MigrationAuthorityError):
            authority.require_owner()


def test_invalid_mode_cannot_hide_behind_emergency(environment, monkeypatch):
    monkeypatch.setenv(authority.MODE_KEY, 'yes')
    monkeypatch.setenv('SKIP_STARTUP_MIGRATIONS', 'true')
    assert command.main(['startup']) == 1


@pytest.mark.parametrize('mode', [None, 'disabled', 'verify_only'])
def test_nonowners_never_upgrade(environment, mode, monkeypatch):
    if mode is not None:
        monkeypatch.setenv(authority.MODE_KEY, mode)
    monkeypatch.setattr(command, 'upgrade', lambda target: pytest.fail('upgrade'))
    monkeypatch.setattr(command, 'target_head', lambda: 'expected')
    reads = []
    monkeypatch.setattr(command, 'current_heads', lambda: reads.append(1) or ('expected',))
    assert command.main(['startup']) == (0 if mode == 'verify_only' else 1)
    assert reads == ([1] if mode == 'verify_only' else [])


def test_verify_mismatch_refuses_without_upgrade(environment, monkeypatch, capsys):
    monkeypatch.setenv(authority.MODE_KEY, 'verify_only')
    monkeypatch.setattr(command, 'target_head', lambda: 'expected')
    monkeypatch.setattr(command, 'current_heads', lambda: ('old',))
    monkeypatch.setattr(command, 'upgrade', lambda target: pytest.fail('upgrade'))
    assert command.main(['verify']) == 1
    assert 'expected_migration_head_expected_got_' in capsys.readouterr().err


@pytest.mark.parametrize('mode', [None, 'disabled', 'verify_only'])
def test_promotion_refuses_without_owner(environment, mode, monkeypatch):
    if mode is not None:
        monkeypatch.setenv(authority.MODE_KEY, mode)
    monkeypatch.setattr(command, 'upgrade', lambda target: pytest.fail('upgrade'))
    assert command.main(['promote', '--source-branch', 'main', '--expected-commit', SHA,
                         '--target-head', 'expected']) == 1


@pytest.mark.parametrize('final', [('expected',), ('wrong',), ()])
def test_promotion_verifies_final_head(environment, monkeypatch, final):
    monkeypatch.setenv(authority.MODE_KEY, 'owner')
    monkeypatch.setattr(command.subprocess, 'check_output',
                        lambda args, **kw: '' if args[1] == 'status' else SHA)
    monkeypatch.setattr(command, 'target_head', lambda: 'expected')
    heads = iter([('old',), final])
    monkeypatch.setattr(command, 'current_heads', lambda: next(heads))
    calls = []
    monkeypatch.setattr(command, 'upgrade', lambda target: calls.append(target))
    result = command.main(['promote', '--source-branch', 'main', '--expected-commit', SHA,
                           '--target-head', 'expected'])
    assert calls == ['expected']
    assert result == (0 if final == ('expected',) else 1)


@pytest.mark.parametrize('command_name', ['upgrade', 'stamp', 'downgrade'])
@pytest.mark.parametrize('mode', [None, 'verify_only', 'disabled', 'yes'])
def test_direct_alembic_cannot_bypass_authority(tmp_path, command_name, mode):
    database = tmp_path / 'authority.db'
    with sqlite3.connect(database) as conn:
        conn.execute('CREATE TABLE alembic_version (version_num varchar(32) PRIMARY KEY)')
        conn.execute("INSERT INTO alembic_version VALUES ('e3f6a9b2c5d8')")
    before = database.read_bytes()
    env = {**os.environ, 'APP_ENV': 'test', 'AUTO_SYNC': 'false',
           'DATABASE_URL': f'sqlite:///{database.as_posix()}',
           'TEST_DATABASE_URL': f'sqlite:///{database.as_posix()}'}
    env.pop(authority.MODE_KEY, None)
    if mode is not None:
        env[authority.MODE_KEY] = mode
    result = subprocess.run([sys.executable, '-m', 'flask', '--app', 'app', 'db',
                             command_name, 'head' if command_name != 'downgrade' else 'base'],
                            cwd=BACKEND, env=env, text=True, capture_output=True, timeout=30)
    assert result.returncode != 0
    assert ('schema_mutation_requires_owner' in result.stderr
            or 'DATABASE_MIGRATION_MODE_must_be_explicit' in result.stderr)
    assert database.read_bytes() == before


def test_alembic_current_is_read_only_without_owner(environment):
    authority.guard_alembic(SimpleNamespace(get_context=lambda: SimpleNamespace(opts={'dont_mutate': True})))
    with pytest.raises(authority.MigrationAuthorityError):
        authority.guard_alembic(SimpleNamespace(get_context=lambda: SimpleNamespace(opts={})))


def test_owner_upgrade_executes_exact_target(environment, monkeypatch):
    monkeypatch.setenv(authority.MODE_KEY, 'owner')
    calls = []
    monkeypatch.setattr(command.subprocess, 'run', lambda args, **kw: calls.append((args, kw)))
    command.upgrade('reviewed-head')
    assert calls[0][0][-3:] == ['db', 'upgrade', 'reviewed-head']
    assert calls[0][1]['check'] is True
    assert calls[0][1]['env']['AUTO_SYNC'] == 'false'


@pytest.mark.parametrize('problem', ['source', 'commit', 'dirty', 'target', 'skip'])
def test_promotion_preflight_refuses_before_upgrade(environment, monkeypatch, problem):
    monkeypatch.setenv(authority.MODE_KEY, 'owner')
    if problem == 'skip':
        monkeypatch.setenv('SKIP_STARTUP_MIGRATIONS', 'true')
    def git(args, **kwargs):
        if args[1] == 'status':
            return ' M file' if problem == 'dirty' else ''
        return 'b' * 40 if problem == 'commit' else SHA
    monkeypatch.setattr(command.subprocess, 'check_output', git)
    monkeypatch.setattr(command, 'target_head', lambda: 'wrong' if problem == 'target' else 'expected')
    monkeypatch.setattr(command, 'current_heads', lambda: pytest.fail('read before preflight'))
    monkeypatch.setattr(command, 'upgrade', lambda target: pytest.fail('upgrade'))
    assert command.main(['promote', '--source-branch', 'feature' if problem == 'source' else 'main',
                         '--expected-commit', SHA, '--target-head', 'expected']) == 1


@pytest.mark.parametrize('heads', [(), ('old',), ('e3f6a9b2c5d8', 'extra')])
def test_shadow_mismatch_prevents_planning(heads, monkeypatch):
    from services import sync_pipeline_shadow as shadow
    from tests.test_sync_pipeline_shadow import SAFE_ENV
    monkeypatch.setattr(shadow, 'ensure_current_date_poll', lambda *a, **kw: pytest.fail('planning'))
    with pytest.raises(shadow.ShadowConfigurationError, match='expected_migration_head_'):
        shadow.run_production_shadow_cycle(env=SAFE_ENV, migration_head_reader=lambda: heads)


@pytest.mark.parametrize('mode', [None, 'owner', 'disabled', 'yes'])
def test_shadow_authority_refusal_precedes_database_access(mode):
    from services import sync_pipeline_shadow as shadow
    from tests.test_sync_pipeline_shadow import SAFE_ENV
    env = dict(SAFE_ENV)
    env.pop(authority.MODE_KEY)
    if mode is not None:
        env[authority.MODE_KEY] = mode
    with pytest.raises(shadow.ShadowConfigurationError):
        shadow.assert_shadow_ready(env=env, migration_head_reader=lambda: pytest.fail('database access'))


def test_head_inspection_emits_no_mutation(tmp_path, monkeypatch):
    from contextlib import nullcontext
    from sqlalchemy import create_engine, event
    database = tmp_path / 'heads.db'
    with sqlite3.connect(database) as connection:
        connection.execute('CREATE TABLE alembic_version (version_num varchar(32) PRIMARY KEY)')
        connection.execute("INSERT INTO alembic_version VALUES ('e3f6a9b2c5d8')")
    before = database.read_bytes()
    engine = create_engine(f'sqlite:///{database.as_posix()}')
    statements = []
    event.listen(engine, 'before_cursor_execute', lambda c, cu, s, p, ctx, many: statements.append(s))
    monkeypatch.setitem(sys.modules, 'app', SimpleNamespace(app=SimpleNamespace(app_context=nullcontext)))
    monkeypatch.setitem(sys.modules, 'utils.db', SimpleNamespace(db=SimpleNamespace(engine=engine)))
    assert command.current_heads() == ('e3f6a9b2c5d8',)
    engine.dispose()
    assert statements and all(s.lstrip().upper().startswith(('SELECT', 'PRAGMA')) for s in statements)
    assert database.read_bytes() == before


def test_startup_shell_keeps_strict_failure_and_preparation_order():
    script = (BACKEND / 'scripts/render_start.sh').read_text()
    assert 'set -euo pipefail' in script
    assert script.index('python -m scripts.database_migrations startup') < script.index(
        'python -m scripts.prepare_daily_edition_snapshot') < script.index('exec gunicorn')


def test_repository_upgrade_calls_have_named_owners():
    # Named executable paths, not a shell/Python grammar. New call sites require review.
    import re
    patterns = [r'flask[^\n]*\bdb\s+upgrade', r'alembic\s+upgrade',
                r'\bcommand\.upgrade\(', r'from flask_migrate import.*upgrade',
                r"['\"]db['\"]\s*,\s*['\"]upgrade['\"]"]
    allowed = {'.github/workflows/ci.yml', 'backend/scripts/database_migrations.py'}
    found = set()
    for path in ROOT.rglob('*'):
        relative = path.relative_to(ROOT)
        if set(relative.parts) & {'tests', 'node_modules', '.venv', 'venv', 'docs'}:
            continue
        if path.suffix not in ('.py', '.sh', '.yml', '.yaml', '.ps1', '.bat'):
            continue
        lines = [line for line in path.read_text(encoding='utf-8').splitlines()
                 if not line.lstrip().startswith('#')]
        if any(re.search(pattern, '\n'.join(lines)) for pattern in patterns):
            found.add(relative.as_posix())
    assert found == allowed
    ci = yaml.safe_load((ROOT / '.github/workflows/ci.yml').read_text())
    assert ci['jobs']['postgres-migrations']['env'][authority.MODE_KEY] == 'owner'
    assert 'localhost' in ci['jobs']['postgres-migrations']['env']['DATABASE_URL']


def test_maintenance_promotion_and_repair_are_bounded():
    maintenance = yaml.safe_load((ROOT / '.github/workflows/baseballos-production-maintenance.yml').read_text())
    step = next(s for s in maintenance['jobs']['maintain-production']['steps'] if s.get('name') == 'Run production migration')
    assert step['env'][authority.MODE_KEY] == 'owner'
    assert step['env']['DATABASE_URL'] == '${{ secrets.DATABASE_MIGRATION_URL }}'
    assert 'refs/heads/main' in step['run']
    assert 'scripts.database_migrations promote' in step['run']
    workflow = yaml.safe_load((ROOT / '.github/workflows/baseballos-sync.yml').read_text())
    for job in workflow['jobs'].values():
        for step in job.get('steps', []):
            run = step.get('run', '')
            if 'scripts.database_migrations verify' in run:
                assert step['env'][authority.MODE_KEY] == 'verify_only'
                assert 'set -euo pipefail' in run
                assert 'db upgrade' not in run
