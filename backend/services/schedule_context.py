"""Schedule Context V1 (pregame, per-team).

Answers one question, purely and deterministically:

    "Given team_id and reference_date, what is this team's schedule context
     entering that date?"

It reads only ``scheduled_games`` rows (Phase 1) and computes forward/backward
schedule pressure — games played recently, games ahead, the next off day, and how
many games stand before it. It stores nothing, predicts nothing, and touches no
product surface. Opponent identity is by team id; the opponent's NAME is resolved
through the same team-identity source the rest of the app uses, and is optional.

Reference date is supplied by the caller (a pregame/current-day concept). This
service is deliberately NOT tied to the completed-game default dates COIN uses.

Status semantics (conservative):
    final      -> a played/completed game (counts as "played")
    scheduled  -> a future/upcoming game (exists, not played)
    suspended  -> the game exists and consumes the date (counts as existence),
                  but is not "played" unless it is final
    postponed  -> not played; does NOT count as a game existing on the date
    other      -> counts only for game existence, never as "played"
So "a non-postponed game exists on a date" = any row whose status_state is not
``postponed``; "a played game" = a row whose status_state is ``final``.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from models.scheduled_game import ScheduledGame

logger = logging.getLogger(__name__)

# Query window around the reference date. "At least" 7 back / 14 ahead per the
# Phase 2 spec; a little extra lookback gives consecutive-played streaks room.
LOOKBACK_DAYS = 10
LOOKAHEAD_DAYS = 14

# Limitation strings.
LIMIT_NO_ROWS = 'no_schedule_rows'
LIMIT_DOUBLEHEADER = 'doubleheader_today'
LIMIT_MISSING_TIME = 'missing_game_time'
LIMIT_NO_OFF_DAY = 'next_off_day_not_found_within_window'


def build_team_schedule_context(team_id, reference_date, *, rows=None,
                                team_name_resolver=None):
    """Compute one team's schedule context entering ``reference_date``.

    ``reference_date`` is a ``date`` or ISO ``YYYY-MM-DD`` string. Pass ``rows``
    (an iterable of ScheduledGame-like objects) to compute purely without a
    database; otherwise rows are loaded from ``scheduled_games`` within the query
    window. ``team_name_resolver`` is an optional callable ``team_id -> name|None``
    for the opponent's display name (defaults to the app's team-identity lookup).
    Returns a plain dict. Deterministic.
    """
    ref = _as_date(reference_date)
    if ref is None:
        raise ValueError('reference_date must be a date or YYYY-MM-DD string')

    if rows is None:
        rows = _load_rows(team_id, ref)
    rows = [r for r in rows if r is not None]

    if not rows:
        return _empty_context(team_id, ref)

    resolver = team_name_resolver or _resolve_team_name
    by_date = _rows_by_date(rows)
    limitations: list[str] = []

    # ── Today ──────────────────────────────────────────────────────────────────
    today_live = _non_postponed_on(by_date, ref)
    is_playing_today = len(today_live) > 0
    games_today_count = len(today_live)

    opponent_today = opponent_id_today = home_away_today = game_time_today = None
    doubleheader_today = False
    if is_playing_today:
        doubleheader_today = (
            games_today_count > 1
            or any(_is_doubleheader_flag(r.doubleheader) for r in today_live)
        )
        lead = _earliest(today_live)
        opponent_id_today = lead.opponent_team_id
        opponent_today = resolver(lead.opponent_team_id) if lead.opponent_team_id is not None else None
        home_away_today = lead.home_away
        game_time_today = _format_time(lead.game_datetime)
        if doubleheader_today:
            limitations.append(LIMIT_DOUBLEHEADER)
        if game_time_today is None:
            limitations.append(LIMIT_MISSING_TIME)

    # ── Recent played (final only; exclude reference_date) ─────────────────────
    games_played_last_3_days = _count_final(by_date, ref - timedelta(days=3), ref - timedelta(days=1))
    games_played_last_5_days = _count_final(by_date, ref - timedelta(days=5), ref - timedelta(days=1))

    # ── Games ahead (non-postponed; include today through +2) ──────────────────
    games_in_next_3_days = _count_live(by_date, ref, ref + timedelta(days=2))

    # ── Next off day and games until it ────────────────────────────────────────
    next_off_day = _find_next_off_day(by_date, ref)
    if next_off_day is None:
        days_until_next_off_day = None
        games_until_next_off_day = None
        limitations.append(LIMIT_NO_OFF_DAY)
    else:
        days_until_next_off_day = (next_off_day - ref).days
        games_until_next_off_day = _count_live(by_date, ref, next_off_day - timedelta(days=1))

    # ── Off-day adjacency ──────────────────────────────────────────────────────
    is_first_game_after_off_day = is_playing_today and not _non_postponed_on(by_date, ref - timedelta(days=1))
    is_last_game_before_off_day = is_playing_today and not _non_postponed_on(by_date, ref + timedelta(days=1))

    # ── Consecutive streaks ────────────────────────────────────────────────────
    consecutive_games_played_entering_today = _consecutive_played_backward(by_date, ref)
    consecutive_games_scheduled_from_today = _consecutive_live_forward(by_date, ref)

    return {
        'team_id': team_id,
        'reference_date': ref.isoformat(),
        'context_available': True,
        'is_playing_today': is_playing_today,
        'opponent_today': opponent_today,
        'opponent_team_id_today': opponent_id_today,
        'home_away_today': home_away_today,
        'game_time_today': game_time_today,
        'doubleheader_today': doubleheader_today,
        'games_today_count': games_today_count,
        'games_played_last_3_days': games_played_last_3_days,
        'games_played_last_5_days': games_played_last_5_days,
        'games_in_next_3_days': games_in_next_3_days,
        'next_off_day': next_off_day.isoformat() if next_off_day else None,
        'days_until_next_off_day': days_until_next_off_day,
        'games_until_next_off_day': games_until_next_off_day,
        'is_first_game_after_off_day': bool(is_first_game_after_off_day),
        'is_last_game_before_off_day': bool(is_last_game_before_off_day),
        'consecutive_games_played_entering_today': consecutive_games_played_entering_today,
        'consecutive_games_scheduled_from_today': consecutive_games_scheduled_from_today,
        'limitations': limitations,
    }


def build_schedule_contexts_for_date(reference_date, *, rows=None,
                                     team_name_resolver=None):
    """Build one context per team that has schedule rows on/near ``reference_date``.

    Returns a list ordered by team_id (deterministic). Pass ``rows`` to compute
    purely; otherwise the window is loaded from the database.
    """
    ref = _as_date(reference_date)
    if ref is None:
        raise ValueError('reference_date must be a date or YYYY-MM-DD string')

    if rows is None:
        rows = _load_rows_all_teams(ref)
    rows = [r for r in rows if r is not None]

    by_team: dict[int, list] = {}
    for row in rows:
        by_team.setdefault(row.team_id, []).append(row)

    return [
        build_team_schedule_context(team_id, ref, rows=team_rows,
                                    team_name_resolver=team_name_resolver)
        for team_id, team_rows in sorted(by_team.items())
    ]


# ── Empty / fallback ──────────────────────────────────────────────────────────

def _empty_context(team_id, ref):
    """No schedule rows near the reference date — nothing safe to compute."""
    return {
        'team_id': team_id,
        'reference_date': ref.isoformat(),
        'context_available': False,
        'is_playing_today': False,
        'opponent_today': None,
        'opponent_team_id_today': None,
        'home_away_today': None,
        'game_time_today': None,
        'doubleheader_today': False,
        'games_today_count': 0,
        'games_played_last_3_days': 0,
        'games_played_last_5_days': 0,
        'games_in_next_3_days': 0,
        'next_off_day': None,
        'days_until_next_off_day': None,
        'games_until_next_off_day': None,
        'is_first_game_after_off_day': False,
        'is_last_game_before_off_day': False,
        'consecutive_games_played_entering_today': 0,
        'consecutive_games_scheduled_from_today': 0,
        'limitations': [LIMIT_NO_ROWS],
    }


# ── Date-bucketed computation helpers ─────────────────────────────────────────

def _rows_by_date(rows):
    by_date: dict[date, list] = {}
    for row in rows:
        if row.game_date is not None:
            by_date.setdefault(row.game_date, []).append(row)
    return by_date


def _non_postponed_on(by_date, day):
    return [r for r in by_date.get(day, ())
            if r.status_state != ScheduledGame.STATE_POSTPONED]


def _final_on(by_date, day):
    return [r for r in by_date.get(day, ())
            if r.status_state == ScheduledGame.STATE_FINAL]


def _count_final(by_date, start_day, end_day):
    """Final games over [start_day, end_day] inclusive (doubleheaders count 2)."""
    total = 0
    day = start_day
    while day <= end_day:
        total += len(_final_on(by_date, day))
        day += timedelta(days=1)
    return total


def _count_live(by_date, start_day, end_day):
    """Non-postponed games over [start_day, end_day] inclusive (doubleheaders 2)."""
    if end_day < start_day:
        return 0
    total = 0
    day = start_day
    while day <= end_day:
        total += len(_non_postponed_on(by_date, day))
        day += timedelta(days=1)
    return total


def _find_next_off_day(by_date, ref):
    """First date >= ref with no non-postponed game, within the lookahead window.

    If ``ref`` itself is already an off day, returns ``ref``. Returns ``None`` if
    every day in the window has a game (caller flags the limitation).
    """
    day = ref
    horizon = ref + timedelta(days=LOOKAHEAD_DAYS)
    while day <= horizon:
        if not _non_postponed_on(by_date, day):
            return day
        day += timedelta(days=1)
    return None


def _consecutive_played_backward(by_date, ref):
    """Consecutive prior dates (before ref) each with >=1 final game; sum games."""
    total = 0
    day = ref - timedelta(days=1)
    floor = ref - timedelta(days=LOOKBACK_DAYS)
    while day >= floor:
        finals = _final_on(by_date, day)
        if not finals:
            break
        total += len(finals)
        day -= timedelta(days=1)
    return total


def _consecutive_live_forward(by_date, ref):
    """Consecutive dates from ref forward each with >=1 non-postponed game; sum."""
    total = 0
    day = ref
    horizon = ref + timedelta(days=LOOKAHEAD_DAYS)
    while day <= horizon:
        live = _non_postponed_on(by_date, day)
        if not live:
            break
        total += len(live)
        day += timedelta(days=1)
    return total


def _earliest(games):
    """Earliest game by start time (missing times sort last), then game_pk."""
    return sorted(
        games,
        key=lambda r: (r.game_datetime is None, r.game_datetime or _MAX_DT, r.game_pk or 0),
    )[0]


# ── Small helpers ─────────────────────────────────────────────────────────────

_MAX_DT = datetime.max


def _is_doubleheader_flag(value):
    return value not in (None, '', 'N')


def _format_time(value):
    if value is None:
        return None
    # Stored as naive UTC; emit an explicit-UTC ISO string.
    return value.isoformat() + 'Z'


def _as_date(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


# ── Database access (only used when rows are not injected) ────────────────────

def _load_rows(team_id, ref):
    start = ref - timedelta(days=LOOKBACK_DAYS)
    end = ref + timedelta(days=LOOKAHEAD_DAYS)
    return (
        ScheduledGame.query
        .filter(ScheduledGame.team_id == team_id)
        .filter(ScheduledGame.game_date >= start)
        .filter(ScheduledGame.game_date <= end)
        .all()
    )


def _load_rows_all_teams(ref):
    start = ref - timedelta(days=LOOKBACK_DAYS)
    end = ref + timedelta(days=LOOKAHEAD_DAYS)
    return (
        ScheduledGame.query
        .filter(ScheduledGame.game_date >= start)
        .filter(ScheduledGame.game_date <= end)
        .all()
    )


def _resolve_team_name(team_id):
    """Opponent display name via the app's existing team-identity source.

    Best-effort and optional: returns ``None`` if unavailable (e.g. no roster
    rows for the team, or called outside an app context).
    """
    if team_id is None:
        return None
    try:
        from utils.db import db
        from models.pitcher import Pitcher

        row = (
            db.session.query(Pitcher.team_name)
            .filter(Pitcher.team_id == team_id)
            .filter(Pitcher.team_name.isnot(None))
            .first()
        )
        return row.team_name if row is not None else None
    except Exception:  # noqa: BLE001 — name is cosmetic; never fail context on it
        return None
