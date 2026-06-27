"""Normalize raw MLB game data into the Completed Game Context payload.

The extraction service (``completed_game_context_service``) consumes a small,
normalized payload — it deliberately knows nothing about MLB's nested JSON. This
adapter is the seam between the two: it takes the raw schedule game, boxscore,
linescore, and play-by-play responses and produces that normalized payload,
discarding everything not needed for derived context. Nothing here is persisted,
and no raw play-by-play leaves this module.

It is deterministic and fail-closed. When play-by-play is ambiguous (missing
score/inning fields, or non-monotonic cumulative scores) it drops the plays
entirely so the downstream service degrades to MEDIUM (linescore) or LOW
(boxscore) rather than inventing a running score.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from utils.games_started import parse_games_started
from utils.innings import InvalidInningsNotation, parse_mlb_innings_to_outs


HALF_TOP = 'top'
HALF_BOTTOM = 'bottom'


def _team_block(game: dict, side: str) -> dict:
    return (((game or {}).get('teams') or {}).get(side) or {})


def _team_info(game: dict, side: str) -> dict:
    return _team_block(game, side).get('team') or {}


def _int_or_none(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _runs(block: Any, default=None):
    """Pull a 'runs' count from an MLB linescore half/team block."""
    if not isinstance(block, dict):
        return default
    value = _int_or_none(block.get('runs'))
    return value if value is not None else default


def _game_date(game: dict, fallback) -> Any:
    if isinstance(fallback, date):
        return fallback
    raw = (game or {}).get('officialDate') or str((game or {}).get('gameDate') or '')[:10]
    try:
        return date.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def _normalize_pitching_lines(boxscore: dict, side: str) -> list[dict]:
    """One normalized pitching line per pitcher who threw, in usage order."""
    team_data = ((boxscore or {}).get('teams') or {}).get(side) or {}
    order = [pid for pid in (team_data.get('pitchers') or [])]
    players = team_data.get('players') or {}

    lines = []
    for index, pitcher_id in enumerate(order):
        player = players.get(f'ID{pitcher_id}') or {}
        stats = ((player.get('stats') or {}).get('pitching') or {})
        if not stats:
            continue

        games_started = parse_games_started(stats.get('gamesStarted'))
        if games_started is None:
            # MLB omitted gamesStarted: the first pitcher used is the starter.
            # Mirrors the fallback used when ingesting boxscore game logs.
            games_started = 1 if index == 0 else 0

        try:
            outs = parse_mlb_innings_to_outs(stats.get('inningsPitched', '0.0'))
        except InvalidInningsNotation:
            outs = None

        lines.append({
            'player_id': pitcher_id,
            'name': (player.get('person') or {}).get('fullName'),
            'games_started': games_started,
            'innings_pitched_outs': outs,
            'pitches_thrown': _int_or_none(stats.get('numberOfPitches')),
        })
    return lines


def _normalize_linescore(linescore: dict, game: dict) -> dict | None:
    """Flatten MLB's linescore into {innings:[{num,home,away}], home_runs, away_runs}.

    Returns None when there is no real inning detail, so a final-score-only
    schedule entry never masquerades as MEDIUM context.
    """
    if not isinstance(linescore, dict):
        return None
    innings_raw = linescore.get('innings')
    if not isinstance(innings_raw, list) or not innings_raw:
        return None

    innings = []
    for inning in innings_raw:
        if not isinstance(inning, dict):
            continue
        innings.append({
            'num': _int_or_none(inning.get('num')),
            'home': _runs(inning.get('home'), default=0),
            'away': _runs(inning.get('away'), default=0),
        })
    if not innings:
        return None

    teams = linescore.get('teams') or {}
    home_total = _runs(teams.get('home'))
    away_total = _runs(teams.get('away'))
    # Backfill from the schedule's final score only — never invent innings.
    if home_total is None:
        home_total = _int_or_none(_team_block(game, 'home').get('score'))
    if away_total is None:
        away_total = _int_or_none(_team_block(game, 'away').get('score'))

    out = {'innings': innings}
    if home_total is not None:
        out['home_runs'] = home_total
    if away_total is not None:
        out['away_runs'] = away_total
    return out


def _normalize_play_by_play(play_by_play: dict) -> list[dict] | None:
    """Normalize allPlays into ordered {inning, half, away_score, home_score, pitcher_id}.

    Fail-closed: any missing inning/half/score or a non-monotonic cumulative
    score drops the whole play log (returns None), so the service falls back to
    linescore/boxscore rather than trusting an ambiguous feed.
    """
    if not isinstance(play_by_play, dict):
        return None
    all_plays = play_by_play.get('allPlays')
    if not isinstance(all_plays, list) or not all_plays:
        return None

    plays = []
    prev_total = -1
    for play in all_plays:
        if not isinstance(play, dict):
            return None
        about = play.get('about') or {}
        result = play.get('result') or {}
        # MLB marks unfinished plays mid-feed; skip them rather than fail.
        if about.get('isComplete') is False:
            continue

        inning = _int_or_none(about.get('inning'))
        half = about.get('halfInning')
        away_score = _int_or_none(result.get('awayScore'))
        home_score = _int_or_none(result.get('homeScore'))
        if inning is None or half not in (HALF_TOP, HALF_BOTTOM) \
                or away_score is None or home_score is None:
            return None

        total = away_score + home_score
        if total < prev_total:
            return None
        prev_total = total

        plays.append({
            'inning': inning,
            'half': half,
            'away_score': away_score,
            'home_score': home_score,
            'pitcher_id': _int_or_none(((play.get('matchup') or {}).get('pitcher') or {}).get('id')),
        })

    return plays or None


def build_completed_game_payload(
    game: dict,
    *,
    boxscore: dict | None = None,
    linescore: dict | None = None,
    play_by_play: dict | None = None,
    game_date=None,
) -> dict | None:
    """Build the normalized completed-game payload from raw MLB responses.

    ``game`` is the schedule entry (gamePk, teams, scores). ``boxscore``,
    ``linescore`` and ``play_by_play`` are the raw endpoint responses; pass only
    what is available. Returns None when the game identity is missing.
    """
    if not isinstance(game, dict):
        return None
    game_pk = _int_or_none(game.get('gamePk'))
    if game_pk is None:
        return None

    home_info = _team_info(game, 'home')
    away_info = _team_info(game, 'away')

    payload = {
        'game_pk': game_pk,
        'game_date': _game_date(game, game_date),
        'game_type': game.get('gameType'),
        'home': {
            'team_id': _int_or_none(home_info.get('id')),
            'team_name': home_info.get('name'),
            'pitchers': _normalize_pitching_lines(boxscore, 'home'),
        },
        'away': {
            'team_id': _int_or_none(away_info.get('id')),
            'team_name': away_info.get('name'),
            'pitchers': _normalize_pitching_lines(boxscore, 'away'),
        },
    }

    normalized_linescore = _normalize_linescore(linescore, game)
    if normalized_linescore is not None:
        payload['linescore'] = normalized_linescore

    normalized_plays = _normalize_play_by_play(play_by_play)
    if normalized_plays is not None:
        payload['plays'] = normalized_plays

    return payload
