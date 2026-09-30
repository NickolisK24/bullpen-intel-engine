"""Explain why a team's Team State readiness is (or is not) publishable.

Read-only operator diagnostic. For each active-bullpen arm it names the first
reason its readiness record is not usable, using the same authorities as the
Team State publication proof. It never writes; on PostgreSQL the transaction is
set READ ONLY and a write probe must be refused before anything is read.

Examples:
  python scripts/diagnose_team_state_coverage.py --snapshot-id 4132 --team-id 118
  python scripts/diagnose_team_state_coverage.py --snapshot-id 4132 --league \
      --output-dir ../artifacts/team-state-coverage-diagnostic

Exit codes: 0 the diagnostic completed (an ineligible team is a result, not an
error), 2 the invocation was refused before any evidence was read, 3 read-only
operation could not be proven, 1 the diagnostic itself failed.
"""

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

READ_ONLY_PGOPTION = '-c default_transaction_read_only=on'


def _configure_read_only_process():
    """Set the operator environment for this process only, never at import.

    This is an operator diagnostic command, not a web worker, and every
    PostgreSQL connection it opens starts read-only, so a read path that rolls
    back and begins a new transaction still cannot write.
    """
    os.environ['AUTO_SYNC'] = 'false'
    options = os.environ.get('PGOPTIONS', '')
    if READ_ONLY_PGOPTION not in options:
        os.environ['PGOPTIONS'] = f'{options} {READ_ONLY_PGOPTION}'.strip()


EXIT_OK = 0
EXIT_FAILED = 1
EXIT_REFUSED = 2
EXIT_READ_ONLY_UNPROVEN = 3

SCHEMA_VERSION = '1'
NON_AUTHORIZATION_STATEMENT = (
    'This diagnostic is read-only. It does not authorize publishing or '
    'promoting a snapshot, resolving sync failures, recalculating fatigue, '
    'repairing roster or schedule authority, or any production mutation.'
)


def _positive_int(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('must be a positive integer')
    return number


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--snapshot-id', type=_positive_int,
                        help='Candidate snapshot whose reference dates to use.')
    parser.add_argument('--membership-date', help='YYYY-MM-DD; overrides the snapshot.')
    parser.add_argument('--availability-date', help='YYYY-MM-DD; overrides the snapshot.')
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument('--team-id', type=_positive_int, help='One team, with per-arm causes.')
    scope.add_argument('--league', action='store_true',
                       help='All 30 teams, ordered by remaining headroom.')
    parser.add_argument('--output-dir',
                        help='Write the JSON evidence and a Markdown summary here.')
    parser.add_argument('--allow-non-postgres', action='store_true',
                        help='Skip the read-only proof (local SQLite only).')
    parser.add_argument('--compact', action='store_true')
    return parser.parse_args(argv)


def _date(value):
    return date.fromisoformat(value) if value else None


def _iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def _snapshot_identity(snapshot):
    if snapshot is None:
        return None
    return {
        'snapshot_id': snapshot.id,
        'status': snapshot.status,
        'is_published': bool(snapshot.is_published),
        'data_through': _iso(snapshot.data_through),
        'availability_reference_date': _iso(snapshot.availability_reference_date),
        'withheld_reason': snapshot.error_message,
        'sync_run_id': snapshot.sync_run_id,
    }


def output_basename(*, snapshot_id, team_id=None, league=False):
    scope = 'league' if league else f'team-{team_id}'
    anchor = f'snapshot-{snapshot_id}' if snapshot_id is not None else 'explicit-dates'
    return f'team-state-coverage-{scope}-{anchor}'


def markdown_summary(document):
    report = document['report']
    lines = [
        '# Team State coverage diagnostic',
        '',
        f"- Mode: {document['mode']}",
        f"- Snapshot: {(document.get('snapshot') or {}).get('snapshot_id')}",
        f"- Membership date: {report.get('membership_date')}",
        f"- Availability date: {report.get('availability_date')}",
        f"- Ledger complete: {report.get('ledger_complete')}",
        f"- Write probe refused: {document['read_only_proof'].get('read_only_probe_refused')}",
        '',
    ]
    if document['mode'] == 'team':
        lines += [
            f"Team {report['team_id']}: {report['usable_record_count']} of "
            f"{report['active_bullpen_count']} active relievers usable "
            f"({report.get('coverage_pct')}%), confidence={report['confidence']}, "
            f"data_state={report['data_state']}, eligible={report.get('eligible_coverage')}, "
            f"headroom={report.get('unresolved_headroom')}.",
            '',
            '| mlb_id | pitcher | cause | usable | data_state | last appearance | fetch failures |',
            '| --- | --- | --- | --- | --- | --- | --- |',
        ]
        for arm in report['arms']:
            lines.append(
                f"| {arm.get('mlb_id')} | {arm.get('pitcher_name')} | {arm['cause']} | "
                f"{arm['usable']} | {arm.get('record_data_state')} | "
                f"{arm.get('latest_game_log_date')} | {arm.get('open_fetch_failure_count')} |"
            )
    else:
        lines += [
            f"Ineligible: {report['ineligible_team_ids']}",
            f"One arm from failing: {report['one_arm_from_failing']}",
            f"Two arms from failing: {report['two_arms_from_failing']}",
            '',
            '| team | active | usable | unresolved | coverage % | headroom | '
            'confidence | data_state | eligible |',
            '| --- | --- | --- | --- | --- | --- | --- | --- | --- |',
        ]
        for team in report['teams']:
            lines.append(
                f"| {team['team']} ({team['team_id']}) | {team['active_bullpen_count']} | "
                f"{team['usable_record_count']} | {team['unresolved_record_count']} | "
                f"{team['coverage_pct']} | {team['unresolved_headroom']} | "
                f"{team['confidence']} | {team['data_state']} | {team['eligible_coverage']} |"
            )
    lines += ['', NON_AUTHORIZATION_STATEMENT, '']
    return '\n'.join(lines)


def _write_outputs(document, output_dir, basename):
    target = Path(output_dir)
    target.mkdir(parents=True, exist_ok=True)
    json_path = target / f'{basename}.json'
    json_path.write_text(
        json.dumps(document, indent=2, sort_keys=True, default=str) + '\n',
        encoding='utf-8',
    )
    (target / f'{basename}.md').write_text(markdown_summary(document), encoding='utf-8')
    return json_path


def main(argv=None):
    args = _parse_args(argv)

    # Refuse an invalid team before any application configuration is loaded.
    from services.mlb_club_directory import MLB_TEAM_IDS

    if args.team_id is not None and args.team_id not in MLB_TEAM_IDS:
        print(f'refusing: team {args.team_id} is not an MLB club', file=sys.stderr)
        return EXIT_REFUSED

    _configure_read_only_process()
    from app import create_app
    from models.dashboard_snapshot import DashboardSnapshot
    from services import active_bullpen_coverage_diagnostic as diagnostic
    from services.noop_qualification_candidate_audit import (
        ReadOnlyNotEnforced,
        ReadOnlyProbeViolation,
        enforce_read_only,
    )
    from utils.db import db

    app = create_app()
    with app.app_context():
        if db.session.get_bind().dialect.name == 'postgresql':
            try:
                read_only_proof = enforce_read_only(db.session)
            except (ReadOnlyNotEnforced, ReadOnlyProbeViolation):
                print('refusing: read-only operation could not be proven', file=sys.stderr)
                return EXIT_READ_ONLY_UNPROVEN
        elif args.allow_non_postgres:
            read_only_proof = {'read_only_probe_refused': None, 'protection': 'none_local_only'}
        else:
            print('refusing: read-only cannot be proven on this database', file=sys.stderr)
            return EXIT_READ_ONLY_UNPROVEN

        snapshot = None
        membership_date = _date(args.membership_date)
        availability_date = _date(args.availability_date)
        if args.snapshot_id is not None:
            snapshot = db.session.get(DashboardSnapshot, args.snapshot_id)
            if snapshot is None:
                print(f'refusing: snapshot {args.snapshot_id} not found', file=sys.stderr)
                return EXIT_REFUSED
            snap_membership, snap_availability = (
                diagnostic.reference_dates_for_snapshot(snapshot)
            )
            membership_date = membership_date or snap_membership
            availability_date = availability_date or snap_availability
        if membership_date is None or availability_date is None:
            print('refusing: need --snapshot-id or both explicit dates', file=sys.stderr)
            return EXIT_REFUSED

        if args.league:
            report = diagnostic.diagnose_league(
                sorted(MLB_TEAM_IDS),
                membership_date=membership_date,
                availability_date=availability_date,
            )
        else:
            report = diagnostic.diagnose_active_bullpen_coverage(
                args.team_id,
                membership_date=membership_date,
                availability_date=availability_date,
            )
        document = {
            'diagnostic': 'team_state_active_bullpen_coverage',
            'schema_version': SCHEMA_VERSION,
            'mode': 'league' if args.league else 'team',
            'snapshot': _snapshot_identity(snapshot),
            'read_only_proof': read_only_proof,
            'run': {
                'commit_sha': os.environ.get('GITHUB_SHA'),
                'workflow_run_id': os.environ.get('GITHUB_RUN_ID'),
            },
            'non_authorization_statement': NON_AUTHORIZATION_STATEMENT,
            'report': report,
        }
        db.session.rollback()

    if args.output_dir:
        path = _write_outputs(document, args.output_dir, output_basename(
            snapshot_id=args.snapshot_id, team_id=args.team_id, league=args.league,
        ))
        print(f'Wrote {path.name}')
    else:
        print(json.dumps(document, indent=None if args.compact else 2, default=str))
    return EXIT_OK


if __name__ == '__main__':
    sys.exit(main())
