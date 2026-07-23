import argparse
import json
import logging
import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# This command is the daily data sync runner. It must not start the web
# process' optional in-process scheduler while running in GitHub Actions.
os.environ['AUTO_SYNC'] = 'false'


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Run BaseballOS daily bullpen sync outside the web request path.'
    )
    parser.add_argument(
        '--days-back',
        type=int,
        default=7,
        help='Number of recent days to pull from MLB game logs.',
    )
    parser.add_argument(
        '--source',
        default='github_actions',
        help='SyncRun source label to persist with durable sync metadata.',
    )
    parser.add_argument(
        '--public-only',
        action='store_true',
        help='Exit after public dashboard/Data & Trust snapshot publication.',
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    source = str(args.source or 'github_actions')[:30]
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )

    from app import app
    from services import sync as sync_service
    from services import sync_metadata
    from services.sync_publication_proof import build_candidate_publication_proof

    status = sync_service.run_daily_sync(
        app,
        days_back=args.days_back,
        source=source,
        include_internal_enrichment=not args.public_only,
    )
    with app.app_context():
        publication_proof = build_candidate_publication_proof(
            status.get('dashboard_snapshot_id'),
            candidate_required=True,
        )

    summary = {
        'status': status.get('status'),
        'source': source,
        'days_back': args.days_back,
        'public_only': args.public_only,
        'publication_proof': publication_proof,
        'sync': status,
    }
    print(json.dumps(summary, sort_keys=True, default=str))

    sync_succeeded = status.get('status') in sync_metadata.SUCCESSFUL_STATUSES
    return 0 if sync_succeeded and publication_proof.get('verified') is True else 1


if __name__ == '__main__':
    raise SystemExit(main())
