"""Read frozen Team Board inputs from the selected Dashboard row.

Only PostgreSQL has the row-version token used here. A hit saves transferring
and decoding the league document, never the lookup of the publication itself.
"""

import json
from types import SimpleNamespace
from typing import NamedTuple

import msgspec
from flask import current_app
from sqlalchemy import String, Text, and_, case, cast, literal_column
from sqlalchemy.exc import SQLAlchemyError

from models.dashboard_snapshot import DashboardSnapshot
from services import dashboard_snapshot as dashboards
from utils.db import db


class _Boards(msgspec.Struct):
    contract: str
    data_through: str
    by_team_id: dict[str, msgspec.Raw]
    frozen_team_state_by_team_id: dict[str, msgspec.Raw]


class _Source(msgspec.Struct):
    freshness: msgspec.Raw
    trusted_team_boards: _Boards


class _CachedSource(NamedTuple):
    snapshot_id: int
    row_version: str
    team_key: str | None
    source: _Source


_DECODER = msgspec.json.Decoder(_Source)
_CACHE_KEY = 'team_board_snapshot_source'
# One immutable source per Flask worker. Oversized publications retain at most
# one team's inputs, so the core-to-details handoff can still benefit.
_MAX_BYTES = 16 * 1024 * 1024


def _project(source, key):
    boards = source.trusted_team_boards
    team = boards.by_team_id.get(key)
    receipt = boards.frozen_team_state_by_team_id.get(key)
    return {
        'freshness': msgspec.json.decode(source.freshness),
        'trusted_team_boards': {
            'contract': boards.contract, 'data_through': boards.data_through,
            'by_team_id': {key: msgspec.json.decode(team)} if team is not None else {},
            'frozen_team_state_by_team_id': (
                {key: msgspec.json.decode(receipt)} if receipt is not None else {}
            ),
        },
    }


def _read(query, team_id):
    key = str(team_id)
    cache = current_app.extensions.get(_CACHE_KEY)
    version = cast(literal_column('dashboard_snapshots.xmin'), String)
    document = cast(DashboardSnapshot.payload, Text)
    reusable = cache is not None and cache.team_key in (None, key)
    if reusable:
        # Capture the entry before the query. A concurrent request may replace
        # the worker's entry but cannot change the source used by this request.
        same_row = and_(DashboardSnapshot.id == cache.snapshot_id, version == cache.row_version)
        document = case((same_row, None), else_=document)
    row = query.with_entities(
        DashboardSnapshot.id, DashboardSnapshot.snapshot_type, DashboardSnapshot.sync_run_id,
        DashboardSnapshot.status, DashboardSnapshot.error_message, DashboardSnapshot.is_published,
        DashboardSnapshot.published_at, DashboardSnapshot.payload_version, DashboardSnapshot.data_through,
        DashboardSnapshot.availability_reference_date, DashboardSnapshot.snapshot_generated_at,
        version.label('row_version'), document.label('document'),
    ).first()
    if row is None:
        return None
    values = row._asdict()
    raw = values.pop('document')
    token = values.pop('row_version')
    if reusable and row.id == cache.snapshot_id and token == cache.row_version:
        payload = _project(cache.source, key)
    elif raw is None:
        payload = None
    else:
        encoded = raw.encode('utf-8')
        try:
            source = _DECODER.decode(encoded)
        except msgspec.DecodeError:
            # Legacy per-team receipts require looking across the entire club
            # map. Preserve the owner's original missing/malformed semantics.
            payload = json.loads(raw)
        else:
            payload = _project(source, key)
            if len(encoded) <= _MAX_BYTES:
                current_app.extensions[_CACHE_KEY] = _CachedSource(row.id, token, None, source)
            else:
                compact = msgspec.json.encode(payload)
                if len(compact) <= _MAX_BYTES:
                    current_app.extensions[_CACHE_KEY] = _CachedSource(
                        row.id, token, key, _DECODER.decode(compact),
                    )
    return SimpleNamespace(**values, payload=payload)


def latest_team_board_snapshot(team_id):
    if db.session.get_bind().dialect.name != 'postgresql':
        return dashboards.get_latest_valid_dashboard_snapshot()
    try:
        snapshot = _read(dashboards._latest_dashboard_snapshot_query(
            dashboards.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
        ), team_id)
    except SQLAlchemyError as exc:
        db.session.rollback()
        current_app.logger.warning('Could not read Team Board snapshot: %s', exc)
        return None
    return snapshot if dashboards.snapshot_current_enough(snapshot) else None


def exact_team_board_snapshot(snapshot_id, team_id, session):
    query = session.query(DashboardSnapshot).filter(DashboardSnapshot.id == snapshot_id)
    if session.get_bind().dialect.name != 'postgresql':
        return query.one_or_none()
    return _read(query, team_id)
