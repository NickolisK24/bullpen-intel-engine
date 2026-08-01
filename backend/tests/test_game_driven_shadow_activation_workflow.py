"""Structure of the automated game-driven shadow activation.

The reviewed workflow source is the activation authority for this phase: there
is no input, no repository variable, and no other lever that can move the lane
to a writing mode without a code review. These tests own that property, and the
property that the established production path was not disturbed to get it.
"""

import re
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / '.github/workflows/baseballos-sync.yml'
MODE_ENV = 'GAME_DRIVEN_INGESTION_MODE'

DAILY_CRON = '0 10 * * *'
MORNING_CRON = '0 14 * * *'
POSTGAME_CRON = '0 2,4,6 * * *'


@pytest.fixture(scope='module')
def workflow_text():
    return WORKFLOW_PATH.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def workflow(workflow_text):
    return yaml.safe_load(workflow_text)


@pytest.fixture(scope='module')
def public_sync(workflow):
    return workflow['jobs']['public-sync']


def _steps(job):
    return job.get('steps') or []


def _step(job, name_fragment):
    for step in _steps(job):
        if name_fragment.lower() in str(step.get('name') or '').lower():
            return step
    raise AssertionError(f'no step matching {name_fragment!r}')


def _mode(step):
    return (step.get('env') or {}).get(MODE_ENV)


def _step_index(job, name_fragment):
    for index, step in enumerate(_steps(job)):
        if name_fragment.lower() in str(step.get('name') or '').lower():
            return index
    raise AssertionError(f'no step matching {name_fragment!r}')


# ── The established production path is untouched ────────────────────────────


def test_the_existing_cron_expressions_are_unchanged(workflow):
    crons = [entry['cron'] for entry in workflow[True]['schedule']]
    assert crons == [DAILY_CRON, MORNING_CRON, POSTGAME_CRON]


def test_no_cron_was_added(workflow):
    assert len(workflow[True]['schedule']) == 3


def test_the_existing_manual_modes_are_unchanged(workflow):
    options = workflow[True]['workflow_dispatch']['inputs']['mode']['options']
    assert options == ['daily', 'postgame', 'backfill', 'intraday']


def test_the_manual_inputs_are_unchanged(workflow):
    inputs = workflow[True]['workflow_dispatch']['inputs']
    assert sorted(inputs) == ['backfill_date', 'mode']


def test_permissions_are_not_broadened(workflow):
    assert workflow['permissions'] == {'contents': 'write'}


def test_concurrency_is_unchanged(workflow):
    assert workflow['concurrency'] == {
        'group': 'baseballos-sync', 'cancel-in-progress': False,
    }


def test_the_daily_command_timeout_is_unchanged(public_sync):
    step = _step(public_sync, 'Run direct daily sync')
    assert step['env']['DAILY_SYNC_COMMAND_TIMEOUT'] == '20m'


def test_the_postgame_command_timeout_is_unchanged(public_sync):
    step = _step(public_sync, 'Run direct postgame refresh')
    assert step['env']['POSTGAME_REFRESH_COMMAND_TIMEOUT'] == '20m'


def test_the_job_timeout_is_unchanged(public_sync):
    assert public_sync['timeout-minutes'] == 40


@pytest.mark.parametrize('name', [
    'Appearance ledger audit',
    'Verify dashboard snapshot cache',
    'Refresh schedule and warm Tonight',
    'Run morning slate schedule refresh',
    'Run explicit backfill',
])
def test_an_existing_production_step_is_retained(public_sync, name):
    assert _step(public_sync, name) is not None


def test_the_daily_runner_command_is_unchanged_apart_from_output(public_sync):
    run = _step(public_sync, 'Run direct daily sync')['run']
    assert 'run_daily_sync.py --days-back 7 --source github_actions --public-only' in run


def test_the_postgame_runner_command_is_unchanged_apart_from_output(public_sync):
    run = _step(public_sync, 'Run direct postgame refresh')['run']
    assert 'run_postgame_refresh.py --source github_actions --public-only' in run


# ── Shadow is on exactly the two eligible steps ─────────────────────────────


def test_the_daily_step_runs_in_shadow(public_sync):
    assert _mode(_step(public_sync, 'Run direct daily sync')) == 'shadow'


def test_the_postgame_step_runs_in_shadow(public_sync):
    """Reactivated on exact-cycle scope.

    It was off after the first cycle planned the rolling correction horizon
    instead of this cycle's own games. It is on again because the lane now
    receives only the games this refresh cycle governs and the writer
    finished.
    """
    assert _mode(_step(public_sync, 'Run direct postgame refresh')) == 'shadow'


def test_manual_daily_uses_the_same_shadow_enabled_step(public_sync):
    condition = _step(public_sync, 'Run direct daily sync')['if']
    assert "inputs.mode == 'daily'" in condition
    assert f"github.event.schedule == '{DAILY_CRON}'" in condition


def test_manual_postgame_uses_the_same_step(public_sync):
    condition = _step(public_sync, 'Run direct postgame refresh')['if']
    assert "inputs.mode == 'postgame'" in condition
    assert f"github.event.schedule == '{POSTGAME_CRON}'" in condition


def test_backfill_is_explicitly_off(public_sync):
    """Backfill runs the same postgame runner, so it must say off out loud."""
    assert _mode(_step(public_sync, 'Run explicit backfill')) == 'off'


def test_exactly_three_steps_configure_the_mode(public_sync):
    configured = {
        step['name']: _mode(step) for step in _steps(public_sync) if _mode(step)
    }
    assert configured == {
        'Run direct daily sync': 'shadow',
        'Run direct postgame refresh': 'shadow',
        'Run explicit backfill': 'off',
    }


def test_exactly_two_shadow_literals_and_one_off_literal(public_sync):
    modes = [_mode(step) for step in _steps(public_sync) if _mode(step)]
    assert modes.count('shadow') == 2
    assert modes.count('off') == 1


def test_daily_shadow_was_not_disturbed_by_the_reactivation(public_sync):
    """Reactivation is postgame-only. Touching daily would be a regression
    smuggled in beside a fix."""
    assert _mode(_step(public_sync, 'Run direct daily sync')) == 'shadow'


def test_the_mode_is_never_set_at_job_scope(workflow):
    for name, job in workflow['jobs'].items():
        assert MODE_ENV not in (job.get('env') or {}), (
            f'{name} sets the mode for every step in the job'
        )


@pytest.mark.parametrize('name', [
    'Run morning slate schedule refresh',
    'Refresh schedule and warm Tonight',
    'Refresh schedule and warm Tonight after postgame',
    'Appearance ledger audit',
    'Verify dashboard snapshot cache',
])
def test_an_excluded_step_does_not_inherit_shadow(public_sync, name):
    assert _mode(_step(public_sync, name)) is None


def test_the_intraday_job_never_reaches_the_lane(workflow):
    for step in _steps(workflow['jobs']['intraday-audit']):
        assert _mode(step) is None


@pytest.mark.parametrize('job_name', [
    'internal-enrichment', 'static-team-story-preview', 'intraday-audit',
])
def test_an_unrelated_job_configures_no_mode(workflow, job_name):
    for step in _steps(workflow['jobs'][job_name]):
        assert _mode(step) is None


# ── No promotion path that skips review ─────────────────────────────────────


def test_no_workflow_input_can_select_the_game_driven_mode(workflow_text, workflow):
    inputs = workflow[True]['workflow_dispatch']['inputs']
    for name, spec in inputs.items():
        assert 'game_driven' not in name.lower()
        assert MODE_ENV not in str(spec)
    assert f'inputs.{MODE_ENV}' not in workflow_text


def test_no_repository_variable_can_promote_the_mode(workflow_text):
    """A vars.* or secrets.* mode would move production without a review."""
    for match in re.finditer(
        rf'{MODE_ENV}:\s*(.+)', workflow_text,
    ):
        value = match.group(1).strip()
        assert value in ("'shadow'", "'off'"), (
            f'the mode must be a reviewed literal, got {value!r}'
        )


def test_the_workflow_never_names_a_writing_mode(workflow_text):
    for step_mode in re.findall(rf'{MODE_ENV}:\s*(.+)', workflow_text):
        assert 'write' not in step_mode
        assert 'authoritative' not in step_mode


def test_the_workflow_supplies_no_expected_plan_fingerprint(workflow_text):
    assert 'expected-plan-fingerprint' not in workflow_text
    assert 'expected_plan_fingerprint' not in workflow_text


def test_no_historical_foundation_fingerprint_appears_in_a_command(workflow_text):
    for fingerprint in (
        '40659a4051226df40ef7cedbca7a6bc2689d5c2bfbdd4ccdb717fc6fc0c79343',
        '9f0fe9839e5aef4149dd6f2761d038e600ca1ea9562830832f5f952324d3e2c6',
        'e8cde57b9fe1033077533f7bee0cc64fc5969aa7fa3fc64efdc672c26d08a804',
        '43b9333ad228c60846f1cd24ae8518273dc1017aefc98e7b7930974c40bdfd22',
    ):
        assert fingerprint not in workflow_text


# ── One invocation, through the service ─────────────────────────────────────


def test_the_workflow_invokes_no_game_driven_cli(workflow_text):
    assert 'game_driven_ingestion.py' not in workflow_text


def test_the_workflow_passes_no_exclusive_scope(workflow_text):
    assert '--only-game-pk' not in workflow_text


def _invocations(workflow_text, runner):
    """Executable invocations only — a mention in a comment is not a call."""
    return workflow_text.count(f'python backend/scripts/{runner}')


def test_the_daily_runner_is_invoked_exactly_once(workflow_text):
    assert _invocations(workflow_text, 'run_daily_sync.py') == 1


def test_the_postgame_runner_is_invoked_by_postgame_and_backfill_only(workflow_text):
    # Two: the scheduled/manual postgame cycle, and the explicit backfill that
    # shares the runner with the mode pinned off.
    assert _invocations(workflow_text, 'run_postgame_refresh.py') == 2


def test_no_foundation_3c_workflow_was_recreated():
    names = [path.name for path in (REPO_ROOT / '.github/workflows').glob('*')]
    assert not [name for name in names if 'foundation-3c' in name.lower()]


def test_no_workflow_display_name_mentions_the_closed_rollout():
    for path in (REPO_ROOT / '.github/workflows').glob('*.yml'):
        assert 'Foundation 3C' not in path.read_text(encoding='utf-8')


# ── Durable evidence, not parsed stdout ─────────────────────────────────────


def test_the_daily_runner_writes_a_durable_summary(public_sync):
    step = _step(public_sync, 'Run direct daily sync')
    assert step['env']['DAILY_SYNC_SUMMARY_PATH'] == (
        'artifacts/game-driven-shadow/daily-sync-summary.json'
    )
    assert '--output "$DAILY_SYNC_SUMMARY_PATH"' in step['run']


def test_the_postgame_runner_writes_a_durable_summary(public_sync):
    step = _step(public_sync, 'Run direct postgame refresh')
    assert step['env']['POSTGAME_SYNC_SUMMARY_PATH'] == (
        'artifacts/game-driven-shadow/postgame-sync-summary.json'
    )
    assert '--output "$POSTGAME_SYNC_SUMMARY_PATH"' in step['run']


def test_the_backfill_step_writes_no_activation_evidence(public_sync):
    run = _step(public_sync, 'Run explicit backfill')['run']
    assert '--output' not in run
    assert 'game-driven-shadow' not in run


@pytest.mark.parametrize('step_name,output_key', [
    ('Run direct daily sync', 'runner_exit_code'),
    ('Run direct postgame refresh', 'runner_exit_code'),
])
def test_the_runner_exit_code_is_recorded_before_the_step_can_exit(
    public_sync, step_name, output_key,
):
    run = _step(public_sync, step_name)['run']
    record_at = run.index(f'echo "{output_key}=$exit_code" >> "$GITHUB_OUTPUT"')
    exit_at = run.index('exit "$exit_code"')
    assert record_at < exit_at, (
        'the exit code must be recorded before the step exits, or a failed '
        'runner leaves the validator with nothing to read'
    )


def test_the_activation_evidence_is_not_parsed_from_stdout(public_sync):
    for name in ('Validate game-driven shadow activation cycle',):
        run = _step(public_sync, name)['run']
        assert 'grep' not in run.split('patterns=')[0]
        assert '--sync-summary' in run


# ── Ordering: production first, then evidence, then the gate ────────────────


def test_activation_validation_runs_after_the_existing_production_gates(public_sync):
    assert _step_index(public_sync, 'Appearance ledger audit') < _step_index(
        public_sync, 'Validate game-driven shadow activation cycle'
    )
    assert _step_index(public_sync, 'Verify dashboard snapshot cache') < _step_index(
        public_sync, 'Validate game-driven shadow activation cycle'
    )


def test_the_scan_runs_before_the_upload(public_sync):
    assert _step_index(public_sync, 'Scan activation artifacts') < _step_index(
        public_sync, 'Upload game-driven shadow activation artifacts'
    )


def test_the_summary_is_appended_before_the_upload(public_sync):
    assert _step_index(public_sync, 'Append activation summary') < _step_index(
        public_sync, 'Upload game-driven shadow activation artifacts'
    )


def test_the_final_gate_runs_after_the_upload(public_sync):
    assert _step_index(public_sync, 'Upload game-driven shadow activation') < (
        _step_index(public_sync, 'activation health gate')
    )


def test_the_final_gate_is_the_last_step(public_sync):
    assert _steps(public_sync)[-1]['name'].endswith('activation health gate')


def test_the_validator_does_not_gate_the_production_publication_steps(public_sync):
    """Publication must not wait on, or be conditioned by, activation health."""
    for name in ('Appearance ledger audit', 'Verify dashboard snapshot cache'):
        condition = str(_step(public_sync, name).get('if'))
        assert 'activation' not in condition.lower()


@pytest.mark.parametrize('name', [
    'Validate game-driven shadow activation cycle',
    'Scan activation artifacts',
    'Append activation summary',
    'Upload game-driven shadow activation artifacts',
    'activation health gate',
])
def test_an_activation_step_runs_under_always(public_sync, name):
    assert 'always()' in str(_step(public_sync, name).get('if'))


@pytest.mark.parametrize('name', [
    'Validate game-driven shadow activation cycle',
    'Scan activation artifacts',
    'Append activation summary',
    'Upload game-driven shadow activation artifacts',
    'activation health gate',
])
def test_an_activation_step_covers_both_eligible_cycles(public_sync, name):
    """Both cycles are observed again, and only those two."""
    condition = str(_step(public_sync, name).get('if'))
    assert "inputs.mode == 'daily'" in condition
    assert "inputs.mode == 'postgame'" in condition
    assert f"github.event.schedule == '{DAILY_CRON}'" in condition
    assert f"github.event.schedule == '{POSTGAME_CRON}'" in condition
    assert MORNING_CRON not in condition
    assert "inputs.mode == 'backfill'" not in condition
    assert "inputs.mode == 'intraday'" not in condition


def test_the_validator_captures_its_exit_code_rather_than_terminating(public_sync):
    run = _step(public_sync, 'Validate game-driven shadow activation cycle')['run']
    assert 'set +e' in run
    assert 'validate_code=$?' in run
    assert 'activation-exit-code' in run


def test_the_final_gate_fails_on_a_failed_validation(public_sync):
    run = _step(public_sync, 'activation health gate')['run']
    assert 'exit 1' in run


def test_an_unproven_validator_result_is_treated_as_failure(public_sync):
    run = _step(public_sync, 'activation health gate')['run']
    # The catch-all branch must exit non-zero, not fall through as a pass.
    tail = run.split('*)')[-1]
    assert 'exit 1' in tail


def test_a_missing_summary_is_an_activation_failure(public_sync):
    run = _step(public_sync, 'Validate game-driven shadow activation cycle')['run']
    assert 'echo "2" > "$ACTIVATION_DIR/activation-exit-code"' in run


# ── Artifacts ───────────────────────────────────────────────────────────────


def test_the_artifact_name_is_run_scoped(public_sync):
    upload = _step(public_sync, 'Upload game-driven shadow activation artifacts')
    assert upload['with']['name'] == 'game-driven-shadow-${{ github.run_id }}'


def test_the_artifact_retention_is_finite(public_sync):
    upload = _step(public_sync, 'Upload game-driven shadow activation artifacts')
    assert upload['with']['retention-days'] == 30


def test_the_artifact_upload_warns_rather_than_silently_skipping(public_sync):
    upload = _step(public_sync, 'Upload game-driven shadow activation artifacts')
    assert upload['with']['if-no-files-found'] == 'warn'


def test_the_upload_uses_the_pinned_action(public_sync):
    upload = _step(public_sync, 'Upload game-driven shadow activation artifacts')
    assert upload['uses'] == 'actions/upload-artifact@v4'


def test_the_upload_covers_all_three_artifact_kinds(public_sync):
    paths = _step(
        public_sync, 'Upload game-driven shadow activation artifacts',
    )['with']['path']
    for suffix in (
        '*-sync-summary.json',
        '*-activation-summary.json',
        '*-activation-summary.md',
    ):
        assert suffix in paths


# ── Credential scan ─────────────────────────────────────────────────────────


@pytest.mark.parametrize('pattern', [
    'postgresql://', 'postgres://', 'password=', 'Authorization:',
    'X-Admin-Token', 'ADMIN_API_TOKEN', 'SECRET_KEY', 'DATABASE_URL',
    'BASEBALLOS_ADMIN_API_TOKEN', 'token=', 'api_key=', 'api-key=', 'secret=',
])
def test_the_scan_rejects_a_required_pattern(public_sync, pattern):
    run = _step(public_sync, 'Scan activation artifacts')['run']
    assert pattern in run


def test_the_scan_also_rejects_tracebacks_and_runner_paths(public_sync):
    run = _step(public_sync, 'Scan activation artifacts')['run']
    assert 'Traceback' in run
    assert '/home/runner/work' in run


def test_the_scan_quarantines_rather_than_uploading(public_sync):
    run = _step(public_sync, 'Scan activation artifacts')['run']
    assert 'rm -f "$file"' in run


def test_the_scan_never_prints_the_matched_content(public_sync):
    run = _step(public_sync, 'Scan activation artifacts')['run']
    assert 'grep -Eq' in run, 'quiet grep only — a printing grep would leak'
    assert 'basename' in run


def test_an_unsafe_artifact_fails_the_final_gate(public_sync):
    run = _step(public_sync, 'activation health gate')['run']
    assert 'activation-scan-unsafe' in run


# ── Mechanical validity ─────────────────────────────────────────────────────


def test_the_workflow_yaml_parses(workflow):
    assert workflow['name'] == 'BaseballOS Bullpen Sync'


def test_every_shell_block_parses(workflow):
    failures = []
    for job_name, job in workflow['jobs'].items():
        for step in _steps(job):
            script = step.get('run')
            if not script:
                continue
            with tempfile.NamedTemporaryFile(
                'w', suffix='.sh', delete=False,
            ) as handle:
                handle.write(script)
                path = handle.name
            result = subprocess.run(
                ['bash', '-n', path], capture_output=True, text=True,
            )
            Path(path).unlink()
            if result.returncode != 0:
                failures.append(f"{job_name}/{step.get('name')}")
    assert failures == []
