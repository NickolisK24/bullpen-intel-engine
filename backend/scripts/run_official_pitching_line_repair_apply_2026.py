"""Apply the ONE reviewed official pitching-line repair manifest against DATABASE_URL.

This command mutates production data. It does so exactly once, for exactly one approved
manifest fingerprint, or it writes nothing at all.

It takes no governed inputs. There is no season flag, no date flag, no team or game scope, no
action-count flag, no fingerprint flag, and no override flag — every governed value is fixed
in ``services.official_pitching_line_repair_apply_2026``. The only argument that gates
execution is the fixed confirmation phrase, and a wrong phrase fails before the Flask
application is imported and therefore before any database connection is opened.

The planner is regenerated from live production state immediately before the write
transaction and the regenerated manifest fingerprint must equal the approved constant
exactly. A one-character difference aborts before the first write, and there is no way for an
operator to proceed past a mismatch.

Exit codes (from the result):
    0  pass          — the approved manifest was regenerated, applied atomically, verified in
                       transaction, committed, and all post-commit verification passed.
    1  fail          — a contradiction was found, a verification failed, or post-commit
                       verification failed. Downstream gates stay blocked.
    2  inconclusive  — nothing was written: a mutable precondition changed, the approved
                       fingerprint was not regenerated, the advisory lock was unavailable, or
                       the repair was already completed.

Only exception class names are reported on crash; messages and payloads are discarded because
database and network errors can carry connection details. Raw MLB payloads are never printed
and no database URL is ever emitted.
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

# Operator write command, not a web worker: never start the in-process scheduler.
os.environ['AUTO_SYNC'] = 'false'

CAPABILITY = 'official_pitching_line_repair_apply_2026_v1'
# Duplicated as a literal so a wrong confirmation is rejected before any import that could
# open a database connection. The service holds the authoritative copy and a test proves the
# two agree.
CONFIRMATION_PHRASE = 'APPLY-2026-PITCHING-LINE-REPAIR-3EE2EA06'
CRASH_EXIT_CODE = 1
INCONCLUSIVE_EXIT_CODE = 2


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=('Apply the reviewed official pitching-line repair manifest. '
                     'No scope, fingerprint, or override inputs exist.'),
    )
    parser.add_argument(
        '--confirm-apply', required=True,
        help='Exact governed confirmation phrase. Any other value refuses before bootstrap.')
    parser.add_argument('--compact', action='store_true', help='Print compact JSON.')
    parser.add_argument('--output', type=Path,
                        help='Also write the complete private JSON artifact here.')
    parser.add_argument('--quiet', action='store_true',
                        help='Suppress the stderr result line.')
    return parser.parse_args(argv)


def _serialize(payload, *, compact):
    return json.dumps(payload, indent=None if compact else 2, sort_keys=True, default=str)


def _emit(payload, *, compact, output):
    """Emit the complete execution artifact. It is never truncated."""
    encoded = _serialize(payload, compact=compact)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded + '\n', encoding='utf-8')
    print(encoded)


def _refusal_payload(reason):
    return {
        'capability': CAPABILITY,
        'mode': 'apply',
        'result': 'inconclusive',
        'exit_code': INCONCLUSIVE_EXIT_CODE,
        'decision_reasons': [reason],
        'transaction_committed': False,
        'database_writes_performed': False,
        'foundation_3b_gate': 'blocked',
        'public_reader_gate': 'blocked',
        'team_state_performance_gate': 'blocked',
        'share_card_performance_gate': 'blocked',
        'sc_05_gate': 'blocked',
    }


def _failure_payload(exc):
    payload = _refusal_payload('apply_command_failed')
    payload['result'] = 'fail'
    payload['exit_code'] = CRASH_EXIT_CODE
    payload['error_type'] = type(exc).__name__
    return payload


def main(argv=None):
    args = _parse_args(argv)

    # Confirmation is checked FIRST, before importing the application. A wrong phrase must
    # never reach application bootstrap, an engine, or a database connection.
    if args.confirm_apply != CONFIRMATION_PHRASE:
        payload = _refusal_payload('confirmation_phrase_mismatch')
        _emit(payload, compact=args.compact, output=args.output)
        if not args.quiet:
            print('[official-pitching-line-repair-apply-2026] '
                  'refused: confirmation phrase mismatch; no bootstrap, no writes',
                  file=sys.stderr)
        return INCONCLUSIVE_EXIT_CODE

    try:
        from app import app
        from services import official_pitching_line_repair_apply_2026 as apply_service

        if apply_service.CONFIRMATION_PHRASE != CONFIRMATION_PHRASE:
            payload = _refusal_payload('confirmation_phrase_contract_drift')
            _emit(payload, compact=args.compact, output=args.output)
            return INCONCLUSIVE_EXIT_CODE

        generated_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        with app.app_context():
            payload = apply_service.apply_reviewed_repair(
                generated_at=generated_at,
                apply_git_sha=os.environ.get('GITHUB_SHA'),
            )
    except Exception as exc:  # noqa: BLE001 — surface a clean nonzero exit
        payload = _failure_payload(exc)

    _emit(payload, compact=args.compact, output=args.output)
    if not args.quiet:
        print(
            '[official-pitching-line-repair-apply-2026] '
            f"result={payload.get('result')} "
            f"committed={payload.get('transaction_committed')} "
            f"writes={payload.get('database_writes_performed')} "
            f"ledger={payload.get('execution_ledger_id')} "
            f"applied={payload.get('action_counts_applied')} "
            f"reasons={payload.get('decision_reasons')} "
            f"error_type={payload.get('error_type')}",
            file=sys.stderr,
        )
    return int(payload.get('exit_code', CRASH_EXIT_CODE))


if __name__ == '__main__':
    sys.exit(main())
