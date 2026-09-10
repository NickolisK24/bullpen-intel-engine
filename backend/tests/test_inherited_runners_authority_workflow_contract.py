"""Structure of the manual inherited-runners authority diagnostic workflow.

The reviewed workflow source is the authority for how this diagnostic can be
invoked. These tests own the properties that make it manual-only, read-only,
hard-pinned to one appearance, and incapable of writing or dispatching
anything.

The property that matters most here is the PINNING. Run #491's discrepancy is
one row; a workflow that could be pointed at any row from a phone would be a
production query tool with a diagnostic's name on it. game_pk, pitcher_mlb_id
and field are literals in the workflow script, and there is no input of any
kind through which an operator could vary them.

They also own the property that adding it disturbed nothing: the diagnostic
itself, the canonical planner's contract versions, and the approved fallback
set are all unchanged.
"""

import re
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = (
    REPO_ROOT / '.github/workflows/inherited-runners-authority-diagnostic.yml'
)
DIAGNOSTIC_PATH = (
    REPO_ROOT / 'backend/scripts/inspect_gamelog_field_authority.py'
)

JOB = 'inherited-runners-authority-diagnostic'
REPOSITORY = 'NickolisK24/bullpen-intel-engine'

GAME_PK = '824969'
PITCHER_MLB_ID = '656240'
FIELD = 'inherited_runners'
ARTIFACT_PATH = (
    'artifacts/field-authority/inherited-runners-824969-656240.json'
)

FORBIDDEN_TRIGGERS = (
    'schedule', 'push', 'pull_request', 'pull_request_target',
    'workflow_run', 'repository_dispatch', 'issue_comment', 'release',
    'workflow_call',
)


@pytest.fixture(scope='module')
def workflow_text():
    return WORKFLOW_PATH.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def workflow_code(workflow_text):
    """The workflow with full-line comments removed.

    Prose is allowed — required, even — to say which production actions this
    workflow does NOT take. Only executable lines are held to the ban.
    """
    return '\n'.join(
        line for line in workflow_text.splitlines()
        if not line.lstrip().startswith('#')
    )


@pytest.fixture(scope='module')
def workflow(workflow_text):
    return yaml.safe_load(workflow_text)


@pytest.fixture(scope='module')
def triggers(workflow):
    # PyYAML resolves the `on:` key to the boolean True.
    return workflow[True]


@pytest.fixture(scope='module')
def job(workflow):
    return workflow['jobs'][JOB]


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
    assert workflow['name'] == 'Inherited Runners Authority Diagnostic'


def test_workflow_dispatch_is_the_only_trigger(triggers):
    assert list(triggers) == ['workflow_dispatch']


@pytest.mark.parametrize('trigger', FORBIDDEN_TRIGGERS)
def test_no_automatic_trigger_exists(triggers, trigger):
    assert trigger not in triggers


def test_no_cron_expression_appears(workflow_text):
    assert 'cron' not in workflow_text.lower()


def test_only_one_job_exists(workflow):
    assert list(workflow['jobs']) == [JOB]


# ── The target cannot be varied ─────────────────────────────────────────────


def test_the_dispatch_declares_no_inputs_at_all(triggers):
    """No input means nothing to point elsewhere, and nothing to type on a
    phone. It also means no operator string crosses the shell boundary."""
    assert triggers['workflow_dispatch'] is None


@pytest.mark.parametrize('name', ['game_pk', 'pitcher_mlb_id', 'field'])
def test_no_editable_target_input_exists(workflow_text, name):
    assert f'{name}:\n' not in workflow_text
    assert f'inputs.{name}' not in workflow_text


def test_the_workflow_references_no_dispatch_input_anywhere(workflow_text):
    assert 'inputs.' not in workflow_text
    assert 'github.event.inputs' not in workflow_text


def test_the_diagnostic_command_pins_all_three_target_values(job):
    script = _step(job, 'Run the read-only field-authority diagnostic')['run']
    assert 'python backend/scripts/inspect_gamelog_field_authority.py' in script
    assert f'--game-pk {GAME_PK}' in script
    assert f'--pitcher-mlb-id {PITCHER_MLB_ID}' in script
    assert f'--field {FIELD}' in script
    assert f'--output {ARTIFACT_PATH}' in script


def test_the_pinned_values_are_literals_not_variables(job):
    """A `$VAR` or `${{ }}` in any of the three positions would reopen exactly
    what the pinning closes."""
    script = _step(job, 'Run the read-only field-authority diagnostic')['run']
    for flag in ('--game-pk', '--pitcher-mlb-id', '--field'):
        match = re.search(re.escape(flag) + r'\s+(\S+)', script)
        assert match, flag
        argument = match.group(1)
        assert '$' not in argument, flag
        assert '{' not in argument, flag


def test_no_other_game_or_pitcher_is_named_in_the_workflow(workflow_text):
    identifiers = set(re.findall(r'\b\d{6}\b', workflow_text))
    assert identifiers <= {GAME_PK, PITCHER_MLB_ID}


def test_the_diagnostic_accepts_the_pinned_field(job):
    """The workflow and the tool must agree, or the run fails at argparse."""
    from scripts import inspect_gamelog_field_authority as audit

    assert FIELD in audit.REPORT_PROFILES


# ── Authorization and bounds ────────────────────────────────────────────────


def test_the_job_is_gated_on_every_authorization_condition(job):
    condition = ' '.join(str(job['if']).split())
    assert "github.event_name == 'workflow_dispatch'" in condition
    assert f"github.repository == '{REPOSITORY}'" in condition
    assert "github.ref == 'refs/heads/main'" in condition
    assert 'github.actor == github.repository_owner' in condition


def test_the_preflight_refuses_a_foreign_repository_or_ref(job):
    guard = _step(job, 'Refuse an unauthorized invocation')['run']
    assert f'"$RESOLVED_REPOSITORY" != "{REPOSITORY}"' in guard
    assert '"$RESOLVED_REF" != "refs/heads/main"' in guard


@pytest.mark.parametrize('variable', [
    'SECRET_DATABASE_URL', 'SECRET_KEY_PRESENT', 'SECRET_ADMIN_TOKEN',
])
def test_every_required_secret_is_proven_present_before_any_session(
    job, variable,
):
    guard = _step(job, 'Refuse an unauthorized invocation')['run']
    assert f'-z "${{{variable}:-}}"' in guard


def test_it_shares_the_production_sync_concurrency_lane(workflow):
    assert workflow['concurrency']['group'] == 'baseballos-sync'


def test_cancel_in_progress_is_false(workflow):
    assert workflow['concurrency']['cancel-in-progress'] is False


def test_permissions_are_read_only(workflow):
    assert workflow['permissions'] == {'contents': 'read'}


def test_the_job_is_bounded(job):
    assert job['timeout-minutes'] <= 20


def test_python_is_pinned_to_the_canonical_production_version(job):
    setup = _step(job, 'Set up Python')
    assert setup['with']['python-version'] == '3.11'


def test_dependencies_use_the_established_install_pattern(job):
    install = _step(job, 'Install backend dependencies')['run']
    assert 'pip install -r backend/requirements.txt' in install


# ── Read-only posture ───────────────────────────────────────────────────────


def test_auto_sync_is_disabled(job):
    env = _step(job, 'Run the read-only field-authority diagnostic')['env']
    assert env['AUTO_SYNC'] == 'false'


def test_the_game_driven_lane_is_pinned_off(job):
    env = _step(job, 'Run the read-only field-authority diagnostic')['env']
    assert env['GAME_DRIVEN_INGESTION_MODE'] == 'off'


def test_no_step_sets_a_write_capable_ingestion_mode(workflow_text):
    for line in workflow_text.splitlines():
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        if 'GAME_DRIVEN_INGESTION_MODE:' in stripped:
            assert stripped.endswith("'off'"), stripped


def test_the_workflow_invokes_no_production_writer(workflow_code):
    for forbidden in (
        'run_daily_sync.py', 'run_postgame_refresh.py',
        'run_tonight_refresh.py', 'refresh_slate_schedule.py',
        'game_driven_ingestion.py', 'build_dashboard_snapshot.py',
        'flask db upgrade', 'alembic upgrade',
        # `backfill_` rather than `backfill`: the summary and the gate say in
        # prose that no backfill ran, which is the opposite of invoking one.
        # Every backfill script in this repository is named `backfill_*.py`.
        'backfill_', 'warm_cache', 'generate_coin_story_corpus.py',
    ):
        assert forbidden not in workflow_code


def test_the_workflow_cannot_dispatch_another_workflow(workflow_code):
    lowered = workflow_code.lower()
    for forbidden in ('gh workflow run', 'actions/github-script', 'workflow_call'):
        assert forbidden not in lowered


def test_it_runs_exactly_one_python_entry_point(job):
    """One diagnostic, one scanner, one summary renderer — and nothing else
    that reaches the application or the database."""
    invoked = set()
    for step in _run_steps(job):
        invoked.update(re.findall(r'python\s+(\S+\.py)', step['run']))
    assert invoked == {
        'backend/scripts/inspect_gamelog_field_authority.py',
        'backend/scripts/scan_forbidden_artifact_content.py',
    }


def test_no_publication_or_sync_url_secret_is_exposed(job):
    for step in _steps(job):
        for value in (step.get('env') or {}).values():
            assert 'BASEBALLOS_SYNC_URL' not in str(value)
            assert 'PUBLICATION' not in str(value).upper()


def test_the_admin_token_is_present_only_with_its_startup_justification(
    workflow_text, job,
):
    """config.py makes booting against production impossible without it.

    APP_ENV != production refuses a non-local DATABASE_URL; APP_ENV=production
    refuses to boot without ADMIN_API_TOKEN. The token is a startup
    requirement, not a diagnostic capability — and the workflow must say so
    rather than carrying it silently.
    """
    env = _step(job, 'Run the read-only field-authority diagnostic')['env']
    assert env['ADMIN_API_TOKEN'] == '${{ secrets.BASEBALLOS_ADMIN_API_TOKEN }}'
    assert 'APPLICATION STARTUP ONLY' in workflow_text
    assert 'config.py:231' in workflow_text


def test_the_production_database_secret_reuses_the_established_name(job):
    env = _step(job, 'Run the read-only field-authority diagnostic')['env']
    assert env['DATABASE_URL'] == '${{ secrets.DATABASE_URL }}'
    assert env['SECRET_KEY'] == '${{ secrets.SECRET_KEY }}'
    assert env['APP_ENV'] == 'production'


def test_no_secret_value_is_ever_echoed(job):
    for step in _run_steps(job):
        script = step['run']
        for secret in ('DATABASE_URL', 'SECRET_KEY', 'ADMIN_API_TOKEN'):
            for line in script.splitlines():
                stripped = line.strip()
                if stripped.startswith('#') or 'echo' not in stripped:
                    continue
                assert f'${secret}' not in stripped, (step.get('name'), line)


# ── Shell boundary ──────────────────────────────────────────────────────────


def test_no_github_expression_appears_inside_any_run_script(job):
    for step in _run_steps(job):
        assert '${{' not in step['run'], step.get('name')


# ── Artifact handling ───────────────────────────────────────────────────────


def test_a_stale_checked_out_artifact_is_cleared_before_the_run(job):
    """The artifact path is committed. Without this, a diagnostic that died
    before writing would upload an earlier run's evidence under this run's id.
    """
    steps = [step.get('name') for step in _steps(job)]
    clear = _step(job, 'Clear the checked-out artifact')
    assert f'rm -f {ARTIFACT_PATH}' in clear['run']
    assert steps.index(clear['name']) < steps.index(
        _step(job, 'Run the read-only field-authority diagnostic')['name']
    )


def test_the_artifact_upload_always_runs(job):
    upload = _step(job, 'Upload the diagnostic artifact')
    assert upload['if'] == '${{ always() }}'


def test_the_artifact_is_named_per_run_and_retained_for_thirty_days(job):
    upload = _step(job, 'Upload the diagnostic artifact')
    assert upload['uses'].startswith('actions/upload-artifact@')
    with_block = upload['with']
    assert with_block['name'] == (
        'inherited-runners-authority-${{ github.run_id }}'
    )
    assert with_block['path'] == ARTIFACT_PATH
    assert with_block['retention-days'] >= 30
    assert with_block['if-no-files-found'] == 'error'


def test_the_artifact_is_scanned_for_forbidden_content_before_upload(job):
    steps = [step.get('name') for step in _steps(job)]
    scan = _step(job, 'Scan the diagnostic artifact')
    assert '--quarantine' in scan['run']
    assert steps.index(scan['name']) < steps.index(
        _step(job, 'Upload the diagnostic artifact')['name']
    )


# ── The result is preserved, never laundered ────────────────────────────────


def test_the_final_gate_is_not_allowed_to_be_skipped_or_ignored(job):
    gate = _step(job, 'Final diagnostic gate')
    assert gate.get('continue-on-error') is None
    assert gate['if'] == '${{ always() }}'
    assert _steps(job)[-1] is gate


@pytest.mark.parametrize('exit_code', ['1', '2'])
def test_a_non_zero_diagnostic_result_fails_the_workflow(job, exit_code):
    gate = _step(job, 'Final diagnostic gate')['run']
    assert f'{exit_code})' in gate
    # Each non-zero branch ends in a failure, never a bare message.
    branch = gate.split(f'{exit_code})', 1)[1].split(';;', 1)[0]
    assert 'exit 1' in branch


def test_only_a_zero_exit_reaches_the_success_message(job):
    gate = _step(job, 'Final diagnostic gate')['run']
    assert 'Field-authority diagnostic completed read-only.' in gate
    success = gate.split('esac', 1)[1]
    assert 'exit 1' not in success


def test_an_unsafe_or_unuploaded_artifact_fails_the_workflow(job):
    gate = _step(job, 'Final diagnostic gate')['run']
    assert '"$SCAN_OUTCOME" != "success"' in gate
    assert '"$UPLOAD_OUTCOME" != "success"' in gate


def test_the_diagnostic_step_records_its_exit_code_for_the_gate(job):
    script = _step(job, 'Run the read-only field-authority diagnostic')['run']
    assert 'echo "exit_code=$exit_code" >> "$GITHUB_OUTPUT"' in script
    assert 'exit "$exit_code"' in script


# ── Job summary ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize('claim', [
    'READ-ONLY',
    '824969',
    '656240',
    'inherited_runners',
    ARTIFACT_PATH,
    'diagnostic exit code',
    'Automated writes remain prohibited',
    'publication authority',
])
def test_the_step_summary_states_every_required_fact(job, claim):
    summary = _step(job, 'Append the diagnostic summary')['run']
    assert claim in summary


def test_the_step_summary_always_runs(job):
    assert _step(job, 'Append the diagnostic summary')['if'] == '${{ always() }}'


def test_the_step_summary_prints_no_secret(job):
    summary = _step(job, 'Append the diagnostic summary')['run']
    for secret in ('DATABASE_URL', 'SECRET_KEY', 'ADMIN_API_TOKEN'):
        assert secret not in summary


def test_the_step_summary_reports_the_read_only_proof(job):
    summary = _step(job, 'Append the diagnostic summary')['run']
    for key in (
        'read_only_transaction', 'write_probe_refused',
        'database_writes_performed', 'row_fingerprint_before',
        'row_fingerprint_after', 'row_unchanged',
    ):
        assert key in summary


# ── Adding the workflow disturbed nothing ───────────────────────────────────


def test_the_diagnostic_itself_was_not_weakened(job):
    """The workflow supplies an environment; it must not pass a flag that
    relaxes the tool, because no such flag exists and none may be invented."""
    script = _step(job, 'Run the read-only field-authority diagnostic')['run']
    for forbidden in ('--allow-write', '--no-probe', '--skip', '--force'):
        assert forbidden not in script


def test_the_approved_fallback_set_is_still_one_member():
    from services import gamelog_source_authority as authority

    assert authority.APPROVED_FALLBACK_FIELDS == ('balls',)


@pytest.mark.parametrize('version,expected', [
    ('RECONCILIATION_PLAN_VERSION', '3'),
    ('PARITY_CONTRACT_VERSION', '4'),
    ('INNINGS_SEMANTICS_VERSION', '2'),
    ('COMPLETE_PLAN_VERSION', '1'),
])
def test_no_reconciliation_contract_version_moved(version, expected):
    from services import game_log_reconciliation as reconciliation

    assert getattr(reconciliation, version) == expected


def test_the_diagnostic_source_is_unchanged_by_this_work():
    """The workflow calls the tool as merged. If a future change to the tool
    is needed to make the workflow run, it must be a reviewed change to the
    tool — not a silent one made to satisfy a runner."""
    text = DIAGNOSTIC_PATH.read_text(encoding='utf-8')
    assert "os.environ['AUTO_SYNC'] = 'false'" in text
    assert "os.environ['GAME_DRIVEN_INGESTION_MODE'] = 'off'" in text
    assert 'SET TRANSACTION READ ONLY' in text
    assert 'db.session.rollback()' in text
    for forbidden in ('db.session.commit()', 'db.session.add('):
        assert forbidden not in text
