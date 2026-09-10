from pathlib import Path

from scripts.run_intraday_repair import _parse_args


WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / '.github'
    / 'workflows'
    / 'baseballos-intraday-repair.yml'
)
WORKFLOWS = WORKFLOW.parent
PUBLIC_SYNC_WORKFLOW = WORKFLOWS / 'baseballos-sync.yml'
SYNC_PIPELINE_DOC = (
    Path(__file__).resolve().parents[2]
    / 'docs'
    / 'current'
    / 'SYNC_PIPELINE.md'
)


def _workflow_text():
    return WORKFLOW.read_text(encoding='utf-8')


def test_intraday_repair_is_dormant_and_manual_only():
    text = _workflow_text()
    assert '\n  schedule:' not in text
    assert 'cron:' not in text
    assert text.count('\n  workflow_dispatch:') == 1
    for trigger in (
        'push',
        'pull_request',
        'repository_dispatch',
        'workflow_call',
        'workflow_run',
    ):
        assert f'\n  {trigger}:' not in text
    assert 'Dormant manual-only seasonal capability' in text


def test_no_other_workflow_invokes_intraday_repair():
    callers = [
        path.name
        for path in sorted(WORKFLOWS.glob('*.y*ml'))
        if 'run_intraday_repair.py' in path.read_text(encoding='utf-8')
    ]
    assert callers == [WORKFLOW.name]


def test_daily_and_postgame_automatic_cadence_is_unchanged():
    text = PUBLIC_SYNC_WORKFLOW.read_text(encoding='utf-8')
    assert text.count('- cron:') == 3
    assert "- cron: '17 10 * * *'" in text
    assert "- cron: '23 14 * * *'" in text
    assert "- cron: '11 2,4,6 * * *'" in text
    assert 'python backend/scripts/run_due_sync.py --mode daily' in text
    assert 'python backend/scripts/run_due_sync.py --mode postgame' in text
    assert 'run_intraday_repair.py' not in text


def test_intraday_repair_shares_public_sync_concurrency_lane():
    text = _workflow_text()
    assert 'group: baseballos-sync' in text
    assert 'cancel-in-progress: false' in text


def test_intraday_repair_uses_fail_closed_command():
    text = _workflow_text()
    assert 'python backend/scripts/run_intraday_repair.py' in text
    assert '--source github_actions_intraday' in text
    assert '--days-back 7' in text
    assert text.count('--repair-transaction-roster-evidence') == 1
    assert 'exit "$exit_code"' in text


def test_intraday_repair_requires_production_secrets_and_timeout():
    text = _workflow_text()
    assert 'DATABASE_URL: ${{ secrets.DATABASE_URL }}' in text
    assert 'SECRET_KEY: ${{ secrets.SECRET_KEY }}' in text
    assert 'ADMIN_API_TOKEN: ${{ secrets.BASEBALLOS_ADMIN_API_TOKEN }}' in text
    assert 'INTRADAY_REPAIR_COMMAND_TIMEOUT: 20m' in text
    assert 'timeout --kill-after=30s' in text
    assert 'timeout-minutes: 25' in text


def test_intraday_repair_cli_flag_is_explicit_and_disabled_by_default():
    assert _parse_args([]).repair_transaction_roster_evidence is False
    assert _parse_args([
        '--repair-transaction-roster-evidence'
    ]).repair_transaction_roster_evidence is True


def test_sync_runbook_records_the_seasonal_manual_only_posture():
    text = SYNC_PIPELINE_DOC.read_text(encoding='utf-8')
    assert 'scheduled intraday repair is retired for the remainder of 2026' in text
    assert '2027 preseason reactivation review' in text
    assert 'Daily and postgame authority are unchanged.' in text
