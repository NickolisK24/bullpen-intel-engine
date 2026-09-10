"""Verify the COMMITTED official pitching-line repair against DATABASE_URL. Read-only.

This command writes nothing. It opens no write transaction, takes no advisory lock, runs no
migration, and never imports or calls the apply entrypoint. It proves, from the durable
execution ledger and from live evidence, that the approved 675-action repair committed and
that every applicable post-commit check now passes.

It exists because the apply run's own post-commit wrapper returned a false negative: it
required every boolean reconciliation to be true in BOTH aggregation modes, and
``all_mandatory_metrics_match`` is false by design in local-only mode because it is an
official-validation reconciliation that local-only cannot evaluate. The historical apply
artifact is not rewritten — it records the decision that run actually made — and this is a
separate, later verification that reaches its own conclusion.

Re-running the apply is forbidden and unnecessary. The ledger already holds exactly one
completed execution for the approved fingerprint, and the apply path refuses a second one.

Exit codes (from the result):
    0  pass          — the ledger proves the approved repair, the reviewed amendment row
                       holds its corrected state, and completeness, local-only aggregation,
                       and official validation all pass under their applicable contracts.
                       Foundation 3A becomes eligible for a SEPARATE gate decision.
    1  fail          — the committed record or a repaired row contradicts the approved
                       result, or an applicable check failed.
    2  inconclusive  — a required read-only source could not be observed, so a check could
                       not run and the question stays open.

Only exception class names are reported on crash; messages and payloads are discarded because
database and network errors can carry connection details. No database URL is ever emitted.
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

CAPABILITY = 'official_pitching_line_repair_closeout_2026_v1'
# Duplicated as a literal so a wrong confirmation is rejected before any import that could
# open a database connection. DISTINCT from the apply phrase on purpose: a read-only closeout
# must never be confirmable with the phrase that authorises a write. The service holds the
# authoritative copy and a test proves the two agree.
CONFIRMATION_PHRASE = 'VERIFY-2026-PITCHING-LINE-REPAIR-CLOSEOUT'
CRASH_EXIT_CODE = 1
INCONCLUSIVE_EXIT_CODE = 2


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=('Verify the committed official pitching-line repair. Read-only: no '
                     'scope, fingerprint, override, or apply inputs exist.'),
    )
    parser.add_argument(
        '--confirm-closeout', required=True,
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
    """Emit the complete closeout artifact. It is never truncated."""
    encoded = _serialize(payload, compact=compact)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded + '\n', encoding='utf-8')
    print(encoded)


def _refusal_payload(reason):
    return {
        'capability': CAPABILITY,
        'mode': 'closeout_verification',
        'result': 'inconclusive',
        'exit_code': INCONCLUSIVE_EXIT_CODE,
        'decision_reasons': [reason],
        'database_writes_performed': False,
        'repair_reapplied': False,
        'foundation_3b_gate': 'blocked',
        'public_reader_gate': 'blocked',
        'team_state_performance_gate': 'blocked',
        'share_card_performance_gate': 'blocked',
        'sc_05_gate': 'blocked',
    }


def _failure_payload(exc):
    payload = _refusal_payload('closeout_command_failed')
    payload['result'] = 'fail'
    payload['exit_code'] = CRASH_EXIT_CODE
    payload['error_type'] = type(exc).__name__
    return payload


def main(argv=None):
    args = _parse_args(argv)

    # Confirmation is checked FIRST, before importing the application. A wrong phrase must
    # never reach application bootstrap, an engine, or a database connection.
    if args.confirm_closeout != CONFIRMATION_PHRASE:
        payload = _refusal_payload('confirmation_phrase_mismatch')
        _emit(payload, compact=args.compact, output=args.output)
        if not args.quiet:
            print('[official-pitching-line-repair-closeout-2026] '
                  'refused: confirmation phrase mismatch; no bootstrap, no reads',
                  file=sys.stderr)
        return INCONCLUSIVE_EXIT_CODE

    try:
        from app import app
        from services import official_pitching_line_repair_closeout_2026 as closeout

        if closeout.CONFIRMATION_PHRASE != CONFIRMATION_PHRASE:
            payload = _refusal_payload('confirmation_phrase_contract_drift')
            _emit(payload, compact=args.compact, output=args.output)
            return INCONCLUSIVE_EXIT_CODE

        generated_at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        with app.app_context():
            payload = closeout.run_closeout_verification(
                generated_at=generated_at,
                closeout_git_sha=os.environ.get('GITHUB_SHA'),
            )
    except Exception as exc:  # noqa: BLE001 — surface a clean nonzero exit
        payload = _failure_payload(exc)

    _emit(payload, compact=args.compact, output=args.output)
    if not args.quiet:
        print(
            '[official-pitching-line-repair-closeout-2026] '
            f"result={payload.get('result')} "
            f"writes={payload.get('database_writes_performed')} "
            f"reapplied={payload.get('repair_reapplied')} "
            f"failed={payload.get('failed_checks')} "
            f"not_executed={payload.get('not_executed_checks')} "
            f"reasons={payload.get('decision_reasons')} "
            f"error_type={payload.get('error_type')}",
            file=sys.stderr,
        )
    return int(payload.get('exit_code', CRASH_EXIT_CODE))


if __name__ == '__main__':
    sys.exit(main())
