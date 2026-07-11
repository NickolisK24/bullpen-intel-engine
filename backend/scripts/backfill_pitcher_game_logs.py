from argparse import ArgumentParser
from datetime import date
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from services.pitcher_game_log_backfill import (  # noqa: E402
    DEFAULT_SOURCE,
    backfill_pitcher_game_logs,
)


def main():
    parser = ArgumentParser(
        description=(
            'Backfill finalized regular-season pitcher game logs and reconcile '
            'starter-assignment ledger coverage.'
        )
    )
    parser.add_argument('--season', type=int, required=True)
    parser.add_argument('--through-date', required=True)
    parser.add_argument('--source', default=DEFAULT_SOURCE)
    parser.add_argument('--pitcher-mlb-id', type=int, default=None)
    parser.add_argument('--limit', type=int, default=None)
    parser.add_argument(
        '--apply',
        action='store_true',
        help='Persist rows and coverage records. Without this flag, rolls back.',
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        summary = backfill_pitcher_game_logs(
            season=args.season,
            through_date=date.fromisoformat(args.through_date),
            source=args.source,
            apply=args.apply,
            pitcher_mlb_id=args.pitcher_mlb_id,
            limit=args.limit,
        )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
