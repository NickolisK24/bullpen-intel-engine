"""Run the governed one-row unresolved appearance-team repair against DATABASE_URL."""

from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ['AUTO_SYNC'] = 'false'


def _positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError('must be a positive integer.') from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError('must be a positive integer.')
    return parsed


def _iso_date(value):
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError('must be YYYY-MM-DD.') from exc


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Dry-run or apply one governed unresolved 2026 appearance-team repair.',
    )
    parser.add_argument('--game-log-id', required=True, type=_positive_int)
    parser.add_argument('--game-pk', required=True, type=_positive_int)
    parser.add_argument('--game-date', required=True, type=_iso_date)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirmation')
    parser.add_argument('--expected-fingerprint')
    parser.add_argument('--compact', action='store_true')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--quiet', action='store_true')
    return parser.parse_args(argv)


def _emit(payload, *, compact, output):
    encoded = json.dumps(payload, indent=None if compact else 2, sort_keys=True, default=str)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded + '\n', encoding='utf-8')
    print(encoded)


def main(argv=None):
    args = _parse_args(argv)
    try:
        from app import app
        from services import unresolved_appearance_team_repair_2026 as repair

        with app.app_context():
            payload = repair.run_repair(
                game_log_id=args.game_log_id,
                expected_game_pk=args.game_pk,
                expected_game_date=args.game_date,
                apply=args.apply,
                confirmation=args.confirmation,
                expected_fingerprint=args.expected_fingerprint,
            )
    except Exception as exc:  # noqa: BLE001
        payload = {
            'capability': 'unresolved_appearance_team_repair_2026_v1',
            'result': 'fail',
            'exit_code': 1,
            'database_writes_performed': False,
            'decision_reasons': ['command_execution_failed'],
            'error_type': type(exc).__name__,
        }

    _emit(payload, compact=args.compact, output=args.output)
    if not args.quiet:
        print(
            '[unresolved-appearance-team-repair-2026] '
            f"result={payload.get('result')} mode={payload.get('mode')} "
            f"reasons={payload.get('decision_reasons')}",
            file=sys.stderr,
        )
    return int(payload.get('exit_code', 1))


if __name__ == '__main__':
    sys.exit(main())
