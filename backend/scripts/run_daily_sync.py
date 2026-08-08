import argparse
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


PRODUCTION_DAILY_TRIGGER_REFUSAL = (
    'production_daily_runner_requires_scheduled_github_trigger'
)


def _truthy(value):
    return str(value or '').strip().lower() in ('1', 'true', 'yes', 'on')


def production_daily_trigger_refusal_reason(environ=None):
    """Return a reason when the external production daily runner is unauthorized.

    The production full-daily command is intentionally schedule-only. A GitHub
    workflow_dispatch (or a local production invocation) must refuse before the
    Flask app is imported, which means before database initialization and before
    any canonical writer can run. Test/development commands remain usable.
    """
    env = environ or os.environ
    if str(env.get('APP_ENV') or '').strip().lower() != 'production':
        return None
    if not _truthy(env.get('GITHUB_ACTIONS')):
        return PRODUCTION_DAILY_TRIGGER_REFUSAL
    if str(env.get('GITHUB_EVENT_NAME') or '').strip().lower() != 'schedule':
        return PRODUCTION_DAILY_TRIGGER_REFUSAL
    return None


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
    parser.add_argument(
        '--output',
        help=(
            'Optional path for a durable copy of the same JSON summary printed '
            'to stdout. Written atomically with sorted keys.'
        ),
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    source = str(args.source or 'github_actions')[:30]
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )

    refusal_reason = production_daily_trigger_refusal_reason()
    if refusal_reason is not None:
        logging.getLogger(__name__).error(
            'Production daily sync refused before application/database initialization '
            '(reason=%s). Full daily production synchronization is schedule-only.',
            refusal_reason,
        )
        return 2

    from app import app
    from services import sync as sync_service
    from services import sync_metadata
    from services.sync_publication_proof import build_candidate_publication_proof
    from utils.summary_output import (
        SummaryOutputError, serialize_summary, write_summary,
    )

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
            publication_critical=status.get('publication_critical'),
            sync_status=status.get('status'),
        )

    summary = {
        'status': status.get('status'),
        'source': source,
        'days_back': args.days_back,
        'public_only': args.public_only,
        'publication_critical': status.get('publication_critical'),
        'publication_proof': publication_proof,
        'sync': status,
    }
    print(serialize_summary(summary))

    sync_succeeded = status.get('status') in sync_metadata.SUCCESSFUL_STATUSES
    exit_code = (
        0 if sync_succeeded and publication_proof.get('verified') is True else 1
    )

    # Durable evidence is written BEFORE the exit code is returned, and a
    # failure to write it is itself a failure: a missing artifact must never be
    # indistinguishable from a clean run. Only the safe reason is reported --
    # the underlying message can contain a filesystem path.
    if args.output:
        try:
            write_summary(summary, args.output)
        except SummaryOutputError as exc:
            logging.getLogger(__name__).error(
                'Daily sync summary output failed (reason=%s).', exc.reason,
            )
            return exit_code or 1

    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
