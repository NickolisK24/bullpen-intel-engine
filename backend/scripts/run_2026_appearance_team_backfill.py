"""Run the governed 2026 team-at-appearance backfill against DATABASE_URL.

Foundation 2 of 6. Attributes legacy 2026 ``GameLog`` rows (``appearance_team_status
IS NULL``) to the MLB team the pitcher represented, resolved from official game-side
evidence via the Foundation 1 resolver/parser — never from the pitcher's mutable
current team assignment.

DRY RUN IS THE DEFAULT: it writes nothing, prints a deterministic JSON plan, and
reports the batch fingerprint. Writing requires ``--apply`` AND
``--confirm RUN_2026_APPEARANCE_TEAM_BACKFILL``; an optional
``--expected-fingerprint`` must match the computed plan or the run is refused before
any write. The keyset cursor (``--after-game-date`` / ``--after-game-pk``, echoed back
as ``next_cursor``) resumes a large sweep across runs.

Exit codes:
    0  completed         — dry run, or apply, with no per-game failures
    1  refused           — apply gate not satisfied (phrase/fingerprint); nothing written
    2  completed_with_failures / failed — a game failed, or an invalid stored state
                            was detected (the latter must never happen)

Only exception class names are reported; messages are discarded because database and
network errors can carry connection details.
"""

from __future__ import annotations

import argparse
from datetime import date
import json
import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Operator batch command, not a web worker: never start the in-process scheduler.
os.environ['AUTO_SYNC'] = 'false'

CAPABILITY = 'appearance_team_backfill_2026_v1'
CONFIRMATION_PHRASE = 'RUN_2026_APPEARANCE_TEAM_BACKFILL'
EXIT_BY_RESULT = {
    'completed': 0,
    'refused': 1,
    'completed_with_failures': 2,
    'failed': 2,
}
DEFAULT_BATCH_SIZE = 200
MAX_BATCH_SIZE = 2000


def _iso_date(value):
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError('date must be ISO-8601 (YYYY-MM-DD).') from exc


def _bounded_batch_size(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError('batch-size must be an integer.') from exc
    if parsed < 1 or parsed > MAX_BATCH_SIZE:
        raise argparse.ArgumentTypeError(
            f'batch-size must be between 1 and {MAX_BATCH_SIZE}.'
        )
    return parsed


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Run the governed 2026 team-at-appearance backfill (dry run by default).'
        ),
    )
    parser.add_argument('--start-date', type=_iso_date, default=_iso_date('2026-01-01'))
    parser.add_argument('--end-date', type=_iso_date, default=_iso_date('2026-12-31'))
    parser.add_argument('--season', type=int, default=2026)
    parser.add_argument('--batch-size', type=_bounded_batch_size, default=DEFAULT_BATCH_SIZE)
    parser.add_argument('--after-game-date', type=_iso_date, default=None)
    parser.add_argument('--after-game-pk', type=int, default=None)
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Persist attributions. Without this flag the run writes nothing.',
    )
    parser.add_argument(
        '--confirm',
        default=None,
        help=f'Required with --apply; must be exactly {CONFIRMATION_PHRASE}.',
    )
    parser.add_argument(
        '--expected-fingerprint',
        default=None,
        help='Optional approved batch fingerprint; apply is refused unless it matches.',
    )
    parser.add_argument(
        '--no-api',
        action='store_true',
        help='Resolve from local evidence only; never call the MLB box-score API.',
    )
    parser.add_argument('--compact', action='store_true', help='Print compact JSON.')
    parser.add_argument('--output', type=Path, help='Also write the clean JSON artifact here.')
    parser.add_argument('--quiet', action='store_true', help='Suppress the stderr result line.')
    return parser.parse_args(argv)


def _serialize(payload, *, compact):
    return json.dumps(
        payload, indent=None if compact else 2, sort_keys=True, default=str,
    )


def _emit(payload, *, compact, output):
    encoded = _serialize(payload, compact=compact)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded + '\n', encoding='utf-8')
    print(encoded)


def _validate_cursor(args):
    if (args.after_game_date is None) != (args.after_game_pk is None):
        raise SystemExit(
            'after-game-date and after-game-pk must be provided together.'
        )


def _failure_payload(exc):
    return {
        'capability': CAPABILITY,
        'result': 'failed',
        'database_writes_performed': False,
        # Messages can carry connection/network detail; report only the type.
        'error_type': type(exc).__name__,
    }


def main(argv=None):
    args = _parse_args(argv)
    _validate_cursor(args)

    try:
        from app import app
        from services import appearance_team_backfill_2026 as backfill

        with app.app_context():
            payload = backfill.run_backfill(
                start_date=args.start_date,
                end_date=args.end_date,
                batch_size=args.batch_size,
                after_game_date=args.after_game_date,
                after_game_pk=args.after_game_pk,
                apply=args.apply,
                confirmation=args.confirm,
                expected_fingerprint=args.expected_fingerprint,
                allow_api=not args.no_api,
                season=args.season,
            )
    except Exception as exc:  # noqa: BLE001 — surface a clean nonzero exit
        payload = _failure_payload(exc)

    _emit(payload, compact=args.compact, output=args.output)
    if not args.quiet:
        print(
            '[appearance-team-backfill-2026] '
            f"result={payload.get('result')} "
            f"mode={payload.get('mode')} "
            f"fingerprint={payload.get('batch_fingerprint')} "
            f"error_type={payload.get('error_type')}",
            file=sys.stderr,
        )
    return EXIT_BY_RESULT.get(payload.get('result'), 2)


if __name__ == '__main__':
    sys.exit(main())
