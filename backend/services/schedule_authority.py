"""Game-centric schedule authority and fail-closed postability contract."""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from models.slate_game import SlateGame
from utils.db import db
from utils.time import utc_now_naive


EASTERN = ZoneInfo('America/New_York')
DEFAULT_FRESHNESS_MAX_AGE_HOURS = 24
ROLLING_WINDOW_BACK_DAYS = 1
ROLLING_WINDOW_FORWARD_DAYS = 3


def normalize_slate_state(status):
    """Normalize MLB status into BaseballOS-owned postability states."""
    status = status if isinstance(status, dict) else {}
    code = str(status.get('statusCode') or '').strip().upper()
    detailed = str(status.get('detailedState') or '').strip().lower()
    abstract = str(status.get('abstractGameState') or '').strip().lower()

    if 'postpon' in detailed or 'cancel' in detailed or code in {'C', 'DR'}:
        return SlateGame.STATE_CANCELLED
    if 'suspend' in detailed or 'delay' in detailed:
        return SlateGame.STATE_UNCERTAIN
    if (
        code in {'F', 'O', 'FR', 'FT'}
        or detailed in {'final', 'game over', 'completed early', 'final: tied'}
        or detailed.startswith('final')
    ):
        return SlateGame.STATE_COMPLETED
    if (
        code == 'I'
        or abstract == 'live'
        or 'progress' in detailed
        or detailed == 'live'
    ):
        return SlateGame.STATE_LIVE
    if (
        code in {'S', 'P', 'PW', 'PR'}
        or abstract == 'preview'
        or detailed in {'scheduled', 'pre-game', 'warmup'}
    ):
        return SlateGame.STATE_UPCOMING
    return SlateGame.STATE_UNCERTAIN


def slate_fields_from_game(game, *, synced_at=None):
    """Parse the fields needed for one ``slate_games`` row."""
    if not isinstance(game, dict):
        return None
    game_pk = _positive_int(game.get('gamePk'))
    game_time_utc = _parse_utc_datetime(game.get('gameDate'))
    teams = game.get('teams') or {}
    home_team_id = _team_id(teams.get('home'))
    away_team_id = _team_id(teams.get('away'))
    if None in {game_pk, game_time_utc, home_team_id, away_team_id}:
        return None

    status = game.get('status') or {}
    return {
        'game_pk': game_pk,
        'game_date_et': game_time_utc.replace(
            tzinfo=timezone.utc
        ).astimezone(EASTERN).date(),
        'game_time_utc': game_time_utc,
        'home_team_id': home_team_id,
        'away_team_id': away_team_id,
        'status_abstract': _text(status.get('abstractGameState')),
        'status_detailed': _text(status.get('detailedState')),
        'status_code': _text(status.get('statusCode')),
        'normalized_state': normalize_slate_state(status),
        'doubleheader_flag': _text(game.get('doubleHeader')),
        'game_number': _int(game.get('gameNumber')),
        'scheduled_innings': _int(game.get('scheduledInnings')),
        'last_synced': synced_at or utc_now_naive(),
    }


def upsert_slate_game(game, *, synced_at=None):
    """Full-upsert one MLB game by ``game_pk``; return created/updated/skipped."""
    fields = slate_fields_from_game(game, synced_at=synced_at)
    if fields is None:
        return 'skipped'
    row = db.session.get(SlateGame, fields['game_pk'])
    created = row is None
    if created:
        row = SlateGame(game_pk=fields['game_pk'])
        db.session.add(row)
    for column in SlateGame.MUTABLE_COLUMNS:
        setattr(row, column, fields[column])
    return 'created' if created else 'updated'


def rolling_window(reference_date=None):
    ref = reference_date or datetime.now(EASTERN).date()
    if isinstance(ref, str):
        ref = date.fromisoformat(ref)
    return (
        ref - timedelta(days=ROLLING_WINDOW_BACK_DAYS),
        ref + timedelta(days=ROLLING_WINDOW_FORWARD_DAYS),
    )


def ingest_rolling_window(reference_date=None, *, source='slate_schedule_refresh'):
    """Fetch yesterday through +3 days and fully upsert both schedule ledgers."""
    from services.schedule_ingestion import ingest_schedule

    start_date, end_date = rolling_window(reference_date)
    summary = ingest_schedule(start_date, end_date, source=source)
    return {
        'status': 'ok' if int(summary.get('errors') or 0) == 0 else 'partial',
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'summary': summary,
    }


def schedule_freshness(*, as_of=None, max_age_hours=None):
    """Describe freshness without treating absent or old schedule data as usable."""
    now = _naive_utc(as_of) if as_of is not None else utc_now_naive()
    latest = db.session.query(db.func.max(SlateGame.last_synced)).scalar()
    max_age = timedelta(hours=_freshness_max_age_hours(max_age_hours))
    age_seconds = None if latest is None else max((now - latest).total_seconds(), 0)
    state = 'unavailable'
    if latest is not None:
        state = 'fresh' if now - latest <= max_age else 'stale'
    return {
        'state': state,
        'is_fresh': state == 'fresh',
        'schedule_data_through': _iso_utc(latest),
        'age_seconds': round(age_seconds) if age_seconds is not None else None,
        'max_age_seconds': round(max_age.total_seconds()),
    }


def build_postability_schedule_contract(slate_date=None, *, as_of=None, max_age_hours=None):
    """Return game-time-aware, split-doubleheader-safe team postability."""
    ref = slate_date or datetime.now(EASTERN).date()
    if isinstance(ref, str):
        ref = date.fromisoformat(ref)
    now = _naive_utc(as_of) if as_of is not None else utc_now_naive()
    freshness = schedule_freshness(as_of=now, max_age_hours=max_age_hours)
    rows = (
        SlateGame.query
        .filter(SlateGame.game_date_et == ref)
        .order_by(SlateGame.game_time_utc.asc(), SlateGame.game_pk.asc())
        .all()
    )
    games = [row.to_dict() for row in rows]
    team_rows = {}
    for row in rows:
        team_rows.setdefault(row.home_team_id, []).append(row)
        team_rows.setdefault(row.away_team_id, []).append(row)

    teams = {
        str(team_id): _team_postability(team_games, freshness, now)
        for team_id, team_games in sorted(team_rows.items())
    }
    return {
        'slate_date_et': ref.isoformat(),
        'freshness': freshness,
        'games': games,
        'teams': teams,
    }


def _team_postability(rows, freshness, as_of):
    states = [
        (
            SlateGame.STATE_UNCERTAIN
            if row.normalized_state == SlateGame.STATE_UPCOMING
            and row.game_time_utc <= as_of
            else row.normalized_state
        )
        for row in rows
    ]
    has_past_due_preview = any(
        row.normalized_state == SlateGame.STATE_UPCOMING
        and row.game_time_utc <= as_of
        for row in rows
    )
    if not freshness['is_fresh']:
        state = SlateGame.STATE_UNCERTAIN
        postable = False
        reason = f"schedule_{freshness['state']}"
    elif SlateGame.STATE_UPCOMING in states:
        state = SlateGame.STATE_UPCOMING
        postable = True
        reason = 'upcoming_game_available'
    elif SlateGame.STATE_LIVE in states:
        state = SlateGame.STATE_LIVE
        postable = False
        reason = 'game_already_live'
    elif SlateGame.STATE_UNCERTAIN in states:
        state = SlateGame.STATE_UNCERTAIN
        postable = False
        reason = (
            'scheduled_start_passed_without_status_update'
            if has_past_due_preview
            else 'schedule_status_uncertain'
        )
    elif SlateGame.STATE_COMPLETED in states:
        state = SlateGame.STATE_COMPLETED
        postable = False
        reason = 'slate_moment_completed'
    else:
        state = SlateGame.STATE_CANCELLED
        postable = False
        reason = 'slate_cancelled'
    return {
        'postable': postable,
        'state': state,
        'reason': reason,
        'doubleheader': len(rows) > 1,
        'games': [row.to_dict() for row in rows],
    }


def _freshness_max_age_hours(override):
    if override is not None:
        return max(float(override), 0)
    raw = os.environ.get('SLATE_SCHEDULE_FRESHNESS_HOURS')
    try:
        return max(float(raw), 0) if raw is not None else DEFAULT_FRESHNESS_MAX_AGE_HOURS
    except (TypeError, ValueError):
        return DEFAULT_FRESHNESS_MAX_AGE_HOURS


def _parse_utc_datetime(raw):
    if not raw:
        return None
    try:
        text = str(raw).strip()
        if text.endswith('Z'):
            text = text[:-1] + '+00:00'
        parsed = datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _naive_utc(value):
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _iso_utc(value):
    return value.isoformat() + 'Z' if value is not None else None


def _team_id(side):
    return _positive_int(((side or {}).get('team') or {}).get('id'))


def _positive_int(value):
    parsed = _int(value)
    return parsed if parsed is not None and parsed > 0 else None


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value):
    if value is None:
        return None
    text = str(value).strip()
    return text or None
