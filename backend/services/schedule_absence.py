"""Retiring a stored postseason "if necessary" game MLB stopped listing.

MLB publishes postseason "if necessary" games before the series is decided.
When a series ends early, MLB has stopped listing the unneeded game rather
than returning it with a Cancelled status. Production schedule-refresh counts
for Oct 1, 2026 show this (``docs/current/SYNC_PIPELINE.md`` §15F). Schedule
ingestion only upserts what MLB *returns*, so a game MLB *stopped* returning
stayed ``scheduled`` forever. Tonight, Matchup, schedule context and the ledger
rest window all kept treating it as a game that will be played.

Absence is never treated as proof by itself. The MLB ``/schedule`` endpoint
has no completeness flag, and a response whose own counts add up proves only
that it is internally consistent, not that it is complete. A stored game is
retired only when every one of these holds. Each is labelled with what kind
of evidence it is.

SOURCE AUTHORITY (what MLB says)

1. MLB marks the game conditional: its stored ``ifNecessary`` flag is 'Y'.
   For rows stored before that flag was kept, the series structure stands in:
   a postseason ``game_type`` and a ``series_game_number`` past the clinching
   minimum of a best-of-``games_in_series`` series. That covers best-of-3
   Game 3, best-of-5 Games 4-5 and best-of-7 Games 5-7. It is MLB's published
   structure; BaseballOS never works out who won a series. ``ifNecessary='N'``,
   or missing or inconsistent series metadata, never qualifies.
2. MLB's league-wide schedule response for a range covering the game's date
   does not list the gamePk anywhere, on any date. A gamePk listed under
   another date has moved and is upserted normally, never retired.

BASEBALLOS SAFEGUARDS (conservative heuristics, not MLB semantics)

3. Response integrity (``response_integrity``). The response must be a real
   league-wide ``/schedule`` response, never a stub, a hand-built list or a
   team-scoped fetch. Its requested range must be known, every date entry must
   lie inside that range with no duplicates, each entry's game list must match
   its declared ``totalGames``, and the per-date totals must sum to the
   response's ``totalGames``. A failed fetch raises before this point and
   changes nothing.
4. No unexplained absence. Every stored game the response omits within its
   range must itself be a scheduled postseason conditional game. Any other
   omission (a regular-season game, a postseason Game 1, a final or postponed
   game) makes the response suspect, so nothing is observed or retired for it.
5. Two observations. The first qualifying absence only records
   ``schedule_absent_since``. A separate later response, at least
   ``ABSENCE_CONFIRMATION_MINUTES`` after the first, must confirm it before the
   game is retired.
6. Reschedule guard. The confirming response's range must extend
   ``RESCHEDULE_GUARD_DAYS`` past the game's date, so a game moved a day or
   two would have been seen under its new date.
7. The ingest of that same response recorded no errors.

Every stored row of the game must also still be ``scheduled``: a final, live,
postponed, suspended or already-cancelled game is never touched.

A retired game is a cancellation in the existing vocabulary, written to both
schedule tables inside the ingest's transaction and schedule-ownership
declaration:

* ``scheduled_games``: ``status_state='other'``, ``status_code='RETIRED'``
  (owned by BaseballOS, never an MLB code), and ``source='schedule_absence'``;
* ``slate_games``: ``normalized_state='cancelled'``, the same code, and
  ``status_detailed='Cancelled: removed from MLB schedule'``.

Slate coverage's cancellation proof, schedule context, ledger rest, Tonight and
Matchup all read the retired game as one that will not be played. Nothing is
deleted. If MLB lists the gamePk again, the ordinary upsert overwrites every
field, clears ``schedule_absent_since``, and ingestion reports the game in
``game_pks_restored``.

An explicit MLB cancellation (code ``C``) is still stored as MLB sent it and
never goes through this path.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from models.scheduled_game import ScheduledGame
from models.slate_game import SlateGame
from utils.db import db


# Owned by BaseballOS, never an MLB code. The detailed state carries the word
# "Cancelled", so ``game_finality.classify_status`` (and therefore slate
# coverage's cancellation proof) reads a retired game as cancelled without a
# second status vocabulary.
SCHEDULE_RETIRED_STATUS_CODE = 'RETIRED'
SCHEDULE_RETIRED_DETAILED_STATE = 'Cancelled: removed from MLB schedule'
CANCELLED_STATUS_CODES = frozenset({'C', SCHEDULE_RETIRED_STATUS_CODE})


def is_unplayed_terminal_schedule_row(status_state, status_code):
    """A stored schedule row for a game that will not be played on its date.

    Postponed, or cancelled: MLB's cancellation code, or a game retired here.
    ``scheduled_games`` keeps a cancellation as ``status_state='other'`` (the
    same bucket as live and unrecognized), so ``other`` alone never qualifies;
    the code must say so.
    """
    if status_state == ScheduledGame.STATE_POSTPONED:
        return True
    return (
        status_state == ScheduledGame.STATE_OTHER
        and str(status_code or '').strip().upper() in CANCELLED_STATUS_CODES
    )


RETIREMENT_SOURCE = 'schedule_absence'
RETIREMENT_REASON = 'postseason_conditional_game_removed_from_schedule'
POSTSEASON_GAME_TYPES = frozenset({'F', 'D', 'L', 'W'})
SERIES_LENGTHS = frozenset({3, 5, 7})
RESCHEDULE_GUARD_DAYS = 2
ABSENCE_CONFIRMATION_MINUTES = 15

# Per-game outcomes.
ACTION_RETIRE = 'retire'
ACTION_OBSERVE = 'absence_observed'
ACTION_AWAIT_CONFIRMATION = 'awaiting_confirmation'
ACTION_RESCHEDULE_GUARD = 'awaiting_reschedule_guard'
UNEXPLAINED_NOT_SCHEDULED = 'stored_state_not_scheduled'
UNEXPLAINED_NOT_CONDITIONAL = 'not_postseason_conditional'

# Whole-response outcomes.
STATUS_NOTHING_ABSENT = 'nothing_absent'
STATUS_RECONCILED = 'reconciled'
STATUS_FAIL_CLOSED_UNEXPLAINED = 'fail_closed_unexplained_absence'
STATUS_FAIL_CLOSED_INGEST_ERRORS = 'fail_closed_ingest_errors'
STATUS_NOT_EVALUATED = 'not_evaluated'

INTEGRITY_NO_RESPONSE_SHAPE = 'no_response_shape'
INTEGRITY_TEAM_SCOPED = 'team_scoped_fetch'
INTEGRITY_RANGE_UNKNOWN = 'requested_range_unknown'
INTEGRITY_MALFORMED = 'malformed_response'
INTEGRITY_TOTAL_UNDECLARED = 'total_games_undeclared'
INTEGRITY_DATE_OUTSIDE_RANGE = 'date_entry_outside_range'
INTEGRITY_DUPLICATE_DATE = 'duplicate_date_entry'
INTEGRITY_DATE_COUNT_MISMATCH = 'date_entry_count_mismatch'
INTEGRITY_TOTAL_MISMATCH = 'total_games_mismatch'


def _date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _int(value):
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def response_integrity(games):
    """Whether the response behind ``games`` is structurally sound.

    ``consistent`` means internally consistent and league-wide for a known
    range. It does NOT mean MLB returned every game that exists: the endpoint
    offers no such signal. The other safeguards exist because of that.
    """
    shape = getattr(games, 'response_shape', None)
    if not isinstance(shape, dict):
        return {'consistent': False, 'reason': INTEGRITY_NO_RESPONSE_SHAPE,
                'start_date': None, 'end_date': None}
    start = _date(shape.get('requested_start'))
    end = _date(shape.get('requested_end'))
    base = {
        'start_date': start.isoformat() if start else None,
        'end_date': end.isoformat() if end else None,
    }

    def refuse(reason):
        return {**base, 'consistent': False, 'reason': reason}

    if shape.get('team_id') not in (None, ''):
        return refuse(INTEGRITY_TEAM_SCOPED)
    if start is None or end is None or end < start:
        return refuse(INTEGRITY_RANGE_UNKNOWN)
    if not shape.get('is_object') or not shape.get('dates_is_list'):
        return refuse(INTEGRITY_MALFORMED)
    declared_total = _int(shape.get('declared_total_games'))
    if declared_total is None:
        return refuse(INTEGRITY_TOTAL_UNDECLARED)
    seen = set()
    counted = 0
    for entry in shape.get('date_entries') or ():
        entry_date = _date(entry.get('date'))
        if entry_date is None or not start <= entry_date <= end:
            return refuse(INTEGRITY_DATE_OUTSIDE_RANGE)
        if entry_date in seen:
            return refuse(INTEGRITY_DUPLICATE_DATE)
        seen.add(entry_date)
        games_listed = _int(entry.get('games'))
        declared = _int(entry.get('declared_games'))
        if games_listed is None or (declared is not None and declared != games_listed):
            return refuse(INTEGRITY_DATE_COUNT_MISMATCH)
        counted += games_listed
    if counted != declared_total:
        return refuse(INTEGRITY_TOTAL_MISMATCH)
    return {**base, 'consistent': True, 'reason': None, 'total_games': declared_total}


def conditional_evidence(row):
    """Why a stored row is (or is not) a postseason conditional game.

    Returns ``(is_conditional, basis)``. MLB's own ``ifNecessary`` flag wins
    when stored; otherwise the published series structure is used, and only
    when it is complete and internally consistent.
    """
    game_type = str(getattr(row, 'game_type', None) or '').strip().upper()
    if game_type not in POSTSEASON_GAME_TYPES:
        return False, 'not_postseason'
    flag = str(getattr(row, 'if_necessary', None) or '').strip().upper()
    if flag == 'Y':
        return True, 'mlb_if_necessary_flag'
    if flag == 'N':
        return False, 'mlb_if_necessary_flag_no'
    series_game = _int(getattr(row, 'series_game_number', None))
    games_in_series = _int(getattr(row, 'games_in_series', None))
    if (
        games_in_series not in SERIES_LENGTHS
        or series_game is None
        or not 1 <= series_game <= games_in_series
    ):
        return False, 'series_metadata_unreliable'
    if series_game > games_in_series // 2 + 1:
        return True, 'series_position_past_clinching_minimum'
    return False, 'series_game_always_played'


def plan_absent_games(integrity, returned_game_pks, *, now):
    """Decide, for one response, what each stored-but-absent game warrants."""
    if not integrity.get('consistent'):
        return {'status': STATUS_NOT_EVALUATED, 'games': []}
    start = _date(integrity['start_date'])
    end = _date(integrity['end_date'])
    returned = {int(pk) for pk in returned_game_pks or () if pk is not None}
    rows = (
        ScheduledGame.query
        .filter(ScheduledGame.game_date >= start)
        .filter(ScheduledGame.game_date <= end)
        .all()
    )
    by_pk = defaultdict(list)
    for row in rows:
        if row.game_pk is not None and int(row.game_pk) not in returned:
            by_pk[int(row.game_pk)].append(row)

    games = []
    confirm_after = timedelta(minutes=ABSENCE_CONFIRMATION_MINUTES)
    for game_pk in sorted(by_pk):
        game_rows = by_pk[game_pk]
        if all(row.status_code == SCHEDULE_RETIRED_STATUS_CODE for row in game_rows):
            continue  # already retired: absence is the expected steady state
        game_date = min(row.game_date for row in game_rows)
        record = {'game_pk': game_pk, 'game_date': game_date.isoformat()}
        if any(row.status_state != ScheduledGame.STATE_SCHEDULED for row in game_rows):
            games.append({**record, 'action': UNEXPLAINED_NOT_SCHEDULED, 'unexplained': True})
            continue
        evidence = [conditional_evidence(row) for row in game_rows]
        if not all(is_conditional for is_conditional, _ in evidence):
            basis = next(b for ok, b in evidence if not ok)
            games.append({**record, 'action': UNEXPLAINED_NOT_CONDITIONAL,
                          'basis': basis, 'unexplained': True})
            continue
        record['basis'] = evidence[0][1]
        first_seen = [row.schedule_absent_since for row in game_rows]
        record['absent_since'] = (
            min(first_seen).isoformat() if all(first_seen) else None
        )
        if not all(first_seen):
            action = ACTION_OBSERVE
        elif now - min(first_seen) < confirm_after:
            action = ACTION_AWAIT_CONFIRMATION
        elif game_date + timedelta(days=RESCHEDULE_GUARD_DAYS) > end:
            action = ACTION_RESCHEDULE_GUARD
        else:
            action = ACTION_RETIRE
        games.append({**record, 'action': action, 'unexplained': False})

    if not games:
        status = STATUS_NOTHING_ABSENT
    elif any(game['unexplained'] for game in games):
        status = STATUS_FAIL_CLOSED_UNEXPLAINED
    else:
        status = STATUS_RECONCILED
    return {'status': status, 'games': games}


def game_pks_to_write(plan):
    """gamePks this plan would write (for the schedule-ownership declaration)."""
    if plan.get('status') != STATUS_RECONCILED:
        return []
    return [game['game_pk'] for game in plan['games']]


def apply_plan(plan, *, now):
    """Record first absences and retire confirmed games, in both tables.

    Runs inside the ingest's transaction; ``plan`` must be ``reconciled``.
    Returns the retired gamePks.
    """
    if plan.get('status') != STATUS_RECONCILED:
        return []
    observe = [g['game_pk'] for g in plan['games'] if g['action'] == ACTION_OBSERVE]
    retire = [g['game_pk'] for g in plan['games'] if g['action'] == ACTION_RETIRE]
    if observe:
        for row in ScheduledGame.query.filter(ScheduledGame.game_pk.in_(observe)).all():
            if row.schedule_absent_since is None:
                row.schedule_absent_since = now
    if retire:
        for row in ScheduledGame.query.filter(ScheduledGame.game_pk.in_(retire)).all():
            row.status_state = ScheduledGame.STATE_OTHER
            row.status_code = SCHEDULE_RETIRED_STATUS_CODE
            row.source = RETIREMENT_SOURCE
        for row in SlateGame.query.filter(SlateGame.game_pk.in_(retire)).all():
            row.normalized_state = SlateGame.STATE_CANCELLED
            row.status_code = SCHEDULE_RETIRED_STATUS_CODE
            row.status_detailed = SCHEDULE_RETIRED_DETAILED_STATE
            row.status_abstract = None
            row.last_synced = now
    return retire


def retired_game_pks(game_pks):
    """The subset of ``game_pks`` currently stored as retired."""
    keys = [int(pk) for pk in game_pks or () if pk is not None]
    if not keys:
        return set()
    rows = (
        db.session.query(ScheduledGame.game_pk)
        .filter(ScheduledGame.game_pk.in_(keys))
        .filter(ScheduledGame.status_code == SCHEDULE_RETIRED_STATUS_CODE)
        .distinct()
        .all()
    )
    return {int(row[0]) for row in rows}
