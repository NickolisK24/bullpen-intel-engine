"""Ledger-confirmed rest for active-bullpen arms that carry no fatigue score.

The fatigue batch (``services.sync.recalculate_all_fatigue_scores``) writes a
score only for an active pitcher with a game log inside the 14-day scoring
window and no unresolved workload-fetch failure. A reliever who has made no MLB
appearance in that window is deliberately not scored: there is no workload to
model. If he was scored in the past, his old score survives and the coverage
contract already treats him as observed rest (``data_state='stale'`` with a
complete appearance ledger, DECISION 2). If he was never scored (an MLB debut,
a call-up, a pitcher whose last appearance predates the stored scores) no score
row exists at all, and he used to count as unresolved.

The availability classifier never reads the score of a stale arm: stale is
decided from the appearance record alone. So the proof that makes a stale arm
usable for coverage does not depend on its score, and the same proof can be
applied to an arm with no score, provided nothing contradicts it.

This module decides that proof. It never creates a score or a readiness record
and never changes an arm's availability. An arm it confirms counts as usable
for TEAM COVERAGE only: BaseballOS knows it carries no recent MLB workload, not
what its modeled fatigue would be. Every uncertainty keeps it unresolved:

* the roster evidence for the arm is not the team's, active and assigned;
* the completed-appearance ledger is not complete for the reference date;
* an unresolved ``pitcher_game_logs`` fetch failure exists for the arm;
* any game log row (complete or not) is dated inside the active window;
* a game of the team inside the ledger window is not final (live, suspended,
  or still scheduled after its date).

The active window is the same ``ACTIVE_WINDOW_DAYS`` that separates a fresh
from a stale arm. The ledger window (10 days by default) contains every
workload input the availability model reads (five days of appearances and
pitches, days of rest), which is why a complete ledger makes absence trustworthy
for scored and unscored arms alike.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, Mapping

from sqlalchemy import or_

from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from models.sync_failure import SyncFailure
from services.availability import ACTIVE_WINDOW_DAYS
from services.schedule_absence import CANCELLED_STATUS_CODES
from utils.db import db


WORKLOAD_FETCH_FAILURE_ENTITY_TYPE = 'pitcher_game_logs'
TEAM_ASSIGNMENT_ASSIGNED = 'ASSIGNED'

REASON_CONFIRMED = 'ledger_confirmed_no_recent_workload'
REASON_PITCHER_UNKNOWN = 'pitcher_unknown'
REASON_OTHER_TEAM = 'pitcher_other_team'
REASON_INACTIVE = 'pitcher_inactive'
REASON_ASSIGNMENT_UNCONFIRMED = 'team_assignment_unconfirmed'
REASON_MLB_ID_MISSING = 'mlb_id_missing'
REASON_LEDGER_INCOMPLETE = 'appearance_ledger_incomplete'
REASON_FETCH_FAILURE_OPEN = 'workload_fetch_failure_open'
REASON_RECENT_APPEARANCE_UNSCORED = 'recent_appearance_unscored'
REASON_WINDOW_LOG_INCOMPLETE = 'window_game_log_incomplete'
REASON_TEAM_GAME_NOT_FINAL = 'team_game_not_final'

_UNSETTLED_GAME_STATES = (
    ScheduledGame.STATE_SCHEDULED,
    ScheduledGame.STATE_SUSPENDED,
    ScheduledGame.STATE_OTHER,
)


def _ledger_window_days():
    from services.appearance_ledger import ledger_window_days
    return ledger_window_days()


def _open_fetch_failure_refs(refs):
    if not refs:
        return set()
    rows = (
        db.session.query(SyncFailure.entity_ref)
        .filter(SyncFailure.entity_type == WORKLOAD_FETCH_FAILURE_ENTITY_TYPE)
        .filter(SyncFailure.resolved.is_(False))
        .filter(SyncFailure.entity_ref.in_(sorted(refs)))
        .all()
    )
    return {row[0] for row in rows}


def _window_logs(pitcher_ids, reference_date):
    """Every stored log row in the active window, by pitcher."""
    if not pitcher_ids:
        return {}
    rows = (
        db.session.query(GameLog.pitcher_id, GameLog.pitches_thrown,
                         GameLog.innings_pitched_outs)
        .filter(GameLog.pitcher_id.in_(sorted(pitcher_ids)))
        .filter(GameLog.game_date >= reference_date - timedelta(days=ACTIVE_WINDOW_DAYS))
        .filter(GameLog.game_date <= reference_date)
        .all()
    )
    grouped = {}
    for pitcher_id, pitches, outs in rows:
        grouped.setdefault(pitcher_id, []).append((pitches, outs))
    return grouped


def _team_has_unsettled_game(team_id, reference_date):
    """True when a team game in the ledger window is not settled.

    Games dated on the reference date itself may legitimately still be ahead
    (the availability date is the day after the slate), so only earlier dates
    are required to be final or postponed.
    """
    start = reference_date - timedelta(days=_ledger_window_days() - 1)
    row = (
        db.session.query(ScheduledGame.id)
        .filter(ScheduledGame.team_id == team_id)
        .filter(ScheduledGame.game_date >= start)
        .filter(ScheduledGame.game_date < reference_date)
        .filter(ScheduledGame.status_state.in_(_UNSETTLED_GAME_STATES))
        # A cancelled or retired game (``other`` with a cancellation code) is
        # settled: it will never be played, so it never awaits finality.
        .filter(or_(
            ScheduledGame.status_state != ScheduledGame.STATE_OTHER,
            ScheduledGame.status_code.is_(None),
            ~ScheduledGame.status_code.in_(tuple(CANCELLED_STATUS_CODES)),
        ))
        .first()
    )
    return row is not None


def _log_reason(logs):
    for pitches, outs in logs:
        if pitches is None:
            return REASON_WINDOW_LOG_INCOMPLETE
    # Any other row in the window is an appearance (or a zero line) that the
    # fatigue batch would have scored; its absence of a score is unexplained.
    return REASON_RECENT_APPEARANCE_UNSCORED


def evaluate_unscored_rest(
    pitcher_ids: Iterable[int],
    *,
    team_id: int,
    reference_date: date,
    ledger_complete: bool,
) -> Mapping[int, str]:
    """Return ``{pitcher_id: reason}`` for active-bullpen arms with no score.

    ``REASON_CONFIRMED`` means the arm is usable for team coverage. Any other
    reason names the first piece of evidence that keeps it unresolved. Read
    only; one query per evidence source regardless of the number of arms.
    """
    pitcher_ids = sorted({pid for pid in pitcher_ids if pid is not None})
    if not pitcher_ids:
        return {}
    pitchers = {
        pitcher.id: pitcher
        for pitcher in Pitcher.query.filter(Pitcher.id.in_(pitcher_ids)).all()
    }
    refs = {
        str(pitcher.mlb_id) for pitcher in pitchers.values()
        if pitcher.mlb_id is not None
    }
    failed_refs = _open_fetch_failure_refs(refs)
    window_logs = _window_logs(pitcher_ids, reference_date)
    unsettled = None

    reasons = {}
    for pitcher_id in pitcher_ids:
        pitcher = pitchers.get(pitcher_id)
        if pitcher is None:
            reasons[pitcher_id] = REASON_PITCHER_UNKNOWN
        elif pitcher.team_id != team_id:
            reasons[pitcher_id] = REASON_OTHER_TEAM
        elif pitcher.active is not True:
            reasons[pitcher_id] = REASON_INACTIVE
        elif pitcher.team_assignment_status != TEAM_ASSIGNMENT_ASSIGNED:
            reasons[pitcher_id] = REASON_ASSIGNMENT_UNCONFIRMED
        elif pitcher.mlb_id is None:
            reasons[pitcher_id] = REASON_MLB_ID_MISSING
        elif str(pitcher.mlb_id) in failed_refs:
            reasons[pitcher_id] = REASON_FETCH_FAILURE_OPEN
        elif window_logs.get(pitcher_id):
            reasons[pitcher_id] = _log_reason(window_logs[pitcher_id])
        elif not ledger_complete:
            reasons[pitcher_id] = REASON_LEDGER_INCOMPLETE
        else:
            if unsettled is None:
                unsettled = _team_has_unsettled_game(team_id, reference_date)
            reasons[pitcher_id] = (
                REASON_TEAM_GAME_NOT_FINAL if unsettled else REASON_CONFIRMED
            )
    return reasons


def ledger_confirmed_rest_ids(
    pitcher_ids: Iterable[int],
    *,
    team_id: int,
    reference_date: date,
    ledger_complete: bool,
) -> frozenset:
    """The unscored active-bullpen arms whose rest the evidence confirms."""
    if not ledger_complete or reference_date is None:
        return frozenset()
    reasons = evaluate_unscored_rest(
        pitcher_ids, team_id=team_id, reference_date=reference_date,
        ledger_complete=ledger_complete,
    )
    return frozenset(
        pitcher_id for pitcher_id, reason in reasons.items()
        if reason == REASON_CONFIRMED
    )
