"""Explicit recovery controls for exhausted postgame game markers.

Normal postgame refreshes intentionally stop retrying a game after the retry
limit. This module provides the narrow, operator-invoked reset required to
repair those visible failed markers without weakening the automatic retry
limit.
"""

from datetime import date

from models.postgame_processed_game import PostgameProcessedGame
from utils.db import db
from utils.time import utc_now_naive


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
