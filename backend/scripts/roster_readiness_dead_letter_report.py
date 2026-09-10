"""
Read-only report of the dead letters that block public roster readiness.

Public roster readiness (public_roster_readiness_v1) degrades with reason code
``dead_letters_unresolved`` when ANY unresolved sync_failures row exists for
the roster source family entity types (see
services.source_readiness._roster_status_snapshot_readiness →
_unresolved_failure_count(entity_types=ROSTER_STATUS_FAILURE_ENTITY_TYPES)).
This report lists exactly those rows, grouped by conflict identity, and
assesses whether current official roster snapshots already supersede each one
(in which case the next daily roster sync resolves it automatically).

Strictly read-only: no rows are modified.

Usage:
  python backend/scripts/roster_readiness_dead_letter_report.py [--json]
      [--include-resolved]
"""

import argparse
import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ['AUTO_SYNC'] = 'false'


def _iso(value):
    return value.isoformat() if value is not None else None


def build_report(include_resolved=False):
    from models.pitcher import Pitcher
    from models.sync_failure import SyncFailure
    from services.roster_status_sync import (
        ROSTER_STATUS_CONFLICT_ENTITY_TYPE,
        ROSTER_STATUS_FETCH_ENTITY_TYPE,
        ROSTER_STATUS_IDENTITY_ENTITY_TYPE,
        latest_roster_status_snapshot_for_pitcher,
    )
    from services.source_readiness import ROSTER_STATUS_FAILURE_ENTITY_TYPES

    query = SyncFailure.query.filter(
        SyncFailure.entity_type.in_(ROSTER_STATUS_FAILURE_ENTITY_TYPES)
    )
    if not include_resolved:
        query = query.filter(SyncFailure.resolved.is_(False))
    rows = query.order_by(SyncFailure.created_at.asc(), SyncFailure.id.asc()).all()

    def _assessment(row):
        payload = row.payload or {}
        if row.entity_type == ROSTER_STATUS_CONFLICT_ENTITY_TYPE:
            pitcher = None
            mlb_id = payload.get('mlb_id') or row.entity_ref
            try:
                pitcher = Pitcher.query.filter_by(mlb_id=int(mlb_id)).first()
            except (TypeError, ValueError):
                pitcher = None
            if pitcher is None:
                return 'A_unresolvable_pitcher_not_tracked', None
            latest = latest_roster_status_snapshot_for_pitcher(pitcher.id)
            conflict_date = payload.get('snapshot_date')
            if (
                latest is not None
                and conflict_date
                and latest.snapshot_date.isoformat() >= conflict_date
                and str(latest.source or '').startswith('mlb_stats_api:roster_sync:')
            ):
                return 'B_superseded_by_newer_official_snapshot', pitcher.full_name
            return 'A_genuine_unresolved_conflict', pitcher.full_name
        if row.entity_type == ROSTER_STATUS_IDENTITY_ENTITY_TYPE:
            return 'B_if_next_clean_team_sync_parses_all_entries', None
        if row.entity_type == ROSTER_STATUS_FETCH_ENTITY_TYPE:
            return 'B_if_next_team_fetch_succeeds', None
        return 'D_unclassified', None

    entries = []
    groups = {}
    for row in rows:
        payload = row.payload or {}
        assessment, player_name = _assessment(row)
        entry = {
            'id': row.id,
            'entity_type': row.entity_type,
            'entity_ref': row.entity_ref,
            'job_name': row.job_name,
            'sync_run_id': row.sync_run_id,
            'created_at': _iso(row.created_at),
            'resolved': bool(row.resolved),
            'resolved_at': _iso(row.resolved_at),
            'error': row.error,
            'reason': payload.get('reason'),
            'player_mlb_id': payload.get('mlb_id') or payload.get('pitcher_mlb_id'),
            'player_name': player_name,
            'team_id': payload.get('team_id'),
            'existing_team_id': payload.get('existing_team_id'),
            'incoming_team_id': payload.get('incoming_team_id'),
            'conflict_snapshot_date': payload.get('snapshot_date'),
            'roster_type': payload.get('roster_type'),
            'assessment': assessment,
        }
        entries.append(entry)
        key = (row.entity_type, row.entity_ref)
        group = groups.setdefault(key, {
            'entity_type': row.entity_type,
            'entity_ref': row.entity_ref,
            'occurrence_count': 0,
            'first_seen_at': _iso(row.created_at),
            'last_seen_at': _iso(row.created_at),
            'row_ids': [],
            'assessment': assessment,
        })
        group['occurrence_count'] += 1
        group['last_seen_at'] = _iso(row.created_at)
        group['row_ids'].append(row.id)

    return {
        'blocking_entity_types': list(ROSTER_STATUS_FAILURE_ENTITY_TYPES),
        'unresolved_included_only': not include_resolved,
        'row_count': len(entries),
        'rows': entries,
        'conflict_groups': sorted(
            groups.values(),
            key=lambda group: (group['entity_type'], str(group['entity_ref'])),
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Report dead letters blocking public roster readiness (read-only).'
    )
    parser.add_argument('--json', action='store_true', help='Emit JSON only.')
    parser.add_argument(
        '--include-resolved',
        action='store_true',
        help='Include already-resolved rows for audit history context.',
    )
    args = parser.parse_args(argv)

    from app import app

    with app.app_context():
        report = build_report(include_resolved=args.include_resolved)

    if args.json:
        print(json.dumps(report, sort_keys=True, default=str))
        return 0

    print('Roster-readiness dead-letter report')
    print(f"Blocking entity types: {', '.join(report['blocking_entity_types'])}")
    print(f"Rows: {report['row_count']}")
    for entry in report['rows']:
        print(
            f"  id={entry['id']} type={entry['entity_type']} ref={entry['entity_ref']} "
            f"created={entry['created_at']} resolved={entry['resolved']} "
            f"player={entry['player_name'] or entry['player_mlb_id'] or '-'} "
            f"team={entry['team_id'] or '-'} "
            f"teams={entry['existing_team_id'] or '-'}→{entry['incoming_team_id'] or '-'} "
            f"date={entry['conflict_snapshot_date'] or '-'} "
            f"reason={entry['reason'] or entry['error']} "
            f"assessment={entry['assessment']}"
        )
    print('Groups (same conflict identity):')
    for group in report['conflict_groups']:
        print(
            f"  {group['entity_type']} ref={group['entity_ref']} "
            f"occurrences={group['occurrence_count']} "
            f"first={group['first_seen_at']} last={group['last_seen_at']} "
            f"rows={group['row_ids']} assessment={group['assessment']}"
        )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
