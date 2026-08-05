"""Read-only source-revision audit for MLB game 824487 (manual, exact scope).

Two retained scheduled daily runs recorded two DIFFERENT source revisions for
one game while agreeing on everything else about it: 12 appearances both times,
all 12 classified unchanged both times, and an identical per-game
reconciliation-plan fingerprint both times. The later run's shadow activation
observer failed on ``source_revision_match`` even though the public daily sync
succeeded, snapshot 353 published and served, and the appearance ledger
reconciled completely.

What a source revision actually is
----------------------------------
It is NOT a hash of the raw MLB response. It is
``game_appearance_extraction.appearance_set_fingerprint`` — SHA-256 over the
deterministic normalized appearance matrix restricted to
``FINGERPRINT_FIELDS``. Two different digests therefore prove that one of the
following happened, and nothing finer:

  * the normalized fingerprint INPUT differed;
  * the fingerprint constructor or upstream normalization CODE differed;
  * a retained artifact is internally inconsistent;
  * the computation was nondeterministic or defective.

A SHA-256 digest is not invertible and carries no field structure. This module
therefore never maps a digest to a guessed field, and every historical value it
cannot positively source is reported with an explicit evidence status rather
than as a null that reads like a baseball value.

What this module does NOT do
----------------------------
It performs no write of any kind, reruns neither historical sync, repairs
nothing, advances no checkpoint, updates no source revision, publishes nothing,
and authorizes nothing. Identifying a cause — or proving that the evidence to
identify one was never retained — is information.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from services import game_appearance_extraction as extraction
from services import game_log_reconciliation as reconciliation
# The read-only enforcement contract, the bounded refused write probe, and its
# evidence validator are the merged audit packages' generic mechanisms. They are
# imported, not reimplemented, so one contract governs every read-only audit.
from services.noop_qualification_candidate_audit import (  # noqa: F401
    EXPECTED_PROBE_EVIDENCE,
    PROBE_EVIDENCE_FIELDS,
    ReadOnlyNotEnforced,
    ReadOnlyProbeViolation,
    enforce_read_only,
    evaluate_probe_evidence,
    probe_evidence,
)


SCHEMA_VERSION = '1'
AUDIT_TYPE = 'game_source_revision_audit'

# ── Locked incident identity ────────────────────────────────────────────────
# Exactly one game and exactly two retained scheduled daily runs. Everything
# below is an EXPECTATION the audit verifies against retained evidence, never a
# fact it may copy into a result.

GAME_PK = 824487
REPRESENTED_DATE = date(2026, 7, 29)
EXPECTED_APPEARANCE_COUNT = 12
EXPECTED_UNCHANGED_COUNT = 12
EXPECTED_PLAN_FINGERPRINT = (
    '8cb7eacbc0e0a6da908ea759c836e585a2e690a99280cd8f274275fc7d1709ec'
)

RUN_PRIOR = 'prior_clean_run'
RUN_LATER = 'failed_observer_run'
RUN_KEYS = (RUN_PRIOR, RUN_LATER)

PRIOR_RUN_ID = '30902544622'
LATER_RUN_ID = '30999087370'

PRIOR_SOURCE_REVISION = (
    '90213dc8e42a9622e9c0dcaea80adb04507a4a5bfe054eaa9b98d2d138b804a0'
)
LATER_SOURCE_REVISION = (
    'a0fe2dbce8ad75ffc880e76996a6fec7bc90f86c296350898c009f97f241ecf4'
)

INCIDENT_CYCLE = 'daily'
INCIDENT_BRANCH = 'main'
INCIDENT_REF = 'refs/heads/main'

RUN_EXPECTATIONS = {
    RUN_PRIOR: {
        'workflow_run_id': PRIOR_RUN_ID,
        'head_sha': '59176cc7076b5d22a6542a491cc93e9710b9b267',
        'artifact_name': f'game-driven-shadow-{PRIOR_RUN_ID}',
        'artifact_id': 8889875247,
        'digest': (
            'sha256:2d5d9584eee09b7a2719efa4c33d0b0bbeea85ddc6b5fb74874db81f'
            'b4693199'
        ),
        'branch': INCIDENT_BRANCH,
        'cycle_kind': INCIDENT_CYCLE,
        'source_revision': PRIOR_SOURCE_REVISION,
        'activation_result': 'PASS',
        'source_revision_match': True,
        'safe_digest_match': True,
        'all_projected_targets_realized': True,
        'unresolved_rows': 0,
        'prohibited_identity_actions': 0,
        # Both runs' PUBLIC daily sync succeeded, so the runner the handoff
        # reports exited 0 in both. The activation observer's own verdict is a
        # separate fact and is validated separately as ``activation_result``.
        'runner_exit_code': 0,
        'handoff_status': 'ready',
        'required': True,
    },
    RUN_LATER: {
        'workflow_run_id': LATER_RUN_ID,
        'head_sha': 'a27631d9d954c65f6a9aae79d0e1df6774719305',
        'artifact_name': f'game-driven-shadow-{LATER_RUN_ID}',
        'artifact_id': 8927687851,
        'digest': (
            'sha256:adecc4bbe15b3f64ed60cccd46a0f370355018aae01079fa65d2cb5f'
            '8a8446de'
        ),
        'branch': INCIDENT_BRANCH,
        'cycle_kind': INCIDENT_CYCLE,
        'source_revision': LATER_SOURCE_REVISION,
        'activation_result': 'FAILED',
        'source_revision_match': False,
        'safe_digest_match': True,
        'all_projected_targets_realized': False,
        'unresolved_rows': 0,
        'prohibited_identity_actions': 0,
        'runner_exit_code': 0,
        'handoff_status': 'ready',
        'required': True,
    },
}

ARTIFACT_NAMES = {
    key: spec['artifact_name'] for key, spec in RUN_EXPECTATIONS.items()
}
HISTORICAL_SHAS = {
    key: spec['head_sha'] for key, spec in RUN_EXPECTATIONS.items()
}

CONFIRMATION = f'AUDIT_GAME_824487_SOURCE_REVISION_{LATER_RUN_ID}'

REQUIRED_REPOSITORY = 'NickolisK24/bullpen-intel-engine'
REQUIRED_REF = INCIDENT_REF
REQUIRED_EVENT_NAME = 'workflow_dispatch'
REQUIRED_ACTOR = 'NickolisK24'

# The later run's whole-lane accounting, as retained. Verified, never assumed.
LATER_LANE_EXPECTATIONS = {
    'games_planned': 94,
    'games_fetched': 94,
    'games_completed': 94,
    'games_failed': 0,
    'rows_expected': 778,
    'rows_unchanged': 778,
    'rows_inserted': 0,
    'rows_updated': 0,
    'rows_blocked': 0,
}

# The global dead-letter backlog is production state this audit never touches.
# It is recorded so a reader cannot mistake "this audit created none" for
# "there are none".
GOVERNED_DEAD_LETTER_BACKLOG = 1389
DEAD_LETTER_BACKLOG_NOTE = (
    'This audit creates zero dead letters. The governed global dead-letter '
    f'backlog remains {GOVERNED_DEAD_LETTER_BACKLOG} and is not changed, '
    'reduced, or drained by this package.'
)

NON_AUTHORIZATION_STATEMENT = (
    'This audit is read-only. It authorizes no mutation. It does not repair '
    'game 824487, does not backfill, does not update any source revision, '
    'does not reset or advance any checkpoint, does not create or modify a '
    'work item, does not publish or select a snapshot, does not change any '
    'ingestion mode or publication authority, does not weaken a validator, '
    'and does not run a migration. A recommendation in this document is not '
    'approval: any future repair requires a separate exact-scope package and '
    'separate explicit approval.'
)

STANDING_PRODUCTION_STATE = {
    'daily_game_driven_lane': 'shadow',
    'postgame_game_driven_lane': 'shadow',
    'backfill': 'off',
    'automated_writes': 'prohibited',
    'authoritative_publication_mode': 'prohibited',
    'publication_authority': 'existing_trusted_path',
}


# ── Result vocabulary ───────────────────────────────────────────────────────

RESULT_ROOT_CAUSE_IDENTIFIED = 'COMPLETE_ROOT_CAUSE_IDENTIFIED'
RESULT_FIELD_DELTA_UNAVAILABLE = (
    'COMPLETE_SCOPE_AND_MATERIALITY_IDENTIFIED_FIELD_DELTA_UNAVAILABLE'
)
RESULT_NO_CURRENT_DEFECT = 'COMPLETE_NO_CURRENT_DEFECT'
RESULT_FAILED = 'FAILED'
RESULT_UNPROVEN = 'UNPROVEN'

COMPLETE_RESULTS = frozenset({
    RESULT_ROOT_CAUSE_IDENTIFIED,
    RESULT_FIELD_DELTA_UNAVAILABLE,
    RESULT_NO_CURRENT_DEFECT,
})

EXIT_CODES = {
    RESULT_ROOT_CAUSE_IDENTIFIED: 0,
    RESULT_FIELD_DELTA_UNAVAILABLE: 0,
    RESULT_NO_CURRENT_DEFECT: 0,
    RESULT_FAILED: 1,
    RESULT_UNPROVEN: 2,
}

CONFIDENCE_HIGH = 'HIGH'
CONFIDENCE_MEDIUM = 'MEDIUM'
CONFIDENCE_LOW = 'LOW'


# ── FAILED reasons (this audit's own safety/integrity contract) ─────────────

FAILED_EVENT_NOT_WORKFLOW_DISPATCH = 'event_not_workflow_dispatch'
FAILED_REPOSITORY_NOT_AUTHORIZED = 'repository_not_authorized'
FAILED_ACTOR_NOT_AUTHORIZED = 'actor_not_authorized'
FAILED_REF_NOT_MAIN = 'ref_not_main'
FAILED_EXPECTED_SHA_MALFORMED = 'expected_main_sha_malformed'
FAILED_EXPECTED_SHA_MISMATCH = 'expected_main_sha_mismatch'
FAILED_CONFIRMATION_MISMATCH = 'confirmation_mismatch'

FAILED_ARTIFACT_IDENTITY_MISMATCH = 'artifact_identity_mismatch'
FAILED_ARTIFACT_DIGEST_MISMATCH = 'artifact_digest_mismatch'
FAILED_ARTIFACT_WRONG_GAME = 'artifact_does_not_contain_target_game'
FAILED_SCOPED_FINGERPRINT_CHANGED = 'scoped_fingerprint_changed'
FAILED_HIDDEN_SOURCE_CALL = 'unbudgeted_or_hidden_source_call'
FAILED_FINGERPRINT_NONDETERMINISTIC = 'fingerprint_nondeterministic'
FAILED_DIGEST_GUESSED_FROM_HASH = 'field_delta_guessed_from_digest'

# Acquisition that never happened is an evidence GAP: the audit observed
# nothing, so it is UNPROVEN. Release that was skipped, or that raised AFTER
# acquisition, is a breach of this audit's own safety contract — which is
# exactly what FAILED is reserved for.
FAILED_LOCK_RELEASE_FAILED = 'advisory_lock_release_failed'
FAILED_LOCK_RELEASE_NOT_ATTEMPTED = 'advisory_lock_release_not_attempted'

FAILED_REASONS = (
    FAILED_EVENT_NOT_WORKFLOW_DISPATCH,
    FAILED_LOCK_RELEASE_FAILED,
    FAILED_LOCK_RELEASE_NOT_ATTEMPTED,
    FAILED_REPOSITORY_NOT_AUTHORIZED,
    FAILED_ACTOR_NOT_AUTHORIZED,
    FAILED_REF_NOT_MAIN,
    FAILED_EXPECTED_SHA_MALFORMED,
    FAILED_EXPECTED_SHA_MISMATCH,
    FAILED_CONFIRMATION_MISMATCH,
    FAILED_ARTIFACT_IDENTITY_MISMATCH,
    FAILED_ARTIFACT_DIGEST_MISMATCH,
    FAILED_ARTIFACT_WRONG_GAME,
    FAILED_SCOPED_FINGERPRINT_CHANGED,
    FAILED_HIDDEN_SOURCE_CALL,
    FAILED_FINGERPRINT_NONDETERMINISTIC,
    FAILED_DIGEST_GUESSED_FROM_HASH,
)


# ── UNPROVEN reasons (required evidence unavailable) ────────────────────────

UNPROVEN_ARTIFACT_MISSING = 'required_artifact_missing'
UNPROVEN_ARTIFACT_FILE_MISSING = 'required_artifact_file_missing'
UNPROVEN_ADVISORY_LOCK_UNAVAILABLE = 'public_sync_advisory_lock_unavailable'
UNPROVEN_READ_ONLY_UNAVAILABLE = 'read_only_transaction_unavailable'
UNPROVEN_FINGERPRINT_UNAVAILABLE = 'scoped_fingerprint_uncomputable'
UNPROVEN_DATABASE_EVIDENCE_UNAVAILABLE = 'required_database_evidence_unavailable'
UNPROVEN_CURRENT_SOURCE_UNAVAILABLE = 'current_official_source_unavailable'
UNPROVEN_HISTORICAL_SHA_UNAVAILABLE = 'historical_sha_unavailable'
UNPROVEN_CODE_COMPARISON_INCOMPLETE = 'code_comparison_incomplete'
UNPROVEN_REQUIRED_SOURCE_CALL_REFUSED = 'required_source_call_refused'
UNPROVEN_EXECUTION_ERROR = 'audit_execution_error'
UNPROVEN_QUESTION_UNANSWERED = 'mandatory_question_unanswered'
UNPROVEN_ARTIFACT_IDENTITY_UNPROVEN = 'artifact_identity_unproven'
UNPROVEN_ARTIFACT_CONTENT_UNPROVEN = 'artifact_content_unproven'
UNPROVEN_ACTIVATION_EVIDENCE_MISSING = 'activation_realization_evidence_missing'
UNPROVEN_WORKFLOW_METADATA_UNAVAILABLE = 'workflow_run_metadata_unavailable'
UNPROVEN_LOCK_RELEASE_UNKNOWN = 'advisory_lock_release_unproven'
# A box score that returned HTTP 200 and parsed cleanly can still carry no
# usable pitching lines. The canonical lane treats that as an ingestion
# failure; the audit treats it as evidence it does not have.
UNPROVEN_CURRENT_SOURCE_EMPTY = 'current_official_appearance_set_empty'
UNPROVEN_CURRENT_SOURCE_INCOMPLETE = (
    'current_official_membership_incomplete'
)
UNPROVEN_REGISTRY_EXPECTATION_MISSING = 'mandatory_field_expectation_missing'

UNPROVEN_REASONS = (
    UNPROVEN_CURRENT_SOURCE_EMPTY,
    UNPROVEN_CURRENT_SOURCE_INCOMPLETE,
    UNPROVEN_REGISTRY_EXPECTATION_MISSING,
    # Declared here; defined with the retained-expectation model below, which
    # needs the observation helpers that appear after this block.
    'current_count_contradicts_retained_expectation',
    'retained_appearance_expectation_unavailable',
    'retained_appearance_counts_disagree',
    'duplicate_appearance_identity',
    UNPROVEN_ARTIFACT_MISSING,
    UNPROVEN_QUESTION_UNANSWERED,
    UNPROVEN_ARTIFACT_IDENTITY_UNPROVEN,
    UNPROVEN_ARTIFACT_CONTENT_UNPROVEN,
    UNPROVEN_ACTIVATION_EVIDENCE_MISSING,
    UNPROVEN_WORKFLOW_METADATA_UNAVAILABLE,
    UNPROVEN_LOCK_RELEASE_UNKNOWN,
    UNPROVEN_ARTIFACT_FILE_MISSING,
    UNPROVEN_ADVISORY_LOCK_UNAVAILABLE,
    UNPROVEN_READ_ONLY_UNAVAILABLE,
    UNPROVEN_FINGERPRINT_UNAVAILABLE,
    UNPROVEN_DATABASE_EVIDENCE_UNAVAILABLE,
    UNPROVEN_CURRENT_SOURCE_UNAVAILABLE,
    UNPROVEN_HISTORICAL_SHA_UNAVAILABLE,
    UNPROVEN_CODE_COMPARISON_INCOMPLETE,
    UNPROVEN_REQUIRED_SOURCE_CALL_REFUSED,
    UNPROVEN_EXECUTION_ERROR,
)


# ── Classification dimensions (never collapsed into one label) ──────────────

ROOT_OFFICIAL_SET_CHANGED = 'official_appearance_set_changed'
ROOT_CODE_PATH_CHANGED = 'source_revision_code_path_changed'
ROOT_FINGERPRINT_NONDETERMINISM = 'fingerprint_nondeterminism'
ROOT_ARTIFACT_CHECKPOINT_INCONSISTENCY = 'artifact_checkpoint_inconsistency'
ROOT_NO_CURRENT_MISMATCH = 'no_current_mismatch'
ROOT_UNPROVEN = 'unproven'

ROOT_CONDITIONS = (
    ROOT_OFFICIAL_SET_CHANGED,
    ROOT_CODE_PATH_CHANGED,
    ROOT_FINGERPRINT_NONDETERMINISM,
    ROOT_ARTIFACT_CHECKPOINT_INCONSISTENCY,
    ROOT_NO_CURRENT_MISMATCH,
    ROOT_UNPROVEN,
)

MATERIALITY_MATERIAL = 'material_to_canonical_writer_target'
MATERIALITY_NON_MATERIAL = 'non_material_to_canonical_writer_target'
MATERIALITY_EXACT_MATCH = 'current_target_exactly_matches_storage'
MATERIALITY_SOURCE_UNAVAILABLE = 'current_source_unavailable'
MATERIALITY_UNPROVEN = 'unproven'

CURRENT_MATERIALITIES = (
    MATERIALITY_MATERIAL,
    MATERIALITY_NON_MATERIAL,
    MATERIALITY_EXACT_MATCH,
    MATERIALITY_SOURCE_UNAVAILABLE,
    MATERIALITY_UNPROVEN,
)

PERSISTENCE_MATCHES_LATER = 'matches_later_revision'
PERSISTENCE_REVERTED = 'reverted_to_prior_revision'
PERSISTENCE_CHANGED_AGAIN = 'changed_again'
PERSISTENCE_UNAVAILABLE = 'unavailable'
PERSISTENCE_UNPROVEN = 'unproven'

PERSISTENCE_STATES = (
    PERSISTENCE_MATCHES_LATER,
    PERSISTENCE_REVERTED,
    PERSISTENCE_CHANGED_AGAIN,
    PERSISTENCE_UNAVAILABLE,
    PERSISTENCE_UNPROVEN,
)

FIELD_ID_IDENTIFIED = 'identified'
FIELD_ID_NARROWED = 'narrowed'
FIELD_ID_NOT_RETAINED = 'not_retained'
FIELD_ID_UNPROVEN = 'unproven'

FIELD_IDENTIFICATIONS = (
    FIELD_ID_IDENTIFIED,
    FIELD_ID_NARROWED,
    FIELD_ID_NOT_RETAINED,
    FIELD_ID_UNPROVEN,
)

CHECKPOINT_CURRENT = 'checkpoint_current'
CHECKPOINT_STALE = 'checkpoint_stale_relative_to_current_source'
CHECKPOINT_MISSING = 'checkpoint_missing'
CHECKPOINT_INCONSISTENT = 'checkpoint_inconsistent'
CHECKPOINT_UNPROVEN = 'unproven'

CHECKPOINT_STATES = (
    CHECKPOINT_CURRENT,
    CHECKPOINT_STALE,
    CHECKPOINT_MISSING,
    CHECKPOINT_INCONSISTENT,
    CHECKPOINT_UNPROVEN,
)

# Question 9 answers.
DELTA_IDENTIFIED = 'identified_from_positive_retained_evidence'
DELTA_NARROWED = 'narrowed_but_not_identified'
DELTA_NOT_RECOVERABLE = (
    'not_recoverable_prior_normalized_values_not_retained'
)
DELTA_UNPROVEN = 'unproven'

DELTA_ANSWERS = (
    DELTA_IDENTIFIED, DELTA_NARROWED, DELTA_NOT_RECOVERABLE, DELTA_UNPROVEN,
)

# Question 4 answers.
CURRENT_MATCHES_PRIOR = 'matches_prior_revision'
CURRENT_MATCHES_LATER = 'matches_later_revision'
CURRENT_MATCHES_NEITHER = 'matches_neither_revision'
CURRENT_SOURCE_UNAVAILABLE = 'current_source_unavailable'
CURRENT_UNPROVEN = 'unproven'

CURRENT_REVISION_STATES = (
    CURRENT_MATCHES_PRIOR,
    CURRENT_MATCHES_LATER,
    CURRENT_MATCHES_NEITHER,
    CURRENT_SOURCE_UNAVAILABLE,
    CURRENT_UNPROVEN,
)

# Question 10 answers.
CAUSALITY_SINGLE_CHAIN = 'single_source_revision_mismatch_caused_both'
CAUSALITY_INDEPENDENT_UNRESOLVED = 'independent_unresolved_row_deficit'
CAUSALITY_INDEPENDENT_IDENTITY = 'independent_prohibited_identity_deficit'
CAUSALITY_UNPROVEN_CODE_DRIFT = 'unproven_due_to_code_drift'
CAUSALITY_UNPROVEN = 'unproven'

CAUSALITY_ANSWERS = (
    CAUSALITY_SINGLE_CHAIN,
    CAUSALITY_INDEPENDENT_UNRESOLVED,
    CAUSALITY_INDEPENDENT_IDENTITY,
    CAUSALITY_UNPROVEN_CODE_DRIFT,
    CAUSALITY_UNPROVEN,
)

# Question 12 vocabulary. Informational only; never an authorization.
CONSEQUENCE_GAMELOG_REPAIR = 'canonical_gamelog_repair'
CONSEQUENCE_EXACT_GAME_BACKFILL = 'exact_game_backfill'
CONSEQUENCE_WORK_ITEM_REVISION_UPDATE = 'work_item_source_revision_update'
CONSEQUENCE_CHECKPOINT_RESET = 'checkpoint_reset'
CONSEQUENCE_VALIDATOR_REPAIR = 'validator_repair'
CONSEQUENCE_ARTIFACT_RETENTION_IMPROVEMENT = 'artifact_retention_improvement'
CONSEQUENCE_NOOP_QUALIFICATION_DELAY = 'no_op_qualification_delay'
CONSEQUENCE_NOOP_CANDIDATE_AUDIT_DELAY = 'no_op_candidate_audit_delay'
CONSEQUENCE_CONTINUED_OBSERVATION = 'continued_scheduled_observation_only'
# A membership discrepancy the one bounded source call could not resolve is
# not "nothing to do" and it is not an approved repair either. It is a bounded
# read-only evidence limitation that a human has to look at.
CONSEQUENCE_SOURCE_COMPLETENESS_REVIEW = (
    'current_source_completeness_review_required'
)
# A population-size contradiction and a duplicated identity are distinct
# read-only review requests, and neither is "nothing to do".
CONSEQUENCE_COUNT_CONSISTENCY_REVIEW = (
    'current_source_count_consistency_review_required'
)
CONSEQUENCE_IDENTITY_REVIEW = 'appearance_identity_review_required'
CONSEQUENCE_NO_ACTION = 'no_action'

CONSEQUENCES = (
    CONSEQUENCE_SOURCE_COMPLETENESS_REVIEW,
    CONSEQUENCE_COUNT_CONSISTENCY_REVIEW,
    CONSEQUENCE_IDENTITY_REVIEW,
    CONSEQUENCE_GAMELOG_REPAIR,
    CONSEQUENCE_EXACT_GAME_BACKFILL,
    CONSEQUENCE_WORK_ITEM_REVISION_UPDATE,
    CONSEQUENCE_CHECKPOINT_RESET,
    CONSEQUENCE_VALIDATOR_REPAIR,
    CONSEQUENCE_ARTIFACT_RETENTION_IMPROVEMENT,
    CONSEQUENCE_NOOP_QUALIFICATION_DELAY,
    CONSEQUENCE_NOOP_CANDIDATE_AUDIT_DELAY,
    CONSEQUENCE_CONTINUED_OBSERVATION,
    CONSEQUENCE_NO_ACTION,
)


# ── Question answer states ──────────────────────────────────────────────────
# A question is not a boolean. "The database said there is no provenance" and
# "the database was never opened" are both a negative-sounding answer and are
# completely different facts, and only one of them is an answer.

ANSWER_OBSERVED_YES = 'observed_yes'
ANSWER_OBSERVED_NO = 'observed_no'
ANSWER_OBSERVED_INSUFFICIENT = 'observed_but_insufficient'
ANSWER_NOT_OBSERVED = 'not_observed'
ANSWER_UNAVAILABLE = 'unavailable'
ANSWER_UNPROVEN = 'unproven'

ANSWER_STATES = (
    ANSWER_OBSERVED_YES,
    ANSWER_OBSERVED_NO,
    ANSWER_OBSERVED_INSUFFICIENT,
    ANSWER_NOT_OBSERVED,
    ANSWER_UNAVAILABLE,
    ANSWER_UNPROVEN,
)

# States that count as an ANSWER. The rest are accounts of an absence.
ANSWERED_STATES = frozenset({
    ANSWER_OBSERVED_YES, ANSWER_OBSERVED_NO, ANSWER_OBSERVED_INSUFFICIENT,
})

# Questions whose unanswered state must close the exit-zero path.
#
# Q5 is mandatory: this audit's entire subject is a fingerprint discrepancy,
# so a conclusion that the current target is fine cannot rest on a fingerprint
# nobody proved was deterministic. Q3 stays outside the set because an
# incomplete code comparison already forces ROOT_UNPROVEN structurally, which
# reaches the same verdict through classify() rather than through this gate.
MANDATORY_QUESTIONS = (
    'Q1', 'Q2', 'Q4', 'Q5', 'Q6', 'Q7', 'Q10', 'Q11', 'Q12',
)


# ── Historical evidence status vocabulary ───────────────────────────────────
# A missing historical value is NOT a null baseball value. Every historical
# cell in the field matrix carries one of these, always.

EVIDENCE_PROVEN = 'proven'
EVIDENCE_ABSENT = 'absent'
EVIDENCE_NOT_RETAINED = 'not_retained'
EVIDENCE_INCONSISTENT = 'inconsistent'
EVIDENCE_UNPROVEN = 'unproven'

EVIDENCE_STATUSES = (
    EVIDENCE_PROVEN,
    EVIDENCE_ABSENT,
    EVIDENCE_NOT_RETAINED,
    EVIDENCE_INCONSISTENT,
    EVIDENCE_UNPROVEN,
)

EVIDENCE_SOURCE_NONE = 'none'
EVIDENCE_SOURCE_RUN_ARTIFACT = 'retained_run_artifact'
EVIDENCE_SOURCE_CORRECTION_PROVENANCE = 'durable_correction_provenance'
EVIDENCE_SOURCE_COMPLETION_PROOF = 'work_item_completion_proof'
EVIDENCE_SOURCE_CURRENT_DATABASE = 'current_database'
EVIDENCE_SOURCE_OFFICIAL = 'current_official_source'

EVIDENCE_SOURCES = (
    EVIDENCE_SOURCE_NONE,
    EVIDENCE_SOURCE_RUN_ARTIFACT,
    EVIDENCE_SOURCE_CORRECTION_PROVENANCE,
    EVIDENCE_SOURCE_COMPLETION_PROOF,
    EVIDENCE_SOURCE_CURRENT_DATABASE,
    EVIDENCE_SOURCE_OFFICIAL,
)

# What would have been required to recover an exact historical field delta.
REQUIRED_MISSING_EVIDENCE = (
    'per-appearance normalized FINGERPRINT_FIELDS values retained by the '
    'prior run',
    'per-appearance normalized FINGERPRINT_FIELDS values retained by the '
    'later run',
    'a durable correction-provenance record naming the changed field, its '
    'previous value, and its new value for this exact game and pitcher',
)


# ── Observation model ───────────────────────────────────────────────────────
# Every fact this audit uses is either POSITIVELY OBSERVED from a named source
# at a named path, or it is not a fact. A locked expectation may only VALIDATE
# an observed value; it may never supply one. The states below exist so that
# "the artifact says null", "the artifact has no such field", "the containing
# object is missing", and "the containing object is not a mapping" can never
# collapse into a single ``None`` that later reads as agreement.

OBS_VERIFIED = 'verified'            # observed AND equal to the expectation
OBS_OBSERVED = 'observed'            # observed; no expectation to compare
OBS_MISMATCH = 'mismatch'            # observed AND different — a definite fact
OBS_ABSENT = 'absent'                # container present, field not in it
OBS_CONTAINER_ABSENT = 'container_absent'
OBS_CONTAINER_MALFORMED = 'container_malformed'
OBS_MALFORMED = 'malformed'          # present but the wrong type
OBS_SOURCE_UNAVAILABLE = 'source_unavailable'

OBSERVATION_STATES = (
    OBS_VERIFIED, OBS_OBSERVED, OBS_MISMATCH, OBS_ABSENT,
    OBS_CONTAINER_ABSENT, OBS_CONTAINER_MALFORMED, OBS_MALFORMED,
    OBS_SOURCE_UNAVAILABLE,
)

# States that mean "we hold a real value". Everything else is a gap.
POSITIVE_STATES = frozenset({OBS_VERIFIED, OBS_OBSERVED})
# States that mean "the evidence definitely contradicts the expectation".
CONTRADICTING_STATES = frozenset({OBS_MISMATCH})
# States that mean "the evidence was not obtained". Never a contradiction.
GAP_STATES = frozenset({
    OBS_ABSENT, OBS_CONTAINER_ABSENT, OBS_CONTAINER_MALFORMED, OBS_MALFORMED,
    OBS_SOURCE_UNAVAILABLE,
})

# Where a fact came from. ``inferred`` exists only so that the audit can assert
# it never appears in a verified observation.
SOURCE_RETAINED_ARTIFACT = 'retained_artifact_file'
SOURCE_WORKFLOW_METADATA = 'github_workflow_run_metadata'
SOURCE_ARTIFACT_METADATA = 'github_artifact_metadata'
SOURCE_INFERRED = 'inferred_or_expected'

OBSERVATION_SOURCES = (
    SOURCE_RETAINED_ARTIFACT,
    SOURCE_WORKFLOW_METADATA,
    SOURCE_ARTIFACT_METADATA,
    SOURCE_INFERRED,
)

_MISSING = object()


def read_path(document, path):
    """Walk a dotted path, distinguishing every way a lookup can fail.

    Returns ``(value, state)``. A retained ``null`` comes back as
    ``(None, OBS_OBSERVED)``; an absent key comes back as
    ``(None, OBS_ABSENT)``. Those must never be the same answer.
    """
    if document is None:
        return None, OBS_CONTAINER_ABSENT
    if not isinstance(document, dict):
        return None, OBS_CONTAINER_MALFORMED

    node = document
    parts = str(path).split('.')
    for index, part in enumerate(parts):
        if not isinstance(node, dict):
            return None, OBS_CONTAINER_MALFORMED
        if part not in node:
            # The last segment missing is an absent FIELD; an earlier segment
            # missing is an absent CONTAINER. Different facts, different fixes.
            return None, (
                OBS_ABSENT if index == len(parts) - 1
                else OBS_CONTAINER_ABSENT
            )
        node = node[part]
    return node, OBS_OBSERVED


def observation(
    *,
    field,
    path,
    source,
    observed=_MISSING,
    state=None,
    expected=_MISSING,
    expected_type=None,
    comparator=None,
) -> dict:
    """One positively-sourced fact, or an explicit account of its absence.

    ``expected`` is a VALIDATOR. When the value was not observed, the returned
    observation keeps ``observed`` as ``None`` with a gap state — the
    expectation is never copied into the observed slot.
    """
    has_value = observed is not _MISSING
    value = None if not has_value else observed
    resolved = state or (OBS_OBSERVED if has_value else OBS_ABSENT)

    if resolved in POSITIVE_STATES and expected_type is not None:
        if not isinstance(value, expected_type) or isinstance(value, bool) != (
            expected_type is bool
        ):
            resolved = OBS_MALFORMED
            value = None

    reason = None
    if resolved in POSITIVE_STATES and expected is not _MISSING:
        equal = (
            comparator(value, expected) if comparator is not None
            else value == expected
        )
        resolved = OBS_VERIFIED if equal else OBS_MISMATCH
        if resolved == OBS_MISMATCH:
            reason = 'observed_value_differs_from_expectation'
    elif resolved in GAP_STATES:
        reason = resolved

    return {
        'field': field,
        'evidence_path': path,
        'source': source,
        'observed': _jsonable(value) if resolved in POSITIVE_STATES
        or resolved == OBS_MISMATCH else None,
        'observed_present': resolved in POSITIVE_STATES
        or resolved == OBS_MISMATCH,
        'expected': None if expected is _MISSING else _jsonable(expected),
        'state': resolved,
        'reason': reason,
    }


def observe(document, spec, *, source, expected=_MISSING) -> dict:
    """Read one registry-specified field out of a retained document."""
    value, state = read_path(document, spec['path'])
    if state is not OBS_OBSERVED:
        return observation(
            field=spec['field'], path=spec['path'], source=source,
            state=state, expected=expected,
        )
    return observation(
        field=spec['field'], path=spec['path'], source=source,
        observed=value, expected=expected,
        expected_type=spec.get('expected_type'),
    )


def observation_gaps(observations) -> list[str]:
    return sorted(
        entry['field'] for entry in observations or ()
        if entry['state'] in GAP_STATES
    )


def observation_mismatches(observations) -> list[str]:
    return sorted(
        entry['field'] for entry in observations or ()
        if entry['state'] in CONTRADICTING_STATES
    )


def observation_verified(observations) -> list[str]:
    """Fields positively observed AND matched. Never merely 'not refuted'."""
    return sorted(
        entry['field'] for entry in observations or ()
        if entry['state'] == OBS_VERIFIED
    )


def observation_value(observations, field, default=None):
    for entry in observations or ():
        if entry['field'] == field and entry['state'] in (
            POSITIVE_STATES | CONTRADICTING_STATES
        ):
            return entry['observed']
    return default


def observation_state(observations, field) -> str | None:
    for entry in observations or ():
        if entry['field'] == field:
            return entry['state']
    return None


# ── Artifact contract ───────────────────────────────────────────────────────

SYNC_SUMMARY_SUFFIX = '-sync-summary.json'
ACTIVATION_SUMMARY_SUFFIX = '-activation-summary.json'
HANDOFF_METADATA_FILENAME = 'handoff-metadata.json'

REQUIRED_ARTIFACT_FILES = (
    SYNC_SUMMARY_SUFFIX,
    ACTIVATION_SUMMARY_SUFFIX,
    HANDOFF_METADATA_FILENAME,
)

_SHA256_HEX = re.compile(r'\A(sha256:)?[0-9a-f]{64}\Z')
_SHA1_HEX = re.compile(r'\A[0-9a-f]{40}\Z')


# ── Mandatory observed-field registry ───────────────────────────────────────
# ONE place that says which facts this audit requires, where each comes from,
# what shape it must have, which conclusion it gates, and what its absence
# means. Scattering these requirements through the orchestration is how a
# missing field becomes an implied match.
#
# ``doc`` names the retained document (or metadata source) the field is read
# from; ``path`` is the exact dotted evidence path inside it; ``expects`` is
# the key in RUN_EXPECTATIONS holding the validator, or a literal.
#
# ``gates`` is the set of conclusions the field is mandatory for:
#   identity — is this the exact artifact this audit is scoped to?
#   content  — does it say what the incident record says about the game?
#   q10      — is it enough to answer the activation-causality question?
# ``absence`` is the outcome when the field is NOT observed. Absence is always
# UNPROVEN: a fact we failed to obtain is not a fact that contradicts us.

DOC_HANDOFF = 'handoff_metadata'
DOC_ACTIVATION = 'activation_summary'
DOC_SYNC = 'sync_summary'
DOC_WORKFLOW_METADATA = 'workflow_run_metadata'
DOC_ARTIFACT_METADATA = 'artifact_metadata'

DOC_SOURCES = {
    DOC_HANDOFF: SOURCE_RETAINED_ARTIFACT,
    DOC_ACTIVATION: SOURCE_RETAINED_ARTIFACT,
    DOC_SYNC: SOURCE_RETAINED_ARTIFACT,
    DOC_WORKFLOW_METADATA: SOURCE_WORKFLOW_METADATA,
    DOC_ARTIFACT_METADATA: SOURCE_ARTIFACT_METADATA,
}

GATE_IDENTITY = 'identity'
GATE_CONTENT = 'content'
GATE_Q10 = 'q10'

ABSENCE_UNPROVEN = 'unproven'


def _field(field, doc, path, *, expects=None, literal=_MISSING,
           expected_type=None, gates=(), later_only=False):
    return {
        'field': field,
        'doc': doc,
        'path': path,
        'expects': expects,
        'literal': literal,
        'expected_type': expected_type,
        'gates': frozenset(gates),
        'later_only': later_only,
        'absence': ABSENCE_UNPROVEN,
    }


MANDATORY_FIELDS = (
    # ── Identity: is this the exact artifact this audit is scoped to? ───────
    _field('workflow_run_id', DOC_HANDOFF, 'run_id',
           expects='workflow_run_id', expected_type=str,
           gates=(GATE_IDENTITY,)),
    _field('head_sha', DOC_HANDOFF, 'repository_sha',
           expects='head_sha', expected_type=str, gates=(GATE_IDENTITY,)),
    _field('handoff_cycle_kind', DOC_HANDOFF, 'cycle_kind',
           expects='cycle_kind', expected_type=str, gates=(GATE_IDENTITY,)),
    _field('handoff_status', DOC_HANDOFF, 'handoff_status',
           expects='handoff_status', expected_type=str,
           gates=(GATE_IDENTITY,)),
    _field('cycle_kind', DOC_ACTIVATION, 'cycle_kind',
           expects='cycle_kind', expected_type=str, gates=(GATE_IDENTITY,)),
    # The runner exit code is compared EXACTLY. "Not null" is not a value.
    _field('runner_exit_code', DOC_ACTIVATION, 'runner_exit_code',
           expects='runner_exit_code', expected_type=int,
           gates=(GATE_IDENTITY,)),
    # Branch lives in NEITHER retained document. The handoff metadata schema
    # carries run id, head SHA, cycle, runner exit code, and three booleans —
    # no branch and no ref. It is therefore read from GitHub workflow-run
    # metadata or it is not read at all.
    _field('branch', DOC_WORKFLOW_METADATA, 'head_branch',
           expects='branch', expected_type=str, gates=(GATE_IDENTITY,)),
    _field('workflow_metadata_head_sha', DOC_WORKFLOW_METADATA, 'head_sha',
           expects='head_sha', expected_type=str, gates=(GATE_IDENTITY,)),

    # ── Content: does it say what the incident record says? ─────────────────
    _field('activation_result', DOC_ACTIVATION, 'result',
           expects='activation_result', expected_type=str,
           gates=(GATE_CONTENT,)),
    _field('configured_mode', DOC_ACTIVATION, 'configured_mode',
           literal='shadow', expected_type=str, gates=(GATE_CONTENT,)),
    _field('writes_enabled', DOC_ACTIVATION, 'execution_effects.writes_enabled',
           literal=False, expected_type=bool, gates=(GATE_CONTENT,)),
    _field('publication_authoritative', DOC_ACTIVATION,
           'execution_effects.publication_authoritative',
           literal=False, expected_type=bool, gates=(GATE_CONTENT,)),

    # ── Activation realization: the ONLY source for Question 10 ─────────────
    _field('source_revision_match', DOC_ACTIVATION,
           'realization.source_revision_match', expects='source_revision_match',
           expected_type=bool, gates=(GATE_CONTENT, GATE_Q10)),
    _field('safe_digest_match', DOC_ACTIVATION,
           'realization.safe_digest_match', expects='safe_digest_match',
           expected_type=bool, gates=(GATE_CONTENT, GATE_Q10)),
    _field('all_projected_targets_realized', DOC_ACTIVATION,
           'realization.all_projected_targets_realized',
           expects='all_projected_targets_realized', expected_type=bool,
           gates=(GATE_CONTENT, GATE_Q10)),
    _field('unresolved_rows', DOC_ACTIVATION, 'realization.unresolved_rows',
           expects='unresolved_rows', expected_type=int,
           gates=(GATE_CONTENT, GATE_Q10)),
    _field('prohibited_identity_actions', DOC_ACTIVATION,
           'realization.prohibited_identity_actions',
           expects='prohibited_identity_actions', expected_type=int,
           gates=(GATE_CONTENT, GATE_Q10)),

    # ── Later-run lane accounting: compared exactly, never merely reported ──
    _field('games_planned', DOC_ACTIVATION, 'games_planned',
           literal=LATER_LANE_EXPECTATIONS['games_planned'],
           expected_type=int, gates=(GATE_CONTENT,), later_only=True),
    _field('games_fetched', DOC_ACTIVATION, 'games_fetched',
           literal=LATER_LANE_EXPECTATIONS['games_fetched'],
           expected_type=int, gates=(GATE_CONTENT,), later_only=True),
    _field('games_completed', DOC_ACTIVATION, 'games_completed',
           literal=LATER_LANE_EXPECTATIONS['games_completed'],
           expected_type=int, gates=(GATE_CONTENT,), later_only=True),
    _field('games_failed', DOC_ACTIVATION, 'games_failed',
           literal=LATER_LANE_EXPECTATIONS['games_failed'],
           expected_type=int, gates=(GATE_CONTENT,), later_only=True),
    _field('rows_expected', DOC_ACTIVATION, 'projected.rows_expected',
           literal=LATER_LANE_EXPECTATIONS['rows_expected'],
           expected_type=int, gates=(GATE_CONTENT,), later_only=True),
    _field('rows_unchanged', DOC_ACTIVATION, 'projected.rows_unchanged',
           literal=LATER_LANE_EXPECTATIONS['rows_unchanged'],
           expected_type=int, gates=(GATE_CONTENT,), later_only=True),
    _field('rows_inserted', DOC_ACTIVATION, 'projected.rows_inserted',
           literal=LATER_LANE_EXPECTATIONS['rows_inserted'],
           expected_type=int, gates=(GATE_CONTENT,), later_only=True),
    _field('rows_updated', DOC_ACTIVATION, 'projected.rows_updated',
           literal=LATER_LANE_EXPECTATIONS['rows_updated'],
           expected_type=int, gates=(GATE_CONTENT,), later_only=True),
    _field('rows_blocked', DOC_ACTIVATION, 'projected.rows_blocked',
           literal=LATER_LANE_EXPECTATIONS['rows_blocked'],
           expected_type=int, gates=(GATE_CONTENT,), later_only=True),
)

Q10_FIELDS = tuple(
    spec['field'] for spec in MANDATORY_FIELDS if GATE_Q10 in spec['gates']
)
IDENTITY_FIELDS = tuple(
    spec['field'] for spec in MANDATORY_FIELDS
    if GATE_IDENTITY in spec['gates']
)


def registry_expectation_defects() -> list[dict]:
    """Registry rows whose validator cannot be resolved for a run.

    A mandatory field is only mandatory if something actually validates it. A
    row that names an ``expects`` key no ``RUN_EXPECTATIONS`` entry carries
    would be observed and never compared — which the hardened state reducer
    now refuses to call verified, but which should never reach production in
    the first place. The package contract tests assert this list is empty.
    """
    defects = []
    for run_key, spec in RUN_EXPECTATIONS.items():
        for entry in mandatory_fields_for(run_key):
            if entry['literal'] is not _MISSING:
                continue
            if entry['expects'] is None or entry['expects'] not in spec:
                defects.append({
                    'run_key': run_key,
                    'field': entry['field'],
                    'expects': entry['expects'],
                    'reason': UNPROVEN_REGISTRY_EXPECTATION_MISSING,
                })
    return defects


def mandatory_fields_for(run_key) -> tuple:
    """The registry rows that apply to one run."""
    return tuple(
        spec for spec in MANDATORY_FIELDS
        if not spec['later_only'] or run_key == RUN_LATER
    )


def mandatory_field_registry() -> list[dict]:
    """The registry, rendered for the evidence artifact."""
    return [
        {
            'field': spec['field'],
            'document': spec['doc'],
            'source': DOC_SOURCES[spec['doc']],
            'evidence_path': spec['path'],
            'expected_type': getattr(
                spec['expected_type'], '__name__', None
            ),
            'gates': sorted(spec['gates']),
            'later_run_only': spec['later_only'],
            'absence_outcome': spec['absence'],
        }
        for spec in MANDATORY_FIELDS
    ]


class AuditInputError(ValueError):
    """A bounded input could not be accepted. Carries a safe reason only."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class SourceCallRefused(RuntimeError):
    """The source-call budget refused a call before it reached the wire."""

    def __init__(self, kind):
        super().__init__(f'source_call_refused:{kind}')
        self.kind = kind


def incident_identity() -> dict:
    """The locked scope this audit investigates."""
    return {
        'audit_type': AUDIT_TYPE,
        'schema_version': SCHEMA_VERSION,
        'game_pk': GAME_PK,
        'represented_game_date': REPRESENTED_DATE.isoformat(),
        'expected_appearance_count': EXPECTED_APPEARANCE_COUNT,
        'expected_unchanged_count': EXPECTED_UNCHANGED_COUNT,
        'expected_plan_fingerprint': EXPECTED_PLAN_FINGERPRINT,
        'prior_run': dict(RUN_EXPECTATIONS[RUN_PRIOR]),
        'later_run': dict(RUN_EXPECTATIONS[RUN_LATER]),
        'confirmation': CONFIRMATION,
    }


def source_revision_semantics() -> dict:
    """What a source revision is, stated in the artifact rather than assumed."""
    return {
        'constructor': (
            'services.game_appearance_extraction.appearance_set_fingerprint'
        ),
        'algorithm': 'sha256',
        'input': 'deterministic normalized appearance matrix',
        'is_raw_payload_hash': False,
        'fingerprint_fields': list(extraction.FINGERPRINT_FIELDS),
        'fingerprint_field_count': len(extraction.FINGERPRINT_FIELDS),
        'digest_is_invertible': False,
        'two_digests_prove': [
            'normalized fingerprint input differed',
            'fingerprint constructor or upstream normalization code differed',
            'a retained artifact is inconsistent',
            'the computation was nondeterministic or defective',
        ],
        'two_digests_do_not_prove': (
            'which governed field changed; SHA-256 carries no field structure '
            'and is not invertible'
        ),
    }


def normalize_digest(raw) -> str | None:
    """Normalize an artifact digest to bare lowercase hex, or None."""
    text = str(raw or '').strip().lower()
    if not text or not _SHA256_HEX.match(text):
        return None
    return text.split(':', 1)[-1]


def normalize_sha(raw) -> str | None:
    text = str(raw or '').strip().lower()
    return text if _SHA1_HEX.match(text) else None


def verify_artifact_digest(run_key, observed_digest) -> dict:
    """Verify an observed artifact digest against the recorded expectation.

    A digest GitHub no longer exposes is UNVERIFIED and is reported as such —
    it is honest, and it is not a failure. A digest that IS exposed and differs
    is a definite violation: the evidence is not the evidence this audit is
    scoped to.
    """
    expected = normalize_digest(
        (RUN_EXPECTATIONS.get(run_key) or {}).get('digest')
    )
    observed = normalize_digest(observed_digest)
    if expected is None:
        return {
            'digest_expected': None, 'digest_observed': observed,
            'digest_verified': False, 'digest_mismatch': False,
            'digest_status': 'no_expected_digest_recorded',
        }
    if observed is None:
        return {
            'digest_expected': expected, 'digest_observed': None,
            'digest_verified': False, 'digest_mismatch': False,
            'digest_status': 'not_exposed_by_github',
        }
    match = observed == expected
    return {
        'digest_expected': expected,
        'digest_observed': observed,
        'digest_verified': match,
        'digest_mismatch': not match,
        'digest_status': 'verified' if match else 'mismatch',
    }


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8')), None
    except (OSError, ValueError):
        # Never surface the underlying message: it can carry a filesystem path.
        return None, 'artifact_file_unparseable'


def read_run_artifact(directory) -> dict:
    """Read one retained ``game-driven-shadow-<run id>`` artifact directory."""
    directory = Path(directory)
    result = {
        'files': [],
        'sync_summary_filename': None,
        'sync_summary': None,
        'activation_summary_filename': None,
        'activation_summary': None,
        'handoff_metadata': None,
        'missing_files': [],
        'parse_error': None,
    }
    try:
        children = sorted(
            child for child in directory.iterdir() if child.is_file()
        )
    except OSError:
        result['parse_error'] = 'artifact_directory_unreadable'
        result['missing_files'] = list(REQUIRED_ARTIFACT_FILES)
        return result

    result['files'] = [child.name for child in children]

    sync_files = [
        child for child in children
        if child.name.endswith(SYNC_SUMMARY_SUFFIX)
    ]
    activation_files = [
        child for child in children
        if child.name.endswith(ACTIVATION_SUMMARY_SUFFIX)
    ]
    handoff_files = [
        child for child in children if child.name == HANDOFF_METADATA_FILENAME
    ]

    for label, matches, key in (
        (SYNC_SUMMARY_SUFFIX, sync_files, 'sync_summary'),
        (ACTIVATION_SUMMARY_SUFFIX, activation_files, 'activation_summary'),
        (HANDOFF_METADATA_FILENAME, handoff_files, 'handoff_metadata'),
    ):
        if not matches:
            result['missing_files'].append(label)
            continue
        payload, error = _read_json(matches[0])
        if error:
            result['parse_error'] = error
            continue
        result[key] = payload
        if key != 'handoff_metadata':
            result[f'{key}_filename'] = matches[0].name
    return result


def lane_report(sync_summary) -> dict:
    """The game-driven lane report inside a retained daily sync summary."""
    summary = sync_summary if isinstance(sync_summary, dict) else {}
    sync = summary.get('sync') if isinstance(summary.get('sync'), dict) else {}
    lane = sync.get('game_driven_ingestion')
    return lane if isinstance(lane, dict) else {}


def lane_games(sync_summary) -> list:
    """Per-game entries, from the lane report or the legacy sibling key."""
    summary = sync_summary if isinstance(sync_summary, dict) else {}
    sync = summary.get('sync') if isinstance(summary.get('sync'), dict) else {}
    lane = lane_report(summary)
    games = lane.get('games')
    if not isinstance(games, list):
        games = sync.get('game_driven_games')
    return [entry for entry in (games or ()) if isinstance(entry, dict)]


def game_entry(sync_summary, game_pk=GAME_PK) -> dict | None:
    for entry in lane_games(sync_summary):
        if entry.get('game_pk') == game_pk:
            return entry
    return None


def scan_row_level_evidence(document, game_pk=GAME_PK) -> dict:
    """Does this retained document carry NORMALIZED per-appearance VALUES?

    Walked generically rather than by known key path: the question is whether
    the artifact retains any structure that pairs a pitcher identity with an
    actual value for a governed fingerprint field. Field NAMES, counts, and
    digests are not values, and finding them is not finding evidence.

    Absence is a material evidence finding in its own right, so it is reported
    positively rather than inferred from a failed lookup.
    """
    fingerprint_fields = set(extraction.FINGERPRINT_FIELDS)
    value_fields: set = set()
    row_like = 0
    inspected = 0

    def walk(node):
        nonlocal row_like, inspected
        inspected += 1
        if inspected > 200000:
            return
        if isinstance(node, dict):
            has_pitcher = any(
                key in node for key in ('pitcher_mlb_id', 'pitcher_id')
            )
            scoped = node.get('game_pk') in (None, game_pk)
            if has_pitcher and scoped:
                row_like += 1
                for field in fingerprint_fields:
                    if field in node and node[field] is not None:
                        value_fields.add(field)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(document)
    retained = bool(value_fields - {'pitcher_mlb_id'})
    return {
        'row_like_entries_for_game': row_like,
        'normalized_value_fields_found': sorted(value_fields),
        'row_level_normalized_values_retained': retained,
        'evidence_status': (
            EVIDENCE_PROVEN if retained else EVIDENCE_NOT_RETAINED
        ),
        'note': (
            'The retained per-game entry carries aggregate counts, the '
            'observed source revision, and the per-game plan fingerprint. '
            'Row detail is retained only for rows whose projected action is '
            'not "unchanged", so a game whose 12 appearances were all '
            'unchanged retains no per-appearance values at all.'
        ),
    }


# ── Historical value extraction ─────────────────────────────────────────────
# A historical value is usable ONLY when the retained document positively
# associates it with all four coordinates at once: exact run, exact game,
# exact pitcher, exact governed field. Anything short of that is not a
# historical value — it is a shape that resembles one.
#
# Repository inspection of the producer settles what these two artifacts
# actually retain. ``services/sync.py`` writes the per-game entry with
# aggregate counts, the observed source revision, and the plan fingerprint
# only; it writes ``projected_differences`` rows solely for rows whose action
# is NOT ``unchanged``, and those rows carry field NAMES and digests, never
# values. Both runs classified all 12 appearances ``unchanged``, so neither
# artifact retains a single per-appearance governed value. The extractor below
# is still real: it runs, it requires full association, and for these two
# artifacts it correctly returns nothing.

HISTORICAL_PROVEN = 'proven'
HISTORICAL_PROVEN_NULL = 'proven_null'
HISTORICAL_ABSENT = 'absent'
HISTORICAL_NOT_RETAINED = 'not_retained'
HISTORICAL_UNPROVEN = 'unproven'
HISTORICAL_INCONSISTENT = 'inconsistent'
HISTORICAL_IDENTITY_MISSING = 'identity_missing'
HISTORICAL_WRONG_GAME = 'wrong_game'

HISTORICAL_STATES = (
    HISTORICAL_PROVEN, HISTORICAL_PROVEN_NULL, HISTORICAL_ABSENT,
    HISTORICAL_NOT_RETAINED, HISTORICAL_UNPROVEN, HISTORICAL_INCONSISTENT,
    HISTORICAL_IDENTITY_MISSING, HISTORICAL_WRONG_GAME,
)


def extract_historical_values(run_key, sync_summary, *, activation=None)\
        -> dict:
    """Exact per-appearance governed values retained by ONE run, if any.

    Association is required, never inferred. A candidate row must carry the
    target game id AND a usable pitcher id AND a governed field key whose value
    is actually present. Ordering, display names, roster membership, and
    co-occurrence prove nothing and are not consulted.
    """
    fingerprint_fields = set(extraction.FINGERPRINT_FIELDS)
    values: list[dict] = []
    ambiguous: list[dict] = []
    inspected = 0

    def walk(node, path):
        nonlocal inspected
        inspected += 1
        if inspected > 200000:
            return
        if isinstance(node, dict):
            game = node.get('game_pk', _MISSING)
            pitcher = node.get('pitcher_mlb_id', _MISSING)
            carried = sorted(
                field for field in fingerprint_fields
                if field in node and field != 'pitcher_mlb_id'
            )
            if carried:
                if game is _MISSING or game != GAME_PK:
                    ambiguous.append({
                        'evidence_path': path,
                        'fields': carried,
                        'status': (
                            HISTORICAL_WRONG_GAME if game is not _MISSING
                            else HISTORICAL_UNPROVEN
                        ),
                        'reason': (
                            'row_not_associated_with_target_game'
                            if game is not _MISSING
                            else 'row_carries_no_game_identity'
                        ),
                    })
                elif pitcher is _MISSING or not isinstance(pitcher, int) or (
                    isinstance(pitcher, bool)
                ):
                    ambiguous.append({
                        'evidence_path': path,
                        'fields': carried,
                        'status': HISTORICAL_IDENTITY_MISSING,
                        'reason': 'row_carries_no_usable_pitcher_identity',
                    })
                else:
                    for field in carried:
                        values.append({
                            'run_key': run_key,
                            'run_id': RUN_EXPECTATIONS[run_key][
                                'workflow_run_id'
                            ],
                            'game_pk': GAME_PK,
                            'pitcher_mlb_id': pitcher,
                            'field_name': field,
                            'value': _jsonable(node[field]),
                            'status': (
                                HISTORICAL_PROVEN_NULL
                                if node[field] is None else HISTORICAL_PROVEN
                            ),
                            'evidence_source': SOURCE_RETAINED_ARTIFACT,
                            'evidence_path': f'{path}.{field}',
                        })
            for key, value in node.items():
                walk(value, f'{path}.{key}')
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f'{path}[{index}]')

    walk(sync_summary, DOC_SYNC)
    walk(activation, DOC_ACTIVATION)

    by_coordinate: dict = {}
    inconsistent: list[dict] = []
    for record in values:
        key = (record['pitcher_mlb_id'], record['field_name'])
        prior = by_coordinate.get(key)
        if prior is None:
            by_coordinate[key] = record
        elif prior['value'] != record['value']:
            # The same coordinate carrying two different values inside one
            # retained document is not a value — it is a contradiction.
            inconsistent.append({
                'pitcher_mlb_id': record['pitcher_mlb_id'],
                'field_name': record['field_name'],
                'status': HISTORICAL_INCONSISTENT,
                'evidence_paths': [
                    prior['evidence_path'], record['evidence_path'],
                ],
            })
            by_coordinate[key] = dict(
                prior, status=HISTORICAL_INCONSISTENT, value=None,
            )

    usable = {
        key: record for key, record in by_coordinate.items()
        if record['status'] in (HISTORICAL_PROVEN, HISTORICAL_PROVEN_NULL)
    }
    return {
        'run_key': run_key,
        'values': list(by_coordinate.values()),
        'value_count': len(usable),
        'associated_coordinates': sorted(
            f'{pitcher}:{field}' for pitcher, field in usable
        ),
        'unassociable_candidates': ambiguous,
        'inconsistent_coordinates': inconsistent,
        'exact_values_retained': bool(usable),
        # The honest headline for these two artifacts.
        'evidence_status': (
            HISTORICAL_PROVEN if usable
            else (HISTORICAL_UNPROVEN if ambiguous else HISTORICAL_NOT_RETAINED)
        ),
    }


def historical_value_for(extracted, pitcher_mlb_id, field_name) -> dict:
    """One coordinate's retained value, with its status. Never a bare None."""
    for record in (extracted or {}).get('values') or ():
        if (
            record['pitcher_mlb_id'] == pitcher_mlb_id
            and record['field_name'] == field_name
        ):
            return record
    candidates = (extracted or {}).get('unassociable_candidates') or []
    return {
        'run_key': (extracted or {}).get('run_key'),
        'game_pk': GAME_PK,
        'pitcher_mlb_id': pitcher_mlb_id,
        'field_name': field_name,
        'value': None,
        'status': (
            HISTORICAL_UNPROVEN if candidates else HISTORICAL_NOT_RETAINED
        ),
        'evidence_source': EVIDENCE_SOURCE_NONE,
        'evidence_path': None,
    }


def historical_delta(prior_extract, later_extract) -> dict:
    """A field delta, ONLY from two exact retained values for one coordinate."""
    prior_values = {
        (record['pitcher_mlb_id'], record['field_name']): record
        for record in (prior_extract or {}).get('values') or ()
        if record['status'] in (HISTORICAL_PROVEN, HISTORICAL_PROVEN_NULL)
    }
    later_values = {
        (record['pitcher_mlb_id'], record['field_name']): record
        for record in (later_extract or {}).get('values') or ()
        if record['status'] in (HISTORICAL_PROVEN, HISTORICAL_PROVEN_NULL)
    }
    shared = sorted(set(prior_values) & set(later_values))
    changed = [
        {
            'pitcher_mlb_id': key[0],
            'field_name': key[1],
            'prior_value': prior_values[key]['value'],
            'later_value': later_values[key]['value'],
            'prior_evidence_path': prior_values[key]['evidence_path'],
            'later_evidence_path': later_values[key]['evidence_path'],
        }
        for key in shared
        if comparable_value(prior_values[key]['value'])
        != comparable_value(later_values[key]['value'])
    ]
    return {
        'comparable_coordinates': len(shared),
        'changed_coordinates': changed,
        'identified_fields': sorted({item['field_name'] for item in changed}),
        # Identification requires BOTH sides for the SAME coordinate. One side
        # alone bounds nothing.
        'delta_identified': bool(changed),
        'prior_value_count': len(prior_values),
        'later_value_count': len(later_values),
    }


def _match(observed, expected) -> str:
    if observed is None or observed == '':
        return 'not_observed'
    return 'match' if str(observed).strip().lower() == str(
        expected
    ).strip().lower() else 'mismatch'


STATE_VERIFIED = 'verified'
STATE_UNPROVEN = 'unproven'
STATE_FAILED = 'failed'
STATE_UNVERIFIED = 'unverified'

ARTIFACT_STATES = (
    STATE_VERIFIED, STATE_UNPROVEN, STATE_FAILED, STATE_UNVERIFIED,
)


def _reduce_state(observations) -> str:
    """A definite contradiction is FAILED; anything short of proof is UNPROVEN.

    Ordered deliberately. A run that is both missing a mandatory field AND
    contradicted by another must read as contradicted — the contradiction is
    the more serious and more actionable fact, and the gap is still reported
    alongside it.

    VERIFIED is a positive claim and is earned, never defaulted into. It
    requires at least one observation and requires EVERY observation to have
    been compared against something and matched. A gate that observed nothing
    observed nothing; a value that was read but never compared was never
    verified. Neither is agreement, and neither may reduce to VERIFIED — which
    is also why ``verified_fields`` can never be empty while the state reads
    verified.
    """
    observations = list(observations or ())
    if observation_mismatches(observations):
        return STATE_FAILED
    if observation_gaps(observations):
        return STATE_UNPROVEN
    if not observations:
        return STATE_UNPROVEN
    if len(observation_verified(observations)) != len(observations):
        return STATE_UNPROVEN
    return STATE_VERIFIED


def verify_run_artifact(run_key, parsed, *, observed_metadata=None,
                        workflow_metadata=None) -> dict:
    """Verify one run's retained artifact against its locked expectations.

    Every fact below is POSITIVELY OBSERVED from a named document at a named
    path, then compared. An expectation validates; it never supplies. Identity,
    digest, and content are three separate verdicts because they answer three
    separate questions and can legitimately disagree.
    """
    spec = RUN_EXPECTATIONS[run_key]
    parsed = parsed or {}
    metadata = observed_metadata if isinstance(observed_metadata, dict) else {}
    run_metadata = (
        workflow_metadata if isinstance(workflow_metadata, dict) else {}
    ).get(spec['workflow_run_id'])

    documents = {
        DOC_HANDOFF: parsed.get('handoff_metadata'),
        DOC_ACTIVATION: parsed.get('activation_summary'),
        DOC_SYNC: parsed.get('sync_summary'),
        DOC_WORKFLOW_METADATA: run_metadata,
        DOC_ARTIFACT_METADATA: metadata.get(spec['artifact_name']),
    }

    observations = []
    for entry_spec in mandatory_fields_for(run_key):
        expected = (
            entry_spec['literal'] if entry_spec['literal'] is not _MISSING
            else spec.get(entry_spec['expects'], _MISSING)
        )
        observations.append(observe(
            documents[entry_spec['doc']], entry_spec,
            source=DOC_SOURCES[entry_spec['doc']], expected=expected,
        ))

    # ── The target game's own retained evidence ─────────────────────────────
    sync_summary = parsed.get('sync_summary')
    entry = game_entry(sync_summary)
    game_present = entry is not None
    game_observations = []
    for field, path_suffix, expected, kind in (
        ('source_revision', 'source_revision', spec['source_revision'], str),
        ('reconciliation_plan_fingerprint', 'reconciliation_plan_fingerprint',
         EXPECTED_PLAN_FINGERPRINT, str),
        ('appearances_extracted', 'appearances_extracted',
         EXPECTED_APPEARANCE_COUNT, int),
        ('unchanged', 'unchanged', EXPECTED_UNCHANGED_COUNT, int),
        ('inserted', 'inserted', 0, int),
        ('updated', 'updated', 0, int),
        ('blocked', 'blocked', 0, int),
    ):
        path = (
            f'sync.game_driven_ingestion.games[game_pk={GAME_PK}]'
            f'.{path_suffix}'
        )
        if not game_present:
            game_observations.append(observation(
                field=field, path=path, source=SOURCE_RETAINED_ARTIFACT,
                state=OBS_CONTAINER_ABSENT, expected=expected,
            ))
            continue
        game_observations.append(observe(
            entry, {'field': field, 'path': path_suffix,
                    'expected_type': kind},
            source=SOURCE_RETAINED_ARTIFACT, expected=expected,
        ) | {'evidence_path': path})

    membership = observation(
        field='game_membership',
        path=f'sync.game_driven_ingestion.games[].game_pk == {GAME_PK}',
        source=SOURCE_RETAINED_ARTIFACT,
        observed=GAME_PK if game_present else _MISSING,
        state=None if game_present else OBS_ABSENT,
        expected=GAME_PK,
    )
    observations.append(membership)
    observations.extend(game_observations)

    # ── Digest, from GitHub artifact metadata only ──────────────────────────
    digest = verify_artifact_digest(
        run_key, (metadata.get(spec['artifact_name']) or {}).get('digest'),
    )
    if digest['digest_mismatch']:
        digest_state = STATE_FAILED
    elif digest['digest_verified']:
        digest_state = STATE_VERIFIED
    else:
        digest_state = STATE_UNVERIFIED

    identity_observations = [
        item for item in observations
        if item['field'] in _gate_fields(run_key, GATE_IDENTITY)
    ]
    content_observations = [
        item for item in observations
        if item['field'] in _gate_fields(run_key, GATE_CONTENT)
        or item['field'] in _CONTENT_GAME_FIELDS
    ]
    q10_observations = [
        item for item in observations
        if item['field'] in _gate_fields(run_key, GATE_Q10)
    ]

    files_present = bool(parsed.get('files'))
    missing_files = list(parsed.get('missing_files') or ())
    parse_error = parsed.get('parse_error')

    identity_state = _reduce_state(identity_observations)
    content_state = _reduce_state(content_observations)
    if not files_present or missing_files or parse_error:
        # Required evidence never reached the audit. That is a gap, and it
        # must not be reported as agreement on anything the files would carry.
        identity_state = (
            STATE_FAILED if identity_state == STATE_FAILED else STATE_UNPROVEN
        )
        content_state = (
            STATE_FAILED if content_state == STATE_FAILED else STATE_UNPROVEN
        )

    observed_artifact_id = (
        metadata.get(spec['artifact_name']) or {}
    ).get('artifact_id')
    if observed_artifact_id is None:
        artifact_id_status = 'not_exposed_by_github'
    else:
        try:
            artifact_id_status = (
                'match' if int(observed_artifact_id) == spec['artifact_id']
                else 'mismatch'
            )
        except (TypeError, ValueError):
            artifact_id_status = 'malformed'
    if artifact_id_status in ('mismatch', 'malformed'):
        identity_state = STATE_FAILED

    return {
        'run_key': run_key,
        'artifact_name': spec['artifact_name'],
        'expected_artifact_id': spec['artifact_id'],
        'observed_artifact_id': observed_artifact_id,
        'artifact_id_status': artifact_id_status,
        'expected_workflow_run_id': spec['workflow_run_id'],
        'expected_head_sha': spec['head_sha'],
        'present': files_present,
        'missing_files': missing_files,
        'parse_error': parse_error,
        'workflow_metadata_available': isinstance(run_metadata, dict),
        'observations': observations,
        # Verified means POSITIVELY OBSERVED AND MATCHED. A field that was
        # never observed can never appear here.
        'verified_fields': observation_verified(observations),
        'mismatched_fields': observation_mismatches(observations),
        'unobserved_fields': observation_gaps(observations),
        'identity_state': identity_state,
        'identity_verified': identity_state == STATE_VERIFIED,
        'identity_unproven': identity_state == STATE_UNPROVEN,
        'identity_failed': identity_state == STATE_FAILED,
        'content_state': content_state,
        'content_verified': content_state == STATE_VERIFIED,
        'content_unproven': content_state == STATE_UNPROVEN,
        'content_failed': content_state == STATE_FAILED,
        'digest_state': digest_state,
        'q10_observations': q10_observations,
        'q10_state': _reduce_state(q10_observations),
        'observed_source_revision': observation_value(
            observations, 'source_revision',
        ),
        'observed_plan_fingerprint': observation_value(
            observations, 'reconciliation_plan_fingerprint',
        ),
        'observed_appearances_extracted': observation_value(
            observations, 'appearances_extracted',
        ),
        'observed_unchanged': observation_value(observations, 'unchanged'),
        'observed_inserted': observation_value(observations, 'inserted'),
        'observed_updated': observation_value(observations, 'updated'),
        'observed_blocked': observation_value(observations, 'blocked'),
        'lane_accounting': {
            field: observation_value(observations, field)
            for field in LATER_LANE_EXPECTATIONS
        },
        'lane_accounting_state': _reduce_state([
            item for item in observations
            if item['field'] in LATER_LANE_EXPECTATIONS
        ]) if run_key == RUN_LATER else STATE_UNVERIFIED,
        'row_level_evidence': scan_row_level_evidence(sync_summary),
        'historical_values': extract_historical_values(
            run_key, sync_summary, activation=parsed.get('activation_summary'),
        ),
        **digest,
    }


_CONTENT_GAME_FIELDS = frozenset({
    'game_membership', 'source_revision', 'reconciliation_plan_fingerprint',
    'appearances_extracted', 'unchanged', 'inserted', 'updated', 'blocked',
})


def _gate_fields(run_key, gate) -> frozenset:
    return frozenset(
        spec['field'] for spec in mandatory_fields_for(run_key)
        if gate in spec['gates']
    )


def _absent_run_entry(run_key, spec) -> dict:
    """An artifact that never arrived. Nothing about it is verified."""
    return {
        'run_key': run_key,
        'artifact_name': spec['artifact_name'],
        'expected_artifact_id': spec['artifact_id'],
        'observed_artifact_id': None,
        'artifact_id_status': 'not_exposed_by_github',
        'expected_workflow_run_id': spec['workflow_run_id'],
        'expected_head_sha': spec['head_sha'],
        'present': False,
        'missing_files': list(REQUIRED_ARTIFACT_FILES),
        'parse_error': None,
        'workflow_metadata_available': False,
        'observations': [],
        'verified_fields': [],
        'mismatched_fields': [],
        'unobserved_fields': sorted(
            spec_entry['field'] for spec_entry in mandatory_fields_for(run_key)
        ),
        'identity_state': STATE_UNPROVEN,
        'identity_verified': False,
        'identity_unproven': True,
        'identity_failed': False,
        'content_state': STATE_UNPROVEN,
        'content_verified': False,
        'content_unproven': True,
        'content_failed': False,
        'digest_state': STATE_UNVERIFIED,
        'q10_observations': [],
        'q10_state': STATE_UNPROVEN,
        'observed_source_revision': None,
        'observed_plan_fingerprint': None,
        'observed_appearances_extracted': None,
        'observed_unchanged': None,
        'observed_inserted': None,
        'observed_updated': None,
        'observed_blocked': None,
        'lane_accounting': {field: None for field in LATER_LANE_EXPECTATIONS},
        'lane_accounting_state': STATE_UNPROVEN,
        'row_level_evidence': scan_row_level_evidence(None),
        'historical_values': extract_historical_values(run_key, None),
        **verify_artifact_digest(run_key, None),
    }


def ingest_run_artifacts(root, *, observed_metadata=None,
                         workflow_metadata=None) -> dict:
    """Discover and verify BOTH retained run artifacts under ``root``."""
    base = Path(root)
    runs: dict[str, dict] = {}
    for run_key, spec in RUN_EXPECTATIONS.items():
        directory = base / spec['artifact_name']
        if not directory.is_dir():
            runs[run_key] = _absent_run_entry(run_key, spec)
            continue
        parsed = read_run_artifact(directory)
        entry = verify_run_artifact(
            run_key, parsed, observed_metadata=observed_metadata,
            workflow_metadata=workflow_metadata,
        )
        entry['present'] = True
        entry['files'] = parsed['files']
        runs[run_key] = entry

    missing = sorted(
        key for key, entry in runs.items() if not entry.get('present')
    )
    missing_files = sorted(
        key for key, entry in runs.items() if entry.get('missing_files')
    )
    identity_failures = sorted(
        key for key, entry in runs.items() if entry.get('identity_failed')
    )
    identity_unproven = sorted(
        key for key, entry in runs.items() if entry.get('identity_unproven')
    )
    content_failures = sorted(
        key for key, entry in runs.items() if entry.get('content_failed')
    )
    content_unproven = sorted(
        key for key, entry in runs.items() if entry.get('content_unproven')
    )
    digest_mismatches = sorted(
        key for key, entry in runs.items() if entry.get('digest_mismatch')
    )
    wrong_game = sorted(
        key for key, entry in runs.items()
        if observation_state(
            entry.get('observations'), 'game_membership',
        ) in CONTRADICTING_STATES | {OBS_ABSENT, OBS_CONTAINER_ABSENT}
        and entry.get('present')
    )

    identity_all_verified = all(
        entry.get('identity_verified') for entry in runs.values()
    )
    content_all_verified = all(
        entry.get('content_verified') for entry in runs.values()
    )
    delta = historical_delta(
        (runs.get(RUN_PRIOR) or {}).get('historical_values'),
        (runs.get(RUN_LATER) or {}).get('historical_values'),
    )
    return {
        'runs': runs,
        'missing_artifacts': missing,
        'artifacts_missing_required_files': missing_files,
        'identity_failures': identity_failures,
        'identity_unproven': identity_unproven,
        'content_failures': content_failures,
        'content_unproven': content_unproven,
        # Retained for the reducer's existing FAILED vocabulary.
        'identity_mismatches': identity_failures,
        'digest_mismatches': digest_mismatches,
        'wrong_game': wrong_game,
        'all_required_present': not missing and not missing_files,
        'identity_all_verified': identity_all_verified,
        'content_all_verified': content_all_verified,
        # Q1 and Q2 answer from VERIFIED evidence, never from file presence.
        'revision_change_proven': bool(
            identity_all_verified
            and content_all_verified
            and runs.get(RUN_PRIOR, {}).get('observed_source_revision')
            == PRIOR_SOURCE_REVISION
            and runs.get(RUN_LATER, {}).get('observed_source_revision')
            == LATER_SOURCE_REVISION
        ),
        'plan_fingerprint_stable': bool(
            identity_all_verified
            and content_all_verified
            and runs.get(RUN_PRIOR, {}).get('observed_plan_fingerprint')
            == EXPECTED_PLAN_FINGERPRINT
            and runs.get(RUN_LATER, {}).get('observed_plan_fingerprint')
            == EXPECTED_PLAN_FINGERPRINT
        ),
        'historical_delta': delta,
        'exact_historical_values_retained': bool(
            delta['prior_value_count'] or delta['later_value_count']
        ),
        'unassociable_historical_candidates': sum(
            len((entry.get('historical_values') or {}).get(
                'unassociable_candidates'
            ) or ())
            for entry in runs.values()
        ),
        'prior_row_level_values_retained': bool(
            (runs.get(RUN_PRIOR, {}).get('historical_values') or {}).get(
                'exact_values_retained'
            )
        ),
        'later_row_level_values_retained': bool(
            (runs.get(RUN_LATER, {}).get('historical_values') or {}).get(
                'exact_values_retained'
            )
        ),
    }


# ── Advisory-lock lifecycle ─────────────────────────────────────────────────
# The lock is a synchronization guarantee, not a formality. A run that took it
# and cannot prove it gave it back has not proven its own safety contract, and
# an audit that cannot prove its own safety contract cannot exit zero.

LOCK_NOT_ATTEMPTED = 'not_attempted'
LOCK_NOT_ACQUIRED = 'not_acquired'
LOCK_RELEASED = 'released'
LOCK_RELEASE_FAILED = 'release_failed'
LOCK_RELEASE_NOT_ATTEMPTED = 'release_not_attempted'
LOCK_RELEASE_UNKNOWN = 'release_unknown'

LOCK_STATES = (
    LOCK_NOT_ATTEMPTED, LOCK_NOT_ACQUIRED, LOCK_RELEASED,
    LOCK_RELEASE_FAILED, LOCK_RELEASE_NOT_ATTEMPTED, LOCK_RELEASE_UNKNOWN,
)

def lock_lifecycle(state) -> dict:
    """Reduce the guard's lifecycle to one status plus its verdict reasons."""
    state = state or {}
    attempted = bool(state.get('acquire_attempted'))
    acquired = bool(state.get('guard_acquired'))
    release_required = acquired
    release_attempted = bool(state.get('guard_release_attempted'))
    released = state.get('guard_released')

    failed: list[str] = []
    unproven: list[str] = []

    if not attempted:
        status = LOCK_NOT_ATTEMPTED
        unproven.append(UNPROVEN_ADVISORY_LOCK_UNAVAILABLE)
    elif not acquired:
        status = LOCK_NOT_ACQUIRED
        unproven.append(UNPROVEN_ADVISORY_LOCK_UNAVAILABLE)
    elif not release_attempted:
        status = LOCK_RELEASE_NOT_ATTEMPTED
        failed.append(FAILED_LOCK_RELEASE_NOT_ATTEMPTED)
    elif released is True:
        status = LOCK_RELEASED
    elif released is False:
        status = LOCK_RELEASE_FAILED
        failed.append(FAILED_LOCK_RELEASE_FAILED)
    else:
        # Attempted, but the outcome was never positively established. The
        # process ending is not proof that the lock came back.
        status = LOCK_RELEASE_UNKNOWN
        unproven.append(UNPROVEN_LOCK_RELEASE_UNKNOWN)

    return {
        'acquire_attempted': attempted,
        'guard_acquired': acquired,
        'acquisition_reason': state.get('acquisition_reason'),
        'release_required': release_required,
        'guard_release_attempted': release_attempted,
        'guard_released': released,
        'release_reason': state.get('release_reason'),
        'rollback_attempted': bool(state.get('rollback_attempted')),
        'rollback_succeeded': state.get('rollback_succeeded'),
        'status': status,
        'release_proven': status == LOCK_RELEASED,
        'failed_reasons': failed,
        'unproven_reasons': unproven,
        'note': (
            'A completed result requires the guard to have been acquired AND '
            'positively released. Process or context termination is not '
            'release evidence.'
        ),
    }


# ── Source-call budget ──────────────────────────────────────────────────────
# The canonical extraction path was inspected rather than guessed: the lane
# synthesizes its game payload from the durable schedule ledger and makes
# exactly ONE upstream request per game — the box score. The optional
# exact-game schedule call buys corroboration that the stored schedule row this
# audit reads is still what the official source says; it is not needed to
# compute a source revision, so refusing it is not an evidence gap.

CALL_KIND_BOXSCORE = 'boxscore'
CALL_KIND_EXACT_GAME = 'exact_game'
CALL_KINDS = (CALL_KIND_BOXSCORE, CALL_KIND_EXACT_GAME)

SOURCE_CALL_BUDGET = {
    CALL_KIND_BOXSCORE: 1,
    CALL_KIND_EXACT_GAME: 1,
}
SOURCE_CALL_TOTAL_BUDGET = 2


class SourceCallBudget:
    """Bounded accounting for upstream MLB calls.

    Every call is reserved BEFORE it is issued, so an exhausted budget refuses
    rather than overspending. Spending an allowance exactly is a correct run;
    only a REQUIRED call that is refused or fails makes a conclusion unproven.
    """

    def __init__(self, *, per_kind=None, total=None):
        self._limits = dict(per_kind or SOURCE_CALL_BUDGET)
        self._total_limit = int(
            SOURCE_CALL_TOTAL_BUDGET if total is None else total
        )
        self._attempted = {kind: 0 for kind in CALL_KINDS}
        self._succeeded = {kind: 0 for kind in CALL_KINDS}
        self._failed = {kind: 0 for kind in CALL_KINDS}
        self._refused = {kind: 0 for kind in CALL_KINDS}
        self._refused_required = {kind: 0 for kind in CALL_KINDS}
        self._latency_ms = 0.0

    @property
    def total_attempted(self) -> int:
        return sum(self._attempted.values())

    def remaining(self, kind) -> int:
        per_kind = max(
            self._limits.get(kind, 0) - self._attempted.get(kind, 0), 0
        )
        overall = max(self._total_limit - self.total_attempted, 0)
        return min(per_kind, overall)

    def reserve(self, kind, *, required=True) -> bool:
        if kind not in CALL_KINDS:
            raise AuditInputError('unknown_source_call_kind')
        if self.remaining(kind) <= 0:
            self._refused[kind] += 1
            if required:
                self._refused_required[kind] += 1
            return False
        self._attempted[kind] += 1
        return True

    def record_success(self, kind, *, latency_ms=0.0) -> None:
        if kind in CALL_KINDS:
            self._succeeded[kind] += 1
            self._latency_ms += max(float(latency_ms or 0.0), 0.0)

    def record_failure(self, kind, *, latency_ms=0.0) -> None:
        if kind in CALL_KINDS:
            self._failed[kind] += 1
            self._latency_ms += max(float(latency_ms or 0.0), 0.0)

    def state(self) -> dict:
        return {
            'limits': dict(self._limits),
            'total_limit': self._total_limit,
            'endpoint_classes': list(CALL_KINDS),
            'calls_attempted': dict(self._attempted),
            'calls_succeeded': dict(self._succeeded),
            'calls_failed': dict(self._failed),
            'calls_refused_by_budget': dict(self._refused),
            'total_attempted': self.total_attempted,
            'total_succeeded': sum(self._succeeded.values()),
            'total_failed': sum(self._failed.values()),
            'total_refused_by_budget': sum(self._refused.values()),
            'total_source_latency_ms': round(self._latency_ms, 2),
            'budget_remaining': {
                kind: self.remaining(kind) for kind in CALL_KINDS
            },
            'total_budget_remaining': max(
                self._total_limit - self.total_attempted, 0
            ),
            # Informational: an allowance spent exactly and successfully is a
            # correct run, not a defective one.
            'allowance_fully_spent': self.total_attempted
            >= self._total_limit,
            'calls_refused_required': dict(self._refused_required),
            'required_call_refused': sum(self._refused_required.values()) > 0,
        }


class CountedMLBClient:
    """The ONLY thing in this package that may reach the MLB client.

    It wraps the canonical client rather than replacing it: there is no second
    MLB client, no second box-score parser, and no second appearance schema.
    Every delegated method reserves budget first, so a call the budget refuses
    never reaches the wire — including one attempted from deep inside the
    canonical reconciliation path. The counters here and the counters in the
    artifact are the same numbers by construction.
    """

    def __init__(self, client, budget):
        self._client = client
        self._budget = budget
        self.calls: list[dict] = []
        self.refusals: list[dict] = []
        self.errors: list[dict] = []
        self.unexpected_methods: list[str] = []

    # ── Governed, budgeted endpoints ────────────────────────────────────────

    def get_game_boxscore(self, game_pk):
        return self._call(
            CALL_KIND_BOXSCORE, f'boxscore:{game_pk}',
            lambda: self._client.get_game_boxscore(game_pk),
            required=True,
        )

    def get_schedule(self, start_date=None, end_date=None, team_id=None):
        return self._call(
            CALL_KIND_EXACT_GAME, f'exact_game:{start_date}',
            lambda: self._client.get_schedule(
                start_date=start_date, end_date=end_date, team_id=team_id,
            ),
            required=False,
        )

    @property
    def metrics(self):
        """Pass-through for the client's own metrics object.

        Reading a counter issues no request, so it is exposed rather than
        refused — refusing it would make the guard itself the reason a
        canonical caller failed.
        """
        return getattr(self._client, 'metrics', None)

    # ── Everything else is refused, loudly ──────────────────────────────────

    def __getattr__(self, name):
        # Reached only for attributes this guard does not define. A canonical
        # path that reaches for another endpoint is a call this audit did not
        # budget, and silently proxying it would make the reported count a lie.
        def _refuse(*_args, **_kwargs):
            self.unexpected_methods.append(name)
            raise SourceCallRefused(name)

        return _refuse

    def _call(self, kind, label, invoke, *, required):
        from time import perf_counter

        if not self._budget.reserve(kind, required=required):
            self.refusals.append(
                {'kind': kind, 'label': label, 'required': required}
            )
            raise SourceCallRefused(kind)
        started = perf_counter()
        try:
            result = invoke()
        except Exception:  # noqa: BLE001 - never leak the upstream message
            elapsed = (perf_counter() - started) * 1000
            self._budget.record_failure(kind, latency_ms=elapsed)
            self.errors.append(
                {'kind': kind, 'label': label, 'required': required}
            )
            self.calls.append({
                'kind': kind, 'label': label, 'outcome': 'failure',
                'latency_ms': round(elapsed, 2), 'required': required,
            })
            raise
        elapsed = (perf_counter() - started) * 1000
        self._budget.record_success(kind, latency_ms=elapsed)
        self.calls.append({
            'kind': kind, 'label': label, 'outcome': 'success',
            'latency_ms': round(elapsed, 2), 'required': required,
        })
        return result

    def state(self) -> dict:
        counted = {kind: 0 for kind in CALL_KINDS}
        for call in self.calls:
            counted[call['kind']] = counted.get(call['kind'], 0) + 1
        budget = self._budget.state()
        return {
            'calls': list(self.calls),
            'calls_by_kind': counted,
            'total_calls_issued': len(self.calls),
            'refusals': list(self.refusals),
            'errors': list(self.errors),
            'unexpected_methods_refused': sorted(set(self.unexpected_methods)),
            # The proof that reported == actual: the guard counted every call
            # it let through, and the budget counted every reservation.
            'reported_equals_actual': (
                counted == budget['calls_attempted']
                and len(self.calls) == budget['total_attempted']
            ),
            'duplicate_boxscore_requests': max(
                counted.get(CALL_KIND_BOXSCORE, 0) - 1, 0
            ),
            'hidden_call_detected': bool(self.unexpected_methods),
            'required_call_failed': any(
                entry.get('required') for entry in self.errors
            ),
            'budget': budget,
        }


# ── Scoped read-only fingerprints ───────────────────────────────────────────
# Scoped rather than whole-table: the blast radius of this audit is exactly one
# game and the identities attached to it. Every digest covers FULL governed row
# content and timestamps, not row counts, so a same-count edit is still caught.

SCOPE_EXACT_GAME = 'exact_game_824487'
SCOPE_PITCHER_IDENTITY = 'official_pitcher_identities'

FINGERPRINT_SCOPE_NAMES = (SCOPE_EXACT_GAME, SCOPE_PITCHER_IDENTITY)

EXACT_GAME_TABLES = (
    'scheduled_games',
    'game_logs',
    'game_ingestion_work_items',
    'postgame_processed_games',
    'team_game_pitching_splits',
    'completed_game_contexts',
    'game_play_by_play_events',
    'sync_failures',
)

# Correction provenance is COLUMNAR in this schema rather than a table of its
# own: it lives on game_logs (stat_correction_count, last_stat_correction_at,
# last_stat_correction_source, last_stat_correction_sync_run_id) and on
# game_ingestion_work_items.correction_count. Appearance-team authority is
# likewise columnar on game_logs (appearance_team_id / _source / _status /
# _reason). Full-row digests of those tables therefore already cover both;
# there is no separate history table to fingerprint.
CORRECTION_PROVENANCE_CARRIERS = (
    'game_logs',
    'game_ingestion_work_items',
    'team_game_pitching_splits',
)
APPEARANCE_TEAM_CARRIERS = ('game_logs',)


def fingerprint_scope_plan(pitcher_mlb_ids=()) -> dict:
    """The exact scope definition, stated in the artifact rather than implied."""
    identities = sorted({int(value) for value in pitcher_mlb_ids or ()})
    return {
        SCOPE_EXACT_GAME: {
            'description': f'every governed row keyed to game {GAME_PK}',
            'tables': list(EXACT_GAME_TABLES),
            'correction_provenance_carriers': list(
                CORRECTION_PROVENANCE_CARRIERS
            ),
            'appearance_team_carriers': list(APPEARANCE_TEAM_CARRIERS),
        },
        SCOPE_PITCHER_IDENTITY: {
            'description': (
                'local Pitcher identity rows for the official pitchers in '
                f'game {GAME_PK}'
            ),
            'tables': ['pitchers'],
            'pitcher_count': len(identities),
        },
    }


def scoped_fingerprints(session, *, pitcher_mlb_ids=()) -> dict | None:
    """Full-content digests for every scope this audit can touch.

    Returns ``None`` when the digests cannot be computed at all, which the
    reducer turns into UNPROVEN rather than into a silent pass.
    """
    from sqlalchemy import text as sql_text

    bind = session.get_bind()
    if getattr(bind.dialect, 'name', '') != 'postgresql':
        return None

    identities = sorted({int(value) for value in pitcher_mlb_ids or ()})
    scopes = {
        SCOPE_EXACT_GAME: [
            ('scheduled_games', 'game_pk = :game_pk', {'game_pk': GAME_PK}),
            ('game_logs', 'mlb_game_pk = :game_pk', {'game_pk': GAME_PK}),
            ('game_ingestion_work_items', 'mlb_game_pk = :game_pk',
             {'game_pk': GAME_PK}),
            ('postgame_processed_games', 'mlb_game_pk = :game_pk',
             {'game_pk': GAME_PK}),
            ('team_game_pitching_splits', 'mlb_game_pk = :game_pk',
             {'game_pk': GAME_PK}),
            ('completed_game_contexts', 'game_pk = :game_pk',
             {'game_pk': GAME_PK}),
            ('game_play_by_play_events', 'mlb_game_pk = :game_pk',
             {'game_pk': GAME_PK}),
            ('sync_failures', 'entity_ref = :game_ref',
             {'game_ref': str(GAME_PK)}),
        ],
        SCOPE_PITCHER_IDENTITY: [
            ('pitchers',
             'id IN (SELECT pitcher_id FROM game_logs WHERE '
             'mlb_game_pk = :game_pk) OR mlb_id = ANY(:mlb_ids)',
             {'game_pk': GAME_PK, 'mlb_ids': identities or [-1]}),
        ],
    }

    digests: dict[str, dict] = {}
    try:
        for scope, entries in scopes.items():
            scope_digests = {}
            for table, predicate, params in entries:
                statement = sql_text(
                    f"SELECT md5(coalesce(string_agg(t::text, '|' "
                    f"ORDER BY t::text), '')) FROM {table} t "
                    f"WHERE {predicate}"
                )
                scope_digests[table] = session.execute(
                    statement, params
                ).scalar()
            digests[scope] = scope_digests
    except Exception:  # noqa: BLE001 - an unprovable fingerprint is UNPROVEN
        return None
    return digests


def fingerprint_scopes_match(before, after) -> bool | None:
    if not isinstance(before, dict) or not isinstance(after, dict):
        return None
    if set(before) != set(after):
        return False
    for scope in before:
        if set(before[scope]) != set(after[scope]):
            return False
        for table in before[scope]:
            if before[scope][table] != after[scope][table]:
                return False
    return True


def changed_fingerprint_scopes(before, after) -> list[str]:
    if not isinstance(before, dict) or not isinstance(after, dict):
        return []
    return [
        scope for scope in sorted(set(before) | set(after))
        if before.get(scope) != after.get(scope)
    ]


# ── Code-path drift (symbol-level, not whole-file) ──────────────────────────
# A whole-file blob comparison answers the wrong question: a module can change
# for reasons that cannot touch either digest. Every target below is compared at
# SYMBOL level over a normalized AST, so formatting-only and comment-only edits
# report no drift while a real change in behaviour does.

SYMBOL_KIND_FUNCTION = 'function'
SYMBOL_KIND_CONSTANT = 'constant'

DRIFT_EQUAL = 'equal'
DRIFT_CHANGED = 'changed'
DRIFT_SYMBOL_MISSING = 'symbol_missing'
DRIFT_FILE_MISSING = 'file_missing'
DRIFT_UNPARSEABLE = 'unparseable'
DRIFT_UNAVAILABLE = 'sha_unavailable'

DRIFT_STATES = (
    DRIFT_EQUAL, DRIFT_CHANGED, DRIFT_SYMBOL_MISSING, DRIFT_FILE_MISSING,
    DRIFT_UNPARSEABLE, DRIFT_UNAVAILABLE,
)

# ``names`` is ordered: the first name found at a given SHA is the historical
# symbol actually used. A renamed symbol is identified rather than silently
# skipped. ``affects`` records which digest a real change to it could move.
AFFECTS_SOURCE_REVISION = 'source_revision'
AFFECTS_PLAN_FINGERPRINT = 'plan_fingerprint'
AFFECTS_OBSERVER = 'activation_observer'

CODE_DRIFT_TARGETS = (
    {
        'target_id': 'extraction.FINGERPRINT_FIELDS',
        'path': 'backend/services/game_appearance_extraction.py',
        'names': ('FINGERPRINT_FIELDS',),
        'kind': SYMBOL_KIND_CONSTANT,
        'affects': (AFFECTS_SOURCE_REVISION,),
    },
    {
        'target_id': 'extraction.extract_game_appearances',
        'path': 'backend/services/game_appearance_extraction.py',
        'names': ('extract_game_appearances',),
        'kind': SYMBOL_KIND_FUNCTION,
        'affects': (AFFECTS_SOURCE_REVISION, AFFECTS_PLAN_FINGERPRINT),
    },
    {
        'target_id': 'extraction.appearance_set_fingerprint',
        'path': 'backend/services/game_appearance_extraction.py',
        'names': ('appearance_set_fingerprint',),
        'kind': SYMBOL_KIND_FUNCTION,
        'affects': (AFFECTS_SOURCE_REVISION,),
    },
    {
        'target_id': 'extraction._games_started_for_line',
        'path': 'backend/services/game_appearance_extraction.py',
        'names': ('_games_started_for_line',),
        'kind': SYMBOL_KIND_FUNCTION,
        'affects': (AFFECTS_SOURCE_REVISION,),
    },
    {
        'target_id': 'sync._extract_pitching_lines_from_boxscore',
        'path': 'backend/services/sync.py',
        'names': ('_extract_pitching_lines_from_boxscore',),
        'kind': SYMBOL_KIND_FUNCTION,
        'affects': (AFFECTS_SOURCE_REVISION, AFFECTS_PLAN_FINGERPRINT),
    },
    {
        'target_id': 'sync._pitcher_order_by_side',
        'path': 'backend/services/sync.py',
        'names': ('_pitcher_order_by_side',),
        'kind': SYMBOL_KIND_FUNCTION,
        'affects': (AFFECTS_SOURCE_REVISION,),
    },
    {
        'target_id': 'sync.games_started_helper',
        'path': 'backend/services/sync.py',
        # The canonical sync games-started helper. Ordered aliases so a
        # historical rename is identified rather than reported as missing.
        'names': ('_line_games_started', '_games_started_for_line'),
        'kind': SYMBOL_KIND_FUNCTION,
        'affects': (AFFECTS_SOURCE_REVISION, AFFECTS_PLAN_FINGERPRINT),
    },
    {
        'target_id': 'utils.games_started.parse_games_started',
        'path': 'backend/utils/games_started.py',
        'names': ('parse_games_started',),
        'kind': SYMBOL_KIND_FUNCTION,
        'affects': (AFFECTS_SOURCE_REVISION, AFFECTS_PLAN_FINGERPRINT),
    },
    {
        'target_id': 'utils.innings.parse_mlb_innings_to_outs',
        'path': 'backend/utils/innings.py',
        'names': ('parse_mlb_innings_to_outs',),
        'kind': SYMBOL_KIND_FUNCTION,
        'affects': (AFFECTS_SOURCE_REVISION, AFFECTS_PLAN_FINGERPRINT),
    },
    {
        'target_id': 'utils.innings.outs_to_decimal_innings',
        'path': 'backend/utils/innings.py',
        'names': ('outs_to_decimal_innings',),
        'kind': SYMBOL_KIND_FUNCTION,
        'affects': (AFFECTS_PLAN_FINGERPRINT,),
    },
    {
        'target_id': 'reconciliation.plan_row',
        'path': 'backend/services/game_log_reconciliation.py',
        'names': ('plan_row',),
        'kind': SYMBOL_KIND_FUNCTION,
        'affects': (AFFECTS_PLAN_FINGERPRINT,),
    },
    {
        'target_id': 'reconciliation._plan_row_decision',
        'path': 'backend/services/game_log_reconciliation.py',
        'names': ('_plan_row_decision',),
        'kind': SYMBOL_KIND_FUNCTION,
        'affects': (AFFECTS_PLAN_FINGERPRINT,),
    },
    {
        'target_id': 'reconciliation.plan_fingerprint',
        'path': 'backend/services/game_log_reconciliation.py',
        'names': ('plan_fingerprint',),
        'kind': SYMBOL_KIND_FUNCTION,
        'affects': (AFFECTS_PLAN_FINGERPRINT,),
    },
    {
        'target_id': 'reconciliation.RECONCILIATION_PLAN_VERSION',
        'path': 'backend/services/game_log_reconciliation.py',
        'names': ('RECONCILIATION_PLAN_VERSION',),
        'kind': SYMBOL_KIND_CONSTANT,
        'affects': (AFFECTS_PLAN_FINGERPRINT,),
    },
    {
        'target_id': 'reconciliation.STATISTICAL_FIELDS',
        'path': 'backend/services/game_log_reconciliation.py',
        'names': ('STATISTICAL_FIELDS',),
        'kind': SYMBOL_KIND_CONSTANT,
        'affects': (AFFECTS_PLAN_FINGERPRINT,),
    },
    {
        'target_id': 'realization._source_revision_states',
        'path': 'backend/services/game_driven_realization.py',
        'names': ('_source_revision_states',),
        'kind': SYMBOL_KIND_FUNCTION,
        'affects': (AFFECTS_OBSERVER,),
    },
    {
        'target_id': 'realization.build_daily_realization',
        'path': 'backend/services/game_driven_realization.py',
        'names': ('build_daily_realization',),
        'kind': SYMBOL_KIND_FUNCTION,
        'affects': (AFFECTS_OBSERVER,),
    },
)

DIGEST_AFFECTING_TARGETS = tuple(
    target['target_id'] for target in CODE_DRIFT_TARGETS
    if AFFECTS_SOURCE_REVISION in target['affects']
)


def _strip_docstring(node):
    """Remove a leading docstring so a documentation edit is not drift."""
    body = list(getattr(node, 'body', ()) or ())
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    return body


def normalized_symbol_digest(node) -> str:
    """Formatting- and comment-insensitive digest of one symbol's semantics.

    Comments never reach the AST. ``ast.dump`` without attributes drops line
    numbers, column offsets, and every whitespace decision, so reflowing a
    function or re-indenting a literal produces the identical digest. A leading
    docstring is removed explicitly, because it IS an AST node.

    The symbol's own NAME is normalized away. A target is identified here by
    the role it plays, not by what it is called, so a historical rename with an
    identical body is a rename — reported as one — and not behavioural drift.
    """
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        clone = ast.Module(body=_strip_docstring(node), type_ignores=[])
        # Signature and decorators are semantics, so they travel with the body.
        rendered = ast.dump(
            ast.Module(
                body=[
                    ast.FunctionDef(
                        name='_normalized_symbol_name',
                        args=node.args,
                        body=clone.body or [ast.Pass()],
                        decorator_list=node.decorator_list,
                        returns=node.returns,
                        type_comment=None,
                    )
                ],
                type_ignores=[],
            ),
            annotate_fields=True,
            include_attributes=False,
        )
    else:
        rendered = ast.dump(
            node, annotate_fields=True, include_attributes=False,
        )
    return hashlib.sha256(rendered.encode('utf-8')).hexdigest()


def find_symbol(source, names, kind) -> dict:
    """Locate the first of ``names`` defined at module level in ``source``."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {'state': DRIFT_UNPARSEABLE, 'symbol_name': None}

    for name in names:
        for node in tree.body:
            if kind == SYMBOL_KIND_FUNCTION and isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) and node.name == name:
                return {
                    'state': 'found',
                    'symbol_name': name,
                    'digest': normalized_symbol_digest(node),
                    'constant_value': None,
                }
            if kind == SYMBOL_KIND_CONSTANT and isinstance(node, ast.Assign):
                targets = [
                    target.id for target in node.targets
                    if isinstance(target, ast.Name)
                ]
                if name in targets:
                    try:
                        value = ast.literal_eval(node.value)
                    except (ValueError, SyntaxError, TypeError):
                        value = None
                    return {
                        'state': 'found',
                        'symbol_name': name,
                        'digest': normalized_symbol_digest(node.value),
                        'constant_value': _jsonable(value),
                    }
    return {'state': DRIFT_SYMBOL_MISSING, 'symbol_name': None}


def _jsonable(value):
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def compare_symbol_across_revisions(target, sources) -> dict:
    """Compare one target symbol across ``{revision_label: source or None}``.

    ``sources`` maps a revision label to the file's text at that revision, or
    to ``None`` when the file (or the revision) could not be read at all.
    """
    observations: dict[str, dict] = {}
    for label, source in sources.items():
        if source is None:
            observations[label] = {
                'state': DRIFT_UNAVAILABLE, 'symbol_name': None,
                'digest': None, 'constant_value': None,
                'full_file_blob': None,
            }
            continue
        if source == '':
            observations[label] = {
                'state': DRIFT_FILE_MISSING, 'symbol_name': None,
                'digest': None, 'constant_value': None,
                'full_file_blob': None,
            }
            continue
        found = find_symbol(source, target['names'], target['kind'])
        observations[label] = {
            'state': found['state'],
            'symbol_name': found.get('symbol_name'),
            'digest': found.get('digest'),
            'constant_value': found.get('constant_value'),
            'full_file_blob': hashlib.sha256(
                source.encode('utf-8')
            ).hexdigest(),
        }

    labels = list(sources)
    resolved = [
        label for label in labels
        if observations[label]['state'] == 'found'
    ]
    unresolved = [
        label for label in labels
        if observations[label]['state'] != 'found'
    ]
    digests = {observations[label]['digest'] for label in resolved}
    constants = {
        json.dumps(observations[label]['constant_value'], sort_keys=True)
        for label in resolved
    }
    blobs = {
        observations[label]['full_file_blob'] for label in labels
        if observations[label]['full_file_blob'] is not None
    }

    if unresolved:
        state = observations[unresolved[0]]['state']
        comparable = False
    elif len(digests) <= 1:
        state = DRIFT_EQUAL
        comparable = True
    else:
        state = DRIFT_CHANGED
        comparable = True

    return {
        'target_id': target['target_id'],
        'path': target['path'],
        'kind': target['kind'],
        'candidate_names': list(target['names']),
        'affects': list(target['affects']),
        'observations': observations,
        'comparable': comparable,
        'state': state,
        'semantic_drift': state == DRIFT_CHANGED,
        # Whole-file equality is reported alongside the symbol verdict, never
        # instead of it: a module can move for reasons that cannot reach either
        # digest, and that difference is exactly what this audit must not
        # mistake for behavioural drift.
        'full_file_identical_across_revisions': len(blobs) <= 1,
        'constants_identical': len(constants) <= 1 if resolved else None,
        'symbol_names_by_revision': {
            label: observations[label]['symbol_name'] for label in labels
        },
        'renamed_between_revisions': len({
            observations[label]['symbol_name'] for label in resolved
        }) > 1,
        'can_affect_source_revision': (
            state == DRIFT_CHANGED
            and AFFECTS_SOURCE_REVISION in target['affects']
        ),
        'can_affect_plan_fingerprint': (
            state == DRIFT_CHANGED
            and AFFECTS_PLAN_FINGERPRINT in target['affects']
        ),
    }


def summarize_code_drift(comparisons) -> dict:
    comparisons = list(comparisons or ())
    changed = [
        entry['target_id'] for entry in comparisons if entry['semantic_drift']
    ]
    incomparable = [
        entry['target_id'] for entry in comparisons if not entry['comparable']
    ]
    revision_affecting = [
        entry['target_id'] for entry in comparisons
        if entry['can_affect_source_revision']
    ]
    plan_affecting = [
        entry['target_id'] for entry in comparisons
        if entry['can_affect_plan_fingerprint']
    ]
    files_changed = sorted({
        entry['path'] for entry in comparisons
        if entry['full_file_identical_across_revisions'] is False
    })
    return {
        'targets_compared': len(comparisons),
        'semantic_drift_targets': sorted(changed),
        'semantic_drift_detected': bool(changed),
        'incomparable_targets': sorted(incomparable),
        'comparison_complete': not incomparable,
        'source_revision_affecting_drift': sorted(revision_affecting),
        'plan_fingerprint_affecting_drift': sorted(plan_affecting),
        'files_whose_full_blob_changed': files_changed,
        # The distinction this audit exists to keep straight.
        'files_changed_without_semantic_drift': sorted(
            path for path in files_changed
            if not any(
                entry['semantic_drift'] for entry in comparisons
                if entry['path'] == path
            )
        ),
        'comparisons': comparisons,
    }


# ── Fingerprint determinism ─────────────────────────────────────────────────

DETERMINISM_REPEATS = 5
DETERMINISM_PERMUTATIONS = 4


def deterministic_permutations(appearances, count=DETERMINISM_PERMUTATIONS):
    """Deterministic reorderings of one appearance set. No randomness."""
    records = list(appearances or ())
    if not records:
        return []
    orders = [
        list(reversed(records)),
        sorted(records, key=lambda item: str(item.get('pitcher_mlb_id'))),
        sorted(
            records,
            key=lambda item: (
                item.get('outs_recorded') or 0, item.get('pitcher_mlb_id') or 0
            ),
            reverse=True,
        ),
        records[len(records) // 2:] + records[:len(records) // 2],
    ]
    return orders[:count]


def fingerprint_determinism(appearances) -> dict:
    """Recompute the fingerprint over identical normalized content.

    No MLB request is made here: the same in-memory appearance set is reused.
    A difference over identical normalized content is a digest defect.
    """
    records = list(appearances or ())
    if not records:
        return {
            'appearance_count': 0,
            'repeat_count': 0,
            'repeated_fingerprints': [],
            'permutation_count': 0,
            'permutation_fingerprints': [],
            'deterministic_in_process': None,
            'evidence_status': EVIDENCE_UNPROVEN,
        }
    repeated = [
        extraction.appearance_set_fingerprint(records)
        for _ in range(DETERMINISM_REPEATS)
    ]
    permutations = deterministic_permutations(records)
    permuted = [
        extraction.appearance_set_fingerprint(order) for order in permutations
    ]
    stable = len(set(repeated) | set(permuted)) == 1
    return {
        'appearance_count': len(records),
        'repeat_count': len(repeated),
        'repeated_fingerprints': repeated,
        'permutation_count': len(permuted),
        'permutation_fingerprints': permuted,
        'deterministic_in_process': stable,
        'evidence_status': EVIDENCE_PROVEN,
    }


# ── Field-level evidence matrix ─────────────────────────────────────────────
# Every current FINGERPRINT_FIELD plus every additional writer-governed field
# the canonical reconciliation plan may determine.

WRITER_GOVERNED_FIELDS = tuple(sorted(set(
    reconciliation.STATISTICAL_FIELDS
    + reconciliation.ROLE_SIGNAL_FIELDS
    + reconciliation.GAME_METADATA_FIELDS
    + reconciliation.APPEARANCE_TEAM_FIELDS
)))

# Official appearance field -> the stored canonical column that carries it.
# ``opponent_team_id`` has no GameLog column: its stored authority is the
# schedule ledger row for this appearance's team, which is where the writer
# reads it from too.
STORED_FIELD_BY_OFFICIAL_FIELD = {
    'pitcher_mlb_id': 'pitcher.mlb_id',
    'team_id': 'game_logs.appearance_team_id',
    'opponent_team_id': 'scheduled_games.opponent_team_id',
    'appearance_role': 'derived_from_game_logs.games_started',
    'games_started': 'game_logs.games_started',
    'outs_recorded': 'game_logs.innings_pitched_outs',
    'earned_runs': 'game_logs.earned_runs',
    'runs_allowed': 'game_logs.runs_allowed',
    'hits_allowed': 'game_logs.hits_allowed',
    'walks': 'game_logs.walks',
    'strikeouts': 'game_logs.strikeouts',
    'home_runs_allowed': 'game_logs.home_runs_allowed',
    'batters_faced': 'game_logs.batters_faced',
    'pitches_thrown': 'game_logs.pitches_thrown',
}

# Writer-governed field -> the key the canonical appearance record carries it
# under. A writer-governed field with no entry here is one the official
# appearance schema simply does not express (strikes, balls, save/hold/win
# flags, leverage index, the appearance-team provenance columns). Those are
# reported NOT COMPARABLE rather than as a difference: "the extractor never
# looked" and "the values disagree" are different facts.
OFFICIAL_FIELD_ALIASES = {
    'innings_pitched_outs': 'outs_recorded',
    'appearance_team_id': 'team_id',
}

# Recorded outs are the permanent innings authority; the decimal companion is
# derived from them and is never an independent official fact, so a decimal
# display difference is NOT a baseball correction.
INNINGS_AUTHORITY_FIELD = 'outs_recorded'
INNINGS_DISPLAY_FIELD = 'innings_pitched'

MATERIALITY_CANONICAL_OUTS = 'canonical_outs'
MATERIALITY_STATISTICAL = 'statistical'
MATERIALITY_ROLE = 'role_signal'
MATERIALITY_APPEARANCE_TEAM = 'appearance_team_authority'
MATERIALITY_IDENTITY = 'pitcher_identity'
MATERIALITY_DISPLAY_ONLY = 'derived_display_only'
MATERIALITY_NONE = 'no_difference'
MATERIALITY_UNKNOWN = 'unknown'

CONCLUSION_MATCHES = 'current_official_matches_storage'
CONCLUSION_DIFFERS = 'current_official_differs_from_storage'
CONCLUSION_STORAGE_MISSING = 'stored_appearance_missing'
CONCLUSION_OFFICIAL_MISSING = 'official_appearance_missing'
CONCLUSION_UNCOMPARABLE = 'not_comparable'


def comparable_value(value):
    """Normalize for comparison only, never for reporting.

    A date read from a model and a date carried by an appearance record
    describe the same day in two representations. Comparing the
    representations rather than the day would manufacture a difference in
    every single row.
    """
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def field_materiality(field, official_value, stored_value) -> str:
    if comparable_value(official_value) == comparable_value(stored_value):
        return MATERIALITY_NONE
    if field == INNINGS_DISPLAY_FIELD:
        return MATERIALITY_DISPLAY_ONLY
    if field == INNINGS_AUTHORITY_FIELD or field == 'innings_pitched_outs':
        return MATERIALITY_CANONICAL_OUTS
    if field in ('appearance_role', 'games_started'):
        return MATERIALITY_ROLE
    if field in ('team_id', 'opponent_team_id') or field in (
        reconciliation.APPEARANCE_TEAM_FIELDS
    ):
        return MATERIALITY_APPEARANCE_TEAM
    if field == 'pitcher_mlb_id':
        return MATERIALITY_IDENTITY
    if field in reconciliation.STATISTICAL_FIELDS or field in (
        'earned_runs', 'runs_allowed', 'hits_allowed', 'walks', 'strikeouts',
        'home_runs_allowed', 'batters_faced', 'pitches_thrown',
    ):
        return MATERIALITY_STATISTICAL
    return MATERIALITY_UNKNOWN


def matrix_row(
    *,
    pitcher_mlb_id,
    side,
    field_name,
    current_official_value,
    current_stored_value,
    official_present=True,
    stored_present=True,
    comparable=True,
    participates_in_writer_target=None,
    prior_value=None,
    prior_value_evidence_source=EVIDENCE_SOURCE_NONE,
    prior_value_evidence_status=EVIDENCE_NOT_RETAINED,
    later_run_value=None,
    later_value_evidence_source=EVIDENCE_SOURCE_NONE,
    later_value_evidence_status=EVIDENCE_NOT_RETAINED,
    correction_provenance_available=False,
    confidence=CONFIDENCE_HIGH,
) -> dict:
    """One machine-readable field-matrix row.

    A historical value that was never retained is reported as ``None`` WITH an
    evidence status of ``not_retained``. Null is a legitimate baseball value, so
    the status — not the value — is what distinguishes "absent from the source"
    from "never recorded anywhere".
    """
    if not official_present:
        conclusion = CONCLUSION_OFFICIAL_MISSING
        values_match = False
        materiality = MATERIALITY_UNKNOWN
    elif not stored_present:
        conclusion = CONCLUSION_STORAGE_MISSING
        values_match = False
        materiality = MATERIALITY_UNKNOWN
    elif not comparable:
        # The official appearance schema does not express this field at all.
        # Absence of a comparison is not agreement, and it is not a difference.
        conclusion = CONCLUSION_UNCOMPARABLE
        values_match = None
        materiality = MATERIALITY_UNKNOWN
    else:
        values_match = comparable_value(
            current_official_value
        ) == comparable_value(current_stored_value)
        conclusion = (
            CONCLUSION_MATCHES if values_match else CONCLUSION_DIFFERS
        )
        materiality = field_materiality(
            field_name, current_official_value, current_stored_value,
        )
    return {
        'game_pk': GAME_PK,
        'pitcher_mlb_id': pitcher_mlb_id,
        'side': side,
        'field_name': field_name,
        'participates_in_source_revision': (
            field_name in extraction.FINGERPRINT_FIELDS
        ),
        'participates_in_writer_target': participates_in_writer_target,
        'stored_authority': STORED_FIELD_BY_OFFICIAL_FIELD.get(field_name),
        'current_official_value': _jsonable(current_official_value),
        'current_stored_value': _jsonable(current_stored_value),
        'current_values_match': values_match,
        'prior_value': _jsonable(prior_value),
        'prior_value_evidence_source': prior_value_evidence_source,
        'prior_value_evidence_status': prior_value_evidence_status,
        'later_run_value': _jsonable(later_run_value),
        'later_value_evidence_source': later_value_evidence_source,
        'later_value_evidence_status': later_value_evidence_status,
        'correction_provenance_available': bool(
            correction_provenance_available
        ),
        'materiality': materiality,
        'conclusion': conclusion,
        'confidence': confidence,
    }


def validate_matrix(rows) -> dict:
    """Structural guarantees the matrix must hold, checked rather than assumed."""
    rows = list(rows or ())
    required = {
        'game_pk', 'pitcher_mlb_id', 'side', 'field_name',
        'participates_in_source_revision', 'participates_in_writer_target',
        'current_official_value', 'current_stored_value',
        'current_values_match', 'prior_value', 'prior_value_evidence_source',
        'prior_value_evidence_status', 'later_run_value',
        'later_value_evidence_source', 'later_value_evidence_status',
        'correction_provenance_available',
        'materiality', 'conclusion', 'confidence',
    }
    missing_keys = sorted({
        key for row in rows for key in required if key not in row
    })
    bad_status = [
        row for row in rows
        if row.get('prior_value_evidence_status') not in EVIDENCE_STATUSES
        or row.get('later_value_evidence_status') not in EVIDENCE_STATUSES
    ]
    return {
        'row_count': len(rows),
        'missing_keys': missing_keys,
        'rows_with_invalid_evidence_status': len(bad_status),
        # No historical cell may be a bare null: a value that was never
        # retained and a value that is legitimately null must stay distinct.
        'every_historical_cell_carries_a_status': not bad_status,
        'structurally_valid': not missing_keys and not bad_status,
        'pitchers': sorted({
            row['pitcher_mlb_id'] for row in rows
            if row.get('pitcher_mlb_id') is not None
        }),
        'fields': sorted({row['field_name'] for row in rows}),
        'differing_rows': [
            {
                'pitcher_mlb_id': row['pitcher_mlb_id'],
                'field_name': row['field_name'],
                'materiality': row['materiality'],
            }
            for row in rows if row.get('conclusion') == CONCLUSION_DIFFERS
        ],
        # An absent row on either side is not a row that agreed. These two
        # counts are conclusion-blocking, not diagnostics: an empty
        # ``differing_rows`` proves only that the COMPARABLE rows carried no
        # governed difference, and says nothing about the rows that were
        # never comparable because one side had no appearance at all.
        'official_missing_rows': [
            {
                'pitcher_mlb_id': row['pitcher_mlb_id'],
                'field_name': row['field_name'],
            }
            for row in rows
            if row.get('conclusion') == CONCLUSION_OFFICIAL_MISSING
        ],
        'stored_missing_rows': [
            {
                'pitcher_mlb_id': row['pitcher_mlb_id'],
                'field_name': row['field_name'],
            }
            for row in rows
            if row.get('conclusion') == CONCLUSION_STORAGE_MISSING
        ],
        'official_missing_row_count': sum(
            1 for row in rows
            if row.get('conclusion') == CONCLUSION_OFFICIAL_MISSING
        ),
        'stored_missing_row_count': sum(
            1 for row in rows
            if row.get('conclusion') == CONCLUSION_STORAGE_MISSING
        ),
    }


# ── Retained appearance-count expectation ───────────────────────────────────
# What the two retained runs POSITIVELY OBSERVED about how many appearances
# this game has. This is the only thing that can tell the audit whether the set
# it observed today is the whole game, and it is read out of the artifacts'
# own observations — never out of RUN_EXPECTATIONS. The locked constant still
# validates artifact content under the artifact contract; after that
# validation, the number the artifact actually carried is what is consumed.

EXPECTATION_VERIFIED = 'verified_common_count'
EXPECTATION_PRIOR_ARTIFACT_UNPROVEN = 'prior_artifact_unproven'
EXPECTATION_LATER_ARTIFACT_UNPROVEN = 'later_artifact_unproven'
EXPECTATION_PRIOR_COUNT_UNOBSERVED = 'prior_count_unobserved'
EXPECTATION_LATER_COUNT_UNOBSERVED = 'later_count_unobserved'
EXPECTATION_COUNTS_DISAGREE = 'retained_counts_disagree'
EXPECTATION_COUNT_MALFORMED = 'retained_count_malformed'
EXPECTATION_UNAVAILABLE = 'retained_expectation_unavailable'

EXPECTATION_STATES = (
    EXPECTATION_VERIFIED,
    EXPECTATION_PRIOR_ARTIFACT_UNPROVEN,
    EXPECTATION_LATER_ARTIFACT_UNPROVEN,
    EXPECTATION_PRIOR_COUNT_UNOBSERVED,
    EXPECTATION_LATER_COUNT_UNOBSERVED,
    EXPECTATION_COUNTS_DISAGREE,
    EXPECTATION_COUNT_MALFORMED,
    EXPECTATION_UNAVAILABLE,
)

UNPROVEN_RETAINED_EXPECTATION_UNAVAILABLE = (
    'retained_appearance_expectation_unavailable'
)
UNPROVEN_RETAINED_COUNTS_DISAGREE = 'retained_appearance_counts_disagree'
UNPROVEN_CURRENT_COUNT_CONTRADICTS = (
    'current_count_contradicts_retained_expectation'
)
UNPROVEN_DUPLICATE_APPEARANCE_IDENTITY = 'duplicate_appearance_identity'

_COUNT_FIELD = 'appearances_extracted'
_COUNT_PATH = (
    f'sync.game_driven_ingestion.games[game_pk={GAME_PK}].{_COUNT_FIELD}'
)


def _retained_count(entry) -> tuple:
    """(count, observation_state, artifact_usable) for one retained run.

    The count is the value the ARTIFACT carried, taken from its own
    observation. Nothing here consults ``RUN_EXPECTATIONS``.
    """
    entry = entry or {}
    artifact_usable = bool(
        entry.get('identity_verified') and entry.get('content_verified')
    )
    observations = entry.get('observations') or ()
    state = observation_state(observations, _COUNT_FIELD)
    if state != OBS_VERIFIED:
        return None, state, artifact_usable
    value = observation_value(observations, _COUNT_FIELD)
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        return None, OBS_MALFORMED, artifact_usable
    return value, state, artifact_usable


def retained_appearance_expectation(runs) -> dict:
    """The appearance count BOTH retained runs positively verified.

    Only ``verified_common_count`` may supply ``expected_current_count``, and
    it requires both artifacts identity-verified AND content-verified, both
    counts positively observed and verified, and the two counts equal. One
    artifact alone establishes nothing; a count inferred from ``unchanged``,
    from a list length, or from the locked constant establishes nothing.
    """
    runs = runs or {}
    prior_entry = runs.get(RUN_PRIOR) or {}
    later_entry = runs.get(RUN_LATER) or {}

    prior_count, prior_obs, prior_usable = _retained_count(prior_entry)
    later_count, later_obs, later_usable = _retained_count(later_entry)

    reasons: list[str] = []
    if not prior_usable and not later_usable:
        state = EXPECTATION_UNAVAILABLE
    elif not prior_usable:
        state = EXPECTATION_PRIOR_ARTIFACT_UNPROVEN
    elif not later_usable:
        state = EXPECTATION_LATER_ARTIFACT_UNPROVEN
    elif prior_obs == OBS_MALFORMED or later_obs == OBS_MALFORMED:
        state = EXPECTATION_COUNT_MALFORMED
    elif prior_count is None:
        state = EXPECTATION_PRIOR_COUNT_UNOBSERVED
    elif later_count is None:
        state = EXPECTATION_LATER_COUNT_UNOBSERVED
    elif prior_count != later_count:
        state = EXPECTATION_COUNTS_DISAGREE
    else:
        state = EXPECTATION_VERIFIED

    usable = state == EXPECTATION_VERIFIED
    if state == EXPECTATION_COUNTS_DISAGREE:
        reasons.append(UNPROVEN_RETAINED_COUNTS_DISAGREE)
    elif not usable:
        reasons.append(UNPROVEN_RETAINED_EXPECTATION_UNAVAILABLE)

    limitations = [] if usable else [
        'The appearance count this game should carry could not be '
        'established from the retained runs, so the audit cannot tell '
        'whether the set it observed today is the whole game.'
    ]
    if state == EXPECTATION_COUNTS_DISAGREE:
        limitations = [
            'The two retained runs recorded different appearance counts for '
            'this game, so neither can serve as the expected population size.'
        ]

    return {
        'prior_identity_state': prior_entry.get('identity_state'),
        'prior_content_state': prior_entry.get('content_state'),
        'prior_count_observation_state': prior_obs,
        'prior_count': prior_count,
        'later_identity_state': later_entry.get('identity_state'),
        'later_content_state': later_entry.get('content_state'),
        'later_count_observation_state': later_obs,
        'later_count': later_count,
        'both_artifacts_verified': bool(prior_usable and later_usable),
        'counts_agree': (
            prior_count is not None and prior_count == later_count
        ),
        'expected_current_count': prior_count if usable else None,
        'expectation_state': state,
        'conclusion_usable': usable,
        'reason_codes': reasons,
        'limitations': limitations,
        'evidence_sources': [SOURCE_RETAINED_ARTIFACT],
        'evidence_paths': [_COUNT_PATH],
        'note': (
            'The expected population size is the count BOTH retained runs '
            'positively observed and verified. It is never supplied by a '
            'locked constant, by one artifact alone, or by any other field.'
        ),
    }


# ── Current official set completeness ───────────────────────────────────────
# One explicit state machine, not a scattering of booleans. A box-score call
# that succeeded proves the transport worked; it proves nothing about whether
# the payload described the whole game. The canonical lane refuses to ingest a
# final game that produced no pitching appearances
# (``game_driven_ingestion`` raises ``ERROR_APPEARANCE_EXTRACTION_FAILED``),
# and this audit refuses to CONCLUDE from anything less than an appearance set
# whose membership exactly matches what canonical storage holds.

SOURCE_COMPLETE = 'complete_and_comparable'
SOURCE_EMPTY = 'empty_official_set'
SOURCE_OFFICIAL_ONLY_MEMBERS = 'official_only_members_present'
SOURCE_STORED_ONLY_MEMBERS = 'stored_only_members_present'
SOURCE_BOTH_DIRECTIONS = 'both_directions_mismatch'
SOURCE_STATE_UNAVAILABLE = 'source_unavailable'
SOURCE_DATABASE_UNAVAILABLE = 'database_unavailable'
SOURCE_MATRIX_UNPROVEN = 'matrix_unproven'
# Two symmetrically incomplete sets agreeing with one another prove nothing
# about either. The observed population size must also match what the retained
# runs verified this game to hold.
SOURCE_COUNT_CONTRADICTS = 'current_count_contradicts_verified_expectation'
SOURCE_EXPECTATION_UNPROVEN = 'retained_count_expectation_unproven'
SOURCE_EXPECTATION_INCONSISTENT = 'retained_counts_inconsistent'
# A duplicate identity is not a truncated payload and must not borrow that
# explanation.
SOURCE_DUPLICATE_OFFICIAL = 'duplicate_official_identities'
SOURCE_DUPLICATE_STORED = 'duplicate_stored_identities'
SOURCE_DUPLICATE_BOTH = 'duplicate_identities_both_sides'

SOURCE_COMPLETENESS_STATES = (
    SOURCE_COMPLETE,
    SOURCE_EMPTY,
    SOURCE_OFFICIAL_ONLY_MEMBERS,
    SOURCE_STORED_ONLY_MEMBERS,
    SOURCE_BOTH_DIRECTIONS,
    SOURCE_STATE_UNAVAILABLE,
    SOURCE_DATABASE_UNAVAILABLE,
    SOURCE_MATRIX_UNPROVEN,
    SOURCE_COUNT_CONTRADICTS,
    SOURCE_EXPECTATION_UNPROVEN,
    SOURCE_EXPECTATION_INCONSISTENT,
    SOURCE_DUPLICATE_OFFICIAL,
    SOURCE_DUPLICATE_STORED,
    SOURCE_DUPLICATE_BOTH,
)

COUNT_CONSISTENCY_VERIFIED = 'current_count_matches_retained_expectation'
COUNT_CONSISTENCY_CONTRADICTED = 'current_count_differs_from_retained'
COUNT_CONSISTENCY_UNPROVEN = 'retained_expectation_not_usable'
COUNT_CONSISTENCY_NOT_APPLICABLE = 'current_count_not_observed'

# Every state except this one closes the exit-zero path.
CONCLUSION_ELIGIBLE_STATES = frozenset({SOURCE_COMPLETE})

_SOURCE_LIMITATIONS = {
    SOURCE_EMPTY: (
        'The box score was fetched and parsed but produced no pitching '
        'appearances. A final MLB game has pitchers, so this is missing '
        'evidence rather than an observation that the game had none. The '
        'audit spends one bounded box-score call and does not retry, so it '
        'cannot distinguish a truncated payload from an upstream defect.'
    ),
    SOURCE_OFFICIAL_ONLY_MEMBERS: (
        'The observed official set contains at least one pitcher canonical '
        'storage does not hold. Storage may be incomplete. The audit reports '
        'this as material and does not repair it.'
    ),
    SOURCE_STORED_ONLY_MEMBERS: (
        'Canonical storage holds at least one pitcher the observed official '
        'set does not contain. With one bounded source call and no '
        'corroborating authority the audit cannot tell whether the payload '
        'was truncated or the stored row is extraneous, so it resolves '
        'neither direction.'
    ),
    SOURCE_BOTH_DIRECTIONS: (
        'Membership differs in both directions at once. Neither side is '
        'established as the complete set, so no current comparison follows.'
    ),
    SOURCE_STATE_UNAVAILABLE: (
        'The current official source was never observed.'
    ),
    SOURCE_DATABASE_UNAVAILABLE: (
        'The canonical database was never observed, so official membership '
        'had nothing to be compared against.'
    ),
    SOURCE_MATRIX_UNPROVEN: (
        'The field matrix did not validate structurally, so its membership '
        'accounting cannot be relied upon.'
    ),
    SOURCE_EXPECTATION_UNPROVEN: (
        'The appearance count this game should carry was not established '
        'from the retained runs, so the observed set cannot be shown to be '
        'the whole game.'
    ),
    SOURCE_EXPECTATION_INCONSISTENT: (
        'The two retained runs recorded different appearance counts, so '
        'neither can serve as the expected population size.'
    ),
    SOURCE_DUPLICATE_OFFICIAL: (
        'The observed official set carries the same pitcher more than once. '
        'One pitcher has exactly one pitching line per game, so the payload '
        'is ambiguous rather than merely incomplete. Deduplicating it to '
        'prove completeness would be inventing evidence.'
    ),
    SOURCE_DUPLICATE_STORED: (
        'Canonical storage holds more than one row for the same pitcher in '
        'this game. That is a stored-identity condition, NOT a truncated '
        'source payload, and it needs read-only identity review rather than '
        'any inference about the official response.'
    ),
    SOURCE_DUPLICATE_BOTH: (
        'Both the observed official set and canonical storage carry a '
        'duplicated pitcher identity. Neither side is an unambiguous '
        'appearance set, so no current comparison follows.'
    ),
}


def _count_limitations(count_state, observed, expected) -> list[str]:
    """The bounded statement for a count contradiction. Counts are dynamic.

    Deliberately says what was observed and what was verified, and then stops.
    It does NOT name a cause: one bounded source call cannot distinguish an
    official correction from incomplete current evidence, and guessing between
    them is the failure this gate exists to prevent.
    """
    if count_state == COUNT_CONSISTENCY_CONTRADICTED:
        return [
            f'The current official source yielded {observed} appearances, '
            f'while both verified retained runs recorded {expected}. The '
            'audit cannot determine from one bounded source call whether '
            'this reflects an official correction or incomplete current '
            'evidence. No current exact-match conclusion is permitted.'
        ]
    if count_state == COUNT_CONSISTENCY_UNPROVEN:
        return [
            'The appearance count this game should carry was not established '
            'from the retained runs, so the observed set cannot be shown to '
            'be the whole game.'
        ]
    return []


def current_source_completeness(
    *, official, matrix_summary, database_observed, retained_expectation=None,
) -> dict:
    """Whether the observed official set may support a current conclusion.

    ``conclusion_eligible`` is the single gate every completed result depends
    on. It is true only when the source was fetched, parsed, produced a
    non-empty appearance set, that set carries no duplicated identity, its
    SIZE equals the appearance count both retained runs positively verified,
    and its pitcher membership matches canonical storage EXACTLY in both
    directions.

    Membership equality is necessary and NOT sufficient: two symmetrically
    truncated sets agree with one another while both remain incomplete, which
    is why the retained population size is consulted before membership.
    """
    official = official or {}
    matrix_summary = matrix_summary or {}
    expectation = retained_expectation or {}

    # The empty-appearance guard marks the source unavailable AS EVIDENCE
    # while recording that the call itself succeeded. Both facts are true and
    # they mean different things: the transport worked, the payload did not
    # describe a game. ``empty_official_set`` is the more specific and more
    # actionable state, so it is resolved before plain unavailability.
    empty_extraction = bool(
        official.get('extraction_yielded_no_appearances')
    )
    fetched = bool(official.get('available')) or empty_extraction
    count = official.get('appearance_count')
    count = count if isinstance(count, int) and not isinstance(count, bool) \
        else 0
    official_ids = list(matrix_summary.get('official_pitcher_mlb_ids') or ())
    stored_ids = list(matrix_summary.get('stored_pitcher_mlb_ids') or ())
    missing_from_storage = list(
        matrix_summary.get('missing_from_storage') or ()
    )
    extra_in_storage = list(matrix_summary.get('extra_in_storage') or ())
    official_missing = matrix_summary.get('official_missing_row_count') or 0
    stored_missing = matrix_summary.get('stored_missing_row_count') or 0
    membership_matches = bool(matrix_summary.get('membership_matches'))

    duplicate_official = list(
        matrix_summary.get('duplicate_official_identities') or ()
    )
    duplicate_stored = list(
        matrix_summary.get('duplicate_stored_identities') or ()
    )

    # ── Count consistency, resolved from the retained expectation ───────────
    expected_count = expectation.get('expected_current_count')
    expectation_usable = bool(expectation.get('conclusion_usable'))
    if not expectation_usable:
        count_state = COUNT_CONSISTENCY_UNPROVEN
    elif count <= 0:
        count_state = COUNT_CONSISTENCY_NOT_APPLICABLE
    elif count == expected_count:
        count_state = COUNT_CONSISTENCY_VERIFIED
    else:
        count_state = COUNT_CONSISTENCY_CONTRADICTED
    count_matches = count_state == COUNT_CONSISTENCY_VERIFIED

    reasons: list[str] = []
    if empty_extraction:
        state = SOURCE_EMPTY
        reasons.append(UNPROVEN_CURRENT_SOURCE_EMPTY)
    elif not fetched:
        state = SOURCE_STATE_UNAVAILABLE
        reasons.append(UNPROVEN_CURRENT_SOURCE_UNAVAILABLE)
    elif count <= 0:
        # Ordered before the database check on purpose: an empty set is
        # missing evidence no matter what storage holds, and "zero official
        # versus zero stored" is never a valid match for a final game.
        state = SOURCE_EMPTY
        reasons.append(UNPROVEN_CURRENT_SOURCE_EMPTY)
    elif not database_observed:
        state = SOURCE_DATABASE_UNAVAILABLE
        reasons.append(UNPROVEN_DATABASE_EVIDENCE_UNAVAILABLE)
    elif not matrix_summary.get('structurally_valid'):
        state = SOURCE_MATRIX_UNPROVEN
        reasons.append(UNPROVEN_EXECUTION_ERROR)
    elif expectation.get('expectation_state') == EXPECTATION_COUNTS_DISAGREE:
        state = SOURCE_EXPECTATION_INCONSISTENT
        reasons.append(UNPROVEN_RETAINED_COUNTS_DISAGREE)
    elif not expectation_usable:
        # Without a verified population size the audit cannot tell a complete
        # observation from a symmetrically truncated one.
        state = SOURCE_EXPECTATION_UNPROVEN
        reasons.append(UNPROVEN_RETAINED_EXPECTATION_UNAVAILABLE)
    elif not count_matches:
        # THE symmetric-truncation gate. Reached before membership on purpose:
        # membership equality is exactly what a symmetrically truncated pair
        # satisfies, so it must not be consulted first.
        state = SOURCE_COUNT_CONTRADICTS
        reasons.append(UNPROVEN_CURRENT_COUNT_CONTRADICTS)
    elif duplicate_official and duplicate_stored:
        state = SOURCE_DUPLICATE_BOTH
        reasons.append(UNPROVEN_DUPLICATE_APPEARANCE_IDENTITY)
    elif duplicate_official:
        state = SOURCE_DUPLICATE_OFFICIAL
        reasons.append(UNPROVEN_DUPLICATE_APPEARANCE_IDENTITY)
    elif duplicate_stored:
        state = SOURCE_DUPLICATE_STORED
        reasons.append(UNPROVEN_DUPLICATE_APPEARANCE_IDENTITY)
    elif missing_from_storage and extra_in_storage:
        state = SOURCE_BOTH_DIRECTIONS
        reasons.append(UNPROVEN_CURRENT_SOURCE_INCOMPLETE)
    elif missing_from_storage or stored_missing:
        state = SOURCE_OFFICIAL_ONLY_MEMBERS
        reasons.append(UNPROVEN_CURRENT_SOURCE_INCOMPLETE)
    elif extra_in_storage or official_missing or not membership_matches:
        state = SOURCE_STORED_ONLY_MEMBERS
        reasons.append(UNPROVEN_CURRENT_SOURCE_INCOMPLETE)
    else:
        state = SOURCE_COMPLETE

    return {
        'source_fetch_succeeded': fetched,
        'parse_succeeded': fetched,
        'extraction_yielded_no_appearances': empty_extraction,
        'unavailable_reason': official.get('unavailable_reason'),
        'extracted_appearance_count': count,
        'non_empty': fetched and count > 0,
        'database_observed': bool(database_observed),
        'official_pitcher_ids': official_ids,
        'stored_pitcher_ids': stored_ids,
        'membership_matches': membership_matches,
        'missing_from_storage': missing_from_storage,
        'extra_in_storage': extra_in_storage,
        'official_missing_row_count': official_missing,
        'stored_missing_row_count': stored_missing,
        'duplicate_official_identities': duplicate_official,
        'duplicate_stored_identities': duplicate_stored,
        'duplicate_identity_count': (
            len(duplicate_official) + len(duplicate_stored)
        ),
        'duplicate_identity_state': (
            SOURCE_DUPLICATE_BOTH if duplicate_official and duplicate_stored
            else SOURCE_DUPLICATE_OFFICIAL if duplicate_official
            else SOURCE_DUPLICATE_STORED if duplicate_stored else None
        ),
        # ── Retained expectation and count consistency ─────────────────────
        'retained_expectation_state': expectation.get('expectation_state'),
        'retained_expected_appearance_count': expected_count,
        'retained_prior_count': expectation.get('prior_count'),
        'retained_later_count': expectation.get('later_count'),
        'retained_counts_agree': bool(expectation.get('counts_agree')),
        'current_count_matches_retained_expectation': count_matches,
        'count_consistency_state': count_state,
        'count_conclusion_eligible': count_matches,
        'count_reason_codes': (
            [] if count_matches else [
                UNPROVEN_CURRENT_COUNT_CONTRADICTS
                if count_state == COUNT_CONSISTENCY_CONTRADICTED
                else UNPROVEN_RETAINED_EXPECTATION_UNAVAILABLE
            ]
        ),
        'count_limitations': _count_limitations(
            count_state, count, expected_count,
        ),
        'completeness_state': state,
        'conclusion_eligible': state in CONCLUSION_ELIGIBLE_STATES,
        'reason_codes': reasons,
        'limitations': (
            _count_limitations(count_state, count, expected_count)
            if state == SOURCE_COUNT_CONTRADICTS
            else [] if state == SOURCE_COMPLETE
            else [_SOURCE_LIMITATIONS[state]]
        ),
        'note': (
            'A successful fetch proves transport, not semantic completeness. '
            'Exact membership equality is necessary but NOT sufficient: two '
            'symmetrically truncated sets match each other while both remain '
            'incomplete. The observed count must also equal the appearance '
            'count both retained runs positively verified.'
        ),
    }


# ── Classification ──────────────────────────────────────────────────────────

def classify(
    *,
    artifacts,
    code_drift,
    determinism,
    current_revision_state,
    matrix_summary,
    plan_observation,
    checkpoint,
    source_available,
    source_completeness=None,
) -> dict:
    """Six independent dimensions. Never collapsed into one vague label."""
    artifacts = artifacts or {}
    code_drift = code_drift or {}
    determinism = determinism or {}
    matrix_summary = matrix_summary or {}
    plan_observation = plan_observation or {}
    checkpoint = checkpoint or {}
    source_completeness = source_completeness or {}
    completeness_state = source_completeness.get('completeness_state')
    conclusion_eligible = bool(
        source_completeness.get('conclusion_eligible')
    )
    determinism_proven = determinism.get('deterministic_in_process') is True

    # ── Root condition ──────────────────────────────────────────────────────
    if determinism.get('deterministic_in_process') is False:
        root = ROOT_FINGERPRINT_NONDETERMINISM
    elif source_available and not determinism_proven:
        # The fingerprint is this audit's only instrument. A source that was
        # observed but whose fingerprint was never proven deterministic
        # cannot support a root-condition claim in either direction.
        root = ROOT_UNPROVEN
    elif not artifacts.get('revision_change_proven'):
        root = ROOT_UNPROVEN
    elif code_drift.get('source_revision_affecting_drift'):
        root = ROOT_CODE_PATH_CHANGED
    elif not code_drift.get('comparison_complete'):
        root = ROOT_UNPROVEN
    elif not source_available:
        root = ROOT_UNPROVEN
    elif current_revision_state == CURRENT_MATCHES_LATER and (
        checkpoint.get('matches_current_revision') is True
    ):
        # The later revision is what the source says today and what the
        # checkpoint holds: the appearance set moved once and settled.
        root = ROOT_OFFICIAL_SET_CHANGED
    elif current_revision_state in (
        CURRENT_MATCHES_LATER, CURRENT_MATCHES_PRIOR, CURRENT_MATCHES_NEITHER
    ):
        root = ROOT_OFFICIAL_SET_CHANGED
    else:
        root = ROOT_UNPROVEN

    if (
        root == ROOT_OFFICIAL_SET_CHANGED
        and checkpoint.get('exists') is True
        and checkpoint.get('matches_any_observed_revision') is False
    ):
        root = ROOT_ARTIFACT_CHECKPOINT_INCONSISTENCY

    # ── Current materiality ─────────────────────────────────────────────────
    # Membership is checked BEFORE field values. An empty ``differing_rows``
    # list proves only that the rows which were comparable carried no governed
    # difference; it says nothing about appearances that had no counterpart on
    # one side and so were never comparable at all. Exact match is the
    # strongest claim this audit can make about the present and it is reached
    # only from complete, deterministic, exactly-matching membership.
    if not source_available:
        materiality = MATERIALITY_SOURCE_UNAVAILABLE
    elif not matrix_summary.get('structurally_valid'):
        materiality = MATERIALITY_UNPROVEN
    elif plan_observation.get('action_counts') is None:
        materiality = MATERIALITY_UNPROVEN
    elif completeness_state == SOURCE_EMPTY:
        # Nothing usable was observed. This is an evidence gap, not a finding.
        materiality = MATERIALITY_UNPROVEN
    elif completeness_state == SOURCE_OFFICIAL_ONLY_MEMBERS:
        # The official source carries a pitcher storage does not hold.
        # Canonical storage may be missing a row: material, and reported as
        # such, though the top-level verdict still fails closed below.
        materiality = MATERIALITY_MATERIAL
    elif completeness_state in (
        SOURCE_STORED_ONLY_MEMBERS, SOURCE_BOTH_DIRECTIONS,
        SOURCE_DATABASE_UNAVAILABLE, SOURCE_MATRIX_UNPROVEN,
        # A count contradiction is NOT labelled a correction, a truncation, a
        # storage defect, or a source defect. One bounded call cannot tell
        # them apart, so the dimension stays unproven.
        SOURCE_COUNT_CONTRADICTS, SOURCE_EXPECTATION_UNPROVEN,
        SOURCE_EXPECTATION_INCONSISTENT,
        SOURCE_DUPLICATE_OFFICIAL, SOURCE_DUPLICATE_STORED,
        SOURCE_DUPLICATE_BOTH,
    ):
        # Either the payload was truncated or the stored row is extraneous.
        # One bounded source call cannot tell them apart, so neither is
        # asserted.
        materiality = MATERIALITY_UNPROVEN
    elif plan_observation.get('proposes_mutation') is True:
        materiality = MATERIALITY_MATERIAL
    elif matrix_summary.get('differing_rows'):
        material_kinds = {
            row['materiality'] for row in matrix_summary['differing_rows']
        }
        materiality = (
            MATERIALITY_NON_MATERIAL
            if material_kinds <= {MATERIALITY_DISPLAY_ONLY}
            else MATERIALITY_MATERIAL
        )
    elif not conclusion_eligible or not determinism_proven:
        materiality = MATERIALITY_UNPROVEN
    else:
        materiality = MATERIALITY_EXACT_MATCH

    # ── Persistence ─────────────────────────────────────────────────────────
    persistence = {
        CURRENT_MATCHES_LATER: PERSISTENCE_MATCHES_LATER,
        CURRENT_MATCHES_PRIOR: PERSISTENCE_REVERTED,
        CURRENT_MATCHES_NEITHER: PERSISTENCE_CHANGED_AGAIN,
        CURRENT_SOURCE_UNAVAILABLE: PERSISTENCE_UNAVAILABLE,
        CURRENT_UNPROVEN: PERSISTENCE_UNPROVEN,
    }.get(current_revision_state, PERSISTENCE_UNPROVEN)

    # ── Historical field identification ─────────────────────────────────────
    # ``identified`` requires TWO exact retained values for the SAME game,
    # pitcher, and governed field that actually differ. Presence of a row-like
    # structure, a list of field names, a digest, a count, or a timestamp
    # identifies nothing, and none of them can reach this branch.
    delta = artifacts.get('historical_delta') or {}
    provenance_fields = list(matrix_summary.get('proven_historical_fields') or ())
    if delta.get('delta_identified') or provenance_fields:
        field_identification = FIELD_ID_IDENTIFIED
    elif not artifacts.get('all_required_present'):
        field_identification = FIELD_ID_UNPROVEN
    elif not artifacts.get('identity_all_verified') or not artifacts.get(
        'content_all_verified'
    ):
        # The artifacts arrived but were not proven to be the right artifacts
        # saying the right things. Their silence about values proves nothing.
        field_identification = FIELD_ID_UNPROVEN
    elif artifacts.get('unassociable_historical_candidates'):
        # Something value-shaped was seen and could NOT be safely tied to a
        # run, game, pitcher, and field. That is unproven, not absent.
        field_identification = FIELD_ID_UNPROVEN
    elif code_drift.get('source_revision_affecting_drift'):
        # Drift in a revision-affecting symbol bounds the cause to the code
        # path without naming a baseball field.
        field_identification = FIELD_ID_NARROWED
    else:
        field_identification = FIELD_ID_NOT_RETAINED

    # ── Checkpoint state ────────────────────────────────────────────────────
    if checkpoint.get('exists') is None:
        checkpoint_state = CHECKPOINT_UNPROVEN
    elif checkpoint.get('exists') is False:
        checkpoint_state = CHECKPOINT_MISSING
    elif checkpoint.get('inconsistent'):
        checkpoint_state = CHECKPOINT_INCONSISTENT
    elif not source_available:
        checkpoint_state = CHECKPOINT_UNPROVEN
    elif checkpoint.get('matches_current_revision') is True:
        checkpoint_state = CHECKPOINT_CURRENT
    elif checkpoint.get('matches_current_revision') is False:
        checkpoint_state = CHECKPOINT_STALE
    else:
        checkpoint_state = CHECKPOINT_UNPROVEN

    return {
        'root_condition': root,
        'current_materiality': materiality,
        'persistence': persistence,
        'historical_field_identification': field_identification,
        'checkpoint_state': checkpoint_state,
        # A sixth named dimension rather than a hidden precondition, so a
        # reader can see WHY a current comparison did or did not follow.
        'current_source_completeness': (
            completeness_state or SOURCE_STATE_UNAVAILABLE
        ),
    }


def field_delta_answer(*, artifacts, classification, matrix_summary) -> dict:
    """Question 9, with the evidence limit stated rather than implied."""
    artifacts = artifacts or {}
    matrix_summary = matrix_summary or {}
    identification = (classification or {}).get(
        'historical_field_identification'
    )
    answer = {
        FIELD_ID_IDENTIFIED: DELTA_IDENTIFIED,
        FIELD_ID_NARROWED: DELTA_NARROWED,
        FIELD_ID_NOT_RETAINED: DELTA_NOT_RECOVERABLE,
        FIELD_ID_UNPROVEN: DELTA_UNPROVEN,
    }.get(identification, DELTA_UNPROVEN)

    available = [
        'both retained run artifacts, verified by identity and content',
        'the observed source revision recorded by each run',
        'the per-game reconciliation-plan fingerprint recorded by each run',
        'per-game aggregate counts (appearances, unchanged, inserted, '
        'updated, blocked)',
        'symbol-level code comparison at both historical SHAs and the audit '
        'SHA',
        'the current official appearance set and its recomputed revision',
        'the current stored canonical GameLog state and work-item checkpoint',
    ]
    return {
        'answer': answer,
        'evidence_available': available,
        'evidence_required_and_missing': (
            [] if answer == DELTA_IDENTIFIED else list(REQUIRED_MISSING_EVIDENCE)
        ),
        'proven_historical_fields': list(
            matrix_summary.get('proven_historical_fields') or ()
        ),
        'digest_was_not_inverted': True,
        'note': (
            'A SHA-256 digest is not invertible and carries no field '
            'structure. No field was inferred from either revision digest.'
        ),
    }


def activation_evidence(run_entry) -> dict:
    """The failed run's activation invariants, POSITIVELY OBSERVED.

    Every value here comes out of the retained activation summary at a named
    path. Nothing is supplied by an expectation, and nothing is inferred from
    the artifact merely existing.
    """
    run_entry = run_entry or {}
    observations = run_entry.get('q10_observations') or []
    by_field = {item['field']: item for item in observations}
    values = {
        field: (
            by_field[field]['observed']
            if field in by_field
            and by_field[field]['state'] in POSITIVE_STATES
            | CONTRADICTING_STATES
            else None
        )
        for field in Q10_FIELDS
    }
    observed_fields = sorted(
        field for field in Q10_FIELDS
        if field in by_field
        and by_field[field]['state'] in POSITIVE_STATES | CONTRADICTING_STATES
    )
    missing = sorted(set(Q10_FIELDS) - set(observed_fields))
    return {
        **values,
        'observations': observations,
        'observed_fields': observed_fields,
        'missing_fields': missing,
        'missing_evidence_paths': sorted(
            item['evidence_path'] for item in observations
            if item['state'] in GAP_STATES
        ),
        'mismatched_fields': observation_mismatches(observations),
        'all_required_observed': not missing,
        'state': run_entry.get('q10_state', STATE_UNPROVEN),
        'artifact_present': bool(run_entry.get('present')),
    }


def causality(*, realization_symbol_state, later_activation, drift) -> dict:
    """Question 10: two independent invariants, or one causal chain?

    ``all_projected_targets_realized`` is defined by the realization
    implementation as zero unresolved rows AND zero prohibited identity actions
    AND ``source_revision_match``. A source-revision mismatch therefore makes
    both false on its own — but only if the implementation AT THE FAILED RUN'S
    SHA is the implementation that defines it that way, which is verified
    rather than assumed.
    """
    later = later_activation or {}
    unresolved = later.get('unresolved_rows')
    prohibited = later.get('prohibited_identity_actions')
    revision_match = later.get('source_revision_match')
    realized = later.get('all_projected_targets_realized')
    safe_digest = later.get('safe_digest_match')
    missing = list(later.get('missing_fields') or ())

    if realization_symbol_state == DRIFT_UNAVAILABLE:
        answer = CAUSALITY_UNPROVEN
    elif drift:
        answer = CAUSALITY_UNPROVEN_CODE_DRIFT
    elif missing or not later.get('all_required_observed'):
        # Some required activation value was never observed. Zero is not the
        # default for a counter nobody read, and the artifact merely existing
        # says nothing about what it contains.
        answer = CAUSALITY_UNPROVEN
    elif not isinstance(unresolved, int) or not isinstance(prohibited, int):
        answer = CAUSALITY_UNPROVEN
    elif unresolved > 0:
        answer = CAUSALITY_INDEPENDENT_UNRESOLVED
    elif prohibited > 0:
        answer = CAUSALITY_INDEPENDENT_IDENTITY
    elif revision_match is not False or realized is not False:
        # The single chain explains a FAILED observer. An artifact reporting a
        # matched revision or realized targets is not that incident, and the
        # audit must not narrate a chain the evidence contradicts.
        answer = CAUSALITY_UNPROVEN
    elif safe_digest is not True:
        answer = CAUSALITY_UNPROVEN
    else:
        answer = CAUSALITY_SINGLE_CHAIN

    return {
        'answer': answer,
        'fully_answered': answer in (
            CAUSALITY_SINGLE_CHAIN,
            CAUSALITY_INDEPENDENT_UNRESOLVED,
            CAUSALITY_INDEPENDENT_IDENTITY,
        ),
        'unresolved_rows': unresolved,
        'prohibited_identity_actions': prohibited,
        'source_revision_match': revision_match,
        'safe_digest_match': safe_digest,
        'all_projected_targets_realized': realized,
        'observed_fields': list(later.get('observed_fields') or ()),
        'missing_fields': missing,
        'missing_evidence_paths': list(
            later.get('missing_evidence_paths') or ()
        ),
        'mismatched_fields': list(later.get('mismatched_fields') or ()),
        'evidence_state': later.get('state'),
        'evidence_source': SOURCE_RETAINED_ARTIFACT,
        'realization_definition_verified_at_failed_run_sha': (
            realization_symbol_state == DRIFT_EQUAL
        ),
        'realization_symbol_state': realization_symbol_state,
        'invariant_definition': (
            'all_projected_targets_realized = unresolved_rows == 0 AND '
            'prohibited_identity_actions == 0 AND source_revision_match'
        ),
        'expectations_supplied_no_value': True,
    }


def operational_consequence(classification) -> dict:
    """Question 12. Informational only. Never an authorization."""
    classification = classification or {}
    materiality = classification.get('current_materiality')
    checkpoint_state = classification.get('checkpoint_state')
    field_id = classification.get('historical_field_identification')
    completeness = classification.get('current_source_completeness')
    membership_resolved = completeness == SOURCE_COMPLETE

    supported: list[str] = []
    if materiality == MATERIALITY_MATERIAL:
        supported.append(CONSEQUENCE_GAMELOG_REPAIR)
    if checkpoint_state == CHECKPOINT_STALE:
        supported.append(CONSEQUENCE_WORK_ITEM_REVISION_UPDATE)
    if checkpoint_state == CHECKPOINT_MISSING:
        supported.append(CONSEQUENCE_EXACT_GAME_BACKFILL)
    if field_id == FIELD_ID_NOT_RETAINED:
        supported.append(CONSEQUENCE_ARTIFACT_RETENTION_IMPROVEMENT)
    if completeness == SOURCE_COUNT_CONTRADICTS:
        supported.append(CONSEQUENCE_COUNT_CONSISTENCY_REVIEW)
        supported.append(CONSEQUENCE_SOURCE_COMPLETENESS_REVIEW)
    elif completeness in (
        SOURCE_DUPLICATE_OFFICIAL, SOURCE_DUPLICATE_STORED,
        SOURCE_DUPLICATE_BOTH,
    ):
        supported.append(CONSEQUENCE_IDENTITY_REVIEW)
        supported.append(CONSEQUENCE_SOURCE_COMPLETENESS_REVIEW)
    elif not membership_resolved:
        # Never "continued observation only" while the current membership
        # question is open — that reads as "storage and the source agreed."
        supported.append(CONSEQUENCE_SOURCE_COMPLETENESS_REVIEW)
    elif materiality in (MATERIALITY_EXACT_MATCH, MATERIALITY_NON_MATERIAL):
        supported.append(CONSEQUENCE_CONTINUED_OBSERVATION)
    if not supported:
        supported.append(CONSEQUENCE_NO_ACTION)

    return {
        'supported_by_evidence': sorted(set(supported)),
        'vocabulary': list(CONSEQUENCES),
        'authorizes_no_mutation': True,
        'recommendation_is_not_approval': True,
        'future_repair_requires': (
            'a separate exact-scope package and separate explicit approval'
        ),
        'non_authorization_statement': NON_AUTHORIZATION_STATEMENT,
        'dead_letter_backlog_note': DEAD_LETTER_BACKLOG_NOTE,
    }


# ── Verdict reducer ─────────────────────────────────────────────────────────

def decide(
    *,
    failed_reasons=(),
    unproven_reasons=(),
    classification=None,
    delta=None,
    lock=None,
    questions=None,
    source_completeness=None,
) -> dict:
    """Reduce every observation to exactly one top-level outcome.

    FAILED is reserved for a violation of THIS audit's safety or integrity
    contract. A platform defect discovered by a clean read-only audit is
    information, and information is a successful audit.

    ``lock`` and ``questions`` are gates, not decoration. A guard that was
    taken and not provably returned, or a mandatory question that could not be
    answered from observed evidence, closes the exit-zero path — even when
    every other stage was clean.
    """
    failed = sorted(set(failed_reasons or ()))
    unproven = sorted(set(unproven_reasons or ()))
    classification = classification or {}
    delta = delta or {}
    lock = lock or {}
    source_completeness = source_completeness or {}

    # The current-source completeness gate. Every completed result — all three
    # of them — is a statement about game 824487 as it stands today, and none
    # of them may be reached from an official appearance set that was empty,
    # truncated, or whose membership did not match canonical storage exactly.
    # This runs BEFORE the classification branches so no branch can slip past
    # it, and it contributes a reason rather than silently downgrading.
    # No truthiness. An absent, empty, malformed, or non-mapping completeness
    # object is an audit that never established eligibility, which is exactly
    # the state that must not complete. Only the identity check passes.
    if isinstance(source_completeness, dict):
        eligible = source_completeness.get('conclusion_eligible') is True
        blocking = set(source_completeness.get('reason_codes') or ())
    else:
        eligible = False
        blocking = set()
        source_completeness = {}
    if not eligible:
        if not blocking:
            blocking = {UNPROVEN_CURRENT_SOURCE_INCOMPLETE}
        unproven = sorted(set(unproven) | blocking)

    # The lock lifecycle contributes its own reasons and never loses them to
    # an earlier failure that happens to be reported first.
    failed = sorted(set(failed) | set(lock.get('failed_reasons') or ()))
    unproven = sorted(set(unproven) | set(lock.get('unproven_reasons') or ()))

    unanswered = sorted(
        entry['question_id'] for entry in questions or ()
        if entry.get('mandatory_for_completion')
        and not entry.get('fully_answered')
    )
    if unanswered:
        unproven = sorted(set(unproven) | {UNPROVEN_QUESTION_UNANSWERED})

    if failed:
        result = RESULT_FAILED
    elif unproven:
        result = RESULT_UNPROVEN
    else:
        root = classification.get('root_condition')
        materiality = classification.get('current_materiality')
        if root == ROOT_UNPROVEN or materiality == MATERIALITY_UNPROVEN:
            result = RESULT_UNPROVEN
            unproven = sorted(set(unproven) | {UNPROVEN_EXECUTION_ERROR})
        elif delta.get('answer') in (DELTA_NOT_RECOVERABLE, DELTA_NARROWED):
            result = RESULT_FIELD_DELTA_UNAVAILABLE
        elif (
            root == ROOT_NO_CURRENT_MISMATCH
            or materiality == MATERIALITY_EXACT_MATCH
        ):
            result = RESULT_NO_CURRENT_DEFECT
        else:
            result = RESULT_ROOT_CAUSE_IDENTIFIED

    return {
        'result': result,
        'exit_code': EXIT_CODES[result],
        'failed_reasons': failed,
        'unproven_reasons': unproven if result != RESULT_FAILED else [],
        'classification': dict(classification),
        'field_delta': dict(delta),
        'advisory_lock_lifecycle': dict(lock),
        'current_source_completeness': dict(source_completeness),
        # Always an explicit boolean, never None: "nobody established this"
        # and "this was established false" both close the exit-zero path, and
        # a reader must not have to tell them apart to see that it is closed.
        'current_source_conclusion_eligible': eligible,
        # Preserved even when FAILED outranks, so an authorization failure
        # never hides the fact that eligibility was also never established.
        'current_source_blocking_reasons': sorted(blocking) if not eligible
        else [],
        'unanswered_mandatory_questions': unanswered,
        'platform_defect_discovery_is_not_an_audit_failure': True,
        'non_authorization_statement': NON_AUTHORIZATION_STATEMENT,
        'dead_letter_backlog_note': DEAD_LETTER_BACKLOG_NOTE,
        'standing_production_state': dict(STANDING_PRODUCTION_STATE),
    }


def explanation(decision) -> str:
    result = (decision or {}).get('result')
    classification = (decision or {}).get('classification') or {}
    if result == RESULT_FAILED:
        return (
            "The audit's own safety or integrity contract was violated. No "
            'conclusion about game 824487 may be drawn from this run.'
        )
    if result == RESULT_UNPROVEN:
        completeness = (decision or {}).get(
            'current_source_completeness'
        ) or {}
        state = completeness.get('completeness_state')
        if state == SOURCE_EMPTY:
            return (
                'The current box score was fetched and parsed but produced '
                'no pitching appearances, so there is no current official '
                'appearance set to compare. The source-revision question '
                'remains open.'
            )
        if state == SOURCE_COUNT_CONTRADICTS:
            observed = completeness.get('extracted_appearance_count')
            expected = completeness.get(
                'retained_expected_appearance_count'
            )
            return (
                f'The current official source yielded {observed} '
                f'appearances, while both verified retained runs recorded '
                f'{expected}. One bounded current source observation cannot '
                'distinguish an official correction from incomplete current '
                'evidence, so no current conclusion follows and the '
                'source-revision question remains open.'
            )
        if state in (
            SOURCE_DUPLICATE_OFFICIAL, SOURCE_DUPLICATE_STORED,
            SOURCE_DUPLICATE_BOTH,
        ):
            return (
                'A pitcher identity appears more than once in the observed '
                'appearance evidence. One pitcher has exactly one pitching '
                'line per game, so the set is ambiguous rather than merely '
                'incomplete, and the source-revision question remains open.'
            )
        if state in (
            SOURCE_EXPECTATION_UNPROVEN, SOURCE_EXPECTATION_INCONSISTENT,
        ):
            return (
                'The appearance count this game should carry could not be '
                'established from the retained runs, so the audit cannot '
                'tell whether the set it observed today is the whole game. '
                'The source-revision question remains open.'
            )
        if state in (
            SOURCE_STORED_ONLY_MEMBERS, SOURCE_BOTH_DIRECTIONS,
        ):
            return (
                'The observed official appearance set and canonical storage '
                'do not hold the same pitchers, and one bounded source call '
                'cannot establish which side is incomplete. No current '
                'comparison follows and the source-revision question '
                'remains open.'
            )
        return (
            'Required evidence could not be obtained or validated. The '
            'source-revision question remains open.'
        )
    if result == RESULT_FIELD_DELTA_UNAVAILABLE:
        return (
            'The revision change is proven, code drift is resolved, and '
            'current materiality is established. The exact historical field '
            'delta is not recoverable because prior normalized row-level '
            'values were never retained. This is a completed audit with an '
            'evidence-limit conclusion, not a failure.'
        )
    if result == RESULT_NO_CURRENT_DEFECT:
        return (
            'The current official source and the current canonical state '
            'agree. There is no currently actionable baseball defect; the '
            'historical observer event is reported accurately.'
        )
    return (
        'A root condition was identified from positive evidence: '
        f"{classification.get('root_condition')}."
    )
