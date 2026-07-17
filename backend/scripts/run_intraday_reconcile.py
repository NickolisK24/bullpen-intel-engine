import argparse
import json
import logging
import os
import sys
import traceback
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Phase 1 intraday reconciliation is audit-only: it reads authoritative source
# state, compares it with stored BaseballOS state, and reports what would need to
# change. It performs no canonical baseball-data writes, publishes no snapshot,
# runs no fatigue/story/cache work, and has no cron schedule. As with the other
# background runners it must not start the web process' optional in-process
# scheduler, so AUTO_SYNC is forced off before the app is imported.
os.environ['AUTO_SYNC'] = 'false'


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Run the audit-only intraday reconciliation check. Detects roster, '
            'assignment, transaction, and schedule/finality differences between '
            'the authoritative MLB source and stored BaseballOS state. Performs '
            'no writes, publishes no snapshot, and runs no derived recalculation.'
        )
    )
    parser.add_argument(
        '--source',
        default='manual',
        help='Source label recorded in the audit artifact (e.g. manual, github_actions).',
    )
    parser.add_argument(
        '--json',
        dest='as_json',
        action='store_true',
        help='Emit the full audit artifact as one JSON object on stdout.',
    )
    parser.add_argument(
        '--output',
        help='Optional path to also write the JSON audit artifact to.',
    )
    parser.add_argument(
        '--lanes',
        help=(
            'Comma-separated subset of lanes to run '
            '(roster_assignment,transactions,schedule_finality). Defaults to all.'
        ),
    )
    parser.add_argument(
        '--transaction-window-days',
        type=int,
        default=None,
        help='Trailing days of transactions to inspect (default: sync window).',
    )
    parser.add_argument(
        '--schedule-lookback-days',
        type=int,
        default=None,
        help='Slate dates before the product date to inspect (default: 1).',
    )
    parser.add_argument(
        '--deep-roster',
        action='store_true',
        help=(
            'Manual diagnostic: sweep all roster types (active, 40-man, full, '
            'non-roster) instead of the lightweight active-roster-only default. '
            'The production GitHub Actions run uses the active-only default.'
        ),
    )
    return parser.parse_args(argv)


def _selected_lanes(raw, all_lanes):
    if not raw:
        return list(all_lanes)
    requested = [item.strip() for item in raw.split(',') if item.strip()]
    unknown = [item for item in requested if item not in all_lanes]
    if unknown:
        raise SystemExit(
            f"Unknown lane(s): {', '.join(unknown)}. "
            f"Valid lanes: {', '.join(all_lanes)}."
        )
    # Preserve canonical lane order.
    return [lane for lane in all_lanes if lane in requested]


def _log_human_summary(artifact):
    """Emit a concise human-readable summary to stderr."""
    summary = artifact.get('summary') or {}
    plan = artifact.get('would_refresh') or {}
    logging.info('─' * 60)
    logging.info(
        'Intraday audit summary (status=%s, source=%s, product_date=%s)',
        artifact.get('status'), artifact.get('source'), artifact.get('product_date'),
    )
    if artifact.get('status') == 'skipped':
        logging.info(
            'SKIPPED — %s. No source acquisition and no work performed.',
            artifact.get('reason_code'),
        )
        logging.info('─' * 60)
        return
    logging.info(
        'Changed: %s | differences: %s | material change: %s',
        artifact.get('changed'), summary.get('total_meaningful_findings'),
        summary.get('material_change_detected'),
    )
    for limitation in artifact.get('limitations') or []:
        logging.info('  limitation: %s', limitation)
    for lane_name, lane in (artifact.get('lanes') or {}).items():
        checked = lane.get('checked') or {}
        logging.info('  [%s] %s', lane_name, json.dumps(checked, sort_keys=True))
    logging.info(
        'Would-refresh plan (dry run): roster_statuses=%s team_assignments=%s '
        'transactions=%s completed_game_pks=%s affected_team_ids=%s',
        plan.get('roster_statuses'), plan.get('team_assignments'),
        plan.get('transactions'), plan.get('completed_game_pks'),
        plan.get('affected_team_ids'),
    )
    logging.info('No writes performed. No snapshot published. Audit-only.')
    logging.info('─' * 60)


def _emit_result(artifact, args):
    """Single, reusable result writer shared by the normal and bootstrap-failure
    paths: writes --output, logs the human summary to stderr, prints exactly one
    JSON object to stdout with --json, and returns the exit code.

    Exit code reflects verification status, not whether differences were found
    (differences are the expected, successful outcome):
      success -> 0   skipped -> 0   partial -> 1   failed -> 1
    """
    payload = json.dumps(artifact, sort_keys=True, default=str)

    if args.output:
        output_path = Path(args.output).expanduser()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(payload + '\n', encoding='utf-8')
        logging.info('Wrote intraday audit artifact to %s', output_path)

    _log_human_summary(artifact)

    if args.as_json:
        # Exactly one JSON object on stdout when --json is requested — identical
        # to what --output wrote.
        print(payload)

    status = artifact.get('status')
    return 0 if status in ('success', 'skipped') else 1


def main(argv=None):
    args = _parse_args(argv)
    source = str(args.source or 'manual')[:100]
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
        stream=sys.stderr,
    )

    # The service module imports without a Flask app context or a database, so
    # its constants and the bootstrap-failure builder are available even if the
    # production app cannot initialize below.
    from services import intraday_reconcile
    from utils.time import to_utc_iso, utc_now_naive

    started_at_iso = to_utc_iso(utc_now_naive())
    lanes = _selected_lanes(args.lanes, intraday_reconcile.ALL_LANES)

    kwargs = {'source': source, 'lanes': lanes}
    if args.transaction_window_days is not None:
        kwargs['transaction_window_days'] = args.transaction_window_days
    if args.schedule_lookback_days is not None:
        kwargs['schedule_lookback_days'] = args.schedule_lookback_days
    if args.deep_roster:
        kwargs['roster_types'] = intraday_reconcile.DEEP_ROSTER_TYPES

    # Import and initialize the production Flask app, then run the audit inside
    # its context. A failure anywhere in this startup path — most importantly a
    # missing required production secret (e.g. ADMIN_API_TOKEN) surfacing while
    # importing app.py — must NOT crash without a result. It is a bootstrap
    # failure: the audit never acquired the lock, never read a source, and never
    # wrote anything. We still emit a valid, versioned failed artifact.
    try:
        from app import app
        from utils.db import db

        with app.app_context():
            try:
                artifact = intraday_reconcile.run_intraday_audit(**kwargs)
            finally:
                # This command never writes; rolling back discards any read-only
                # transaction state so nothing can leak a write.
                db.session.rollback()
                db.session.remove()
    except Exception as exc:  # noqa: BLE001 - any startup failure yields a valid artifact
        # Diagnostic detail and the full traceback go to stderr only — never
        # into stdout or the JSON artifact (which must not carry secrets).
        logging.error(
            'Intraday audit bootstrap failed before the audit could start: %s: %s',
            type(exc).__name__, exc,
        )
        traceback.print_exc(file=sys.stderr)
        artifact = intraday_reconcile.build_bootstrap_failure_artifact(
            source=source,
            started_at_iso=started_at_iso,
            completed_at_iso=to_utc_iso(utc_now_naive()),
            exception_class=type(exc).__name__,
            lanes=lanes,
        )

    return _emit_result(artifact, args)


if __name__ == '__main__':
    raise SystemExit(main())
