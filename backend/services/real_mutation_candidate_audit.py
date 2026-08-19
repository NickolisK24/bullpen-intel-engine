"""Read-only discovery of exact-one-game real-mutation qualification candidates.

Identifies completed durable game-driven work items whose CURRENT canonical
shadow plan is exactly one governed statistical correction, to one existing row,
on one field whose source authority the repository has resolved — and which are
therefore eligible targets for the Manual Game-Driven Real-Mutation
Qualification.

Why it exists
-------------
D-042 established that operator intuition cannot pick a qualification candidate;
a bounded read-only audit must. That reasoning applies with more force here. A
no-op candidate is merely a settled game, and picking the wrong one wastes a
run. A real-mutation candidate is a game the lane intends to CHANGE, so picking
the wrong one is how an unreviewed mutation reaches production.

Read-only, three ways — reusing the exact machinery the no-op candidate audit
already proves in production rather than reimplementing it:

    the public sync advisory lock, acquire-only
    a PostgreSQL read-only transaction with a refused write probe
    before/after content fingerprints across every table the shadow path reaches

Finding zero eligible candidates is a COMPLETED audit, not a failure. Given a
clean shadow corpus, zero is the expected first answer: a real-mutation
candidate exists only while shadow has found a divergence the legacy writer has
not yet resolved.

Nothing here creates a work item, advances a checkpoint, commits, dispatches the
write qualification, or authorizes any write. A candidate this audit reports is
a suggestion to review, never an authorization: the qualification generates and
a human reviews its own current plan, and only that reviewed fingerprint can
authorize a write.

On reported values
------------------
The stored value of the reviewed field is read directly from the canonical row
and reported. The value the plan would WRITE is deliberately not reported: the
lane's safe row report keeps intended values in-process and exports only their
digest, and re-deriving them here would mean a second comparator — exactly the
drift this design exists to prevent. The plan's target digest is reported as
that value's identity, and the qualification's own reviewed shadow plan is where
a human sees the change itself.
"""

from __future__ import annotations

from sqlalchemy import text

from models.game_ingestion_work_item import GameIngestionWorkItem
from models.game_log import GameLog
from models.pitcher import Pitcher
from services import game_driven_ingestion as lane
from services import game_log_reconciliation as reconciliation
from services import noop_qualification_candidate_audit as shared
from services import real_mutation_qualification as qualification
from utils.db import db


SCHEMA_VERSION = '1'
AUDIT_TYPE = 'real_mutation_qualification_candidate_audit'

CONFIRMATION = 'AUDIT_REAL_MUTATION_CANDIDATES'

RESULT_ELIGIBLE_FOUND = 'COMPLETE_ELIGIBLE_FOUND'
RESULT_NO_ELIGIBLE_CANDIDATE = 'COMPLETE_NO_ELIGIBLE_CANDIDATE'
RESULT_FAILED = 'FAILED'
RESULT_UNPROVEN = 'UNPROVEN'

EXIT_CODES = {
    RESULT_ELIGIBLE_FOUND: 0,
    RESULT_NO_ELIGIBLE_CANDIDATE: 0,
    RESULT_FAILED: 1,
    RESULT_UNPROVEN: 2,
}

NON_AUTHORIZATION_STATEMENT = (
    'This audit authorizes nothing. It performs no write, creates no work '
    'item, advances no checkpoint, and dispatches no qualification. A '
    'candidate reported here must still be re-planned and re-reviewed by the '
    'qualification itself before any mutation is authorized.'
)

# The only lane mode this audit may ever run.
PERMITTED_INGESTION_MODE = lane.MODE_SHADOW

# Read-only machinery, reused rather than reimplemented. Each of these is
# already exercised against production by the no-op candidate audit.
AuditInputError = shared.AuditInputError
ReadOnlyProbeViolation = shared.ReadOnlyProbeViolation
enforce_read_only = shared.enforce_read_only
table_fingerprints = shared.table_fingerprints
fingerprints_match = shared.fingerprints_match
changed_tables = shared.changed_tables
discover_candidates = shared.discover_candidates
probe_evidence = shared.probe_evidence
evaluate_probe_evidence = shared.evaluate_probe_evidence
parse_bounded_int = shared.parse_bounded_int
resolve_bounds = shared.resolve_bounds
safe_work_item = shared.safe_work_item
digest_for = shared.digest_for
FINGERPRINT_TABLES = shared.FINGERPRINT_TABLES

STOP_REASON_TARGET_REACHED = shared.STOP_REASON_TARGET_REACHED
STOP_REASON_CANDIDATE_LIMIT = shared.STOP_REASON_CANDIDATE_LIMIT
STOP_REASON_POOL_EXHAUSTED = shared.STOP_REASON_POOL_EXHAUSTED

SHADOW_STATUS_COMPLETE = shared.SHADOW_STATUS_COMPLETE


# ── Classification vocabulary ───────────────────────────────────────────────
ELIGIBLE = 'eligible'

# Structural refusals, shared with the no-op audit's vocabulary where the fact
# being reported is the same fact.
TARGET_WORK_ITEM_MISSING = 'target_work_item_missing'
TARGET_WORK_ITEM_NOT_COMPLETED = 'target_work_item_not_completed'
WORK_ITEM_CHANGED_DURING_AUDIT = 'work_item_changed_during_audit'
PLANNER_NOT_EXECUTED = 'planner_not_executed'
GAME_NOT_PLANNABLE = 'game_not_plannable_or_not_final'
SCOPE_NOT_EXACT = 'scope_not_exact'
UNEXPECTED_PLANNED_GAME = 'unexpected_planned_game'
PLANNED_ROW_COUNT_ZERO = 'planned_row_count_zero'
SHADOW_STATUS_NOT_COMPLETE = 'shadow_status_not_complete'
SHADOW_BUDGET_STOP = 'shadow_budget_stop'
SHADOW_EXECUTION_ERROR = 'shadow_execution_error'
READ_ONLY_CONTRACT_VIOLATED = 'read_only_contract_violated'
SOURCE_REVISION_MISSING = 'source_revision_missing'
SOURCE_REVISION_WRONG_GAME = 'source_revision_wrong_game'
PLAN_FINGERPRINT_MISSING = 'plan_fingerprint_missing'

# Real-mutation specific refusals.
NO_MUTATION_CANDIDATE = 'plan_proposes_no_mutation'
MULTI_ROW_MUTATION = 'plan_proposes_more_than_one_updated_row'
MULTI_FIELD_MUTATION = 'plan_proposes_more_than_one_changed_field'
PLAN_PROPOSES_INSERT = 'plan_proposes_insert'
PLAN_CONTAINS_BLOCKED_ROW = 'plan_contains_blocked_row'
PLAN_PROPOSES_IDENTITY_MUTATION = 'plan_proposes_identity_mutation'
PLAN_PROHIBITED_CATEGORY = 'plan_contains_prohibited_mutation_category'
NOT_A_STATISTICAL_CORRECTION = 'plan_is_not_a_statistical_correction'
FIELD_NOT_GOVERNED_STATISTICAL = 'changed_field_not_governed_statistical'
FIELD_AUTHORITY_UNRESOLVED = 'changed_field_source_authority_unresolved'
TARGET_ROW_NOT_READABLE = 'target_row_not_readable'
TARGET_ROW_ABSENT = 'target_row_absent'
TARGET_ROW_DUPLICATE = 'target_row_duplicated'
PROHIBITED_PLAN_COUNTER = 'prohibited_plan_counter_non_zero'
PLAN_COUNTERS_UNEXPECTED = 'plan_counters_not_exactly_one_correction'

# Reasons that mean "the evidence could not be trusted", as distinct from
# "this candidate is not suitable". Only the former makes the whole audit
# UNPROVEN; the latter is a completed classification.
UNPROVEN_CLASSIFICATIONS = frozenset({
    PLANNER_NOT_EXECUTED,
    SHADOW_EXECUTION_ERROR,
    READ_ONLY_CONTRACT_VIOLATED,
    TARGET_ROW_NOT_READABLE,
})

# Reasons that mean a governed contract was actually violated during the audit.
FAILED_CLASSIFICATIONS = frozenset({
    WORK_ITEM_CHANGED_DURING_AUDIT,
})

# Reported first when a candidate collects several reasons. Ordered from the
# most structural to the most specific so the headline reason explains the
# refusal rather than restating a downstream consequence.
CLASSIFICATION_PRECEDENCE = (
    READ_ONLY_CONTRACT_VIOLATED,
    WORK_ITEM_CHANGED_DURING_AUDIT,
    SHADOW_EXECUTION_ERROR,
    PLANNER_NOT_EXECUTED,
    SHADOW_STATUS_NOT_COMPLETE,
    SHADOW_BUDGET_STOP,
    TARGET_WORK_ITEM_MISSING,
    TARGET_WORK_ITEM_NOT_COMPLETED,
    GAME_NOT_PLANNABLE,
    SCOPE_NOT_EXACT,
    UNEXPECTED_PLANNED_GAME,
    PLANNED_ROW_COUNT_ZERO,
    PLAN_CONTAINS_BLOCKED_ROW,
    PLAN_PROPOSES_INSERT,
    PLAN_PROPOSES_IDENTITY_MUTATION,
    PLAN_PROHIBITED_CATEGORY,
    PROHIBITED_PLAN_COUNTER,
    PLAN_COUNTERS_UNEXPECTED,
    NO_MUTATION_CANDIDATE,
    MULTI_ROW_MUTATION,
    MULTI_FIELD_MUTATION,
    NOT_A_STATISTICAL_CORRECTION,
    FIELD_NOT_GOVERNED_STATISTICAL,
    FIELD_AUTHORITY_UNRESOLVED,
    TARGET_ROW_NOT_READABLE,
    TARGET_ROW_ABSENT,
    TARGET_ROW_DUPLICATE,
    SOURCE_REVISION_WRONG_GAME,
    SOURCE_REVISION_MISSING,
    PLAN_FINGERPRINT_MISSING,
)

MAX_REASON_CODES = 8


def read_stored_value(*, game_pk, pitcher_mlb_id, field) -> dict:
    """Read one governed statistic from the canonical row. Read-only.

    Returns the stored value and how many rows matched, so an absent or
    duplicated appearance is reported as the distinct fact it is rather than
    collapsing into a null value.
    """
    try:
        pitcher = Pitcher.query.filter(
            Pitcher.mlb_id == pitcher_mlb_id
        ).one_or_none()
        if pitcher is None:
            return {'readable': True, 'match_count': 0, 'stored_value': None}
        records = GameLog.query.filter(
            GameLog.mlb_game_pk == game_pk,
            GameLog.pitcher_id == pitcher.id,
        ).all()
        if len(records) != 1:
            return {
                'readable': True,
                'match_count': len(records),
                'stored_value': None,
            }
        return {
            'readable': True,
            'match_count': 1,
            'stored_value': getattr(records[0], field, None),
        }
    except Exception:  # noqa: BLE001 - an unreadable row is never eligible
        return {'readable': False, 'match_count': None, 'stored_value': None}


def classify_candidate(*, game_pk, shadow_report, planner_executed,
                       work_item_before, work_item_after,
                       tables_changed=(), shadow_error=False,
                       stored_value_reader=read_stored_value) -> dict:
    """Classify one candidate from positive canonical evidence.

    Nothing is eligible because a failure is absent. Every eligibility condition
    must be positively observed, and the mutation shape must be exactly the v1
    contract: one update, one field, resolved source authority.
    """
    reasons: list[str] = []
    report = shadow_report or {}

    if tables_changed:
        reasons.append(READ_ONLY_CONTRACT_VIOLATED)
    if shadow_error:
        reasons.append(SHADOW_EXECUTION_ERROR)
    if not planner_executed:
        reasons.append(PLANNER_NOT_EXECUTED)
    if report.get('budget_stop_triggered'):
        reasons.append(SHADOW_BUDGET_STOP)

    # ── Durable work item, before and after ─────────────────────────────────
    if not work_item_before:
        reasons.append(TARGET_WORK_ITEM_MISSING)
    elif work_item_before.get('status') != (
        GameIngestionWorkItem.STATUS_COMPLETED
    ):
        reasons.append(TARGET_WORK_ITEM_NOT_COMPLETED)

    # The audit is read-only. If the row moved while it ran, something wrote.
    if work_item_before != work_item_after:
        reasons.append(WORK_ITEM_CHANGED_DURING_AUDIT)

    # ── Canonical shadow status, required positively ────────────────────────
    if planner_executed and shadow_report is not None:
        if report.get('status') != SHADOW_STATUS_COMPLETE:
            reasons.append(SHADOW_STATUS_NOT_COMPLETE)

    # ── Scope ───────────────────────────────────────────────────────────────
    scope = qualification.evaluate_scope(report, game_pk=game_pk)
    if scope['planned_game_count'] == 0:
        reasons.append(GAME_NOT_PLANNABLE)
    if not scope['execution_scope_exact_match']:
        reasons.append(SCOPE_NOT_EXACT)
    if scope['unexpected_planned_game_pks']:
        reasons.append(UNEXPECTED_PLANNED_GAME)

    # ── Candidate shape, from the one shared contract ───────────────────────
    candidate = qualification.evaluate_candidate_plan(report, game_pk=game_pk)
    if not candidate['planned_row_count']:
        reasons.append(PLANNED_ROW_COUNT_ZERO)
    elif not candidate['mutation_present']:
        # Nothing to correct. A completely clean game is the normal state and
        # is not a defect — it simply is not a real-mutation candidate.
        reasons.append(NO_MUTATION_CANDIDATE)

    reasons.extend(_translate_contract_reasons(candidate))

    # ── Source revision and fingerprint ─────────────────────────────────────
    revision = qualification.single_source_revision(
        qualification.source_revisions(report), game_pk,
    )
    if revision['state'] == 'wrong_game':
        reasons.append(SOURCE_REVISION_WRONG_GAME)
    elif revision['state'] != 'present':
        reasons.append(SOURCE_REVISION_MISSING)

    fingerprint = report.get('reconciliation_plan_fingerprint')
    if not fingerprint:
        reasons.append(PLAN_FINGERPRINT_MISSING)

    # ── Stored value of the reviewed field ──────────────────────────────────
    reviewed = candidate.get('reviewed_mutation')
    stored = None
    if reviewed:
        stored = stored_value_reader(
            game_pk=game_pk,
            pitcher_mlb_id=reviewed['pitcher_mlb_id'],
            field=reviewed['field'],
        )
        if not stored.get('readable'):
            reasons.append(TARGET_ROW_NOT_READABLE)
        elif stored.get('match_count') == 0:
            reasons.append(TARGET_ROW_ABSENT)
        elif (stored.get('match_count') or 0) > 1:
            reasons.append(TARGET_ROW_DUPLICATE)

    return _candidate_result(
        game_pk=game_pk,
        reasons=reasons,
        candidate=candidate,
        reviewed=reviewed,
        stored=stored,
        revision=revision,
        fingerprint=fingerprint,
        scope=scope,
        work_item_before=work_item_before,
    )


def _translate_contract_reasons(candidate) -> list[str]:
    """Map the shared candidate contract's reason codes into audit vocabulary.

    The qualification service owns what a valid candidate is. This audit reports
    the same decision in its own reporting vocabulary rather than reaching a
    second, possibly different, conclusion about the same plan.
    """
    mapping = {
        qualification.FAILED_PLAN_PROPOSES_INSERT: PLAN_PROPOSES_INSERT,
        qualification.FAILED_PLAN_CONTAINS_BLOCKED_ROW:
            PLAN_CONTAINS_BLOCKED_ROW,
        qualification.FAILED_PLAN_MULTI_ROW_MUTATION: MULTI_ROW_MUTATION,
        qualification.FAILED_PLAN_MULTI_FIELD_MUTATION: MULTI_FIELD_MUTATION,
        qualification.FAILED_PLAN_NOT_STATISTICAL_CORRECTION:
            NOT_A_STATISTICAL_CORRECTION,
        qualification.FAILED_PROHIBITED_MUTATION_CATEGORY:
            PLAN_PROHIBITED_CATEGORY,
        qualification.FAILED_PROHIBITED_IDENTITY_ACTION:
            PLAN_PROPOSES_IDENTITY_MUTATION,
        qualification.FAILED_FIELD_NOT_GOVERNED_STATISTICAL:
            FIELD_NOT_GOVERNED_STATISTICAL,
        qualification.FAILED_FIELD_AUTHORITY_UNRESOLVED:
            FIELD_AUTHORITY_UNRESOLVED,
        qualification.FAILED_PROHIBITED_EFFECT_OBSERVED: PROHIBITED_PLAN_COUNTER,
        qualification.FAILED_PLAN_COUNTERS_UNEXPECTED: PLAN_COUNTERS_UNEXPECTED,
        qualification.FAILED_PLAN_UNKNOWN_ACTION: PLAN_CONTAINS_BLOCKED_ROW,
        qualification.FAILED_UNEXPECTED_PLANNED_GAME: UNEXPECTED_PLANNED_GAME,
    }
    return [
        mapping[reason]
        for reason in candidate.get('failed_reasons') or ()
        if reason in mapping
    ]


def _candidate_result(*, game_pk, reasons, candidate, reviewed, stored,
                      revision, fingerprint, scope, work_item_before) -> dict:
    ordered = _ordered_reasons(reasons)
    eligible = not ordered
    return {
        'game_pk': game_pk,
        'eligible': eligible,
        'classification': ELIGIBLE if eligible else ordered[0],
        'reasons': ordered[:MAX_REASON_CODES],
        'reason_count': len(ordered),
        'work_item_status': (work_item_before or {}).get('status'),
        'work_item': work_item_before,
        'planned_row_count': candidate.get('planned_row_count'),
        'planned_update_row_count': candidate.get('planned_update_row_count'),
        'planned_unchanged_count': candidate.get('planned_unchanged_count'),
        'planned_action_counts': candidate.get('planned_action_counts'),
        'planned_identity_action_counts': candidate.get(
            'planned_identity_action_counts'
        ),
        'scope_exact': scope.get('execution_scope_exact_match'),
        'source_revision': revision.get('revision'),
        'source_revision_state': revision.get('state'),
        'plan_fingerprint': fingerprint,
        'field_authority': candidate.get('field_authority'),
        'pitcher_mlb_id': (reviewed or {}).get('pitcher_mlb_id'),
        'field': (reviewed or {}).get('field'),
        'field_category': (reviewed or {}).get('field_category'),
        'difference_classifications': (reviewed or {}).get(
            'difference_classifications'
        ),
        # The stored value is read from the canonical row. The value the plan
        # would write is represented by its digest only — see the module
        # docstring for why it is deliberately not re-derived here.
        'stored_value': (stored or {}).get('stored_value'),
        'stored_row_match_count': (stored or {}).get('match_count'),
        'stored_state_digest': (reviewed or {}).get('stored_state_digest'),
        'canonical_target_state_digest': (reviewed or {}).get(
            'target_state_digest'
        ),
        'target_fields': (reviewed or {}).get('target_fields'),
        'reason_eligible': (
            'Exactly one governed statistical correction to one existing row '
            'on one resolved-authority field, in exactly the requested '
            'completed game, with a durable completed work item, a present '
            'source revision, and a present plan fingerprint.'
            if eligible else None
        ),
    }


def _ordered_reasons(reasons) -> list[str]:
    unique = set(reasons or ())
    ordered = [reason for reason in CLASSIFICATION_PRECEDENCE if reason in unique]
    # Anything not in the precedence list still gets reported, deterministically.
    ordered.extend(sorted(unique - set(CLASSIFICATION_PRECEDENCE)))
    return ordered


def evaluate_candidates(*, candidates, reference_date, eligible_target_count,
                        candidate_limit=None, candidate_pool_size=None,
                        session=None) -> dict:
    """Run the canonical one-game SHADOW lane for each candidate, in order.

    Stops as soon as the eligible target is met. Re-asserts the read-only
    transaction after every candidate, because the shadow lane ends with an
    explicit rollback and a rollback starts a fresh transaction without the
    read-only attribute.
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


def decide(*, candidates, read_only_proof, discovery_available=True) -> dict:
    """Reduce the audit to one terminal result.

    Finding no eligible candidate is a COMPLETED audit. Only a broken read-only
    contract, an untrustworthy evaluation, or unavailable discovery is anything
    worse.
    """
    failed: list[str] = []
    unproven: list[str] = []

    proof = read_only_proof or {}
    failed.extend(proof.get('failed_reasons') or ())
    unproven.extend(proof.get('unproven_reasons') or ())

    if not discovery_available:
        unproven.append('candidate_discovery_unavailable')

    for entry in candidates or ():
        for reason in entry.get('reasons') or ():
            if reason in FAILED_CLASSIFICATIONS:
                failed.append(reason)
            elif reason in UNPROVEN_CLASSIFICATIONS:
                unproven.append(reason)

    eligible = [entry for entry in candidates or () if entry.get('eligible')]

    if failed:
        result = RESULT_FAILED
    elif unproven:
        result = RESULT_UNPROVEN
    elif eligible:
        result = RESULT_ELIGIBLE_FOUND
    else:
        result = RESULT_NO_ELIGIBLE_CANDIDATE

    return {
        'result': result,
        'exit_code': EXIT_CODES[result],
        'failed_reasons': sorted(set(failed)),
        'unproven_reasons': sorted(set(unproven)),
        'eligible_candidate_count': len(eligible),
        'eligible_game_pks': sorted(entry['game_pk'] for entry in eligible),
        'non_authorization_statement': NON_AUTHORIZATION_STATEMENT,
        'unresolved_authority_fields': sorted(
            qualification.UNRESOLVED_SOURCE_AUTHORITY_FIELDS
        ),
        'permitted_ingestion_mode': PERMITTED_INGESTION_MODE,
        'reconciliation_plan_version': (
            reconciliation.RECONCILIATION_PLAN_VERSION
        ),
    }
