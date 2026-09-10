from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from scripts import check_scheduled_sync_health as health


REPO_ROOT = Path(__file__).resolve().parents[2]
SYNC_WORKFLOW = REPO_ROOT / '.github' / 'workflows' / 'baseballos-sync.yml'
HEALTH_WORKFLOW = REPO_ROOT / '.github' / 'workflows' / 'baseballos-scheduler-health.yml'


def _run(run_id, created_at, conclusion='success'):
    return {
        'id': run_id,
        'event': 'schedule',
        'created_at': created_at,
        'status': 'completed',
        'conclusion': conclusion,
        'head_sha': f'sha-{run_id}',
    }


def test_schedule_trigger_conditions_and_concurrency_are_pinned():
    text = SYNC_WORKFLOW.read_text(encoding='utf-8')
    workflow = yaml.safe_load(text)
    crons = [entry['cron'] for entry in workflow[True]['schedule']]

    assert crons == ['17 10 * * *', '23 14 * * *', '11 2,4,6 * * *']
    assert workflow['concurrency'] == {
        'group': 'baseballos-sync',
        'cancel-in-progress': False,
    }
    for cron in crons:
        assert f"github.event.schedule == '{cron}'" in text


def test_health_report_identifies_the_exact_missing_window():
    report = health.evaluate_schedule_health(
        [
            _run(1, '2026-08-27T02:45:00Z'),
            _run(2, '2026-08-27T04:50:00Z'),
        ],
        now=datetime(2026, 8, 27, 10, 0, tzinfo=timezone.utc),
        lookback=timedelta(hours=10),
        grace=timedelta(minutes=90),
    )

    assert report['status'] == 'stale'
    assert report['missing_window_count'] == 1
    assert report['windows'][-1] == {
        'cron': '11 2,4,6 * * *',
        'mode': 'postgame',
        'expected_at': '2026-08-27T06:11:00Z',
        'observed': False,
    }


def test_health_report_retains_failed_runs_as_observed_attempts():
    report = health.evaluate_schedule_health(
        [_run(3, '2026-08-27T11:10:00Z', conclusion='failure')],
        now=datetime(2026, 8, 27, 13, 0, tzinfo=timezone.utc),
        lookback=timedelta(hours=3),
        grace=timedelta(minutes=90),
    )

    assert report['status'] == 'healthy'
    assert report['windows'][0]['conclusion'] == 'failure'


def test_health_diagnostic_is_manual_read_only_and_outside_writer_concurrency():
    workflow = yaml.safe_load(HEALTH_WORKFLOW.read_text(encoding='utf-8'))
    triggers = workflow[True]
    blob = HEALTH_WORKFLOW.read_text(encoding='utf-8')

    assert sorted(triggers) == ['workflow_dispatch']
    assert workflow['permissions'] == {'contents': 'read', 'actions': 'read'}
    assert 'concurrency:' not in blob
    assert 'DATABASE_URL' in blob
    assert 'run_daily_sync.py' not in blob
    assert 'run_postgame_refresh.py' not in blob
    assert 'check_scheduled_sync_health.py' in blob


def test_production_health_separates_external_authority_from_freshness():
    report = health.evaluate_production_health(
        [{
            'id': 7,
            'source': 'github_schedule',
            'outcome': 'executed',
            'intended_window': 'daily:2026-08-27',
        }],
        now=datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc),
        lookback=timedelta(hours=3),
        grace=timedelta(minutes=90),
    )

    assert report['external_scheduler']['status'] == 'degraded'
    assert report['production_freshness']['status'] == 'healthy'
