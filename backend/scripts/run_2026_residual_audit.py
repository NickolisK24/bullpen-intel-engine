"""Run the read-only 2026 residual appearance-team audit against DATABASE_URL.

Classifies every 2026 legacy-NULL GameLog appearance into exactly one deterministic
exclusion category and proves how many are actually eligible under the exact
Foundation 2 selection query (must be zero). Performs NO database write — only SELECTs
and in-memory classification. A private JSON artifact can be written to ``--output``.

Exit codes (from the audit result):
    0  pass          — every residual row classified; zero backfill-eligible; reconciled
    1  fail          — backfill-eligible rows remain, totals do not reconcile, an invalid
                       stored state exists, or the migration head is wrong
    2  inconclusive  — some rows unclassified, or no residual rows to audit

Only exception class names are reported; messages are discarded because database errors
can carry connection details.
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

# Operator diagnostic command, not a web worker: never start background sync.
os.environ['AUTO_SYNC'] = 'false'

CAPABILITY = 'appearance_team_residual_audit_2026_v1'
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
        raise argparse.ArgumentTypeError('limit must be an integer.') from exc
    if parsed < 0 or parsed > MAX_DETAIL_LIMIT:
        raise argparse.ArgumentTypeError(f'limit must be between 0 and {MAX_DETAIL_LIMIT}.')
    return parsed


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Run the read-only 2026 residual appearance-team audit.',
    )
    parser.add_argument('--season', type=int, default=2026)
    parser.add_argument('--campaign-start-date', type=_iso_date, default=_iso_date('2026-01-01'))
    parser.add_argument('--campaign-end-date', type=_iso_date, default=_iso_date('2026-07-25'))
    parser.add_argument('--row-detail-limit', type=_bounded_limit, default=50)
    parser.add_argument('--game-detail-limit', type=_bounded_limit, default=50)
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
        from services import appearance_team_residual_audit_2026 as audit

        generated_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        with app.app_context():
            payload = audit.run_residual_audit(
                season=args.season,
                campaign_start_date=args.campaign_start_date,
                campaign_end_date=args.campaign_end_date,
                row_detail_limit=args.row_detail_limit,
                game_detail_limit=args.game_detail_limit,
                generated_at=generated_at,
            )
    except Exception as exc:  # noqa: BLE001 — surface a clean nonzero exit
        payload = _failure_payload(exc)

    _emit(payload, compact=args.compact, output=args.output)
    if not args.quiet:
        print(
            '[appearance-team-residual-audit-2026] '
            f"result={payload.get('result')} "
            f"eligible={payload.get('exact_backfill_eligible_rows')} "
            f"unclassified={payload.get('unclassified_rows')} "
            f"error_type={payload.get('error_type')}",
            file=sys.stderr,
        )
    return int(payload.get('exit_code', CRASH_EXIT_CODE))


if __name__ == '__main__':
    sys.exit(main())
