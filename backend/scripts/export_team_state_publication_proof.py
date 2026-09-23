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

    from utils.read_only_app import create_read_only_app
    from services.production_accuracy_reconciliation import resolve_snapshot
    from services.team_state_vnext_production_proof import (
        FAILURE_PROOF_ARTIFACT_MISSING,
        FAILURE_PROOF_EXPORT_ENVIRONMENT_INVALID,
        FAILURE_PROOF_EXPORT_FAILED,
        OBSERVATION_EXPORT_FAILED,
        OBSERVATION_PROOF_VALID,
        OBSERVATION_PUBLICATION_NOT_OBSERVED,
        build_postcommit_observation,
        load_durable_proof,
        write_proof,
    )

    def write_observation(payload):
        if not args.observation_output:
            return
        marker = Path(args.observation_output)
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            json.dumps(payload, sort_keys=True, separators=(',', ':')) + '\n',
            encoding='utf-8',
        )

    snapshot = None
    try:
        app = create_read_only_app()
    except Exception:
        write_observation({
            'publication_observed': None,
            'snapshot_id': args.snapshot_id,
            'status': OBSERVATION_EXPORT_FAILED,
            'reason_code': FAILURE_PROOF_EXPORT_ENVIRONMENT_INVALID,
        })
        print(
            'Team State proof export environment is invalid for read-only access.',
            file=sys.stderr,
        )
        return 4

    try:
        with app.app_context():
            snapshot = resolve_snapshot(snapshot_id=args.snapshot_id, current=args.current)
            if snapshot is None:
                write_observation({
                    'publication_observed': False,
                    'snapshot_id': None,
                    'status': OBSERVATION_PUBLICATION_NOT_OBSERVED,
                    'reason_code': None,
                })
                print('No target publication exists; no proof is required for this observation.')
                return 0
            row = load_durable_proof(snapshot.id)
            if row is None:
                write_observation({
                    'publication_observed': True,
                    'snapshot_id': snapshot.id,
                    'status': OBSERVATION_EXPORT_FAILED,
                    'reason_code': FAILURE_PROOF_ARTIFACT_MISSING,
                })
                print(
                    f'Required Team State proof missing for snapshot_id={snapshot.id}.',
                    file=sys.stderr,
                )
                return 3
            proof = dict(row.proof)
            observation = build_postcommit_observation(snapshot, proof)
            proof['postcommit_observation'] = observation
            write_observation(observation)
        write_proof(proof, args.output)
    except Exception:
        write_observation({
            'publication_observed': None,
            'snapshot_id': getattr(snapshot, 'id', args.snapshot_id),
            'status': OBSERVATION_EXPORT_FAILED,
            'reason_code': FAILURE_PROOF_EXPORT_FAILED,
        })
        print('Team State proof export failed.', file=sys.stderr)
        return 4
    if observation.get('status') != OBSERVATION_PROOF_VALID:
        print(
            'Team State proof observation failed '
            f"for snapshot_id={snapshot.id}: {observation.get('reason_code')}",
            file=sys.stderr,
        )
        return 5
    print(f'Exported Team State proof for snapshot_id={snapshot.id}.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
