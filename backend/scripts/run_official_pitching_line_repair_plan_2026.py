"""Generate the official pitching-line repair PLAN against DATABASE_URL (READ ONLY).

The merged completeness diagnostic proved the 2026 local GameLog ledger is short of the
official pitching-line population. This command turns that proof into a deterministic,
reviewable repair manifest: which official MLB identities must exist first, which official
pitching lines have no local row, and which stored rows differ from official evidence.

It PLANS. It never applies. There is no apply flag, no fingerprint-acceptance flag, and no
write path anywhere in this command. It reports ``database_writes_performed: false``.

The full-season run (no --team-id, no --game-pk) is the only artifact eligible for
fingerprint review. A scoped run returns plan_scope=diagnostic_subset and
repair_apply_gate=blocked_subset_not_apply_eligible.

Exit codes (from the result):
    0  pass          — every defect line maps to a supported action, the accepted baseline
                       still holds, and the manifest is ready for fingerprint review.
    1  fail          — a contradictory population exists (extra, duplicate, or
                       appearance-team-mismatched line), or a reconciliation failed.
    2  inconclusive  — official evidence is unavailable, the accepted baseline drifted, an
                       identity cannot be represented safely, or the run was scoped.

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

CAPABILITY = 'official_pitching_line_repair_plan_2026_v1'
CRASH_EXIT_CODE = 1
MAX_PREVIEW_LIMIT = 500


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
    if parsed < 0 or parsed > MAX_PREVIEW_LIMIT:
        raise argparse.ArgumentTypeError(f'must be between 0 and {MAX_PREVIEW_LIMIT}.')
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
        description='Generate the official pitching-line repair plan (read-only).',
    )
    parser.add_argument('--season', type=int, default=2026)
    parser.add_argument('--as-of-date', type=_iso_date, default=_iso_date('2026-07-25'))
    parser.add_argument('--preview-limit', type=_bounded_limit, default=100)
    parser.add_argument('--team-id', type=_positive_int, default=None,
                        help='Optional diagnostic-only scope; not apply eligible.')
    parser.add_argument('--game-pk', type=_positive_int, default=None,
                        help='Optional diagnostic-only scope; not apply eligible.')
    parser.add_argument('--compact', action='store_true', help='Print compact JSON.')
    parser.add_argument('--output', type=Path, help='Also write the clean JSON artifact here.')
    parser.add_argument('--quiet', action='store_true', help='Suppress the stderr result line.')
    return parser.parse_args(argv)


def _serialize(payload, *, compact):
    return json.dumps(payload, indent=None if compact else 2, sort_keys=True, default=str)


def _emit(payload, *, compact, output):
    """Emit the payload. The repair manifest is written in full and never truncated."""
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
        from services import official_pitching_line_repair_plan_2026 as planner

        generated_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        with app.app_context():
            payload = planner.run_repair_plan(
                season=args.season,
                as_of_date=args.as_of_date,
                preview_limit=args.preview_limit,
                team_id=args.team_id,
                game_pk=args.game_pk,
                generated_at=generated_at,
            )
    except Exception as exc:  # noqa: BLE001 — surface a clean nonzero exit
        payload = _failure_payload(exc)

    _emit(payload, compact=args.compact, output=args.output)
    if not args.quiet:
        print(
            '[official-pitching-line-repair-plan-2026] '
            f"result={payload.get('result')} "
            f"plan_status={payload.get('plan_status')} "
            f"plan_scope={payload.get('plan_scope')} "
            f"actions={payload.get('repair_manifest_action_count')} "
            f"fingerprint={payload.get('repair_manifest_fingerprint')} "
            f"error_type={payload.get('error_type')}",
            file=sys.stderr,
        )
    return int(payload.get('exit_code', CRASH_EXIT_CODE))


if __name__ == '__main__':
    sys.exit(main())
