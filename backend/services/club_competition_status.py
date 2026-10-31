"""Whether a club is still in active competition (WP-0.1, EOS-002).

A current Team State is a pregame operating read. It is only meaningful for a
club that is still playing. Before this module nothing in the publication path
knew that a club's season had ended, so an eliminated club kept receiving a
"current" read dated with the league's data-through date for weeks.

This module answers one narrow question from stored authority only:

* the ``scheduled_games`` schedule authority (refreshed for yesterday through
  ``schedule_authority.ROLLING_WINDOW_FORWARD_DAYS`` before every Daily and
  Postgame candidate, with postseason "if necessary" games retired by
  ``schedule_absence`` when MLB stops listing them), and
* official pitching decisions on canonical ``game_logs`` rows (the ``win``
  flag from the MLB boxscore), used only to read whether a postseason series
  reached its clinching win count.

Outcomes:

``active``
    An upcoming competitive game is scheduled for the club, a postseason series
    has been won and the next round is not yet listed, or the regular season is
    still in progress (the club's last game was a regular-season game and the
    stored schedule still lists a regular-season game on or after the
    reference date). No activity-window threshold is used.
``season_complete``
    The club lost a postseason series, the World Series has been decided, or
    the postseason is past its first round (a Division Series or later game is
    final) and the club appears nowhere in the postseason schedule.
``undetermined``
    The stored evidence cannot establish either. This never becomes a
    definitive claim in either direction; the caller withholds the current
    read. Example: after the regular season and before any Division Series
    game is final, a club absent from the stored postseason rows may be a
    first-round bye club whose games are outside the rolling schedule window,
    so it is unconfirmed rather than complete.

Every evaluation is as of its reference date: games dated on or after the
reference date count as still to be played, and only decisions in games dated
before it are read. A historical read is therefore classified with what was
knowable when it was published, not with later results.

Spring training and exhibition games are not competition for this purpose. A
game whose type is unknown is ignored rather than assumed regular season.

This is deliberately narrower than the full season-phase model (roadmap
WP-1.1): it does not name a champion, describe the offseason, or open spring
training. It only stops a club that is no longer playing from being presented
as having a current pregame bullpen state.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterable, Mapping, Optional

from services.schedule_absence import (
    POSTSEASON_GAME_TYPES,
    SERIES_LENGTHS,
    is_unplayed_terminal_schedule_row,
)


CONTRACT = 'club_competition_status_v1'

STATUS_ACTIVE = 'active'
STATUS_SEASON_COMPLETE = 'season_complete'
STATUS_UNDETERMINED = 'undetermined'
STATUSES = frozenset({STATUS_ACTIVE, STATUS_SEASON_COMPLETE, STATUS_UNDETERMINED})

BASIS_UPCOMING_GAME = 'upcoming_scheduled_game'
BASIS_AWAITING_NEXT_ROUND = 'postseason_series_won_next_round_not_listed'
BASIS_REGULAR_SEASON_IN_PROGRESS = 'regular_season_in_progress'
BASIS_ELIMINATED = 'postseason_series_lost'
BASIS_POSTSEASON_COMPLETE = 'world_series_decided'
BASIS_NOT_IN_POSTSEASON = 'postseason_scheduled_without_club'
BASIS_NO_SCHEDULE_EVIDENCE = 'no_competitive_schedule_evidence'
BASIS_UNRESOLVED = 'competition_status_unresolved'
BASIS_LOOKUP_FAILED = 'competition_status_lookup_failed'

REGULAR_SEASON_GAME_TYPE = 'R'
COMPETITIVE_GAME_TYPES = frozenset({REGULAR_SEASON_GAME_TYPE}) | POSTSEASON_GAME_TYPES
POSTSEASON_ROUND_ORDER = {'F': 1, 'D': 2, 'L': 3, 'W': 4}
# A final game from this round on means the first round is over, so every club
# still playing appears in the postseason schedule.
PAST_FIRST_ROUND_GAME_TYPES = frozenset({'D', 'L', 'W'})
WORLD_SERIES_GAME_TYPE = 'W'

FINAL_STATE = 'final'
# Rows fetched to prove the league still has regular-season games ahead. Any
# one pending row is enough; a few guard against a cancelled first row.
LEAGUE_REGULAR_SEASON_PROBE_ROWS = 32


@dataclass(frozen=True)
class ClubCompetitionStatus:
    team_id: int
    status: str
    basis: str
    reference_date: Optional[date]
    last_final_game_date: Optional[date] = None
    last_final_game_type: Optional[str] = None
    next_scheduled_game_date: Optional[date] = None

    @property
    def is_active(self) -> bool:
        return self.status == STATUS_ACTIVE

    def to_dict(self) -> dict:
        return {
            'contract': CONTRACT,
            'team_id': int(self.team_id),
            'status': self.status,
            'basis': self.basis,
            'reference_date': _iso(self.reference_date),
            'last_final_game_date': _iso(self.last_final_game_date),
            'last_final_game_type': self.last_final_game_type,
            'next_scheduled_game_date': _iso(self.next_scheduled_game_date),
        }


def _iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def _value(row, name):
    if isinstance(row, Mapping):
        return row.get(name)
    return getattr(row, name, None)


def _int_or_none(value):
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _is_final(row, reference_date) -> bool:
    """Final and dated before the reference date (known when the read ran)."""
    return (
        _value(row, 'status_state') == FINAL_STATE
        and _value(row, 'game_date') < reference_date
    )


def _is_pending(row, reference_date) -> bool:
    """A game still to be played as of the reference date.

    A game dated on or after the reference date counts as pending even if it
    is final now. A game MLB has cancelled or retired stays not pending.
    """
    if _value(row, 'game_date') < reference_date:
        return False
    if _value(row, 'status_state') == FINAL_STATE:
        return True
    return not is_unplayed_terminal_schedule_row(
        _value(row, 'status_state'), _value(row, 'status_code'),
    )


def _competitive_rows(rows, season):
    selected = []
    for row in rows or ():
        game_date = _value(row, 'game_date')
        if not isinstance(game_date, date) or game_date.year != season:
            continue
        if _value(row, 'game_type') not in COMPETITIVE_GAME_TYPES:
            continue
        selected.append(row)
    return selected


def _series_outcomes(club_id, club_post_rows, winner_by_game, reference_date):
    """Per postseason series: (round, club_clinched, opponent_clinched).

    A series is identified by its round (game type) and opponent. It is decided
    only when one side's official wins reach the clinching count for MLB's
    published ``games_in_series``. Missing decisions never decide a series.
    """
    by_series = defaultdict(list)
    for row in club_post_rows:
        opponent = _int_or_none(_value(row, 'opponent_team_id'))
        if opponent is None:
            continue
        by_series[(_value(row, 'game_type'), opponent)].append(row)

    outcomes = []
    for (game_type, opponent), rows in by_series.items():
        lengths = {
            _int_or_none(_value(row, 'games_in_series')) for row in rows
        } - {None}
        length = max(lengths) if lengths else None
        if length not in SERIES_LENGTHS:
            outcomes.append((POSTSEASON_ROUND_ORDER[game_type], False, False))
            continue
        clinch = length // 2 + 1
        game_pks = {
            _int_or_none(_value(row, 'game_pk')) for row in rows
            if _is_final(row, reference_date)
        } - {None}
        club_wins = sum(1 for pk in game_pks if winner_by_game.get(pk) == club_id)
        opponent_wins = sum(1 for pk in game_pks if winner_by_game.get(pk) == opponent)
        outcomes.append((
            POSTSEASON_ROUND_ORDER[game_type],
            club_wins >= clinch,
            opponent_wins >= clinch,
        ))
    return outcomes


def _world_series_decided(league_post_rows, winner_by_game, reference_date) -> bool:
    world_series_rows = defaultdict(list)
    for row in league_post_rows:
        if _value(row, 'game_type') != WORLD_SERIES_GAME_TYPE:
            continue
        team_id = _int_or_none(_value(row, 'team_id'))
        if team_id is None:
            continue
        world_series_rows[team_id].append(row)
    for team_id, rows in world_series_rows.items():
        for _round, club_clinched, opponent_clinched in _series_outcomes(
            team_id, rows, winner_by_game, reference_date,
        ):
            if club_clinched or opponent_clinched:
                return True
    return False


def classify_club_competition_status(
    team_id,
    reference_date,
    *,
    schedule_rows: Iterable[Any],
    winner_by_game: Mapping[int, int],
) -> ClubCompetitionStatus:
    """Classify one club from stored schedule rows and official decisions.

    ``schedule_rows`` are ScheduledGame-like rows (``team_id``, ``game_pk``,
    ``game_date``, ``game_type``, ``status_state``, ``status_code``,
    ``opponent_team_id``, ``games_in_series``) for the reference date's season:
    every row of this club, the league's postseason rows, and the league's
    regular-season rows dated on or after the reference date. Pure function.
    """
    team_id = int(team_id)
    if not isinstance(reference_date, date):
        return ClubCompetitionStatus(
            team_id, STATUS_UNDETERMINED, BASIS_NO_SCHEDULE_EVIDENCE, None,
        )
    season = reference_date.year
    rows = _competitive_rows(schedule_rows, season)
    club_rows = [row for row in rows if _int_or_none(_value(row, 'team_id')) == team_id]
    league_post_rows = [row for row in rows if _value(row, 'game_type') in POSTSEASON_GAME_TYPES]
    club_post_rows = [row for row in club_rows if _value(row, 'game_type') in POSTSEASON_GAME_TYPES]

    finals = [row for row in club_rows if _is_final(row, reference_date)]
    last_final = max(finals, key=lambda row: _value(row, 'game_date'), default=None)
    last_final_date = _value(last_final, 'game_date') if last_final is not None else None
    last_final_type = _value(last_final, 'game_type') if last_final is not None else None
    upcoming = [
        _value(row, 'game_date') for row in club_rows
        if _is_pending(row, reference_date)
    ]
    next_date = min(upcoming) if upcoming else None

    def result(status, basis):
        return ClubCompetitionStatus(
            team_id, status, basis, reference_date,
            last_final_game_date=last_final_date,
            last_final_game_type=last_final_type,
            next_scheduled_game_date=next_date,
        )

    if not club_rows:
        return result(STATUS_UNDETERMINED, BASIS_NO_SCHEDULE_EVIDENCE)

    if _world_series_decided(league_post_rows, winner_by_game, reference_date):
        return result(STATUS_SEASON_COMPLETE, BASIS_POSTSEASON_COMPLETE)

    if club_post_rows:
        outcomes = _series_outcomes(
            team_id, club_post_rows, winner_by_game, reference_date,
        )
        if any(opponent_clinched for _round, _won, opponent_clinched in outcomes):
            return result(STATUS_SEASON_COMPLETE, BASIS_ELIMINATED)
        if next_date is not None:
            return result(STATUS_ACTIVE, BASIS_UPCOMING_GAME)
        latest_round = max((round_ for round_, _w, _l in outcomes), default=None)
        if latest_round is not None and any(
            won for round_, won, _lost in outcomes if round_ == latest_round
        ):
            return result(STATUS_ACTIVE, BASIS_AWAITING_NEXT_ROUND)
        return result(STATUS_UNDETERMINED, BASIS_UNRESOLVED)

    if next_date is not None:
        return result(STATUS_ACTIVE, BASIS_UPCOMING_GAME)
    if any(
        _value(row, 'game_type') in PAST_FIRST_ROUND_GAME_TYPES
        and _is_final(row, reference_date)
        for row in league_post_rows
    ):
        # Every club still playing is in the postseason schedule by now.
        return result(STATUS_SEASON_COMPLETE, BASIS_NOT_IN_POSTSEASON)
    if not league_post_rows and last_final_type == REGULAR_SEASON_GAME_TYPE and any(
        _value(row, 'game_type') == REGULAR_SEASON_GAME_TYPE
        and _is_pending(row, reference_date)
        for row in rows
    ):
        return result(STATUS_ACTIVE, BASIS_REGULAR_SEASON_IN_PROGRESS)
    return result(STATUS_UNDETERMINED, BASIS_UNRESOLVED)


def lookup_failed_status(team_id, reference_date) -> ClubCompetitionStatus:
    """The fail-closed status when stored authority could not be read."""
    return ClubCompetitionStatus(
        int(team_id), STATUS_UNDETERMINED, BASIS_LOOKUP_FAILED, reference_date,
    )


def load_competition_inputs(team_id, reference_date, *, session=None):
    """Read this club's season schedule, league postseason rows, and decisions.

    Read-only and bounded: one club's season of rows, the league's postseason
    rows, and the winning-pitcher rows of final postseason games.
    """
    from sqlalchemy import or_

    from models.game_log import GameLog
    from models.scheduled_game import ScheduledGame
    from utils.db import db

    session = session or db.session
    season_start = date(reference_date.year, 1, 1)
    season_end = date(reference_date.year, 12, 31)
    columns = (
        ScheduledGame.team_id,
        ScheduledGame.game_pk,
        ScheduledGame.game_date,
        ScheduledGame.game_type,
        ScheduledGame.status_state,
        ScheduledGame.status_code,
        ScheduledGame.opponent_team_id,
        ScheduledGame.games_in_series,
    )
    rows = (
        session.query(*columns)
        .filter(ScheduledGame.game_date >= season_start)
        .filter(ScheduledGame.game_date <= season_end)
        .filter(or_(
            ScheduledGame.team_id == int(team_id),
            ScheduledGame.game_type.in_(sorted(POSTSEASON_GAME_TYPES)),
        ))
        .all()
    )
    # Positive evidence that the regular season continues: the league's
    # earliest stored regular-season games on or after the reference date.
    league_regular_ahead = (
        session.query(*columns)
        .filter(ScheduledGame.game_date >= reference_date)
        .filter(ScheduledGame.game_date <= season_end)
        .filter(ScheduledGame.game_type == REGULAR_SEASON_GAME_TYPE)
        .filter(ScheduledGame.team_id != int(team_id))
        .order_by(ScheduledGame.game_date, ScheduledGame.game_pk, ScheduledGame.team_id)
        .limit(LEAGUE_REGULAR_SEASON_PROBE_ROWS)
        .all()
    )
    rows = list(rows) + list(league_regular_ahead)
    final_post_pks = sorted({
        row.game_pk for row in rows
        if row.game_type in POSTSEASON_GAME_TYPES
        and row.status_state == FINAL_STATE
        and row.game_date < reference_date
    })
    winner_by_game = {}
    if final_post_pks:
        decisions = (
            session.query(GameLog.mlb_game_pk, GameLog.appearance_team_id)
            .filter(GameLog.mlb_game_pk.in_(final_post_pks))
            .filter(GameLog.win.is_(True))
            .all()
        )
        teams_by_game = defaultdict(set)
        for game_pk, team in decisions:
            if team is not None:
                teams_by_game[int(game_pk)].add(int(team))
        # Exactly one credited winning club per game; anything else is not a
        # decision this module may read.
        winner_by_game = {
            game_pk: next(iter(teams))
            for game_pk, teams in teams_by_game.items()
            if len(teams) == 1
        }
    return rows, winner_by_game


def resolve_club_competition_status(team_id, reference_date, *, session=None):
    """Classify one club from stored authority, failing closed on read errors."""
    if not isinstance(reference_date, date):
        return ClubCompetitionStatus(
            int(team_id), STATUS_UNDETERMINED, BASIS_NO_SCHEDULE_EVIDENCE, None,
        )
    from utils.db import db

    active_session = session or db.session
    try:
        # A savepoint keeps a failed read from aborting the caller's
        # publication transaction; only this club fails closed.
        with active_session.begin_nested():
            rows, winner_by_game = load_competition_inputs(
                team_id, reference_date, session=active_session,
            )
    except Exception:  # noqa: BLE001 - an unreadable authority fails closed
        return lookup_failed_status(team_id, reference_date)
    return classify_club_competition_status(
        team_id,
        reference_date,
        schedule_rows=rows,
        winner_by_game=winner_by_game,
    )
