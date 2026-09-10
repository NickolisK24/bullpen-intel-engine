"""Manual postgame publication incident audit — workflow contract.

Requirements 1-30.

The reviewed workflow source is the authority for how this audit can be
invoked. These tests own the properties that make it manual-only, exact-scope,
read-only, and incapable of rerunning, dispatching, repairing, or publishing
anything.
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

JOB = 'incident-audit'
REPOSITORY = 'NickolisK24/bullpen-intel-engine'
CONFIRMATION = 'AUDIT_POSTGAME_PUBLICATION_INCIDENT_30873422601'
INCIDENT_RUN_ID = '30873422601'

# PyYAML parses the unquoted `on:` key as the boolean True. The reviewed source
# is the authority, so the key is read as YAML actually produces it rather than
# the workflow being rewritten to make a test convenient.
ON = True

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


def _downloads(steps):
    return [
        step for step in steps
        if str(step.get('uses', '')).startswith('actions/download-artifact')
    ]


# ── 1-6 Trigger surface ─────────────────────────────────────────────────────

def test_001_workflow_dispatch_only(workflow):
    assert set(workflow[ON]) == {'workflow_dispatch'}


def test_002_no_schedule_trigger(workflow):
    assert 'schedule' not in workflow[ON]


def test_003_no_push_trigger(workflow):
    assert 'push' not in workflow[ON]


def test_004_no_pull_request_trigger(workflow):
    assert 'pull_request' not in workflow[ON]
    assert 'pull_request_target' not in workflow[ON]


def test_005_no_workflow_run_trigger(workflow):
    assert 'workflow_run' not in workflow[ON]


def test_006_no_repository_dispatch_trigger(workflow):
    assert 'repository_dispatch' not in workflow[ON]


# ── 7-12 Authorization ──────────────────────────────────────────────────────

def test_007_repository_is_pinned(job):
    assert f"github.repository == '{REPOSITORY}'" in ' '.join(
        str(job['if']).split()
    )


def test_008_main_only(job):
    assert "github.ref == 'refs/heads/main'" in ' '.join(str(job['if']).split())


def test_009_owner_only(job):
    assert 'github.actor == github.repository_owner' in ' '.join(
        str(job['if']).split()
    )


def test_010_expected_sha_is_required(workflow):
    field = workflow[ON]['workflow_dispatch']['inputs']['expected_head_sha']
    assert field['required'] is True


def test_011_confirmation_is_required(workflow):
    field = workflow[ON]['workflow_dispatch']['inputs']['confirmation']
    assert field['required'] is True


def test_012_confirmation_value_is_exact(steps, workflow):
    guard = _step(steps, 'Refuse an unauthorized invocation')
    assert f'"$INPUT_CONFIRMATION" != "{CONFIRMATION}"' in guard['run']
    described = workflow[ON]['workflow_dispatch']['inputs']['confirmation']
    assert CONFIRMATION in described['description']


# ── 13-15 Shell boundary ────────────────────────────────────────────────────

def test_013_inputs_cross_through_env(steps):
    guard = _step(steps, 'Refuse an unauthorized invocation')
    audit_step = _step(steps, 'Run the read-only incident audit')
    for name, expression in EXPECTED_INPUT_ENV.items():
        assert guard['env'][name] == expression
        assert audit_step['env'][name] == expression


def test_014_no_input_expression_inside_any_run_script(steps):
    offenders = [
        step.get('name') for step in steps
        if 'run' in step and EXPRESSION.search(str(step['run']))
    ]
    assert offenders == []


def test_015_a_hostile_operator_note_stays_inert(steps):
    guard = _step(steps, 'Refuse an unauthorized invocation')
    audit_step = _step(steps, 'Run the read-only incident audit')
    # The note is only ever measured, and only ever passed as a quoted value.
    assert 'wc -c' in guard['run']
    assert 'eval' not in guard['run']
    assert '"$INPUT_OPERATOR_NOTE"' in audit_step['run']
    assert '$INPUT_OPERATOR_NOTE' not in audit_step['run'].replace(
        '"$INPUT_OPERATOR_NOTE"', ''
    )


# ── 16-18 Permissions ───────────────────────────────────────────────────────

def test_016_actions_read_is_granted(workflow):
    assert workflow['permissions']['actions'] == 'read'


def test_017_contents_read_is_granted(workflow):
    assert workflow['permissions']['contents'] == 'read'


def test_018_no_write_permission_anywhere(workflow):
    assert set(workflow['permissions']) == {'contents', 'actions'}
    assert all(value == 'read' for value in workflow['permissions'].values())


# ── 19-20 Concurrency ───────────────────────────────────────────────────────

def test_019_shared_baseballos_sync_concurrency(workflow):
    assert workflow['concurrency']['group'] == 'baseballos-sync'


def test_020_cancel_in_progress_is_false(workflow):
    assert workflow['concurrency']['cancel-in-progress'] is False


# ── 21-26 Runtime environment ───────────────────────────────────────────────

def test_021_auto_sync_is_false(steps):
    assert _step(steps, 'Run the read-only incident audit')['env'][
        'AUTO_SYNC'
    ] == 'false'


def test_022_no_write_mode_is_configured(steps, workflow_text):
    """No step SETS a write mode. The name may appear in a comment explaining
    that it is deliberately unset — a comment configures nothing."""
    for step in steps:
        assert 'GAME_DRIVEN_INGESTION_MODE' not in (step.get('env') or {})
    assert 'MODE_WRITE' not in workflow_text
    assert 'mode: write' not in workflow_text


def test_023_no_authoritative_mode(steps):
    env = _step(steps, 'Run the read-only incident audit')['env']
    assert not any('AUTHORITATIVE' in key.upper() for key in env)


def test_024_no_backfill_mode(steps):
    env = _step(steps, 'Run the read-only incident audit')['env']
    assert not any('BACKFILL' in key.upper() for key in env)


def test_025_no_sync_url(steps, workflow_text):
    """No step RECEIVES a sync URL. The name may appear in a comment saying so."""
    for step in steps:
        assert 'BASEBALLOS_SYNC_URL' not in (step.get('env') or {})
    assert 'secrets.BASEBALLOS_SYNC_URL' not in workflow_text


def test_026_no_publication_token(steps):
    env = _step(steps, 'Run the read-only incident audit')['env']
    assert not any('PUBLICATION' in key.upper() for key in env)
    # ADMIN_API_TOKEN is present only because application startup requires it.
    assert 'ADMIN_API_TOKEN' in env


# ── 27-30 Incident scope and ordering ───────────────────────────────────────

def test_027_every_download_uses_the_exact_incident_run_id(steps):
    downloads = _downloads(steps)
    assert downloads
    for step in downloads:
        assert str(step['with']['run-id']) == INCIDENT_RUN_ID


@pytest.mark.parametrize('artifact', [
    'game-driven-shadow-30873422601',
    'appearance-ledger-audit-30873422601',
    'game-driven-shadow-handoff-30873422601',
])
def test_028_each_artifact_is_requested_by_exact_name(steps, artifact):
    assert any(
        step['with']['name'] == artifact for step in _downloads(steps)
    )


def test_029_artifact_download_precedes_the_database_lock(steps):
    audit_index = _index(steps, 'Run the read-only incident audit')
    for step in _downloads(steps):
        assert steps.index(step) < audit_index
    assert _index(steps, 'Record incident artifact metadata') < audit_index


def test_030_upload_precedes_the_final_gate(steps):
    assert _index(steps, 'Scan the evidence artifact') < _index(
        steps, 'Upload the evidence artifact'
    )
    assert _index(steps, 'Upload the evidence artifact') < _index(
        steps, 'Final audit gate'
    )


# ── Supporting structure ────────────────────────────────────────────────────

def test_the_workflow_is_named_for_the_incident(workflow):
    assert workflow['name'] == 'Manual Postgame Publication Incident Audit'


def test_the_job_is_bounded_by_a_twenty_minute_timeout(job):
    assert job['timeout-minutes'] == 20


def test_the_final_gate_cannot_be_softened(steps):
    gate = _step(steps, 'Final audit gate')
    assert 'continue-on-error' not in gate
    assert gate['run'].lstrip().startswith('set -euo pipefail')
    assert '"1"' in gate['run'] and '"2"' in gate['run']
    assert gate['env']['AUDIT_EXIT_CODE'] == (
        '${{ steps.audit.outputs.exit_code }}'
    )


def test_the_workflow_runs_no_repair_or_publication_command(workflow_text):
    for forbidden in (
        'run_postgame_refresh.py', 'run_daily_sync.py',
        'run_intraday_repair.py', 'build_dashboard_snapshot.py',
        'appearance_ledger_audit.py', 'game_driven_ingestion.py',
        'run_game_driven_noop_qualification.py',
        'run_noop_qualification_candidate_audit.py',
        'gh workflow run', 'gh run rerun', '/rerun', '/dispatches',
    ):
        assert forbidden not in workflow_text
