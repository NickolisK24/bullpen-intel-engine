"""Read-only postgame publication incident audit (run 30873422601).

WHAT HAPPENED
-------------
The scheduled postgame cycle for slate 2026-08-03 (workflow run 30873422601,
branch ``main``, head ``9f9f640799af973f0a39cdafb1db83fba473b10c``) failed while
its parts reported success:

* the game-driven shadow lane completed cleanly (35/35/35, 295 rows, all
  unchanged, zero projected mutations);
* legacy postgame ingestion completed its baseball work (35 completed games, 5
  newly processed, 40 new GameLog rows, zero failures);
* publication proof still failed;
* game 822867 was mapped ``other`` by the schedule finality preflight while the
  appearance ledger counted it as a completed game requiring appearance rows;
* dashboard snapshot 344 stayed pending while 343 kept serving;
* the completeness report counted 60 unresolved final games.

THE SEPARATION THIS MODULE PRESERVES
------------------------------------
This is NOT a game-driven reconciliation failure. The correct reading is:

* game-driven shadow execution:                    PASS
* legacy postgame baseball ingestion:              completed successfully
* appearance-ledger publication qualification:     FAILED
* dashboard publication qualification:             FAILED
* complete postgame activation cycle:              FAILED

A perfect shadow reconciliation does not prove the publication system correct,
and a publication failure does not invalidate the reconciliation engine.

FOUR EVIDENCE SOURCES, NEVER BLENDED
------------------------------------
1. ``incident_artifact``    — immutable facts from run 30873422601;
2. ``current_database``     — live production state at audit time;
3. ``official_mlb_source``  — the canonical MLB client's current answer;
4. ``derived_inference``    — conclusions drawn by comparing the first three.

Every recorded fact carries its source. A current-state observation may never be
presented as incident evidence, and an inference may never be presented as an
observation.

WHAT THIS MODULE DOES NOT OWN
-----------------------------
Deliberately, so the audit cannot become a second authority that drifts from the
one production actually runs:

* schedule-finality mapping    — ``services.game_finality``
* appearance-ledger membership — ``services.appearance_ledger``
* game-ingestion completeness  — ``services.game_ingestion_completeness``
* game-level planning          — ``services.game_ingestion_planner``
* snapshot publication rules   — ``services.dashboard_snapshot``
* publication proof            — ``services.sync_publication_proof``
* reconciliation               — ``services.game_log_reconciliation``

Each is CALLED, never reimplemented.

VERDICT SEMANTICS
-----------------
``FAILED`` is reserved for a violation of the AUDIT'S OWN safety contract —
production content changed, the write probe was accepted, the artifact carries
prohibited material, or the invocation was unauthorized. A platform defect the
audit *discovers* is a successful audit: ``COMPLETE_ROOT_CAUSE_IDENTIFIED``.

FAILED outranks UNPROVEN outranks every COMPLETE result. UNPROVEN is never
softened: absent evidence is the state most easily mistaken for success.
"""

from __future__ import annotations

import re
from datetime import date

from services.noop_qualification_candidate_audit import (  # noqa: F401 - shared contract
    ReadOnlyNotEnforced,
    ReadOnlyProbeViolation,
    enforce_read_only,
    probe_evidence,
)


SCHEMA_VERSION = '2'
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
INCIDENT_RUNNER_EXIT_CODE = 1

CONFIRMATION = 'AUDIT_POSTGAME_PUBLICATION_INCIDENT_30873422601'

NON_AUTHORIZATION_STATEMENT = (
    'This audit is read-only. It does not authorize backfill, repair, '
    'schedule-status mutation, appearance-row creation, marker reset, '
    'snapshot publication, automated writes, authoritative mode, or any '
    'future production mutation.'
)

# ── Evidence source kinds ───────────────────────────────────────────────────
SOURCE_INCIDENT = 'incident_artifact'
SOURCE_CURRENT_DB = 'current_database'
SOURCE_OFFICIAL = 'official_mlb_source'
SOURCE_INFERENCE = 'derived_inference'

EVIDENCE_SOURCES = (
    SOURCE_INCIDENT, SOURCE_CURRENT_DB, SOURCE_OFFICIAL, SOURCE_INFERENCE,
)

# ── Correct incident interpretation (preserved, never re-litigated) ─────────
OUTCOME_PASS = 'PASS'
OUTCOME_COMPLETED = 'COMPLETED_SUCCESSFULLY'
OUTCOME_FAILED = 'FAILED'

INCIDENT_INTERPRETATION = {
    'game_driven_shadow_execution': OUTCOME_PASS,
    'legacy_postgame_baseball_ingestion': OUTCOME_COMPLETED,
    'appearance_ledger_publication_qualification': OUTCOME_FAILED,
    'dashboard_publication_qualification': OUTCOME_FAILED,
    'complete_postgame_activation_cycle': OUTCOME_FAILED,
}

INTERPRETATION_NOTE = (
    'A perfect shadow reconciliation result does not prove the publication '
    'system is correct, and a publication failure does not invalidate the '
    'game-driven reconciliation engine. This incident is a publication '
    'qualification failure, not a reconciliation failure.'
)

# ── Immutable incident evidence (from run 30873422601) ──────────────────────
INCIDENT_SHADOW_LANE = {
    'games_planned': 35,
    'games_fetched': 35,
    'games_completed': 35,
    'games_failed': 0,
    'rows_expected': 295,
    'rows_unchanged': 295,
    'projected_inserts': 0,
    'projected_updates': 0,
    'projected_blocked_rows': 0,
    'canonical_outs_corrections': 0,
    'statistical_corrections': 0,
    'identity_mutations': 0,
    'appearance_team_mutations': 0,
    'dead_letters_created': 0,
    'baseball_rows_written': 0,
    'writes_enabled': False,
    'publication_authoritative': False,
    'exact_execution_scope': True,
    'budget_stop': False,
    'elapsed_seconds': 13.794,
    'allocated_budget_seconds': 150.0,
    'remaining_headroom_seconds': 136.206,
    'shadow_status': 'complete',
}

INCIDENT_LEGACY_POSTGAME = {
    'status': 'success',
    'completed_games_found': 35,
    'already_processed': 30,
    'newly_processed': 5,
    'skipped': 0,
    'failed': 0,
    'game_log_rows_added': 40,
    'game_log_rows_corrected': 0,
    'completed_game_contexts_upserted': 10,
    'progressive_team_publication_attempts': 10,
    'progressive_team_publication_generated': 10,
    'progressive_team_publication_failed': 0,
    'intelligence_snapshot_status': 'ok',
}

INCIDENT_NEWLY_PROCESSED_GAMES = (823431, 823520, 823757, 824160, 824647)

# The preflight rechecked eight games for 2026-08-03.
INCIDENT_PREFLIGHT_STATUS_STATES = {
    822867: 'other',
    823431: 'final',
    823520: 'final',
    823757: 'final',
    824160: 'final',
    824324: 'other',
    824647: 'final',
    825095: 'other',
}

INCIDENT_LEDGER = {
    'window_start': '2026-07-25',
    'window_end': '2026-08-03',
    'completed_games_expected': 133,
    'completed_games_represented': 132,
    'expected_appearances': 1110,
    'stored_appearances': 1110,
    'latest_appearance_mismatches': 9,
    'players_affected': 9,
    'missing_game_pks': (822867,),
    'date_with_hole': '2026-08-03',
    'date_with_hole_represented': 5,
    'date_with_hole_expected': 6,
    'publish_eligible': False,
    'reasons': ('final_games_without_appearance_rows',),
}

# The nine mismatched players. Identity travels as the MLBAM id; the name is
# retained because it is already public in the incident's own ledger artifact.
INCIDENT_PLAYER_MISMATCHES = (
    {'player_id': 687239, 'name': 'Ben Peoples',
     'last_stored_appearance': '2026-08-02'},
    {'player_id': 615698, 'name': 'Cal Quantrill',
     'last_stored_appearance': '2026-07-28'},
    {'player_id': 676775, 'name': 'Keaton Winn',
     'last_stored_appearance': '2026-08-01'},
    {'player_id': 657277, 'name': 'Logan Webb',
     'last_stored_appearance': '2026-07-29'},
    {'player_id': 663884, 'name': 'Nolan Kingham',
     'last_stored_appearance': None},
    {'player_id': 682608, 'name': 'Peyton Gray',
     'last_stored_appearance': '2026-08-01'},
    {'player_id': 665665, 'name': 'Reiver Sanmartin',
     'last_stored_appearance': '2026-06-13'},
    {'player_id': 656529, 'name': 'Sam Hentges',
     'last_stored_appearance': '2026-08-02'},
    {'player_id': 663941, 'name': 'Tristan Beck',
     'last_stored_appearance': '2026-07-25'},
)

INCIDENT_PLAYER_IDS = tuple(
    entry['player_id'] for entry in INCIDENT_PLAYER_MISMATCHES
)

INCIDENT_SNAPSHOT_CANDIDATE = {
    'id': 344,
    'status': 'pending',
    'is_published': False,
    'published_at': None,
    'data_through': '2026-08-03',
    'availability_reference_date': '2026-08-04',
    'sync_run_id': 596,
}

INCIDENT_SNAPSHOT_SERVED = {
    'id': 343,
    'remained_public': True,
    'data_through': '2026-08-02',
}

# The completeness proof's own reason code, used to ask whether the
# unresolved-final-game signal actually reached the publication gate.
REASON_UNRESOLVED_FINAL_GAMES_CODE = 'unresolved_final_games'

INCIDENT_PUBLICATION_REASON_CODES = (
    'candidate_snapshot_not_ready',
    'candidate_snapshot_not_published',
    'candidate_snapshot_published_at_missing',
    'dashboard_snapshot_slate_coverage_incomplete',
    'candidate_not_selected_for_serving',
)

INCIDENT_COMPLETENESS = {
    'horizon_days': 7,
    'expected_final_games': 102,
    'completed_final_games': 42,
    'unresolved_final_games': 60,
    'critical_appearance_rows_expected': 377,
    'critical_appearance_rows_reconciled': 377,
    'finality_conflicts': 0,
    'schedule_authority_missing': 0,
    'terminal_failure_games': 0,
    'publication_complete': False,
    'decision_reasons': ('unresolved_final_games',),
}

# The global dead-letter backlog is governed at 1,389 and is NOT re-derived
# here. The audit may truthfully report that it created zero dead letters; it
# may never report the backlog itself as zero.
GOVERNED_DEAD_LETTER_BACKLOG = 1389
DEAD_LETTER_BACKLOG_NOTE = (
    'The global dead-letter backlog remains governed at 1,389 unless '
    'separately and authoritatively re-derived. This audit does not re-derive '
    'it and does not report it as zero. What this audit does report is that it '
    'created zero dead letters.'
)

# ── Canonical module digests at the incident SHA ────────────────────────────
# Recorded so Question 3 can answer "did code behaviour change since the
# incident?" without shelling out to git at runtime and without rewriting
# history. Computed from the tree at 9f9f640799af973f0a39cdafb1db83fba473b10c.
INCIDENT_CANONICAL_MODULE_DIGESTS = {
    'services/game_finality.py':
        'fd7c43a0c57f4eacdf1727f1f3e059b175a17995c8371f01b2e35ad65b8c5ece',
    'services/appearance_ledger.py':
        '14be8b8742ebca7865fb2a7c6cc5d4550c6825fa31a923e204563eafdcb27d83',
    'services/game_ingestion_completeness.py':
        'f97c7ffae0e3de99310d17e2323e10e380001839060324b4c2338ee3c9fc17a9',
    'services/game_ingestion_planner.py':
        'cf885c93d2fbb1d6d839e7157e873cc39e54bdfbe1fa2287af2b88637819e8c0',
    'services/sync_publication_proof.py':
        'e74869aa34751de3a0a0a63e2fb807272f17f58c5cf6254c3d69160534ed7930',
    'services/dashboard_snapshot.py':
        'd7b11239be253063d4c763d5ca11f669b90b71c3ef8f653ac625a8ade19b098d',
    'services/schedule_ingestion.py':
        '351eaccc43d28b773bd213753a84f895082d547204893a7fe33ff337d476c9b2',
}

# Later governed packages deliberately modified the canonical modules recorded
# below. This is current package accounting, not a rewrite of incident evidence:
# INCIDENT_CANONICAL_MODULE_DIGESTS remains the immutable Aug. 3 tree. Recording
# each approved post-incident digest keeps Question 3 honest — a module that
# differs because a named governed package changed it is a different fact from
# unexplained production drift, and the two must not be conflated.
PACKAGE_MODIFIED_MODULES = {
    'services/game_ingestion_completeness.py': {
        'digest_after':
            'cd715a1b701f6aec9525c5565611bd2aa62fc3c72f5741bea2fc982b34d2b362',
        'change': (
            'added read-only unresolved_final_game_membership helper (D-043); '
            'then separated observation completeness from publication-blocking '
            'completeness so shadow work-item backlog no longer withholds '
            'publication (D-044)'
        ),
        # D-044 DID change behaviour, and says so. `publication_complete` is
        # now the publication-gate view rather than the observation view, so a
        # reader comparing this audit's current-state findings against the
        # incident must know the gate moved underneath them. Reporting False
        # here would let a corrected gate look like an unchanged one.
        'behaviour_changed': True,
    },
    'services/dashboard_snapshot.py': {
        'digest_after':
            'aad00171d280696b9a49ee316c3eb8e34ca31ca90574ab6c819b7638be4ca8d3',
        'change': (
            'D-054 extracted the existing latest Dashboard snapshot queries '
            'for reuse and added guarded read entry points that distinguish a '
            'database-read failure from a legitimate missing snapshot; the '
            'existing selection filters and order, snapshot_unavailable_reason, '
            'and snapshot publishability, freshness, version, status, and '
            'publication-eligibility semantics remain unchanged. D-056 then '
            'added an env-gated branch in the post-commit publication hook that '
            'runs the SAME single Team State generation under observation and '
            'writes a side-channel proof file; with TEAM_STATE_VNEXT_PROOF_PATH '
            'unset the branch is not taken at all. The Production Accuracy Proof '
            'package subsequently made durable Team State proof mandatory before '
            'a newly trusted/current publication can advance, while retaining the '
            'prior trusted publication on proof failure. F-019 then binds the '
            'already-rendered What Changed comparison to its exact publication '
            'pair before the candidate becomes publicly served; missing identity '
            'withholds only the dependent share action. F-004 added a read-only '
            'field projection for purpose-built public surfaces; the Daily '
            'Edition cold-start package then made its already-governed snapshot '
            'projection a prerequisite of publication, preventing a trusted '
            'snapshot from becoming public before its Daily Edition is prepared; '
            'trusted snapshot selection and other publication eligibility '
            'semantics remain unchanged'
        ),
        # D-054 and D-056 did not move a publication outcome. The Production
        # Accuracy Proof package deliberately does: proof construction and
        # persistence are now prerequisites for advancing the trusted/current
        # pointer. Report that governed gate change instead of misclassifying it
        # as unexplained drift or unchanged behavior.
        'behaviour_changed': True,
    },
}

# ── Stored schedule row agreement (Question 2 / Blocker 5) ──────────────────
# Governed identity and finality fields. Every one of these disagreeing across
# the rows for a single game is a real conflict. `created_at`/`updated_at` are
# deliberately absent: two rows written microseconds apart are not a baseball
# identity conflict, and treating them as one would make the check meaningless.
# What the stored rows are shaped like, before asking whether they agree.
ROW_SHAPE_NO_ROWS = 'no_rows'
ROW_SHAPE_INCOMPLETE_PAIR = 'incomplete_pair'
ROW_SHAPE_EXACT_PAIR = 'exact_team_row_pair'
ROW_SHAPE_DUPLICATE_TEAM_ROWS = 'duplicate_team_rows'
ROW_SHAPE_TOO_MANY_ROWS = 'more_than_two_rows'

ROW_AGREEMENT_FIELDS = (
    'exact_team_row_pair',
    'unique_team_rows',
    'reciprocal_team_identity',
    'reciprocal_home_away_roles',
    'game_date',
    'original_product_date',
    'status_state',
    'status_code',
    'game_type',
    'game_number',
    'doubleheader',
    'resumed_from_game_pk',
    'resumed_to_game_pk',
    'source',
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

CONFIDENCE_HIGH = 'HIGH'
CONFIDENCE_MEDIUM = 'MEDIUM'
CONFIDENCE_LOW = 'LOW'
CONFIDENCE_LEVELS = (CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW)

# ── Evidence artifacts, addressed by EXACT run id and EXACT name ────────────
ARTIFACT_SHADOW = f'game-driven-shadow-{INCIDENT_RUN_ID}'
ARTIFACT_SHADOW_HANDOFF = f'game-driven-shadow-handoff-{INCIDENT_RUN_ID}'
ARTIFACT_LEDGER_AUDIT = f'appearance-ledger-audit-{INCIDENT_RUN_ID}'

# Known metadata from the incident. Treated as EXPECTATIONS to verify, never as
# facts to assume: GitHub may no longer expose an id or digest, and the handoff
# artifact's 7-day retention means it may simply be gone.
ARTIFACT_EXPECTATIONS = {
    ARTIFACT_SHADOW: {
        'artifact_id': 8878694840,
        'retention_days': 30,
        'digest': (
            'sha256:7527ffef431e811379e1e149e4593039157f12f2c66694ac2bbfbd48'
            'bb6f4d1f'
        ),
        'required': True,
    },
    ARTIFACT_SHADOW_HANDOFF: {
        'artifact_id': 8878688244,
        'retention_days': 7,
        'digest': (
            'sha256:49655824d4fba9e0c0bd769f6ccacc9f9b435cf20291912fe6d92b305'
            '0dbe0d7'
        ),
        'required': False,
    },
    ARTIFACT_LEDGER_AUDIT: {
        'artifact_id': 8878687942,
        'retention_days': 90,
        'digest': (
            'sha256:71fecf0df910ee303566030cedc23ba6169a25a7d7673391c138451af'
            'd7d475e'
        ),
        'required': True,
    },
}

REQUIRED_ARTIFACTS = tuple(
    name for name, spec in ARTIFACT_EXPECTATIONS.items() if spec['required']
)
OPTIONAL_ARTIFACTS = tuple(
    name for name, spec in ARTIFACT_EXPECTATIONS.items()
    if not spec['required']
)
EXPECTED_ARTIFACTS = tuple(ARTIFACT_EXPECTATIONS)

SHADOW_SYNC_SUMMARY_SUFFIX = '-sync-summary.json'
SHADOW_ACTIVATION_SUMMARY_SUFFIX = '-activation-summary.json'
LEDGER_REPORT_FILENAME = 'ledger_audit_report.txt'
HANDOFF_METADATA_FILENAME = 'handoff-metadata.json'

# ── Fingerprint scopes ──────────────────────────────────────────────────────
# Scoped rather than whole-table: a full digest of game_logs on every run would
# be needlessly expensive, and the incident's blast radius is precisely known.
# Every scope covers FULL governed row content and timestamps, not row counts.
SCOPE_EXACT_GAME = 'exact_game_822867'
SCOPE_SLATE = 'slate_2026_08_03'
SCOPE_LEDGER_WINDOW = 'ledger_window_2026_07_25__2026_08_03'
SCOPE_SNAPSHOTS = 'dashboard_snapshots_343_344'
SCOPE_SYNC_RUN = 'sync_run_596'
SCOPE_UNRESOLVED_GAMES = 'unresolved_final_games'

FINGERPRINT_SCOPE_NAMES = (
    SCOPE_EXACT_GAME,
    SCOPE_SLATE,
    SCOPE_LEDGER_WINDOW,
    SCOPE_SNAPSHOTS,
    SCOPE_SYNC_RUN,
    SCOPE_UNRESOLVED_GAMES,
)

# Correction provenance is COLUMNAR in this schema, not a table of its own: it
# lives on game_logs (stat_correction_count, last_stat_correction_at,
# last_stat_correction_source, last_stat_correction_sync_run_id),
# team_game_pitching_splits, game_play_by_play_events, and
# game_ingestion_work_items.correction_count. Full-row digests of those tables
# therefore already cover it; there is no separate table to fingerprint.
CORRECTION_PROVENANCE_CARRIERS = (
    'game_logs',
    'team_game_pitching_splits',
    'game_play_by_play_events',
    'game_ingestion_work_items',
)

FINGERPRINTED_TABLES = (
    'scheduled_games',
    'game_logs',
    'pitchers',
    'postgame_processed_games',
    'game_ingestion_work_items',
    'team_game_pitching_splits',
    'completed_game_contexts',
    'game_play_by_play_events',
    'dashboard_snapshots',
    'sync_runs',
    'sync_failures',
)

# Named evidence a source call is bought to obtain. Recovery must say WHICH
# of these a fallback restored, because a fallback usually restores only part
# of what the failed call would have provided — a successful exact-game call
# for one game recovers nothing about the other games in the window.
EVIDENCE_DISPUTED_GAME_OFFICIAL_STATUS = 'disputed_game_official_status'
EVIDENCE_UNRESOLVED_WINDOW_OFFICIAL_STATUS = (
    'unresolved_window_official_status'
)
EVIDENCE_DISPUTED_BOXSCORE = 'disputed_game_boxscore'

SOURCE_EVIDENCE_KINDS = (
    EVIDENCE_DISPUTED_GAME_OFFICIAL_STATUS,
    EVIDENCE_UNRESOLVED_WINDOW_OFFICIAL_STATUS,
    EVIDENCE_DISPUTED_BOXSCORE,
)

UNPROVEN_REQUIRED_SOURCE_CALL_FAILED = 'required_source_call_failed'
UNPROVEN_PLAYER_EVIDENCE_INCOMPLETE = 'player_attribution_evidence_incomplete'
UNPROVEN_UNRESOLVED_EVIDENCE_INCOMPLETE = (
    'unresolved_game_evidence_incomplete'
)
UNPROVEN_SNAPSHOT_GATE_INCOMPLETE = 'snapshot_gate_conclusion_incomplete'

# ── MLB source-call budget ──────────────────────────────────────────────────
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

# ── Primary root-cause classifications ──────────────────────────────────────
CLASSIFICATION_SCHEDULE_FINALITY_MAPPING_DRIFT = 'schedule_finality_mapping_drift'
CLASSIFICATION_APPEARANCE_LEDGER_COMPLETION_AUTHORITY_DEFECT = (
    'appearance_ledger_completion_authority_defect'
)
CLASSIFICATION_STORED_SCHEDULE_ROW_CONFLICT = 'stored_schedule_row_conflict'
CLASSIFICATION_EXACT_GAME_INGESTION_GAP = 'exact_game_ingestion_gap'
CLASSIFICATION_APPEARANCE_LEDGER_QUERY_DEFECT = 'appearance_ledger_query_defect'
CLASSIFICATION_PUBLICATION_GATE_SCOPE_DEFECT = 'publication_gate_scope_defect'
CLASSIFICATION_SNAPSHOT_STATE_TRANSITION_DEFECT = (
    'snapshot_state_transition_defect'
)
CLASSIFICATION_RESCHEDULE_OR_SUSPENSION_IDENTITY_DEFECT = (
    'reschedule_or_suspension_identity_defect'
)
CLASSIFICATION_MULTIPLE_CONTRIBUTING_DEFECTS = 'multiple_contributing_defects'
CLASSIFICATION_INCIDENT_CONDITION_NO_LONGER_REPRODUCIBLE = (
    'incident_condition_no_longer_reproducible'
)
CLASSIFICATION_NO_PLATFORM_DEFECT_PROVEN = 'no_platform_defect_proven'
CLASSIFICATION_UNPROVEN = 'unproven'

# Precedence: most specific proven defect first. `multiple_contributing_defects`
# is chosen by the reducer, not observed, so it is not in the observable set.
DEFECT_CLASSIFICATIONS = (
    CLASSIFICATION_RESCHEDULE_OR_SUSPENSION_IDENTITY_DEFECT,
    CLASSIFICATION_STORED_SCHEDULE_ROW_CONFLICT,
    CLASSIFICATION_APPEARANCE_LEDGER_COMPLETION_AUTHORITY_DEFECT,
    CLASSIFICATION_SCHEDULE_FINALITY_MAPPING_DRIFT,
    CLASSIFICATION_APPEARANCE_LEDGER_QUERY_DEFECT,
    CLASSIFICATION_EXACT_GAME_INGESTION_GAP,
    CLASSIFICATION_PUBLICATION_GATE_SCOPE_DEFECT,
    CLASSIFICATION_SNAPSHOT_STATE_TRANSITION_DEFECT,
)

TERMINAL_CLASSIFICATIONS = (
    CLASSIFICATION_MULTIPLE_CONTRIBUTING_DEFECTS,
    CLASSIFICATION_INCIDENT_CONDITION_NO_LONGER_REPRODUCIBLE,
    CLASSIFICATION_NO_PLATFORM_DEFECT_PROVEN,
    CLASSIFICATION_UNPROVEN,
)

PRIMARY_CLASSIFICATIONS = DEFECT_CLASSIFICATIONS + TERMINAL_CLASSIFICATIONS

assert len(PRIMARY_CLASSIFICATIONS) == 12
assert len(set(PRIMARY_CLASSIFICATIONS)) == 12

# ── Recommended next-package categories (informational only) ────────────────
NEXT_EXACT_GAME_FINALITY_REPAIR_REVIEW = 'exact_game_finality_repair_review'
NEXT_APPEARANCE_LEDGER_AUTHORITY_FIX = 'appearance_ledger_authority_fix'
NEXT_SCHEDULE_ROW_CONSISTENCY_FIX = 'schedule_row_consistency_fix'
NEXT_EXACT_GAME_INGESTION_REPAIR_REVIEW = 'exact_game_ingestion_repair_review'
NEXT_PUBLICATION_GATE_SCOPE_FIX = 'publication_gate_scope_fix'
NEXT_SNAPSHOT_TRANSITION_FIX = 'snapshot_transition_fix'
NEXT_RESCHEDULE_IDENTITY_FIX = 'reschedule_identity_fix'
NEXT_NO_MUTATION_REQUIRED = 'no_mutation_required'
NEXT_ADDITIONAL_EVIDENCE_REQUIRED = 'additional_evidence_required'

NEXT_PACKAGE_CATEGORIES = (
    NEXT_EXACT_GAME_FINALITY_REPAIR_REVIEW,
    NEXT_APPEARANCE_LEDGER_AUTHORITY_FIX,
    NEXT_SCHEDULE_ROW_CONSISTENCY_FIX,
    NEXT_EXACT_GAME_INGESTION_REPAIR_REVIEW,
    NEXT_PUBLICATION_GATE_SCOPE_FIX,
    NEXT_SNAPSHOT_TRANSITION_FIX,
    NEXT_RESCHEDULE_IDENTITY_FIX,
    NEXT_NO_MUTATION_REQUIRED,
    NEXT_ADDITIONAL_EVIDENCE_REQUIRED,
)

NEXT_PACKAGE_FOR_CLASSIFICATION = {
    CLASSIFICATION_SCHEDULE_FINALITY_MAPPING_DRIFT:
        NEXT_EXACT_GAME_FINALITY_REPAIR_REVIEW,
    CLASSIFICATION_APPEARANCE_LEDGER_COMPLETION_AUTHORITY_DEFECT:
        NEXT_APPEARANCE_LEDGER_AUTHORITY_FIX,
    CLASSIFICATION_APPEARANCE_LEDGER_QUERY_DEFECT:
        NEXT_APPEARANCE_LEDGER_AUTHORITY_FIX,
    CLASSIFICATION_STORED_SCHEDULE_ROW_CONFLICT:
        NEXT_SCHEDULE_ROW_CONSISTENCY_FIX,
    CLASSIFICATION_EXACT_GAME_INGESTION_GAP:
        NEXT_EXACT_GAME_INGESTION_REPAIR_REVIEW,
    CLASSIFICATION_PUBLICATION_GATE_SCOPE_DEFECT:
        NEXT_PUBLICATION_GATE_SCOPE_FIX,
    CLASSIFICATION_SNAPSHOT_STATE_TRANSITION_DEFECT:
        NEXT_SNAPSHOT_TRANSITION_FIX,
    CLASSIFICATION_RESCHEDULE_OR_SUSPENSION_IDENTITY_DEFECT:
        NEXT_RESCHEDULE_IDENTITY_FIX,
    CLASSIFICATION_MULTIPLE_CONTRIBUTING_DEFECTS:
        NEXT_ADDITIONAL_EVIDENCE_REQUIRED,
    CLASSIFICATION_NO_PLATFORM_DEFECT_PROVEN: NEXT_NO_MUTATION_REQUIRED,
    CLASSIFICATION_INCIDENT_CONDITION_NO_LONGER_REPRODUCIBLE:
        NEXT_ADDITIONAL_EVIDENCE_REQUIRED,
    CLASSIFICATION_UNPROVEN: NEXT_ADDITIONAL_EVIDENCE_REQUIRED,
}

NEXT_PACKAGE_DISCLAIMER = (
    'The recommended next-package category is informational only. It does not '
    'authorize implementation, dispatch, or production execution.'
)

# ── Player mismatch attribution (Question 6) ────────────────────────────────
PLAYER_CAUSED_BY_DISPUTED_GAME = 'caused_by_game_822867'
PLAYER_CAUSED_BY_ANOTHER_GAME = 'caused_by_another_game'
PLAYER_CAUSED_BY_RESCHEDULE_RELATIONSHIP = (
    'caused_by_postponed_or_rescheduled_relationship'
)
PLAYER_CAUSED_BY_IDENTITY_PROBLEM = 'caused_by_player_identity_problem'
PLAYER_CAUSED_BY_LEDGER_QUERY = 'caused_by_ledger_query'
PLAYER_CAUSED_BY_STALE_DATA = 'caused_by_stale_data'
PLAYER_NOT_REPRODUCIBLE = 'not_reproducible'
PLAYER_UNPROVEN = 'unproven'

PLAYER_CLASSIFICATIONS = (
    PLAYER_CAUSED_BY_DISPUTED_GAME,
    PLAYER_CAUSED_BY_ANOTHER_GAME,
    PLAYER_CAUSED_BY_RESCHEDULE_RELATIONSHIP,
    PLAYER_CAUSED_BY_IDENTITY_PROBLEM,
    PLAYER_CAUSED_BY_LEDGER_QUERY,
    PLAYER_CAUSED_BY_STALE_DATA,
    PLAYER_NOT_REPRODUCIBLE,
    PLAYER_UNPROVEN,
)

# ── Unresolved-game classification (Question 7) ─────────────────────────────
UNRESOLVED_FINAL_FULLY_REPRESENTED = 'official_final_and_fully_represented'
UNRESOLVED_FINAL_MISSING_ROWS = 'official_final_and_missing_game_log_rows'
UNRESOLVED_FINAL_PARTIAL = 'official_final_and_partially_represented'
UNRESOLVED_FINAL_OUT_OF_SCOPE = (
    'official_final_but_outside_required_publication_scope'
)
UNRESOLVED_STORED_FINAL_SOURCE_NON_FINAL = (
    'stored_final_but_official_source_non_final'
)
UNRESOLVED_SOURCE_FINAL_STORED_NON_FINAL = (
    'official_final_but_stored_schedule_non_final'
)
UNRESOLVED_POSTPONED = 'postponed'
UNRESOLVED_SUSPENDED = 'suspended'
UNRESOLVED_CANCELLED = 'cancelled'
UNRESOLVED_RESCHEDULED = 'rescheduled_or_makeup_relationship'
UNRESOLVED_DOUBLEHEADER_IDENTITY = 'duplicate_or_doubleheader_identity_issue'
UNRESOLVED_SCHEDULE_AUTHORITY_MISSING = 'missing_schedule_authority'
UNRESOLVED_TERMINAL_FAILURE = 'terminal_processing_failure'
UNRESOLVED_RETRYABLE = 'retryable_processing_state'
UNRESOLVED_WORK_ITEM_ABSENT_SHADOW_ONLY = (
    'completed_but_work_item_absent_because_lane_is_shadow_only'
)
UNRESOLVED_GATE_SCOPE_MISMATCH = 'publication_gate_scope_mismatch'
UNRESOLVED_NOT_REPRODUCIBLE = 'no_longer_reproducible'
UNRESOLVED_UNPROVEN = 'unproven'
UNRESOLVED_OTHER = 'other'

UNRESOLVED_CLASSIFICATIONS = (
    UNRESOLVED_FINAL_FULLY_REPRESENTED,
    UNRESOLVED_FINAL_MISSING_ROWS,
    UNRESOLVED_FINAL_PARTIAL,
    UNRESOLVED_FINAL_OUT_OF_SCOPE,
    UNRESOLVED_STORED_FINAL_SOURCE_NON_FINAL,
    UNRESOLVED_SOURCE_FINAL_STORED_NON_FINAL,
    UNRESOLVED_POSTPONED,
    UNRESOLVED_SUSPENDED,
    UNRESOLVED_CANCELLED,
    UNRESOLVED_RESCHEDULED,
    UNRESOLVED_DOUBLEHEADER_IDENTITY,
    UNRESOLVED_SCHEDULE_AUTHORITY_MISSING,
    UNRESOLVED_TERMINAL_FAILURE,
    UNRESOLVED_RETRYABLE,
    UNRESOLVED_WORK_ITEM_ABSENT_SHADOW_ONLY,
    UNRESOLVED_GATE_SCOPE_MISMATCH,
    UNRESOLVED_NOT_REPRODUCIBLE,
    UNRESOLVED_UNPROVEN,
    UNRESOLVED_OTHER,
)

assert len(UNRESOLVED_CLASSIFICATIONS) == 19
assert len(set(UNRESOLVED_CLASSIFICATIONS)) == 19

# Categories whose verdict rests on the official record. A member landing in
# one of these without official evidence was not established, it was assumed.
OFFICIAL_DEPENDENT_UNRESOLVED_CATEGORIES = frozenset({
    UNRESOLVED_FINAL_FULLY_REPRESENTED,
    UNRESOLVED_FINAL_MISSING_ROWS,
    UNRESOLVED_FINAL_PARTIAL,
    UNRESOLVED_STORED_FINAL_SOURCE_NON_FINAL,
    UNRESOLVED_SOURCE_FINAL_STORED_NON_FINAL,
    UNRESOLVED_POSTPONED,
    UNRESOLVED_SUSPENDED,
    UNRESOLVED_CANCELLED,
    UNRESOLVED_RESCHEDULED,
    UNRESOLVED_WORK_ITEM_ABSENT_SHADOW_ONLY,
})

# Player classifications that rest on positive evidence rather than on the
# absence of a contradiction.
PLAYER_POSITIVE_EVIDENCE_CLASSIFICATIONS = frozenset({
    PLAYER_CAUSED_BY_DISPUTED_GAME,
    PLAYER_CAUSED_BY_LEDGER_QUERY,
    PLAYER_CAUSED_BY_IDENTITY_PROBLEM,
    PLAYER_CAUSED_BY_RESCHEDULE_RELATIONSHIP,
    PLAYER_CAUSED_BY_STALE_DATA,
    PLAYER_CAUSED_BY_ANOTHER_GAME,
})

# Categories that do NOT represent a genuine unpublished final-game deficit.
# A postponed or cancelled game must never inflate the true deficit.
UNRESOLVED_NON_DEFICIT_CATEGORIES = frozenset({
    UNRESOLVED_FINAL_FULLY_REPRESENTED,
    UNRESOLVED_FINAL_OUT_OF_SCOPE,
    UNRESOLVED_POSTPONED,
    UNRESOLVED_SUSPENDED,
    UNRESOLVED_CANCELLED,
    UNRESOLVED_RESCHEDULED,
    UNRESOLVED_GATE_SCOPE_MISMATCH,
    UNRESOLVED_WORK_ITEM_ABSENT_SHADOW_ONLY,
})

# Membership provenance for the unresolved set.
# The status fields the canonical mapper actually consumes. Reproducing the
# incident's mapping means having THESE values as they stood at incident time,
# not today's equivalents.
MAPPING_INPUT_FIELDS = (
    'abstractGameState',
    'codedGameState',
    'detailedState',
    'statusCode',
    'reason',
)

MAPPING_INPUT_NOT_RECONSTRUCTED = 'incident_mapping_input_not_reconstructed'
MAPPING_INPUT_RECONSTRUCTED = 'incident_mapping_input_reconstructed'


def incident_mapping_input(shadow) -> dict:
    """Recover the status payload the incident preflight mapped, if retained.

    Question 3 asks why the incident produced ``other``. Observing what the
    game maps to TODAY cannot answer that: today's official record is a
    different input, and a mapping that no longer reproduces ``other`` is
    evidence that the input changed, not an explanation of the original
    result. The question is answerable only from the incident-time status
    payload, and only if a retained artifact actually carries it.

    The retained artifacts record the preflight's OUTPUT — the status_state it
    stored — and not the status payload it read. So this normally reports that
    the input was not reconstructed, which is the honest answer. It is written
    to recover the input if a future artifact does carry it rather than to
    hard-code the absence.
    """
    summary = (shadow or {}).get('sync_summary') or {}
    candidates = (
        summary.get('preflight_status_payloads')
        or summary.get('schedule_status_payloads')
        or {}
    )
    payload = None
    if isinstance(candidates, dict):
        for key in (INCIDENT_GAME_PK, str(INCIDENT_GAME_PK)):
            entry = candidates.get(key)
            if isinstance(entry, dict):
                payload = entry
                break

    # The recovered payload is consumed here and never returned. Reporting it
    # would put raw source content into the evidence document, which the
    # artifact contract forbids; and the question does not need it. What a
    # reader needs is whether the input was recovered, how completely, and
    # what the canonical authority makes of it — the resulting status_state,
    # which is a governed value the document already reports elsewhere.
    if not payload:
        return {
            'evidence_source': SOURCE_INCIDENT,
            'input_recovered': False,
            'mapping_input_fields_expected': len(MAPPING_INPUT_FIELDS),
            'mapping_input_fields_recovered': 0,
            'remapped_status_state': None,
            'reproduces_incident_state': None,
            'reason': MAPPING_INPUT_NOT_RECONSTRUCTED,
            'raw_source_content_withheld': True,
            'note': (
                'The retained incident artifacts record the status_state the '
                'preflight STORED and not the status it READ. The mapping '
                'input cannot be reconstructed from them, so the incident '
                'mapping cannot be re-derived.'
            ),
        }

    recovered = sum(1 for field in MAPPING_INPUT_FIELDS if payload.get(field))
    try:
        from services import game_finality

        remapped = game_finality.normalize_schedule_status_state(payload)
    except Exception:  # noqa: BLE001 - an unmappable input is unproven
        remapped = None

    incident_state = INCIDENT_PREFLIGHT_STATUS_STATES.get(INCIDENT_GAME_PK)
    return {
        'evidence_source': SOURCE_INCIDENT,
        'input_recovered': bool(recovered) and remapped is not None,
        'mapping_input_fields_expected': len(MAPPING_INPUT_FIELDS),
        'mapping_input_fields_recovered': recovered,
        'remapped_status_state': remapped,
        'reproduces_incident_state': (
            None if remapped is None else remapped == incident_state
        ),
        'reason': (
            MAPPING_INPUT_RECONSTRUCTED if remapped is not None
            else MAPPING_INPUT_NOT_RECONSTRUCTED
        ),
        'raw_source_content_withheld': True,
        'note': (
            'The incident-time status was recovered from a retained artifact '
            'and re-mapped through the canonical authority. Only the mapped '
            'result is reported; the source content itself is withheld.'
        ),
    }


# Planner classification of the disputed game. Three-valued on purpose: a
# planner whose plan was never observed has not excluded anything.
PLANNER_CLASS_PLANNED = 'planned'
PLANNER_CLASS_EXCLUDED = 'excluded'
PLANNER_CLASS_UNPROVEN = 'unproven'
PLANNER_CLASSIFICATIONS = (
    PLANNER_CLASS_PLANNED, PLANNER_CLASS_EXCLUDED, PLANNER_CLASS_UNPROVEN,
)

MEMBERSHIP_INCIDENT_ARTIFACT = 'immutable_incident_membership'
MEMBERSHIP_CURRENT_RECONSTRUCTION = 'current_reconstruction'

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
FAILED_ARTIFACT_DIGEST_MISMATCH = 'incident_artifact_digest_mismatch'
FAILED_UNAUTHORIZED_INVOCATION = 'unauthorized_invocation'
FAILED_ARTIFACT_PROHIBITED_CONTENT = 'artifact_contains_prohibited_content'

UNPROVEN_GUARD_NOT_ACQUIRED = 'sync_read_guard_not_acquired'
UNPROVEN_READ_ONLY_NOT_ENFORCED = 'read_only_transaction_not_enforced'
UNPROVEN_PROBE_EVIDENCE_MISSING = 'read_only_probe_evidence_missing'
UNPROVEN_PROBE_NOT_ATTEMPTED = 'read_only_probe_not_attempted'
UNPROVEN_PROBE_COUNT_UNKNOWN = 'read_only_probe_count_unknown'
UNPROVEN_FINGERPRINTS_UNAVAILABLE = 'required_fingerprint_unavailable'
UNPROVEN_REQUIRED_ARTIFACT_MISSING = 'required_incident_artifact_missing'
UNPROVEN_REQUIRED_ARTIFACT_UNREADABLE = 'required_incident_artifact_unreadable'
UNPROVEN_SOURCE_BUDGET_EXHAUSTED = 'mlb_source_call_budget_exhausted'
UNPROVEN_QUESTION_UNANSWERED = 'incident_question_unanswered'
UNPROVEN_AUDIT_EXECUTION_ERROR = 'audit_execution_error'
UNPROVEN_ARTIFACT_CONSTRUCTION_FAILED = 'artifact_construction_failed'
UNPROVEN_ARTIFACT_UPLOAD_FAILED = 'evidence_artifact_upload_failed'
UNPROVEN_SNAPSHOT_EVIDENCE_MISSING = 'snapshot_evidence_missing'

# ── Execution stages ────────────────────────────────────────────────────────
# The audit must be able to say WHERE it stopped without saying WHAT the
# database contained. These are the only stage names it may report, and the
# only error classes it may attribute a stop to. Both vocabularies are closed:
# an unrecognised value is reported as the unclassified member, never as free
# text. Nothing derived from an exception message, a SQL statement, a
# connection string, or a row value may ever reach the artifact.

STAGE_NOT_STARTED = 'not_started'
STAGE_GUARD_ACQUIRED = 'advisory_guard_acquired'
STAGE_READ_ONLY_ENFORCED = 'read_only_transaction_enforced'
STAGE_BEFORE_FINGERPRINTS = 'before_fingerprints_phase_one'
STAGE_SOURCE_WINDOW = 'official_source_window'
STAGE_STORED_SCHEDULE = 'stored_schedule_observed'
STAGE_OFFICIAL_STATUS = 'official_status_observed'
STAGE_BASEBALL_STATE = 'baseball_state_observed'
STAGE_APPEARANCE_LEDGER = 'appearance_ledger_observed'
STAGE_COMPLETENESS = 'completeness_observed'
STAGE_PLAYER_ATTRIBUTION = 'player_attribution_observed'
STAGE_SNAPSHOT_GATE = 'snapshot_gate_observed'
STAGE_DEAD_LETTER = 'dead_letter_backlog_observed'
STAGE_UNRESOLVED_FINGERPRINTS = 'before_fingerprints_phase_two'
STAGE_AFTER_FINGERPRINTS = 'after_fingerprints'
STAGE_COMPLETE = 'all_stages_complete'

EXECUTION_STAGES = (
    STAGE_NOT_STARTED,
    STAGE_GUARD_ACQUIRED,
    STAGE_READ_ONLY_ENFORCED,
    STAGE_BEFORE_FINGERPRINTS,
    STAGE_SOURCE_WINDOW,
    STAGE_STORED_SCHEDULE,
    STAGE_OFFICIAL_STATUS,
    STAGE_BASEBALL_STATE,
    STAGE_APPEARANCE_LEDGER,
    STAGE_COMPLETENESS,
    STAGE_PLAYER_ATTRIBUTION,
    STAGE_SNAPSHOT_GATE,
    STAGE_DEAD_LETTER,
    STAGE_UNRESOLVED_FINGERPRINTS,
    STAGE_AFTER_FINGERPRINTS,
    STAGE_COMPLETE,
)

# Bounded error classes. Each names a KIND of failure, never an instance of
# one. 'audit_code_defect' is what the first production run would have
# reported: a NameError inside the audit's own code, which is a defect in this
# package and not a statement about production data.
ERROR_CLASS_NONE = 'none'
ERROR_CLASS_AUDIT_CODE_DEFECT = 'audit_code_defect'
ERROR_CLASS_MISSING_ATTRIBUTE = 'expected_attribute_absent'
ERROR_CLASS_UNEXPECTED_SHAPE = 'unexpected_evidence_shape'
ERROR_CLASS_ARITHMETIC = 'arithmetic_or_conversion_error'
ERROR_CLASS_DATABASE_READ = 'database_read_error'
ERROR_CLASS_READ_ONLY_REFUSED = 'read_only_transaction_refused_statement'
ERROR_CLASS_TIMEOUT = 'operation_timed_out'
ERROR_CLASS_UNCLASSIFIED = 'unclassified_error'

SAFE_ERROR_CLASSES = (
    ERROR_CLASS_NONE,
    ERROR_CLASS_AUDIT_CODE_DEFECT,
    ERROR_CLASS_MISSING_ATTRIBUTE,
    ERROR_CLASS_UNEXPECTED_SHAPE,
    ERROR_CLASS_ARITHMETIC,
    ERROR_CLASS_DATABASE_READ,
    ERROR_CLASS_READ_ONLY_REFUSED,
    ERROR_CLASS_TIMEOUT,
    ERROR_CLASS_UNCLASSIFIED,
)

# Exception TYPE names only. The mapping is keyed on the class name so that no
# instance data — which is where row values and SQL text live — is consulted.
_ERROR_CLASS_BY_TYPE = {
    'NameError': ERROR_CLASS_AUDIT_CODE_DEFECT,
    'UnboundLocalError': ERROR_CLASS_AUDIT_CODE_DEFECT,
    'ImportError': ERROR_CLASS_AUDIT_CODE_DEFECT,
    'ModuleNotFoundError': ERROR_CLASS_AUDIT_CODE_DEFECT,
    'IndentationError': ERROR_CLASS_AUDIT_CODE_DEFECT,
    'SyntaxError': ERROR_CLASS_AUDIT_CODE_DEFECT,
    'AttributeError': ERROR_CLASS_MISSING_ATTRIBUTE,
    'KeyError': ERROR_CLASS_MISSING_ATTRIBUTE,
    'IndexError': ERROR_CLASS_MISSING_ATTRIBUTE,
    'TypeError': ERROR_CLASS_UNEXPECTED_SHAPE,
    'ValueError': ERROR_CLASS_UNEXPECTED_SHAPE,
    'StopIteration': ERROR_CLASS_UNEXPECTED_SHAPE,
    'ZeroDivisionError': ERROR_CLASS_ARITHMETIC,
    'ArithmeticError': ERROR_CLASS_ARITHMETIC,
    'OverflowError': ERROR_CLASS_ARITHMETIC,
    'DecimalException': ERROR_CLASS_ARITHMETIC,
    'InvalidOperation': ERROR_CLASS_ARITHMETIC,
    'ReadOnlySqlTransactionError': ERROR_CLASS_READ_ONLY_REFUSED,
    'InternalError': ERROR_CLASS_DATABASE_READ,
    'OperationalError': ERROR_CLASS_DATABASE_READ,
    'ProgrammingError': ERROR_CLASS_DATABASE_READ,
    'DataError': ERROR_CLASS_DATABASE_READ,
    'IntegrityError': ERROR_CLASS_DATABASE_READ,
    'DatabaseError': ERROR_CLASS_DATABASE_READ,
    'InterfaceError': ERROR_CLASS_DATABASE_READ,
    'DBAPIError': ERROR_CLASS_DATABASE_READ,
    'SQLAlchemyError': ERROR_CLASS_DATABASE_READ,
    'TimeoutError': ERROR_CLASS_TIMEOUT,
    'ReadOnlyProbeViolation': ERROR_CLASS_READ_ONLY_REFUSED,
}


def classify_error(exc) -> str:
    """Name the KIND of failure, using the exception TYPE and nothing else.

    The exception instance is never rendered, formatted, or inspected for
    content. Only ``type(exc).__name__`` and the names of its base classes are
    read, so no message text, bound parameter, SQL statement, or row value can
    escape into the evidence document. A read-only refusal is recognised
    ahead of the generic database classes because it is the one database error
    that would mean the audit had tried to write.
    """
    if exc is None:
        return ERROR_CLASS_NONE
    for klass in type(exc).__mro__:
        name = getattr(klass, '__name__', '')
        if name in _ERROR_CLASS_BY_TYPE:
            return _ERROR_CLASS_BY_TYPE[name]
    return ERROR_CLASS_UNCLASSIFIED


def safe_stage(value) -> str:
    """Admit a stage name only if it is in the closed vocabulary."""
    return value if value in EXECUTION_STAGES else STAGE_NOT_STARTED


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
QUESTION_UNRESOLVED_GAME_CLASSIFICATION = (
    'q7_unresolved_final_game_classification'
)
QUESTION_SNAPSHOT_GATE = 'q8_snapshot_publication_gate'

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
        f'What is the current official MLB status of game {INCIDENT_GAME_PK}?'
    ),
    QUESTION_STORED_SCHEDULE_STATE: (
        f'What schedule state does production store for game '
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
        'What is the exact stored baseball state for the game across every '
        'relevant table?'
    ),
    QUESTION_PLAYER_MISMATCH_ATTRIBUTION: (
        'What individually explains each of the nine reported player '
        'appearance mismatches?'
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

# ── Official-status normalized field set (Question 1) ───────────────────────
# Safe normalized fields only. The raw MLB payload is never reproduced.
OFFICIAL_STATUS_FIELDS = (
    'game_pk',
    'official_date',
    'original_date',
    'resume_date',
    'reschedule_date',
    'game_type',
    'doubleheader',
    'game_number',
    'abstract_game_state',
    'detailed_state',
    'coded_game_state',
    'status_code',
    'reason',
    'home_team_id',
    'away_team_id',
    'venue_id',
    'probable_classification',
    'retrieved_at',
    'source_revision',
)

OFFICIAL_CLASS_FINAL = 'final'
OFFICIAL_CLASS_POSTPONED = 'postponed'
OFFICIAL_CLASS_SUSPENDED = 'suspended'
OFFICIAL_CLASS_CANCELLED = 'cancelled'
OFFICIAL_CLASS_NON_FINAL = 'non_final'
OFFICIAL_CLASS_UNKNOWN = 'unknown'

OFFICIAL_CLASSIFICATIONS = (
    OFFICIAL_CLASS_FINAL,
    OFFICIAL_CLASS_POSTPONED,
    OFFICIAL_CLASS_SUSPENDED,
    OFFICIAL_CLASS_CANCELLED,
    OFFICIAL_CLASS_NON_FINAL,
    OFFICIAL_CLASS_UNKNOWN,
)

MAX_REPORTED_REASON_CODES = 12
MAX_REPORTED_GAMES_PER_CATEGORY = 200

_DIGITS = re.compile(r'-?\d+')
_SHA256_HEX = re.compile(r'\A(?:sha256:)?[0-9a-f]{64}\Z')


class AuditInputError(ValueError):
    """A bounded input could not be accepted. Carries a safe reason only."""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class SourceCallBudget:
    """Bounded accounting for upstream MLB calls.

    Every call is reserved BEFORE it is issued, so an exhausted budget refuses
    rather than overspending. Exhaustion is UNPROVEN: the audit reports what it
    could not observe instead of guessing.

    Attempts, successes, failures, retries, and latency are counted separately
    because they answer different questions. A call that was attempted and
    failed is not the same fact as a call that was never attempted.
    """

    def __init__(self, *, per_kind=None, total=None):
        self._limits = dict(per_kind or SOURCE_CALL_BUDGET)
        self._total_limit = int(
            SOURCE_CALL_TOTAL_BUDGET if total is None else total
        )
        self._attempted = {kind: 0 for kind in CALL_KINDS}
        self._succeeded = {kind: 0 for kind in CALL_KINDS}
        self._failed = {kind: 0 for kind in CALL_KINDS}
        self._retries = {kind: 0 for kind in CALL_KINDS}
        self._refused = {kind: 0 for kind in CALL_KINDS}
        self._refused_required = {kind: 0 for kind in CALL_KINDS}
        self._latency_ms = 0.0

    @property
    def total_attempted(self) -> int:
        return sum(self._attempted.values())

    @property
    def exhausted(self) -> bool:
        if self.total_attempted >= self._total_limit:
            return True
        return any(
            self._attempted[kind] >= self._limits.get(kind, 0)
            for kind in CALL_KINDS
        )

    def remaining(self, kind) -> int:
        per_kind = max(
            self._limits.get(kind, 0) - self._attempted.get(kind, 0), 0
        )
        overall = max(self._total_limit - self.total_attempted, 0)
        return min(per_kind, overall)

    def reserve(self, kind, *, required=True) -> bool:
        """Reserve one call of ``kind``. False when the budget refuses it.

        ``required`` marks a call the audit needs in order to answer a
        question. Refusing one of those is what makes evidence incomplete;
        refusing an optional opportunistic call is not, and neither is simply
        having spent the last unit of an allowance on a call that succeeded.
        """
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

    def record_failure(self, kind, *, latency_ms=0.0, retries=0) -> None:
        if kind in CALL_KINDS:
            self._failed[kind] += 1
            self._retries[kind] += max(int(retries or 0), 0)
            self._latency_ms += max(float(latency_ms or 0.0), 0.0)

    def state(self) -> dict:
        return {
            'limits': dict(self._limits),
            'total_limit': self._total_limit,
            'endpoint_classes': list(CALL_KINDS),
            'calls_attempted': dict(self._attempted),
            'calls_succeeded': dict(self._succeeded),
            'calls_failed': dict(self._failed),
            'retries': dict(self._retries),
            'calls_refused_by_budget': dict(self._refused),
            'total_attempted': self.total_attempted,
            'total_succeeded': sum(self._succeeded.values()),
            'total_failed': sum(self._failed.values()),
            'total_retries': sum(self._retries.values()),
            'total_refused_by_budget': sum(self._refused.values()),
            'total_source_latency_ms': round(self._latency_ms, 2),
            'budget_remaining': {
                kind: self.remaining(kind) for kind in CALL_KINDS
            },
            'total_budget_remaining': max(
                self._total_limit - self.total_attempted, 0
            ),
            # Informational: an allowance fully and successfully spent is a
            # correct run, not a defective one.
            'budget_exhausted': self.exhausted,
            'budget_refused_a_call': sum(self._refused.values()) > 0,
            'calls_refused_required': dict(self._refused_required),
            'total_refused_required': sum(self._refused_required.values()),
            # Decision-relevant: evidence the audit needed and could not buy.
            'required_call_refused': sum(self._refused_required.values()) > 0,
        }


# ── Incident identity ───────────────────────────────────────────────────────

def incident_identity() -> dict:
    """The locked incident this audit reconstructs."""
    return {
        'workflow_run_id': INCIDENT_RUN_ID,
        'head_sha': INCIDENT_HEAD_SHA,
        'cycle_kind': INCIDENT_CYCLE,
        'slate_date': INCIDENT_SLATE_DATE.isoformat(),
        'disputed_game_pk': INCIDENT_GAME_PK,
        'candidate_snapshot_id': INCIDENT_CANDIDATE_SNAPSHOT_ID,
        'served_snapshot_id': INCIDENT_SERVING_SNAPSHOT_ID,
        'sync_run_id': INCIDENT_SYNC_RUN_ID,
        'runner_exit_code': INCIDENT_RUNNER_EXIT_CODE,
        'artifact_names': list(EXPECTED_ARTIFACTS),
    }


def immutable_incident_facts() -> dict:
    """Every incident fact this audit preserves, tagged as incident evidence."""
    return {
        'evidence_source': SOURCE_INCIDENT,
        'interpretation': dict(INCIDENT_INTERPRETATION),
        'interpretation_note': INTERPRETATION_NOTE,
        'shadow_lane': dict(INCIDENT_SHADOW_LANE),
        'legacy_postgame': dict(INCIDENT_LEGACY_POSTGAME),
        'newly_processed_games': list(INCIDENT_NEWLY_PROCESSED_GAMES),
        'preflight_status_states': dict(INCIDENT_PREFLIGHT_STATUS_STATES),
        'appearance_ledger': {
            key: (list(value) if isinstance(value, tuple) else value)
            for key, value in INCIDENT_LEDGER.items()
        },
        'player_mismatches': [
            dict(entry) for entry in INCIDENT_PLAYER_MISMATCHES
        ],
        'candidate_snapshot': dict(INCIDENT_SNAPSHOT_CANDIDATE),
        'served_snapshot': dict(INCIDENT_SNAPSHOT_SERVED),
        'publication_proof_reason_codes': list(
            INCIDENT_PUBLICATION_REASON_CODES
        ),
        'game_ingestion_completeness': {
            key: (list(value) if isinstance(value, tuple) else value)
            for key, value in INCIDENT_COMPLETENESS.items()
        },
        'dead_letter_backlog_note': DEAD_LETTER_BACKLOG_NOTE,
        'governed_dead_letter_backlog': GOVERNED_DEAD_LETTER_BACKLOG,
    }


def validate_incident_scope(
    *, run_id, cycle, slate_date, game_pk=None, head_sha=None,
) -> list[str]:
    """Refuse any scope other than the one incident. Exact-scope, always."""
    failures: list[str] = []
    if str(run_id or '').strip() != INCIDENT_RUN_ID:
        failures.append('incident_run_id_mismatch')
    if str(cycle or '').strip().lower() != INCIDENT_CYCLE:
        failures.append('incident_cycle_mismatch')
    if _as_date(slate_date) != INCIDENT_SLATE_DATE:
        failures.append('incident_slate_date_mismatch')
    if game_pk is not None and _as_int(game_pk) != INCIDENT_GAME_PK:
        failures.append('incident_game_pk_mismatch')
    if head_sha is not None and str(head_sha).strip().lower() != (
        INCIDENT_HEAD_SHA
    ):
        failures.append('incident_head_sha_mismatch')
    return failures


def canonical_module_drift(module_digests) -> dict:
    """Compare current canonical module digests with the incident SHA's.

    Answers Question 3's "did code behaviour change since 9f9f640?" without
    shelling out to git and without rewriting history.
    """
    observed = module_digests if isinstance(module_digests, dict) else {}
    compared = {}
    changed = []
    unknown = []
    package_changed = []
    upstream_changed = []
    for path, expected in sorted(INCIDENT_CANONICAL_MODULE_DIGESTS.items()):
        current = observed.get(path)
        if not current:
            unknown.append(path)
            compared[path] = {
                'incident_digest': expected,
                'current_digest': None,
                'unchanged': None,
            }
            continue
        same = current == expected
        known = PACKAGE_MODIFIED_MODULES.get(path) or {}
        by_package = bool(known) and current == known.get('digest_after')
        compared[path] = {
            'incident_digest': expected,
            'current_digest': current,
            'unchanged': same,
            'changed_by_this_package': by_package,
            'package_change': known.get('change') if by_package else None,
            'behaviour_changed': (
                known.get('behaviour_changed') if by_package else (not same)
            ),
        }
        if not same:
            changed.append(path)
            (package_changed if by_package else upstream_changed).append(path)
    return {
        'evidence_source': SOURCE_INFERENCE,
        'modules': compared,
        'changed_modules': sorted(changed),
        # A module this package edited is a different fact from one that
        # drifted in production. Only the latter can explain the incident.
        'changed_by_this_package': sorted(package_changed),
        'changed_upstream_since_incident': sorted(upstream_changed),
        'unknown_modules': sorted(unknown),
        'any_change_since_incident': bool(changed),
        'any_upstream_change_since_incident': bool(upstream_changed),
        'comparable': not unknown,
    }


# ── Evidence artifact ingestion ─────────────────────────────────────────────

def artifact_expectations() -> dict:
    return {
        'run_id': INCIDENT_RUN_ID,
        'required': list(REQUIRED_ARTIFACTS),
        'optional': list(OPTIONAL_ARTIFACTS),
        'expected_metadata': {
            name: dict(spec) for name, spec in ARTIFACT_EXPECTATIONS.items()
        },
    }


def normalize_digest(raw) -> str | None:
    """Normalize a digest to bare lowercase hex, or None when unusable."""
    text = str(raw or '').strip().lower()
    if not text or not _SHA256_HEX.match(text):
        return None
    return text.split(':', 1)[-1]


def verify_artifact_digest(name, observed_digest) -> dict:
    """Verify an observed digest against the incident's recorded digest.

    A digest GitHub no longer exposes is UNVERIFIED — honest, and not a failure.
    A digest that is present and DIFFERENT is a definite violation: the evidence
    is not the evidence this audit is scoped to.
    """
    expected = normalize_digest(
        (ARTIFACT_EXPECTATIONS.get(name) or {}).get('digest')
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


def ingest_incident_artifacts(root, *, observed_metadata=None) -> dict:
    """Discover and validate the incident artifacts downloaded under ``root``.

    One directory per artifact name, exactly as ``actions/download-artifact``
    lays them out. Presence, readability, digest verification, and parsed
    content are separate facts, and a missing OPTIONAL artifact is reported
    rather than inferred away.
    """
    from pathlib import Path

    base = Path(root)
    metadata = observed_metadata if isinstance(observed_metadata, dict) else {}
    artifacts: dict[str, dict] = {}

    for name in EXPECTED_ARTIFACTS:
        spec = ARTIFACT_EXPECTATIONS[name]
        directory = base / name
        entry = {
            'artifact_name': name,
            'required': spec['required'],
            'expected_artifact_id': spec['artifact_id'],
            'expected_retention_days': spec['retention_days'],
            'present': directory.is_dir(),
            'files': [],
            'readable': False,
            'parse_error': None,
            **verify_artifact_digest(
                name, (metadata.get(name) or {}).get('digest')
            ),
        }
        if entry['present']:
            try:
                entry['files'] = sorted(
                    child.name for child in directory.iterdir()
                    if child.is_file()
                )
                entry['readable'] = True
            except OSError:
                entry['parse_error'] = 'artifact_directory_unreadable'
        artifacts[name] = entry

    shadow = artifacts[ARTIFACT_SHADOW]
    if shadow['present'] and shadow['readable']:
        shadow.update(_read_shadow_artifact(base / ARTIFACT_SHADOW))

    ledger = artifacts[ARTIFACT_LEDGER_AUDIT]
    if ledger['present'] and ledger['readable']:
        ledger.update(_read_ledger_artifact(base / ARTIFACT_LEDGER_AUDIT))

    handoff = artifacts[ARTIFACT_SHADOW_HANDOFF]
    if handoff['present'] and handoff['readable']:
        handoff.update(_read_handoff_artifact(base / ARTIFACT_SHADOW_HANDOFF))

    missing_required = sorted(
        name for name in REQUIRED_ARTIFACTS if not artifacts[name]['present']
    )
    unreadable_required = sorted(
        name for name in REQUIRED_ARTIFACTS
        if artifacts[name]['present'] and artifacts[name].get('parse_error')
    )
    missing_optional = sorted(
        name for name in OPTIONAL_ARTIFACTS if not artifacts[name]['present']
    )
    digest_mismatches = sorted(
        name for name, entry in artifacts.items()
        if entry.get('digest_mismatch')
    )

    return {
        'expectations': artifact_expectations(),
        'artifacts': artifacts,
        'missing_required': missing_required,
        'unreadable_required': unreadable_required,
        # Reported, never inferred away: the handoff artifact carries a 7-day
        # retention and its evidence is duplicated by the activation artifact,
        # so its absence is legitimate — but a reader must still see it.
        'missing_optional': missing_optional,
        'digest_mismatches': digest_mismatches,
        'all_required_present': (
            not missing_required and not unreadable_required
        ),
        'incident_validation': _validate_incident_facts(artifacts),
    }


def _validate_incident_facts(artifacts) -> dict:
    """Cross-check the artifacts' own claims against the locked incident scope.

    Filenames are never trusted on their own: the run id, head SHA, cycle kind,
    slate date, runner exit code, and disputed game id are read from inside the
    documents.
    """
    shadow = artifacts.get(ARTIFACT_SHADOW) or {}
    summary = shadow.get('sync_summary') or {}
    activation = shadow.get('activation_summary') or {}
    handoff_meta = (
        artifacts.get(ARTIFACT_SHADOW_HANDOFF) or {}
    ).get('handoff_metadata') or {}
    ledger_report = (
        artifacts.get(ARTIFACT_LEDGER_AUDIT) or {}
    ).get('ledger_report') or {}

    observed_run_id = (
        handoff_meta.get('run_id') or handoff_meta.get('workflow_run_id')
    )
    observed_head_sha = (
        handoff_meta.get('repository_sha') or handoff_meta.get('head_sha')
    )
    observed_cycle = (
        activation.get('cycle_kind') or handoff_meta.get('cycle_kind')
    )
    observed_slate = summary.get('schedule_date') or (
        (summary.get('sync') or {}).get('schedule_date')
    )
    observed_exit = activation.get('runner_exit_code')
    observed_missing_games = ledger_report.get('missing_game_pks') or []

    checks = {
        'run_id': _match(observed_run_id, INCIDENT_RUN_ID),
        'head_sha': _match(observed_head_sha, INCIDENT_HEAD_SHA),
        'cycle_kind': _match(observed_cycle, INCIDENT_CYCLE),
        'slate_date': _match(observed_slate, INCIDENT_SLATE_DATE.isoformat()),
        'runner_exit_code': _match(observed_exit, INCIDENT_RUNNER_EXIT_CODE),
        'disputed_game_pk': (
            'not_observed' if not observed_missing_games
            else ('match' if INCIDENT_GAME_PK in observed_missing_games
                  else 'mismatch')
        ),
    }
    mismatched = sorted(
        key for key, value in checks.items() if value == 'mismatch'
    )
    unobserved = sorted(
        key for key, value in checks.items() if value == 'not_observed'
    )
    return {
        'checks': checks,
        'mismatched_fields': mismatched,
        'unobserved_fields': unobserved,
        'any_mismatch': bool(mismatched),
        'fully_verified': not mismatched and not unobserved,
    }


def _match(observed, expected) -> str:
    if observed is None or observed == '':
        return 'not_observed'
    return 'match' if str(observed).strip().lower() == str(
        expected
    ).strip().lower() else 'mismatch'


def _read_shadow_artifact(directory) -> dict:
    import json

    result: dict = {
        'sync_summary_filename': None, 'sync_summary': None,
        'activation_summary_filename': None, 'activation_summary': None,
    }
    try:
        children = list(directory.iterdir())
    except OSError:
        return {**result, 'parse_error': 'artifact_directory_unreadable'}

    sync_files = sorted(
        path for path in children
        if path.is_file() and path.name.endswith(SHADOW_SYNC_SUMMARY_SUFFIX)
    )
    activation_files = sorted(
        path for path in children
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
        return {**result, 'parse_error': 'shadow_artifact_unparseable'}
    if result['sync_summary'] is None:
        result['parse_error'] = 'shadow_sync_summary_missing'
    return result


def _read_handoff_artifact(directory) -> dict:
    import json

    result: dict = {'handoff_metadata': None}
    path = directory / HANDOFF_METADATA_FILENAME
    if not path.is_file():
        return result
    try:
        result['handoff_metadata'] = json.loads(
            path.read_text(encoding='utf-8')
        )
    except (OSError, ValueError):
        result['parse_error'] = 'handoff_artifact_unparseable'
    return result


def _read_ledger_artifact(directory) -> dict:
    result: dict = {'ledger_report_filename': None, 'ledger_report': None}
    report = directory / LEDGER_REPORT_FILENAME
    if not report.is_file():
        return {**result, 'parse_error': 'ledger_report_missing'}
    try:
        text = report.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return {**result, 'parse_error': 'ledger_report_unreadable'}
    result['ledger_report_filename'] = report.name
    result['ledger_report'] = parse_ledger_audit_report(text)
    if result['ledger_report'].get('parsed') is not True:
        result['parse_error'] = 'ledger_report_unparseable'
    return result


# ── Ledger audit report parsing ─────────────────────────────────────────────

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
        'evidence_source': SOURCE_INCIDENT,
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

        matched = False
        for key, label in _LEDGER_LABELS.items():
            if stripped.startswith(label):
                parsed[key] = _first_int(stripped[len(label):])
                matched = True
                break
        if matched:
            continue

        for key, label in _GAME_PK_LIST_LABELS.items():
            if stripped.startswith(label):
                parsed[key] = _game_pk_list(stripped[len(label):])
                matched = True
                break
        if matched:
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
            parsed['player_mismatches'].append({
                'player_id': int(player.group('player_id')),
                'name': player.group('name').strip(),
                'latest_stored_appearance': (
                    None if last_stored.lower() == 'never' else last_stored
                ),
            })

    parsed['parsed'] = parsed['expected_games'] is not None
    return parsed


def _publish_verdict(following_lines):
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
    return sorted({int(value) for value in _DIGITS.findall(text)})


# ── Probe-evidence validation ───────────────────────────────────────────────

def evaluate_probe_evidence(proof) -> dict:
    """Validate every probe field that is PRESENT; never invent a failure.

    A missing field is UNPROVEN. A present field that contradicts the contract
    is FAILED. Absence must never mask a violation, and never manufacture one:
    there is no early return, so every present field is checked.
    """
    proof = proof if isinstance(proof, dict) else {}
    failed: list[str] = []
    unproven: list[str] = []

    missing = [field for field in PROBE_EVIDENCE_FIELDS if field not in proof]
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


# ── Scoped content fingerprints ─────────────────────────────────────────────

def fingerprint_scope_plan(unresolved_game_pks=()) -> dict:
    """The exact scope definition, so the artifact can state it explicitly."""
    unresolved = _clean_ints(unresolved_game_pks)
    return {
        SCOPE_EXACT_GAME: {
            'description': f'every table row keyed to game {INCIDENT_GAME_PK}',
            'tables': [
                'scheduled_games', 'game_logs', 'postgame_processed_games',
                'game_ingestion_work_items', 'team_game_pitching_splits',
                'completed_game_contexts', 'game_play_by_play_events',
                'sync_failures', 'pitchers',
            ],
        },
        SCOPE_SLATE: {
            'description': f'slate {INCIDENT_SLATE_DATE.isoformat()}',
            'tables': [
                'scheduled_games', 'game_logs', 'postgame_processed_games',
            ],
        },
        SCOPE_LEDGER_WINDOW: {
            'description': (
                f"appearance-ledger window {INCIDENT_LEDGER['window_start']}"
                f" .. {INCIDENT_LEDGER['window_end']}"
            ),
            'tables': [
                'scheduled_games', 'game_logs', 'postgame_processed_games',
                'game_ingestion_work_items',
            ],
        },
        SCOPE_SNAPSHOTS: {
            'description': (
                f'dashboard snapshots {INCIDENT_SERVING_SNAPSHOT_ID} and '
                f'{INCIDENT_CANDIDATE_SNAPSHOT_ID}'
            ),
            'tables': ['dashboard_snapshots'],
        },
        SCOPE_SYNC_RUN: {
            'description': f'sync run {INCIDENT_SYNC_RUN_ID}',
            'tables': ['sync_runs'],
        },
        SCOPE_UNRESOLVED_GAMES: {
            'description': (
                f'{len(unresolved)} game(s) in the unresolved classification'
            ),
            'tables': [
                'scheduled_games', 'game_logs', 'game_ingestion_work_items',
            ],
            'game_count': len(unresolved),
        },
    }


def scoped_fingerprints(session, *, unresolved_game_pks=()) -> dict | None:
    """Content digests for every scope the incident can touch.

    Each digest covers FULL governed row content and timestamps (``t::text``),
    not row counts, so a same-count edit is still detected. Returns ``None``
    when the digests cannot be computed at all, which the reducer turns into
    UNPROVEN.
    """
    from sqlalchemy import text as sql_text

    bind = session.get_bind()
    if getattr(bind.dialect, 'name', '') != 'postgresql':
        return None

    game_pk = INCIDENT_GAME_PK
    slate = INCIDENT_SLATE_DATE
    window_start = _as_date(INCIDENT_LEDGER['window_start'])
    window_end = _as_date(INCIDENT_LEDGER['window_end'])
    unresolved = _clean_ints(unresolved_game_pks)

    scopes = {
        SCOPE_EXACT_GAME: [
            ('scheduled_games', 'game_pk = :game_pk', {'game_pk': game_pk}),
            ('game_logs', 'mlb_game_pk = :game_pk', {'game_pk': game_pk}),
            ('postgame_processed_games', 'mlb_game_pk = :game_pk',
             {'game_pk': game_pk}),
            ('game_ingestion_work_items', 'mlb_game_pk = :game_pk',
             {'game_pk': game_pk}),
            ('team_game_pitching_splits', 'mlb_game_pk = :game_pk',
             {'game_pk': game_pk}),
            ('completed_game_contexts', 'game_pk = :game_pk',
             {'game_pk': game_pk}),
            ('game_play_by_play_events', 'mlb_game_pk = :game_pk',
             {'game_pk': game_pk}),
            ('sync_failures', 'entity_ref = :game_ref',
             {'game_ref': str(game_pk)}),
            ('pitchers',
             'id IN (SELECT pitcher_id FROM game_logs '
             'WHERE mlb_game_pk = :game_pk)', {'game_pk': game_pk}),
        ],
        SCOPE_SLATE: [
            ('scheduled_games', 'game_date = :slate', {'slate': slate}),
            ('game_logs', 'game_date = :slate', {'slate': slate}),
            ('postgame_processed_games', 'game_date = :slate',
             {'slate': slate}),
        ],
        SCOPE_LEDGER_WINDOW: [
            ('scheduled_games', 'game_date BETWEEN :start AND :end',
             {'start': window_start, 'end': window_end}),
            ('game_logs', 'game_date BETWEEN :start AND :end',
             {'start': window_start, 'end': window_end}),
            ('postgame_processed_games', 'game_date BETWEEN :start AND :end',
             {'start': window_start, 'end': window_end}),
            ('game_ingestion_work_items',
             'represented_date BETWEEN :start AND :end',
             {'start': window_start, 'end': window_end}),
        ],
        SCOPE_SNAPSHOTS: [
            ('dashboard_snapshots', 'id = ANY(:ids)',
             {'ids': [INCIDENT_SERVING_SNAPSHOT_ID,
                      INCIDENT_CANDIDATE_SNAPSHOT_ID]}),
        ],
        SCOPE_SYNC_RUN: [
            ('sync_runs', 'id = :sync_run',
             {'sync_run': INCIDENT_SYNC_RUN_ID}),
        ],
        # An empty unresolved set is a real observation, not a missing scope.
        SCOPE_UNRESOLVED_GAMES: [
            ('scheduled_games', 'game_pk = ANY(:pks)', {'pks': unresolved}),
            ('game_logs', 'mlb_game_pk = ANY(:pks)', {'pks': unresolved}),
            ('game_ingestion_work_items', 'mlb_game_pk = ANY(:pks)',
             {'pks': unresolved}),
        ] if unresolved else [],
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
    """True only when every scope and table digest is identical."""
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
    """Scopes whose content moved. Empty when nothing moved or unknown."""
    if not isinstance(before, dict) or not isinstance(after, dict):
        return []
    return [
        scope for scope in sorted(set(before) | set(after))
        if before.get(scope) != after.get(scope)
    ]


# ── Verdict reducer ─────────────────────────────────────────────────────────

def decide(
    *,
    questions,
    findings,
    read_only_proof,
    artifact_ingestion,
    budget_state,
    identity_failures=(),
    extra_failed=(),
    extra_unproven=(),
) -> dict:
    """Reduce evidence into one verdict and one primary classification.

    ``findings`` is a list of dicts, each carrying a ``classification``, its
    ``supporting_evidence``, its ``counter_evidence``, a ``confidence``, and a
    ``proven`` flag. A finding is eligible to become the primary classification
    only when it is positively proven with real supporting evidence — never
    because some other failure happened to be absent.

    FAILED is reserved for a violation of the AUDIT'S OWN safety contract. A
    platform defect the audit discovers is a successful audit.
    """
    questions = list(questions or [])
    proof = read_only_proof if isinstance(read_only_proof, dict) else {}
    ingestion = (
        artifact_ingestion if isinstance(artifact_ingestion, dict) else {}
    )
    budget = budget_state if isinstance(budget_state, dict) else {}

    failed = list(extra_failed or [])
    unproven = list(extra_unproven or [])

    if identity_failures:
        failed.append(FAILED_INCIDENT_IDENTITY_MISMATCH)
        failed.extend(identity_failures)

    # ── The audit's own safety contract ──────────────────────────────────
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

    # ── Evidence artifacts ───────────────────────────────────────────────
    if ingestion.get('digest_mismatches'):
        failed.append(FAILED_ARTIFACT_DIGEST_MISMATCH)
    if (ingestion.get('incident_validation') or {}).get('any_mismatch'):
        failed.append(FAILED_INCIDENT_IDENTITY_MISMATCH)
    if ingestion.get('missing_required'):
        unproven.append(UNPROVEN_REQUIRED_ARTIFACT_MISSING)
    if ingestion.get('unreadable_required'):
        unproven.append(UNPROVEN_REQUIRED_ARTIFACT_UNREADABLE)

    # ── Source-call budget ───────────────────────────────────────────────
    # Spending an allowance exactly is a completed observation, not a gap. Only
    # a REQUIRED call the budget refused leaves evidence missing.
    if budget.get('required_call_refused'):
        unproven.append(UNPROVEN_SOURCE_BUDGET_EXHAUSTED)

    # A required call that was reserved, dialled and FAILED is missing evidence
    # too. The budget cannot see that — it only knows the reservation succeeded
    # — so a failure is a gap unless a governed fallback positively recovered
    # everything it was bought to obtain.
    if budget.get('required_source_failure') and not budget.get(
        'all_required_evidence_recovered', True
    ):
        unproven.append(UNPROVEN_REQUIRED_SOURCE_CALL_FAILED)

    # ── Questions ────────────────────────────────────────────────────────
    answered = {
        question.get('question_id') for question in questions
        if question.get('answered') is True
    }
    unanswered = [
        question_id for question_id in QUESTION_IDS
        if question_id not in answered
    ]
    if unanswered:
        unproven.append(UNPROVEN_QUESTION_UNANSWERED)

    failed = sorted(set(value for value in failed if value))
    unproven = sorted(set(value for value in unproven if value))

    proven = _proven_findings(findings)
    proven_names = [entry['classification'] for entry in proven]

    if failed:
        result = RESULT_FAILED
        primary = CLASSIFICATION_UNPROVEN
        confidence = CONFIDENCE_HIGH
        contributing: list[str] = []
    elif unproven:
        result = RESULT_UNPROVEN
        primary = CLASSIFICATION_UNPROVEN
        confidence = CONFIDENCE_LOW
        contributing = []
    elif len(proven) > 1:
        result = RESULT_ROOT_CAUSE_IDENTIFIED
        primary = CLASSIFICATION_MULTIPLE_CONTRIBUTING_DEFECTS
        confidence = _confidence(proven)
        contributing = proven_names
    elif len(proven) == 1:
        result = RESULT_ROOT_CAUSE_IDENTIFIED
        primary = proven_names[0]
        confidence = _confidence(proven)
        contributing = []
    elif _genuine_source_gap(findings):
        result = RESULT_NO_PLATFORM_DEFECT_PROVEN
        primary = CLASSIFICATION_NO_PLATFORM_DEFECT_PROVEN
        confidence = CONFIDENCE_MEDIUM
        contributing = []
    else:
        result = RESULT_INCIDENT_NOT_REPRODUCIBLE
        primary = CLASSIFICATION_INCIDENT_CONDITION_NO_LONGER_REPRODUCIBLE
        confidence = CONFIDENCE_LOW
        contributing = []

    return {
        'result': result,
        'exit_code': EXIT_CODES[result],
        'failed_reasons': failed[:MAX_REPORTED_REASON_CODES],
        'unproven_reasons': unproven[:MAX_REPORTED_REASON_CODES],
        'unanswered_question_ids': unanswered,
        'questions_answered': len(QUESTION_IDS) - len(unanswered),
        'questions_total': len(QUESTION_IDS),
        'primary_classification': primary,
        'contributing_classifications': contributing,
        'confidence': confidence,
        'current_condition_persists': _condition_persists(findings, unproven),
        'recommended_next_package': NEXT_PACKAGE_FOR_CLASSIFICATION.get(
            primary, NEXT_ADDITIONAL_EVIDENCE_REQUIRED
        ),
        'recommendation_informational_only': True,
        'recommendation_note': NEXT_PACKAGE_DISCLAIMER,
        'findings': [_finding_view(entry) for entry in (findings or [])],
        'non_authorization_statement': NON_AUTHORIZATION_STATEMENT,
    }


def _proven_findings(findings) -> list[dict]:
    """Only positively proven findings carrying real supporting evidence."""
    proven = [
        entry for entry in (findings or [])
        if entry.get('proven') is True
        and entry.get('classification') in DEFECT_CLASSIFICATIONS
        and entry.get('supporting_evidence')
    ]
    order = {name: index for index, name in enumerate(DEFECT_CLASSIFICATIONS)}
    proven.sort(key=lambda entry: order.get(entry['classification'], 99))
    return proven


def _confidence(proven) -> str:
    levels = {entry.get('confidence') for entry in proven}
    if CONFIDENCE_LOW in levels:
        return CONFIDENCE_LOW
    if CONFIDENCE_MEDIUM in levels:
        return CONFIDENCE_MEDIUM
    return CONFIDENCE_HIGH


def _genuine_source_gap(findings) -> bool:
    return any(
        entry.get('genuine_source_gap') is True for entry in (findings or [])
    )


def _condition_persists(findings, unproven):
    values = {
        entry.get('current_condition_persists')
        for entry in (findings or [])
        if entry.get('current_condition_persists') is not None
    }
    if unproven or not values:
        return 'unproven'
    return True if True in values else False


def _finding_view(entry) -> dict:
    entry = entry or {}
    return {
        'classification': entry.get('classification'),
        'proven': bool(entry.get('proven')),
        'confidence': entry.get('confidence'),
        'supporting_evidence': list(entry.get('supporting_evidence') or ()),
        'counter_evidence': list(entry.get('counter_evidence') or ()),
        'current_condition_persists': entry.get('current_condition_persists'),
        'evidence_sources': list(entry.get('evidence_sources') or ()),
    }


def explanation(decision) -> str:
    result = (decision or {}).get('result')
    if result == RESULT_ROOT_CAUSE_IDENTIFIED:
        return (
            'The audit completed read-only, answered every incident question, '
            'and positively proved at least one platform defect that explains '
            'the failed publication cycle. Naming a cause is not a repair and '
            'authorizes no mutation.'
        )
    if result == RESULT_NO_PLATFORM_DEFECT_PROVEN:
        return (
            'The audit completed read-only and answered every incident '
            'question. Publication was correctly withheld for a genuine '
            'source or data gap; no platform defect was proven. That is a '
            'completed audit, not a clean bill of health for the underlying '
            'baseball data.'
        )
    if result == RESULT_INCIDENT_NOT_REPRODUCIBLE:
        return (
            'The audit completed read-only and answered every incident '
            'question, and current evidence no longer reproduces the incident '
            'condition while retained evidence is insufficient to prove one '
            'root cause. The run artifacts remain the only record of it.'
        )
    if result == RESULT_FAILED:
        return (
            "A violation of the audit's own safety contract was observed. "
            'This is a definite negative result and is never softened by '
            'anything else the audit found.'
        )
    return (
        'Trustworthy evidence could not be completed, so the incident is '
        'unproven. UNPROVEN is not a pass: absent evidence is the state most '
        'easily mistaken for success.'
    )


# ── Small helpers ───────────────────────────────────────────────────────────

def _clean_ints(values) -> list[int]:
    return sorted({
        value for value in (_as_int(entry) for entry in (values or ()))
        if value is not None
    })


def _as_date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value).strip())
    except (TypeError, ValueError):
        return None


def _as_int(value):
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
