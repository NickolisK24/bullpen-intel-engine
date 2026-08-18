"""Contract for the sharded backend CI gate and the confidence it depends on.

The backend confidence gate is split across four concurrent CI jobs. That split is
only safe while three things stay true: every collected test is owned by exactly
one shard, no two shards share a PostgreSQL database, and no shard quietly turns
on worker parallelism inside a single database. Those are the properties that were
proven once by measurement; this file is what keeps them true.

It also holds the two prerequisites a green suite can otherwise hide. Three
behaviour-freeze guards use ``origin/main`` and the appearance-team guard uses
the actual PR/integration base; under a shallow checkout those refs may not
exist, so a guard can skip without running. And frontend unit tests exercise
modules, not the bundle, so a production build that no longer compiles can sit
behind a green test job. Full checkout history and a required build step close
both, and the assertions here keep them closed.

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
FRONTEND_JOB_ID = 'frontend-tests'

# Jobs that must check out full history. The shards run the behaviour-freeze
# guards; accounting imports every backend test module during collection and has
# to see the same repository shape the shards do.
FULL_HISTORY_JOB_IDS = (SHARD_JOB_ID, ACCOUNTING_JOB_ID)

# The behaviour-freeze guards that compare this branch against a governed base.
# Each protects a frozen public or legacy contract, and each skips when the
# comparison ref is missing. Named exactly so a rename is a visible failure
# rather than an assertion that quietly stops checking anything.
FREEZE_GUARD_NODE_IDS = (
    'tests/test_appearance_team_authority.py::test_branch_touches_no_team_state_or_public_surface_files',
    'tests/test_public_team_relief_work.py::test_existing_public_routes_behavior_freeze',
    'tests/test_qa_reconciliation_scenarios.py::test_phase0e_switches_and_legacy_public_files_not_modified',
    'tests/test_snapshot_trust_freeze.py::test_frozen_legacy_what_changed_files_untouched',
)

FRONTEND_LOCKFILE = 'frontend/package-lock.json'
FRONTEND_MANIFEST = 'frontend/package.json'

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


# ══════════════════════════════════════════════════════════════════════════════
# Runtime / test dependency separation
#
# Production installs requirements.txt only. Nothing under backend/ imports
# pytest outside backend/tests/, so shipping it to Render put an unused package
# — and its advisories — on the production dependency surface.
#
# The split is only worth anything while two things stay true: the runtime file
# never regains a test dependency, and the operational workflows never quietly
# start installing the dev layer. Both are asserted here, and the second is
# derived from the workflows themselves rather than from a hand-kept list, so a
# new job cannot slip through.
# ══════════════════════════════════════════════════════════════════════════════

RUNTIME_REQUIREMENTS_PATH = os.path.join(BACKEND_ROOT, 'requirements.txt')
DEV_REQUIREMENTS_PATH = os.path.join(BACKEND_ROOT, 'requirements-dev.txt')

DEV_REQUIREMENTS_REF = 'requirements-dev.txt'
RUNTIME_REQUIREMENTS_CACHE_KEY = 'backend/requirements.txt'
DEV_REQUIREMENTS_CACHE_KEY = 'backend/requirements-dev.txt'

# The only workflows allowed to install the dev/test layer. Everything else —
# including the production sync path — stays on the runtime set.
DEV_REQUIREMENTS_WORKFLOWS = frozenset({'ci.yml', 'phantom_game_log_guard.yml'})

# ci.yml jobs that must install the dev/test layer: one collects the suite, the
# others run it.
DEV_DEPENDENCY_JOB_IDS = (ACCOUNTING_JOB_ID, SHARD_JOB_ID)

# The migration job deliberately stays on the runtime set. It runs only
# `flask db upgrade`, which is the production startup path, so keeping it here
# proves the runtime requirements alone are sufficient to boot production.
RUNTIME_ONLY_JOB_ID = 'postgres-migrations'


def _workflow_paths():
    return sorted(
        os.path.join(WORKFLOWS_DIR, name)
        for name in os.listdir(WORKFLOWS_DIR)
        if name.endswith(('.yml', '.yaml'))
    )


def _setup_python_steps(job):
    return [
        step for step in job.get('steps', [])
        if 'actions/setup-python' in str(step.get('uses', ''))
    ]


def _cache_dependency_paths(step):
    raw = (step.get('with') or {}).get('cache-dependency-path') or ''
    return [line.strip() for line in str(raw).splitlines() if line.strip()]


def test_the_runtime_requirements_do_not_carry_pytest():
    """Production must not install a test framework it never imports."""
    with open(RUNTIME_REQUIREMENTS_PATH, encoding='utf-8') as handle:
        declarations = [
            line.strip().lower()
            for line in handle
            if line.strip() and not line.lstrip().startswith('#')
        ]
    offenders = [line for line in declarations if line.startswith('pytest')]
    assert offenders == [], (
        'pytest belongs in requirements-dev.txt, not the production runtime set: '
        f'{offenders}'
    )


def test_the_dev_requirements_exist_and_include_the_runtime_set():
    """A dev environment must be a superset of production, not a second resolution."""
    assert os.path.isfile(DEV_REQUIREMENTS_PATH), (
        'backend/requirements-dev.txt is the declared development/test layer'
    )
    with open(DEV_REQUIREMENTS_PATH, encoding='utf-8') as handle:
        body = handle.read()
    assert '-r requirements.txt' in body, (
        'requirements-dev.txt must pull in the runtime set so developers and CI '
        'resolve the same production dependencies plus test tooling'
    )


def test_the_dev_requirements_declare_pytest():
    with open(DEV_REQUIREMENTS_PATH, encoding='utf-8') as handle:
        declarations = [
            line.strip().lower()
            for line in handle
            if line.strip() and not line.lstrip().startswith('#')
        ]
    assert any(line.startswith('pytest') for line in declarations), (
        'requirements-dev.txt is where pytest is pinned'
    )


def test_only_test_consuming_workflows_install_the_dev_requirements():
    """Operational workflows stay on the runtime set.

    Repointing them wholesale would put the test tooling back on every
    production and scheduled run, which is the thing the split removes.
    """
    leaked = []
    for path in _workflow_paths():
        name = os.path.basename(path)
        if name in DEV_REQUIREMENTS_WORKFLOWS:
            continue
        with open(path, encoding='utf-8') as handle:
            if DEV_REQUIREMENTS_REF in handle.read():
                leaked.append(name)
    assert leaked == [], (
        'these workflows do not run tests and must install the runtime '
        f'requirements only: {leaked}'
    )


def test_the_production_sync_workflow_stays_on_the_runtime_requirements():
    """Called out separately because this is the scheduled production path."""
    path = os.path.join(WORKFLOWS_DIR, 'baseballos-sync.yml')
    with open(path, encoding='utf-8') as handle:
        body = handle.read()
    assert DEV_REQUIREMENTS_REF not in body, (
        'baseballos-sync.yml is the scheduled production sync; it does not run '
        'pytest and must never install the development/test layer'
    )
    assert 'pip install -r backend/requirements.txt' in body


def test_the_migration_job_installs_only_the_runtime_requirements(ci_workflow):
    """Keeping this job runtime-only is what proves production can boot on it."""
    job = ci_workflow['jobs'][RUNTIME_ONLY_JOB_ID]
    commands = ' '.join(_run_blocks(job))
    assert DEV_REQUIREMENTS_REF not in commands, (
        f'{RUNTIME_ONLY_JOB_ID} runs only `flask db upgrade`. Leaving it on the '
        'runtime set is the evidence that the production startup path needs no '
        'test dependencies.'
    )
    assert 'pip install -r requirements.txt' in commands


@pytest.mark.parametrize('job_id', DEV_DEPENDENCY_JOB_IDS)
def test_backend_test_jobs_install_the_dev_requirements(ci_workflow, job_id):
    commands = ' '.join(_run_blocks(ci_workflow['jobs'][job_id]))
    assert f'pip install -r {DEV_REQUIREMENTS_REF}' in commands, (
        f'{job_id} collects or runs the backend suite, so it needs the '
        'development/test requirements'
    )


@pytest.mark.parametrize('job_id', DEV_DEPENDENCY_JOB_IDS)
def test_dev_dependency_jobs_cache_on_both_requirements_files(ci_workflow, job_id):
    """requirements-dev.txt includes requirements.txt, so both decide the install."""
    steps = _setup_python_steps(ci_workflow['jobs'][job_id])
    assert steps, f'{job_id} does not set up Python'
    for step in steps:
        paths = _cache_dependency_paths(step)
        assert RUNTIME_REQUIREMENTS_CACHE_KEY in paths, (
            f'{job_id} must keep {RUNTIME_REQUIREMENTS_CACHE_KEY} in its pip cache '
            f'key; the dev file includes it. Got {paths}'
        )
        assert DEV_REQUIREMENTS_CACHE_KEY in paths, (
            f'{job_id} installs the dev requirements, so {DEV_REQUIREMENTS_CACHE_KEY} '
            f'must be part of its pip cache key. Got {paths}'
        )


def test_every_job_that_runs_the_suite_installs_the_dev_requirements():
    """Derived from the workflows themselves, so a new test job cannot slip through."""
    offenders = []
    for path in _workflow_paths():
        with open(path, encoding='utf-8') as handle:
            workflow = yaml.safe_load(handle)
        if not isinstance(workflow, dict):
            continue
        for job_id, job in (workflow.get('jobs') or {}).items():
            blocks = _run_blocks(job)
            runs_suite = any(
                'pytest' in block or 'ci_shard.py' in block for block in blocks
            )
            if not runs_suite:
                continue
            if not any(DEV_REQUIREMENTS_REF in block for block in blocks):
                offenders.append((os.path.basename(path), job_id))
    assert offenders == [], (
        'these jobs run pytest or drive pytest collection but do not install the '
        f'development/test requirements: {offenders}'
    )


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


# ══════════════════════════════════════════════════════════════════════════════
# Full checkout history — the prerequisite the behaviour-freeze guards need
# ══════════════════════════════════════════════════════════════════════════════
@pytest.fixture(scope='module')
def frontend_job(ci_workflow):
    return ci_workflow['jobs'][FRONTEND_JOB_ID]


def _checkout_steps(job):
    return [
        step for step in job.get('steps', [])
        if 'actions/checkout' in str(step.get('uses', ''))
    ]


def _git_stdout(*args):
    """Run a read-only git command from the repository root."""
    return subprocess.run(
        ['git', *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize('job_id', FULL_HISTORY_JOB_IDS)
def test_backend_jobs_check_out_full_history(ci_workflow, job_id):
    steps = _checkout_steps(ci_workflow['jobs'][job_id])
    assert steps, f'{job_id} does not check out the repository'
    for step in steps:
        assert step['uses'].startswith('actions/checkout@v4'), (
            f'{job_id} uses {step["uses"]!r}; the contract is pinned to checkout@v4'
        )
        options = step.get('with') or {}
        assert options.get('fetch-depth') == 0, (
            f'{job_id} checks out with fetch-depth {options.get("fetch-depth")!r}. '
            'The behaviour-freeze guards diff against origin/main; without full '
            'history that ref is missing, the diff fails, and the guards skip '
            'instead of running.'
        )


@pytest.mark.parametrize('job_id', FULL_HISTORY_JOB_IDS)
def test_no_backend_job_checks_out_shallow(ci_workflow, job_id):
    """A shallow depth is worse than no setting: it looks deliberate."""
    for step in _checkout_steps(ci_workflow['jobs'][job_id]):
        depth = (step.get('with') or {}).get('fetch-depth')
        assert depth != 1, f'{job_id} pins fetch-depth: 1, which hides origin/main'
        assert not (isinstance(depth, int) and depth > 0), (
            f'{job_id} pins a shallow fetch-depth ({depth!r}); only 0 gives origin/main'
        )


def test_every_job_that_runs_pytest_has_full_history(ci_workflow):
    """Derived from the workflow itself, so a new backend job cannot slip through."""
    shallow = []
    for job_id, job in ci_workflow['jobs'].items():
        runs_backend = any(
            'pytest' in block or 'ci_shard.py' in block
            for block in _run_blocks(job)
        )
        if not runs_backend:
            continue
        for step in _checkout_steps(job):
            if (step.get('with') or {}).get('fetch-depth') != 0:
                shallow.append(job_id)
    assert shallow == [], (
        f'these jobs run backend tests without full history: {shallow}'
    )


@pytest.mark.parametrize('node_id', FREEZE_GUARD_NODE_IDS)
def test_each_behaviour_freeze_guard_is_still_collected(collection, node_id):
    assert node_id in collection['full'], (
        f'{node_id} is no longer collected. It protects a frozen public or legacy '
        'contract; if it was renamed, update FREEZE_GUARD_NODE_IDS deliberately.'
    )


@pytest.mark.parametrize('node_id', FREEZE_GUARD_NODE_IDS)
def test_each_behaviour_freeze_guard_keeps_its_governed_diff_baseline(node_id):
    """The guards' prerequisite is real, so supplying history is not cosmetic."""
    path = os.path.join(BACKEND_ROOT, node_id.split('::', 1)[0])
    with open(path, encoding='utf-8') as handle:
        source = handle.read()
    if 'test_appearance_team_authority.py' in node_id:
        assert 'changed_files_for_current_change' in source, (
            f'{node_id} no longer resolves the current PR/integration diff'
        )
    else:
        assert 'origin/main' in source, (
            f'{node_id} no longer diffs against origin/main; the full-history '
            'requirement in ci.yml may no longer describe why it exists'
        )


def test_every_behaviour_freeze_guard_runs_in_a_full_history_job(manifest, ci_workflow):
    """Whichever shard owns a guard, that shard checks out full history."""
    owner = {}
    for shard_id in range(1, SHARD_COUNT + 1):
        for entry in manifest['shards'][str(shard_id)]['files']:
            owner[entry['path']] = shard_id

    shard_depth = (
        (_checkout_steps(ci_workflow['jobs'][SHARD_JOB_ID])[0].get('with') or {})
        .get('fetch-depth')
    )
    unowned = []
    for node_id in FREEZE_GUARD_NODE_IDS:
        path = node_id.split('::', 1)[0]
        if path not in owner:
            unowned.append(path)
    assert unowned == [], f'freeze guards owned by no shard: {unowned}'
    assert shard_depth == 0, (
        'the shard job that runs the freeze guards does not check out full history'
    )


# ══════════════════════════════════════════════════════════════════════════════
# Deterministic frontend installation and production build validation
# ══════════════════════════════════════════════════════════════════════════════
def test_the_frontend_job_installs_from_the_committed_lockfile(frontend_job):
    commands = ' '.join(_run_blocks(frontend_job))
    assert 'npm ci --no-audit --no-fund' in commands, (
        'the frontend job must install exactly what the lockfile pins'
    )


def test_the_frontend_job_never_falls_back_to_npm_install(frontend_job):
    for block in _run_blocks(frontend_job):
        assert not re.search(r'(?:^|\s|;|&&|\|)npm\s+install(?:\s|$)', block), (
            f'npm install resolves versions afresh and defeats the lockfile: {block!r}'
        )


def test_the_frontend_job_does_not_delete_the_lockfile(ci_workflow):
    """CI that rewrites its own inputs cannot prove anything about what ships."""
    offenders = []
    for job_id, job in ci_workflow['jobs'].items():
        for block in _run_blocks(job):
            if re.search(r'\brm\b[^\n]*package-lock\.json', block):
                offenders.append((job_id, block.strip()))
    assert offenders == [], f'the workflow deletes the committed lockfile: {offenders}'


def test_the_frontend_job_does_not_delete_node_modules_as_an_install_workaround(ci_workflow):
    offenders = []
    for job_id, job in ci_workflow['jobs'].items():
        for block in _run_blocks(job):
            if re.search(r'\brm\b[^\n]*node_modules', block):
                offenders.append((job_id, block.strip()))
    assert offenders == [], (
        'deleting node_modules was a workaround for a tracked install tree that no '
        f'longer exists; npm ci already starts from a clean tree: {offenders}'
    )


def test_the_frontend_job_caches_npm_against_the_lockfile(frontend_job):
    setup = [
        step for step in frontend_job['steps']
        if 'actions/setup-node' in str(step.get('uses', ''))
    ]
    assert setup, 'the frontend job does not set up Node'
    for step in setup:
        assert step['uses'].startswith('actions/setup-node@v4')
        options = step.get('with') or {}
        assert options.get('cache') == 'npm', (
            f'setup-node does not enable the npm cache: {options!r}'
        )
        assert options.get('cache-dependency-path') == FRONTEND_LOCKFILE, (
            'the npm cache key must come from the committed lockfile, so a '
            f'dependency change invalidates it: {options.get("cache-dependency-path")!r}'
        )


def test_the_frontend_job_runs_both_the_tests_and_the_production_build(frontend_job):
    commands = _run_blocks(frontend_job)
    assert any(re.search(r'\bnpm\s+test\b', block) for block in commands), (
        'the frontend job no longer runs npm test'
    )
    assert any(re.search(r'\bnpm\s+run\s+build\b', block) for block in commands), (
        'unit tests do not prove the production bundle compiles; npm run build is required'
    )


def test_the_frontend_build_runs_after_the_tests(frontend_job):
    """Tests first: a failing unit test should be reported before a failing bundle."""
    order = []
    for index, block in enumerate(_run_blocks(frontend_job)):
        if re.search(r'\bnpm\s+run\s+build\b', block):
            order.append(('build', index))
        elif re.search(r'\bnpm\s+test\b', block):
            order.append(('test', index))
    names = [name for name, _ in order]
    assert names.index('test') < names.index('build'), (
        f'npm run build must not precede npm test: {order}'
    )


def test_the_build_step_is_not_allowed_to_fail_softly(frontend_job):
    for step in frontend_job['steps']:
        if re.search(r'\bnpm\s+run\s+build\b', str(step.get('run', ''))):
            assert step.get('continue-on-error') is not True, (
                'a build that cannot fail the job proves nothing'
            )


# ══════════════════════════════════════════════════════════════════════════════
# The frontend dependency manifest is an input to CI, never an output
# ══════════════════════════════════════════════════════════════════════════════
#
# These assert repository content first and consult git only as a second,
# stronger check. Content is what `npm ci` actually depends on, and it holds in
# any checkout; git availability is an environment detail. Where git IS available
# and disagrees, that is a failure — never a skip.
def test_the_committed_lockfile_can_satisfy_npm_ci():
    """npm ci refuses to run without a lockfile, and fails without the runner's binary."""
    path = os.path.join(REPO_ROOT, FRONTEND_LOCKFILE)
    assert os.path.isfile(path), (
        f'{FRONTEND_LOCKFILE} is missing; npm ci has nothing authoritative to install from'
    )
    with open(path, encoding='utf-8') as handle:
        lockfile = json.load(handle)
    assert lockfile.get('lockfileVersion', 0) >= 3, (
        f'unexpected lockfileVersion {lockfile.get("lockfileVersion")!r}'
    )
    packages = lockfile.get('packages') or {}
    assert 'node_modules/@rollup/rollup-linux-x64-gnu' in packages, (
        'the lockfile does not pin the Linux Rollup binary the runner needs. That '
        'missing entry is what the old delete-the-lockfile workaround papered over; '
        'npm ci depends on it being present.'
    )

    result = _git_stdout('ls-files', '--error-unmatch', FRONTEND_LOCKFILE)
    if result.returncode != 0 and 'not a git repository' not in result.stderr.lower():
        raise AssertionError(f'{FRONTEND_LOCKFILE} exists but is not tracked')


def test_frontend_node_modules_stays_out_of_the_repository():
    with open(os.path.join(REPO_ROOT, '.gitignore'), encoding='utf-8') as handle:
        ignored = {line.strip() for line in handle}
    assert {'node_modules/', 'frontend/node_modules/'} & ignored, (
        '.gitignore no longer ignores the frontend install tree'
    )

    result = _git_stdout('ls-files', 'frontend/node_modules')
    if result.returncode == 0:
        tracked = [line for line in result.stdout.splitlines() if line.strip()]
        assert tracked == [], (
            f'{len(tracked)} file(s) under frontend/node_modules are tracked; a '
            'committed install tree is what made the old delete-and-reinstall step '
            'look necessary'
        )


def test_the_frontend_dependency_files_are_not_ci_outputs(ci_workflow):
    """Nothing in CI may write package.json or package-lock.json."""
    offenders = []
    for job_id, job in ci_workflow['jobs'].items():
        for block in _run_blocks(job):
            for target in ('package-lock.json', 'package.json'):
                if re.search(rf'>\s*{re.escape(target)}|\brm\b[^\n]*{re.escape(target)}', block):
                    offenders.append((job_id, target))
                if re.search(r'npm\s+(install|update|i)\b', block):
                    offenders.append((job_id, 'npm install/update rewrites the lockfile'))
    assert offenders == [], f'CI writes its own dependency inputs: {sorted(set(offenders))}'
