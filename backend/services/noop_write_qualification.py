"""Manual exact-scope no-op write qualification.

Proves the game-driven ingestion lane can enter its governed write-capable code
path for exactly one completed game while mutating no baseball data.

What this module is
-------------------
Governance and evidence only. It owns no writer, no comparator, and no
reconciliation logic. Every baseball decision is made by the canonical
components and read back out of their reports:

    services.game_ingestion_planner.plan_game_work   scope + finality
    services.game_driven_ingestion.run_game_driven_ingestion
                                                     the one lane entry point
    services.game_log_reconciliation                 the one planner + digests
    services.pitcher_identity_reconciliation         D-009 identity governance
    services.game_driven_realization                 the realization proof
    services.sync_metadata.acquire_sync_writer_guard the production writer lock

The two-phase shape
-------------------
1. ``shadow``  exclusive to the requested game. Reads only. Produces the
   reconciliation-plan fingerprint and the per-row plan a human reviews.
2. ``write``   exclusive to the same game, authorized by that fingerprint. The
   canonical lane re-fetches, re-plans, and refuses before its first mutation
   if either the source revision or the plan moved.

Step 2's drift check is the lane's own ``_authorize_reviewed_plan``. This module
does not re-implement it — a second comparator is exactly the drift this design
exists to prevent.

What "no-op" means here, precisely
----------------------------------
Measured against the canonical lane, an exclusive write over an
already-matching game produces:

    game_log_rows_written              0
    pitcher_rows_written               0
    appearance_team_rows_written       0
    correction_provenance_rows_written 0
    dead_letters_created               0
    work_items_updated                 1
    work_items_completed               1
    checkpoints_advanced               1
    commits_performed                  1

The first group is BASEBALL DATA. PASS requires every one of them to be zero,
and a single non-zero value is a hard failure.

The second group is the lane's own completion ledger. ``_process_one_game``
claims a work item before fetching and completes it after persisting, whenever
writes are enabled, independently of whether the plan mutates anything. Those
writes are therefore unavoidable on the canonical path. They are NOT reported as
zero and NOT hidden: they are carried in their own labelled group with their
real values, and the artifact states plainly that the lane ledger advanced while
no baseball data changed.

Making them zero would require either bypassing the canonical writer or changing
canonical completion semantics. Both are out of scope here, and both would cost
more safety than they buy.

Nothing in this module authorizes scheduled writes, automated writes,
authoritative publication, backfill, or any future mutation. A fingerprint is
evidence of what a plan was, never a token that permits a later write.
"""

from __future__ import annotations

import hashlib
import re

from models.game_ingestion_work_item import GameIngestionWorkItem
from models.game_log import GameLog
from models.pitcher import Pitcher
from services import game_driven_ingestion as lane
from services import game_log_reconciliation as reconciliation
from services import pitcher_identity_reconciliation as pitcher_identity


SCHEMA_VERSION = '1'
QUALIFICATION_TYPE = 'manual_game_driven_noop_write_qualification'

RESULT_PASS = 'PASS'
RESULT_FAILED = 'FAILED'
RESULT_UNPROVEN = 'UNPROVEN'

EXIT_PASS = 0
EXIT_FAILED = 1
EXIT_UNPROVEN = 2

EXIT_CODES = {
    RESULT_PASS: EXIT_PASS,
    RESULT_FAILED: EXIT_FAILED,
    RESULT_UNPROVEN: EXIT_UNPROVEN,
}

# ── Authorization constants ─────────────────────────────────────────────────
REQUIRED_REPOSITORY = 'NickolisK24/bullpen-intel-engine'
REQUIRED_REF = 'refs/heads/main'
REQUIRED_EVENT_NAME = 'workflow_dispatch'
REQUIRED_ACTOR = 'NickolisK24'
CONFIRMATION_PREFIX = 'QUALIFY_NOOP_GAME_'

_SHA_PATTERN = re.compile(r'\A[0-9a-f]{40}\Z')
_GAME_PK_PATTERN = re.compile(r'\A[0-9]+\Z')

NON_AUTHORIZATION_STATEMENT = (
    'This qualification does not authorize scheduled writes, automated '
    'writes, authoritative publication, backfill, or future mutations.'
)

# ── Reason codes ────────────────────────────────────────────────────────────
# FAILED: a definite contract violation was observed.
FAILED_EVENT_NOT_WORKFLOW_DISPATCH = 'event_not_workflow_dispatch'
FAILED_REPOSITORY_NOT_AUTHORIZED = 'repository_not_authorized'
FAILED_ACTOR_NOT_AUTHORIZED = 'actor_not_authorized'
FAILED_REF_NOT_MAIN = 'ref_not_main'
FAILED_EXPECTED_SHA_MALFORMED = 'expected_head_sha_malformed'
FAILED_EXPECTED_SHA_MISMATCH = 'expected_head_sha_mismatch'
FAILED_CONFIRMATION_MISMATCH = 'confirmation_mismatch'
FAILED_GAME_PK_EMPTY = 'game_pk_empty'
FAILED_GAME_PK_NOT_AN_INTEGER = 'game_pk_not_a_single_integer'
FAILED_GAME_PK_NOT_POSITIVE = 'game_pk_not_positive'
FAILED_GAME_NOT_PLANNABLE = 'requested_game_not_plannable_or_not_final'
FAILED_SCOPE_NOT_EXACT = 'execution_scope_not_exact'
FAILED_REQUESTED_COUNT_NOT_ONE = 'requested_game_count_not_one'
FAILED_PLANNED_COUNT_NOT_ONE = 'planned_game_count_not_one'
FAILED_FETCHED_COUNT_NOT_ONE = 'fetched_game_count_not_one'
FAILED_COMPLETED_COUNT_NOT_ONE = 'completed_game_count_not_one'
FAILED_DUPLICATE_REQUESTED_GAME = 'duplicate_requested_game'
FAILED_UNEXPECTED_PLANNED_GAME = 'unexpected_planned_game'
FAILED_MISSING_REQUESTED_GAME = 'missing_requested_game'
FAILED_PLAN_PROPOSES_MUTATION = 'plan_proposes_mutation'
FAILED_PLAN_UNKNOWN_ACTION = 'plan_contains_unknown_action'
FAILED_PROHIBITED_IDENTITY_ACTION = 'plan_proposes_identity_mutation'
FAILED_SOURCE_REVISION_CHANGED = 'source_revision_changed_before_execution'
FAILED_PLAN_FINGERPRINT_CHANGED = 'plan_fingerprint_changed_before_execution'
FAILED_BASEBALL_DATA_MUTATED = 'baseball_data_mutation_detected'
FAILED_STATE_DIGEST_MISMATCH = 'before_after_state_digest_mismatch'
FAILED_REALIZATION_UNRESOLVED = 'realization_reported_unresolved_rows'
FAILED_PUBLICATION_AUTHORITATIVE = 'publication_authoritative_enabled'
FAILED_WRITES_NOT_ENABLED = 'write_capable_path_not_entered'
FAILED_LANE_STATUS_NOT_COMPLETE = 'lane_run_did_not_complete'
FAILED_ARTIFACT_FORBIDDEN_CONTENT = 'artifact_forbidden_content_detected'

# UNPROVEN: trustworthy evidence could not be completed.
UNPROVEN_PRE_READBACK_UNAVAILABLE = 'pre_execution_readback_unavailable'
UNPROVEN_POST_READBACK_UNAVAILABLE = 'post_execution_readback_unavailable'
UNPROVEN_REALIZATION_UNAVAILABLE = 'realization_unavailable'
UNPROVEN_SOURCE_REVISION_MISSING = 'source_revision_missing'
UNPROVEN_PLAN_FINGERPRINT_MISSING = 'plan_fingerprint_missing'
UNPROVEN_EFFECT_COUNTERS_MISSING = 'execution_effect_counters_incomplete'
UNPROVEN_WRITER_GUARD_UNAVAILABLE = 'writer_guard_unavailable'
UNPROVEN_SHADOW_PHASE_UNUSABLE = 'shadow_phase_produced_no_usable_plan'
UNPROVEN_ARTIFACT_SCAN_UNAVAILABLE = 'artifact_scan_unavailable'
UNPROVEN_ARTIFACT_BUILD_FAILED = 'artifact_construction_failed'
UNPROVEN_LANE_ERROR = 'lane_execution_error'

# ── Effect groups ───────────────────────────────────────────────────────────
# Baseball data. Every one of these MUST be zero for PASS.
BASEBALL_DATA_EFFECT_FIELDS = (
    'game_log_rows_written',
    'pitcher_rows_written',
    'appearance_team_rows_written',
    'correction_provenance_rows_written',
    'dead_letters_created',
)

# The lane's own completion ledger. Reported with real values, never zeroed and
# never suppressed. See the module docstring for why these cannot be zero on the
# canonical path.
LANE_BOOKKEEPING_EFFECT_FIELDS = (
    'work_items_created',
    'work_items_updated',
    'work_items_completed',
    'checkpoints_advanced',
    'commits_performed',
)

REQUIRED_EFFECT_FIELDS = (
    ('writes_enabled', 'publication_authoritative')
    + BASEBALL_DATA_EFFECT_FIELDS
    + LANE_BOOKKEEPING_EFFECT_FIELDS
)

# Plan-level counters that must all be zero for a genuine no-op.
PROJECTED_MUTATION_COUNTERS = (
    'rows_inserted',
    'rows_updated',
    'rows_blocked',
    'statistical_corrections',
    'authority_reconciliations',
    'provenance_only_updates',
    'canonical_outs_corrections',
    'pitcher_identity_mutations',
    'pitcher_identity_creations',
    'pitcher_identity_reactivations',
    'pitcher_identity_metadata_updates',
    'pitcher_identity_blocked',
    'appearance_team_mutations',
    'complete_mutation_count',
)

KNOWN_ACTIONS = frozenset({
    reconciliation.ACTION_UNCHANGED,
    reconciliation.ACTION_INSERT,
    reconciliation.ACTION_UPDATE,
    reconciliation.ACTION_BLOCKED,
})

# The only row action a no-op qualification may contain.
PERMITTED_ACTIONS = frozenset({reconciliation.ACTION_UNCHANGED})

# The only identity decisions a no-op qualification may contain. Creation and
# reactivation are identity MUTATIONS and are refused here even though D-009
# permits them in a normal governed run.
PERMITTED_IDENTITY_ACTIONS = frozenset({
    pitcher_identity.ACTION_UNCHANGED,
    None,
})

# Canonical governed field vocabulary, reused rather than redeclared, so the
# before/after digest compares exactly the fields the reconciliation contract
# governs. Provenance and derived companions are excluded by construction:
# a provenance timestamp moving is not a baseball change, and a decimal
# companion difference is never a baseball repair (D-008).
STATE_DIGEST_FIELDS = tuple(sorted(
    set(
        reconciliation.STATISTICAL_FIELDS
        + reconciliation.ROLE_SIGNAL_FIELDS
        + reconciliation.GAME_METADATA_FIELDS
        + reconciliation.APPEARANCE_TEAM_FIELDS
    )
    - set(reconciliation.PROVENANCE_FIELDS)
    # ``innings_pitched`` is a derived decimal companion of the integer
    # authority ``innings_pitched_outs`` (D-008). Digesting it would let a
    # representation difference read as a state change, which is precisely the
    # class of false positive the innings semantics contract exists to prevent.
    - set(reconciliation.DERIVED_COMPANION_FIELDS)
))


# ── Lane bookkeeping governance ─────────────────────────────────────────────
# The approved split permits the lane's own completion ledger to move. It does
# NOT permit it to move arbitrarily. Everything below governs the exact shape
# and scope of that movement.
#
# This lane has no separate checkpoint table: ``checkpoints_advanced`` is
# recorded at the same site that completes the work item, so the work-item row
# carries BOTH the lifecycle state and the checkpoint state. They are split
# into two named field groups here so the evidence can report them distinctly
# rather than pretending a second table exists.

WORK_ITEM_COLUMNS = tuple(
    column.name for column in GameIngestionWorkItem.__table__.columns
)

# Checkpoint state: what the lane durably asserts about the game's ingestion.
BOOKKEEPING_CHECKPOINT_FIELDS = (
    'status',
    'completed_at',
    'source_revision',
    'rows_expected',
    'rows_reconciled',
    'relief_rows_reconciled',
    'correction_count',
    'completion_proof',
)

# Lifecycle state: how the lane got there.
BOOKKEEPING_LIFECYCLE_FIELDS = (
    'candidate_reason',
    'criticality',
    'attempt_count',
    'first_attempted_at',
    'last_attempted_at',
    'error_class',
    'sync_run_id',
    'updated_at',
)

# MEASURED, not assumed. A no-op exclusive write over an EXISTING completed
# work item was run through the canonical PostgreSQL-backed path; exactly these
# six fields moved:
#
#   candidate_reason    prior reason -> explicit_repair (exclusive scope always
#                       plans as an explicit repair; unchanged when the stored
#                       reason was already explicit_repair, so this field is
#                       permitted-to-change rather than required-to-change)
#   attempt_count       +1
#   last_attempted_at   new timestamp
#   completed_at        new timestamp
#   completion_proof    re-stamped with what THIS run did (inserted 1 -> 0)
#   updated_at          onupdate timestamp
#
# Every other column held, including status, source_revision, rows_expected,
# rows_reconciled, relief_rows_reconciled, correction_count, error_class,
# first_attempted_at, and all game identity fields.
BOOKKEEPING_ALLOWED_CHANGED_FIELDS = frozenset({
    'candidate_reason',
    'attempt_count',
    'last_attempted_at',
    'completed_at',
    'completion_proof',
    'updated_at',
})

BOOKKEEPING_REQUIRED_UNCHANGED_FIELDS = tuple(sorted(
    set(WORK_ITEM_COLUMNS) - BOOKKEEPING_ALLOWED_CHANGED_FIELDS
))

# The exact canonical delta. Deliberately exact integers rather than ``>= 1``:
# the measurement produced one deterministic outcome, so a range would permit
# behaviour nobody has observed.
EXPECTED_LANE_BOOKKEEPING_DELTA = {
    'work_items_created': 0,
    'work_items_updated': 1,
    'work_items_completed': 1,
    'checkpoints_advanced': 1,
    'commits_performed': 1,
}

# The work item must already exist and must already be completed. A first
# production qualification does not create lane state.
REQUIRED_WORK_ITEM_STATUS_BEFORE = GameIngestionWorkItem.STATUS_COMPLETED
REQUIRED_WORK_ITEM_STATUS_AFTER = GameIngestionWorkItem.STATUS_COMPLETED

FAILED_TARGET_WORK_ITEM_MISSING = 'target_work_item_missing'
FAILED_UNEXPECTED_WORK_ITEM_CREATION = 'unexpected_work_item_creation'
FAILED_UNEXPECTED_BOOKKEEPING_COUNTER = 'unexpected_bookkeeping_counter'
FAILED_UNEXPECTED_WORK_ITEM_FIELD_CHANGE = 'unexpected_work_item_field_change'
FAILED_UNRELATED_WORK_ITEM_CHANGED = 'unrelated_work_item_changed'
FAILED_UNRELATED_CHECKPOINT_CHANGED = 'unrelated_checkpoint_changed'
FAILED_CHECKPOINT_DELTA_MISMATCH = 'checkpoint_delta_mismatch'
FAILED_COMMIT_COUNT_MISMATCH = 'commit_count_mismatch'
FAILED_WORK_ITEM_STATUS_UNEXPECTED = 'work_item_status_unexpected'
FAILED_ATTEMPT_COUNT_DELTA_UNEXPECTED = 'attempt_count_delta_unexpected'
UNPROVEN_BOOKKEEPING_READBACK_UNAVAILABLE = 'bookkeeping_readback_unavailable'

# Fingerprint and source-revision positive proof.
FAILED_PLAN_FINGERPRINT_MISMATCH = 'plan_fingerprint_mismatch'
UNPROVEN_AUTHORIZED_FINGERPRINT_MISSING = 'authorized_plan_fingerprint_missing'
FAILED_SOURCE_REVISION_WRONG_GAME = 'source_revision_for_wrong_game'
UNPROVEN_WRITE_SOURCE_REVISION_MISSING = 'write_phase_source_revision_missing'

# Writer guard proof.
UNPROVEN_WRITER_GUARD_RELEASE_UNPROVEN = 'writer_guard_release_unproven'


# ── Execution-state evidence ────────────────────────────────────────────────
# Production run 30862655470 refused at the missing-work-item precondition,
# before the planner ever ran, and the artifact still reported
# ``finality_proven_by_planner: true`` — because that field was derived from
# the ABSENCE of a "not plannable" failure rather than from positive planner
# evidence. The refusal was correct; the evidence was not.
#
# These flags record what actually executed. Each is false until the step it
# names has genuinely happened, so an early refusal cannot inherit a positive
# claim from a step that never ran.

def execution_state(*, work_item_precondition_checked=False,
                    work_item_precondition_passed=False,
                    planner_phase_entered=False,
                    shadow_report=None, game_pk=None) -> dict:
    """Report which phases actually executed, and what the planner proved.

    ``finality_proven_by_planner`` is True ONLY when the planner ran and
    positively planned exactly the requested game under finality authority. It
    is None when the check never executed, and False when it executed and did
    not prove finality. It is never inferred from a missing failure reason.
    """
    finality_check_executed = bool(
        planner_phase_entered and shadow_report is not None
    )
    finality_proven = None
    if finality_check_executed:
        planned = [
            _as_int(value)
            for value in ((shadow_report or {}).get('planned_game_pks') or ())
        ]
        finality_proven = bool(
            game_pk is not None and planned == [int(game_pk)]
        )
    return {
        'work_item_precondition_checked': bool(work_item_precondition_checked),
        'work_item_precondition_passed': bool(work_item_precondition_passed),
        'planner_phase_entered': bool(planner_phase_entered),
        'finality_check_executed': finality_check_executed,
        'finality_proven_by_planner': finality_proven,
    }


def render_finality(state) -> str:
    """Human-readable finality cell. Never renders ``True`` for a check that
    did not run."""
    if not (state or {}).get('finality_check_executed'):
        return 'not executed'
    return 'proven' if state.get('finality_proven_by_planner') else 'not proven'


class QualificationInputError(ValueError):
    """A supplied operator input is not usable. Carries a safe reason code."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


# ── Input parsing ───────────────────────────────────────────────────────────


def parse_game_pk(raw) -> int:
    """Parse exactly one positive integer game id.

    Deliberately strict: a list, a range, a date, a wildcard, or anything with
    separators is refused rather than reinterpreted. "Exactly one game" is the
    entire safety property, so it is enforced at the narrowest possible point.
    """
    if raw is None:
        raise QualificationInputError(FAILED_GAME_PK_EMPTY)
    text = str(raw).strip()
    if not text:
        raise QualificationInputError(FAILED_GAME_PK_EMPTY)
    if not _GAME_PK_PATTERN.match(text):
        raise QualificationInputError(FAILED_GAME_PK_NOT_AN_INTEGER)
    value = int(text)
    if value <= 0:
        raise QualificationInputError(FAILED_GAME_PK_NOT_POSITIVE)
    return value


def expected_confirmation(game_pk) -> str:
    return f'{CONFIRMATION_PREFIX}{int(game_pk)}'


def normalize_sha(raw) -> str:
    return str(raw or '').strip().lower()


# ── Authorization ───────────────────────────────────────────────────────────


def validate_authorization(context, *, game_pk) -> list[str]:
    """Return every authorization reason code that failed.

    Every condition is evaluated rather than short-circuiting, so the artifact
    records all of them instead of only the first.
    """
    failures: list[str] = []

    if str(context.get('event_name') or '') != REQUIRED_EVENT_NAME:
        failures.append(FAILED_EVENT_NOT_WORKFLOW_DISPATCH)
    if str(context.get('repository') or '') != REQUIRED_REPOSITORY:
        failures.append(FAILED_REPOSITORY_NOT_AUTHORIZED)
    if str(context.get('actor') or '') != REQUIRED_ACTOR:
        failures.append(FAILED_ACTOR_NOT_AUTHORIZED)
    if str(context.get('ref') or '') != REQUIRED_REF:
        failures.append(FAILED_REF_NOT_MAIN)

    expected_sha = normalize_sha(context.get('expected_head_sha'))
    actual_sha = normalize_sha(context.get('github_sha'))
    if not _SHA_PATTERN.match(expected_sha):
        failures.append(FAILED_EXPECTED_SHA_MALFORMED)
    elif not _SHA_PATTERN.match(actual_sha) or expected_sha != actual_sha:
        failures.append(FAILED_EXPECTED_SHA_MISMATCH)

    supplied = str(context.get('confirmation') or '')
    if supplied != expected_confirmation(game_pk):
        failures.append(FAILED_CONFIRMATION_MISMATCH)

    return failures


def sanitize_note(raw, *, limit=280) -> str:
    """Reduce a free-text operator note to a safe, bounded token set.

    The note never affects authorization. It is reported, so it is stripped to
    characters that cannot carry a credential, URL, path, or header.
    """
    text = str(raw or '')
    kept = re.sub(r'[^A-Za-z0-9 .,_-]', ' ', text)
    return re.sub(r'\s+', ' ', kept).strip()[:limit]


# ── Plan governance ─────────────────────────────────────────────────────────


def plan_rows(report) -> list[dict]:
    return [
        row
        for game in (report.get('games') or ())
        for row in (game.get('rows') or ())
    ]


def evaluate_plan_governance(report) -> dict:
    """Classify every planned row. Any proposed mutation is a refusal.

    A row is acceptable only when the canonical planner said ``unchanged`` and
    proposed no identity decision beyond ``unchanged``. Anything else — an
    insert, an update, a delete, a block, an outs correction, a team
    reassignment, an identity creation, or an action this contract does not
    recognise — is counted as prohibited.
    """
    rows = plan_rows(report)
    action_counts: dict[str, int] = {}
    identity_action_counts: dict[str, int] = {}
    prohibited: dict[str, int] = {}
    unknown_actions = 0

    for row in rows:
        action = row.get('action')
        key = str(action)
        action_counts[key] = action_counts.get(key, 0) + 1
        if action not in KNOWN_ACTIONS:
            unknown_actions += 1
            prohibited[f'unknown_action:{key}'] = (
                prohibited.get(f'unknown_action:{key}', 0) + 1
            )
        elif action not in PERMITTED_ACTIONS:
            prohibited[f'action:{key}'] = prohibited.get(f'action:{key}', 0) + 1

        identity_action = row.get('pitcher_identity_action')
        identity_key = str(identity_action)
        identity_action_counts[identity_key] = (
            identity_action_counts.get(identity_key, 0) + 1
        )
        if identity_action not in PERMITTED_IDENTITY_ACTIONS:
            prohibited[f'identity:{identity_key}'] = (
                prohibited.get(f'identity:{identity_key}', 0) + 1
            )

        # A row the planner called unchanged must also carry no changed field.
        # Belt and braces: the action and the field list are produced by the
        # same planner, so disagreement between them is itself a defect.
        if row.get('changed_fields'):
            prohibited['changed_fields_on_unchanged_row'] = (
                prohibited.get('changed_fields_on_unchanged_row', 0) + 1
            )

    counters = {
        field: _as_int(report.get(field))
        for field in PROJECTED_MUTATION_COUNTERS
    }
    nonzero_counters = {
        field: value for field, value in counters.items() if value != 0
    }

    return {
        'planned_row_count': len(rows),
        'planned_unchanged_count': action_counts.get(
            reconciliation.ACTION_UNCHANGED, 0
        ),
        'planned_action_counts': dict(sorted(action_counts.items())),
        'planned_identity_action_counts': dict(
            sorted(identity_action_counts.items())
        ),
        'planned_mutation_counters': dict(sorted(counters.items())),
        'nonzero_mutation_counters': dict(sorted(nonzero_counters.items())),
        'prohibited_action_counts': dict(sorted(prohibited.items())),
        'prohibited_actions': sum(prohibited.values()),
        'unknown_action_count': unknown_actions,
        'all_rows_already_matching': bool(
            rows
            and not prohibited
            and not nonzero_counters
            and len(rows) == action_counts.get(reconciliation.ACTION_UNCHANGED, 0)
        ),
    }


def evaluate_scope(report, *, game_pk) -> dict:
    """Prove requested scope is exactly the one requested game."""
    requested = [_as_int(value) for value in (report.get('requested_game_pks') or ())]
    planned = [_as_int(value) for value in (report.get('planned_game_pks') or ())]
    unexpected = [
        _as_int(value) for value in (report.get('unexpected_planned_game_pks') or ())
    ]
    missing = [
        _as_int(value) for value in (report.get('missing_requested_game_pks') or ())
    ]
    return {
        'requested_game_pks': requested,
        'requested_game_count': len(requested),
        'planned_game_pks': planned,
        'planned_game_count': len(planned),
        # Fetch OPERATIONS, not distinct games. An authorized exclusive write
        # legitimately fetches the same single game twice: once to recompute the
        # plan for the reviewed-fingerprint comparison, and once to execute it.
        # Requiring one operation here would refuse the very drift re-validation
        # the contract asks for, so the count is reported and the distinct-game
        # property is asserted separately.
        'fetch_operations': _as_int(report.get('games_fetched')),
        'games_attempted': _as_int(report.get('games_attempted')),
        'distinct_games_fetched': len(planned),
        'games_completed': _as_int(report.get('games_completed')),
        'duplicate_requested_count': _as_int(
            report.get('duplicate_requested_count')
        ),
        'unexpected_planned_game_pks': unexpected,
        'missing_requested_game_pks': missing,
        'execution_scope_mode': report.get('execution_scope_mode'),
        'execution_scope_exact_match': bool(
            report.get('execution_scope_exact_match')
        ),
        'requested_is_exactly_target': requested == [int(game_pk)],
        'planned_is_exactly_target': planned == [int(game_pk)],
    }


def _single_revision(entries, game_pk) -> dict:
    """Require exactly one non-null revision, for exactly the requested game.

    States: ``present`` (proven), ``wrong_game`` (a definite violation),
    ``missing`` / ``multiple`` / ``null`` (unproven).
    """
    entries = list(entries or ())
    if not entries:
        return {'state': 'missing', 'revision': None}
    if len(entries) > 1:
        return {'state': 'multiple', 'revision': None}
    entry = entries[0]
    if _as_int(entry.get('game_pk')) != int(game_pk):
        return {'state': 'wrong_game', 'revision': None}
    if not entry.get('source_revision'):
        return {'state': 'null', 'revision': None}
    return {'state': 'present', 'revision': entry['source_revision']}


def source_revisions(report) -> list[dict]:
    return [
        {
            'game_pk': _as_int(game.get('game_pk')),
            'source_revision': game.get('source_revision'),
        }
        for game in (report.get('games') or ())
    ]


# ── Canonical state readback ────────────────────────────────────────────────


def read_canonical_state(rows) -> dict | None:
    """Read stored canonical state for exactly the planned rows.

    Returns ``None`` when the read cannot be completed — the caller turns that
    into UNPROVEN rather than assuming the state was unchanged.
    """
    try:
        mlb_ids = sorted({
            row.get('pitcher_mlb_id') for row in rows
            if row.get('pitcher_mlb_id') is not None
        })
        game_pks = sorted({
            row.get('game_pk') for row in rows
            if row.get('game_pk') is not None
        })
        if not mlb_ids or not game_pks:
            return None

        local_ids = {
            pitcher.mlb_id: pitcher.id
            for pitcher in Pitcher.query.filter(Pitcher.mlb_id.in_(mlb_ids)).all()
        }
        stored: dict = {}
        for record in GameLog.query.filter(
            GameLog.mlb_game_pk.in_(game_pks)
        ).all():
            stored.setdefault((record.pitcher_id, record.mlb_game_pk), []).append(
                record
            )

        entries = []
        for row in rows:
            local_id = local_ids.get(row.get('pitcher_mlb_id'))
            matches = stored.get((local_id, row.get('game_pk'))) or []
            entries.append((
                _as_int(row.get('game_pk')),
                _as_int(row.get('pitcher_mlb_id')),
                len(matches),
                # Canonical digest helper over the canonical field vocabulary.
                reconciliation.stored_state_digest(
                    matches[0], STATE_DIGEST_FIELDS
                ) if len(matches) == 1 else '',
            ))

        return {
            'available': True,
            'row_count': sum(entry[2] for entry in entries),
            'identity_count': len([
                mlb_id for mlb_id in mlb_ids if local_ids.get(mlb_id) is not None
            ]),
            'projected_row_count': len(rows),
            'digest': _digest_entries(entries),
        }
    except Exception:  # noqa: BLE001 - a failed read is UNPROVEN, never PASS
        return None


def read_lane_bookkeeping(game_pk) -> dict | None:
    """Read the target work item and fingerprint every unrelated one.

    Returns ``None`` when the read cannot be completed — the caller turns that
    into UNPROVEN rather than assuming nothing moved. A present result with
    ``target`` of ``None`` means the work item genuinely does not exist, which
    is a refusal rather than an unproven state.

    The unrelated digests are computed while the writer guard is held, so
    nothing else can be writing them between the two reads.
    """
    try:
        target = None
        unrelated_full = []
        unrelated_checkpoint = []
        for item in GameIngestionWorkItem.query.order_by(
            GameIngestionWorkItem.mlb_game_pk
        ).all():
            row = {
                column: getattr(item, column) for column in WORK_ITEM_COLUMNS
            }
            if item.mlb_game_pk == int(game_pk):
                target = row
                continue
            unrelated_full.append((
                item.mlb_game_pk,
                tuple(f'{key}={row[key]!r}' for key in WORK_ITEM_COLUMNS),
            ))
            unrelated_checkpoint.append((
                item.mlb_game_pk,
                tuple(
                    f'{key}={row[key]!r}'
                    for key in BOOKKEEPING_CHECKPOINT_FIELDS
                ),
            ))

        return {
            'available': True,
            'target': target,
            'target_present': target is not None,
            'unrelated_count': len(unrelated_full),
            'unrelated_work_items_digest': _digest_pairs(unrelated_full),
            'unrelated_checkpoints_digest': _digest_pairs(unrelated_checkpoint),
        }
    except Exception:  # noqa: BLE001 - a failed read is UNPROVEN, never PASS
        return None


def _digest_pairs(pairs) -> str:
    encoded = '|'.join(
        f'{game_pk}:' + ','.join(fields)
        for game_pk, fields in sorted(pairs, key=lambda pair: pair[0])
    )
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def safe_work_item_state(row) -> dict:
    """Governed, reportable view of one work item.

    Field NAMES and small governed scalars only. Timestamps are reported as
    presence rather than value, and ``completion_proof`` as a digest, so the
    evidence cannot carry payload fragments.
    """
    if not row:
        return {}
    state = {}
    for key in WORK_ITEM_COLUMNS:
        value = row.get(key)
        if key in ('completion_proof',):
            state[key] = (
                hashlib.sha256(
                    repr(value).encode('utf-8')
                ).hexdigest()[:16] if value is not None else None
            )
        elif hasattr(value, 'isoformat'):
            state[key] = 'present'
        else:
            state[key] = value
    return state


def changed_bookkeeping_fields(before, after) -> list[str]:
    if not before or not after:
        return []
    return sorted(
        key for key in WORK_ITEM_COLUMNS
        if before.get(key) != after.get(key)
    )


def evaluate_lane_bookkeeping(before, after, effects) -> dict:
    """Govern the exact shape and scope of the lane ledger movement.

    Returns failed/unproven reason codes plus the reportable evidence. The
    permitted movement is the one that was MEASURED through the canonical
    PostgreSQL path; anything outside it refuses.
    """
    failed: list[str] = []
    unproven: list[str] = []

    if not before or not before.get('available'):
        unproven.append(UNPROVEN_BOOKKEEPING_READBACK_UNAVAILABLE)
    if not after or not after.get('available'):
        unproven.append(UNPROVEN_BOOKKEEPING_READBACK_UNAVAILABLE)

    before = before or {}
    after = after or {}
    target_before = before.get('target')
    target_after = after.get('target')

    if before.get('available') and not before.get('target_present'):
        # A first production qualification requires an EXISTING durable item.
        failed.append(FAILED_TARGET_WORK_ITEM_MISSING)

    changed = changed_bookkeeping_fields(target_before, target_after)
    unexpected_changed = sorted(
        set(changed) - BOOKKEEPING_ALLOWED_CHANGED_FIELDS
    )
    if unexpected_changed:
        failed.append(FAILED_UNEXPECTED_WORK_ITEM_FIELD_CHANGE)

    if target_before and target_after:
        if target_before.get('status') != REQUIRED_WORK_ITEM_STATUS_BEFORE:
            failed.append(FAILED_WORK_ITEM_STATUS_UNEXPECTED)
        if target_after.get('status') != REQUIRED_WORK_ITEM_STATUS_AFTER:
            failed.append(FAILED_WORK_ITEM_STATUS_UNEXPECTED)
        attempts_before = _as_int(target_before.get('attempt_count'))
        attempts_after = _as_int(target_after.get('attempt_count'))
        if attempts_after - attempts_before != 1:
            failed.append(FAILED_ATTEMPT_COUNT_DELTA_UNEXPECTED)

    # Unrelated state must be byte-identical across the write.
    if before.get('available') and after.get('available'):
        if before.get('unrelated_work_items_digest') != after.get(
            'unrelated_work_items_digest'
        ):
            failed.append(FAILED_UNRELATED_WORK_ITEM_CHANGED)
        if before.get('unrelated_checkpoints_digest') != after.get(
            'unrelated_checkpoints_digest'
        ):
            failed.append(FAILED_UNRELATED_CHECKPOINT_CHANGED)

    # The counters themselves must match the measured delta exactly.
    #
    # When the effect block is unavailable there is nothing to compare against.
    # Comparing anyway would read every absent counter as 0 and manufacture a
    # FAILED out of missing evidence — the caller already records that absence
    # as UNPROVEN, which is the honest verdict.
    effects = effects or {}
    observed = dict(effects.get('lane_bookkeeping') or {})
    if not effects.get('available'):
        return _bookkeeping_result(
            failed, unproven, before, after, target_before, target_after,
            changed, unexpected_changed, observed, delta_match=None,
        )

    delta_match = True
    for field, expected in EXPECTED_LANE_BOOKKEEPING_DELTA.items():
        actual = _as_int(observed.get(field))
        if actual == expected:
            continue
        delta_match = False
        if field == 'work_items_created':
            failed.append(FAILED_UNEXPECTED_WORK_ITEM_CREATION)
        elif field == 'checkpoints_advanced':
            failed.append(FAILED_CHECKPOINT_DELTA_MISMATCH)
        elif field == 'commits_performed':
            failed.append(FAILED_COMMIT_COUNT_MISMATCH)
        else:
            failed.append(FAILED_UNEXPECTED_BOOKKEEPING_COUNTER)

    return _bookkeeping_result(
        failed, unproven, before, after, target_before, target_after,
        changed, unexpected_changed, observed, delta_match=delta_match,
    )


def _bookkeeping_result(failed, unproven, before, after, target_before,
                        target_after, changed, unexpected_changed, observed,
                        *, delta_match) -> dict:
    return {
        'failed_reasons': failed,
        'unproven_reasons': unproven,
        'lane_bookkeeping_before': safe_work_item_state(target_before),
        'lane_bookkeeping_after': safe_work_item_state(target_after),
        'lane_bookkeeping_changed_fields': changed,
        'lane_bookkeeping_unexpected_changed_fields': unexpected_changed,
        'lane_bookkeeping_allowed_changed_fields': sorted(
            BOOKKEEPING_ALLOWED_CHANGED_FIELDS
        ),
        'lane_bookkeeping_required_unchanged_fields': list(
            BOOKKEEPING_REQUIRED_UNCHANGED_FIELDS
        ),
        'lane_bookkeeping_expected_delta': dict(
            sorted(EXPECTED_LANE_BOOKKEEPING_DELTA.items())
        ),
        'lane_bookkeeping_observed_delta': dict(sorted(observed.items())),
        'lane_bookkeeping_delta_match': delta_match,
        'target_work_item_present_before': bool(before.get('target_present')),
        'target_work_item_present_after': bool(after.get('target_present')),
        'unrelated_work_items_digest_before': before.get(
            'unrelated_work_items_digest'
        ),
        'unrelated_work_items_digest_after': after.get(
            'unrelated_work_items_digest'
        ),
        'unrelated_checkpoints_digest_before': before.get(
            'unrelated_checkpoints_digest'
        ),
        'unrelated_checkpoints_digest_after': after.get(
            'unrelated_checkpoints_digest'
        ),
        'unrelated_work_item_count': before.get('unrelated_count'),
        'unrelated_bookkeeping_unchanged': bool(
            before.get('available') and after.get('available')
            and before.get('unrelated_work_items_digest')
            == after.get('unrelated_work_items_digest')
            and before.get('unrelated_checkpoints_digest')
            == after.get('unrelated_checkpoints_digest')
        ),
    }


def _digest_entries(entries) -> str:
    encoded = '|'.join(
        f'{game_pk}:{pitcher_mlb_id}:{count}:{digest}'
        for game_pk, pitcher_mlb_id, count, digest in sorted(entries)
    )
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


# ── Execution effects ───────────────────────────────────────────────────────


def split_execution_effects(report) -> dict:
    """Separate baseball-data effects from lane bookkeeping.

    Both groups carry their real measured values. Nothing is zeroed to make a
    verdict reachable — the split exists so the artifact can state which kind of
    write happened, not so one kind can be ignored.
    """
    effects = report.get('execution_effects')
    if not isinstance(effects, dict):
        return {
            'available': False,
            'missing_fields': list(REQUIRED_EFFECT_FIELDS),
            'baseball_data': {},
            'lane_bookkeeping': {},
            'baseball_data_total': None,
        }

    missing = [
        field for field in REQUIRED_EFFECT_FIELDS if field not in effects
    ]
    baseball = {
        field: _as_int(effects.get(field))
        for field in BASEBALL_DATA_EFFECT_FIELDS
    }
    bookkeeping = {
        field: _as_int(effects.get(field))
        for field in LANE_BOOKKEEPING_EFFECT_FIELDS
    }
    return {
        'available': not missing,
        'missing_fields': missing,
        'writes_enabled': bool(effects.get('writes_enabled')),
        'publication_authoritative': bool(
            effects.get('publication_authoritative')
        ),
        'baseball_data': baseball,
        'lane_bookkeeping': bookkeeping,
        'baseball_data_total': sum(baseball.values()),
        'transaction_boundary_entered': _as_int(
            effects.get('commits_performed')
        ) > 0,
        'baseball_row_mutation_performed': sum(baseball.values()) > 0,
    }


def _as_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


# ── Verdict ─────────────────────────────────────────────────────────────────


def decide(evidence) -> dict:
    """Reduce collected evidence to PASS, FAILED, or UNPROVEN.

    FAILED outranks UNPROVEN: an observed violation is a stronger statement than
    absent evidence, and reporting it as merely unproven would understate it.
    PASS is reachable only when every contract condition was positively
    observed — never because nothing raised.
    """
    failed = list(evidence.get('failed_reasons') or ())
    unproven = list(evidence.get('unproven_reasons') or ())

    if failed:
        result = RESULT_FAILED
    elif unproven:
        result = RESULT_UNPROVEN
    else:
        result = RESULT_PASS

    return {
        'result': result,
        'exit_code': EXIT_CODES[result],
        'failed_reasons': sorted(set(failed)),
        'unproven_reasons': sorted(set(unproven)),
        'non_authorization_statement': NON_AUTHORIZATION_STATEMENT,
    }


def assess(*, context, game_pk, shadow_report, write_report,
           before_state, after_state, realization, artifact_scan=None,
           bookkeeping_before=None, bookkeeping_after=None,
           writer_guard=None) -> dict:
    """Apply the full no-op contract to the collected evidence.

    Pure: takes reports and readbacks, returns reason codes. Every condition in
    the contract is checked here in one place so the failure matrix can be
    executed by tests rather than described in prose.
    """
    failed: list[str] = []
    unproven: list[str] = []

    failed.extend(validate_authorization(context, game_pk=game_pk))

    shadow_report = shadow_report or {}
    write_report = write_report or {}

    # ── Scope, proven on the phase that actually executed ────────────────────
    scope = evaluate_scope(write_report, game_pk=game_pk)
    shadow_scope = evaluate_scope(shadow_report, game_pk=game_pk)

    if shadow_scope['planned_game_count'] == 0:
        failed.append(FAILED_GAME_NOT_PLANNABLE)
    if scope['duplicate_requested_count'] or shadow_scope['duplicate_requested_count']:
        failed.append(FAILED_DUPLICATE_REQUESTED_GAME)
    if not scope['requested_is_exactly_target']:
        failed.append(FAILED_REQUESTED_COUNT_NOT_ONE)
    if scope['planned_game_count'] != 1:
        failed.append(FAILED_PLANNED_COUNT_NOT_ONE)
    elif not scope['planned_is_exactly_target']:
        failed.append(FAILED_UNEXPECTED_PLANNED_GAME)
    if scope['unexpected_planned_game_pks']:
        failed.append(FAILED_UNEXPECTED_PLANNED_GAME)
    if scope['missing_requested_game_pks']:
        failed.append(FAILED_MISSING_REQUESTED_GAME)
    if not scope['execution_scope_exact_match']:
        failed.append(FAILED_SCOPE_NOT_EXACT)
    if scope['distinct_games_fetched'] != 1 or scope['games_attempted'] != 1:
        failed.append(FAILED_FETCHED_COUNT_NOT_ONE)
    if scope['games_completed'] != 1:
        failed.append(FAILED_COMPLETED_COUNT_NOT_ONE)

    # ── Lane refusal statuses map to their specific causes ───────────────────
    write_status = write_report.get('status')
    if write_status == lane.STATUS_PLAN_FINGERPRINT_MISMATCH:
        failed.append(FAILED_PLAN_FINGERPRINT_CHANGED)
    elif write_status in (
        lane.STATUS_SCOPE_MISMATCH, lane.STATUS_SCOPE_INVALID,
    ):
        failed.append(FAILED_SCOPE_NOT_EXACT)
    elif write_status == lane.STATUS_PLAN_AUTHORIZATION_REQUIRED:
        unproven.append(UNPROVEN_PLAN_FINGERPRINT_MISSING)
    elif write_status != 'complete':
        failed.append(FAILED_LANE_STATUS_NOT_COMPLETE)

    # ── Plan governance, evaluated on both phases ────────────────────────────
    shadow_governance = evaluate_plan_governance(shadow_report)
    write_governance = evaluate_plan_governance(write_report)

    if not shadow_governance['planned_row_count']:
        unproven.append(UNPROVEN_SHADOW_PHASE_UNUSABLE)
    for governance in (shadow_governance, write_governance):
        if governance['unknown_action_count']:
            failed.append(FAILED_PLAN_UNKNOWN_ACTION)
        if any(
            key.startswith('identity:')
            for key in governance['prohibited_action_counts']
        ):
            failed.append(FAILED_PROHIBITED_IDENTITY_ACTION)
        if governance['planned_row_count'] and not governance[
            'all_rows_already_matching'
        ]:
            failed.append(FAILED_PLAN_PROPOSES_MUTATION)

    # ── Fingerprints: POSITIVE proof, never absence of a mismatch ───────────
    # A missing authorized fingerprint used to pass silently because the lane
    # status alone was consulted. PASS now requires the two fingerprints to be
    # present AND equal, proven here rather than inferred from a status code.
    shadow_fingerprint = shadow_report.get('reconciliation_plan_fingerprint')
    authorized_fingerprint = write_report.get('authorized_plan_fingerprint')
    fingerprint_match = False
    if not shadow_fingerprint:
        unproven.append(UNPROVEN_PLAN_FINGERPRINT_MISSING)
    if not authorized_fingerprint:
        unproven.append(UNPROVEN_AUTHORIZED_FINGERPRINT_MISSING)
    if shadow_fingerprint and authorized_fingerprint:
        if shadow_fingerprint == authorized_fingerprint:
            fingerprint_match = True
        else:
            failed.append(FAILED_PLAN_FINGERPRINT_MISMATCH)

    # ── Source revisions: POSITIVE proof for BOTH phases ────────────────────
    # Each phase must carry exactly one revision, for exactly the requested
    # game, non-null, and the two must be equal. An absent write-phase revision
    # is unproven rather than silently "matched".
    shadow_revisions = source_revisions(shadow_report)
    write_revisions = source_revisions(write_report)
    source_revision_match = False

    shadow_revision = _single_revision(shadow_revisions, game_pk)
    write_revision = _single_revision(write_revisions, game_pk)

    if shadow_revision['state'] == 'wrong_game':
        failed.append(FAILED_SOURCE_REVISION_WRONG_GAME)
    elif shadow_revision['state'] != 'present':
        unproven.append(UNPROVEN_SOURCE_REVISION_MISSING)

    if write_revision['state'] == 'wrong_game':
        failed.append(FAILED_SOURCE_REVISION_WRONG_GAME)
    elif write_revision['state'] != 'present':
        unproven.append(UNPROVEN_WRITE_SOURCE_REVISION_MISSING)

    if (
        shadow_revision['state'] == 'present'
        and write_revision['state'] == 'present'
    ):
        if shadow_revision['revision'] == write_revision['revision']:
            source_revision_match = True
        else:
            failed.append(FAILED_SOURCE_REVISION_CHANGED)

    # ── Execution effects ───────────────────────────────────────────────────
    effects = split_execution_effects(write_report)
    if not effects['available']:
        unproven.append(UNPROVEN_EFFECT_COUNTERS_MISSING)
    else:
        if effects['baseball_data_total'] > 0:
            failed.append(FAILED_BASEBALL_DATA_MUTATED)
        if not effects['writes_enabled']:
            failed.append(FAILED_WRITES_NOT_ENABLED)
        if effects['publication_authoritative']:
            failed.append(FAILED_PUBLICATION_AUTHORITATIVE)

    # ── Before / after state ────────────────────────────────────────────────
    if not before_state or not before_state.get('available'):
        unproven.append(UNPROVEN_PRE_READBACK_UNAVAILABLE)
    if not after_state or not after_state.get('available'):
        unproven.append(UNPROVEN_POST_READBACK_UNAVAILABLE)
    if (
        before_state and after_state
        and before_state.get('available') and after_state.get('available')
        and before_state.get('digest') != after_state.get('digest')
    ):
        failed.append(FAILED_STATE_DIGEST_MISMATCH)

    # ── Realization ─────────────────────────────────────────────────────────
    if not realization or not realization.get('applicable'):
        unproven.append(UNPROVEN_REALIZATION_UNAVAILABLE)
    else:
        if _as_int(realization.get('unresolved_rows')):
            failed.append(FAILED_REALIZATION_UNRESOLVED)
        for field in ('divergent_rows', 'missing_rows', 'duplicate_rows'):
            if _as_int(realization.get(field)):
                failed.append(FAILED_REALIZATION_UNRESOLVED)
        if _as_int(realization.get('prohibited_identity_actions')):
            failed.append(FAILED_PROHIBITED_IDENTITY_ACTION)
        if not realization.get('all_projected_targets_realized'):
            failed.append(FAILED_REALIZATION_UNRESOLVED)

    # ── Lane bookkeeping: exact shape and scope ─────────────────────────────
    bookkeeping = evaluate_lane_bookkeeping(
        bookkeeping_before, bookkeeping_after, effects,
    )
    failed.extend(bookkeeping['failed_reasons'])
    unproven.extend(bookkeeping['unproven_reasons'])

    # ── Writer guard: released, and PROVEN released ─────────────────────────
    guard = dict(writer_guard or {})
    if guard:
        if not guard.get('acquired'):
            unproven.append(UNPROVEN_WRITER_GUARD_UNAVAILABLE)
        elif not (
            guard.get('release_attempted') and guard.get('released')
        ):
            unproven.append(UNPROVEN_WRITER_GUARD_RELEASE_UNPROVEN)

    # ── Artifact safety ─────────────────────────────────────────────────────
    if artifact_scan is not None:
        if not artifact_scan.get('available'):
            unproven.append(UNPROVEN_ARTIFACT_SCAN_UNAVAILABLE)
        elif not artifact_scan.get('safe'):
            failed.append(FAILED_ARTIFACT_FORBIDDEN_CONTENT)

    decision = decide({
        'failed_reasons': failed,
        'unproven_reasons': unproven,
    })
    decision['scope'] = scope
    decision['shadow_scope'] = shadow_scope
    decision['shadow_plan'] = shadow_governance
    decision['write_plan'] = write_governance
    decision['execution_effects'] = effects
    decision['shadow_plan_fingerprint'] = shadow_fingerprint
    decision['authorized_plan_fingerprint'] = authorized_fingerprint
    # Positive proof only: True because equality was observed, never because a
    # mismatch reason happened to be absent.
    decision['plan_fingerprint_match'] = fingerprint_match
    decision['source_revisions_before'] = shadow_revisions
    decision['source_revisions_before_execution'] = write_revisions
    decision['shadow_source_revision_state'] = shadow_revision['state']
    decision['write_source_revision_state'] = write_revision['state']
    decision['source_revision_match'] = source_revision_match
    decision['lane_bookkeeping'] = {
        key: value for key, value in bookkeeping.items()
        if key not in ('failed_reasons', 'unproven_reasons')
    }
    decision['writer_guard'] = {
        'acquired': bool(guard.get('acquired')),
        'release_attempted': bool(guard.get('release_attempted')),
        'released': bool(guard.get('released')),
    }
    decision['before_state'] = before_state or {'available': False}
    decision['after_state'] = after_state or {'available': False}
    decision['state_digest_match'] = (
        bool(before_state) and bool(after_state)
        and bool(before_state.get('available'))
        and bool(after_state.get('available'))
        and before_state.get('digest') == after_state.get('digest')
    )
    return decision
