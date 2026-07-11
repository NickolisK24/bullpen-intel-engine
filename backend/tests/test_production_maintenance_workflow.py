import json
from pathlib import Path
import subprocess
import sys
import textwrap


WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / '.github/workflows/baseballos-production-maintenance.yml'
)


def _validator_source():
    text = WORKFLOW.read_text(encoding='utf-8').replace('\r\n', '\n')
    marker = '            python - "$summary_file" "$summary_kind" <<\'PY\'\n'
    source = text.split(marker, 1)[1].split('\n          PY\n', 1)[0]
    return textwrap.dedent(source)


def _run_validator(tmp_path, output, summary_kind):
    output_path = tmp_path / f'{summary_kind}.log'
    output_path.write_text(output, encoding='utf-8')
    return subprocess.run(
        [sys.executable, '-', str(output_path), summary_kind],
        input=_validator_source(),
        text=True,
        capture_output=True,
        check=False,
    )


def test_schedule_summary_parser_ignores_logs_before_final_json(tmp_path):
    output = '\n'.join((
        '[scheduler] AUTO_SYNC disabled - daily scheduler not started.',
        '2026-07-11 12:00:00 INFO baseballos.mlb_api MLB API ok',
        '{"end_date":"2026-07-09","status":"ok","summary":{"errors":0}}',
    ))

    result = _run_validator(tmp_path, output, 'schedule')

    assert result.returncode == 0, result.stderr


def test_schedule_summary_parser_accepts_pure_json(tmp_path):
    result = _run_validator(
        tmp_path,
        '{"status":"ok","summary":{"errors":0}}\n',
        'schedule',
    )

    assert result.returncode == 0, result.stderr


def test_summary_parser_fails_clearly_when_json_is_missing(tmp_path):
    result = _run_validator(
        tmp_path,
        '[scheduler] AUTO_SYNC disabled\nINFO no summary emitted\n',
        'schedule',
    )

    assert result.returncode != 0
    assert 'No JSON summary object found in command output.' in result.stderr


def test_backfill_summary_parser_accepts_real_pretty_printed_contract(tmp_path):
    summary = {
        'pitchers_total': 1,
        'fetch_failures': 0,
        'records_failed': 0,
        'coverage_records_incomplete': 0,
    }
    output = '\n'.join((
        '[scheduler] AUTO_SYNC disabled - daily scheduler not started.',
        '2026-07-11 12:00:00 INFO baseballos.mlb_api MLB API ok',
        json.dumps(summary, indent=2, sort_keys=True),
    ))

    result = _run_validator(tmp_path, output, 'backfill')

    assert result.returncode == 0, result.stderr


def test_backfill_summary_parser_preserves_failure_checks(tmp_path):
    valid_summary = {
        'pitchers_total': 1,
        'fetch_failures': 0,
        'records_failed': 0,
        'coverage_records_incomplete': 0,
    }
    cases = (
        ('pitchers_total', 0, 'Ledger backfill matched no pitchers.'),
        ('fetch_failures', 1, "'fetch_failures': 1"),
        ('records_failed', 1, "'records_failed': 1"),
        (
            'coverage_records_incomplete',
            1,
            "'coverage_records_incomplete': 1",
        ),
    )

    for field, value, expected_error in cases:
        summary = {**valid_summary, field: value}
        result = _run_validator(
            tmp_path,
            json.dumps(summary, indent=2, sort_keys=True),
            'backfill',
        )

        assert result.returncode != 0
        assert expected_error in result.stderr


def test_workflow_keeps_tee_output_and_verified_summary_fields():
    text = WORKFLOW.read_text(encoding='utf-8').replace('\r\n', '\n')

    assert '| tee "$schedule_summary_file"' in text
    assert '| tee "$backfill_summary_file"' in text
    assert "summary.get('status') != 'ok'" in text
    assert "summary.get('pitchers_total', 0)" in text
    assert "'fetch_failures'" in text
    assert "'records_failed'" in text
    assert "'coverage_records_incomplete'" in text
