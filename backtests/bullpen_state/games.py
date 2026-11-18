"""Parse cached schedules and boxscores into games and pitching appearances.

Everything here is source parsing. No engine logic, no outcome derivation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from . import mlb_client


@dataclass(frozen=True)
class Game:
    game_pk: int
    season: int
    game_date: date            # MLB officialDate
    start_utc: Optional[str]   # scheduled first pitch (ISO, UTC)
    home_id: int
    away_id: int
    home_abbr: str
    away_abbr: str
    venue_id: Optional[int]
    venue_name: Optional[str]
    double_header: str         # 'N', 'Y' (traditional), 'S' (split)
    game_number: int           # 1 or 2 within a doubleheader
    scheduled_innings: int
    home_runs: Optional[int]
    away_runs: Optional[int]
    innings: tuple = field(default_factory=tuple)  # ((num, away_runs, home_runs), ...)
    resumed: bool = False


@dataclass(frozen=True)
class Appearance:
    """One pitcher's line in one game, shaped like a production GameLog."""
    pitcher_mlb_id: int
    pitcher_name: str
    team_id: int
    game_pk: int
    game_date: date
    game_number: int
    order: int                       # position in the team's pitcher list (0 = starter)
    games_started: Optional[int]
    innings_pitched_outs: int
    innings_pitched: float
    pitches_thrown: Optional[int]
    runs_allowed: int
    earned_runs: int
    save: bool
    hold: bool
    save_situation: bool
    blown_save: bool
    inherited_runners: Optional[int]
    inherited_runners_scored: Optional[int]
    position: str


def _is_final(g) -> bool:
    status = g.get('status') or {}
    return (
        status.get('abstractGameState') == 'Final'
        and status.get('detailedState') not in {'Postponed', 'Cancelled', 'Suspended'}
        and status.get('codedGameState') not in {'D', 'C', 'T', 'U'}
    )


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def load_games(season: int, offline: bool = False) -> list[Game]:
    data = mlb_client.schedule(season, offline=offline)
    by_pk: dict[int, Game] = {}
    for day in data.get('dates') or []:
        for g in day.get('games') or []:
            if g.get('gameType') != 'R' or not _is_final(g):
                continue
            teams = g['teams']
            ls = g.get('linescore') or {}
            innings = tuple(
                (
                    inn.get('num'),
                    _int((inn.get('away') or {}).get('runs')),
                    _int((inn.get('home') or {}).get('runs')),
                )
                for inn in ls.get('innings') or []
            )
            venue = g.get('venue') or {}
            game = Game(
                game_pk=int(g['gamePk']),
                season=season,
                game_date=date.fromisoformat(g['officialDate']),
                start_utc=g.get('gameDate'),
                home_id=int(teams['home']['team']['id']),
                away_id=int(teams['away']['team']['id']),
                home_abbr=teams['home']['team'].get('abbreviation') or teams['home']['team'].get('name', ''),
                away_abbr=teams['away']['team'].get('abbreviation') or teams['away']['team'].get('name', ''),
                venue_id=_int(venue.get('id')),
                venue_name=venue.get('name'),
                double_header=g.get('doubleHeader') or 'N',
                game_number=int(g.get('gameNumber') or 1),
                scheduled_innings=int(g.get('scheduledInnings') or 9),
                home_runs=_int(teams['home'].get('score')),
                away_runs=_int(teams['away'].get('score')),
                innings=innings,
                resumed=bool(g.get('resumedFrom') or g.get('resumeDate') or g.get('resumedFromDate')),
            )
            # A game listed twice (suspended/resumed) keeps its last Final entry.
            by_pk[game.game_pk] = game
    return sorted(by_pk.values(), key=lambda x: (x.game_date, x.start_utc or '', x.game_pk))


def parse_boxscore(game: Game, box: dict) -> list[Appearance]:
    out: list[Appearance] = []
    for side in ('home', 'away'):
        team = box['teams'][side]
        team_id = int(team['team']['id'])
        players = team.get('players') or {}
        for order, pid in enumerate(team.get('pitchers') or []):
            p = players.get(f'ID{pid}') or {}
            st = (p.get('stats') or {}).get('pitching') or {}
            if not st:
                continue
            outs = _int(st.get('outs')) or 0
            pitches = _int(st.get('numberOfPitches'))
            if pitches is None:
                pitches = _int(st.get('pitchesThrown'))
            out.append(Appearance(
                pitcher_mlb_id=int(pid),
                pitcher_name=(p.get('person') or {}).get('fullName', ''),
                team_id=team_id,
                game_pk=game.game_pk,
                game_date=game.game_date,
                game_number=game.game_number,
                order=order,
                games_started=_int(st.get('gamesStarted')),
                innings_pitched_outs=outs,
                innings_pitched=outs / 3.0,
                pitches_thrown=pitches,
                runs_allowed=_int(st.get('runs')) or 0,
                earned_runs=_int(st.get('earnedRuns')) or 0,
                save=bool(_int(st.get('saves'))),
                hold=bool(_int(st.get('holds'))),
                save_situation=bool(_int(st.get('saveOpportunities'))),
                blown_save=bool(_int(st.get('blownSaves'))),
                inherited_runners=_int(st.get('inheritedRunners')),
                inherited_runners_scored=_int(st.get('inheritedRunnersScored')),
                # Boxscore 'position' is the position held at game end, so a position
                # player who finishes on the mound reads 'P'. The first entry of
                # allPositions is the position he entered the game at.
                position=(
                    ((p.get('allPositions') or [{}])[0].get('abbreviation'))
                    or (p.get('position') or {}).get('abbreviation') or ''
                ),
            ))
    return out
