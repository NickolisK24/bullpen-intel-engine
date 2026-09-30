"""Manual Team State coverage diagnostic — workflow contract.

The reviewed workflow source is the authority for how the production diagnostic
can be invoked. These tests hold it to: dispatch-only, main-only, owner-only,
typed confirmation, exactly one of team or league, the existing production
DATABASE_URL secret and no other production credential, read-only at the
connection and the script, one production-data command, a scan before upload,
and no repair, sync, publication, migration or mutation command anywhere.
"""

import re
import subprocess
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / '.github/workflows/manual-team-state-coverage-diagnostic.yml'

JOB = 'team-state-coverage-diagnostic'
REPOSITORY = 'NickolisK24/bullpen-intel-engine'
CONFIRMATION = 'RUN READ ONLY TEAM STATE DIAGNOSTIC'
VALIDATE = 'Refuse an unauthorized or invalid invocation'
RUN = 'Run the read-only Team State coverage diagnostic'
SCAN = 'Scan the diagnostic artifact'
UPLOAD = 'Upload the diagnostic artifact'
GATE = 'Final diagnostic gate'

# PyYAML parses the unquoted `on:` key as the boolean True.
ON = True
EXPRESSION = re.compile(r'\$\{\{')


@pytest.fixture(scope='module')
def workflow_text():
    return WORKFLOW_PATH.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def workflow(workflow_text):
    return yaml.safe_load(workflow_text)


@pytest.fixture(scope='module')
def job(workflow):
    return workflow['jobs'][JOB]


@pytest.fixture(scope='module')
def steps(job):
    return job['steps']


def _step(steps, name):
    for step in steps:
        if step.get('name') == name:
            return step
    raise AssertionError(f'no step named {name!r}')


def _index(steps, name):
    return steps.index(_step(steps, name))


# ── Trigger surface and governance ──────────────────────────────────────────

def test_workflow_dispatch_is_the_only_trigger(workflow):
    assert set(workflow[ON]) == {'workflow_dispatch'}


def test_the_job_runs_only_from_main_in_this_repository_for_the_owner(job):
    condition = ' '.join(job['if'].split())
    assert "github.event_name == 'workflow_dispatch'" in condition
    assert f"github.repository == '{REPOSITORY}'" in condition
    assert "github.ref == 'refs/heads/main'" in condition
    assert 'github.actor == github.repository_owner' in condition


def test_the_validation_step_repeats_the_main_only_guard(steps):
    validate = _step(steps, VALIDATE)
    assert validate['env']['RESOLVED_REF'] == '${{ github.ref }}'
    assert '"refs/heads/main"' in validate['run']


def test_the_inputs_are_exactly_the_four_reviewed_inputs(workflow):
    inputs = workflow[ON]['workflow_dispatch']['inputs']
    assert set(inputs) == {'snapshot_id', 'team_id', 'league', 'confirmation'}
    assert inputs['snapshot_id']['required'] is True
    assert inputs['confirmation']['required'] is True
    assert inputs['team_id']['required'] is False
    assert inputs['league']['type'] == 'boolean'
    assert inputs['league']['default'] is False


def test_the_confirmation_phrase_is_exact(steps, workflow):
    assert f'"{CONFIRMATION}"' in _step(steps, VALIDATE)['run']
    assert CONFIRMATION in workflow[ON]['workflow_dispatch']['inputs'][
        'confirmation']['description']


def test_validation_precedes_checkout_and_any_credential(steps):
    validate = _index(steps, VALIDATE)
    assert validate == 0
    for position, step in enumerate(steps):
        env = step.get('env') or {}
        if any('secrets.' in str(value) for value in env.values()):
            assert position > validate


def test_inputs_never_appear_as_expressions_inside_run_scripts(steps):
    for step in steps:
        assert not EXPRESSION.search(step.get('run') or ''), step.get('name')


# ── Validation behaviour, executed ──────────────────────────────────────────

def _validate(**overrides):
    env = {
        'INPUT_SNAPSHOT_ID': '4132',
        'INPUT_TEAM_ID': '',
        'INPUT_LEAGUE': 'false',
        'INPUT_CONFIRMATION': CONFIRMATION,
        'RESOLVED_REF': 'refs/heads/main',
        'PATH': '/usr/bin:/bin',
    }
    env.update(overrides)
    script = _step(
        yaml.safe_load(WORKFLOW_PATH.read_text(encoding='utf-8'))['jobs'][JOB]['steps'],
        VALIDATE,
    )['run']
    return subprocess.run(['bash', '-c', script], env=env, capture_output=True, text=True)


@pytest.mark.parametrize('overrides', [
    {'INPUT_TEAM_ID': '118'},
    {'INPUT_LEAGUE': 'true'},
])
def test_a_valid_team_or_league_invocation_is_accepted(overrides):
    result = _validate(**overrides)
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize('overrides,reason', [
    ({'INPUT_TEAM_ID': '118', 'INPUT_LEAGUE': 'true'}, 'not both'),
    ({}, 'supply team_id, or set league=true'),
    ({'INPUT_TEAM_ID': '0'}, 'team_id must be a positive integer'),
    ({'INPUT_TEAM_ID': '-118'}, 'team_id must be a positive integer'),
    ({'INPUT_TEAM_ID': '118; rm -rf /'}, 'team_id must be a positive integer'),
    ({'INPUT_TEAM_ID': '118', 'INPUT_SNAPSHOT_ID': ''}, 'snapshot_id'),
    ({'INPUT_TEAM_ID': '118', 'INPUT_SNAPSHOT_ID': '0'}, 'snapshot_id'),
    ({'INPUT_TEAM_ID': '118', 'INPUT_SNAPSHOT_ID': '41x'}, 'snapshot_id'),
    ({'INPUT_TEAM_ID': '118', 'INPUT_LEAGUE': 'yes'}, 'league must be explicitly'),
    ({'INPUT_TEAM_ID': '118', 'INPUT_CONFIRMATION': 'run read only'}, 'confirmation'),
    ({'INPUT_TEAM_ID': '118', 'RESOLVED_REF': 'refs/heads/fix/x'}, 'refs/heads/main'),
])
def test_an_invalid_invocation_is_refused_before_database_access(overrides, reason):
    result = _validate(**overrides)
    assert result.returncode == 1
    assert reason in result.stdout


# ── Credentials and read-only operation ─────────────────────────────────────

def test_only_contents_read_is_granted(workflow):
    assert workflow['permissions'] == {'contents': 'read'}


def test_the_existing_production_database_secret_is_the_only_database_credential(
    steps, workflow_text,
):
    run_env = _step(steps, RUN)['env']
    assert run_env['DATABASE_URL'] == '${{ secrets.DATABASE_URL }}'
    secrets = set(re.findall(r'secrets\.([A-Z_]+)', workflow_text))
    assert secrets == {'DATABASE_URL', 'SECRET_KEY', 'BASEBALLOS_ADMIN_API_TOKEN'}
    for step in steps:
        if step.get('name') != RUN:
            env = step.get('env') or {}
            assert not any('secrets.' in str(value) for value in env.values())


def test_every_connection_starts_read_only(steps):
    assert _step(steps, RUN)['env']['PGOPTIONS'] == (
        '-c default_transaction_read_only=on'
    )


def test_the_script_itself_proves_read_only_and_fails_otherwise():
    script = (REPO_ROOT / 'backend/scripts/diagnose_team_state_coverage.py').read_text()
    assert 'default_transaction_read_only=on' in script
    assert 'enforce_read_only(db.session)' in script
    assert 'return EXIT_READ_ONLY_UNPROVEN' in script


def test_no_sync_publication_or_ingestion_environment(steps, workflow_text):
    run_env = _step(steps, RUN)['env']
    assert run_env['AUTO_SYNC'] == 'false'
    for key in run_env:
        upper = key.upper()
        assert not any(word in upper for word in (
            'SYNC_URL', 'PUBLICATION', 'INGESTION_MODE', 'AUTHORITATIVE', 'BACKFILL',
            'MIGRATION',
        )), key
    assert 'DATABASE_MIGRATION_URL' not in workflow_text


def test_the_diagnostic_is_the_only_production_data_command(steps):
    python_commands = []
    for step in steps:
        for line in (step.get('run') or '').splitlines():
            match = re.search(r'python\s+(\S+\.py)', line)
            if match:
                python_commands.append((step['name'], match.group(1)))
    assert python_commands == [
        (RUN, 'scripts/diagnose_team_state_coverage.py'),
        (SCAN, 'backend/scripts/scan_forbidden_artifact_content.py'),
    ]


@pytest.mark.parametrize('forbidden', [
    'flask db upgrade', 'db upgrade', 'alembic', 'run_due_sync', 'run_daily_sync',
    'run_postgame', 'run_intraday_repair', 'recovery_daily', 'recovery_morning',
    'backfill', 'ingest_schedule', 'recalculate', 'publish_dashboard_snapshot',
    'resolve_entity_failures', 'psql', 'INSERT ', 'UPDATE ', 'DELETE ',
    'gh workflow run', 'gh run rerun', '/dispatches', 'curl ',
])
def test_no_write_capable_command_exists(steps, forbidden):
    for step in steps:
        assert forbidden.lower() not in (step.get('run') or '').lower(), (
            step.get('name'), forbidden,
        )


# ── Artifact handling ───────────────────────────────────────────────────────

def test_the_artifact_is_scanned_before_it_is_uploaded(steps):
    scan = _step(steps, SCAN)
    assert '--directory artifacts/team-state-coverage-diagnostic' in scan['run']
    assert _index(steps, RUN) < _index(steps, SCAN) < _index(steps, UPLOAD)
    assert _step(steps, UPLOAD)['if'] == "${{ steps.scan.outcome == 'success' }}"


def test_the_upload_carries_the_diagnostic_directory(steps):
    upload = _step(steps, UPLOAD)
    assert upload['uses'] == 'actions/upload-artifact@v4'
    assert upload['with']['path'] == 'artifacts/team-state-coverage-diagnostic'
    assert upload['with']['if-no-files-found'] == 'error'
    assert upload['with']['name'] == 'team-state-coverage-diagnostic-${{ github.run_id }}'


def test_the_diagnostic_writes_structured_files_not_console_output(steps):
    assert '--output-dir ../artifacts/team-state-coverage-diagnostic' in _step(
        steps, RUN)['run']


def test_the_final_gate_fails_only_for_operational_reasons(steps):
    gate = _step(steps, GATE)
    assert 'continue-on-error' not in gate
    assert gate['run'].lstrip().startswith('set -euo pipefail')
    assert _index(steps, UPLOAD) < _index(steps, GATE)
    for exit_code in ('"2"', '"3"'):
        assert exit_code in gate['run']
    for outcome in ('DIAGNOSTIC_OUTCOME', 'SCAN_OUTCOME', 'UPLOAD_OUTCOME'):
        assert outcome in gate['env']
    # An ineligible team is data: nothing in the gate reads the verdict.
    assert 'eligible' not in gate['run'].lower()


def test_the_shared_sync_lane_is_used_and_never_cancelled(workflow, job):
    assert workflow['concurrency'] == {'group': 'baseballos-sync', 'cancel-in-progress': False}
    assert job['timeout-minutes'] == 20
