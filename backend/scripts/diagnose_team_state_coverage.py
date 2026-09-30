"""Explain why a team's Team State readiness is (or is not) publishable.

Read-only operator diagnostic. For each active-bullpen arm it names the first
reason its readiness record is not usable, using the same authorities as the
Team State publication proof. It never writes; on PostgreSQL the transaction is
set READ ONLY and a write probe must be refused before anything is read.

Examples:
  python scripts/diagnose_team_state_coverage.py --snapshot-id 4132 --team-id 118
  python scripts/diagnose_team_state_coverage.py --snapshot-id 4132 --league
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

# This is an operator diagnostic command, not a web worker.
os.environ['AUTO_SYNC'] = 'false'
# Every PostgreSQL connection this process opens starts read-only, so a read path
# that rolls back and begins a new transaction still cannot write.
os.environ['PGOPTIONS'] = (
    os.environ.get('PGOPTIONS', '') + ' -c default_transaction_read_only=on'
).strip()


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--snapshot-id', type=int,
                        help='Candidate snapshot whose reference dates to use.')
    parser.add_argument('--membership-date', help='YYYY-MM-DD; overrides the snapshot.')
    parser.add_argument('--availability-date', help='YYYY-MM-DD; overrides the snapshot.')
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument('--team-id', type=int, help='One team, with per-arm causes.')
    scope.add_argument('--league', action='store_true',
                       help='All 30 teams, ordered by remaining headroom.')
    parser.add_argument('--allow-non-postgres', action='store_true',
                        help='Skip the read-only proof (local SQLite only).')
    parser.add_argument('--compact', action='store_true')
    return parser.parse_args(argv)


def _date(value):
    return date.fromisoformat(value) if value else None


def main(argv=None):
    args = _parse_args(argv)

    from app import create_app
    from models.dashboard_snapshot import DashboardSnapshot
    from services import active_bullpen_coverage_diagnostic as diagnostic
    from services.mlb_club_directory import MLB_TEAM_IDS
    from services.noop_qualification_candidate_audit import enforce_read_only
    from utils.db import db

    app = create_app()
    with app.app_context():
        if db.session.get_bind().dialect.name == 'postgresql':
            enforce_read_only(db.session)
        elif not args.allow_non_postgres:
            print('refusing: read-only cannot be proven on this database', file=sys.stderr)
            return 2

        membership_date = _date(args.membership_date)
        availability_date = _date(args.availability_date)
        if args.snapshot_id is not None:
            snapshot = db.session.get(DashboardSnapshot, args.snapshot_id)
            if snapshot is None:
                print(f'snapshot {args.snapshot_id} not found', file=sys.stderr)
                return 2
            snap_membership, snap_availability = (
                diagnostic.reference_dates_for_snapshot(snapshot)
            )
            membership_date = membership_date or snap_membership
            availability_date = availability_date or snap_availability
        if membership_date is None or availability_date is None:
            print('need --snapshot-id or both explicit dates', file=sys.stderr)
            return 2

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
        db.session.rollback()

    print(json.dumps(report, indent=None if args.compact else 2, default=str))
    return 0


if __name__ == '__main__':
    sys.exit(main())
