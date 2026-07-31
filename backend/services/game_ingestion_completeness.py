"""Game-level publication completeness proof (Foundation 3C).

Publication completeness for the daily appearance lane is a statement about
GAMES, not about how many pitcher rows a loop managed to touch before its
budget ran out.

For represented date ``D``, publication-critical appearance ingestion is
complete only when ALL of the following hold:

  * every governed game through ``D`` that should be final is resolved;
  * every final governed game has a completed work item at its currently known
    source revision;
  * every extracted publication-critical appearance has reconciled;
  * no retryable or terminal critical failure remains unresolved;
  * no finality conflict remains;
  * schedule-authority coverage reconciles;
  * game-level appearance totals reconcile with the stored appearance ledger.

The result fails closed: any unprovable condition yields
``publication_complete = False`` with explicit reason codes. It never weakens
an existing gate — it is an ADDITIONAL, more precise input to the same
publication-critical completeness contract.
"""

from __future__ import annotations

from datetime import date, timedelta

from models.game_ingestion_work_item import GameIngestionWorkItem
from models.game_log import GameLog
from services import game_ingestion_planner as planner


REASON_COMPLETE = 'game_ingestion_complete'
REASON_UNRESOLVED_FINAL_GAMES = 'unresolved_final_games'
REASON_CRITICAL_FAILURE_UNRESOLVED = 'critical_game_failure_unresolved'
REASON_TERMINAL_CRITICAL_FAILURE = 'terminal_critical_game_failure'
REASON_FINALITY_CONFLICT = 'finality_conflict_unresolved'
REASON_SCHEDULE_AUTHORITY_MISSING = 'schedule_authority_missing'
REASON_APPEARANCE_ROWS_UNRECONCILED = 'critical_appearance_rows_unreconciled'
REASON_CORRECTION_PENDING = 'material_correction_pending'
REASON_LANE_NOT_AUTHORITATIVE = 'game_lane_not_publication_authoritative'


def build_game_ingestion_completeness(
    represented_date: date,
    *,
    horizon_days: int | None = None,
    plan: dict | None = None,
) -> dict:
    """Return the explicit game-level publication completeness proof."""
    horizon_days = int(
        horizon_days if horizon_days is not None else planner.ingestion_horizon_days()
    )
    window_start = represented_date - timedelta(days=horizon_days)

    plan = plan if plan is not None else planner.plan_game_work(represented_date)
    planned_items = list(plan.get('items') or [])
    critical_items = [
        item for item in planned_items
        if item.criticality != GameIngestionWorkItem.CRITICALITY_BEST_EFFORT
    ]

    work_items = _work_items_in_window(window_start, represented_date)
    completed = [
        item for item in work_items
        if item.status == GameIngestionWorkItem.STATUS_COMPLETED
    ]
    unresolved = [
        item for item in work_items
        if item.status in GameIngestionWorkItem.UNRESOLVED_STATUSES
        and item.criticality != GameIngestionWorkItem.CRITICALITY_BEST_EFFORT
    ]
    terminal = [
        item for item in work_items
        if item.status == GameIngestionWorkItem.STATUS_TERMINAL_FAILURE
        and item.criticality != GameIngestionWorkItem.CRITICALITY_BEST_EFFORT
    ]

    # A planned critical game that is not already completed at its current
    # source revision is, by definition, an unresolved final game for this
    # represented date. `corrected_final` re-checks are the one exception: the
    # game IS complete at its last known revision, and a correction only
    # withholds once it is proven material (see below).
    outstanding_critical = [
        item for item in critical_items
        if item.candidate_reason != GameIngestionWorkItem.REASON_CORRECTED_FINAL
    ]

    expected_rows, reconciled_rows = _appearance_row_reconciliation(completed)
    corrections_reconciled = sum(int(item.correction_count or 0) for item in completed)

    # A `corrected_final` re-check is not itself a withholding condition: the
    # game is complete at its last known revision and the re-check either
    # confirms it or reconciles the change inside the same run. A correction
    # becomes MATERIAL — and withholds — only when it was detected and could
    # not be applied safely, which leaves the work item unresolved carrying the
    # correction-conflict class.
    correction_pending = [
        item for item in unresolved
        if (item.error_class or '') == 'correction_conflict'
    ]

    expected_final_games = len(
        {item.mlb_game_pk for item in work_items}
        | {item.game_pk for item in critical_items}
    )

    reasons: list[str] = []
    if correction_pending:
        reasons.append(REASON_CORRECTION_PENDING)
    if outstanding_critical:
        reasons.append(REASON_UNRESOLVED_FINAL_GAMES)
    if unresolved:
        reasons.append(REASON_CRITICAL_FAILURE_UNRESOLVED)
    if terminal:
        reasons.append(REASON_TERMINAL_CRITICAL_FAILURE)
    if plan.get('finality_conflicts'):
        reasons.append(REASON_FINALITY_CONFLICT)
    if plan.get('schedule_authority_missing'):
        reasons.append(REASON_SCHEDULE_AUTHORITY_MISSING)
    if expected_rows != reconciled_rows:
        reasons.append(REASON_APPEARANCE_ROWS_UNRECONCILED)

    complete = not reasons
    if complete:
        reasons.append(REASON_COMPLETE)

    return {
        'represented_date': represented_date.isoformat(),
        'window_start': window_start.isoformat(),
        'horizon_days': horizon_days,
        'expected_final_games': expected_final_games,
        'completed_final_games': len(completed),
        'unresolved_final_games': len(
            {item.game_pk for item in outstanding_critical}
            | {item.mlb_game_pk for item in unresolved}
        ),
        'correction_pending_games': len(correction_pending),
        'terminal_failure_games': len(terminal),
        'corrected_games_reconciled': corrections_reconciled,
        'critical_appearance_rows_expected': expected_rows,
        'critical_appearance_rows_reconciled': reconciled_rows,
        'finality_conflicts': len(plan.get('finality_conflicts') or []),
        'schedule_authority_missing': len(
            plan.get('schedule_authority_missing') or []
        ),
        'best_effort_games_planned': len(planned_items) - len(critical_items),
        'publication_complete': complete,
        'decision_reasons': list(dict.fromkeys(reasons)),
    }


def _work_items_in_window(window_start, represented_date):
    return (
        GameIngestionWorkItem.query
        .filter(GameIngestionWorkItem.represented_date >= window_start)
        .filter(GameIngestionWorkItem.represented_date <= represented_date)
        .order_by(GameIngestionWorkItem.mlb_game_pk.asc())
        .all()
    )


def _appearance_row_reconciliation(completed_items) -> tuple[int, int]:
    """Reconcile each completed game's proven expectation against stored rows.

    ``rows_expected`` is what the game's official box score contained;
    ``rows_reconciled`` is what the writer proved it stored. The stored
    appearance ledger is re-counted here so a work item cannot claim
    completeness for rows that later disappeared.
    """
    expected = sum(int(item.rows_expected or 0) for item in completed_items)
    if not completed_items:
        return 0, 0

    game_pks = [item.mlb_game_pk for item in completed_items]
    stored_counts: dict[int, int] = {}
    rows = (
        GameLog.query
        .with_entities(GameLog.mlb_game_pk)
        .filter(GameLog.mlb_game_pk.in_(game_pks))
        .all()
    )
    for (game_pk,) in rows:
        stored_counts[game_pk] = stored_counts.get(game_pk, 0) + 1

    reconciled = 0
    for item in completed_items:
        proven = int(item.rows_reconciled or 0)
        stored = stored_counts.get(item.mlb_game_pk, 0)
        # Fail closed: credit only the rows that are BOTH proven by the work
        # item and still present in the appearance ledger.
        reconciled += min(proven, stored)
    return expected, reconciled
