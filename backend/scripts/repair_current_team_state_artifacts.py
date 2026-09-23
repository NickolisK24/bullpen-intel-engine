"""Governed, idempotent repair of the current League Board artifact set."""

import argparse
import json
import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
os.environ['AUTO_SYNC'] = 'false'


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--output')
    args = parser.parse_args(argv)

    from app import app
    from services.dashboard_snapshot import get_latest_valid_dashboard_snapshot
    from services.league_team_state_artifact_recovery import (
        repair_current_snapshot_artifacts,
    )

    with app.app_context():
        snapshot = get_latest_valid_dashboard_snapshot()
        result = repair_current_snapshot_artifacts(snapshot)
        payload = result.to_dict()

    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n',
            encoding='utf-8',
        )
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
