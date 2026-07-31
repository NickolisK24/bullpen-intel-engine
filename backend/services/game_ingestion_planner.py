"""Deterministic game-driven ingestion work planner (Foundation 3C).

The daily publication-critical appearance lane's unit of work is ONE GAME. This
planner produces the ordered set of game work items for a represented date, and
it is derived from the canonical scheduled-game ledger plus the canonical game
finality authority — never from ``Pitcher.query.filter_by(active=True)``.

Inputs (all existing canonical authorities, no new ones):

  * ``models.scheduled_game.ScheduledGame`` — the durable schedule ledger,
    already refreshed daily by the sync's schedule/finality preflight;
  * ``services.game_finality`` — status precedence and suspended/resumed
    linkage resolution;
  * ``models.game_ingestion_work_item.GameIngestionWorkItem`` — durable prior
    completion state.

Horizon
-------
Two bounded horizons, both governed and both far smaller than a season:

  * ``ingestion_horizon_days`` — how far back a newly-final game is still
    picked up. Defaults to the daily lane's existing ``days_back`` window (7),
    so game-driven planning covers exactly what the pitcher loop covered.
  * ``correction_horizon_days`` — how far back an already-completed final game
    is re-examined for an official stat correction. Also 7, for the same
    reason: the pitcher loop re-read its 7-day window every day, so a 7-day
    correction horizon is equal coverage, not reduced coverage.

Unresolved work has NO horizon: an incomplete work item of any age is always
re-planned first. That is the resume guarantee — a game can never be
permanently skipped because time passed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from models.game_ingestion_work_item import GameIngestionWorkItem
from models.scheduled_game import ScheduledGame
from services import game_finality


DEFAULT_INGESTION_HORIZON_DAYS = 7
DEFAULT_CORRECTION_HORIZON_DAYS = 7

SOURCE_AUTHORITY_SCHEDULE_LEDGER = 'scheduled_games'

# Planner-level exclusion reasons (safe, non-sensitive, explicitly counted).
EXCLUDED_NOT_FINAL = 'not_final'
EXCLUDED_POSTPONED = 'postponed'
EXCLUDED_CANCELLED = 'cancelled'
EXCLUDED_SUSPENDED_NOT_FINAL = 'suspended_not_final'
EXCLUDED_UNRESOLVED_RESUMED_LINKAGE = 'unresolved_resumed_linkage'
EXCLUDED_FINALITY_CONFLICT = 'finality_conflict'
EXCLUDED_ALREADY_COMPLETE = 'already_complete_at_current_revision'
EXCLUDED_TERMINAL_FAILURE = 'terminal_failure'
EXCLUDED_SUPERSEDED = 'superseded'


@dataclass(frozen=True)
class GameWorkItem:
    """One planned unit of game-driven ingestion work."""

    game_pk: int
    represented_date: date
    game_date: date
    game_datetime: datetime | None
    home_team_id: int | None
    away_team_id: int | None
    game_type: str | None
    finality_state: str
    candidate_reason: str
    criticality: str
    source_authority: str
    prior_status: str | None
    prior_source_revision: str | None
    attempt_count: int
    ordering_key: tuple = field(default=())

    def to_dict(self) -> dict:
        return {
            'game_pk': self.game_pk,
            'represented_date': self.represented_date.isoformat(),
            'game_date': self.game_date.isoformat() if self.game_date else None,
            'game_datetime': (
                self.game_datetime.isoformat() if self.game_datetime else None
            ),
            'home_team_id': self.home_team_id,
            'away_team_id': self.away_team_id,
            'game_type': self.game_type,
            'finality_state': self.finality_state,
            'candidate_reason': self.candidate_reason,
            'criticality': self.criticality,
            'source_authority': self.source_authority,
            'prior_status': self.prior_status,
            'prior_source_revision': self.prior_source_revision,
            'attempt_count': self.attempt_count,
        }


def ingestion_horizon_days() -> int:
    return _env_positive_int(
        'GAME_INGESTION_HORIZON_DAYS', DEFAULT_INGESTION_HORIZON_DAYS
    )


def correction_horizon_days() -> int:
    return _env_positive_int(
        'GAME_INGESTION_CORRECTION_HORIZON_DAYS', DEFAULT_CORRECTION_HORIZON_DAYS
    )


def plan_game_work(
    reference_date: date,
    *,
    horizon_days: int | None = None,
    correction_days: int | None = None,
    explicit_game_pks=None,
    include_backfill: bool = False,
) -> dict:
    """Build the deterministic, ordered game work plan for ``reference_date``.

    Returns a dict with ``items`` (ordered ``GameWorkItem`` list) and the
    planner accounting the run report and the completeness proof both read.
    Every scheduled game inside the horizon is accounted for exactly once:
    either it is planned, or it carries an explicit exclusion reason.
    """
    horizon_days = int(
        horizon_days if horizon_days is not None else ingestion_horizon_days()
    )
    correction_days = int(
        correction_days if correction_days is not None else correction_horizon_days()
    )
    window_start = reference_date - timedelta(days=max(horizon_days, correction_days))
    explicit_game_pks = {
        pk for pk in (_positive_int(value) for value in (explicit_game_pks or ()))
        if pk is not None
    }

    rows_by_game = _scheduled_rows_by_game(
        window_start, reference_date, explicit_game_pks
    )

    # Unresolved work of ANY age is always re-planned, even when it has aged out
    # of the horizon. Without this a game interrupted mid-run could be skipped
    # forever once the window moved past it.
    for stale_pk in _unresolved_game_pks_outside(set(rows_by_game)):
        rows_by_game.setdefault(stale_pk, _rows_for_game(stale_pk))

    work_items_by_game = _work_items_by_game(
        set(rows_by_game) | explicit_game_pks
    )

    planned: list[GameWorkItem] = []
    excluded: dict[str, int] = {}
    excluded_game_pks: dict[str, list[int]] = {}
    schedule_authority_missing: list[int] = []
    finality_conflicts: list[int] = []

    for game_pk in sorted(rows_by_game):
        rows = rows_by_game.get(game_pk) or []
        work_item = work_items_by_game.get(game_pk)
        if not rows:
            # Unresolved work whose schedule authority has vanished cannot be
            # proven final. Critical work fails the gate closed rather than
            # being quietly dropped; a best-effort backlog item does not
            # withhold the public snapshot.
            if (
                work_item is None
                or work_item.criticality
                != GameIngestionWorkItem.CRITICALITY_BEST_EFFORT
            ):
                schedule_authority_missing.append(game_pk)
            continue

        finality = _finality_for_rows(rows)
        if finality['conflict']:
            finality_conflicts.append(game_pk)
            _count(excluded, excluded_game_pks, EXCLUDED_FINALITY_CONFLICT, game_pk)
            continue
        if finality['state'] != game_finality.FINAL_STATUS_STATE:
            _count(excluded, excluded_game_pks, finality['exclusion'], game_pk)
            continue

        represented = _represented_date(rows)
        decision = _candidate_reason(
            work_item=work_item,
            represented_date=represented,
            reference_date=reference_date,
            horizon_days=horizon_days,
            correction_days=correction_days,
            explicit=game_pk in explicit_game_pks,
            include_backfill=include_backfill,
        )
        if decision['reason'] is None:
            _count(excluded, excluded_game_pks, decision['exclusion'], game_pk)
            continue

        planned.append(_build_item(
            game_pk=game_pk,
            rows=rows,
            represented_date=represented,
            reference_date=reference_date,
            horizon_days=horizon_days,
            candidate_reason=decision['reason'],
            work_item=work_item,
        ))

    planned.sort(key=lambda item: item.ordering_key)

    reason_counts: dict[str, int] = {}
    for item in planned:
        reason_counts[item.candidate_reason] = (
            reason_counts.get(item.candidate_reason, 0) + 1
        )
    criticality_counts: dict[str, int] = {}
    for item in planned:
        criticality_counts[item.criticality] = (
            criticality_counts.get(item.criticality, 0) + 1
        )

    return {
        'reference_date': reference_date.isoformat(),
        'window_start': window_start.isoformat(),
        'ingestion_horizon_days': horizon_days,
        'correction_horizon_days': correction_days,
        'items': planned,
        'games_discovered': len(rows_by_game),
        'games_planned': len(planned),
        'candidate_reason_counts': reason_counts,
        'criticality_counts': criticality_counts,
        'newly_final_count': reason_counts.get(
            GameIngestionWorkItem.REASON_NEWLY_FINAL, 0
        ),
        'corrected_final_count': reason_counts.get(
            GameIngestionWorkItem.REASON_CORRECTED_FINAL, 0
        ),
        'retry_count': reason_counts.get(
            GameIngestionWorkItem.REASON_INCOMPLETE_PRIOR_ATTEMPT, 0
        ),
        'excluded_counts': excluded,
        'excluded_game_pks': {
            reason: sorted(pks)[:200] for reason, pks in excluded_game_pks.items()
        },
        'schedule_authority_missing': sorted(schedule_authority_missing),
        'finality_conflicts': sorted(finality_conflicts),
    }


# ── Internals ────────────────────────────────────────────────────────────────


def _scheduled_rows_by_game(window_start, reference_date, explicit_game_pks):
    query = ScheduledGame.query.filter(
        ScheduledGame.game_date >= window_start,
        ScheduledGame.game_date <= reference_date,
    )
    rows = query.order_by(
        ScheduledGame.game_pk.asc(), ScheduledGame.team_id.asc()
    ).all()
    grouped: dict[int, list] = {}
    for row in rows:
        grouped.setdefault(row.game_pk, []).append(row)
    for game_pk in explicit_game_pks:
        if game_pk not in grouped:
            grouped[game_pk] = _rows_for_game(game_pk)
    return grouped


def _rows_for_game(game_pk):
    return (
        ScheduledGame.query
        .filter(ScheduledGame.game_pk == game_pk)
        .order_by(ScheduledGame.team_id.asc())
        .all()
    )


def _work_items_by_game(game_pks):
    game_pks = sorted(pk for pk in game_pks if pk)
    if not game_pks:
        return {}
    return {
        item.mlb_game_pk: item
        for item in (
            GameIngestionWorkItem.query
            .filter(GameIngestionWorkItem.mlb_game_pk.in_(game_pks))
            .all()
        )
    }


def _unresolved_game_pks_outside(known_game_pks):
    rows = (
        GameIngestionWorkItem.query
        .filter(GameIngestionWorkItem.status.in_(
            list(GameIngestionWorkItem.UNRESOLVED_STATUSES)
        ))
        .with_entities(GameIngestionWorkItem.mlb_game_pk)
        .all()
    )
    return sorted({pk for (pk,) in rows if pk and pk not in known_game_pks})


def _finality_for_rows(rows) -> dict:
    """Resolve one game's finality from its stored schedule rows (fail closed)."""
    if game_finality.scheduled_rows_have_unresolved_resumed_linkage(rows):
        return {
            'state': None,
            'conflict': False,
            'exclusion': EXCLUDED_UNRESOLVED_RESUMED_LINKAGE,
        }

    states = {row.status_state for row in rows}
    if game_finality.SUSPENDED_STATUS_STATE in states:
        return {
            'state': None,
            'conflict': False,
            'exclusion': EXCLUDED_SUSPENDED_NOT_FINAL,
        }
    if game_finality.FINAL_STATUS_STATE in states:
        # Both sides of one game must agree that it is final. A one-sided final
        # is a conflicting finality source and fails closed.
        if len(states) > 1:
            return {'state': None, 'conflict': True, 'exclusion': EXCLUDED_FINALITY_CONFLICT}
        return {
            'state': game_finality.FINAL_STATUS_STATE,
            'conflict': False,
            'exclusion': None,
        }
    if game_finality.POSTPONED_STATUS_STATE in states:
        return {'state': None, 'conflict': False, 'exclusion': EXCLUDED_POSTPONED}
    if game_finality.SCHEDULED_STATUS_STATE in states:
        return {'state': None, 'conflict': False, 'exclusion': EXCLUDED_NOT_FINAL}
    # Cancelled and every other terminal-but-not-final state stores as 'other'.
    return {'state': None, 'conflict': False, 'exclusion': EXCLUDED_CANCELLED}


def _represented_date(rows):
    """The baseball date a game belongs to for publication purposes.

    A suspended game resumed on a later calendar date keeps the ORIGINAL
    product date when the schedule ledger recorded one, so a resumed game
    cannot silently move a represented date's completeness.
    """
    for row in rows:
        if row.original_product_date:
            return row.original_product_date
    for row in rows:
        if row.game_date:
            return row.game_date
    return None


def _candidate_reason(
    *,
    work_item,
    represented_date,
    reference_date,
    horizon_days,
    correction_days,
    explicit,
    include_backfill,
) -> dict:
    if explicit:
        return {'reason': GameIngestionWorkItem.REASON_EXPLICIT_REPAIR, 'exclusion': None}

    if work_item is not None:
        if work_item.status == GameIngestionWorkItem.STATUS_SUPERSEDED:
            return {'reason': None, 'exclusion': EXCLUDED_SUPERSEDED}
        if work_item.status == GameIngestionWorkItem.STATUS_TERMINAL_FAILURE:
            return {'reason': None, 'exclusion': EXCLUDED_TERMINAL_FAILURE}
        if work_item.status in GameIngestionWorkItem.UNRESOLVED_STATUSES:
            return {
                'reason': GameIngestionWorkItem.REASON_INCOMPLETE_PRIOR_ATTEMPT,
                'exclusion': None,
            }
        # Completed. Only a game inside the correction horizon is re-examined;
        # whether its official line actually changed is proven by comparing the
        # observed appearance-set fingerprint after the fetch, not guessed here.
        if _within(represented_date, reference_date, correction_days):
            return {
                'reason': GameIngestionWorkItem.REASON_CORRECTED_FINAL,
                'exclusion': None,
            }
        return {'reason': None, 'exclusion': EXCLUDED_ALREADY_COMPLETE}

    if _within(represented_date, reference_date, horizon_days):
        return {'reason': GameIngestionWorkItem.REASON_NEWLY_FINAL, 'exclusion': None}
    if include_backfill:
        return {'reason': GameIngestionWorkItem.REASON_BACKFILL, 'exclusion': None}
    return {'reason': None, 'exclusion': EXCLUDED_ALREADY_COMPLETE}


def _build_item(
    *,
    game_pk,
    rows,
    represented_date,
    reference_date,
    horizon_days,
    candidate_reason,
    work_item,
) -> GameWorkItem:
    home_team_id = _side_team_id(rows, 'home')
    away_team_id = _side_team_id(rows, 'away')
    game_datetime = next(
        (row.game_datetime for row in rows if row.game_datetime), None
    )
    game_date = next((row.game_date for row in rows if row.game_date), None)
    game_type = next((row.game_type for row in rows if row.game_type), None)
    criticality = _criticality(
        candidate_reason=candidate_reason,
        represented_date=represented_date,
        reference_date=reference_date,
        horizon_days=horizon_days,
        prior_criticality=(
            work_item.criticality if work_item is not None else None
        ),
    )

    # Deterministic ordering (never database default row order):
    #   1. incomplete prior critical work
    #   2. oldest unresolved represented date
    #   3. game start time (unknown start times sort last, stably)
    #   4. game identifier
    retry_rank = (
        0 if candidate_reason == GameIngestionWorkItem.REASON_INCOMPLETE_PRIOR_ATTEMPT
        else 1
    )
    critical_rank = (
        0 if criticality != GameIngestionWorkItem.CRITICALITY_BEST_EFFORT else 1
    )
    ordering_key = (
        retry_rank,
        critical_rank,
        represented_date.toordinal() if represented_date else 0,
        0 if game_datetime is not None else 1,
        game_datetime.isoformat() if game_datetime is not None else '',
        game_pk,
    )

    return GameWorkItem(
        game_pk=game_pk,
        represented_date=represented_date,
        game_date=game_date,
        game_datetime=game_datetime,
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        game_type=game_type,
        finality_state=game_finality.FINAL_STATUS_STATE,
        candidate_reason=candidate_reason,
        criticality=criticality,
        source_authority=SOURCE_AUTHORITY_SCHEDULE_LEDGER,
        prior_status=work_item.status if work_item is not None else None,
        prior_source_revision=(
            work_item.source_revision if work_item is not None else None
        ),
        attempt_count=(work_item.attempt_count or 0) if work_item is not None else 0,
        ordering_key=ordering_key,
    )


def _criticality(
    *, candidate_reason, represented_date, reference_date, horizon_days,
    prior_criticality=None,
) -> str:
    """Game-level publication criticality.

    A governed final game inside the represented-date horizon is
    publication-critical: its appearances ARE the bullpen evidence the public
    snapshot is built from. Everything older is best-effort backfill. A game
    whose represented date cannot be established fails closed to unknown.
    """
    if represented_date is None:
        return GameIngestionWorkItem.CRITICALITY_UNKNOWN
    if candidate_reason == GameIngestionWorkItem.REASON_BACKFILL:
        return GameIngestionWorkItem.CRITICALITY_BEST_EFFORT
    if _within(represented_date, reference_date, horizon_days):
        return GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL
    if (
        candidate_reason in (
            GameIngestionWorkItem.REASON_INCOMPLETE_PRIOR_ATTEMPT,
            GameIngestionWorkItem.REASON_EXPLICIT_REPAIR,
        )
        and prior_criticality != GameIngestionWorkItem.CRITICALITY_BEST_EFFORT
    ):
        # Unresolved CRITICAL work does not become best-effort merely because
        # the window moved past it. Work that was best-effort to begin with
        # stays best-effort, so a repair backlog can never withhold publication.
        return GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL
    return GameIngestionWorkItem.CRITICALITY_BEST_EFFORT


def _side_team_id(rows, side):
    for row in rows:
        if row.home_away == side:
            return row.team_id
    opposite = 'away' if side == 'home' else 'home'
    for row in rows:
        if row.home_away == opposite and row.opponent_team_id is not None:
            return row.opponent_team_id
    return None


def _within(value, reference_date, days) -> bool:
    if value is None or reference_date is None:
        return False
    return 0 <= (reference_date - value).days <= int(days)


def _count(counts, game_pks, reason, game_pk):
    counts[reason] = counts.get(reason, 0) + 1
    game_pks.setdefault(reason, []).append(game_pk)


def _positive_int(value):
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _env_positive_int(name, default):
    raw = os.environ.get(name)
    if raw in (None, ''):
        return default
    try:
        parsed = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
