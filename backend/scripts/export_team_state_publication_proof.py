"""Export the durable Team State proof for one exact trusted publication."""

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
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--snapshot-id', type=int)
    target.add_argument('--current', action='store_true')
    parser.add_argument('--output', required=True)
    parser.add_argument('--observation-output')
    args = parser.parse_args(argv)

    from app import app
    from services.production_accuracy_reconciliation import resolve_snapshot
    from services.team_state_vnext_production_proof import load_durable_proof, write_proof

    with app.app_context():
        snapshot = resolve_snapshot(snapshot_id=args.snapshot_id, current=args.current)
        if snapshot is None:
            if args.observation_output:
                marker = Path(args.observation_output)
                marker.parent.mkdir(parents=True, exist_ok=True)
                marker.write_text(
                    json.dumps({'publication_observed': False, 'snapshot_id': None}) + '\n',
                    encoding='utf-8',
                )
                print('No target publication exists; no proof is required for this observation.')
                return 0
            print('No target publication exists.', file=sys.stderr)
            return 2
        row = load_durable_proof(snapshot.id)
        if row is None:
            print(
                f'Required Team State proof missing for snapshot_id={snapshot.id}.',
                file=sys.stderr,
            )
            return 3
        proof = row.proof
        if args.observation_output:
            marker = Path(args.observation_output)
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(
                json.dumps({'publication_observed': True, 'snapshot_id': snapshot.id}) + '\n',
                encoding='utf-8',
            )
    write_proof(proof, args.output)
    print(f'Exported Team State proof for snapshot_id={snapshot.id}.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
