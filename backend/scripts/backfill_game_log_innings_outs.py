import argparse
import json
import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ['AUTO_SYNC'] = 'false'

from app import app
from services.innings_backfill import (  # noqa: E402
    backfill_game_log_innings_outs,
    count_raw_mlb_fraction_rows,
    repair_missing_innings_outs,
)
from utils.db import db  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description='Backfill game_logs innings_pitched_outs from stored innings_pitched values.',
    )
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Persist the backfill. Without this flag the command reports a dry run.',
    )
    parser.add_argument(
        '--missing-outs-only',
        action='store_true',
        help='Repair only rows where innings_pitched_outs is null.',
    )
    args = parser.parse_args()

    with app.app_context():
        if args.missing_outs_only:
            stats = repair_missing_innings_outs(db.session, apply=args.apply)
        else:
            stats = backfill_game_log_innings_outs(db.session, apply=args.apply)
        payload = stats.to_dict()
        payload['mode'] = 'apply' if args.apply else 'dry_run'
        payload['scope'] = 'missing_outs_only' if args.missing_outs_only else 'all_game_logs'
        payload['raw_mlb_fraction_rows_remaining'] = count_raw_mlb_fraction_rows(db.session)

    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if payload['rows_flagged_anomalous'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
