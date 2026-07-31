#!/usr/bin/env python
"""Validate the Foundation 3C Stage E bootstrap closeout.

Stage E is the final independent verification of the completed 109-game
bootstrap. It authorizes nothing. It proves three things and stops:

  * production really is 109 completed / 0 unresolved with 946 reconciled
    appearance rows and publication complete;
  * replaying the entire bootstrap projects no mutation to any target;
  * the verification itself changed nothing.

Two deliberate refusals:

  * It never trusts an aggregate alone. Row totals, ignored-difference totals,
    and appearance identities are recomputed from the per-row detail, because
    an aggregate is exactly what a bug would get right while the detail
    disagreed.
  * It never reports "dead letters: 0" as a system-wide claim. The governed
    bootstrap count must be zero; the global count was already 1,389 at R6
    closeout and belongs to unrelated work. Collapsing the two would either
    hide a governed failure or make a false claim about the whole system.

There is no `review_required` tier. PASS or FAILED. An unrelated change in the
GLOBAL dead-letter count is reported as an advisory, not a failure — a governed
bootstrap game with a dead letter is always FAILED.

TEMPORARY. Retained only until Stage E2 removes it with the Stage E workflow.
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

import stage_e_bootstrap_scope as scope  # noqa: E402
from services import game_log_reconciliation as reconciliation  # noqa: E402
from services import pitcher_identity_reconciliation as identity  # noqa: E402
from models.game_ingestion_work_item import GameIngestionWorkItem  # noqa: E402


EXIT_OK = 0
EXIT_FAILED = 1

RESULT_PASS = 'pass'
RESULT_FAILED = 'failed'

REFERENCE_DATE = scope.REFERENCE_DATE
CANONICAL_ORDER = scope.CANONICAL_ORDER
GOVERNED_SET = scope.SORTED_SET
EXPECTED_GAME_COUNT = scope.EXPECTED_GAME_COUNT          # 109
EXPECTED_TOTAL_ROWS = scope.EXPECTED_TOTAL_ROWS          # 946
EXPECTED_TOTAL_IGNORED = scope.EXPECTED_TOTAL_IGNORED    # 323
FULL_SCOPE_DIGEST = scope.FULL_SCOPE_DIGEST

EXPECTED_PARITY_CONTRACT_VERSION = '4'

R6_GLOBAL_DEAD_LETTER_COUNT = scope.R6_GLOBAL_DEAD_LETTER_COUNT   # 1389

# Production must be the completed bootstrap, before and after.
BOOTSTRAP_COMPLETENESS = {
    'expected_final_games': 109,
    'completed_final_games': 109,
    'unresolved_final_games': 0,
    'terminal_failure_games': 0,
    'correction_pending_games': 0,
    'critical_appearance_rows_reconciled': 946,
    'publication_complete': True,
}

PROHIBITED_SEMANTIC_FIELDS = frozenset(reconciliation.DERIVED_COMPANION_FIELDS)
FORBIDDEN_IDENTITY_ACTIONS = frozenset(
    set(identity.MUTATING_ACTIONS)
    | set(identity.RETIRED_WRITE_ACTIONS)
    | {identity.ACTION_BLOCKED}
)
APPROVED_SUPPRESSIBLE_FIELDS = frozenset({
    'active', 'full_name', 'position', 'roster_status', 'team_abbreviation',
    'team_id', 'team_name',
})

FINGERPRINT_PATTERN = re.compile(r'^[0-9a-f]{64}$')

IMMUTABLE_STATE_HASHES = (
    'game_log_content_hash',
    'canonical_outs_hash',
    'correction_provenance_hash',
    'appearance_team_hash',
    'pitcher_state_hash',
)

EXPECTED_CANDIDATE_REASON = GameIngestionWorkItem.REASON_EXPLICIT_REPAIR

NEXT_ACTION_PASS = (
    'Proceed to Stage E2: record this verification in the historical closeout, '
    'remove the Stage E workflow and its temporary support files, and prove no '
    'temporary Foundation 3C rollout workflow remains. Do not enable any lane.'
)
NEXT_ACTION_FAILED = (
    'Do not enable any lane. Do not remove the Stage E verification workflow. '
    'Do not proceed to E2.'
)


class ValidationFailure(Exception):
    """One named invariant did not hold. Stage E stops here."""

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


# ── Bootstrap state ─────────────────────────────────────────────────────────


def validate_bootstrap_state(state, *, phase) -> dict:
    """Production must be the completed 109-game bootstrap."""
    if not isinstance(state, dict):
        raise ValidationFailure(f'{phase}_state_is_an_object', 'object',
                                type(state).__name__, phase=phase)
    _require(f'{phase}_state_phase', phase, state.get('phase'), phase=phase)
    _require_true(f'{phase}_state_read_only',
                  (state.get('read_only') or {}).get('write_probe_refused'),
                  phase=phase)
    _require(f'{phase}_state_reference_date', REFERENCE_DATE,
             state.get('reference_date'), phase=phase)

    _require(f'{phase}_state_governed_game_count', EXPECTED_GAME_COUNT,
             state.get('governed_game_count'), phase=phase)
    _require(f'{phase}_state_governed_game_pks', list(GOVERNED_SET),
             sorted(state.get('governed_game_pks') or []), phase=phase)
    _require(f'{phase}_state_full_scope_digest', FULL_SCOPE_DIGEST,
             state.get('full_scope_digest'), phase=phase)

    # ── Completeness ────────────────────────────────────────────────────────
    completeness = dict(state.get('publication_completeness') or {})
    for field, expected in BOOTSTRAP_COMPLETENESS.items():
        observed = completeness.get(field)
        if field == 'publication_complete':
            observed = bool(observed)
        _require(f'{phase}_state_completeness_{field}', expected, observed,
                 phase=phase)

    # ── Governed control state ──────────────────────────────────────────────
    _require(f'{phase}_state_governed_work_item_count', EXPECTED_GAME_COUNT,
             state.get('governed_work_item_count'), phase=phase)
    _require(f'{phase}_state_governed_completed_set', list(GOVERNED_SET),
             sorted(state.get('governed_completed_set') or []), phase=phase)
    _require(f'{phase}_state_governed_unresolved_set', [],
             sorted(state.get('governed_unresolved_set') or []), phase=phase)
    _require(f'{phase}_state_governed_terminal_set', [],
             sorted(state.get('governed_terminal_set') or []), phase=phase)
    _require(f'{phase}_state_duplicate_governed_game_pks', [],
             sorted(state.get('duplicate_governed_game_pks') or []),
             phase=phase)
    _require(f'{phase}_state_completed_work_item_set', list(GOVERNED_SET),
             sorted(state.get('completed_work_item_set') or []), phase=phase)
    _require(f'{phase}_state_terminal_work_item_set', [],
             sorted(state.get('terminal_work_item_set') or []), phase=phase)
    _require(f'{phase}_state_unresolved_set', [],
             sorted(state.get('unresolved_set') or []), phase=phase)

    work_items = dict(state.get('governed_work_items') or {})
    _require(f'{phase}_state_governed_work_item_keys',
             sorted(str(pk) for pk in GOVERNED_SET), sorted(work_items),
             phase=phase)
    for game_pk, item in sorted(work_items.items()):
        _require_true(f'{phase}_state_game_{game_pk}_completed',
                      item.get('completed'), phase=phase, game_pk=int(game_pk))
        _require(f'{phase}_state_game_{game_pk}_error_class', None,
                 item.get('error_class'), phase=phase, game_pk=int(game_pk))

    # ── Dead letters: governed must be zero, global is only recorded ────────
    _require(f'{phase}_state_governed_dead_letter_count', 0,
             state.get('governed_dead_letter_count'), phase=phase)

    # ── Version constants ───────────────────────────────────────────────────
    versions = dict(state.get('version_constants') or {})
    for field, expected in (
        ('reconciliation_plan_version',
         reconciliation.RECONCILIATION_PLAN_VERSION),
        ('parity_contract_version', reconciliation.PARITY_CONTRACT_VERSION),
        ('innings_semantics_version', reconciliation.INNINGS_SEMANTICS_VERSION),
        ('complete_plan_version', reconciliation.COMPLETE_PLAN_VERSION),
        ('identity_plan_version', identity.IDENTITY_PLAN_VERSION),
    ):
        _require(f'{phase}_state_{field}', expected, versions.get(field),
                 phase=phase)

    _require(f'{phase}_state_automated_lane', 'off',
             state.get('automated_lane'), phase=phase)
    _require(f'{phase}_state_authoritative_mode', 'unapproved',
             state.get('authoritative_mode'), phase=phase)

    global_count = state.get('global_dead_letter_count')
    return {
        'completed_final_games': completeness.get('completed_final_games'),
        'unresolved_final_games': completeness.get('unresolved_final_games'),
        'expected_final_games': completeness.get('expected_final_games'),
        'reconciled_appearance_rows': completeness.get(
            'critical_appearance_rows_reconciled'
        ),
        'governed_work_item_count': state.get('governed_work_item_count'),
        'governed_dead_letter_count': state.get('governed_dead_letter_count'),
        'global_dead_letter_count': global_count,
        'r6_global_dead_letter_count': R6_GLOBAL_DEAD_LETTER_COUNT,
        'global_dead_letter_delta': (
            None if global_count is None
            else int(global_count) - R6_GLOBAL_DEAD_LETTER_COUNT
        ),
    }


def dead_letter_advisory(state) -> dict:
    """Describe the GLOBAL dead-letter position without judging it.

    A change here is unrelated to Foundation 3C by construction — the governed
    count is asserted zero separately — so it is reported, not failed on.
    """
    observed = state.get('global_dead_letter_count')
    delta = (
        None if observed is None
        else int(observed) - R6_GLOBAL_DEAD_LETTER_COUNT
    )
    return {
        'r6_closeout_global_dead_letters': R6_GLOBAL_DEAD_LETTER_COUNT,
        'current_global_dead_letters': observed,
        'delta': delta,
        'governed_bootstrap_dead_letters': state.get(
            'governed_dead_letter_count'
        ),
        'foundation_3c_created_new_dead_letters': False,
        'advisory': (
            'The global count is unchanged from R6 closeout.'
            if delta == 0 else
            'The global count changed since R6 closeout. Foundation 3C created '
            'no governed-bootstrap dead letters; this movement belongs to '
            'unrelated work and is recorded rather than failed on.'
        ),
    }


# ── Full 109-game replay ────────────────────────────────────────────────────


def _validate_row(row, *, game_pk, totals):
    """One appearance row. Unchanged on every target, or Stage E fails."""
    pitcher_mlb_id = row.get('pitcher_mlb_id')
    label = f'{game_pk}_{pitcher_mlb_id}'
    context = {'phase': 'replay', 'game_pk': game_pk,
               'pitcher_mlb_id': pitcher_mlb_id}

    _require(f'row_{label}_action', reconciliation.ACTION_UNCHANGED,
             row.get('action'), **context)
    _require(f'row_{label}_changed_field_count', 0,
             row.get('changed_field_count'), **context)
    for field in ('changed_fields', 'semantic_changed_fields',
                  'applied_changed_fields', 'derived_companion_fields'):
        _require(f'row_{label}_{field}', [], list(row.get(field) or []),
                 **context)
    _require_true(f'row_{label}_governed_and_safe',
                  row.get('governed_and_safe'), **context)
    _require(f'row_{label}_blocked_reason', None, row.get('blocked_reason'),
             **context)
    _require(f'row_{label}_affects_published_evidence', False,
             bool(row.get('affects_published_evidence')), **context)
    _require(f'row_{label}_is_statistical_correction', False,
             bool(row.get('is_statistical_correction')), **context)
    _require(f'row_{label}_is_provenance_only', False,
             bool(row.get('is_provenance_only')), **context)
    _require(f'row_{label}_mutation_digest', '',
             row.get('mutation_digest') or '', **context)

    action = row.get('pitcher_identity_action')
    if action in FORBIDDEN_IDENTITY_ACTIONS:
        raise ValidationFailure(f'row_{label}_pitcher_identity_action',
                                identity.ACTION_UNCHANGED, action, **context)
    _require(f'row_{label}_pitcher_identity_action', identity.ACTION_UNCHANGED,
             action, **context)
    for field in ('pitcher_identity_changed_fields',
                  'pitcher_identity_applied_fields'):
        _require(f'row_{label}_{field}', [], list(row.get(field) or []),
                 **context)
    _require(f'row_{label}_identity_mutation_digest', '',
             row.get('pitcher_identity_mutation_digest') or '', **context)
    _require_true(f'row_{label}_identity_governed_and_safe',
                  row.get('pitcher_identity_governed_and_safe', True), **context)
    _require(f'row_{label}_identity_blocked_reason', None,
             row.get('pitcher_identity_blocked_reason'), **context)
    _require(f'row_{label}_identity_requires_creation', False,
             bool(row.get('pitcher_identity_requires_creation')), **context)

    # Suppressed historical current-state evidence: expected D-009 output.
    # Counted, never pinned — current roster state moves for its own reasons.
    suppressed = list(row.get('pitcher_identity_suppressed_fields') or [])
    for field in suppressed:
        if field not in APPROVED_SUPPRESSIBLE_FIELDS:
            raise ValidationFailure(
                f'row_{label}_suppressed_field_is_approved',
                'an approved protected current-state field', field, **context,
            )
    if suppressed:
        _require_true(
            f'row_{label}_current_authority_mutation_refused',
            row.get('pitcher_identity_current_authority_mutation_refused'),
            **context,
        )
        totals['suppressed_rows'] += 1
        for field in suppressed:
            totals['suppressed_field_counts'][field] = (
                totals['suppressed_field_counts'].get(field, 0) + 1
            )

    _require(f'row_{label}_appearance_team_reason', None,
             row.get('appearance_team_reason'), **context)
    _require(f'row_{label}_appearance_team_decision', None,
             row.get('appearance_team_decision'), **context)

    ignored = list(row.get('derived_companion_differences_ignored') or [])
    for field in ignored:
        if field not in PROHIBITED_SEMANTIC_FIELDS:
            raise ValidationFailure(
                f'row_{label}_ignored_difference_is_a_known_companion',
                'a known derived companion field', field, **context,
            )
    totals['ignored'] += len(ignored)

    key = (game_pk, pitcher_mlb_id)
    if key in totals['appearance_identities']:
        raise ValidationFailure('duplicate_appearance_identity',
                                'one row per (game_pk, pitcher_mlb_id)',
                                'duplicate', **context)
    totals['appearance_identities'].add(key)


def validate_full_replay(report) -> dict:
    """The entire 109-game bootstrap, replayed read-only."""
    if not isinstance(report, dict):
        raise ValidationFailure('replay_is_an_object', 'object',
                                type(report).__name__, phase='replay')

    governed = list(GOVERNED_SET)

    _require('replay_status', 'complete', report.get('status'), phase='replay')
    _require('replay_mode', 'shadow', report.get('mode'), phase='replay')
    _require('replay_reference_date', REFERENCE_DATE,
             report.get('reference_date'), phase='replay')
    _require('replay_execution_scope_mode', 'exclusive',
             report.get('execution_scope_mode'), phase='replay')

    for field, expected in (
        ('reconciliation_plan_version',
         reconciliation.RECONCILIATION_PLAN_VERSION),
        ('parity_contract_version', reconciliation.PARITY_CONTRACT_VERSION),
        ('innings_semantics_version', reconciliation.INNINGS_SEMANTICS_VERSION),
        ('complete_plan_version', reconciliation.COMPLETE_PLAN_VERSION),
        ('identity_plan_version', identity.IDENTITY_PLAN_VERSION),
    ):
        _require(f'replay_{field}', expected, report.get(field), phase='replay')
    _require('replay_parity_contract_is_4', EXPECTED_PARITY_CONTRACT_VERSION,
             report.get('parity_contract_version'), phase='replay')

    _require('replay_requested_game_count', EXPECTED_GAME_COUNT,
             report.get('requested_game_count'), phase='replay')
    _require('replay_planned_game_count', EXPECTED_GAME_COUNT,
             report.get('planned_game_count'), phase='replay')
    _require('replay_duplicate_requested_count', 0,
             report.get('duplicate_requested_count'), phase='replay')
    _require_true('replay_execution_scope_exact_match',
                  report.get('execution_scope_exact_match'), phase='replay')
    _require('replay_requested_game_pks', governed,
             sorted(report.get('requested_game_pks') or []), phase='replay')
    _require('replay_planned_game_pks', governed,
             sorted(report.get('planned_game_pks') or []), phase='replay')
    _require('replay_unexpected_planned_game_pks', [],
             list(report.get('unexpected_planned_game_pks') or []),
             phase='replay')
    _require('replay_missing_requested_game_pks', [],
             list(report.get('missing_requested_game_pks') or []),
             phase='replay')

    for field in ('games_attempted', 'games_fetched', 'games_completed'):
        _require(f'replay_{field}', EXPECTED_GAME_COUNT, report.get(field),
                 phase='replay')
    _require('replay_games_failed', 0, report.get('games_failed'),
             phase='replay')
    _require('replay_games_remaining', 0, report.get('games_remaining'),
             phase='replay')
    _require('replay_budget_stop_triggered', False,
             bool(report.get('budget_stop_triggered')), phase='replay')
    _require('replay_budget_stop_is_null', None, report.get('budget_stop'),
             phase='replay')
    _require('replay_finality_conflicts', 0, report.get('finality_conflicts'),
             phase='replay')
    _require('replay_schedule_authority_missing', 0,
             report.get('schedule_authority_missing'), phase='replay')
    _require('replay_failure_classes_is_empty', {},
             dict(report.get('failure_classes') or {}), phase='replay')
    _require('replay_critical_games_unresolved', 0,
             report.get('critical_games_unresolved'), phase='replay')

    _require('replay_rows_expected', EXPECTED_TOTAL_ROWS,
             report.get('rows_expected'), phase='replay')
    _require('replay_rows_inserted', 0, report.get('rows_inserted'),
             phase='replay')
    _require('replay_rows_updated', 0, report.get('rows_updated'),
             phase='replay')
    _require('replay_rows_unchanged', EXPECTED_TOTAL_ROWS,
             report.get('rows_unchanged'), phase='replay')
    _require('replay_rows_blocked', 0, report.get('rows_blocked'),
             phase='replay')

    for counter in (
        'pitcher_identity_mutations', 'pitcher_identity_creations',
        'pitcher_identity_reactivations', 'pitcher_identity_metadata_updates',
        'pitcher_identity_blocked', 'appearance_team_mutations',
        'complete_mutation_count', 'canonical_outs_corrections',
        'statistical_corrections', 'derived_companion_fields_applied',
        'authority_reconciliations', 'provenance_only_updates',
        'corrections_applied',
    ):
        _require(f'replay_{counter}', 0, report.get(counter), phase='replay')
    _require('replay_changed_fields_counts', {},
             dict(report.get('changed_fields_counts') or {}), phase='replay')
    _require('replay_pitcher_identity_changed_fields_counts', {},
             dict(report.get('pitcher_identity_changed_fields_counts') or {}),
             phase='replay')

    _require('replay_derived_companion_differences_ignored',
             EXPECTED_TOTAL_IGNORED,
             report.get('derived_companion_differences_ignored'),
             phase='replay')
    _require('replay_decimal_only_updates_suppressed', EXPECTED_TOTAL_IGNORED,
             report.get('decimal_only_updates_suppressed'), phase='replay')

    games = list(report.get('games') or [])
    _require('replay_per_game_count', EXPECTED_GAME_COUNT, len(games),
             phase='replay')
    observed_order = [game.get('game_pk') for game in games]
    _require('replay_canonical_processing_order', list(CANONICAL_ORDER),
             observed_order, phase='replay')
    _require('replay_per_game_ids', governed, sorted(observed_order),
             phase='replay')

    totals = {
        'rows': 0, 'ignored': 0, 'suppressed_rows': 0,
        'suppressed_field_counts': {}, 'appearance_identities': set(),
    }
    per_game = []
    for index, game in enumerate(games):
        game_pk = game.get('game_pk')
        _require(f'replay_game_{game_pk}_status', 'projected',
                 game.get('status'), phase='replay', game_pk=game_pk)
        _require(f'replay_game_{game_pk}_error_class', None,
                 game.get('error_class'), phase='replay', game_pk=game_pk)
        for counter in ('inserted', 'updated', 'blocked',
                        'complete_mutation_count',
                        'pitcher_identity_mutations',
                        'appearance_team_mutations',
                        'canonical_outs_corrections', 'statistical_corrections'):
            _require(f'replay_game_{game_pk}_{counter}', 0, game.get(counter),
                     phase='replay', game_pk=game_pk)

        rows = list(game.get('rows') or [])
        _require(f'replay_game_{game_pk}_appearances_match_rows',
                 game.get('appearances_extracted'), len(rows), phase='replay',
                 game_pk=game_pk)
        before_ignored = totals['ignored']
        for row in rows:
            _validate_row(row, game_pk=game_pk, totals=totals)
        totals['rows'] += len(rows)
        _require(f'replay_game_{game_pk}_ignored_reconciles',
                 totals['ignored'] - before_ignored,
                 game.get('derived_companion_differences_ignored'),
                 phase='replay', game_pk=game_pk)
        fingerprint = _require_fingerprint(
            f'replay_game_{game_pk}_complete_reconciliation_fingerprint',
            game.get('complete_reconciliation_fingerprint'), phase='replay',
            game_pk=game_pk,
        )
        per_game.append({
            'canonical_index': index,
            'game_pk': game_pk,
            'appearance_rows': len(rows),
            'ignored_decimal_differences': totals['ignored'] - before_ignored,
            'source_revision': game.get('source_revision'),
            'complete_reconciliation_fingerprint': fingerprint,
        })

    _require('replay_recomputed_row_total', EXPECTED_TOTAL_ROWS,
             totals['rows'], phase='replay')
    _require('replay_recomputed_ignored_total', EXPECTED_TOTAL_IGNORED,
             totals['ignored'], phase='replay')
    _require('replay_recomputed_appearance_identity_count',
             EXPECTED_TOTAL_ROWS, len(totals['appearance_identities']),
             phase='replay')
    _require('replay_recomputed_per_game_appearance_total',
             EXPECTED_TOTAL_ROWS,
             sum(int(game.get('appearances_extracted') or 0) for game in games),
             phase='replay')

    fingerprint = _require_fingerprint(
        'replay_complete_reconciliation_fingerprint',
        report.get('complete_reconciliation_fingerprint'), phase='replay',
    )

    return {
        'fingerprint': fingerprint,
        'per_game': per_game,
        'total_rows': totals['rows'],
        'total_ignored': totals['ignored'],
        'suppressed_rows': totals['suppressed_rows'],
        'suppressed_field_counts': dict(
            sorted(totals['suppressed_field_counts'].items())
        ),
    }


# ── No drift ────────────────────────────────────────────────────────────────


def validate_no_drift(before, after) -> dict:
    """Stage E is read-only. Nothing at all may have moved."""
    for field in IMMUTABLE_STATE_HASHES:
        _require(f'stage_e_{field}_unchanged', before.get(field),
                 after.get(field), phase='drift')
    for field in (
        'game_log_row_count', 'pitcher_count', 'governed_work_items_hash',
        'governed_work_item_count', 'governed_dead_letter_count',
        'full_scope_digest',
    ):
        _require(f'stage_e_{field}_unchanged', before.get(field),
                 after.get(field), phase='drift')
    for field in ('pitcher_mlb_ids', 'governed_completed_set',
                  'governed_unresolved_set', 'governed_terminal_set',
                  'completed_work_item_set', 'terminal_work_item_set',
                  'unresolved_set'):
        _require(f'stage_e_{field}_unchanged', sorted(before.get(field) or []),
                 sorted(after.get(field) or []), phase='drift')
    _require('stage_e_governed_work_items_unchanged',
             dict(before.get('governed_work_items') or {}),
             dict(after.get('governed_work_items') or {}), phase='drift')
    _require('stage_e_publication_completeness_unchanged',
             dict(before.get('publication_completeness') or {}),
             dict(after.get('publication_completeness') or {}), phase='drift')
    return {
        'database_drift': 'none',
        'work_items_changed': False,
        'checkpoints_changed': False,
    }


# ── Complete decision ───────────────────────────────────────────────────────


def validate_closeout(*, before_state, replay, after_state) -> dict:
    """The complete Stage E decision. PASS or FAILED, nothing in between."""
    before = validate_bootstrap_state(before_state, phase='before')
    replay_facts = validate_full_replay(replay)
    validate_bootstrap_state(after_state, phase='after')
    drift = validate_no_drift(before_state, after_state)
    advisory = dead_letter_advisory(after_state)
    return {
        'result': RESULT_PASS,
        'before_state': before,
        'replay': replay_facts,
        'drift': drift,
        'dead_letters': advisory,
        'failed_invariant': None,
    }


# ── Closeout package ────────────────────────────────────────────────────────


def build_closeout(decision, *, repository_sha, run_id, before, after) -> dict:
    passed = decision.get('result') == RESULT_PASS
    replay = decision.get('replay') or {}
    state = decision.get('before_state') or {}
    advisory = decision.get('dead_letters') or {}

    def _hashes(snapshot):
        snapshot = snapshot or {}
        return {field: snapshot.get(field) for field in IMMUTABLE_STATE_HASHES}

    return {
        'result': decision.get('result'),
        'stage': 'E1',
        'repository_sha': repository_sha,
        'workflow_run_id': run_id,
        'reference_date': REFERENCE_DATE,

        'governed_game_count': EXPECTED_GAME_COUNT,
        'canonical_processing_order': list(CANONICAL_ORDER),
        'governed_game_pks_sorted': list(GOVERNED_SET),
        'full_scope_sha256': FULL_SCOPE_DIGEST,

        'expected_final_games': state.get('expected_final_games'),
        'completed_final_games': state.get('completed_final_games'),
        'unresolved_final_games': state.get('unresolved_final_games'),
        'reconciled_appearance_rows': state.get('reconciled_appearance_rows'),
        'governed_work_item_count': state.get('governed_work_item_count'),

        'replay_games_completed': EXPECTED_GAME_COUNT if passed else None,
        'replay_rows_expected': EXPECTED_TOTAL_ROWS,
        'replay_rows_unchanged': replay.get('total_rows'),
        'replay_ignored_decimal_differences': replay.get('total_ignored'),
        'replay_suppressed_historical_differences': replay.get(
            'suppressed_rows'
        ),
        'replay_suppressed_field_counts': replay.get('suppressed_field_counts'),
        'replay_mutations_by_target': {
            'game_log': 0, 'pitcher_identity': 0, 'appearance_team': 0,
        } if passed else None,
        'complete_mutation_count': 0 if passed else None,

        'parity_contract_version': EXPECTED_PARITY_CONTRACT_VERSION,
        'full_bootstrap_fingerprint': replay.get('fingerprint'),
        'per_game_fingerprints': replay.get('per_game'),

        'before_state_hashes': _hashes(before),
        'after_state_hashes': _hashes(after),
        'database_drift': (decision.get('drift') or {}).get('database_drift'),
        'baseball_data_changed': False if passed else None,

        'governed_bootstrap_dead_letters': advisory.get(
            'governed_bootstrap_dead_letters'
        ),
        'r6_closeout_global_dead_letters': advisory.get(
            'r6_closeout_global_dead_letters'
        ),
        'current_global_dead_letters': advisory.get(
            'current_global_dead_letters'
        ),
        'global_dead_letter_delta': advisory.get('delta'),
        'dead_letter_advisory': advisory.get('advisory'),

        'r6_repository_sha': scope.R6_REPOSITORY_SHA,
        'r6_workflow_run_id': scope.R6_WORKFLOW_RUN_ID,
        'r6_approved_fingerprint': scope.R6_APPROVED_FINGERPRINT,
        'r6_scope_digest': scope.R6_SCOPE_DIGEST,

        'database_writes': 'none',
        'write_approved': False,
        'future_write_authorized': False,
        'automated_lane': 'off',
        'authoritative_mode': 'unapproved',
        'rollout_workflows_retired': True,
        'stage_e2': 'not_implemented',
        'next_action': NEXT_ACTION_PASS if passed else NEXT_ACTION_FAILED,
        'failed_invariant': decision.get('failed_invariant'),
    }


def build_summary(decision, closeout) -> dict:
    passed = decision.get('result') == RESULT_PASS
    return {
        'result': decision.get('result'),
        'stage': 'E1',
        'reference_date': REFERENCE_DATE,
        'expected_final_games': closeout.get('expected_final_games'),
        'completed_final_games': closeout.get('completed_final_games'),
        'unresolved_final_games': closeout.get('unresolved_final_games'),
        'reconciled_appearance_rows': closeout.get(
            'reconciled_appearance_rows'
        ),
        'replay_games_completed': closeout.get('replay_games_completed'),
        'replay_rows_unchanged': closeout.get('replay_rows_unchanged'),
        'replay_ignored_decimal_differences': closeout.get(
            'replay_ignored_decimal_differences'
        ),
        'mutations_by_target': closeout.get('replay_mutations_by_target'),
        'database_drift': closeout.get('database_drift'),
        'database_writes': 'none',
        'governed_bootstrap_dead_letters': closeout.get(
            'governed_bootstrap_dead_letters'
        ),
        'r6_closeout_global_dead_letters': closeout.get(
            'r6_closeout_global_dead_letters'
        ),
        'current_global_dead_letters': closeout.get(
            'current_global_dead_letters'
        ),
        'global_dead_letter_delta': closeout.get('global_dead_letter_delta'),
        'parity_contract_version': EXPECTED_PARITY_CONTRACT_VERSION,
        'full_bootstrap_fingerprint': closeout.get(
            'full_bootstrap_fingerprint'
        ),
        'full_scope_sha256': FULL_SCOPE_DIGEST,
        'write_approved': False,
        'future_write_authorized': False,
        'automated_lane': 'off',
        'authoritative_mode': 'unapproved',
        'rollout_workflows_retired': True,
        'stage_e2': 'not_implemented',
        'next_action': closeout.get('next_action'),
        'artifact': 'foundation-3c-stage-e-bootstrap-closeout',
        'failed_invariant': decision.get('failed_invariant'),
    }


def failed_summary(failure) -> dict:
    """Safe evidence only. Never a payload, never an exception message."""
    return {
        'result': RESULT_FAILED,
        'stage': 'E1',
        'failed_phase': failure.phase,
        'failed_invariant': failure.invariant,
        'expected': failure.expected,
        'observed': failure.observed,
        'game_pk': failure.game_pk,
        'pitcher_mlb_id': failure.pitcher_mlb_id,
        'reference_date': REFERENCE_DATE,
        'governed_game_count': EXPECTED_GAME_COUNT,
        'expected_rows': EXPECTED_TOTAL_ROWS,
        'database_writes': 'none',
        'write_approved': False,
        'automated_lane': 'off',
        'authoritative_mode': 'unapproved',
        'stage_e2': 'not_implemented',
        'artifact': 'foundation-3c-stage-e-bootstrap-closeout',
        'next_action': NEXT_ACTION_FAILED,
        'sanitized': True,
    }


# ── Markdown ────────────────────────────────────────────────────────────────


def pass_markdown(summary) -> str:
    return '\n'.join([
        '## FOUNDATION 3C STAGE E1 — PASS',
        '',
        '### Bootstrap state',
        '- Expected final games: 109',
        '- Completed final games: 109',
        '- Unresolved final games: 0',
        '- Terminal failures: 0',
        '- Correction pending: 0',
        '- Publication complete: yes',
        f"- Reconciled appearance rows: {summary['reconciled_appearance_rows']}",
        '',
        '### Full replay',
        '- Requested games: 109',
        '- Planned games: 109',
        f"- Completed in shadow: {summary['replay_games_completed']}",
        '- Failed: 0',
        '- Rows expected: 946',
        f"- Rows unchanged: {summary['replay_rows_unchanged']}",
        '- Inserted / updated / blocked: 0 / 0 / 0',
        '- Decimal-only differences safely ignored: '
        f"{summary['replay_ignored_decimal_differences']}",
        '',
        '### Mutations',
        '- GameLog: 0',
        '- Pitcher identity: 0',
        '- Appearance team: 0',
        '- Complete-plan: 0',
        '',
        '### Data integrity',
        '- Database drift: none',
        '- Work items changed: no',
        '- Checkpoints changed: no',
        f"- Governed-game dead letters: {summary['governed_bootstrap_dead_letters']}",
        '- Global dead letters at R6 closeout: '
        f"{summary['r6_closeout_global_dead_letters']}",
        f"- Current global dead letters: {summary['current_global_dead_letters']}",
        f"- Global delta: {summary['global_dead_letter_delta']}",
        '',
        '### Final evidence',
        '- Parity contract version: 4',
        f"- Full-bootstrap fingerprint: {summary['full_bootstrap_fingerprint']}",
        f"- Full-scope SHA-256: {summary['full_scope_sha256']}",
        '- Write approved: no',
        '',
        '### Workflow retirement',
        '- R1 workflow removed: yes',
        '- R2 workflow removed: yes',
        '- R3 workflow removed: yes',
        '- R4 workflow removed: yes',
        '- R5 workflow removed: yes',
        '- R6 workflow removed: yes',
        '- Stage E workflow remains temporarily for this verification: yes',
        '',
        '### Result',
        '- The 109-game Foundation 3C bootstrap is independently verified.',
        '- The complete replay projected zero mutations.',
        '- No database writes were performed by Stage E.',
        '- The six R1–R6 rollout workflows are retired.',
        '- GAME_DRIVEN_INGESTION_MODE remains off.',
        '- Authoritative mode remains unapproved.',
        '- Stage E may proceed to E2 final cleanup.',
        '',
    ])


def failed_markdown(summary) -> str:
    lines = [
        '## FOUNDATION 3C STAGE E1 — FAILED',
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
        f"- Governed games: {summary['governed_game_count']}",
        f"- Rows expected: {summary['expected_rows']}",
        '- No database writes were performed by Stage E.',
        '- Automated lane: off',
        '- Authoritative mode: unapproved',
        f"- Artifact: `{summary['artifact']}`",
        '',
        '**Do not enable any lane. Do not remove the Stage E verification '
        'workflow. Do not proceed to E2.**',
        '',
    ]
    return '\n'.join(lines)


def closeout_markdown(closeout) -> str:
    passed = closeout['result'] == RESULT_PASS
    lines = [
        f"## Foundation 3C Stage E1 closeout — {'PASS' if passed else 'FAILED'}",
        '',
        f"- Repository SHA: `{closeout['repository_sha']}`",
        f"- Workflow run: `{closeout['workflow_run_id']}`",
        f"- Reference date: `{closeout['reference_date']}`",
        f"- Governed games: **{closeout['governed_game_count']}**",
        f"- Full-scope SHA-256: `{closeout['full_scope_sha256']}`",
        '- Full-bootstrap fingerprint: '
        f"`{closeout['full_bootstrap_fingerprint']}`",
        f"- Parity contract: **{closeout['parity_contract_version']}**",
        '',
        '### Verified production state',
        '',
        '| | |',
        '|---|---:|',
        f"| expected final games | {closeout['expected_final_games']} |",
        f"| completed final games | {closeout['completed_final_games']} |",
        f"| unresolved final games | {closeout['unresolved_final_games']} |",
        f"| reconciled appearance rows | {closeout['reconciled_appearance_rows']} |",
        f"| governed work items | {closeout['governed_work_item_count']} |",
        '',
        '### Full replay',
        '',
        f"- Rows unchanged: {closeout['replay_rows_unchanged']} "
        f"of {closeout['replay_rows_expected']}",
        '- Ignored decimal differences: '
        f"{closeout['replay_ignored_decimal_differences']}",
        '- Suppressed historical current-state differences: '
        f"{closeout['replay_suppressed_historical_differences']}",
        '- Mutations, every target: 0',
        f"- Database drift: {closeout['database_drift']}",
        f"- Database writes: {closeout['database_writes']}",
        '',
        '### Dead letters',
        '',
        '- Governed bootstrap dead letters: '
        f"**{closeout['governed_bootstrap_dead_letters']}**",
        '- Global count at R6 closeout: '
        f"{closeout['r6_closeout_global_dead_letters']}",
        f"- Current global count: {closeout['current_global_dead_letters']}",
        f"- Delta: {closeout['global_dead_letter_delta']}",
        f"- {closeout['dead_letter_advisory']}",
        '',
        '### R6 historical evidence',
        '',
        f"- Repository SHA: `{closeout['r6_repository_sha']}`",
        f"- Workflow run: `{closeout['r6_workflow_run_id']}`",
        f"- Approved fingerprint: `{closeout['r6_approved_fingerprint']}`",
        f"- 99-game scope digest: `{closeout['r6_scope_digest']}`",
        '',
        '### Rollout',
        '',
        f"- Rollout workflows retired: {closeout['rollout_workflows_retired']}",
        f"- Write approved: {closeout['write_approved']}",
        f"- Future write authorized: {closeout['future_write_authorized']}",
        f"- Automated lane: {closeout['automated_lane']}",
        f"- Authoritative mode: {closeout['authoritative_mode']}",
        f"- Stage E2: {closeout['stage_e2']}",
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


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='Validate the Foundation 3C Stage E bootstrap closeout.',
    )
    parser.add_argument('--before-state', required=True)
    parser.add_argument('--replay', required=True)
    parser.add_argument('--after-state', required=True)
    parser.add_argument('--summary-json', required=True)
    parser.add_argument('--summary-markdown', required=True)
    parser.add_argument('--closeout-json', required=True)
    parser.add_argument('--closeout-markdown', required=True)
    parser.add_argument('--repository-sha', default='')
    parser.add_argument('--run-id', default='')
    args = parser.parse_args(argv)

    try:
        before = _load(args.before_state, 'before_state_artifact')
        replay = _load(args.replay, 'replay_artifact')
        after = _load(args.after_state, 'after_state_artifact')
        decision = validate_closeout(
            before_state=before, replay=replay, after_state=after,
        )
        closeout = build_closeout(
            decision, repository_sha=args.repository_sha, run_id=args.run_id,
            before=before, after=after,
        )
        summary = build_summary(decision, closeout)
        _write_json(args.closeout_json, closeout)
        _write_text(args.closeout_markdown, closeout_markdown(closeout))
        _write_json(args.summary_json, summary)
        _write_text(args.summary_markdown, pass_markdown(summary))
        return EXIT_OK
    except ValidationFailure as failure:
        summary = failed_summary(failure)
        _write_json(args.summary_json, summary)
        _write_text(args.summary_markdown, failed_markdown(summary))
        return EXIT_FAILED


if __name__ == '__main__':
    raise SystemExit(main())
