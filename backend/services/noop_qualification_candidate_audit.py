"""Read-only audit for manual no-op write qualification candidates.

Why this exists
---------------
Production run 30862655470 dispatched the manual no-op write qualification for
game 824488 and refused with the single reason ``target_work_item_missing``.
Every safety property held: authorization passed, the writer guard was acquired
and released, the write phase was never entered, and no baseball-data or
lane-bookkeeping effect was produced.

What it proved is the point. Game 824488's GameLog rows exist and reconcile
cleanly, but a reconciling GameLog row is NOT the same fact as a durable
``game_ingestion_work_item`` completed by the game-driven lane. The lane only
creates that row when it runs in a write-capable mode, and it has only ever run
in shadow. Operator intuition about "a game that looks clean" therefore cannot
identify a qualification candidate.

This audit replaces guessing with production evidence: it reads the durable
work-item table, runs the real canonical shadow lane against a bounded,
deterministically ordered candidate set, and reports which games are eligible.

What this module is
-------------------
Orchestration, classification, and evidence. It owns no baseball decision. Every
eligibility fact is read out of the canonical components:

    services.game_driven_ingestion.run_game_driven_ingestion  (SHADOW only)
    services.game_ingestion_planner.plan_game_work            scope + finality
    services.game_log_reconciliation                          the one planner
    services.pitcher_identity_reconciliation                  D-009 governance
    services.noop_write_qualification                         the shared plan
                                                              governance helpers
    services.sync_metadata.acquire_public_sync_read_lock      lock-only guard

It never calls the lane in ``write``, ``authoritative``, or backfill mode, and
it contains no insert, update, delete, add, or commit of its own. The single
``UPDATE`` text in this file is the canonical refused write probe — bounded by
``WHERE 1 = 0``, expected to raise, and rolled back — reused from the existing
production read-only diagnostics.

Nothing here authorizes a dispatch. Finding a candidate is information, not
permission.
"""

from __future__ import annotations

import hashlib
import re
from datetime import timedelta

from sqlalchemy import text

from models.game_ingestion_work_item import GameIngestionWorkItem
from services import game_driven_ingestion as lane
from services import game_log_reconciliation as reconciliation
from services import noop_write_qualification as qualification
from services import pitcher_identity_reconciliation as pitcher_identity
from utils.db import db


SCHEMA_VERSION = '1'
AUDIT_TYPE = 'noop_qualification_candidate_audit'

CONFIRMATION = 'AUDIT_NOOP_QUALIFICATION_CANDIDATES'

RESULT_ELIGIBLE_FOUND = 'COMPLETE_ELIGIBLE_FOUND'
RESULT_NO_ELIGIBLE_CANDIDATE = 'COMPLETE_NO_ELIGIBLE_CANDIDATE'
RESULT_FAILED = 'FAILED'
RESULT_UNPROVEN = 'UNPROVEN'

EXIT_CODES = {
    RESULT_ELIGIBLE_FOUND: 0,
    # Finding nothing is a completed audit, not a workflow failure.
    RESULT_NO_ELIGIBLE_CANDIDATE: 0,
    RESULT_FAILED: 1,
    RESULT_UNPROVEN: 2,
}

NON_AUTHORIZATION_STATEMENT = (
    'This audit is read-only and does not authorize a no-op write dispatch, '
    'scheduled writes, automated writes, authoritative publication, backfill, '
    'or future mutations.'
)

# ── Bounds ──────────────────────────────────────────────────────────────────
LOOKBACK_DAYS_DEFAULT, LOOKBACK_DAYS_MIN, LOOKBACK_DAYS_MAX = 30, 1, 120
CANDIDATE_LIMIT_DEFAULT, CANDIDATE_LIMIT_MIN, CANDIDATE_LIMIT_MAX = 20, 1, 50
ELIGIBLE_TARGET_DEFAULT, ELIGIBLE_TARGET_MIN, ELIGIBLE_TARGET_MAX = 5, 1, 10

_DIGITS_ONLY = re.compile(r'\A[0-9]+\Z')

STOP_REASON_TARGET_REACHED = 'eligible_target_reached'
STOP_REASON_CANDIDATE_LIMIT = 'candidate_limit_reached'
STOP_REASON_POOL_EXHAUSTED = 'candidate_pool_exhausted'

# ── Tables whose content must not move ──────────────────────────────────────
# Every table the game-driven shadow path can reach, plus the dead-letter
# target. ``sync_failures`` is the dead-letter table (services.dead_letter
# writes SyncFailure rows).
FINGERPRINT_TABLES = (
    'game_logs',
    'pitchers',
    'game_ingestion_work_items',
    'postgame_processed_games',
    'scheduled_games',
    'sync_failures',
)

# ── Classifications ─────────────────────────────────────────────────────────
ELIGIBLE = 'eligible'
DUPLICATE_WORK_ITEM_IDENTITY = 'duplicate_work_item_identity'
TARGET_WORK_ITEM_MISSING = 'target_work_item_missing'
TARGET_WORK_ITEM_NOT_COMPLETED = 'target_work_item_not_completed'
REPRESENTED_DATE_UNAVAILABLE = 'represented_date_unavailable'
PLANNER_NOT_EXECUTED = 'planner_not_executed'
GAME_NOT_PLANNABLE = 'game_not_plannable_or_not_final'
SCOPE_NOT_EXACT = 'scope_not_exact'
REQUESTED_GAME_MISSING = 'requested_game_missing'
UNEXPECTED_PLANNED_GAME = 'unexpected_planned_game'
PLANNED_ROW_COUNT_ZERO = 'planned_row_count_zero'
PLAN_PROPOSES_INSERT = 'plan_proposes_insert'
PLAN_PROPOSES_UPDATE = 'plan_proposes_update'
PLAN_CONTAINS_BLOCKED_ROW = 'plan_contains_blocked_row'
PLAN_PROPOSES_BASEBALL_MUTATION = 'plan_proposes_baseball_mutation'
PLAN_PROPOSES_IDENTITY_MUTATION = 'plan_proposes_identity_mutation'
SOURCE_REVISION_MISSING = 'source_revision_missing'
SOURCE_REVISION_MULTIPLE = 'source_revision_multiple'
SOURCE_REVISION_WRONG_GAME = 'source_revision_wrong_game'
PLAN_FINGERPRINT_MISSING = 'plan_fingerprint_missing'
SHADOW_BUDGET_STOP = 'shadow_budget_stop'
SHADOW_EXECUTION_ERROR = 'shadow_execution_error'
READ_ONLY_CONTRACT_VIOLATED = 'read_only_contract_violated'
EVIDENCE_UNPROVEN = 'evidence_unproven'
PLAN_UNKNOWN_ACTION = 'plan_contains_unknown_action'
PLAN_PROHIBITED_ACTION = 'plan_contains_prohibited_action'
PLAN_CHANGED_FIELDS_ON_UNCHANGED_ROW = 'changed_fields_on_unchanged_row'
PLAN_UNCHANGED_COVERAGE_INCOMPLETE = 'unchanged_row_coverage_incomplete'
PLAN_GOVERNANCE_FAILED = 'shared_plan_governance_failed'
SHADOW_STATUS_NOT_COMPLETE = 'shadow_status_not_complete'

# The canonical lane's successful-completion status. The lane can also return
# 'planned', 'disabled', 'scope_invalid', 'scope_mismatch',
# 'plan_authorization_required', 'plan_fingerprint_mismatch', and 'incomplete'
# — none of which is a completed shadow pass.
SHADOW_STATUS_COMPLETE = 'complete'
SHADOW_STATUS_INCOMPLETE = 'incomplete'

# Deterministic precedence, most severe first. A candidate may accumulate
# several reason codes; exactly one of them becomes the primary classification,
# chosen by this order. Declared once so the artifact and the tests agree.
CLASSIFICATION_PRECEDENCE = (
    # 1. read-only contract violation — the audit's own integrity
    READ_ONLY_CONTRACT_VIOLATED,
    # 2. execution error / unproven evidence
    SHADOW_EXECUTION_ERROR,
    EVIDENCE_UNPROVEN,
    SHADOW_BUDGET_STOP,
    SHADOW_STATUS_NOT_COMPLETE,
    # 3. durable-work-item invalidity
    DUPLICATE_WORK_ITEM_IDENTITY,
    TARGET_WORK_ITEM_MISSING,
    TARGET_WORK_ITEM_NOT_COMPLETED,
    REPRESENTED_DATE_UNAVAILABLE,
    # 4. finality / scope failure
    PLANNER_NOT_EXECUTED,
    GAME_NOT_PLANNABLE,
    REQUESTED_GAME_MISSING,
    UNEXPECTED_PLANNED_GAME,
    SCOPE_NOT_EXACT,
    PLANNED_ROW_COUNT_ZERO,
    # 5. mutation / identity failure
    PLAN_UNKNOWN_ACTION,
    PLAN_PROHIBITED_ACTION,
    PLAN_GOVERNANCE_FAILED,
    PLAN_CHANGED_FIELDS_ON_UNCHANGED_ROW,
    PLAN_UNCHANGED_COVERAGE_INCOMPLETE,
    PLAN_PROPOSES_IDENTITY_MUTATION,
    PLAN_PROPOSES_INSERT,
    PLAN_PROPOSES_UPDATE,
    PLAN_CONTAINS_BLOCKED_ROW,
    PLAN_PROPOSES_BASEBALL_MUTATION,
    # 6. revision / fingerprint failure
    SOURCE_REVISION_WRONG_GAME,
    SOURCE_REVISION_MULTIPLE,
    SOURCE_REVISION_MISSING,
    PLAN_FINGERPRINT_MISSING,
    # 7. eligible
    ELIGIBLE,
)

# Reason codes whose presence makes the audit itself unusable rather than the
# candidate merely ineligible.
UNPROVEN_CLASSIFICATIONS = frozenset({
    SHADOW_EXECUTION_ERROR, EVIDENCE_UNPROVEN, SHADOW_BUDGET_STOP,
})

# Lane statuses that map to a specific named refusal rather than a generic
# error. Anything not listed and not SHADOW_STATUS_COMPLETE fails closed as
# shadow_execution_error, so a future status cannot silently become eligible.
SHADOW_STATUS_CLASSIFICATIONS = {
    lane.STATUS_SCOPE_MISMATCH: SCOPE_NOT_EXACT,
    lane.STATUS_SCOPE_INVALID: SCOPE_NOT_EXACT,
    lane.STATUS_PLAN_AUTHORIZATION_REQUIRED: EVIDENCE_UNPROVEN,
    lane.STATUS_PLAN_FINGERPRINT_MISMATCH: PLAN_FINGERPRINT_MISSING,
    SHADOW_STATUS_INCOMPLETE: SHADOW_BUDGET_STOP,
    'disabled': SHADOW_EXECUTION_ERROR,
    'planned': SHADOW_STATUS_NOT_COMPLETE,
}

MAX_REASON_CODES = 8


class ReadOnlyNotEnforced(RuntimeError):
    """The session could not be proven read-only, so nothing is audited."""


class AuditInputError(ValueError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


# ── Input bounds ────────────────────────────────────────────────────────────


def parse_bounded_int(raw, *, name, default, minimum, maximum) -> int:
    if raw is None or str(raw).strip() == '':
        return default
    text_value = str(raw).strip()
    # Digits only, and no leading plus — exactly what the workflow preflight
    # accepts (`^[0-9]+$`). A parser looser than its own gate is a gap.
    if not _DIGITS_ONLY.match(text_value):
        raise AuditInputError(f'{name}_not_an_integer')
    value = int(text_value)
    if value < minimum or value > maximum:
        raise AuditInputError(f'{name}_out_of_bounds')
    return value


def resolve_bounds(*, lookback_days=None, candidate_limit=None,
                   eligible_target_count=None) -> dict:
    lookback = parse_bounded_int(
        lookback_days, name='lookback_days', default=LOOKBACK_DAYS_DEFAULT,
        minimum=LOOKBACK_DAYS_MIN, maximum=LOOKBACK_DAYS_MAX,
    )
    limit = parse_bounded_int(
        candidate_limit, name='candidate_limit',
        default=CANDIDATE_LIMIT_DEFAULT, minimum=CANDIDATE_LIMIT_MIN,
        maximum=CANDIDATE_LIMIT_MAX,
    )
    target = parse_bounded_int(
        eligible_target_count, name='eligible_target_count',
        default=ELIGIBLE_TARGET_DEFAULT, minimum=ELIGIBLE_TARGET_MIN,
        maximum=ELIGIBLE_TARGET_MAX,
    )
    if target > limit:
        raise AuditInputError('eligible_target_count_exceeds_candidate_limit')
    return {
        'lookback_days': lookback,
        'candidate_limit': limit,
        'eligible_target_count': target,
    }


# ── Read-only enforcement ───────────────────────────────────────────────────


def enforce_read_only(session) -> dict:
    """Set the transaction read-only and PROVE a write is refused.

    The canonical pattern from the existing production diagnostics, reused
    rather than reinvented. Fails closed: a session that cannot be proven
    read-only audits nothing. The probe is bounded by ``WHERE 1 = 0`` so it
    touches no row even in the impossible case that it is accepted, and it is
    rolled back either way.
    """
    bind = session.get_bind()
    dialect = getattr(bind.dialect, 'name', '')
    if dialect != 'postgresql':
        raise ReadOnlyNotEnforced(dialect or 'unknown_dialect')

    session.execute(text('SET TRANSACTION READ ONLY'))
    try:
        session.execute(text(
            'UPDATE game_logs SET stat_correction_count = stat_correction_count '
            'WHERE 1 = 0'
        ))
        refused = False
    except Exception:  # noqa: BLE001 - the refusal itself is the signal
        session.rollback()
        session.execute(text('SET TRANSACTION READ ONLY'))
        refused = True

    if not refused:
        raise ReadOnlyNotEnforced('postgresql_read_only_transaction')
    return {
        'dialect': dialect,
        'protection': 'postgresql_read_only_transaction',
        # Reported honestly: the audit DOES issue one SQL write statement — the
        # proof itself. Claiming zero SQL write attempts while executing this
        # probe would be false. What is zero is DURABLE writes: the statement
        # is bounded to zero rows, is expected to be refused, and is rolled
        # back. The full statement text is never reproduced in the artifact.
        'read_only_probe_attempted': True,
        'read_only_probe_count': 1,
        'read_only_probe_statement_class': 'UPDATE',
        'read_only_probe_bounded_to_zero_rows': True,
        'read_only_probe_refused': True,
        'durable_write_attempts': 0,
        'write_probe_refused': True,
    }


def table_fingerprints(session, tables=FINGERPRINT_TABLES) -> dict | None:
    """Content fingerprint per table: every column and timestamp, not a count.

    Computed in the database as one aggregate per table so the whole-table
    content is covered without streaming it into the process. Returns ``None``
    when it cannot be computed, which the caller turns into UNPROVEN.
    """
    bind = session.get_bind()
    if getattr(bind.dialect, 'name', '') != 'postgresql':
        return None
    fingerprints = {}
    try:
        for table in tables:
            digest = session.execute(text(
                f"SELECT md5(coalesce(string_agg(t::text, '|' "
                f"ORDER BY t::text), '')) FROM {table} t"
            )).scalar()
            fingerprints[table] = digest
        return fingerprints
    except Exception:  # noqa: BLE001 - an unprovable fingerprint is UNPROVEN
        return None


def fingerprints_match(before, after) -> bool:
    return bool(before) and bool(after) and before == after


def changed_tables(before, after) -> list[str]:
    if not before or not after:
        return []
    return sorted(
        table for table in set(before) | set(after)
        if before.get(table) != after.get(table)
    )


# ── Candidate discovery ─────────────────────────────────────────────────────


def discover_candidates(*, reference_date, lookback_days, candidate_limit)\
        -> dict:
    """Read-only, deterministic, bounded discovery of completed work items.

    Ordering is declared explicitly and never left to the database default:

        1. most recent ``completed_at`` first
        2. most recent represented date next
        3. lowest ``mlb_game_pk`` as the final stable tie-breaker

    A game id appearing on more than one durable row is a governance defect,
    not something to collapse silently: it is reported and excluded.
    """
    window_start = reference_date - timedelta(days=int(lookback_days))

    rows = (
        GameIngestionWorkItem.query
        .filter(
            GameIngestionWorkItem.status
            == GameIngestionWorkItem.STATUS_COMPLETED,
            GameIngestionWorkItem.completed_at.isnot(None),
            GameIngestionWorkItem.mlb_game_pk.isnot(None),
            GameIngestionWorkItem.mlb_game_pk > 0,
            GameIngestionWorkItem.represented_date >= window_start,
            GameIngestionWorkItem.represented_date <= reference_date,
        )
        .order_by(
            GameIngestionWorkItem.completed_at.desc(),
            GameIngestionWorkItem.represented_date.desc(),
            GameIngestionWorkItem.mlb_game_pk.asc(),
        )
        .all()
    )

    seen: dict[int, int] = {}
    for row in rows:
        seen[row.mlb_game_pk] = seen.get(row.mlb_game_pk, 0) + 1
    duplicates = sorted(pk for pk, count in seen.items() if count > 1)

    ordered: list[dict] = []
    emitted: set[int] = set()
    for row in rows:
        game_pk = row.mlb_game_pk
        if game_pk in duplicates or game_pk in emitted:
            continue
        emitted.add(game_pk)
        ordered.append({
            'game_pk': game_pk,
            'represented_date': (
                row.represented_date.isoformat()
                if row.represented_date else None
            ),
            'completed_at_present': row.completed_at is not None,
            'status': row.status,
        })

    completion_dates = sorted(
        row.completed_at for row in rows if row.completed_at is not None
    )
    return {
        'work_items_considered': len(rows),
        'completed_work_items_found': len(rows),
        'duplicates_excluded': duplicates,
        'duplicate_count': len(duplicates),
        'candidates_selected': ordered[:candidate_limit],
        'candidate_pool_size': len(ordered),
        'ordering': (
            'completed_at DESC, represented_date DESC, mlb_game_pk ASC'
        ),
        'window_start': window_start.isoformat(),
        'window_end': reference_date.isoformat(),
        'earliest_completion_considered': (
            completion_dates[0].isoformat() if completion_dates else None
        ),
        'latest_completion_considered': (
            completion_dates[-1].isoformat() if completion_dates else None
        ),
    }


# ── Candidate classification ────────────────────────────────────────────────


def classify_candidate(*, game_pk, shadow_report, planner_executed,
                       work_item_before, work_item_after,
                       tables_changed=(), shadow_error=False) -> dict:
    """Classify one candidate from positive canonical evidence.

    Nothing is eligible because a failure is absent. Every one of the
    eligibility conditions must be positively observed.
    """
    reasons: list[str] = []
    report = shadow_report or {}

    if tables_changed:
        reasons.append(READ_ONLY_CONTRACT_VIOLATED)
    if shadow_error:
        reasons.append(SHADOW_EXECUTION_ERROR)
    if report.get('budget_stop_triggered'):
        reasons.append(SHADOW_BUDGET_STOP)

    # ── Canonical shadow status, required positively ────────────────────────
    # Only the lane's exact successful-completion status may be eligible. Every
    # other known status maps to a named refusal, and anything unrecognised —
    # including a status a future change introduces — fails closed rather than
    # being read as success because some rows happened to look unchanged.
    shadow_status = report.get('status') if shadow_report else None
    if planner_executed and shadow_report is not None:
        if shadow_status != SHADOW_STATUS_COMPLETE:
            reasons.append(SHADOW_STATUS_CLASSIFICATIONS.get(
                shadow_status, SHADOW_EXECUTION_ERROR,
            ))
            if shadow_status not in SHADOW_STATUS_CLASSIFICATIONS:
                reasons.append(SHADOW_STATUS_NOT_COMPLETE)

    # ── Durable work item ───────────────────────────────────────────────────
    if not work_item_before:
        reasons.append(TARGET_WORK_ITEM_MISSING)
    else:
        if work_item_before.get('status') != (
            GameIngestionWorkItem.STATUS_COMPLETED
        ):
            reasons.append(TARGET_WORK_ITEM_NOT_COMPLETED)
        if not work_item_before.get('represented_date'):
            reasons.append(REPRESENTED_DATE_UNAVAILABLE)
    if work_item_before and not work_item_after:
        reasons.append(TARGET_WORK_ITEM_MISSING)
    if work_item_after and work_item_after.get('status') != (
        GameIngestionWorkItem.STATUS_COMPLETED
    ):
        reasons.append(TARGET_WORK_ITEM_NOT_COMPLETED)

    # ── Planner / finality ──────────────────────────────────────────────────
    if not planner_executed or not shadow_report:
        reasons.append(PLANNER_NOT_EXECUTED)
        return _candidate_result(game_pk, reasons, report, work_item_before)

    scope = qualification.evaluate_scope(report, game_pk=game_pk)
    if scope['planned_game_count'] == 0:
        reasons.append(GAME_NOT_PLANNABLE)
    if scope['missing_requested_game_pks']:
        reasons.append(REQUESTED_GAME_MISSING)
    if scope['unexpected_planned_game_pks']:
        reasons.append(UNEXPECTED_PLANNED_GAME)
    if not (
        scope['execution_scope_exact_match']
        and scope['requested_is_exactly_target']
        and scope['planned_is_exactly_target']
        and scope['duplicate_requested_count'] == 0
    ):
        reasons.append(SCOPE_NOT_EXACT)

    # ── Plan governance, via the shared qualification helpers ───────────────
    # The shared pass is authoritative. Checking only the individual counters
    # would let an action this contract does not recognise, or an `unchanged`
    # row carrying changed fields, fall through to eligible.
    governance = qualification.evaluate_plan_governance(report)
    if governance['planned_row_count'] == 0:
        reasons.append(PLANNED_ROW_COUNT_ZERO)
    if governance['unknown_action_count']:
        reasons.append(PLAN_UNKNOWN_ACTION)
    if governance['prohibited_actions'] or governance[
        'prohibited_action_counts'
    ]:
        reasons.append(PLAN_PROHIBITED_ACTION)
    if 'changed_fields_on_unchanged_row' in governance[
        'prohibited_action_counts'
    ]:
        reasons.append(PLAN_CHANGED_FIELDS_ON_UNCHANGED_ROW)
    if governance['planned_row_count'] and (
        governance['planned_unchanged_count'] != governance['planned_row_count']
    ):
        reasons.append(PLAN_UNCHANGED_COVERAGE_INCOMPLETE)
    if governance['nonzero_mutation_counters']:
        reasons.append(PLAN_GOVERNANCE_FAILED)
    if not governance['all_rows_already_matching']:
        reasons.append(PLAN_GOVERNANCE_FAILED)

    actions = governance['planned_action_counts']
    if actions.get(reconciliation.ACTION_INSERT):
        reasons.append(PLAN_PROPOSES_INSERT)
    if actions.get(reconciliation.ACTION_UPDATE):
        reasons.append(PLAN_PROPOSES_UPDATE)
    if actions.get(reconciliation.ACTION_BLOCKED):
        reasons.append(PLAN_CONTAINS_BLOCKED_ROW)

    identity_counts = governance['planned_identity_action_counts']
    prohibited_identity = any(
        action not in ('unchanged', 'None', 'none')
        for action in identity_counts
    )
    identity_counters = (
        'pitcher_identity_creations', 'pitcher_identity_reactivations',
        'pitcher_identity_metadata_updates', 'pitcher_identity_blocked',
        'pitcher_identity_mutations',
    )
    if prohibited_identity or any(
        governance['planned_mutation_counters'].get(field)
        for field in identity_counters
    ):
        reasons.append(PLAN_PROPOSES_IDENTITY_MUTATION)

    baseball_counters = (
        'complete_mutation_count', 'canonical_outs_corrections',
        'statistical_corrections', 'authority_reconciliations',
        'appearance_team_mutations', 'provenance_only_updates',
        'rows_blocked',
    )
    if any(
        governance['planned_mutation_counters'].get(field)
        for field in baseball_counters
    ):
        reasons.append(PLAN_PROPOSES_BASEBALL_MUTATION)

    # ── Source revision and fingerprint ─────────────────────────────────────
    revisions = qualification.source_revisions(report)
    if not revisions:
        reasons.append(SOURCE_REVISION_MISSING)
    elif len(revisions) > 1:
        reasons.append(SOURCE_REVISION_MULTIPLE)
    else:
        entry = revisions[0]
        if int(entry.get('game_pk') or 0) != int(game_pk):
            reasons.append(SOURCE_REVISION_WRONG_GAME)
        elif not entry.get('source_revision'):
            reasons.append(SOURCE_REVISION_MISSING)

    if not report.get('reconciliation_plan_fingerprint'):
        reasons.append(PLAN_FINGERPRINT_MISSING)

    return _candidate_result(game_pk, reasons, report, work_item_before)


def positive_eligibility(*, reasons, governance, scope, revisions, report,
                         work_item_before, game_pk) -> dict:
    """Every eligibility condition, asserted positively and reported."""
    revision_ok = bool(
        len(revisions) == 1
        and revisions[0].get('source_revision')
        and int(revisions[0].get('game_pk') or 0) == int(game_pk)
    )
    conditions = {
        'no_reason_codes': not reasons,
        'work_item_present': bool(work_item_before),
        'work_item_completed': bool(
            work_item_before
            and work_item_before.get('status')
            == GameIngestionWorkItem.STATUS_COMPLETED
        ),
        'represented_date_present': bool(
            work_item_before and work_item_before.get('represented_date')
        ),
        'shadow_status_complete': (
            (report or {}).get('status') == SHADOW_STATUS_COMPLETE
        ),
        'no_budget_stop': not (report or {}).get('budget_stop_triggered'),
        'exact_scope': bool(scope['execution_scope_exact_match']),
        'planned_is_exactly_target': bool(scope['planned_is_exactly_target']),
        'requested_is_exactly_target': bool(
            scope['requested_is_exactly_target']
        ),
        'no_duplicate_request': scope['duplicate_requested_count'] == 0,
        'planned_rows_present': governance['planned_row_count'] > 0,
        'all_rows_unchanged': (
            governance['planned_row_count'] > 0
            and governance['planned_unchanged_count']
            == governance['planned_row_count']
        ),
        'no_unknown_actions': governance['unknown_action_count'] == 0,
        'no_prohibited_actions': (
            governance['prohibited_actions'] == 0
            and not governance['prohibited_action_counts']
        ),
        'no_nonzero_mutation_counters': not governance[
            'nonzero_mutation_counters'
        ],
        'governance_all_rows_already_matching': (
            governance['all_rows_already_matching'] is True
        ),
        'exactly_one_valid_source_revision': revision_ok,
        'plan_fingerprint_present': bool(
            (report or {}).get('reconciliation_plan_fingerprint')
        ),
    }
    return {
        'conditions': dict(sorted(conditions.items())),
        'unmet_conditions': sorted(
            name for name, met in conditions.items() if not met
        ),
        'all_conditions_met': all(conditions.values()),
    }


def _candidate_result(game_pk, reasons, report, work_item_before) -> dict:
    governance = qualification.evaluate_plan_governance(report)
    scope = qualification.evaluate_scope(report, game_pk=game_pk)
    revisions = qualification.source_revisions(report)

    deduped = []
    for reason in reasons:
        if reason not in deduped:
            deduped.append(reason)
    primary = _primary_classification(deduped)

    # Explicit POSITIVE predicate. `primary == ELIGIBLE` alone would mean
    # "no recognised reason was appended", which is absence of failure — the
    # exact inference this contract refuses everywhere else. Every condition
    # below must be observed true.
    positive = positive_eligibility(
        reasons=deduped, governance=governance, scope=scope,
        revisions=revisions, report=report,
        work_item_before=work_item_before, game_pk=game_pk,
    )
    eligible = bool(primary == ELIGIBLE and positive['all_conditions_met'])
    if primary == ELIGIBLE and not positive['all_conditions_met']:
        # A condition failed without producing a reason code. Fail closed and
        # say so rather than emitting an eligible verdict nobody can justify.
        deduped.append(PLAN_GOVERNANCE_FAILED)
        primary = PLAN_GOVERNANCE_FAILED

    return {
        'game_pk': int(game_pk),
        'represented_date': (work_item_before or {}).get('represented_date'),
        'work_item_status': (work_item_before or {}).get('status'),
        'completed_at_present': bool(
            (work_item_before or {}).get('completed_at_present')
        ),
        'planner_executed': PLANNER_NOT_EXECUTED not in deduped,
        'finality_positively_proven': bool(
            PLANNER_NOT_EXECUTED not in deduped
            and scope['planned_is_exactly_target']
        ),
        'exact_scope': bool(scope['execution_scope_exact_match']),
        'planned_game_count': scope['planned_game_count'],
        'planned_row_count': governance['planned_row_count'],
        'unchanged_row_count': governance['planned_unchanged_count'],
        'planned_action_counts': governance['planned_action_counts'],
        'planned_identity_action_counts': governance[
            'planned_identity_action_counts'
        ],
        'mutation_counters': governance['planned_mutation_counters'],
        'source_revision_count': len(revisions),
        'source_revision_present': bool(
            len(revisions) == 1 and revisions[0].get('source_revision')
        ),
        'plan_fingerprint_present': bool(
            (report or {}).get('reconciliation_plan_fingerprint')
        ),
        'budget_stop': bool((report or {}).get('budget_stop_triggered')),
        'shadow_status': (report or {}).get('status'),
        'shadow_status_is_complete': (
            (report or {}).get('status') == SHADOW_STATUS_COMPLETE
        ),
        'eligibility_conditions': positive['conditions'],
        'unmet_eligibility_conditions': positive['unmet_conditions'],
        'primary_classification': primary,
        'reason_codes': deduped[:MAX_REASON_CODES],
        'eligible': eligible,
    }


def _primary_classification(reasons) -> str:
    for classification in CLASSIFICATION_PRECEDENCE:
        if classification in reasons:
            return classification
    # No failure reason survived: every eligibility condition was positively
    # observed by the checks above, each of which appends on failure.
    return ELIGIBLE


def safe_work_item(row) -> dict | None:
    """Governed view of a durable work item. No completion-proof content."""
    if row is None:
        return None
    return {
        'game_pk': row.mlb_game_pk,
        'status': row.status,
        'represented_date': (
            row.represented_date.isoformat() if row.represented_date else None
        ),
        'completed_at_present': row.completed_at is not None,
        'attempt_count': row.attempt_count,
        'source_revision_present': bool(row.source_revision),
    }


# ── Verdict ─────────────────────────────────────────────────────────────────


def decide(*, candidates, read_only_proof, discovery_available=True) -> dict:
    """Reduce the audit to one result.

    Zero eligible candidates is a COMPLETED audit. Only a proven write, or
    evidence that could not be completed, is a failure.
    """
    failed: list[str] = []
    unproven: list[str] = []

    proof = read_only_proof or {}
    if not proof.get('read_only_enabled'):
        unproven.append('read_only_transaction_unavailable')
    if not proof.get('guard_acquired'):
        unproven.append('writer_guard_unavailable')
    elif not (proof.get('guard_release_attempted') and proof.get('guard_released')):
        unproven.append('writer_guard_release_unproven')
    if not proof.get('before_fingerprints') or not proof.get(
        'after_fingerprints'
    ):
        unproven.append('table_fingerprints_unavailable')
    elif not proof.get('fingerprints_match'):
        failed.append('read_only_contract_violated')
    if not discovery_available:
        unproven.append('candidate_discovery_unavailable')

    for candidate in candidates or ():
        if candidate['primary_classification'] == READ_ONLY_CONTRACT_VIOLATED:
            failed.append('read_only_contract_violated')
        elif candidate['primary_classification'] in UNPROVEN_CLASSIFICATIONS:
            unproven.append('candidate_evidence_unproven')

    eligible = [c for c in (candidates or ()) if c['eligible']]

    if failed:
        result = RESULT_FAILED
    elif unproven:
        result = RESULT_UNPROVEN
    elif eligible:
        result = RESULT_ELIGIBLE_FOUND
    else:
        result = RESULT_NO_ELIGIBLE_CANDIDATE

    counts: dict[str, int] = {}
    for candidate in candidates or ():
        key = candidate['primary_classification']
        counts[key] = counts.get(key, 0) + 1

    return {
        'result': result,
        'exit_code': EXIT_CODES[result],
        'failed_reasons': sorted(set(failed)),
        'unproven_reasons': sorted(set(unproven)),
        'eligible_count': len(eligible),
        'ineligible_count': len([
            c for c in (candidates or ())
            if not c['eligible']
            and c['primary_classification'] not in UNPROVEN_CLASSIFICATIONS
        ]),
        'unproven_count': len([
            c for c in (candidates or ())
            if c['primary_classification'] in UNPROVEN_CLASSIFICATIONS
        ]),
        'classification_counts': dict(sorted(counts.items())),
        'ordered_eligible_game_pks': [c['game_pk'] for c in eligible],
        # First eligible candidate under the declared deterministic ordering.
        'suggested_candidate_game_pk': (
            eligible[0]['game_pk'] if eligible else None
        ),
        'suggestion_is_informational_only': True,
        'non_authorization_statement': NON_AUTHORIZATION_STATEMENT,
    }


def evaluate_candidates(*, candidates, reference_date, eligible_target_count,
                        candidate_limit=None, candidate_pool_size=None,
                        session=None) -> dict:
    """Run the canonical one-game SHADOW lane for each candidate, in order.

    Stops as soon as the eligible target is met; the candidate list is already
    bounded by ``candidate_limit``. Re-asserts the read-only transaction after
    every candidate, because the shadow lane ends with an explicit rollback and
    a rollback starts a fresh transaction without the read-only attribute.
    """
    session = session if session is not None else db.session
    evaluated: list[dict] = []
    stop_reason = STOP_REASON_POOL_EXHAUSTED
    eligible_stop_position = None

    for position, candidate in enumerate(candidates or (), start=1):
        game_pk = candidate['game_pk']

        before_row = GameIngestionWorkItem.query.filter_by(
            mlb_game_pk=game_pk
        ).first()
        work_item_before = safe_work_item(before_row)

        shadow_report = None
        shadow_error = False
        planner_executed = False
        try:
            shadow_report = lane.run_game_driven_ingestion(
                reference_date,
                mode=PERMITTED_INGESTION_MODE,
                only_game_pks=[game_pk],
            )
            planner_executed = True
        except Exception:  # noqa: BLE001 - never leak exception text
            shadow_error = True

        # The lane rolls back at the end of a shadow run, which ends the
        # read-only transaction. Re-assert it before the next read.
        read_only_intact = True
        try:
            session.rollback()
            session.execute(text('SET TRANSACTION READ ONLY'))
        except Exception:  # noqa: BLE001
            read_only_intact = False

        after_row = GameIngestionWorkItem.query.filter_by(
            mlb_game_pk=game_pk
        ).first()
        work_item_after = safe_work_item(after_row)

        entry = classify_candidate(
            game_pk=game_pk,
            shadow_report=shadow_report,
            planner_executed=planner_executed,
            work_item_before=work_item_before,
            work_item_after=work_item_after,
            tables_changed=() if read_only_intact else ('session',),
            shadow_error=shadow_error or not read_only_intact,
        )
        entry['ordering_position'] = position
        evaluated.append(entry)

        if len([e for e in evaluated if e['eligible']]) >= eligible_target_count:
            stop_reason = STOP_REASON_TARGET_REACHED
            eligible_stop_position = position
            break
    else:
        # Every selected candidate was evaluated. Whether that is "the limit"
        # or "the pool ran out" depends on the configured limit, NOT on the
        # list being non-empty — reporting the limit for a 3-item pool with a
        # limit of 20 would misdescribe why the audit stopped.
        selected_count = len(candidates or ())
        limit = candidate_limit
        pool = (
            candidate_pool_size if candidate_pool_size is not None
            else selected_count
        )
        if limit is not None and (
            selected_count >= int(limit) or pool > int(limit)
        ):
            stop_reason = STOP_REASON_CANDIDATE_LIMIT
        else:
            stop_reason = STOP_REASON_POOL_EXHAUSTED

    return {
        'candidates': evaluated,
        'stop_reason': stop_reason,
        'candidates_evaluated': len(evaluated),
        'candidates_selected': len(candidates or ()),
        'candidate_pool_size': (
            candidate_pool_size if candidate_pool_size is not None
            else len(candidates or ())
        ),
        'configured_candidate_limit': candidate_limit,
        'eligible_stop_position': eligible_stop_position,
    }


def digest_for(values) -> str:
    return hashlib.sha256(
        '|'.join(str(value) for value in values).encode('utf-8')
    ).hexdigest()


# Declared so tests can assert the audit reaches the lane in shadow only.
PERMITTED_INGESTION_MODE = lane.MODE_SHADOW

__all__ = [name for name in dir() if not name.startswith('_')]

# Referenced so the identity-governance import is a real dependency of the
# classification vocabulary rather than an unused import.
PERMITTED_IDENTITY_ACTIONS = qualification.PERMITTED_IDENTITY_ACTIONS
IDENTITY_MUTATING_ACTIONS = frozenset(pitcher_identity.MUTATING_ACTIONS)
