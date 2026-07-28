"""Diagnose ONE exact-to-defective pitching-line transition against DATABASE_URL (READ ONLY).

The repaired repair-planner ran cleanly in production and still returned inconclusive on a
single moved line: official MLB person 805299, Brandyn Garcia, relieving for official team 109
in game 825058, stored locally as GameLog 43765. The local row says one hit; the current
official box score says zero.

This command asks only which side moved. It reproduces the current mismatch from live official
evidence and the live local row, then searches every durable local source that could establish
a PRIOR value on either side. If no durable source retains one, it reports
``historical_state_unprovable`` and exits inconclusive. Absence of history is never reported as
proof that MLB changed the box score.

It DIAGNOSES. It never repairs. There is no apply flag, no fingerprint-acceptance flag, no
baseline amendment, and no write path anywhere in this command. It reports
``database_writes_performed: false``.

The target is fixed. There are no scope inputs, because a diagnostic that could be pointed at
any line would be a general tool rather than an answer to this question.

Exit codes (from the result):
    0  pass          — the source of the transition is proven by durable evidence.
    1  fail          — contradictory identities, duplicate official or local lines, an
                       appearance-team mismatch, or a failed reconciliation.
    2  inconclusive  — the current mismatch is reproduced but the historical source of the
                       transition cannot be proven from retained evidence.

Only exception class names are reported on crash; messages/payloads are discarded because
database and network errors can carry connection details. Raw MLB payloads are never printed
to the step summary; the complete artifact ships privately.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Operator read command, not a web worker: never start the in-process scheduler.
os.environ['AUTO_SYNC'] = 'false'

CAPABILITY = 'official_pitching_line_transition_diagnostic_2026_v1'
CRASH_EXIT_CODE = 1


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Diagnose the Brandyn Garcia exact-to-defective pitching-line transition '
            '(read-only). The target line is fixed and cannot be redirected.'),
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
        from services import official_pitching_line_transition_diagnostic_2026 as diagnostic

        now = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        with app.app_context():
            payload = diagnostic.run_transition_diagnostic(
                generated_at=now, retrieved_at=now)
    except Exception as exc:  # noqa: BLE001 — surface a clean nonzero exit
        payload = _failure_payload(exc)

    _emit(payload, compact=args.compact, output=args.output)
    if not args.quiet:
        print(
            '[official-pitching-line-transition-diagnostic-2026] '
            f"result={payload.get('result')} "
            f"classification={payload.get('authority_transition_classification')} "
            f"confidence={payload.get('confidence')} "
            f"historical_evidence_found={payload.get('historical_evidence_found')} "
            f"writes={payload.get('database_writes_performed')} "
            f"error_type={payload.get('error_type')}",
            file=sys.stderr,
        )
    return int(payload.get('exit_code', CRASH_EXIT_CODE))


if __name__ == '__main__':
    sys.exit(main())
