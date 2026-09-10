"""Run the canonical 2026 season bullpen aggregation (Foundation 3A) against DATABASE_URL.

This is the single canonical read model for team-level season bullpen performance. It
aggregates completed regular-season RELIEF appearances by the historical team authority
``GameLog.appearance_team_id`` — never current roster/team/role. It is READ-ONLY: it
performs no INSERT/UPDATE/DELETE and reports ``database_writes_performed: false``.

Modes:
    local_only (default)       — pure local aggregation over canonical stored data.
    --official-validation      — additionally re-derive relief totals independently from
                                 official MLB box scores and compare every mandatory team
                                 and league total EXACTLY. No public metric ships until this
                                 matches in production.

Exit codes (from the result):
    0  pass          — local aggregation reconciled (and, with --official-validation, every
                       mandatory official comparison matched).
    1  fail          — a critical invariant failed, or a mandatory official metric mismatched.
    2  inconclusive  — starter identity incomplete, team population unestablished, or the
                       official source was unavailable.

Only exception class names are reported on crash; messages/payloads are discarded because
database and network errors can carry connection details. Raw MLB payloads are never printed.
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

# Operator read command, not a web worker: never start the in-process scheduler.
os.environ['AUTO_SYNC'] = 'false'

CAPABILITY = 'canonical_season_bullpen_aggregation_2026_v1'
CRASH_EXIT_CODE = 1
MAX_DETAIL_LIMIT = 200


def _iso_date(value):
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError('date must be ISO-8601 (YYYY-MM-DD).') from exc


def _bounded_limit(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError('must be an integer.') from exc
    if parsed < 0 or parsed > MAX_DETAIL_LIMIT:
        raise argparse.ArgumentTypeError(f'must be between 0 and {MAX_DETAIL_LIMIT}.')
    return parsed


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Run the canonical 2026 season bullpen aggregation (read-only).',
    )
    parser.add_argument('--season', type=int, default=2026)
    parser.add_argument('--as-of-date', type=_iso_date, default=_iso_date('2026-07-25'))
    parser.add_argument(
        '--official-validation', action='store_true',
        help='Independently validate relief totals against official MLB box scores.',
    )
    parser.add_argument('--team-detail-limit', type=_bounded_limit, default=40)
    parser.add_argument('--mismatch-detail-limit', type=_bounded_limit, default=60)
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
        from services import season_bullpen_aggregation_2026 as aggregation

        generated_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        with app.app_context():
            payload = aggregation.run_aggregation(
                season=args.season,
                as_of_date=args.as_of_date,
                include_official_validation=args.official_validation,
                team_detail_limit=args.team_detail_limit,
                mismatch_detail_limit=args.mismatch_detail_limit,
                generated_at=generated_at,
            )
    except Exception as exc:  # noqa: BLE001 — surface a clean nonzero exit
        payload = _failure_payload(exc)

    _emit(payload, compact=args.compact, output=args.output)
    if not args.quiet:
        print(
            '[season-bullpen-aggregation-2026] '
            f"result={payload.get('result')} "
            f"mode={payload.get('mode')} "
            f"foundation_3_status={payload.get('foundation_3_status')} "
            f"error_type={payload.get('error_type')}",
            file=sys.stderr,
        )
    return int(payload.get('exit_code', CRASH_EXIT_CODE))


if __name__ == '__main__':
    sys.exit(main())
