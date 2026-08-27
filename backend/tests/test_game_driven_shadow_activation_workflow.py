"""Structure of the automated game-driven shadow activation.

The reviewed workflow source is the activation authority for this phase: there
is no input, no repository variable, and no other lever that can move the lane
to a writing mode without a code review. These tests own that property, and the
property that the established production path was not disturbed to get it.

OPS-001 added a second property they now own. Activation health used to be
evaluated at the end of ``public-sync``, so a shadow-only defect turned the
publication job red and skipped ``internal-enrichment`` and
``static-team-story-preview`` — even when the sync, snapshot publication,
appearance-ledger proof, and dashboard verification those jobs actually depend
on had all succeeded. One red signal meant two unrelated things.

The observer now lives in its own job. These tests assert the boundary in both
directions: no publication-critical work left ``public-sync``, and no shadow
verdict remains inside it.
"""

import json
import re
import subprocess
import tempfile
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = REPO_ROOT / '.github/workflows/baseballos-sync.yml'
MODE_ENV = 'GAME_DRIVEN_INGESTION_MODE'

DAILY_CRON = '17 10 * * *'
MORNING_CRON = '23 14 * * *'
POSTGAME_CRON = '11 2,4,6 * * *'

SHADOW_JOB = 'shadow-activation-health'
PRODUCTION_CREDENTIALS = (
    'DATABASE_URL', 'SECRET_KEY', 'ADMIN_API_TOKEN',
    'BASEBALLOS_ADMIN_API_TOKEN', 'BASEBALLOS_SYNC_URL',
)


@pytest.fixture(scope='module')
def workflow_text():
    return WORKFLOW_PATH.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def workflow(workflow_text):
    return yaml.safe_load(workflow_text)


@pytest.fixture(scope='module')
def public_sync(workflow):
    return workflow['jobs']['public-sync']


@pytest.fixture(scope='module')
def shadow_activation_health(workflow):
    return workflow['jobs'][SHADOW_JOB]


@pytest.fixture(scope='module')
def internal_enrichment(workflow):
    return workflow['jobs']['internal-enrichment']


@pytest.fixture(scope='module')
def static_team_story_preview(workflow):
    return workflow['jobs']['static-team-story-preview']


def _steps(job):
    return job.get('steps') or []


def _step(job, name_fragment):
    for step in _steps(job):
        if name_fragment.lower() in str(step.get('name') or '').lower():
            return step
    raise AssertionError(f'no step matching {name_fragment!r}')


def _has_step(job, name_fragment):
    return any(
        name_fragment.lower() in str(step.get('name') or '').lower()
        for step in _steps(job)
    )


def _mode(step):
    return (step.get('env') or {}).get(MODE_ENV)


def _step_index(job, name_fragment):
    for index, step in enumerate(_steps(job)):
        if name_fragment.lower() in str(step.get('name') or '').lower():
            return index
    raise AssertionError(f'no step matching {name_fragment!r}')


def _blob(job):
    return json.dumps(job)


# ── The established production path is untouched ────────────────────────────


def test_production_crons_are_staggered_off_the_hour(workflow):
    crons = [entry['cron'] for entry in workflow[True]['schedule']]
    assert crons == [DAILY_CRON, MORNING_CRON, POSTGAME_CRON]


def test_no_cron_was_added(workflow):
    assert len(workflow[True]['schedule']) == 3


def test_the_manual_modes_include_only_governed_recovery(workflow):
    options = workflow[True]['workflow_dispatch']['inputs']['mode']['options']
    assert options == ['recovery_daily', 'recovery_postgame', 'backfill', 'intraday']


def test_the_manual_inputs_include_recovery_evidence(workflow):
    inputs = workflow[True]['workflow_dispatch']['inputs']
    assert sorted(inputs) == [
        'backfill_date', 'confirm_recovery', 'mode', 'recovery_reason',
        'scheduled_for',
    ]


def test_permissions_are_not_broadened(workflow):
    """CI-003 / #598 narrowed this, and it must stay narrowed.

    The workflow used to grant ``contents: write`` to every job in it, including
    four that never touch the repository. Write authority now belongs to the one
    job that publishes generated content, and the workflow default is read-only.
    Anything that puts write back at workflow scope — or hands it to a second
    job — is a broadening, which is what this test has always existed to catch.
    """
    assert workflow['permissions'] == {'contents': 'read'}

    writers = sorted(
        name for name, job in workflow['jobs'].items()
        if (job.get('permissions') or {}).get('contents') == 'write'
    )
    assert writers == ['static-team-story-preview']
    assert workflow['jobs']['static-team-story-preview']['permissions'] == {
        'contents': 'write'
    }


def test_concurrency_is_unchanged(workflow):
    assert workflow['concurrency'] == {
        'group': 'baseballos-sync',
        'cancel-in-progress': False,
    }


def test_the_daily_command_timeout_is_the_ops_002_value(public_sync):
    """OPS-002 raised this from 20m deliberately.

    It is a last-resort kill, not control flow: 40m = 2400s sits 200s above the
    2200s internal budget so the Python process always reaches its own governed
    shutdown first and still writes its metadata, snapshot decision, and
    writer-guard release.
    """
    step = _step(public_sync, 'Run direct daily sync')
    assert step['env']['DAILY_SYNC_COMMAND_TIMEOUT'] == '40m'


def test_the_postgame_command_timeout_is_unchanged(public_sync):
    step = _step(public_sync, 'Run direct postgame refresh')
    assert step['env']['POSTGAME_REFRESH_COMMAND_TIMEOUT'] == '20m'


def test_the_public_sync_job_timeout_is_the_ops_002_value(public_sync):
    """Raised with the daily command timeout, not independently.

    The 60 minutes covers the worst case of the step timeouts that remain
    (40m sync + 10m tonight + 5m audit) plus uploads and cleanup. It was 40
    when the daily command timeout was 20m; OPS-002 moved both together so the
    always() ledger and cache proofs still get to run after a shell kill.
    """
    assert public_sync['timeout-minutes'] == 60


@pytest.mark.parametrize('name', [
    'Appearance ledger audit',
    'Verify dashboard snapshot cache',
    'Run morning slate schedule refresh',
    'Run explicit backfill',
    'Run direct daily sync',
    'Run direct postgame refresh',
    'Upload appearance ledger audit report',
])
def test_an_existing_production_step_is_retained(public_sync, name):
    assert _step(public_sync, name) is not None


def test_the_daily_runner_uses_due_coordinator(public_sync):
    run = _step(public_sync, 'Run direct daily sync')['run']
    assert 'run_due_sync.py --mode daily' in run
    assert '--execution-source "$EXECUTION_SOURCE"' in run


def test_the_postgame_runner_uses_due_coordinator(public_sync):
    run = _step(public_sync, 'Run direct postgame refresh')['run']
    assert 'run_due_sync.py --mode postgame' in run
    assert '--execution-source "$EXECUTION_SOURCE"' in run


def test_the_appearance_ledger_command_is_unchanged(public_sync):
    run = _step(public_sync, 'Appearance ledger audit')['run']
    assert 'appearance_ledger_audit.py --days 10 --deep' in run


@pytest.mark.parametrize('name', [
    'Run direct daily sync',
    'Run direct postgame refresh',
    'Run morning slate schedule refresh',
    'Run explicit backfill',
    'Appearance ledger audit',
    'Verify dashboard snapshot cache',
])
def test_no_publication_critical_step_became_advisory(public_sync, name):
    """continue-on-error here would convert a real failure into a green run."""
    assert _step(public_sync, name).get('continue-on-error') is not True


# ── Shadow is on exactly the two eligible steps ─────────────────────────────


def test_the_daily_step_runs_in_shadow(public_sync):
    assert _mode(_step(public_sync, 'Run direct daily sync')) == 'shadow'


def test_the_postgame_step_runs_in_shadow(public_sync):
    assert _mode(_step(public_sync, 'Run direct postgame refresh')) == 'shadow'


def test_manual_daily_uses_the_same_shadow_enabled_step(public_sync):
    condition = _step(public_sync, 'Run direct daily sync')['if']
    assert "inputs.mode == 'recovery_daily'" in condition
    assert f"github.event.schedule == '{DAILY_CRON}'" in condition


def test_manual_postgame_uses_the_same_step(public_sync):
    condition = _step(public_sync, 'Run direct postgame refresh')['if']
    assert "inputs.mode == 'recovery_postgame'" in condition
    assert f"github.event.schedule == '{POSTGAME_CRON}'" in condition


def test_backfill_is_explicitly_off(public_sync):
    assert _mode(_step(public_sync, 'Run explicit backfill')) == 'off'


def test_exactly_three_steps_configure_the_mode(workflow):
    configured = [
        step.get('name')
        for job in workflow['jobs'].values()
        for step in _steps(job)
        if _mode(step) is not None
    ]
    assert len(configured) == 3


def test_exactly_two_shadow_literals_and_one_off_literal(workflow):
    modes = sorted(
        _mode(step)
        for job in workflow['jobs'].values()
        for step in _steps(job)
        if _mode(step) is not None
    )
    assert modes == ['off', 'shadow', 'shadow']


def test_the_mode_is_never_set_at_job_scope(workflow):
    for name, job in workflow['jobs'].items():
        assert MODE_ENV not in (job.get('env') or {}), name


@pytest.mark.parametrize('name', [
    'Run morning slate schedule refresh',
    'Appearance ledger audit',
    'Verify dashboard snapshot cache',
])
def test_an_excluded_step_does_not_inherit_shadow(public_sync, name):
    assert _mode(_step(public_sync, name)) is None


def test_the_intraday_job_never_reaches_the_lane(workflow):
    job = workflow['jobs']['intraday-audit']
    assert all(_mode(step) is None for step in _steps(job))


@pytest.mark.parametrize('job_name', [
    'internal-enrichment', 'static-team-story-preview', 'intraday-audit',
    SHADOW_JOB,
])
def test_an_unrelated_job_configures_no_mode(workflow, job_name):
    job = workflow['jobs'][job_name]
    assert all(_mode(step) is None for step in _steps(job))


def test_the_observer_job_never_sets_the_ingestion_mode(shadow_activation_health):
    """It validates retained evidence; it does not invoke the lane."""
    assert MODE_ENV not in _blob(shadow_activation_health)


# ── No promotion path that skips review ─────────────────────────────────────


def test_no_workflow_input_can_select_the_game_driven_mode(workflow_text, workflow):
    inputs = workflow[True]['workflow_dispatch']['inputs']
    assert MODE_ENV.lower() not in ' '.join(inputs).lower()
    for name, spec in inputs.items():
        assert 'shadow' not in json.dumps(spec).lower(), name


def test_no_repository_variable_can_promote_the_mode(workflow_text):
    for line in workflow_text.splitlines():
        if MODE_ENV in line:
            assert 'vars.' not in line
            assert 'inputs.' not in line
            assert 'secrets.' not in line


def test_the_workflow_never_names_a_writing_mode(workflow_text):
    for line in workflow_text.splitlines():
        if MODE_ENV in line:
            assert "'write'" not in line
            assert "'authoritative'" not in line


def test_the_workflow_supplies_no_expected_plan_fingerprint(workflow_text):
    assert '--expected-plan-fingerprint' not in workflow_text


def test_no_historical_foundation_fingerprint_appears_in_a_command(workflow_text):
    assert not re.search(r'--expected-[a-z-]*fingerprint', workflow_text)


# ── One invocation, through the service ─────────────────────────────────────


def test_the_workflow_invokes_no_game_driven_cli(workflow_text):
    assert 'scripts/game_driven_ingestion.py' not in workflow_text


def test_the_workflow_passes_no_exclusive_scope(workflow_text):
    assert '--only-game-pk' not in workflow_text


def _invocations(workflow_text, runner):
    """Executable invocations only — a mention in a comment is not a call."""
    return workflow_text.count(f'python backend/scripts/{runner}')


def test_the_daily_runner_is_invoked_exactly_once(workflow_text):
    assert workflow_text.count('python backend/scripts/run_due_sync.py --mode daily') == 1


def test_postgame_due_and_backfill_runners_are_separate(workflow_text):
    assert workflow_text.count('python backend/scripts/run_due_sync.py --mode postgame') == 1
    assert _invocations(workflow_text, 'run_postgame_refresh.py') == 1


def test_no_foundation_3c_workflow_was_recreated():
    for path in (REPO_ROOT / '.github/workflows').glob('*.yml'):
        assert 'foundation-3c' not in path.name.lower()


# The sole remaining scheduled workflow after the 2026 seasonal intraday repair
# retirement. Separating a job must not add another scheduled lane outside this
# workflow's concurrency group where it could overlap a production sync.
EXISTING_SCHEDULED_WORKFLOWS = (
    'baseballos-sync.yml',
)


def test_no_scheduled_workflow_was_added():
    scheduled = []
    for path in sorted((REPO_ROOT / '.github/workflows').glob('*.yml')):
        parsed = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
        triggers = parsed.get(True) or parsed.get('on') or {}
        if isinstance(triggers, dict) and 'schedule' in triggers:
            scheduled.append(path.name)
    assert tuple(scheduled) == EXISTING_SCHEDULED_WORKFLOWS


def test_the_observer_did_not_become_its_own_scheduled_workflow():
    """The split adds a JOB, not a lane. A separate workflow would run outside
    the concurrency group that keeps production syncs from overlapping."""
    sync = yaml.safe_load(WORKFLOW_PATH.read_text(encoding='utf-8'))
    assert SHADOW_JOB in sync['jobs']


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


def test_the_activation_evidence_is_not_parsed_from_stdout(shadow_activation_health):
    run = _step(shadow_activation_health, 'Validate game-driven shadow')['run']
    assert '--sync-summary' in run


# ══ OPS-001: publication and observer are separate jobs ══════════════════════


def test_the_observer_job_exists(workflow):
    assert SHADOW_JOB in workflow['jobs']


def test_the_observer_job_needs_only_public_sync(shadow_activation_health):
    needs = shadow_activation_health['needs']
    needs = [needs] if isinstance(needs, str) else list(needs)
    assert needs == ['public-sync']


def test_the_observer_job_runs_under_always(shadow_activation_health):
    """It must still run when public-sync failed.

    A public failure that happens after the runner wrote its summary leaves
    real activation evidence behind, and that evidence is worth validating and
    preserving rather than discarding.
    """
    assert 'always()' in shadow_activation_health['if']


def test_the_observer_job_does_not_require_public_sync_success(
    shadow_activation_health,
):
    assert "needs.public-sync.result == 'success'" not in shadow_activation_health['if']


def test_the_observer_job_covers_both_eligible_cycles(shadow_activation_health):
    condition = shadow_activation_health['if']
    assert "inputs.mode == 'recovery_daily'" in condition
    assert "inputs.mode == 'recovery_postgame'" in condition
    assert f"github.event.schedule == '{DAILY_CRON}'" in condition
    assert f"github.event.schedule == '{POSTGAME_CRON}'" in condition


def test_the_observer_job_excludes_morning_backfill_and_intraday(
    shadow_activation_health,
):
    condition = shadow_activation_health['if']
    assert MORNING_CRON not in condition
    assert "inputs.mode == 'backfill'" not in condition
    assert "inputs.mode == 'intraday'" not in condition


def test_the_validator_no_longer_runs_inside_public_sync(public_sync):
    assert 'validate_game_driven_shadow_cycle.py' not in _blob(public_sync)


def test_the_activation_health_gate_no_longer_runs_inside_public_sync(public_sync):
    assert not _has_step(public_sync, 'activation health gate')
    assert 'evaluate_shadow_activation_gate.py' not in _blob(public_sync)


def test_no_shadow_verdict_can_exit_nonzero_inside_public_sync(public_sync):
    """The whole point of the split, stated as one assertion."""
    assert 'activation-exit-code' not in _blob(public_sync)


def test_the_validator_is_invoked_exactly_once_in_the_workflow(workflow_text):
    assert workflow_text.count('validate_game_driven_shadow_cycle.py') == 1


def test_the_final_gate_is_invoked_exactly_once_in_the_workflow(workflow_text):
    assert workflow_text.count('evaluate_shadow_activation_gate.py') == 1


def test_the_validator_runs_exactly_once_in_the_observer_job(
    shadow_activation_health,
):
    matches = [
        step for step in _steps(shadow_activation_health)
        if 'validate_game_driven_shadow_cycle.py' in str(step.get('run') or '')
    ]
    assert len(matches) == 1


def test_the_health_gate_runs_exactly_once_in_the_observer_job(
    shadow_activation_health,
):
    matches = [
        step for step in _steps(shadow_activation_health)
        if 'evaluate_shadow_activation_gate.py' in str(step.get('run') or '')
    ]
    assert len(matches) == 1


def test_no_public_sync_production_step_reads_a_shadow_result(public_sync):
    for step in _steps(public_sync):
        condition = str(step.get('if') or '')
        assert SHADOW_JOB not in condition
        assert 'activation-validate' not in condition


# ══ Credential isolation ═════════════════════════════════════════════════════


@pytest.mark.parametrize('credential', PRODUCTION_CREDENTIALS)
def test_the_observer_job_holds_no_production_credential(
    shadow_activation_health, credential,
):
    assert credential not in _blob(shadow_activation_health)


def test_the_observer_job_references_no_repository_secret(shadow_activation_health):
    assert 'secrets.' not in _blob(shadow_activation_health)


@pytest.mark.parametrize('command', [
    'run_daily_sync.py', 'run_postgame_refresh.py', 'run_tonight_refresh.py',
    'refresh_slate_schedule.py', 'appearance_ledger_audit.py',
])
def test_the_observer_job_invokes_no_production_command(
    shadow_activation_health, command,
):
    assert command not in _blob(shadow_activation_health)


def test_the_observer_job_sets_no_production_app_env(shadow_activation_health):
    assert 'APP_ENV' not in _blob(shadow_activation_health)


# ══ Handoff safety ═══════════════════════════════════════════════════════════


def test_the_handoff_stages_rather_than_uploading_the_runner_directory(public_sync):
    """A scanner bug must produce an empty handoff, not a leak."""
    upload = _step(public_sync, 'Upload game-driven shadow handoff')
    path = upload['with']['path']
    assert path.strip() == 'artifacts/game-driven-shadow-handoff'
    assert 'artifacts/game-driven-shadow\n' not in path
    assert path.strip() != 'artifacts/game-driven-shadow'


def test_the_handoff_preparation_uses_the_shared_helper(public_sync):
    run = _step(public_sync, 'Prepare game-driven shadow handoff')['run']
    assert 'prepare_shadow_handoff.py' in run
    assert '--source-dir' in run and '--staging-dir' in run


def test_the_handoff_preparation_runs_before_the_handoff_upload(public_sync):
    assert (
        _step_index(public_sync, 'Prepare game-driven shadow handoff')
        < _step_index(public_sync, 'Upload game-driven shadow handoff')
    )


def test_the_handoff_artifact_is_run_scoped(public_sync):
    upload = _step(public_sync, 'Upload game-driven shadow handoff')
    assert upload['with']['name'] == (
        'game-driven-shadow-handoff-${{ github.run_id }}'
    )


def test_the_handoff_retention_is_finite_and_short(public_sync):
    upload = _step(public_sync, 'Upload game-driven shadow handoff')
    retention = upload['with']['retention-days']
    assert 0 < int(retention) <= 7


def test_the_handoff_upload_uses_the_pinned_action(public_sync):
    upload = _step(public_sync, 'Upload game-driven shadow handoff')
    assert upload['uses'] == 'actions/upload-artifact@v4'


@pytest.mark.parametrize('name', [
    'Prepare game-driven shadow handoff',
    'Upload game-driven shadow handoff',
])
def test_a_handoff_failure_cannot_fail_public_sync(public_sync, name):
    assert _step(public_sync, name)['continue-on-error'] is True


def test_the_handoff_preparation_step_always_exits_zero(public_sync):
    run = _step(public_sync, 'Prepare game-driven shadow handoff')['run']
    assert run.rstrip().endswith('exit 0')


def test_the_observer_downloads_the_matching_handoff(shadow_activation_health):
    download = _step(shadow_activation_health, 'Download game-driven shadow handoff')
    assert download['uses'].startswith('actions/download-artifact@')
    assert download['with']['name'] == (
        'game-driven-shadow-handoff-${{ github.run_id }}'
    )
    assert download['continue-on-error'] is True


# ══ Final artifact safety ════════════════════════════════════════════════════


def test_the_final_scan_runs_before_the_final_upload(shadow_activation_health):
    assert (
        _step_index(shadow_activation_health, 'Scan activation artifacts')
        < _step_index(shadow_activation_health, 'Upload game-driven shadow activation')
    )


def test_the_summary_is_appended_before_the_final_upload(shadow_activation_health):
    assert (
        _step_index(shadow_activation_health, 'Append activation summary')
        < _step_index(shadow_activation_health, 'Upload game-driven shadow activation')
    )


def test_the_final_upload_runs_before_the_final_gate(shadow_activation_health):
    assert (
        _step_index(shadow_activation_health, 'Upload game-driven shadow activation')
        < _step_index(shadow_activation_health, 'activation health gate')
    )


def test_the_final_gate_is_the_last_step(shadow_activation_health):
    assert (
        _step_index(shadow_activation_health, 'activation health gate')
        == len(_steps(shadow_activation_health)) - 1
    )


def test_the_final_artifact_name_is_run_scoped(shadow_activation_health):
    upload = _step(shadow_activation_health, 'Upload game-driven shadow activation')
    assert upload['with']['name'] == 'game-driven-shadow-${{ github.run_id }}'


def test_the_final_artifact_retention_is_unchanged(shadow_activation_health):
    upload = _step(shadow_activation_health, 'Upload game-driven shadow activation')
    assert upload['with']['retention-days'] == 30


def test_the_final_upload_uses_the_pinned_action(shadow_activation_health):
    upload = _step(shadow_activation_health, 'Upload game-driven shadow activation')
    assert upload['uses'] == 'actions/upload-artifact@v4'


def test_the_final_upload_covers_every_artifact_kind(shadow_activation_health):
    path = _step(
        shadow_activation_health, 'Upload game-driven shadow activation',
    )['with']['path']
    for expected in (
        '*-sync-summary.json',
        '*-activation-summary.json',
        '*-activation-summary.md',
        'handoff-metadata.json',
    ):
        assert expected in path


def test_the_final_upload_outcome_is_captured_for_the_gate(shadow_activation_health):
    upload = _step(shadow_activation_health, 'Upload game-driven shadow activation')
    assert upload['continue-on-error'] is True
    assert upload['id'] == 'activation-upload'
    gate = _step(shadow_activation_health, 'activation health gate')
    assert 'steps.activation-upload.outcome' in json.dumps(gate['env'])


def test_the_final_scan_uses_the_shared_scanner(shadow_activation_health):
    run = _step(shadow_activation_health, 'Scan activation artifacts')['run']
    assert 'scan_forbidden_artifact_content.py' in run
    assert '--quarantine' in run


def test_the_scan_result_is_captured_for_the_gate(shadow_activation_health):
    gate = _step(shadow_activation_health, 'activation health gate')
    assert 'steps.activation-scan.outputs.safe' in json.dumps(gate['env'])


def test_the_download_outcome_is_captured_for_the_gate(shadow_activation_health):
    gate = _step(shadow_activation_health, 'activation health gate')
    assert 'steps.handoff-download.outcome' in json.dumps(gate['env'])


def test_no_forbidden_pattern_list_is_duplicated_in_the_workflow(workflow, workflow_text):
    """One pattern list, however many scans there are.

    The two scans previously carried independent copies of the same list, which
    is a list that can drift silently — the second copy learns about a new
    secret shape only if someone remembers it exists. The fix was never "scan
    once"; it was "never inline the list". CI-003 / #598 added a third scan, for
    the generated-publication evidence, and it delegates to the same shared
    scanner. What must stay true is that every scan step in this workflow goes
    through that one script and none rolls its own patterns.
    """
    assert 'BASEBALLOS_ADMIN_API_TOKEN|token=' not in workflow_text

    scan_steps = [
        step
        for job in workflow['jobs'].values()
        for step in (job.get('steps') or [])
        if 'scan' in (step.get('name') or '').lower()
    ]
    assert scan_steps, 'the workflow no longer scans artifacts before upload'
    for step in scan_steps:
        assert 'scan_forbidden_artifact_content.py' in (step.get('run') or ''), (
            f'{step.get("name")!r} must delegate to the one shared scanner'
        )


# ══ Dependency graph ═════════════════════════════════════════════════════════


def test_internal_enrichment_needs_only_public_sync(internal_enrichment):
    needs = internal_enrichment['needs']
    needs = [needs] if isinstance(needs, str) else list(needs)
    assert needs == ['public-sync']


def test_internal_enrichment_requires_public_sync_success(internal_enrichment):
    assert "needs.public-sync.result == 'success'" in internal_enrichment['if']


def test_internal_enrichment_never_mentions_shadow_health(internal_enrichment):
    assert SHADOW_JOB not in _blob(internal_enrichment)


def test_internal_enrichment_remains_non_blocking(internal_enrichment):
    assert internal_enrichment['continue-on-error'] is True


def test_static_preview_needs_only_public_sync(static_team_story_preview):
    needs = static_team_story_preview['needs']
    needs = [needs] if isinstance(needs, str) else list(needs)
    assert needs == ['public-sync']


def test_static_preview_requires_public_sync_success(static_team_story_preview):
    assert "needs.public-sync.result == 'success'" in static_team_story_preview['if']


def test_static_preview_keeps_its_daily_only_condition(static_team_story_preview):
    condition = static_team_story_preview['if']
    assert "inputs.mode == 'recovery_daily'" in condition
    assert f"github.event.schedule == '{DAILY_CRON}'" in condition


def test_static_preview_never_mentions_shadow_health(static_team_story_preview):
    assert SHADOW_JOB not in _blob(static_team_story_preview)


def test_no_job_depends_on_the_observer(workflow):
    for name, job in workflow['jobs'].items():
        needs = job.get('needs') or []
        needs = [needs] if isinstance(needs, str) else list(needs)
        assert SHADOW_JOB not in needs, name


def test_the_observer_is_the_only_job_holding_the_activation_gate(workflow):
    holders = [
        name for name, job in workflow['jobs'].items()
        if 'evaluate_shadow_activation_gate.py' in _blob(job)
    ]
    assert holders == [SHADOW_JOB]


# ══ Mechanical validity ══════════════════════════════════════════════════════


def test_the_workflow_yaml_parses(workflow):
    assert workflow['jobs']


def test_the_expected_jobs_exist(workflow):
    # 'team-state-vnext-proof' is the second observer job, added with D-056. Like
    # this file's shadow observer it holds no production credential, gates nothing,
    # and is itself gated by nothing; its own contract lives in
    # tests/test_team_state_vnext_proof_workflow.py.
    assert sorted(workflow['jobs']) == sorted([
        'public-sync', SHADOW_JOB, 'internal-enrichment',
        'static-team-story-preview', 'intraday-audit', 'team-state-vnext-proof',
    ])


def test_no_duplicate_job_names(workflow_text):
    names = re.findall(r'^  ([a-z][a-z0-9-]*):$', workflow_text, re.M)
    assert len(names) == len(set(names))


def test_every_shell_block_parses(workflow):
    for job in workflow['jobs'].values():
        for step in _steps(job):
            run = step.get('run')
            if not run:
                continue
            with tempfile.NamedTemporaryFile('w', suffix='.sh') as handle:
                handle.write(run)
                handle.flush()
                result = subprocess.run(
                    ['bash', '-n', handle.name],
                    capture_output=True, text=True,
                )
            assert result.returncode == 0, (
                f"{step.get('name')}: {result.stderr}"
            )


# ── OPS-002 — the mitigated runtime budget is a reviewed workflow contract ───
#
# The August 6 incident was a runtime-budget exhaustion: five upstream stages
# consumed 612-628s, the combined ingestion pool that remained was 151-168s,
# the shadow observer took its share, and the legacy GameLog writer received
# 112-125s for work whose corrected cold upper bound is 767-895s. The mitigation
# is four workflow values and nothing else.
#
# These tests own two properties. First, the mitigated values are exactly what
# was reviewed. Second — and this is the one that matters — raising a ceiling
# did not quietly buy anything else: no new schedule, no new mode, no promoted
# lane, no advisory production step, no retry.

OPS002_TOTAL_BUDGET = '2200'
OPS002_FINAL_PHASE_RESERVE = '300'
OPS002_INGESTION_CAP = '1500'
OPS002_DAILY_COMMAND_TIMEOUT = '40m'
OPS002_JOB_TIMEOUT_MINUTES = 60
POSTGAME_COMMAND_TIMEOUT = '20m'

MAX_OBSERVED_UPSTREAM_SECONDS = 628.5
MITIGATION_FLOOR_SECONDS = 950.0
SHADOW_LANE_SHARE = 0.25

TONIGHT_TIMEOUT_MINUTES = 10
APPEARANCE_AUDIT_TIMEOUT_MINUTES = 5


@pytest.fixture(scope='module')
def daily_step(public_sync):
    return _step(public_sync, 'Run direct daily sync')


def _minutes(timeout_text):
    assert timeout_text.endswith('m'), timeout_text
    return int(timeout_text[:-1])


def test_the_total_internal_budget_is_the_ops_002_value(daily_step):
    assert daily_step['env']['DAILY_SYNC_TOTAL_BUDGET_SECONDS'] == OPS002_TOTAL_BUDGET


def test_the_final_phase_reserve_is_unchanged(daily_step):
    """Deliberately NOT part of the mitigation.

    The final phase genuinely needs it — the successful August 6 recovery spent
    189.7s in its snapshot phase alone. Reducing it would be the wrong lever
    and would endanger finalisation, so it stays at 300 and is not in rollback.
    """
    assert (
        daily_step['env']['DAILY_SYNC_FINAL_PHASE_RESERVE_SECONDS']
        == OPS002_FINAL_PHASE_RESERVE
    )


def test_the_combined_ingestion_cap_is_the_ops_002_value(daily_step):
    assert (
        daily_step['env']['DAILY_SYNC_INGESTION_BUDGET_SECONDS']
        == OPS002_INGESTION_CAP
    )


def test_the_postgame_command_timeout_is_not_swept_up_in_the_mitigation(public_sync):
    step = _step(public_sync, 'Run direct postgame refresh')
    assert (
        step['env']['POSTGAME_REFRESH_COMMAND_TIMEOUT'] == POSTGAME_COMMAND_TIMEOUT
    )


def test_the_mitigation_floor_holds_at_maximum_observed_upstream(daily_step):
    """The property the four values exist to satisfy, derived from the workflow.

    Read straight out of the reviewed file rather than restated, so editing the
    values without re-deriving the floor fails here instead of in production.
    """
    total = float(daily_step['env']['DAILY_SYNC_TOTAL_BUDGET_SECONDS'])
    reserve = float(daily_step['env']['DAILY_SYNC_FINAL_PHASE_RESERVE_SECONDS'])
    cap = float(daily_step['env']['DAILY_SYNC_INGESTION_BUDGET_SECONDS'])

    pool = min(cap, total - reserve - MAX_OBSERVED_UPSTREAM_SECONDS)
    gamelog_floor = pool * (1 - SHADOW_LANE_SHARE)

    assert pool == 1271.5
    assert gamelog_floor == 953.625
    assert gamelog_floor >= MITIGATION_FLOOR_SECONDS


def test_the_cap_is_a_ceiling_above_the_derived_pool_not_the_operative_limit(
    daily_step,
):
    """A cap BELOW the derived pool would re-create the OPS-002 defect itself.

    The pre-incident 720s cap needed upstream <= 60s to bind and never did, so
    the configuration advertised a budget the code never delivered. The fix is
    not to make the cap bind — it is to put it safely above the pool and report
    the pool separately.
    """
    total = float(daily_step['env']['DAILY_SYNC_TOTAL_BUDGET_SECONDS'])
    reserve = float(daily_step['env']['DAILY_SYNC_FINAL_PHASE_RESERVE_SECONDS'])
    cap = float(daily_step['env']['DAILY_SYNC_INGESTION_BUDGET_SECONDS'])

    assert cap > total - reserve - MAX_OBSERVED_UPSTREAM_SECONDS


def test_the_shell_timeout_exceeds_the_internal_budget_with_cleanup_headroom(
    daily_step,
):
    shell_seconds = _minutes(daily_step['env']['DAILY_SYNC_COMMAND_TIMEOUT']) * 60
    total = float(daily_step['env']['DAILY_SYNC_TOTAL_BUDGET_SECONDS'])

    assert shell_seconds == 2400
    assert shell_seconds > total
    assert shell_seconds - total >= 200


def test_the_job_timeout_exceeds_the_shell_timeout(public_sync, daily_step):
    job_seconds = public_sync['timeout-minutes'] * 60
    shell_seconds = _minutes(daily_step['env']['DAILY_SYNC_COMMAND_TIMEOUT']) * 60

    assert job_seconds == 3600
    assert job_seconds > shell_seconds


def test_the_job_timeout_covers_the_steps_that_must_still_run_after_the_sync(
    public_sync, daily_step,
):
    """The always() ledger and cache proofs are the point of the headroom.

    If the job could expire while the shell timeout was still running, a killed
    sync would take the publication proofs down with it and the run would be
    indistinguishable from an unproven one.
    """
    job_minutes = public_sync['timeout-minutes']
    shell_minutes = _minutes(daily_step['env']['DAILY_SYNC_COMMAND_TIMEOUT'])
    accounted = (
        shell_minutes + TONIGHT_TIMEOUT_MINUTES + APPEARANCE_AUDIT_TIMEOUT_MINUTES
    )

    assert job_minutes >= accounted
    assert job_minutes - accounted >= 5


def test_the_mitigation_did_not_add_a_schedule(workflow):
    assert [entry['cron'] for entry in workflow[True]['schedule']] == [
        DAILY_CRON, MORNING_CRON, POSTGAME_CRON,
    ]


def test_the_mitigation_did_not_add_a_manual_mode(workflow):
    assert workflow[True]['workflow_dispatch']['inputs']['mode']['options'] == [
        'recovery_daily', 'recovery_postgame', 'backfill', 'intraday',
    ]


def test_the_mitigation_did_not_promote_the_lane(daily_step):
    assert daily_step['env'][MODE_ENV] == 'shadow'


def test_no_workflow_lever_can_move_the_lane_to_a_writing_mode(workflow_text):
    """The reviewed source stays the only activation authority.

    A budget change must not become a back door: no input, no repository
    variable, and no expression may supply the mode.
    """
    for forbidden in (
        f'{MODE_ENV}: write',
        f'{MODE_ENV}: authoritative',
        f'{MODE_ENV}: ${{{{',
        f"{MODE_ENV}: '${{{{",
    ):
        assert forbidden not in workflow_text


def test_backfill_remains_off_in_the_daily_lane(workflow_text):
    assert 'GAME_DRIVEN_BACKFILL_ENABLED' not in workflow_text


def test_the_mitigation_values_do_not_leak_into_any_other_job(workflow):
    """Scoped to the daily step, exactly like the shadow mode is.

    Every other step in the file must keep the deployed defaults.
    """
    mitigation_keys = {
        'DAILY_SYNC_TOTAL_BUDGET_SECONDS',
        'DAILY_SYNC_FINAL_PHASE_RESERVE_SECONDS',
        'DAILY_SYNC_INGESTION_BUDGET_SECONDS',
        'DAILY_SYNC_COMMAND_TIMEOUT',
    }
    for job_name, job in workflow['jobs'].items():
        assert not (mitigation_keys & set((job.get('env') or {}))), job_name
        for step in job.get('steps') or []:
            if step.get('name') == 'Run direct daily sync':
                continue
            leaked = mitigation_keys & set((step.get('env') or {}))
            assert not leaked, f'{job_name}/{step.get("name")}: {leaked}'


# The only advisory steps in public-sync are the shadow handoff pair and the Team
# State vNext proof pair, and all four are advisory by the same OPS-001 design: an
# observer artifact must not fail the publication job. The proof pair is written
# after the publication has already committed, so failing the job on it would
# suppress the static delivery that follows and protect nothing. Pinned as an exact
# set so nothing else can quietly join them.
ADVISORY_PUBLIC_SYNC_STEPS = {
    'Prepare game-driven shadow handoff',
    'Upload game-driven shadow handoff',
    'Scan Team State vNext proof for forbidden content',
    'Upload Team State vNext production proof',
}


def test_the_mitigation_did_not_make_a_production_step_advisory(public_sync):
    advisory = {
        step.get('name') for step in public_sync['steps']
        if step.get('continue-on-error')
    }
    assert advisory == ADVISORY_PUBLIC_SYNC_STEPS


@pytest.mark.parametrize('name', [
    'Run direct daily sync',
    'Appearance ledger audit (publish eligibility)',
    'Verify dashboard snapshot cache',
])
def test_a_publication_critical_step_is_never_advisory(public_sync, name):
    step = _step(public_sync, name)
    assert step.get('continue-on-error') in (None, False)


def test_the_mitigation_did_not_add_a_retry_loop(daily_step):
    """Headroom, not repetition.

    A retry inside the step would re-run the whole daily command against the
    same singleton lane and could double the work the incident is about.
    """
    script = daily_step['run']
    assert 'run_due_sync.py --mode daily' in script
    assert script.count('run_due_sync.py --mode daily') == 1
    for forbidden in ('for attempt', 'while true', 'until python', 'retry'):
        assert forbidden not in script.lower()


def test_the_daily_runner_still_fails_closed_on_a_nonzero_exit(daily_step):
    script = daily_step['run']
    assert 'exit "$exit_code"' in script
    assert 'set -euo pipefail' in script
