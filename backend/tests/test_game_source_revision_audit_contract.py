"""Game 824487 source-revision audit — workflow and result contract.

Requirements 16-26 and 99-105.

The reviewed workflow source is the authority for how this audit can be
invoked; the reducer is the authority for what its outcome means. These tests
own the properties that make the package manual-only, exact-scope, read-only,
and incapable of rerunning, dispatching, repairing, or publishing anything —
and the property that keeps FAILED reserved for a violation of the audit's own
contract rather than for a platform defect it successfully discovered.
"""

import re
from pathlib import Path

import pytest
import yaml

from services import game_source_revision_audit as audit


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_PATH = (
    REPO_ROOT / '.github/workflows/manual-game-824487-source-revision-audit.yml'
)

JOB = 'source-revision-audit'
REPOSITORY = 'NickolisK24/bullpen-intel-engine'
CONFIRMATION = 'AUDIT_GAME_824487_SOURCE_REVISION_30999087370'

# PyYAML parses the unquoted `on:` key as the boolean True. The reviewed source
# is the authority, so the key is read as YAML actually produces it rather than
# the workflow being rewritten to make a test convenient.
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


def _command_lines(script):
    """Shell lines that INVOKE something, with prose and heredocs removed.

    Prose is not a command. A gate that prints "this audit does not repair game
    824487" must not fail a check meant to catch a step that RUNS a repair, and
    an inline Python heredoc that renders a summary is not a shell invocation
    either. Both are excluded here and covered by their own checks below.
    """
    lines = []
    in_heredoc = False
    for raw in str(script or '').splitlines():
        line = raw.strip()
        if line.startswith("python - <<'PY'"):
            in_heredoc = True
            continue
        if in_heredoc:
            if line == 'PY':
                in_heredoc = False
            continue
        if not line or line.startswith('#'):
            continue
        if line.startswith(('echo ', 'echo"', 'printf ')):
            continue
        lines.append(line)
    return lines


def _executable_surface(steps):
    """Everything the runner will actually EXECUTE, and nothing it merely says."""
    parts = []
    for step in steps:
        parts.extend(_command_lines(step.get('run')))
        if step.get('uses'):
            parts.append(str(step['uses']))
    return '\n'.join(parts)


def _heredocs(steps):
    """The inline Python bodies, so they get checked rather than skipped."""
    bodies = []
    for step in steps:
        current = None
        for raw in str(step.get('run') or '').splitlines():
            line = raw.strip()
            if line.startswith("python - <<'PY'"):
                current = []
                continue
            if current is not None:
                if line == 'PY':
                    bodies.append('\n'.join(current))
                    current = None
                    continue
                current.append(raw)
    return bodies


# ── 16-20. workflow_dispatch is the only trigger ────────────────────────────

def test_the_workflow_exists_and_is_named_for_its_exact_scope(workflow):
    assert workflow['name'] == 'Manual Game 824487 Source Revision Audit'


def test_workflow_dispatch_is_the_only_trigger(workflow):
    assert list(workflow[ON]) == ['workflow_dispatch']


@pytest.mark.parametrize('trigger', [
    'schedule', 'push', 'pull_request', 'workflow_run', 'repository_dispatch',
    'workflow_call', 'issue_comment',
])
def test_no_automatic_trigger_is_declared(workflow, trigger):
    assert trigger not in workflow[ON]


def test_no_step_chains_another_workflow(steps):
    executable = _executable_surface(steps)
    for forbidden in (
        'actions/github-script', 'gh workflow run', 'workflow_dispatch.yml',
        '/dispatches', 'gh api', 'benc-uk/workflow-dispatch',
    ):
        assert forbidden not in executable


# ── 21-22. Exact confirmation and exact main SHA ────────────────────────────

def test_both_required_manual_inputs_are_declared(workflow):
    inputs = workflow[ON]['workflow_dispatch']['inputs']
    assert inputs['expected_main_sha']['required'] is True
    assert inputs['confirmation']['required'] is True


def test_the_exact_confirmation_string_is_enforced_in_the_gate(workflow_text):
    assert CONFIRMATION == audit.CONFIRMATION
    assert f'!= "{CONFIRMATION}"' in workflow_text


def test_the_expected_main_sha_must_equal_the_resolved_commit(workflow_text):
    assert '^[0-9a-f]{40}$' in workflow_text
    assert '"$INPUT_EXPECTED_MAIN_SHA" != "$RESOLVED_SHA"' in workflow_text


def test_the_repository_and_ref_are_refused_before_anything_else(
    steps, workflow_text,
):
    guard = _index(steps, 'Refuse an unauthorized invocation')
    assert guard == 0
    assert '"$RESOLVED_REPOSITORY" != "NickolisK24/bullpen-intel-engine"' in (
        workflow_text
    )
    assert '"$RESOLVED_REF" != "refs/heads/main"' in workflow_text


def test_every_required_secret_is_refused_when_absent(workflow_text):
    for variable in (
        'SECRET_DATABASE_URL', 'SECRET_KEY_PRESENT', 'SECRET_ADMIN_TOKEN',
    ):
        assert f'if [ -z "${{{variable}:-}}" ]; then' in workflow_text


def test_the_job_condition_repeats_every_authorization_precondition(job):
    condition = str(job['if'])
    assert "github.event_name == 'workflow_dispatch'" in condition
    assert f"github.repository == '{REPOSITORY}'" in condition
    assert "github.ref == 'refs/heads/main'" in condition
    assert 'github.actor == github.repository_owner' in condition


def test_the_refusal_gate_runs_before_any_download_or_database_step(steps):
    guard = _index(steps, 'Refuse an unauthorized invocation')
    for needle in ('Download the prior', 'Download the failed', 'Run the read-only'):
        assert guard < _index(steps, needle)


# ── 23-25. Least privilege and full history ─────────────────────────────────

def test_permissions_are_read_only_and_nothing_more(workflow):
    assert workflow['permissions'] == {'contents': 'read', 'actions': 'read'}


def test_no_job_grants_write_to_any_scope(workflow):
    for entry in workflow['jobs'].values():
        for value in (entry.get('permissions') or {}).values():
            assert value != 'write'


def test_checkout_uses_full_history(steps):
    checkout = _step(steps, 'Check out')
    assert checkout['with']['fetch-depth'] == 0


def test_the_job_is_bounded_by_a_timeout(job):
    assert isinstance(job['timeout-minutes'], int)
    assert 0 < job['timeout-minutes'] <= 30


def test_the_audit_shares_the_production_sync_concurrency_lane(workflow):
    assert workflow['concurrency']['group'] == 'baseballos-sync'
    assert workflow['concurrency']['cancel-in-progress'] is False


# ── 26. The workflow runs nothing that could mutate production ──────────────

@pytest.mark.parametrize('forbidden', [
    'run_daily_sync.py',
    'game_driven_ingestion.py',
    'run_game_driven_noop_qualification',
    'recalculate_fatigue.py',
    'seed.py',
    'alembic',
    'flask db',
    'publish',
    'backfill',
    'repair',
    'rollback',
    'intraday',
    'snapshot',
])
def test_the_workflow_invokes_no_sync_repair_backfill_or_publication_script(
    steps, forbidden,
):
    assert forbidden not in _executable_surface(steps)


def test_the_only_python_entrypoints_are_the_audit_and_the_scanner(steps):
    invoked = set(re.findall(
        r'python (?:-u )?(\S+\.py)', _executable_surface(steps),
    ))
    assert invoked == {
        'scripts/run_game_source_revision_audit.py',
        'backend/scripts/scan_forbidden_artifact_content.py',
    }


def test_the_inline_python_bodies_shell_out_to_nothing_and_write_nowhere(
    steps,
):
    """The heredocs are excluded from the command scan, so they get their own.

    One reads artifact metadata over HTTPS and writes it beside the evidence;
    the other renders the job summary. Neither may spawn a process, POST, or
    reach a production endpoint.
    """
    bodies = _heredocs(steps)
    assert bodies
    for body in bodies:
        for forbidden in (
            'subprocess', 'os.system', 'popen', 'eval(', 'exec(',
            "method='POST'", 'method="POST"', 'DELETE', 'PATCH',
            'DATABASE_URL', 'ADMIN_API_TOKEN',
        ):
            assert forbidden not in body


def test_the_deployed_shadow_and_no_auto_sync_posture_is_asserted(steps):
    env = _step(steps, 'Run the read-only source-revision audit')['env']
    assert env['APP_ENV'] == 'production'
    assert env['AUTO_SYNC'] == 'false'
    assert env['GAME_DRIVEN_INGESTION_MODE'] == 'shadow'
    assert 'BASEBALLOS_SYNC_URL' not in env


def test_no_run_script_interpolates_a_github_expression(steps):
    """Operator input crosses into bash through env:, never through `${{ }}`.

    A `${{ }}` expression is substituted into the script TEXT before bash
    parses it, so an expression holding operator input becomes shell code in a
    step that carries production credentials.
    """
    for step in steps:
        script = str(step.get('run') or '')
        assert not EXPRESSION.search(script), step.get('name')


# ── Artifact acquisition contract ───────────────────────────────────────────

def test_both_artifacts_are_downloaded_by_exact_run_id_and_exact_name(steps):
    downloads = [
        step for step in steps
        if str(step.get('uses', '')).startswith('actions/download-artifact')
    ]
    assert len(downloads) == 2
    addressed = {
        (str(step['with']['run-id']), step['with']['name'])
        for step in downloads
    }
    assert addressed == {
        (audit.PRIOR_RUN_ID, f'game-driven-shadow-{audit.PRIOR_RUN_ID}'),
        (audit.LATER_RUN_ID, f'game-driven-shadow-{audit.LATER_RUN_ID}'),
    }


def test_both_downloads_precede_the_audit_so_no_lock_is_held_while_fetching(
    steps,
):
    audit_index = _index(steps, 'Run the read-only source-revision audit')
    for needle in ('Download the prior', 'Download the failed'):
        assert _index(steps, needle) < audit_index


def test_a_failed_download_never_kills_the_run_before_a_document_exists(steps):
    for step in steps:
        if str(step.get('uses', '')).startswith('actions/download-artifact'):
            assert step.get('continue-on-error') is True


# ── Upload, scan, and gate ordering ─────────────────────────────────────────

def test_the_uploaded_artifact_is_named_and_retained_as_specified(steps):
    upload = _step(steps, 'Upload the evidence artifact')
    assert upload['with']['name'] == (
        'game-824487-source-revision-audit-${{ github.run_id }}'
    )
    assert upload['with']['retention-days'] == 90
    assert upload['with']['if-no-files-found'] == 'error'


def test_the_secret_scanner_runs_before_upload_and_gates_it(steps):
    scan = _index(steps, 'Scan the evidence artifact')
    upload = _index(steps, 'Upload the evidence artifact')
    assert scan < upload
    assert _step(steps, 'Upload the evidence artifact')['if'] == (
        "${{ steps.scan.outcome == 'success' }}"
    )


def test_a_scanner_failure_fails_the_workflow(workflow_text):
    assert 'UNPROVEN: the evidence artifact could not be proven safe.' in (
        workflow_text
    )
    gate = workflow_text.split('Final audit gate', 1)[1]
    assert 'if [ "$SCAN_OUTCOME" != "success" ]; then' in gate
    assert 'exit 1' in gate


def test_the_final_gate_preserves_failed_and_unproven(steps, workflow_text):
    gate = _step(steps, 'Final audit gate')
    assert 'continue-on-error' not in gate
    body = str(gate['run'])
    assert 'AUDIT_EXIT_CODE:-}" = "1"' in body
    assert 'AUDIT_EXIT_CODE:-}" = "2"' in body
    assert _index(steps, 'Final audit gate') == len(steps) - 1


def _echoed_message(script):
    """What the operator actually reads, reassembled across wrapped echoes."""
    parts = []
    for raw in str(script or '').splitlines():
        line = raw.strip()
        if line.startswith('echo "') and line.endswith('"'):
            parts.append(line[len('echo "'):-1])
    return ' '.join(parts)


def test_the_gate_states_that_the_audit_authorizes_nothing(steps):
    tail = _echoed_message(_step(steps, 'Final audit gate')['run'])
    for phrase in (
        'authorizes no mutation',
        'does not repair game 824487',
        'does not backfill',
        'does not update a source revision',
        'does not reset',
        'does not publish or select a snapshot',
        'does not weaken a validator',
        'run a migration',
    ):
        assert phrase in tail


# ── 99-105. Result and exit-code semantics ──────────────────────────────────

def _classification(**overrides):
    base = {
        'root_condition': audit.ROOT_OFFICIAL_SET_CHANGED,
        'current_materiality': audit.MATERIALITY_MATERIAL,
        'persistence': audit.PERSISTENCE_MATCHES_LATER,
        'historical_field_identification': audit.FIELD_ID_IDENTIFIED,
        'checkpoint_state': audit.CHECKPOINT_CURRENT,
    }
    base.update(overrides)
    return base


def test_a_positive_root_cause_returns_complete_root_cause_identified():
    decision = audit.decide(
        classification=_classification(),
        delta={'answer': audit.DELTA_IDENTIFIED},
    )
    assert decision['result'] == audit.RESULT_ROOT_CAUSE_IDENTIFIED
    assert decision['exit_code'] == 0


def test_proven_limited_historical_evidence_returns_the_field_delta_result():
    decision = audit.decide(
        classification=_classification(
            historical_field_identification=audit.FIELD_ID_NOT_RETAINED,
        ),
        delta={'answer': audit.DELTA_NOT_RECOVERABLE},
    )
    assert decision['result'] == audit.RESULT_FIELD_DELTA_UNAVAILABLE
    assert decision['exit_code'] == 0


def test_narrowed_but_unidentified_evidence_also_completes_with_exit_zero():
    decision = audit.decide(
        classification=_classification(
            historical_field_identification=audit.FIELD_ID_NARROWED,
        ),
        delta={'answer': audit.DELTA_NARROWED},
    )
    assert decision['result'] == audit.RESULT_FIELD_DELTA_UNAVAILABLE
    assert decision['exit_code'] == 0


def test_no_current_actionable_defect_returns_complete_no_current_defect():
    decision = audit.decide(
        classification=_classification(
            current_materiality=audit.MATERIALITY_EXACT_MATCH,
        ),
        delta={'answer': audit.DELTA_IDENTIFIED},
    )
    assert decision['result'] == audit.RESULT_NO_CURRENT_DEFECT
    assert decision['exit_code'] == 0


@pytest.mark.parametrize('reason', [
    audit.FAILED_SCOPED_FINGERPRINT_CHANGED,
    audit.FAILED_ARTIFACT_DIGEST_MISMATCH,
    audit.FAILED_ARTIFACT_WRONG_GAME,
    audit.FAILED_HIDDEN_SOURCE_CALL,
    audit.FAILED_FINGERPRINT_NONDETERMINISTIC,
    audit.FAILED_CONFIRMATION_MISMATCH,
])
def test_a_safety_or_integrity_violation_returns_failed(reason):
    decision = audit.decide(
        failed_reasons=[reason],
        classification=_classification(),
        delta={'answer': audit.DELTA_IDENTIFIED},
    )
    assert decision['result'] == audit.RESULT_FAILED
    assert decision['exit_code'] == 1
    assert decision['failed_reasons'] == [reason]


@pytest.mark.parametrize('reason', [
    audit.UNPROVEN_ARTIFACT_MISSING,
    audit.UNPROVEN_CURRENT_SOURCE_UNAVAILABLE,
    audit.UNPROVEN_ADVISORY_LOCK_UNAVAILABLE,
    audit.UNPROVEN_DATABASE_EVIDENCE_UNAVAILABLE,
    audit.UNPROVEN_HISTORICAL_SHA_UNAVAILABLE,
    audit.UNPROVEN_CODE_COMPARISON_INCOMPLETE,
    audit.UNPROVEN_FINGERPRINT_UNAVAILABLE,
])
def test_missing_required_evidence_returns_unproven(reason):
    decision = audit.decide(
        unproven_reasons=[reason],
        classification=_classification(),
        delta={'answer': audit.DELTA_IDENTIFIED},
    )
    assert decision['result'] == audit.RESULT_UNPROVEN
    assert decision['exit_code'] == 2
    assert reason in decision['unproven_reasons']


def test_failed_outranks_unproven_when_both_are_present():
    decision = audit.decide(
        failed_reasons=[audit.FAILED_SCOPED_FINGERPRINT_CHANGED],
        unproven_reasons=[audit.UNPROVEN_ARTIFACT_MISSING],
        classification=_classification(),
    )
    assert decision['result'] == audit.RESULT_FAILED


def test_discovering_a_platform_defect_alone_does_not_make_the_audit_fail():
    """A read-only audit that finds a real defect has SUCCEEDED.

    Materiality against the canonical writer target is exactly the kind of
    finding this audit exists to produce. Reporting it as FAILED would make
    the exit code mean "the platform is broken" in one run and "the audit is
    broken" in another.
    """
    decision = audit.decide(
        classification=_classification(
            current_materiality=audit.MATERIALITY_MATERIAL,
            checkpoint_state=audit.CHECKPOINT_STALE,
        ),
        delta={'answer': audit.DELTA_IDENTIFIED},
    )
    assert decision['result'] in audit.COMPLETE_RESULTS
    assert decision['exit_code'] == 0
    assert decision['platform_defect_discovery_is_not_an_audit_failure'] is True


def test_an_unproven_classification_dimension_cannot_complete():
    for overrides in (
        {'root_condition': audit.ROOT_UNPROVEN},
        {'current_materiality': audit.MATERIALITY_UNPROVEN},
    ):
        decision = audit.decide(
            classification=_classification(**overrides),
            delta={'answer': audit.DELTA_IDENTIFIED},
        )
        assert decision['result'] == audit.RESULT_UNPROVEN
        assert decision['exit_code'] == 2


def test_every_result_has_exactly_one_exit_code():
    assert set(audit.EXIT_CODES) == {
        audit.RESULT_ROOT_CAUSE_IDENTIFIED,
        audit.RESULT_FIELD_DELTA_UNAVAILABLE,
        audit.RESULT_NO_CURRENT_DEFECT,
        audit.RESULT_FAILED,
        audit.RESULT_UNPROVEN,
    }
    assert {audit.EXIT_CODES[result] for result in audit.COMPLETE_RESULTS} == {0}
    assert audit.EXIT_CODES[audit.RESULT_FAILED] == 1
    assert audit.EXIT_CODES[audit.RESULT_UNPROVEN] == 2


def test_a_recommendation_never_grants_authorization():
    consequence = audit.operational_consequence(_classification(
        current_materiality=audit.MATERIALITY_MATERIAL,
        checkpoint_state=audit.CHECKPOINT_STALE,
    ))
    assert audit.CONSEQUENCE_GAMELOG_REPAIR in (
        consequence['supported_by_evidence']
    )
    assert consequence['authorizes_no_mutation'] is True
    assert consequence['recommendation_is_not_approval'] is True
    assert 'separate explicit approval' in consequence['future_repair_requires']


def test_every_decision_carries_the_non_authorization_statement():
    decision = audit.decide(classification=_classification())
    assert 'authorizes no mutation' in decision['non_authorization_statement']
    assert decision['standing_production_state'] == {
        'daily_game_driven_lane': 'shadow',
        'postgame_game_driven_lane': 'shadow',
        'backfill': 'off',
        'automated_writes': 'prohibited',
        'authoritative_publication_mode': 'prohibited',
        'publication_authority': 'existing_trusted_path',
    }


def test_the_global_dead_letter_backlog_is_never_reported_as_zero():
    """The audit may report only that IT created none."""
    decision = audit.decide(classification=_classification())
    assert audit.GOVERNED_DEAD_LETTER_BACKLOG == 1389
    note = decision['dead_letter_backlog_note']
    assert 'zero dead letters' in note
    assert '1389' in note
    assert 'is not changed' in note
