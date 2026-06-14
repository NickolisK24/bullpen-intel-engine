import json
import logging
import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# This command is a standalone snapshot job, not the daily data sync runner.
os.environ['AUTO_SYNC'] = 'false'

from app import app
from services.dashboard_snapshot import build_bullpen_dashboard_snapshot_v2


def main():
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )
    with app.app_context():
        result = build_bullpen_dashboard_snapshot_v2()
    print(json.dumps(result, sort_keys=True))
    return 0 if result.get('status') == 'ready' else 1


if __name__ == '__main__':
    raise SystemExit(main())
