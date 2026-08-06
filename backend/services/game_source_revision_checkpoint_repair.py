"""Exact-scope checkpoint repair for MLB game 824487's source revision.

WHAT THIS PACKAGE IS ALLOWED TO CHANGE
--------------------------------------
Exactly one column, on exactly one already-existing row::

    game_ingestion_work_items.source_revision
        WHERE mlb_game_pk = 824487

    from 90213dc8e42a9622e9c0dcaea80adb04507a4a5bfe054eaa9b98d2d138b804a0
    to   a0fe2dbce8ad75ffc880e76996a6fec7bc90f86c296350898c009f97f241ecf4

``updated_at`` moves as well, because the model declares
``onupdate=utc_now_naive`` and that fires on any UPDATE of the row. That is an
automatic bookkeeping side effect of the permitted change, not a second
governed decision, and it is declared rather than hidden: the permitted changed
column set is EXACTLY ``{source_revision, updated_at}`` and any other observed
column delta is a contract violation.

WHAT IT MAY NEVER DO
--------------------
It may not insert a work item, create a missing checkpoint, update more than
one work item, update any other column on the work item, or touch ``GameLog``,
``ScheduledGame``, ``SyncRun``, correction provenance, dead letters, snapshots,
publication state, serving state, team intelligence, or player intelligence. It
changes no mode and no authority, triggers no sync, backfill, or replay, reruns
no historical workflow, modifies no source data, modifies no canonical
appearance row, generates no public snapshot, and publishes nothing.

If the expected row is missing, it refuses. If more than one candidate row
exists, it refuses. If the existing value is not the expected old value, it
refuses. If today's official source does not reproduce the intended new value,
it refuses. Refusal is a first-class successful outcome with its own exit code:
this package would rather do nothing than do something it cannot prove.

WHY A CHECKPOINT REPAIR IS NOT A DATA REPAIR
--------------------------------------------
``source_revision`` is
``game_appearance_extraction.appearance_set_fingerprint``
— SHA-256 over the deterministic normalized appearance matrix over 14 governed
fields. It is an observed-content marker on the ingestion checkpoint, not a
baseball value. Moving it changes no pitching line, no inning, no earned run,
and no roster association. What it changes is what the daily lane believes it
has already observed for this game.

That is precisely why the repair is gated on the canonical appearance data
being *already correct*: a checkpoint may only be advanced to describe evidence
that has actually been observed and already agrees with storage. This package
therefore refuses unless the canonical reconciler itself, run against today's
box score, proposes no insert, no update, and no blocked row for game 824487.

DIVERGENCE FROM THE AUDIT'S POPULATION EXPECTATION
---------------------------------------------------
The merged audit establishes "how many appearances this game has" from the two
retained shadow artifacts. Those artifacts expire. A repair that may be
dispatched later must not depend on evidence with an expiry date, so this
package sources the expected population size from LIVE durable state instead:
the checkpoint's own ``rows_expected``, which the table's completion CHECK
constraint already ties to ``rows_reconciled`` for a completed row,
corroborated
by the canonical appearance rows actually stored. All of it is re-observed at
execution time. Nothing here reads a retained artifact, and nothing here reads
the audit's conclusion — a conclusion is not a precondition.

This module judges. It observes nothing on its own: the runner supplies
observations produced by the merged audit's own observation functions, which
call the canonical planner, the canonical MLB client, the canonical box-score
parser, the canonical appearance extractor, and the canonical reconciliation
planner. No second pipeline, client, parser, planner, or reconciler exists
here.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa

from services import game_source_revision_audit as audit


def _jsonable(value):
    """Serializable for the artifact, comparable for the scope proof.

    Dates and decimals are normalized to one representation so a snapshot
    taken before a flush and one taken after cannot differ purely in how the
    same value was rendered.
    """
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


SCHEMA_VERSION = '1'
REPAIR_TYPE = 'game_source_revision_checkpoint_repair'


# ── Locked scope ────────────────────────────────────────────────────────────
# Every governed value is a reviewed literal in code. A dispatch cannot select
# what runs, only whether it runs — the same posture the merged
# official_pitching_line_matt_festa_apply_2026 capability establishes.

GAME_PK = audit.GAME_PK
REPRESENTED_DATE = audit.REPRESENTED_DATE

TARGET_TABLE = 'game_ingestion_work_items'
TARGET_IDENTITY_COLUMN = 'mlb_game_pk'
TARGET_COLUMN = 'source_revision'

# The value the checkpoint is expected to be holding right now.
EXPECTED_EXISTING_SOURCE_REVISION = audit.PRIOR_SOURCE_REVISION
# The value today's official source must reproduce before anything is written.
INTENDED_SOURCE_REVISION = audit.LATER_SOURCE_REVISION

# Two more reviewed literals the controlled audit positively established for
# this game, checked here IN ADDITION to the live population expectation
# (§6 of the package doc). The live check and the literal answer different
# questions: the live one proves the checkpoint and storage still agree with
# each other, the literal proves they still agree with what was reviewed.
# Either failing refuses.
EXPECTED_APPEARANCE_COUNT = audit.EXPECTED_APPEARANCE_COUNT
EXPECTED_PLAN_FINGERPRINT = audit.EXPECTED_PLAN_FINGERPRINT

# The permitted post-state column delta, declared in full. ``updated_at`` is an
# automatic bookkeeping side effect of the model's ``onupdate``; it is named
# here so it can be checked, not so it can be excused. Pinning it back to its
# old value was considered and rejected: falsifying a bookkeeping timestamp to
# make a diff look smaller is worse than disclosing the timestamp.
PERMITTED_CHANGED_COLUMNS = frozenset({'source_revision', 'updated_at'})
GOVERNED_CHANGED_COLUMNS = frozenset({'source_revision'})
AUTOMATIC_BOOKKEEPING_COLUMNS = frozenset({'updated_at'})

# The status a checkpoint must already be in. A checkpoint that is not resolved
# is still the lane's to finish, and advancing an unfinished checkpoint would
# suppress work rather than describe it.
REQUIRED_WORK_ITEM_STATUS = 'completed'

PROHIBITED_MUTATIONS = (
    'insert_a_game_ingestion_work_item',
    'create_a_missing_checkpoint',
    'update_more_than_one_work_item',
    'update_any_other_work_item_column',
    'update_game_log',
    'update_scheduled_game',
    'update_sync_run',
    'write_correction_provenance',
    'write_or_clear_dead_letters',
    'generate_or_publish_a_snapshot',
    'change_serving_or_publication_state',
    'change_team_intelligence',
    'change_player_intelligence',
    'change_ingestion_mode',
    'change_publication_authority',
    'trigger_sync_backfill_or_replay',
    'rerun_a_historical_workflow',
    'modify_source_data',
    'modify_a_canonical_appearance_row',
    'run_a_migration_or_schema_change',
    'weaken_a_validator',
)

NON_AUTHORIZATION_STATEMENT = (
    'This package authorizes nothing on its own. A verify run proves whether '
    'the single approved change is currently required and currently safe; it '
    'is not approval to make it. An apply run is authorized only by a '
    'separate '
    'explicit human decision, expressed as a manual dispatch carrying the '
    'apply confirmation phrase. Nothing here dispatches itself, enables '
    'auto-merge, schedules itself, or widens its own scope.'
)

STANDING_PRODUCTION_STATE = dict(audit.STANDING_PRODUCTION_STATE)

DEAD_LETTER_BACKLOG_NOTE = audit.DEAD_LETTER_BACKLOG_NOTE


# ── Operations ──────────────────────────────────────────────────────────────
# A closed vocabulary of two. Each carries its OWN confirmation phrase, so a
# confirmation reviewed and typed for a verify run can never start an apply
# run even if the operation selector were somehow wrong.

OPERATION_VERIFY = 'verify'
OPERATION_APPLY = 'apply'
OPERATIONS = (OPERATION_VERIFY, OPERATION_APPLY)

CONFIRMATION_VERIFY = 'VERIFY_GAME_824487_SOURCE_REVISION_CHECKPOINT'
CONFIRMATION_APPLY = 'APPLY_GAME_824487_SOURCE_REVISION_CHECKPOINT'
CONFIRMATIONS = {
    OPERATION_VERIFY: CONFIRMATION_VERIFY,
    OPERATION_APPLY: CONFIRMATION_APPLY,
}

REQUIRED_REPOSITORY = audit.REQUIRED_REPOSITORY
REQUIRED_REF = audit.REQUIRED_REF
REQUIRED_EVENT_NAME = audit.REQUIRED_EVENT_NAME
REQUIRED_ACTOR = audit.REQUIRED_ACTOR


# ── Results and exit codes ──────────────────────────────────────────────────

RESULT_VERIFIED_REQUIRED_AND_SAFE = 'VERIFIED_REPAIR_REQUIRED_AND_SAFE'
RESULT_NOT_REQUIRED = 'REPAIR_NOT_REQUIRED'
RESULT_APPLIED = 'REPAIR_APPLIED'
RESULT_REFUSED = 'REPAIR_REFUSED'
RESULT_FAILED = 'FAILED'
RESULT_UNPROVEN = 'UNPROVEN'

RESULTS = (
    RESULT_VERIFIED_REQUIRED_AND_SAFE,
    RESULT_NOT_REQUIRED,
    RESULT_APPLIED,
    RESULT_REFUSED,
    RESULT_FAILED,
    RESULT_UNPROVEN,
)

# Three exit codes, and only three.
#
# 0 the repair is currently eligible, was applied, or was already applied.
# 1 the package broke its OWN contract. Reserved for that and nothing else.
# 2 the repair is not currently eligible to proceed — either because required
#   evidence could not be obtained (UNPROVEN) or because a precondition was
#   positively observed not to hold (REPAIR_REFUSED).
#
# A fourth code for refusal was considered and rejected. The governing rule is
# "exit 0 only if the repair is currently eligible", and a refused run is not
# eligible, so it must not be distinguishable from UNPROVEN by exit status —
# an operator or a workflow gate reading only the exit code must treat both
# identically, which is to say: do not proceed. The DISTINCTION between them is
# preserved where it actually matters, in the result name and the reason codes
# a reviewer reads in the artifact, and it is never flattened there.
EXIT_CODES = {
    RESULT_VERIFIED_REQUIRED_AND_SAFE: 0,
    RESULT_NOT_REQUIRED: 0,
    RESULT_APPLIED: 0,
    RESULT_FAILED: 1,
    RESULT_UNPROVEN: 2,
    RESULT_REFUSED: 2,
}

SUCCESSFUL_RESULTS = frozenset({
    RESULT_VERIFIED_REQUIRED_AND_SAFE,
    RESULT_NOT_REQUIRED,
    RESULT_APPLIED,
})


# ── Reason codes ────────────────────────────────────────────────────────────
# FAILED: this package violated its own safety contract. Nothing about the
# platform belongs in this family.

FAILED_EVENT_NOT_WORKFLOW_DISPATCH = 'event_not_workflow_dispatch'
FAILED_REPOSITORY_NOT_AUTHORIZED = 'repository_not_authorized'
FAILED_ACTOR_NOT_AUTHORIZED = 'actor_not_authorized'
FAILED_REF_NOT_MAIN = 'ref_not_main'
FAILED_EXPECTED_SHA_MALFORMED = 'expected_main_sha_malformed'
FAILED_EXPECTED_SHA_MISMATCH = 'expected_main_sha_mismatch'
FAILED_OPERATION_UNKNOWN = 'operation_not_in_closed_vocabulary'
FAILED_CONFIRMATION_MISMATCH = 'confirmation_does_not_match_operation'

FAILED_MUTATION_SCOPE_EXCEEDED = 'mutation_scope_exceeded'
FAILED_UNEXPECTED_ROW_CREATED = 'unexpected_row_created'
FAILED_UNEXPECTED_ROW_DELETED = 'unexpected_row_deleted'
FAILED_OTHER_WORK_ITEM_MUTATED = 'work_item_outside_target_mutated'
FAILED_AFFECTED_ROW_COUNT_NOT_ONE = 'affected_row_count_not_exactly_one'
FAILED_MUTATION_ROW_COUNT_MULTIPLE = 'mutation_row_count_multiple'
FAILED_ARTIFACT_GENERATION_FAILED = 'artifact_generation_failed'
# Dedicated to the post-commit path, and deliberately NOT reusable for the
# pre-observation one. Failing to establish read-only BEFORE any mutation is
# missing evidence; failing to establish it AFTER a durable commit is this
# package breaking a safety property it explicitly promises, at the one moment
# rollback cannot help. The artifact must be able to tell those apart.
FAILED_POST_COMMIT_READ_ONLY_PROOF = 'post_commit_read_only_proof_failed'
FAILED_POST_COMMIT_VERIFICATION_INCOMPLETE = (
    'post_commit_verification_incomplete'
)
FAILED_POST_STATE_NOT_INTENDED = 'post_state_is_not_the_intended_revision'
FAILED_OUT_OF_SCOPE_TABLE_CHANGED = 'out_of_scope_table_changed'
FAILED_UNPERMITTED_SCOPE_CHANGED = 'unpermitted_fingerprint_scope_changed'
FAILED_TARGET_TABLE_UNCHANGED_AFTER_APPLY = (
    'target_table_fingerprint_unchanged_after_apply'
)
FAILED_READ_ONLY_PROBE_ACCEPTED = 'read_only_probe_accepted_not_refused'
FAILED_MUTATION_ATTEMPTED_IN_VERIFY = 'mutation_attempted_during_verify'
FAILED_LOCK_RELEASE_FAILED = 'advisory_lock_release_failed'
FAILED_LOCK_RELEASE_NOT_ATTEMPTED = 'advisory_lock_release_not_attempted'

FAILED_REASONS = (
    FAILED_EVENT_NOT_WORKFLOW_DISPATCH,
    FAILED_REPOSITORY_NOT_AUTHORIZED,
    FAILED_ACTOR_NOT_AUTHORIZED,
    FAILED_REF_NOT_MAIN,
    FAILED_EXPECTED_SHA_MALFORMED,
    FAILED_EXPECTED_SHA_MISMATCH,
    FAILED_OPERATION_UNKNOWN,
    FAILED_CONFIRMATION_MISMATCH,
    FAILED_MUTATION_SCOPE_EXCEEDED,
    FAILED_UNEXPECTED_ROW_CREATED,
    FAILED_UNEXPECTED_ROW_DELETED,
    FAILED_OTHER_WORK_ITEM_MUTATED,
    FAILED_AFFECTED_ROW_COUNT_NOT_ONE,
    FAILED_MUTATION_ROW_COUNT_MULTIPLE,
    FAILED_ARTIFACT_GENERATION_FAILED,
    FAILED_POST_COMMIT_READ_ONLY_PROOF,
    FAILED_POST_COMMIT_VERIFICATION_INCOMPLETE,
    FAILED_POST_STATE_NOT_INTENDED,
    FAILED_OUT_OF_SCOPE_TABLE_CHANGED,
    FAILED_UNPERMITTED_SCOPE_CHANGED,
    FAILED_TARGET_TABLE_UNCHANGED_AFTER_APPLY,
    FAILED_READ_ONLY_PROBE_ACCEPTED,
    FAILED_MUTATION_ATTEMPTED_IN_VERIFY,
    FAILED_LOCK_RELEASE_FAILED,
    FAILED_LOCK_RELEASE_NOT_ATTEMPTED,
)

# UNPROVEN: required evidence was never obtained. Never a pass, never a
# refusal-by-evidence — a claim this package declines to make at all.
UNPROVEN_ADVISORY_LOCK_UNAVAILABLE = 'public_sync_advisory_lock_unavailable'
UNPROVEN_LOCK_RELEASE_UNKNOWN = 'advisory_lock_release_unproven'
UNPROVEN_READ_ONLY_UNAVAILABLE = 'read_only_transaction_unavailable'
UNPROVEN_PROBE_EVIDENCE_MISSING = 'read_only_probe_evidence_missing'
UNPROVEN_DATABASE_EVIDENCE_UNAVAILABLE = (
    'required_database_evidence_unavailable'
)
UNPROVEN_CURRENT_SOURCE_UNAVAILABLE = 'current_official_source_unavailable'
UNPROVEN_CANONICAL_PLAN_UNAVAILABLE = (
    'canonical_reconciliation_plan_unavailable'
)
UNPROVEN_FINGERPRINT_UNAVAILABLE = 'scoped_fingerprint_uncomputable'
UNPROVEN_OUT_OF_SCOPE_FINGERPRINT_UNAVAILABLE = (
    'out_of_scope_fingerprint_uncomputable'
)
UNPROVEN_TARGET_ROW_NOT_LOCKABLE = 'target_row_not_lockable_without_waiting'
UNPROVEN_EXECUTION_ERROR = 'repair_execution_error'
UNPROVEN_PRECONDITION_NOT_OBSERVED = 'mandatory_precondition_not_observed'
UNPROVEN_APPLY_OUTCOME_UNKNOWN = 'apply_outcome_never_established'

UNPROVEN_REASONS = (
    UNPROVEN_ADVISORY_LOCK_UNAVAILABLE,
    UNPROVEN_LOCK_RELEASE_UNKNOWN,
    UNPROVEN_READ_ONLY_UNAVAILABLE,
    UNPROVEN_PROBE_EVIDENCE_MISSING,
    UNPROVEN_DATABASE_EVIDENCE_UNAVAILABLE,
    UNPROVEN_CURRENT_SOURCE_UNAVAILABLE,
    UNPROVEN_CANONICAL_PLAN_UNAVAILABLE,
    UNPROVEN_FINGERPRINT_UNAVAILABLE,
    UNPROVEN_OUT_OF_SCOPE_FINGERPRINT_UNAVAILABLE,
    UNPROVEN_TARGET_ROW_NOT_LOCKABLE,
    UNPROVEN_EXECUTION_ERROR,
    UNPROVEN_PRECONDITION_NOT_OBSERVED,
    UNPROVEN_APPLY_OUTCOME_UNKNOWN,
)

# REFUSED: a precondition was positively observed NOT to hold. Every one of
# these is a correct, safe outcome of a correctly-working package.
REFUSED_WORK_ITEM_MISSING = 'target_work_item_missing'
REFUSED_WORK_ITEM_MULTIPLE = 'multiple_candidate_work_items'
REFUSED_WRONG_GAME = 'work_item_is_not_the_target_game'
REFUSED_REPRESENTED_DATE_MISMATCH = 'work_item_represented_date_mismatch'
REFUSED_EXISTING_REVISION_ABSENT = 'existing_source_revision_absent'
REFUSED_EXISTING_REVISION_UNEXPECTED = 'existing_source_revision_not_expected'
REFUSED_ALREADY_AT_INTENDED_REVISION = (
    'checkpoint_already_at_intended_revision'
)
REFUSED_STATUS_NOT_COMPLETED = 'work_item_status_not_completed'
REFUSED_POPULATION_EXPECTATION_UNVERIFIED = (
    'appearance_population_expectation_unverified'
)
REFUSED_STORED_COUNT_DISAGREES = (
    'stored_appearance_count_disagrees_with_checkpoint'
)
REFUSED_SOURCE_NOT_CONCLUSION_ELIGIBLE = (
    'current_official_source_not_conclusion_eligible'
)
REFUSED_CURRENT_REVISION_NOT_INTENDED = (
    'current_official_revision_is_not_the_intended_revision'
)
REFUSED_GOVERNED_FIELD_DIFFERS = 'governed_fingerprint_field_differs'
REFUSED_NON_DISPLAY_DIFFERENCE = 'non_display_difference_present'
REFUSED_CANONICAL_PLAN_PROPOSES_MUTATION = (
    'canonical_plan_proposes_a_baseball_mutation'
)
REFUSED_CONCURRENT_MODIFICATION = 'target_row_modified_concurrently'
REFUSED_SCOPE_MOVED_BEFORE_APPLY = 'governed_scope_moved_before_apply'
REFUSED_APPEARANCE_COUNT_UNEXPECTED = 'current_source_count_unexpected'
REFUSED_PLAN_FINGERPRINT_CHANGED = 'reconciliation_plan_changed'
REFUSED_TARGET_ERROR_STATE = 'target_status_unexpected_error_state'
REFUSED_PROHIBITED_SCOPE_CHANGED = 'prohibited_scope_changed'
REFUSED_POST_COMMIT_VERIFICATION_FAILED = 'post_commit_verification_failed'
# Zero affected rows under an exclusive row lock we just re-validated against.
# Classified as a concurrency refusal rather than a contract violation: the
# safe reading is that the row moved, and a refusal never claims the repair was
# already applied without a fresh read establishing it.
REFUSED_MUTATION_ROW_COUNT_ZERO = 'mutation_row_count_zero'

REFUSED_REASONS = (
    REFUSED_WORK_ITEM_MISSING,
    REFUSED_WORK_ITEM_MULTIPLE,
    REFUSED_WRONG_GAME,
    REFUSED_REPRESENTED_DATE_MISMATCH,
    REFUSED_EXISTING_REVISION_ABSENT,
    REFUSED_EXISTING_REVISION_UNEXPECTED,
    REFUSED_ALREADY_AT_INTENDED_REVISION,
    REFUSED_STATUS_NOT_COMPLETED,
    REFUSED_POPULATION_EXPECTATION_UNVERIFIED,
    REFUSED_STORED_COUNT_DISAGREES,
    REFUSED_SOURCE_NOT_CONCLUSION_ELIGIBLE,
    REFUSED_CURRENT_REVISION_NOT_INTENDED,
    REFUSED_GOVERNED_FIELD_DIFFERS,
    REFUSED_NON_DISPLAY_DIFFERENCE,
    REFUSED_CANONICAL_PLAN_PROPOSES_MUTATION,
    REFUSED_CONCURRENT_MODIFICATION,
    REFUSED_SCOPE_MOVED_BEFORE_APPLY,
    REFUSED_APPEARANCE_COUNT_UNEXPECTED,
    REFUSED_PLAN_FINGERPRINT_CHANGED,
    REFUSED_TARGET_ERROR_STATE,
    REFUSED_PROHIBITED_SCOPE_CHANGED,
    REFUSED_POST_COMMIT_VERIFICATION_FAILED,
    REFUSED_MUTATION_ROW_COUNT_ZERO,
)

# ── Traceability to the governing specification ─────────────────────────────
# The repair specification names a minimum set of conditions that must carry a
# stable, safe reason code. This package's own codes are more specific in
# several places — "current_official_revision_is_not_the_intended_revision"
# says more than "current_source_revision_unexpected" — so rather than rename
# them down to the specification's granularity, the mapping is published.
#
# A reviewer working from the specification can look up any listed condition
# and find the code this package actually emits for it. A contract test asserts
# every listed condition maps to a code that really exists, so the map cannot
# rot into a list of names for conditions nobody detects.
SPECIFIED_REASON_CODES = {
    'unauthorized_invocation': FAILED_REPOSITORY_NOT_AUTHORIZED,
    'expected_main_sha_mismatch': FAILED_EXPECTED_SHA_MISMATCH,
    'target_work_item_missing': REFUSED_WORK_ITEM_MISSING,
    'target_work_item_ambiguous': REFUSED_WORK_ITEM_MULTIPLE,
    'target_status_unexpected': REFUSED_STATUS_NOT_COMPLETED,
    'target_checkpoint_missing': REFUSED_EXISTING_REVISION_ABSENT,
    'target_checkpoint_malformed': REFUSED_EXISTING_REVISION_UNEXPECTED,
    'target_checkpoint_unexpected': REFUSED_EXISTING_REVISION_UNEXPECTED,
    'repair_already_applied': REFUSED_ALREADY_AT_INTENDED_REVISION,
    'current_source_unavailable': UNPROVEN_CURRENT_SOURCE_UNAVAILABLE,
    'current_source_empty': UNPROVEN_CURRENT_SOURCE_UNAVAILABLE,
    'current_source_count_unexpected': REFUSED_APPEARANCE_COUNT_UNEXPECTED,
    'current_source_revision_unexpected':
        REFUSED_CURRENT_REVISION_NOT_INTENDED,
    'official_membership_mismatch': REFUSED_SOURCE_NOT_CONCLUSION_ELIGIBLE,
    'duplicate_official_identity': REFUSED_SOURCE_NOT_CONCLUSION_ELIGIBLE,
    'duplicate_stored_identity': REFUSED_SOURCE_NOT_CONCLUSION_ELIGIBLE,
    'stored_appearance_count_unexpected': REFUSED_STORED_COUNT_DISAGREES,
    'reconciliation_plan_changed': REFUSED_PLAN_FINGERPRINT_CHANGED,
    'reconciliation_proposes_insert':
        REFUSED_CANONICAL_PLAN_PROPOSES_MUTATION,
    'reconciliation_proposes_update':
        REFUSED_CANONICAL_PLAN_PROPOSES_MUTATION,
    'reconciliation_proposes_delete':
        REFUSED_CANONICAL_PLAN_PROPOSES_MUTATION,
    'reconciliation_has_blocked_rows':
        REFUSED_CANONICAL_PLAN_PROPOSES_MUTATION,
    'governed_field_difference_detected': REFUSED_GOVERNED_FIELD_DIFFERS,
    'advisory_lock_unavailable': UNPROVEN_ADVISORY_LOCK_UNAVAILABLE,
    'advisory_lock_release_failed': FAILED_LOCK_RELEASE_FAILED,
    'transaction_read_only_proof_failed': UNPROVEN_READ_ONLY_UNAVAILABLE,
    'mutation_row_count_zero': REFUSED_MUTATION_ROW_COUNT_ZERO,
    'mutation_row_count_multiple': FAILED_MUTATION_ROW_COUNT_MULTIPLE,
    'concurrent_precondition_change': REFUSED_CONCURRENT_MODIFICATION,
    'prohibited_scope_changed': REFUSED_PROHIBITED_SCOPE_CHANGED,
    'post_commit_verification_failed':
        REFUSED_POST_COMMIT_VERIFICATION_FAILED,
    'post_commit_read_only_proof_failed':
        FAILED_POST_COMMIT_READ_ONLY_PROOF,
    'artifact_generation_failed': FAILED_ARTIFACT_GENERATION_FAILED,
}

ALL_REASON_CODES = frozenset(
    FAILED_REASONS + UNPROVEN_REASONS + REFUSED_REASONS
)


MAX_REASON_CODES = 12


# ── Precondition model ──────────────────────────────────────────────────────
# Three states, never two. "Violated" and "not observed" sound similar and are
# completely different facts: the first is a refusal backed by evidence, the
# second is a claim this package declines to make.

PRECONDITION_SATISFIED = 'satisfied'
PRECONDITION_VIOLATED = 'violated'
PRECONDITION_NOT_OBSERVED = 'not_observed'
PRECONDITION_STATES = (
    PRECONDITION_SATISFIED,
    PRECONDITION_VIOLATED,
    PRECONDITION_NOT_OBSERVED,
)

PRE_ROW_EXISTS = 'target_row_exists'
PRE_ROW_UNIQUE = 'target_row_is_unique'
PRE_ROW_GAME = 'target_row_is_the_target_game'
PRE_ROW_REPRESENTED_DATE = 'target_row_represented_date_matches'
PRE_ROW_STATUS = 'target_row_status_is_completed'
PRE_EXISTING_REVISION = 'existing_revision_is_the_expected_old_value'
PRE_INTENDED_DIFFERS = 'intended_revision_differs_from_existing'
PRE_POPULATION_VERIFIED = 'appearance_population_size_verified'
PRE_STORED_COUNT = 'stored_appearance_count_matches_population'
PRE_SOURCE_OBSERVED = 'current_official_source_observed'
PRE_SOURCE_COMPLETE = 'current_official_source_conclusion_eligible'
PRE_CURRENT_REVISION = 'current_official_revision_is_the_intended_value'
PRE_NO_GOVERNED_DIFFERENCE = 'no_governed_fingerprint_field_differs'
PRE_DIFFERENCES_DISPLAY_ONLY = 'every_difference_is_derived_display_only'
PRE_CANONICAL_PLAN_CLEAN = 'canonical_plan_proposes_no_mutation'
PRE_PLAN_FINGERPRINT = 'reconciliation_plan_fingerprint_unchanged'
PRE_APPEARANCE_COUNT = 'current_appearance_count_is_the_reviewed_count'
PRE_ROW_NO_ERROR_STATE = 'target_row_carries_no_unresolved_error_state'
PRE_SCOPE_FINGERPRINTS = 'governed_scope_fingerprints_observed'

# The violations that are INTRINSIC to a row already holding the intended
# value, and therefore the only ones a clean REPAIR_NOT_REQUIRED may carry.
#
# PRE_INTENDED_DIFFERS is the obvious one. PRE_EXISTING_REVISION is the
# unavoidable companion: the two governed revisions differ by contract, so a
# row holding the intended value necessarily does NOT hold the expected old
# value. Requiring PRE_INTENDED_DIFFERS to be the *sole* violation would make
# REPAIR_NOT_REQUIRED unreachable rather than strict.
#
# Every other violated precondition describes the surrounding state, and a
# surrounding state that is wrong must not be reported as a clean no-op.
ALREADY_APPLIED_TOLERATED_VIOLATIONS = frozenset()  # populated below

PRECONDITION_IDS = (
    PRE_ROW_EXISTS,
    PRE_ROW_UNIQUE,
    PRE_ROW_GAME,
    PRE_ROW_REPRESENTED_DATE,
    PRE_ROW_STATUS,
    PRE_ROW_NO_ERROR_STATE,
    PRE_EXISTING_REVISION,
    PRE_INTENDED_DIFFERS,
    PRE_POPULATION_VERIFIED,
    PRE_STORED_COUNT,
    PRE_SOURCE_OBSERVED,
    PRE_SOURCE_COMPLETE,
    PRE_CURRENT_REVISION,
    PRE_NO_GOVERNED_DIFFERENCE,
    PRE_DIFFERENCES_DISPLAY_ONLY,
    PRE_CANONICAL_PLAN_CLEAN,
    PRE_PLAN_FINGERPRINT,
    PRE_APPEARANCE_COUNT,
    PRE_SCOPE_FINGERPRINTS,
)

ALREADY_APPLIED_TOLERATED_VIOLATIONS = frozenset({
    PRE_INTENDED_DIFFERS,
    PRE_EXISTING_REVISION,
})

# The refusal codes those two contribute, stripped ONLY on the clean
# already-applied path so a genuine refusal never loses its reasons.
ALREADY_APPLIED_INTRINSIC_REASONS = frozenset()  # populated below

# Which reason a violated precondition contributes. A precondition with no
# mapped reason code could refuse without saying why, so a contract test
# asserts this mapping covers every id above.
PRECONDITION_REFUSAL_REASONS = {
    PRE_ROW_EXISTS: REFUSED_WORK_ITEM_MISSING,
    PRE_ROW_UNIQUE: REFUSED_WORK_ITEM_MULTIPLE,
    PRE_ROW_GAME: REFUSED_WRONG_GAME,
    PRE_ROW_REPRESENTED_DATE: REFUSED_REPRESENTED_DATE_MISMATCH,
    PRE_ROW_STATUS: REFUSED_STATUS_NOT_COMPLETED,
    PRE_EXISTING_REVISION: REFUSED_EXISTING_REVISION_UNEXPECTED,
    PRE_INTENDED_DIFFERS: REFUSED_ALREADY_AT_INTENDED_REVISION,
    PRE_POPULATION_VERIFIED: REFUSED_POPULATION_EXPECTATION_UNVERIFIED,
    PRE_STORED_COUNT: REFUSED_STORED_COUNT_DISAGREES,
    PRE_SOURCE_OBSERVED: REFUSED_SOURCE_NOT_CONCLUSION_ELIGIBLE,
    PRE_SOURCE_COMPLETE: REFUSED_SOURCE_NOT_CONCLUSION_ELIGIBLE,
    PRE_CURRENT_REVISION: REFUSED_CURRENT_REVISION_NOT_INTENDED,
    PRE_NO_GOVERNED_DIFFERENCE: REFUSED_GOVERNED_FIELD_DIFFERS,
    PRE_DIFFERENCES_DISPLAY_ONLY: REFUSED_NON_DISPLAY_DIFFERENCE,
    PRE_CANONICAL_PLAN_CLEAN: REFUSED_CANONICAL_PLAN_PROPOSES_MUTATION,
    PRE_PLAN_FINGERPRINT: REFUSED_PLAN_FINGERPRINT_CHANGED,
    PRE_APPEARANCE_COUNT: REFUSED_APPEARANCE_COUNT_UNEXPECTED,
    PRE_ROW_NO_ERROR_STATE: REFUSED_TARGET_ERROR_STATE,
    PRE_SCOPE_FINGERPRINTS: REFUSED_SCOPE_MOVED_BEFORE_APPLY,
}

# Which reason an UNOBSERVED precondition contributes. Deliberately different
# from the refusal reason: "the source said something else" and "the source was
# never read" must never share a code.
PRECONDITION_UNPROVEN_REASONS = {
    PRE_ROW_EXISTS: UNPROVEN_DATABASE_EVIDENCE_UNAVAILABLE,
    PRE_ROW_UNIQUE: UNPROVEN_DATABASE_EVIDENCE_UNAVAILABLE,
    PRE_ROW_GAME: UNPROVEN_DATABASE_EVIDENCE_UNAVAILABLE,
    PRE_ROW_REPRESENTED_DATE: UNPROVEN_DATABASE_EVIDENCE_UNAVAILABLE,
    PRE_ROW_STATUS: UNPROVEN_DATABASE_EVIDENCE_UNAVAILABLE,
    PRE_EXISTING_REVISION: UNPROVEN_DATABASE_EVIDENCE_UNAVAILABLE,
    PRE_INTENDED_DIFFERS: UNPROVEN_DATABASE_EVIDENCE_UNAVAILABLE,
    PRE_POPULATION_VERIFIED: UNPROVEN_DATABASE_EVIDENCE_UNAVAILABLE,
    PRE_STORED_COUNT: UNPROVEN_DATABASE_EVIDENCE_UNAVAILABLE,
    PRE_SOURCE_OBSERVED: UNPROVEN_CURRENT_SOURCE_UNAVAILABLE,
    PRE_SOURCE_COMPLETE: UNPROVEN_CURRENT_SOURCE_UNAVAILABLE,
    PRE_CURRENT_REVISION: UNPROVEN_CURRENT_SOURCE_UNAVAILABLE,
    PRE_NO_GOVERNED_DIFFERENCE: UNPROVEN_CURRENT_SOURCE_UNAVAILABLE,
    PRE_DIFFERENCES_DISPLAY_ONLY: UNPROVEN_CURRENT_SOURCE_UNAVAILABLE,
    PRE_CANONICAL_PLAN_CLEAN: UNPROVEN_CANONICAL_PLAN_UNAVAILABLE,
    PRE_PLAN_FINGERPRINT: UNPROVEN_CANONICAL_PLAN_UNAVAILABLE,
    PRE_APPEARANCE_COUNT: UNPROVEN_CURRENT_SOURCE_UNAVAILABLE,
    PRE_ROW_NO_ERROR_STATE: UNPROVEN_DATABASE_EVIDENCE_UNAVAILABLE,
    PRE_SCOPE_FINGERPRINTS: UNPROVEN_FINGERPRINT_UNAVAILABLE,
}


ALREADY_APPLIED_INTRINSIC_REASONS = frozenset(
    PRECONDITION_REFUSAL_REASONS[identifier]
    for identifier in ALREADY_APPLIED_TOLERATED_VIOLATIONS
)


def precondition(identifier, *, requirement, state, observed=None,
                 expected=None, note=None) -> dict:
    """One precondition, carrying what it required and what it actually saw."""
    if state not in PRECONDITION_STATES:
        state = PRECONDITION_NOT_OBSERVED
    return {
        'precondition_id': identifier,
        'requirement': requirement,
        'state': state,
        'satisfied': state == PRECONDITION_SATISFIED,
        'expected': expected,
        'observed': observed,
        'note': note,
        'refusal_reason': (
            PRECONDITION_REFUSAL_REASONS.get(identifier)
            if state == PRECONDITION_VIOLATED else None
        ),
        'unproven_reason': (
            PRECONDITION_UNPROVEN_REASONS.get(identifier)
            if state == PRECONDITION_NOT_OBSERVED else None
        ),
    }


def _state(observed_flag, *, satisfied):
    """Three-way state from an observation flag and a comparison result.

    ``observed_flag`` False always wins: a comparison against something that
    was never observed is not a comparison at all.
    """
    if not observed_flag:
        return PRECONDITION_NOT_OBSERVED
    return PRECONDITION_SATISFIED if satisfied else PRECONDITION_VIOLATED


# ── Population expectation, from LIVE durable state ─────────────────────────

POPULATION_VERIFIED = 'verified_from_checkpoint_and_storage'
POPULATION_CHECKPOINT_UNAVAILABLE = 'checkpoint_unavailable'
POPULATION_ROWS_EXPECTED_MISSING = 'rows_expected_not_recorded'
POPULATION_ROWS_EXPECTED_NOT_POSITIVE = 'rows_expected_not_positive'
POPULATION_RECONCILED_DISAGREES = 'rows_reconciled_disagrees_with_expected'
POPULATION_STORED_DISAGREES = 'stored_appearance_count_disagrees'

POPULATION_STATES = (
    POPULATION_VERIFIED,
    POPULATION_CHECKPOINT_UNAVAILABLE,
    POPULATION_ROWS_EXPECTED_MISSING,
    POPULATION_ROWS_EXPECTED_NOT_POSITIVE,
    POPULATION_RECONCILED_DISAGREES,
    POPULATION_STORED_DISAGREES,
)


def _positive_int(value):
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def population_expectation(*, work_item, stored_appearance_count,
                           database_observed=True) -> dict:
    """How many appearances game 824487 has, from live durable state only.

    The checkpoint's ``rows_expected`` is the lane's own recorded population
    size for this game, and the table's completion CHECK constraint already
    requires ``rows_reconciled = rows_expected`` and ``rows_expected > 0``
    for a
    completed row. Both halves are re-checked here anyway rather than assumed
    from the constraint's existence, and the count of canonical appearance rows
    actually stored must agree with them.

    A count nobody recorded is never inferred, and the audit's locked
    ``EXPECTED_APPEARANCE_COUNT`` is deliberately NOT consulted: a constant is
    not an observation.
    """
    if not database_observed or not isinstance(work_item, dict):
        return {
            'expectation_state': POPULATION_CHECKPOINT_UNAVAILABLE,
            'conclusion_usable': False,
            'expected_appearance_count': None,
            'rows_expected': None,
            'rows_reconciled': None,
            'stored_appearance_count': None,
            'database_observed': bool(database_observed),
        }

    rows_expected = _positive_int(work_item.get('rows_expected'))
    rows_reconciled = _positive_int(work_item.get('rows_reconciled'))
    stored_count = _positive_int(stored_appearance_count)

    if rows_expected is None:
        state = POPULATION_ROWS_EXPECTED_MISSING
    elif rows_expected <= 0:
        state = POPULATION_ROWS_EXPECTED_NOT_POSITIVE
    elif rows_reconciled != rows_expected:
        state = POPULATION_RECONCILED_DISAGREES
    elif stored_count != rows_expected:
        state = POPULATION_STORED_DISAGREES
    else:
        state = POPULATION_VERIFIED

    return {
        'expectation_state': state,
        'conclusion_usable': state == POPULATION_VERIFIED,
        'expected_appearance_count': (
            rows_expected if state == POPULATION_VERIFIED else None
        ),
        'rows_expected': rows_expected,
        'rows_reconciled': rows_reconciled,
        'stored_appearance_count': stored_count,
        'database_observed': True,
        'note': (
            'Sourced from live durable state — the checkpoint the repair is '
            'about, corroborated by the canonical appearance rows actually '
            'stored. No retained artifact and no locked constant contributes '
            'to this number.'
        ),
    }


# ── Current-source completeness, against the LIVE expectation ───────────────
# Same shape and same fail-closed ordering as the merged audit's gate: the
# population size is resolved BEFORE membership, because membership equality is
# exactly what two symmetrically truncated sets satisfy.

SOURCE_COMPLETE = 'complete_and_comparable'
SOURCE_UNAVAILABLE = 'source_unavailable'
SOURCE_EMPTY = 'empty_official_set'
SOURCE_DATABASE_UNAVAILABLE = 'database_unavailable'
SOURCE_MATRIX_UNPROVEN = 'matrix_unproven'
SOURCE_EXPECTATION_UNPROVEN = 'population_expectation_unproven'
SOURCE_COUNT_CONTRADICTS = 'current_count_contradicts_population'
SOURCE_DUPLICATE_OFFICIAL = 'duplicate_official_identities'
SOURCE_DUPLICATE_STORED = 'duplicate_stored_identities'
SOURCE_DUPLICATE_BOTH = 'duplicate_identities_both_sides'
SOURCE_OFFICIAL_ONLY_MEMBERS = 'official_only_members_present'
SOURCE_STORED_ONLY_MEMBERS = 'stored_only_members_present'
SOURCE_BOTH_DIRECTIONS = 'both_directions_mismatch'

COMPLETENESS_STATES = (
    SOURCE_COMPLETE,
    SOURCE_UNAVAILABLE,
    SOURCE_EMPTY,
    SOURCE_DATABASE_UNAVAILABLE,
    SOURCE_MATRIX_UNPROVEN,
    SOURCE_EXPECTATION_UNPROVEN,
    SOURCE_COUNT_CONTRADICTS,
    SOURCE_DUPLICATE_OFFICIAL,
    SOURCE_DUPLICATE_STORED,
    SOURCE_DUPLICATE_BOTH,
    SOURCE_OFFICIAL_ONLY_MEMBERS,
    SOURCE_STORED_ONLY_MEMBERS,
    SOURCE_BOTH_DIRECTIONS,
)

CONCLUSION_ELIGIBLE_STATES = frozenset({SOURCE_COMPLETE})


def source_completeness(*, official, comparison, database_observed,
                        expectation) -> dict:
    """Whether today's official set may support ANY conclusion about this game.

    ``conclusion_eligible`` is the single gate every non-refusal outcome
    depends on. A successful fetch proves the transport worked. It never proves
    the payload described the whole game.
    """
    official = official or {}
    comparison = comparison or {}
    expectation = expectation or {}

    empty_extraction = bool(official.get('extraction_yielded_no_appearances'))
    fetched = bool(official.get('available')) or empty_extraction
    count = _positive_int(official.get('appearance_count')) or 0

    duplicate_official = list(
        comparison.get('duplicate_official_identities') or ()
    )
    duplicate_stored = list(
        comparison.get('duplicate_stored_identities') or ()
    )
    missing_from_storage = list(comparison.get('missing_from_storage') or ())
    extra_in_storage = list(comparison.get('extra_in_storage') or ())
    official_missing = comparison.get('official_missing_row_count') or 0
    stored_missing = comparison.get('stored_missing_row_count') or 0
    membership_matches = bool(comparison.get('membership_matches'))

    expected_count = expectation.get('expected_appearance_count')
    expectation_usable = bool(expectation.get('conclusion_usable'))
    count_matches = bool(
        expectation_usable and count > 0 and count == expected_count
    )

    reasons: list[str] = []
    if empty_extraction:
        state = SOURCE_EMPTY
        reasons.append(UNPROVEN_CURRENT_SOURCE_UNAVAILABLE)
    elif not fetched:
        state = SOURCE_UNAVAILABLE
        reasons.append(UNPROVEN_CURRENT_SOURCE_UNAVAILABLE)
    elif count <= 0:
        state = SOURCE_EMPTY
        reasons.append(UNPROVEN_CURRENT_SOURCE_UNAVAILABLE)
    elif not database_observed:
        state = SOURCE_DATABASE_UNAVAILABLE
        reasons.append(UNPROVEN_DATABASE_EVIDENCE_UNAVAILABLE)
    elif not comparison.get('structurally_valid'):
        state = SOURCE_MATRIX_UNPROVEN
        reasons.append(UNPROVEN_EXECUTION_ERROR)
    elif not expectation_usable:
        state = SOURCE_EXPECTATION_UNPROVEN
        reasons.append(UNPROVEN_DATABASE_EVIDENCE_UNAVAILABLE)
    elif not count_matches:
        # The symmetric-truncation gate, resolved BEFORE membership on purpose.
        state = SOURCE_COUNT_CONTRADICTS
        reasons.append(REFUSED_SOURCE_NOT_CONCLUSION_ELIGIBLE)
    elif duplicate_official and duplicate_stored:
        state = SOURCE_DUPLICATE_BOTH
        reasons.append(REFUSED_SOURCE_NOT_CONCLUSION_ELIGIBLE)
    elif duplicate_official:
        state = SOURCE_DUPLICATE_OFFICIAL
        reasons.append(REFUSED_SOURCE_NOT_CONCLUSION_ELIGIBLE)
    elif duplicate_stored:
        state = SOURCE_DUPLICATE_STORED
        reasons.append(REFUSED_SOURCE_NOT_CONCLUSION_ELIGIBLE)
    elif missing_from_storage and extra_in_storage:
        state = SOURCE_BOTH_DIRECTIONS
        reasons.append(REFUSED_SOURCE_NOT_CONCLUSION_ELIGIBLE)
    elif missing_from_storage or stored_missing:
        state = SOURCE_OFFICIAL_ONLY_MEMBERS
        reasons.append(REFUSED_SOURCE_NOT_CONCLUSION_ELIGIBLE)
    elif extra_in_storage or official_missing or not membership_matches:
        state = SOURCE_STORED_ONLY_MEMBERS
        reasons.append(REFUSED_SOURCE_NOT_CONCLUSION_ELIGIBLE)
    else:
        state = SOURCE_COMPLETE

    return {
        'source_fetch_succeeded': fetched,
        'extraction_yielded_no_appearances': empty_extraction,
        'unavailable_reason': official.get('unavailable_reason'),
        'observed_appearance_count': count,
        'expected_appearance_count': expected_count,
        'population_expectation_state': expectation.get('expectation_state'),
        'count_matches_population': count_matches,
        'database_observed': bool(database_observed),
        'membership_matches': membership_matches,
        'missing_from_storage': missing_from_storage,
        'extra_in_storage': extra_in_storage,
        'official_missing_row_count': official_missing,
        'stored_missing_row_count': stored_missing,
        'duplicate_official_identities': duplicate_official,
        'duplicate_stored_identities': duplicate_stored,
        'completeness_state': state,
        'conclusion_eligible': state in CONCLUSION_ELIGIBLE_STATES,
        'reason_codes': reasons,
        'note': (
            'Exact membership equality is necessary and NOT sufficient. Two '
            'symmetrically truncated sets match each other while both remain '
            'incomplete, so the observed count is compared against the live '
            'population expectation BEFORE membership is consulted.'
        ),
    }


# ── Field comparison: today's official source versus canonical storage ──────

def build_comparison(*, official, stored) -> dict:
    """One row per pitcher per governed field, reusing the merged audit's row
    builder, validator, and materiality classifier.

    This package retains NO historical evidence and makes NO historical claim,
    so every historical cell is ``unproven`` — which is the merged audit's own
    rule for a run holding no verified retained document. It is not
    ``not_retained``: that is a claim about a document, and it requires a
    document proven to be the right one.
    """
    from services import game_appearance_extraction as extraction

    official_appearances = list((official or {}).get('appearances') or ())
    official_records = {}
    seen: dict = {}
    for record in official_appearances:
        key = record.get('pitcher_mlb_id')
        seen[key] = seen.get(key, 0) + 1
        official_records[key] = record
    duplicate_official = sorted(
        key for key, count in seen.items() if count > 1 and key is not None
    )

    stored_records = {
        entry['pitcher_mlb_id']: entry
        for entry in (stored or {}).get('stored_appearances') or ()
        if entry.get('pitcher_mlb_id') is not None
    }

    fields = list(extraction.FINGERPRINT_FIELDS) + [
        field for field in audit.WRITER_GOVERNED_FIELDS
        if field not in extraction.FINGERPRINT_FIELDS
    ]

    rows = []
    for pitcher_mlb_id in sorted(set(official_records) | set(stored_records)):
        official_record = official_records.get(pitcher_mlb_id)
        stored_record = stored_records.get(pitcher_mlb_id)
        for field in fields:
            official_key = audit.OFFICIAL_FIELD_ALIASES.get(field, field)
            rows.append(audit.matrix_row(
                pitcher_mlb_id=pitcher_mlb_id,
                side=(official_record or {}).get('side'),
                field_name=field,
                current_official_value=(official_record or {}).get(
                    official_key
                ),
                current_stored_value=(stored_record or {}).get(field),
                official_present=official_record is not None,
                stored_present=stored_record is not None,
                comparable=(
                    official_record is not None
                    and stored_record is not None
                    and official_key in official_record
                    and field in stored_record
                ),
                prior_value_evidence_status=audit.EVIDENCE_UNPROVEN,
                later_value_evidence_status=audit.EVIDENCE_UNPROVEN,
                confidence=(
                    audit.CONFIDENCE_HIGH
                    if official_record is not None
                    and stored_record is not None
                    else audit.CONFIDENCE_MEDIUM
                ),
            ))

    summary = audit.validate_matrix(rows)
    summary['official_pitcher_mlb_ids'] = sorted(official_records)
    summary['stored_pitcher_mlb_ids'] = sorted(stored_records)
    summary['missing_from_storage'] = sorted(
        set(official_records) - set(stored_records)
    )
    summary['extra_in_storage'] = sorted(
        set(stored_records) - set(official_records)
    )
    summary['duplicate_official_identities'] = duplicate_official
    summary['duplicate_stored_identities'] = list(
        (stored or {}).get('duplicate_stored_pitchers') or ()
    )
    summary['membership_matches'] = bool(
        official_records
        and not summary['missing_from_storage']
        and not summary['extra_in_storage']
        and not duplicate_official
        and not summary['duplicate_stored_identities']
    )

    differing = summary.get('differing_rows') or []
    # The distinction the whole repair turns on. A governed fingerprint field
    # differing means today's official set would produce a DIFFERENT digest
    # from the one stored, which makes the intended value wrong. A derived
    # display difference cannot move the digest at all: integer recorded outs
    # are the innings authority and ``innings_pitched`` is deliberately not a
    # fingerprint field.
    summary['governed_differing_rows'] = [
        row for row in differing
        if row['field_name'] in extraction.FINGERPRINT_FIELDS
    ]
    summary['non_display_differing_rows'] = [
        row for row in differing
        if row['materiality'] != audit.MATERIALITY_DISPLAY_ONLY
    ]
    summary['display_only_differing_rows'] = [
        row for row in differing
        if row['materiality'] == audit.MATERIALITY_DISPLAY_ONLY
    ]
    summary['any_governed_field_differs'] = bool(
        summary['governed_differing_rows']
    )
    summary['every_difference_is_display_only'] = not (
        summary['non_display_differing_rows']
    )
    summary['fingerprint_fields'] = list(extraction.FINGERPRINT_FIELDS)
    return {'rows': rows, 'summary': summary}


# ── Preconditions ───────────────────────────────────────────────────────────

def evaluate_preconditions(*, target, official, comparison, plan,
                           expectation, completeness, database_observed,
                           before_fingerprints) -> dict:
    """Every precondition, each judged independently and reported in full.

    Nothing short-circuits. A reviewer reading the artifact must be able to see
    every requirement, what it wanted, and what was actually observed — not
    just the first one that stopped the run.
    """
    target = target or {}
    official = official or {}
    summary = (comparison or {}).get('summary') or {}
    plan = plan or {}
    completeness = completeness or {}
    expectation = expectation or {}

    row = target.get('work_item')
    # "The database was opened" and "the row was there" are different facts and
    # they gate different things. Every row-detail precondition below is gated
    # on the FIRST: a database that was opened and found no row has positively
    # observed that no row satisfies "represented_date matches", which is a
    # violation. Only a database that was never opened leaves those facts
    # unobserved. Gating them on row PRESENCE instead would report a proven
    # absence as missing evidence, and UNPROVEN outranks REFUSED — so the run
    # would say "we do not know" about something it knew exactly.
    row_observed = bool(database_observed) and target.get('observed') is True
    row_present = isinstance(row, dict)
    candidate_count = target.get('candidate_row_count')

    # "The source was obtained" — not "a fetch was attempted". An empty
    # extraction is a successful transport that produced no evidence, and a
    # final game has pitchers, so it counts as missing evidence rather than as
    # an observation that the game had none.
    source_observed = bool(official.get('available'))
    plan_available = bool(plan.get('available'))

    checks = [
        precondition(
            PRE_ROW_EXISTS,
            requirement=(
                f'exactly one existing {TARGET_TABLE} row for game {GAME_PK}'
            ),
            # Satisfied by AT LEAST one row; uniqueness is the next
            # precondition's job. Splitting them keeps the reason codes
            # accurate: zero rows must never report
            # ``multiple_candidate_work_items``, and two rows must never
            # report ``target_work_item_missing``.
            state=_state(
                row_observed,
                satisfied=isinstance(candidate_count, int)
                and candidate_count >= 1,
            ),
            expected='at least one existing row',
            observed=candidate_count if row_observed else None,
            note=(
                'The repair may only UPDATE. Creating a missing checkpoint is '
                'a prohibited mutation, so an absent row is a refusal.'
            ),
        ),
        precondition(
            PRE_ROW_UNIQUE,
            requirement='no more than one candidate row',
            state=_state(
                row_observed and isinstance(candidate_count, int),
                satisfied=isinstance(candidate_count, int)
                and candidate_count <= 1,
            ),
            expected='no more than 1',
            observed=candidate_count,
            note=(
                'A UNIQUE constraint on mlb_game_pk makes a second row '
                'structurally impossible. It is counted anyway: a guard that '
                'trusts a constraint it never checked is not a guard.'
            ),
        ),
        precondition(
            PRE_ROW_GAME,
            requirement=f'{TARGET_IDENTITY_COLUMN} == {GAME_PK}',
            state=_state(
                row_observed,
                satisfied=(row or {}).get('mlb_game_pk') == GAME_PK,
            ),
            expected=GAME_PK,
            observed=(row or {}).get('mlb_game_pk'),
        ),
        precondition(
            PRE_ROW_REPRESENTED_DATE,
            requirement=(
                f'represented_date == {REPRESENTED_DATE.isoformat()}'
            ),
            state=_state(
                row_observed,
                satisfied=(
                    (row or {}).get('represented_date')
                    == REPRESENTED_DATE.isoformat()
                ),
            ),
            expected=REPRESENTED_DATE.isoformat(),
            observed=(row or {}).get('represented_date'),
        ),
        precondition(
            PRE_ROW_STATUS,
            requirement=f'status == {REQUIRED_WORK_ITEM_STATUS!r}',
            state=_state(
                row_observed,
                satisfied=(
                    (row or {}).get('status') == REQUIRED_WORK_ITEM_STATUS
                ),
            ),
            expected=REQUIRED_WORK_ITEM_STATUS,
            observed=(row or {}).get('status'),
            note=(
                'An unresolved checkpoint is still work the lane owns and '
                'has to finish. Advancing it would suppress that work '
                'rather than describe it.'
            ),
        ),
        precondition(
            PRE_ROW_NO_ERROR_STATE,
            requirement=(
                'the row carries no unresolved error class and no attempt '
                'left in flight'
            ),
            state=_state(
                row_observed,
                satisfied=(
                    not (row or {}).get('error_class')
                    and (row or {}).get('completed_at') is not None
                ),
            ),
            expected='error_class absent, completed_at present',
            observed={
                'error_class': (row or {}).get('error_class'),
                'completed_at': (row or {}).get('completed_at'),
            } if row_observed else None,
            note=(
                'A completed row that still carries an error class, or that '
                'never recorded a completion time, is a row whose own lane '
                'did not finish cleanly. Its checkpoint is not this '
                'package to advance.'
            ),
        ),
        precondition(
            PRE_EXISTING_REVISION,
            requirement='existing source_revision is the expected old value',
            state=_state(
                row_observed,
                satisfied=(
                    (row or {}).get('source_revision')
                    == EXPECTED_EXISTING_SOURCE_REVISION
                ),
            ),
            expected=EXPECTED_EXISTING_SOURCE_REVISION,
            observed=(row or {}).get('source_revision'),
            note=(
                'A row already holding some third value is not this repair '
                'target. An absent value is equally a refusal: this package '
                'updates a known value, it does not fill a blank.'
            ),
        ),
        precondition(
            PRE_INTENDED_DIFFERS,
            requirement='the intended value is not already stored',
            state=_state(
                row_observed,
                satisfied=(
                    (row or {}).get('source_revision')
                    != INTENDED_SOURCE_REVISION
                ),
            ),
            expected=f'!= {INTENDED_SOURCE_REVISION}',
            observed=(row or {}).get('source_revision'),
            note=(
                'Already at the intended value means there is nothing to do. '
                'That is REPAIR_NOT_REQUIRED, not a failure.'
            ),
        ),
        precondition(
            PRE_POPULATION_VERIFIED,
            requirement=(
                'the appearance population size is verified from live durable '
                'state'
            ),
            state=_state(
                row_observed,
                satisfied=bool(expectation.get('conclusion_usable')),
            ),
            expected=POPULATION_VERIFIED,
            observed=expectation.get('expectation_state'),
        ),
        precondition(
            PRE_STORED_COUNT,
            requirement=(
                'stored canonical appearance rows equal the population size'
            ),
            state=_state(
                row_observed,
                satisfied=(
                    expectation.get('conclusion_usable')
                    and expectation.get('stored_appearance_count')
                    == expectation.get('expected_appearance_count')
                ),
            ),
            expected=expectation.get('expected_appearance_count'),
            observed=expectation.get('stored_appearance_count'),
        ),
        precondition(
            PRE_SOURCE_OBSERVED,
            requirement=(
                'the current official box score was fetched and extracted'
            ),
            # A source that was not obtained is NOT_OBSERVED even when the
            # reason it was not obtained is perfectly well known. Knowing WHY
            # the evidence is missing does not make it present, and a refusal
            # code here would claim this run had read the source and found it
            # wanting.
            state=_state(source_observed, satisfied=True),
            expected='one bounded box-score call, non-empty extraction',
            observed=official.get('unavailable_reason') or (
                'available' if official.get('available') else None
            ),
        ),
        precondition(
            PRE_SOURCE_COMPLETE,
            requirement=(
                f'current source completeness is {SOURCE_COMPLETE!r}'
            ),
            # Completeness is a judgement ABOUT an observed source. With no
            # source and no database there is nothing to judge, so the state is
            # unobserved rather than a refusal.
            state=_state(
                source_observed and bool(database_observed),
                satisfied=bool(completeness.get('conclusion_eligible')),
            ),
            expected=SOURCE_COMPLETE,
            observed=completeness.get('completeness_state'),
        ),
        precondition(
            PRE_CURRENT_REVISION,
            requirement=(
                'the current official appearance set fingerprints to the '
                'intended value'
            ),
            state=_state(
                bool(official.get('available')),
                satisfied=(
                    official.get('current_source_revision')
                    == INTENDED_SOURCE_REVISION
                ),
            ),
            expected=INTENDED_SOURCE_REVISION,
            observed=official.get('current_source_revision'),
            note=(
                'The intended value is never assumed from a literal. It is '
                'recomputed from the current source through the canonical '
                'extractor and must reproduce the reviewed constant exactly.'
            ),
        ),
        precondition(
            PRE_NO_GOVERNED_DIFFERENCE,
            requirement=(
                'no governed fingerprint field differs between the official '
                'set and canonical storage'
            ),
            state=_state(
                bool(summary.get('structurally_valid'))
                and bool(official.get('available')),
                satisfied=not summary.get('any_governed_field_differs'),
            ),
            expected=[],
            observed=summary.get('governed_differing_rows'),
            note=(
                'A governed field differing would mean canonical storage is '
                'behind the source. That is a DATA repair, which this package '
                'is not and must never become.'
            ),
        ),
        precondition(
            PRE_DIFFERENCES_DISPLAY_ONLY,
            requirement='every observed difference is derived_display_only',
            state=_state(
                bool(summary.get('structurally_valid'))
                and bool(official.get('available')),
                satisfied=bool(
                    summary.get('every_difference_is_display_only')
                ),
            ),
            expected=audit.MATERIALITY_DISPLAY_ONLY,
            observed=summary.get('non_display_differing_rows'),
            note=(
                'The differing-row list is NOT required to be empty. Integer '
                'recorded outs are the innings authority, so a decimal '
                'innings_pitched display difference is expected and cannot '
                'move the fingerprint.'
            ),
        ),
        precondition(
            PRE_CANONICAL_PLAN_CLEAN,
            requirement=(
                'the canonical reconciler proposes no insert, update, or '
                'blocked row for this game'
            ),
            state=_state(
                plan_available,
                satisfied=bool(
                    plan.get('row_count')
                    and not plan.get('proposes_mutation')
                ),
            ),
            expected='zero insert, zero update, zero blocked',
            observed=plan.get('action_counts') if plan_available else None,
            note=(
                'The strongest available statement that canonical storage is '
                'already correct, made by the canonical authority itself '
                'rather than by the comparison this package makes.'
            ),
        ),
        precondition(
            PRE_PLAN_FINGERPRINT,
            requirement=(
                'the per-game reconciliation-plan fingerprint still equals '
                'the reviewed value'
            ),
            state=_state(
                plan_available and bool(
                    plan.get('reconciliation_plan_fingerprint')
                ),
                satisfied=(
                    plan.get('reconciliation_plan_fingerprint')
                    == EXPECTED_PLAN_FINGERPRINT
                ),
            ),
            expected=EXPECTED_PLAN_FINGERPRINT,
            observed=plan.get('reconciliation_plan_fingerprint'),
            note=(
                'Checked SEPARATELY from the action counts, and refusing on '
                'its own. A plan can report zero inserts, zero updates, and '
                'zero blocked rows while its fingerprint has moved, which '
                'means the plan this repair was reviewed against is not the '
                'plan the reconciler is producing today.'
            ),
        ),
        precondition(
            PRE_APPEARANCE_COUNT,
            requirement=(
                f'the observed appearance count is exactly '
                f'{EXPECTED_APPEARANCE_COUNT}'
            ),
            state=_state(
                bool(official.get('available')) and bool(database_observed),
                satisfied=(
                    official.get('appearance_count')
                    == EXPECTED_APPEARANCE_COUNT
                    and expectation.get('stored_appearance_count')
                    == EXPECTED_APPEARANCE_COUNT
                ),
            ),
            expected=EXPECTED_APPEARANCE_COUNT,
            observed={
                'official': official.get('appearance_count'),
                'stored': expectation.get('stored_appearance_count'),
            },
            note=(
                'The reviewed literal, checked IN ADDITION to the live '
                'population expectation. The live check proves the '
                'checkpoint and storage still agree with each other; this '
                'one proves they still agree with what was reviewed. Either '
                'failing refuses.'
            ),
        ),
        precondition(
            PRE_SCOPE_FINGERPRINTS,
            requirement='governed scope fingerprints were computed',
            state=_state(
                before_fingerprints is not None,
                satisfied=isinstance(before_fingerprints, dict)
                and bool(before_fingerprints),
            ),
            expected='per-table digests for every governed scope',
            observed=(
                sorted(before_fingerprints)
                if isinstance(before_fingerprints, dict) else None
            ),
        ),
    ]

    by_state: dict[str, list[str]] = {
        PRECONDITION_SATISFIED: [],
        PRECONDITION_VIOLATED: [],
        PRECONDITION_NOT_OBSERVED: [],
    }
    for check in checks:
        by_state[check['state']].append(check['precondition_id'])

    refusal_reasons: list[str] = []
    unproven_reasons: list[str] = []
    for check in checks:
        if check['refusal_reason'] and (
            check['refusal_reason'] not in refusal_reasons
        ):
            refusal_reasons.append(check['refusal_reason'])
        if check['unproven_reason'] and (
            check['unproven_reason'] not in unproven_reasons
        ):
            unproven_reasons.append(check['unproven_reason'])
    if by_state[PRECONDITION_NOT_OBSERVED]:
        unproven_reasons.append(UNPROVEN_PRECONDITION_NOT_OBSERVED)

    # ``already at the intended value`` is the ONE violated precondition that
    # means "nothing to do" rather than "something is wrong". It is separated
    # here so the reducer can reach REPAIR_NOT_REQUIRED, and it is still
    # reported as a violated precondition rather than quietly reclassified.
    already_applied = PRE_INTENDED_DIFFERS in by_state[PRECONDITION_VIOLATED]

    return {
        'preconditions': checks,
        'precondition_ids': list(PRECONDITION_IDS),
        'satisfied': by_state[PRECONDITION_SATISFIED],
        'violated': by_state[PRECONDITION_VIOLATED],
        'not_observed': by_state[PRECONDITION_NOT_OBSERVED],
        'all_satisfied': (
            not by_state[PRECONDITION_VIOLATED]
            and not by_state[PRECONDITION_NOT_OBSERVED]
        ),
        'any_violated': bool(by_state[PRECONDITION_VIOLATED]),
        'any_not_observed': bool(by_state[PRECONDITION_NOT_OBSERVED]),
        'already_at_intended_revision': already_applied,
        'refusal_reasons': refusal_reasons,
        'unproven_reasons': unproven_reasons,
    }


# ── Mutation-scope observation ──────────────────────────────────────────────

def row_snapshot(row) -> dict:
    """Every mapped column, read by inspection rather than by a hand list.

    A hand-written column list silently stops covering a column somebody adds
    later, and the whole scope proof rests on this snapshot being complete.
    """
    if row is None:
        return {}
    mapper = sa.inspect(type(row))
    return {
        column.key: _jsonable(getattr(row, column.key, None))
        for column in mapper.columns
    }


def changed_columns(before, after) -> list[str]:
    """Column keys whose values differ between two snapshots."""
    before = before or {}
    after = after or {}
    return sorted(
        key for key in set(before) | set(after)
        if before.get(key) != after.get(key)
    )


class MutationScopeGuard:
    """ORM-level evidence of everything a transaction actually did.

    Observed from flushed session state rather than asserted by reading the
    code. It records creations, deletions, and the changed-attribute set of
    every dirty object — so a mutation this package did not intend is visible
    even when it happens somewhere this package never looks.

    ``updated_at`` will NOT appear in the changed-attribute set: the model's
    ``onupdate`` default is applied by the flush process AFTER ``before_flush``
    runs. That is why the authoritative scope proof is the before/after column
    snapshot, and this guard is the corroborating second control rather than
    the only one.
    """

    def __init__(self, session):
        self._session = session
        self._listener = None
        self.created_object_types: list[str] = []
        self.deleted_object_types: list[str] = []
        self.mutated_objects: list[dict] = []

    def attach(self):
        def _before_flush(session, flush_context, instances):  # noqa: ARG001
            for obj in session.deleted:
                self.deleted_object_types.append(type(obj).__name__)
            for obj in session.new:
                self.created_object_types.append(type(obj).__name__)
            for obj in session.dirty:
                state = sa.inspect(obj)
                changed = sorted(
                    attr.key for attr in state.attrs
                    if attr.history.has_changes()
                )
                if not changed:
                    continue
                self.mutated_objects.append({
                    'type': type(obj).__name__,
                    'primary_key': getattr(obj, 'id', None),
                    'changed_attributes': changed,
                })

        self._listener = _before_flush
        sa.event.listen(self._session, 'before_flush', _before_flush)
        return self

    def detach(self):
        if self._listener is not None:
            sa.event.remove(self._session, 'before_flush', self._listener)
            self._listener = None

    def as_dict(self) -> dict:
        return {
            'created_object_types': sorted(set(self.created_object_types)),
            'created_object_count': len(self.created_object_types),
            'deleted_object_types': sorted(set(self.deleted_object_types)),
            'deleted_object_count': len(self.deleted_object_types),
            'mutated_objects': list(self.mutated_objects),
            'mutated_object_count': len(self.mutated_objects),
            'mutated_types': sorted({
                entry['type'] for entry in self.mutated_objects
            }),
            'mutated_attributes': sorted({
                key for entry in self.mutated_objects
                for key in entry['changed_attributes']
            }),
        }

    def checks(self, *, target_row_id, expect_mutation) -> dict:
        observed = self.as_dict()
        mutated_ids = [
            entry['primary_key'] for entry in self.mutated_objects
        ]
        return {
            'no_object_was_created': observed['created_object_count'] == 0,
            'no_object_was_deleted': observed['deleted_object_count'] == 0,
            'exactly_the_expected_objects_mutated': (
                mutated_ids == [target_row_id] if expect_mutation
                else observed['mutated_object_count'] == 0
            ),
            'only_the_target_type_mutated': (
                observed['mutated_types'] == ['GameIngestionWorkItem']
                if expect_mutation else observed['mutated_types'] == []
            ),
            'only_governed_attributes_changed': (
                set(observed['mutated_attributes'])
                <= GOVERNED_CHANGED_COLUMNS
            ),
        }


class StatementWatch:
    """Every SQL write statement the apply transaction actually issued.

    The ORM guard proves what the SESSION intended. This proves what the
    DATABASE was actually told, which is a different and stronger claim: a raw
    statement issued from anywhere under this connection is visible here even
    though no ORM object was ever made dirty.

    Statement TEXT is never retained. Only a statement class, a row count, and
    one boolean about whether the target table was named cross into the
    artifact — the package's safe-summaries rule applies to SQL exactly as it
    applies to exception messages.
    """

    WRITE_STATEMENT_CLASSES = (
        'INSERT', 'UPDATE', 'DELETE', 'MERGE', 'TRUNCATE', 'COPY',
        'CREATE', 'DROP', 'ALTER', 'GRANT', 'REVOKE',
    )

    def __init__(self, engine):
        self._engine = engine
        self._listener = None
        self.write_statements: list[dict] = []

    def attach(self):
        def _after_cursor_execute(conn, cursor, statement, parameters,
                                  context, executemany):  # noqa: ARG001
            text_value = (statement or '').lstrip()
            if not text_value:
                return
            head = text_value.split(None, 1)[0].upper().strip('(')
            if head not in self.WRITE_STATEMENT_CLASSES:
                return
            try:
                rowcount = int(cursor.rowcount)
            except (TypeError, ValueError):
                rowcount = None
            self.write_statements.append({
                'statement_class': head,
                'rowcount': rowcount,
                'names_target_table': TARGET_TABLE in text_value.lower(),
                'executemany': bool(executemany),
            })

        self._listener = _after_cursor_execute
        sa.event.listen(
            self._engine, 'after_cursor_execute', _after_cursor_execute,
        )
        return self

    def detach(self):
        if self._listener is not None:
            sa.event.remove(
                self._engine, 'after_cursor_execute', self._listener,
            )
            self._listener = None

    def as_dict(self) -> dict:
        target_updates = [
            entry for entry in self.write_statements
            if entry['statement_class'] == 'UPDATE'
            and entry['names_target_table']
        ]
        other = [
            entry for entry in self.write_statements
            if entry not in target_updates
        ]
        rowcounts = [
            entry['rowcount'] for entry in target_updates
            if entry['rowcount'] is not None
        ]
        return {
            'write_statement_count': len(self.write_statements),
            'statement_classes': sorted({
                entry['statement_class'] for entry in self.write_statements
            }),
            'target_table_update_count': len(target_updates),
            'target_table_affected_rows': sum(rowcounts) if rowcounts else 0,
            'target_table_rowcount_observed': bool(rowcounts),
            'other_write_statement_count': len(other),
            'other_write_statement_classes': sorted({
                entry['statement_class'] for entry in other
            }),
            'exactly_one_target_update': len(target_updates) == 1,
            'no_other_write_statement': not other,
        }


# ── Fingerprint scope helpers ───────────────────────────────────────────────

def changed_fingerprint_tables(before, after) -> list[list]:
    """``[scope, table]`` pairs whose digests differ, sorted.

    Coarser than a per-scope comparison would be: an apply legitimately moves
    exactly ONE table inside one scope, so the proof has to be able to say
    which table, not merely which scope.
    """
    if not isinstance(before, dict) or not isinstance(after, dict):
        return []
    changed = []
    for scope in sorted(set(before) | set(after)):
        left = before.get(scope) or {}
        right = after.get(scope) or {}
        if not isinstance(left, dict) or not isinstance(right, dict):
            changed.append([scope, None])
            continue
        for table in sorted(set(left) | set(right)):
            if left.get(table) != right.get(table):
                changed.append([scope, table])
    return changed


# The one table any statement in this package names. Everything else in the
# governed scope is covered by the audit's in-scope fingerprints; this is the
# complement — every row of the target table that is NOT game 824487 — so a
# statement that somehow reached another game's checkpoint is visible.
OUT_OF_SCOPE_TABLE = TARGET_TABLE


def out_of_scope_fingerprint(session) -> dict | None:
    """Digest and row count for every target-table row that is NOT this game.

    Returns ``None`` when it cannot be computed at all, which the reducer turns
    into UNPROVEN rather than into a silent pass.
    """
    bind = session.get_bind()
    if getattr(bind.dialect, 'name', '') != 'postgresql':
        return None
    try:
        digest = session.execute(sa.text(
            "SELECT md5(coalesce(string_agg(t::text, '|' ORDER BY t::text), "
            "'')) FROM game_ingestion_work_items t "
            'WHERE mlb_game_pk <> :game_pk'
        ), {'game_pk': GAME_PK}).scalar()
        count = session.execute(sa.text(
            'SELECT count(*) FROM game_ingestion_work_items '
            'WHERE mlb_game_pk <> :game_pk'
        ), {'game_pk': GAME_PK}).scalar()
    except Exception:  # noqa: BLE001 - an unprovable fingerprint is UNPROVEN
        return None
    return {'table': OUT_OF_SCOPE_TABLE, 'digest': digest, 'row_count': count}


# ── The permitted post-state ────────────────────────────────────────────────

def evaluate_mutation(*, before_snapshot, after_snapshot, guard_checks,
                      affected_row_count, changed_tables,
                      out_of_scope_before, out_of_scope_after,
                      statements=None) -> dict:
    """Judge what the apply ACTUALLY did against what it was permitted to do.

    Every clause is a positive observation. Nothing is inferred from the
    absence of an error.
    """
    before_snapshot = before_snapshot or {}
    after_snapshot = after_snapshot or {}
    guard_checks = guard_checks or {}
    statements = statements or {}

    observed_changed = changed_columns(before_snapshot, after_snapshot)
    unpermitted = sorted(set(observed_changed) - PERMITTED_CHANGED_COLUMNS)
    governed_changed = sorted(
        set(observed_changed) & GOVERNED_CHANGED_COLUMNS
    )
    bookkeeping_changed = sorted(
        set(observed_changed) & AUTOMATIC_BOOKKEEPING_COLUMNS
    )

    expected_tables = [[audit.SCOPE_EXACT_GAME, TARGET_TABLE]]
    # ``None`` means the comparison was never computable. It is NOT the same
    # as an empty list, which means the digests were computed and nothing
    # moved — after a committed apply that is a definite violation, while an
    # uncomputable comparison is missing evidence.
    tables_observed = changed_tables is not None
    changed_tables = [list(entry) for entry in (changed_tables or ())]
    unexpected_tables = [
        entry for entry in changed_tables if entry not in expected_tables
    ]

    out_of_scope_observed = (
        isinstance(out_of_scope_before, dict)
        and isinstance(out_of_scope_after, dict)
    )
    out_of_scope_unchanged = (
        out_of_scope_before == out_of_scope_after
        if out_of_scope_observed else None
    )

    failed: list[str] = []
    unproven: list[str] = []

    if unpermitted:
        failed.append(FAILED_MUTATION_SCOPE_EXCEEDED)
    if observed_changed and governed_changed != sorted(
        GOVERNED_CHANGED_COLUMNS
    ):
        failed.append(FAILED_MUTATION_SCOPE_EXCEEDED)
    if guard_checks.get('no_object_was_created') is False:
        failed.append(FAILED_UNEXPECTED_ROW_CREATED)
    if guard_checks.get('no_object_was_deleted') is False:
        failed.append(FAILED_UNEXPECTED_ROW_DELETED)
    if guard_checks.get('exactly_the_expected_objects_mutated') is False:
        failed.append(FAILED_OTHER_WORK_ITEM_MUTATED)
    if guard_checks.get('only_governed_attributes_changed') is False:
        failed.append(FAILED_MUTATION_SCOPE_EXCEEDED)
    if affected_row_count != 1:
        failed.append(FAILED_AFFECTED_ROW_COUNT_NOT_ONE)
    if after_snapshot.get(TARGET_COLUMN) != INTENDED_SOURCE_REVISION:
        failed.append(FAILED_POST_STATE_NOT_INTENDED)
    if unexpected_tables:
        failed.append(FAILED_UNPERMITTED_SCOPE_CHANGED)
    if not tables_observed:
        unproven.append(UNPROVEN_FINGERPRINT_UNAVAILABLE)
    elif expected_tables[0] not in changed_tables:
        # The target table's digest MUST move: a row whose source revision
        # changed and whose full-row digest did not is not a repair that
        # happened, it is a repair that reported itself. An empty list here is
        # therefore a violation, not a clean run.
        failed.append(FAILED_TARGET_TABLE_UNCHANGED_AFTER_APPLY)
    if out_of_scope_unchanged is False:
        failed.append(FAILED_OUT_OF_SCOPE_TABLE_CHANGED)
    elif out_of_scope_unchanged is None:
        unproven.append(UNPROVEN_OUT_OF_SCOPE_FINGERPRINT_UNAVAILABLE)

    # What the DATABASE was told, independent of what the session intended.
    if statements:
        if statements.get('no_other_write_statement') is False:
            failed.append(FAILED_MUTATION_SCOPE_EXCEEDED)
        if statements.get('exactly_one_target_update') is False:
            failed.append(FAILED_AFFECTED_ROW_COUNT_NOT_ONE)
        observed_rows = statements.get('target_table_affected_rows')
        if statements.get('target_table_rowcount_observed') and (
            observed_rows != 1
        ):
            failed.append(FAILED_AFFECTED_ROW_COUNT_NOT_ONE)

    return {
        'observed_changed_columns': observed_changed,
        'permitted_changed_columns': sorted(PERMITTED_CHANGED_COLUMNS),
        'governed_changed_columns': governed_changed,
        'automatic_bookkeeping_changed_columns': bookkeeping_changed,
        'unpermitted_changed_columns': unpermitted,
        'changed_columns_are_exactly_permitted': (
            sorted(observed_changed) == sorted(PERMITTED_CHANGED_COLUMNS)
        ),
        'affected_row_count': affected_row_count,
        'affected_exactly_one_row': affected_row_count == 1,
        'post_state_is_intended_revision': (
            after_snapshot.get(TARGET_COLUMN) == INTENDED_SOURCE_REVISION
        ),
        'changed_fingerprint_tables_observed': tables_observed,
        'changed_fingerprint_tables': changed_tables,
        'expected_changed_fingerprint_tables': expected_tables,
        'unexpected_changed_fingerprint_tables': unexpected_tables,
        'out_of_scope_fingerprint_observed': out_of_scope_observed,
        'out_of_scope_unchanged': out_of_scope_unchanged,
        'guard_checks': guard_checks,
        'statement_report': dict(statements),
        'failed_reasons': sorted(dict.fromkeys(failed)),
        'unproven_reasons': sorted(dict.fromkeys(unproven)),
        'mutation_within_scope': not failed and not unproven,
        'updated_at_disclosure': (
            'updated_at moved because the model declares '
            'onupdate=utc_now_naive, which fires on any UPDATE of this row. '
            'It is an automatic bookkeeping side effect of the one permitted '
            'change, it is declared in PERMITTED_CHANGED_COLUMNS, and it was '
            'deliberately NOT pinned back to its old value.'
        ),
    }


# ── Advisory-lock lifecycle ─────────────────────────────────────────────────

def lock_lifecycle(state) -> dict:
    """The full acquire/release lifecycle, and what each outcome means.

    A lock that was acquired and never provably released is not a clean run.
    Process termination is not release evidence.
    """
    state = state or {}
    acquired = bool(state.get('guard_acquired'))
    attempted = bool(state.get('acquire_attempted'))
    release_attempted = bool(state.get('guard_release_attempted'))
    released = state.get('guard_released')

    failed: list[str] = []
    unproven: list[str] = []
    if not acquired:
        unproven.append(UNPROVEN_ADVISORY_LOCK_UNAVAILABLE)
    elif released is False:
        failed.append(FAILED_LOCK_RELEASE_FAILED)
    elif not release_attempted:
        failed.append(FAILED_LOCK_RELEASE_NOT_ATTEMPTED)
    elif released is not True:
        unproven.append(UNPROVEN_LOCK_RELEASE_UNKNOWN)

    return {
        'acquire_attempted': attempted,
        'guard_acquired': acquired,
        'acquisition_reason': state.get('acquisition_reason'),
        'release_required': acquired,
        'guard_release_attempted': release_attempted,
        'guard_released': released,
        'release_reason': state.get('release_reason'),
        'rollback_attempted': bool(state.get('rollback_attempted')),
        'rollback_succeeded': state.get('rollback_succeeded'),
        'lifecycle_complete': acquired and released is True,
        'failed_reasons': failed,
        'unproven_reasons': unproven,
    }


# ── Verdict ─────────────────────────────────────────────────────────────────

def precondition_coverage(preconditions) -> dict:
    """What the reducer can PROVE about the precondition evaluation.

    Deliberately re-derived from the evaluated check objects rather than read
    off the summary booleans ``evaluate_preconditions`` also produces. A
    summary flag is a claim; the check list is the evidence, and the reducer
    that decides whether production may be written should read the evidence.

    An evaluation that does not cover every governed precondition id cannot
    support any outcome except UNPROVEN — an empty or partial evaluation must
    never reach a success result by having nothing to object with.
    """
    preconditions = preconditions or {}
    raw = preconditions.get('preconditions')
    checks = [
        check for check in raw if isinstance(check, dict)
    ] if isinstance(raw, list) else []

    covered = {check.get('precondition_id') for check in checks}
    expected = set(PRECONDITION_IDS)
    duplicate = len(checks) != len(covered)

    violated = sorted({
        check['precondition_id'] for check in checks
        if check.get('state') == PRECONDITION_VIOLATED
        and check.get('precondition_id') in expected
    })
    not_observed = sorted({
        check['precondition_id'] for check in checks
        if check.get('state') == PRECONDITION_NOT_OBSERVED
        and check.get('precondition_id') in expected
    })
    unknown_state = sorted({
        check.get('precondition_id') for check in checks
        if check.get('state') not in PRECONDITION_STATES
    })

    # Tolerance is REGIME-SCOPED. PRE_EXISTING_REVISION is forgiven only when
    # the row is already at the intended value, where its violation is an
    # arithmetic consequence rather than a finding. When the row is NOT at the
    # intended value, the same violation means the checkpoint holds some third
    # unexpected value — the primary thing this package refuses on — and it
    # must stay blocking.
    already_at_intended = PRE_INTENDED_DIFFERS in violated
    tolerated = (
        ALREADY_APPLIED_TOLERATED_VIOLATIONS if already_at_intended
        else frozenset()
    )

    return {
        'evaluated_count': len(checks),
        'covered_ids': sorted(
            identifier for identifier in covered if identifier
        ),
        'missing_ids': sorted(expected - covered),
        'unexpected_ids': sorted(covered - expected - {None}),
        'duplicate_ids_present': duplicate,
        'coverage_complete': covered == expected and not duplicate,
        'violated': violated,
        'not_observed': not_observed,
        'unknown_state_ids': unknown_state,
        # PRE_INTENDED_DIFFERS is the ONE violated precondition that means
        # "nothing left to do" rather than "something is wrong".
        'already_at_intended_revision': already_at_intended,
        'blocking_violations': [
            identifier for identifier in violated
            if identifier not in tolerated
        ],
        'tolerated_violations': [
            identifier for identifier in violated if identifier in tolerated
        ],
        # A clean no-op requires the row to be at the intended value AND the
        # surrounding state to be entirely intact. "The checkpoint already says
        # what we wanted" is not a safe conclusion when the evidence around it
        # is contradictory: reporting exit 0 there would announce success on a
        # state nobody verified.
        'already_applied_is_clean': (
            already_at_intended
            and covered == expected
            and not duplicate
            and not unknown_state
            and not not_observed
            and not [
                identifier for identifier in violated
                if identifier not in tolerated
            ]
        ),
    }


#: The post-commit lifecycle fields the reducer re-derives from, in the order
#: they must occur. A run that skipped a step cannot have proven the one after
#: it, so the FIRST unmet expectation is the one reported.
POST_COMMIT_PROOF_SEQUENCE = (
    ('post_commit_verification_attempted',
     FAILED_POST_COMMIT_VERIFICATION_INCOMPLETE),
    ('post_commit_read_only_attempted',
     FAILED_POST_COMMIT_VERIFICATION_INCOMPLETE),
    ('post_commit_transaction_read_only',
     FAILED_POST_COMMIT_READ_ONLY_PROOF),
    ('post_commit_verification_completed',
     FAILED_POST_COMMIT_VERIFICATION_INCOMPLETE),
)


def post_commit_proof_failures(post_commit) -> list[str]:
    """Why a landed commit may not be claimed as a completed repair.

    Re-derived from the lifecycle fields themselves rather than from whatever
    reason codes the caller remembered to pass in, so a caller that establishes
    nothing and reports nothing still cannot reach REPAIR_APPLIED. Absent or
    empty input is not neutral here — it is the absence of the proof, which is
    exactly the condition this gate exists to catch.
    """
    post_commit = post_commit or {}
    for field, reason in POST_COMMIT_PROOF_SEQUENCE:
        if post_commit.get(field) is not True:
            return [reason]
    return []


def decide(*, operation, preconditions=None, mutation=None,
           failed_reasons=(), unproven_reasons=(), refusal_reasons=(),
           apply_attempted=False, apply_committed=None,
           post_commit=None) -> dict:
    """One reducer for both operations.

    The completion gate comes first and is structural: an evaluation that does
    not positively cover every governed precondition id, with a recognised
    state on each, is UNPROVEN before any classification branch is reached.
    Nothing may reach a success result by having no evidence to object with.

    Precedence, and why:

    1. FAILED — this package broke its own contract. Nothing else matters, and
       nothing downstream may convert it into anything else.
    2. UNPROVEN — required evidence is missing. A claim is not made.
    3. REPAIR_NOT_REQUIRED — the checkpoint already holds the intended value.
       Resolved before REFUSED so an already-applied repair reads as done
       rather than as declined.
    4. REFUSED — a precondition was positively observed not to hold.
    5. The operation's own success result.

    An apply that was attempted but whose commit outcome was never established
    is UNPROVEN, never applied: a commit nobody observed is not a commit.

    A commit that DID land but whose post-commit proof did not complete is
    FAILED, never applied, and never downgraded to "outcome unknown". Once
    COMMIT returns, rollback is gone and the production row has moved, so
    failing the proof there is this package breaking its own guarantee rather
    than lacking evidence about someone else's.
    """
    preconditions = preconditions or {}
    mutation = mutation or {}

    failed = list(dict.fromkeys(failed_reasons or ()))
    unproven = list(dict.fromkeys(unproven_reasons or ()))
    refused = list(dict.fromkeys(refusal_reasons or ()))

    for reason in (mutation.get('failed_reasons') or ()):
        if reason not in failed:
            failed.append(reason)
    for reason in (mutation.get('unproven_reasons') or ()):
        if reason not in unproven:
            unproven.append(reason)
    # THE COMPLETION GATE. Re-derived from the evaluated checks, never read
    # off a summary flag, and applied BEFORE any classification branch so no
    # branch can route around it.
    coverage = precondition_coverage(preconditions)
    if not coverage['coverage_complete'] or coverage['unknown_state_ids']:
        if UNPROVEN_PRECONDITION_NOT_OBSERVED not in unproven:
            unproven.append(UNPROVEN_PRECONDITION_NOT_OBSERVED)
    for identifier in coverage['not_observed']:
        reason = PRECONDITION_UNPROVEN_REASONS.get(identifier)
        if reason and reason not in unproven:
            unproven.append(reason)
        if UNPROVEN_PRECONDITION_NOT_OBSERVED not in unproven:
            unproven.append(UNPROVEN_PRECONDITION_NOT_OBSERVED)
    for identifier in coverage['blocking_violations']:
        reason = PRECONDITION_REFUSAL_REASONS.get(identifier)
        if reason and reason not in refused:
            refused.append(reason)

    # A clean no-op strips the two intrinsic refusal reasons, because on that
    # path they are not refusals at all. A DIRTY already-applied state keeps
    # every reason it earned and is reported as the refusal it is.
    already_applied = coverage['already_applied_is_clean']
    if already_applied:
        refused = [
            reason for reason in refused
            if reason not in ALREADY_APPLIED_INTRINSIC_REASONS
        ]

    if operation not in OPERATIONS:
        failed.append(FAILED_OPERATION_UNKNOWN)

    if apply_attempted and apply_committed is not True and not failed:
        if apply_committed is None:
            unproven.append(UNPROVEN_APPLY_OUTCOME_UNKNOWN)

    # A commit that landed still has to have been PROVEN to have landed
    # correctly. This gate re-derives that from the lifecycle rather than
    # trusting the reason codes handed in, so an observation layer that
    # silently skipped the proof cannot produce a success verdict.
    if operation == OPERATION_APPLY and apply_committed is True:
        for reason in post_commit_proof_failures(post_commit):
            if reason not in failed:
                failed.append(reason)

    if failed:
        result = RESULT_FAILED
    elif unproven:
        result = RESULT_UNPROVEN
    elif already_applied:
        result = RESULT_NOT_REQUIRED
    elif refused:
        result = RESULT_REFUSED
    elif operation == OPERATION_APPLY:
        result = (
            RESULT_APPLIED if apply_committed is True else RESULT_UNPROVEN
        )
        if result == RESULT_UNPROVEN and (
            UNPROVEN_APPLY_OUTCOME_UNKNOWN not in unproven
        ):
            unproven.append(UNPROVEN_APPLY_OUTCOME_UNKNOWN)
    else:
        result = RESULT_VERIFIED_REQUIRED_AND_SAFE

    return {
        'operation': operation,
        'result': result,
        'exit_code': EXIT_CODES.get(result, EXIT_CODES[RESULT_UNPROVEN]),
        'failed_reasons': failed[:MAX_REASON_CODES],
        'unproven_reasons': unproven[:MAX_REASON_CODES],
        'refusal_reasons': refused[:MAX_REASON_CODES],
        # What DURABLY HAPPENED, not whether the run succeeded. A commit that
        # landed and then failed a safety check is still a commit, and the
        # most safety-critical field in the verdict must never under-report
        # it. RESULT_APPLIED is the separate claim that the run also passed.
        'mutation_performed': apply_committed is True,
        'apply_attempted': bool(apply_attempted),
        'apply_committed': apply_committed,
        'precondition_coverage': coverage,
        'preconditions_all_satisfied': bool(
            coverage['coverage_complete']
            and not coverage['violated']
            and not coverage['not_observed']
        ),
        'prohibited_mutations': list(PROHIBITED_MUTATIONS),
        'permitted_changed_columns': sorted(PERMITTED_CHANGED_COLUMNS),
        'non_authorization_statement': NON_AUTHORIZATION_STATEMENT,
        'dead_letter_backlog_note': DEAD_LETTER_BACKLOG_NOTE,
        'standing_production_state': dict(STANDING_PRODUCTION_STATE),
    }


def explanation(decision) -> str:
    """One paragraph a reviewer can read without the JSON."""
    decision = decision or {}
    result = decision.get('result')
    operation = decision.get('operation')

    if result == RESULT_APPLIED:
        return (
            f'The approved change was applied: {TARGET_TABLE}.'
            f'{TARGET_COLUMN} for game {GAME_PK} moved from the expected old '
            'value to the intended value. Exactly one row was affected, the '
            'observed column delta was exactly source_revision plus the '
            'automatic updated_at bookkeeping timestamp, and no other '
            'governed '
            'table moved.'
        )
    if result == RESULT_NOT_REQUIRED:
        return (
            f'No change was made. The checkpoint for game {GAME_PK} already '
            'holds the intended source revision, so the repair is complete by '
            'observation rather than by action.'
        )
    if result == RESULT_VERIFIED_REQUIRED_AND_SAFE:
        return (
            'Every precondition was positively re-observed and satisfied. The '
            'single approved change is currently required and currently safe. '
            'This is evidence for a human decision, not that decision: no '
            'production row was modified by this run.'
        )
    if result == RESULT_REFUSED:
        reasons = ', '.join(decision.get('refusal_reasons') or ()) or 'unknown'
        return (
            'The repair refused. At least one precondition was positively '
            f'observed not to hold ({reasons}), so nothing was written. A '
            'refusal is a correct outcome of a correctly-working package.'
        )
    if result == RESULT_FAILED:
        reasons = ', '.join(decision.get('failed_reasons') or ()) or 'unknown'
        return (
            f'This package violated its own safety contract ({reasons}). The '
            'result says nothing about whether the platform is healthy; it '
            'says this run may not be trusted.'
        )
    reasons = ', '.join(decision.get('unproven_reasons') or ()) or 'unknown'
    return (
        f'The {operation} run could not obtain required evidence ({reasons}), '
        'so it makes no claim about whether the repair is required or safe. '
        'Nothing was written.'
    )
