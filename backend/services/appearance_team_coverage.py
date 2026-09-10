"""Read-only coverage audit for the team-at-appearance authority (Foundation 1).

Bounded internal diagnostics over the durable ``GameLog`` appearance-team columns:
how many appearances carry a resolved team, how many are unresolved/conflicted, how
many are legacy rows not yet attributed (NULL), broken down by season and by the
official source that resolved them, plus a current-team-mismatch signal (resolved
appearances whose represented team differs from the pitcher's current team — the
population the future team-season aggregation must attribute correctly).

This module READS ONLY. It performs no backfill (Step 2 owns that), mutates nothing,
computes no baseball metric, and exposes nothing publicly. It logs no external
payloads and no secrets.
"""

from __future__ import annotations

from models.game_log import GameLog
from models.pitcher import Pitcher
from services.appearance_team_authority import (
    STATUS_CONFLICT,
    STATUS_RESOLVED,
    STATUS_UNRESOLVED,
)
from utils.db import db


# The legacy sentinel for a row with no stored appearance-team status.
LEGACY_NULL = 'null_legacy'


def _counts_by(session, column):
    rows = (
        session.query(column, db.func.count(GameLog.id))
        .group_by(column)
        .all()
    )
    return rows


def build_appearance_team_coverage(*, session=None) -> dict:
    """Deterministic coverage counts for the team-at-appearance authority.

    Ordering is deterministic (sorted keys) so repeated audits over the same data
    are byte-identical. Never writes; never consults the current roster except for
    the explicit mismatch diagnostic below.
    """
    session = session or db.session

    total = session.query(db.func.count(GameLog.id)).scalar() or 0

    status_counts = {
        STATUS_RESOLVED: 0,
        STATUS_UNRESOLVED: 0,
        STATUS_CONFLICT: 0,
        LEGACY_NULL: 0,
    }
    for status, count in _counts_by(session, GameLog.appearance_team_status):
        key = status if status is not None else LEGACY_NULL
        status_counts[key] = status_counts.get(key, 0) + int(count)

    by_source = {}
    for source, count in _counts_by(session, GameLog.appearance_team_source):
        by_source[source if source is not None else LEGACY_NULL] = int(count)

    by_season = {}
    season_rows = (
        session.query(
            db.extract('year', GameLog.game_date),
            GameLog.appearance_team_status,
            db.func.count(GameLog.id),
        )
        .group_by(db.extract('year', GameLog.game_date), GameLog.appearance_team_status)
        .all()
    )
    for season, status, count in season_rows:
        season_key = int(season) if season is not None else None
        bucket = by_season.setdefault(
            season_key,
            {STATUS_RESOLVED: 0, STATUS_UNRESOLVED: 0, STATUS_CONFLICT: 0, LEGACY_NULL: 0},
        )
        key = status if status is not None else LEGACY_NULL
        bucket[key] = bucket.get(key, 0) + int(count)

    # Diagnostic only (never an attribution source): resolved appearances whose
    # represented team differs from the pitcher's CURRENT team — the traded/optioned
    # population the historical authority now protects.
    current_team_mismatch = (
        session.query(db.func.count(GameLog.id))
        .join(Pitcher, GameLog.pitcher_id == Pitcher.id)
        .filter(GameLog.appearance_team_status == STATUS_RESOLVED)
        .filter(GameLog.appearance_team_id.isnot(None))
        .filter(Pitcher.team_id.isnot(None))
        .filter(GameLog.appearance_team_id != Pitcher.team_id)
        .scalar()
    ) or 0

    return {
        'capability': 'appearance_team_coverage_v1',
        'total_game_logs': int(total),
        'resolved': status_counts[STATUS_RESOLVED],
        'unresolved': status_counts[STATUS_UNRESOLVED],
        'conflict': status_counts[STATUS_CONFLICT],
        'null_legacy': status_counts[LEGACY_NULL],
        'by_source': dict(sorted(by_source.items(), key=lambda kv: str(kv[0]))),
        'by_season': {
            season: by_season[season]
            for season in sorted(by_season, key=lambda s: (s is None, s))
        },
        'current_team_mismatch': int(current_team_mismatch),
    }
