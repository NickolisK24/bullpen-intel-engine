from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parents[2]
    / '.github'
    / 'workflows'
    / 'baseballos-intraday-repair.yml'
)


def _workflow_text():
    return WORKFLOW.read_text(encoding='utf-8')


def test_intraday_repair_has_bounded_daytime_cadence():
    text = _workflow_text()
    assert "cron: '0 0,16,20 * * *'" in text
    assert text.count('cron:') == 1


def test_intraday_repair_shares_public_sync_concurrency_lane():
    text = _workflow_text()
    assert 'group: baseballos-sync' in text
    assert 'cancel-in-progress: false' in text


def test_intraday_repair_uses_fail_closed_command():
    text = _workflow_text()
    assert 'python backend/scripts/run_intraday_repair.py' in text
    assert '--source github_actions_intraday' in text
    assert '--days-back 7' in text
    assert 'exit "$exit_code"' in text


def test_intraday_repair_requires_production_secrets_and_timeout():
    text = _workflow_text()
    assert 'DATABASE_URL: ${{ secrets.DATABASE_URL }}' in text
    assert 'SECRET_KEY: ${{ secrets.SECRET_KEY }}' in text
    assert 'ADMIN_API_TOKEN: ${{ secrets.BASEBALLOS_ADMIN_API_TOKEN }}' in text
    assert 'INTRADAY_REPAIR_COMMAND_TIMEOUT: 20m' in text
    assert 'timeout --kill-after=30s' in text
