"""Completed Game Context backfill (COIN).

Games processed before COIN Phase 3 have no ``completed_game_contexts`` rows:
the ``postgame_processed_games`` marker makes the normal refresh skip them, so
context was never derived. This module is the explicit, opt-in path to derive
context for those historical games.

Candidate source: ``postgame_processed_games``. It is the authoritative ledger
of games whose pitching lines were already ingested — exactly the set the normal
refresh skips — and it carries one row per game with both team ids and the game
date, so it is cleaner than scanning the per-pitcher ``game_logs``. A game is
"covered" when a CompletedGameContext row exists for each of its teams.

The work itself reuses the live pipeline unchanged: it resolves the schedule
game, fetches the boxscore, and hands off to ``sync.generate_completed_game_context``
(which transiently fetches linescore/play-by-play, normalizes via the adapter,
extracts derived context, and upserts one row per team). No raw play-by-play is
stored, confidence gates are untouched, and the upsert keeps reruns idempotent.

Safety: the caller must pass an explicit date range or a limit — the backfill
refuses to sweep an entire season unbounded. Failures are per-game and
fail-closed: one bad game rolls back only its own work and the backfill
continues (unless ``strict`` is set).
"""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import or_

from utils.db import db
from models.completed_game_context import CompletedGameContext
from models.postgame_processed_game import PostgameProcessedGame
from services import sync as sync_service
from services.mlb_api import mlb_client


logger = logging.getLogger(__name__)

BACKFILL_SOURCE = 'completed_game_context_backfill'


def _coerce_date(value):
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _candidate_games(start_date, end_date, team_id, limit):
    query = PostgameProcessedGame.query
    if start_date is not None:
        query = query.filter(PostgameProcessedGame.game_date >= start_date)
    if end_date is not None:
        query = query.filter(PostgameProcessedGame.game_date <= end_date)
    if team_id is not None:
        query = query.filter(or_(
            PostgameProcessedGame.home_team_id == team_id,
            PostgameProcessedGame.away_team_id == team_id,
        ))
    query = query.order_by(
        PostgameProcessedGame.game_date.asc(),
        PostgameProcessedGame.mlb_game_pk.asc(),
    )
    if limit is not None:
        query = query.limit(limit)
    return query.all()


def _existing_context_team_ids(game_pk) -> set[int]:
    rows = (
        db.session.query(CompletedGameContext.team_id)
        .filter(CompletedGameContext.game_pk == game_pk)
        .all()
    )
    return {row[0] for row in rows if row[0] is not None}


def _is_covered(marker, existing_team_ids: set[int]) -> bool:
    team_ids = {tid for tid in (marker.home_team_id, marker.away_team_id) if tid is not None}
    if team_ids:
        return team_ids <= existing_team_ids
    # Marker lacks team ids — fall back to "both sides present".
    return len(existing_team_ids) >= 2


def _resolve_schedule_game(game_pk, game_date):
    """Fetch the schedule for the game's date and return the matching game dict."""
    games = mlb_client.get_schedule(
        start_date=game_date.isoformat(),
        end_date=game_date.isoformat(),
    )
    for game in games or []:
        if sync_service._game_pk(game) == game_pk:
            return game
    return None


def run_backfill(
    app,
    *,
    start_date=None,
    end_date=None,
    team_id=None,
    limit=None,
    dry_run=False,
    force=False,
    strict=False,
) -> dict:
    """Derive completed-game context for already-processed historical games.

    Requires an explicit date range or a limit so a full season is never swept
    by accident. Returns a summary of counters; never raises per game unless
    ``strict`` is set.
    """
    start_date = _coerce_date(start_date)
    end_date = _coerce_date(end_date)
    if start_date is None and end_date is None and limit is None:
        raise ValueError(
            'Refusing to backfill without an explicit date range or limit; '
            'pass start_date/end_date or limit.'
        )

    summary = {
        'source': BACKFILL_SOURCE,
        'dry_run': bool(dry_run),
        'force': bool(force),
        'strict': bool(strict),
        'start_date': start_date.isoformat() if start_date else None,
        'end_date': end_date.isoformat() if end_date else None,
        'team_id': team_id,
        'limit': limit,
        'candidate_games': 0,
        'skipped_existing': 0,
        'would_process': 0,
        'skipped_missing_data': 0,
        'contexts_upserted': 0,
        'games_succeeded': 0,
        'games_failed': 0,
        'failures': [],
    }

    with app.app_context():
        candidates = _candidate_games(start_date, end_date, team_id, limit)
        summary['candidate_games'] = len(candidates)

        for marker in candidates:
            game_pk = marker.mlb_game_pk
            existing = _existing_context_team_ids(game_pk)
            if _is_covered(marker, existing) and not force:
                summary['skipped_existing'] += 1
                continue

            # Dry run: report intent only — no MLB fetch, no writes.
            if dry_run:
                summary['would_process'] += 1
                continue

            try:
                game = _resolve_schedule_game(game_pk, marker.game_date)
                if game is None:
                    summary['skipped_missing_data'] += 1
                    summary['failures'].append(
                        {'game_pk': game_pk, 'reason': 'schedule_game_not_found'}
                    )
                    continue

                boxscore = mlb_client.get_game_boxscore(game_pk)
                result = sync_service.generate_completed_game_context(
                    game,
                    boxscore=boxscore,
                    game_date=marker.game_date,
                )
                if result['contexts_upserted'] > 0:
                    db.session.commit()
                    summary['contexts_upserted'] += result['contexts_upserted']
                    summary['games_succeeded'] += 1
                else:
                    # No usable payload — write nothing rather than partial context.
                    db.session.rollback()
                    summary['skipped_missing_data'] += 1
                    summary['failures'].append(
                        {'game_pk': game_pk, 'reason': result.get('reason') or 'no_contexts'}
                    )
            except Exception as exc:  # noqa: BLE001 — per-game fail-closed
                db.session.rollback()
                summary['games_failed'] += 1
                summary['failures'].append({'game_pk': game_pk, 'reason': str(exc)})
                logger.warning('Backfill failed for game_pk=%s: %s', game_pk, exc)
                if strict:
                    raise

    return summary
