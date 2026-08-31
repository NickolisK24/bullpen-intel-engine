"""CLI for read-only production accuracy reconciliation."""

import argparse
import json
import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
os.environ['AUTO_SYNC'] = 'false'


def _args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--snapshot-id', type=int)
    target.add_argument('--current', action='store_true')
    parser.add_argument('--json', dest='json_path')
    parser.add_argument('--require-mlb', action='store_true')
    parser.add_argument('--skip-mlb', action='store_true')
    return parser.parse_args(argv)


def render_console(report):
    lines = [
        'BASEBALLOS PRODUCTION ACCURACY RECONCILIATION',
        f"Snapshot: {report.get('snapshot_id')}",
        f"Data through: {report.get('data_through')}",
    ]
    labels = {
        'publication_coherence': 'Publication coherence',
        'games': 'Games',
        'pitching_appearances': 'Pitching appearances',
        'bullpen_membership': 'Bullpen membership',
        'workload_values': 'Workload values',
        'rest_patterns': 'Rest patterns',
        'arm_reads': 'Arm reads',
        'team_states': 'Team States',
        'team_aggregates': 'Team aggregates',
        'served_read_models': 'Served read models',
    }
    for key, item in report.get('domains', {}).items():
        lines.append(f"{labels.get(key, key):24} {item['correct']}/{item['checked']} {item['status']}")
    lines.append('MLB reconciliation:')
    for key, item in report.get('external_mlb', {}).items():
        if item['checked']:
            measure = f"{item['correct']}/{item['checked']}"
        else:
            measure = f"0 compared; {item['unproven']} unproven"
        lines.append(f"{key.replace('_', ' ').title():24} {measure} {item['status']}")
    lines.extend([
        f"Incorrect: {sum(item['incorrect'] for item in report.get('domains', {}).values())}",
        f"Unproven: {sum(item['unproven'] for item in report.get('external_mlb', {}).values())}",
        f"VERDICT: {report.get('verdict')}",
    ])
    return '\n'.join(lines)


def main(argv=None):
    args = _args(argv)
    from app import app
    from services.production_accuracy_reconciliation import (
        NOT_VERIFIED, reconcile_external_mlb, reconcile_publication, resolve_snapshot,
    )
    with app.app_context():
        snapshot = resolve_snapshot(snapshot_id=args.snapshot_id, current=args.current)
        external = None
        if snapshot is not None and not args.skip_mlb:
            external = reconcile_external_mlb(snapshot)
        report = reconcile_publication(
            snapshot,
            external_domains=external,
            external_required=args.require_mlb,
        )
    print(render_console(report))
    if args.json_path:
        destination = Path(args.json_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    return 1 if report['verdict'] == NOT_VERIFIED else 0


if __name__ == '__main__':
    raise SystemExit(main())
