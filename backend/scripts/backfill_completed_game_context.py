import argparse
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# This is a manual backfill runner; never start the in-process scheduler.
os.environ['AUTO_SYNC'] = 'false'


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Backfill completed_game_context rows for already-processed historical '
            'games. Requires an explicit date range or a limit.'
        )
    )
    parser.add_argument('--start-date', dest='start_date',
                        help='Earliest game date to backfill, YYYY-MM-DD.')
    parser.add_argument('--end-date', dest='end_date',
                        help='Latest game date to backfill, YYYY-MM-DD.')
    parser.add_argument('--team-id', dest='team_id', type=int,
                        help='Only backfill games involving this MLB team id.')
    parser.add_argument('--limit', dest='limit', type=int,
                        help='Maximum number of candidate games to examine.')
    parser.add_argument('--dry-run', dest='dry_run', action='store_true',
                        help='Report what would be processed without fetching or writing.')
    parser.add_argument('--force', dest='force', action='store_true',
                        help='Rederive and upsert even when context already exists.')
    parser.add_argument('--strict', dest='strict', action='store_true',
                        help='Abort the whole backfill on the first game failure.')
    return parser.parse_args(argv)


def _parse_date(value):
    if not value:
        return None
    return date.fromisoformat(value)


def main(argv=None):
    args = _parse_args(argv)
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )

    from app import app
    from services import completed_game_context_backfill as backfill

    try:
        summary = backfill.run_backfill(
            app,
            start_date=_parse_date(args.start_date),
            end_date=_parse_date(args.end_date),
            team_id=args.team_id,
            limit=args.limit,
            dry_run=bool(args.dry_run),
            force=bool(args.force),
            strict=bool(args.strict),
        )
    except ValueError as exc:
        print(json.dumps({'error': str(exc)}, sort_keys=True))
        return 2

    print(json.dumps(summary, sort_keys=True))
    return 0 if summary['games_failed'] == 0 else 1


if __name__ == '__main__':
    raise SystemExit(main())
