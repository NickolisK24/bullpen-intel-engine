"""Export historical Team State calibration evidence as a JSON artifact.

READ-ONLY. This script issues SELECT queries only. It never adds, updates,
deletes, commits, publishes, recalculates, repairs, or calls a source API. It
exists so Team State calibration can be studied against the evidence production
already froze, rather than against re-derived current data.

A bounded range is required — there is no unbounded default. Supply either a
snapshot-id range or a data-through date range.

    python -m scripts.export_team_state_history \
      --snapshot-id-from 380 --snapshot-id-to 424 \
      --output /tmp/team_state_calibration_history.json

Prohibited uses: this artifact must not be used to rewrite historical state, to
publish anything, or to fill a frozen historical gap with a current value. Fields
history did not preserve are exported as null and must stay null.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ['AUTO_SYNC'] = 'false'


class ExportError(RuntimeError):
    """Raised so the operator sees a loud failure instead of an empty artifact."""


def _parse_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ExportError(f'Invalid date {value!r}; expected YYYY-MM-DD.')


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Read-only export of historical Team State calibration evidence.',
    )
    parser.add_argument('--snapshot-id', type=int, help='Export exactly one snapshot id.')
    parser.add_argument('--snapshot-id-from', type=int)
    parser.add_argument('--snapshot-id-to', type=int)
    parser.add_argument('--date-from', help='Earliest data_through (YYYY-MM-DD).')
    parser.add_argument('--date-to', help='Latest data_through (YYYY-MM-DD).')
    parser.add_argument(
        '--output',
        default='team_state_calibration_history.json',
        help='Destination path for the JSON artifact.',
    )
    return parser.parse_args(argv)


def _filters_from_args(args) -> dict:
    """Require an explicit bound. An unbounded production export is not offered."""
    filters = {}
    if args.snapshot_id is not None:
        filters['snapshot_id'] = args.snapshot_id
    if args.snapshot_id_from is not None:
        filters['snapshot_id_from'] = args.snapshot_id_from
    if args.snapshot_id_to is not None:
        filters['snapshot_id_to'] = args.snapshot_id_to
    if args.date_from:
        filters['date_from'] = _parse_date(args.date_from).isoformat()
    if args.date_to:
        filters['date_to'] = _parse_date(args.date_to).isoformat()
    if not filters:
        raise ExportError(
            'A bounded range is required: pass --snapshot-id, a '
            '--snapshot-id-from/--snapshot-id-to pair, or --date-from/--date-to.'
        )
    lo, hi = filters.get('snapshot_id_from'), filters.get('snapshot_id_to')
    if lo is not None and hi is not None and lo > hi:
        raise ExportError('--snapshot-id-from must not exceed --snapshot-id-to.')
    lo, hi = filters.get('date_from'), filters.get('date_to')
    if lo is not None and hi is not None and lo > hi:
        raise ExportError('--date-from must not exceed --date-to.')
    return filters


def _repository_sha():
    try:
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=str(BACKEND_DIR.parent), capture_output=True, text=True, check=False,
        )
    except OSError:
        return None
    sha = result.stdout.strip()
    return sha or None


def _trusted_snapshots(filters):
    """Published, ready bullpen-dashboard snapshots inside the requested bound."""
    from models.dashboard_snapshot import DashboardSnapshot
    from services.dashboard_snapshot import (
        SNAPSHOT_STATUS_READY,
        SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
    )

    query = DashboardSnapshot.query.filter(
        DashboardSnapshot.snapshot_type == SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
        DashboardSnapshot.status == SNAPSHOT_STATUS_READY,
        DashboardSnapshot.published_at.isnot(None),
    )
    if 'snapshot_id' in filters:
        query = query.filter(DashboardSnapshot.id == filters['snapshot_id'])
    if 'snapshot_id_from' in filters:
        query = query.filter(DashboardSnapshot.id >= filters['snapshot_id_from'])
    if 'snapshot_id_to' in filters:
        query = query.filter(DashboardSnapshot.id <= filters['snapshot_id_to'])
    if 'date_from' in filters:
        query = query.filter(DashboardSnapshot.data_through >= date.fromisoformat(filters['date_from']))
    if 'date_to' in filters:
        query = query.filter(DashboardSnapshot.data_through <= date.fromisoformat(filters['date_to']))
    return query.order_by(DashboardSnapshot.id).all()


def _published_team_state_artifacts(snapshot_ids):
    from models.share_artifact import LIFECYCLE_PUBLISHED, ShareArtifact
    from services.team_state_payload import TEAM_STATE_ARTIFACT_TYPE

    if not snapshot_ids:
        return []
    return (
        ShareArtifact.query
        .filter(
            ShareArtifact.artifact_type == TEAM_STATE_ARTIFACT_TYPE,
            ShareArtifact.source_snapshot_id.in_(snapshot_ids),
            ShareArtifact.subject_type.is_(None),
            ShareArtifact.lifecycle_state == LIFECYCLE_PUBLISHED,
        )
        .order_by(ShareArtifact.source_snapshot_id, ShareArtifact.team_id)
        .all()
    )


def collect_pairs(filters):
    snapshots = _trusted_snapshots(filters)
    if not snapshots:
        raise ExportError('No trusted published snapshots matched the requested range.')
    by_id = {snapshot.id: snapshot for snapshot in snapshots}
    artifacts = _published_team_state_artifacts(list(by_id))
    if not artifacts:
        raise ExportError(
            'Matched trusted snapshots but no published Team State artifacts; '
            'the requested range carries no Team State authority.'
        )
    return [(by_id[artifact.source_snapshot_id], artifact) for artifact in artifacts]


def main(argv=None):
    args = _parse_args(argv)
    try:
        filters = _filters_from_args(args)
    except ExportError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2

    from app import app
    from services.team_state_history_export import build_export
    from utils.db import db

    with app.app_context():
        try:
            pairs = collect_pairs(filters)
        except ExportError as exc:
            print(f'error: {exc}', file=sys.stderr)
            return 2
        export = build_export(
            pairs,
            generated_at=datetime.now(timezone.utc).isoformat(),
            repository_sha=_repository_sha(),
            filters=filters,
        )
        # Read-only guarantee, asserted rather than assumed: a SELECT-only pass
        # leaves the session clean. Roll back regardless so nothing can escape.
        dirty = bool(db.session.new or db.session.dirty or db.session.deleted)
        db.session.rollback()
        if dirty:
            print('error: export unexpectedly staged ORM changes; aborting.', file=sys.stderr)
            return 3

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(export, indent=2, sort_keys=True, default=str))
    print(
        f"Exported {export['team_classification_count']} team-classifications "
        f"across {export['snapshot_count']} snapshots to {output}"
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
