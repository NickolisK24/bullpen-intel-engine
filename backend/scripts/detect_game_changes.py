"""Run one bounded CU-02 detection cycle without downstream ingestion/publication."""

from __future__ import annotations

import argparse
import json
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Detection is deliberately schedule-independent. Importing the Flask module
# must not bootstrap its optional in-process scheduler.
os.environ['AUTO_SYNC'] = 'false'

from app import app  # noqa: E402
from services.game_change_detection import detect_active_slate_changes  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description='Detect material MLB game changes; performs no downstream work.',
    )
    parser.add_argument('--reference-date', help='UTC date (YYYY-MM-DD); default today')
    parser.add_argument('--correction-days', type=int, default=2)
    args = parser.parse_args()

    with app.app_context():
        result = detect_active_slate_changes(
            reference_date=args.reference_date,
            correction_days=args.correction_days,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result['source_failures'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
