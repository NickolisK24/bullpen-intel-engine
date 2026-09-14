"""Admission only for repeated slate-rejected continuous Dashboard candidates.

The candidate's receipt and rejection commit together. A missing receipt (or a
crash before that commit) permits a retry; it never consumes an obligation.
The existing continuous-cycle writer lock serializes these attempts. Admission
does not publish, move a selector, or certify any baseball input as complete.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os

from flask import current_app, has_app_context
from sqlalchemy import Text, func, literal, select
from sqlalchemy.dialects.postgresql import aggregate_order_by

from models.dashboard_snapshot import DashboardSnapshot
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from models.postgame_processed_game import PostgameProcessedGame
from models.roster_status_snapshot import RosterStatusSnapshot
from models.roster_membership import RosterMembershipInterval
from models.final_game_reconciliation import FinalGameVersion
from services import dashboard_snapshot
from services.availability_reference_date import product_current_date
from utils.db import db


SIGNATURE_VERSION = 'continuous-slate-admission-v1'


def _digest_rows(statement):
    """One digest row crosses the production connection, never the evidence.

    Hash actual values, not just count/max(timestamp): in-place corrections and
    deletions must invalidate a receipt. SQLite is solely the disposable-test
    implementation; PostgreSQL hashes ordered projected rows on the server.
    """
    rows = statement.subquery('dependency_rows')
    if db.engine.dialect.name == 'postgresql':
        encoded = func.convert_to(func.row_to_json(rows.table_valued()).cast(Text), 'UTF8')
        row_hash = func.encode(func.sha256(encoded), 'hex')
        combined = func.coalesce(func.string_agg(row_hash, aggregate_order_by(literal(''), rows.c.id)), '')
        return db.session.execute(select(func.encode(func.sha256(
            func.convert_to(combined, 'UTF8'),
        ), 'hex'))).scalar_one()
    values = db.session.execute(select(rows).order_by(rows.c.id)).all()
    return sha256(json.dumps([list(row) for row in values], default=str,
                             separators=(',', ':')).encode()).hexdigest()


def dependency_signature(*, current_publication_id, represented_date):
    # Schedule polling timestamps/observation IDs and marker retry counters are
    # not changed baseball evidence. Include finality, linkage and processing
    # facts explicitly so routine polls cannot defeat suppression.
    schedule_fields = (
        'id', 'team_id', 'game_pk', 'game_date', 'game_datetime', 'opponent_team_id',
        'home_away', 'game_type', 'status_code', 'status_state',
        'original_product_date', 'resumed_game_date', 'resumed_product_date',
        'resumed_from_game_pk', 'resumed_to_game_pk',
    )
    marker_fields = (
        'id', 'mlb_game_pk', 'game_date', 'game_type', 'home_team_id', 'away_team_id',
        'final_state', 'logs_added', 'pitchers_touched', 'processing_status',
        'incomplete_reason', 'pitching_lines_seen', 'pitcher_resolution_failures',
        'correction_attempts_failed',
    )
    pitcher_fields = [column for column in Pitcher.__table__.columns
                      if column.name not in {'created_at', 'updated_at'}]
    # Roster/assignment evidence timestamps participate in authority precedence;
    # they are not generic poll bookkeeping. Retain observation/version identity.
    roster_fields = [column for column in RosterStatusSnapshot.__table__.columns
                     if column.name not in {'created_at', 'updated_at', 'sync_run_id'}]
    inputs = {
        'version': SIGNATURE_VERSION,
        'release': os.environ.get('RENDER_GIT_COMMIT'),
        'payload_version': dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION,
        'represented_date': represented_date.isoformat(),
        'current_publication_id': current_publication_id,
        'policy': {key: current_app.config.get(key, os.environ.get(key)) for key in (
            'ROLE_AUTHORITY_ENABLED', 'AMBIGUOUS_START_SHARE_ELIGIBILITY_THRESHOLD',
            'DAILY_EDITION_PUBLICATION_REQUIRED', 'FRESHNESS_STALE_AFTER_DAYS',
            'FRESHNESS_UNAVAILABLE_AFTER_DAYS',
        )},
        # Full canonical appearance values include first-write and correction
        # identities and future/old evidence. There is no guessed date window.
        'appearances': _digest_rows(select(*GameLog.__table__.columns)),
        'pitchers': _digest_rows(select(*pitcher_fields)),
        'schedule': _digest_rows(select(*(getattr(ScheduledGame, field) for field in schedule_fields))),
        'markers': _digest_rows(select(*(getattr(PostgameProcessedGame, field) for field in marker_fields))),
        'roster': _digest_rows(select(*roster_fields)),
        'membership': _digest_rows(select(*RosterMembershipInterval.__table__.columns)),
        'canonical_versions': _digest_rows(select(*FinalGameVersion.__table__.columns)
                                         .where(FinalGameVersion.is_current.is_(True))),
    }
    return sha256(json.dumps(inputs, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def prepare(*, current_publication_id, source):
    if not has_app_context():
        # Preserve the adapter's database-free unit seam; production owns an app.
        return None, None
    prior = db.session.execute(select(
        DashboardSnapshot.id, DashboardSnapshot.data_through,
        DashboardSnapshot.build_dependency_signature, DashboardSnapshot.error_message,
    ).where(
        DashboardSnapshot.snapshot_type == dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
        DashboardSnapshot.source == source,
    ).order_by(DashboardSnapshot.id.desc()).limit(1)).first()
    if (prior is not None and prior.build_dependency_signature
            and prior.error_message == dashboard_snapshot.DASHBOARD_SNAPSHOT_SLATE_COVERAGE_INCOMPLETE):
        # The heavy writer previously owned this refresh. Keep that existing
        # source check alive even while heavy builds are deferred.
        dashboard_snapshot._refresh_stale_non_final_slate_games(prior.data_through)
    signature = dependency_signature(
        current_publication_id=current_publication_id,
        represented_date=product_current_date(),
    )
    blocked = (
        prior is not None
        and prior.error_message == dashboard_snapshot.DASHBOARD_SNAPSHOT_SLATE_COVERAGE_INCOMPLETE
        and prior.build_dependency_signature == signature
    )
    return signature, prior if blocked else None
