#!/usr/bin/env python
"""Validate the Foundation 3C R5 full remaining-window shadow.

R5 is the last read-only gate before a 99-game production write. Everything it
produces is evidence for that decision, so this validator fails closed on every
difference: there is no `review_required` tier and no invariant that degrades to
a warning. PASS means every one of the 99 games projected no mutation to any
database target, and the run left production byte-identical.

Three things it deliberately does NOT do:

  * It does not recompute the reconciliation fingerprint. The planner's value is
    the authority; a validator that computes its own is only checking itself.
  * It does not trust aggregate counters. Row totals, ignored-difference totals,
    and mutation counts are all recomputed from the per-row detail and compared
    against the aggregate, because an aggregate is exactly what a bug would get
    right while the detail disagreed.
  * It does not accept a scope discovered at runtime. The 99 games are imported
    from the pinned scope module and the report must match them exactly, in the
    canonical order, with no completed game present.

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
EXPECTED_GAME_COUNT = scope.EXPECTED_GAME_COUNT
EXPECTED_TOTAL_ROWS = scope.EXPECTED_TOTAL_ROWS            # 865
EXPECTED_TOTAL_IGNORED = scope.EXPECTED_TOTAL_IGNORED      # 291
SCOPE_DIGEST = scope.SCOPE_DIGEST

EXPECTED_PARITY_CONTRACT_VERSION = '4'

# Production must still be exactly where R4 left it.
BEFORE_COMPLETENESS = {
    'expected_final_games': 109,
    'completed_final_games': 10,
    'unresolved_final_games': 99,
    'terminal_failure_games': 0,
    'correction_pending_games': 0,
    'publication_complete': False,
}

PROHIBITED_SEMANTIC_FIELDS = frozenset(reconciliation.DERIVED_COMPANION_FIELDS)
FORBIDDEN_IDENTITY_ACTIONS = frozenset(
    set(identity.MUTATING_ACTIONS)
    | set(identity.RETIRED_WRITE_ACTIONS)
    | {identity.ACTION_BLOCKED}
)

# The exact field set `identity.suppressed_current_state_fields` can emit.
# Deliberately narrower than KNOWN_IDENTITY_FIELDS: a suppressed difference
# names a field the completed game WOULD have rewritten, and only these can be
# produced by that path. A test probes the real function to prove the set has
# not grown behind this constant.
APPROVED_SUPPRESSIBLE_FIELDS = frozenset({
    'active',
    'full_name',
    'position',
    'roster_status',
    'team_abbreviation',
    'team_id',
    'team_name',
})

FINGERPRINT_PATTERN = re.compile(r'^[0-9a-f]{64}$')

# Baseball-data families that must be byte-identical across the shadow.
IMMUTABLE_STATE_HASHES = (
    'game_log_content_hash',
    'canonical_outs_hash',
    'correction_provenance_hash',
    'appearance_team_hash',
    'pitcher_state_hash',
)

# Exclusive scope short-circuits every candidate to the explicit reason, so
# `newly_final` is unreachable here and requiring it would fail every run.
EXPECTED_CANDIDATE_REASON = GameIngestionWorkItem.REASON_EXPLICIT_REPAIR

R6_STATUS_BLOCKED = 'blocked_pending_founder_review'


class ValidationFailure(Exception):
    """One named invariant did not hold. R5 stops here."""

    def __init__(self, invariant, expected, observed, game_pk=None,
                 pitcher_mlb_id=None):
        super().__init__(invariant)
        self.invariant = invariant
        self.expected = expected
        self.observed = observed
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

    Everything here runs before the shadow. If production has moved since R4,
    the reviewed scope is stale and the run must not start.
    """
    if not isinstance(before, dict):
        raise ValidationFailure('before_state_is_an_object', 'object',
                                type(before).__name__)
    _require('before_state_phase', 'before', before.get('phase'))
    _require_true('before_state_read_only',
                  (before.get('read_only') or {}).get('write_probe_refused'))
    _require('before_state_reference_date', REFERENCE_DATE,
             before.get('reference_date'))

    # ── Exact scope, proven against the database ────────────────────────────
    _require('before_state_selected_game_count', EXPECTED_GAME_COUNT,
             before.get('selected_game_count'))
    _require('before_state_selected_game_pks', list(APPROVED_SET),
             sorted(before.get('selected_game_pks') or []))
    _require('before_state_scope_digest', SCOPE_DIGEST,
             before.get('selected_scope_digest'))
    _require('before_state_approved_completed_game_pks',
             list(COMPLETED_GAME_PKS),
             sorted(before.get('approved_completed_game_pks') or []))

    # ── Completeness ────────────────────────────────────────────────────────
    completeness = dict(before.get('publication_completeness') or {})
    for field, expected in BEFORE_COMPLETENESS.items():
        observed = completeness.get(field)
        if field == 'publication_complete':
            observed = bool(observed)
        _require(f'before_state_completeness_{field}', expected, observed)

    # ── The completed set is EXACTLY the approved ten ───────────────────────
    _require('before_state_completed_work_item_set', list(COMPLETED_GAME_PKS),
             sorted(before.get('completed_work_item_set') or []))
    _require('before_state_unresolved_set', list(APPROVED_SET),
             sorted(before.get('unresolved_set') or []))
    _require('before_state_terminal_work_item_set', [],
             sorted(before.get('terminal_work_item_set') or []))

    # ── No selected game may carry ANY work item ────────────────────────────
    # No completed checkpoint, no partial attempt, no retry, no correction
    # state, no terminal status: for these games the absence of a work item is
    # what "unresolved" means, so any row at all is a stop.
    work_items = dict(before.get('selected_work_items') or {})
    if work_items:
        raise ValidationFailure(
            'before_state_selected_games_have_no_work_item', 0,
            len(work_items),
            game_pk=sorted(int(pk) for pk in work_items)[:20],
        )
    _require('before_state_selected_work_item_count', 0,
             before.get('selected_work_item_count'))

    # ── Every selected game is planned, final, critical, and untouched ──────
    # This is where finality and prior status are actually proven. The run
    # report does not carry either, so asserting them there would prove
    # nothing; the durable plan is the authority.
    for field in (
        'non_critical_selected_game_pks',
        'unplanned_selected_game_pks',
        'non_final_selected_game_pks',
        'selected_game_pks_with_prior_status',
        'selected_game_pks_with_prior_attempts',
    ):
        if field not in before:
            raise ValidationFailure(f'before_state_{field}_present', 'present',
                                    'missing')
        _require(f'before_state_{field}', [], sorted(before.get(field) or []))

    _require('before_state_finality_conflicts', 0,
             before.get('finality_conflicts'))
    _require('before_state_schedule_authority_missing', 0,
             before.get('schedule_authority_missing'))

    return {
        'completed_final_games': completeness.get('completed_final_games'),
        'unresolved_final_games': completeness.get('unresolved_final_games'),
        'expected_final_games': completeness.get('expected_final_games'),
        'scope_digest': before.get('selected_scope_digest'),
    }


# ── Shadow report ───────────────────────────────────────────────────────────


def _validate_row(row, *, game_pk, totals):
    """One appearance row. Unchanged on every target, or R5 fails."""
    pitcher_mlb_id = row.get('pitcher_mlb_id')
    label = f'{game_pk}_{pitcher_mlb_id}'
    context = {'game_pk': game_pk, 'pitcher_mlb_id': pitcher_mlb_id}

    # ── GameLog ─────────────────────────────────────────────────────────────
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

    # ── Pitcher identity ────────────────────────────────────────────────────
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

    # ── Suppressed historical current-state evidence ────────────────────────
    # Expected D-009 evidence, not a mutation: current roster and team state
    # can legitimately have moved since R2 without changing what happened in a
    # completed game. It must stay visible, name only an approved protected
    # field, and say out loud that it was refused.
    suppressed = list(row.get('pitcher_identity_suppressed_fields') or [])
    for field in suppressed:
        if field not in APPROVED_SUPPRESSIBLE_FIELDS:
            raise ValidationFailure(
                f'row_{label}_suppressed_field_is_approved',
                'an approved protected current-state field', field, **context,
            )
    if suppressed:
        _require_true(f'row_{label}_current_authority_mutation_refused',
                      row.get('pitcher_identity_current_authority_mutation_refused'),
                      **context)
        totals['suppressed_rows'] += 1
        for field in suppressed:
            totals['suppressed_field_counts'][field] = (
                totals['suppressed_field_counts'].get(field, 0) + 1
            )

    # ── Appearance-team authority ───────────────────────────────────────────
    # `plan_update` returns None when the row would not change and a decision
    # dict when it would, so an absent decision IS the no-drift proof. Asserted
    # on the decision itself rather than on a changed-field list, because this
    # planner does not publish one and an assertion against a key that does not
    # exist would pass vacuously.
    _require(f'row_{label}_appearance_team_reason', None,
             row.get('appearance_team_reason'), **context)
    _require(f'row_{label}_appearance_team_decision', None,
             row.get('appearance_team_decision'), **context)

    # ── Canonical innings ───────────────────────────────────────────────────
    # A decimal-only difference may appear ONLY as an explicit ignored
    # companion on an unchanged row, and only for a known companion field.
    ignored = list(row.get('derived_companion_differences_ignored') or [])
    for field in ignored:
        if field not in PROHIBITED_SEMANTIC_FIELDS:
            raise ValidationFailure(
                f'row_{label}_ignored_difference_is_a_known_companion',
                'a known derived companion field', field, **context,
            )
    totals['ignored'] += len(ignored)

    identity_key = (game_pk, pitcher_mlb_id)
    if identity_key in totals['appearance_identities']:
        raise ValidationFailure('duplicate_appearance_identity',
                                'one row per (game_pk, pitcher_mlb_id)',
                                'duplicate', **context)
    totals['appearance_identities'].add(identity_key)


def validate_shadow_report(report) -> dict:
    """Everything the 99-game exclusive shadow must satisfy."""
    if not isinstance(report, dict):
        raise ValidationFailure('shadow_report_is_an_object', 'object',
                                type(report).__name__)

    approved = list(APPROVED_SET)

    # ── Identity ────────────────────────────────────────────────────────────
    _require('shadow_status', 'complete', report.get('status'))
    _require('shadow_mode', 'shadow', report.get('mode'))
    _require('shadow_reference_date', REFERENCE_DATE,
             report.get('reference_date'))
    _require('shadow_execution_scope_mode', 'exclusive',
             report.get('execution_scope_mode'))

    for field, expected in (
        ('reconciliation_plan_version',
         reconciliation.RECONCILIATION_PLAN_VERSION),
        ('parity_contract_version', reconciliation.PARITY_CONTRACT_VERSION),
        ('innings_semantics_version', reconciliation.INNINGS_SEMANTICS_VERSION),
        ('complete_plan_version', reconciliation.COMPLETE_PLAN_VERSION),
        ('identity_plan_version', identity.IDENTITY_PLAN_VERSION),
    ):
        _require(f'shadow_{field}', expected, report.get(field))
    _require('shadow_parity_contract_is_4', EXPECTED_PARITY_CONTRACT_VERSION,
             report.get('parity_contract_version'))

    # ── Exact scope ─────────────────────────────────────────────────────────
    _require('shadow_requested_game_count', EXPECTED_GAME_COUNT,
             report.get('requested_game_count'))
    _require('shadow_planned_game_count', EXPECTED_GAME_COUNT,
             report.get('planned_game_count'))
    _require('shadow_duplicate_requested_count', 0,
             report.get('duplicate_requested_count'))
    _require_true('shadow_execution_scope_exact_match',
                  report.get('execution_scope_exact_match'))
    _require('shadow_requested_game_pks', approved,
             sorted(report.get('requested_game_pks') or []))
    _require('shadow_planned_game_pks', approved,
             sorted(report.get('planned_game_pks') or []))
    _require('shadow_unexpected_planned_game_pks', [],
             list(report.get('unexpected_planned_game_pks') or []))
    _require('shadow_missing_requested_game_pks', [],
             list(report.get('missing_requested_game_pks') or []))

    # ── Games ───────────────────────────────────────────────────────────────
    for field in ('games_attempted', 'games_fetched', 'games_completed'):
        _require(f'shadow_{field}', EXPECTED_GAME_COUNT, report.get(field))
    _require('shadow_games_failed', 0, report.get('games_failed'))
    _require('shadow_games_remaining', 0, report.get('games_remaining'))
    _require('shadow_budget_stop_triggered', False,
             bool(report.get('budget_stop_triggered')))
    _require('shadow_budget_stop_is_null', None, report.get('budget_stop'))
    _require('shadow_finality_conflicts', 0, report.get('finality_conflicts'))
    _require('shadow_schedule_authority_missing', 0,
             report.get('schedule_authority_missing'))
    _require('shadow_failure_classes_is_empty', {},
             dict(report.get('failure_classes') or {}))
    _require('shadow_critical_games_unresolved', 0,
             report.get('critical_games_unresolved'))
    _require('shadow_best_effort_games_deferred', 0,
             report.get('best_effort_games_deferred'))

    # ── Aggregate rows and mutations ────────────────────────────────────────
    _require('shadow_rows_expected', EXPECTED_TOTAL_ROWS,
             report.get('rows_expected'))
    _require('shadow_rows_inserted', 0, report.get('rows_inserted'))
    _require('shadow_rows_updated', 0, report.get('rows_updated'))
    _require('shadow_rows_unchanged', EXPECTED_TOTAL_ROWS,
             report.get('rows_unchanged'))
    _require('shadow_rows_blocked', 0, report.get('rows_blocked'))
    _require(
        'shadow_row_totals_reconcile', EXPECTED_TOTAL_ROWS,
        int(report.get('rows_inserted') or 0)
        + int(report.get('rows_updated') or 0)
        + int(report.get('rows_unchanged') or 0)
        + int(report.get('rows_blocked') or 0),
    )

    for counter in (
        'pitcher_identity_mutations', 'pitcher_identity_creations',
        'pitcher_identity_reactivations', 'pitcher_identity_metadata_updates',
        'pitcher_identity_blocked', 'appearance_team_mutations',
        'complete_mutation_count', 'canonical_outs_corrections',
        'statistical_corrections', 'derived_companion_fields_applied',
        'authority_reconciliations', 'provenance_only_updates',
        'corrections_applied',
    ):
        _require(f'shadow_{counter}', 0, report.get(counter))
    _require('shadow_changed_fields_counts', {},
             dict(report.get('changed_fields_counts') or {}))
    _require('shadow_pitcher_identity_changed_fields_counts', {},
             dict(report.get('pitcher_identity_changed_fields_counts') or {}))
    _require('shadow_pitcher_identity_rows_examined', EXPECTED_TOTAL_ROWS,
             report.get('pitcher_identity_rows_examined'))

    _require('shadow_derived_companion_differences_ignored',
             EXPECTED_TOTAL_IGNORED,
             report.get('derived_companion_differences_ignored'))
    _require('shadow_decimal_only_updates_suppressed', EXPECTED_TOTAL_IGNORED,
             report.get('decimal_only_updates_suppressed'))

    # ── Per game, in canonical order ────────────────────────────────────────
    games = list(report.get('games') or [])
    _require('shadow_per_game_count', EXPECTED_GAME_COUNT, len(games))
    observed_order = [game.get('game_pk') for game in games]

    # Checked BEFORE the ordering and set comparisons on purpose. A completed
    # game reaching the run is the single most consequential scope failure R5
    # can have, and it deserves its own named invariant rather than being
    # reported as a generic ordering mismatch.
    intruders = sorted(set(observed_order) & set(COMPLETED_GAME_PKS))
    if intruders:
        raise ValidationFailure('shadow_excludes_completed_games', [],
                                intruders)

    _require('shadow_canonical_processing_order', list(APPROVED_ORDER),
             observed_order)
    _require('shadow_per_game_ids', approved, sorted(observed_order))

    totals = {
        'rows': 0,
        'ignored': 0,
        'suppressed_rows': 0,
        'suppressed_field_counts': {},
        'appearance_identities': set(),
    }
    per_game = []
    for index, game in enumerate(games):
        game_pk = game.get('game_pk')
        _require(f'game_{game_pk}_status', 'projected', game.get('status'))
        _require(f'game_{game_pk}_error_class', None, game.get('error_class'),
                 game_pk=game_pk)
        for counter in ('inserted', 'updated', 'blocked',
                        'complete_mutation_count', 'pitcher_identity_mutations',
                        'appearance_team_mutations',
                        'canonical_outs_corrections', 'statistical_corrections'):
            _require(f'game_{game_pk}_{counter}', 0, game.get(counter),
                     game_pk=game_pk)

        # ── Eligibility, from the run's own view of durable state ───────────
        # attempt_number is (attempt_count + 1), so 1 proves no work item and
        # therefore no completed checkpoint, no partial attempt, no retry and
        # no correction re-check. Finality and prior status are NOT asserted
        # here: the per-game report does not carry them, and an assertion
        # against absent keys would pass while proving nothing. They are proven
        # against the before-state snapshot instead, which is where the durable
        # answer actually lives.
        _require(f'game_{game_pk}_attempt_number', 1, game.get('attempt_number'),
                 game_pk=game_pk)
        _require(f'game_{game_pk}_criticality',
                 GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL,
                 game.get('criticality'), game_pk=game_pk)
        _require(f'game_{game_pk}_candidate_reason', EXPECTED_CANDIDATE_REASON,
                 game.get('candidate_reason'), game_pk=game_pk)

        rows = list(game.get('rows') or [])
        _require(f'game_{game_pk}_appearances_match_rows',
                 game.get('appearances_extracted'), len(rows), game_pk=game_pk)
        game_ignored_before = totals['ignored']
        for row in rows:
            _validate_row(row, game_pk=game_pk, totals=totals)
        totals['rows'] += len(rows)
        game_ignored = totals['ignored'] - game_ignored_before
        _require(f'game_{game_pk}_ignored_reconciles', game_ignored,
                 game.get('derived_companion_differences_ignored'),
                 game_pk=game_pk)

        game_fingerprint = _require_fingerprint(
            f'game_{game_pk}_complete_reconciliation_fingerprint',
            game.get('complete_reconciliation_fingerprint'), game_pk=game_pk,
        )
        per_game.append({
            'canonical_index': index,
            'game_pk': game_pk,
            'represented_date': game.get('represented_date'),
            'candidate_reason': game.get('candidate_reason'),
            'prior_status': None,
            'attempt_number': game.get('attempt_number'),
            'criticality': game.get('criticality'),
            'appearance_rows': len(rows),
            'ignored_decimal_differences': game_ignored,
            'suppressed_historical_differences': sum(
                1 for row in rows
                if row.get('pitcher_identity_suppressed_fields')
            ),
            'game_log_mutations': 0,
            'pitcher_identity_mutations': 0,
            'appearance_team_mutations': 0,
            'blocked': 0,
            'source_revision': game.get('source_revision'),
            'complete_reconciliation_fingerprint': game_fingerprint,
        })

    # ── Recomputed totals must equal the aggregates ─────────────────────────
    _require('recomputed_row_total', EXPECTED_TOTAL_ROWS, totals['rows'])
    _require('recomputed_ignored_total', EXPECTED_TOTAL_IGNORED,
             totals['ignored'])
    _require('recomputed_appearance_identity_count', EXPECTED_TOTAL_ROWS,
             len(totals['appearance_identities']))
    _require('recomputed_per_game_appearance_total', EXPECTED_TOTAL_ROWS,
             sum(int(game.get('appearances_extracted') or 0) for game in games))

    fingerprint = _require_fingerprint(
        'shadow_complete_reconciliation_fingerprint',
        report.get('complete_reconciliation_fingerprint'),
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


# ── State comparison ────────────────────────────────────────────────────────


def validate_state_transition(before, after) -> dict:
    """Nothing at all may have moved. R5 is read-only."""
    if not isinstance(after, dict):
        raise ValidationFailure('after_state_is_an_object', 'object',
                                type(after).__name__)
    _require('after_state_phase', 'after', after.get('phase'))
    _require_true('after_state_read_only',
                  (after.get('read_only') or {}).get('write_probe_refused'))

    for field in IMMUTABLE_STATE_HASHES:
        _require(f'state_{field}_unchanged', before.get(field), after.get(field))

    for field in (
        'game_log_row_count', 'pitcher_count', 'all_work_items_hash',
        'all_work_item_count', 'selected_work_item_count', 'dead_letter_count',
        'selected_scope_digest', 'finality_conflicts',
        'schedule_authority_missing',
    ):
        _require(f'state_{field}_unchanged', before.get(field), after.get(field))

    for field in ('pitcher_mlb_ids', 'completed_work_item_set',
                  'unresolved_set', 'terminal_work_item_set'):
        _require(f'state_{field}_unchanged', sorted(before.get(field) or []),
                 sorted(after.get(field) or []))

    # Shadow must not have created a work item for any selected game.
    _require('state_no_selected_work_item_created', {},
             dict(after.get('selected_work_items') or {}))

    before_completeness = dict(before.get('publication_completeness') or {})
    after_completeness = dict(after.get('publication_completeness') or {})
    _require('state_publication_completeness_unchanged', before_completeness,
             after_completeness)
    for field, expected in BEFORE_COMPLETENESS.items():
        observed = after_completeness.get(field)
        if field == 'publication_complete':
            observed = bool(observed)
        _require(f'after_state_completeness_{field}', expected, observed)

    return {
        'database_drift': 'none',
        'work_items_created': 0,
        'checkpoints_completed': 0,
        'dead_letters_created': 0,
        'completed_final_games': after_completeness.get('completed_final_games'),
        'unresolved_final_games': after_completeness.get(
            'unresolved_final_games'
        ),
    }


# ── Complete decision ───────────────────────────────────────────────────────


def validate_r5(*, before_state, shadow, after_state) -> dict:
    """The complete R5 decision. PASS or FAILED, nothing in between."""
    state = validate_before_state(before_state)
    shadow_facts = validate_shadow_report(shadow)
    transition = validate_state_transition(before_state, after_state)
    return {
        'result': RESULT_PASS,
        'before_state': state,
        'shadow': shadow_facts,
        'transition': transition,
        'failed_invariant': None,
    }


# ── Authorization package ───────────────────────────────────────────────────


NEXT_ACTION_PASS = (
    'Review the R5 authorization package, then implement R6 as one full '
    'remaining-window write of the same 99 games. Do not select another '
    'small sample.'
)
NEXT_ACTION_FAILED = (
    'Stop Foundation 3C. Do not implement or execute R6 without founder '
    'review.'
)


def build_authorization(decision, *, repository_sha, run_id) -> dict:
    shadow = decision['shadow']
    transition = decision['transition']
    return {
        'result': decision['result'],
        'repository_sha': repository_sha,
        'workflow_run_id': run_id,
        'reference_date': REFERENCE_DATE,

        'completed_game_pks': list(COMPLETED_GAME_PKS),
        'unresolved_game_pks_sorted': list(APPROVED_SET),
        'canonical_processing_order': list(APPROVED_ORDER),
        'scope_set_sha256': SCOPE_DIGEST,

        'games_requested': EXPECTED_GAME_COUNT,
        'games_planned': EXPECTED_GAME_COUNT,
        'games_completed': EXPECTED_GAME_COUNT,
        'games_failed': 0,
        'exact_scope': True,
        'eligibility': 'all_99_unresolved_publication_critical_attempt_1',

        'games': shadow['per_game'],

        'total_appearance_rows': shadow['total_rows'],
        'total_ignored_decimal_differences': shadow['total_ignored'],
        'total_suppressed_historical_differences': shadow['suppressed_rows'],
        'suppressed_field_counts': shadow['suppressed_field_counts'],

        'mutations_by_target': {
            'game_log': 0,
            'pitcher_identity': 0,
            'appearance_team': 0,
        },
        'complete_mutation_count': 0,
        'complete_reconciliation_fingerprint': shadow['fingerprint'],

        'versions': {
            'reconciliation_plan_version':
                reconciliation.RECONCILIATION_PLAN_VERSION,
            'parity_contract_version': reconciliation.PARITY_CONTRACT_VERSION,
            'innings_semantics_version':
                reconciliation.INNINGS_SEMANTICS_VERSION,
            'complete_plan_version': reconciliation.COMPLETE_PLAN_VERSION,
            'identity_plan_version': identity.IDENTITY_PLAN_VERSION,
        },

        'before_state_hashes': {
            field: (decision.get('_before') or {}).get(field)
            for field in IMMUTABLE_STATE_HASHES
        },
        'after_state_hashes': {
            field: (decision.get('_after') or {}).get(field)
            for field in IMMUTABLE_STATE_HASHES
        },
        'publication_completeness': {
            'expected_final_games': 109,
            'completed_final_games': 10,
            'unresolved_final_games': 99,
            'terminal_failure_games': 0,
            'correction_pending_games': 0,
            'publication_complete': False,
        },
        'database_drift': transition['database_drift'],
        'database_writes': 'none',
        'write_approved': False,
        'r6_status': R6_STATUS_BLOCKED,
        'authoritative_mode': 'unapproved',
        'automated_lane': 'off',
    }


def build_r6_manifest(decision) -> dict:
    """A reviewed INPUT package for the next prompt. Not an executable."""
    shadow = decision['shadow']
    return {
        'document': 'foundation_3c_r6_command_manifest',
        'executable': False,
        'note': (
            'Reviewed input for the R6 implementation prompt. Not a script, '
            'not a workflow, and not runnable as written.'
        ),
        'reference_date': REFERENCE_DATE,
        'canonical_processing_order': list(APPROVED_ORDER),
        'unresolved_game_pks_sorted': list(APPROVED_SET),
        'scope_set_sha256': SCOPE_DIGEST,
        'game_count': EXPECTED_GAME_COUNT,
        'versions': {
            'reconciliation_plan_version':
                reconciliation.RECONCILIATION_PLAN_VERSION,
            'parity_contract_version': reconciliation.PARITY_CONTRACT_VERSION,
            'innings_semantics_version':
                reconciliation.INNINGS_SEMANTICS_VERSION,
            'complete_plan_version': reconciliation.COMPLETE_PLAN_VERSION,
            'identity_plan_version': identity.IDENTITY_PLAN_VERSION,
        },
        'approved_complete_fingerprint_candidate': shadow['fingerprint'],
        'expected_rows': EXPECTED_TOTAL_ROWS,
        'expected_ignored_decimal_differences': EXPECTED_TOTAL_IGNORED,
        'required_only_game_pk_arguments': scope.only_game_pk_arguments(),
        'required_expected_plan_fingerprint': shadow['fingerprint'],
        'stale_or_invalid_fingerprints': [],
        'write_approved': False,
        'founder_review_required': True,
        'r6_implemented': False,
        'r6_executed': False,
        'r6_status': R6_STATUS_BLOCKED,
    }


def build_summary(decision) -> dict:
    shadow = decision['shadow']
    return {
        'result': decision['result'],
        'reference_date': REFERENCE_DATE,
        'expected_final_games': 109,
        'completed_final_games': 10,
        'unresolved_final_games': 99,
        'terminal_failure_games': 0,
        'publication_complete': False,
        'games_requested': EXPECTED_GAME_COUNT,
        'games_planned': EXPECTED_GAME_COUNT,
        'games_completed': EXPECTED_GAME_COUNT,
        'games_failed': 0,
        'completed_games_excluded': len(COMPLETED_GAME_PKS),
        'rows_expected': EXPECTED_TOTAL_ROWS,
        'rows_inserted': 0,
        'rows_updated': 0,
        'rows_unchanged': shadow['total_rows'],
        'rows_blocked': 0,
        'mutations_by_target': {
            'game_log': 0, 'pitcher_identity': 0, 'appearance_team': 0,
        },
        'complete_mutation_count': 0,
        'suppressed_historical_differences': shadow['suppressed_rows'],
        'ignored_decimal_differences': shadow['total_ignored'],
        'canonical_outs_corrections': 0,
        'parity_contract_version': EXPECTED_PARITY_CONTRACT_VERSION,
        'complete_reconciliation_fingerprint': shadow['fingerprint'],
        'scope_set_sha256': SCOPE_DIGEST,
        'database_writes': 'none',
        'database_drift': 'none',
        'work_items_created': 0,
        'checkpoints_completed': 0,
        'dead_letters_created': 0,
        'write_approved': False,
        'r6_status': R6_STATUS_BLOCKED,
        'automated_lane': 'off',
        'authoritative_mode': 'unapproved',
        'next_action': NEXT_ACTION_PASS,
        'artifact': 'foundation-3c-r5-remaining-window-shadow',
        'failed_invariant': None,
    }


def failed_summary(failure) -> dict:
    """Safe evidence only. Never a payload, never an exception message."""
    return {
        'result': RESULT_FAILED,
        'failed_invariant': failure.invariant,
        'expected': failure.expected,
        'observed': failure.observed,
        'game_pk': failure.game_pk,
        'pitcher_mlb_id': failure.pitcher_mlb_id,
        'reference_date': REFERENCE_DATE,
        'games_requested': EXPECTED_GAME_COUNT,
        'rows_expected': EXPECTED_TOTAL_ROWS,
        'expected_final_games': 109,
        'completed_final_games': 10,
        'unresolved_final_games': 99,
        'write_approved': False,
        'r6_status': R6_STATUS_BLOCKED,
        'r6_blocked': True,
        'database_writes': 'none',
        'artifact': 'foundation-3c-r5-remaining-window-shadow',
        'next_action': NEXT_ACTION_FAILED,
        'sanitized': True,
    }


# ── Markdown ────────────────────────────────────────────────────────────────


def pass_markdown(summary) -> str:
    return '\n'.join([
        '## FOUNDATION 3C R5 — PASS',
        '',
        '### Production state',
        '- Expected final games: 109',
        '- Completed final games: 10',
        '- Unresolved final games: 99',
        '- Terminal failures: 0',
        '- Publication complete: no',
        '',
        '### Remaining-window scope',
        f"- Requested: {summary['games_requested']}",
        f"- Planned: {summary['games_planned']}",
        '- Exact scope: yes',
        f"- Completed games excluded: {summary['completed_games_excluded']}",
        f"- Eligible unresolved games: {summary['games_requested']}",
        '',
        '### Games',
        f"- Completed in shadow: {summary['games_completed']}",
        f"- Failed: {summary['games_failed']}",
        '- Budget stop: no',
        '',
        '### Appearance rows',
        f"- Expected: {summary['rows_expected']}",
        f"- Inserted: {summary['rows_inserted']}",
        f"- Updated: {summary['rows_updated']}",
        f"- Unchanged: {summary['rows_unchanged']}",
        f"- Blocked: {summary['rows_blocked']}",
        '',
        '### Mutations by target',
        '- GameLog: 0',
        '- Pitcher identity: 0',
        '- Appearance team: 0',
        '- Total complete-plan mutations: 0',
        '',
        '### Pitcher identity detail',
        '- Reactivations: 0',
        '- Metadata updates: 0',
        '- Minimal identity creations: 0',
        '- Blocked identity entries: 0',
        '- Suppressed historical current-state differences: '
        f"{summary['suppressed_historical_differences']}",
        '',
        '### Canonical innings',
        '- Decimal-only differences safely ignored: '
        f"{summary['ignored_decimal_differences']}",
        '- Canonical outs corrections: 0',
        '- innings_pitched semantic corrections: 0',
        '',
        '### Complete authorization',
        '- Parity contract version: 4',
        f"- Complete fingerprint: `{summary['complete_reconciliation_fingerprint']}`",
        f"- Scope-set SHA-256: `{summary['scope_set_sha256']}`",
        '- Write approved: no',
        '- R6 status: blocked pending founder review',
        '',
        '### Data integrity',
        '- Database drift: none',
        '- Work items created: 0',
        '- Checkpoints completed: 0',
        '- Dead letters created: 0',
        '',
        '### Result',
        '- The entire remaining 99-game window projects no mutations to any '
        'database target.',
        '- No database writes were performed.',
        '- Production completeness remains 10 completed / 99 unresolved.',
        '- Review the R5 authorization package before implementing R6.',
        '- GAME_DRIVEN_INGESTION_MODE remains off.',
        '- Authoritative mode remains unapproved.',
        '',
    ])


def failed_markdown(summary) -> str:
    lines = [
        '## FOUNDATION 3C R5 — FAILED',
        '',
        f"- Failed invariant: `{summary['failed_invariant']}`",
        f"- Expected: `{summary['expected']}`",
        f"- Observed: `{summary['observed']}`",
    ]
    if summary.get('game_pk') is not None:
        lines.append(f"- Affected game: `{summary['game_pk']}`")
    if summary.get('pitcher_mlb_id') is not None:
        lines.append(f"- Affected pitcher MLB id: `{summary['pitcher_mlb_id']}`")
    lines += [
        '- Expected final games: 109',
        '- Completed final games: 10',
        '- Unresolved final games: 99',
        f"- Games requested: {summary['games_requested']}",
        f"- Rows expected: {summary['rows_expected']}",
        '- No database writes were performed.',
        f"- Artifact: `{summary['artifact']}`",
        '',
        '**R6 is blocked pending founder review.** '
        'Do not implement or execute R6 from a non-PASS package.',
        '',
    ]
    return '\n'.join(lines)


def authorization_markdown(authorization) -> str:
    """Readable from a phone: the full list, then a compact evidence table."""
    passed = authorization['result'] == RESULT_PASS
    lines = [
        f"## Foundation 3C R5 authorization — {'PASS' if passed else 'FAILED'}",
        '',
        f"- Reference date: `{authorization['reference_date']}`",
        f"- Repository SHA: `{authorization['repository_sha']}`",
        f"- Workflow run: `{authorization['workflow_run_id']}`",
        f"- Parity contract: **4**",
        '- Complete fingerprint: '
        f"`{authorization['complete_reconciliation_fingerprint']}`",
        f"- Scope-set SHA-256: `{authorization['scope_set_sha256']}`",
        f"- Appearance rows: **{authorization['total_appearance_rows']}**",
        '- Ignored decimal-only differences: '
        f"**{authorization['total_ignored_decimal_differences']}**",
        '- Suppressed historical current-state differences: '
        f"{authorization['total_suppressed_historical_differences']}",
        '- Mutations, every target: **0**',
        '- Database writes: none',
        '- Write approved: **no**',
        '- R6 status: **blocked pending founder review**',
        '',
        '### Completed games excluded from R5 (10)',
        '',
        '```',
        ' '.join(str(pk) for pk in authorization['completed_game_pks']),
        '```',
        '',
        '### R5 scope — canonical processing order (99)',
        '',
        '```',
    ]
    order = authorization['canonical_processing_order']
    for start in range(0, len(order), 10):
        lines.append(' '.join(str(pk) for pk in order[start:start + 10]))
    lines += [
        '```',
        '',
        '### Per-game evidence',
        '',
        '| # | game | date | rows | ignored | suppressed | mutations | fingerprint |',
        '|---:|---:|---|---:|---:|---:|---:|---|',
    ]
    for game in authorization['games']:
        mutations = (
            game['game_log_mutations'] + game['pitcher_identity_mutations']
            + game['appearance_team_mutations']
        )
        lines.append(
            f"| {game['canonical_index']} | {game['game_pk']} "
            f"| {game['represented_date'] or ''} | {game['appearance_rows']} "
            f"| {game['ignored_decimal_differences']} "
            f"| {game['suppressed_historical_differences']} | {mutations} "
            f"| `{(game['complete_reconciliation_fingerprint'] or '')[:12]}` |"
        )
    lines += ['', f"_{NEXT_ACTION_PASS if passed else NEXT_ACTION_FAILED}_", '']
    return '\n'.join(lines)


def r6_manifest_markdown(manifest) -> str:
    lines = [
        '## Foundation 3C R6 command manifest',
        '',
        '**This is a reviewed input package, not an executable.** It contains '
        'no runnable script and must not be turned into one without founder '
        'review.',
        '',
        f"- Reference date: `{manifest['reference_date']}`",
        f"- Games: **{manifest['game_count']}**",
        f"- Scope-set SHA-256: `{manifest['scope_set_sha256']}`",
        f"- Expected rows: **{manifest['expected_rows']}**",
        '- Expected ignored decimal differences: '
        f"**{manifest['expected_ignored_decimal_differences']}**",
        '- Parity contract: '
        f"**{manifest['versions']['parity_contract_version']}**",
        '- Required `--expected-plan-fingerprint`: '
        f"`{manifest['required_expected_plan_fingerprint']}`",
        '- Write approved: **no**',
        '- Founder review required: **yes**',
        '- R6 implemented: no',
        '- R6 executed: no',
        '',
        '### Canonical processing order (99)',
        '',
        '```',
    ]
    order = manifest['canonical_processing_order']
    for start in range(0, len(order), 10):
        lines.append(' '.join(str(pk) for pk in order[start:start + 10]))
    lines += ['```', '']
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
        description='Validate the Foundation 3C R5 remaining-window shadow.',
    )
    parser.add_argument('--before-state', required=True)
    parser.add_argument('--shadow', required=True)
    parser.add_argument('--after-state', required=True)
    parser.add_argument('--summary-json', required=True)
    parser.add_argument('--summary-markdown', required=True)
    parser.add_argument('--authorization-json', required=True)
    parser.add_argument('--authorization-markdown', required=True)
    parser.add_argument('--manifest-json', required=True)
    parser.add_argument('--manifest-markdown', required=True)
    parser.add_argument('--repository-sha', default='')
    parser.add_argument('--run-id', default='')
    args = parser.parse_args(argv)

    try:
        before = _load(args.before_state, 'before_state_artifact')
        shadow = _load(args.shadow, 'shadow_report_artifact')
        after = _load(args.after_state, 'after_state_artifact')
        decision = validate_r5(
            before_state=before, shadow=shadow, after_state=after,
        )
        decision['_before'] = before
        decision['_after'] = after

        summary = build_summary(decision)
        authorization = build_authorization(
            decision, repository_sha=args.repository_sha, run_id=args.run_id,
        )
        manifest = build_r6_manifest(decision)

        _write_json(args.summary_json, summary)
        _write_text(args.summary_markdown, pass_markdown(summary))
        _write_json(args.authorization_json, authorization)
        _write_text(args.authorization_markdown,
                    authorization_markdown(authorization))
        _write_json(args.manifest_json, manifest)
        _write_text(args.manifest_markdown, r6_manifest_markdown(manifest))
        return EXIT_OK
    except ValidationFailure as failure:
        summary = failed_summary(failure)
        _write_json(args.summary_json, summary)
        _write_text(args.summary_markdown, failed_markdown(summary))
        return EXIT_FAILED


if __name__ == '__main__':
    raise SystemExit(main())
