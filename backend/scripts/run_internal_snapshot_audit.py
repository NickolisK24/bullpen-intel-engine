"""Run the internal Phase 0H trusted snapshot audit outside the web request path.

Why this exists
---------------
The admin web route GET /api/system/internal/snapshot-audit must answer inside
Render/Gunicorn request limits (worker --timeout 60, connection-level
statement_timeout 15s). The full bounded summary reads JSON-path projections
of stored dashboard snapshot payloads, which can be too expensive for those
limits in production; the route then degrades to a DB-row fallback that is
explicitly non-ratifiable. This command runs the exact same audit builder
against DATABASE_URL as an operator process with relaxed limits, so the full
trusted-pair evidence for Decision 4/5 ratification can still be produced
without adding any public surface.

Output contract
---------------
Prints the same compact, bounded, memo-friendly audit JSON the route returns
on success. Stage checkpoints go to stderr (stage names and elapsed ms only).
No secrets are read, printed, or logged: the payload quotes stored snapshot
trust fields only, and failures report exception class names, never messages.

Exit codes: 0 = full summary produced; 1 = degraded DB-row fallback only
(NOT ratification evidence); 2 = invalid request parameters.

Usage (from backend/, e.g. a Render shell against the production service):
    python scripts/run_internal_snapshot_audit.py --window 14
    python scripts/run_internal_snapshot_audit.py --window 14 --date 2026-07-08 --compact
"""

import argparse
import json
import os
import sys
from pathlib import Path
from time import monotonic


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Operator diagnostic command, not a web worker: never kick background sync.
os.environ['AUTO_SYNC'] = 'false'

CLI_DEFAULT_STATEMENT_TIMEOUT_MS = 600000  # 10 minutes per statement.
CLI_DEFAULT_TIME_BUDGET_SECONDS = 0  # 0 disables the in-request time budget.


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Run the internal Phase 0H snapshot audit against DATABASE_URL '
            'outside the web request path. Read-only and quote-only.'
        ),
    )
    parser.add_argument(
        '--date',
        dest='product_date',
        help='Product date anchor, YYYY-MM-DD. Defaults to the latest snapshot.',
    )
    parser.add_argument(
        '--window',
        dest='window_days',
        default='14',
        help='Audit window in days (bounded server-side; default 14).',
    )
    parser.add_argument(
        '--statement-timeout-ms',
        type=int,
        default=CLI_DEFAULT_STATEMENT_TIMEOUT_MS,
        help='Per-statement Postgres timeout for this run (default 600000).',
    )
    parser.add_argument(
        '--time-budget-seconds',
        type=float,
        default=CLI_DEFAULT_TIME_BUDGET_SECONDS,
        help='Overall soft budget; 0 disables it (default 0 for CLI runs).',
    )
    parser.add_argument(
        '--compact',
        action='store_true',
        help='Print compact JSON instead of indented JSON.',
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress stage checkpoint lines on stderr.',
    )
    return parser.parse_args(argv)


def _print_json(payload, *, compact):
    print(json.dumps(
        payload,
        indent=None if compact else 2,
        sort_keys=True,
        default=str,
    ))


def main(argv=None):
    args = _parse_args(argv)

    from app import app
    from services.internal_snapshot_audit import (
        SnapshotAuditRequestError,
        build_internal_snapshot_audit_fallback_payload,
        build_internal_snapshot_audit_payload,
        error_payload,
    )

    started = monotonic()
    stages = []

    def checkpoint(stage_name):
        stages.append(stage_name)
        if not args.quiet:
            elapsed_ms = int((monotonic() - started) * 1000)
            print(
                f'[snapshot-audit-cli] stage={stage_name} elapsed_ms={elapsed_ms}',
                file=sys.stderr,
            )

    with app.app_context():
        try:
            payload = build_internal_snapshot_audit_payload(
                product_date=args.product_date,
                window_days=args.window_days,
                checkpoint=checkpoint,
                statement_timeout_ms=args.statement_timeout_ms,
                time_budget_seconds=args.time_budget_seconds,
            )
        except SnapshotAuditRequestError as exc:
            _print_json(error_payload(str(exc), status=400), compact=args.compact)
            return 2
        except Exception as exc:
            failure_stage = stages[-1] if stages else None
            failure_code = f'summary_exception:{type(exc).__name__}'
            print(
                '[snapshot-audit-cli] summary failed; emitting DB-row '
                f'fallback (NOT ratification evidence). stage={failure_stage} '
                f'error_type={type(exc).__name__}',
                file=sys.stderr,
            )
            fallback = build_internal_snapshot_audit_fallback_payload(
                product_date=args.product_date,
                window_days=args.window_days,
                failure_stage=failure_stage,
                failure_code=failure_code,
                checkpoint=checkpoint,
            )
            _print_json(fallback, compact=args.compact)
            return 1

    _print_json(payload, compact=args.compact)
    return 0


if __name__ == '__main__':
    sys.exit(main())
