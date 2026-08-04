"""Contract for the sharded backend CI gate.

The backend confidence gate is split across four concurrent CI jobs. That split is
only safe while three things stay true: every collected test is owned by exactly
one shard, no two shards share a PostgreSQL database, and no shard quietly turns
on worker parallelism inside a single database. Those are the properties that were
proven once by measurement; this file is what keeps them true.

Deliberately database-free. It reads the checked-in manifest, drives pytest
collection through subprocesses, and parses `.github/workflows/ci.yml`.
"""

import json
import os
import re
import subprocess
import sys

import pytest
import yaml


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BACKEND_ROOT = os.path.join(REPO_ROOT, 'backend')
TESTS_DIR = os.path.join(BACKEND_ROOT, 'tests')
WORKFLOWS_DIR = os.path.join(REPO_ROOT, '.github', 'workflows')

MANIFEST_PATH = os.path.join(TESTS_DIR, 'ci_shard_manifest.json')
SCRIPT_PATH = os.path.join(BACKEND_ROOT, 'scripts', 'ci_shard.py')
CI_WORKFLOW_PATH = os.path.join(WORKFLOWS_DIR, 'ci.yml')

SHARD_COUNT = 4
SUPPORTED_SCHEMA_VERSIONS = (1,)
SHARD_JOB_ID = 'backend-postgres-tests'
ACCOUNTING_JOB_ID = 'backend-collection-accounting'

# Operational workflows this package must not touch. Listed explicitly so that
# deleting or renaming one is a visible failure rather than a silent gap.
OPERATIONAL_WORKFLOWS = (
    'appearance_team_backfill_2026.yml',
    'baseballos-intraday-repair.yml',
    'baseballos-production-maintenance.yml',
    'baseballos-sync.yml',
    'canonical_season_bullpen_aggregation.yml',
    'manual-game-driven-noop-qualification.yml',
    'manual-noop-qualification-candidate-audit.yml',
    'manual-postgame-publication-incident-audit.yml',
    'official-starter-alignment-audit.yml',
    'official_pitching_line_completeness.yml',
    'official_pitching_line_matt_festa_apply.yml',
    'official_pitching_line_repair_apply.yml',
    'official_pitching_line_repair_closeout.yml',
    'official_pitching_line_repair_plan.yml',
    'official_pitching_line_transition_diagnostic.yml',
    'phantom_game_log_guard.yml',
    'phantom_game_log_reconciliation.yml',
    'unresolved_appearance_team_diagnostic_2026.yml',
    'unresolved_appearance_team_repair_2026.yml',
)

# Worker parallelism inside one shard is prohibited: concurrent pytest workers
# sharing a single PostgreSQL database collide on create_all/drop_all DDL, on
# unique constraints, and on the database-global advisory locks the sync services
# take. Isolation between shards is what makes the split safe.
#
# These are matched against pytest *invocations*, not against whole shell blocks,
# so an unrelated flag elsewhere in a script is not mistaken for worker
# parallelism.
WORKER_FLAG_PATTERNS = (
    re.compile(r'(?:^|\s)-n(?:\s|=|\d|$)'),
    re.compile(r'--numprocesses'),
    re.compile(r'--dist(?:\s|=)'),
)
# The plugin must not appear anywhere in a workflow command.
XDIST_PATTERN = re.compile(r'xdist')

PYTEST_INVOCATION = re.compile(r'(?:^|\s|;|&&|\|)(?:-m\s+)?pytest(?:\s|$)')


# ── shared fixtures ───────────────────────────────────────────────────────────
@pytest.fixture(scope='module')
def manifest():
    with open(MANIFEST_PATH, encoding='utf-8') as handle:
        return json.load(handle)


@pytest.fixture(scope='module')
def assigned_paths(manifest):
    """Every path in the manifest, in shard order, duplicates preserved."""
    paths = []
    for shard_id in range(1, SHARD_COUNT + 1):
        for entry in manifest['shards'][str(shard_id)]['files']:
            paths.append(entry['path'])
    return paths


@pytest.fixture(scope='module')
def ci_workflow():
    with open(CI_WORKFLOW_PATH, encoding='utf-8') as handle:
        return yaml.safe_load(handle)


@pytest.fixture(scope='module')
def shard_job(ci_workflow):
    return ci_workflow['jobs'][SHARD_JOB_ID]


def _collection_environment():
    """Disposable, database-free environment for a collection subprocess.

    Importing the test modules imports ``app``, which needs a local DATABASE_URL
    at import time but never opens a connection during collection. Pinning
    in-memory SQLite keeps this contract identical on a laptop and in a CI job
    that has no PostgreSQL service.
    """
    env = dict(os.environ)
    env['APP_ENV'] = 'test'
    env['AUTO_SYNC'] = 'false'
    env['DATABASE_URL'] = 'sqlite:///:memory:'
    env['TEST_DATABASE_URL'] = 'sqlite:///:memory:'
    return env


def _collect_node_ids(targets):
    """Return pytest node IDs for ``targets``, collected from backend/."""
    result = subprocess.run(
        [
            sys.executable, '-m', 'pytest', *targets,
            '--collect-only', '-q', '-p', 'no:cacheprovider',
        ],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
        env=_collection_environment(),
    )
    assert result.returncode == 0, (
        f'pytest collection failed for {targets[:3]}…\n'
        f'{result.stderr[-4000:]}\n{result.stdout[-4000:]}'
    )
    node_ids = {
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip().startswith('tests/') and '::' in line
    }
    assert node_ids, f'no node IDs collected for {targets[:3]}…'
    return node_ids


@pytest.fixture(scope='module')
def collection(manifest):
    """Collect the full suite once, then each shard's file list once.

    Five subprocess collections, shared across every test in this module, so the
    node-ID accounting costs one pass rather than one per assertion.
    """
    full = _collect_node_ids(['tests'])
    per_shard = {}
    for shard_id in range(1, SHARD_COUNT + 1):
        files = [entry['path'] for entry in manifest['shards'][str(shard_id)]['files']]
        per_shard[shard_id] = _collect_node_ids(files)
    return {'full': full, 'per_shard': per_shard}


def _run_blocks(job):
    """Every shell command string in a job's steps."""
    return [step['run'] for step in job.get('steps', []) if isinstance(step.get('run'), str)]


# ── manifest shape ────────────────────────────────────────────────────────────
def test_the_shard_manifest_and_script_are_checked_in():
    assert os.path.isfile(MANIFEST_PATH), (
        'backend/tests/ci_shard_manifest.json is the only source of shard ownership'
    )
    assert os.path.isfile(SCRIPT_PATH), 'backend/scripts/ci_shard.py is missing'


def test_manifest_schema_version_is_supported(manifest):
    assert manifest['schema_version'] in SUPPORTED_SCHEMA_VERSIONS


def test_manifest_declares_exactly_four_shards(manifest):
    assert manifest['shard_count'] == SHARD_COUNT
    assert set(manifest['shards']) == {str(index) for index in range(1, SHARD_COUNT + 1)}


def test_no_shard_is_empty(manifest):
    for shard_id in range(1, SHARD_COUNT + 1):
        files = manifest['shards'][str(shard_id)]['files']
        assert files, f'shard {shard_id} owns no test files'


def test_no_test_file_is_assigned_to_more_than_one_shard(assigned_paths):
    duplicates = sorted({path for path in assigned_paths if assigned_paths.count(path) > 1})
    assert duplicates == [], f'assigned to multiple shards: {duplicates}'


def test_every_assigned_path_exists_on_disk(assigned_paths):
    missing = [
        path for path in assigned_paths
        if not os.path.isfile(os.path.join(BACKEND_ROOT, path))
    ]
    assert missing == [], f'manifest names files that do not exist: {missing}'


def test_every_assigned_path_stays_inside_backend_tests(assigned_paths):
    tests_root = os.path.realpath(TESTS_DIR)
    escaping = []
    for path in assigned_paths:
        resolved = os.path.realpath(os.path.join(BACKEND_ROOT, path))
        if not resolved.startswith(tests_root + os.sep):
            escaping.append(path)
    assert escaping == [], f'paths escape backend/tests: {escaping}'


def test_every_assigned_path_names_a_backend_test_module(assigned_paths):
    malformed = [
        path for path in assigned_paths
        if not (path.startswith('tests/')
                and path.rsplit('/', 1)[-1].startswith('test_')
                and path.endswith('.py'))
    ]
    assert malformed == [], f'paths are not tests/test_*.py modules: {malformed}'


# ── file-level and node-level completeness ────────────────────────────────────
def test_every_collected_test_file_is_assigned_exactly_once(assigned_paths, collection):
    collected = {node_id.split('::', 1)[0] for node_id in collection['full']}
    unassigned = sorted(collected - set(assigned_paths))
    assert unassigned == [], (
        'these collected test files are in no shard. A new test file fails this '
        'check on purpose — regenerate the manifest deliberately with '
        '"python scripts/ci_shard.py generate --timings <path>" and review the '
        f'diff: {unassigned}'
    )


def test_the_manifest_carries_no_stale_files(assigned_paths, collection):
    collected = {node_id.split('::', 1)[0] for node_id in collection['full']}
    stale = sorted(set(assigned_paths) - collected)
    assert stale == [], f'manifest names files pytest no longer collects: {stale}'


def test_the_four_shards_collect_the_whole_suite(collection):
    union = set()
    for node_ids in collection['per_shard'].values():
        union |= node_ids
    missing = sorted(collection['full'] - union)
    extra = sorted(union - collection['full'])
    assert missing == [], f'{len(missing)} node ID(s) would run in no shard: {missing[:10]}'
    assert extra == [], f'{len(extra)} node ID(s) run in a shard but not the full suite: {extra[:10]}'


def test_no_two_shards_collect_the_same_node_id(collection):
    overlaps = []
    shard_ids = sorted(collection['per_shard'])
    for index, left in enumerate(shard_ids):
        for right in shard_ids[index + 1:]:
            shared = collection['per_shard'][left] & collection['per_shard'][right]
            if shared:
                overlaps.append((left, right, sorted(shared)[:5]))
    assert overlaps == [], f'shards collect overlapping node IDs: {overlaps}'


# ── workflow topology ─────────────────────────────────────────────────────────
def test_the_backend_shard_job_is_a_four_entry_matrix(shard_job):
    matrix = shard_job['strategy']['matrix']
    assert matrix['shard'] == [1, 2, 3, 4], (
        f'expected a four-entry shard matrix, got {matrix.get("shard")!r}'
    )


def test_the_shard_matrix_does_not_fail_fast(shard_job):
    assert shard_job['strategy']['fail-fast'] is False, (
        'one failing shard must not cancel the other three; the founder needs '
        'every shard result from a single run'
    )


def test_each_shard_gets_its_own_database(shard_job):
    database_url = shard_job['env']['DATABASE_URL']
    test_database_url = shard_job['env']['TEST_DATABASE_URL']
    service_database = shard_job['services']['postgres']['env']['POSTGRES_DB']

    for value in (database_url, test_database_url, service_database):
        assert '${{ matrix.shard }}' in value, (
            f'{value!r} does not vary per shard — two shards would share one '
            'database, which is exactly the collision this split avoids'
        )
    assert database_url == test_database_url, (
        'DATABASE_URL and TEST_DATABASE_URL must name the same shard database'
    )

    names = {
        service_database.replace('${{ matrix.shard }}', str(shard_id))
        for shard_id in range(1, SHARD_COUNT + 1)
    }
    assert len(names) == SHARD_COUNT, f'shard database names are not distinct: {sorted(names)}'


def test_every_shard_database_name_satisfies_the_disposable_guard(shard_job):
    """backend/tests/db_config.py only allows a local database whose name contains 'test'."""
    template = shard_job['services']['postgres']['env']['POSTGRES_DB']
    for shard_id in range(1, SHARD_COUNT + 1):
        name = template.replace('${{ matrix.shard }}', str(shard_id))
        assert 'test' in name.lower(), (
            f'{name!r} would be refused by assert_disposable_test_target'
        )


def test_each_shard_runs_its_own_postgres_16_service(shard_job):
    service = shard_job['services']['postgres']
    assert service['image'] == 'postgres:16'
    assert 'pg_isready' in service['options']
    assert '5432:5432' in service['ports']


def test_each_shard_has_a_twenty_minute_timeout(shard_job):
    assert shard_job['timeout-minutes'] == 20


def test_the_shard_command_takes_its_file_list_from_the_shard_script(shard_job):
    commands = ' '.join(_run_blocks(shard_job))
    assert 'ci_shard.py files --shard' in commands, (
        'shard file lists must come from the manifest, never from a handwritten '
        'list in the workflow'
    )
    assert 'tests/test_' not in commands, (
        'the workflow must not name individual test files; ownership lives in '
        'backend/tests/ci_shard_manifest.json'
    )


def test_the_shard_command_keeps_the_reporting_flags(shard_job):
    pytest_commands = [block for block in _run_blocks(shard_job) if 'pytest' in block]
    assert pytest_commands, 'the shard job runs no pytest command'
    joined = ' '.join(pytest_commands)
    for flag in ('-q', '-ra', '--tb=short', '--durations='):
        assert flag in joined, f'shard pytest command is missing {flag}'


def test_the_shard_job_refuses_an_empty_file_list(shard_job):
    commands = ' '.join(_run_blocks(shard_job))
    assert 'SHARD_FILE_COUNT' in commands or 'no files' in commands, (
        'an empty shard file list must fail the job rather than pass vacuously'
    )


def test_the_shard_job_writes_a_step_summary(shard_job):
    commands = ' '.join(_run_blocks(shard_job))
    assert 'GITHUB_STEP_SUMMARY' in commands, (
        'each shard must report its number, database, and file list'
    )


# ── prohibited worker parallelism ─────────────────────────────────────────────
def _workflow_files():
    return sorted(
        os.path.join(WORKFLOWS_DIR, name)
        for name in os.listdir(WORKFLOWS_DIR)
        if name.endswith(('.yml', '.yaml'))
    )


def _pytest_invocations(block):
    """Return the logical command lines in ``block`` that invoke pytest.

    Backslash continuations are joined first so a multi-line pytest command is
    inspected as the single command it actually is.
    """
    joined = re.sub(r'\\\s*\n\s*', ' ', block)
    return [line for line in joined.splitlines() if PYTEST_INVOCATION.search(line)]


def test_no_workflow_command_enables_pytest_worker_parallelism():
    offenders = []
    for path in _workflow_files():
        with open(path, encoding='utf-8') as handle:
            workflow = yaml.safe_load(handle)
        for job_id, job in (workflow.get('jobs') or {}).items():
            for block in _run_blocks(job):
                if XDIST_PATTERN.search(block):
                    offenders.append((os.path.basename(path), job_id, 'xdist'))
                for line in _pytest_invocations(block):
                    for pattern in WORKER_FLAG_PATTERNS:
                        if pattern.search(line):
                            offenders.append(
                                (os.path.basename(path), job_id, pattern.pattern, line.strip())
                            )
    assert offenders == [], (
        'pytest worker parallelism inside a single database was measured unsafe '
        f'and is prohibited: {offenders}'
    )


def test_the_backend_requirements_do_not_carry_pytest_xdist():
    with open(os.path.join(BACKEND_ROOT, 'requirements.txt'), encoding='utf-8') as handle:
        requirements = handle.read().lower()
    assert 'xdist' not in requirements


# ── preserved CI behaviour ────────────────────────────────────────────────────
def test_the_migration_job_still_upgrades_a_fresh_postgres(ci_workflow):
    job = ci_workflow['jobs']['postgres-migrations']
    assert job['services']['postgres']['image'] == 'postgres:16'
    assert any('flask db upgrade' in block for block in _run_blocks(job))


def test_the_frontend_job_still_runs_the_frontend_suite(ci_workflow):
    job = ci_workflow['jobs']['frontend-tests']
    assert job['defaults']['run']['working-directory'] == 'frontend'
    assert any('npm test' in block for block in _run_blocks(job))


def test_the_collection_accounting_job_runs_the_verification(ci_workflow):
    job = ci_workflow['jobs'][ACCOUNTING_JOB_ID]
    commands = ' '.join(_run_blocks(job))
    assert 'ci_shard.py verify' in commands
    assert 'GITHUB_STEP_SUMMARY' in commands
    assert 'services' not in job, (
        'collection accounting proves coverage and must not need a database'
    )
    assert 'generate' not in commands, (
        'CI must never regenerate the manifest; rebalancing is a reviewed change'
    )


def test_superseded_runs_are_still_cancelled(ci_workflow):
    concurrency = ci_workflow['concurrency']
    assert concurrency['cancel-in-progress'] is True
    assert 'github.ref' in concurrency['group']


def test_the_ci_workflow_keeps_its_name_and_triggers(ci_workflow):
    assert ci_workflow['name'] == 'CI'
    triggers = ci_workflow.get(True) or ci_workflow.get('on')
    assert set(triggers) == {'push', 'pull_request', 'workflow_dispatch'}
    assert triggers['push']['branches'] == ['**']


# ── operational workflows are out of scope for this package ───────────────────
def test_every_operational_workflow_is_still_present():
    missing = [
        name for name in OPERATIONAL_WORKFLOWS
        if not os.path.isfile(os.path.join(WORKFLOWS_DIR, name))
    ]
    assert missing == [], f'operational workflows disappeared: {missing}'


def test_shard_infrastructure_stayed_out_of_the_operational_workflows():
    """The sharding package touches ci.yml and nothing else under .github/workflows."""
    leaked = []
    for name in OPERATIONAL_WORKFLOWS:
        with open(os.path.join(WORKFLOWS_DIR, name), encoding='utf-8') as handle:
            body = handle.read()
        for token in ('ci_shard', 'matrix.shard', 'baseballos_ci_tests_'):
            if token in body:
                leaked.append((name, token))
    assert leaked == [], f'shard infrastructure leaked into operational workflows: {leaked}'


def test_the_phantom_guard_still_runs_its_focused_postgres_tests():
    path = os.path.join(WORKFLOWS_DIR, 'phantom_game_log_guard.yml')
    with open(path, encoding='utf-8') as handle:
        workflow = yaml.safe_load(handle)
    job = workflow['jobs']['focused-postgres-tests']
    commands = ' '.join(_run_blocks(job))
    assert 'tests/test_phantom_game_log_reconciliation.py' in commands
    assert 'tests/test_zero_out_game_log_ingestion_guard.py' in commands
