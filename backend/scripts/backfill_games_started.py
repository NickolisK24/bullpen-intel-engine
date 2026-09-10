from argparse import ArgumentParser
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from services.games_started_backfill import (  # noqa: E402
    DEFAULT_CHECKPOINT_PATH,
    backfill_games_started,
)


def main():
    parser = ArgumentParser(
        description='Backfill null GameLog.games_started values from MLB game logs.'
    )
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--checkpoint', default=str(DEFAULT_CHECKPOINT_PATH))
    parser.add_argument('--limit', type=int, default=None)
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        summary = backfill_games_started(
            checkpoint_path=args.checkpoint,
            apply=args.apply,
            limit=args.limit,
        )
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
