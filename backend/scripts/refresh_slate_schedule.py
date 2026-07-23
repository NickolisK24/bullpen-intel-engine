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

os.environ['AUTO_SYNC'] = 'false'


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Refresh the BaseballOS rolling slate schedule authority and rebuild '
            'the Tonight public snapshot from the same schedule state.'
        )
    )
    parser.add_argument('--reference-date', help='Eastern slate date, YYYY-MM-DD.')
    parser.add_argument('--source', default='morning_slate_schedule')
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )
    reference_date = date.fromisoformat(args.reference_date) if args.reference_date else None

    from app import app
    from services.schedule_tonight_refresh import refresh_schedule_and_tonight

    try:
        with app.app_context():
            result = refresh_schedule_and_tonight(
                reference_date,
                source=str(args.source)[:40],
            )
    except Exception as exc:  # noqa: BLE001 - command must surface a nonzero failure
        print(json.dumps({'status': 'failed', 'error': str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0 if result['status'] == 'ok' else 1


if __name__ == '__main__':
    raise SystemExit(main())
