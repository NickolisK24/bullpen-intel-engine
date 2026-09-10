"""Run the governed 2026 opening-week schedule-authority repair against DATABASE_URL.

Reconstructs the MISSING canonical ScheduledGame authority for exactly the 47 approved
2026-03-25..29 regular-season games (418 residual pitching appearances) from official
MLB evidence, then lets the existing Foundation 1/2 resolver/backfill attribute the
appearances. It NEVER writes GameLog appearance-team fields.

DRY RUN IS THE DEFAULT: it writes nothing, prints a deterministic JSON plan, and reports
the repair fingerprint. Writing requires ``--apply`` AND
``--confirm RUN_2026_OPENING_WEEK_SCHEDULE_REPAIR`` AND a matching
``--expected-fingerprint``; any missing/mismatched gate is refused before any write.

Exit codes (from the result):
    0  pass          — dry run ready, or apply committed the 47 games cleanly
    1  fail / refused — a blocking condition, or an unsatisfied apply gate
    2  inconclusive  — the official source was unavailable, or no residual population remains

Only exception class names are reported; messages are discarded because database and
network errors can carry connection details. Raw MLB payloads are never printed.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Operator repair command, not a web worker: never start the in-process scheduler.
os.environ['AUTO_SYNC'] = 'false'

CAPABILITY = 'opening_week_schedule_authority_repair_2026_v1'
CONFIRMATION_PHRASE = 'RUN_2026_OPENING_WEEK_SCHEDULE_REPAIR'
CRASH_EXIT_CODE = 1


def _iso_date(value):
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError('date must be ISO-8601 (YYYY-MM-DD).') from exc


def _positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError('must be an integer.') from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError('must be >= 1.')
    return parsed


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Run the governed 2026 opening-week schedule-authority repair (dry run by default).',
    )
    parser.add_argument('--season', type=int, default=2026)
    parser.add_argument('--campaign-start-date', type=_iso_date, default=_iso_date('2026-03-25'))
    parser.add_argument('--campaign-end-date', type=_iso_date, default=_iso_date('2026-03-29'))
    parser.add_argument('--expected-game-count', type=_positive_int, default=47)
    parser.add_argument('--expected-residual-row-count', type=_positive_int, default=418)
    parser.add_argument(
        '--apply', action='store_true',
        help='Persist canonical schedule rows. Without this flag the run writes nothing.',
    )
    parser.add_argument(
        '--confirm', default=None,
        help=f'Required with --apply; must be exactly {CONFIRMATION_PHRASE}.',
    )
    parser.add_argument(
        '--expected-fingerprint', default=None,
        help='Required with --apply; the approved dry-run fingerprint.',
    )
    parser.add_argument('--compact', action='store_true', help='Print compact JSON.')
    parser.add_argument('--output', type=Path, help='Also write the clean JSON artifact here.')
    parser.add_argument('--quiet', action='store_true', help='Suppress the stderr result line.')
    return parser.parse_args(argv)


def _serialize(payload, *, compact):
    return json.dumps(payload, indent=None if compact else 2, sort_keys=True, default=str)


def _emit(payload, *, compact, output):
    encoded = _serialize(payload, compact=compact)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded + '\n', encoding='utf-8')
    print(encoded)


def _failure_payload(exc):
    return {
        'capability': CAPABILITY,
        'result': 'fail',
        'exit_code': CRASH_EXIT_CODE,
        'database_writes_performed': False,
        'error_type': type(exc).__name__,
    }


def main(argv=None):
    args = _parse_args(argv)
    try:
        from app import app
        from services import opening_week_schedule_authority_repair_2026 as repair

        generated_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        with app.app_context():
            payload = repair.run_repair(
                season=args.season,
                campaign_start_date=args.campaign_start_date,
                campaign_end_date=args.campaign_end_date,
                expected_game_count=args.expected_game_count,
                expected_residual_row_count=args.expected_residual_row_count,
                apply=args.apply,
                confirmation=args.confirm,
                expected_fingerprint=args.expected_fingerprint,
                generated_at=generated_at,
            )
    except Exception as exc:  # noqa: BLE001 — surface a clean nonzero exit
        payload = _failure_payload(exc)

    _emit(payload, compact=args.compact, output=args.output)
    if not args.quiet:
        print(
            '[opening-week-schedule-repair-2026] '
            f"result={payload.get('result')} "
            f"mode={payload.get('mode')} "
            f"fingerprint={payload.get('fingerprint')} "
            f"error_type={payload.get('error_type')}",
            file=sys.stderr,
        )
    return int(payload.get('exit_code', CRASH_EXIT_CODE))


if __name__ == '__main__':
    sys.exit(main())
