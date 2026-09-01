#!/usr/bin/env python3
"""Freeze and verify the trusted publication for static distribution export."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ['AUTO_SYNC'] = 'false'

from app import app
from models.dashboard_snapshot import DashboardSnapshot
from models.sync_run import SyncRun
from services import dashboard_snapshot as dashboard_snapshot_service
from utils.db import db
from utils.summary_output import SummaryOutputError, serialize_summary, write_summary


EXIT_OK = 0
EXIT_INVALID_PUBLICATION = 1
EXIT_OUTPUT_FAILED = 2


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot-id', type=int)
    parser.add_argument('--sync-run-id', type=int)
    parser.add_argument('--data-through')
    parser.add_argument('--publication-source')
    parser.add_argument('--publication-type')
    parser.add_argument('--output', required=True)
    return parser.parse_args(argv)


def resolve_publication(
    *,
    snapshot_id=None,
    sync_run_id=None,
    data_through=None,
    publication_source=None,
    publication_type=None,
):
    current = dashboard_snapshot_service.get_latest_valid_dashboard_snapshot()
    if current is None:
        raise ValueError('trusted_publication_missing')

    requested_id = snapshot_id if snapshot_id is not None else current.id
    requested = db.session.get(DashboardSnapshot, requested_id)
    if requested is None:
        raise ValueError('requested_snapshot_missing')
    if requested.id != current.id:
        raise ValueError('requested_snapshot_not_current')
    if not requested.is_published or requested.status != 'ready':
        raise ValueError('requested_snapshot_not_trusted')
    if requested.sync_run_id is None:
        raise ValueError('requested_snapshot_sync_run_missing')
    if requested.published_at is None or requested.snapshot_generated_at is None:
        raise ValueError('requested_snapshot_publication_metadata_missing')

    run = db.session.get(SyncRun, requested.sync_run_id)
    if run is None:
        raise ValueError('requested_sync_run_missing')
    if run.published_dashboard_snapshot_id != requested.id:
        raise ValueError('sync_run_publication_identity_mismatch')
    if sync_run_id is not None and requested.sync_run_id != sync_run_id:
        raise ValueError('sync_run_id_mismatch')

    requested_data_through = (
        requested.data_through.isoformat() if requested.data_through else None
    )
    if data_through and requested_data_through != data_through:
        raise ValueError('data_through_mismatch')
    if publication_source and run.source != publication_source:
        raise ValueError('publication_source_mismatch')

    return {
        'status': 'ok',
        'requested_snapshot_id': requested_id,
        'publication_snapshot_id': requested.id,
        'sync_run_id': requested.sync_run_id,
        'data_through': requested_data_through,
        'published_at': requested.published_at.isoformat() if requested.published_at else None,
        'snapshot_generated_at': (
            requested.snapshot_generated_at.isoformat()
            if requested.snapshot_generated_at else None
        ),
        'snapshot_source': requested.source,
        'publication_source': run.source,
        'publication_type': publication_type or run.job_name,
        'current': True,
    }


def main(argv=None):
    args = parse_args(argv)
    try:
        with app.app_context():
            result = resolve_publication(
                snapshot_id=args.snapshot_id,
                sync_run_id=args.sync_run_id,
                data_through=args.data_through,
                publication_source=args.publication_source,
                publication_type=args.publication_type,
            )
    except ValueError as exc:
        result = {
            'status': 'refused',
            'reason': str(exc),
            'requested_snapshot_id': args.snapshot_id,
        }
        print(serialize_summary(result))
        try:
            write_summary(result, args.output)
        except SummaryOutputError:
            return EXIT_OUTPUT_FAILED
        return EXIT_INVALID_PUBLICATION

    print(serialize_summary(result))
    try:
        write_summary(result, args.output)
    except SummaryOutputError:
        return EXIT_OUTPUT_FAILED
    return EXIT_OK


if __name__ == '__main__':
    raise SystemExit(main())
