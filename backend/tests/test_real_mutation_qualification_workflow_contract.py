"""The real-mutation workflows' governance contract, asserted from the YAML.

A workflow that holds production credentials and can mutate baseball data is a
security boundary, not merely configuration. Every property that makes it safe
is asserted here so a future edit that removes one fails CI instead of shipping.

The shell boundary is the most important of these. GitHub substitutes `${{ }}`
expressions into a `run:` script BEFORE bash parses it, so an expression holding
operator input inside a credentialed step becomes shell code. Every input must
cross into the shell through `env:` and be read only as a quoted variable.
"""

import pathlib
import re

import pytest
import yaml

from services import real_mutation_candidate_audit as audit
from services import real_mutation_qualification as qualification


REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / '.github' / 'workflows'
QUALIFICATION = WORKFLOWS / (
    'manual-game-driven-real-mutation-qualification.yml'
)
CANDIDATE_AUDIT = WORKFLOWS / 'manual-real-mutation-candidate-audit.yml'

ALL = (QUALIFICATION, CANDIDATE_AUDIT)


def load(path):
    # `on` parses as the boolean True under the YAML 1.1 rules PyYAML follows.
    return yaml.safe_load(path.read_text(encoding='utf-8'))


def triggers(document):
    return document.get('on', document.get(True))


def steps(document, job):
    return document['jobs'][job]['steps']


@pytest.fixture
def qualification_doc():
    return load(QUALIFICATION)


@pytest.fixture
def audit_doc():
    return load(CANDIDATE_AUDIT)


# ── Both workflows exist and are manual only ────────────────────────────────


@pytest.mark.parametrize('path', ALL)
def test_the_workflow_exists(path):
    assert path.is_file()


@pytest.mark.parametrize('path', ALL)
def test_workflow_dispatch_is_the_only_trigger(path):
    document = load(path)
    assert set(triggers(document)) == {'workflow_dispatch'}


@pytest.mark.parametrize('path', ALL)
@pytest.mark.parametrize('forbidden', [
    'schedule', 'push', 'pull_request', 'workflow_run', 'repository_dispatch',
    'workflow_call', 'issue_comment', 'release',
])
def test_no_automatic_trigger_exists(path, forbidden):
    assert forbidden not in triggers(load(path))


@pytest.mark.parametrize('path', ALL)
def test_the_job_is_gated_on_repository_ref_actor_and_event(path):
    document = load(path)
    for job in document['jobs'].values():
        condition = job['if']
        assert "github.event_name == 'workflow_dispatch'" in condition
        assert (
            "github.repository == 'NickolisK24/bullpen-intel-engine'"
            in condition
        )
        assert "github.ref == 'refs/heads/main'" in condition
        assert 'github.actor == github.repository_owner' in condition


@pytest.mark.parametrize('path', ALL)
def test_the_production_writer_lane_is_shared_and_never_cancelled(path):
    document = load(path)
    assert document['concurrency']['group'] == 'baseballos-sync'
    assert document['concurrency']['cancel-in-progress'] is False


@pytest.mark.parametrize('path', ALL)
def test_permissions_are_read_only(path):
    assert load(path)['permissions'] == {'contents': 'read'}


# ── The shell boundary ──────────────────────────────────────────────────────


@pytest.mark.parametrize('path', ALL)
def test_no_expression_is_interpolated_into_any_run_script(path):
    document = load(path)
    for job in document['jobs'].values():
        for step in job['steps']:
            script = step.get('run')
            if not script:
                continue
            assert '${{' not in script, (
                f"{path.name}: step {step.get('name')!r} interpolates a "
                'GitHub expression into its shell script'
            )


@pytest.mark.parametrize('path', ALL)
def test_every_input_reaches_the_shell_through_env(path):
    document = load(path)
    declared = set(triggers(document)['workflow_dispatch']['inputs'])
    piped = set()
    for job in document['jobs'].values():
        for step in job['steps']:
            for value in (step.get('env') or {}).values():
                match = re.search(r'inputs\.([a-z_]+)', str(value))
                if match:
                    piped.add(match.group(1))
    assert declared <= piped


@pytest.mark.parametrize('path', ALL)
def test_operator_input_is_read_only_as_a_quoted_variable(path):
    text = path.read_text(encoding='utf-8')
    for name in re.findall(r'\b(INPUT_[A-Z_]+)\b', text):
        # Every use inside a script is quoted; the only unquoted appearances
        # are the env: declarations themselves.
        for use in re.findall(rf'[^A-Z_"]\${{{name}}}', text):
            raise AssertionError(f'{path.name}: unquoted use of {name}')


# ── Qualification-specific authorization ────────────────────────────────────


def test_the_qualification_requires_the_four_authorization_inputs(
    qualification_doc,
):
    inputs = triggers(qualification_doc)['workflow_dispatch']['inputs']
    for name in (
        'game_pk', 'expected_head_sha', 'reviewed_plan_fingerprint',
        'confirmation',
    ):
        assert inputs[name]['required'] is True


def test_the_operator_note_is_optional_and_never_authorization_bearing(
    qualification_doc,
):
    inputs = triggers(qualification_doc)['workflow_dispatch']['inputs']
    assert inputs['operator_note']['required'] is False
    precheck = steps(qualification_doc, 'real-mutation-qualification')[0]['run']
    # It is length-reported and never compared, tested, or evaluated.
    assert 'wc -c' in precheck
    assert 'INPUT_OPERATOR_NOTE" =' not in precheck


def test_the_qualification_refuses_a_non_singular_game_scope(
    qualification_doc,
):
    precheck = steps(qualification_doc, 'real-mutation-qualification')[0]['run']
    assert "grep -Eq '^[1-9][0-9]*$'" in precheck


def test_the_qualification_requires_a_full_lowercase_sha(qualification_doc):
    precheck = steps(qualification_doc, 'real-mutation-qualification')[0]['run']
    assert "grep -Eq '^[0-9a-f]{40}$'" in precheck
    assert 'INPUT_EXPECTED_HEAD_SHA" != "$RESOLVED_SHA"' in precheck


def test_the_qualification_requires_a_full_lowercase_fingerprint(
    qualification_doc,
):
    precheck = steps(qualification_doc, 'real-mutation-qualification')[0]['run']
    assert "grep -Eq '^[0-9a-f]{64}$'" in precheck


def test_the_confirmation_string_is_the_real_mutation_one(qualification_doc):
    precheck = steps(qualification_doc, 'real-mutation-qualification')[0]['run']
    assert 'QUALIFY_REAL_MUTATION_GAME_${INPUT_GAME_PK}' in precheck
    assert qualification.CONFIRMATION_PREFIX == 'QUALIFY_REAL_MUTATION_GAME_'


def test_the_audit_confirmation_string_matches_its_service(audit_doc):
    precheck = steps(audit_doc, 'candidate-audit')[0]['run']
    assert audit.CONFIRMATION in precheck
    assert audit.CONFIRMATION == 'AUDIT_REAL_MUTATION_CANDIDATES'


# ── Scope and authority the workflow may never widen ────────────────────────


def test_the_qualification_offers_no_backfill_or_authoritative_input(
    qualification_doc,
):
    inputs = triggers(qualification_doc)['workflow_dispatch']['inputs']
    for forbidden in (
        'backfill', 'include_backfill', 'mode', 'authoritative',
        'publication', 'game_pks', 'games',
    ):
        assert forbidden not in inputs


def test_the_lane_mode_is_never_set_in_the_workflow_environment(
    qualification_doc,
):
    """The qualification supplies the mode per phase, in code."""
    for step in steps(qualification_doc, 'real-mutation-qualification'):
        assert 'GAME_DRIVEN_INGESTION_MODE' not in (step.get('env') or {})


def test_auto_sync_is_disabled_on_the_credentialed_step(qualification_doc):
    step = _step_by_id(qualification_doc, 'real-mutation-qualification',
                       'qualification')
    assert step['env']['AUTO_SYNC'] == 'false'


def _step_by_id(document, job, step_id):
    for step in steps(document, job):
        if step.get('id') == step_id:
            return step
    raise AssertionError(f'no step with id {step_id!r}')


def test_only_the_qualification_step_carries_production_credentials(
    qualification_doc,
):
    credentialed = [
        step.get('id') for step in steps(
            qualification_doc, 'real-mutation-qualification',
        )
        if 'DATABASE_URL' in (step.get('env') or {})
    ]
    assert credentialed == ['qualification']


def test_the_audit_carries_no_publication_credential(audit_doc):
    for step in steps(audit_doc, 'candidate-audit'):
        env = step.get('env') or {}
        assert 'BASEBALLOS_SYNC_URL' not in env
        assert 'PUBLICATION_TOKEN' not in env


# ── Evidence ordering ───────────────────────────────────────────────────────


@pytest.mark.parametrize('path,job', [
    (QUALIFICATION, 'real-mutation-qualification'),
    (CANDIDATE_AUDIT, 'candidate-audit'),
])
def test_the_artifact_is_scanned_before_it_is_uploaded(path, job):
    ids = [step.get('id') for step in steps(load(path), job)]
    assert ids.index('scan') < ids.index('upload')


@pytest.mark.parametrize('path,job', [
    (QUALIFICATION, 'real-mutation-qualification'),
    (CANDIDATE_AUDIT, 'candidate-audit'),
])
def test_an_unsafe_artifact_is_never_uploaded(path, job):
    upload = _step_by_id(load(path), job, 'upload')
    assert "steps.scan.outcome == 'success'" in upload['if']


@pytest.mark.parametrize('path,job', [
    (QUALIFICATION, 'real-mutation-qualification'),
    (CANDIDATE_AUDIT, 'candidate-audit'),
])
def test_a_failing_run_still_preserves_its_evidence(path, job):
    """continue-on-error on the run step is what lets the scan and upload run."""
    document = load(path)
    ids = [step.get('id') for step in steps(document, job)]
    runner = 'qualification' if job == 'real-mutation-qualification' else 'audit'
    assert _step_by_id(document, job, runner)['continue-on-error'] is True
    assert ids.index(runner) < ids.index('scan')
    summary = [
        step for step in steps(document, job)
        if 'summary' in (step.get('name') or '').lower()
    ]
    assert summary and 'always()' in summary[0]['if']


@pytest.mark.parametrize('path,job', [
    (QUALIFICATION, 'real-mutation-qualification'),
    (CANDIDATE_AUDIT, 'candidate-audit'),
])
def test_the_final_gate_runs_last(path, job):
    names = [step.get('name') for step in steps(load(path), job)]
    assert 'gate' in names[-1].lower()


@pytest.mark.parametrize('path,job', [
    (QUALIFICATION, 'real-mutation-qualification'),
    (CANDIDATE_AUDIT, 'candidate-audit'),
])
def test_a_missing_scan_or_upload_fails_the_gate(path, job):
    gate = steps(load(path), job)[-1]['run']
    assert 'SCAN_OUTCOME" != "success"' in gate
    assert 'UPLOAD_OUTCOME" != "success"' in gate
    assert gate.count('exit 1') >= 2


@pytest.mark.parametrize('path,job,retention', [
    (QUALIFICATION, 'real-mutation-qualification', 30),
    (CANDIDATE_AUDIT, 'candidate-audit', 30),
])
def test_the_artifact_is_retained_and_fails_when_empty(path, job, retention):
    upload = _step_by_id(load(path), job, 'upload')
    assert upload['with']['retention-days'] == retention
    assert upload['with']['if-no-files-found'] == 'error'


def test_the_qualification_artifact_is_named_for_its_run(qualification_doc):
    upload = _step_by_id(
        qualification_doc, 'real-mutation-qualification', 'upload',
    )
    assert upload['with']['name'] == (
        'game-driven-real-mutation-qualification-${{ github.run_id }}'
    )


# ── The runner the workflow invokes ─────────────────────────────────────────


def test_the_qualification_invokes_its_own_runner_with_every_input(
    qualification_doc,
):
    script = _step_by_id(
        qualification_doc, 'real-mutation-qualification', 'qualification',
    )['run']
    assert 'run_game_driven_real_mutation_qualification.py' in script
    for flag in (
        '--game-pk', '--expected-head-sha', '--reviewed-plan-fingerprint',
        '--confirmation', '--operator-note', '--artifact-dir',
    ):
        assert flag in script


def test_the_audit_invokes_its_own_runner(audit_doc):
    script = _step_by_id(audit_doc, 'candidate-audit', 'audit')['run']
    assert 'run_real_mutation_candidate_audit.py' in script


def test_the_qualification_exits_with_the_runners_own_code(qualification_doc):
    script = _step_by_id(
        qualification_doc, 'real-mutation-qualification', 'qualification',
    )['run']
    assert 'exit "$exit_code"' in script


# ── Non-authorization language ──────────────────────────────────────────────


def test_the_qualification_gate_states_what_a_pass_does_not_grant(
    qualification_doc,
):
    gate = steps(
        qualification_doc, 'real-mutation-qualification',
    )[-1]['run'].lower()
    for phrase in (
        'scheduled writes', 'automated writes', 'authoritative publication',
        'backfill', 'multiple-game', 'identity mutation', 'o-008',
    ):
        assert phrase in gate


def test_the_audit_gate_states_that_it_authorizes_nothing(audit_doc):
    gate = steps(audit_doc, 'candidate-audit')[-1]['run'].lower()
    assert 'authorizes nothing' in gate
    assert 're-reviewed by the qualification' in gate
