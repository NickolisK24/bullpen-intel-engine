"""Run one non-scheduled CU-02 -> CU-03 proof cycle for a game."""

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
from services.change_impact_orchestration import detect_and_orchestrate_game  # noqa: E402


def main():
    parser = argparse.ArgumentParser(
        description='Detect and non-authoritatively orchestrate one MLB game.',
    )
    parser.add_argument('game_pk', type=int)
    parser.add_argument('--apply-reviewed-canonical-plan', action='store_true')
    parser.add_argument('--expected-plan-fingerprint')
    args = parser.parse_args()
    if args.apply_reviewed_canonical_plan and not args.expected_plan_fingerprint:
        parser.error('--expected-plan-fingerprint is required when applying a plan')

    with app.app_context():
        result = detect_and_orchestrate_game(
            args.game_pk,
            allow_canonical_write=args.apply_reviewed_canonical_plan,
            expected_plan_fingerprint=args.expected_plan_fingerprint,
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    status = result['orchestration']['orchestration_status']
    return 1 if status == 'canonical_failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
