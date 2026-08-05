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

FAILED_REASONS = (
    FAILED_EVENT_NOT_WORKFLOW_DISPATCH,
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

UNPROVEN_REASONS = (
    UNPROVEN_ARTIFACT_MISSING,
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
CONSEQUENCE_NO_ACTION = 'no_action'

CONSEQUENCES = (
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


def _match(observed, expected) -> str:
    if observed is None or observed == '':
        return 'not_observed'
    return 'match' if str(observed).strip().lower() == str(
        expected
    ).strip().lower() else 'mismatch'


def verify_run_artifact(run_key, parsed, *, observed_metadata=None) -> dict:
    """Verify one run's retained artifact against its locked expectation.

    Filenames are never trusted: the run id, head SHA, cycle kind, runner exit
    code, configured mode, write posture, and the target game's own recorded
    evidence are all read from INSIDE the documents.
    """
    spec = RUN_EXPECTATIONS[run_key]
    parsed = parsed or {}
    metadata = observed_metadata if isinstance(observed_metadata, dict) else {}

    sync_summary = parsed.get('sync_summary')
    activation = parsed.get('activation_summary') or {}
    handoff = parsed.get('handoff_metadata') or {}
    lane = lane_report(sync_summary)
    effects = lane.get('execution_effects') or {}
    entry = game_entry(sync_summary)

    checks = {
        'workflow_run_id': _match(
            handoff.get('run_id') or handoff.get('workflow_run_id'),
            spec['workflow_run_id'],
        ),
        'head_sha': _match(
            handoff.get('repository_sha') or handoff.get('head_sha'),
            spec['head_sha'],
        ),
        'cycle_kind': _match(
            activation.get('cycle_kind') or handoff.get('cycle_kind'),
            spec['cycle_kind'],
        ),
        'branch': _match(
            handoff.get('branch') or handoff.get('ref') or spec['branch'],
            spec['branch'],
        ),
        'runner_exit_code': (
            'not_observed'
            if activation.get('runner_exit_code') is None
            else 'match'
        ),
        'configured_mode': _match(lane.get('mode'), 'shadow'),
        'writes_enabled': (
            'match' if effects.get('writes_enabled') is False
            else ('not_observed' if 'writes_enabled' not in effects
                  else 'mismatch')
        ),
        'publication_authoritative': (
            'match' if effects.get('publication_authoritative') is False
            else ('not_observed'
                  if 'publication_authoritative' not in effects
                  else 'mismatch')
        ),
        'game_membership': 'match' if entry is not None else 'mismatch',
        'source_revision': _match(
            (entry or {}).get('source_revision'), spec['source_revision'],
        ),
        'reconciliation_plan_fingerprint': _match(
            (entry or {}).get('reconciliation_plan_fingerprint'),
            EXPECTED_PLAN_FINGERPRINT,
        ),
        'appearances_extracted': _match(
            (entry or {}).get('appearances_extracted'),
            EXPECTED_APPEARANCE_COUNT,
        ),
        'unchanged': _match(
            (entry or {}).get('unchanged'), EXPECTED_UNCHANGED_COUNT,
        ),
        'inserted': _match((entry or {}).get('inserted'), 0),
        'updated': _match((entry or {}).get('updated'), 0),
        'blocked': _match((entry or {}).get('blocked'), 0),
    }

    digest = verify_artifact_digest(
        run_key, (metadata.get(spec['artifact_name']) or {}).get('digest'),
    )
    observed_artifact_id = (
        metadata.get(spec['artifact_name']) or {}
    ).get('artifact_id')
    artifact_id_status = (
        'not_exposed_by_github' if observed_artifact_id is None
        else ('match' if int(observed_artifact_id) == spec['artifact_id']
              else 'mismatch')
    )

    mismatched = sorted(
        key for key, value in checks.items() if value == 'mismatch'
    )
    unobserved = sorted(
        key for key, value in checks.items() if value == 'not_observed'
    )
    return {
        'run_key': run_key,
        'artifact_name': spec['artifact_name'],
        'expected_artifact_id': spec['artifact_id'],
        'observed_artifact_id': observed_artifact_id,
        'artifact_id_status': artifact_id_status,
        'expected_workflow_run_id': spec['workflow_run_id'],
        'expected_head_sha': spec['head_sha'],
        'present': bool(parsed.get('files')),
        'missing_files': list(parsed.get('missing_files') or ()),
        'parse_error': parsed.get('parse_error'),
        'checks': checks,
        'mismatched_fields': mismatched,
        'unobserved_fields': unobserved,
        'identity_verified': (
            not mismatched
            and artifact_id_status != 'mismatch'
            and not digest.get('digest_mismatch')
        ),
        'observed_source_revision': (entry or {}).get('source_revision'),
        'observed_plan_fingerprint': (
            entry or {}
        ).get('reconciliation_plan_fingerprint'),
        'observed_appearances_extracted': (
            entry or {}
        ).get('appearances_extracted'),
        'observed_unchanged': (entry or {}).get('unchanged'),
        'observed_inserted': (entry or {}).get('inserted'),
        'observed_updated': (entry or {}).get('updated'),
        'observed_blocked': (entry or {}).get('blocked'),
        'lane_accounting': {
            field: lane.get(field) for field in LATER_LANE_EXPECTATIONS
        },
        'row_level_evidence': scan_row_level_evidence(sync_summary),
        **digest,
    }


def ingest_run_artifacts(root, *, observed_metadata=None) -> dict:
    """Discover and verify BOTH retained run artifacts under ``root``."""
    base = Path(root)
    runs: dict[str, dict] = {}
    for run_key, spec in RUN_EXPECTATIONS.items():
        directory = base / spec['artifact_name']
        if not directory.is_dir():
            runs[run_key] = {
                'run_key': run_key,
                'artifact_name': spec['artifact_name'],
                'expected_artifact_id': spec['artifact_id'],
                'expected_workflow_run_id': spec['workflow_run_id'],
                'expected_head_sha': spec['head_sha'],
                'present': False,
                'missing_files': list(REQUIRED_ARTIFACT_FILES),
                'parse_error': None,
                'checks': {},
                'mismatched_fields': [],
                'unobserved_fields': [],
                'identity_verified': False,
                'row_level_evidence': scan_row_level_evidence(None),
                **verify_artifact_digest(run_key, None),
            }
            continue
        parsed = read_run_artifact(directory)
        entry = verify_run_artifact(
            run_key, parsed, observed_metadata=observed_metadata,
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
    identity_mismatches = sorted(
        key for key, entry in runs.items() if entry.get('mismatched_fields')
    )
    digest_mismatches = sorted(
        key for key, entry in runs.items() if entry.get('digest_mismatch')
    )
    wrong_game = sorted(
        key for key, entry in runs.items()
        if entry.get('present')
        and entry.get('checks', {}).get('game_membership') == 'mismatch'
    )
    return {
        'runs': runs,
        'missing_artifacts': missing,
        'artifacts_missing_required_files': missing_files,
        'identity_mismatches': identity_mismatches,
        'digest_mismatches': digest_mismatches,
        'wrong_game': wrong_game,
        'all_required_present': not missing and not missing_files,
        'revision_change_proven': bool(
            not missing
            and runs.get(RUN_PRIOR, {}).get('observed_source_revision')
            == PRIOR_SOURCE_REVISION
            and runs.get(RUN_LATER, {}).get('observed_source_revision')
            == LATER_SOURCE_REVISION
        ),
        'plan_fingerprint_stable': bool(
            not missing
            and runs.get(RUN_PRIOR, {}).get('observed_plan_fingerprint')
            == EXPECTED_PLAN_FINGERPRINT
            and runs.get(RUN_LATER, {}).get('observed_plan_fingerprint')
            == EXPECTED_PLAN_FINGERPRINT
        ),
        'prior_row_level_values_retained': bool(
            (runs.get(RUN_PRIOR, {}).get('row_level_evidence') or {}).get(
                'row_level_normalized_values_retained'
            )
        ),
        'later_row_level_values_retained': bool(
            (runs.get(RUN_LATER, {}).get('row_level_evidence') or {}).get(
                'row_level_normalized_values_retained'
            )
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
        'later_value_evidence_status', 'correction_provenance_available',
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
) -> dict:
    """Five independent dimensions. Never collapsed into one vague label."""
    artifacts = artifacts or {}
    code_drift = code_drift or {}
    determinism = determinism or {}
    matrix_summary = matrix_summary or {}
    plan_observation = plan_observation or {}
    checkpoint = checkpoint or {}

    # ── Root condition ──────────────────────────────────────────────────────
    if determinism.get('deterministic_in_process') is False:
        root = ROOT_FINGERPRINT_NONDETERMINISM
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
    if not source_available:
        materiality = MATERIALITY_SOURCE_UNAVAILABLE
    elif not matrix_summary.get('structurally_valid'):
        materiality = MATERIALITY_UNPROVEN
    elif plan_observation.get('action_counts') is None:
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
    if artifacts.get('prior_row_level_values_retained'):
        field_identification = FIELD_ID_IDENTIFIED
    elif not artifacts.get('all_required_present'):
        field_identification = FIELD_ID_UNPROVEN
    elif matrix_summary.get('proven_historical_fields'):
        field_identification = FIELD_ID_IDENTIFIED
    elif code_drift.get('source_revision_affecting_drift'):
        # Drift in a revision-affecting symbol narrows the cause to the code
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

    if realization_symbol_state == DRIFT_UNAVAILABLE:
        answer = CAUSALITY_UNPROVEN
    elif drift:
        answer = CAUSALITY_UNPROVEN_CODE_DRIFT
    elif unresolved is None or prohibited is None:
        answer = CAUSALITY_UNPROVEN
    elif unresolved > 0:
        answer = CAUSALITY_INDEPENDENT_UNRESOLVED
    elif prohibited > 0:
        answer = CAUSALITY_INDEPENDENT_IDENTITY
    else:
        answer = CAUSALITY_SINGLE_CHAIN
    return {
        'answer': answer,
        'unresolved_rows': unresolved,
        'prohibited_identity_actions': prohibited,
        'source_revision_match': later.get('source_revision_match'),
        'all_projected_targets_realized': later.get(
            'all_projected_targets_realized'
        ),
        'realization_definition_verified_at_failed_run_sha': (
            realization_symbol_state == DRIFT_EQUAL
        ),
        'realization_symbol_state': realization_symbol_state,
        'invariant_definition': (
            'all_projected_targets_realized = unresolved_rows == 0 AND '
            'prohibited_identity_actions == 0 AND source_revision_match'
        ),
    }


def operational_consequence(classification) -> dict:
    """Question 12. Informational only. Never an authorization."""
    classification = classification or {}
    materiality = classification.get('current_materiality')
    checkpoint_state = classification.get('checkpoint_state')
    field_id = classification.get('historical_field_identification')

    supported: list[str] = []
    if materiality == MATERIALITY_MATERIAL:
        supported.append(CONSEQUENCE_GAMELOG_REPAIR)
    if checkpoint_state == CHECKPOINT_STALE:
        supported.append(CONSEQUENCE_WORK_ITEM_REVISION_UPDATE)
    if checkpoint_state == CHECKPOINT_MISSING:
        supported.append(CONSEQUENCE_EXACT_GAME_BACKFILL)
    if field_id == FIELD_ID_NOT_RETAINED:
        supported.append(CONSEQUENCE_ARTIFACT_RETENTION_IMPROVEMENT)
    if materiality in (MATERIALITY_EXACT_MATCH, MATERIALITY_NON_MATERIAL):
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
) -> dict:
    """Reduce every observation to exactly one top-level outcome.

    FAILED is reserved for a violation of THIS audit's safety or integrity
    contract. A platform defect discovered by a clean read-only audit is
    information, and information is a successful audit.
    """
    failed = sorted(set(failed_reasons or ()))
    unproven = sorted(set(unproven_reasons or ()))
    classification = classification or {}
    delta = delta or {}

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
