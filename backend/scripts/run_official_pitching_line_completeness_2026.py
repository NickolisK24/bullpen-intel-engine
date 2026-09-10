"""Run the official pitching-line completeness diagnostic against DATABASE_URL (READ ONLY).

The canonical Foundation 3A official validation failed with
``official_mandatory_metric_mismatch`` while the local-only audit passed, because the local
audit's ``complete_team_games`` counts SCHEDULED FINAL GAMES rather than verified official
pitching lines. This command identifies exactly WHICH official box-score pitching lines are
absent, extra, misclassified, misassigned, duplicated, or statistically different in the
local ``GameLog`` ledger.

It is READ-ONLY: no INSERT/UPDATE/DELETE, no backfill, no reconciliation write, no repair.
It reports ``database_writes_performed: false``.

Exit codes (from the result):
    0  pass          — every official pitching line has exactly one exact local counterpart
                       and no unmatched local line exists.
    1  fail          — official evidence proves a missing, extra, duplicate, misassigned,
                       misclassified, or differing local line.
    2  inconclusive  — required official evidence could not be fetched, or a team-game side
                       has no unique official starter.

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

CAPABILITY = 'official_pitching_line_completeness_2026_v1'
CRASH_EXIT_CODE = 1
MAX_DETAIL_LIMIT = 500


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


def _positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError('must be an integer.') from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError('must be a positive integer.')
    return parsed


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Diagnose official-vs-local pitching-line completeness (read-only).',
    )
    parser.add_argument('--season', type=int, default=2026)
    parser.add_argument('--as-of-date', type=_iso_date, default=_iso_date('2026-07-25'))
    parser.add_argument('--detail-limit', type=_bounded_limit, default=100)
    parser.add_argument('--team-id', type=_positive_int, default=None,
                        help='Optional: restrict game selection to one MLB team id.')
    parser.add_argument('--game-pk', type=_positive_int, default=None,
                        help='Optional: restrict the diagnostic to one MLB gamePk.')
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
        'mode': 'read_only',
        'result': 'fail',
        'exit_code': CRASH_EXIT_CODE,
        'database_writes_performed': False,
        'error_type': type(exc).__name__,
    }


def main(argv=None):
    args = _parse_args(argv)
    try:
        from app import app
        from services import official_pitching_line_completeness_2026 as diagnostic

        generated_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        with app.app_context():
            payload = diagnostic.run_diagnostic(
                season=args.season,
                as_of_date=args.as_of_date,
                detail_limit=args.detail_limit,
                team_id=args.team_id,
                game_pk=args.game_pk,
                generated_at=generated_at,
            )
    except Exception as exc:  # noqa: BLE001 — surface a clean nonzero exit
        payload = _failure_payload(exc)

    _emit(payload, compact=args.compact, output=args.output)
    if not args.quiet:
        print(
            '[official-pitching-line-completeness-2026] '
            f"result={payload.get('result')} "
            f"official_pitching_lines={payload.get('official_pitching_lines')} "
            f"exact_match_count={payload.get('exact_match_count')} "
            f"missing_local_line_count={payload.get('missing_local_line_count')} "
            f"extra_local_line_count={payload.get('extra_local_line_count')} "
            f"error_type={payload.get('error_type')}",
            file=sys.stderr,
        )
    return int(payload.get('exit_code', CRASH_EXIT_CODE))


if __name__ == '__main__':
    sys.exit(main())
