#!/usr/bin/env python
"""Validate a Foundation 3C Stage R3 controlled-sample shadow report.

R3 is the last read-only gate before a controlled write is even proposed. It
asks three things about one specific five-game sample:

    is it still the next unresolved sample?
    is it provably clean across EVERY database target?
    what exact plan would a later write have to match?

Two results only. There is no `review_required` here: this sample is expected
to be clean, and any projected mutation means it is not eligible for the
controlled write. PASS produces a reviewed authorization package; it does not
authorize anything. R4 stays blocked until a human approves the fingerprint.

Canonical vocabulary — versions, actions, field authority — is imported from the
merged reconciliation modules rather than restated, so this gate cannot drift
from the planner it checks.

Output carries only safe structured values: counts, game ids, pitcher MLB ids,
governed field names, fingerprints, and the named invariant that failed. No
payload, path, credential, connection string, header, or exception text.
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

from models.game_ingestion_work_item import GameIngestionWorkItem  # noqa: E402
from services import game_log_reconciliation as reconciliation  # noqa: E402
from services import pitcher_identity_reconciliation as identity  # noqa: E402


EXIT_OK = 0
EXIT_FAILED = 1

RESULT_PASS = 'pass'
RESULT_FAILED = 'failed'

REFERENCE_DATE = '2026-07-29'
EXPECTED_MODE = 'shadow'
EXPECTED_STATUS = 'complete'
EXPECTED_SCOPE_MODE = 'exclusive'
EXPECTED_GAME_STATUS = 'projected'

# ── The approved controlled sample ──────────────────────────────────────────
# The first five unresolved `newly_final` games after the five already
# completed by the first controlled write. Pinned in the reviewed order.
APPROVED_GAME_PKS = (823110, 825055, 824004, 823438, 824408)

# Reviewed R2 evidence for this exact sample.
EXPECTED_ROWS_BY_GAME = {
    823110: 6,
    825055: 8,
    824004: 9,
    823438: 10,
    824408: 10,
}
EXPECTED_IGNORED_BY_GAME = {
    823110: 2,
    825055: 4,
    824004: 2,
    823438: 6,
    824408: 4,
}
EXPECTED_TOTAL_ROWS = sum(EXPECTED_ROWS_BY_GAME.values())          # 43
EXPECTED_TOTAL_IGNORED = sum(EXPECTED_IGNORED_BY_GAME.values())   # 18

# ── Sample eligibility ──────────────────────────────────────────────────────
# The five games must still be unresolved, first-attempt, publication-critical
# work. Proving that needs care, because `candidate_reason` CANNOT carry it
# here: the planner short-circuits every explicitly requested game to
# `explicit_repair` before it classifies state at all (see
# `game_ingestion_planner._candidate_decision`, `if explicit:`). Under exclusive
# scope `newly_final` is unreachable by construction, so asserting it would fail
# every R3 run while proving nothing.
#
# The load-bearing proof is the ATTEMPT NUMBER. The planner derives it from the
# stored work item, so attempt 1 means no work item exists for the game — and no
# work item means no completed checkpoint, no prior failed attempt, and no
# correction re-check. A game already written by the first controlled write, or
# retried, or re-planned as a correction, cannot report attempt 1.
EXPECTED_CANDIDATE_REASON = GameIngestionWorkItem.REASON_EXPLICIT_REPAIR
EXPECTED_ATTEMPT_NUMBER = 1
BEST_EFFORT_CRITICALITY = GameIngestionWorkItem.CRITICALITY_BEST_EFFORT
EXPECTED_CRITICALITY = GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL

# A reason other than the exclusive-scope value means a different planner, or a
# non-exclusive run, produced this report.
FORBIDDEN_CANDIDATE_REASONS = tuple(sorted(
    reason for reason in GameIngestionWorkItem.CANDIDATE_REASONS
    if reason != EXPECTED_CANDIDATE_REASON
))

# The reviewed July 29 bootstrap state. R3 is pinned to it: a legitimately
# changed population is reported as a failure rather than reinterpreted.
EXPECTED_COMPLETENESS = {
    'expected_final_games': 109,
    'completed_final_games': 5,
    'unresolved_final_games': 104,
    'terminal_failure_games': 0,
    'publication_complete': False,
}

# ── Merged canonical constants ──────────────────────────────────────────────
EXPECTED_RECONCILIATION_PLAN_VERSION = reconciliation.RECONCILIATION_PLAN_VERSION
EXPECTED_PARITY_CONTRACT_VERSION = reconciliation.PARITY_CONTRACT_VERSION
EXPECTED_INNINGS_SEMANTICS_VERSION = reconciliation.INNINGS_SEMANTICS_VERSION
EXPECTED_COMPLETE_PLAN_VERSION = reconciliation.COMPLETE_PLAN_VERSION
EXPECTED_IDENTITY_PLAN_VERSION = identity.IDENTITY_PLAN_VERSION

# D-008: the decimal companion is derived and may never be a semantic change.
PROHIBITED_SEMANTIC_FIELDS = frozenset(reconciliation.DERIVED_COMPANION_FIELDS)

# D-009: every identity action that would write, plus the retired ones. R3
# accepts only the canonical unchanged action.
FORBIDDEN_IDENTITY_ACTIONS = frozenset(
    set(identity.MUTATING_ACTIONS)
    | set(identity.RETIRED_WRITE_ACTIONS)
    | {identity.ACTION_BLOCKED}
)

FINGERPRINT_PATTERN = re.compile(r'^[0-9a-f]{64}$')


class ValidationFailure(Exception):
    """One named invariant did not hold. R3 stops here."""

    def __init__(self, invariant, expected, observed):
        super().__init__(invariant)
        self.invariant = invariant
        self.expected = expected
        self.observed = observed


def _require(invariant, expected, observed):
    if observed != expected:
        raise ValidationFailure(invariant, expected, observed)


def _require_true(invariant, observed):
    _require(invariant, True, bool(observed))


def _require_fingerprint(invariant, value):
    if not isinstance(value, str) or not FINGERPRINT_PATTERN.match(value):
        raise ValidationFailure(
            invariant, 'a 64-character lowercase sha256 hex digest',
            'absent' if not value else 'malformed',
        )
    return value


# ── Top level ───────────────────────────────────────────────────────────────


def _validate_identity_and_versions(report):
    _require('status', EXPECTED_STATUS, report.get('status'))
    _require('mode', EXPECTED_MODE, report.get('mode'))
    _require('reference_date', REFERENCE_DATE, report.get('reference_date'))
    for field, expected in (
        ('reconciliation_plan_version', EXPECTED_RECONCILIATION_PLAN_VERSION),
        ('parity_contract_version', EXPECTED_PARITY_CONTRACT_VERSION),
        ('innings_semantics_version', EXPECTED_INNINGS_SEMANTICS_VERSION),
        ('complete_plan_version', EXPECTED_COMPLETE_PLAN_VERSION),
        ('identity_plan_version', EXPECTED_IDENTITY_PLAN_VERSION),
    ):
        _require(field, expected, report.get(field))


def _validate_scope(report):
    """Exact sets, not counts. A matching count over the wrong five games is
    exactly the mistake this gate exists to prevent."""
    approved = sorted(APPROVED_GAME_PKS)

    _require('execution_scope_mode', EXPECTED_SCOPE_MODE,
             report.get('execution_scope_mode'))
    _require('requested_game_count', 5, report.get('requested_game_count'))
    _require('planned_game_count', 5, report.get('planned_game_count'))
    _require('duplicate_requested_count', 0,
             report.get('duplicate_requested_count'))
    _require_true('execution_scope_exact_match',
                  report.get('execution_scope_exact_match'))

    requested = list(report.get('requested_game_pks') or [])
    planned = list(report.get('planned_game_pks') or [])
    _require('requested_game_pks', approved, sorted(requested))
    _require('planned_game_pks', approved, sorted(planned))
    # The canonical planner emits a sorted plan; a different order means a
    # different planner produced this report.
    _require('planned_game_pks_are_canonically_ordered', sorted(planned), planned)

    _require('unexpected_planned_game_pks', [],
             list(report.get('unexpected_planned_game_pks') or []))
    _require('missing_requested_game_pks', [],
             list(report.get('missing_requested_game_pks') or []))

    _require('games_attempted', 5, report.get('games_attempted'))
    _require('games_fetched', 5, report.get('games_fetched'))
    _require('games_completed', 5, report.get('games_completed'))
    _require('games_failed', 0, report.get('games_failed'))
    _require('games_remaining', 0, report.get('games_remaining'))

    _require('budget_stop_triggered', False,
             bool(report.get('budget_stop_triggered')))
    _require('budget_stop_is_null', None, report.get('budget_stop'))
    _require('finality_conflicts', 0, report.get('finality_conflicts'))
    _require('schedule_authority_missing', 0,
             report.get('schedule_authority_missing'))
    _require('failure_classes_is_empty', {},
             dict(report.get('failure_classes') or {}))
    _require('critical_games_unresolved', 0,
             report.get('critical_games_unresolved'))

    # Planner-level eligibility: none of the five may be a retry or a
    # correction re-check of an already-completed checkpoint.
    _require('retry_count', 0, report.get('retry_count'))
    _require('corrected_final_count', 0, report.get('corrected_final_count'))


def _validate_row_totals(report):
    _require('rows_expected', EXPECTED_TOTAL_ROWS, report.get('rows_expected'))
    _require('rows_inserted', 0, report.get('rows_inserted'))
    _require('rows_updated', 0, report.get('rows_updated'))
    _require('rows_unchanged', EXPECTED_TOTAL_ROWS, report.get('rows_unchanged'))
    _require('rows_blocked', 0, report.get('rows_blocked'))

    total = (
        int(report.get('rows_inserted') or 0)
        + int(report.get('rows_updated') or 0)
        + int(report.get('rows_unchanged') or 0)
        + int(report.get('rows_blocked') or 0)
    )
    _require('rows_expected_equals_row_actions', EXPECTED_TOTAL_ROWS, total)


def _validate_mutation_targets(report):
    """Zero on every target. A clean GameLog half is not a clean run."""
    _require('rows_inserted_and_updated_are_zero', 0,
             int(report.get('rows_inserted') or 0)
             + int(report.get('rows_updated') or 0))
    for counter in (
        'pitcher_identity_mutations',
        'pitcher_identity_creations',
        'pitcher_identity_reactivations',
        'pitcher_identity_metadata_updates',
        'pitcher_identity_blocked',
        'appearance_team_mutations',
        'complete_mutation_count',
        'statistical_corrections',
        'authority_reconciliations',
        'provenance_only_updates',
        'canonical_outs_corrections',
        'derived_companion_fields_applied',
    ):
        _require(counter, 0, report.get(counter))

    _require('pitcher_identity_changed_fields_counts', {},
             dict(report.get('pitcher_identity_changed_fields_counts') or {}))
    _require('changed_fields_counts', {},
             dict(report.get('changed_fields_counts') or {}))

    actions = dict(report.get('pitcher_identity_action_counts') or {})
    for action in sorted(actions):
        if action in FORBIDDEN_IDENTITY_ACTIONS:
            raise ValidationFailure(
                f'pitcher_identity_action_counts_excludes_{action}', 0,
                actions[action],
            )
        if action != identity.ACTION_UNCHANGED:
            raise ValidationFailure(
                'pitcher_identity_action_is_unchanged',
                identity.ACTION_UNCHANGED, action,
            )
    _require('pitcher_identity_action_counts',
             {identity.ACTION_UNCHANGED: EXPECTED_TOTAL_ROWS}, actions)


def _validate_innings(report):
    _require('derived_companion_differences_ignored', EXPECTED_TOTAL_IGNORED,
             report.get('derived_companion_differences_ignored'))
    _require('decimal_only_updates_suppressed', EXPECTED_TOTAL_IGNORED,
             report.get('decimal_only_updates_suppressed'))
    for field in sorted(PROHIBITED_SEMANTIC_FIELDS):
        if field in (report.get('changed_fields_counts') or {}):
            raise ValidationFailure(
                f'changed_fields_counts_excludes_{field}', 'absent', field,
            )


def _validate_publication_completeness(report):
    """Pinned to the reviewed bootstrap state.

    R3 is read-only, so it must not move these numbers. A legitimately changed
    governed population is reported as a failure rather than reinterpreted,
    because the approved sample was chosen against this exact state.
    """
    completeness = report.get('publication_completeness')
    if not isinstance(completeness, dict):
        raise ValidationFailure(
            'publication_completeness_is_an_object', 'object',
            type(completeness).__name__,
        )
    for field, expected in EXPECTED_COMPLETENESS.items():
        observed = completeness.get(field)
        if field == 'publication_complete':
            observed = bool(observed)
        _require(f'completeness_{field}', expected, observed)
    _require('completeness_finality_conflicts', 0,
             completeness.get('finality_conflicts'))
    _require('completeness_schedule_authority_missing', 0,
             completeness.get('schedule_authority_missing'))
    return {
        field: completeness.get(field)
        for field in (
            'expected_final_games', 'completed_final_games',
            'unresolved_final_games', 'terminal_failure_games',
            'correction_pending_games', 'publication_complete',
            'decision_reasons',
        )
    }


# ── Rows ────────────────────────────────────────────────────────────────────


def _validate_row(row, *, game_pk):
    pitcher = row.get('pitcher_mlb_id')
    label = f'{game_pk}_{pitcher}'
    if pitcher is None:
        raise ValidationFailure(
            f'row_{game_pk}_pitcher_mlb_id_present', 'an mlb id', None,
        )
    _require(f'row_{label}_game_pk_matches_game', game_pk, row.get('game_pk'))

    # ── GameLog ─────────────────────────────────────────────────────────────
    _require(f'row_{label}_action', reconciliation.ACTION_UNCHANGED,
             row.get('action'))
    _require(f'row_{label}_changed_field_count', 0,
             row.get('changed_field_count'))
    _require(f'row_{label}_changed_fields', [],
             list(row.get('changed_fields') or []))
    _require(f'row_{label}_semantic_changed_fields', [],
             list(row.get('semantic_changed_fields') or []))
    _require(f'row_{label}_applied_changed_fields', [],
             list(row.get('applied_changed_fields') or []))
    _require(f'row_{label}_derived_companion_fields', [],
             list(row.get('derived_companion_fields') or []))
    _require_true(f'row_{label}_governed_and_safe', row.get('governed_and_safe'))
    _require(f'row_{label}_blocked_reason', None, row.get('blocked_reason'))
    _require(f'row_{label}_affects_published_evidence', False,
             bool(row.get('affects_published_evidence')))
    _require(f'row_{label}_is_statistical_correction', False,
             bool(row.get('is_statistical_correction')))

    # ── Appearance-team authority ───────────────────────────────────────────
    _require(f'row_{label}_appearance_team_reason', None,
             row.get('appearance_team_reason'))

    # ── Pitcher identity (D-009) ────────────────────────────────────────────
    action = row.get('pitcher_identity_action')
    if action is None:
        raise ValidationFailure(
            f'row_{label}_reports_a_pitcher_identity_action',
            'an identity action', None,
        )
    if action in FORBIDDEN_IDENTITY_ACTIONS:
        raise ValidationFailure(
            f'row_{label}_pitcher_identity_action', identity.ACTION_UNCHANGED,
            action,
        )
    _require(f'row_{label}_pitcher_identity_action',
             identity.ACTION_UNCHANGED, action)
    _require(f'row_{label}_identity_changed_fields', [],
             list(row.get('pitcher_identity_changed_fields') or []))
    _require(f'row_{label}_identity_applied_fields', [],
             list(row.get('pitcher_identity_applied_fields') or []))
    _require(f'row_{label}_identity_mutation_digest', '',
             row.get('pitcher_identity_mutation_digest') or '')
    _require_true(f'row_{label}_identity_governed_and_safe',
                  row.get('pitcher_identity_governed_and_safe', True))
    _require(f'row_{label}_identity_blocked_reason', None,
             row.get('pitcher_identity_blocked_reason'))
    _require(f'row_{label}_identity_requires_creation', False,
             bool(row.get('pitcher_identity_requires_creation')))

    # Suppressed historical differences are expected D-009 evidence, not
    # mutations. When any exist the row must SAY it refused them.
    suppressed = list(row.get('pitcher_identity_suppressed_fields') or [])
    for field in suppressed:
        if field not in identity.KNOWN_IDENTITY_FIELDS:
            raise ValidationFailure(
                f'row_{label}_suppressed_field_{field}_is_known',
                'a known identity field', field,
            )
    if suppressed:
        _require_true(
            f'row_{label}_current_authority_mutation_refused',
            row.get('pitcher_identity_current_authority_mutation_refused'),
        )

    ignored = list(row.get('derived_companion_differences_ignored') or [])
    for field in ignored:
        if field not in PROHIBITED_SEMANTIC_FIELDS:
            raise ValidationFailure(
                f'row_{label}_ignored_difference_is_a_known_companion',
                'a known companion', field,
            )

    return {
        'ignored': len(ignored),
        'suppressed': len(suppressed),
        'suppressed_fields': sorted(suppressed),
    }


# ── Games ───────────────────────────────────────────────────────────────────


def _validate_games(report):
    games = list(report.get('games') or [])
    _require('per_game_result_count', 5, len(games))
    _require('per_game_ids', sorted(APPROVED_GAME_PKS),
             sorted(game.get('game_pk') for game in games))

    entries = []
    row_total = 0
    ignored_total = 0
    suppressed_rows = 0
    suppressed_field_counts: dict[str, int] = {}

    for game in games:
        game_pk = game.get('game_pk')
        _require(f'game_{game_pk}_status', EXPECTED_GAME_STATUS,
                 game.get('status'))
        _require(f'game_{game_pk}_error_class', None, game.get('error_class'))
        _require(f'game_{game_pk}_inserted', 0, game.get('inserted'))
        _require(f'game_{game_pk}_updated', 0, game.get('updated'))
        _require(f'game_{game_pk}_blocked', 0, game.get('blocked'))

        # ── Eligibility: still the next unresolved sample ────────────────────
        reason = game.get('candidate_reason')
        _require(f'game_{game_pk}_candidate_reason', EXPECTED_CANDIDATE_REASON,
                 reason)
        if reason in FORBIDDEN_CANDIDATE_REASONS:
            raise ValidationFailure(
                f'game_{game_pk}_candidate_reason_is_not_{reason}',
                EXPECTED_CANDIDATE_REASON, reason,
            )
        # A first attempt is what proves no completed checkpoint preceded this
        # run: the planner derives the attempt number from the stored work item.
        _require(f'game_{game_pk}_attempt_number', EXPECTED_ATTEMPT_NUMBER,
                 game.get('attempt_number'))
        criticality = game.get('criticality')
        _require(f'game_{game_pk}_criticality', EXPECTED_CRITICALITY,
                 criticality)

        expected_rows = EXPECTED_ROWS_BY_GAME[game_pk]
        _require(f'game_{game_pk}_appearances_extracted', expected_rows,
                 game.get('appearances_extracted'))
        _require(f'game_{game_pk}_unchanged', expected_rows,
                 game.get('unchanged'))

        rows = list(game.get('rows') or [])
        _require(f'game_{game_pk}_row_count', expected_rows, len(rows))

        game_ignored = 0
        game_suppressed = 0
        seen = set()
        for row in rows:
            facts = _validate_row(row, game_pk=game_pk)
            key = row.get('pitcher_mlb_id')
            if key in seen:
                raise ValidationFailure(
                    f'game_{game_pk}_row_appears_once', 'unique pitcher ids', key,
                )
            seen.add(key)
            game_ignored += facts['ignored']
            if facts['suppressed']:
                game_suppressed += 1
                suppressed_rows += 1
            for field in facts['suppressed_fields']:
                suppressed_field_counts[field] = (
                    suppressed_field_counts.get(field, 0) + 1
                )

        _require(f'game_{game_pk}_ignored_decimal_differences',
                 EXPECTED_IGNORED_BY_GAME[game_pk], game_ignored)
        _require(f'game_{game_pk}_derived_companion_differences_ignored',
                 EXPECTED_IGNORED_BY_GAME[game_pk],
                 game.get('derived_companion_differences_ignored'))
        _require(f'game_{game_pk}_canonical_outs_corrections', 0,
                 game.get('canonical_outs_corrections'))
        _require(f'game_{game_pk}_pitcher_identity_mutations', 0,
                 game.get('pitcher_identity_mutations'))
        _require(f'game_{game_pk}_appearance_team_mutations', 0,
                 game.get('appearance_team_mutations'))
        _require(f'game_{game_pk}_complete_mutation_count', 0,
                 game.get('complete_mutation_count'))

        fingerprint = _require_fingerprint(
            f'game_{game_pk}_complete_reconciliation_fingerprint',
            game.get('complete_reconciliation_fingerprint'),
        )

        row_total += len(rows)
        ignored_total += game_ignored
        entries.append({
            'game_pk': game_pk,
            'represented_date': game.get('represented_date'),
            'candidate_reason': reason,
            'attempt_number': game.get('attempt_number'),
            'criticality': criticality,
            'appearance_rows': len(rows),
            'ignored_decimal_differences': game_ignored,
            'suppressed_historical_differences': game_suppressed,
            'game_log_mutations': 0,
            'pitcher_identity_mutations': 0,
            'appearance_team_mutations': 0,
            'blocked': 0,
            'source_revision': game.get('source_revision'),
            'complete_reconciliation_fingerprint': fingerprint,
        })

    # The rows are the authority; the aggregates must agree with them.
    _require('per_row_total', EXPECTED_TOTAL_ROWS, row_total)
    _require('per_row_ignored_total', EXPECTED_TOTAL_IGNORED, ignored_total)

    # Deterministic package ordering: the reviewed sample order, not payload
    # order.
    order = {game_pk: index for index, game_pk in enumerate(APPROVED_GAME_PKS)}
    entries.sort(key=lambda entry: order[entry['game_pk']])
    return {
        'entries': entries,
        'suppressed_rows': suppressed_rows,
        'suppressed_field_counts': dict(sorted(suppressed_field_counts.items())),
    }


def _validate_fingerprints(report, games):
    run_fingerprint = _require_fingerprint(
        'complete_reconciliation_fingerprint',
        report.get('complete_reconciliation_fingerprint'),
    )
    _require_fingerprint(
        'reconciliation_plan_fingerprint',
        report.get('reconciliation_plan_fingerprint'),
    )
    # Five distinct game plans must not collapse to one identity.
    per_game = [entry['complete_reconciliation_fingerprint'] for entry in games]
    if len(set(per_game)) != len(per_game):
        raise ValidationFailure(
            'per_game_fingerprints_are_distinct', len(per_game),
            len(set(per_game)),
        )
    return run_fingerprint


# ── Validation entry point ──────────────────────────────────────────────────


def validate(report) -> dict:
    """Assert every R3 invariant. Raises on the first break; never softens."""
    if not isinstance(report, dict):
        raise ValidationFailure('report_is_an_object', 'object',
                                type(report).__name__)

    _validate_identity_and_versions(report)
    _validate_scope(report)
    _validate_row_totals(report)
    _validate_mutation_targets(report)
    _validate_innings(report)
    completeness = _validate_publication_completeness(report)
    games = _validate_games(report)
    fingerprint = _validate_fingerprints(report, games['entries'])

    summary = {
        'result': RESULT_PASS,
        'reference_date': REFERENCE_DATE,
        'execution_scope_mode': report.get('execution_scope_mode'),
        'requested_game_pks': list(APPROVED_GAME_PKS),
        'planned_game_pks': list(APPROVED_GAME_PKS),
        'execution_scope_exact_match': True,
        'eligible_unresolved_sample': True,
        'games_planned': 5,
        'games_completed': report.get('games_completed'),
        'games_failed': report.get('games_failed'),
        'rows_by_game': {
            str(entry['game_pk']): entry['appearance_rows']
            for entry in games['entries']
        },
        'rows_expected': EXPECTED_TOTAL_ROWS,
        'rows_inserted': 0,
        'rows_updated': 0,
        'rows_unchanged': EXPECTED_TOTAL_ROWS,
        'rows_blocked': 0,
        'game_log_mutations': 0,
        'pitcher_identity_mutations': 0,
        'appearance_team_mutations': 0,
        'complete_mutation_count': 0,
        'pitcher_identity_creations': 0,
        'pitcher_identity_reactivations': 0,
        'pitcher_identity_metadata_updates': 0,
        'pitcher_identity_blocked': 0,
        'derived_companion_differences_ignored': EXPECTED_TOTAL_IGNORED,
        'canonical_outs_corrections': 0,
        'statistical_corrections': 0,
        'innings_pitched_semantic_corrections': 0,
        'historical_current_state_changes_suppressed': games['suppressed_rows'],
        'suppressed_current_state_field_counts': games['suppressed_field_counts'],
        'complete_reconciliation_fingerprint': fingerprint,
        'reconciliation_plan_version': report.get('reconciliation_plan_version'),
        'parity_contract_version': report.get('parity_contract_version'),
        'innings_semantics_version': report.get('innings_semantics_version'),
        'complete_plan_version': report.get('complete_plan_version'),
        'identity_plan_version': report.get('identity_plan_version'),
        'publication_completeness': completeness,
        'database_writes': 'none',
        'write_approved': False,
        'r4_status': 'blocked_pending_founder_review',
        'failed_invariant': None,
        'next_action': (
            'Review the R3 authorization package. Do not run or build R4 until '
            'the complete reconciliation fingerprint is founder-approved.'
        ),
    }
    return {'summary': summary, 'games': games['entries']}


def build_authorization(summary, entries, *, repository_sha, run_id) -> dict:
    """The deterministic package a later R4 write would be reviewed against."""
    return {
        'result': summary['result'],
        'reference_date': REFERENCE_DATE,
        'repository_sha': repository_sha,
        'workflow_run_id': run_id,
        'requested_game_pks': list(APPROVED_GAME_PKS),
        'planned_game_pks': list(APPROVED_GAME_PKS),
        'execution_scope_exact_match': True,
        'eligible_unresolved_sample': True,
        'games': entries,
        'total_appearance_rows': summary['rows_expected'],
        'total_ignored_decimal_differences': summary[
            'derived_companion_differences_ignored'
        ],
        'historical_current_state_changes_suppressed': summary[
            'historical_current_state_changes_suppressed'
        ],
        'suppressed_current_state_field_counts': summary[
            'suppressed_current_state_field_counts'
        ],
        'mutations_by_target': {
            'game_log': 0,
            'pitcher_identity': 0,
            'appearance_team': 0,
        },
        'complete_mutation_count': 0,
        'complete_reconciliation_fingerprint': summary[
            'complete_reconciliation_fingerprint'
        ],
        'reconciliation_plan_version': summary['reconciliation_plan_version'],
        'parity_contract_version': summary['parity_contract_version'],
        'innings_semantics_version': summary['innings_semantics_version'],
        'complete_plan_version': summary['complete_plan_version'],
        'identity_plan_version': summary['identity_plan_version'],
        'publication_completeness': summary['publication_completeness'],
        'database_writes': 'none',
        # Structurally constant. This package is evidence for a review, never
        # an approval, so there is no code path that can set it true.
        'write_approved': False,
        'r4_status': 'blocked_pending_founder_review',
    }


# ── Summaries ───────────────────────────────────────────────────────────────


def authorization_markdown(package) -> str:
    lines = [
        '# Foundation 3C R3 — reviewed authorization package',
        '',
        f"- Result: **{package['result'].upper()}**",
        f"- Reference date: {package['reference_date']}",
        f"- Games: {', '.join(str(pk) for pk in package['planned_game_pks'])}",
        f"- Appearance rows: {package['total_appearance_rows']}",
        '- Decimal-only differences ignored: '
        f"{package['total_ignored_decimal_differences']}",
        '- Suppressed historical current-state differences: '
        f"{package['historical_current_state_changes_suppressed']}",
        '',
        '## Mutations by target',
        f"- GameLog: {package['mutations_by_target']['game_log']}",
        f"- Pitcher identity: {package['mutations_by_target']['pitcher_identity']}",
        f"- Appearance team: {package['mutations_by_target']['appearance_team']}",
        f"- Total: {package['complete_mutation_count']}",
        '',
        '## Per game',
        '',
        '| Game | Date | Reason | Attempt | Rows | Ignored | Fingerprint |',
        '| --- | --- | --- | --- | --- | --- | --- |',
    ]
    for entry in package['games']:
        lines.append(
            f"| {entry['game_pk']} | {entry['represented_date']} "
            f"| {entry['candidate_reason']} | {entry['attempt_number']} "
            f"| {entry['appearance_rows']} "
            f"| {entry['ignored_decimal_differences']} "
            f"| `{entry['complete_reconciliation_fingerprint'][:16]}…` |"
        )
    lines += [
        '',
        '## Reviewed fingerprint',
        '',
        f"`{package['complete_reconciliation_fingerprint']}`",
        '',
        '- Database writes: none',
        '- Write approved: **no**',
        '- R4 status: **blocked pending founder review**',
        '',
    ]
    return '\n'.join(lines)


def pass_markdown(summary) -> str:
    rows = summary['rows_by_game']
    lines = [
        '## FOUNDATION 3C R3 — PASS',
        '',
        '### Controlled sample',
        f"- Reference date: {summary['reference_date']}",
        '- Requested: 5',
        '- Planned: 5',
        '- Exact scope: yes',
        '- Eligible unresolved sample: yes',
        '',
        '### Games',
    ]
    for game_pk in APPROVED_GAME_PKS:
        lines.append(f"- {game_pk}: {rows[str(game_pk)]} rows")
    lines += [
        f"- Completed: {summary['games_completed']}",
        f"- Failed: {summary['games_failed']}",
        '',
        '### Appearance rows',
        f"- Expected: {summary['rows_expected']}",
        f"- Inserted: {summary['rows_inserted']}",
        f"- Updated: {summary['rows_updated']}",
        f"- Unchanged: {summary['rows_unchanged']}",
        f"- Blocked: {summary['rows_blocked']}",
        '',
        '### Mutations by target',
        f"- GameLog: {summary['game_log_mutations']}",
        f"- Pitcher identity: {summary['pitcher_identity_mutations']}",
        f"- Appearance team: {summary['appearance_team_mutations']}",
        f"- Total complete-plan mutations: {summary['complete_mutation_count']}",
        '',
        '### Pitcher identity detail',
        f"- Reactivations: {summary['pitcher_identity_reactivations']}",
        f"- Metadata updates: {summary['pitcher_identity_metadata_updates']}",
        f"- Minimal identity creations: {summary['pitcher_identity_creations']}",
        f"- Blocked identity entries: {summary['pitcher_identity_blocked']}",
        '- Suppressed historical current-state differences: '
        f"{summary['historical_current_state_changes_suppressed']}",
        '',
        '### Canonical innings',
        '- Decimal-only differences safely ignored: '
        f"{summary['derived_companion_differences_ignored']}",
        f"- Canonical outs corrections: {summary['canonical_outs_corrections']}",
        '- `innings_pitched` semantic corrections: '
        f"{summary['innings_pitched_semantic_corrections']}",
        '',
        '### Reviewed authorization',
        f"- Complete fingerprint: `{summary['complete_reconciliation_fingerprint']}`",
        '- Write approved: no',
        '- R4 status: blocked pending founder review',
        '',
        '### Result',
        '- The controlled sample projects no mutations to any database target.',
        '- No database writes were performed.',
        '- Review the authorization package before creating R4.',
        '',
    ]
    return '\n'.join(lines)


def failed_markdown(summary) -> str:
    lines = [
        '## FOUNDATION 3C R3 — FAILED',
        '',
        f"- Failed invariant: `{summary.get('failed_invariant')}`",
        f"- Expected: `{summary.get('expected')}`",
        f"- Observed: `{summary.get('observed')}`",
        '',
        '### Observed totals',
        f"- Games completed: {summary.get('games_completed')}",
        f"- Games failed: {summary.get('games_failed')}",
        f"- Rows expected: {summary.get('rows_expected')}",
        f"- Rows unchanged: {summary.get('rows_unchanged')}",
        f"- Rows updated: {summary.get('rows_updated')}",
        f"- Rows inserted: {summary.get('rows_inserted')}",
        f"- Rows blocked: {summary.get('rows_blocked')}",
        '',
        f"- Artifact: `{summary.get('artifact')}`",
        '',
        'This is a rollout stop. R4 is blocked and must not be created.',
        '',
    ]
    return '\n'.join(lines)


def _failure_summary(report, failure, artifact) -> dict:
    report = report if isinstance(report, dict) else {}
    return {
        'result': RESULT_FAILED,
        'reference_date': REFERENCE_DATE,
        'failed_invariant': failure.invariant,
        'expected': failure.expected,
        'observed': failure.observed,
        'games_completed': report.get('games_completed'),
        'games_failed': report.get('games_failed'),
        'rows_expected': report.get('rows_expected'),
        'rows_inserted': report.get('rows_inserted'),
        'rows_updated': report.get('rows_updated'),
        'rows_unchanged': report.get('rows_unchanged'),
        'rows_blocked': report.get('rows_blocked'),
        'complete_mutation_count': report.get('complete_mutation_count'),
        'database_writes': 'none',
        'write_approved': False,
        'r4_status': 'blocked_pending_founder_review',
        'artifact': artifact,
        'next_action': 'Stop Foundation 3C rollout. Do not create or run R4.',
    }


def _empty_authorization(repository_sha, run_id) -> dict:
    """A failed run still writes the package, so a reviewer never wonders
    whether it was withheld."""
    return {
        'result': RESULT_FAILED,
        'reference_date': REFERENCE_DATE,
        'repository_sha': repository_sha,
        'workflow_run_id': run_id,
        'requested_game_pks': list(APPROVED_GAME_PKS),
        'planned_game_pks': [],
        'execution_scope_exact_match': False,
        'eligible_unresolved_sample': False,
        'games': [],
        'total_appearance_rows': 0,
        'total_ignored_decimal_differences': 0,
        'historical_current_state_changes_suppressed': 0,
        'suppressed_current_state_field_counts': {},
        'mutations_by_target': {
            'game_log': 0, 'pitcher_identity': 0, 'appearance_team': 0,
        },
        'complete_mutation_count': 0,
        'complete_reconciliation_fingerprint': None,
        'database_writes': 'none',
        'write_approved': False,
        'r4_status': 'blocked_pending_founder_review',
    }


# ── CLI ─────────────────────────────────────────────────────────────────────


def _write_text(path, text):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding='utf-8')


def _write_json(path, payload):
    _write_text(
        path, json.dumps(payload, indent=2, sort_keys=True, default=str) + '\n',
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='Validate a Foundation 3C R3 controlled-sample shadow report.',
    )
    parser.add_argument('--report', required=True)
    parser.add_argument('--summary-json', required=True)
    parser.add_argument('--summary-markdown', required=True)
    parser.add_argument('--authorization-json', required=True)
    parser.add_argument('--authorization-markdown', required=True)
    parser.add_argument('--repository-sha', default=None)
    parser.add_argument('--run-id', default=None)
    args = parser.parse_args(argv)

    artifact = Path(args.report).name
    report_path = Path(args.report)
    report = {}
    package = None

    if not report_path.exists():
        summary = _failure_summary(
            {}, ValidationFailure('report_file_exists', 'present', 'missing'),
            artifact,
        )
    else:
        try:
            report = json.loads(report_path.read_text(encoding='utf-8'))
        except Exception:  # noqa: BLE001 - the parse failure itself is the signal
            summary = _failure_summary(
                {}, ValidationFailure('report_is_valid_json', 'json', 'unparsable'),
                artifact,
            )
        else:
            try:
                validated = validate(report)
                summary = validated['summary']
                summary['artifact'] = artifact
                summary['repository_sha'] = args.repository_sha
                summary['workflow_run_id'] = args.run_id
                package = build_authorization(
                    summary, validated['games'],
                    repository_sha=args.repository_sha, run_id=args.run_id,
                )
            except ValidationFailure as failure:
                summary = _failure_summary(report, failure, artifact)

    summary.setdefault('repository_sha', args.repository_sha)
    summary.setdefault('workflow_run_id', args.run_id)
    if package is None:
        package = _empty_authorization(args.repository_sha, args.run_id)

    if summary['result'] == RESULT_PASS:
        markdown = pass_markdown(summary)
        exit_code = EXIT_OK
    else:
        markdown = failed_markdown(summary)
        exit_code = EXIT_FAILED

    _write_json(args.summary_json, summary)
    _write_text(args.summary_markdown, markdown)
    _write_json(args.authorization_json, package)
    _write_text(args.authorization_markdown, authorization_markdown(package))
    print(markdown)
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
