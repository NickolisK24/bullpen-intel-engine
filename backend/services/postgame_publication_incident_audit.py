"""Read-only postgame publication incident audit (run 30873422601).

WHAT HAPPENED
-------------
The scheduled postgame cycle for slate 2026-08-03 (workflow run 30873422601,
branch ``main``, head ``9f9f640799af973f0a39cdafb1db83fba473b10c``) produced a
contradictory picture:

* the game-driven shadow lane completed cleanly;
* legacy postgame ingestion completed its baseball work;
* publication proof still failed;
* game 822867 was mapped ``other`` by the schedule finality authority while the
  appearance ledger counted it as a completed game requiring appearance rows;
* dashboard snapshot 344 stayed pending while 343 kept serving;
* the completeness report counted 60 unresolved final games.

WHAT THIS MODULE IS
-------------------
The evidence contract for a manual, exact-scope, read-only diagnostic that
reconstructs that cycle and answers eight explicit questions about it. It is a
DIAGNOSTIC. It changes nothing, and finding a root cause authorizes nothing.

WHAT THIS MODULE DOES NOT OWN
-----------------------------
Deliberately, so the audit cannot become a second authority that drifts from
the one production actually runs:

* schedule-finality mapping — ``services.game_finality``;
* appearance-ledger membership — ``services.appearance_ledger``;
* game-ingestion completeness — ``services.game_ingestion_completeness``;
* game-level planning and exclusion accounting — ``services.game_ingestion_planner``;
* snapshot publication rules — ``services.dashboard_snapshot``;
* publication proof — ``services.sync_publication_proof``;
* reconciliation — ``services.game_log_reconciliation``.

Each is CALLED, never reimplemented. Where this module names a condition it
names it as a CLASSIFICATION of what those authorities reported, never as a
competing decision.

READ-ONLY, THREE WAYS
---------------------
Inherited unchanged from the no-op qualification candidate audit (PR #605): the
acquire-only public sync advisory lock, a PostgreSQL read-only transaction with
a bounded write probe that must be REFUSED, and before/after content
fingerprints over every table the incident touches.

VERDICT SEMANTICS
-----------------
FAILED outranks UNPROVEN outranks COMPLETE. UNPROVEN is never softened into a
pass: absent evidence is the state most easily mistaken for success. An
exhausted MLB source-call budget is UNPROVEN, never a shortcut to a verdict.
"""

from __future__ import annotations

import re
from datetime import date

from services.noop_qualification_candidate_audit import (  # noqa: F401 - reused contract
    ReadOnlyNotEnforced,
    ReadOnlyProbeViolation,
    changed_tables,
    enforce_read_only,
    fingerprints_match,
    probe_evidence,
    table_fingerprints as _shared_table_fingerprints,
)


SCHEMA_VERSION = '1'
AUDIT_TYPE = 'postgame_publication_incident_audit'

# ── Incident identity (locked; this audit reconstructs exactly one cycle) ────
INCIDENT_RUN_ID = '30873422601'
INCIDENT_HEAD_SHA = '9f9f640799af973f0a39cdafb1db83fba473b10c'
INCIDENT_CYCLE = 'postgame'
INCIDENT_SLATE_DATE = date(2026, 8, 3)
INCIDENT_GAME_PK = 822867
INCIDENT_CANDIDATE_SNAPSHOT_ID = 344
INCIDENT_SERVING_SNAPSHOT_ID = 343
INCIDENT_SYNC_RUN_ID = 596
INCIDENT_REPORTED_PLAYER_MISMATCHES = 9
INCIDENT_REPORTED_UNRESOLVED_FINAL_GAMES = 60

CONFIRMATION = 'AUDIT_POSTGAME_PUBLICATION_INCIDENT_30873422601'

NON_AUTHORIZATION_STATEMENT = (
    'This audit is read-only. It does not authorize backfill, repair, '
    'schedule-status mutation, appearance-row creation, marker reset, '
    'snapshot publication, automated writes, authoritative mode, or any '
    'future production mutation.'
)

# ── Results ─────────────────────────────────────────────────────────────────
RESULT_ROOT_CAUSE_IDENTIFIED = 'COMPLETE_ROOT_CAUSE_IDENTIFIED'
RESULT_NO_PLATFORM_DEFECT_PROVEN = 'COMPLETE_NO_PLATFORM_DEFECT_PROVEN'
RESULT_INCIDENT_NOT_REPRODUCIBLE = 'COMPLETE_INCIDENT_NOT_REPRODUCIBLE'
RESULT_FAILED = 'FAILED'
RESULT_UNPROVEN = 'UNPROVEN'

COMPLETE_RESULTS = frozenset({
    RESULT_ROOT_CAUSE_IDENTIFIED,
    RESULT_NO_PLATFORM_DEFECT_PROVEN,
    RESULT_INCIDENT_NOT_REPRODUCIBLE,
})

EXIT_CODES = {
    RESULT_ROOT_CAUSE_IDENTIFIED: 0,
    RESULT_NO_PLATFORM_DEFECT_PROVEN: 0,
    RESULT_INCIDENT_NOT_REPRODUCIBLE: 0,
    RESULT_FAILED: 1,
    RESULT_UNPROVEN: 2,
}

# ── Evidence artifacts, addressed by EXACT run id and EXACT name ────────────
ARTIFACT_SHADOW = f'game-driven-shadow-{INCIDENT_RUN_ID}'
ARTIFACT_LEDGER_AUDIT = f'appearance-ledger-audit-{INCIDENT_RUN_ID}'
ARTIFACT_SHADOW_HANDOFF = f'game-driven-shadow-handoff-{INCIDENT_RUN_ID}'

REQUIRED_ARTIFACTS = (ARTIFACT_SHADOW, ARTIFACT_LEDGER_AUDIT)
OPTIONAL_ARTIFACTS = (ARTIFACT_SHADOW_HANDOFF,)
EXPECTED_ARTIFACTS = REQUIRED_ARTIFACTS + OPTIONAL_ARTIFACTS

# Files the sync workflow writes into those artifacts.
SHADOW_SYNC_SUMMARY_SUFFIX = '-sync-summary.json'
SHADOW_ACTIVATION_SUMMARY_SUFFIX = '-activation-summary.json'
LEDGER_REPORT_FILENAME = 'ledger_audit_report.txt'

# ── Tables fingerprinted before and after ───────────────────────────────────
FINGERPRINT_TABLES = (
    'scheduled_games',
    'game_logs',
    'pitchers',
    'postgame_processed_games',
    'game_ingestion_work_items',
    'team_game_pitching_splits',
    'completed_game_contexts',
    'dashboard_snapshots',
    'sync_runs',
    'sync_failures',
)

# ── MLB source-call budget ──────────────────────────────────────────────────
# Bounded so a diagnostic can never become a crawl of the upstream source.
# Exhaustion is UNPROVEN, never a shortcut to a verdict.
CALL_KIND_SCHEDULE = 'schedule'
CALL_KIND_EXACT_GAME = 'exact_game'
CALL_KIND_BOXSCORE = 'boxscore'
CALL_KINDS = (CALL_KIND_SCHEDULE, CALL_KIND_EXACT_GAME, CALL_KIND_BOXSCORE)

SOURCE_CALL_BUDGET = {
    CALL_KIND_SCHEDULE: 8,
    CALL_KIND_EXACT_GAME: 10,
    CALL_KIND_BOXSCORE: 10,
}
SOURCE_CALL_TOTAL_BUDGET = 20

# ── Root-cause classifications ──────────────────────────────────────────────
# Twelve named conditions. Precedence runs most-definite first; the reducer
# reports every classification it observed and names the first as primary.
CLASSIFICATION_READ_ONLY_CONTRACT_VIOLATED = 'read_only_contract_violated'
CLASSIFICATION_SCHEDULE_ROW_FINALITY_CONFLICT = 'schedule_row_finality_conflict'
CLASSIFICATION_STORED_SCHEDULE_STATE_DIVERGES_FROM_SOURCE = (
    'stored_schedule_state_diverges_from_source'
)
CLASSIFICATION_FINALITY_AUTHORITY_MAPS_GAME_OUT_OF_SCOPE = (
    'finality_authority_maps_game_out_of_planning_scope'
)
CLASSIFICATION_LEDGER_MEMBERSHIP_DIVERGES_FROM_PLANNER = (
    'ledger_membership_diverges_from_planner_membership'
)
CLASSIFICATION_POSTGAME_MARKER_INCOMPLETE = 'postgame_marker_incomplete'
CLASSIFICATION_POSTGAME_MARKER_MISSING = 'postgame_marker_missing'
CLASSIFICATION_APPEARANCE_ROWS_MISSING_FOR_FINAL_GAME = (
    'appearance_rows_missing_for_final_game'
)
CLASSIFICATION_WORK_ITEM_BACKLOG_UNRESOLVED = 'work_item_backlog_unresolved'
CLASSIFICATION_SNAPSHOT_WITHHELD_BY_APPEARANCE_LEDGER_GATE = (
    'snapshot_withheld_by_appearance_ledger_gate'
)
CLASSIFICATION_SNAPSHOT_WITHHELD_BY_SLATE_COVERAGE = (
    'snapshot_withheld_by_slate_coverage'
)
CLASSIFICATION_PUBLICATION_PROOF_CANDIDATE_NOT_SERVING = (
    'publication_proof_candidate_not_serving'
)

CLASSIFICATION_PRECEDENCE = (
    CLASSIFICATION_READ_ONLY_CONTRACT_VIOLATED,
    CLASSIFICATION_SCHEDULE_ROW_FINALITY_CONFLICT,
    CLASSIFICATION_STORED_SCHEDULE_STATE_DIVERGES_FROM_SOURCE,
    CLASSIFICATION_FINALITY_AUTHORITY_MAPS_GAME_OUT_OF_SCOPE,
    CLASSIFICATION_LEDGER_MEMBERSHIP_DIVERGES_FROM_PLANNER,
    CLASSIFICATION_APPEARANCE_ROWS_MISSING_FOR_FINAL_GAME,
    CLASSIFICATION_POSTGAME_MARKER_MISSING,
    CLASSIFICATION_POSTGAME_MARKER_INCOMPLETE,
    CLASSIFICATION_WORK_ITEM_BACKLOG_UNRESOLVED,
    CLASSIFICATION_SNAPSHOT_WITHHELD_BY_APPEARANCE_LEDGER_GATE,
    CLASSIFICATION_SNAPSHOT_WITHHELD_BY_SLATE_COVERAGE,
    CLASSIFICATION_PUBLICATION_PROOF_CANDIDATE_NOT_SERVING,
)

assert len(CLASSIFICATION_PRECEDENCE) == 12
assert len(set(CLASSIFICATION_PRECEDENCE)) == 12

# A classification that names a platform defect — something the platform did
# wrong — as opposed to one that names correct fail-closed behaviour reacting
# to an upstream or baseball-data condition.
PLATFORM_DEFECT_CLASSIFICATIONS = frozenset({
    CLASSIFICATION_READ_ONLY_CONTRACT_VIOLATED,
    CLASSIFICATION_SCHEDULE_ROW_FINALITY_CONFLICT,
    CLASSIFICATION_STORED_SCHEDULE_STATE_DIVERGES_FROM_SOURCE,
    CLASSIFICATION_FINALITY_AUTHORITY_MAPS_GAME_OUT_OF_SCOPE,
    CLASSIFICATION_LEDGER_MEMBERSHIP_DIVERGES_FROM_PLANNER,
})

# Fail-closed behaviour: correct, explainable withholding. Present in the
# report, but on its own it does not make the incident a platform defect.
FAIL_CLOSED_CLASSIFICATIONS = frozenset({
    CLASSIFICATION_APPEARANCE_ROWS_MISSING_FOR_FINAL_GAME,
    CLASSIFICATION_POSTGAME_MARKER_MISSING,
    CLASSIFICATION_POSTGAME_MARKER_INCOMPLETE,
    CLASSIFICATION_WORK_ITEM_BACKLOG_UNRESOLVED,
    CLASSIFICATION_SNAPSHOT_WITHHELD_BY_APPEARANCE_LEDGER_GATE,
    CLASSIFICATION_SNAPSHOT_WITHHELD_BY_SLATE_COVERAGE,
    CLASSIFICATION_PUBLICATION_PROOF_CANDIDATE_NOT_SERVING,
})

assert not (PLATFORM_DEFECT_CLASSIFICATIONS & FAIL_CLOSED_CLASSIFICATIONS)
assert (
    PLATFORM_DEFECT_CLASSIFICATIONS | FAIL_CLOSED_CLASSIFICATIONS
) == set(CLASSIFICATION_PRECEDENCE)

# ── Failure and unproven reason codes ───────────────────────────────────────
FAILED_READ_ONLY_PROBE_ACCEPTED = 'read_only_probe_accepted_not_refused'
FAILED_DURABLE_WRITE_ATTEMPTED = 'durable_write_attempted'
FAILED_FINGERPRINTS_CHANGED = 'database_content_changed_during_audit'
FAILED_PROBE_COUNT_UNEXPECTED = 'read_only_probe_count_unexpected'
FAILED_PROBE_NOT_BOUNDED = 'read_only_probe_not_bounded_to_zero_rows'
FAILED_PROBE_STATEMENT_CLASS_UNEXPECTED = (
    'read_only_probe_statement_class_unexpected'
)
FAILED_INCIDENT_IDENTITY_MISMATCH = 'incident_identity_mismatch'

UNPROVEN_GUARD_NOT_ACQUIRED = 'sync_read_guard_not_acquired'
UNPROVEN_READ_ONLY_NOT_ENFORCED = 'read_only_transaction_not_enforced'
UNPROVEN_PROBE_EVIDENCE_MISSING = 'read_only_probe_evidence_missing'
UNPROVEN_PROBE_NOT_ATTEMPTED = 'read_only_probe_not_attempted'
UNPROVEN_PROBE_COUNT_UNKNOWN = 'read_only_probe_count_unknown'
UNPROVEN_FINGERPRINTS_UNAVAILABLE = 'table_fingerprints_unavailable'
UNPROVEN_REQUIRED_ARTIFACT_MISSING = 'required_incident_artifact_missing'
UNPROVEN_REQUIRED_ARTIFACT_UNREADABLE = 'required_incident_artifact_unreadable'
UNPROVEN_SOURCE_BUDGET_EXHAUSTED = 'mlb_source_call_budget_exhausted'
UNPROVEN_QUESTION_UNANSWERED = 'incident_question_unanswered'
UNPROVEN_AUDIT_EXECUTION_ERROR = 'audit_execution_error'
UNPROVEN_ARTIFACT_CONSTRUCTION_FAILED = 'artifact_construction_failed'

# Probe evidence this audit requires, identical in shape to PR #605 so the two
# read-only audits cannot drift.
EXPECTED_PROBE_EVIDENCE = {
    'read_only_probe_attempted': True,
    'read_only_probe_count': 1,
    'read_only_probe_statement_class': 'UPDATE',
    'read_only_probe_bounded_to_zero_rows': True,
    'read_only_probe_refused': True,
    'durable_write_attempts': 0,
}
PROBE_EVIDENCE_FIELDS = tuple(EXPECTED_PROBE_EVIDENCE)

# ── The eight questions ─────────────────────────────────────────────────────
QUESTION_OFFICIAL_STATUS = 'q1_official_status_of_game'
QUESTION_STORED_SCHEDULE_STATE = 'q2_stored_schedule_state'
QUESTION_PREFLIGHT_PRODUCED_OTHER = 'q3_why_preflight_produced_other'
QUESTION_LEDGER_COUNTED_COMPLETED = 'q4_why_ledger_counted_game_completed'
QUESTION_EXACT_BASEBALL_STATE = 'q5_exact_baseball_state'
QUESTION_PLAYER_MISMATCH_ATTRIBUTION = 'q6_player_mismatch_attribution'
QUESTION_UNRESOLVED_GAME_CLASSIFICATION = 'q7_unresolved_final_game_classification'
QUESTION_SNAPSHOT_GATE = 'q8_snapshot_and_sync_run_gate'

QUESTION_IDS = (
    QUESTION_OFFICIAL_STATUS,
    QUESTION_STORED_SCHEDULE_STATE,
    QUESTION_PREFLIGHT_PRODUCED_OTHER,
    QUESTION_LEDGER_COUNTED_COMPLETED,
    QUESTION_EXACT_BASEBALL_STATE,
    QUESTION_PLAYER_MISMATCH_ATTRIBUTION,
    QUESTION_UNRESOLVED_GAME_CLASSIFICATION,
    QUESTION_SNAPSHOT_GATE,
)

QUESTION_TEXT = {
    QUESTION_OFFICIAL_STATUS: (
        f'What is the official MLB status of game {INCIDENT_GAME_PK}?'
    ),
    QUESTION_STORED_SCHEDULE_STATE: (
        f'What schedule state does the database store for game '
        f'{INCIDENT_GAME_PK}?'
    ),
    QUESTION_PREFLIGHT_PRODUCED_OTHER: (
        'Why did the schedule finality preflight map the game to "other"?'
    ),
    QUESTION_LEDGER_COUNTED_COMPLETED: (
        'Why did the appearance ledger count the game as a completed game '
        'requiring appearance rows?'
    ),
    QUESTION_EXACT_BASEBALL_STATE: (
        'What is the exact stored baseball state for the game?'
    ),
    QUESTION_PLAYER_MISMATCH_ATTRIBUTION: (
        'What individually explains each reported player appearance mismatch?'
    ),
    QUESTION_UNRESOLVED_GAME_CLASSIFICATION: (
        'How does each unresolved final game counted by the completeness '
        'report classify?'
    ),
    QUESTION_SNAPSHOT_GATE: (
        f'Why did dashboard snapshot {INCIDENT_CANDIDATE_SNAPSHOT_ID} stay '
        f'pending while {INCIDENT_SERVING_SNAPSHOT_ID} kept serving, and what '
        f'did sync run {INCIDENT_SYNC_RUN_ID} record?'
    ),
}

# ── Per-mismatch and per-game attribution buckets ───────────────────────────
MISMATCH_NO_APPEARANCE_ROW = 'no_stored_appearance_row_for_game'
MISMATCH_PITCHER_IDENTITY_UNTRACKED = 'pitcher_identity_not_tracked'
MISMATCH_APPEARANCE_ROW_NOW_PRESENT = 'appearance_row_present_at_audit_time'
MISMATCH_GAME_NOT_IN_LEDGER_WINDOW = 'game_outside_current_ledger_window'
MISMATCH_UNATTRIBUTED = 'unattributed'

MISMATCH_CLASSIFICATIONS = (
    MISMATCH_NO_APPEARANCE_ROW,
    MISMATCH_PITCHER_IDENTITY_UNTRACKED,
    MISMATCH_APPEARANCE_ROW_NOW_PRESENT,
    MISMATCH_GAME_NOT_IN_LEDGER_WINDOW,
    MISMATCH_UNATTRIBUTED,
)

UNRESOLVED_PLANNED_NEVER_ATTEMPTED = 'planned_critical_never_attempted'
UNRESOLVED_IN_PROGRESS = 'work_item_in_progress'
UNRESOLVED_RETRYABLE_FAILURE = 'work_item_retryable_failure'
UNRESOLVED_TERMINAL_FAILURE = 'work_item_terminal_failure'
UNRESOLVED_CORRECTION_CONFLICT = 'work_item_correction_conflict'
UNRESOLVED_SCHEDULE_AUTHORITY_MISSING = 'schedule_authority_missing'
UNRESOLVED_UNATTRIBUTED = 'unattributed'

UNRESOLVED_CLASSIFICATIONS = (
    UNRESOLVED_PLANNED_NEVER_ATTEMPTED,
    UNRESOLVED_IN_PROGRESS,
    UNRESOLVED_RETRYABLE_FAILURE,
    UNRESOLVED_TERMINAL_FAILURE,
    UNRESOLVED_CORRECTION_CONFLICT,
    UNRESOLVED_SCHEDULE_AUTHORITY_MISSING,
    UNRESOLVED_UNATTRIBUTED,
)

MAX_REPORTED_REASON_CODES = 12
MAX_REPORTED_UNRESOLVED_GAMES = 200

_DIGITS = re.compile(r'-?\d+')


class AuditInputError(ValueError):
    """A bounded input could not be accepted. Carries a safe reason only."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class SourceCallBudgetExhausted(RuntimeError):
    """The bounded MLB source-call budget was reached. Never a verdict."""


class SourceCallBudget:
    """Bounded accounting for upstream MLB calls.

    Every call is counted BEFORE it is issued, so an exhausted budget refuses
    rather than overspending. Exhaustion is an UNPROVEN condition: the audit
    reports what it could not observe instead of guessing.
    """

    def __init__(self, *, per_kind=None, total=None):
        self._limits = dict(per_kind or SOURCE_CALL_BUDGET)
        self._total_limit = int(
            SOURCE_CALL_TOTAL_BUDGET if total is None else total
        )
        self._counts = {kind: 0 for kind in CALL_KINDS}
        self._refusals = {kind: 0 for kind in CALL_KINDS}
        self._errors = {kind: 0 for kind in CALL_KINDS}

    @property
    def total_spent(self) -> int:
        return sum(self._counts.values())

    @property
    def exhausted(self) -> bool:
        if self.total_spent >= self._total_limit:
            return True
        return any(
            self._counts[kind] >= self._limits.get(kind, 0)
            for kind in CALL_KINDS
        )

    def remaining(self, kind) -> int:
        per_kind = max(self._limits.get(kind, 0) - self._counts.get(kind, 0), 0)
        overall = max(self._total_limit - self.total_spent, 0)
        return min(per_kind, overall)

    def reserve(self, kind) -> bool:
        """Reserve one call of ``kind``. False when the budget refuses it."""
        if kind not in CALL_KINDS:
            raise AuditInputError('unknown_source_call_kind')
        if self.remaining(kind) <= 0:
            self._refusals[kind] += 1
            return False
        self._counts[kind] += 1
        return True

    def record_error(self, kind) -> None:
        if kind in CALL_KINDS:
            self._errors[kind] += 1

    def state(self) -> dict:
        return {
            'limits': dict(self._limits),
            'total_limit': self._total_limit,
            'calls_spent': dict(self._counts),
            'total_spent': self.total_spent,
            'calls_refused_by_budget': dict(self._refusals),
            'total_refused_by_budget': sum(self._refusals.values()),
            'source_errors': dict(self._errors),
            'total_source_errors': sum(self._errors.values()),
            'budget_exhausted': self.exhausted,
            'budget_refused_a_call': sum(self._refusals.values()) > 0,
        }


# ── Incident identity ───────────────────────────────────────────────────────

def incident_identity() -> dict:
    """The locked incident this audit reconstructs."""
    return {
        'workflow_run_id': INCIDENT_RUN_ID,
        'head_sha': INCIDENT_HEAD_SHA,
        'cycle': INCIDENT_CYCLE,
        'slate_date': INCIDENT_SLATE_DATE.isoformat(),
        'game_pk': INCIDENT_GAME_PK,
        'candidate_snapshot_id': INCIDENT_CANDIDATE_SNAPSHOT_ID,
        'serving_snapshot_id': INCIDENT_SERVING_SNAPSHOT_ID,
        'sync_run_id': INCIDENT_SYNC_RUN_ID,
        'reported_player_mismatches': INCIDENT_REPORTED_PLAYER_MISMATCHES,
        'reported_unresolved_final_games': (
            INCIDENT_REPORTED_UNRESOLVED_FINAL_GAMES
        ),
    }


def validate_incident_scope(*, run_id, cycle, slate_date) -> list[str]:
    """Refuse any scope other than the one incident. Exact-scope, always."""
    failures: list[str] = []
    if str(run_id or '').strip() != INCIDENT_RUN_ID:
        failures.append('incident_run_id_mismatch')
    if str(cycle or '').strip().lower() != INCIDENT_CYCLE:
        failures.append('incident_cycle_mismatch')
    resolved = _as_date(slate_date)
    if resolved != INCIDENT_SLATE_DATE:
        failures.append('incident_slate_date_mismatch')
    return failures


# ── Evidence artifact ingestion ─────────────────────────────────────────────

def artifact_expectations() -> dict:
    return {
        'required': list(REQUIRED_ARTIFACTS),
        'optional': list(OPTIONAL_ARTIFACTS),
        'run_id': INCIDENT_RUN_ID,
    }


def ingest_incident_artifacts(root) -> dict:
    """Discover the incident artifacts downloaded under ``root``.

    One directory per artifact name, exactly as ``actions/download-artifact``
    lays them out. Presence, readability, and parsed content are separate
    facts; a missing OPTIONAL artifact is reported, never inferred away.
    """
    from pathlib import Path

    base = Path(root)
    artifacts: dict[str, dict] = {}
    for name in EXPECTED_ARTIFACTS:
        required = name in REQUIRED_ARTIFACTS
        directory = base / name
        entry = {
            'artifact_name': name,
            'required': required,
            'present': directory.is_dir(),
            'files': [],
            'readable': False,
            'parse_error': None,
        }
        if entry['present']:
            try:
                entry['files'] = sorted(
                    child.name for child in directory.iterdir()
                    if child.is_file()
                )
                entry['readable'] = True
            except OSError:
                entry['readable'] = False
                entry['parse_error'] = 'artifact_directory_unreadable'
        artifacts[name] = entry

    shadow = artifacts[ARTIFACT_SHADOW]
    if shadow['present'] and shadow['readable']:
        shadow.update(_read_shadow_artifact(base / ARTIFACT_SHADOW))

    ledger = artifacts[ARTIFACT_LEDGER_AUDIT]
    if ledger['present'] and ledger['readable']:
        ledger.update(_read_ledger_artifact(base / ARTIFACT_LEDGER_AUDIT))

    missing_required = sorted(
        name for name in REQUIRED_ARTIFACTS
        if not artifacts[name]['present']
    )
    unreadable_required = sorted(
        name for name in REQUIRED_ARTIFACTS
        if artifacts[name]['present'] and artifacts[name].get('parse_error')
    )
    missing_optional = sorted(
        name for name in OPTIONAL_ARTIFACTS
        if not artifacts[name]['present']
    )
    return {
        'expectations': artifact_expectations(),
        'artifacts': artifacts,
        'missing_required': missing_required,
        'unreadable_required': unreadable_required,
        # Reported, never inferred away: the handoff artifact is diagnostic
        # transport and its absence changes no verdict, but a reader must be
        # able to see that it was absent.
        'missing_optional': missing_optional,
        'all_required_present': not missing_required and not unreadable_required,
    }


def _read_shadow_artifact(directory) -> dict:
    """Read the postgame sync summary and shadow activation summary."""
    import json

    result: dict = {
        'sync_summary_filename': None,
        'sync_summary': None,
        'activation_summary_filename': None,
        'activation_summary': None,
    }
    sync_files = sorted(
        path for path in directory.iterdir()
        if path.is_file() and path.name.endswith(SHADOW_SYNC_SUMMARY_SUFFIX)
    )
    activation_files = sorted(
        path for path in directory.iterdir()
        if path.is_file()
        and path.name.endswith(SHADOW_ACTIVATION_SUMMARY_SUFFIX)
    )
    try:
        if sync_files:
            result['sync_summary_filename'] = sync_files[0].name
            result['sync_summary'] = json.loads(
                sync_files[0].read_text(encoding='utf-8')
            )
        if activation_files:
            result['activation_summary_filename'] = activation_files[0].name
            result['activation_summary'] = json.loads(
                activation_files[0].read_text(encoding='utf-8')
            )
    except (OSError, ValueError):
        # Never surface the underlying message: it can carry a filesystem path.
        result['parse_error'] = 'shadow_artifact_unparseable'
        return result
    if result['sync_summary'] is None:
        result['parse_error'] = 'shadow_sync_summary_missing'
    return result


def _read_ledger_artifact(directory) -> dict:
    result: dict = {'ledger_report_filename': None, 'ledger_report': None}
    report = directory / LEDGER_REPORT_FILENAME
    if not report.is_file():
        result['parse_error'] = 'ledger_report_missing'
        return result
    try:
        text = report.read_text(encoding='utf-8', errors='replace')
    except OSError:
        result['parse_error'] = 'ledger_report_unreadable'
        return result
    result['ledger_report_filename'] = report.name
    result['ledger_report'] = parse_ledger_audit_report(text)
    if result['ledger_report'].get('parsed') is not True:
        result['parse_error'] = 'ledger_report_unparseable'
    return result


# ── Ledger audit report parsing ─────────────────────────────────────────────
# The production report is the rendered text written by
# ``backend/scripts/appearance_ledger_audit.py``. Its labels are stable, so it
# is parsed by label rather than by position.

_LEDGER_LABELS = {
    'expected_games': 'Completed games expected:',
    'represented_games': 'Completed games represented:',
    'expected_appearances': 'Expected reliever appearances:',
    'stored_appearances': 'Stored appearances:',
    'latest_appearance_mismatches': 'Latest appearance mismatches:',
    'players_affected': 'Players affected:',
}

_PLAYER_LINE = re.compile(
    r'^\s*-\s+(?P<name>.*?)\s+\((?P<player_id>\d+),\s*'
    r'last stored:\s*(?P<last_stored>[^)]*)\)\s*$'
)
_WINDOW_LINE = re.compile(
    r'^Window:\s*(?P<start>\d{4}-\d{2}-\d{2})\s*\.\.\s*'
    r'(?P<end>\d{4}-\d{2}-\d{2})'
)
_GAME_PK_LIST_LABELS = {
    'missing_game_pks': 'Missing game_pks:',
    'count_deficit_game_pks': 'Count-deficit game_pks:',
    'incomplete_marker_game_pks': 'Incomplete-marker game_pks:',
}


def parse_ledger_audit_report(text) -> dict:
    """Parse the rendered appearance-ledger audit report.

    Returns ``parsed=False`` when the document does not look like the report;
    an unparseable artifact is UNPROVEN, never an empty success.
    """
    raw = str(text or '')
    lines = raw.splitlines()
    parsed: dict = {
        'parsed': False,
        'window_start': None,
        'window_end': None,
        'publish_eligible': None,
        'reasons': [],
        'player_mismatches': [],
        'unfetchable_game_count': 0,
    }
    for key in _LEDGER_LABELS:
        parsed[key] = None
    for key in _GAME_PK_LIST_LABELS:
        parsed[key] = []

    if 'APPEARANCE LEDGER AUDIT' not in raw:
        return parsed

    for index, line in enumerate(lines):
        stripped = line.strip()

        window = _WINDOW_LINE.match(stripped)
        if window:
            parsed['window_start'] = window.group('start')
            parsed['window_end'] = window.group('end')
            continue

        matched_label = False
        for key, label in _LEDGER_LABELS.items():
            if stripped.startswith(label):
                parsed[key] = _first_int(stripped[len(label):])
                matched_label = True
                break
        if matched_label:
            continue

        for key, label in _GAME_PK_LIST_LABELS.items():
            if stripped.startswith(label):
                parsed[key] = _game_pk_list(stripped[len(label):])
                matched_label = True
                break
        if matched_label:
            continue

        if stripped.startswith('! boxscore unavailable for game'):
            parsed['unfetchable_game_count'] += 1
            continue

        if stripped.startswith('Reasons:'):
            parsed['reasons'] = [
                value.strip()
                for value in stripped[len('Reasons:'):].split(',')
                if value.strip()
            ]
            continue

        if stripped == 'Publish eligible:':
            parsed['publish_eligible'] = _publish_verdict(lines[index + 1:])
            continue

        player = _PLAYER_LINE.match(line)
        if player:
            last_stored = player.group('last_stored').strip()
            # The player NAME is matched so the line can be recognised, and is
            # then deliberately dropped. Identity travels as the MLB player id;
            # the ledger artifact itself remains the place where names are
            # rendered for a human reader.
            parsed['player_mismatches'].append({
                'player_id': int(player.group('player_id')),
                'latest_stored_appearance': (
                    None if last_stored.lower() == 'never' else last_stored
                ),
            })

    parsed['parsed'] = parsed['expected_games'] is not None
    return parsed


def _publish_verdict(following_lines) -> bool | None:
    for line in following_lines:
        value = line.strip().upper()
        if value == 'YES':
            return True
        if value == 'NO':
            return False
        if value:
            return None
    return None


def _first_int(fragment):
    match = _DIGITS.search(str(fragment or ''))
    return int(match.group()) if match else None


def _game_pk_list(fragment):
    text = str(fragment or '').strip()
    if not text or text.lower() == 'none':
        return []
    return sorted({
        int(value) for value in _DIGITS.findall(text)
    })


# ── Probe-evidence validation (shape shared with PR #605) ───────────────────

def evaluate_probe_evidence(proof) -> dict:
    """Validate every probe field that is PRESENT; never invent a failure.

    A missing field is UNPROVEN. A present field that contradicts the contract
    is FAILED. Absence must never mask a violation, and it must never manufacture
    one either — so there is no early return: every present field is checked.
    """
    proof = proof if isinstance(proof, dict) else {}
    failed: list[str] = []
    unproven: list[str] = []

    missing = [
        field for field in PROBE_EVIDENCE_FIELDS if field not in proof
    ]
    if missing:
        unproven.append(UNPROVEN_PROBE_EVIDENCE_MISSING)

    if 'read_only_probe_attempted' in proof:
        if proof['read_only_probe_attempted'] is not True:
            unproven.append(UNPROVEN_PROBE_NOT_ATTEMPTED)

    if 'read_only_probe_count' in proof:
        count = proof['read_only_probe_count']
        if not isinstance(count, int) or isinstance(count, bool):
            unproven.append(UNPROVEN_PROBE_COUNT_UNKNOWN)
        elif count != EXPECTED_PROBE_EVIDENCE['read_only_probe_count']:
            failed.append(FAILED_PROBE_COUNT_UNEXPECTED)

    if 'read_only_probe_statement_class' in proof:
        if (
            proof['read_only_probe_statement_class']
            != EXPECTED_PROBE_EVIDENCE['read_only_probe_statement_class']
        ):
            failed.append(FAILED_PROBE_STATEMENT_CLASS_UNEXPECTED)

    if 'read_only_probe_bounded_to_zero_rows' in proof:
        if proof['read_only_probe_bounded_to_zero_rows'] is not True:
            failed.append(FAILED_PROBE_NOT_BOUNDED)

    if 'read_only_probe_refused' in proof:
        if proof['read_only_probe_refused'] is not True:
            failed.append(FAILED_READ_ONLY_PROBE_ACCEPTED)

    if 'durable_write_attempts' in proof:
        attempts = proof['durable_write_attempts']
        if not isinstance(attempts, int) or isinstance(attempts, bool):
            unproven.append(UNPROVEN_PROBE_COUNT_UNKNOWN)
        elif attempts != 0:
            failed.append(FAILED_DURABLE_WRITE_ATTEMPTED)

    return {
        'failed_reasons': sorted(set(failed)),
        'unproven_reasons': sorted(set(unproven)),
        'missing_fields': sorted(missing),
    }


def table_fingerprints(session, tables=FINGERPRINT_TABLES) -> dict | None:
    """Content fingerprints over the tables this incident touches.

    Thin binding over the shared helper so both read-only audits compute
    fingerprints exactly one way. Returns ``None`` when they cannot be
    computed, which the reducer turns into UNPROVEN.
    """
    return _shared_table_fingerprints(session, tables=tables)


# ── Verdict reducer ─────────────────────────────────────────────────────────

def decide(
    *,
    questions,
    classifications,
    read_only_proof,
    artifact_ingestion,
    budget_state,
    identity_failures=(),
    extra_failed=(),
    extra_unproven=(),
) -> dict:
    """Reduce observations into one verdict.

    Precedence is absolute: FAILED outranks UNPROVEN outranks COMPLETE. A
    COMPLETE result requires that all eight questions were answered, every
    required artifact was ingested, the read-only contract held, and the source
    budget never refused a call the audit needed.
    """
    questions = list(questions or [])
    observed = _ordered_classifications(classifications)
    proof = read_only_proof if isinstance(read_only_proof, dict) else {}
    ingestion = artifact_ingestion if isinstance(artifact_ingestion, dict) else {}
    budget = budget_state if isinstance(budget_state, dict) else {}

    failed = list(extra_failed or [])
    unproven = list(extra_unproven or [])

    if identity_failures:
        failed.append(FAILED_INCIDENT_IDENTITY_MISMATCH)
        failed.extend(identity_failures)

    # Read-only contract.
    if proof.get('advisory_guard_acquired') is not True:
        unproven.append(UNPROVEN_GUARD_NOT_ACQUIRED)
    if proof.get('transaction_read_only_enabled') is not True:
        unproven.append(UNPROVEN_READ_ONLY_NOT_ENFORCED)

    probe = evaluate_probe_evidence(proof)
    failed.extend(probe['failed_reasons'])
    unproven.extend(probe['unproven_reasons'])

    match = proof.get('fingerprints_match')
    if match is False:
        failed.append(FAILED_FINGERPRINTS_CHANGED)
    elif match is not True:
        unproven.append(UNPROVEN_FINGERPRINTS_UNAVAILABLE)

    # Evidence artifacts.
    if ingestion.get('missing_required'):
        unproven.append(UNPROVEN_REQUIRED_ARTIFACT_MISSING)
    if ingestion.get('unreadable_required'):
        unproven.append(UNPROVEN_REQUIRED_ARTIFACT_UNREADABLE)

    # Source-call budget: an exhausted or refusing budget is UNPROVEN.
    if budget.get('budget_exhausted') or budget.get('budget_refused_a_call'):
        unproven.append(UNPROVEN_SOURCE_BUDGET_EXHAUSTED)

    # Questions.
    answered_ids = {
        question.get('question_id') for question in questions
        if question.get('answered') is True
    }
    unanswered = [
        question_id for question_id in QUESTION_IDS
        if question_id not in answered_ids
    ]
    if unanswered:
        unproven.append(UNPROVEN_QUESTION_UNANSWERED)

    if FAILED_READ_ONLY_PROBE_ACCEPTED in failed or (
        FAILED_FINGERPRINTS_CHANGED in failed
    ):
        observed = _ordered_classifications(
            list(observed) + [CLASSIFICATION_READ_ONLY_CONTRACT_VIOLATED]
        )

    failed = sorted(set(value for value in failed if value))
    unproven = sorted(set(value for value in unproven if value))

    platform_defects = [
        value for value in observed
        if value in PLATFORM_DEFECT_CLASSIFICATIONS
    ]

    if failed:
        result = RESULT_FAILED
    elif unproven:
        result = RESULT_UNPROVEN
    elif platform_defects:
        result = RESULT_ROOT_CAUSE_IDENTIFIED
    elif observed:
        result = RESULT_NO_PLATFORM_DEFECT_PROVEN
    else:
        result = RESULT_INCIDENT_NOT_REPRODUCIBLE

    return {
        'result': result,
        'exit_code': EXIT_CODES[result],
        'failed_reasons': failed[:MAX_REPORTED_REASON_CODES],
        'unproven_reasons': unproven[:MAX_REPORTED_REASON_CODES],
        'unanswered_question_ids': unanswered,
        'questions_answered': len(QUESTION_IDS) - len(unanswered),
        'questions_total': len(QUESTION_IDS),
        'classifications': list(observed),
        'primary_classification': observed[0] if observed else None,
        'platform_defect_classifications': platform_defects,
        'platform_defect_proven': bool(platform_defects) and not failed
        and not unproven,
        'non_authorization_statement': NON_AUTHORIZATION_STATEMENT,
    }


def _ordered_classifications(values) -> list[str]:
    seen = {value for value in (values or []) if value}
    unknown = sorted(seen - set(CLASSIFICATION_PRECEDENCE))
    ordered = [
        value for value in CLASSIFICATION_PRECEDENCE if value in seen
    ]
    return ordered + unknown


def explanation(decision) -> str:
    result = (decision or {}).get('result')
    if result == RESULT_ROOT_CAUSE_IDENTIFIED:
        return (
            'The audit completed read-only, answered every incident question, '
            'and identified at least one platform defect that explains the '
            'failed publication cycle. Naming a cause is not a repair and '
            'authorizes no mutation.'
        )
    if result == RESULT_NO_PLATFORM_DEFECT_PROVEN:
        return (
            'The audit completed read-only and answered every incident '
            'question. Every observed condition is correct fail-closed '
            'behaviour reacting to an upstream or baseball-data state; no '
            'platform defect was proven. That is a completed audit, not a '
            'clean bill of health for the underlying data.'
        )
    if result == RESULT_INCIDENT_NOT_REPRODUCIBLE:
        return (
            'The audit completed read-only and answered every incident '
            'question, and none of the incident conditions are present in '
            'current state. The failed cycle is not reproducible from the '
            'database as it stands now; the run artifacts remain the only '
            'record of it.'
        )
    if result == RESULT_FAILED:
        return (
            'A contract violation was observed. This is a definite negative '
            'result and is never softened by anything else the audit found.'
        )
    return (
        'Trustworthy evidence could not be completed, so the incident is '
        'unproven. UNPROVEN is not a pass: absent evidence is the state most '
        'easily mistaken for success.'
    )


# ── Small helpers ───────────────────────────────────────────────────────────

def _as_date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return None
