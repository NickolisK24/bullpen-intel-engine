"""Game 824487 checkpoint repair — evidence artifacts.

The artifact is what a reviewer reads. These tests own the properties that make
it reviewable and safe: every file is written under every outcome, the mutation
ledger exists even when nothing was written, the permitted-column disclosure is
present, and nothing that could leak — a raw payload, a database URL, a token,
an exception message, a SQL statement, a connection string — ever reaches it.

They also enforce the repository's forbidden-content scanner against the real
artifact directory, so the workflow's pre-upload gate is exercised here rather
than trusted.
"""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from services import game_source_revision_checkpoint_repair as repair
from scripts import run_game_source_revision_checkpoint_repair as runner


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCANNER = BACKEND_ROOT / 'scripts/scan_forbidden_artifact_content.py'

EXPECTED_FILES = runner.ARTIFACT_FILES


def _document(**overrides):
    """A document produced by the real builder, not a hand-written stub."""
    payload = {
        'context': {
            'event_name': 'workflow_dispatch',
            'repository': repair.REQUIRED_REPOSITORY,
            'actor': repair.REQUIRED_ACTOR,
            'ref': repair.REQUIRED_REF,
            'commit_sha': 'f' * 40,
            'workflow': 'Manual Game 824487 Source Revision Checkpoint Repair',
            'workflow_run_id': '1',
            'workflow_run_attempt': '1',
        },
        'note': '',
        'operation': 'verify',
        'target': {},
        'official': {},
        'comparison': {},
        'plan': {},
        'expectation': {},
        'completeness': {},
        'preconditions': {},
        'read_only': {},
        'lock': {},
        'fingerprints': {},
        'mutation': {},
        'apply_state': {},
        'source_calls': {},
        'decision': repair.decide(operation='verify'),
    }
    payload.update(overrides)
    return runner.build_document(**payload)


def _evaluation(violated=()):
    """A fully-covered precondition evaluation.

    The reducer's completion gate refuses to classify a partial evaluation at
    all, so a test that wants a REFUSED verdict has to supply real coverage —
    which is the point of the gate.
    """
    violated = set(violated)
    return {'preconditions': [
        repair.precondition(
            identifier, requirement='r',
            state=(
                repair.PRECONDITION_VIOLATED if identifier in violated
                else repair.PRECONDITION_SATISFIED
            ),
        )
        for identifier in repair.PRECONDITION_IDS
    ]}


def _refused(operation='apply'):
    return repair.decide(
        operation=operation,
        preconditions=_evaluation({repair.PRE_ROW_EXISTS}),
    )


@pytest.fixture
def artifact_dir(tmp_path):
    return tmp_path / 'game-824487-checkpoint-repair'


def _write(document, artifact_dir, rows=()):
    runner.write_artifacts(document, list(rows), str(artifact_dir))
    return artifact_dir


# ── Every file, under every outcome ─────────────────────────────────────────

@pytest.mark.parametrize('operation', list(repair.OPERATIONS))
def test_every_artifact_file_is_written_under_every_outcome(
    artifact_dir, operation,
):
    for decision in (
        repair.decide(operation=operation),
        repair.decide(
            operation=operation,
            failed_reasons=[repair.FAILED_MUTATION_SCOPE_EXCEEDED],
        ),
        _refused(operation),
    ):
        _write(_document(operation=operation, decision=decision), artifact_dir)
        for name in EXPECTED_FILES:
            path = artifact_dir / name
            assert path.is_file(), name
            assert path.read_text(encoding='utf-8').strip()


def test_the_json_document_is_parseable_and_carries_its_schema_version(
    artifact_dir,
):
    _write(_document(), artifact_dir)
    payload = json.loads(
        (artifact_dir / runner.SUMMARY_JSON).read_text(encoding='utf-8')
    )
    assert payload['schema_version'] == repair.SCHEMA_VERSION
    assert payload['repair_type'] == repair.REPAIR_TYPE
    assert payload['scope']['game_pk'] == repair.GAME_PK
    assert payload['scope']['target_column'] == repair.TARGET_COLUMN


def test_the_document_never_carries_the_internal_comparison_rows(artifact_dir):
    """The rows travel in their own file, never duplicated here."""
    document = _document()
    rows = document.pop('_comparison_rows')
    _write(document, artifact_dir, rows)
    payload = json.loads(
        (artifact_dir / runner.SUMMARY_JSON).read_text(encoding='utf-8')
    )
    assert '_comparison_rows' not in payload


def test_the_mutation_ledger_exists_even_when_nothing_was_written(
    artifact_dir,
):
    """"No ledger" must never be ambiguous between "did not run" and "wrote
    nothing"."""
    _write(_document(), artifact_dir)
    ledger = json.loads(
        (artifact_dir / runner.MUTATION_LEDGER_JSON).read_text(
            encoding='utf-8'
        )
    )
    assert ledger['table'] == repair.TARGET_TABLE
    assert ledger['column'] == repair.TARGET_COLUMN
    assert ledger['apply_attempted'] is False
    assert ledger['committed'] is None
    assert ledger['intended_value'] == repair.INTENDED_SOURCE_REVISION
    assert ledger['expected_old_value'] == (
        repair.EXPECTED_EXISTING_SOURCE_REVISION
    )
    assert ledger['permitted_changed_columns'] == [
        'source_revision', 'updated_at',
    ]
    assert ledger['prohibited_mutations']


def test_the_preconditions_file_publishes_the_whole_requirement_model(
    artifact_dir,
):
    """A reader can check the package's requirements against its results."""
    _write(_document(), artifact_dir)
    payload = json.loads(
        (artifact_dir / runner.PRECONDITIONS_JSON).read_text(encoding='utf-8')
    )
    assert payload['precondition_ids'] == list(repair.PRECONDITION_IDS)
    assert payload['precondition_states'] == list(repair.PRECONDITION_STATES)
    assert set(payload['refusal_reason_by_precondition']) == set(
        repair.PRECONDITION_IDS
    )
    assert set(payload['unproven_reason_by_precondition']) == set(
        repair.PRECONDITION_IDS
    )
    # The whole reason vocabulary and the specification map travel with it,
    # so a reviewer can check a listed condition without reading the source.
    assert payload['specified_condition_to_reason_code'] == dict(
        repair.SPECIFIED_REASON_CODES
    )
    assert set(payload['failed_reasons']) == set(repair.FAILED_REASONS)
    assert set(payload['unproven_reasons']) == set(repair.UNPROVEN_REASONS)
    assert set(payload['refusal_reasons']) == set(repair.REFUSED_REASONS)


def test_the_artifact_filenames_are_the_reviewed_names(artifact_dir):
    _write(_document(), artifact_dir)
    assert sorted(path.name for path in artifact_dir.iterdir()) == sorted(
        runner.ARTIFACT_FILES
    )
    for name in runner.ARTIFACT_FILES:
        assert name.startswith('game-824487-source-revision-checkpoint-repair')


def test_the_proof_file_carries_the_read_only_and_lock_evidence(artifact_dir):
    _write(_document(), artifact_dir)
    payload = json.loads(
        (artifact_dir / runner.PROOF_JSON).read_text(encoding='utf-8')
    )
    for key in (
        'read_only_proof', 'advisory_lock', 'source_call_report',
        'prohibited_mutations', 'permitted_changed_columns',
        'standing_production_state', 'non_authorization_statement',
    ):
        assert key in payload, key


def test_the_fingerprint_file_carries_both_scopes(artifact_dir):
    _write(_document(), artifact_dir)
    payload = json.loads(
        (artifact_dir / runner.FINGERPRINTS_JSON).read_text(encoding='utf-8')
    )
    assert 'fingerprints' in payload
    assert 'scope_evaluation' in payload
    assert payload['out_of_scope_table'] == repair.OUT_OF_SCOPE_TABLE


def test_the_ledger_carries_every_governed_field(artifact_dir):
    """§16: a ledger a reviewer can read without correlating other files."""
    _write(_document(), artifact_dir)
    ledger = json.loads(
        (artifact_dir / runner.MUTATION_LEDGER_JSON).read_text(
            encoding='utf-8'
        )
    )
    for key in (
        'operation', 'model', 'table', 'column', 'target_row_identity',
        'game_pk', 'represented_date', 'observed_value_before',
        'observed_value_after', 'proposed_value', 'affected_row_count',
        'commits_performed', 'rollback_performed', 'mutation_status',
        'mutation_timestamp', 'workflow_run_id', 'main_sha', 'actor',
        'operator_note', 'advisory_lock_state', 'transaction_state',
    ):
        assert key in ledger, key


def test_the_comparison_file_carries_its_rows_and_its_gates(artifact_dir):
    document = _document()
    rows = [{'pitcher_mlb_id': 1, 'field_name': 'strikeouts'}]
    _write(document, artifact_dir, rows)
    payload = json.loads(
        (artifact_dir / runner.COMPARISON_JSON).read_text(encoding='utf-8')
    )
    assert payload['game_pk'] == repair.GAME_PK
    assert payload['rows'] == rows
    assert 'current_source_completeness' in payload
    assert 'population_expectation' in payload


# ── Markdown ────────────────────────────────────────────────────────────────

def test_the_markdown_summary_carries_every_required_section(artifact_dir):
    _write(_document(), artifact_dir)
    text = (artifact_dir / runner.SUMMARY_MARKDOWN).read_text(encoding='utf-8')
    for section in runner.REQUIRED_MARKDOWN_SECTIONS:
        assert section in text, section


def test_the_markdown_numbers_its_fifteen_sections(artifact_dir):
    _write(_document(), artifact_dir)
    text = (artifact_dir / runner.SUMMARY_MARKDOWN).read_text(encoding='utf-8')
    for index in range(1, 16):
        assert f'## {index}. ' in text, index


def test_the_markdown_discloses_the_updated_at_side_effect(artifact_dir):
    _write(_document(), artifact_dir)
    text = (artifact_dir / runner.SUMMARY_MARKDOWN).read_text(encoding='utf-8')
    assert 'updated_at' in text
    assert 'onupdate' in text
    assert 'automatic bookkeeping side effect' in text


def test_the_markdown_states_the_result_and_the_non_authorization(
    artifact_dir,
):
    decision = _refused()
    assert decision['result'] == repair.RESULT_REFUSED
    _write(_document(operation='apply', decision=decision), artifact_dir)
    text = (artifact_dir / runner.SUMMARY_MARKDOWN).read_text(encoding='utf-8')
    assert repair.RESULT_REFUSED in text
    assert repair.REFUSED_WORK_ITEM_MISSING in text
    assert 'authorizes nothing' in text


def test_the_markdown_lists_every_prohibited_mutation(artifact_dir):
    _write(_document(), artifact_dir)
    text = (artifact_dir / runner.SUMMARY_MARKDOWN).read_text(encoding='utf-8')
    for prohibited in repair.PROHIBITED_MUTATIONS:
        assert prohibited in text


# ── Nothing unsafe reaches the artifact ─────────────────────────────────────

UNSAFE = (
    'postgresql://', 'postgres://', 'password=', 'Bearer ',
    'Authorization:', 'ADMIN_API_TOKEN', 'SECRET_KEY', 'DATABASE_URL',
    'Traceback (most recent call last)', 'psycopg2.', 'sqlalchemy.exc.',
    'UPDATE game_', 'SELECT ', 'INSERT INTO',
)


def test_no_artifact_file_carries_a_credential_statement_or_stack_trace(
    artifact_dir,
):
    _write(_document(), artifact_dir)
    for name in EXPECTED_FILES:
        text = (artifact_dir / name).read_text(encoding='utf-8')
        for needle in UNSAFE:
            assert needle not in text, f'{name}: {needle}'


def test_the_statement_report_carries_a_class_and_a_count_never_sql():
    """Safe summaries apply to SQL exactly as they apply to exceptions."""
    watch = repair.StatementWatch(engine=None)
    watch.write_statements = [{
        'statement_class': 'UPDATE',
        'rowcount': 1,
        'names_target_table': True,
        'executemany': False,
    }]
    report = json.dumps(watch.as_dict())
    assert 'UPDATE' in report
    assert 'game_ingestion_work_items SET' not in report
    assert 'WHERE' not in report


def test_a_sanitized_operator_note_can_never_carry_shell_metacharacters():
    note = runner.sanitize_note('rm -rf `whoami` $HOME \\x00 ' + 'x' * 500)
    assert '`' not in note
    assert '$' not in note
    assert '\\' not in note
    assert len(note) <= runner.MAX_NOTE_LENGTH


def test_the_operator_note_reaches_the_document_but_no_verdict(artifact_dir):
    document = _document(note=runner.sanitize_note('a routine note'))
    _write(document, artifact_dir)
    payload = json.loads(
        (artifact_dir / runner.SUMMARY_JSON).read_text(encoding='utf-8')
    )
    assert payload['identity']['operator_note'] == 'a routine note'
    assert 'operator_note' not in json.dumps(payload['verdict'])


# ── The committed-but-proof-failed artifact ─────────────────────────────────
#
# The one outcome where an artifact could actively mislead: the production row
# HAS moved, and the run reports FAILED. A reader who takes FAILED to mean
# "nothing happened" would draw the opposite of the truth, so the artifact has
# to carry the durable facts louder than the verdict.

def _proof_failed_apply_state():
    """The state apply_repair returns after a post-commit read-only failure."""
    state = runner.new_apply_state()
    state.update({
        'attempted': True,
        'row_locked': True,
        'lock_available': True,
        'revalidated': True,
        'committed': True,
        'commit_attempted': True,
        'commit_count': 1,
        'affected_row_count': 1,
        'before_snapshot': {
            repair.TARGET_COLUMN: repair.EXPECTED_EXISTING_SOURCE_REVISION,
        },
        'in_transaction_value': repair.INTENDED_SOURCE_REVISION,
        'in_transaction_value_is_intended': True,
        'post_commit_verification_attempted': True,
        'post_commit_read_only_attempted': True,
        'post_commit_transaction_read_only': False,
        'post_commit_read_only_reason': 'read_only_setup_failed',
        'post_commit_verification_completed': False,
        'post_commit_verification_transaction_rollback_succeeded': True,
        'failed_reasons': [repair.FAILED_POST_COMMIT_READ_ONLY_PROOF],
    })
    return state


def _proof_failed_document():
    state = _proof_failed_apply_state()
    return _document(
        operation='apply',
        apply_state=state,
        preconditions=_evaluation(),
        decision=repair.decide(
            operation='apply', preconditions=_evaluation(),
            apply_attempted=True, apply_committed=True,
            failed_reasons=state['failed_reasons'], post_commit=state,
        ),
    )


def test_the_proof_failed_verdict_is_failed_at_exit_one(artifact_dir):
    document = _proof_failed_document()
    verdict = document['verdict']
    assert verdict['result'] == repair.RESULT_FAILED
    assert verdict['exit_code'] == 1
    assert verdict['mutation_performed'] is True
    assert verdict['apply_committed'] is True
    assert repair.FAILED_POST_COMMIT_READ_ONLY_PROOF in (
        verdict['failed_reasons']
    )


def test_the_proof_failed_ledger_keeps_every_durable_fact(artifact_dir):
    _write(_proof_failed_document(), artifact_dir)
    ledger = json.loads(
        (artifact_dir / runner.MUTATION_LEDGER_JSON).read_text(
            encoding='utf-8'
        )
    )
    assert ledger['committed'] is True
    assert ledger['commits_performed'] == 1
    assert ledger['affected_row_count'] == 1
    assert ledger['mutation_performed'] is True
    assert ledger['mutation_status'] == repair.RESULT_FAILED
    assert ledger['post_commit_verification_attempted'] is True
    assert ledger['post_commit_read_only_attempted'] is True
    assert ledger['post_commit_transaction_read_only'] is False
    assert ledger['post_commit_read_only_reason'] == 'read_only_setup_failed'
    assert ledger['post_commit_verification_completed'] is False
    assert ledger['observed_value_before'] == (
        repair.EXPECTED_EXISTING_SOURCE_REVISION
    )
    assert ledger['intended_value'] == repair.INTENDED_SOURCE_REVISION
    assert ledger['in_transaction_value'] == repair.INTENDED_SOURCE_REVISION
    # Not observed, therefore absent — never back-filled from the intended
    # literal, which would turn an assumption into a reported observation.
    assert ledger['observed_value_after'] is None
    assert ledger['post_commit_row_count'] is None
    assert ledger['post_commit_value_is_intended'] is None
    # The cleanup rollback cleared the verification transaction. It is
    # recorded as exactly that, and never as reversing the repair.
    assert ledger['rollback_performed'] is False
    assert ledger['transaction_state'][
        'post_commit_verification_transaction_rollback_succeeded'
    ] is True


def test_the_proof_failed_markdown_says_it_in_words(artifact_dir):
    _write(_proof_failed_document(), artifact_dir)
    markdown = (artifact_dir / runner.SUMMARY_MARKDOWN).read_text(
        encoding='utf-8'
    )
    assert '**FAILED** (exit 1)' in markdown
    assert 'The repair COMMITTED.' in markdown
    assert 'durable' in markdown
    assert 'Nothing was rolled back' in markdown
    assert f'- FAILED: `{repair.FAILED_POST_COMMIT_READ_ONLY_PROOF}`' in (
        markdown
    )
    for absent in (
        'apply_outcome_unknown', 'REPAIR_APPLIED', 'Traceback', 'psycopg2',
    ):
        assert absent not in markdown, absent


def test_a_proven_post_commit_lifecycle_gets_no_such_narrative(artifact_dir):
    """The warning appears only where it is true."""
    state = _proof_failed_apply_state()
    state.update({
        'post_commit_transaction_read_only': True,
        'post_commit_read_only_reason': 'established',
        'post_commit_verification_completed': True,
        'post_commit_row_count': 1,
        'post_commit_value_is_intended': True,
        'after_snapshot': {
            repair.TARGET_COLUMN: repair.INTENDED_SOURCE_REVISION,
        },
        'failed_reasons': [],
    })
    document = _document(
        operation='apply', apply_state=state, preconditions=_evaluation(),
        decision=repair.decide(
            operation='apply', preconditions=_evaluation(),
            apply_attempted=True, apply_committed=True, post_commit=state,
        ),
    )
    assert document['verdict']['result'] == repair.RESULT_APPLIED
    _write(document, artifact_dir)
    markdown = (artifact_dir / runner.SUMMARY_MARKDOWN).read_text(
        encoding='utf-8'
    )
    assert 'The repair COMMITTED.' not in markdown


def _skipped_observation_document():
    """The document a committed-but-proof-failed run now produces."""
    state = _proof_failed_apply_state()
    return _document(
        operation='apply',
        apply_state=state,
        preconditions=_evaluation(),
        mutation=(
            repair.committed_mutation_evidence_without_post_commit_proof(
                state
            )
        ),
        fingerprints={
            'before': {'exact_game_824487': {}},
            'after_apply': None,
            'out_of_scope_before': {'rows': 1},
            'out_of_scope_after_apply': None,
            'post_commit_proof_complete': False,
            'post_apply_fingerprint_collection_attempted': False,
            'post_apply_fingerprints_observed': False,
            'post_apply_out_of_scope_fingerprint_observed': False,
            'post_apply_observation_skip_reason': (
                repair.POST_COMMIT_OBSERVATION_SKIPPED
            ),
        },
        decision=repair.decide(
            operation='apply', preconditions=_evaluation(),
            apply_attempted=True, apply_committed=True,
            failed_reasons=state['failed_reasons'], post_commit=state,
        ),
    )


def test_the_failure_artifact_marks_the_skipped_observation_explicitly(
    artifact_dir,
):
    _write(_skipped_observation_document(), artifact_dir)
    document = json.loads(
        (artifact_dir / runner.SUMMARY_JSON).read_text(encoding='utf-8')
    )
    fingerprints = document['fingerprints']
    assert fingerprints['post_commit_proof_complete'] is False
    assert fingerprints[
        'post_apply_fingerprint_collection_attempted'
    ] is False
    assert fingerprints['post_apply_fingerprints_observed'] is False
    assert fingerprints[
        'post_apply_out_of_scope_fingerprint_observed'
    ] is False
    assert fingerprints['post_apply_observation_skip_reason'] == (
        'post_commit_proof_incomplete'
    )

    ledger = json.loads(
        (artifact_dir / runner.MUTATION_LEDGER_JSON).read_text(
            encoding='utf-8'
        )
    )
    assert ledger['post_commit_proof_complete'] is False
    assert ledger['post_apply_scope_evaluation_completed'] is False
    assert ledger['post_apply_observation_skip_reason'] == (
        'post_commit_proof_incomplete'
    )


def test_the_failure_artifact_fabricates_no_post_apply_evidence(artifact_dir):
    """Unobserved must never be serialized as observed-and-clean."""
    _write(_skipped_observation_document(), artifact_dir)
    ledger = json.loads(
        (artifact_dir / runner.MUTATION_LEDGER_JSON).read_text(
            encoding='utf-8'
        )
    )
    evaluation = ledger['scope_evaluation']
    for field in (
        'changed_fingerprint_tables',
        'unexpected_changed_fingerprint_tables',
        'out_of_scope_unchanged',
        'mutation_within_scope',
        'observed_changed_columns',
        'post_state_is_intended_revision',
    ):
        assert evaluation[field] is None, field
    assert evaluation['changed_fingerprint_tables_observed'] is False
    assert evaluation['out_of_scope_fingerprint_observed'] is False
    assert evaluation['failed_reasons'] == []

    blob = '\n'.join(
        path.read_text(encoding='utf-8') for path in artifact_dir.iterdir()
    )
    # The specific false shapes: an empty changed-table list read as "nothing
    # moved", and the two accusations the real evaluator invents from a
    # missing after-snapshot.
    assert '"changed_fingerprint_tables": []' not in blob
    assert '"out_of_scope_unchanged": true' not in blob
    assert '"mutation_within_scope": true' not in blob
    # Scoped to what the run CLAIMS, not to the published reason vocabulary,
    # which legitimately lists every code the package can ever emit.
    document = json.loads(
        (artifact_dir / runner.SUMMARY_JSON).read_text(encoding='utf-8')
    )
    emitted = json.dumps(document['verdict']) + json.dumps(evaluation)
    assert repair.FAILED_MUTATION_SCOPE_EXCEEDED not in emitted
    assert repair.FAILED_POST_STATE_NOT_INTENDED not in emitted
    assert repair.FAILED_POST_COMMIT_READ_ONLY_PROOF in emitted
    assert ledger['after_snapshot'] is None
    assert ledger['observed_value_after'] is None


def test_the_failure_markdown_says_the_reads_were_skipped_and_why(
    artifact_dir,
):
    _write(_skipped_observation_document(), artifact_dir)
    markdown = (artifact_dir / runner.SUMMARY_MARKDOWN).read_text(
        encoding='utf-8'
    )
    assert '**FAILED** (exit 1)' in markdown
    assert 'The repair COMMITTED.' in markdown
    assert 'Nothing was rolled back' in markdown
    assert 'deliberately **not collected**' in markdown
    assert 'UNOBSERVED, not unchanged' in markdown
    assert 'Run `verify`' in markdown
    assert 'post_commit_proof_incomplete' in markdown


def test_the_clean_apply_markdown_still_states_the_full_post_apply_proof(
    artifact_dir,
):
    """The control: the skip narrative must not become boilerplate."""
    state = _proof_failed_apply_state()
    state.update({
        'post_commit_transaction_read_only': True,
        'post_commit_read_only_reason': 'established',
        'post_commit_verification_completed': True,
        'post_commit_row_count': 1,
        'post_commit_value_is_intended': True,
        'after_snapshot': {
            repair.TARGET_COLUMN: repair.INTENDED_SOURCE_REVISION,
        },
        'failed_reasons': [],
    })
    document = _document(
        operation='apply', apply_state=state, preconditions=_evaluation(),
        fingerprints={
            'after_apply': {'exact_game_824487': {}},
            'out_of_scope_after_apply': {'rows': 1},
            'post_commit_proof_complete': True,
            'post_apply_fingerprint_collection_attempted': True,
            'post_apply_fingerprints_observed': True,
            'post_apply_out_of_scope_fingerprint_observed': True,
            'post_apply_observation_skip_reason': None,
        },
        mutation={
            'changed_fingerprint_tables': [['exact_game_824487', 'x']],
            'out_of_scope_unchanged': True,
            'mutation_within_scope': True,
        },
        decision=repair.decide(
            operation='apply', preconditions=_evaluation(),
            apply_attempted=True, apply_committed=True, post_commit=state,
        ),
    )
    assert document['verdict']['result'] == repair.RESULT_APPLIED
    _write(document, artifact_dir)
    markdown = (artifact_dir / runner.SUMMARY_MARKDOWN).read_text(
        encoding='utf-8'
    )
    assert 'deliberately **not collected**' not in markdown
    assert 'The repair COMMITTED.' not in markdown
    assert '| post-apply fingerprints observed | True |' in markdown
    assert '| out-of-scope digest unchanged | True |' in markdown
    assert '| post-apply skip reason | None |' in markdown


def test_the_scanner_passes_on_the_skipped_observation_artifact(artifact_dir):
    _write(_skipped_observation_document(), artifact_dir)
    result = subprocess.run(
        [sys.executable, str(SCANNER), '--directory', str(artifact_dir)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_scanner_passes_on_the_proof_failed_artifact(artifact_dir):
    _write(_proof_failed_document(), artifact_dir)
    result = subprocess.run(
        [sys.executable, str(SCANNER), '--directory', str(artifact_dir)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    blob = '\n'.join(
        path.read_text(encoding='utf-8') for path in artifact_dir.iterdir()
    )
    for forbidden in (
        'Traceback', 'psycopg2', 'InFailedSqlTransaction',
        'SET TRANSACTION READ ONLY', 'postgresql://', 'password',
        'apply_outcome_unknown',
    ):
        assert forbidden not in blob, forbidden
    assert '"committed": null' not in blob
    assert '"mutation_performed": false' not in blob


# ── The repository's own scanner ────────────────────────────────────────────

def test_the_repository_scanner_passes_on_a_real_artifact_directory(
    artifact_dir,
):
    _write(_document(), artifact_dir)
    result = subprocess.run(
        [sys.executable, str(SCANNER), '--directory', str(artifact_dir)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_repository_scanner_rejects_a_planted_credential(artifact_dir):
    """The gate is exercised, not assumed: a bad artifact must fail it."""
    _write(_document(), artifact_dir)
    (artifact_dir / 'planted.json').write_text(
        json.dumps({
            'database_url': 'postgresql://user:pw@host/db',
        }) + '\n',
        encoding='utf-8',
    )
    result = subprocess.run(
        [sys.executable, str(SCANNER), '--directory', str(artifact_dir)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode != 0


# ── The runner's own entry point ────────────────────────────────────────────

def test_main_returns_the_verdicts_exit_code(monkeypatch, tmp_path):
    monkeypatch.setattr(
        runner, 'run',
        lambda args: _document(decision=_refused()),
    )
    code = runner.main([
        '--operation', 'apply',
        '--expected-main-sha', 'f' * 40,
        '--confirmation', repair.CONFIRMATIONS['apply'],
        '--artifact-dir', str(tmp_path / 'out'),
    ])
    assert code == repair.EXIT_CODES[repair.RESULT_REFUSED] == 2
    assert (tmp_path / 'out' / runner.SUMMARY_JSON).is_file()


def test_main_refuses_an_operation_outside_the_closed_vocabulary(tmp_path):
    with pytest.raises(SystemExit):
        runner.main([
            '--operation', 'apply-everything',
            '--expected-main-sha', 'f' * 40,
            '--confirmation', repair.CONFIRMATIONS['apply'],
            '--artifact-dir', str(tmp_path / 'out'),
        ])


def test_the_runner_parses_only_the_four_governed_arguments():
    args = runner.parse_args([
        '--operation', 'verify',
        '--expected-main-sha', 'f' * 40,
        '--confirmation', repair.CONFIRMATIONS['verify'],
        '--artifact-dir', 'out',
    ])
    assert args.operation == 'verify'
    assert args.operator_note == ''
    # No argument exists that can name a game, a table, a column, or a value.
    assert not hasattr(args, 'game_pk')
    assert not hasattr(args, 'source_revision')
    assert not hasattr(args, 'target_table')


def test_the_authorization_check_rejects_a_mismatched_confirmation():
    context = {
        'event_name': repair.REQUIRED_EVENT_NAME,
        'repository': repair.REQUIRED_REPOSITORY,
        'actor': repair.REQUIRED_ACTOR,
        'ref': repair.REQUIRED_REF,
        'commit_sha': 'f' * 40,
        'expected_main_sha': 'f' * 40,
    }
    ok = runner.validate_authorization(
        context,
        SimpleNamespace(
            operation='apply', expected_main_sha='f' * 40,
            confirmation=repair.CONFIRMATIONS['apply'],
        ),
    )
    assert ok == []

    swapped = runner.validate_authorization(
        context,
        SimpleNamespace(
            operation='apply', expected_main_sha='f' * 40,
            confirmation=repair.CONFIRMATIONS['verify'],
        ),
    )
    assert repair.FAILED_CONFIRMATION_MISMATCH in swapped


def test_an_unknown_operation_never_falls_through_to_a_default_phrase():
    context = {
        'event_name': repair.REQUIRED_EVENT_NAME,
        'repository': repair.REQUIRED_REPOSITORY,
        'actor': repair.REQUIRED_ACTOR,
        'ref': repair.REQUIRED_REF,
        'commit_sha': 'f' * 40,
        'expected_main_sha': 'f' * 40,
    }
    failures = runner.validate_authorization(
        context,
        SimpleNamespace(
            operation='', expected_main_sha='f' * 40,
            confirmation=repair.CONFIRMATIONS['apply'],
        ),
    )
    assert repair.FAILED_OPERATION_UNKNOWN in failures
    assert repair.FAILED_CONFIRMATION_MISMATCH in failures
