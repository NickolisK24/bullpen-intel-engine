"""Manual exact-scope real-mutation qualification.

Proves the game-driven ingestion lane can apply ONE reviewed canonical
statistical correction to ONE existing GameLog row in ONE completed game, and
change nothing else.

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
    services.gamelog_source_authority                field source authority

Contract-neutral primitives — exact game parsing, scope evaluation, source
revision extraction, work-item readback — are imported from
``noop_write_qualification`` rather than copied. Re-deriving the exact-one-game
scope guarantee in a second place is precisely the drift this design exists to
prevent.

How this differs from the no-op qualification
---------------------------------------------
The no-op contract asserts ABSENCE: every counter zero, every digest identical.
This contract asserts an EXACT PRESENCE — one row, one field, one value — and
absence everywhere else. The central assertion is inverted, so the failure
surface is different and the contract is its own.

Measured against the canonical lane, an exclusive write applying one reviewed
single-field statistical correction produces:

    game_log_rows_written              1
    pitcher_rows_written               0
    appearance_team_rows_written       0
    correction_provenance_rows_written 1
    dead_letters_created               0
    work_items_updated                 1
    work_items_completed               1
    checkpoints_advanced               1
    commits_performed                  1

``game_log_rows_written`` is EXACTLY one, never ``>= 1``. The reviewed plan
names one row and one field; anything else is a different mutation than the one
a human authorized.

``correction_provenance_rows_written`` is EXACTLY one, and that was MEASURED
rather than assumed. The canonical writer stamps correction provenance on the
same row it corrects — the lane computes the counter as
``provenance_only_updates + statistical_corrections`` — so a genuine correction
necessarily writes it. Pinning it to zero, as the no-op contract does, would
refuse every correct run. It is one row's provenance for one correction, not a
second baseball mutation, and the plan-level ``provenance_only_updates`` counter
must still be zero: a row that changes ONLY provenance corrects no baseball
value and is not a candidate.

Four terminal results
---------------------
``PASS``                exactly the reviewed mutation happened, and nothing else
``FAILED``              a definite contract violation was observed
``UNPROVEN``            trustworthy evidence could not be completed
``NO_LONGER_MUTATING``  the candidate became already-correct before execution

``NO_LONGER_MUTATING`` is not a PASS and never counts as real-mutation proof. It
is the verdict a replay reaches after a prior successful qualification already
corrected the row, and the verdict a race with the legacy writer reaches.

Field source authority
----------------------
A correction may only be applied to a field whose source authority the
repository has actually resolved. ``inherited_runners`` is refused: its field
authority is recorded UNRESOLVED and failed closed in
``docs/current/GAME_DRIVEN_DAILY_INGESTION.md``, and the deciding diagnostic has
never been run against production. This module encodes that refusal; it does not
resolve the question and must not be used to.

Nothing here authorizes scheduled writes, automated writes, authoritative
publication, backfill, multi-game scope, identity mutation, or any future
mutation. A reviewed fingerprint is evidence of what a plan was, never a token
that permits a later write.
"""

from __future__ import annotations

import hashlib
import re

from models.game_ingestion_work_item import GameIngestionWorkItem
from models.game_log import GameLog
from models.pitcher import Pitcher
from services import gamelog_source_authority as source_authority
from services import game_log_reconciliation as reconciliation
from services import noop_write_qualification as base
from services import pitcher_identity_reconciliation as pitcher_identity


SCHEMA_VERSION = '1'
QUALIFICATION_TYPE = 'manual_game_driven_real_mutation_qualification_v1'

RESULT_PASS = 'PASS'
RESULT_FAILED = 'FAILED'
RESULT_UNPROVEN = 'UNPROVEN'
RESULT_NO_LONGER_MUTATING = 'NO_LONGER_MUTATING'

EXIT_PASS = 0
EXIT_FAILED = 1
EXIT_UNPROVEN = 2
EXIT_NO_LONGER_MUTATING = 3

EXIT_CODES = {
    RESULT_PASS: EXIT_PASS,
    RESULT_FAILED: EXIT_FAILED,
    RESULT_UNPROVEN: EXIT_UNPROVEN,
    RESULT_NO_LONGER_MUTATING: EXIT_NO_LONGER_MUTATING,
}

# ── Authorization constants ─────────────────────────────────────────────────
REQUIRED_REPOSITORY = 'NickolisK24/bullpen-intel-engine'
REQUIRED_REF = 'refs/heads/main'
REQUIRED_EVENT_NAME = 'workflow_dispatch'
REQUIRED_ACTOR = 'NickolisK24'
CONFIRMATION_PREFIX = 'QUALIFY_REAL_MUTATION_GAME_'

NON_AUTHORIZATION_STATEMENT = (
    'This qualification does not authorize scheduled writes, automated '
    'writes, authoritative publication, backfill, multiple-game mutation, '
    'identity mutation, or future mutations. One reviewed correction proves '
    'one reviewed correction.'
)

# Contract-neutral input parsing, reused rather than redeclared.
QualificationInputError = base.QualificationInputError
parse_game_pk = base.parse_game_pk
normalize_sha = base.normalize_sha
sanitize_note = base.sanitize_note
evaluate_scope = base.evaluate_scope
source_revisions = base.source_revisions
read_lane_bookkeeping = base.read_lane_bookkeeping
safe_work_item_state = base.safe_work_item_state
changed_bookkeeping_fields = base.changed_bookkeeping_fields
execution_state = base.execution_state
render_finality = base.render_finality
WORK_ITEM_COLUMNS = base.WORK_ITEM_COLUMNS
STATE_DIGEST_FIELDS = base.STATE_DIGEST_FIELDS

_SHA_PATTERN = re.compile(r'\A[0-9a-f]{40}\Z')
_FINGERPRINT_LENGTH = 64


def expected_confirmation(game_pk) -> str:
    return f'{CONFIRMATION_PREFIX}{int(game_pk)}'


# ── Reason codes ────────────────────────────────────────────────────────────
# FAILED: a definite contract violation was observed.
FAILED_EVENT_NOT_WORKFLOW_DISPATCH = 'event_not_workflow_dispatch'
FAILED_REPOSITORY_NOT_AUTHORIZED = 'repository_not_authorized'
FAILED_ACTOR_NOT_AUTHORIZED = 'actor_not_authorized'
FAILED_REF_NOT_MAIN = 'ref_not_main'
FAILED_EXPECTED_SHA_MALFORMED = 'expected_head_sha_malformed'
FAILED_EXPECTED_SHA_MISMATCH = 'expected_head_sha_mismatch'
FAILED_CONFIRMATION_MISMATCH = 'confirmation_mismatch'
FAILED_REVIEWED_FINGERPRINT_MALFORMED = 'reviewed_plan_fingerprint_malformed'
FAILED_GAME_PK_EMPTY = base.FAILED_GAME_PK_EMPTY
FAILED_GAME_PK_NOT_AN_INTEGER = base.FAILED_GAME_PK_NOT_AN_INTEGER
FAILED_GAME_PK_NOT_POSITIVE = base.FAILED_GAME_PK_NOT_POSITIVE

FAILED_GAME_NOT_PLANNABLE = 'requested_game_not_plannable_or_not_final'
FAILED_SCOPE_NOT_EXACT = 'execution_scope_not_exact'
FAILED_REQUESTED_COUNT_NOT_ONE = 'requested_game_count_not_one'
FAILED_PLANNED_COUNT_NOT_ONE = 'planned_game_count_not_one'
FAILED_FETCHED_COUNT_NOT_ONE = 'fetched_game_count_not_one'
FAILED_COMPLETED_COUNT_NOT_ONE = 'completed_game_count_not_one'
FAILED_DUPLICATE_REQUESTED_GAME = 'duplicate_requested_game'
FAILED_UNEXPECTED_PLANNED_GAME = 'unexpected_planned_game'
FAILED_MISSING_REQUESTED_GAME = 'missing_requested_game'

# Candidate shape.
FAILED_PLAN_UNKNOWN_ACTION = 'plan_contains_unknown_action'
FAILED_PLAN_PROPOSES_INSERT = 'plan_proposes_insert'
FAILED_PLAN_CONTAINS_BLOCKED_ROW = 'plan_contains_blocked_row'
FAILED_PLAN_MULTI_ROW_MUTATION = 'plan_proposes_more_than_one_updated_row'
FAILED_PLAN_MULTI_FIELD_MUTATION = 'plan_proposes_more_than_one_changed_field'
FAILED_PLAN_NOT_STATISTICAL_CORRECTION = 'plan_is_not_a_statistical_correction'
FAILED_PLAN_IS_PROVENANCE_ONLY = 'plan_row_is_provenance_only'
FAILED_PROHIBITED_MUTATION_CATEGORY = 'plan_contains_prohibited_mutation_category'
FAILED_PROHIBITED_IDENTITY_ACTION = 'plan_proposes_identity_mutation'
FAILED_FIELD_NOT_GOVERNED_STATISTICAL = 'changed_field_not_governed_statistical'
FAILED_FIELD_AUTHORITY_UNRESOLVED = 'changed_field_source_authority_unresolved'
FAILED_TARGET_ROW_ABSENT = 'target_row_absent_before_execution'
FAILED_TARGET_ROW_DUPLICATE = 'target_row_duplicated_before_execution'

# Drift.
FAILED_SOURCE_REVISION_CHANGED = 'source_revision_changed_before_execution'
FAILED_SOURCE_REVISION_WRONG_GAME = 'source_revision_for_wrong_game'
FAILED_PLAN_FINGERPRINT_MISMATCH = 'plan_fingerprint_mismatch'
FAILED_REVIEWED_FINGERPRINT_MISMATCH = 'reviewed_plan_fingerprint_mismatch'

# Execution effects.
FAILED_BASEBALL_EFFECTS_UNEXPECTED = 'baseball_data_effects_not_exactly_expected'
FAILED_PROHIBITED_EFFECT_OBSERVED = 'prohibited_mutation_counter_non_zero'
FAILED_PLAN_COUNTERS_UNEXPECTED = 'plan_counters_not_exactly_one_correction'
FAILED_WRITES_NOT_ENABLED = 'write_capable_path_not_entered'
FAILED_PUBLICATION_AUTHORITATIVE = 'publication_authoritative_enabled'
FAILED_LANE_STATUS_NOT_COMPLETE = 'lane_run_did_not_complete'

# Integrity.
FAILED_TARGET_ROW_NOT_REALIZED = 'target_row_did_not_reach_canonical_value'
FAILED_TARGET_ROW_UNREVIEWED_FIELD_CHANGED = (
    'unreviewed_field_changed_on_target_row'
)
FAILED_TARGET_ROW_UNCHANGED_AFTER_WRITE = 'target_row_unchanged_after_write'
FAILED_OTHER_ROWS_CHANGED = 'other_rows_in_game_changed'
FAILED_REALIZATION_UNRESOLVED = 'realization_reported_unresolved_rows'
FAILED_ARTIFACT_FORBIDDEN_CONTENT = 'artifact_forbidden_content_detected'

# Bookkeeping.
FAILED_TARGET_WORK_ITEM_MISSING = 'target_work_item_missing'
FAILED_TARGET_WORK_ITEM_NOT_COMPLETED = 'target_work_item_not_completed'
FAILED_UNEXPECTED_WORK_ITEM_CREATION = 'unexpected_work_item_creation'
FAILED_UNEXPECTED_BOOKKEEPING_COUNTER = 'unexpected_bookkeeping_counter'
FAILED_UNEXPECTED_WORK_ITEM_FIELD_CHANGE = 'unexpected_work_item_field_change'
FAILED_UNRELATED_WORK_ITEM_CHANGED = 'unrelated_work_item_changed'
FAILED_UNRELATED_CHECKPOINT_CHANGED = 'unrelated_checkpoint_changed'
FAILED_CHECKPOINT_DELTA_MISMATCH = 'checkpoint_delta_mismatch'
FAILED_COMMIT_COUNT_MISMATCH = 'commit_count_mismatch'
FAILED_WORK_ITEM_STATUS_UNEXPECTED = 'work_item_status_unexpected'
FAILED_ATTEMPT_COUNT_DELTA_UNEXPECTED = 'attempt_count_delta_unexpected'
FAILED_CORRECTION_COUNT_DELTA_UNEXPECTED = 'correction_count_delta_unexpected'

# UNPROVEN: trustworthy evidence could not be completed.
UNPROVEN_PRE_READBACK_UNAVAILABLE = 'pre_execution_readback_unavailable'
UNPROVEN_POST_READBACK_UNAVAILABLE = 'post_execution_readback_unavailable'
UNPROVEN_REALIZATION_UNAVAILABLE = 'realization_unavailable'
UNPROVEN_SOURCE_REVISION_MISSING = 'source_revision_missing'
UNPROVEN_WRITE_SOURCE_REVISION_MISSING = 'write_phase_source_revision_missing'
UNPROVEN_PLAN_FINGERPRINT_MISSING = 'plan_fingerprint_missing'
UNPROVEN_AUTHORIZED_FINGERPRINT_MISSING = 'authorized_plan_fingerprint_missing'
UNPROVEN_EFFECT_COUNTERS_MISSING = 'execution_effect_counters_incomplete'
UNPROVEN_WRITER_GUARD_UNAVAILABLE = 'writer_guard_unavailable'
UNPROVEN_WRITER_GUARD_RELEASE_UNPROVEN = 'writer_guard_release_unproven'
UNPROVEN_SHADOW_PHASE_UNUSABLE = 'shadow_phase_produced_no_usable_plan'
UNPROVEN_BOOKKEEPING_READBACK_UNAVAILABLE = 'bookkeeping_readback_unavailable'
UNPROVEN_ARTIFACT_SCAN_UNAVAILABLE = 'artifact_scan_unavailable'
UNPROVEN_ARTIFACT_BUILD_FAILED = 'artifact_construction_failed'
UNPROVEN_LANE_ERROR = 'lane_execution_error'

# NO_LONGER_MUTATING: the candidate was valid when reviewed and is not now.
NO_LONGER_MUTATING_PLAN_IS_CLEAN = 'reviewed_correction_already_applied'


# ── Field source authority ──────────────────────────────────────────────────
# The canonical authority contract is
# ``player_split_primary_with_boxscore_fallback``: the player game-log split is
# the primary source for governed statistical fields, and the completed-game box
# score is an approved fallback for exactly the fields
# ``gamelog_source_authority.APPROVED_FALLBACK_FIELDS`` names.
#
# A field is eligible for a real-mutation qualification only when the repository
# has NOT recorded an open question about which source is authoritative for it.
# This is a denylist rather than an allowlist because the repository's recorded
# position is that the primary split is authoritative by default; an allowlist
# would misdescribe that and would refuse every field except ``balls``.
#
# Each entry must cite a current, canonical record of the open question. Nothing
# may be added here casually, and nothing may be REMOVED here except by a
# decision that records how the authority was resolved — which is a governance
# act, never an implementation detail.
UNRESOLVED_SOURCE_AUTHORITY_FIELDS = frozenset({
    # docs/current/GAME_DRIVEN_DAILY_INGESTION.md
    #   "GameLog `inherited_runners` — field authority UNRESOLVED"
    #   Status: unresolved, failed closed. The deciding diagnostic
    #   (scripts/inspect_gamelog_field_authority.py) has never been run against
    #   production; the recorded artifact reports
    #   discrepancy_classification: unresolved, authority_resolved: false.
    'inherited_runners',
    # Refused with the same open question. The runbook's REPORT_PROFILES entry
    # for `inherited_runners` audits `inherited_runners_scored` alongside it, and
    # no separate resolution has been recorded for the companion statistic.
    # Refusing a field the repository has not positively resolved can only ever
    # decline a candidate; it can never permit a wrong write.
    'inherited_runners_scored',
})

FIELD_AUTHORITY_RESOLVED = 'resolved'
FIELD_AUTHORITY_UNRESOLVED = 'unresolved'
FIELD_AUTHORITY_NOT_GOVERNED = 'not_a_governed_statistical_field'


def field_authority_resolved(field) -> bool:
    """Whether one field's source authority is settled enough to be corrected.

    Fails closed twice: a field outside the canonical statistical vocabulary is
    refused, and a field with a recorded open authority question is refused.
    """
    return (
        field in reconciliation.STATISTICAL_FIELDS
        and field not in UNRESOLVED_SOURCE_AUTHORITY_FIELDS
    )


def field_authority_state(field) -> str:
    if field not in reconciliation.STATISTICAL_FIELDS:
        return FIELD_AUTHORITY_NOT_GOVERNED
    if field in UNRESOLVED_SOURCE_AUTHORITY_FIELDS:
        return FIELD_AUTHORITY_UNRESOLVED
    return FIELD_AUTHORITY_RESOLVED


def describe_field_authority(field) -> dict:
    """Reportable authority decision for one field. Names only, never values."""
    state = field_authority_state(field)
    return {
        'field': field,
        'authority_state': state,
        'authority_resolved': state == FIELD_AUTHORITY_RESOLVED,
        'field_category': reconciliation.field_category(field),
        'authority_contract': source_authority.AUTHORITY_CONTRACT,
        'authority_version': source_authority.AUTHORITY_VERSION,
        'approved_fallback_field': source_authority.is_approved_fallback_field(
            field
        ),
        'unresolved_authority_fields': sorted(
            UNRESOLVED_SOURCE_AUTHORITY_FIELDS
        ),
    }


# ── Plan governance ─────────────────────────────────────────────────────────
KNOWN_ACTIONS = frozenset({
    reconciliation.ACTION_UNCHANGED,
    reconciliation.ACTION_INSERT,
    reconciliation.ACTION_UPDATE,
    reconciliation.ACTION_BLOCKED,
})

# The only two row actions a v1 real-mutation plan may contain: exactly one
# ``update`` and any number of ``unchanged``.
PERMITTED_ACTIONS = frozenset({
    reconciliation.ACTION_UNCHANGED,
    reconciliation.ACTION_UPDATE,
})

# Identity decisions, exactly as restrictive as the no-op contract. D-009
# permits creation and reactivation in a normal governed run; this stage refuses
# them so identity authority stays outside it entirely.
PERMITTED_IDENTITY_ACTIONS = frozenset({
    pitcher_identity.ACTION_UNCHANGED,
    None,
})

# The mutation categories the reviewed row may carry.
#
# MEASURED: the canonical planner appends CATEGORY_PROVENANCE_ONLY to EVERY
# genuine statistical correction, because the correction stamps provenance on the
# row it corrects. It is therefore permitted here. What is refused is the row
# being provenance-only — `is_provenance_only`, a separate flag the planner sets
# when a row changes provenance and no published evidence. Such a row corrects no
# baseball value and is not a real-mutation candidate.
PERMITTED_MUTATION_CATEGORIES = frozenset({
    reconciliation.CATEGORY_STATISTICAL_CORRECTION,
    reconciliation.CATEGORY_PROVENANCE_ONLY,
    reconciliation.CATEGORY_UNCHANGED,
})

PROHIBITED_MUTATION_CATEGORIES = frozenset({
    reconciliation.CATEGORY_APPEARANCE_TEAM_AUTHORITY,
    reconciliation.CATEGORY_ROLE_SIGNAL,
    reconciliation.CATEGORY_GAME_METADATA,
    reconciliation.CATEGORY_PITCHER_IDENTITY,
    reconciliation.CATEGORY_BLOCKED,
})

# Report-level plan counters that must be exactly zero for a v1 candidate.
PROHIBITED_PLAN_COUNTERS = (
    'rows_inserted',
    'rows_blocked',
    'authority_reconciliations',
    'provenance_only_updates',
    'canonical_outs_corrections',
    'pitcher_identity_mutations',
    'pitcher_identity_creations',
    'pitcher_identity_reactivations',
    'pitcher_identity_metadata_updates',
    'pitcher_identity_blocked',
    'appearance_team_mutations',
)

# Report-level plan counters that must hold exactly these values.
EXPECTED_PLAN_COUNTERS = {
    'rows_updated': 1,
    'statistical_corrections': 1,
}

# ── Execution effect contract ───────────────────────────────────────────────
# Baseball data. Exactly one GameLog row is written; every other baseball effect
# is exactly zero. Deliberately exact integers rather than ``>= 1``: the reviewed
# plan named one row, so any other count is a different mutation.
EXPECTED_BASEBALL_DATA_EFFECTS = {
    'game_log_rows_written': 1,
    'pitcher_rows_written': 0,
    'appearance_team_rows_written': 0,
    # MEASURED, not assumed. `_process_one_game` records this counter as
    # `provenance_only_updates + statistical_corrections`, so the one correction
    # stamps provenance on the row it corrects. Pinning it to zero would refuse
    # every correct run. See the module docstring.
    'correction_provenance_rows_written': 1,
    'dead_letters_created': 0,
}

BASEBALL_DATA_EFFECT_FIELDS = tuple(sorted(EXPECTED_BASEBALL_DATA_EFFECTS))

LANE_BOOKKEEPING_EFFECT_FIELDS = base.LANE_BOOKKEEPING_EFFECT_FIELDS

REQUIRED_EFFECT_FIELDS = (
    ('writes_enabled', 'publication_authoritative')
    + BASEBALL_DATA_EFFECT_FIELDS
    + LANE_BOOKKEEPING_EFFECT_FIELDS
)

# ── Lane bookkeeping governance ─────────────────────────────────────────────
# A real correction legitimately moves MORE work-item state than a no-op run
# does, so the no-op contract's permitted set is deliberately NOT reused.
#
# ``_complete_work_item`` increments ``correction_count`` when a correction was
# applied and re-stamps ``completion_proof`` with what this run did, on top of
# the fields a no-op run already moves. ``rows_reconciled`` and
# ``source_revision`` are re-asserted from the run that just executed and may
# legitimately differ from the values a prior run stored.
BOOKKEEPING_ALLOWED_CHANGED_FIELDS = frozenset({
    'candidate_reason',
    'attempt_count',
    'last_attempted_at',
    'completed_at',
    'completion_proof',
    'updated_at',
    # Real-correction additions, absent from the no-op contract.
    'correction_count',
    'rows_reconciled',
    'relief_rows_reconciled',
    'source_revision',
})

BOOKKEEPING_REQUIRED_UNCHANGED_FIELDS = tuple(sorted(
    set(WORK_ITEM_COLUMNS) - BOOKKEEPING_ALLOWED_CHANGED_FIELDS
))

BOOKKEEPING_CHECKPOINT_FIELDS = base.BOOKKEEPING_CHECKPOINT_FIELDS
BOOKKEEPING_LIFECYCLE_FIELDS = base.BOOKKEEPING_LIFECYCLE_FIELDS

EXPECTED_LANE_BOOKKEEPING_DELTA = {
    'work_items_created': 0,
    'work_items_updated': 1,
    'work_items_completed': 1,
    'checkpoints_advanced': 1,
    'commits_performed': 1,
}

# The work item must already exist and must already be completed. This stage
# proves re-reconciliation of a settled game; it does not prove first ingestion.
REQUIRED_WORK_ITEM_STATUS_BEFORE = GameIngestionWorkItem.STATUS_COMPLETED
REQUIRED_WORK_ITEM_STATUS_AFTER = GameIngestionWorkItem.STATUS_COMPLETED

EXPECTED_ATTEMPT_COUNT_DELTA = 1
EXPECTED_CORRECTION_COUNT_DELTA = 1


# ── Input validation ────────────────────────────────────────────────────────


def parse_reviewed_fingerprint(raw) -> str:
    """Parse the reviewed plan fingerprint. Shape only, never authority.

    A fingerprint is evidence of what a plan was. Accepting a malformed one
    would let an operator hand the lane a value it can only fail to match, which
    reads as drift rather than as the input error it is.
    """
    text = str(raw or '').strip().lower()
    if len(text) != _FINGERPRINT_LENGTH or not all(
        character in '0123456789abcdef' for character in text
    ):
        raise QualificationInputError(FAILED_REVIEWED_FINGERPRINT_MALFORMED)
    return text


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


# ── Candidate plan evaluation ───────────────────────────────────────────────


def plan_rows(report) -> list[dict]:
    return [
        row
        for game in (report.get('games') or ())
        for row in (game.get('rows') or ())
    ]


def evaluate_candidate_plan(report, *, game_pk) -> dict:
    """Classify a reconciliation plan against the exact v1 candidate contract.

    Returns the failure reason codes plus the reviewed-mutation descriptor. A
    plan is a valid candidate only when EVERY condition is positively observed:
    exactly one ``update`` row, exactly one changed field, a governed statistical
    field with resolved source authority, no prohibited category, no identity
    mutation, and every other row ``unchanged``.

    A plan with no update at all is not a failure — it is the
    ``NO_LONGER_MUTATING`` state, reported through ``mutation_present``.
    """
    rows = plan_rows(report)
    reasons: list[str] = []
    action_counts: dict[str, int] = {}
    identity_action_counts: dict[str, int] = {}
    prohibited: dict[str, int] = {}

    update_rows = []
    for row in rows:
        action = row.get('action')
        key = str(action)
        action_counts[key] = action_counts.get(key, 0) + 1

        if action not in KNOWN_ACTIONS:
            prohibited[f'unknown_action:{key}'] = (
                prohibited.get(f'unknown_action:{key}', 0) + 1
            )
        elif action == reconciliation.ACTION_INSERT:
            prohibited[f'action:{key}'] = prohibited.get(f'action:{key}', 0) + 1
        elif action == reconciliation.ACTION_BLOCKED:
            prohibited[f'action:{key}'] = prohibited.get(f'action:{key}', 0) + 1
        elif action == reconciliation.ACTION_UPDATE:
            update_rows.append(row)

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
        if (
            action == reconciliation.ACTION_UNCHANGED
            and row.get('changed_fields')
        ):
            prohibited['changed_fields_on_unchanged_row'] = (
                prohibited.get('changed_fields_on_unchanged_row', 0) + 1
            )

    if any(key.startswith('unknown_action:') for key in prohibited):
        reasons.append(FAILED_PLAN_UNKNOWN_ACTION)
    if action_counts.get(reconciliation.ACTION_INSERT):
        reasons.append(FAILED_PLAN_PROPOSES_INSERT)
    if action_counts.get(reconciliation.ACTION_BLOCKED):
        reasons.append(FAILED_PLAN_CONTAINS_BLOCKED_ROW)
    if any(key.startswith('identity:') for key in prohibited):
        reasons.append(FAILED_PROHIBITED_IDENTITY_ACTION)

    plan_counters = {
        field: _as_int(report.get(field))
        for field in PROHIBITED_PLAN_COUNTERS
    }
    nonzero_prohibited_counters = {
        field: value for field, value in plan_counters.items() if value != 0
    }
    if nonzero_prohibited_counters:
        reasons.append(FAILED_PROHIBITED_EFFECT_OBSERVED)

    descriptor = None
    authority = None
    if len(update_rows) > 1:
        reasons.append(FAILED_PLAN_MULTI_ROW_MUTATION)
    elif len(update_rows) == 1:
        row = update_rows[0]
        changed_fields = list(row.get('semantic_changed_fields') or ())
        if not changed_fields:
            changed_fields = list(row.get('changed_fields') or ())

        categories = set(row.get('mutation_categories') or ())
        if categories & PROHIBITED_MUTATION_CATEGORIES:
            reasons.append(FAILED_PROHIBITED_MUTATION_CATEGORY)
        if not row.get('is_statistical_correction'):
            reasons.append(FAILED_PLAN_NOT_STATISTICAL_CORRECTION)
        # Provenance moved but no published evidence did. Nothing baseball
        # changed, so there is no correction to qualify.
        if row.get('is_provenance_only'):
            reasons.append(FAILED_PLAN_IS_PROVENANCE_ONLY)

        if len(changed_fields) != 1:
            reasons.append(FAILED_PLAN_MULTI_FIELD_MUTATION)
        else:
            field = changed_fields[0]
            authority = describe_field_authority(field)
            if authority['authority_state'] == FIELD_AUTHORITY_NOT_GOVERNED:
                reasons.append(FAILED_FIELD_NOT_GOVERNED_STATISTICAL)
            elif authority['authority_state'] == FIELD_AUTHORITY_UNRESOLVED:
                reasons.append(FAILED_FIELD_AUTHORITY_UNRESOLVED)

            descriptor = {
                'game_pk': _as_int(row.get('game_pk')),
                'pitcher_mlb_id': _as_int(row.get('pitcher_mlb_id')),
                'field': field,
                'field_category': reconciliation.field_category(field),
                'classification': (
                    reconciliation.CATEGORY_STATISTICAL_CORRECTION
                ),
                'difference_classifications': list(
                    row.get('difference_classifications') or ()
                ),
                'target_fields': list(row.get('target_fields') or ()),
                'target_state_digest': row.get('target_state_digest'),
                'stored_state_digest': row.get('stored_state_digest'),
                'mutation_digest': row.get('mutation_digest'),
                'affects_published_evidence': bool(
                    row.get('affects_published_evidence')
                ),
            }
            if descriptor['game_pk'] != int(game_pk):
                reasons.append(FAILED_UNEXPECTED_PLANNED_GAME)
            if not descriptor['target_fields']:
                reasons.append(FAILED_PLAN_MULTI_FIELD_MUTATION)

    for field, expected in EXPECTED_PLAN_COUNTERS.items():
        if update_rows and _as_int(report.get(field)) != expected:
            reasons.append(FAILED_PLAN_COUNTERS_UNEXPECTED)

    return {
        'planned_row_count': len(rows),
        'planned_action_counts': dict(sorted(action_counts.items())),
        'planned_identity_action_counts': dict(
            sorted(identity_action_counts.items())
        ),
        'prohibited_action_counts': dict(sorted(prohibited.items())),
        'planned_update_row_count': len(update_rows),
        'planned_unchanged_count': action_counts.get(
            reconciliation.ACTION_UNCHANGED, 0
        ),
        'prohibited_plan_counters': dict(sorted(plan_counters.items())),
        'nonzero_prohibited_plan_counters': dict(
            sorted(nonzero_prohibited_counters.items())
        ),
        'expected_plan_counters': dict(sorted(EXPECTED_PLAN_COUNTERS.items())),
        'observed_plan_counters': {
            field: _as_int(report.get(field))
            for field in sorted(EXPECTED_PLAN_COUNTERS)
        },
        'mutation_present': bool(update_rows),
        'reviewed_mutation': descriptor,
        'field_authority': authority,
        'failed_reasons': sorted(set(reasons)),
        'is_valid_candidate': bool(
            len(update_rows) == 1 and descriptor is not None and not reasons
        ),
    }


def single_source_revision(entries, game_pk) -> dict:
    """Require exactly one non-null revision, for exactly the requested game."""
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


# ── Canonical state readback ────────────────────────────────────────────────


def read_target_row_state(*, game_pk, pitcher_mlb_id, reviewed_field) -> dict | None:
    """Read the one row the reviewed plan targets, plus every other row.

    The target row legitimately changes, so whole-game digest equality — the
    no-op invariant — cannot be used. Three digests are captured instead:

    ``target_row_digest``     the whole governed row, expected to CHANGE
    ``target_unreviewed_digest``
                              the governed row minus the reviewed field,
                              expected to be IDENTICAL
    ``other_rows_digest``     every other row in the game, expected to be
                              IDENTICAL

    Returns ``None`` when the read cannot be completed — the caller turns that
    into UNPROVEN rather than assuming the state was as intended.
    """
    try:
        pitcher = Pitcher.query.filter(
            Pitcher.mlb_id == pitcher_mlb_id
        ).one_or_none()
        local_id = pitcher.id if pitcher is not None else None

        records = GameLog.query.filter(
            GameLog.mlb_game_pk == game_pk
        ).all()

        target_matches = [
            record for record in records
            if local_id is not None and record.pitcher_id == local_id
        ]
        others = [
            record for record in records
            if local_id is None or record.pitcher_id != local_id
        ]

        unreviewed_fields = tuple(
            field for field in STATE_DIGEST_FIELDS if field != reviewed_field
        )

        target = target_matches[0] if len(target_matches) == 1 else None
        return {
            'available': True,
            'identity_resolved': local_id is not None,
            'game_row_count': len(records),
            'target_row_count': len(target_matches),
            'other_row_count': len(others),
            'reviewed_field': reviewed_field,
            'reviewed_field_value': (
                getattr(target, reviewed_field, None)
                if target is not None else None
            ),
            'target_row_digest': (
                reconciliation.stored_state_digest(target, STATE_DIGEST_FIELDS)
                if target is not None else ''
            ),
            'target_unreviewed_digest': (
                reconciliation.stored_state_digest(target, unreviewed_fields)
                if target is not None else ''
            ),
            'other_rows_digest': _digest_rows(others),
        }
    except Exception:  # noqa: BLE001 - a failed read is UNPROVEN, never PASS
        return None


def realized_target_digest(*, game_pk, pitcher_mlb_id, target_fields) -> str | None:
    """Digest the stored row over exactly the fields the plan intended.

    Comparable with the plan's ``target_state_digest`` by construction: the same
    canonical encoder over the same field names. This is the positive proof that
    the row reached the canonical value, not merely that nothing diverged.
    """
    try:
        pitcher = Pitcher.query.filter(
            Pitcher.mlb_id == pitcher_mlb_id
        ).one_or_none()
        if pitcher is None:
            return None
        records = GameLog.query.filter(
            GameLog.mlb_game_pk == game_pk,
            GameLog.pitcher_id == pitcher.id,
        ).all()
        if len(records) != 1:
            return None
        return reconciliation.stored_state_digest(
            records[0], list(target_fields or ())
        )
    except Exception:  # noqa: BLE001 - a failed read is UNPROVEN, never PASS
        return None


def _digest_rows(records) -> str:
    entries = sorted(
        (
            record.pitcher_id or 0,
            reconciliation.stored_state_digest(record, STATE_DIGEST_FIELDS),
        )
        for record in records or ()
    )
    encoded = '|'.join(f'{pitcher_id}:{digest}' for pitcher_id, digest in entries)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


# ── Execution effects ───────────────────────────────────────────────────────


def split_execution_effects(report) -> dict:
    """Separate baseball-data effects from lane bookkeeping.

    Both groups carry their real measured values. Nothing is zeroed to make a
    verdict reachable.
    """
    effects = report.get('execution_effects')
    if not isinstance(effects, dict):
        return {
            'available': False,
            'missing_fields': list(REQUIRED_EFFECT_FIELDS),
            'baseball_data': {},
            'lane_bookkeeping': {},
            'baseball_data_matches_expected': None,
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
    unexpected = {
        field: value for field, value in sorted(baseball.items())
        if value != EXPECTED_BASEBALL_DATA_EFFECTS[field]
    }
    return {
        'available': not missing,
        'missing_fields': missing,
        'writes_enabled': bool(effects.get('writes_enabled')),
        'publication_authoritative': bool(
            effects.get('publication_authoritative')
        ),
        'baseball_data': baseball,
        'expected_baseball_data': dict(
            sorted(EXPECTED_BASEBALL_DATA_EFFECTS.items())
        ),
        'unexpected_baseball_data': unexpected,
        'baseball_data_matches_expected': not unexpected,
        'lane_bookkeeping': bookkeeping,
        'transaction_boundary_entered': _as_int(
            effects.get('commits_performed')
        ) > 0,
        'baseball_row_mutation_performed': sum(baseball.values()) > 0,
    }


def evaluate_lane_bookkeeping(before, after, effects) -> dict:
    """Govern the exact shape and scope of the lane ledger movement.

    A real correction moves more than a no-op run does, and the extra movement
    is EXPECTED rather than merely tolerated: ``correction_count`` must advance
    by exactly one, because that is what makes the ledger say a correction
    happened.
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
        failed.append(FAILED_TARGET_WORK_ITEM_MISSING)

    changed = changed_bookkeeping_fields(target_before, target_after)
    unexpected_changed = sorted(
        set(changed) - BOOKKEEPING_ALLOWED_CHANGED_FIELDS
    )
    if unexpected_changed:
        failed.append(FAILED_UNEXPECTED_WORK_ITEM_FIELD_CHANGE)

    correction_delta = None
    if target_before and target_after:
        if target_before.get('status') != REQUIRED_WORK_ITEM_STATUS_BEFORE:
            failed.append(FAILED_WORK_ITEM_STATUS_UNEXPECTED)
        if target_after.get('status') != REQUIRED_WORK_ITEM_STATUS_AFTER:
            failed.append(FAILED_WORK_ITEM_STATUS_UNEXPECTED)

        attempts_before = _as_int(target_before.get('attempt_count'))
        attempts_after = _as_int(target_after.get('attempt_count'))
        if attempts_after - attempts_before != EXPECTED_ATTEMPT_COUNT_DELTA:
            failed.append(FAILED_ATTEMPT_COUNT_DELTA_UNEXPECTED)

        # The ledger must say a correction happened, exactly once.
        corrections_before = _as_int(target_before.get('correction_count'))
        corrections_after = _as_int(target_after.get('correction_count'))
        correction_delta = corrections_after - corrections_before
        if correction_delta != EXPECTED_CORRECTION_COUNT_DELTA:
            failed.append(FAILED_CORRECTION_COUNT_DELTA_UNEXPECTED)

    if before.get('available') and after.get('available'):
        if before.get('unrelated_work_items_digest') != after.get(
            'unrelated_work_items_digest'
        ):
            failed.append(FAILED_UNRELATED_WORK_ITEM_CHANGED)
        if before.get('unrelated_checkpoints_digest') != after.get(
            'unrelated_checkpoints_digest'
        ):
            failed.append(FAILED_UNRELATED_CHECKPOINT_CHANGED)

    effects = effects or {}
    observed = dict(effects.get('lane_bookkeeping') or {})
    if not effects.get('available'):
        return _bookkeeping_result(
            failed, unproven, before, after, target_before, target_after,
            changed, unexpected_changed, observed,
            delta_match=None, correction_delta=correction_delta,
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
        changed, unexpected_changed, observed,
        delta_match=delta_match, correction_delta=correction_delta,
    )


def _bookkeeping_result(failed, unproven, before, after, target_before,
                        target_after, changed, unexpected_changed, observed,
                        *, delta_match, correction_delta) -> dict:
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
        'expected_correction_count_delta': EXPECTED_CORRECTION_COUNT_DELTA,
        'observed_correction_count_delta': correction_delta,
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


def _as_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


# ── Verdict ─────────────────────────────────────────────────────────────────


def decide(evidence) -> dict:
    """Reduce collected evidence to one of the four terminal results.

    Precedence is FAILED, then UNPROVEN, then NO_LONGER_MUTATING, then PASS.

    FAILED outranks everything: an observed violation is a stronger statement
    than absent evidence. UNPROVEN outranks NO_LONGER_MUTATING because
    "the correction was already applied" is itself a positive claim about
    production state, and untrustworthy evidence cannot support it either.
    PASS is reachable only when every contract condition was positively
    observed — never because nothing raised.
    """
    failed = list(evidence.get('failed_reasons') or ())
    unproven = list(evidence.get('unproven_reasons') or ())
    no_longer_mutating = bool(evidence.get('no_longer_mutating'))

    if failed:
        result = RESULT_FAILED
    elif unproven:
        result = RESULT_UNPROVEN
    elif no_longer_mutating:
        result = RESULT_NO_LONGER_MUTATING
    else:
        result = RESULT_PASS

    return {
        'result': result,
        'exit_code': EXIT_CODES[result],
        'failed_reasons': sorted(set(failed)),
        'unproven_reasons': sorted(set(unproven)),
        'no_longer_mutating': no_longer_mutating,
        'non_authorization_statement': NON_AUTHORIZATION_STATEMENT,
    }


def assess(*, context, game_pk, reviewed_fingerprint, shadow_report,
           write_report, before_state, after_state, realized_digest,
           realization, artifact_scan=None, bookkeeping_before=None,
           bookkeeping_after=None, writer_guard=None) -> dict:
    """Apply the full real-mutation contract to the collected evidence.

    Pure: takes reports and readbacks, returns reason codes. Every condition in
    the contract is checked here in one place so the failure matrix can be
    executed by tests rather than described in prose.
    """
    failed: list[str] = []
    unproven: list[str] = []

    failed.extend(validate_authorization(context, game_pk=game_pk))

    shadow_report = shadow_report or {}
    write_report = write_report or {}

    # ── Scope, proven on the phase that actually executed ───────────────────
    scope = evaluate_scope(write_report, game_pk=game_pk)
    shadow_scope = evaluate_scope(shadow_report, game_pk=game_pk)

    if shadow_scope['planned_game_count'] == 0:
        failed.append(FAILED_GAME_NOT_PLANNABLE)
    if scope['duplicate_requested_count'] or shadow_scope[
        'duplicate_requested_count'
    ]:
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

    # ── Lane refusal statuses map to their specific causes ──────────────────
    from services import game_driven_ingestion as lane

    write_status = write_report.get('status')
    if write_status == lane.STATUS_PLAN_FINGERPRINT_MISMATCH:
        failed.append(FAILED_PLAN_FINGERPRINT_MISMATCH)
    elif write_status in (
        lane.STATUS_SCOPE_MISMATCH, lane.STATUS_SCOPE_INVALID,
    ):
        failed.append(FAILED_SCOPE_NOT_EXACT)
    elif write_status == lane.STATUS_PLAN_AUTHORIZATION_REQUIRED:
        unproven.append(UNPROVEN_PLAN_FINGERPRINT_MISSING)
    elif write_status != 'complete':
        failed.append(FAILED_LANE_STATUS_NOT_COMPLETE)

    # ── Candidate plan governance on both phases ────────────────────────────
    shadow_candidate = evaluate_candidate_plan(shadow_report, game_pk=game_pk)
    write_candidate = evaluate_candidate_plan(write_report, game_pk=game_pk)

    if not shadow_candidate['planned_row_count']:
        unproven.append(UNPROVEN_SHADOW_PHASE_UNUSABLE)
    failed.extend(shadow_candidate['failed_reasons'])
    failed.extend(write_candidate['failed_reasons'])

    # A shadow plan with rows but no update means the reviewed correction is
    # already applied. That is NO_LONGER_MUTATING, never a failure and never a
    # PASS. The runner normally refuses before the write phase on exactly this
    # condition; the same conclusion is reachable here so no caller can turn it
    # into a different verdict.
    no_longer_mutating = bool(
        shadow_candidate['planned_row_count']
        and not shadow_candidate['mutation_present']
    )

    reviewed = shadow_candidate.get('reviewed_mutation')

    # ── Fingerprints: POSITIVE proof, never absence of a mismatch ───────────
    shadow_fingerprint = shadow_report.get('reconciliation_plan_fingerprint')
    authorized_fingerprint = write_report.get('authorized_plan_fingerprint')
    fingerprint_match = False
    reviewed_fingerprint_match = False

    if not shadow_fingerprint:
        unproven.append(UNPROVEN_PLAN_FINGERPRINT_MISSING)
    if not authorized_fingerprint:
        unproven.append(UNPROVEN_AUTHORIZED_FINGERPRINT_MISSING)
    if shadow_fingerprint and authorized_fingerprint:
        if shadow_fingerprint == authorized_fingerprint:
            fingerprint_match = True
        else:
            failed.append(FAILED_PLAN_FINGERPRINT_MISMATCH)

    # The operator reviewed a specific plan. The shadow phase this run executed
    # must be that same plan, or the human authorized something else.
    if reviewed_fingerprint and shadow_fingerprint:
        if reviewed_fingerprint == shadow_fingerprint:
            reviewed_fingerprint_match = True
        else:
            failed.append(FAILED_REVIEWED_FINGERPRINT_MISMATCH)

    # ── Source revisions: POSITIVE proof for BOTH phases ────────────────────
    shadow_revisions = source_revisions(shadow_report)
    write_revisions = source_revisions(write_report)
    source_revision_match = False

    shadow_revision = single_source_revision(shadow_revisions, game_pk)
    write_revision = single_source_revision(write_revisions, game_pk)

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

    # ── Execution effects: EXACT, never ">= 1" ──────────────────────────────
    effects = split_execution_effects(write_report)
    if not effects['available']:
        unproven.append(UNPROVEN_EFFECT_COUNTERS_MISSING)
    else:
        if not effects['baseball_data_matches_expected']:
            failed.append(FAILED_BASEBALL_EFFECTS_UNEXPECTED)
        if not effects['writes_enabled']:
            failed.append(FAILED_WRITES_NOT_ENABLED)
        if effects['publication_authoritative']:
            failed.append(FAILED_PUBLICATION_AUTHORITATIVE)

    # ── Before / after integrity ────────────────────────────────────────────
    integrity = evaluate_row_integrity(
        before_state=before_state,
        after_state=after_state,
        realized_digest=realized_digest,
        reviewed=reviewed,
    )
    failed.extend(integrity['failed_reasons'])
    unproven.extend(integrity['unproven_reasons'])

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

    # ── Lane bookkeeping ────────────────────────────────────────────────────
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
        elif not (guard.get('release_attempted') and guard.get('released')):
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
        'no_longer_mutating': no_longer_mutating,
    })
    decision['scope'] = scope
    decision['shadow_scope'] = shadow_scope
    decision['shadow_candidate'] = shadow_candidate
    decision['write_candidate'] = write_candidate
    decision['reviewed_mutation'] = reviewed
    decision['field_authority'] = shadow_candidate.get('field_authority')
    decision['execution_effects'] = effects
    decision['shadow_plan_fingerprint'] = shadow_fingerprint
    decision['authorized_plan_fingerprint'] = authorized_fingerprint
    decision['reviewed_plan_fingerprint'] = reviewed_fingerprint
    decision['plan_fingerprint_match'] = fingerprint_match
    decision['reviewed_plan_fingerprint_match'] = reviewed_fingerprint_match
    decision['source_revisions_before'] = shadow_revisions
    decision['source_revisions_before_execution'] = write_revisions
    decision['shadow_source_revision_state'] = shadow_revision['state']
    decision['write_source_revision_state'] = write_revision['state']
    decision['source_revision_match'] = source_revision_match
    decision['integrity'] = integrity
    decision['lane_bookkeeping'] = {
        key: value for key, value in bookkeeping.items()
        if key not in ('failed_reasons', 'unproven_reasons')
    }
    decision['writer_guard'] = {
        'acquired': bool(guard.get('acquired')),
        'release_attempted': bool(guard.get('release_attempted')),
        'released': bool(guard.get('released')),
    }
    return decision


def evaluate_row_integrity(*, before_state, after_state, realized_digest,
                           reviewed) -> dict:
    """Prove the target changed exactly as reviewed, and nothing else moved."""
    failed: list[str] = []
    unproven: list[str] = []

    if not before_state or not before_state.get('available'):
        unproven.append(UNPROVEN_PRE_READBACK_UNAVAILABLE)
    if not after_state or not after_state.get('available'):
        unproven.append(UNPROVEN_POST_READBACK_UNAVAILABLE)

    before_state = before_state or {}
    after_state = after_state or {}
    usable = bool(
        before_state.get('available') and after_state.get('available')
    )

    if usable:
        if before_state.get('target_row_count') == 0:
            failed.append(FAILED_TARGET_ROW_ABSENT)
        elif before_state.get('target_row_count', 0) > 1:
            failed.append(FAILED_TARGET_ROW_DUPLICATE)
        if after_state.get('target_row_count') == 0:
            failed.append(FAILED_TARGET_ROW_ABSENT)
        elif after_state.get('target_row_count', 0) > 1:
            failed.append(FAILED_TARGET_ROW_DUPLICATE)

        # Every other row in the game must be byte-identical.
        if before_state.get('other_rows_digest') != after_state.get(
            'other_rows_digest'
        ):
            failed.append(FAILED_OTHER_ROWS_CHANGED)

        # Every governed field on the target row EXCEPT the reviewed one must
        # be byte-identical.
        if before_state.get('target_unreviewed_digest') != after_state.get(
            'target_unreviewed_digest'
        ):
            failed.append(FAILED_TARGET_ROW_UNREVIEWED_FIELD_CHANGED)

        # The reviewed field must actually have moved.
        if before_state.get('target_row_digest') == after_state.get(
            'target_row_digest'
        ):
            failed.append(FAILED_TARGET_ROW_UNCHANGED_AFTER_WRITE)

    # The row must hold exactly the value the reviewed plan intended. Proven by
    # the canonical encoder over the canonical target fields, not by inspection.
    expected_digest = (reviewed or {}).get('target_state_digest')
    if reviewed is None:
        unproven.append(UNPROVEN_SHADOW_PHASE_UNUSABLE)
    elif realized_digest is None:
        unproven.append(UNPROVEN_POST_READBACK_UNAVAILABLE)
    elif not expected_digest:
        unproven.append(UNPROVEN_SHADOW_PHASE_UNUSABLE)
    elif realized_digest != expected_digest:
        failed.append(FAILED_TARGET_ROW_NOT_REALIZED)

    return {
        'failed_reasons': failed,
        'unproven_reasons': unproven,
        'target_row_before': _safe_row_state(before_state),
        'target_row_after': _safe_row_state(after_state),
        'expected_target_state_digest': expected_digest,
        'observed_target_state_digest': realized_digest,
        'target_reached_canonical_value': bool(
            expected_digest and realized_digest
            and expected_digest == realized_digest
        ),
        'target_unreviewed_fields_unchanged': bool(
            usable
            and before_state.get('target_unreviewed_digest')
            == after_state.get('target_unreviewed_digest')
        ),
        'other_rows_unchanged': bool(
            usable
            and before_state.get('other_rows_digest')
            == after_state.get('other_rows_digest')
        ),
        'other_rows_digest_before': before_state.get('other_rows_digest'),
        'other_rows_digest_after': after_state.get('other_rows_digest'),
        'target_row_digest_before': before_state.get('target_row_digest'),
        'target_row_digest_after': after_state.get('target_row_digest'),
    }


def _safe_row_state(state) -> dict:
    """Reportable view of one canonical row readback.

    Governed field NAMES, integer statistics, counts and digests only. The
    reviewed statistic is a governed baseball integer and is safe to record; no
    payload, path, credential, or exception text can reach here.
    """
    state = state or {}
    return {
        'available': bool(state.get('available')),
        'identity_resolved': state.get('identity_resolved'),
        'game_row_count': state.get('game_row_count'),
        'target_row_count': state.get('target_row_count'),
        'other_row_count': state.get('other_row_count'),
        'reviewed_field': state.get('reviewed_field'),
        'reviewed_field_value': state.get('reviewed_field_value'),
        'target_row_digest': state.get('target_row_digest'),
        'target_unreviewed_digest': state.get('target_unreviewed_digest'),
    }
