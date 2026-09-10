import argparse
import json
import logging
import os
import sys
from datetime import date, timedelta
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# This command is a background data ingestion runner. It must not start the web
# process' optional in-process scheduler while running headless.
os.environ['AUTO_SYNC'] = 'false'

# Default rolling window (days) around the product current date when no explicit
# dates are given: recent past for "consecutive games", near future for "games
# ahead" / "next off day".
DEFAULT_WINDOW_BACK_DAYS = 10
DEFAULT_WINDOW_FORWARD_DAYS = 10


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Ingest a window of the MLB schedule into scheduled_games.'
    )
    parser.add_argument(
        '--start-date',
        dest='start_date',
        help='First schedule date to ingest, YYYY-MM-DD. '
             'Defaults to product current date minus 10 days.',
    )
    parser.add_argument(
        '--end-date',
        dest='end_date',
        help='Last schedule date to ingest, YYYY-MM-DD. '
             'Defaults to product current date plus 10 days.',
    )
    parser.add_argument(
        '--source',
        default='schedule_ingestion',
        help='Provenance label stored on each row.',
    )
    return parser.parse_args(argv)


def _resolve_window(start_raw, end_raw, today):
    """Resolve (start_date, end_date) as ISO strings, defaulting to a window."""
    start = date.fromisoformat(start_raw) if start_raw else (
        today - timedelta(days=DEFAULT_WINDOW_BACK_DAYS))
    end = date.fromisoformat(end_raw) if end_raw else (
        today + timedelta(days=DEFAULT_WINDOW_FORWARD_DAYS))
    if end < start:
        raise ValueError(f'end-date {end} is before start-date {start}')
    return start.isoformat(), end.isoformat()


def main(argv=None):
    args = _parse_args(argv)
    source = str(args.source or 'schedule_ingestion')[:40]
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )

    from app import app
    from services.availability_reference_date import product_current_date
    from services import schedule_ingestion

    try:
        with app.app_context():
            start_iso, end_iso = _resolve_window(
                args.start_date, args.end_date, product_current_date())
            summary = schedule_ingestion.ingest_schedule(
                start_iso, end_iso, source=source)
    except Exception as exc:  # noqa: BLE001 — surface a clean nonzero exit
        print(json.dumps({'status': 'error', 'error': str(exc)}, sort_keys=True))
        return 1

    out = {
        'status': 'ok' if summary.get('errors', 0) == 0 else 'partial',
        'source': source,
        'start_date': start_iso,
        'end_date': end_iso,
        'summary': summary,
    }
    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
