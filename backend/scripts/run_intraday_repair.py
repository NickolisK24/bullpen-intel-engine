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
            'Detect and repair governed intraday roster-status changes, refresh '
            'recent workload, recalculate fatigue, and rebuild public snapshots.'
        )
    )
    parser.add_argument('--source', default='github_actions')
    parser.add_argument('--days-back', type=int, default=7)
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )

    from app import app
    from services.intraday_repair import run_intraday_roster_repair
    from services import sync_metadata

    result = run_intraday_roster_repair(
        app,
        source=str(args.source or 'github_actions')[:30],
        days_back=max(int(args.days_back or 0), 1),
    )
    print(json.dumps(result, sort_keys=True, default=str))
    return 0 if result.get('status') == sync_metadata.STATUS_SUCCESS else 1


if __name__ == '__main__':
    raise SystemExit(main())
