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


SUCCESS_STATUSES = frozenset({'off', 'complete', 'skipped'})


def _compact_cycle_payload(payload):
    return {
        'event': 'continuous_cycle',
        'mode': payload.get('mode'),
        'sync_run_id': payload.get('sync_run_id'),
        'games_checked': payload.get('games_checked'),
        'changed_games': payload.get('changed_games'),
        'unchanged_games': payload.get('unchanged_games'),
        'rejected_observations': payload.get('rejected_observations'),
        'source_failures': payload.get('source_failures'),
        'failures': len(payload.get('failures') or ()),
        'source_requests': payload.get('source_requests'),
        'source_retries': payload.get('source_retries'),
        'runtime_ms': payload.get('runtime_ms'),
        'status': payload.get('status'),
        'reason_code': payload.get('reason_code'),
        'canonical_actions': payload.get('canonical_actions'),
        'canonical_mutation_games': payload.get('canonical_mutation_games'),
        'live_publications': payload.get('live_publications'),
        'cache_handoffs': payload.get('cache_handoffs'),
        'production_authority_affected': payload.get(
            'production_authority_affected'
        ),
        'timeout_reached': payload.get('timeout_reached'),
        'source_budget_exhausted': payload.get('source_budget_exhausted'),
        'circuit_breaker_open': payload.get('circuit_breaker_open'),
    }


def _changed_game_payload(observation):
    differences = observation.get('differences') or {}
    return {
        'event': 'game_changed',
        'game_pk': observation.get('game_pk'),
        'classification': observation.get('classification'),
        'finality': observation.get('finality_state'),
        'differences': list(differences.keys()),
    }


def render_output(payload, *, full_json=False):
    if full_json:
        return (json.dumps(payload, indent=2, sort_keys=True),)
    lines = [json.dumps(_compact_cycle_payload(payload), separators=(',', ':'))]
    if payload.get('changed_games', 0) > 0:
        lines.extend(
            json.dumps(_changed_game_payload(observation), separators=(',', ':'))
            for observation in payload.get('detection_results') or ()
            if observation.get('changed') is True
        )
    return tuple(lines)


def exit_code(payload):
    return 0 if payload['status'] in SUCCESS_STATUSES else 1


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
    parser.add_argument(
        '--full-json', action='store_true',
        help='Print the complete pretty-formatted cycle result for debugging.',
    )
    args = parser.parse_args()
    with app.app_context():
        result = run_continuous_cycle(
            mode=args.mode,
            represented_time=args.represented_time,
        )
    payload = result.to_dict()
    for line in render_output(payload, full_json=args.full_json):
        print(line)
    return exit_code(payload)


if __name__ == '__main__':
    raise SystemExit(main())
