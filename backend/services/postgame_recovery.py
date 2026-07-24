"""Explicit and automatic recovery controls for inconsistent postgame markers.

Normal postgame refreshes intentionally stop retrying a game after the retry
limit. This module provides the narrow operator-invoked reset for visible failed
markers and an automatic bounded repair for impossible marker/ledger states.
"""

from datetime import date

from models.game_log import GameLog
from models.postgame_processed_game import PostgameProcessedGame
from utils.db import db
from utils.time import utc_now_naive


MISSING_APPEARANCE_ROWS_REASON = 'appearance_rows_missing_after_full_marker'


def reset_failed_postgame_markers(
    *,
    schedule_date: date | None = None,
    game_pks: list[int] | tuple[int, ...] | set[int] | None = None,
) -> dict:
    """Reset selected FAILED markers so the next refresh can retry them.

    At least one selector is required. When both are supplied they are combined
    with AND semantics, preventing a broad accidental reset.
    """
    normalized_game_pks = sorted({int(game_pk) for game_pk in (game_pks or [])})
    if schedule_date is None and not normalized_game_pks:
        raise ValueError('schedule_date or game_pks is required for failed-marker recovery')

    query = PostgameProcessedGame.query.filter_by(
        processing_status=PostgameProcessedGame.STATUS_FAILED,
    )
    if schedule_date is not None:
        query = query.filter(PostgameProcessedGame.game_date == schedule_date)
    if normalized_game_pks:
        query = query.filter(PostgameProcessedGame.mlb_game_pk.in_(normalized_game_pks))

    markers = query.order_by(PostgameProcessedGame.mlb_game_pk.asc()).all()
    reset_at = utc_now_naive()
    for marker in markers:
        marker.processing_status = PostgameProcessedGame.STATUS_INCOMPLETE
        marker.attempt_count = 0
        marker.last_attempted_at = None
        marker.failed_at = None
        marker.processed_at = None
        marker.sync_run_id = None
        # Preserve incomplete_reason and prior counters as operator-visible
        # diagnostics until the next authoritative attempt replaces them.

    db.session.commit()
    return {
        'status': 'reset' if markers else 'no_matching_failed_markers',
        'schedule_date': schedule_date.isoformat() if schedule_date else None,
        'requested_game_pks': normalized_game_pks,
        'markers_reset': len(markers),
        'reset_game_pks': [marker.mlb_game_pk for marker in markers],
        'reset_at': reset_at.isoformat(),
    }


def reset_fully_processed_markers_without_appearance_rows(
    *,
    schedule_dates: list[date] | tuple[date, ...] | set[date],
) -> dict:
    """Reopen impossible fully-processed markers inside a bounded date set.

    A fully processed postgame marker is only trustworthy when at least one
    appearance row exists for that game. If the marker is closed but the ledger
    has no rows, reopen it so the normal postgame boxscore path can rebuild the
    game atomically. The caller must provide the exact slate dates it is about
    to sweep; this function never performs an unbounded production reset.
    """
    normalized_dates = sorted({value for value in schedule_dates if value is not None})
    if not normalized_dates:
        return {
            'status': 'not_requested',
            'schedule_dates': [],
            'markers_reset': 0,
            'reset_game_pks': [],
            'reset_at': None,
        }

    markers = (
        PostgameProcessedGame.query
        .filter(PostgameProcessedGame.game_date.in_(normalized_dates))
        .filter(
            PostgameProcessedGame.processing_status
            == PostgameProcessedGame.STATUS_FULLY_PROCESSED
        )
        .order_by(PostgameProcessedGame.mlb_game_pk.asc())
        .all()
    )
    marker_game_pks = [marker.mlb_game_pk for marker in markers]
    represented_game_pks = set()
    if marker_game_pks:
        represented_game_pks = {
            game_pk
            for (game_pk,) in (
                db.session.query(GameLog.mlb_game_pk)
                .filter(GameLog.mlb_game_pk.in_(marker_game_pks))
                .distinct()
                .all()
            )
        }

    inconsistent = [
        marker for marker in markers
        if marker.mlb_game_pk not in represented_game_pks
    ]
    reset_at = utc_now_naive()
    for marker in inconsistent:
        marker.processing_status = PostgameProcessedGame.STATUS_INCOMPLETE
        marker.attempt_count = 0
        marker.last_attempted_at = None
        marker.incomplete_reason = MISSING_APPEARANCE_ROWS_REASON
        marker.processed_at = None
        marker.failed_at = None
        marker.sync_run_id = None

    db.session.commit()
    return {
        'status': 'reset' if inconsistent else 'no_inconsistent_markers',
        'schedule_dates': [value.isoformat() for value in normalized_dates],
        'markers_reset': len(inconsistent),
        'reset_game_pks': [marker.mlb_game_pk for marker in inconsistent],
        'reset_at': reset_at.isoformat(),
    }
