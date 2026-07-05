import argparse
import json
import logging
import os
import signal
import sys
import threading
from datetime import date, timedelta
from pathlib import Path
from time import perf_counter


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
DEFAULT_SCHEDULE_TIMEOUT_SECONDS = 180.0
DEFAULT_WARM_TIMEOUT_SECONDS = 300.0
_FALSEY_TIMEOUT_VALUES = {'0', 'false', 'no', 'off', ''}
_TIMEOUT_DISABLED = object()


class TonightRefreshTimeout(TimeoutError):
    """Raised when a Tonight refresh phase exceeds its configured budget."""


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


def _resolve_timeout_seconds(env_name, default):
    raw = os.environ.get(env_name)
    if raw is None:
        return default

    value = raw.strip().lower()
    if value in _FALSEY_TIMEOUT_VALUES:
        return None

    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return default

    return seconds if seconds > 0 else None


def _format_timeout(timeout_seconds):
    return 'disabled' if timeout_seconds is None else f'{timeout_seconds:g}'


def _timeout_supported():
    return (
        threading.current_thread() is threading.main_thread()
        and hasattr(signal, 'SIGALRM')
        and hasattr(signal, 'setitimer')
        and hasattr(signal, 'ITIMER_REAL')
    )


def _run_with_timeout(fn, *, phase_name, timeout_seconds):
    if timeout_seconds is None:
        return fn()

    if not _timeout_supported():
        logger.warning(
            '%s timeout unavailable on this runtime; continuing without a hard '
            'bound (timeout_seconds=%s).',
            phase_name,
            _format_timeout(timeout_seconds),
        )
        return fn()

    previous_handler = signal.getsignal(signal.SIGALRM)

    def _raise_timeout(_signum, _frame):
        raise TonightRefreshTimeout(
            f'{phase_name} exceeded {timeout_seconds:g}s')

    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        return fn()
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def _warm_tonight(warm_fn, today, source, *, timeout_seconds):
    """Build/overwrite the Tonight snapshot; report failure without raising.

    Empty Tonight cards are a valid state (no team playing, or nothing clears a
    signal) — not a failure. A genuine build/write failure is logged and reported
    so it is visible, but it never crashes the refresh: schedule rows are already
    committed and the endpoint falls back to an on-demand build.
    """
    started = perf_counter()
    logger.info(
        'Tonight snapshot warm starting: reference_date=%s source=%s '
        'timeout_seconds=%s.',
        today,
        source,
        _format_timeout(timeout_seconds),
    )
    try:
        response = _run_with_timeout(
            lambda: warm_fn(today, source) or {},
            phase_name='Tonight snapshot warm',
            timeout_seconds=timeout_seconds,
        )
        elapsed_ms = round((perf_counter() - started) * 1000, 1)
        logger.info(
            'Tonight snapshot warm completed: reference_date=%s status=%s '
            'card_count=%s empty_reason=%s elapsed_ms=%s.',
            today,
            response.get('status'),
            response.get('card_count', 0),
            response.get('empty_reason'),
            elapsed_ms,
        )
        return {
            'status': response.get('status'),
            'card_count': response.get('card_count', 0),
            'empty_reason': response.get('empty_reason'),
        }
    except TonightRefreshTimeout as exc:
        elapsed_ms = round((perf_counter() - started) * 1000, 1)
        logger.warning(
            'Tonight snapshot warm timed out for %s after %ss '
            '(elapsed_ms=%s); schedule refresh will finish and the endpoint '
            'can build on demand: %s',
            today,
            _format_timeout(timeout_seconds),
            elapsed_ms,
            exc,
        )
        return {
            'status': 'failed',
            'error': str(exc),
            'timeout_seconds': timeout_seconds,
        }
    except Exception as exc:  # noqa: BLE001 — warm is best-effort, never fatal
        elapsed_ms = round((perf_counter() - started) * 1000, 1)
        logger.warning(
            'Tonight snapshot warm failed for %s after %sms: %s',
            today,
            elapsed_ms,
            exc,
        )
        return {'status': 'failed', 'error': str(exc)}


def run_refresh(
    app,
    *,
    source,
    reference_date,
    ingest_fn,
    today_fn,
    warm_fn,
    schedule_timeout_seconds=_TIMEOUT_DISABLED,
    warm_timeout_seconds=_TIMEOUT_DISABLED,
):
    """Orchestrate the refresh; dependencies are injected so it stays testable.

    A schedule-ingestion exception propagates (a true failure → nonzero exit). A
    Tonight warm failure is caught and reported (the schedule was still refreshed).
    """
    if schedule_timeout_seconds is _TIMEOUT_DISABLED:
        schedule_timeout_seconds = _resolve_timeout_seconds(
            'TONIGHT_REFRESH_SCHEDULE_TIMEOUT_SECONDS',
            DEFAULT_SCHEDULE_TIMEOUT_SECONDS,
        )
    if warm_timeout_seconds is _TIMEOUT_DISABLED:
        warm_timeout_seconds = _resolve_timeout_seconds(
            'TONIGHT_REFRESH_WARM_TIMEOUT_SECONDS',
            DEFAULT_WARM_TIMEOUT_SECONDS,
        )

    with app.app_context():
        today = _resolve_today(reference_date, today_fn())
        start_iso, end_iso = _window(today)
        schedule_started = perf_counter()
        logger.info(
            'Schedule refresh starting: start_date=%s end_date=%s source=%s '
            'timeout_seconds=%s.',
            start_iso,
            end_iso,
            source,
            _format_timeout(schedule_timeout_seconds),
        )
        try:
            schedule_summary = _run_with_timeout(
                lambda: ingest_fn(start_iso, end_iso, source=source),
                phase_name='Schedule refresh',
                timeout_seconds=schedule_timeout_seconds,
            )
        except TonightRefreshTimeout as exc:
            elapsed_ms = round((perf_counter() - schedule_started) * 1000, 1)
            logger.error(
                'Schedule refresh timed out: start_date=%s end_date=%s '
                'source=%s timeout_seconds=%s elapsed_ms=%s.',
                start_iso,
                end_iso,
                source,
                _format_timeout(schedule_timeout_seconds),
                elapsed_ms,
            )
            raise
        except Exception:
            elapsed_ms = round((perf_counter() - schedule_started) * 1000, 1)
            logger.exception(
                'Schedule refresh failed: start_date=%s end_date=%s source=%s '
                'elapsed_ms=%s.',
                start_iso,
                end_iso,
                source,
                elapsed_ms,
            )
            raise

        schedule_elapsed_ms = round((perf_counter() - schedule_started) * 1000, 1)
        logger.info(
            'Schedule refresh completed: games_seen=%s games_ingested=%s '
            'rows_created=%s rows_updated=%s errors=%s elapsed_ms=%s.',
            (schedule_summary or {}).get('games_seen'),
            (schedule_summary or {}).get('games_ingested'),
            (schedule_summary or {}).get('rows_created'),
            (schedule_summary or {}).get('rows_updated'),
            (schedule_summary or {}).get('errors'),
            schedule_elapsed_ms,
        )
        tonight = _warm_tonight(
            warm_fn,
            today,
            source,
            timeout_seconds=warm_timeout_seconds,
        )

    schedule_errors = (schedule_summary or {}).get('errors', 0)
    return {
        'status': 'ok' if schedule_errors == 0 else 'partial',
        'source': source,
        'reference_date': today.isoformat(),
        'schedule_window': {'start_date': start_iso, 'end_date': end_iso},
        'schedule': schedule_summary,
        'tonight_snapshot': tonight,
        'timeouts': {
            'schedule_seconds': schedule_timeout_seconds,
            'warm_seconds': warm_timeout_seconds,
        },
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
