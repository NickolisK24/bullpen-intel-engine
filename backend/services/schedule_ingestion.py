"""MLB schedule ingestion (Schedule Storage V1).

Pulls a window of the MLB schedule and upserts it into ``scheduled_games`` — the
durable, forward-looking team game calendar. One MLB game produces two rows (home
and away), keyed by (team_id, game_pk), so re-ingesting the same window updates
status / time / opponent / series / doubleheader fields in place rather than
duplicating rows.

This module only stores schedule facts. It computes no schedule context, builds no
cards, makes no predictions, and touches no product surface — those are later
phases. Status is normalized conservatively into a small, stable set while the raw
MLB status code is preserved verbatim.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from models.scheduled_game import ScheduledGame
from services.game_finality import normalize_schedule_status_state
from services.mlb_api import mlb_client
from utils.db import db

logger = logging.getLogger(__name__)

DEFAULT_SOURCE = 'schedule_ingestion'

def ingest_schedule(start_date, end_date, *, source=DEFAULT_SOURCE, app=None):
    """Fetch and upsert the MLB schedule for [start_date, end_date].

    ``start_date`` / ``end_date`` may be ``date`` objects or ISO ``YYYY-MM-DD``
    strings. Returns a summary dict. ``app`` (a Flask app) wraps the work in an
    app context for the real path; when already inside an app/request context,
    leave it ``None``. Read of MLB data, write of scheduled_games only.
    """
    def _run():
        games = mlb_client.get_schedule(
            start_date=_iso(start_date), end_date=_iso(end_date))
        return ingest_games(games or [], source=source)

    if app is not None:
        with app.app_context():
            return _run()
    return _run()


def ingest_games(games, *, source=DEFAULT_SOURCE):
    """Upsert an iterable of raw MLB schedule game dicts. Returns a summary.

    Idempotent: each game yields one row per team keyed by (team_id, game_pk).
    A game missing its gamePk or both team ids is skipped (counted), never fatal.
    """
    summary = {
        'games_seen': 0,
        'games_ingested': 0,
        'games_skipped': 0,
        'rows_created': 0,
        'rows_updated': 0,
        'errors': 0,
    }

    for game in games or []:
        summary['games_seen'] += 1
        parsed = _parse_game(game)
        if parsed is None:
            summary['games_skipped'] += 1
            continue
        try:
            for team_id, opponent_id, home_away in (
                (parsed['home_team_id'], parsed['away_team_id'], 'home'),
                (parsed['away_team_id'], parsed['home_team_id'], 'away'),
            ):
                if team_id is None:
                    continue
                outcome = _upsert_row(team_id, opponent_id, home_away, parsed, source)
                summary[f'rows_{outcome}'] += 1
            summary['games_ingested'] += 1
        except Exception:  # noqa: BLE001 — one bad game never sinks the window
            db.session.rollback()
            summary['errors'] += 1
            logger.warning('Schedule ingest failed for game %s',
                           parsed.get('game_pk'), exc_info=True)

    db.session.commit()
    return summary


# ── Parsing ───────────────────────────────────────────────────────────────────

def _parse_game(game):
    """Normalize one raw MLB schedule game into the fields we store.

    Returns a dict (shared fields + home/away team ids) or ``None`` when the game
    is unusable (no gamePk, no valid date, or no teams at all).
    """
    if not isinstance(game, dict):
        return None
    game_pk = _int(game.get('gamePk'))
    if game_pk is None:
        return None

    game_date = _parse_date(game)
    if game_date is None:
        return None

    teams = game.get('teams') or {}
    home_team_id = _team_id(teams.get('home'))
    away_team_id = _team_id(teams.get('away'))
    if home_team_id is None and away_team_id is None:
        return None

    status = game.get('status') or {}
    status_code = _str_or_none(status.get('statusCode'))
    original_game_date = _parse_date_value(
        game.get('resumedFromDate')
        or game.get('originalGameDate')
        or game.get('originalDate')
    )
    resumed_game_date = _parse_date_value(
        game.get('rescheduleDate')
        or game.get('resumedDate')
        or game.get('resumedGameDate')
    )
    resumed_from_game_pk = _int(
        game.get('resumedFrom')
        or game.get('resumedFromGamePk')
        or game.get('resumedFromGamePK')
    )
    resumed_to_game_pk = _int(
        game.get('resumedTo')
        or game.get('resumedToGamePk')
        or game.get('resumedToGamePK')
        or game.get('rescheduledGamePk')
        or game.get('rescheduledGamePK')
    )

    return {
        'game_pk': game_pk,
        'game_date': game_date,
        'game_datetime': _parse_datetime(game.get('gameDate')),
        'game_type': _str_or_none(game.get('gameType')),
        'status_code': status_code,
        'status_state': _normalize_status_state(game),
        'doubleheader': _str_or_none(game.get('doubleHeader')),
        'game_number': _int(game.get('gameNumber')),
        'series_game_number': _int(game.get('seriesGameNumber')),
        'games_in_series': _int(game.get('gamesInSeries')),
        'original_game_date': original_game_date,
        'original_product_date': original_game_date,
        'resumed_game_date': resumed_game_date,
        'resumed_product_date': (
            resumed_game_date
            or (game_date if resumed_from_game_pk is not None else None)
        ),
        'resumed_from_game_pk': resumed_from_game_pk,
        'resumed_to_game_pk': resumed_to_game_pk,
        'home_team_id': home_team_id,
        'away_team_id': away_team_id,
    }


def _normalize_status_state(game_or_status):
    """Map MLB status into {scheduled, final, postponed, suspended, other}.

    Compatibility wrapper around the shared finality authority. Schedule
    ingestion stores display/status facts here; it does not create an
    independent finality authority.
    """
    return normalize_schedule_status_state(game_or_status)


# ── Upsert ────────────────────────────────────────────────────────────────────

def _upsert_row(team_id, opponent_team_id, home_away, parsed, source):
    """Insert or update one team's row for a game. Returns 'created' or 'updated'."""
    row = (
        ScheduledGame.query
        .filter_by(team_id=team_id, game_pk=parsed['game_pk'])
        .first()
    )
    created = row is None
    if created:
        row = ScheduledGame(team_id=team_id, game_pk=parsed['game_pk'])
        db.session.add(row)

    row.game_date = parsed['game_date']
    row.game_datetime = parsed['game_datetime']
    row.opponent_team_id = opponent_team_id
    row.home_away = home_away
    row.game_type = parsed['game_type']
    row.status_code = parsed['status_code']
    row.status_state = parsed['status_state']
    row.doubleheader = parsed['doubleheader']
    row.game_number = parsed['game_number']
    row.series_game_number = parsed['series_game_number']
    row.games_in_series = parsed['games_in_series']
    row.original_game_date = parsed['original_game_date']
    row.original_product_date = parsed['original_product_date']
    row.resumed_game_date = parsed['resumed_game_date']
    row.resumed_product_date = parsed['resumed_product_date']
    row.resumed_from_game_pk = parsed['resumed_from_game_pk']
    row.resumed_to_game_pk = parsed['resumed_to_game_pk']
    row.source = source
    return 'created' if created else 'updated'


# ── Small helpers ─────────────────────────────────────────────────────────────

def _team_id(side):
    if not isinstance(side, dict):
        return None
    return _int((side.get('team') or {}).get('id'))


def _parse_date(game):
    raw = (game or {}).get('officialDate') or str((game or {}).get('gameDate') or '')[:10]
    try:
        return date.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def _parse_date_value(raw):
    if raw is None:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except (TypeError, ValueError):
        return None


def _parse_datetime(raw):
    """Parse an ISO 8601 timestamp (often '...Z') into a naive UTC datetime."""
    if not raw:
        return None
    try:
        text = str(raw).strip()
        if text.endswith('Z'):
            text = text[:-1] + '+00:00'
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _str_or_none(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _iso(value):
    if value is None:
        return None
    isoformat = getattr(value, 'isoformat', None)
    if callable(isoformat) and not isinstance(value, str):
        return isoformat()
    return value
