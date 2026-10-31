"""Build the dry-run correction manifest for frozen Team State artifacts.

READ-ONLY. This command never supersedes, withdraws, edits, or publishes an
artifact, and never commits. It reads published Team State artifacts, their
durable publication proofs, and the stored schedule, and writes a JSON
manifest of proposed corrections for human review (WP-0.1, EOS-003).

Database dry run (the authoritative classification; requires DATABASE_URL):

    python -m scripts.build_team_state_correction_manifest \
      --start 2026-09-28 --end 2026-10-31 \
      --output /tmp/team_state_correction_manifest.json

Offline inventory of the committed ``frontend/public/share`` pages (no
database; every entry is ``review_required`` until the dry run runs):

    python -m scripts.build_team_state_correction_manifest \
      --static-share-root ../frontend/public/share --start 2026-09-28 \
      --output /tmp/team_state_correction_inventory.json

Executing any proposed correction is a separate operation that requires
explicit authorization; this command has no execute mode.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ['AUTO_SYNC'] = 'false'


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--start', required=True, type=date.fromisoformat)
    parser.add_argument('--end', type=date.fromisoformat, default=None)
    parser.add_argument('--output', required=True)
    parser.add_argument(
        '--csv',
        help='Also write a compact CSV of the entries for review.',
    )
    parser.add_argument(
        '--static-share-root',
        help='Inventory committed /share pages instead of reading the database.',
    )
    return parser.parse_args(argv)


CSV_FIELDS = (
    'product_date', 'team_abbreviation', 'team_id', 'public_id',
    'source_snapshot_id', 'published_public_state', 'competition_status',
    'corrected_public_state', 'proposed_action', 'reasons',
)


def _write(manifest, output):
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str) + '\n')


def _write_csv(manifest, output):
    import csv

    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as handle:
        writer = csv.writer(handle, lineterminator='\n')
        writer.writerow(CSV_FIELDS)
        for entry in manifest['entries']:
            writer.writerow([
                entry.get('product_date'),
                entry.get('team_abbreviation'),
                entry.get('team_id'),
                entry.get('public_id'),
                entry.get('source_snapshot_id'),
                entry.get('published_public_state'),
                (entry.get('competition_status') or {}).get('status'),
                (entry.get('correction') or {}).get('corrected_public_state'),
                entry.get('proposed_action'),
                ';'.join(entry.get('reasons') or ()),
            ])


def main(argv=None):
    from services.team_state_correction_manifest import (
        build_manifest,
        load_manifest_entries,
        static_inventory_entries,
    )

    args = _parse_args(argv)
    end = args.end or date.max
    if end < args.start:
        print('error: --end precedes --start', file=sys.stderr)
        return 2

    if args.static_share_root:
        entries = [
            entry for entry in static_inventory_entries(args.static_share_root)
            if entry.get('product_date')
            and args.start.isoformat() <= entry['product_date'] <= end.isoformat()
        ]
        scope = {
            'source': 'committed_static_share_pages',
            'start': args.start.isoformat(),
            'end': None if args.end is None else args.end.isoformat(),
        }
    else:
        from utils.db import db
        from utils.read_only_app import create_read_only_app

        app = create_read_only_app()
        with app.app_context():
            try:
                if db.engine.dialect.name == 'postgresql':
                    # Enforced by the database, not only by this code: any
                    # write in this transaction is refused.
                    from sqlalchemy import text

                    db.session.execute(text('SET TRANSACTION READ ONLY'))
                entries = load_manifest_entries(args.start, end)
            finally:
                # Never leave a transaction open, and never commit.
                db.session.rollback()
        scope = {
            'source': 'database_dry_run',
            'start': args.start.isoformat(),
            'end': None if args.end is None else args.end.isoformat(),
        }

    manifest = build_manifest(entries, scope=scope)
    _write(manifest, args.output)
    if args.csv:
        _write_csv(manifest, args.csv)
    print(json.dumps({
        'artifact_count': manifest['artifact_count'],
        'action_counts': manifest['action_counts'],
        'entries_digest': manifest['entries_digest'],
        'output': args.output,
    }, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
