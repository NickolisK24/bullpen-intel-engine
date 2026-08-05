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

EXPECTED_FILES = (
    runner.SUMMARY_JSON,
    runner.SUMMARY_MARKDOWN,
    runner.PRECONDITIONS_JSON,
    runner.MUTATION_LEDGER_JSON,
    runner.COMPARISON_JSON,
)


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
    assert code == repair.EXIT_CODES[repair.RESULT_REFUSED] == 3
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
