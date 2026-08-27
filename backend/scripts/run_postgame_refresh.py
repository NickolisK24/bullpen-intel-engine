import argparse
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


PRODUCTION_POSTGAME_TRIGGER_REFUSAL = (
    'production_postgame_runner_requires_due_sync_coordinator'
)


def production_postgame_trigger_refusal_reason(*, source, schedule_date, environ=None):
    env = environ or os.environ
    if str(env.get('APP_ENV') or '').strip().lower() != 'production':
        return None
    governed_backfill = (
        source == 'github_actions_backfill'
        and schedule_date is not None
        and str(env.get('GITHUB_ACTIONS') or '').strip().lower() == 'true'
        and str(env.get('GITHUB_EVENT_NAME') or '').strip() == 'workflow_dispatch'
        and str(env.get('GITHUB_REF') or '').strip() == 'refs/heads/main'
        and str(env.get('GITHUB_REPOSITORY') or '').strip()
        == 'NickolisK24/bullpen-intel-engine'
    )
    return None if governed_backfill else PRODUCTION_POSTGAME_TRIGGER_REFUSAL


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
    parser.add_argument(
        '--output',
        help=(
            'Optional path for a durable copy of the same JSON summary printed '
            'to stdout. Written atomically with sorted keys.'
        ),
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

    refusal = production_postgame_trigger_refusal_reason(
        source=source,
        schedule_date=schedule_date,
    )
    if refusal is not None:
        logging.getLogger(__name__).error(
            'Production postgame sync refused before application/database '
            'initialization (reason=%s).', refusal,
        )
        return 2

    from app import app
    from services import sync as sync_service
    from services import sync_metadata
    from services.postgame_recovery import (
        reset_failed_postgame_markers,
        reset_fully_processed_markers_without_appearance_rows,
    )
    from services.sync_publication_proof import build_candidate_publication_proof
    from utils.summary_output import (
        SummaryOutputError, serialize_summary, write_summary,
    )

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

    sweep_dates = [schedule_date] if schedule_date else sync_service.postgame_schedule_dates()
    with app.app_context():
        ledger_marker_recovery = reset_fully_processed_markers_without_appearance_rows(
            schedule_dates=sweep_dates,
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
        'ledger_marker_recovery': ledger_marker_recovery,
        'publication_proof': publication_proof,
        'sync': status,
    }
    print(serialize_summary(summary))

    # Postgame job success and LEAGUE snapshot publication are two separate results.
    # A postgame refresh that ingested cleanly must not be marked failed merely because
    # the league snapshot is (correctly) still pending during an active slate — the
    # league snapshot stays all-or-nothing and only withholds because unrelated games
    # remain non-final. The publication proof still honestly reports the candidate as
    # unverified/pending; we only stop treating that EXPECTED active-slate pending as a
    # workflow failure. Any GENUINE withholding (schedule gap, un-ingested final games,
    # failed/incomplete markers, partial publication-critical work) is not classified
    # as expected-pending and still exits non-zero. (The daily sync is unchanged: it
    # continues to require a verified published trusted snapshot.)
    from services.sync_publication_proof import (
        LEAGUE_PUBLICATION_EXPECTED_PENDING_ACTIVE_SLATE,
    )

    sync_succeeded = status.get('status') in sync_metadata.SUCCESSFUL_STATUSES
    publication_ok = (
        publication_proof.get('verified') is True
        or publication_proof.get('league_publication_status')
        == LEAGUE_PUBLICATION_EXPECTED_PENDING_ACTIVE_SLATE
    )
    exit_code = 0 if sync_succeeded and publication_ok else 1

    # Durable evidence is written BEFORE the exit code is returned, and a
    # failure to write it is itself a failure: a missing artifact must never be
    # indistinguishable from a clean run. Only the safe reason is reported --
    # the underlying message can contain a filesystem path.
    if args.output:
        try:
            write_summary(summary, args.output)
        except SummaryOutputError as exc:
            logging.getLogger(__name__).error(
                'Postgame refresh summary output failed (reason=%s).', exc.reason,
            )
            return exit_code or 1

    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
