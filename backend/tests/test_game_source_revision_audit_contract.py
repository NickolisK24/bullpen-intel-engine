"""Game 824487 source-revision audit — workflow and result contract.

Requirements 16-26 and 99-105.

The reviewed workflow source is the authority for how this audit can be
invoked; the reducer is the authority for what its outcome means. These tests
own the properties that make the package manual-only, exact-scope, read-only,
and incapable of rerunning, dispatching, repairing, or publishing anything —
and the property that keeps FAILED reserved for a violation of the audit's own
contract rather than for a platform defect it successfully discovered.
"""

import json
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

# A retained expectation and a completeness verdict that are BOTH positively
# established. Completed results now require the observed population size to
# equal the count both retained runs verified, so a reducer test that means to
# exercise a clean run has to supply that evidence rather than omit it.
def _verified_expectation(prior=12, later=12):
    def _entry(count):
        return {
            'identity_state': audit.STATE_VERIFIED,
            'content_state': audit.STATE_VERIFIED,
            'identity_verified': True, 'content_verified': True,
            'observations': [{
                'field': 'appearances_extracted', 'state': audit.OBS_VERIFIED,
                'observed': count, 'evidence_path': 'p',
                'source': audit.SOURCE_RETAINED_ARTIFACT,
            }],
        }
    return audit.retained_appearance_expectation({
        audit.RUN_PRIOR: _entry(prior), audit.RUN_LATER: _entry(later),
    })


def _eligible_completeness(count=12, official=None, stored=None):
    ids = list(range(7001, 7001 + count))
    official = ids if official is None else list(official)
    stored = ids if stored is None else list(stored)
    return audit.current_source_completeness(
        official={'available': True, 'appearance_count': len(official)},
        matrix_summary={
            'structurally_valid': True,
            'official_pitcher_mlb_ids': official,
            'stored_pitcher_mlb_ids': stored,
            'membership_matches': set(official) == set(stored),
            'missing_from_storage': sorted(set(official) - set(stored)),
            'extra_in_storage': sorted(set(stored) - set(official)),
            'official_missing_row_count': len(set(stored) - set(official)),
            'stored_missing_row_count': len(set(official) - set(stored)),
        },
        database_observed=True,
        retained_expectation=_verified_expectation(),
    )


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
        source_completeness=_eligible_completeness(),
        classification=_classification(),
        delta={'answer': audit.DELTA_IDENTIFIED},
    )
    assert decision['result'] == audit.RESULT_ROOT_CAUSE_IDENTIFIED
    assert decision['exit_code'] == 0


def test_proven_limited_historical_evidence_returns_the_field_delta_result():
    decision = audit.decide(
        source_completeness=_eligible_completeness(),
        classification=_classification(
            historical_field_identification=audit.FIELD_ID_NOT_RETAINED,
        ),
        delta={'answer': audit.DELTA_NOT_RECOVERABLE},
    )
    assert decision['result'] == audit.RESULT_FIELD_DELTA_UNAVAILABLE
    assert decision['exit_code'] == 0


def test_narrowed_but_unidentified_evidence_also_completes_with_exit_zero():
    decision = audit.decide(
        source_completeness=_eligible_completeness(),
        classification=_classification(
            historical_field_identification=audit.FIELD_ID_NARROWED,
        ),
        delta={'answer': audit.DELTA_NARROWED},
    )
    assert decision['result'] == audit.RESULT_FIELD_DELTA_UNAVAILABLE
    assert decision['exit_code'] == 0


def test_no_current_actionable_defect_returns_complete_no_current_defect():
    decision = audit.decide(
        source_completeness=_eligible_completeness(),
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
        source_completeness=_eligible_completeness(),
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
        source_completeness=_eligible_completeness(),
        unproven_reasons=[reason],
        classification=_classification(),
        delta={'answer': audit.DELTA_IDENTIFIED},
    )
    assert decision['result'] == audit.RESULT_UNPROVEN
    assert decision['exit_code'] == 2
    assert reason in decision['unproven_reasons']


def test_failed_outranks_unproven_when_both_are_present():
    decision = audit.decide(
        source_completeness=_eligible_completeness(),
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
        source_completeness=_eligible_completeness(),
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
        source_completeness=_eligible_completeness(),
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
    decision = audit.decide(
        source_completeness=_eligible_completeness(),classification=_classification())
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
    decision = audit.decide(
        source_completeness=_eligible_completeness(),classification=_classification())
    assert audit.GOVERNED_DEAD_LETTER_BACKLOG == 1389
    note = decision['dead_letter_backlog_note']
    assert 'zero dead letters' in note
    assert '1389' in note
    assert 'is not changed' in note


# ══════════════════════════════════════════════════════════════════════════
# BLOCKER 3 — the advisory-lock lifecycle must reach the verdict
# ══════════════════════════════════════════════════════════════════════════

def _lock(**overrides):
    state = {
        'acquire_attempted': True,
        'guard_acquired': True,
        'acquisition_reason': 'acquired',
        'guard_release_attempted': True,
        'guard_released': True,
        'release_reason': 'released',
        'rollback_attempted': True,
        'rollback_succeeded': True,
    }
    state.update(overrides)
    return audit.lock_lifecycle(state)


def test_a_never_acquired_lock_is_unproven():
    lifecycle = _lock(guard_acquired=False, guard_release_attempted=False,
                      guard_released=None)
    assert lifecycle['status'] == audit.LOCK_NOT_ACQUIRED
    assert lifecycle['release_proven'] is False
    assert audit.UNPROVEN_ADVISORY_LOCK_UNAVAILABLE in (
        lifecycle['unproven_reasons']
    )
    assert lifecycle['failed_reasons'] == []
    decision = audit.decide(
        source_completeness=_eligible_completeness(),classification=_classification(), lock=lifecycle)
    assert decision['result'] == audit.RESULT_UNPROVEN
    assert decision['exit_code'] == 2


def test_a_never_attempted_lock_is_unproven():
    lifecycle = _lock(acquire_attempted=False, guard_acquired=False,
                      guard_release_attempted=False, guard_released=None)
    assert lifecycle['status'] == audit.LOCK_NOT_ATTEMPTED
    assert audit.decide(
        source_completeness=_eligible_completeness(),
        classification=_classification(), lock=lifecycle,
    )['exit_code'] == 2


def test_an_acquired_and_released_lock_may_complete():
    lifecycle = _lock()
    assert lifecycle['status'] == audit.LOCK_RELEASED
    assert lifecycle['release_proven'] is True
    assert lifecycle['failed_reasons'] == []
    assert lifecycle['unproven_reasons'] == []
    decision = audit.decide(
        source_completeness=_eligible_completeness(),
        classification=_classification(),
        delta={'answer': audit.DELTA_IDENTIFIED}, lock=lifecycle,
    )
    assert decision['exit_code'] == 0


def test_a_release_that_raised_cannot_complete():
    lifecycle = _lock(guard_released=False, release_reason='release_raised')
    assert lifecycle['status'] == audit.LOCK_RELEASE_FAILED
    assert audit.FAILED_LOCK_RELEASE_FAILED in lifecycle['failed_reasons']
    decision = audit.decide(
        source_completeness=_eligible_completeness(),
        classification=_classification(),
        delta={'answer': audit.DELTA_IDENTIFIED}, lock=lifecycle,
    )
    assert decision['result'] == audit.RESULT_FAILED
    assert decision['exit_code'] == 1
    assert audit.FAILED_LOCK_RELEASE_FAILED in decision['failed_reasons']


def test_a_release_never_attempted_after_acquisition_cannot_complete():
    lifecycle = _lock(guard_release_attempted=False, guard_released=None)
    assert lifecycle['status'] == audit.LOCK_RELEASE_NOT_ATTEMPTED
    assert audit.FAILED_LOCK_RELEASE_NOT_ATTEMPTED in (
        lifecycle['failed_reasons']
    )
    assert audit.decide(
        source_completeness=_eligible_completeness(),
        classification=_classification(), lock=lifecycle,
    )['exit_code'] == 1


def test_a_release_outcome_never_established_cannot_complete():
    """Attempted, but nobody proved it came back."""
    lifecycle = _lock(guard_released=None, release_reason=None)
    assert lifecycle['status'] == audit.LOCK_RELEASE_UNKNOWN
    assert audit.UNPROVEN_LOCK_RELEASE_UNKNOWN in (
        lifecycle['unproven_reasons']
    )
    decision = audit.decide(
        source_completeness=_eligible_completeness(),
        classification=_classification(),
        delta={'answer': audit.DELTA_IDENTIFIED}, lock=lifecycle,
    )
    assert decision['exit_code'] == 2


def test_context_termination_alone_does_not_prove_release():
    """The default is 'unknown', not 'released'."""
    lifecycle = audit.lock_lifecycle({
        'acquire_attempted': True, 'guard_acquired': True,
        'guard_release_attempted': True,
    })
    assert lifecycle['guard_released'] is None
    assert lifecycle['release_proven'] is False


def test_an_earlier_source_failure_and_a_failed_release_both_report():
    decision = audit.decide(
        source_completeness=_eligible_completeness(),
        failed_reasons=[audit.FAILED_HIDDEN_SOURCE_CALL],
        classification=_classification(),
        lock=_lock(guard_released=False),
    )
    assert audit.FAILED_HIDDEN_SOURCE_CALL in decision['failed_reasons']
    assert audit.FAILED_LOCK_RELEASE_FAILED in decision['failed_reasons']


def test_an_earlier_artifact_gap_and_a_failed_release_both_report():
    decision = audit.decide(
        source_completeness=_eligible_completeness(),
        unproven_reasons=[audit.UNPROVEN_ARTIFACT_MISSING],
        classification=_classification(),
        lock=_lock(guard_released=False),
    )
    assert decision['result'] == audit.RESULT_FAILED
    assert audit.FAILED_LOCK_RELEASE_FAILED in decision['failed_reasons']


def test_the_lifecycle_records_rollback_alongside_release():
    lifecycle = _lock(guard_released=False, rollback_succeeded=True)
    assert lifecycle['rollback_attempted'] is True
    assert lifecycle['rollback_succeeded'] is True
    assert lifecycle['release_proven'] is False


def test_the_lifecycle_carries_no_exception_text():
    lifecycle = _lock(
        guard_released=False, release_reason='release_raised',
        acquisition_reason='lock_unavailable_or_contended',
    )
    rendered = json.dumps(lifecycle)
    for forbidden in ('Traceback', 'File "', 'psycopg2', '/home/', 'Error('):
        assert forbidden not in rendered


def test_a_completed_result_requires_a_proven_release():
    for lifecycle in (
        _lock(guard_released=False),
        _lock(guard_released=None),
        _lock(guard_release_attempted=False, guard_released=None),
        _lock(guard_acquired=False, guard_release_attempted=False,
              guard_released=None),
    ):
        decision = audit.decide(
        source_completeness=_eligible_completeness(),
            classification=_classification(),
            delta={'answer': audit.DELTA_IDENTIFIED}, lock=lifecycle,
        )
        assert decision['exit_code'] != 0
        assert decision['result'] not in audit.COMPLETE_RESULTS


# ══════════════════════════════════════════════════════════════════════════
# Question gating — an unanswered mandatory question closes exit zero
# ══════════════════════════════════════════════════════════════════════════

def _questions(**states):
    """Every mandatory question answered unless overridden."""
    return [
        {
            'question_id': qid,
            'mandatory_for_completion': True,
            'fully_answered': states.get(qid, True),
        }
        for qid in audit.MANDATORY_QUESTIONS
    ]


def test_all_mandatory_questions_answered_permits_completion():
    decision = audit.decide(
        source_completeness=_eligible_completeness(),
        classification=_classification(),
        delta={'answer': audit.DELTA_IDENTIFIED},
        lock=_lock(), questions=_questions(),
    )
    assert decision['exit_code'] == 0
    assert decision['unanswered_mandatory_questions'] == []


@pytest.mark.parametrize('question_id', audit.MANDATORY_QUESTIONS)
def test_one_unanswered_mandatory_question_closes_exit_zero(question_id):
    decision = audit.decide(
        source_completeness=_eligible_completeness(),
        classification=_classification(),
        delta={'answer': audit.DELTA_IDENTIFIED},
        lock=_lock(), questions=_questions(**{question_id: False}),
    )
    assert decision['result'] == audit.RESULT_UNPROVEN
    assert decision['exit_code'] == 2
    assert question_id in decision['unanswered_mandatory_questions']
    assert audit.UNPROVEN_QUESTION_UNANSWERED in decision['unproven_reasons']


def test_a_non_mandatory_unanswered_question_does_not_close_exit_zero():
    questions = _questions() + [{
        'question_id': 'Q3', 'mandatory_for_completion': False,
        'fully_answered': False,
    }]
    decision = audit.decide(
        source_completeness=_eligible_completeness(),
        classification=_classification(),
        delta={'answer': audit.DELTA_IDENTIFIED},
        lock=_lock(), questions=questions,
    )
    assert decision['exit_code'] == 0


def test_the_answer_state_vocabulary_is_closed_and_distinguishing():
    assert audit.ANSWER_OBSERVED_NO in audit.ANSWERED_STATES
    assert audit.ANSWER_OBSERVED_INSUFFICIENT in audit.ANSWERED_STATES
    # "nobody looked" is NOT an answer, however negative it sounds.
    assert audit.ANSWER_NOT_OBSERVED not in audit.ANSWERED_STATES
    assert audit.ANSWER_UNAVAILABLE not in audit.ANSWERED_STATES
    assert audit.ANSWER_UNPROVEN not in audit.ANSWERED_STATES


# ══════════════════════════════════════════════════════════════════════════
# Static regression — no expected value may become an observed value
# ══════════════════════════════════════════════════════════════════════════

AUDIT_SOURCES = (
    REPO_ROOT / 'backend/services/game_source_revision_audit.py',
    REPO_ROOT / 'backend/scripts/run_game_source_revision_audit.py',
)


def test_no_audit_source_falls_back_from_observed_to_expected():
    """The Blocker 1 and Blocker 2 defect shape, banned by static scan.

    ``observed = artifact.get(x) or spec[...]`` and its relatives turn a
    missing fact into a matching one. Nothing in the package may express that
    shape against a locked expectation.
    """
    banned = (
        re.compile(r"\.get\([^)]*\)\s+or\s+spec\["),
        re.compile(r"\.get\([^)]*\)\s+or\s+RUN_EXPECTATIONS"),
        re.compile(r"\.get\([^)]*\)\s+or\s+expected"),
        re.compile(r"\.get\([^)]*,\s*expected\)"),
        re.compile(r"\.get\([^)]*,\s*spec\["),
        re.compile(r"or\s+EXPECTED_[A-Z_]+"),
        re.compile(r"\.get\([^)]*\)\s+or\s+LATER_LANE_EXPECTATIONS"),
    )
    for path in AUDIT_SOURCES:
        text = path.read_text(encoding='utf-8')
        for pattern in banned:
            assert not pattern.search(text), (
                f'{path.name} contains an expected-value fallback: '
                f'{pattern.pattern}'
            )


def test_the_audit_never_reads_an_expectation_inside_the_activation_view():
    """Question 10's input must come only from parsed observations."""
    runner_source = (
        REPO_ROOT / 'backend/scripts/run_game_source_revision_audit.py'
    ).read_text(encoding='utf-8')
    body = runner_source.split('def later_activation_view', 1)[1].split(
        '\ndef ', 1
    )[0]
    assert 'RUN_EXPECTATIONS' not in body
    assert "if later.get('present')" not in body
    assert 'activation_evidence' in body


def test_no_audit_source_serializes_exception_text():
    for path in AUDIT_SOURCES:
        text = path.read_text(encoding='utf-8')
        for banned in ('traceback.format_exc', 'repr(exc)', 'str(exc)'):
            assert banned not in text, f'{path.name} may leak exception text'


def test_no_audit_source_carries_prohibited_attribution():
    terms = (
        'claude', 'anthropic', 'chatgpt', 'openai', 'ai-generated',
        'generated by', 'generated-by', 'co-authored-by', 'assisted-by',
        'copilot',
    )
    paths = list(AUDIT_SOURCES) + [
        WORKFLOW_PATH,
        REPO_ROOT / 'docs/current/GAME_824487_SOURCE_REVISION_AUDIT.md',
    ]
    for path in paths:
        lowered = path.read_text(encoding='utf-8').lower()
        for term in terms:
            assert term not in lowered, f'{path.name} carries "{term}"'


# ══════════════════════════════════════════════════════════════════════════
# Workflow contract additions for workflow-run metadata retrieval
# ══════════════════════════════════════════════════════════════════════════

def test_the_workflow_records_historical_workflow_run_metadata(steps):
    step = _step(steps, 'Record historical workflow-run metadata')
    assert step['continue-on-error'] is True
    body = str(step['run'])
    assert '/actions/runs/' in body
    assert 'head_branch' in body
    assert 'workflow-run-metadata.json' in body


def test_workflow_metadata_retrieval_is_read_only(steps, workflow):
    assert workflow['permissions'] == {'contents': 'read', 'actions': 'read'}
    body = str(_step(steps, 'Record historical workflow-run metadata')['run'])
    for forbidden in ("method='POST'", 'method="POST"', 'DELETE', 'PATCH'):
        assert forbidden not in body


def test_workflow_metadata_is_recorded_before_the_audit_runs(steps):
    assert _index(steps, 'Record historical workflow-run metadata') < _index(
        steps, 'Run the read-only source-revision audit',
    )


def test_workflow_metadata_covers_exactly_the_two_locked_runs(steps):
    body = str(_step(steps, 'Record historical workflow-run metadata')['run'])
    assert audit.PRIOR_RUN_ID in body
    assert audit.LATER_RUN_ID in body
    assert body.count("RUN_IDS = ('") == 1


# ══════════════════════════════════════════════════════════════════════════
# MEDIUM-C — the state reducer must never default into VERIFIED
#
# VERIFIED is a positive claim. A gate that observed nothing observed nothing,
# and a value that was read but never compared against anything was never
# verified. Neither may reduce to agreement, and neither may leave a state
# reading verified while ``verified_fields`` is empty.
# ══════════════════════════════════════════════════════════════════════════

def _verified_observation(field='observed_field', value=7):
    return audit.observation(
        field=field, path=field, source=audit.SOURCE_RETAINED_ARTIFACT,
        observed=value, expected=value,
    )


def _unvalidated_observation(field='unvalidated_field', value=7):
    """Read from the document, compared against nothing."""
    return audit.observation(
        field=field, path=field, source=audit.SOURCE_RETAINED_ARTIFACT,
        observed=value,
    )


def _absent_observation(field='absent_field'):
    return audit.observation(
        field=field, path=field, source=audit.SOURCE_RETAINED_ARTIFACT,
    )


def _mismatched_observation(field='mismatched_field'):
    return audit.observation(
        field=field, path=field, source=audit.SOURCE_RETAINED_ARTIFACT,
        observed=1, expected=2,
    )


def test_an_empty_observation_set_reduces_to_unproven():
    assert audit._reduce_state([]) == audit.STATE_UNPROVEN
    assert audit._reduce_state(None) == audit.STATE_UNPROVEN


def test_only_unvalidated_observations_reduce_to_unproven():
    observation = _unvalidated_observation()
    assert observation['state'] == audit.OBS_OBSERVED
    assert audit._reduce_state([observation]) == audit.STATE_UNPROVEN


def test_a_single_verified_observation_reduces_to_verified():
    assert audit._reduce_state(
        [_verified_observation()],
    ) == audit.STATE_VERIFIED


def test_verified_plus_mismatch_reduces_to_failed():
    assert audit._reduce_state([
        _verified_observation(), _mismatched_observation(),
    ]) == audit.STATE_FAILED


def test_verified_plus_absent_reduces_to_unproven():
    assert audit._reduce_state([
        _verified_observation(), _absent_observation(),
    ]) == audit.STATE_UNPROVEN


def test_verified_plus_unvalidated_reduces_to_unproven():
    assert audit._reduce_state([
        _verified_observation(), _unvalidated_observation(),
    ]) == audit.STATE_UNPROVEN


def test_a_mismatch_still_outranks_an_unvalidated_value():
    assert audit._reduce_state([
        _unvalidated_observation(), _mismatched_observation(),
    ]) == audit.STATE_FAILED


def test_every_mandatory_registry_row_resolves_its_validator():
    """A field nothing validates is not a mandatory field."""
    assert audit.registry_expectation_defects() == []


def test_a_registry_row_with_an_unresolvable_expectation_cannot_verify(
    monkeypatch,
):
    """The reducer refuses even if a defective row ever reaches production."""
    broken = audit.observation(
        field='runner_exit_code', path='runner_exit_code',
        source=audit.SOURCE_RETAINED_ARTIFACT, observed=0,
    )
    assert broken['state'] == audit.OBS_OBSERVED
    assert audit._reduce_state([broken]) == audit.STATE_UNPROVEN
    assert audit.observation_verified([broken]) == []


def test_a_verified_state_can_never_have_empty_verified_fields():
    """identity and content verified both imply a non-empty verified list."""
    ingested = audit.ingest_run_artifacts('/nonexistent-evidence-root')
    for run_key in audit.RUN_KEYS:
        entry = ingested['runs'][run_key]
        for state_key, verified_key in (
            ('identity_state', 'verified_fields'),
            ('content_state', 'verified_fields'),
        ):
            if entry[state_key] == audit.STATE_VERIFIED:
                assert entry[verified_key], (
                    f'{run_key}.{state_key} verified with nothing verified'
                )


def test_state_and_verified_fields_cannot_contradict_each_other():
    """Verified requires that EVERY observation was compared and matched."""
    observations = [_verified_observation('a'), _verified_observation('b')]
    assert audit._reduce_state(observations) == audit.STATE_VERIFIED
    assert len(audit.observation_verified(observations)) == len(observations)

    observations.append(_unvalidated_observation('c'))
    assert audit._reduce_state(observations) == audit.STATE_UNPROVEN
    assert len(audit.observation_verified(observations)) != len(observations)


# ══════════════════════════════════════════════════════════════════════════
# HIGH-B — fingerprint determinism is mandatory
# ══════════════════════════════════════════════════════════════════════════

def test_question_five_is_mandatory_for_completion():
    assert 'Q5' in audit.MANDATORY_QUESTIONS


def _gate_lock():
    return audit.lock_lifecycle({
        'acquire_attempted': True, 'guard_acquired': True,
        'guard_release_attempted': True, 'guard_released': True,
    })


def _eligible_source():
    return audit.current_source_completeness(
        official={'available': True, 'appearance_count': 12},
        matrix_summary={
            'structurally_valid': True, 'membership_matches': True,
            'missing_from_storage': [], 'extra_in_storage': [],
            'official_missing_row_count': 0, 'stored_missing_row_count': 0,
        },
        database_observed=True,
        retained_expectation=_verified_expectation(),
    )


def _gate_questions(unanswered=()):
    return [
        {
            'question_id': question_id,
            'mandatory_for_completion': (
                question_id in audit.MANDATORY_QUESTIONS
            ),
            'fully_answered': question_id not in unanswered,
        }
        for question_id in (
            'Q1', 'Q2', 'Q3', 'Q4', 'Q5', 'Q6',
            'Q7', 'Q8', 'Q9', 'Q10', 'Q11', 'Q12',
        )
    ]


def test_question_five_alone_unanswered_prevents_exit_zero():
    decision = audit.decide(
        classification={
            'root_condition': audit.ROOT_OFFICIAL_SET_CHANGED,
            'current_materiality': audit.MATERIALITY_EXACT_MATCH,
            'current_source_completeness': audit.SOURCE_COMPLETE,
        },
        delta={}, lock=_gate_lock(),
        questions=_gate_questions(unanswered={'Q5'}),
        source_completeness=_eligible_source(),
    )
    assert decision['unanswered_mandatory_questions'] == ['Q5']
    assert decision['result'] == audit.RESULT_UNPROVEN
    assert decision['exit_code'] == 2


def test_determinism_over_an_empty_set_is_unproven_not_deterministic():
    result = audit.fingerprint_determinism([])
    assert result['deterministic_in_process'] is None
    assert result['evidence_status'] == audit.EVIDENCE_UNPROVEN
    assert result['appearance_count'] == 0


# ══════════════════════════════════════════════════════════════════════════
# BLOCKER-A — current official set completeness gates every completed result
# ══════════════════════════════════════════════════════════════════════════

def _source_completeness(*, available=True, count=12, official=(), stored=(),
                  database_observed=True, structurally_valid=True,
                  expectation=None, duplicates_official=(),
                  duplicates_stored=()):
    official_ids = list(official) if official or stored else list(range(12))
    stored_ids = list(stored) if official or stored else list(range(12))
    return audit.current_source_completeness(
        official={'available': available, 'appearance_count': count},
        matrix_summary={
            'structurally_valid': structurally_valid,
            'official_pitcher_mlb_ids': official_ids,
            'stored_pitcher_mlb_ids': stored_ids,
            'membership_matches': set(official_ids) == set(stored_ids),
            'missing_from_storage': sorted(
                set(official_ids) - set(stored_ids)
            ),
            'extra_in_storage': sorted(set(stored_ids) - set(official_ids)),
            'official_missing_row_count': len(
                set(stored_ids) - set(official_ids)
            ),
            'stored_missing_row_count': len(
                set(official_ids) - set(stored_ids)
            ),
            'duplicate_official_identities': list(duplicates_official),
            'duplicate_stored_identities': list(duplicates_stored),
        },
        database_observed=database_observed,
        # Membership states are only REACHED once the population size is
        # established, so a membership test has to supply that evidence.
        retained_expectation=(
            _verified_expectation(count, count) if expectation is None
            else expectation
        ),
    )


def test_an_exactly_matching_membership_set_is_conclusion_eligible():
    result = _source_completeness()
    assert result['completeness_state'] == audit.SOURCE_COMPLETE
    assert result['conclusion_eligible'] is True
    assert result['limitations'] == []
    assert result['reason_codes'] == []


def test_an_empty_official_set_is_never_conclusion_eligible():
    result = _source_completeness(count=0, official=[], stored=list(range(12)))
    assert result['completeness_state'] == audit.SOURCE_EMPTY
    assert result['conclusion_eligible'] is False
    assert audit.UNPROVEN_CURRENT_SOURCE_EMPTY in result['reason_codes']


def test_an_empty_official_set_stays_ineligible_when_storage_is_also_empty():
    """Zero versus zero is never a valid match for a FINAL MLB game."""
    result = _source_completeness(count=0, official=[], stored=[])
    assert result['completeness_state'] == audit.SOURCE_EMPTY
    assert result['conclusion_eligible'] is False


def test_an_official_only_member_is_reported_in_its_own_direction():
    result = _source_completeness(
        count=13, official=list(range(13)), stored=list(range(12)),
    )
    assert result['completeness_state'] == audit.SOURCE_OFFICIAL_ONLY_MEMBERS
    assert result['conclusion_eligible'] is False
    assert result['missing_from_storage'] == [12]


def test_a_stored_only_member_is_reported_in_its_own_direction():
    result = _source_completeness(
        count=6, official=list(range(6)), stored=list(range(12)),
    )
    assert result['completeness_state'] == audit.SOURCE_STORED_ONLY_MEMBERS
    assert result['conclusion_eligible'] is False
    assert result['extra_in_storage'] == list(range(6, 12))


def test_membership_differing_in_both_directions_is_its_own_state():
    result = _source_completeness(
        count=12, official=list(range(12)), stored=list(range(1, 13)),
    )
    assert result['completeness_state'] == audit.SOURCE_BOTH_DIRECTIONS
    assert result['conclusion_eligible'] is False


def test_an_unfetched_source_is_source_unavailable_not_empty():
    result = _source_completeness(available=False, count=0)
    assert result['completeness_state'] == audit.SOURCE_STATE_UNAVAILABLE
    assert result['conclusion_eligible'] is False


def test_an_unobserved_database_leaves_membership_unresolved():
    result = _source_completeness(database_observed=False)
    assert result['completeness_state'] == audit.SOURCE_DATABASE_UNAVAILABLE
    assert result['conclusion_eligible'] is False


def test_an_invalid_matrix_leaves_membership_unresolved():
    result = _source_completeness(structurally_valid=False)
    assert result['completeness_state'] == audit.SOURCE_MATRIX_UNPROVEN
    assert result['conclusion_eligible'] is False


def test_exactly_one_completeness_state_is_conclusion_eligible():
    eligible = [
        state for state in audit.SOURCE_COMPLETENESS_STATES
        if state in audit.CONCLUSION_ELIGIBLE_STATES
    ]
    assert eligible == [audit.SOURCE_COMPLETE]


@pytest.mark.parametrize('state', [
    state for state in audit.SOURCE_COMPLETENESS_STATES
    if state not in audit.CONCLUSION_ELIGIBLE_STATES
])
def test_no_completed_result_survives_an_ineligible_source(state):
    """Every exit-zero name is gated, not just the no-defect one."""
    for materiality, delta_answer in (
        (audit.MATERIALITY_EXACT_MATCH, audit.DELTA_IDENTIFIED),
        (audit.MATERIALITY_MATERIAL, audit.DELTA_IDENTIFIED),
        (audit.MATERIALITY_MATERIAL, audit.DELTA_NOT_RECOVERABLE),
    ):
        decision = audit.decide(
            classification={
                'root_condition': audit.ROOT_OFFICIAL_SET_CHANGED,
                'current_materiality': materiality,
                'current_source_completeness': state,
            },
            delta={'answer': delta_answer}, lock=_gate_lock(),
            questions=_gate_questions(),
            source_completeness={
                'completeness_state': state, 'conclusion_eligible': False,
                'reason_codes': [audit.UNPROVEN_CURRENT_SOURCE_INCOMPLETE],
            },
        )
        assert decision['result'] not in audit.COMPLETE_RESULTS
        assert decision['exit_code'] == 2


def test_a_conclusion_eligible_source_still_permits_completion():
    decision = audit.decide(
        classification={
            'root_condition': audit.ROOT_OFFICIAL_SET_CHANGED,
            'current_materiality': audit.MATERIALITY_EXACT_MATCH,
            'current_source_completeness': audit.SOURCE_COMPLETE,
        },
        delta={'answer': audit.DELTA_IDENTIFIED}, lock=_gate_lock(),
        questions=_gate_questions(), source_completeness=_eligible_source(),
    )
    assert decision['result'] in audit.COMPLETE_RESULTS
    assert decision['exit_code'] == 0
    assert decision['current_source_conclusion_eligible'] is True


def test_the_completeness_gate_reason_reaches_the_verdict():
    decision = audit.decide(
        classification={
            'root_condition': audit.ROOT_OFFICIAL_SET_CHANGED,
            'current_materiality': audit.MATERIALITY_UNPROVEN,
            'current_source_completeness': audit.SOURCE_EMPTY,
        },
        delta={}, lock=_gate_lock(), questions=_gate_questions(),
        source_completeness=_source_completeness(
            count=0, official=[], stored=list(range(12)),
        ),
    )
    assert audit.UNPROVEN_CURRENT_SOURCE_EMPTY in decision['unproven_reasons']
    assert decision['exit_code'] == 2


def test_the_completeness_reason_codes_are_declared_unproven_reasons():
    for reason in (
        audit.UNPROVEN_CURRENT_SOURCE_EMPTY,
        audit.UNPROVEN_CURRENT_SOURCE_INCOMPLETE,
        audit.UNPROVEN_REGISTRY_EXPECTATION_MISSING,
    ):
        assert reason in audit.UNPROVEN_REASONS


def test_the_completeness_object_carries_no_raw_payload():
    """Counts, ids, a state, a flag and reasons — never a box score."""
    result = _source_completeness()
    serialized = json.dumps(result, sort_keys=True, default=str).lower()
    for banned in ('boxscore', 'teams', 'players', 'traceback', 'password'):
        assert banned not in serialized


# ══════════════════════════════════════════════════════════════════════════
# MEDIUM-D — documented registry scope must match the implementation
# ══════════════════════════════════════════════════════════════════════════

DOC_PATH = REPO_ROOT / 'docs/current/GAME_824487_SOURCE_REVISION_AUDIT.md'


def test_the_registry_row_count_the_docs_claim_is_the_real_one():
    assert len(audit.MANDATORY_FIELDS) == 26
    assert f'{len(audit.MANDATORY_FIELDS)} rows' in DOC_PATH.read_text(
        encoding='utf-8',
    )


def test_the_registry_covers_only_handoff_activation_and_workflow_metadata():
    """Artifact id, digest and the sync-summary game facts live elsewhere."""
    documents = {spec['doc'] for spec in audit.MANDATORY_FIELDS}
    assert documents == {
        audit.DOC_HANDOFF, audit.DOC_ACTIVATION, audit.DOC_WORKFLOW_METADATA,
    }
    fields = {spec['field'] for spec in audit.MANDATORY_FIELDS}
    assert 'artifact_id' not in fields
    assert 'digest' not in fields
    assert 'source_revision' not in fields


def test_the_game_scoped_sync_facts_are_enforced_outside_the_registry():
    """Separately enforced, but still enforced — and still content-gating."""
    assert audit._CONTENT_GAME_FIELDS == frozenset({
        'game_membership', 'source_revision', 'reconciliation_plan_fingerprint',
        'appearances_extracted', 'unchanged', 'inserted', 'updated', 'blocked',
    })


def _doc_prose():
    """The doc with line wrapping normalised away.

    These assertions are about what the document CLAIMS, so they must survive
    a reflow that changes nothing about the claim.
    """
    return ' '.join(DOC_PATH.read_text(encoding='utf-8').split()).lower()


def test_the_docs_describe_artifact_id_absence_accurately():
    prose = _doc_prose()
    assert 'not_exposed_by_github' in prose
    assert 'does not on its own make identity unproven' in prose
    assert 'exposed and differs, or is malformed, **fails** identity' in prose


def test_the_docs_do_not_claim_an_unfetched_source_is_the_only_non_match():
    """The old wording covered only the never-fetched case."""
    prose = _doc_prose()
    assert (
        'unavailable, empty, membership-incomplete, duplicate-bearing, '
        'inconsistent with the common appearance count verified in the '
        'retained artifacts, or otherwise not conclusion-eligible'
    ) in prose
    assert 'an unfetched source is not a current match' not in prose
    # Membership equality alone must never be presented as proof of a
    # complete official set.
    assert 'necessary but not sufficient' in prose
    assert 'two symmetrically truncated sets match each other' in prose


# ══════════════════════════════════════════════════════════════════════════
# LOW-E — the workflow comment must describe the real control flow
# ══════════════════════════════════════════════════════════════════════════

def test_the_scan_step_comment_matches_its_actual_failure_behaviour():
    text = WORKFLOW_PATH.read_text(encoding='utf-8')
    assert 'A scanner failure fails the workflow' not in text
    assert 'the final audit gate fails the workflow unless' in text


def test_the_scan_outcome_really_is_enforced_by_the_final_gate(steps):
    scan = _step(steps, 'Scan the evidence artifact')
    assert scan['continue-on-error'] is True
    upload = _step(steps, 'Upload the evidence artifact')
    assert "steps.scan.outcome == 'success'" in str(upload['if'])
    gate = _step(steps, 'Final audit gate')
    assert 'continue-on-error' not in gate
    assert '$SCAN_OUTCOME' in str(gate['run'])


# ══════════════════════════════════════════════════════════════════════════
# BLOCKER-F — symmetric truncation
#
# Two incomplete sets agreeing with one another prove nothing about either.
# The observed population size must equal the appearance count BOTH retained
# runs positively verified, and that count is read out of the artifacts' own
# observations rather than out of any locked constant.
# ══════════════════════════════════════════════════════════════════════════

def _run_entry(count, *, identity=audit.STATE_VERIFIED,
               content=audit.STATE_VERIFIED, state=audit.OBS_VERIFIED):
    observations = []
    if count is not _UNSET_COUNT:
        observations.append({
            'field': 'appearances_extracted', 'state': state,
            'observed': count, 'evidence_path': 'p',
            'source': audit.SOURCE_RETAINED_ARTIFACT,
        })
    return {
        'identity_state': identity, 'content_state': content,
        'identity_verified': identity == audit.STATE_VERIFIED,
        'content_verified': content == audit.STATE_VERIFIED,
        'observations': observations,
    }


_UNSET_COUNT = object()


def _expectation(prior=12, later=12, **kw):
    return audit.retained_appearance_expectation({
        audit.RUN_PRIOR: _run_entry(prior, **kw),
        audit.RUN_LATER: _run_entry(later, **kw),
    })


def test_two_verified_agreeing_counts_supply_the_expectation():
    result = _expectation(12, 12)
    assert result['expectation_state'] == audit.EXPECTATION_VERIFIED
    assert result['expected_current_count'] == 12
    assert result['conclusion_usable'] is True
    assert result['counts_agree'] is True
    assert result['both_artifacts_verified'] is True


def test_disagreeing_retained_counts_supply_nothing():
    result = _expectation(12, 11)
    assert result['expectation_state'] == audit.EXPECTATION_COUNTS_DISAGREE
    assert result['expected_current_count'] is None
    assert result['conclusion_usable'] is False


def test_an_absent_prior_count_makes_the_expectation_unusable():
    result = audit.retained_appearance_expectation({
        audit.RUN_PRIOR: _run_entry(_UNSET_COUNT),
        audit.RUN_LATER: _run_entry(12),
    })
    assert result['expectation_state'] == (
        audit.EXPECTATION_PRIOR_COUNT_UNOBSERVED
    )
    assert result['conclusion_usable'] is False


def test_an_absent_later_count_makes_the_expectation_unusable():
    result = audit.retained_appearance_expectation({
        audit.RUN_PRIOR: _run_entry(12),
        audit.RUN_LATER: _run_entry(_UNSET_COUNT),
    })
    assert result['expectation_state'] == (
        audit.EXPECTATION_LATER_COUNT_UNOBSERVED
    )
    assert result['conclusion_usable'] is False


def test_an_unproven_prior_identity_makes_the_expectation_unavailable():
    result = audit.retained_appearance_expectation({
        audit.RUN_PRIOR: _run_entry(12, identity=audit.STATE_UNPROVEN),
        audit.RUN_LATER: _run_entry(12),
    })
    assert result['expectation_state'] == (
        audit.EXPECTATION_PRIOR_ARTIFACT_UNPROVEN
    )
    assert result['conclusion_usable'] is False


def test_unproven_later_content_makes_the_expectation_unavailable():
    result = audit.retained_appearance_expectation({
        audit.RUN_PRIOR: _run_entry(12),
        audit.RUN_LATER: _run_entry(12, content=audit.STATE_UNPROVEN),
    })
    assert result['expectation_state'] == (
        audit.EXPECTATION_LATER_ARTIFACT_UNPROVEN
    )
    assert result['conclusion_usable'] is False


def test_a_malformed_retained_count_is_not_a_count():
    result = _expectation('12', '12')
    assert result['expectation_state'] == audit.EXPECTATION_COUNT_MALFORMED
    assert result['expected_current_count'] is None
    assert result['conclusion_usable'] is False


def test_one_artifact_alone_cannot_establish_the_common_expectation():
    result = audit.retained_appearance_expectation({
        audit.RUN_PRIOR: _run_entry(12),
    })
    assert result['conclusion_usable'] is False
    assert result['expected_current_count'] is None


def test_a_count_observed_but_not_verified_cannot_supply_the_expectation():
    """observed-but-uncompared is not verified, here as everywhere else."""
    result = _expectation(12, 12, state=audit.OBS_OBSERVED)
    assert result['conclusion_usable'] is False
    assert result['expected_current_count'] is None


def test_the_expectation_never_falls_back_to_the_locked_constant():
    """Remove the observed counts; nothing may substitute EXPECTED_APPEARANCE_COUNT."""
    result = audit.retained_appearance_expectation({
        audit.RUN_PRIOR: _run_entry(_UNSET_COUNT),
        audit.RUN_LATER: _run_entry(_UNSET_COUNT),
    })
    assert result['expected_current_count'] is None
    assert result['expected_current_count'] != audit.EXPECTED_APPEARANCE_COUNT


def test_the_expectation_tracks_the_artifact_not_run_expectations(monkeypatch):
    """The value comes from the observation, so a changed constant cannot move it."""
    monkeypatch.setitem(
        audit.RUN_EXPECTATIONS[audit.RUN_PRIOR], 'source_revision', 'changed',
    )
    assert _expectation(9, 9)['expected_current_count'] == 9
    assert _expectation(12, 12)['expected_current_count'] == 12


def test_unchanged_alone_cannot_supply_the_retained_count():
    """Only appearances_extracted counts; `unchanged` is a different fact."""
    entry = {
        'identity_state': audit.STATE_VERIFIED,
        'content_state': audit.STATE_VERIFIED,
        'identity_verified': True, 'content_verified': True,
        'observations': [{
            'field': 'unchanged', 'state': audit.OBS_VERIFIED, 'observed': 12,
            'evidence_path': 'p', 'source': audit.SOURCE_RETAINED_ARTIFACT,
        }],
    }
    result = audit.retained_appearance_expectation({
        audit.RUN_PRIOR: entry, audit.RUN_LATER: entry,
    })
    assert result['conclusion_usable'] is False


# ── Count consistency inside the completeness model ────────────────────────

def test_symmetric_truncation_is_not_conclusion_eligible():
    """THE blocker: six observed, six stored, retained expectation twelve."""
    six = list(range(7001, 7007))
    result = _source_completeness(count=6, official=six, stored=six,
                                  expectation=_expectation(12, 12))
    assert result['completeness_state'] == audit.SOURCE_COUNT_CONTRADICTS
    assert result['conclusion_eligible'] is False
    assert result['membership_matches'] is True
    assert result['current_count_matches_retained_expectation'] is False
    assert result['count_consistency_state'] == (
        audit.COUNT_CONSISTENCY_CONTRADICTED
    )
    assert audit.UNPROVEN_CURRENT_COUNT_CONTRADICTS in result['reason_codes']


@pytest.mark.parametrize('size', [1, 6, 11, 13, 24])
def test_any_symmetric_population_other_than_the_verified_one_is_ineligible(
    size,
):
    ids = list(range(7001, 7001 + size))
    result = _source_completeness(count=size, official=ids, stored=ids,
                                  expectation=_expectation(12, 12))
    assert result['conclusion_eligible'] is False
    assert result['completeness_state'] == audit.SOURCE_COUNT_CONTRADICTS


def test_the_verified_population_size_remains_eligible():
    ids = list(range(7001, 7013))
    result = _source_completeness(count=12, official=ids, stored=ids,
                                  expectation=_expectation(12, 12))
    assert result['completeness_state'] == audit.SOURCE_COMPLETE
    assert result['conclusion_eligible'] is True
    assert result['current_count_matches_retained_expectation'] is True


def test_disagreeing_retained_counts_block_eligibility():
    ids = list(range(7001, 7013))
    result = _source_completeness(count=12, official=ids, stored=ids,
                                  expectation=_expectation(12, 11))
    assert result['completeness_state'] == (
        audit.SOURCE_EXPECTATION_INCONSISTENT
    )
    assert result['conclusion_eligible'] is False


def test_an_unusable_retained_expectation_blocks_eligibility():
    ids = list(range(7001, 7013))
    result = _source_completeness(
        count=12, official=ids, stored=ids,
        expectation=audit.retained_appearance_expectation({}))
    assert result['completeness_state'] == audit.SOURCE_EXPECTATION_UNPROVEN
    assert result['conclusion_eligible'] is False


def test_the_count_limitation_uses_the_actual_observed_and_expected_counts():
    six = list(range(7001, 7007))
    result = _source_completeness(count=6, official=six, stored=six,
                                  expectation=_expectation(12, 12))
    text = ' '.join(result['limitations'])
    assert 'yielded 6 appearances' in text
    assert 'recorded 12' in text
    # Bounded: it must NOT name a cause.
    lowered = text.lower()
    assert 'truncat' not in lowered
    assert 'correction' not in lowered or 'official correction' in lowered
    assert 'storage defect' not in lowered


# ── Duplicate identities (MEDIUM-H) ────────────────────────────────────────

def test_a_duplicate_stored_identity_has_its_own_state_and_prose():
    ids = list(range(7001, 7013))
    result = _source_completeness(count=12, official=ids, stored=ids,
                                  expectation=_expectation(12, 12),
                                  duplicates_stored=[7001])
    assert result['completeness_state'] == audit.SOURCE_DUPLICATE_STORED
    assert result['conclusion_eligible'] is False
    assert result['duplicate_stored_identities'] == [7001]
    assert result['duplicate_identity_count'] == 1
    text = ' '.join(result['limitations']).lower()
    assert 'stored-identity condition' in text
    assert 'truncated source payload' in text  # explicitly ruled OUT
    assert 'not a truncated source payload' in text


def test_a_duplicate_official_identity_has_its_own_state():
    ids = list(range(7001, 7013))
    result = _source_completeness(count=12, official=ids, stored=ids,
                                  expectation=_expectation(12, 12),
                                  duplicates_official=[7002])
    assert result['completeness_state'] == audit.SOURCE_DUPLICATE_OFFICIAL
    assert result['conclusion_eligible'] is False
    assert result['duplicate_official_identities'] == [7002]


def test_duplicates_on_both_sides_have_their_own_state():
    ids = list(range(7001, 7013))
    result = _source_completeness(count=12, official=ids, stored=ids,
                                  expectation=_expectation(12, 12),
                                  duplicates_official=[7002],
                                  duplicates_stored=[7001])
    assert result['completeness_state'] == audit.SOURCE_DUPLICATE_BOTH
    assert result['conclusion_eligible'] is False
    assert result['duplicate_identity_count'] == 2


def test_duplicate_states_never_borrow_the_truncation_explanation():
    ids = list(range(7001, 7013))
    for kwargs in ({'duplicates_stored': [7001]},
                   {'duplicates_official': [7002]},
                   {'duplicates_official': [7002], 'duplicates_stored': [7001]}):
        result = _source_completeness(count=12, official=ids, stored=ids,
                                      expectation=_expectation(12, 12),
                                      **kwargs)
        text = ' '.join(result['limitations']).lower()
        assert 'payload was truncated' not in text
        assert 'extraneous' not in text


# ── Reducer: nothing incomplete may complete ───────────────────────────────

_INELIGIBLE_STATES = [
    state for state in audit.SOURCE_COMPLETENESS_STATES
    if state not in audit.CONCLUSION_ELIGIBLE_STATES
]


@pytest.mark.parametrize('state', _INELIGIBLE_STATES)
def test_no_ineligible_state_reaches_any_completed_result(state):
    """Brute force over every completed classification combination."""
    for root in audit.ROOT_CONDITIONS:
        for materiality in audit.CURRENT_MATERIALITIES:
            for answer in (audit.DELTA_IDENTIFIED, audit.DELTA_NARROWED,
                           audit.DELTA_NOT_RECOVERABLE, audit.DELTA_UNPROVEN):
                decision = audit.decide(
                    classification={
                        'root_condition': root,
                        'current_materiality': materiality,
                        'current_source_completeness': state,
                    },
                    delta={'answer': answer}, lock=_gate_lock(),
                    questions=_gate_questions(),
                    source_completeness={
                        'completeness_state': state,
                        'conclusion_eligible': False,
                        'reason_codes': [
                            audit.UNPROVEN_CURRENT_COUNT_CONTRADICTS,
                        ],
                    })
                assert decision['result'] not in audit.COMPLETE_RESULTS
                assert decision['exit_code'] != 0


@pytest.mark.parametrize('supplied', [
    None, {}, {'completeness_state': 'x'}, {'conclusion_eligible': 1},
    {'conclusion_eligible': 'yes'}, 'not-a-mapping', 42, [],
])
def test_a_missing_or_malformed_completeness_object_cannot_exit_zero(supplied):
    """MEDIUM-G. No truthiness: only ``is True`` satisfies the gate."""
    decision = audit.decide(
        classification={
            'root_condition': audit.ROOT_OFFICIAL_SET_CHANGED,
            'current_materiality': audit.MATERIALITY_EXACT_MATCH,
        },
        delta={'answer': audit.DELTA_IDENTIFIED}, lock=_gate_lock(),
        questions=_gate_questions(), source_completeness=supplied)
    assert decision['result'] == audit.RESULT_UNPROVEN
    assert decision['exit_code'] == 2
    assert decision['current_source_conclusion_eligible'] is False


def test_an_authorization_failure_survives_a_missing_completeness_object():
    """FAILED still outranks, and BOTH facts stay visible."""
    decision = audit.decide(
        failed_reasons=[audit.FAILED_EXPECTED_SHA_MISMATCH],
    )
    assert decision['result'] == audit.RESULT_FAILED
    assert decision['exit_code'] == 1
    assert audit.FAILED_EXPECTED_SHA_MISMATCH in decision['failed_reasons']
    assert decision['current_source_conclusion_eligible'] is False
    assert decision['current_source_blocking_reasons']


def test_determinism_over_a_count_inconsistent_set_cannot_complete():
    six = list(range(7001, 7007))
    completeness = _source_completeness(count=6, official=six, stored=six,
                                        expectation=_expectation(12, 12))
    decision = audit.decide(
        classification={
            'root_condition': audit.ROOT_OFFICIAL_SET_CHANGED,
            'current_materiality': audit.MATERIALITY_EXACT_MATCH,
            'current_source_completeness': (
                completeness['completeness_state']
            ),
        },
        delta={'answer': audit.DELTA_IDENTIFIED}, lock=_gate_lock(),
        questions=_gate_questions(), source_completeness=completeness)
    assert decision['result'] == audit.RESULT_UNPROVEN
    assert decision['exit_code'] == 2


def test_the_new_consequences_are_in_the_declared_vocabulary():
    assert audit.CONSEQUENCE_COUNT_CONSISTENCY_REVIEW in audit.CONSEQUENCES
    assert audit.CONSEQUENCE_IDENTITY_REVIEW in audit.CONSEQUENCES


def test_a_count_contradiction_never_recommends_continued_observation():
    supported = audit.operational_consequence({
        'current_materiality': audit.MATERIALITY_UNPROVEN,
        'current_source_completeness': audit.SOURCE_COUNT_CONTRADICTS,
    })['supported_by_evidence']
    assert audit.CONSEQUENCE_CONTINUED_OBSERVATION not in supported
    assert audit.CONSEQUENCE_COUNT_CONSISTENCY_REVIEW in supported


def test_a_duplicate_identity_recommends_identity_review():
    supported = audit.operational_consequence({
        'current_materiality': audit.MATERIALITY_UNPROVEN,
        'current_source_completeness': audit.SOURCE_DUPLICATE_STORED,
    })['supported_by_evidence']
    assert audit.CONSEQUENCE_CONTINUED_OBSERVATION not in supported
    assert audit.CONSEQUENCE_IDENTITY_REVIEW in supported


def test_the_new_reason_codes_are_declared():
    for reason in (
        audit.UNPROVEN_CURRENT_COUNT_CONTRADICTS,
        audit.UNPROVEN_RETAINED_EXPECTATION_UNAVAILABLE,
        audit.UNPROVEN_RETAINED_COUNTS_DISAGREE,
        audit.UNPROVEN_DUPLICATE_APPEARANCE_IDENTITY,
    ):
        assert reason in audit.UNPROVEN_REASONS
