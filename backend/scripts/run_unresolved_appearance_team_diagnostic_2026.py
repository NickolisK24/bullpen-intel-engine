#!/usr/bin/env python3
"""Run the private read-only unresolved appearance-team identity diagnostic."""

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


def _date(value):
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('game-date must be YYYY-MM-DD.') from exc


def _positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError('value must be a positive integer.') from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError('value must be a positive integer.')
    return parsed


def _parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--game-log-id', required=True, type=_positive_int)
    parser.add_argument('--game-pk', required=True, type=_positive_int)
    parser.add_argument('--game-date', required=True, type=_date)
    parser.add_argument('--compact', action='store_true')
    parser.add_argument('--output', type=Path)
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    try:
        from app import app
        from services.unresolved_appearance_team_diagnostic_2026 import run_diagnostic
        from utils.db import db

        with app.app_context():
            payload = run_diagnostic(
                game_log_id=args.game_log_id,
                expected_game_pk=args.game_pk,
                expected_game_date=args.game_date,
                session=db.session,
            )
    except Exception as exc:  # noqa: BLE001
        payload = {
            'capability': 'unresolved_appearance_team_diagnostic_2026_v1',
            'mode': 'read_only',
            'result': 'fail',
            'exit_code': 1,
            'decision_reasons': ['diagnostic_execution_failed'],
            'error_type': type(exc).__name__,
            'database_writes_performed': False,
        }

    encoded = json.dumps(
        payload,
        indent=None if args.compact else 2,
        sort_keys=True,
        default=str,
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + '\n', encoding='utf-8')
    print(encoded)
    print(
        '[unresolved-appearance-team-diagnostic-2026] '
        f"result={payload.get('result')} reasons={payload.get('decision_reasons')}",
        file=sys.stderr,
    )
    return int(payload.get('exit_code', 1))


if __name__ == '__main__':
    raise SystemExit(main())
