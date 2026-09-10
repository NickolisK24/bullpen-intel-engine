import argparse
import json
import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ['AUTO_SYNC'] = 'false'


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Refresh stored availability operational backtest results.'
    )
    parser.add_argument(
        '--seasons',
        default='2026,2025',
        help='Comma-separated seasons to compute, default 2026,2025.',
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    seasons = [
        int(part.strip())
        for part in str(args.seasons).split(',')
        if part.strip()
    ]

    from app import app
    from services.availability_backtest import refresh_availability_backtest

    with app.app_context():
        payload = refresh_availability_backtest(seasons=seasons)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
