"""Matt Festa earned-run correction (2026) — ONE reviewed action, applied once, atomically.

The approved 675-action pitching-line repair committed and is permanently closed. Its ledger
row, its fingerprint, its confirmation phrase, and its entrypoint are untouched by this module
and it is never rerun.

The later read-only closeout found exactly ONE new discrepancy: official scoring credits Matt
Festa with one earned run in game 822952 and the local row carries zero. Everything else about
that line already agrees — five outs, one run, two hits, no walks, two strikeouts, no home
runs — and the rest of the season is exact at 13,300 of 13,301 lines.

This is a SEPARATE, one-time, explicitly reviewed capability. It is not a general repair path:

* It accepts no scope, season, date, team, game, field, value, fingerprint, count, or override
  input. Every governed value is fixed in ``IMMUTABLE_CONTRACT`` below, so a dispatch can
  choose only WHETHER it runs, never WHAT it does.
* It regenerates the planner and refuses unless the manifest fingerprint is byte-for-byte the
  approved one AND every field of the single action matches the reviewed contract exactly.
* It is bound to a fingerprint the generic apply service cannot execute, and it does not make
  scoped plans apply-eligible: the planner still reports ``diagnostic_subset`` and
  ``diagnostic_subset_not_apply_eligible``. This module is the reviewed exception, not a
  loosening of that rule.
* The only baseball-stat mutation it can perform is ``GameLog 44140.earned_runs 0 -> 1``.

A successful apply does NOT close Foundation 3A and opens no gate. The read-only closeout
verification is run later, under separate authorization.
"""

from __future__ import annotations

from datetime import date
import hashlib
from typing import Dict, List, Optional

import sqlalchemy as sa

from models.game_log import GameLog
from models.official_pitching_line_repair_execution import (
    OfficialPitchingLineRepairExecution as RepairExecution,
)
from models.pitcher import Pitcher
from services import official_pitching_line_completeness_2026 as completeness
from services import official_pitching_line_repair_apply_2026 as repair_apply
from services import official_pitching_line_repair_plan_2026 as planner
from services import season_bullpen_aggregation_2026 as aggregation
from services import sync as sync_service
from services.mlb_api import mlb_client
from utils.db import db
from utils.time import utc_now_naive


CAPABILITY = 'official_pitching_line_matt_festa_apply_2026_v1'
APPLY_CONTRACT_VERSION = 'official_pitching_line_matt_festa_apply_2026.v1'
MODE_APPLY = 'apply'

# The reviewed targeted manifest fingerprint. Approved for THIS capability alone.
APPROVED_MATT_FESTA_MANIFEST_FINGERPRINT_2026 = (
    '903766c4d71652d102410d924d1adf2479f21b07a6742e2ce407385a06ac8f2b')

# Deliberately unlike the 675-action phrase: neither can be pasted into the other's workflow.
CONFIRMATION_PHRASE = 'APPLY-2026-MATT-FESTA-ER-903766C4'

# The two-field manifest the planner produced BEFORE the derived-innings correction, when it
# still proposed `innings_pitched 1.66666666666667 -> 1.6666666666666667` alongside the real
# earned-run change. Recorded so it is unmistakably named and unmistakably NOT approved: it
# reviewed a mutation this capability is not permitted to make.
REFUSED_PRE_FIX_MANIFEST_FINGERPRINT_2026 = (
    '257ff3a64261d69908248de81e6c67a83d1e0357241cacab897fe610f91cb838')

RESULT_PASS = repair_apply.RESULT_PASS
RESULT_FAIL = repair_apply.RESULT_FAIL
RESULT_INCONCLUSIVE = repair_apply.RESULT_INCONCLUSIVE
EXIT_BY_RESULT = dict(repair_apply.EXIT_BY_RESULT)

CORRECTION_SOURCE = repair_apply.CORRECTION_SOURCE
EVIDENCE_INVALIDATION_STRICT = True
REQUIRED_EVIDENCE_FAMILIES = repair_apply.REQUIRED_EVIDENCE_FAMILIES
EVIDENCE_FAMILY_COMPLETED = repair_apply.EVIDENCE_FAMILY_COMPLETED
REPAIR_LEDGER_MIGRATION_REVISION = repair_apply.REPAIR_LEDGER_MIGRATION_REVISION
# The schema head THIS capability may observe, kept as its own fact rather than
# reused from the ledger's revision. Until Foundation 3C the two coincided; the
# game-driven ingestion work-state checkpoint (b9d4e17c3a80) then chained onto
# the ledger revision. That migration is purely additive — one new table, and
# none of the tables this repair reads or writes is touched — so the reviewed
# schema is a strict subset of the observed one. "Which migration created the
# ledger" and "which head may this repair run against" are different facts, and
# conflating them made a purely additive migration look like an unreviewed
# schema change. The guard keeps its full strength: an unexpected head still
# refuses the repair, and the post-commit completeness check enforces the same
# head through services/official_pitching_line_completeness_2026.
GOVERNED_SCHEMA_HEAD = 'b9d4e17c3a80'

GATE_BLOCKED = repair_apply.GATE_BLOCKED
DOWNSTREAM_GATES = repair_apply.DOWNSTREAM_GATES

# ── Dedicated advisory lock ───────────────────────────────────────────────────
# A DIFFERENT contract name from the 675-action repair, so the two capabilities take different
# keys and neither can be mistaken for the other's serialization guarantee.
ADVISORY_LOCK_CONTRACT = (
    'official_pitching_line_matt_festa_2026.transaction_advisory_lock')
ADVISORY_LOCK_KEY = int.from_bytes(
    hashlib.sha256(ADVISORY_LOCK_CONTRACT.encode('utf-8')).digest()[:8],
    'big', signed=True)
LOCK_ACQUIRED = repair_apply.LOCK_ACQUIRED
LOCK_UNAVAILABLE = repair_apply.LOCK_UNAVAILABLE
LOCK_SINGLE_WRITER_DIALECT = repair_apply.LOCK_SINGLE_WRITER_DIALECT

# ── Abort reasons ─────────────────────────────────────────────────────────────
ABORT_ALREADY_COMPLETED = 'correction_already_completed_for_this_approved_fingerprint'
ABORT_LOCK_UNAVAILABLE = 'targeted_advisory_lock_unavailable'
ABORT_FINGERPRINT_MISMATCH = 'regenerated_fingerprint_is_not_the_approved_fingerprint'
ABORT_PLAN_CONTRACT = 'regenerated_plan_does_not_match_the_reviewed_contract'
ABORT_ACTION_CONTRACT = 'regenerated_action_does_not_match_the_reviewed_contract'
ABORT_POPULATION = 'current_population_is_not_the_reviewed_single_defect_population'
ABORT_ORIGINAL_REPAIR = 'original_repair_record_does_not_match_its_approved_result'
ABORT_TARGET_ROW = 'target_game_log_does_not_match_the_reviewed_state'
ABORT_DEPENDENT_EVIDENCE = 'dependent_evidence_invalidation_failed'
ABORT_FLOAT_READBACK = 'exact_float_readback_could_not_be_established'
ABORT_PLANNER_SOURCE = 'runtime_planner_source_is_not_the_reviewed_planner_source'
ABORT_VERIFICATION = 'in_transaction_verification_failed'

# ── The immutable reviewed contract ───────────────────────────────────────────
# Every governed value, restated here rather than derived, so nothing outside this module can
# redefine what this capability is permitted to do.
IMMUTABLE_CONTRACT = {
    'capability': CAPABILITY,
    'approved_manifest_fingerprint': APPROVED_MATT_FESTA_MANIFEST_FINGERPRINT_2026,
    'planner_capability': planner.CAPABILITY,
    # The commit at which the reviewed targeted plan and its fingerprint were GENERATED.
    # Not the commit that executes the apply, and not the runtime SHA the planner reports:
    # once this capability merges, the deployed tree is necessarily a later commit.
    'approved_planner_git_sha': 'c4a0b3e4e33d64c5cecea3151ff3c30df7e0c5fa',
    # SHA-256 of the exact bytes of the planner module as they existed at that commit.
    # This is what actually has to hold at runtime: the apply may live at a newer commit,
    # but the planner IMPLEMENTATION that regenerates the manifest must be byte-identical
    # to the one that was reviewed.
    'approved_planner_source_sha256': (
        '65fef8d3d104faf4186005e7602ac871c5eb61f11647690ef230629cfe92668d'),
    'approved_planner_source_path':
        'backend/services/official_pitching_line_repair_plan_2026.py',
    'season': 2026,
    'as_of_date': '2026-07-25',
    'team_id': 114,
    'game_pk': 822952,
    # ── The complete reviewed plan envelope ──────────────────────────────────
    # Not a subset: the whole shape the reviewed plan reported. Anything else is a
    # different plan, whatever its manifest happens to fingerprint to.
    'planner_mode': planner.MODE_READ_ONLY,
    'planner_exit_code': 2,
    'plan_scope': planner.PLAN_SCOPE_SUBSET,
    'plan_status': planner.PLAN_BLOCKED_SUBSET,
    'planner_result': RESULT_INCONCLUSIVE,
    'repair_apply_gate': planner.GATE_BLOCKED_SUBSET,
    # EXACT equality, not membership: an extra reason is a different decision.
    'decision_reasons': [planner.BLOCK_BASELINE_DRIFT],
    'expected_decision_reason': planner.BLOCK_BASELINE_DRIFT,
    'planner_inputs': {
        'season': 2026,
        'as_of_date': '2026-07-25',
        'game_type': planner.REGULAR_SEASON_GAME_TYPE,
        'team_id': 114,
        'game_pk': 822952,
    },
    'blocking_counts_by_reason': {},
    'duplicate_action_ids': [],
    'database_writes_performed': False,
    'migration_head': GOVERNED_SCHEMA_HEAD,
    'amendment_id': 'post_repair_matt_festa_earned_runs_2026',
    'action_counts': {
        planner.ACTION_IDENTITY_CREATE: 0,
        planner.ACTION_GAME_LOG_INSERT: 0,
        planner.ACTION_GAME_LOG_UPDATE: 1,
    },
    'total_action_count': 1,
    'action': {
        'action_id': 'gamelog:update:44140:822952:670036',
        'action_type': planner.ACTION_GAME_LOG_UPDATE,
        'local_game_log_id': 44140,
        'stable_key': '822952:670036:114',
        'mlb_game_pk': 822952,
        'game_date': '2026-07-24',
        'official_mlb_person_id': 670036,
        'local_pitcher_id': 169,
        'official_name': 'Matt Festa',
        'appearance_team_id': 114,
        'official_team_name': 'Cleveland Guardians',
        'official_role': 'relief',
        'changed_fields': ['earned_runs'],
        'current_values': {'earned_runs': 0},
        'proposed_values': {'earned_runs': 1},
        'field_reason': completeness.REASON_EARNED_RUNS_MISMATCH,
        'reason_codes': [completeness.REASON_EARNED_RUNS_MISMATCH],
        'safe_to_apply': True,
        'blocking_reasons': [],
        'dependency_action_ids': [],
        'null_guarded_fields': [],
        'comparison_fingerprint': (
            'cd77ae197a37d37a7622e9708c2b227e64c44e3ec26384d6940083e1c4adf40b'),
        'source_fingerprint': (
            '1daec972ba85b257beaac0b401631b62e4c1f669eb4568ea60d805926a890571'),
    },
    # The complete official mandatory line for the corrected appearance.
    'official_line': {
        'outs': 5, 'runs': 1, 'earned_runs': 1, 'hits': 2,
        'walks': 0, 'strikeouts': 2, 'home_runs': 0,
    },
    # The full-season population this correction was reviewed against.
    'expected_population': {
        'official_games_selected': 1570,
        'official_games_fetched': 1570,
        'official_pitching_lines': 13301,
        'local_pitching_lines': 13301,
        'exact_match_count': 13300,
        'stat_mismatch_count': 1,
        'missing_local_line_count': 0,
        'extra_local_line_count': 0,
        'duplicate_local_line_count': 0,
        'role_mismatch_count': 0,
        'appearance_team_mismatch_count': 0,
        'missing_local_pitcher_identity_count': 0,
    },
    # The population the SAME diagnostic must report after the correction commits: the one
    # defect becomes an exact match and nothing else moves.
    'verified_population': {
        'official_pitching_lines': 13301,
        'local_pitching_lines': 13301,
        'exact_match_count': 13301,
        'stat_mismatch_count': 0,
        'missing_local_line_count': 0,
        'extra_local_line_count': 0,
        'duplicate_local_line_count': 0,
        'role_mismatch_count': 0,
        'appearance_team_mismatch_count': 0,
    },
    # The original repair, which this capability verifies and never touches.
    'original_repair': {
        'approved_manifest_fingerprint': (
            repair_apply.APPROVED_OFFICIAL_PITCHING_LINE_REPAIR_MANIFEST_FINGERPRINT_2026),
        'identity_action_count': 70,
        'insert_action_count': 445,
        'update_action_count': 160,
        'total_action_count': 675,
        'season': 2026,
        'as_of_date': '2026-07-25',
        'amendment_game_log_id': 43765,
        'amendment_hits_allowed': 0,
        'amendment_stat_correction_count': 1,
        'amendment_correction_source': CORRECTION_SOURCE,
    },
}

# The exact stored state the reviewed target row must hold BEFORE the correction.
TARGET_ROW_BEFORE = {
    'id': 44140,
    'mlb_game_pk': 822952,
    'pitcher_id': 169,
    'appearance_team_id': 114,
    'games_started': 0,
    'innings_pitched_outs': 5,
    'runs_allowed': 1,
    'earned_runs': 0,
    'hits_allowed': 2,
    'walks': 0,
    'strikeouts': 2,
    'home_runs_allowed': 0,
}
TARGET_OFFICIAL_PERSON_ID = 670036

# The ONE field this capability may change, and the metadata the correction contract stamps.
APPROVED_MUTABLE_FIELD = 'earned_runs'
APPROVED_VALUE_BEFORE = 0
APPROVED_VALUE_AFTER = 1
CORRECTION_METADATA_FIELDS = (
    'stat_correction_count', 'last_stat_correction_at',
    'last_stat_correction_source', 'last_stat_correction_sync_run_id',
)
# Every stored GameLog field that must be byte-identical afterwards. Stated positively so a
# newly added column cannot quietly escape the guarantee: the snapshot below covers every
# column except the one approved field and the correction metadata.
IMMUTABLE_STAT_FIELDS = (
    'games_started', 'innings_pitched', 'innings_pitched_outs', 'runs_allowed',
    'hits_allowed', 'walks', 'strikeouts', 'home_runs_allowed',
    'pitcher_id', 'mlb_game_pk', 'game_date', 'appearance_team_id',
    'appearance_team_source', 'appearance_team_status', 'appearance_team_reason',
    'opponent', 'opponent_abbreviation',
)
# The approved action writes one integer. No float column may be written at all.
FLOAT_FIELDS = frozenset(
    column.name for column in GameLog.__table__.columns
    if isinstance(column.type, (sa.Float, sa.Numeric)))

POST_COMMIT_CHECKS = (
    'official_pitching_line_completeness_2026',
    'canonical_season_bullpen_aggregation_local_only',
    'canonical_season_bullpen_aggregation_official_validation',
    'original_repair_record_still_intact',
)


class _Abort(Exception):
    """Abort with a typed reason. Never carries a database or network message."""

    def __init__(self, reason, *, result, detail=None):
        super().__init__(reason)
        self.reason = reason
        self.result = result
        self.detail = detail or {}


class _TargetedMutationWatch:
    """ORM-level evidence of everything this transaction actually did.

    The 675-action repair's watch proves the two facts that mattered there — no delete, no
    existing-``Pitcher`` mutation. This capability has to prove more: that exactly ONE
    existing ``GameLog`` changed, that its changed baseball-stat fields were exactly
    ``['earned_runs']``, that nothing but the governed correction metadata was added to that,
    that no OTHER game log moved, and that exactly one ledger row was created. All of it is
    observed from flushed session state rather than asserted by reading the code.
    """

    def __init__(self, session):
        self._session = session
        self.deleted_objects: List[str] = []
        self.mutated_pitcher_ids: List[int] = []
        self.mutated_pitcher_fields: List[str] = []
        self.mutated_game_log_ids: List[int] = []
        self.mutated_game_log_fields: List[str] = []
        self.created_ledger_ids: List[int] = []
        self.created_object_types: List[str] = []
        self._listener = None

    def attach(self):
        def _before_flush(session, flush_context, instances):  # noqa: ARG001
            for obj in session.deleted:
                self.deleted_objects.append(type(obj).__name__)
            for obj in session.new:
                self.created_object_types.append(type(obj).__name__)
                if isinstance(obj, RepairExecution):
                    self.created_ledger_ids.append(id(obj))
            for obj in session.dirty:
                state = sa.inspect(obj)
                changed = sorted(attr.key for attr in state.attrs
                                 if attr.history.has_changes())
                if not changed:
                    continue
                if isinstance(obj, Pitcher):
                    self.mutated_pitcher_ids.append(obj.id)
                    self.mutated_pitcher_fields.extend(changed)
                elif isinstance(obj, GameLog):
                    self.mutated_game_log_ids.append(obj.id)
                    self.mutated_game_log_fields.extend(changed)

        self._listener = _before_flush
        sa.event.listen(self._session, 'before_flush', _before_flush)
        return self

    def detach(self):
        if self._listener is not None:
            sa.event.remove(self._session, 'before_flush', self._listener)
            self._listener = None

    def as_dict(self) -> dict:
        stat_fields = sorted(set(self.mutated_game_log_fields)
                             - set(CORRECTION_METADATA_FIELDS))
        return {
            'mutated_game_log_count': len(set(self.mutated_game_log_ids)),
            'mutated_game_log_ids': sorted(set(self.mutated_game_log_ids)),
            'mutated_game_log_fields': sorted(set(self.mutated_game_log_fields)),
            'mutated_game_log_stat_fields': stat_fields,
            'mutated_game_log_metadata_fields': sorted(
                set(self.mutated_game_log_fields) & set(CORRECTION_METADATA_FIELDS)),
            'created_ledger_row_count': len(set(self.created_ledger_ids)),
            'created_object_types': sorted(set(self.created_object_types)),
            'deleted_object_count': len(self.deleted_objects),
            'deleted_object_types': sorted(set(self.deleted_objects)),
            'mutated_existing_pitcher_count': len(set(self.mutated_pitcher_ids)),
            'mutated_existing_pitcher_fields': sorted(set(self.mutated_pitcher_fields)),
        }

    def checks(self, *, target_log_id) -> dict:
        observed = self.as_dict()
        return {
            'exactly_one_existing_game_log_changed':
                observed['mutated_game_log_ids'] == [target_log_id],
            'changed_baseball_stat_fields_are_exactly_the_approved_field':
                observed['mutated_game_log_stat_fields'] == [APPROVED_MUTABLE_FIELD],
            'only_governed_correction_metadata_was_added':
                set(observed['mutated_game_log_metadata_fields'])
                <= set(CORRECTION_METADATA_FIELDS),
            'no_other_game_log_was_mutated':
                observed['mutated_game_log_count'] == 1,
            'exactly_one_ledger_row_was_created':
                observed['created_ledger_row_count'] == 1,
            'no_delete_occurred': observed['deleted_object_count'] == 0,
            'no_existing_pitcher_row_was_mutated':
                observed['mutated_existing_pitcher_count'] == 0,
        }


def governed_operation_id() -> int:
    """Deterministic operation id for THIS approved fingerprint.

    Masked to 31 bits because the stamped column is a plain Integer. Derived from the targeted
    fingerprint, so the corrected row points back at exactly one approved manifest and never at
    the 675-action repair's operation id.
    """
    digest = hashlib.sha256(
        APPROVED_MATT_FESTA_MANIFEST_FINGERPRINT_2026.encode('utf-8')).digest()
    return int.from_bytes(digest[:4], 'big') & 0x7FFFFFFF


def acquire_targeted_advisory_lock(session) -> dict:
    """Take the dedicated transaction-level advisory lock, without waiting."""
    bind = session.get_bind() if hasattr(session, 'get_bind') else session.bind
    dialect = bind.dialect.name if bind is not None else None
    if dialect != 'postgresql':
        return {'contract': ADVISORY_LOCK_CONTRACT, 'key': ADVISORY_LOCK_KEY,
                'dialect': dialect, 'status': LOCK_SINGLE_WRITER_DIALECT, 'acquired': False}
    acquired = bool(session.execute(
        sa.text('SELECT pg_try_advisory_xact_lock(:key)'),
        {'key': ADVISORY_LOCK_KEY}).scalar())
    return {'contract': ADVISORY_LOCK_CONTRACT, 'key': ADVISORY_LOCK_KEY,
            'dialect': dialect,
            'status': LOCK_ACQUIRED if acquired else LOCK_UNAVAILABLE,
            'acquired': acquired}


def _lock_permits_write(lock) -> bool:
    return lock['status'] in (LOCK_ACQUIRED, LOCK_SINGLE_WRITER_DIALECT)


def _stable_key(action) -> str:
    """The official-evidence identity of an appearance: game, person, team."""
    return (f"{action.get('mlb_game_pk')}:{action.get('official_mlb_person_id')}"
            f":{action.get('official_team_id')}")


# ── Gate 0: the runtime planner must BE the reviewed planner ─────────────────
def planner_source_sha256() -> Optional[str]:
    """SHA-256 of the exact bytes of the planner module that is actually loaded.

    Read from the imported module's own file, so it hashes the implementation this process
    will run rather than a path guessed from the repository layout. No Git command is used:
    a shallow checkout, a detached HEAD, or a missing .git directory must not be able to
    turn this proof into a silent pass.
    """
    path = getattr(planner, '__file__', None)
    if not path:
        return None
    try:
        with open(path, 'rb') as handle:
            return hashlib.sha256(handle.read()).hexdigest()
    except OSError:
        return None


def verify_planner_source() -> dict:
    """Prove the loaded planner implementation is byte-identical to the reviewed one.

    The apply capability necessarily lives at a LATER commit than the plan it applies — once
    this module merges, the deployed tree can never again be the plan-generation commit. So
    the runtime Git SHA is recorded, not required. What is required is that the planner
    SOURCE has not changed: a full-length, constant-shaped comparison of two SHA-256 digests,
    never a prefix match.
    """
    contract = IMMUTABLE_CONTRACT
    approved = contract['approved_planner_source_sha256']
    observed = planner_source_sha256()
    matches = (isinstance(observed, str) and len(observed) == len(approved)
               and observed == approved)
    checks = {
        'planner_source_was_readable': observed is not None,
        'planner_source_matches_the_reviewed_source': matches,
    }
    return {
        'approved_planner_git_sha': contract['approved_planner_git_sha'],
        'approved_planner_source_path': contract['approved_planner_source_path'],
        'approved_planner_source_sha256': approved,
        'observed_planner_source_sha256': observed,
        'planner_source_matches': matches,
        'checks': checks,
        'failed': sorted(name for name, value in checks.items() if not value),
    }


# ── Gate 1: the regenerated plan must be the reviewed plan ───────────────────
def verify_regenerated_plan(plan) -> dict:
    """Byte-for-byte fingerprint equality plus every reviewed plan and action field."""
    contract = IMMUTABLE_CONTRACT
    expected = contract['action']
    manifest = list(plan.get('repair_manifest') or ())
    counts = plan.get('actions_by_type') or {}
    reconciliations = {name: value
                       for name, value in (plan.get('reconciliations') or {}).items()
                       if isinstance(value, bool)}
    action = manifest[0] if len(manifest) == 1 else {}

    checks = {
        'regenerated_fingerprint_equals_the_approved_fingerprint':
            plan.get('repair_manifest_fingerprint')
            == contract['approved_manifest_fingerprint'],
        'planner_capability_matches': plan.get('capability') == contract[
            'planner_capability'],
        'planner_mode_is_read_only': plan.get('mode') == contract['planner_mode'],
        'planner_exit_code_is_the_reviewed_exit_code':
            plan.get('exit_code') == contract['planner_exit_code'],
        # The exact scope the plan was asked for, read back from what the planner itself
        # reports it ran with, so a caller cannot claim one scope and regenerate another.
        'planner_inputs_are_exactly_the_reviewed_inputs':
            {name: (plan.get('inputs') or {}).get(name)
             for name in contract['planner_inputs']} == contract['planner_inputs'],
        'plan_scope_is_the_reviewed_diagnostic_subset':
            plan.get('plan_scope') == contract['plan_scope'],
        'plan_status_is_not_apply_eligible':
            plan.get('plan_status') == contract['plan_status'],
        'planner_result_is_the_reviewed_result':
            plan.get('result') == contract['planner_result'],
        'generic_repair_apply_gate_is_still_blocked_for_a_subset':
            plan.get('repair_apply_gate') == contract['repair_apply_gate'],
        # EXACT equality, not membership. A plan that decided the reviewed thing AND
        # something else did not decide the reviewed thing.
        'decision_reasons_are_exactly_the_reviewed_reasons':
            list(plan.get('decision_reasons') or ()) == contract['decision_reasons'],
        'zero_blocking_reasons_anywhere_in_the_plan':
            dict(plan.get('blocking_counts_by_reason') or {})
            == contract['blocking_counts_by_reason'],
        'no_duplicate_action_ids_reported_by_the_planner':
            list(plan.get('duplicate_action_ids') or ()) == contract[
                'duplicate_action_ids'],
        'migration_head_is_exactly_the_governed_repair_ledger_revision':
            list(plan.get('migration_head') or ()) == [contract['migration_head']],
        'exactly_one_action_planned': len(manifest) == 1,
        'zero_identity_actions':
            counts.get(planner.ACTION_IDENTITY_CREATE) == 0,
        'zero_insertion_actions':
            counts.get(planner.ACTION_GAME_LOG_INSERT) == 0,
        'exactly_one_update_action':
            counts.get(planner.ACTION_GAME_LOG_UPDATE) == 1,
        'total_action_count_is_one':
            plan.get('repair_manifest_action_count') == contract['total_action_count'],
        'no_duplicate_action_ids':
            len({a.get('action_id') for a in manifest}) == len(manifest),
        'every_planner_reconciliation_is_true':
            bool(reconciliations) and all(reconciliations.values()),
        'planner_performed_no_writes':
            plan.get('database_writes_performed') is False,
    }

    # Every reviewed field of the single action, compared exactly.
    action_checks = {
        'action_id': action.get('action_id') == expected['action_id'],
        'action_type': action.get('action_type') == expected['action_type'],
        'local_game_log_id':
            action.get('local_game_log_id') == expected['local_game_log_id'],
        'mlb_game_pk': action.get('mlb_game_pk') == expected['mlb_game_pk'],
        'official_mlb_person_id':
            action.get('official_mlb_person_id') == expected['official_mlb_person_id'],
        'appearance_team_id':
            action.get('official_team_id') == expected['appearance_team_id'],
        'stored_appearance_team_id':
            action.get('appearance_team_id') == expected['appearance_team_id'],
        'local_pitcher_id':
            action.get('local_pitcher_id') == expected['local_pitcher_id'],
        'game_date': action.get('game_date') == expected['game_date'],
        'official_name': action.get('official_name') == expected['official_name'],
        'official_role': action.get('official_role') == expected['official_role'],
        'official_team_name':
            action.get('official_team_name') == expected['official_team_name'],
        'stable_key': _stable_key(action) == expected['stable_key'],
        'changed_fields':
            list(action.get('changed_fields') or ()) == expected['changed_fields'],
        'current_values': dict(action.get('current_values') or {}) == expected[
            'current_values'],
        'proposed_values': dict(action.get('proposed_values') or {}) == expected[
            'proposed_values'],
        'reason_codes':
            list(action.get('reason_codes') or ()) == expected['reason_codes'],
        'field_reason':
            (action.get('field_reason_codes') or {}).get(APPROVED_MUTABLE_FIELD)
            == expected['field_reason'],
        'safe_to_apply': action.get('safe_to_apply') is True,
        'blocking_reasons': list(action.get('blocking_reasons') or ()) == [],
        'dependency_action_ids':
            list(action.get('dependency_action_ids') or ()) == [],
        'null_guarded_fields': list(action.get('null_guarded_fields') or ()) == [],
        'comparison_fingerprint':
            action.get('comparison_fingerprint') == expected['comparison_fingerprint'],
        'source_fingerprint':
            action.get('source_fingerprint') == expected['source_fingerprint'],
    }
    checks['regenerated_action_matches_the_reviewed_contract'] = all(
        action_checks.values())
    return {
        'checks': checks,
        'action_checks': action_checks,
        'failed': sorted(name for name, value in checks.items() if not value),
        'failed_action_fields': sorted(
            name for name, value in action_checks.items() if not value),
        'observed': {
            'regenerated_manifest_fingerprint': plan.get('repair_manifest_fingerprint'),
            'planner_capability': plan.get('capability'),
            'planner_mode': plan.get('mode'),
            'planner_exit_code': plan.get('exit_code'),
            'planner_inputs': {name: (plan.get('inputs') or {}).get(name)
                               for name in contract['planner_inputs']},
            'plan_scope': plan.get('plan_scope'),
            'plan_status': plan.get('plan_status'),
            'planner_result': plan.get('result'),
            'repair_apply_gate': plan.get('repair_apply_gate'),
            'decision_reasons': list(plan.get('decision_reasons') or ()),
            'blocking_counts_by_reason': dict(plan.get('blocking_counts_by_reason') or {}),
            'duplicate_action_ids': list(plan.get('duplicate_action_ids') or ()),
            'database_writes_performed': plan.get('database_writes_performed'),
            'migration_head': list(plan.get('migration_head') or ()),
            'regenerated_planner_git_sha': plan.get('git_sha'),
            'actions_by_type': dict(counts),
            'action_count': plan.get('repair_manifest_action_count'),
        },
        'regenerated_action': action,
    }


# ── Gate 2: the whole season must still be exactly one defect ────────────────
def verify_current_population(diagnostic) -> dict:
    """The reviewed correction is safe only while it is the season's ONLY defect."""
    expected = IMMUTABLE_CONTRACT['expected_population']
    action = IMMUTABLE_CONTRACT['action']
    details = list(diagnostic.get('bounded_details') or ())
    defects = [d for d in details
               if completeness.REASON_EXACT_MATCH not in (d.get('reason_codes') or ())]

    observed = {name: diagnostic.get(name) for name in expected}
    checks = {f'{name}_matches': diagnostic.get(name) == value
              for name, value in expected.items()}
    only = defects[0] if len(defects) == 1 else {}
    checks.update({
        'exactly_one_defect_detail_returned': len(defects) == 1,
        'the_only_defect_is_the_reviewed_game':
            only.get('game_pk') == action['mlb_game_pk'],
        'the_only_defect_is_the_reviewed_official_person':
            only.get('official_pitcher_id') == action['official_mlb_person_id'],
        'the_only_defect_is_the_reviewed_appearance_team':
            (only.get('team_id') == action['appearance_team_id']
             and only.get('local_appearance_team_id') == action['appearance_team_id']),
        'the_only_defect_is_the_reviewed_local_row':
            only.get('local_pitcher_id') == action['local_pitcher_id'],
        'the_only_reason_is_earned_runs_mismatch':
            list(only.get('reason_codes') or ()) == action['reason_codes'],
        'local_earned_runs_is_zero':
            (only.get('local_stats') or {}).get(APPROVED_MUTABLE_FIELD)
            == APPROVED_VALUE_BEFORE,
        'official_earned_runs_is_one':
            (only.get('official_stats') or {}).get(APPROVED_MUTABLE_FIELD)
            == APPROVED_VALUE_AFTER,
        'every_other_official_stat_already_agrees':
            {name: value for name, value in (only.get('official_stats') or {}).items()
             if name != APPROVED_MUTABLE_FIELD}
            == {name: value for name, value in (only.get('local_stats') or {}).items()
                if name != APPROVED_MUTABLE_FIELD},
    })
    return {'checks': checks,
            'failed': sorted(name for name, value in checks.items() if not value),
            'observed': observed,
            'stable_key': f"{only.get('game_pk')}:{only.get('official_pitcher_id')}"
                          f":{only.get('team_id')}" if only else None,
            'defect_detail_count': len(defects)}


# ── Gate 3: the original repair must still be exactly what it was ───────────
def verify_original_repair(session) -> dict:
    """Read-only proof that the 675-action repair record and its amendment are intact."""
    original = IMMUTABLE_CONTRACT['original_repair']
    rows = (session.query(RepairExecution)
            .filter(RepairExecution.approved_manifest_fingerprint
                    == original['approved_manifest_fingerprint'])
            .all())
    completed = [r for r in rows if r.status == RepairExecution.STATUS_COMPLETED]
    checks = {
        'exactly_one_original_ledger_row': len(rows) == 1,
        'exactly_one_completed_original_row': len(completed) == 1,
    }
    observed: Dict[str, object] = {'original_ledger_row_count': len(rows)}
    if len(completed) == 1:
        row = completed[0]
        observed.update({
            'original_execution_ledger_id': int(row.id),
            'identity_action_count': row.identity_action_count,
            'insert_action_count': row.insert_action_count,
            'update_action_count': row.update_action_count,
            'total_action_count': row.total_action_count,
        })
        checks.update({
            'original_regenerated_fingerprint_matches':
                row.regenerated_manifest_fingerprint
                == original['approved_manifest_fingerprint'],
            'original_identity_count_matches':
                row.identity_action_count == original['identity_action_count'],
            'original_insert_count_matches':
                row.insert_action_count == original['insert_action_count'],
            'original_update_count_matches':
                row.update_action_count == original['update_action_count'],
            'original_total_count_matches':
                row.total_action_count == original['total_action_count'],
            'original_season_matches': int(row.season) == original['season'],
            'original_as_of_date_matches':
                row.as_of_date == date.fromisoformat(original['as_of_date']),
        })
    else:
        checks.update({
            'original_regenerated_fingerprint_matches': False,
            'original_identity_count_matches': False,
            'original_insert_count_matches': False,
            'original_update_count_matches': False,
            'original_total_count_matches': False,
            'original_season_matches': False,
            'original_as_of_date_matches': False,
        })

    amendment = (session.query(GameLog)
                 .filter(GameLog.id == original['amendment_game_log_id'])
                 .one_or_none())
    if amendment is None:
        checks['reviewed_amendment_row_exists'] = False
        checks['reviewed_amendment_state_is_intact'] = False
    else:
        observed.update({
            'amendment_hits_allowed': amendment.hits_allowed,
            'amendment_stat_correction_count': amendment.stat_correction_count,
            'amendment_correction_source': amendment.last_stat_correction_source,
        })
        checks['reviewed_amendment_row_exists'] = True
        checks['reviewed_amendment_state_is_intact'] = (
            amendment.hits_allowed == original['amendment_hits_allowed']
            and int(amendment.stat_correction_count or 0)
            == original['amendment_stat_correction_count']
            and amendment.last_stat_correction_source
            == original['amendment_correction_source'])
    return {'checks': checks,
            'failed': sorted(name for name, value in checks.items() if not value),
            'observed': observed}


# ── Gate 4: the target row, under the lock ──────────────────────────────────
def _row_snapshot(log) -> dict:
    """Every stored column except the approved field and the correction metadata."""
    skip = {APPROVED_MUTABLE_FIELD, *CORRECTION_METADATA_FIELDS}
    return {column.name: getattr(log, column.name, None)
            for column in GameLog.__table__.columns if column.name not in skip}


def verify_target_row(session, log, pitcher) -> dict:
    """The reviewed row, in the reviewed state, identified by its official identity."""
    checks = {
        'target_row_exists': log is not None,
        'target_pitcher_row_exists': pitcher is not None,
    }
    observed: Dict[str, object] = {}
    if log is not None:
        observed = {name: getattr(log, name, None) for name in TARGET_ROW_BEFORE}
        for name, value in TARGET_ROW_BEFORE.items():
            checks[f'target_{name}_matches'] = getattr(log, name, None) == value
    else:
        for name in TARGET_ROW_BEFORE:
            checks[f'target_{name}_matches'] = False
    checks['target_official_person_matches'] = (
        pitcher is not None and int(pitcher.mlb_id) == TARGET_OFFICIAL_PERSON_ID)
    if pitcher is not None:
        observed['official_mlb_person_id'] = int(pitcher.mlb_id)
    return {'checks': checks,
            'failed': sorted(name for name, value in checks.items() if not value),
            'observed': observed}


# ── The single atomic entrypoint ────────────────────────────────────────────
def apply_matt_festa_earned_run_correction(
    *,
    generated_at: Optional[str] = None,
    apply_git_sha: Optional[str] = None,
    client=mlb_client,
    session=None,
) -> dict:
    """Regenerate, gate on the exact reviewed contract, then apply ONE field, atomically.

    The signature carries no governed input — no season, date, scope, field, value,
    fingerprint, count, force, or override. Only wiring: two timestamps for the artifact, the
    official-evidence client, and the session.
    """
    session = session or db.session
    contract = IMMUTABLE_CONTRACT
    operation_id = governed_operation_id()
    started_at = utc_now_naive()
    season = int(contract['season'])
    as_of_date = date.fromisoformat(contract['as_of_date'])

    payload = _base_payload(generated_at, apply_git_sha, operation_id, started_at)

    # ── Gate 0: the runtime planner must BE the reviewed planner ─────────────
    # Checked BEFORE regeneration, so a changed planner never even produces a manifest to
    # be compared. The apply may run from a newer commit; the planner code may not differ.
    source = verify_planner_source()
    payload['planner_source_verification'] = source
    payload['approved_planner_source_sha256'] = source['approved_planner_source_sha256']
    payload['observed_planner_source_sha256'] = source['observed_planner_source_sha256']
    payload['planner_source_matches'] = source['planner_source_matches']
    if source['failed']:
        return _finalize_without_writes(payload, ABORT_PLANNER_SOURCE, RESULT_INCONCLUSIVE,
                                        detail={'failed': source['failed']})

    # ── Gate 1: regenerate the reviewed plan, read-only ──────────────────────
    plan = planner.run_repair_plan(
        season=season, as_of_date=as_of_date, preview_limit=100,
        team_id=contract['team_id'], game_pk=contract['game_pk'],
        generated_at=generated_at, client=client, session=session)
    plan_verification = verify_regenerated_plan(plan)
    payload['regenerated_manifest_fingerprint'] = plan.get('repair_manifest_fingerprint')
    payload['planner_verification'] = plan_verification
    payload['regenerated_action'] = plan_verification['regenerated_action']
    # Three DIFFERENT commits, kept as three different facts:
    #   approved   — where the reviewed plan and its fingerprint were generated
    #   regenerated— where the planner ran just now (necessarily later, once this merges)
    #   apply      — the deployed commit executing this correction
    payload['regenerated_planner_git_sha'] = plan.get('git_sha')
    payload['migration_head'] = plan.get('migration_head')
    if plan_verification['failed']:
        reason = (
            ABORT_FINGERPRINT_MISMATCH
            if 'regenerated_fingerprint_equals_the_approved_fingerprint'
            in plan_verification['failed']
            else ABORT_ACTION_CONTRACT
            if 'regenerated_action_matches_the_reviewed_contract'
            in plan_verification['failed']
            else ABORT_PLAN_CONTRACT)
        return _finalize_without_writes(payload, reason, RESULT_INCONCLUSIVE,
                                        detail={'failed': plan_verification['failed'],
                                                'failed_action_fields':
                                                    plan_verification[
                                                        'failed_action_fields']})

    # ── Gate 2: the full current population, read-only ───────────────────────
    diagnostic = completeness.run_diagnostic(
        season=season, as_of_date=as_of_date, detail_limit=100,
        generated_at=generated_at, client=client, session=session)
    population = verify_current_population(diagnostic)
    payload['population_precondition'] = population
    if population['failed']:
        return _finalize_without_writes(payload, ABORT_POPULATION, RESULT_INCONCLUSIVE,
                                        detail={'failed': population['failed']})

    # ── Gate 3: the original repair, read-only and never modified ────────────
    original = verify_original_repair(session)
    payload['original_repair_precondition'] = original
    if original['failed']:
        return _finalize_without_writes(payload, ABORT_ORIGINAL_REPAIR, RESULT_FAIL,
                                        detail={'failed': original['failed']})

    # ── The one mutation transaction ─────────────────────────────────────────
    session.rollback()
    watch = _TargetedMutationWatch(session).attach()
    applied_at = utc_now_naive()
    try:
        lock = acquire_targeted_advisory_lock(session)
        payload['advisory_lock'] = lock
        if not _lock_permits_write(lock):
            raise _Abort(ABORT_LOCK_UNAVAILABLE, result=RESULT_INCONCLUSIVE,
                         detail={'status': lock['status']})

        # One completed execution per approved fingerprint, forever.
        existing = (session.query(RepairExecution)
                    .filter(RepairExecution.approved_manifest_fingerprint
                            == contract['approved_manifest_fingerprint'])
                    .one_or_none())
        if existing is not None:
            raise _Abort(ABORT_ALREADY_COMPLETED, result=RESULT_INCONCLUSIVE,
                         detail={'execution_ledger_id': int(existing.id)})

        rows = (session.query(GameLog)
                .filter(GameLog.id == contract['action']['local_game_log_id'])
                .with_for_update().all())
        log = rows[0] if len(rows) == 1 else None
        pitcher = None
        if log is not None:
            pitcher = (session.query(Pitcher)
                       .filter(Pitcher.id == log.pitcher_id)
                       .with_for_update().one_or_none())
        target = verify_target_row(session, log, pitcher)
        payload['target_row_precondition'] = target
        if target['failed'] or log is None:
            raise _Abort(ABORT_TARGET_ROW, result=RESULT_FAIL,
                         detail={'failed': target['failed']})

        payload['target_row_before'] = dict(target['observed'])
        payload['correction_metadata_before'] = {
            name: _isoformat(getattr(log, name, None)) for name in CORRECTION_METADATA_FIELDS
        }
        untouched_before = _row_snapshot(log)
        prior_correction_count = int(log.stat_correction_count or 0)

        # ── The ONLY approved baseball-stat mutation ─────────────────────────
        setattr(log, APPROVED_MUTABLE_FIELD, APPROVED_VALUE_AFTER)
        log.stat_correction_count = prior_correction_count + 1
        log.last_stat_correction_at = applied_at
        log.last_stat_correction_source = CORRECTION_SOURCE
        log.last_stat_correction_sync_run_id = operation_id
        session.add(log)
        session.flush()

        # Dependent evidence, through the SAME governed strict contract the 675-action
        # repair used, in this transaction, so a rollback removes it with the correction.
        try:
            marked = sync_service._notify_workload_evidence_game_log_correction(
                log, sync_run_id=operation_id, strict=EVIDENCE_INVALIDATION_STRICT,
                session=session)
        except sync_service.WorkloadEvidenceInvalidationError as failure:
            raise _Abort(ABORT_DEPENDENT_EVIDENCE, result=RESULT_FAIL,
                         detail={'failed_families': list(failure.failed_families)}) from failure
        invalidation = _invalidation_record(marked, log_id=int(log.id),
                                            operation_id=operation_id, session=session)
        payload['dependent_evidence_invalidation'] = invalidation
        if invalidation['failed']:
            raise _Abort(ABORT_DEPENDENT_EVIDENCE, result=RESULT_FAIL,
                         detail={'failed': invalidation['failed']})

        # float8 renderings are compared type-exactly below, so the transaction must return
        # the exact stored double. Transaction-scoped only; discarded with the commit.
        float_readback = repair_apply._configure_exact_postgres_float_readback(session)
        payload['float_readback_contract'] = float_readback
        if not float_readback['exact_float_readback_enabled']:
            raise _Abort(ABORT_FLOAT_READBACK, result=RESULT_FAIL,
                         detail={'float_readback_contract': float_readback})

        # ── Direct column readback, bypassing the ORM identity map ───────────
        readback = _direct_readback(session, int(log.id))
        payload['direct_readback'] = readback

        verification = _verify_before_commit(
            readback=readback, untouched_before=untouched_before, log=log,
            prior_correction_count=prior_correction_count, watch=watch,
            operation_id=operation_id, log_id=int(log.id))
        payload['verification_results'] = verification['checks']
        payload['mutation_watch'] = watch.as_dict()
        if verification['failed']:
            raise _Abort(ABORT_VERIFICATION, result=RESULT_FAIL,
                         detail={'failed_verifications': verification['failed']})

        ledger = RepairExecution(
            capability=CAPABILITY,
            approved_manifest_fingerprint=contract['approved_manifest_fingerprint'],
            regenerated_manifest_fingerprint=plan.get('repair_manifest_fingerprint'),
            # The commit where the APPROVED plan was generated. Never the runtime SHA:
            # after this capability merges, the deployed tree is always a later commit,
            # and writing that here would silently redefine what the column means.
            planner_git_sha=contract['approved_planner_git_sha'],
            apply_git_sha=apply_git_sha,
            season=season,
            as_of_date=as_of_date,
            accepted_baseline_version='v2',
            amendment_id=contract['amendment_id'],
            status=RepairExecution.STATUS_COMPLETED,
            identity_action_count=0,
            insert_action_count=0,
            update_action_count=1,
            total_action_count=1,
            started_at=started_at,
            completed_at=applied_at,
            committed_at=applied_at,
            execution_summary={
                'governed_operation_id': operation_id,
                'correction_source': CORRECTION_SOURCE,
                'advisory_lock': {key: lock[key] for key in ('contract', 'status')},
                'corrected_game_log_id': contract['action']['local_game_log_id'],
                'changed_fields': [APPROVED_MUTABLE_FIELD],
                # The runtime SHA the fresh planner reported, retained here rather than in
                # planner_git_sha so the durable column keeps its reviewed meaning.
                'regenerated_planner_git_sha': plan.get('git_sha'),
                'approved_planner_source_sha256': source[
                    'approved_planner_source_sha256'],
                'observed_planner_source_sha256': source[
                    'observed_planner_source_sha256'],
            },
            precondition_summary={
                'planner_checked': len(plan_verification['checks']), 'planner_failed': [],
                'population_checked': len(population['checks']), 'population_failed': [],
                'original_repair_checked': len(original['checks']),
                'original_repair_failed': [],
                'target_row_checked': len(target['checks']), 'target_row_failed': [],
            },
            verification_summary={
                'checked': len(verification['checks']), 'failed': [],
                'stable_key': contract['action']['stable_key'],
            },
        )
        session.add(ledger)
        session.flush()
        # Re-evaluated AFTER the ledger flush, so "exactly one ledger row was created" is
        # observed rather than assumed, and every earlier guarantee is re-proven against the
        # complete transaction rather than a prefix of it.
        watch_checks = watch.checks(target_log_id=int(log.id))
        watch_checks['ledger_counts_match_the_reviewed_contract'] = (
            ledger.total_action_count == contract['total_action_count']
            and ledger.update_action_count == 1
            and ledger.identity_action_count == 0
            and ledger.insert_action_count == 0)
        watch_checks['ledger_records_the_dedicated_capability'] = (
            ledger.capability == CAPABILITY)
        watch_checks['ledger_records_the_approved_fingerprint'] = (
            ledger.approved_manifest_fingerprint
            == contract['approved_manifest_fingerprint'])
        payload['verification_results'] = dict(verification['checks'], **watch_checks)
        payload['mutation_watch'] = watch.as_dict()
        failed_watch = sorted(name for name, value in watch_checks.items() if not value)
        if failed_watch:
            raise _Abort(ABORT_VERIFICATION, result=RESULT_FAIL,
                         detail={'failed_verifications': failed_watch})

        session.commit()
        # The authoritative committed id, read from the row rather than assumed.
        payload['execution_ledger_id'] = int(ledger.id)
        payload['execution_ledger_row'] = {
            'id': int(ledger.id), 'capability': ledger.capability,
            'approved_manifest_fingerprint': ledger.approved_manifest_fingerprint,
            'regenerated_manifest_fingerprint': ledger.regenerated_manifest_fingerprint,
            'status': ledger.status, 'season': ledger.season,
            'as_of_date': ledger.as_of_date.isoformat() if ledger.as_of_date else None,
            'accepted_baseline_version': ledger.accepted_baseline_version,
            'amendment_id': ledger.amendment_id,
            'identity_action_count': ledger.identity_action_count,
            'insert_action_count': ledger.insert_action_count,
            'update_action_count': ledger.update_action_count,
            'total_action_count': ledger.total_action_count,
            'started_at': _isoformat(ledger.started_at),
            'completed_at': _isoformat(ledger.completed_at),
            'committed_at': _isoformat(ledger.committed_at),
        }
        payload['transaction_committed'] = True
        payload['database_writes_performed'] = True
        payload['target_row_after'] = readback['stored']
        payload['correction_metadata_after'] = readback['correction_metadata']
    except _Abort as abort:
        session.rollback()
        payload['rollback_performed'] = True
        return _finalize_without_writes(payload, abort.reason, abort.result,
                                        detail=abort.detail)
    except Exception as exc:  # noqa: BLE001 — never leak a database or network message
        session.rollback()
        payload['rollback_performed'] = True
        payload['error_type'] = type(exc).__name__
        return _finalize_without_writes(payload, ABORT_VERIFICATION, RESULT_FAIL)
    finally:
        watch.detach()

    # ── Post-commit verification. Always. No rollback, no retry. ─────────────
    post = None
    try:
        post = run_post_commit_verification(
            season=season, as_of_date=as_of_date, generated_at=generated_at,
            client=client, session=session)
    except Exception as exc:  # noqa: BLE001 — a check that could not run has not passed
        payload['error_type'] = type(exc).__name__
    payload['post_commit_verification'] = post
    failed = sorted((post or {}).get('failed_checks') or ())
    not_executed = sorted((post or {}).get('not_executed_checks') or ())
    if failed or not_executed or post is None:
        payload['result'] = RESULT_FAIL
        payload['exit_code'] = EXIT_BY_RESULT[RESULT_FAIL]
        payload['decision_reasons'] = ['post_commit_verification_failed']
        payload['failed_checks'] = failed
        payload['unresolved_issues'] = sorted(set(failed) | set(not_executed))
        return payload

    payload['result'] = RESULT_PASS
    payload['exit_code'] = EXIT_BY_RESULT[RESULT_PASS]
    payload['decision_reasons'] = ['reviewed_matt_festa_correction_applied_and_verified']
    return payload


def _isoformat(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def _invalidation_record(marked, *, log_id, operation_id, session) -> dict:
    families = (marked or {}).get('families') or {}
    record = {
        'local_game_log_id': log_id,
        'marked_count': int((marked or {}).get('marked_count') or 0),
        'evidence_object_count': len((marked or {}).get('evidence_ids') or ()),
        'rows_invalidated': 1,
        'registered_families': sorted((marked or {}).get('registered_families') or ()),
        'families': {
            name: {'status': item.get('status'),
                   'exhaustive': item.get('exhaustive'),
                   'marked_count': item.get('marked_count'),
                   'batch_count': item.get('batch_count'),
                   'remaining_current_dependency_count': item.get(
                       'remaining_current_dependency_count')}
            for name, item in sorted(families.items())
        },
        'failed_families': sorted((marked or {}).get('failed_families') or ()),
        'all_required_families_completed': (marked or {}).get(
            'all_required_families_completed'),
        'exhaustive': (marked or {}).get('exhaustive'),
        'final_unscoped_current_dependency_count': (marked or {}).get(
            'final_unscoped_current_dependency_count'),
        'final_unscoped_residual_rule_ids': sorted(
            (marked or {}).get('final_unscoped_residual_rule_ids') or ()),
    }
    checks = {
        'every_required_family_was_attempted':
            sorted(families) == sorted(REQUIRED_EVIDENCE_FAMILIES),
        'every_registered_family_is_the_governed_registry':
            record['registered_families'] == sorted(REQUIRED_EVIDENCE_FAMILIES),
        'invalidation_reported_all_required_families_completed':
            record['all_required_families_completed'] is True,
        'invalidation_reported_itself_exhaustive': record['exhaustive'] is True,
        'every_family_completed':
            bool(families) and all(item.get('status') == EVIDENCE_FAMILY_COMPLETED
                                   for item in families.values()),
        'every_family_is_exhaustive':
            bool(families) and all(item.get('exhaustive') is True
                                   for item in families.values()),
        'every_family_has_zero_remaining_dependencies':
            all(item.get('remaining_current_dependency_count') == 0
                for item in families.values()),
        'zero_failed_families': not record['failed_families'],
        'result_belongs_to_this_row': (marked or {}).get('game_log_id') == log_id,
        'result_carries_the_governed_operation_id':
            (marked or {}).get('sync_run_id') == operation_id,
        'result_used_this_transaction':
            (marked or {}).get('session_id') == id(session),
        'no_unregistered_residual_dependency_remains':
            (marked or {}).get('all_direct_game_log_dependencies_exhausted') is True
            and not record['final_unscoped_residual_rule_ids'],
        'final_unscoped_dependency_count_is_zero':
            record['final_unscoped_current_dependency_count'] == 0,
    }
    record['checks'] = checks
    record['failed'] = sorted(name for name, value in checks.items() if not value)
    return record


def _direct_readback(session, log_id) -> dict:
    """An explicit column SELECT, so the identity map cannot answer for the database."""
    columns = GameLog.__table__.c
    wanted = sorted({APPROVED_MUTABLE_FIELD, *TARGET_ROW_BEFORE,
                     *IMMUTABLE_STAT_FIELDS, *CORRECTION_METADATA_FIELDS} - {'id'})
    row = session.execute(
        sa.select(columns['id'], *[columns[name] for name in wanted])
        .where(columns['id'] == log_id)).mappings().one_or_none()
    stored = dict(row) if row is not None else {}
    return {
        'row_present': row is not None,
        'stored': {name: _isoformat(value) for name, value in stored.items()
                   if name not in CORRECTION_METADATA_FIELDS},
        'correction_metadata': {name: _isoformat(stored.get(name))
                                for name in CORRECTION_METADATA_FIELDS},
        'raw': stored,
    }


def _verify_before_commit(*, readback, untouched_before, log, prior_correction_count,
                          watch, operation_id, log_id) -> dict:
    """Prove every mutation AND every non-mutation, from the database's own values."""
    stored = readback['raw']
    same = repair_apply._same_governed_value
    watch_checks = watch.checks(target_log_id=log_id)
    # The ledger has not been added yet at this point; it is proven separately, after its
    # own flush, so a passing check here can never stand in for one that has not happened.
    watch_checks.pop('exactly_one_ledger_row_was_created', None)
    checks = {
        'target_row_read_back': readback['row_present'],
        # Type-exact: the stored value is the integer 1, not 1.0 and not "1".
        'earned_runs_is_exactly_one':
            same(stored.get(APPROVED_MUTABLE_FIELD), APPROVED_VALUE_AFTER),
        'correction_count_delta_is_exactly_one':
            same(stored.get('stat_correction_count'), prior_correction_count + 1),
        'correction_source_is_the_governed_source':
            stored.get('last_stat_correction_source') == CORRECTION_SOURCE,
        'correction_timestamp_is_populated':
            stored.get('last_stat_correction_at') is not None,
        'governed_operation_id_is_stamped':
            same(stored.get('last_stat_correction_sync_run_id'), operation_id),
        # Every other stored column is byte-identical to its pre-mutation snapshot.
        'every_untouched_field_is_unchanged':
            _row_snapshot(log) == untouched_before,
        # No float field is written by this capability at all.
        'no_float_field_was_written':
            not (set(watch.mutated_game_log_fields) & FLOAT_FIELDS),
        **watch_checks,
    }
    # Each immutable stat, compared type-exactly against its own pre-state. Both sides are
    # raw stored values, so a type disagreement is a real disagreement.
    for name in IMMUTABLE_STAT_FIELDS:
        if name in stored:
            checks[f'{name}_is_unchanged'] = same(
                stored.get(name), untouched_before.get(name))
    return {'checks': checks,
            'failed': sorted(name for name, value in checks.items() if not value)}


# ── Post-commit verification ────────────────────────────────────────────────
def run_post_commit_verification(*, season, as_of_date, generated_at=None,
                                 client=mlb_client, session=None) -> dict:
    """Read-only checks that must hold after the correction commits."""
    session = session or db.session
    results: Dict[str, dict] = {}

    try:
        diagnostic = completeness.run_diagnostic(
            season=season, as_of_date=as_of_date, detail_limit=0,
            generated_at=generated_at, client=client, session=session)
        expected = IMMUTABLE_CONTRACT['verified_population']
        checks = {
            'result_is_pass': diagnostic.get('result') == completeness.RESULT_PASS,
            'exit_code_is_zero': diagnostic.get('exit_code') == 0,
        }
        checks.update({f'{name}_matches_the_verified_population':
                       diagnostic.get(name) == value
                       for name, value in expected.items()})
        results[POST_COMMIT_CHECKS[0]] = _executed(
            all(checks.values()), checks=checks, result=diagnostic.get('result'),
            observed={name: diagnostic.get(name) for name in expected})
    except Exception as exc:  # noqa: BLE001
        results[POST_COMMIT_CHECKS[0]] = _not_executed(exc)

    for index, official in ((1, False), (2, True)):
        try:
            audit = aggregation.run_aggregation(
                season=season, as_of_date=as_of_date,
                include_official_validation=official, team_detail_limit=0,
                mismatch_detail_limit=0, generated_at=generated_at, client=client,
                session=session)
            local = audit.get('local_aggregation') or {}
            validation = audit.get('official_validation') or {}
            reconciliation = repair_apply.evaluate_mode_reconciliations(
                audit.get('reconciliations') or {}, include_official_validation=official)
            checks = {
                'result_is_pass': audit.get('result') == aggregation.RESULT_PASS,
                'exit_code_is_zero': audit.get('exit_code') == 0,
                'every_applicable_reconciliation_holds': reconciliation['satisfied'],
                'thirty_complete_teams': local.get('teams_complete') == 30,
                'zero_partial_teams': local.get('teams_partial') == 0,
                'zero_unavailable_teams': local.get('teams_unavailable') == 0,
            }
            if official:
                checks.update({
                    'all_thirty_teams_matched': validation.get('teams_matched') == 30,
                    'zero_teams_mismatched': validation.get('teams_mismatched') == 0,
                    'zero_mandatory_metric_mismatches':
                        validation.get('mandatory_metric_mismatches') == 0,
                    'zero_unavailable_official_evidence':
                        validation.get('unavailable_evidence_count') == 0,
                    'zero_missing_unique_starters':
                        validation.get('official_games_missing_unique_starter') == 0,
                    'zero_multiple_starter_contradictions':
                        validation.get('official_games_with_multiple_starters') == 0,
                })
            results[POST_COMMIT_CHECKS[index]] = _executed(
                all(checks.values()), checks=checks, result=audit.get('result'),
                reconciliations=reconciliation)
        except Exception as exc:  # noqa: BLE001
            results[POST_COMMIT_CHECKS[index]] = _not_executed(exc)

    try:
        original = verify_original_repair(session)
        results[POST_COMMIT_CHECKS[3]] = _executed(
            not original['failed'], checks=original['checks'],
            observed=original['observed'])
    except Exception as exc:  # noqa: BLE001
        results[POST_COMMIT_CHECKS[3]] = _not_executed(exc)

    executed = [name for name in POST_COMMIT_CHECKS
                if (results.get(name) or {}).get('executed') is True]
    return {
        'checks': results,
        'passed': all((results.get(name) or {}).get('passed') is True
                      for name in POST_COMMIT_CHECKS),
        'failed_checks': sorted(name for name in executed
                                if not results[name].get('passed')),
        'executed_checks': executed,
        'not_executed_checks': [name for name in POST_COMMIT_CHECKS
                                if name not in executed],
    }


def _executed(passed, **payload) -> dict:
    return {'executed': True, 'execution_state': repair_apply.CHECK_EXECUTED,
            'passed': bool(passed), **payload}


def _not_executed(exc) -> dict:
    return {'executed': False, 'execution_state': repair_apply.CHECK_NOT_EXECUTED,
            'passed': False, 'checks': {}, 'error_type': type(exc).__name__}


def _base_payload(generated_at, apply_git_sha, operation_id, started_at) -> dict:
    return {
        'capability': CAPABILITY,
        'mode': MODE_APPLY,
        'result': RESULT_INCONCLUSIVE,
        'exit_code': EXIT_BY_RESULT[RESULT_INCONCLUSIVE],
        'generated_at': generated_at,
        'started_at': started_at.isoformat(),
        # Three separate provenance facts, never collapsed into one field.
        'apply_git_sha': apply_git_sha or completeness._git_sha(),
        'approved_planner_git_sha': IMMUTABLE_CONTRACT['approved_planner_git_sha'],
        'regenerated_planner_git_sha': None,
        'approved_planner_source_sha256': IMMUTABLE_CONTRACT[
            'approved_planner_source_sha256'],
        'observed_planner_source_sha256': None,
        'planner_source_matches': False,
        'planner_source_verification': {},
        'migration_head': None,
        'contracts': {
            'apply_contract_version': APPLY_CONTRACT_VERSION,
            'planner_contract_version': planner.PLAN_CONTRACT_VERSION,
            'advisory_lock_contract': ADVISORY_LOCK_CONTRACT,
            'correction_source': CORRECTION_SOURCE,
            'post_commit_checks': list(POST_COMMIT_CHECKS),
        },
        'immutable_approved_contract': _jsonable(IMMUTABLE_CONTRACT),
        'approved_manifest_fingerprint': APPROVED_MATT_FESTA_MANIFEST_FINGERPRINT_2026,
        'regenerated_manifest_fingerprint': None,
        'governed_operation_id': operation_id,
        'planner_verification': {},
        'regenerated_action': {},
        'population_precondition': {},
        'original_repair_precondition': {},
        'target_row_precondition': {},
        'target_row_before': {},
        'correction_metadata_before': {},
        'advisory_lock': None,
        'float_readback_contract': {},
        'mutation_watch': {},
        'dependent_evidence_invalidation': {},
        'direct_readback': {},
        'verification_results': {},
        'transaction_committed': False,
        'rollback_performed': False,
        'database_writes_performed': False,
        'target_row_after': {},
        'correction_metadata_after': {},
        'execution_ledger_id': None,
        'execution_ledger_row': None,
        'post_commit_verification': None,
        'failed_checks': [],
        'unresolved_issues': [],
        'decision_reasons': [],
        # A successful correction does NOT close Foundation 3A and opens no gate.
        **{gate: GATE_BLOCKED for gate in DOWNSTREAM_GATES},
        'downstream_gate_statuses': {gate: GATE_BLOCKED for gate in DOWNSTREAM_GATES},
    }


def _jsonable(value):
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _finalize_without_writes(payload, reason, result, detail=None) -> dict:
    payload['result'] = result
    payload['exit_code'] = EXIT_BY_RESULT[result]
    payload['decision_reasons'] = [reason]
    payload['abort_detail'] = detail or {}
    payload['unresolved_issues'] = [reason]
    payload['transaction_committed'] = False
    payload['database_writes_performed'] = False
    payload['execution_ledger_id'] = None
    for gate in DOWNSTREAM_GATES:
        payload[gate] = GATE_BLOCKED
    payload['downstream_gate_statuses'] = {gate: GATE_BLOCKED for gate in DOWNSTREAM_GATES}
    return payload
