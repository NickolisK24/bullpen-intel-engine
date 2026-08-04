"""Structure of the manual postgame publication incident audit workflow.

Requirements 89-114.

The reviewed workflow source is the authority for how this audit can be
invoked. These tests own the properties that make it manual-only, exact-scope,
read-only, and incapable of rerunning, dispatching, or publishing anything.

They also own the property that adding it disturbed nothing: the scheduled sync
keeps its triggers, and no migration was introduced.
"""

import re
from pathlib import Path

import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = (
    REPO_ROOT
    / '.github/workflows/manual-postgame-publication-incident-audit.yml'
)
SYNC_WORKFLOW_PATH = REPO_ROOT / '.github/workflows/baseballos-sync.yml'
CANDIDATE_AUDIT_PATH = (
    REPO_ROOT / '.github/workflows/manual-noop-qualification-candidate-audit.yml'
)
MIGRATIONS_DIR = REPO_ROOT / 'backend/migrations/versions'

JOB = 'incident-audit'
REPOSITORY = 'NickolisK24/bullpen-intel-engine'
CONFIRMATION = 'AUDIT_POSTGAME_PUBLICATION_INCIDENT_30873422601'
INCIDENT_RUN_ID = '30873422601'

FORBIDDEN_TRIGGERS = (
    'schedule', 'push', 'pull_request', 'pull_request_target',
    'workflow_run', 'repository_dispatch', 'issue_comment', 'release',
    'workflow_call',
)

EXPECTED_INPUT_ENV = {
    'INPUT_EXPECTED_HEAD_SHA': '${{ inputs.expected_head_sha }}',
    'INPUT_CONFIRMATION': '${{ inputs.confirmation }}',
    'INPUT_OPERATOR_NOTE': '${{ inputs.operator_note }}',
}

EXPRESSION = re.compile(r'\$\{\{')


@pytest.fixture(scope='module')
def workflow_text():
    return WORKFLOW_PATH.read_text(encoding='utf-8')


@pytest.fixture(scope='module')
def workflow(workflow_text):
    return yaml.safe_load(workflow_text)


# PyYAML parses the unquoted `on:` key as the boolean True. The reviewed
# workflow source is the authority, so the key is read as YAML actually
# produces it rather than rewritten to make a test pass.
ON = True


@pytest.fixture(scope='module')
def job(workflow):
    return workflow['jobs'][JOB]


@pytest.fixture(scope='module')
def steps(job):
    return job['steps']


def _step(steps, needle):
    for step in steps:
        if needle.lower() in str(step.get('name', '')).lower():
            return step
    raise AssertionError(f'no step matching {needle!r}')


def _index(steps, needle):
    for position, step in enumerate(steps):
        if needle.lower() in str(step.get('name', '')).lower():
            return position
    raise AssertionError(f'no step matching {needle!r}')


# ── 89-94 Trigger and authorization ─────────────────────────────────────────

def test_089_the_workflow_exists_and_is_named_for_the_incident(workflow):
    assert workflow['name'] == 'Manual Postgame Publication Incident Audit'


def test_090_workflow_dispatch_is_the_only_trigger(workflow):
    assert set(workflow[ON]) == {'workflow_dispatch'}


@pytest.mark.parametrize('trigger', FORBIDDEN_TRIGGERS)
def test_091_no_automatic_trigger_exists(workflow, trigger):
    assert trigger not in workflow[ON]


def test_092_exactly_three_inputs_are_accepted(workflow):
    inputs = workflow[ON]['workflow_dispatch']['inputs']
    assert set(inputs) == {
        'expected_head_sha', 'confirmation', 'operator_note',
    }


def test_093_the_job_gate_requires_dispatch_repository_main_and_owner(job):
    condition = ' '.join(str(job['if']).split())
    assert "github.event_name == 'workflow_dispatch'" in condition
    assert f"github.repository == '{REPOSITORY}'" in condition
    assert "github.ref == 'refs/heads/main'" in condition
    assert 'github.actor == github.repository_owner' in condition


def test_094_the_guard_step_checks_the_exact_confirmation(steps):
    guard = _step(steps, 'Refuse an unauthorized invocation')
    assert CONFIRMATION in guard['run']
    assert '^[0-9a-f]{40}$' in guard['run']


# ── 95-99 Concurrency, permissions, timeout ─────────────────────────────────

def test_095_the_audit_shares_the_production_sync_concurrency_lane(workflow):
    assert workflow['concurrency']['group'] == 'baseballos-sync'


def test_096_a_running_production_writer_is_never_cancelled(workflow):
    assert workflow['concurrency']['cancel-in-progress'] is False


def test_097_permissions_are_read_only_and_only_contents_and_actions(workflow):
    assert workflow['permissions'] == {'contents': 'read', 'actions': 'read'}


def test_098_no_permission_scope_is_granted_write(workflow):
    assert all(
        value == 'read' for value in workflow['permissions'].values()
    )


def test_099_the_job_is_bounded_by_a_twenty_minute_timeout(job):
    assert job['timeout-minutes'] == 20


# ── 100-104 Shell boundary ──────────────────────────────────────────────────

def test_100_no_run_script_contains_a_github_expression(steps):
    offenders = [
        step.get('name') for step in steps
        if 'run' in step and EXPRESSION.search(str(step['run']))
    ]
    assert offenders == []


def test_101_every_operator_input_crosses_through_step_env(steps):
    guard = _step(steps, 'Refuse an unauthorized invocation')
    for name, expression in EXPECTED_INPUT_ENV.items():
        assert guard['env'][name] == expression


def test_102_the_audit_step_receives_inputs_through_env_only(steps):
    step = _step(steps, 'Run the read-only incident audit')
    for name, expression in EXPECTED_INPUT_ENV.items():
        assert step['env'][name] == expression
    assert not EXPRESSION.search(step['run'])


def test_103_inputs_are_read_as_quoted_shell_variables(steps):
    step = _step(steps, 'Run the read-only incident audit')
    assert '"$INPUT_EXPECTED_HEAD_SHA"' in step['run']
    assert '"$INPUT_CONFIRMATION"' in step['run']
    assert '"$INPUT_OPERATOR_NOTE"' in step['run']


def test_104_the_operator_note_is_only_ever_measured_never_interpreted(steps):
    guard = _step(steps, 'Refuse an unauthorized invocation')
    # The only thing the guard does with the note is count its characters.
    assert 'wc -c' in guard['run']
    assert 'eval' not in guard['run']


# ── 105-109 Incident evidence is fetched by exact run id and name ───────────

@pytest.mark.parametrize('artifact', [
    'game-driven-shadow-30873422601',
    'appearance-ledger-audit-30873422601',
    'game-driven-shadow-handoff-30873422601',
])
def test_105_each_incident_artifact_is_requested_by_exact_name(
    steps, artifact,
):
    downloads = [
        step for step in steps
        if str(step.get('uses', '')).startswith('actions/download-artifact')
    ]
    assert any(step['with']['name'] == artifact for step in downloads)


def test_106_every_download_targets_the_incident_run_id(steps):
    downloads = [
        step for step in steps
        if str(step.get('uses', '')).startswith('actions/download-artifact')
    ]
    assert downloads
    for step in downloads:
        assert str(step['with']['run-id']) == INCIDENT_RUN_ID


def test_107_a_missing_artifact_never_aborts_before_the_evidence_document(
    steps,
):
    downloads = [
        step for step in steps
        if str(step.get('uses', '')).startswith('actions/download-artifact')
    ]
    for step in downloads:
        assert step.get('continue-on-error') is True


def test_108_the_workflow_never_reruns_or_dispatches_anything(workflow_text):
    """No command in the file can restart the incident run or start another
    workflow. Matched against COMMANDS, not prose: the header legitimately
    describes ``workflow run 30873422601`` as the subject of the audit."""
    lowered = workflow_text.lower()
    for forbidden in (
        'gh workflow run', 'gh run rerun', 'gh api', 'actions/rerun',
        '/rerun', 'actions_run_trigger', 'curl -x post',
        '/actions/workflows/', '/dispatches',
    ):
        assert forbidden not in lowered


def test_109_the_workflow_runs_no_sync_repair_or_publication_command(
    workflow_text,
):
    for forbidden in (
        'run_postgame_refresh.py', 'run_daily_sync.py',
        'run_intraday_repair.py', 'build_dashboard_snapshot.py',
        'appearance_ledger_audit.py', 'game_driven_ingestion.py',
        'run_game_driven_noop_qualification.py',
        'run_noop_qualification_candidate_audit.py',
    ):
        assert forbidden not in workflow_text


# ── 110-114 Evidence survives, and the gate still fails ─────────────────────

def test_110_the_artifact_is_scanned_before_it_is_uploaded(steps):
    assert _index(steps, 'Scan the evidence artifact') < _index(
        steps, 'Upload the evidence artifact'
    )


def test_111_the_artifact_uploads_before_the_final_gate(steps):
    assert _index(steps, 'Upload the evidence artifact') < _index(
        steps, 'Final audit gate'
    )


def test_112_the_upload_only_happens_when_the_scan_passed(steps):
    upload = _step(steps, 'Upload the evidence artifact')
    assert upload['if'] == "${{ steps.scan.outcome == 'success' }}"
    assert upload['with']['retention-days'] == 30
    assert upload['with']['if-no-files-found'] == 'error'


def test_113_the_final_gate_cannot_be_softened(steps):
    gate = _step(steps, 'Final audit gate')
    assert 'continue-on-error' not in gate
    assert gate['run'].lstrip().startswith('set -euo pipefail')


def test_114_the_final_gate_preserves_failed_and_unproven(steps):
    gate = _step(steps, 'Final audit gate')
    assert 'FAILED' in gate['run']
    assert 'UNPROVEN' in gate['run']
    # Exit code 1 (FAILED) and 2 (UNPROVEN) both fail the job explicitly.
    assert '"1"' in gate['run'] and '"2"' in gate['run']
    assert gate['env']['AUDIT_EXIT_CODE'] == (
        '${{ steps.audit.outputs.exit_code }}'
    )


# ── Adding the audit disturbed nothing ──────────────────────────────────────

def test_the_scheduled_sync_keeps_its_own_triggers():
    sync = yaml.safe_load(SYNC_WORKFLOW_PATH.read_text(encoding='utf-8'))
    assert 'schedule' in sync[ON]
    assert 'workflow_dispatch' in sync[ON]


def test_the_incident_audit_is_not_in_the_scheduled_set():
    scheduled = sorted(
        path.name
        for path in (REPO_ROOT / '.github/workflows').glob('*.yml')
        if 'schedule' in (
            (yaml.safe_load(path.read_text(encoding='utf-8')) or {}).get(ON)
            or {}
        )
    )
    assert WORKFLOW_PATH.name not in scheduled


def test_the_candidate_audit_workflow_is_unchanged_in_shape():
    candidate = yaml.safe_load(
        CANDIDATE_AUDIT_PATH.read_text(encoding='utf-8')
    )
    assert set(candidate[ON]) == {'workflow_dispatch'}
    assert candidate['concurrency']['cancel-in-progress'] is False


def test_no_migration_was_added_for_this_audit():
    heads = sorted(path.name for path in MIGRATIONS_DIR.glob('*.py'))
    for name in heads:
        assert 'incident' not in name.lower()
