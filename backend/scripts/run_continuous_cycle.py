"""Run one bounded CU-08 cycle; this command never installs a schedule."""

from __future__ import annotations

import argparse
import json
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.environ['AUTO_SYNC'] = 'false'

from app import app  # noqa: E402
from services.continuous_execution import (  # noqa: E402
    ActivationMode,
    run_continuous_cycle,
)


def main():
    parser = argparse.ArgumentParser(
        description='Run one fail-closed, bounded continuous-update cycle.',
    )
    parser.add_argument(
        '--mode', choices=[mode.value for mode in ActivationMode],
        help='Explicit mode override; execution kill switch still applies.',
    )
    parser.add_argument(
        '--represented-time',
        help='Timezone-explicit ISO timestamp; defaults to current UTC once.',
    )
    args = parser.parse_args()
    with app.app_context():
        result = run_continuous_cycle(
            mode=args.mode,
            represented_time=args.represented_time,
        )
    payload = result.to_dict()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload['status'] in {'off', 'complete', 'skipped'} else 1


if __name__ == '__main__':
    raise SystemExit(main())
