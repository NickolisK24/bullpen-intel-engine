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


def _audit_validator_source():
    text = WORKFLOW.read_text(encoding='utf-8').replace('\r\n', '\n')
    marker = (
        '          python - "$audit_json" "$audit_exit_code" '
        '"$GITHUB_STEP_SUMMARY" <<\'PY\'\n'
    )
    source = text.split(marker, 1)[1].split('\n          PY\n', 1)[0]
    return textwrap.dedent(source)


def _appearance_team_audit_validator_source():
    text = WORKFLOW.read_text(encoding='utf-8').replace('\r\n', '\n')
    step = text.split(
        '      - name: Run Foundation 1 appearance-team production audit\n',
        1,
    )[1]
    marker = (
        '          python - "$audit_json" "$audit_exit_code" '
        '"$GITHUB_STEP_SUMMARY" <<\'PY\'\n'
    )
    source = step.split(marker, 1)[1].split('\n          PY\n', 1)[0]
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


def _audit_payload(**overrides):
    payload = {
        'route_status': 'internal_admin_only',
        'request': {'window_days': 14},
        'latest_snapshot': {'id': 101, 'data_through': '2026-07-10'},
        'recent_snapshots': [{'id': 101, 'data_through': '2026-07-10'}],
        'diagnostics': [],
        'snapshot_adjacency_summary': {
            'response_mode': 'bounded_summary',
            'published_snapshot_count': 15,
            'trusted_published_snapshot_count': 15,
            'adjacent_published_pair_count': 14,
            'trusted_pair_count': 14,
            'comparable_adjacent_pair_count': 14,
            'non_comparable_count': 0,
            'non_comparable_reason_codes': [],
            'non_adjacent_comparison_count': 0,
            'recent_row_query_limit': 256,
            'recent_rows_truncated': False,
        },
    }
    payload.update(overrides)
    return payload


def _run_audit_validator(tmp_path, payload, exit_code=0, prefix=''):
    output_path = tmp_path / 'phase0h-snapshot-audit.json'
    summary_path = tmp_path / 'step-summary.md'
    output_path.write_text(prefix + json.dumps(payload), encoding='utf-8')
    return subprocess.run(
        [
            sys.executable,
            '-',
            str(output_path),
            str(exit_code),
            str(summary_path),
        ],
        input=_audit_validator_source(),
        text=True,
        capture_output=True,
        check=False,
    )


def _appearance_team_audit_payload(**overrides):
    payload = {
        'capability': 'appearance_team_production_audit_v1',
        'coverage_capability': 'appearance_team_coverage_v1',
        'status': 'complete',
        'result': 'PASS',
        'mode': 'read_only',
        'database_writes_performed': False,
        'migration': {
            'expected_head': 'c7b3e5a91d48',
            'current_heads': ['c7b3e5a91d48'],
            'head_matches': True,
        },
        'coverage': {
            'total_game_logs': 10,
            'resolved': 3,
            'unresolved': 1,
            'conflict': 1,
            'null_legacy': 5,
            'current_team_mismatch': 1,
            'by_source': {
                'boxscore_side': 3,
                'null_legacy': 7,
            },
            'by_season': {
                '2025': {
                    'resolved': 0,
                    'unresolved': 0,
                    'conflict': 0,
                    'null_legacy': 4,
                },
                '2026': {
                    'resolved': 3,
                    'unresolved': 1,
                    'conflict': 1,
                    'null_legacy': 1,
                },
            },
        },
        'coverage_contract': {
            'status_total': 10,
            'source_total': 10,
            'season_total': 10,
            'totals_match': True,
        },
        'new_row_attribution': {
            'since_utc': '2026-07-26T00:00:00Z',
            'total': 1,
            'resolved': 1,
            'unresolved': 0,
            'conflict': 0,
            'null_legacy': 0,
            'status_recorded': 1,
        },
        'invalid_states': {'total': 0, 'counts': {}},
        'non_resolved': {
            'total': 7,
            'row_limit': 50,
            'returned': 1,
            'truncated': True,
            'rows': [{'mlb_game_pk': 7001}],
        },
        'decision_reasons': ['post_cutover_rows_fully_resolved'],
    }
    payload.update(overrides)
    return payload


def _run_appearance_team_audit_validator(tmp_path, payload, exit_code=0):
    output_path = tmp_path / 'appearance-team-production-audit.json'
    summary_path = tmp_path / 'step-summary.md'
    output_path.write_text(json.dumps(payload), encoding='utf-8')
    return subprocess.run(
        [
            sys.executable,
            '-',
            str(output_path),
            str(exit_code),
            str(summary_path),
        ],
        input=_appearance_team_audit_validator_source(),
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


def test_workflow_has_read_only_phase0h_snapshot_audit_operation():
    text = WORKFLOW.read_text(encoding='utf-8').replace('\r\n', '\n')

    assert 'phase0h_snapshot_audit' in text
    assert 'RUN_PHASE0H_PRODUCTION_AUDIT' in text
    assert 'python scripts/run_internal_snapshot_audit.py \\' in text
    assert '--window "$AUDIT_WINDOW"' in text
    assert '--recent-row-limit "$AUDIT_RECENT_ROW_LIMIT"' in text
    assert '--compact' in text
    assert '> "$audit_json"' in text
    assert '2> "$audit_stderr"' in text
    assert 'actions/upload-artifact@v4' in text
    assert 'phase0h-snapshot-audit-${{ github.run_id }}' in text
    assert 'if: ${{ inputs.operation == \'phase0h_snapshot_audit\' }}' in text
    assert 'if: ${{ always() && inputs.operation == \'phase0h_snapshot_audit\' }}' in text
    assert 'Phase 0H production ratification requires audit_window=14.' in text
    assert 'audit_recent_row_limit must be between 64 and 512.' in text
    assert 'AUDIT_WINDOW: ${{ inputs.audit_window }}' in text
    assert 'AUDIT_RECENT_ROW_LIMIT: ${{ inputs.audit_recent_row_limit }}' in text
    assert 'DATABASE_URL: ${{ secrets.DATABASE_URL }}' in text
    assert 'ADMIN_API_TOKEN: ${{ secrets.BASEBALLOS_ADMIN_API_TOKEN }}' in text


def test_phase0h_audit_validator_accepts_full_bounded_summary(tmp_path):
    result = _run_audit_validator(tmp_path, _audit_payload())

    assert result.returncode == 0, result.stderr


def test_phase0h_audit_validator_ignores_scheduler_banner_before_json(tmp_path):
    result = _run_audit_validator(
        tmp_path,
        _audit_payload(),
        prefix='[scheduler] AUTO_SYNC disabled - daily scheduler not started.\n',
    )

    assert result.returncode == 0, result.stderr


def test_phase0h_audit_validator_rejects_missing_audit_json(tmp_path):
    output_path = tmp_path / 'phase0h-snapshot-audit.json'
    summary_path = tmp_path / 'step-summary.md'
    output_path.write_text(
        '[scheduler] AUTO_SYNC disabled\nINFO no audit summary emitted\n',
        encoding='utf-8',
    )

    result = subprocess.run(
        [
            sys.executable,
            '-',
            str(output_path),
            '0',
            str(summary_path),
        ],
        input=_audit_validator_source(),
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert 'Audit output was not valid JSON' in result.stderr


def test_phase0h_audit_validator_rejects_degraded_fallback(tmp_path):
    payload = _audit_payload(
        route_status='degraded',
        response_mode='fallback_db_row_metadata',
        snapshot_adjacency_summary={
            'available': False,
            'reason': 'trust_summary_unavailable_in_fallback',
            'trusted_pair_count': None,
            'comparable_adjacent_pair_count': None,
            'non_comparable_count': None,
            'non_comparable_reason_codes': None,
            'non_adjacent_comparison_count': None,
        },
    )

    result = _run_audit_validator(tmp_path, payload, exit_code=1)

    assert result.returncode != 0
    assert 'audit_exit_code=1' in result.stderr
    assert "route_status='degraded'" in result.stderr
    assert 'top-level fallback response_mode observed' in result.stderr


def test_phase0h_audit_validator_rejects_truncated_or_missing_counts(tmp_path):
    payload = _audit_payload()
    payload['snapshot_adjacency_summary'] = {
        **payload['snapshot_adjacency_summary'],
        'recent_rows_truncated': True,
        'trusted_pair_count': None,
    }

    result = _run_audit_validator(tmp_path, payload)

    assert result.returncode != 0
    assert 'recent_rows_truncated=True' in result.stderr
    assert 'trusted_pair_count=None' in result.stderr


def test_workflow_has_read_only_appearance_team_production_audit_operation():
    text = WORKFLOW.read_text(encoding='utf-8').replace('\r\n', '\n')

    assert 'appearance_team_audit' in text
    assert 'RUN_APPEARANCE_TEAM_PRODUCTION_AUDIT' in text
    assert 'python scripts/run_appearance_team_coverage_audit.py \\' in text
    assert '--new-row-since "$APPEARANCE_TEAM_SINCE"' in text
    assert '--row-limit "$APPEARANCE_TEAM_ROW_LIMIT"' in text
    assert '--output "$audit_json"' in text
    assert 'appearance_team_production_audit_v1' in text
    assert 'appearance_team_coverage_v1' in text
    assert "expected_exit = {'PASS': 0, 'INCONCLUSIVE': 1, 'FAIL': 2}" in text
    assert "payload.get('mode') != 'read_only'" in text
    assert "payload.get('database_writes_performed') is not False" in text
    assert "migration.get('expected_head') != 'c7b3e5a91d48'" in text
    assert "new_rows.get('since_utc')" in text
    assert "invalid_states.get('total')" in text
    assert "non_resolved.get('row_limit')" in text
    assert 'No backfill or reader migration was performed.' in text
    assert 'appearance-team-production-audit-${{ github.run_id }}' in text
    assert 'exit "$audit_exit_code"' in text
    assert "if: ${{ inputs.operation == 'appearance_team_audit' }}" in text
    assert (
        "if: ${{ always() && inputs.operation == 'appearance_team_audit' }}"
        in text
    )


def test_appearance_team_audit_validator_accepts_consistent_read_only_counts(
    tmp_path,
):
    result = _run_appearance_team_audit_validator(
        tmp_path,
        _appearance_team_audit_payload(),
    )

    assert result.returncode == 0, result.stderr


def test_appearance_team_audit_validator_rejects_failed_or_write_claim(
    tmp_path,
):
    result = _run_appearance_team_audit_validator(
        tmp_path,
        _appearance_team_audit_payload(
            status='failed',
            result='FAIL',
            database_writes_performed=True,
            error_type='RuntimeError',
        ),
        exit_code=2,
    )

    assert result.returncode != 0
    assert 'database_writes_performed=True' in result.stderr


def test_appearance_team_audit_validator_rejects_exit_mismatch_and_unbounded_rows(
    tmp_path,
):
    payload = _appearance_team_audit_payload(result='INCONCLUSIVE')
    payload['non_resolved'] = {
        **payload['non_resolved'],
        'row_limit': 1,
        'returned': 2,
        'rows': [{'id': 1}, {'id': 2}],
    }
    result = _run_appearance_team_audit_validator(
        tmp_path,
        payload,
        exit_code=0,
    )

    assert result.returncode != 0
    assert 'audit_exit_code=0; expected=1' in result.stderr
    assert 'non_resolved.rows exceeds row_limit' in result.stderr
