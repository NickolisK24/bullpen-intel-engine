"""Manual publication truth certification — workflow contract.

The reviewed workflow source is the authority for how the production
certification can be invoked. These tests hold it to the governed diagnostic
pattern: dispatch-only, main-only, owner-only, typed confirmation, one positive
snapshot id and nothing else, the existing production DATABASE_URL secret and
no other production credential, read-only at the connection and the script,
one production-data command, outputs verified then scanned then uploaded then
retained, and no repair, sync, publication, migration or mutation command
anywhere. A certification FAIL is data; only operational failures fail it.
"""

import re
import subprocess
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / '.github/workflows/manual-publication-truth-certification.yml'
SCRIPT_PATH = REPO_ROOT / 'backend/scripts/certify_publication_truth.py'

JOB = 'publication-truth-certification'
REPOSITORY = 'NickolisK24/bullpen-intel-engine'
CONFIRMATION = 'RUN READ ONLY PUBLICATION TRUTH CERTIFICATION'
VALIDATE = 'Refuse an unauthorized or invalid invocation'
CHECKOUT = 'Check out the reviewed commit'
RUN = 'Run the read-only publication truth certification'
VERIFY = 'Verify the certification output files'
SCAN = 'Scan the certification artifact'
UPLOAD = 'Upload the certification artifact'
RETAINED = 'Confirm the artifact was retained'
SUMMARY = 'Append the certification summary'
GATE = 'Final certification gate'
OUTPUT_DIR = 'artifacts/publication-truth-certification'

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


def _run_step(name, env, cwd):
    script = _step(
        yaml.safe_load(WORKFLOW_PATH.read_text(encoding='utf-8'))['jobs'][JOB]['steps'],
        name,
    )['run']
    return subprocess.run(
        ['bash', '-c', script], env={'PATH': '/usr/bin:/bin', **env},
        cwd=cwd, capture_output=True, text=True,
    )


# ── Trigger surface and governance ──────────────────────────────────────────

def test_workflow_dispatch_is_the_only_trigger(workflow):
    assert set(workflow[ON]) == {'workflow_dispatch'}


def test_the_job_runs_only_from_main_in_this_repository_for_the_owner(job):
    condition = ' '.join(job['if'].split())
    assert "github.event_name == 'workflow_dispatch'" in condition
    assert f"github.repository == '{REPOSITORY}'" in condition
    assert "github.ref == 'refs/heads/main'" in condition
    assert 'github.actor == github.repository_owner' in condition


def test_the_inputs_are_exactly_a_snapshot_id_and_the_confirmation(workflow):
    inputs = workflow[ON]['workflow_dispatch']['inputs']
    assert set(inputs) == {'snapshot_id', 'confirmation'}
    assert inputs['snapshot_id']['required'] is True
    assert inputs['snapshot_id']['type'] == 'string'
    assert inputs['confirmation']['required'] is True
    assert CONFIRMATION in inputs['confirmation']['description']


def test_the_confirmation_phrase_is_exact(steps):
    assert f'"{CONFIRMATION}"' in _step(steps, VALIDATE)['run']


def test_validation_precedes_checkout_and_any_credential(steps):
    validate = _index(steps, VALIDATE)
    assert validate == 0
    assert _index(steps, CHECKOUT) > validate
    for position, step in enumerate(steps):
        env = step.get('env') or {}
        if any('secrets.' in str(value) for value in env.values()):
            assert position > validate


def test_inputs_never_appear_as_expressions_inside_run_scripts(steps):
    for step in steps:
        assert not EXPRESSION.search(step.get('run') or ''), step.get('name')


def test_the_reviewed_commit_is_checked_out(steps):
    assert _step(steps, CHECKOUT)['with'] == {'ref': '${{ github.sha }}'}


# ── Validation behaviour, executed ──────────────────────────────────────────

def _validate(tmp_path, **overrides):
    env = {
        'INPUT_SNAPSHOT_ID': '4496',
        'INPUT_CONFIRMATION': CONFIRMATION,
        'RESOLVED_REF': 'refs/heads/main',
    }
    env.update(overrides)
    return _run_step(VALIDATE, env, tmp_path)


def test_a_valid_snapshot_and_exact_confirmation_are_accepted(tmp_path):
    result = _validate(tmp_path)
    assert result.returncode == 0, result.stdout
    assert 'preconditions satisfied' in result.stdout


@pytest.mark.parametrize('overrides,reason', [
    ({'INPUT_CONFIRMATION': 'run read only publication truth certification'},
     'confirmation must be exactly'),
    ({'INPUT_CONFIRMATION': f'{CONFIRMATION} '}, 'confirmation must be exactly'),
    ({'INPUT_CONFIRMATION': ''}, 'confirmation must be exactly'),
    ({'INPUT_SNAPSHOT_ID': ''}, 'snapshot_id must be a positive integer'),
    ({'INPUT_SNAPSHOT_ID': '0'}, 'snapshot_id must be a positive integer'),
    ({'INPUT_SNAPSHOT_ID': '-4496'}, 'snapshot_id must be a positive integer'),
    ({'INPUT_SNAPSHOT_ID': '0496'}, 'snapshot_id must be a positive integer'),
    ({'INPUT_SNAPSHOT_ID': '44.96'}, 'snapshot_id must be a positive integer'),
    ({'INPUT_SNAPSHOT_ID': 'abc'}, 'snapshot_id must be a positive integer'),
    ({'INPUT_SNAPSHOT_ID': '4496; rm -rf /'}, 'snapshot_id must be a positive integer'),
    ({'INPUT_SNAPSHOT_ID': '$(id)'}, 'snapshot_id must be a positive integer'),
    ({'INPUT_SNAPSHOT_ID': '`id`'}, 'snapshot_id must be a positive integer'),
    ({'INPUT_SNAPSHOT_ID': '4496\n--allow-non-postgres'},
     'snapshot_id must be a positive integer'),
    ({'INPUT_SNAPSHOT_ID': '4496 --allow-non-postgres'},
     'snapshot_id must be a positive integer'),
    ({'INPUT_SNAPSHOT_ID': '12345678901'}, 'snapshot_id must be a positive integer'),
    ({'RESOLVED_REF': 'refs/heads/audit/post-stabilization-truth-certification'},
     'refs/heads/main'),
    ({'RESOLVED_REF': 'refs/tags/v1'}, 'refs/heads/main'),
])
def test_an_invalid_invocation_is_refused_before_credentials(tmp_path, overrides, reason):
    result = _validate(tmp_path, **overrides)
    assert result.returncode == 1
    assert reason in result.stdout


def test_a_wrong_confirmation_is_refused_before_any_credential_or_checkout(steps, tmp_path):
    """The refusing step is the first step and carries no secret."""
    validate = _step(steps, VALIDATE)
    assert not any('secrets.' in str(v) for v in (validate.get('env') or {}).values())
    result = _validate(tmp_path, INPUT_CONFIRMATION='yes')
    assert result.returncode == 1


# ── Credentials and read-only operation ─────────────────────────────────────

def test_only_contents_read_is_granted(workflow):
    assert workflow['permissions'] == {'contents': 'read'}


def test_the_existing_production_database_secret_is_scoped_to_the_run_step(
    steps, workflow_text,
):
    run_env = _step(steps, RUN)['env']
    assert run_env['DATABASE_URL'] == '${{ secrets.DATABASE_URL }}'
    secrets = set(re.findall(r'secrets\.([A-Z_]+)', workflow_text))
    assert secrets == {'DATABASE_URL', 'SECRET_KEY', 'BASEBALLOS_ADMIN_API_TOKEN'}
    for step in steps:
        if step.get('name') != RUN:
            env = step.get('env') or {}
            assert not any('secrets.' in str(value) for value in env.values()), step['name']


def test_every_connection_starts_read_only(steps):
    assert _step(steps, RUN)['env']['PGOPTIONS'] == '-c default_transaction_read_only=on'


def test_the_script_itself_proves_read_only_and_refuses_otherwise():
    script = SCRIPT_PATH.read_text(encoding='utf-8')
    assert 'default_transaction_read_only=on' in script
    assert 'enforce_read_only(db.session)' in script
    assert 'except ReadOnlyProbeViolation' in script
    assert 'exit_code=EXIT_READ_ONLY_UNPROVEN' in script
    # The probe runs before the snapshot is read or certified.
    assert script.index('enforce_read_only(db.session)') < script.index(
        'db.session.get(DashboardSnapshot')
    assert script.index('enforce_read_only(db.session)') < script.index(
        'certification.certify_snapshot(snapshot)')


def test_no_sync_publication_or_ingestion_environment(steps, workflow_text):
    run_env = _step(steps, RUN)['env']
    assert run_env['AUTO_SYNC'] == 'false'
    assert run_env['APP_ENV'] == 'production'
    for key in run_env:
        upper = key.upper()
        assert not any(word in upper for word in (
            'SYNC_URL', 'PUBLICATION', 'INGESTION_MODE', 'AUTHORITATIVE', 'BACKFILL',
            'MIGRATION',
        )), key
    assert 'DATABASE_MIGRATION_URL' not in workflow_text


def test_the_certification_is_the_only_production_data_command(steps):
    python_commands = []
    for step in steps:
        for line in (step.get('run') or '').splitlines():
            match = re.search(r'python\s+(\S+\.py)', line)
            if match:
                python_commands.append((step['name'], match.group(1)))
    assert python_commands == [
        (RUN, 'scripts/certify_publication_truth.py'),
        (SCAN, 'backend/scripts/scan_forbidden_artifact_content.py'),
    ]


def test_the_run_passes_only_the_validated_snapshot_and_a_fixed_output_path(steps):
    run = _step(steps, RUN)['run']
    assert '--snapshot-id "$INPUT_SNAPSHOT_ID"' in run
    assert f'--output-dir ../{OUTPUT_DIR}' in run
    assert '--allow-non-postgres' not in run
    assert set(re.findall(r'--[a-z-]+', run)) == {'--snapshot-id', '--output-dir'}


@pytest.mark.parametrize('forbidden', [
    'flask db upgrade', 'db upgrade', 'alembic', 'run_due_sync', 'run_daily_sync',
    'run_postgame', 'run_intraday_repair', 'recovery_daily', 'recovery_morning',
    'backfill', 'ingest_schedule', 'recalculate', 'publish_dashboard_snapshot',
    'resolve_entity_failures', 'psql', 'INSERT ', 'UPDATE ', 'DELETE ',
    'gh workflow run', 'gh run rerun', '/dispatches', 'curl ', 'git push',
])
def test_no_write_capable_command_exists(steps, forbidden):
    for step in steps:
        assert forbidden.lower() not in (step.get('run') or '').lower(), (
            step.get('name'), forbidden,
        )


def test_the_shared_sync_lane_is_used_and_never_cancelled(workflow, job):
    assert workflow['concurrency'] == {'group': 'baseballos-sync', 'cancel-in-progress': False}
    assert job['timeout-minutes'] == 30


# ── Failure visibility and artifact retention ────────────────────────────────

def test_no_step_hides_its_failure(workflow_text, steps):
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
        'name': 'publication-truth-certification-${{ github.run_id }}',
        'path': OUTPUT_DIR,
        'retention-days': 30,
        'if-no-files-found': 'error',
    }


def test_retention_is_proven_by_the_returned_artifact_id(steps):
    assert _step(steps, RETAINED)['env']['ARTIFACT_ID'] == (
        '${{ steps.upload.outputs.artifact-id }}')
    assert _step(steps, GATE)['env']['ARTIFACT_ID'] == (
        '${{ steps.upload.outputs.artifact-id }}')


# ── Executed control flow ────────────────────────────────────────────────────

def _write(directory, name, text='{"mode": "certified"}\n'):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(text, encoding='utf-8')


RESULT = 'certification-4496'
REFUSAL = 'certification-refused'


def _verify(tmp_path, exit_code='0', snapshot_id='4496'):
    return _run_step(VERIFY, {
        'OUTPUT_DIR': OUTPUT_DIR, 'CERTIFICATION_EXIT_CODE': exit_code,
        'INPUT_SNAPSHOT_ID': snapshot_id,
    }, tmp_path)


def test_verify_accepts_the_certification_pair(tmp_path):
    _write(tmp_path / OUTPUT_DIR, f'{RESULT}.json')
    _write(tmp_path / OUTPUT_DIR, f'{RESULT}.md', '# summary\n')
    result = _verify(tmp_path)
    assert result.returncode == 0, result.stdout
    assert f'{RESULT}.json' in result.stdout and f'{RESULT}.md' in result.stdout


@pytest.mark.parametrize('files,exit_code,reason', [
    ((), '0', 'MISSING'),                                    # directory never created
    ((f'{RESULT}.json',), '0', 'MISSING'),                   # no Markdown
    ((f'{RESULT}.md',), '0', 'MISSING'),                     # no JSON
    ((f'{REFUSAL}.json', f'{REFUSAL}.md'), '0', 'exactly'),  # refusal, yet exit 0
    (('certification-4495.json', 'certification-4495.md'), '0', 'exactly'),
    ((f'{RESULT}.json', f'{RESULT}.md', 'extra.json'), '0', 'exactly'),
])
def test_verify_refuses_missing_or_wrong_evidence(tmp_path, files, exit_code, reason):
    for name in files:
        _write(tmp_path / OUTPUT_DIR, name)
    result = _verify(tmp_path, exit_code)
    assert result.returncode == 1
    assert reason in result.stdout


@pytest.mark.parametrize('empty', [f'{RESULT}.json', f'{RESULT}.md'])
def test_verify_refuses_an_empty_evidence_file(tmp_path, empty):
    _write(tmp_path / OUTPUT_DIR, f'{RESULT}.json')
    _write(tmp_path / OUTPUT_DIR, f'{RESULT}.md', '# summary\n')
    (tmp_path / OUTPUT_DIR / empty).write_text('', encoding='utf-8')
    result = _verify(tmp_path)
    assert result.returncode == 1
    assert 'EMPTY' in result.stdout


@pytest.mark.parametrize('exit_code', ['2', '3'])
def test_a_refusal_document_is_verified_so_the_refusal_is_uploaded(tmp_path, exit_code):
    _write(tmp_path / OUTPUT_DIR, f'{REFUSAL}.json')
    _write(tmp_path / OUTPUT_DIR, f'{REFUSAL}.md', '# refused\n')
    assert _verify(tmp_path, exit_code=exit_code).returncode == 0


SUCCESS = {
    'CERTIFICATION_OUTCOME': 'success',
    'CERTIFICATION_EXIT_CODE': '0',
    'VERIFY_OUTCOME': 'success',
    'SCAN_OUTCOME': 'success',
    'UPLOAD_OUTCOME': 'success',
    'RETAINED_OUTCOME': 'success',
    'ARTIFACT_ID': '4412057731',
}


def _gate(tmp_path, **overrides):
    return _run_step(GATE, {**SUCCESS, **overrides}, tmp_path)


@pytest.mark.parametrize('verdict', ['FAIL', 'CONDITIONAL', 'PASS'])
def test_a_completed_certification_succeeds_whatever_the_verdict(tmp_path, verdict):
    """The verdict lives in the artifact; the gate sees only operational outcomes."""
    _write(tmp_path / OUTPUT_DIR, f'{RESULT}.json',
           f'{{"certification": {{"league_verdict": "{verdict}"}}}}\n')
    result = _gate(tmp_path)
    assert result.returncode == 0, result.stdout
    assert 'Retained artifact id: 4412057731' in result.stdout


@pytest.mark.parametrize('overrides,reason', [
    ({'CERTIFICATION_OUTCOME': 'failure', 'CERTIFICATION_EXIT_CODE': '2'}, 'REFUSED'),
    ({'CERTIFICATION_OUTCOME': 'failure', 'CERTIFICATION_EXIT_CODE': '3'},
     'READ_ONLY_UNPROVEN'),
    ({'CERTIFICATION_OUTCOME': 'failure', 'CERTIFICATION_EXIT_CODE': '1'}, 'FAILED'),
    ({'CERTIFICATION_OUTCOME': 'failure', 'CERTIFICATION_EXIT_CODE': ''}, 'FAILED'),
    ({'CERTIFICATION_OUTCOME': 'success', 'CERTIFICATION_EXIT_CODE': ''}, 'FAILED'),
    ({'CERTIFICATION_OUTCOME': 'skipped', 'CERTIFICATION_EXIT_CODE': ''}, 'FAILED'),
    ({'VERIFY_OUTCOME': 'failure'}, 'MISSING'),
    ({'SCAN_OUTCOME': 'failure'}, 'UNSAFE'),
    ({'SCAN_OUTCOME': 'skipped'}, 'UNSAFE'),
    ({'UPLOAD_OUTCOME': 'failure'}, 'did not upload'),
    ({'UPLOAD_OUTCOME': 'skipped'}, 'did not upload'),
    ({'RETAINED_OUTCOME': 'failure'}, 'UNRETAINED'),
    ({'RETAINED_OUTCOME': 'skipped'}, 'UNRETAINED'),
    ({'ARTIFACT_ID': ''}, 'UNRETAINED'),
])
def test_every_operational_failure_fails_the_gate(tmp_path, overrides, reason):
    result = _gate(tmp_path, **overrides)
    assert result.returncode == 1
    assert reason in result.stdout


@pytest.mark.parametrize('artifact_id,ok', [
    ('4412057731', True), ('', False), ('0', False), ('abc', False), ('12a', False),
])
def test_retention_requires_a_real_artifact_id(tmp_path, artifact_id, ok):
    result = _run_step(RETAINED, {'ARTIFACT_ID': artifact_id}, tmp_path)
    assert (result.returncode == 0) is ok


def test_the_final_gate_does_not_read_the_certification_verdict(steps):
    gate = _step(steps, GATE)
    assert gate['run'].lstrip().startswith('set -euo pipefail')
    assert set(gate['env']) == {
        'CERTIFICATION_OUTCOME', 'CERTIFICATION_EXIT_CODE', 'VERIFY_OUTCOME',
        'SCAN_OUTCOME', 'UPLOAD_OUTCOME', 'RETAINED_OUTCOME', 'ARTIFACT_ID',
    }
    for word in ('league_verdict', 'verdict', 'artifacts/', '.json', 'jq '):
        assert word not in gate['run'].lower()


def test_the_scanner_rejects_a_leaked_credential_in_the_artifact(tmp_path):
    directory = tmp_path / OUTPUT_DIR
    _write(directory, f'{RESULT}.json', '{"note": "postgresql://user:pw@host/db"}\n')
    _write(directory, f'{RESULT}.md', '# summary\n')
    result = subprocess.run(
        ['python3', str(REPO_ROOT / 'backend/scripts/scan_forbidden_artifact_content.py'),
         '--directory', str(directory)],
        capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert 'user:pw' not in result.stdout + result.stderr
