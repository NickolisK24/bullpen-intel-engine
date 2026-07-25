"""Team State card metrics — readiness_summary + reliever_evidence (SC-04B v1.2).

Backend-owned computation of the two card-only data blocks the v1.2 payload adds
over v1.1: a four-metric ``readiness_summary`` (clean options, multi-use arms,
short-rest arms, left-handed options) and a bounded, deterministically-ordered
``reliever_evidence`` table. Every value comes from an existing canonical
authority — this module composes them for the card. It invents no baseball
meaning, computes no performance metric (no ERA, saves, ranks — none of which is
truthfully supportable without a team-at-appearance authority), and attaches no
card-only availability label (Normal/Stressed/Tired/…) or recommendation language.

Determinism / temporal correctness: the SAME governed slate (the source
snapshot's ``data_through``) always produces the SAME metrics. Every window is
anchored to that slate — three completed TEAM games (never three calendar days),
rest measured to the slate, appearances counted against the just-completed trigger
slate inclusive. No build-time clock is read; a rerun on the same slate is
byte-identical. Off days never enter a window because only ``final`` games count,
and a doubleheader contributes two distinct ``game_pk`` window entries.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Optional

from sqlalchemy import or_

from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from services.availability import (
    STATUS_AVAILABLE,
    STATUS_MONITOR,
)
from services.availability_snapshot import (
    classify_latest_fatigue_rows,
    latest_fatigue_rows,
)
from services.availability_summary import STATUS_ORDER
from services.bullpen_optionality_context import build_bullpen_optionality_context
from services.workload_appearance import is_workload_appearance_log, workload_out_count
from utils.db import db


# Number of completed TEAM games in the reliever workload window. NOT calendar
# days: off days never enter, and a doubleheader contributes two entries.
TEAM_GAME_WINDOW = 3

# The bounded reliever evidence table size.
MAX_RELIEVER_ROWS = 6

# Short rest is zero or one day since the last completed appearance, measured to
# the slate (a pitcher who worked the just-completed trigger game is on zero rest).
SHORT_REST_DAYS = (0, 1)

# Most-restrictive-first ordering for reliever rows: the governed availability
# ladder is least-restrictive-first, so reverse it. An unrecognized/absent label
# sorts last (never ahead of a governed one).
_RESTRICTION_ORDER = list(reversed(STATUS_ORDER))

# A "usable option" reuses the optionality authority's own tiering: Available and
# Monitor arms are options; Limited/Avoid/Unavailable are restricted. Resolved data
# only — a missing/incomplete source read is not a usable option.
_USABLE_OPTION_STATUSES = frozenset({STATUS_AVAILABLE, STATUS_MONITOR})
_UNRESOLVED_DATA_STATES = frozenset({'missing', 'incomplete'})


def _availability_of(record: Mapping[str, Any]) -> dict:
    availability = record.get('availability') if isinstance(record, Mapping) else None
    return availability if isinstance(availability, Mapping) else {}


def _restriction_rank(status: Optional[str]) -> int:
    try:
        return _RESTRICTION_ORDER.index(status)
    except ValueError:
        return len(_RESTRICTION_ORDER)


def _is_usable_option(record: Optional[Mapping[str, Any]]) -> bool:
    if not isinstance(record, Mapping):
        return False
    availability = _availability_of(record)
    status = availability.get('availability_status')
    data_state = availability.get('data_state')
    return status in _USABLE_OPTION_STATUSES and data_state not in _UNRESOLVED_DATA_STATES


def _outs_to_innings_text(outs: int) -> str:
    """Recorded outs → conventional innings text (7 outs -> ``2.1``)."""
    return f'{outs // 3}.{outs % 3}'


def _last_completed_team_games(team_id: int, reference_date: date) -> list:
    """The team's last ``TEAM_GAME_WINDOW`` completed games on or before the slate.

    Newest first; distinct ``game_pk`` so a doubleheader is two window entries, not
    one. Only ``final`` games count, so an off day is never mistaken for a game and
    the window is exactly N *played* games, never N calendar days.
    """
    return (
        ScheduledGame.query
        .filter(ScheduledGame.team_id == team_id)
        .filter(ScheduledGame.status_state == ScheduledGame.STATE_FINAL)
        .filter(ScheduledGame.game_date <= reference_date)
        .order_by(ScheduledGame.game_date.desc(), ScheduledGame.game_pk.desc())
        .limit(TEAM_GAME_WINDOW)
        .all()
    )


def _window_workload_by_pitcher(active_ids, game_pks) -> dict:
    """Per-pitcher (appearances, recorded outs) within the team-game window.

    An appearance is a governed workload log (``is_workload_appearance_log``) whose
    game is one of the window's games. Appearances are counted by distinct game
    (the ``(pitcher_id, mlb_game_pk)`` uniqueness gives one row per pitcher-game),
    so a doubleheader in which a pitcher worked both games counts as two.
    """
    if not active_ids or not game_pks:
        return {}
    logs = (
        GameLog.query
        .filter(GameLog.pitcher_id.in_(active_ids))
        .filter(GameLog.mlb_game_pk.in_(game_pks))
        .all()
    )
    workload: dict = {}
    for log in logs:
        if not is_workload_appearance_log(log):
            continue
        entry = workload.setdefault(log.pitcher_id, {'appearances': 0, 'outs': 0})
        entry['appearances'] += 1
        entry['outs'] += int(workload_out_count(log) or 0)
    return workload


def _last_appearances(active_ids, reference_date: date) -> dict:
    """Per-pitcher most-recent completed appearance on or before the slate.

    Returns ``{pitcher_id: {'date': date, 'opponent': abbr}}``. Anchored to the
    slate (``game_date <= reference_date``) so post-slate rows never leak into a
    historical read. On a doubleheader date the higher ``mlb_game_pk`` (the later
    game) wins, keeping the choice deterministic.
    """
    if not active_ids:
        return {}
    logs = (
        GameLog.query
        .filter(GameLog.pitcher_id.in_(active_ids))
        .filter(GameLog.game_date <= reference_date)
        .filter(or_(GameLog.pitches_thrown > 0, GameLog.innings_pitched_outs > 0))
        .order_by(GameLog.game_date.desc(), GameLog.mlb_game_pk.desc())
        .all()
    )
    latest: dict = {}
    for log in logs:
        if log.pitcher_id in latest:
            continue  # first row per pitcher is the most recent (query is ordered)
        latest[log.pitcher_id] = {
            'date': log.game_date,
            'opponent': log.opponent_abbreviation,
        }
    return latest


def _rest_days(last_date: Optional[date], reference_date: date) -> Optional[int]:
    if not isinstance(last_date, date):
        return None
    return max((reference_date - last_date).days, 0)


def _metric(label: str, count: int, total: int, statement: str, **extra) -> dict:
    metric = {'label': label, 'count': int(count), 'total': int(total), 'statement': statement}
    metric.update(extra)
    return metric


def build_team_state_card_metrics(team_id: int, *, reference_date: date) -> dict:
    """Return ``{'readiness_summary': {...}, 'reliever_evidence': [...]}`` for a team.

    ``reference_date`` is the governed slate the artifact is anchored to (the source
    snapshot's ``data_through``). It is the single reference for membership, rest,
    and the three-team-game workload window, so a progressive read and a league read
    on the SAME slate produce identical card metrics (distinct provenance, identical
    baseball facts).
    """
    from api.team_operations import _active_bullpen_membership

    active_ids, authority_complete = _active_bullpen_membership(team_id, reference_date)
    active_ids = {pid for pid in active_ids if pid is not None}

    # Classified availability for the team, anchored to the slate — the SAME
    # authority the readiness verdict used, so labels never contradict the read.
    rows = latest_fatigue_rows(team_id=team_id)
    records = classify_latest_fatigue_rows(rows, reference_date=reference_date)
    record_by_pid = {
        r['pitcher_id']: r
        for r in records
        if r.get('pitcher_id') in active_ids
    }
    active_records = list(record_by_pid.values())

    pitchers = {}
    if active_ids:
        pitchers = {
            p.id: p
            for p in Pitcher.query.filter(Pitcher.id.in_(active_ids)).all()
        }

    games = _last_completed_team_games(team_id, reference_date)
    game_pks = [g.game_pk for g in games]
    workload = _window_workload_by_pitcher(active_ids, game_pks)
    last_appearances = _last_appearances(active_ids, reference_date)

    active_count = len(active_ids)

    # -- CLEAN OPTIONS ------------------------------------------------------
    # Existing canonical optionality authority — clean (Available, no workload
    # warning) arms of the active bullpen.
    optionality = build_bullpen_optionality_context(
        active_records, reference_date=reference_date
    )
    if optionality.get('context_available') is True:
        clean_count = int(optionality['optionality_summary_inputs']['clean_count'])
    else:
        clean_count = 0
    clean_options = _metric(
        'Clean options', clean_count, active_count,
        f'{clean_count} of {active_count} active bullpen arms are clean options.',
    )

    # -- MULTI-USE ARMS -----------------------------------------------------
    multi_use_count = sum(
        1 for pid in active_ids
        if workload.get(pid, {}).get('appearances', 0) >= 2
    )
    games_in_window = len(games)
    multi_use_arms = _metric(
        'Multi-use arms', multi_use_count, active_count,
        (
            f'{multi_use_count} of {active_count} active bullpen arms pitched in at '
            f'least two of the last {games_in_window} completed games.'
        ),
        games_in_window=games_in_window,
    )

    # -- SHORT-REST ARMS ----------------------------------------------------
    short_rest_count = 0
    for pid in active_ids:
        rest = _rest_days(last_appearances.get(pid, {}).get('date'), reference_date)
        if rest in SHORT_REST_DAYS:
            short_rest_count += 1
    short_rest_arms = _metric(
        'Short-rest arms', short_rest_count, active_count,
        (
            f'{short_rest_count} of {active_count} active bullpen arms are on zero or '
            'one day of rest.'
        ),
    )

    # -- LEFT-HANDED OPTIONS ------------------------------------------------
    # Numerator: left-handers in the usable-option set. Denominator: left-handers on
    # the active bullpen (documented). Injured/inactive arms are already outside
    # active-bullpen membership; unresolved/unavailable arms are not usable options.
    active_lhp = [pid for pid in active_ids
                  if getattr(pitchers.get(pid), 'throws', None) == 'L']
    usable_lhp = [pid for pid in active_lhp if _is_usable_option(record_by_pid.get(pid))]
    left_handed_options = _metric(
        'Left-handed options', len(usable_lhp), len(active_lhp),
        (
            f'{len(usable_lhp)} of {len(active_lhp)} active bullpen left-handers are '
            'usable options.'
        ),
        denominator='active bullpen left-handers',
    )

    readiness_summary = {
        'clean_options': clean_options,
        'multi_use_arms': multi_use_arms,
        'short_rest_arms': short_rest_arms,
        'left_handed_options': left_handed_options,
        'active_bullpen_count': active_count,
        'authority_complete': bool(authority_complete),
    }

    reliever_evidence = _build_reliever_evidence(
        active_ids=active_ids,
        record_by_pid=record_by_pid,
        pitchers=pitchers,
        workload=workload,
        last_appearances=last_appearances,
        reference_date=reference_date,
    )

    return {
        'readiness_summary': readiness_summary,
        'reliever_evidence': reliever_evidence,
        'evidence_window': {
            'team_games': games_in_window,
            'game_pks': list(game_pks),
        },
    }


def _build_reliever_evidence(
    *, active_ids, record_by_pid, pitchers, workload, last_appearances, reference_date
) -> list:
    """Bounded, deterministically-ordered reliever rows.

    Candidates are active-bullpen arms with a classified availability read (every
    row carries a canonical availability label). Ordering is the governed selection
    order (spec): more-restrictive availability, then more window appearances, then
    more recorded outs, then more recent appearance, then a stable pitcher-id / name
    tiebreak. The bounded table shows the first ``MAX_RELIEVER_ROWS``.
    """
    candidates = []
    for pid in active_ids:
        record = record_by_pid.get(pid)
        if record is None:
            continue  # no classified availability read -> no canonical label -> omit
        pitcher = pitchers.get(pid) or record.get('pitcher')
        availability = _availability_of(record)
        status = availability.get('availability_status')
        entry = workload.get(pid, {})
        appearances = int(entry.get('appearances', 0))
        outs = int(entry.get('outs', 0))
        last = last_appearances.get(pid, {})
        last_date = last.get('date')
        rest_days = _rest_days(last_date, reference_date)
        name = getattr(pitcher, 'full_name', None) or record.get('pitcher_name')
        candidates.append({
            'pitcher_id': pid,
            'name': name,
            'last_three_appearances': appearances,
            'outs_recorded': outs,
            'innings_text': _outs_to_innings_text(outs),
            'last_appearance_date': last_date.isoformat() if isinstance(last_date, date) else None,
            'last_opponent': last.get('opponent'),
            'rest_days': rest_days,
            'availability': status,
        })

    def sort_key(row):
        last_date = row['last_appearance_date']
        # More recent first: a real ISO date sorts ahead of a missing one.
        date_rank = last_date or ''
        return (
            _restriction_rank(row['availability']),          # most restrictive first
            -row['last_three_appearances'],                  # more appearances first
            -row['outs_recorded'],                           # more recorded outs first
            _DateDesc(date_rank),                            # more recent first
            row['pitcher_id'],                               # stable tiebreak
            row['name'] or '',
        )

    candidates.sort(key=sort_key)
    return candidates[:MAX_RELIEVER_ROWS]


class _DateDesc:
    """Sort helper: descending by ISO date string, with '' (missing) sorting last."""

    __slots__ = ('value',)

    def __init__(self, value: str):
        self.value = value

    def __lt__(self, other: '_DateDesc') -> bool:
        # Missing dates ('') always sort AFTER present dates; otherwise later ISO
        # date strings sort first (descending -> most recent appearance leads).
        if self.value == other.value:
            return False
        if self.value == '':
            return False
        if other.value == '':
            return True
        return self.value > other.value

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _DateDesc) and self.value == other.value
