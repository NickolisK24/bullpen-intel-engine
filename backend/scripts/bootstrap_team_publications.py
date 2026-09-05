"""Explicit D-058 Package 1 bootstrap and internal inspection command."""

from __future__ import annotations

import argparse
import json

from app import create_app
from services.team_publication_storage import (
    TeamPublicationError,
    bootstrap_current_trusted_dashboard,
    inspect_team_publication_storage,
)
from utils.db import db


def _parser():
    parser = argparse.ArgumentParser(
        description='Bootstrap dormant per-team publications from the current Dashboard.'
    )
    parser.add_argument(
        '--inspect',
        action='store_true',
        help='Read-only integrity/status output; do not bootstrap.',
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Build and validate the bootstrap transaction, then roll it back.',
    )
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    app = create_app()
    with app.app_context():
        try:
            if args.inspect:
                result = inspect_team_publication_storage()
            else:
                authored = bootstrap_current_trusted_dashboard(
                    commit=not args.dry_run
                )
                result = authored.to_dict()
                if args.dry_run:
                    db.session.rollback()
                    result['status'] = 'dry_run_complete'
        except TeamPublicationError as exc:
            db.session.rollback()
            result = {
                'event': 'team_publication_bootstrap',
                'status': 'refused',
                'reason': str(exc),
            }
            print(json.dumps(result, sort_keys=True, separators=(',', ':')))
            return 1
        print(json.dumps(result, sort_keys=True, separators=(',', ':')))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
