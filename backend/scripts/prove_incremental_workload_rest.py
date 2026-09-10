"""Run one dormant CU-02 -> CU-03 -> CU-01 -> CU-04 proof cycle."""

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
from services.incremental_workload_rest import (  # noqa: E402
    recompute_workload_rest_impact,
)


def main():
    parser = argparse.ArgumentParser(
        description=(
            'Run one explicitly authorized, non-publishing CU-04 proof cycle.'
        ),
    )
    parser.add_argument('game_pk', type=int)
    parser.add_argument(
        '--data-through', required=True,
        help='Represented baseball date (YYYY-MM-DD), never server-local now.',
    )
    parser.add_argument('--apply-reviewed-canonical-plan', action='store_true')
    parser.add_argument('--expected-plan-fingerprint')
    args = parser.parse_args()
    if args.apply_reviewed_canonical_plan and not args.expected_plan_fingerprint:
        parser.error('--expected-plan-fingerprint is required when applying a plan')

    with app.app_context():
        upstream = detect_and_orchestrate_game(
            args.game_pk,
            allow_canonical_write=args.apply_reviewed_canonical_plan,
            expected_plan_fingerprint=args.expected_plan_fingerprint,
        )
        workload_rest = recompute_workload_rest_impact(
            upstream['orchestration'], data_through=args.data_through,
        )
    result = {
        **upstream,
        'workload_rest': workload_rest.to_dict(),
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if workload_rest.status == 'partial' else 0


if __name__ == '__main__':
    raise SystemExit(main())
