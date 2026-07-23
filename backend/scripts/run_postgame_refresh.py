import argparse
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# This command is a background data sync runner. It must not start the web
# process' optional in-process scheduler while running in GitHub Actions.
os.environ['AUTO_SYNC'] = 'false'


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Run BaseballOS completed-game bullpen workload refresh.'
    )
    parser.add_argument(
        '--date',
        dest='schedule_date',
        help='MLB schedule date to inspect, YYYY-MM-DD. Defaults to the current baseball slate date.',
    )
    parser.add_argument(
        '--source',
        default='github_actions',
        help='SyncRun source label to persist with durable sync metadata.',
    )
    parser.add_argument(
        '--public-only',
        action='store_true',
        help='Exit after public postgame ingestion/snapshot publication.',
    )
    parser.add_argument(
        '--retry-failed',
        action='store_true',
        help='Explicitly reset exhausted FAILED markers for --date before refreshing.',
    )
    parser.add_argument(
        '--game-pk',
        action='append',
        type=int,
        default=[],
        help='Limit --retry-failed to one MLB gamePk. Repeat for multiple games.',
    )
    args = parser.parse_args(argv)
    if args.retry_failed and not args.schedule_date:
        parser.error('--retry-failed requires --date so recovery cannot reset an unbounded range')
    if args.game_pk and not args.retry_failed:
        parser.error('--game-pk requires --retry-failed')
    return args


def _parse_schedule_date(value):
    if not value:
        return None
    return date.fromisoformat(value)


def main(argv=None):
    args = _parse_args(argv)
    source = str(args.source or 'github_actions')[:30]
    schedule_date = _parse_schedule_date(args.schedule_date)
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )

    from app import app
    from services import sync as sync_service
    from services import sync_metadata
    from services.postgame_recovery import reset_failed_postgame_markers
    from services.sync_publication_proof import build_candidate_publication_proof

    recovery = {
        'status': 'not_requested',
        'schedule_date': schedule_date.isoformat() if schedule_date else None,
        'requested_game_pks': list(args.game_pk),
        'markers_reset': 0,
        'reset_game_pks': [],
    }
    if args.retry_failed:
        with app.app_context():
            recovery = reset_failed_postgame_markers(
                schedule_date=schedule_date,
                game_pks=args.game_pk,
            )

    status = sync_service.run_postgame_refresh(
        app,
        schedule_date=schedule_date,
        source=source,
        include_internal_enrichment=not args.public_only,
    )
    changed_workload = (
        int(status.get('new_logs_added') or 0)
        + int(status.get('logs_corrected') or 0)
    ) > 0
    with app.app_context():
        publication_proof = build_candidate_publication_proof(
            status.get('dashboard_snapshot_id'),
            candidate_required=changed_workload,
        )

    summary = {
        'status': status.get('status'),
        'source': source,
        'schedule_date': status.get('schedule_date'),
        'public_only': args.public_only,
        'changed_workload': changed_workload,
        'failed_marker_recovery': recovery,
        'publication_proof': publication_proof,
        'sync': status,
    }
    print(json.dumps(summary, sort_keys=True, default=str))

    sync_succeeded = status.get('status') in sync_metadata.SUCCESSFUL_STATUSES
    return 0 if sync_succeeded and publication_proof.get('verified') is True else 1


if __name__ == '__main__':
    raise SystemExit(main())
