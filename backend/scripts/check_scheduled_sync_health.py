"""Report expected versus observed BaseballOS scheduled workflow runs.

This command is read-only. It queries GitHub's workflow API and exits nonzero
when an active schedule window has no workflow run after the configured grace
period. Automatic alerting requires an independent scheduler to invoke it;
running it from a GitHub scheduled workflow would share the failure domain it
is intended to observe.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timedelta, timezone


DEFAULT_REPOSITORY = 'NickolisK24/bullpen-intel-engine'
DEFAULT_WORKFLOW_ID = 287009741
DEFAULT_LOOKBACK_HOURS = 36
DEFAULT_GRACE_MINUTES = 90

SCHEDULES = (
    {'cron': '11 2,4,6 * * *', 'mode': 'postgame', 'hours': (2, 4, 6), 'minute': 11},
    {'cron': '17 10 * * *', 'mode': 'daily', 'hours': (10,), 'minute': 17},
    {'cron': '23 14 * * *', 'mode': 'morning', 'hours': (14,), 'minute': 23},
)


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


def _expected_windows(now: datetime, lookback: timedelta) -> list[dict]:
    now = now.astimezone(timezone.utc)
    start = now - lookback
    day = start.date()
    windows = []
    while day <= now.date():
        for schedule in SCHEDULES:
            for hour in schedule['hours']:
                expected_at = datetime.combine(
                    day,
                    time(hour=hour, minute=schedule['minute'], tzinfo=timezone.utc),
                )
                if start <= expected_at <= now:
                    windows.append({
                        'cron': schedule['cron'],
                        'mode': schedule['mode'],
                        'expected_at': expected_at,
                    })
        day = date.fromordinal(day.toordinal() + 1)
    return sorted(windows, key=lambda window: window['expected_at'])


def evaluate_schedule_health(
    runs: list[dict],
    *,
    now: datetime,
    lookback: timedelta,
    grace: timedelta,
) -> dict:
    """Match scheduled runs to expected windows without mutating any state."""
    now = now.astimezone(timezone.utc)
    eligible = [
        window for window in _expected_windows(now, lookback)
        if window['expected_at'] + grace <= now
    ]
    observed = sorted(
        (
            run for run in runs
            if run.get('event') == 'schedule' and run.get('created_at')
        ),
        key=lambda run: _parse_timestamp(run['created_at']),
    )
    used_run_ids = set()
    results = []

    for window in eligible:
        match = None
        for run in observed:
            run_key = run.get('id') or run['created_at']
            if run_key in used_run_ids:
                continue
            created_at = _parse_timestamp(run['created_at'])
            delay = created_at - window['expected_at']
            if timedelta(0) <= delay <= grace:
                match = run
                used_run_ids.add(run_key)
                break

        row = {
            'cron': window['cron'],
            'mode': window['mode'],
            'expected_at': window['expected_at'].isoformat().replace('+00:00', 'Z'),
            'observed': match is not None,
        }
        if match is not None:
            row.update({
                'run_id': match.get('id'),
                'created_at': match['created_at'],
                'status': match.get('status'),
                'conclusion': match.get('conclusion'),
                'head_sha': match.get('head_sha'),
            })
        results.append(row)

    missing = [row for row in results if not row['observed']]
    return {
        'status': 'healthy' if not missing else 'stale',
        'checked_at': now.isoformat().replace('+00:00', 'Z'),
        'grace_minutes': int(grace.total_seconds() // 60),
        'expected_window_count': len(results),
        'missing_window_count': len(missing),
        'windows': results,
    }


def _request_json(url: str, token: str | None) -> dict:
    headers = {
        'Accept': 'application/vnd.github+json',
        'User-Agent': 'baseballos-scheduler-health',
        'X-GitHub-Api-Version': '2022-11-28',
    }
    if token:
        headers['Authorization'] = f'Bearer {token}'
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError('must be greater than zero')
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repository', default=DEFAULT_REPOSITORY)
    parser.add_argument('--workflow-id', type=_positive_int, default=DEFAULT_WORKFLOW_ID)
    parser.add_argument('--lookback-hours', type=_positive_int, default=DEFAULT_LOOKBACK_HOURS)
    parser.add_argument('--grace-minutes', type=_positive_int, default=DEFAULT_GRACE_MINUTES)
    args = parser.parse_args(argv)

    base = f'https://api.github.com/repos/{args.repository}/actions/workflows/{args.workflow_id}'
    query = urllib.parse.urlencode({'event': 'schedule', 'per_page': 100})
    try:
        workflow = _request_json(base, os.environ.get('GITHUB_TOKEN'))
        payload = _request_json(f'{base}/runs?{query}', os.environ.get('GITHUB_TOKEN'))
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        print(json.dumps({'status': 'query_error', 'error': str(exc)}, sort_keys=True))
        return 2

    report = evaluate_schedule_health(
        payload.get('workflow_runs', []),
        now=datetime.now(timezone.utc),
        lookback=timedelta(hours=args.lookback_hours),
        grace=timedelta(minutes=args.grace_minutes),
    )
    report.update({
        'repository': args.repository,
        'workflow_id': args.workflow_id,
        'workflow_state': workflow.get('state'),
    })
    if workflow.get('state') != 'active':
        report['status'] = 'inactive'

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report['status'] == 'healthy' else 1


if __name__ == '__main__':
    sys.exit(main())
