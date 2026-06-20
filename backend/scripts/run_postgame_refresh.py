import argparse
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# This command is a background data sync runner. It must not start the web
# process' optional in-process scheduler while running in GitHub Actions.
os.environ['AUTO_SYNC'] = 'false'


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Run BaseballOS completed-game bullpen workload refresh.'
    )
    parser.add_argument(
        '--date',
        dest='schedule_date',
        help='MLB schedule date to inspect, YYYY-MM-DD. Defaults to the current baseball slate date.',
    )
    parser.add_argument(
        '--source',
        default='github_actions',
        help='SyncRun source label to persist with durable sync metadata.',
    )
    return parser.parse_args(argv)


def _parse_schedule_date(value):
    if not value:
        return None
    return date.fromisoformat(value)


def main(argv=None):
    args = _parse_args(argv)
    source = str(args.source or 'github_actions')[:30]
    schedule_date = _parse_schedule_date(args.schedule_date)
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )

    from app import app
    from services import sync as sync_service
    from services import sync_metadata

    status = sync_service.run_postgame_refresh(
        app,
        schedule_date=schedule_date,
        source=source,
    )
    summary = {
        'status': status.get('status'),
        'source': source,
        'schedule_date': status.get('schedule_date'),
        'sync': status,
    }
    print(json.dumps(summary, sort_keys=True))

    return 0 if status.get('status') in sync_metadata.SUCCESSFUL_STATUSES else 1


if __name__ == '__main__':
    raise SystemExit(main())
