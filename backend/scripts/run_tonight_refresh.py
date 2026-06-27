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

# This command is a background data refresh runner. It must not start the web
# process' optional in-process scheduler while running headless.
os.environ['AUTO_SYNC'] = 'false'

logger = logging.getLogger('baseballos.tonight_refresh')

# Rolling schedule window around the product current date: recent past for
# "consecutive games", near future for "games ahead" / "next off day".
WINDOW_BACK_DAYS = 10
WINDOW_FORWARD_DAYS = 10


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Refresh the MLB schedule window and warm the Tonight snapshot.'
    )
    parser.add_argument(
        '--reference-date',
        dest='reference_date',
        help='Slate date to warm, YYYY-MM-DD. Defaults to the product current date.',
    )
    parser.add_argument(
        '--source',
        default='github_actions',
        help='Provenance label stored on schedule rows and the Tonight snapshot.',
    )
    return parser.parse_args(argv)


def _resolve_today(reference_date_raw, product_today):
    if reference_date_raw:
        return date.fromisoformat(reference_date_raw)
    return product_today


def _window(today):
    start = (today - timedelta(days=WINDOW_BACK_DAYS)).isoformat()
    end = (today + timedelta(days=WINDOW_FORWARD_DAYS)).isoformat()
    return start, end


def _warm_tonight(warm_fn, today, source):
    """Build/overwrite the Tonight snapshot; report failure without raising.

    Empty Tonight cards are a valid state (no team playing, or nothing clears a
    signal) — not a failure. A genuine build/write failure is logged and reported
    so it is visible, but it never crashes the refresh: schedule rows are already
    committed and the endpoint falls back to an on-demand build.
    """
    try:
        response = warm_fn(today, source) or {}
        return {
            'status': response.get('status'),
            'card_count': response.get('card_count', 0),
            'empty_reason': response.get('empty_reason'),
        }
    except Exception as exc:  # noqa: BLE001 — warm is best-effort, never fatal
        logger.warning('Tonight snapshot warm failed for %s: %s', today, exc)
        return {'status': 'failed', 'error': str(exc)}


def run_refresh(app, *, source, reference_date, ingest_fn, today_fn, warm_fn):
    """Orchestrate the refresh; dependencies are injected so it stays testable.

    A schedule-ingestion exception propagates (a true failure → nonzero exit). A
    Tonight warm failure is caught and reported (the schedule was still refreshed).
    """
    with app.app_context():
        today = _resolve_today(reference_date, today_fn())
        start_iso, end_iso = _window(today)
        schedule_summary = ingest_fn(start_iso, end_iso, source=source)
        tonight = _warm_tonight(warm_fn, today, source)

    schedule_errors = (schedule_summary or {}).get('errors', 0)
    return {
        'status': 'ok' if schedule_errors == 0 else 'partial',
        'source': source,
        'reference_date': today.isoformat(),
        'schedule_window': {'start_date': start_iso, 'end_date': end_iso},
        'schedule': schedule_summary,
        'tonight_snapshot': tonight,
    }


def main(argv=None):
    args = _parse_args(argv)
    source = str(args.source or 'github_actions')[:40]
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )

    from app import app
    from services.availability_reference_date import product_current_date
    from services import schedule_ingestion
    from services import tonight_intelligence_snapshot

    def _warm(today, warm_source):
        return tonight_intelligence_snapshot.generate_tonight_snapshot_for_date(
            today, source=warm_source)

    try:
        out = run_refresh(
            app,
            source=source,
            reference_date=args.reference_date,
            ingest_fn=schedule_ingestion.ingest_schedule,
            today_fn=product_current_date,
            warm_fn=_warm,
        )
    except Exception as exc:  # noqa: BLE001 — surface a clean nonzero exit
        print(json.dumps({'status': 'error', 'error': str(exc)}, sort_keys=True))
        return 1

    print(json.dumps(out, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
