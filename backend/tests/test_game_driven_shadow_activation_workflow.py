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

DAILY_CRON = '0 10 * * *'
MORNING_CRON = '0 14 * * *'
POSTGAME_CRON = '0 2,4,6 * * *'

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
        'group': 'baseballos-sync',
        'cancel-in-progress': False,
    }


def test_the_daily_command_timeout_is_unchanged(public_sync):
    step = _step(public_sync, 'Run direct daily sync')
    assert step['env']['DAILY_SYNC_COMMAND_TIMEOUT'] == '20m'


def test_the_postgame_command_timeout_is_unchanged(public_sync):
    step = _step(public_sync, 'Run direct postgame refresh')
    assert step['env']['POSTGAME_REFRESH_COMMAND_TIMEOUT'] == '20m'


def test_the_public_sync_job_timeout_is_unchanged(public_sync):
    """Not reduced when the observer moved out.

    The 40 minutes covers the worst case of the step timeouts that remain
    (20m sync + 10m tonight + 5m audit); the activation steps never had their
    own allowance in that budget, so removing them frees nothing to reclaim.
    """
    assert public_sync['timeout-minutes'] == 40


@pytest.mark.parametrize('name', [
    'Appearance ledger audit',
    'Verify dashboard snapshot cache',
    'Refresh schedule and warm Tonight',
    'Run morning slate schedule refresh',
    'Run explicit backfill',
    'Run direct daily sync',
    'Run direct postgame refresh',
    'Upload appearance ledger audit report',
])
def test_an_existing_production_step_is_retained(public_sync, name):
    assert _step(public_sync, name) is not None


def test_the_daily_runner_command_is_unchanged_apart_from_output(public_sync):
    run = _step(public_sync, 'Run direct daily sync')['run']
    assert 'run_daily_sync.py --days-back 7 --source github_actions --public-only' in run


def test_the_postgame_runner_command_is_unchanged_apart_from_output(public_sync):
    run = _step(public_sync, 'Run direct postgame refresh')['run']
    assert 'run_postgame_refresh.py --source github_actions --public-only' in run


def test_the_appearance_ledger_command_is_unchanged(public_sync):
    run = _step(public_sync, 'Appearance ledger audit')['run']
    assert 'appearance_ledger_audit.py --days 10 --deep' in run


@pytest.mark.parametrize('name', [
    'Run direct daily sync',
    'Run direct postgame refresh',
    'Refresh schedule and warm Tonight',
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
    assert "inputs.mode == 'daily'" in condition
    assert f"github.event.schedule == '{DAILY_CRON}'" in condition


def test_manual_postgame_uses_the_same_step(public_sync):
    condition = _step(public_sync, 'Run direct postgame refresh')['if']
    assert "inputs.mode == 'postgame'" in condition
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
    'Refresh schedule and warm Tonight',
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
    assert _invocations(workflow_text, 'run_daily_sync.py') == 1


def test_the_postgame_runner_is_invoked_by_postgame_and_backfill_only(workflow_text):
    # Two: the scheduled/manual postgame cycle, and the explicit backfill that
    # shares the runner with the mode pinned off.
    assert _invocations(workflow_text, 'run_postgame_refresh.py') == 2


def test_no_foundation_3c_workflow_was_recreated():
    for path in (REPO_ROOT / '.github/workflows').glob('*.yml'):
        assert 'foundation-3c' not in path.name.lower()


# The scheduled workflows that already existed. Separating a job must not add
# a third: a new scheduled lane would run outside this workflow's concurrency
# group and could overlap a production sync.
EXISTING_SCHEDULED_WORKFLOWS = (
    'baseballos-intraday-repair.yml',
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
    assert "inputs.mode == 'daily'" in condition
    assert "inputs.mode == 'postgame'" in condition
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


def test_no_forbidden_pattern_list_is_duplicated_in_the_workflow(workflow_text):
    """One scanner, one pattern list.

    The two scans previously carried independent copies of the same list, which
    is a list that can drift silently — the second copy learns about a new
    secret shape only if someone remembers it exists.
    """
    assert 'BASEBALLOS_ADMIN_API_TOKEN|token=' not in workflow_text
    assert workflow_text.count('scan_forbidden_artifact_content.py') == 1


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
    assert "inputs.mode == 'daily'" in condition
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
    assert sorted(workflow['jobs']) == sorted([
        'public-sync', SHADOW_JOB, 'internal-enrichment',
        'static-team-story-preview', 'intraday-audit',
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
