#!/usr/bin/env python3
"""Run the governed exact phantom GameLog reconciliation."""

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
        raise argparse.ArgumentTypeError('value must be a positive integer.') from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError('value must be a positive integer.')
    return parsed


def _date(value):
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError('game-date must be YYYY-MM-DD.') from exc


def _parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--game-log-id', required=True, type=_positive_int)
    parser.add_argument('--game-pk', required=True, type=_positive_int)
    parser.add_argument('--game-date', required=True, type=_date)
    parser.add_argument('--pitcher-mlb-id', required=True, type=_positive_int)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--confirmation')
    parser.add_argument('--expected-fingerprint')
    parser.add_argument('--compact', action='store_true')
    parser.add_argument('--output', type=Path)
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    try:
        from app import app
        from services.phantom_game_log_reconciliation import run_reconciliation
        from utils.db import db

        with app.app_context():
            payload = run_reconciliation(
                game_log_id=args.game_log_id,
                expected_game_pk=args.game_pk,
                expected_game_date=args.game_date,
                expected_pitcher_mlb_id=args.pitcher_mlb_id,
                apply=args.apply,
                confirmation=args.confirmation,
                expected_fingerprint=args.expected_fingerprint,
                session=db.session,
            )
    except Exception as exc:  # noqa: BLE001
        payload = {
            'capability': 'phantom_game_log_reconciliation_v1',
            'mode': 'apply' if args.apply else 'dry_run',
            'result': 'fail',
            'exit_code': 1,
            'decision_reasons': ['phantom_reconciliation_bootstrap_failed'],
            'error_type': type(exc).__name__,
            'database_writes_performed': False,
            'rows_deleted': 0,
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
        '[phantom-game-log-reconciliation] '
        f"result={payload.get('result')} mode={payload.get('mode')} "
        f"reasons={payload.get('decision_reasons')}",
        file=sys.stderr,
    )
    return int(payload.get('exit_code', 1))


if __name__ == '__main__':
    raise SystemExit(main())
