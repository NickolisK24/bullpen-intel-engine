"""Bounded intraday exact-date roster repair for stored transactions.

Only current-window, already-canonical pitcher transactions whose sole roster
classification is ``roster_snapshot_missing`` enter this lane. Source evidence
must explicitly place the participant on an MLB transaction endpoint on the
exact transaction date. Wrong-team snapshots, unknown events, and historical
windows remain outside this service.
"""

from __future__ import annotations

from models.pitcher import Pitcher
from models.player_transaction import PlayerTransaction, PlayerTransactionSyncWindow
from models.roster_status_snapshot import RosterStatusSnapshot
from services.mlb_api import mlb_client
from services.transaction_ingestion import (
    ALIGNMENT_NO_SNAPSHOT,
    CATEGORY_UNKNOWN,
    WINDOW_STATUS_PARTIAL,
    WINDOW_STATUS_SUCCESS,
    realign_stored_transactions_from_exact_roster,
)
from services.transaction_roster_evidence import (
    acquire_exact_transaction_roster_evidence,
)
from utils.time import utc_now_naive


CORRECTION_SOURCE = 'mlb_stats_api:intraday_transaction_roster_repair'


def select_current_window_roster_repair_candidates():
    """Return the latest governed window and its bounded missing-snapshot rows."""
    window = (
        PlayerTransactionSyncWindow.query
        .filter(PlayerTransactionSyncWindow.status.in_((
            WINDOW_STATUS_SUCCESS,
            WINDOW_STATUS_PARTIAL,
        )))
        .order_by(
            PlayerTransactionSyncWindow.attempted_at.desc(),
            PlayerTransactionSyncWindow.id.desc(),
        )
        .first()
    )
    if window is None:
        return None, [], {}

    rows = (
        PlayerTransaction.query
        .join(Pitcher, Pitcher.id == PlayerTransaction.pitcher_id)
        .filter(
            PlayerTransaction.source_query_start_date == window.source_query_start_date,
            PlayerTransaction.source_query_end_date == window.source_query_end_date,
            PlayerTransaction.transaction_date >= window.source_query_start_date,
            PlayerTransaction.transaction_date <= window.source_query_end_date,
            PlayerTransaction.pitcher_id.isnot(None),
            PlayerTransaction.participant_role == 'pitcher',
            PlayerTransaction.normalized_category != CATEGORY_UNKNOWN,
            PlayerTransaction.roster_snapshot_alignment == ALIGNMENT_NO_SNAPSHOT,
            PlayerTransaction.alignment_reason_code == 'roster_snapshot_missing',
            Pitcher.mlb_id == PlayerTransaction.player_mlb_id,
        )
        .order_by(PlayerTransaction.transaction_date.asc(), PlayerTransaction.id.asc())
        .all()
    )
    if not rows:
        return window, [], {}

    pitcher_ids = {row.pitcher_id for row in rows}
    snapshot_dates = {row.transaction_date for row in rows}
    existing = (
        RosterStatusSnapshot.query
        .filter(RosterStatusSnapshot.pitcher_id.in_(pitcher_ids))
        .filter(RosterStatusSnapshot.snapshot_date.in_(snapshot_dates))
        .order_by(RosterStatusSnapshot.id.asc())
        .all()
    )
    existing_keys = {(row.pitcher_id, row.snapshot_date) for row in existing}
    eligible = [
        row for row in rows
        if (row.pitcher_id, row.transaction_date) not in existing_keys
    ]
    pitchers = (
        Pitcher.query.filter(Pitcher.id.in_({row.pitcher_id for row in eligible})).all()
        if eligible else []
    )
    return window, eligible, {pitcher.id: pitcher for pitcher in pitchers}


def repair_current_window_transaction_roster_evidence(
    *,
    client=None,
    timestamp=None,
    sync_run_id=None,
):
    """Acquire, persist, and consume exact-date evidence for bounded candidates."""
    client = client or mlb_client
    timestamp = timestamp or utc_now_naive()
    window, rows, pitchers_by_id = select_current_window_roster_repair_candidates()
    base = {
        'status': 'success',
        'window_id': getattr(window, 'id', None),
        'window_start_date': _iso(getattr(window, 'source_query_start_date', None)),
        'window_end_date': _iso(getattr(window, 'source_query_end_date', None)),
        'repair_candidates': len(rows),
        'pitchers': len({row.pitcher_id for row in rows}),
        'team_date_pairs': 0,
        'roster_gets_attempted': 0,
        'source_matches': 0,
        'snapshots_created': 0,
        'snapshots_already_identical': 0,
        'conflicts': 0,
        'source_misses': 0,
        'fetch_failures': 0,
        'transactions_corrected': 0,
        'transactions_still_blocked': len(rows),
    }
    if window is None or not rows:
        return base

    transaction_dates = {row.transaction_date for row in rows}
    team_metadata_by_season = {}
    metadata_reader = getattr(client, 'get_team_metadata', None)
    for season in sorted({value.year for value in transaction_dates}):
        try:
            team_metadata_by_season[season] = (
                metadata_reader(season) if callable(metadata_reader) else {}
            ) or {}
        except Exception as exc:  # noqa: BLE001 - missing metadata fails this lane closed
            base.update({
                'status': 'failed',
                'fetch_failures': 1,
                'error_details': [{
                    'reason': 'team_metadata_fetch_failed',
                    'season': season,
                    'error': str(exc),
                }],
            })
            return base

    pitchers_by_mlb_id = {
        pitcher.mlb_id: pitcher for pitcher in pitchers_by_id.values()
    }
    source_rows = [{
        'player_mlb_id': row.player_mlb_id,
        'transaction_date': row.transaction_date,
        'from_team_id': row.from_team_id,
        'to_team_id': row.to_team_id,
    } for row in rows]
    acquisition = acquire_exact_transaction_roster_evidence(
        transactions=source_rows,
        eligible_mlb_ids=pitchers_by_mlb_id,
        pitchers_by_mlb_id=pitchers_by_mlb_id,
        team_metadata_by_season=team_metadata_by_season,
        client=client,
        timestamp=timestamp,
        sync_run_id=sync_run_id,
    )
    base.update({
        'team_date_pairs': acquisition['eligible_team_date_pairs'],
        'roster_gets_attempted': acquisition['requests'],
        'source_matches': acquisition['source_matches'],
        'snapshots_created': acquisition['snapshots_created'],
        'snapshots_already_identical': acquisition['snapshots_unchanged'],
        'conflicts': acquisition['source_conflicts'] + acquisition['snapshot_conflicts'],
        'source_misses': acquisition['source_omissions'],
        'fetch_failures': acquisition['fetch_failures'],
        'error_details': acquisition['error_details'],
    })
    if acquisition['fetch_failures']:
        base['status'] = 'failed'
        return base

    snapshots = (
        RosterStatusSnapshot.query
        .filter(RosterStatusSnapshot.pitcher_id.in_({row.pitcher_id for row in rows}))
        .filter(RosterStatusSnapshot.snapshot_date.in_(transaction_dates))
        .order_by(RosterStatusSnapshot.updated_at.asc(), RosterStatusSnapshot.id.asc())
        .all()
    )
    snapshots_by_pair = {
        (row.pitcher_id, row.snapshot_date): row for row in snapshots
    }
    alignment = realign_stored_transactions_from_exact_roster(
        rows,
        pitchers_by_id=pitchers_by_id,
        roster_snapshots_by_pair=snapshots_by_pair,
        sync_run_id=sync_run_id,
        timestamp=timestamp,
        correction_source=CORRECTION_SOURCE,
    )
    base.update({
        'transactions_corrected': alignment['corrected'],
        'transactions_still_blocked': alignment['still_blocked'],
    })
    return base


def _iso(value):
    return value.isoformat() if value is not None else None


__all__ = [
    'CORRECTION_SOURCE',
    'repair_current_window_transaction_roster_evidence',
    'select_current_window_roster_repair_candidates',
]
