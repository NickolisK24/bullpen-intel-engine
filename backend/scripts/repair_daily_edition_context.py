"""Repair one current Daily Edition whose completed-game context is missing."""

from __future__ import annotations

import argparse
from datetime import date
import json
import os


CONFIRMATION = 'REPAIR_DAILY_EDITION_CONTEXT'
SOURCE = 'daily_edition_context_incident_repair'


def _parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--date', required=True, dest='repair_date')
    parser.add_argument('--confirm', required=True)
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    if args.confirm != CONFIRMATION:
        print(json.dumps({'status': 'refused', 'reason': 'confirmation_required'}))
        return 2

    try:
        repair_date = date.fromisoformat(args.repair_date)
    except ValueError:
        print(json.dumps({'status': 'refused', 'reason': 'invalid_date'}))
        return 2

    # This is a bounded manual repair. Never start the in-process scheduler.
    os.environ['AUTO_SYNC'] = 'false'

    from app import app
    from models.dashboard_snapshot import DashboardSnapshot
    from services import completed_game_context_backfill
    from services import dashboard_snapshot as dashboard_snapshot_service
    from services import intelligence_surface_snapshot
    from utils.db import db

    with app.app_context():
        publication = (
            DashboardSnapshot.query
            .filter_by(
                snapshot_type=(
                    dashboard_snapshot_service.SNAPSHOT_TYPE_BULLPEN_DASHBOARD
                ),
                is_published=True,
                status=dashboard_snapshot_service.SNAPSHOT_STATUS_READY,
            )
            .order_by(DashboardSnapshot.id.desc())
            .first()
        )
        if publication is None:
            print(json.dumps({
                'status': 'refused',
                'reason': 'trusted_publication_unavailable',
            }))
            return 2
        if publication.data_through != repair_date:
            print(json.dumps({
                'status': 'refused',
                'reason': 'repair_date_is_not_current_publication',
                'repair_date': repair_date.isoformat(),
                'current_data_through': publication.data_through.isoformat(),
                'publication_snapshot_id': publication.id,
            }, sort_keys=True))
            return 2

        backfill = completed_game_context_backfill.run_backfill(
            app,
            start_date=repair_date,
            end_date=repair_date,
            strict=True,
        )
        if (
            backfill.get('candidate_games', 0) <= 0
            or backfill.get('games_failed', 0) != 0
            or backfill.get('skipped_missing_data', 0) != 0
        ):
            print(json.dumps({
                'status': 'failed',
                'reason': 'completed_game_context_backfill_incomplete',
                'backfill': backfill,
            }, sort_keys=True))
            return 1

        response = intelligence_surface_snapshot.generate_snapshot_for_date(
            repair_date,
            source=SOURCE,
            publication_snapshot=publication,
            commit=False,
        )
        if (
            response.get('status') != 'ok'
            or response.get('lead_story') is None
            or int(response.get('publishable_candidates') or 0) <= 0
        ):
            db.session.rollback()
            print(json.dumps({
                'status': 'failed',
                'reason': 'daily_edition_still_empty_after_context_repair',
                'reference_date': response.get('reference_date'),
                'empty_reason': response.get('empty_reason'),
                'candidates_considered': response.get('candidates_considered'),
                'publishable_candidates': response.get('publishable_candidates'),
                'errors': response.get('errors'),
                'backfill': backfill,
            }, sort_keys=True))
            return 1
        db.session.commit()

        print(json.dumps({
            'status': 'repaired',
            'repair_date': repair_date.isoformat(),
            'publication_snapshot_id': publication.id,
            'backfill': backfill,
            'daily_edition': {
                'status': response.get('status'),
                'reference_date': response.get('reference_date'),
                'candidates_considered': response.get('candidates_considered'),
                'publishable_candidates': response.get('publishable_candidates'),
                'lead_team_id': (response.get('lead_story') or {}).get('team_id'),
                'lead_game_pk': (response.get('lead_story') or {}).get('game_pk'),
            },
        }, sort_keys=True))
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
