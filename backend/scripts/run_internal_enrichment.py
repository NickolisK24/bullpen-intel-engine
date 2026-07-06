import argparse
import json
import logging
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# This command is a background enrichment runner. It must not start the web
# process' optional in-process scheduler while running in GitHub Actions.
os.environ['AUTO_SYNC'] = 'false'


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Run BaseballOS internal evidence/read enrichment.'
    )
    parser.add_argument(
        '--mode',
        choices=('daily', 'postgame'),
        default='daily',
        help='Date selection mode when --date is omitted.',
    )
    parser.add_argument(
        '--date',
        dest='product_date',
        help='Product/schedule date to enrich, YYYY-MM-DD.',
    )
    parser.add_argument(
        '--source',
        default='github_actions_internal',
        help='SyncRun source label to persist with durable sync metadata.',
    )
    parser.add_argument(
        '--skip-backtest',
        action='store_true',
        help='Skip availability backtest refresh for postgame-only enrichment.',
    )
    return parser.parse_args(argv)


def _parse_product_date(value):
    if not value:
        return None
    return date.fromisoformat(value)


def main(argv=None):
    args = _parse_args(argv)
    source = str(args.source or 'github_actions_internal')[:30]
    product_date = _parse_product_date(args.product_date)
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )

    from app import app
    from services import sync as sync_service
    from services import sync_metadata
    from services.availability_reference_date import resolve_product_day

    if product_date is None:
        now = datetime.now(timezone.utc)
        product_date = (
            sync_service.postgame_schedule_date(now)
            if args.mode == 'postgame'
            else resolve_product_day(now).calendar_date
        )

    status = sync_service.run_internal_enrichment(
        app,
        product_dates=[product_date],
        source=source,
        include_backtest=not args.skip_backtest,
    )
    summary = {
        'status': status.get('status'),
        'source': source,
        'mode': args.mode,
        'product_date': product_date.isoformat(),
        'include_backtest': not args.skip_backtest,
        'sync': status,
    }
    print(json.dumps(summary, sort_keys=True, default=str))

    return 0 if status.get('status') in sync_metadata.SUCCESSFUL_STATUSES else 1


if __name__ == '__main__':
    raise SystemExit(main())
