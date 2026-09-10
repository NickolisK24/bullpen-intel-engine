"""The evidence handoff and the final activation verdict, executed.

The workflow-structure tests prove where things live. These prove what they
DO — because a gate asserted only by reading YAML is a gate nobody has run, and
this particular gate decides whether an unproven shadow cycle can look like a
passing one.

Three properties are worth stating plainly, since each one is a way the split
could have quietly gone wrong:

* an unsafe raw summary is never staged, so a scanner bug produces an empty
  handoff rather than a leaked production artifact;
* missing evidence produces UNPROVEN, never a skip and never a pass — absent
  evidence is the state most easily mistaken for success;
* the publication-critical side cannot be turned red by any of it.
"""

import json
from pathlib import Path

import pytest

from scripts import evaluate_shadow_activation_gate as gate
from scripts import prepare_shadow_handoff as handoff
from scripts import scan_forbidden_artifact_content as scanner


PRODUCTION_SOURCE = '{"status": "success", "games_planned": 45}'


@pytest.fixture
def staging(tmp_path):
    return tmp_path / 'handoff'


@pytest.fixture
def source(tmp_path):
    path = tmp_path / 'game-driven-shadow'
    path.mkdir()
    return path


def _ready_handoff(source, staging, *, cycle='daily', runner_exit='0'):
    (source / f'{cycle}-sync-summary.json').write_text(PRODUCTION_SOURCE)
    metadata, code = handoff.prepare(
        source_dir=source, staging_dir=staging, run_id='42',
        repository_sha='abc123',
        daily_runner_exit=runner_exit if cycle == 'daily' else None,
        postgame_runner_exit=runner_exit if cycle == 'postgame' else None,
    )
    handoff.write_metadata(metadata, staging)
    return metadata, code


# ── The shared forbidden-content contract ───────────────────────────────────


@pytest.mark.parametrize('sample,category', [
    ('postgresql://user:pw@host/db', 'postgres_connection_url'),
    ('postgres://user:pw@host/db', 'postgres_connection_url'),
    ('password=hunter2', 'inline_password'),
    ('Authorization: Bearer x', 'authorization_header'),
    ('X-Admin-Token: abc', 'admin_token_header'),
    ('ADMIN_API_TOKEN', 'admin_token_variable'),
    ('SECRET_KEY', 'secret_key_variable'),
    ('DATABASE_URL', 'database_url_variable'),
    ('BASEBALLOS_ADMIN_API_TOKEN', 'baseballos_admin_token'),
    ('token=abc', 'inline_token'),
    ('api_key=abc', 'inline_api_key'),
    ('api-key=abc', 'inline_api_key'),
    ('secret=abc', 'inline_secret'),
    ('Traceback (most recent call last)', 'python_traceback'),
    ('/home/runner/work/repo', 'runner_filesystem_path'),
])
def test_every_forbidden_category_is_detected(sample, category):
    assert category in scanner.categories_in(sample)


def test_ordinary_activation_evidence_is_safe():
    assert scanner.categories_in(PRODUCTION_SOURCE) == []


def test_the_scanner_reports_categories_and_never_the_matched_content(capsys):
    """The tool that catches a leak must not re-leak it."""
    path = Path(pytest.importorskip('tempfile').mkdtemp()) / 'bad.json'
    path.write_text('{"dsn": "postgresql://user:SUPERSECRET@host/db"}')

    code = scanner.main([str(path)])
    output = capsys.readouterr().out

    assert code == scanner.EXIT_UNSAFE
    assert 'postgres_connection_url' in output
    assert 'SUPERSECRET' not in output
    assert 'postgresql://' not in output


def test_an_unreadable_file_is_unsafe_rather_than_skipped(tmp_path):
    assert scanner.scan_file(tmp_path / 'absent.json') == ['unreadable_file']


def test_quarantine_removes_the_unsafe_file(tmp_path):
    bad = tmp_path / 'bad.json'
    bad.write_text('DATABASE_URL=postgres://x')
    result = scanner.scan_paths([bad], quarantine=True)
    assert result['safe'] is False
    assert not bad.exists()


# ── Staging: nothing unscanned ever leaves the runner ───────────────────────


def test_a_clean_summary_is_staged_and_described(source, staging):
    metadata, code = _ready_handoff(source, staging)

    assert code == handoff.EXIT_READY
    assert metadata['handoff_status'] == handoff.STATUS_READY
    assert metadata['cycle_kind'] == 'daily'
    assert metadata['runner_exit_code'] == 0
    assert metadata['summary_present'] is True
    assert metadata['preupload_scan_safe'] is True
    assert (staging / 'daily-sync-summary.json').is_file()
    assert (staging / handoff.METADATA_FILENAME).is_file()


def test_an_unsafe_summary_is_never_copied_into_staging(source, staging):
    """The staging rule, stated as the assertion that matters.

    If the raw directory were uploaded directly, a scanner miss would be a
    leak. Because only staging is uploaded, the worst case is an empty handoff.
    """
    (source / 'daily-sync-summary.json').write_text(
        '{"dsn": "postgresql://user:pw@host/db"}'
    )
    metadata, code = handoff.prepare(
        source_dir=source, staging_dir=staging, daily_runner_exit='0',
    )
    handoff.write_metadata(metadata, staging)

    assert code == handoff.EXIT_NOT_READY
    assert metadata['handoff_status'] == handoff.STATUS_ARTIFACT_UNSAFE
    assert metadata['preupload_scan_safe'] is False
    assert not (staging / 'daily-sync-summary.json').exists()
    assert sorted(p.name for p in staging.iterdir()) == [handoff.METADATA_FILENAME]


def test_a_missing_summary_is_described_rather_than_silent(source, staging):
    metadata, code = handoff.prepare(source_dir=source, staging_dir=staging)
    handoff.write_metadata(metadata, staging)

    assert code == handoff.EXIT_NOT_READY
    assert metadata['handoff_status'] == handoff.STATUS_SUMMARY_MISSING
    assert metadata['summary_present'] is False


def test_metadata_is_written_on_every_failure_path(source, staging):
    metadata, _ = handoff.prepare(source_dir=source, staging_dir=staging)
    handoff.write_metadata(metadata, staging)
    assert (staging / handoff.METADATA_FILENAME).is_file()


def test_a_missing_runner_exit_code_is_not_coerced_to_success(source, staging):
    """The validator's contract depends on what the runner actually did."""
    (source / 'postgame-sync-summary.json').write_text(PRODUCTION_SOURCE)
    metadata, code = handoff.prepare(
        source_dir=source, staging_dir=staging, postgame_runner_exit='',
    )
    assert code == handoff.EXIT_NOT_READY
    assert metadata['runner_exit_code'] is None
    assert metadata['handoff_status'] != handoff.STATUS_READY


def test_the_postgame_cycle_is_resolved_from_its_own_summary(source, staging):
    metadata, code = _ready_handoff(source, staging, cycle='postgame')
    assert code == handoff.EXIT_READY
    assert metadata['cycle_kind'] == 'postgame'
    assert metadata['expected_summary_filename'] == 'postgame-sync-summary.json'


def test_the_metadata_carries_no_credential_shaped_content(source, staging):
    metadata, _ = _ready_handoff(source, staging)
    assert scanner.categories_in(json.dumps(metadata)) == []


def test_the_metadata_schema_is_exactly_the_agreed_fields(source, staging):
    metadata, _ = _ready_handoff(source, staging)
    assert set(metadata) == {
        'schema_version', 'run_id', 'repository_sha', 'cycle_kind',
        'runner_exit_code', 'expected_summary_filename', 'summary_present',
        'preupload_scan_safe', 'handoff_status',
    }


# ── The failure matrix, executed ────────────────────────────────────────────


def _evaluate(staging, **overrides):
    kwargs = {
        'handoff_dir': staging, 'handoff_download_ok': True,
        'validator_exit_code': '0', 'final_scan_safe': True,
        'final_upload_ok': True,
    }
    kwargs.update(overrides)
    return gate.evaluate(**kwargs)


def test_case_1_a_valid_handoff_and_a_passing_validator_passes(source, staging):
    _ready_handoff(source, staging)
    assert _evaluate(staging) == {'result': gate.RESULT_PASS, 'reason': None}


def test_case_2_a_validator_failure_fails(source, staging):
    _ready_handoff(source, staging)
    decision = _evaluate(staging, validator_exit_code='1')
    assert decision['result'] == gate.RESULT_FAILED
    assert decision['reason'] == gate.REASON_VALIDATOR_FAILED


@pytest.mark.parametrize('code', ['2', '3', '127', '', 'nonsense', None])
def test_case_3_an_unexpected_validator_code_is_unproven(source, staging, code):
    _ready_handoff(source, staging)
    decision = _evaluate(staging, validator_exit_code=code)
    assert decision['result'] == gate.RESULT_UNPROVEN
    assert decision['reason'] == gate.REASON_VALIDATOR_UNPROVEN


def test_case_4_a_missing_handoff_download_is_unproven(source, staging):
    _ready_handoff(source, staging)
    decision = _evaluate(staging, handoff_download_ok=False)
    assert decision['result'] == gate.RESULT_UNPROVEN
    assert decision['reason'] == gate.REASON_HANDOFF_DOWNLOAD_FAILED


def test_case_5_missing_metadata_is_unproven(staging):
    staging.mkdir(parents=True)
    decision = _evaluate(staging)
    assert decision['result'] == gate.RESULT_UNPROVEN
    assert decision['reason'] == gate.REASON_METADATA_MISSING


@pytest.mark.parametrize('body', ['not json', '[]', '{"schema_version": "999"}'])
def test_invalid_metadata_is_unproven(staging, body):
    staging.mkdir(parents=True)
    (staging / handoff.METADATA_FILENAME).write_text(body)
    decision = _evaluate(staging)
    assert decision['result'] == gate.RESULT_UNPROVEN
    assert decision['reason'] == gate.REASON_METADATA_INVALID


def test_case_6_a_missing_summary_file_is_unproven(source, staging):
    _ready_handoff(source, staging)
    (staging / 'daily-sync-summary.json').unlink()
    decision = _evaluate(staging)
    assert decision['result'] == gate.RESULT_UNPROVEN
    assert decision['reason'] == gate.REASON_SUMMARY_MISSING


def test_case_7_an_unsafe_preupload_scan_is_unproven(source, staging):
    """The end-to-end path from an unsafe raw artifact to a failed gate."""
    (source / 'daily-sync-summary.json').write_text('DATABASE_URL=postgres://x')
    metadata, _ = handoff.prepare(
        source_dir=source, staging_dir=staging, daily_runner_exit='0',
    )
    handoff.write_metadata(metadata, staging)

    decision = _evaluate(staging)
    assert decision['result'] == gate.RESULT_UNPROVEN
    assert decision['reason'] == gate.REASON_HANDOFF_NOT_READY


def test_case_8_an_unsafe_final_scan_is_unproven(source, staging):
    _ready_handoff(source, staging)
    decision = _evaluate(staging, final_scan_safe=False)
    assert decision['result'] == gate.RESULT_UNPROVEN
    assert decision['reason'] == gate.REASON_FINAL_SCAN_UNSAFE


def test_case_9_a_failed_final_upload_is_unproven(source, staging):
    """Evidence that was not preserved cannot support a PASS."""
    _ready_handoff(source, staging)
    decision = _evaluate(staging, final_upload_ok=False)
    assert decision['result'] == gate.RESULT_UNPROVEN
    assert decision['reason'] == gate.REASON_FINAL_UPLOAD_FAILED


def test_a_handoff_that_was_never_ready_is_unproven(source, staging):
    metadata, _ = handoff.prepare(source_dir=source, staging_dir=staging)
    handoff.write_metadata(metadata, staging)
    decision = _evaluate(staging)
    assert decision['result'] == gate.RESULT_UNPROVEN
    assert decision['reason'] == gate.REASON_HANDOFF_NOT_READY


@pytest.mark.parametrize('cycle_kind', ['morning', 'backfill', 'intraday', '', None])
def test_an_ineligible_cycle_kind_is_unproven(source, staging, cycle_kind):
    _ready_handoff(source, staging)
    path = staging / handoff.METADATA_FILENAME
    metadata = json.loads(path.read_text())
    metadata['cycle_kind'] = cycle_kind
    path.write_text(json.dumps(metadata))

    decision = _evaluate(staging)
    assert decision['result'] == gate.RESULT_UNPROVEN
    assert decision['reason'] == gate.REASON_CYCLE_KIND_INVALID


@pytest.mark.parametrize('runner_exit', ['0', None, True, 'zero'])
def test_a_non_integer_runner_exit_code_is_unproven(source, staging, runner_exit):
    _ready_handoff(source, staging)
    path = staging / handoff.METADATA_FILENAME
    metadata = json.loads(path.read_text())
    metadata['runner_exit_code'] = runner_exit
    path.write_text(json.dumps(metadata))

    decision = _evaluate(staging)
    assert decision['result'] == gate.RESULT_UNPROVEN
    assert decision['reason'] == gate.REASON_RUNNER_EXIT_INVALID


def test_a_nonzero_runner_exit_code_still_reaches_the_validator(source, staging):
    """A failed runner is the validator's question to answer, not the gate's."""
    _ready_handoff(source, staging, runner_exit='1')
    metadata = json.loads((staging / handoff.METADATA_FILENAME).read_text())
    assert metadata['runner_exit_code'] == 1
    assert metadata['handoff_status'] == handoff.STATUS_READY
    assert _evaluate(staging, validator_exit_code='1')['result'] == gate.RESULT_FAILED


# ── Vocabulary and reporting ────────────────────────────────────────────────


def test_the_verdict_vocabulary_is_exactly_three_values():
    assert {gate.RESULT_PASS, gate.RESULT_FAILED, gate.RESULT_UNPROVEN} == {
        'PASS', 'FAILED', 'UNPROVEN',
    }


def test_a_passing_gate_exits_zero(source, staging, capsys):
    _ready_handoff(source, staging)
    code = gate.main([
        '--handoff-dir', str(staging), '--handoff-download-outcome', 'success',
        '--validator-exit-code', '0', '--final-scan-safe', 'true',
        '--final-upload-outcome', 'success',
    ])
    assert code == gate.EXIT_PASS
    assert 'PASS' in capsys.readouterr().out


@pytest.mark.parametrize('validator_code,expected_label', [
    ('1', 'FAILED'),
    ('2', 'UNPROVEN'),
])
def test_a_non_passing_gate_exits_nonzero_and_names_the_state(
    source, staging, capsys, validator_code, expected_label,
):
    _ready_handoff(source, staging)
    code = gate.main([
        '--handoff-dir', str(staging), '--handoff-download-outcome', 'success',
        '--validator-exit-code', validator_code, '--final-scan-safe', 'true',
        '--final-upload-outcome', 'success',
    ])
    output = capsys.readouterr().out

    assert code == gate.EXIT_NOT_PASS
    assert expected_label in output
    assert 'not a pass' in output


def test_the_failure_message_restates_the_unchanged_authorities(
    source, staging, capsys,
):
    _ready_handoff(source, staging)
    gate.main([
        '--handoff-dir', str(staging), '--handoff-download-outcome', 'success',
        '--validator-exit-code', '1', '--final-scan-safe', 'true',
        '--final-upload-outcome', 'success',
    ])
    output = capsys.readouterr().out

    assert 'Automated write mode remains prohibited' in output
    assert 'Authoritative mode remains prohibited' in output
    assert 'publication authority remains unchanged' in output
    assert 'Review the retained activation evidence' in output


def test_the_failure_message_says_publication_is_unaffected(
    source, staging, capsys,
):
    """Case B, in words an operator reads at 3am."""
    _ready_handoff(source, staging)
    gate.main([
        '--handoff-dir', str(staging), '--handoff-download-outcome', 'failure',
        '--validator-exit-code', '0', '--final-scan-safe', 'true',
        '--final-upload-outcome', 'success',
    ])
    output = capsys.readouterr().out
    assert 'does not change the publication-critical result' in output


@pytest.mark.parametrize('value,expected', [
    ('true', True), ('success', True), ('1', True), ('yes', True),
    ('false', False), ('failure', False), ('skipped', False), ('', False),
    ('cancelled', False), (None, False), ('maybe', False),
])
def test_outcome_strings_are_read_strictly(value, expected):
    """An unrecognized outcome must never read as 'probably fine'."""
    assert gate._as_bool(value) is expected


# ── The helpers stay standard-library only ──────────────────────────────────


def _imported_roots(module):
    """Top-level package of every import, read from the AST.

    Parsed rather than grepped: these modules describe their own constraints in
    prose, and a substring search would match the docstring that says "no
    Flask" instead of an import that uses it.
    """
    import ast

    tree = ast.parse(Path(module.__file__).read_text(encoding='utf-8'))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split('.')[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split('.')[0])
    return roots


@pytest.mark.parametrize('module', [scanner, handoff, gate])
def test_the_helper_imports_no_application_stack(module):
    """These run in a job with no credentials and no database.

    An import of the app, the models, or a driver would either need
    configuration this job deliberately lacks, or would signal that the
    observer had grown a capability it must not have.
    """
    forbidden = {'app', 'utils', 'models', 'services', 'flask',
                 'flask_sqlalchemy', 'sqlalchemy', 'psycopg2'}
    assert not (_imported_roots(module) & forbidden)


def test_the_helpers_import_only_each_other_and_the_standard_library():
    allowed = {'__future__', 'argparse', 'ast', 'json', 're', 'shutil', 'sys',
               'pathlib', 'scripts'}
    for module in (scanner, handoff, gate):
        assert _imported_roots(module) <= allowed, module.__name__
