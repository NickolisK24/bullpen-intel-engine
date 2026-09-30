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


def test_the_inputs_are_exactly_the_reviewed_inputs(workflow):
    inputs = workflow[ON]['workflow_dispatch']['inputs']
    assert set(inputs) == {
        'snapshot_id', 'membership_date', 'availability_date', 'team_id', 'league',
        'confirmation',
    }
    # The anchor is snapshot_id OR both dates; the validation step enforces one.
    for name in ('snapshot_id', 'membership_date', 'availability_date', 'team_id'):
        assert inputs[name]['required'] is False
        assert inputs[name]['default'] == ''
    assert inputs['confirmation']['required'] is True
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
        'INPUT_MEMBERSHIP_DATE': '',
        'INPUT_AVAILABILITY_DATE': '',
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
    {'INPUT_TEAM_ID': '118', 'INPUT_SNAPSHOT_ID': '',
     'INPUT_MEMBERSHIP_DATE': '2026-09-29', 'INPUT_AVAILABILITY_DATE': '2026-09-30'},
    {'INPUT_LEAGUE': 'true', 'INPUT_SNAPSHOT_ID': '',
     'INPUT_MEMBERSHIP_DATE': '2026-09-29', 'INPUT_AVAILABILITY_DATE': '2026-09-30'},
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
    ({'INPUT_TEAM_ID': '118', 'INPUT_SNAPSHOT_ID': ''}, 'supply snapshot_id, or both'),
    ({'INPUT_TEAM_ID': '118', 'INPUT_SNAPSHOT_ID': '',
      'INPUT_MEMBERSHIP_DATE': '2026-09-29'}, 'supply snapshot_id, or both'),
    ({'INPUT_TEAM_ID': '118', 'INPUT_MEMBERSHIP_DATE': '2026-09-29',
      'INPUT_AVAILABILITY_DATE': '2026-09-30'}, 'not both'),
    ({'INPUT_TEAM_ID': '118', 'INPUT_SNAPSHOT_ID': '',
      'INPUT_MEMBERSHIP_DATE': '09/29/2026', 'INPUT_AVAILABILITY_DATE': '2026-09-30'},
     'YYYY-MM-DD'),
    ({'INPUT_TEAM_ID': '118', 'INPUT_SNAPSHOT_ID': '',
      'INPUT_MEMBERSHIP_DATE': '2026-09-29', 'INPUT_AVAILABILITY_DATE': '$(id)'},
     'YYYY-MM-DD'),
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
    assert 'exit_code=EXIT_READ_ONLY_UNPROVEN' in script


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


# ── Failure visibility and artifact retention ────────────────────────────────

VERIFY = 'Verify the diagnostic output files'
RETAINED = 'Confirm the artifact was retained'
OUTPUT_DIR = 'artifacts/team-state-coverage-diagnostic'


def test_no_step_hides_its_failure(workflow_text, steps):
    """continue-on-error painted failed steps green in runs 36738310262 and
    36738442939; a failed step must be shown as failed."""
    assert not re.search(r'^\s*continue-on-error\s*:', workflow_text, re.MULTILINE)
    for step in steps:
        assert 'continue-on-error' not in step


def test_evidence_steps_run_after_a_failure_but_not_after_cancellation(steps):
    assert _step(steps, VERIFY)['if'] == '${{ !cancelled() }}'
    assert _step(steps, GATE)['if'] == '${{ !cancelled() }}'
    assert 'always()' not in str([step.get('if') for step in steps])


def test_outputs_are_verified_then_scanned_then_uploaded_then_confirmed(steps):
    order = [_index(steps, name) for name in (RUN, VERIFY, SCAN, UPLOAD, RETAINED, GATE)]
    assert order == sorted(order)
    assert _step(steps, SCAN)['if'] == (
        "${{ !cancelled() && steps.verify.outcome == 'success' }}"
    )
    assert _step(steps, UPLOAD)['if'] == (
        "${{ !cancelled() && steps.verify.outcome == 'success' "
        "&& steps.scan.outcome == 'success' }}"
    )
    assert _step(steps, RETAINED)['if'] == (
        "${{ !cancelled() && steps.upload.outcome == 'success' }}"
    )


def test_the_scan_step_fails_on_an_unsafe_artifact(steps):
    scan = _step(steps, SCAN)
    assert scan['run'].lstrip().startswith('set -euo pipefail')
    assert f'--directory {OUTPUT_DIR}' in scan['run']
    assert '|| ' not in scan['run']


def test_the_upload_requires_files_and_carries_the_whole_directory(steps):
    upload = _step(steps, UPLOAD)
    assert upload['uses'] == 'actions/upload-artifact@v4'
    assert upload['with'] == {
        'name': 'team-state-coverage-diagnostic-${{ github.run_id }}',
        'path': OUTPUT_DIR,
        'retention-days': 30,
        'if-no-files-found': 'error',
    }


def test_retention_is_proven_by_the_returned_artifact_id(steps):
    retained = _step(steps, RETAINED)
    assert retained['env']['ARTIFACT_ID'] == '${{ steps.upload.outputs.artifact-id }}'
    assert _step(steps, GATE)['env']['ARTIFACT_ID'] == (
        '${{ steps.upload.outputs.artifact-id }}'
    )


def test_the_diagnostic_writes_structured_files_not_console_output(steps):
    assert f'--output-dir ../{OUTPUT_DIR}' in _step(steps, RUN)['run']


def test_the_shared_sync_lane_is_used_and_never_cancelled(workflow, job):
    assert workflow['concurrency'] == {'group': 'baseballos-sync', 'cancel-in-progress': False}
    assert job['timeout-minutes'] == 20


# ── Executed control flow ────────────────────────────────────────────────────

def _run_step(name, env, cwd):
    script = _step(
        yaml.safe_load(WORKFLOW_PATH.read_text(encoding='utf-8'))['jobs'][JOB]['steps'],
        name,
    )['run']
    return subprocess.run(
        ['bash', '-c', script], env={'PATH': '/usr/bin:/bin', **env},
        cwd=cwd, capture_output=True, text=True,
    )


def _write(directory, name, text='{"mode": "team"}\n'):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(text, encoding='utf-8')


RESULT = 'team-state-coverage-team-118-dates-2026-09-29-2026-09-30'
REFUSAL = 'team-state-coverage-refused'


def _verify(tmp_path, exit_code='0'):
    return _run_step(VERIFY, {
        'OUTPUT_DIR': OUTPUT_DIR, 'DIAGNOSTIC_EXIT_CODE': exit_code,
    }, tmp_path)


def test_verify_accepts_one_result_document_pair(tmp_path):
    _write(tmp_path / OUTPUT_DIR, f'{RESULT}.json')
    _write(tmp_path / OUTPUT_DIR, f'{RESULT}.md', '# summary\n')
    result = _verify(tmp_path)
    assert result.returncode == 0, result.stdout
    assert f'{RESULT}.json' in result.stdout and f'{RESULT}.md' in result.stdout


@pytest.mark.parametrize('files,exit_code,reason', [
    ((), '0', 'MISSING'),                                    # directory never created
    ((f'{RESULT}.json',), '0', 'MISSING'),                   # no Markdown
    ((f'{RESULT}.md',), '0', 'MISSING'),                     # no JSON
    ((f'{REFUSAL}.json', f'{REFUSAL}.md'), '0', 'exactly one result'),
    ((f'{RESULT}.json', f'{RESULT}.md', 'extra.json'), '0', 'exactly one result'),
])
def test_verify_refuses_missing_or_wrong_evidence(tmp_path, files, exit_code, reason):
    for name in files:
        _write(tmp_path / OUTPUT_DIR, name)
    result = _verify(tmp_path, exit_code)
    assert result.returncode == 1
    assert reason in result.stdout


def test_verify_refuses_an_empty_evidence_file(tmp_path):
    _write(tmp_path / OUTPUT_DIR, f'{RESULT}.json')
    _write(tmp_path / OUTPUT_DIR, f'{RESULT}.md', '')
    result = _verify(tmp_path)
    assert result.returncode == 1
    assert 'EMPTY' in result.stdout


def test_a_refusal_document_is_verified_so_the_refusal_is_uploaded(tmp_path):
    _write(tmp_path / OUTPUT_DIR, f'{REFUSAL}.json')
    _write(tmp_path / OUTPUT_DIR, f'{REFUSAL}.md', '# refused\n')
    assert _verify(tmp_path, exit_code='2').returncode == 0


SUCCESS = {
    'DIAGNOSTIC_OUTCOME': 'success',
    'DIAGNOSTIC_EXIT_CODE': '0',
    'VERIFY_OUTCOME': 'success',
    'SCAN_OUTCOME': 'success',
    'UPLOAD_OUTCOME': 'success',
    'RETAINED_OUTCOME': 'success',
    'ARTIFACT_ID': '4412057731',
}


def _gate(tmp_path, **overrides):
    return _run_step(GATE, {**SUCCESS, **overrides}, tmp_path)


@pytest.mark.parametrize('verdict', ['ineligible', 'eligible'])
def test_a_completed_diagnostic_succeeds_whatever_the_team_verdict(tmp_path, verdict):
    """The verdict lives in the artifact; the gate sees only operational outcomes."""
    _write(tmp_path / OUTPUT_DIR, f'{RESULT}.json',
           f'{{"report": {{"eligible_coverage": {str(verdict == "eligible").lower()}}}}}\n')
    result = _gate(tmp_path)
    assert result.returncode == 0, result.stdout
    assert 'Retained artifact id: 4412057731' in result.stdout


@pytest.mark.parametrize('overrides,reason', [
    ({'DIAGNOSTIC_OUTCOME': 'failure', 'DIAGNOSTIC_EXIT_CODE': '2'}, 'REFUSED'),
    ({'DIAGNOSTIC_OUTCOME': 'failure', 'DIAGNOSTIC_EXIT_CODE': '3'}, 'UNPROVEN: read-only'),
    ({'DIAGNOSTIC_OUTCOME': 'failure', 'DIAGNOSTIC_EXIT_CODE': '1'}, 'FAILED'),
    ({'DIAGNOSTIC_OUTCOME': 'failure', 'DIAGNOSTIC_EXIT_CODE': ''}, 'FAILED'),
    ({'DIAGNOSTIC_OUTCOME': 'success', 'DIAGNOSTIC_EXIT_CODE': ''}, 'FAILED'),
    ({'VERIFY_OUTCOME': 'failure'}, 'MISSING'),
    ({'SCAN_OUTCOME': 'failure'}, 'UNSAFE'),
    ({'SCAN_OUTCOME': 'skipped'}, 'UNSAFE'),
    ({'UPLOAD_OUTCOME': 'failure'}, 'did not upload'),
    ({'UPLOAD_OUTCOME': 'skipped'}, 'did not upload'),
    ({'RETAINED_OUTCOME': 'failure'}, 'UNRETAINED'),
    ({'ARTIFACT_ID': ''}, 'UNRETAINED'),
])
def test_every_operational_failure_fails_the_gate(tmp_path, overrides, reason):
    result = _gate(tmp_path, **overrides)
    assert result.returncode == 1
    assert reason in result.stdout


def test_production_runs_36738310262_and_36738442939_fail_as_refusals(tmp_path):
    """The recorded outcomes of both production runs: the diagnostic refused
    (snapshot 4132 not found), nothing was written, the upload found no files."""
    result = _gate(
        tmp_path,
        DIAGNOSTIC_OUTCOME='failure', DIAGNOSTIC_EXIT_CODE='2',
        VERIFY_OUTCOME='', SCAN_OUTCOME='success', UPLOAD_OUTCOME='failure',
        RETAINED_OUTCOME='', ARTIFACT_ID='',
    )
    assert result.returncode == 1
    assert 'REFUSED' in result.stdout


@pytest.mark.parametrize('artifact_id,ok', [
    ('4412057731', True), ('', False), ('0', False), ('abc', False),
])
def test_retention_requires_a_real_artifact_id(tmp_path, artifact_id, ok):
    result = _run_step(RETAINED, {'ARTIFACT_ID': artifact_id}, tmp_path)
    assert (result.returncode == 0) is ok


def test_the_final_gate_does_not_read_baseball_eligibility(steps):
    gate = _step(steps, GATE)
    assert gate['run'].lstrip().startswith('set -euo pipefail')
    assert set(gate['env']) == {
        'DIAGNOSTIC_OUTCOME', 'DIAGNOSTIC_EXIT_CODE', 'VERIFY_OUTCOME', 'SCAN_OUTCOME',
        'UPLOAD_OUTCOME', 'RETAINED_OUTCOME', 'ARTIFACT_ID',
    }
    for word in ('eligible', 'confidence', 'data_state', 'artifacts/', '.json', 'jq '):
        assert word not in gate['run'].lower()
