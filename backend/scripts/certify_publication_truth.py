"""Read-only truth certification of a trusted Dashboard publication.

Usage (operator, against a database it may read):

    python scripts/certify_publication_truth.py [--snapshot-id N] \
        [--membership-date YYYY-MM-DD] [--output report.json]

Defaults to the current trusted publication. The work runs inside a
read-only transaction on PostgreSQL (``SET TRANSACTION READ ONLY``) and the
session is rolled back at the end; nothing is ever written.
"""

import argparse
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot-id', type=int)
    parser.add_argument('--membership-date')
    parser.add_argument('--output')
    args = parser.parse_args(argv)

    from sqlalchemy import text

    from app import app
    from models.dashboard_snapshot import DashboardSnapshot
    from services import dashboard_snapshot as dashboard_snapshot_service
    from services.publication_truth_certification import certify_snapshot
    from utils.db import db

    with app.app_context():
        if db.session.get_bind().dialect.name == 'postgresql':
            db.session.execute(text('SET TRANSACTION READ ONLY'))
        try:
            snapshot = (
                db.session.get(DashboardSnapshot, args.snapshot_id)
                if args.snapshot_id
                else dashboard_snapshot_service.get_latest_valid_dashboard_snapshot()
            )
            if snapshot is None:
                print('No snapshot to certify.', file=sys.stderr)
                return 2
            report = certify_snapshot(
                snapshot,
                membership_date=(
                    date.fromisoformat(args.membership_date) if args.membership_date else None
                ),
            )
        finally:
            db.session.rollback()

    body = json.dumps(report, indent=2, sort_keys=True, default=str)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as handle:
            handle.write(body)
    print(json.dumps({
        key: report[key] for key in (
            'snapshot_id', 'data_through', 'availability_reference_date',
            'league_verdict', 'teams_passed', 'teams_conditional', 'teams_failed', 'domains',
        )
    }, indent=2, default=str))
    return 0 if report['league_verdict'] != 'FAIL' else 1


if __name__ == '__main__':
    raise SystemExit(main())
