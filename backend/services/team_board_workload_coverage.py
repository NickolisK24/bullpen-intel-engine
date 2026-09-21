"""Publication-time slate evidence for frozen Team Board workload windows.

This only batches the older days absent from TB-03's seven-day coverage. The
actual daily completeness decision remains owned by slate_coverage.
"""

from collections import defaultdict
from datetime import timedelta

from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from services import slate_coverage


WORKLOAD_DAYS = 30


def extend_coverage(anchor, recent_coverage):
    """Return 30 publication-date decisions with at most two source queries."""
    coverage = dict(recent_coverage or {})
    oldest = anchor - timedelta(days=WORKLOAD_DAYS - 1)
    context = slate_coverage._SCHEDULE_CONTEXT_WINDOW_DAYS
    try:
        rows = ScheduledGame.query.filter(
            ScheduledGame.game_date >= oldest - timedelta(days=context),
            ScheduledGame.game_date <= anchor + timedelta(days=context),
        ).all()
        game_pks = {row.game_pk for row in rows if row.game_pk is not None}
        markers = (
            PostgameProcessedGame.query.filter(
                PostgameProcessedGame.mlb_game_pk.in_(game_pks)
            ).all() if game_pks else []
        )
    except Exception:
        rows = None
        markers = None

    by_date = defaultdict(list)
    for row in rows or []:
        by_date[row.game_date].append(row)
    for offset in range(WORKLOAD_DAYS):
        day = anchor - timedelta(days=offset)
        if day.isoformat() in coverage:
            continue
        if rows is None or markers is None:
            coverage[day.isoformat()] = slate_coverage.unknown_slate_coverage(day)
            continue
        nearby = any(
            by_date.get(day + timedelta(days=delta))
            for delta in range(-context, context + 1)
        )
        try:
            coverage[day.isoformat()] = slate_coverage.compute_slate_coverage(
                day, schedule_rows=by_date.get(day, []),
                postgame_markers=markers, schedule_material_available=nearby,
            )
        except Exception:
            coverage[day.isoformat()] = slate_coverage.unknown_slate_coverage(day)
    return coverage
