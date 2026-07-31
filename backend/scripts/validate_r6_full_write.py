#!/usr/bin/env python
"""Validate the Foundation 3C R6 full remaining-window write.

R6 completes the bootstrap: one fingerprint-authorized write over the entire
remaining 99-game scope, moving completeness from 10/99 to 109/0. It may change
governed ingestion control state and nothing else.

Three things this validator refuses to do:

  * It never infers authorization from an exit code. The write report must
    carry the expected fingerprint AND the recomputed authorized fingerprint,
    and both must equal the founder-approved value. Exit zero is not evidence
    that the comparison ever happened.
  * It never accepts a stale or wrong-shaped authorization. The contract-3 R3
    value, the contract-4 R4 five-game value, and the scope-set digest are all
    explicitly rejected — the digest especially, because it is a scope proof
    and not a reconciliation-plan fingerprint at all.
  * It never trusts an aggregate alone. Row totals, ignored-difference totals,
    and appearance identities are recomputed from the per-row detail, because
    an aggregate is exactly what a bug would get right while the detail
    disagreed.

Partial completion is FAILED. The canonical writer commits per game, so a run
that dies at game 50 leaves 49 durable checkpoints. That state is reported
honestly and stops the rollout — it is never retried and never compensated.

Output is safe structured evidence only: game ids, MLB ids, counts, statuses,
field names, and hashes. No credentials, connection strings, payloads, headers,
filesystem paths, or exception text.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import r5_remaining_window_scope as scope  # noqa: E402
from services import game_log_reconciliation as reconciliation  # noqa: E402
from services import pitcher_identity_reconciliation as identity  # noqa: E402
from models.game_ingestion_work_item import GameIngestionWorkItem  # noqa: E402


EXIT_OK = 0
EXIT_FAILED = 1

RESULT_PASS = 'pass'
RESULT_FAILED = 'failed'

REFERENCE_DATE = scope.REFERENCE_DATE
APPROVED_ORDER = scope.CANONICAL_ORDER
APPROVED_SET = scope.SORTED_SET
COMPLETED_GAME_PKS = scope.COMPLETED_GAME_PKS
EXPECTED_GAME_COUNT = scope.EXPECTED_GAME_COUNT              # 99
EXPECTED_TOTAL_ROWS = scope.EXPECTED_TOTAL_ROWS              # 865
EXPECTED_TOTAL_IGNORED = scope.EXPECTED_TOTAL_IGNORED        # 291
SCOPE_DIGEST = scope.SCOPE_DIGEST

# ── Authorization ───────────────────────────────────────────────────────────
# The ONLY value that may authorize the R6 write. Reviewed by the founder from
# the R5 production run.
APPROVED_FINGERPRINT = (
    '40659a4051226df40ef7cedbca7a6bc2689d5c2bfbdd4ccdb717fc6fc0c79343'
)

# Values that must NEVER authorize R6. Present here so the rejection is
# testable, and nowhere in any executable command.
STALE_CONTRACT_3_FINGERPRINT = (
    '2a06f7e5b1aad853c6280ae3488a88f39ba0402cfb0b8044f0ba75d7be20c239'
)
R4_FIVE_GAME_FINGERPRINT = (
    '08bf16bc730ffe4c5c024c8e1dbc000d017a1a4956878f49a988fb22a1e4adda'
)
# The scope digest proves WHICH GAMES are included. It is not a
# reconciliation-plan fingerprint and must never be accepted as one — they are
# both 64 hex characters, which is exactly why this needs to be explicit.
REJECTED_AUTHORIZATION_VALUES = frozenset({
    STALE_CONTRACT_3_FINGERPRINT,
    R4_FIVE_GAME_FINGERPRINT,
    SCOPE_DIGEST,
})

EXPECTED_PARITY_CONTRACT_VERSION = '4'

# ── Production state, before and after ──────────────────────────────────────
BEFORE_COMPLETENESS = {
    'expected_final_games': 109,
    'completed_final_games': 10,
    'unresolved_final_games': 99,
    'terminal_failure_games': 0,
    'correction_pending_games': 0,
    'publication_complete': False,
}
AFTER_COMPLETENESS = {
    'expected_final_games': 109,
    'completed_final_games': 109,
    'unresolved_final_games': 0,
    'terminal_failure_games': 0,
    'correction_pending_games': 0,
    'publication_complete': True,
}

# The completeness object's own durable appearance ledger after a complete
# bootstrap: 38 (original five) + 43 (R4 five) + 865 (R6 99) = 946 rows across
# the 109 final games. These are the real field names on the object, not
# invented ones.
EXPECTED_RECONCILED_APPEARANCE_ROWS = 946

PROHIBITED_SEMANTIC_FIELDS = frozenset(reconciliation.DERIVED_COMPANION_FIELDS)
FORBIDDEN_IDENTITY_ACTIONS = frozenset(
    set(identity.MUTATING_ACTIONS)
    | set(identity.RETIRED_WRITE_ACTIONS)
    | {identity.ACTION_BLOCKED}
)

# The exact field set `identity.suppressed_current_state_fields` can emit.
APPROVED_SUPPRESSIBLE_FIELDS = frozenset({
    'active', 'full_name', 'position', 'roster_status', 'team_abbreviation',
    'team_id', 'team_name',
})

FINGERPRINT_PATTERN = re.compile(r'^[0-9a-f]{64}$')

# Baseball-data families that must be byte-identical across the whole run.
IMMUTABLE_STATE_HASHES = (
    'game_log_content_hash',
    'canonical_outs_hash',
    'correction_provenance_hash',
    'appearance_team_hash',
    'pitcher_state_hash',
)

# Exclusive scope short-circuits every candidate to the explicit reason.
EXPECTED_CANDIDATE_REASON = GameIngestionWorkItem.REASON_EXPLICIT_REPAIR

TRANSACTION_BOUNDARY = (
    'per_game: the canonical writer commits once per game inside '
    '_process_one_game, so 99-game atomicity does not exist and is not '
    'claimed. Partial completion is durable, is detected, and is reported as '
    'FAILED — never retried and never compensated.'
)

NEXT_ACTION_PASS = (
    'Implement Stage E rollout closeout. Verify the complete 109-game '
    'bootstrap, remove temporary Foundation 3C rollout workflows, document the '
    'final production state, and separately decide whether to enable any '
    'automated or authoritative lane.'
)
NEXT_ACTION_FAILED = (
    'Stop Foundation 3C. Do not retry R6, remove workflows, or enable any lane '
    'without founder review.'
)


class ValidationFailure(Exception):
    """One named invariant did not hold. R6 stops here."""

    def __init__(self, invariant, expected, observed, phase=None, game_pk=None,
                 pitcher_mlb_id=None):
        super().__init__(invariant)
        self.invariant = invariant
        self.expected = expected
        self.observed = observed
        self.phase = phase
        self.game_pk = game_pk
        self.pitcher_mlb_id = pitcher_mlb_id


def _require(invariant, expected, observed, **context):
    if observed != expected:
        raise ValidationFailure(invariant, expected, observed, **context)


def _require_true(invariant, observed, **context):
    _require(invariant, True, bool(observed), **context)


def _require_fingerprint(invariant, value, **context):
    if not isinstance(value, str) or not FINGERPRINT_PATTERN.match(value):
        raise ValidationFailure(
            invariant, 'a 64-character lowercase sha256 hex digest',
            'absent' if not value else 'malformed', **context,
        )
    return value


def _load(path, invariant):
    target = Path(path) if path else None
    if target is None or not target.exists():
        raise ValidationFailure(invariant, 'present', 'missing')
    try:
        return json.loads(target.read_text(encoding='utf-8'))
    except Exception:  # noqa: BLE001 - the parse failure itself is the signal
        raise ValidationFailure(invariant, 'json', 'unparsable')


# ── Before state ────────────────────────────────────────────────────────────


def validate_before_state(before) -> dict:
    """Production must still be exactly 10 completed / 99 unresolved.

    This is also what makes R6 single-use: after a successful run the selected
    games all carry work items, so a second dispatch fails here and never
    reaches the write.
    """
    if not isinstance(before, dict):
        raise ValidationFailure('before_state_is_an_object', 'object',
                                type(before).__name__, phase='before')
    _require('before_state_phase', 'before', before.get('phase'),
             phase='before')
    _require_true('before_state_read_only',
                  (before.get('read_only') or {}).get('write_probe_refused'),
                  phase='before')
    _require('before_state_reference_date', REFERENCE_DATE,
             before.get('reference_date'), phase='before')

    _require('before_state_selected_game_count', EXPECTED_GAME_COUNT,
             before.get('selected_game_count'), phase='before')
    _require('before_state_selected_game_pks', list(APPROVED_SET),
             sorted(before.get('selected_game_pks') or []), phase='before')
    _require('before_state_scope_digest', SCOPE_DIGEST,
             before.get('selected_scope_digest'), phase='before')
    _require('before_state_approved_completed_game_pks',
             list(COMPLETED_GAME_PKS),
             sorted(before.get('approved_completed_game_pks') or []),
             phase='before')

    completeness = dict(before.get('publication_completeness') or {})
    for field, expected in BEFORE_COMPLETENESS.items():
        observed = completeness.get(field)
        if field == 'publication_complete':
            observed = bool(observed)
        _require(f'before_state_completeness_{field}', expected, observed,
                 phase='before')

    _require('before_state_completed_work_item_set', list(COMPLETED_GAME_PKS),
             sorted(before.get('completed_work_item_set') or []), phase='before')
    _require('before_state_unresolved_set', list(APPROVED_SET),
             sorted(before.get('unresolved_set') or []), phase='before')
    _require('before_state_terminal_work_item_set', [],
             sorted(before.get('terminal_work_item_set') or []), phase='before')
    _require('before_state_total_work_item_count', 10,
             before.get('all_work_item_count'), phase='before')

    work_items = dict(before.get('selected_work_items') or {})
    if work_items:
        raise ValidationFailure(
            'before_state_selected_games_have_no_work_item', 0,
            len(work_items), phase='before',
            game_pk=sorted(int(pk) for pk in work_items)[:20],
        )
    _require('before_state_selected_work_item_count', 0,
             before.get('selected_work_item_count'), phase='before')

    for field in (
        'non_critical_selected_game_pks',
        'unplanned_selected_game_pks',
        'non_final_selected_game_pks',
        'selected_game_pks_with_prior_status',
        'selected_game_pks_with_prior_attempts',
        'selected_terminal_set',
        'duplicate_selected_game_pks',
    ):
        if field not in before:
            raise ValidationFailure(f'before_state_{field}_present', 'present',
                                    'missing', phase='before')
        _require(f'before_state_{field}', [], sorted(before.get(field) or []),
                 phase='before')

    _require('before_state_finality_conflicts', 0,
             before.get('finality_conflicts'), phase='before')
    _require('before_state_schedule_authority_missing', 0,
             before.get('schedule_authority_missing'), phase='before')
    _require('before_state_dead_letter_count', 0,
             before.get('dead_letter_count'), phase='before')

    return {
        'completed_final_games': completeness.get('completed_final_games'),
        'unresolved_final_games': completeness.get('unresolved_final_games'),
        'expected_final_games': completeness.get('expected_final_games'),
        'total_work_items': before.get('all_work_item_count'),
        'scope_digest': before.get('selected_scope_digest'),
    }


def validate_no_drift(earlier, later, *, phase, allow_control_state=False):
    """Two snapshots must be identical.

    `allow_control_state` never relaxes baseball data — it only permits the
    governed work-item family to differ, which is the one thing R6 is allowed
    to change.
    """
    if not isinstance(later, dict):
        raise ValidationFailure(f'{phase}_state_is_an_object', 'object',
                                type(later).__name__, phase=phase)
    _require_true(f'{phase}_state_read_only',
                  (later.get('read_only') or {}).get('write_probe_refused'),
                  phase=phase)

    for field in IMMUTABLE_STATE_HASHES:
        _require(f'{phase}_{field}_unchanged', earlier.get(field),
                 later.get(field), phase=phase)
    _require(f'{phase}_game_log_row_count_unchanged',
             earlier.get('game_log_row_count'), later.get('game_log_row_count'),
             phase=phase)
    _require(f'{phase}_pitcher_count_unchanged', earlier.get('pitcher_count'),
             later.get('pitcher_count'), phase=phase)
    _require(f'{phase}_pitcher_mlb_ids_unchanged',
             sorted(earlier.get('pitcher_mlb_ids') or []),
             sorted(later.get('pitcher_mlb_ids') or []), phase=phase)
    _require(f'{phase}_dead_letter_count_unchanged',
             earlier.get('dead_letter_count'), later.get('dead_letter_count'),
             phase=phase)
    _require(f'{phase}_all_dead_letter_count_unchanged',
             earlier.get('all_dead_letter_count'),
             later.get('all_dead_letter_count'), phase=phase)

    if allow_control_state:
        return

    for field in ('all_work_items_hash', 'all_work_item_count',
                  'selected_work_item_count'):
        _require(f'{phase}_{field}_unchanged', earlier.get(field),
                 later.get(field), phase=phase)
    for field in ('completed_work_item_set', 'unresolved_set',
                  'terminal_work_item_set', 'selected_completed_set'):
        _require(f'{phase}_{field}_unchanged',
                 sorted(earlier.get(field) or []),
                 sorted(later.get(field) or []), phase=phase)
    _require(f'{phase}_selected_work_items_unchanged',
             dict(earlier.get('selected_work_items') or {}),
             dict(later.get('selected_work_items') or {}), phase=phase)
    _require(f'{phase}_publication_completeness_unchanged',
             dict(earlier.get('publication_completeness') or {}),
             dict(later.get('publication_completeness') or {}), phase=phase)


# ── Shadow report, shared by preflight and replay ───────────────────────────


def _validate_row(row, *, game_pk, totals, phase):
    """One appearance row. Unchanged on every target, or R6 fails."""
    pitcher_mlb_id = row.get('pitcher_mlb_id')
    label = f'{game_pk}_{pitcher_mlb_id}'
    context = {'phase': phase, 'game_pk': game_pk,
               'pitcher_mlb_id': pitcher_mlb_id}

    _require(f'{phase}_row_{label}_action', reconciliation.ACTION_UNCHANGED,
             row.get('action'), **context)
    _require(f'{phase}_row_{label}_changed_field_count', 0,
             row.get('changed_field_count'), **context)
    for field in ('changed_fields', 'semantic_changed_fields',
                  'applied_changed_fields', 'derived_companion_fields'):
        _require(f'{phase}_row_{label}_{field}', [], list(row.get(field) or []),
                 **context)
    _require_true(f'{phase}_row_{label}_governed_and_safe',
                  row.get('governed_and_safe'), **context)
    _require(f'{phase}_row_{label}_blocked_reason', None,
             row.get('blocked_reason'), **context)
    _require(f'{phase}_row_{label}_affects_published_evidence', False,
             bool(row.get('affects_published_evidence')), **context)
    _require(f'{phase}_row_{label}_is_statistical_correction', False,
             bool(row.get('is_statistical_correction')), **context)
    _require(f'{phase}_row_{label}_is_provenance_only', False,
             bool(row.get('is_provenance_only')), **context)
    _require(f'{phase}_row_{label}_mutation_digest', '',
             row.get('mutation_digest') or '', **context)

    action = row.get('pitcher_identity_action')
    if action in FORBIDDEN_IDENTITY_ACTIONS:
        raise ValidationFailure(f'{phase}_row_{label}_pitcher_identity_action',
                                identity.ACTION_UNCHANGED, action, **context)
    _require(f'{phase}_row_{label}_pitcher_identity_action',
             identity.ACTION_UNCHANGED, action, **context)
    for field in ('pitcher_identity_changed_fields',
                  'pitcher_identity_applied_fields'):
        _require(f'{phase}_row_{label}_{field}', [], list(row.get(field) or []),
                 **context)
    _require(f'{phase}_row_{label}_identity_mutation_digest', '',
             row.get('pitcher_identity_mutation_digest') or '', **context)
    _require_true(f'{phase}_row_{label}_identity_governed_and_safe',
                  row.get('pitcher_identity_governed_and_safe', True), **context)
    _require(f'{phase}_row_{label}_identity_blocked_reason', None,
             row.get('pitcher_identity_blocked_reason'), **context)
    _require(f'{phase}_row_{label}_identity_requires_creation', False,
             bool(row.get('pitcher_identity_requires_creation')), **context)

    # Suppressed historical current-state evidence: expected D-009 output, not
    # a mutation. Current roster and team state may legitimately have moved
    # without changing what happened in a completed game. Counted, never pinned.
    suppressed = list(row.get('pitcher_identity_suppressed_fields') or [])
    for field in suppressed:
        if field not in APPROVED_SUPPRESSIBLE_FIELDS:
            raise ValidationFailure(
                f'{phase}_row_{label}_suppressed_field_is_approved',
                'an approved protected current-state field', field, **context,
            )
    if suppressed:
        _require_true(
            f'{phase}_row_{label}_current_authority_mutation_refused',
            row.get('pitcher_identity_current_authority_mutation_refused'),
            **context,
        )
        totals['suppressed_rows'] += 1
        for field in suppressed:
            totals['suppressed_field_counts'][field] = (
                totals['suppressed_field_counts'].get(field, 0) + 1
            )

    _require(f'{phase}_row_{label}_appearance_team_reason', None,
             row.get('appearance_team_reason'), **context)
    _require(f'{phase}_row_{label}_appearance_team_decision', None,
             row.get('appearance_team_decision'), **context)

    ignored = list(row.get('derived_companion_differences_ignored') or [])
    for field in ignored:
        if field not in PROHIBITED_SEMANTIC_FIELDS:
            raise ValidationFailure(
                f'{phase}_row_{label}_ignored_difference_is_a_known_companion',
                'a known derived companion field', field, **context,
            )
    totals['ignored'] += len(ignored)

    key = (game_pk, pitcher_mlb_id)
    if key in totals['appearance_identities']:
        raise ValidationFailure(f'{phase}_duplicate_appearance_identity',
                                'one row per (game_pk, pitcher_mlb_id)',
                                'duplicate', **context)
    totals['appearance_identities'].add(key)


def validate_shadow_report(report, *, phase, require_attempt_one) -> dict:
    """Everything a 99-game exclusive shadow must satisfy.

    Used for BOTH the preflight and the post-write replay. The replay does not
    require attempt 1: the write leaves completed work items behind, so a later
    attempt number is the correct consequence of the write having happened.
    """
    if not isinstance(report, dict):
        raise ValidationFailure(f'{phase}_is_an_object', 'object',
                                type(report).__name__, phase=phase)

    approved = list(APPROVED_SET)

    _require(f'{phase}_status', 'complete', report.get('status'), phase=phase)
    _require(f'{phase}_mode', 'shadow', report.get('mode'), phase=phase)
    _require(f'{phase}_reference_date', REFERENCE_DATE,
             report.get('reference_date'), phase=phase)
    _require(f'{phase}_execution_scope_mode', 'exclusive',
             report.get('execution_scope_mode'), phase=phase)

    for field, expected in (
        ('reconciliation_plan_version',
         reconciliation.RECONCILIATION_PLAN_VERSION),
        ('parity_contract_version', reconciliation.PARITY_CONTRACT_VERSION),
        ('innings_semantics_version', reconciliation.INNINGS_SEMANTICS_VERSION),
        ('complete_plan_version', reconciliation.COMPLETE_PLAN_VERSION),
        ('identity_plan_version', identity.IDENTITY_PLAN_VERSION),
    ):
        _require(f'{phase}_{field}', expected, report.get(field), phase=phase)
    _require(f'{phase}_parity_contract_is_4', EXPECTED_PARITY_CONTRACT_VERSION,
             report.get('parity_contract_version'), phase=phase)

    _require(f'{phase}_requested_game_count', EXPECTED_GAME_COUNT,
             report.get('requested_game_count'), phase=phase)
    _require(f'{phase}_planned_game_count', EXPECTED_GAME_COUNT,
             report.get('planned_game_count'), phase=phase)
    _require(f'{phase}_duplicate_requested_count', 0,
             report.get('duplicate_requested_count'), phase=phase)
    _require_true(f'{phase}_execution_scope_exact_match',
                  report.get('execution_scope_exact_match'), phase=phase)
    _require(f'{phase}_requested_game_pks', approved,
             sorted(report.get('requested_game_pks') or []), phase=phase)
    _require(f'{phase}_planned_game_pks', approved,
             sorted(report.get('planned_game_pks') or []), phase=phase)
    _require(f'{phase}_unexpected_planned_game_pks', [],
             list(report.get('unexpected_planned_game_pks') or []), phase=phase)
    _require(f'{phase}_missing_requested_game_pks', [],
             list(report.get('missing_requested_game_pks') or []), phase=phase)

    for field in ('games_attempted', 'games_fetched', 'games_completed'):
        _require(f'{phase}_{field}', EXPECTED_GAME_COUNT, report.get(field),
                 phase=phase)
    _require(f'{phase}_games_failed', 0, report.get('games_failed'), phase=phase)
    _require(f'{phase}_games_remaining', 0, report.get('games_remaining'),
             phase=phase)
    _require(f'{phase}_budget_stop_triggered', False,
             bool(report.get('budget_stop_triggered')), phase=phase)
    _require(f'{phase}_budget_stop_is_null', None, report.get('budget_stop'),
             phase=phase)
    _require(f'{phase}_finality_conflicts', 0, report.get('finality_conflicts'),
             phase=phase)
    _require(f'{phase}_schedule_authority_missing', 0,
             report.get('schedule_authority_missing'), phase=phase)
    _require(f'{phase}_failure_classes_is_empty', {},
             dict(report.get('failure_classes') or {}), phase=phase)
    _require(f'{phase}_critical_games_unresolved', 0,
             report.get('critical_games_unresolved'), phase=phase)
    _require(f'{phase}_best_effort_games_deferred', 0,
             report.get('best_effort_games_deferred'), phase=phase)

    _require(f'{phase}_rows_expected', EXPECTED_TOTAL_ROWS,
             report.get('rows_expected'), phase=phase)
    _require(f'{phase}_rows_inserted', 0, report.get('rows_inserted'),
             phase=phase)
    _require(f'{phase}_rows_updated', 0, report.get('rows_updated'), phase=phase)
    _require(f'{phase}_rows_unchanged', EXPECTED_TOTAL_ROWS,
             report.get('rows_unchanged'), phase=phase)
    _require(f'{phase}_rows_blocked', 0, report.get('rows_blocked'), phase=phase)

    for counter in (
        'pitcher_identity_mutations', 'pitcher_identity_creations',
        'pitcher_identity_reactivations', 'pitcher_identity_metadata_updates',
        'pitcher_identity_blocked', 'appearance_team_mutations',
        'complete_mutation_count', 'canonical_outs_corrections',
        'statistical_corrections', 'derived_companion_fields_applied',
        'authority_reconciliations', 'provenance_only_updates',
        'corrections_applied',
    ):
        _require(f'{phase}_{counter}', 0, report.get(counter), phase=phase)
    _require(f'{phase}_changed_fields_counts', {},
             dict(report.get('changed_fields_counts') or {}), phase=phase)
    _require(f'{phase}_pitcher_identity_changed_fields_counts', {},
             dict(report.get('pitcher_identity_changed_fields_counts') or {}),
             phase=phase)

    _require(f'{phase}_derived_companion_differences_ignored',
             EXPECTED_TOTAL_IGNORED,
             report.get('derived_companion_differences_ignored'), phase=phase)
    _require(f'{phase}_decimal_only_updates_suppressed', EXPECTED_TOTAL_IGNORED,
             report.get('decimal_only_updates_suppressed'), phase=phase)

    games = list(report.get('games') or [])
    _require(f'{phase}_per_game_count', EXPECTED_GAME_COUNT, len(games),
             phase=phase)
    observed_order = [game.get('game_pk') for game in games]

    intruders = sorted(set(observed_order) & set(COMPLETED_GAME_PKS))
    if intruders:
        raise ValidationFailure(f'{phase}_excludes_completed_games', [],
                                intruders, phase=phase)

    _require(f'{phase}_canonical_processing_order', list(APPROVED_ORDER),
             observed_order, phase=phase)
    _require(f'{phase}_per_game_ids', approved, sorted(observed_order),
             phase=phase)

    totals = {
        'rows': 0, 'ignored': 0, 'suppressed_rows': 0,
        'suppressed_field_counts': {}, 'appearance_identities': set(),
    }
    for game in games:
        game_pk = game.get('game_pk')
        _require(f'{phase}_game_{game_pk}_status', 'projected',
                 game.get('status'), phase=phase, game_pk=game_pk)
        _require(f'{phase}_game_{game_pk}_error_class', None,
                 game.get('error_class'), phase=phase, game_pk=game_pk)
        for counter in ('inserted', 'updated', 'blocked',
                        'complete_mutation_count',
                        'pitcher_identity_mutations',
                        'appearance_team_mutations',
                        'canonical_outs_corrections', 'statistical_corrections'):
            _require(f'{phase}_game_{game_pk}_{counter}', 0, game.get(counter),
                     phase=phase, game_pk=game_pk)
        _require(f'{phase}_game_{game_pk}_criticality',
                 GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL,
                 game.get('criticality'), phase=phase, game_pk=game_pk)
        _require(f'{phase}_game_{game_pk}_candidate_reason',
                 EXPECTED_CANDIDATE_REASON, game.get('candidate_reason'),
                 phase=phase, game_pk=game_pk)
        if require_attempt_one:
            # Proves no work item exists yet — no checkpoint, no prior attempt,
            # no retry, no correction re-check. This is what makes R6
            # single-use.
            _require(f'{phase}_game_{game_pk}_attempt_number', 1,
                     game.get('attempt_number'), phase=phase, game_pk=game_pk)

        rows = list(game.get('rows') or [])
        _require(f'{phase}_game_{game_pk}_appearances_match_rows',
                 game.get('appearances_extracted'), len(rows), phase=phase,
                 game_pk=game_pk)
        before_ignored = totals['ignored']
        for row in rows:
            _validate_row(row, game_pk=game_pk, totals=totals, phase=phase)
        totals['rows'] += len(rows)
        _require(f'{phase}_game_{game_pk}_ignored_reconciles',
                 totals['ignored'] - before_ignored,
                 game.get('derived_companion_differences_ignored'),
                 phase=phase, game_pk=game_pk)
        _require_fingerprint(
            f'{phase}_game_{game_pk}_complete_reconciliation_fingerprint',
            game.get('complete_reconciliation_fingerprint'), phase=phase,
            game_pk=game_pk,
        )

    _require(f'{phase}_recomputed_row_total', EXPECTED_TOTAL_ROWS,
             totals['rows'], phase=phase)
    _require(f'{phase}_recomputed_ignored_total', EXPECTED_TOTAL_IGNORED,
             totals['ignored'], phase=phase)
    _require(f'{phase}_recomputed_appearance_identity_count',
             EXPECTED_TOTAL_ROWS, len(totals['appearance_identities']),
             phase=phase)
    _require(f'{phase}_recomputed_per_game_appearance_total',
             EXPECTED_TOTAL_ROWS,
             sum(int(game.get('appearances_extracted') or 0) for game in games),
             phase=phase)

    fingerprint = _require_fingerprint(
        f'{phase}_complete_reconciliation_fingerprint',
        report.get('complete_reconciliation_fingerprint'), phase=phase,
    )
    _require(f'{phase}_fingerprint_matches_the_approved_plan',
             APPROVED_FINGERPRINT, fingerprint, phase=phase)

    return {
        'fingerprint': fingerprint,
        'total_rows': totals['rows'],
        'total_ignored': totals['ignored'],
        'suppressed_rows': totals['suppressed_rows'],
        'suppressed_field_counts': dict(
            sorted(totals['suppressed_field_counts'].items())
        ),
    }


# ── Preflight ───────────────────────────────────────────────────────────────


def validate_preflight(before_state, preflight, prewrite_state) -> dict:
    """May the write run? Everything here happens before any mutation."""
    state = validate_before_state(before_state)
    facts = validate_shadow_report(
        preflight, phase='preflight', require_attempt_one=True,
    )
    _require('preflight_scope_digest', SCOPE_DIGEST,
             before_state.get('selected_scope_digest'), phase='preflight')
    # The preflight is read-only. Anything it moved is drift, not a shadow.
    validate_no_drift(before_state, prewrite_state, phase='prewrite')
    _require('prewrite_state_phase', 'prewrite', prewrite_state.get('phase'),
             phase='prewrite')
    return {
        'authorized': True,
        'fingerprint': facts['fingerprint'],
        'scope_digest': SCOPE_DIGEST,
        'before_state': state,
        'preflight': facts,
    }


# ── Write report ────────────────────────────────────────────────────────────


def validate_write(write, *, write_exit) -> dict:
    """The one authorized write. Authorization is proven from the REPORT."""
    if not isinstance(write, dict):
        raise ValidationFailure('write_report_is_an_object', 'object',
                                type(write).__name__, phase='write')
    _require('write_exit_code', 0, int(write_exit), phase='write')
    _require('write_mode', 'write', write.get('mode'), phase='write')
    _require('write_status', 'complete', write.get('status'), phase='write')
    _require('write_reference_date', REFERENCE_DATE,
             write.get('reference_date'), phase='write')
    _require('write_execution_scope_mode', 'exclusive',
             write.get('execution_scope_mode'), phase='write')

    # ── Authorization, re-proven from the report ────────────────────────────
    # Exit zero is not evidence the comparison happened. Both fields must be
    # present AND equal to the founder-approved value.
    expected = write.get('expected_plan_fingerprint')
    authorized = write.get('authorized_plan_fingerprint')
    if not expected:
        raise ValidationFailure('write_expected_plan_fingerprint_present',
                                'present', 'missing', phase='write')
    if not authorized:
        raise ValidationFailure('write_authorized_plan_fingerprint_present',
                                'present', 'missing', phase='write')
    if expected in REJECTED_AUTHORIZATION_VALUES:
        raise ValidationFailure('write_expected_fingerprint_is_not_stale',
                                APPROVED_FINGERPRINT, 'a rejected value',
                                phase='write')
    _require_fingerprint('write_expected_plan_fingerprint_shape', expected,
                         phase='write')
    _require_fingerprint('write_authorized_plan_fingerprint_shape', authorized,
                         phase='write')
    _require('write_expected_plan_fingerprint', APPROVED_FINGERPRINT, expected,
             phase='write')
    _require('write_authorized_plan_fingerprint', APPROVED_FINGERPRINT,
             authorized, phase='write')
    _require('write_authorization_is_self_consistent', expected, authorized,
             phase='write')

    for field, expected_version in (
        ('reconciliation_plan_version',
         reconciliation.RECONCILIATION_PLAN_VERSION),
        ('parity_contract_version', reconciliation.PARITY_CONTRACT_VERSION),
        ('innings_semantics_version', reconciliation.INNINGS_SEMANTICS_VERSION),
        ('complete_plan_version', reconciliation.COMPLETE_PLAN_VERSION),
        ('identity_plan_version', identity.IDENTITY_PLAN_VERSION),
    ):
        _require(f'write_{field}', expected_version, write.get(field),
                 phase='write')

    # ── Scope ───────────────────────────────────────────────────────────────
    approved = list(APPROVED_SET)
    _require('write_requested_game_count', EXPECTED_GAME_COUNT,
             write.get('requested_game_count'), phase='write')
    _require('write_planned_game_count', EXPECTED_GAME_COUNT,
             write.get('planned_game_count'), phase='write')
    _require_true('write_execution_scope_exact_match',
                  write.get('execution_scope_exact_match'), phase='write')
    _require('write_requested_game_pks', approved,
             sorted(write.get('requested_game_pks') or []), phase='write')
    _require('write_planned_game_pks', approved,
             sorted(write.get('planned_game_pks') or []), phase='write')

    # ── Completion: partial completion is FAILED ────────────────────────────
    games = list(write.get('games') or [])
    completed = sorted({
        game.get('game_pk') for game in games
        if game.get('status') in (
            GameIngestionWorkItem.STATUS_COMPLETED,
            'completed_with_correction',
        )
    })
    unresolved = sorted(set(APPROVED_SET) - set(completed))
    if unresolved:
        raise ValidationFailure(
            'write_completed_every_selected_game', EXPECTED_GAME_COUNT,
            len(completed), phase='write', game_pk=unresolved[:20],
        )
    _require('write_games_attempted', EXPECTED_GAME_COUNT,
             write.get('games_attempted'), phase='write')
    _require('write_games_completed', EXPECTED_GAME_COUNT,
             write.get('games_completed'), phase='write')
    _require('write_games_failed', 0, write.get('games_failed'), phase='write')
    _require('write_games_remaining', 0, write.get('games_remaining'),
             phase='write')
    _require('write_budget_stop_triggered', False,
             bool(write.get('budget_stop_triggered')), phase='write')

    # ── Rows and mutations: none, on any target ─────────────────────────────
    _require('write_rows_expected', EXPECTED_TOTAL_ROWS,
             write.get('rows_expected'), phase='write')
    _require('write_rows_inserted', 0, write.get('rows_inserted'), phase='write')
    _require('write_rows_updated', 0, write.get('rows_updated'), phase='write')
    _require('write_rows_unchanged', EXPECTED_TOTAL_ROWS,
             write.get('rows_unchanged'), phase='write')
    _require('write_rows_blocked', 0, write.get('rows_blocked'), phase='write')
    for counter in (
        'pitcher_identity_mutations', 'pitcher_identity_creations',
        'pitcher_identity_reactivations', 'pitcher_identity_metadata_updates',
        'pitcher_identity_blocked', 'appearance_team_mutations',
        'complete_mutation_count', 'canonical_outs_corrections',
        'statistical_corrections', 'provenance_only_updates',
        'authority_reconciliations', 'corrections_applied',
        'derived_companion_fields_applied',
    ):
        _require(f'write_{counter}', 0, write.get(counter), phase='write')
    _require('write_changed_fields_counts', {},
             dict(write.get('changed_fields_counts') or {}), phase='write')
    # The writer sees the same representation differences and must still ignore
    # them rather than write them.
    _require('write_derived_companion_differences_ignored',
             EXPECTED_TOTAL_IGNORED,
             write.get('derived_companion_differences_ignored'), phase='write')

    return {
        'games_attempted': write.get('games_attempted'),
        'games_completed': write.get('games_completed'),
        'games_failed': write.get('games_failed'),
        'completed_subset': completed,
        'unresolved_subset': unresolved,
        'partial_completion': False,
        'expected_plan_fingerprint': expected,
        'authorized_plan_fingerprint': authorized,
        'rows_unchanged': write.get('rows_unchanged'),
        'ignored_decimal_differences': write.get(
            'derived_companion_differences_ignored'
        ),
    }


def summarize_partial_write(write, *, write_exit) -> dict:
    """Describe a failed or partial write honestly, without judging it PASS."""
    write = write if isinstance(write, dict) else {}
    games = list(write.get('games') or [])
    completed = sorted({
        game.get('game_pk') for game in games
        if game.get('status') in (
            GameIngestionWorkItem.STATUS_COMPLETED,
            'completed_with_correction',
        )
    })
    unresolved = sorted(set(APPROVED_SET) - set(completed))
    return {
        'write_exit': write_exit,
        'games_attempted': write.get('games_attempted'),
        'games_completed': write.get('games_completed'),
        'games_failed': write.get('games_failed'),
        'completed_subset': completed,
        'completed_subset_count': len(completed),
        'unresolved_subset': unresolved,
        'unresolved_subset_count': len(unresolved),
        'partial_completion': bool(completed) and bool(unresolved),
        'transaction_boundary': TRANSACTION_BOUNDARY,
    }


# ── Control-state transition ────────────────────────────────────────────────


def validate_control_state(before, after) -> dict:
    """Exactly one thing may have moved: governed control state."""
    if not isinstance(after, dict):
        raise ValidationFailure('after_write_state_is_an_object', 'object',
                                type(after).__name__, phase='after_write')
    _require('after_write_state_phase', 'after_write', after.get('phase'),
             phase='after_write')

    # Baseball data byte-identical; control state allowed to move.
    validate_no_drift(before, after, phase='after_write',
                      allow_control_state=True)

    work_items = dict(after.get('selected_work_items') or {})
    _require('after_write_selected_work_item_keys',
             sorted(str(pk) for pk in APPROVED_SET), sorted(work_items),
             phase='after_write')
    _require('after_write_selected_work_item_count', EXPECTED_GAME_COUNT,
             after.get('selected_work_item_count'), phase='after_write')
    _require('after_write_duplicate_selected_game_pks', [],
             sorted(after.get('duplicate_selected_game_pks') or []),
             phase='after_write')
    _require('after_write_selected_completed_set', list(APPROVED_SET),
             sorted(after.get('selected_completed_set') or []),
             phase='after_write')
    _require('after_write_selected_unresolved_set', [],
             sorted(after.get('selected_unresolved_set') or []),
             phase='after_write')
    _require('after_write_selected_terminal_set', [],
             sorted(after.get('selected_terminal_set') or []),
             phase='after_write')

    for game_pk, item in sorted(work_items.items()):
        _require_true(f'after_write_game_{game_pk}_completed',
                      item.get('completed'), phase='after_write',
                      game_pk=int(game_pk))
        _require(f'after_write_game_{game_pk}_error_class', None,
                 item.get('error_class'), phase='after_write',
                 game_pk=int(game_pk))
        _require(f'after_write_game_{game_pk}_rows_reconciled',
                 item.get('rows_expected'), item.get('rows_reconciled'),
                 phase='after_write', game_pk=int(game_pk))

    # The whole governed window: 10 before, 109 after, nothing else touched.
    _require('after_write_total_work_item_count',
             int(before.get('all_work_item_count') or 0) + EXPECTED_GAME_COUNT,
             int(after.get('all_work_item_count') or 0), phase='after_write')
    _require('after_write_total_work_item_count_is_109', 109,
             int(after.get('all_work_item_count') or 0), phase='after_write')
    _require('after_write_completed_work_item_set',
             sorted(set(COMPLETED_GAME_PKS) | set(APPROVED_SET)),
             sorted(after.get('completed_work_item_set') or []),
             phase='after_write')
    _require('after_write_terminal_work_item_set', [],
             sorted(after.get('terminal_work_item_set') or []),
             phase='after_write')
    _require('after_write_unresolved_set', [],
             sorted(after.get('unresolved_set') or []), phase='after_write')

    completeness = dict(after.get('publication_completeness') or {})
    for field, expected in AFTER_COMPLETENESS.items():
        observed = completeness.get(field)
        if field == 'publication_complete':
            observed = bool(observed)
        _require(f'after_write_completeness_{field}', expected, observed,
                 phase='after_write')
    # The completeness object's own durable appearance ledger.
    _require('after_write_critical_appearance_rows_reconciled',
             EXPECTED_RECONCILED_APPEARANCE_ROWS,
             completeness.get('critical_appearance_rows_reconciled'),
             phase='after_write')
    _require('after_write_critical_appearance_rows_expected',
             EXPECTED_RECONCILED_APPEARANCE_ROWS,
             completeness.get('critical_appearance_rows_expected'),
             phase='after_write')

    before_completeness = dict(before.get('publication_completeness') or {})
    return {
        'newly_completed_work_items': EXPECTED_GAME_COUNT,
        'total_work_items_before': before.get('all_work_item_count'),
        'total_work_items_after': after.get('all_work_item_count'),
        'completed_before': before_completeness.get('completed_final_games'),
        'completed_after': completeness.get('completed_final_games'),
        'unresolved_before': before_completeness.get('unresolved_final_games'),
        'unresolved_after': completeness.get('unresolved_final_games'),
        'expected_final_before': before_completeness.get('expected_final_games'),
        'expected_final_after': completeness.get('expected_final_games'),
        'publication_complete_before': bool(
            before_completeness.get('publication_complete')
        ),
        'publication_complete_after': bool(
            completeness.get('publication_complete')
        ),
        'reconciled_appearance_rows': completeness.get(
            'critical_appearance_rows_reconciled'
        ),
        'unexpected_games_changed': 0,
        'baseball_data_changed': False,
    }


# ── Complete closeout ───────────────────────────────────────────────────────


def validate_closeout(*, before_state, preflight, prewrite_state, write,
                      after_write_state, replay, final_state, write_exit) -> dict:
    """The complete R6 decision. PASS or FAILED, nothing in between."""
    authorization = validate_preflight(before_state, preflight, prewrite_state)
    write_facts = validate_write(write, write_exit=write_exit)
    transition = validate_control_state(before_state, after_write_state)
    replay_facts = validate_shadow_report(
        replay, phase='replay', require_attempt_one=False,
    )

    # The replay is read-only. Control state may not move again either — the
    # write already happened, so anything new here is drift.
    _require('final_state_phase', 'final', final_state.get('phase'),
             phase='final')
    validate_no_drift(after_write_state, final_state, phase='final')

    _require('replay_fingerprint_matches_the_approved_plan',
             APPROVED_FINGERPRINT, replay_facts['fingerprint'], phase='replay')

    return {
        'result': RESULT_PASS,
        'authorization': authorization,
        'write': write_facts,
        'transition': transition,
        'replay': replay_facts,
        'failed_invariant': None,
    }


# ── Closeout package ────────────────────────────────────────────────────────


def build_closeout(decision, *, repository_sha, run_id, before, prewrite,
                   after_write, final, partial=None) -> dict:
    passed = decision.get('result') == RESULT_PASS
    authorization = decision.get('authorization') or {}
    preflight = authorization.get('preflight') or {}
    write = decision.get('write') or {}
    transition = decision.get('transition') or {}
    replay = decision.get('replay') or {}

    def _hashes(state):
        state = state or {}
        return {field: state.get(field) for field in IMMUTABLE_STATE_HASHES}

    return {
        'result': decision.get('result'),
        'repository_sha': repository_sha,
        'workflow_run_id': run_id,
        'reference_date': REFERENCE_DATE,

        'approved_complete_fingerprint': APPROVED_FINGERPRINT,
        'approved_scope_digest': SCOPE_DIGEST,
        'canonical_processing_order': list(APPROVED_ORDER),
        'unresolved_game_pks_sorted': list(APPROVED_SET),
        'completed_game_pks_before_r6': list(COMPLETED_GAME_PKS),

        'scope_authorization': 'exact_match' if passed else 'not_established',
        'fingerprint_authorization': (
            'matched_before_mutation' if passed else 'not_established'
        ),

        'preflight_fingerprint': preflight.get('fingerprint'),
        'preflight_games_completed': EXPECTED_GAME_COUNT if passed else None,
        'preflight_rows_unchanged': preflight.get('total_rows'),
        'preflight_mutations_by_target': {
            'game_log': 0, 'pitcher_identity': 0, 'appearance_team': 0,
        } if passed else None,
        'preflight_ignored_decimal_differences': preflight.get('total_ignored'),
        'preflight_suppressed_historical_differences': preflight.get(
            'suppressed_rows'
        ),

        'write_exit': 0 if passed else (partial or {}).get('write_exit'),
        'write_games_attempted': write.get('games_attempted'),
        'write_games_completed': write.get('games_completed'),
        'write_games_failed': write.get('games_failed'),
        'write_completed_subset': write.get('completed_subset')
        or (partial or {}).get('completed_subset'),
        'write_unresolved_subset': write.get('unresolved_subset')
        if passed else (partial or {}).get('unresolved_subset'),
        'write_rows_unchanged': write.get('rows_unchanged'),
        'write_mutations_by_target': {
            'game_log': 0, 'pitcher_identity': 0, 'appearance_team': 0,
        } if passed else None,
        'write_expected_plan_fingerprint': write.get(
            'expected_plan_fingerprint'
        ),
        'write_authorized_plan_fingerprint': write.get(
            'authorized_plan_fingerprint'
        ),

        'newly_completed_work_items': transition.get(
            'newly_completed_work_items'
        ),
        'total_work_items_before': transition.get('total_work_items_before'),
        'total_work_items_after': transition.get('total_work_items_after'),
        'completed_final_games_before': transition.get('completed_before'),
        'completed_final_games_after': transition.get('completed_after'),
        'unresolved_final_games_before': transition.get('unresolved_before'),
        'unresolved_final_games_after': transition.get('unresolved_after'),
        'expected_final_games_before': transition.get('expected_final_before'),
        'expected_final_games_after': transition.get('expected_final_after'),
        'publication_complete_before': transition.get(
            'publication_complete_before'
        ),
        'publication_complete_after': transition.get(
            'publication_complete_after'
        ),
        'reconciled_appearance_rows': transition.get(
            'reconciled_appearance_rows'
        ),

        'before_state_hashes': _hashes(before),
        'prewrite_state_hashes': _hashes(prewrite),
        'after_write_state_hashes': _hashes(after_write),
        'final_state_hashes': _hashes(final),
        'baseball_data_changed': False if passed else None,
        'dead_letter_count_before': (before or {}).get('all_dead_letter_count'),
        'dead_letter_count_after': (final or {}).get('all_dead_letter_count'),

        'replay_games_completed': EXPECTED_GAME_COUNT if passed else None,
        'replay_rows_unchanged': replay.get('total_rows'),
        'replay_mutations_by_target': {
            'game_log': 0, 'pitcher_identity': 0, 'appearance_team': 0,
        } if passed else None,
        'replay_ignored_decimal_differences': replay.get('total_ignored'),
        'replay_suppressed_historical_differences': replay.get(
            'suppressed_rows'
        ),
        'replay_fingerprint': replay.get('fingerprint'),
        'replay_caused_database_drift': False if passed else None,

        'transaction_boundary': TRANSACTION_BOUNDARY,
        'partial_completion': (
            False if passed else (partial or {}).get('partial_completion')
        ),
        'database_writes': (
            'governed ingestion control state only: 99 work items created and '
            'completed. No baseball-data rows changed.'
        ),
        'automated_lane': 'off',
        'authoritative_mode': 'unapproved',
        'stage_e': 'not_implemented',
        'next_action': NEXT_ACTION_PASS if passed else NEXT_ACTION_FAILED,
        'failed_invariant': decision.get('failed_invariant'),
    }


def build_summary(decision, closeout) -> dict:
    passed = decision.get('result') == RESULT_PASS
    return {
        'result': decision.get('result'),
        'reference_date': REFERENCE_DATE,
        'games_requested': EXPECTED_GAME_COUNT,
        'games_planned': EXPECTED_GAME_COUNT,
        'games_completed': closeout.get('write_games_completed'),
        'games_failed': closeout.get('write_games_failed'),
        'scope_set_sha256': SCOPE_DIGEST,
        'parity_contract_version': EXPECTED_PARITY_CONTRACT_VERSION,
        'approved_fingerprint': APPROVED_FINGERPRINT,
        'preflight_fingerprint_matched': passed,
        'authorization_before_mutation': passed,
        'rows_expected': EXPECTED_TOTAL_ROWS,
        'rows_unchanged': closeout.get('write_rows_unchanged'),
        'mutations_by_target': closeout.get('write_mutations_by_target'),
        'newly_completed_work_items': closeout.get(
            'newly_completed_work_items'
        ),
        'total_work_items_before': closeout.get('total_work_items_before'),
        'total_work_items_after': closeout.get('total_work_items_after'),
        'completed_final_games_before': closeout.get(
            'completed_final_games_before'
        ),
        'completed_final_games_after': closeout.get(
            'completed_final_games_after'
        ),
        'unresolved_final_games_before': closeout.get(
            'unresolved_final_games_before'
        ),
        'unresolved_final_games_after': closeout.get(
            'unresolved_final_games_after'
        ),
        'publication_complete': closeout.get('publication_complete_after'),
        'baseball_data_changed': False if passed else None,
        'replay_rows_unchanged': closeout.get('replay_rows_unchanged'),
        'replay_ignored_decimal_differences': closeout.get(
            'replay_ignored_decimal_differences'
        ),
        'replay_fingerprint_matched': passed,
        'replay_caused_database_drift': False if passed else None,
        'partial_completion': closeout.get('partial_completion'),
        'database_writes': closeout.get('database_writes'),
        'automated_lane': 'off',
        'authoritative_mode': 'unapproved',
        'stage_e': 'not_implemented',
        'next_action': closeout.get('next_action'),
        'artifact': 'foundation-3c-r6-full-remaining-window-write',
        'failed_invariant': decision.get('failed_invariant'),
    }


def failed_summary(failure, partial=None) -> dict:
    """Safe evidence only. Never a payload, never an exception message."""
    partial = partial or {}
    return {
        'result': RESULT_FAILED,
        'failed_phase': failure.phase,
        'failed_invariant': failure.invariant,
        'expected': failure.expected,
        'observed': failure.observed,
        'game_pk': failure.game_pk,
        'pitcher_mlb_id': failure.pitcher_mlb_id,
        'reference_date': REFERENCE_DATE,
        'games_requested': EXPECTED_GAME_COUNT,
        'rows_expected': EXPECTED_TOTAL_ROWS,
        'completed_subset_count': partial.get('completed_subset_count'),
        'unresolved_subset_count': partial.get('unresolved_subset_count'),
        'partial_completion': partial.get('partial_completion'),
        'transaction_boundary': TRANSACTION_BOUNDARY,
        'automated_lane': 'off',
        'authoritative_mode': 'unapproved',
        'stage_e': 'not_implemented',
        'artifact': 'foundation-3c-r6-full-remaining-window-write',
        'next_action': NEXT_ACTION_FAILED,
        'sanitized': True,
    }


# ── Markdown ────────────────────────────────────────────────────────────────


def pass_markdown(summary, closeout) -> str:
    return '\n'.join([
        '## FOUNDATION 3C R6 — PASS',
        '',
        '### Authorization',
        f"- Reference date: {REFERENCE_DATE}",
        f"- Requested games: {summary['games_requested']}",
        f"- Planned games: {summary['games_planned']}",
        '- Exact scope: yes',
        '- Scope-set SHA-256:',
        f"  {SCOPE_DIGEST}",
        '- Parity contract version: 4',
        '- Approved fingerprint:',
        f"  {APPROVED_FINGERPRINT}",
        '- Preflight fingerprint matched: yes',
        '- Authorization occurred before mutation: yes',
        '',
        '### Controlled write',
        f"- Games attempted: {closeout['write_games_attempted']}",
        f"- Games completed: {closeout['write_games_completed']}",
        f"- Games failed: {closeout['write_games_failed']}",
        f"- Appearance rows: {summary['rows_expected']}",
        '- GameLog inserted: 0',
        '- GameLog updated: 0',
        f"- GameLog unchanged: {closeout['write_rows_unchanged']}",
        '- Blocked: 0',
        '',
        '### Mutations by target',
        '- GameLog: 0',
        '- Pitcher identity: 0',
        '- Appearance team: 0',
        '- Complete-plan mutations: 0',
        '',
        '### Checkpoint effects',
        f"- Newly completed work items: {closeout['newly_completed_work_items']}",
        f"- Total work items before: {closeout['total_work_items_before']}",
        f"- Total work items after: {closeout['total_work_items_after']}",
        '- Completed final games before: '
        f"{closeout['completed_final_games_before']}",
        '- Completed final games after: '
        f"{closeout['completed_final_games_after']}",
        '- Unresolved final games before: '
        f"{closeout['unresolved_final_games_before']}",
        '- Unresolved final games after: '
        f"{closeout['unresolved_final_games_after']}",
        '- Unexpected games changed: 0',
        '- Partial completion: no',
        '',
        '### Data integrity',
        '- GameLog data changed: no',
        '- Canonical outs changed: no',
        '- Pitcher data changed: no',
        '- Appearance-team data changed: no',
        '- Correction provenance changed: no',
        '- Dead letters created: 0',
        '',
        '### Immediate replay',
        '- Games completed in shadow: '
        f"{closeout['replay_games_completed']}",
        f"- Rows unchanged: {closeout['replay_rows_unchanged']}",
        '- Mutations across all targets: 0',
        '- Decimal-only differences safely ignored: '
        f"{closeout['replay_ignored_decimal_differences']}",
        '- Replay fingerprint matched: yes',
        '- Replay caused database drift: no',
        '- Suppressed historical current-state differences: '
        f"{closeout['replay_suppressed_historical_differences']}",
        '',
        '### Publication completeness',
        '- Expected final games: 109',
        '- Completed final games: 109',
        '- Unresolved final games: 0',
        '- Terminal failures: 0',
        '- Correction pending: 0',
        '- Publication complete: yes',
        f"- Reconciled appearance rows: {closeout['reconciled_appearance_rows']}",
        '',
        '### Result',
        '- The fingerprint-authorized full 99-game write completed '
        'successfully.',
        '- Only governed ingestion control state changed.',
        '- No baseball-data rows changed.',
        '- The immediate replay converged to zero mutations.',
        '- The 109-game Foundation 3C bootstrap is complete.',
        '- GAME_DRIVEN_INGESTION_MODE remains off.',
        '- Authoritative mode remains unapproved.',
        '- Foundation 3C may proceed to Stage E rollout closeout.',
        '',
    ])


def failed_markdown(summary) -> str:
    lines = [
        '## FOUNDATION 3C R6 — FAILED',
        '',
        f"- Failed phase: `{summary.get('failed_phase')}`",
        f"- Failed invariant: `{summary['failed_invariant']}`",
        f"- Expected: `{summary['expected']}`",
        f"- Observed: `{summary['observed']}`",
    ]
    if summary.get('game_pk') is not None:
        lines.append(f"- Affected game: `{summary['game_pk']}`")
    if summary.get('pitcher_mlb_id') is not None:
        lines.append(f"- Affected pitcher MLB id: `{summary['pitcher_mlb_id']}`")
    lines += [
        f"- Completed subset: {summary.get('completed_subset_count')}",
        f"- Unresolved subset: {summary.get('unresolved_subset_count')}",
        f"- Partial completion: {summary.get('partial_completion')}",
        f"- Games requested: {summary['games_requested']}",
        f"- Rows expected: {summary['rows_expected']}",
        '- Automated lane: off',
        '- Authoritative mode: unapproved',
        f"- Artifact: `{summary['artifact']}`",
        '',
        '**This is a rollout stop.** Do not retry R6, remove workflows, or '
        'enable any lane without founder review. The canonical writer commits '
        'per game, so any completed subset above is durable and must not be '
        'compensated or deleted.',
        '',
    ]
    return '\n'.join(lines)


def closeout_markdown(closeout) -> str:
    passed = closeout['result'] == RESULT_PASS
    lines = [
        f"## Foundation 3C R6 closeout — {'PASS' if passed else 'FAILED'}",
        '',
        f"- Repository SHA: `{closeout['repository_sha']}`",
        f"- Workflow run: `{closeout['workflow_run_id']}`",
        f"- Reference date: `{closeout['reference_date']}`",
        f"- Approved fingerprint: `{closeout['approved_complete_fingerprint']}`",
        f"- Approved scope digest: `{closeout['approved_scope_digest']}`",
        f"- Scope authorization: {closeout['scope_authorization']}",
        f"- Fingerprint authorization: {closeout['fingerprint_authorization']}",
        '',
        '### Transition',
        '',
        '| | before | after |',
        '|---|---:|---:|',
        f"| total work items | {closeout['total_work_items_before']} "
        f"| {closeout['total_work_items_after']} |",
        f"| completed final games | {closeout['completed_final_games_before']} "
        f"| {closeout['completed_final_games_after']} |",
        f"| unresolved final games "
        f"| {closeout['unresolved_final_games_before']} "
        f"| {closeout['unresolved_final_games_after']} |",
        f"| expected final games | {closeout['expected_final_games_before']} "
        f"| {closeout['expected_final_games_after']} |",
        f"| publication complete | {closeout['publication_complete_before']} "
        f"| {closeout['publication_complete_after']} |",
        '',
        f"- Newly completed work items: {closeout['newly_completed_work_items']}",
        f"- Reconciled appearance rows: {closeout['reconciled_appearance_rows']}",
        f"- Partial completion: {closeout['partial_completion']}",
        f"- Database writes: {closeout['database_writes']}",
        f"- Transaction boundary: {closeout['transaction_boundary']}",
        '',
        '### Replay',
        '',
        f"- Rows unchanged: {closeout['replay_rows_unchanged']}",
        '- Ignored decimal differences: '
        f"{closeout['replay_ignored_decimal_differences']}",
        f"- Fingerprint: `{closeout['replay_fingerprint']}`",
        f"- Caused drift: {closeout['replay_caused_database_drift']}",
        '',
        '### Rollout',
        '',
        f"- Automated lane: {closeout['automated_lane']}",
        f"- Authoritative mode: {closeout['authoritative_mode']}",
        f"- Stage E: {closeout['stage_e']}",
        '',
        f"_{closeout['next_action']}_",
        '',
    ]
    return '\n'.join(lines)


# ── CLI ─────────────────────────────────────────────────────────────────────


def _write_text(path, text):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding='utf-8')


def _write_json(path, payload):
    _write_text(
        path, json.dumps(payload, indent=2, sort_keys=True, default=str) + '\n'
    )


def _run_preflight(args) -> int:
    try:
        before = _load(args.before_state, 'before_state_artifact')
        preflight = _load(args.preflight, 'preflight_artifact')
        prewrite = _load(args.prewrite_state, 'prewrite_state_artifact')
        validate_preflight(before, preflight, prewrite)
        print('R6 preflight authorized the write.')
        return EXIT_OK
    except ValidationFailure as failure:
        print(f'::error::R6 preflight refused: {failure.invariant}')
        return EXIT_FAILED


def _run_closeout(args) -> int:
    partial = None
    try:
        before = _load(args.before_state, 'before_state_artifact')
        preflight = _load(args.preflight, 'preflight_artifact')
        prewrite = _load(args.prewrite_state, 'prewrite_state_artifact')
        write = _load(args.write, 'write_artifact')
        after_write = _load(args.after_write_state, 'after_write_state_artifact')
        replay = _load(args.replay, 'replay_artifact')
        final = _load(args.final_state, 'final_state_artifact')

        partial = summarize_partial_write(write, write_exit=args.write_exit)
        decision = validate_closeout(
            before_state=before, preflight=preflight, prewrite_state=prewrite,
            write=write, after_write_state=after_write, replay=replay,
            final_state=final, write_exit=args.write_exit,
        )
        closeout = build_closeout(
            decision, repository_sha=args.repository_sha, run_id=args.run_id,
            before=before, prewrite=prewrite, after_write=after_write,
            final=final,
        )
        summary = build_summary(decision, closeout)

        _write_json(args.closeout_json, closeout)
        _write_text(args.closeout_markdown, closeout_markdown(closeout))
        _write_json(args.summary_json, summary)
        _write_text(args.summary_markdown, pass_markdown(summary, closeout))
        return EXIT_OK
    except ValidationFailure as failure:
        summary = failed_summary(failure, partial)
        _write_json(args.summary_json, summary)
        _write_text(args.summary_markdown, failed_markdown(summary))
        failed_closeout = build_closeout(
            {'result': RESULT_FAILED, 'failed_invariant': failure.invariant},
            repository_sha=args.repository_sha, run_id=args.run_id,
            before=None, prewrite=None, after_write=None, final=None,
            partial=partial,
        )
        _write_json(args.closeout_json, failed_closeout)
        _write_text(args.closeout_markdown, closeout_markdown(failed_closeout))
        return EXIT_FAILED


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='Validate the Foundation 3C R6 full remaining-window write.',
    )
    sub = parser.add_subparsers(dest='phase', required=True)

    pre = sub.add_parser('preflight')
    pre.add_argument('--before-state', required=True)
    pre.add_argument('--preflight', required=True)
    pre.add_argument('--prewrite-state', required=True)

    close = sub.add_parser('closeout')
    close.add_argument('--before-state', required=True)
    close.add_argument('--preflight', required=True)
    close.add_argument('--prewrite-state', required=True)
    close.add_argument('--write', required=True)
    close.add_argument('--after-write-state', required=True)
    close.add_argument('--replay', required=True)
    close.add_argument('--final-state', required=True)
    close.add_argument('--write-exit', type=int, required=True)
    close.add_argument('--summary-json', required=True)
    close.add_argument('--summary-markdown', required=True)
    close.add_argument('--closeout-json', required=True)
    close.add_argument('--closeout-markdown', required=True)
    close.add_argument('--repository-sha', default='')
    close.add_argument('--run-id', default='')

    args = parser.parse_args(argv)
    if args.phase == 'preflight':
        return _run_preflight(args)
    return _run_closeout(args)


if __name__ == '__main__':
    raise SystemExit(main())
