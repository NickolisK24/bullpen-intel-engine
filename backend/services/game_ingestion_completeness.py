"""Game-level publication completeness proof (Foundation 3C).

Publication completeness for the daily appearance lane is a statement about
GAMES, not about how many pitcher rows a loop managed to touch before its
budget ran out.

This module produces ONE canonical per-game classification and projects it
into TWO explicitly separate views:

  OBSERVATION       what the game-driven lane has and has not proven or
                    persisted for its own staged rollout;
  PUBLICATION GATE  what is allowed to affect the public publication gate
                    under the lane's CURRENT authority mode.

Both views come from the same classification, so they cannot drift.

The distinction exists because of a production-proven scope defect. The lane
runs in SHADOW mode and by design creates no durable work items. Every planned
critical game therefore looked like an unresolved final game, and the daily
sync folded that number into publication-critical unresolved work. A read-only
production audit found 63 such games, all of them with official-final evidence,
final stored schedule authority, and stored appearance rows — and zero true
baseball deficits among them. Shadow OBSERVATION incompleteness was being
represented as PUBLICATION-BLOCKING incompleteness.

The governing invariant is therefore:

    observation backlog != publication blocker

unless game-driven publication authority has been explicitly activated.

Work-item evidence — a missing, retryable, or terminal work item — becomes a
publication blocker ONLY under ``authoritative`` mode. Everything that is
evidence about BASEBALL rather than about the lane's own bookkeeping blocks in
every mode: finality conflicts, missing schedule authority, an appearance-row
reconciliation shortfall, and a material correction conflict.

The result still fails closed. Any unprovable condition, and any unavailable or
unknown lane authority, yields ``publication_complete = False`` with explicit
reason codes. It never weakens an existing gate — it is an ADDITIONAL, more
precise input to the same publication-critical completeness contract, and the
canonical finality, appearance-ledger, freshness, provenance and
serving-selection gates are untouched.
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

# Non-blocking observation signal. It names, on the publication gate itself,
# the backlog the gate is deliberately NOT counting, so a reader can see that
# the games were observed and consciously excluded rather than overlooked.
# It is informational only: it never sets a blocking count.
REASON_OBSERVATION_UNRESOLVED_GAMES = 'shadow_observation_unresolved_games'

# The lane could not be asked what its authority is. Fail closed.
REASON_LANE_AUTHORITY_UNAVAILABLE = 'game_lane_authority_unavailable'

# Closed vocabulary for what the lane's mode does to the publication gate.
AUTHORITY_EFFECT_OBSERVATIONAL_ONLY = 'observational_only'
AUTHORITY_EFFECT_NON_AUTHORITATIVE_WRITE = 'non_authoritative_write'
AUTHORITY_EFFECT_AUTHORITATIVE = 'authoritative'
AUTHORITY_EFFECT_UNAVAILABLE = 'unavailable'

AUTHORITY_EFFECTS = (
    AUTHORITY_EFFECT_OBSERVATIONAL_ONLY,
    AUTHORITY_EFFECT_NON_AUTHORITATIVE_WRITE,
    AUTHORITY_EFFECT_AUTHORITATIVE,
    AUTHORITY_EFFECT_UNAVAILABLE,
)


def authority_effect_for_mode(lane_mode) -> str:
    """Map a lane mode to its effect on the publication gate.

    Imported lazily so the completeness proof stays importable on its own and
    no import cycle can form between it and the lane it describes.
    """
    from services import game_driven_ingestion

    if lane_mode == game_driven_ingestion.MODE_SHADOW:
        return AUTHORITY_EFFECT_OBSERVATIONAL_ONLY
    if lane_mode == game_driven_ingestion.MODE_WRITE:
        return AUTHORITY_EFFECT_NON_AUTHORITATIVE_WRITE
    if lane_mode == game_driven_ingestion.MODE_AUTHORITATIVE:
        return AUTHORITY_EFFECT_AUTHORITATIVE
    # off, None, or anything unrecognised. An absent lane cannot certify a
    # publication gate, so it is never silently treated as "nothing to block".
    return AUTHORITY_EFFECT_UNAVAILABLE


def resolve_lane_mode(lane_mode=None) -> str:
    """The effective mode, preferring what the caller already knows.

    A caller that has just RUN the lane knows the mode it ran under. Re-reading
    the environment there would let a status report describe a different mode
    from the one that produced the evidence.
    """
    from services import game_driven_ingestion

    if lane_mode is not None:
        return str(lane_mode)
    return game_driven_ingestion.ingestion_mode()


def classify_game_ingestion_scope(
    represented_date: date,
    *,
    horizon_days: int | None = None,
    plan: dict | None = None,
) -> dict:
    """The ONE canonical classification both views are projected from.

    Everything downstream — observation membership, publication-blocker
    membership, every count in either view — is derived from this single pass.
    Nothing re-derives the predicate, so the two views cannot drift into
    disagreeing about the same game.

    Read-only: it queries and returns, and writes nothing. It creates no work
    item, updates none, and performs no commit.
    """
    horizon_days = int(
        horizon_days if horizon_days is not None
        else planner.ingestion_horizon_days()
    )
    window_start = represented_date - timedelta(days=horizon_days)
    plan = plan if plan is not None else planner.plan_game_work(represented_date)

    planned_items = list(plan.get('items') or [])
    critical = [
        entry for entry in planned_items
        if entry.criticality != GameIngestionWorkItem.CRITICALITY_BEST_EFFORT
    ]
    # A planned critical game that is not already completed at its current
    # source revision should be resolved for this represented date and is not.
    # `corrected_final` re-checks are the exception: the game IS complete at
    # its last known revision, and a correction withholds only once proven
    # material.
    outstanding = [
        entry for entry in critical
        if entry.candidate_reason != GameIngestionWorkItem.REASON_CORRECTED_FINAL
    ]

    work_items = _work_items_in_window(window_start, represented_date)
    completed = [
        item for item in work_items
        if item.status == GameIngestionWorkItem.STATUS_COMPLETED
    ]
    unresolved_work = [
        item for item in work_items
        if item.status in GameIngestionWorkItem.UNRESOLVED_STATUSES
        and item.criticality != GameIngestionWorkItem.CRITICALITY_BEST_EFFORT
    ]
    terminal_work = [
        item for item in work_items
        if item.status == GameIngestionWorkItem.STATUS_TERMINAL_FAILURE
        and item.criticality != GameIngestionWorkItem.CRITICALITY_BEST_EFFORT
    ]

    # A correction is MATERIAL — and withholds — only when it was detected and
    # could not be applied safely, which leaves the work item unresolved
    # carrying the correction-conflict class. That is evidence about the
    # BASEBALL record, not about the lane's bookkeeping, so it blocks in every
    # mode.
    correction_pending = [
        item for item in unresolved_work
        if (item.error_class or '') == 'correction_conflict'
    ]

    expected_rows, reconciled_rows = _appearance_row_reconciliation(completed)

    outstanding_pks = {entry.game_pk for entry in outstanding}
    unresolved_pks = {item.mlb_game_pk for item in unresolved_work}

    return {
        'represented_date': represented_date.isoformat(),
        'window_start': window_start.isoformat(),
        'horizon_days': horizon_days,
        # ── Membership ──────────────────────────────────────────────────
        'unresolved_game_pks': sorted(outstanding_pks | unresolved_pks),
        'outstanding_critical_game_pks': sorted(outstanding_pks),
        'unresolved_work_item_game_pks': sorted(unresolved_pks),
        'terminal_work_item_game_pks': sorted(
            item.mlb_game_pk for item in terminal_work
        ),
        'critical_planned_game_pks': sorted(
            entry.game_pk for entry in critical
        ),
        'correction_pending_game_pks': sorted(
            item.mlb_game_pk for item in correction_pending
        ),
        # ── Counts ──────────────────────────────────────────────────────
        'expected_final_games': len(
            {item.mlb_game_pk for item in work_items}
            | {entry.game_pk for entry in critical}
        ),
        'completed_work_item_games': len(completed),
        'retryable_work_item_count': len(unresolved_work),
        'terminal_work_item_count': len(terminal_work),
        'correction_pending_count': len(correction_pending),
        'best_effort_games_planned': len(planned_items) - len(critical),
        'corrected_games_reconciled': sum(
            int(item.correction_count or 0) for item in completed
        ),
        'appearance_rows_expected': expected_rows,
        'appearance_rows_reconciled': reconciled_rows,
        'finality_conflict_count': len(plan.get('finality_conflicts') or []),
        'schedule_authority_missing_count': len(
            plan.get('schedule_authority_missing') or []
        ),
    }


def unresolved_final_game_membership(
    represented_date: date,
    *,
    horizon_days: int | None = None,
    plan: dict | None = None,
    scope: dict | None = None,
) -> dict:
    """The canonical OBSERVATION membership: what the LANE has not resolved.

    This is telemetry about the game-driven lane's own staged rollout. It is
    NOT a publication-blocker set. In shadow mode the lane creates no durable
    work items by design, so every planned critical game appears here while
    none of them blocks publication. Use
    ``publication_blocking_game_membership`` for the gate.

    A game is observationally unresolved when EITHER it is a planned critical
    game that is not a ``corrected_final`` re-check, OR it carries a
    non-best-effort work item still in an unresolved status inside the window.
    The two sets overlap, so the answer is their union, which is why the count
    is smaller than the planned-critical total.

    Read-only: it queries and returns, and writes nothing.
    """
    scope = scope if scope is not None else classify_game_ingestion_scope(
        represented_date, horizon_days=horizon_days, plan=plan,
    )
    return {
        'represented_date': scope['represented_date'],
        'window_start': scope['window_start'],
        'horizon_days': scope['horizon_days'],
        'membership_view': 'observation',
        'game_pks': list(scope['unresolved_game_pks']),
        'outstanding_critical_game_pks': list(
            scope['outstanding_critical_game_pks']
        ),
        'unresolved_work_item_game_pks': list(
            scope['unresolved_work_item_game_pks']
        ),
        'critical_planned_game_pks': list(scope['critical_planned_game_pks']),
    }


def publication_blocking_game_membership(
    represented_date: date,
    *,
    horizon_days: int | None = None,
    plan: dict | None = None,
    scope: dict | None = None,
    lane_mode=None,
) -> dict:
    """The games whose WORK-ITEM state is allowed to withhold publication.

    Derived from the same classification as the observation membership, so the
    two can never disagree about a game. The projection is the whole
    difference: work-item evidence becomes blocking only when the lane is
    publication-authoritative.

    Conditions that are evidence about BASEBALL rather than about the lane's
    bookkeeping — finality conflicts, missing schedule authority, appearance
    shortfalls, material corrections — are not in this membership and block
    through their own counts in every mode.
    """
    scope = scope if scope is not None else classify_game_ingestion_scope(
        represented_date, horizon_days=horizon_days, plan=plan,
    )
    effect = authority_effect_for_mode(resolve_lane_mode(lane_mode))
    authoritative = effect == AUTHORITY_EFFECT_AUTHORITATIVE
    return {
        'represented_date': scope['represented_date'],
        'window_start': scope['window_start'],
        'horizon_days': scope['horizon_days'],
        'membership_view': 'publication_blocker',
        'authority_effect': effect,
        'publication_authoritative': authoritative,
        'game_pks': (
            list(scope['unresolved_game_pks']) if authoritative else []
        ),
        'terminal_game_pks': (
            list(scope['terminal_work_item_game_pks']) if authoritative else []
        ),
        # Always reported so a reader can see exactly what was withheld from
        # the gate, and on what grounds.
        'observation_only_game_pks': (
            [] if authoritative else list(scope['unresolved_game_pks'])
        ),
    }


def build_game_ingestion_completeness(
    represented_date: date,
    *,
    horizon_days: int | None = None,
    plan: dict | None = None,
    lane_mode=None,
) -> dict:
    """Return the game-level proof as two explicitly separate views.

    ``lane_mode`` should be passed by any caller that already knows which mode
    the lane ran under. It falls back to the canonical mode authority only
    when the caller cannot say.
    """
    scope = classify_game_ingestion_scope(
        represented_date, horizon_days=horizon_days, plan=plan,
    )
    mode = resolve_lane_mode(lane_mode)
    effect = authority_effect_for_mode(mode)
    authoritative = effect == AUTHORITY_EFFECT_AUTHORITATIVE

    observation = _observation_view(scope)
    publication_gate = _publication_gate_view(scope, effect)

    return {
        'represented_date': scope['represented_date'],
        'window_start': scope['window_start'],
        'horizon_days': scope['horizon_days'],
        'lane_mode': mode,
        'publication_authoritative': authoritative,
        'observation': observation,
        'publication_gate': publication_gate,

        # ── Publication truth ───────────────────────────────────────────
        # These are the fields a publication gate may act on.
        'publication_complete': publication_gate['complete'],
        'decision_reasons': list(publication_gate['reason_codes']),
        'publication_blocking_unresolved_final_games': publication_gate[
            'blocking_unresolved_game_count'
        ],
        'publication_blocking_terminal_failure_games': publication_gate[
            'blocking_terminal_failure_count'
        ],

        # ── Retained legacy fields — OBSERVATIONAL, not publication ─────
        # Kept under their original names so existing telemetry readers do not
        # break. Their meaning is the lane's own backlog. A reader that treats
        # `unresolved_final_games` or `terminal_failure_games` as a publication
        # blocker is reading observation telemetry as authority; the
        # `publication_blocking_*` fields above are the gate.
        'expected_final_games': observation['expected_final_games'],
        'completed_final_games': observation['completed_work_item_games'],
        'unresolved_final_games': observation['unresolved_game_count'],
        'terminal_failure_games': observation['terminal_work_item_count'],
        'observational_fields': (
            'expected_final_games', 'completed_final_games',
            'unresolved_final_games', 'terminal_failure_games',
        ),

        # ── Mode-independent baseball evidence ──────────────────────────
        'correction_pending_games': scope['correction_pending_count'],
        'corrected_games_reconciled': scope['corrected_games_reconciled'],
        'critical_appearance_rows_expected': scope['appearance_rows_expected'],
        'critical_appearance_rows_reconciled': scope[
            'appearance_rows_reconciled'
        ],
        'finality_conflicts': scope['finality_conflict_count'],
        'schedule_authority_missing': scope[
            'schedule_authority_missing_count'
        ],
        'best_effort_games_planned': scope['best_effort_games_planned'],
    }


def _observation_view(scope) -> dict:
    """What the lane has and has not proven for its own staged rollout."""
    reasons: list[str] = []
    if scope['correction_pending_count']:
        reasons.append(REASON_CORRECTION_PENDING)
    if scope['outstanding_critical_game_pks']:
        reasons.append(REASON_UNRESOLVED_FINAL_GAMES)
    if scope['retryable_work_item_count']:
        reasons.append(REASON_CRITICAL_FAILURE_UNRESOLVED)
    if scope['terminal_work_item_count']:
        reasons.append(REASON_TERMINAL_CRITICAL_FAILURE)
    if scope['finality_conflict_count']:
        reasons.append(REASON_FINALITY_CONFLICT)
    if scope['schedule_authority_missing_count']:
        reasons.append(REASON_SCHEDULE_AUTHORITY_MISSING)
    if scope['appearance_rows_expected'] != scope['appearance_rows_reconciled']:
        reasons.append(REASON_APPEARANCE_ROWS_UNRECONCILED)

    complete = not reasons
    if complete:
        reasons.append(REASON_COMPLETE)

    return {
        'view': 'observation',
        'expected_final_games': scope['expected_final_games'],
        'completed_work_item_games': scope['completed_work_item_games'],
        'unresolved_game_count': len(scope['unresolved_game_pks']),
        'retryable_work_item_count': scope['retryable_work_item_count'],
        'terminal_work_item_count': scope['terminal_work_item_count'],
        'complete': complete,
        'reason_codes': list(dict.fromkeys(reasons)),
    }


def _publication_gate_view(scope, authority_effect) -> dict:
    """What may withhold the public snapshot under the CURRENT authority.

    Work-item evidence counts only under ``authoritative``. Baseball evidence
    counts in every mode. An unavailable authority is never complete.
    """
    authoritative = authority_effect == AUTHORITY_EFFECT_AUTHORITATIVE
    unavailable = authority_effect == AUTHORITY_EFFECT_UNAVAILABLE

    blocking_unresolved = (
        len(scope['unresolved_game_pks']) if authoritative else 0
    )
    blocking_terminal = (
        scope['terminal_work_item_count'] if authoritative else 0
    )
    blocking_retryable = (
        scope['retryable_work_item_count'] if authoritative else 0
    )
    appearance_shortfall = (
        scope['appearance_rows_expected'] != scope['appearance_rows_reconciled']
    )

    reasons: list[str] = []
    if unavailable:
        reasons.append(REASON_LANE_AUTHORITY_UNAVAILABLE)
    # Baseball evidence: blocks in every mode.
    if scope['correction_pending_count']:
        reasons.append(REASON_CORRECTION_PENDING)
    if scope['finality_conflict_count']:
        reasons.append(REASON_FINALITY_CONFLICT)
    if scope['schedule_authority_missing_count']:
        reasons.append(REASON_SCHEDULE_AUTHORITY_MISSING)
    if appearance_shortfall:
        reasons.append(REASON_APPEARANCE_ROWS_UNRECONCILED)
    # Lane bookkeeping: blocks only under authoritative mode.
    if blocking_unresolved:
        reasons.append(REASON_UNRESOLVED_FINAL_GAMES)
    if blocking_retryable:
        reasons.append(REASON_CRITICAL_FAILURE_UNRESOLVED)
    if blocking_terminal:
        reasons.append(REASON_TERMINAL_CRITICAL_FAILURE)

    complete = not reasons

    # Informational reasons are appended only AFTER `complete` is decided, so
    # a non-blocking observation signal can never turn into a withholding one.
    if complete:
        reasons.append(REASON_COMPLETE)
    if not authoritative:
        reasons.append(REASON_LANE_NOT_AUTHORITATIVE)
        if scope['unresolved_game_pks']:
            reasons.append(REASON_OBSERVATION_UNRESOLVED_GAMES)

    return {
        'view': 'publication_gate',
        'authority_effect': authority_effect,
        'complete': complete,
        # The lane's contribution to publication-critical GAME scope. Zero
        # when the lane is not authoritative, so a consumer cannot report
        # "105 total, 42 completed, 0 unresolved" and imply 63 vanished.
        'blocking_scope_game_count': (
            scope['expected_final_games'] if authoritative else 0
        ),
        'blocking_completed_game_count': (
            scope['completed_work_item_games'] if authoritative else 0
        ),
        'blocking_unresolved_game_count': blocking_unresolved,
        'blocking_terminal_failure_count': blocking_terminal,
        'blocking_retryable_work_item_count': blocking_retryable,
        'finality_conflict_count': scope['finality_conflict_count'],
        'schedule_authority_missing_count': scope[
            'schedule_authority_missing_count'
        ],
        'correction_pending_count': scope['correction_pending_count'],
        'appearance_rows_expected': scope['appearance_rows_expected'],
        'appearance_rows_reconciled': scope['appearance_rows_reconciled'],
        'observation_only_game_count': (
            0 if authoritative else len(scope['unresolved_game_pks'])
        ),
        'reason_codes': list(dict.fromkeys(reasons)),
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
