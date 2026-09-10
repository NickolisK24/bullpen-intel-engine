import argparse
import json
import logging
import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ['AUTO_SYNC'] = 'false'


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Repair governed intraday schedule changes, process newly-final games, '
            'and publish refreshed BaseballOS intelligence surfaces.'
        )
    )
    parser.add_argument('--source', default='github_actions')
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )

    from app import app
    from services import sync_metadata
    from services.intraday_completed_game_repair import (
        run_intraday_completed_game_repair,
    )

    result = run_intraday_completed_game_repair(
        app,
        source=str(args.source or 'github_actions')[:30],
    )
    print(json.dumps(result, sort_keys=True, default=str))
    return 0 if result.get('status') == sync_metadata.STATUS_SUCCESS else 1


if __name__ == '__main__':
    raise SystemExit(main())
