#!/usr/bin/env python
"""Foundation 3C R4 — the controlled-write authorization and closeout gate.

R4 is the first stage that writes. This module owns the whole decision, in two
phases:

    preflight  — may the write run at all?
    closeout   — did it change exactly what it was allowed to change?

`preflight` is the gate the workflow puts between the shadow and the write. It
must pass before the write step is reachable. `closeout` compares the before and
after snapshots, the write report, and the immediate replay, and produces the
deterministic record of what actually happened.

Two results only: pass or failed. There is no partial credit and no automatic
retry. In particular the canonical writer commits PER GAME, so partial
completion is genuinely reachable — and it is a FAILED result that stops the
rollout, never something to paper over.

Authorization rests on one hard-coded contract-4 fingerprint. The contract-3
value R3 originally produced is stale after the identity-coverage repair and is
recorded here only so it can be explicitly refused.

Output carries only safe structured values: counts, game ids, statuses, hashes,
fingerprints, and the named invariant that failed. No payload, path, credential,
connection string, header, or exception text.
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

from services import game_log_reconciliation as reconciliation  # noqa: E402
from services import pitcher_identity_reconciliation as identity  # noqa: E402


EXIT_OK = 0
EXIT_FAILED = 1

RESULT_PASS = 'pass'
RESULT_FAILED = 'failed'

REFERENCE_DATE = '2026-07-29'
APPROVED_GAME_PKS = (823110, 825055, 824004, 823438, 824408)

EXPECTED_ROWS_BY_GAME = {823110: 6, 825055: 8, 824004: 9, 823438: 10, 824408: 10}
EXPECTED_IGNORED_BY_GAME = {823110: 2, 825055: 4, 824004: 2, 823438: 6, 824408: 4}
EXPECTED_TOTAL_ROWS = sum(EXPECTED_ROWS_BY_GAME.values())         # 43
EXPECTED_TOTAL_IGNORED = sum(EXPECTED_IGNORED_BY_GAME.values())   # 18

# ── Authorization ───────────────────────────────────────────────────────────
# The founder-approved fingerprint, produced by R3 under parity contract 4.
APPROVED_FINGERPRINT = (
    '08bf16bc730ffe4c5c024c8e1dbc000d017a1a4956878f49a988fb22a1e4adda'
)
# Produced by R3 under contract 3, before the identity half of the fingerprint
# was repaired. Present ONLY so it can be named and refused; it must never
# authorize anything.
STALE_CONTRACT_3_FINGERPRINT = (
    '2a06f7e5b1aad853c6280ae3488a88f39ba0402cfb0b8044f0ba75d7be20c239'
)

EXPECTED_PARITY_CONTRACT_VERSION = '4'

# ── Pre-write and post-write bootstrap population ───────────────────────────
BEFORE_COMPLETENESS = {
    'expected_final_games': 109,
    'completed_final_games': 5,
    'unresolved_final_games': 104,
    'terminal_failure_games': 0,
    'publication_complete': False,
}
AFTER_COMPLETENESS = {
    'expected_final_games': 109,
    'completed_final_games': 10,
    'unresolved_final_games': 99,
    'terminal_failure_games': 0,
    'publication_complete': False,
}

PROHIBITED_SEMANTIC_FIELDS = frozenset(reconciliation.DERIVED_COMPANION_FIELDS)
FORBIDDEN_IDENTITY_ACTIONS = frozenset(
    set(identity.MUTATING_ACTIONS)
    | set(identity.RETIRED_WRITE_ACTIONS)
    | {identity.ACTION_BLOCKED}
)

FINGERPRINT_PATTERN = re.compile(r'^[0-9a-f]{64}$')

# Baseball-data families that must be byte-identical across the write.
IMMUTABLE_STATE_HASHES = (
    'game_log_content_hash',
    'correction_provenance_hash',
    'appearance_team_hash',
    'pitcher_state_hash',
)


class ValidationFailure(Exception):
    """One named invariant did not hold. R4 stops here."""

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


def _load(path, invariant):
    target = Path(path) if path else None
    if target is None or not target.exists():
        raise ValidationFailure(invariant, 'present', 'missing')
    try:
        return json.loads(target.read_text(encoding='utf-8'))
    except Exception:  # noqa: BLE001 - the parse failure itself is the signal
        raise ValidationFailure(invariant, 'json', 'unparsable')


# ── Shadow report shape (shared by preflight and replay) ────────────────────


def _validate_shadow_report(report, *, phase, require_attempt_one):
    """Everything a five-game exclusive shadow must satisfy.

    Used for BOTH the preflight and the post-write replay. The replay
    deliberately does not require attempt 1 or a particular candidate reason:
    the write leaves completed work items behind, so a later attempt number is
    the correct, expected consequence of the write having happened.
    """
    if not isinstance(report, dict):
        raise ValidationFailure(f'{phase}_is_an_object', 'object',
                                type(report).__name__)

    approved = sorted(APPROVED_GAME_PKS)

    _require(f'{phase}_status', 'complete', report.get('status'))
    _require(f'{phase}_mode', 'shadow', report.get('mode'))
    _require(f'{phase}_reference_date', REFERENCE_DATE,
             report.get('reference_date'))
    _require(f'{phase}_execution_scope_mode', 'exclusive',
             report.get('execution_scope_mode'))
    _require(f'{phase}_requested_game_count', 5,
             report.get('requested_game_count'))
    _require(f'{phase}_planned_game_count', 5, report.get('planned_game_count'))
    _require(f'{phase}_duplicate_requested_count', 0,
             report.get('duplicate_requested_count'))
    _require_true(f'{phase}_execution_scope_exact_match',
                  report.get('execution_scope_exact_match'))
    _require(f'{phase}_requested_game_pks', approved,
             sorted(report.get('requested_game_pks') or []))
    _require(f'{phase}_planned_game_pks', approved,
             sorted(report.get('planned_game_pks') or []))
    _require(f'{phase}_unexpected_planned_game_pks', [],
             list(report.get('unexpected_planned_game_pks') or []))
    _require(f'{phase}_missing_requested_game_pks', [],
             list(report.get('missing_requested_game_pks') or []))

    for field in ('games_attempted', 'games_fetched', 'games_completed'):
        _require(f'{phase}_{field}', 5, report.get(field))
    _require(f'{phase}_games_failed', 0, report.get('games_failed'))
    _require(f'{phase}_games_remaining', 0, report.get('games_remaining'))
    _require(f'{phase}_budget_stop_triggered', False,
             bool(report.get('budget_stop_triggered')))
    _require(f'{phase}_budget_stop_is_null', None, report.get('budget_stop'))
    _require(f'{phase}_finality_conflicts', 0, report.get('finality_conflicts'))
    _require(f'{phase}_schedule_authority_missing', 0,
             report.get('schedule_authority_missing'))
    _require(f'{phase}_failure_classes_is_empty', {},
             dict(report.get('failure_classes') or {}))

    # ── Versions ────────────────────────────────────────────────────────────
    for field, expected in (
        ('reconciliation_plan_version',
         reconciliation.RECONCILIATION_PLAN_VERSION),
        ('parity_contract_version', reconciliation.PARITY_CONTRACT_VERSION),
        ('innings_semantics_version', reconciliation.INNINGS_SEMANTICS_VERSION),
        ('complete_plan_version', reconciliation.COMPLETE_PLAN_VERSION),
        ('identity_plan_version', identity.IDENTITY_PLAN_VERSION),
    ):
        _require(f'{phase}_{field}', expected, report.get(field))
    _require(f'{phase}_parity_contract_is_4', EXPECTED_PARITY_CONTRACT_VERSION,
             report.get('parity_contract_version'))

    # ── Rows ────────────────────────────────────────────────────────────────
    _require(f'{phase}_rows_expected', EXPECTED_TOTAL_ROWS,
             report.get('rows_expected'))
    _require(f'{phase}_rows_inserted', 0, report.get('rows_inserted'))
    _require(f'{phase}_rows_updated', 0, report.get('rows_updated'))
    _require(f'{phase}_rows_unchanged', EXPECTED_TOTAL_ROWS,
             report.get('rows_unchanged'))
    _require(f'{phase}_rows_blocked', 0, report.get('rows_blocked'))

    # ── Mutations, every target ─────────────────────────────────────────────
    for counter in (
        'pitcher_identity_mutations', 'pitcher_identity_creations',
        'pitcher_identity_reactivations', 'pitcher_identity_metadata_updates',
        'pitcher_identity_blocked', 'appearance_team_mutations',
        'complete_mutation_count', 'canonical_outs_corrections',
        'statistical_corrections', 'derived_companion_fields_applied',
    ):
        _require(f'{phase}_{counter}', 0, report.get(counter))
    _require(f'{phase}_changed_fields_counts', {},
             dict(report.get('changed_fields_counts') or {}))
    _require(f'{phase}_pitcher_identity_changed_fields_counts', {},
             dict(report.get('pitcher_identity_changed_fields_counts') or {}))

    # ── Innings ─────────────────────────────────────────────────────────────
    _require(f'{phase}_derived_companion_differences_ignored',
             EXPECTED_TOTAL_IGNORED,
             report.get('derived_companion_differences_ignored'))
    _require(f'{phase}_decimal_only_updates_suppressed', EXPECTED_TOTAL_IGNORED,
             report.get('decimal_only_updates_suppressed'))

    # ── Per game and per row ────────────────────────────────────────────────
    games = list(report.get('games') or [])
    _require(f'{phase}_per_game_count', 5, len(games))
    _require(f'{phase}_per_game_ids', approved,
             sorted(game.get('game_pk') for game in games))

    row_total = 0
    suppressed_rows = 0
    for game in games:
        game_pk = game.get('game_pk')
        _require(f'{phase}_game_{game_pk}_status', 'projected',
                 game.get('status'))
        _require(f'{phase}_game_{game_pk}_error_class', None,
                 game.get('error_class'))
        _require(f'{phase}_game_{game_pk}_inserted', 0, game.get('inserted'))
        _require(f'{phase}_game_{game_pk}_updated', 0, game.get('updated'))
        _require(f'{phase}_game_{game_pk}_blocked', 0, game.get('blocked'))
        _require(f'{phase}_game_{game_pk}_appearances',
                 EXPECTED_ROWS_BY_GAME[game_pk],
                 game.get('appearances_extracted'))
        _require(f'{phase}_game_{game_pk}_ignored',
                 EXPECTED_IGNORED_BY_GAME[game_pk],
                 game.get('derived_companion_differences_ignored'))
        _require(f'{phase}_game_{game_pk}_complete_mutation_count', 0,
                 game.get('complete_mutation_count'))
        if require_attempt_one:
            # Proves no work item exists yet: no completed checkpoint, no prior
            # attempt, no correction re-check. This is what makes R4 single-use.
            _require(f'{phase}_game_{game_pk}_attempt_number', 1,
                     game.get('attempt_number'))

        rows = list(game.get('rows') or [])
        _require(f'{phase}_game_{game_pk}_row_count',
                 EXPECTED_ROWS_BY_GAME[game_pk], len(rows))
        row_total += len(rows)
        for row in rows:
            label = f"{game_pk}_{row.get('pitcher_mlb_id')}"
            _require(f'{phase}_row_{label}_action',
                     reconciliation.ACTION_UNCHANGED, row.get('action'))
            _require(f'{phase}_row_{label}_changed_fields', [],
                     list(row.get('changed_fields') or []))
            _require(f'{phase}_row_{label}_semantic_changed_fields', [],
                     list(row.get('semantic_changed_fields') or []))
            _require(f'{phase}_row_{label}_derived_companion_fields', [],
                     list(row.get('derived_companion_fields') or []))
            _require_true(f'{phase}_row_{label}_governed_and_safe',
                          row.get('governed_and_safe'))
            _require(f'{phase}_row_{label}_blocked_reason', None,
                     row.get('blocked_reason'))
            _require(f'{phase}_row_{label}_appearance_team_reason', None,
                     row.get('appearance_team_reason'))

            action = row.get('pitcher_identity_action')
            if action in FORBIDDEN_IDENTITY_ACTIONS:
                raise ValidationFailure(
                    f'{phase}_row_{label}_pitcher_identity_action',
                    identity.ACTION_UNCHANGED, action,
                )
            _require(f'{phase}_row_{label}_pitcher_identity_action',
                     identity.ACTION_UNCHANGED, action)
            _require(f'{phase}_row_{label}_identity_changed_fields', [],
                     list(row.get('pitcher_identity_changed_fields') or []))
            _require(f'{phase}_row_{label}_identity_mutation_digest', '',
                     row.get('pitcher_identity_mutation_digest') or '')
            _require(f'{phase}_row_{label}_identity_blocked_reason', None,
                     row.get('pitcher_identity_blocked_reason'))
            if row.get('pitcher_identity_suppressed_fields'):
                suppressed_rows += 1

    _require(f'{phase}_per_row_total', EXPECTED_TOTAL_ROWS, row_total)

    fingerprint = _require_fingerprint(
        f'{phase}_complete_reconciliation_fingerprint',
        report.get('complete_reconciliation_fingerprint'),
    )
    return {'fingerprint': fingerprint, 'suppressed_rows': suppressed_rows}


# ── Preflight ───────────────────────────────────────────────────────────────


def validate_preflight(before_state, preflight) -> dict:
    """May the write run? Everything here happens before any mutation."""
    if not isinstance(before_state, dict):
        raise ValidationFailure('before_state_is_an_object', 'object',
                                type(before_state).__name__)
    _require('before_state_phase', 'before', before_state.get('phase'))
    _require_true('before_state_read_only',
                  (before_state.get('read_only') or {}).get(
                      'write_probe_refused'))

    # ── Single use: nothing may already exist for the selected five ─────────
    work_items = dict(before_state.get('selected_work_items') or {})
    if work_items:
        raise ValidationFailure(
            'before_state_no_selected_work_item_exists', {},
            sorted(work_items),
        )
    _require('before_state_selected_completed_count', 0,
             before_state.get('selected_completed_count'))
    _require('before_state_game_log_row_count', EXPECTED_TOTAL_ROWS,
             before_state.get('game_log_row_count'))

    completeness = dict(before_state.get('publication_completeness') or {})
    for field, expected in BEFORE_COMPLETENESS.items():
        observed = completeness.get(field)
        if field == 'publication_complete':
            observed = bool(observed)
        _require(f'before_state_completeness_{field}', expected, observed)

    facts = _validate_shadow_report(
        preflight, phase='preflight', require_attempt_one=True,
    )

    # ── The authorization itself ────────────────────────────────────────────
    if facts['fingerprint'] == STALE_CONTRACT_3_FINGERPRINT:
        raise ValidationFailure(
            'preflight_fingerprint_is_not_the_stale_contract_3_value',
            APPROVED_FINGERPRINT, 'stale_contract_3_fingerprint',
        )
    _require('preflight_complete_reconciliation_fingerprint',
             APPROVED_FINGERPRINT, facts['fingerprint'])

    return {
        'result': RESULT_PASS,
        'authorized': True,
        'approved_fingerprint': APPROVED_FINGERPRINT,
        'observed_fingerprint': facts['fingerprint'],
        'stale_contract_3_fingerprint_rejected': True,
        'parity_contract_version': preflight.get('parity_contract_version'),
        'suppressed_historical_differences': facts['suppressed_rows'],
    }


# ── Write report ────────────────────────────────────────────────────────────


def validate_write(write, *, write_exit) -> dict:
    """Did the write apply exactly the authorized plan, and prove it?"""
    _require('write_command_exit_code', 0, int(write_exit))

    if not isinstance(write, dict):
        raise ValidationFailure('write_is_an_object', 'object',
                                type(write).__name__)
    _require('write_status', 'complete', write.get('status'))
    _require('write_mode', 'write', write.get('mode'))
    _require('write_reference_date', REFERENCE_DATE,
             write.get('reference_date'))
    _require('write_execution_scope_mode', 'exclusive',
             write.get('execution_scope_mode'))
    _require('write_planned_game_pks', sorted(APPROVED_GAME_PKS),
             sorted(write.get('planned_game_pks') or []))
    _require_true('write_execution_scope_exact_match',
                  write.get('execution_scope_exact_match'))

    # ── Authorization proof, read from the report rather than inferred ──────
    supplied = write.get('expected_plan_fingerprint')
    if supplied == STALE_CONTRACT_3_FINGERPRINT:
        raise ValidationFailure(
            'write_expected_fingerprint_is_not_the_stale_contract_3_value',
            APPROVED_FINGERPRINT, 'stale_contract_3_fingerprint',
        )
    _require('write_expected_plan_fingerprint', APPROVED_FINGERPRINT, supplied)
    authorized = _require_fingerprint(
        'write_authorized_plan_fingerprint',
        write.get('authorized_plan_fingerprint'),
    )
    # The writer records the fingerprint it recomputed and matched BEFORE the
    # first mutation. Its absence means authorization was never proven, whatever
    # the exit code said.
    _require('write_authorization_matched_the_approved_plan',
             APPROVED_FINGERPRINT, authorized)
    _require('write_parity_contract_version', EXPECTED_PARITY_CONTRACT_VERSION,
             write.get('parity_contract_version'))

    # ── Baseball data must not move ─────────────────────────────────────────
    _require('write_games_attempted', 5, write.get('games_attempted'))
    _require('write_games_completed', 5, write.get('games_completed'))
    _require('write_games_failed', 0, write.get('games_failed'))
    _require('write_rows_expected', EXPECTED_TOTAL_ROWS,
             write.get('rows_expected'))
    _require('write_rows_inserted', 0, write.get('rows_inserted'))
    _require('write_rows_updated', 0, write.get('rows_updated'))
    _require('write_rows_unchanged', EXPECTED_TOTAL_ROWS,
             write.get('rows_unchanged'))
    _require('write_rows_blocked', 0, write.get('rows_blocked'))
    for counter in (
        'pitcher_identity_mutations', 'pitcher_identity_creations',
        'pitcher_identity_reactivations', 'pitcher_identity_metadata_updates',
        'pitcher_identity_blocked', 'appearance_team_mutations',
        'complete_mutation_count', 'canonical_outs_corrections',
        'statistical_corrections', 'corrections_applied',
    ):
        _require(f'write_{counter}', 0, write.get(counter))
    _require('write_changed_fields_counts', {},
             dict(write.get('changed_fields_counts') or {}))
    _require('write_failure_classes_is_empty', {},
             dict(write.get('failure_classes') or {}))

    # Per-game completion. The writer commits per game, so a partial run is
    # genuinely reachable and is caught here rather than assumed away.
    games = list(write.get('games') or [])
    _require('write_per_game_count', 5, len(games))
    completed = []
    for game in games:
        game_pk = game.get('game_pk')
        _require(f'write_game_{game_pk}_error_class', None,
                 game.get('error_class'))
        _require(f'write_game_{game_pk}_inserted', 0, game.get('inserted'))
        _require(f'write_game_{game_pk}_updated', 0, game.get('updated'))
        _require(f'write_game_{game_pk}_blocked', 0, game.get('blocked'))
        if game.get('status') != 'completed':
            raise ValidationFailure(
                f'write_game_{game_pk}_completed', 'completed',
                game.get('status'),
            )
        completed.append(game_pk)
    _require('write_completed_game_set', sorted(APPROVED_GAME_PKS),
             sorted(completed))
    return {'completed_games': sorted(completed)}


# ── State comparison ────────────────────────────────────────────────────────


def validate_state_transition(before, after) -> dict:
    """Exactly one thing may have moved: governed control state."""
    if not isinstance(after, dict):
        raise ValidationFailure('after_state_is_an_object', 'object',
                                type(after).__name__)
    _require('after_state_phase', 'after', after.get('phase'))
    _require_true('after_state_read_only',
                  (after.get('read_only') or {}).get('write_probe_refused'))

    # ── Baseball data: byte-identical ───────────────────────────────────────
    for field in IMMUTABLE_STATE_HASHES:
        _require(f'state_{field}_unchanged', before.get(field), after.get(field))
    _require('state_game_log_row_count_unchanged',
             before.get('game_log_row_count'), after.get('game_log_row_count'))
    _require('state_pitcher_count_unchanged', before.get('pitcher_count'),
             after.get('pitcher_count'))
    _require('state_pitcher_mlb_ids_unchanged',
             sorted(before.get('pitcher_mlb_ids') or []),
             sorted(after.get('pitcher_mlb_ids') or []))
    _require('state_dead_letter_count_unchanged',
             before.get('dead_letter_count'), after.get('dead_letter_count'))

    # ── Control state: exactly the five approved games completed ────────────
    work_items = dict(after.get('selected_work_items') or {})
    _require('state_selected_work_item_set',
             sorted(str(pk) for pk in APPROVED_GAME_PKS), sorted(work_items))
    for game_pk, item in sorted(work_items.items()):
        _require_true(f'state_game_{game_pk}_completed', item.get('completed'))
        _require(f'state_game_{game_pk}_error_class', None,
                 item.get('error_class'))
        _require(f'state_game_{game_pk}_rows_reconciled',
                 item.get('rows_expected'), item.get('rows_reconciled'))
    _require('state_selected_completed_count', 5,
             after.get('selected_completed_count'))

    # No game OUTSIDE the approved five may have gained or changed a work item.
    before_total = int(before.get('all_work_item_count') or 0)
    after_total = int(after.get('all_work_item_count') or 0)
    _require('state_no_unexpected_work_item_created', before_total + 5,
             after_total)

    # ── Publication completeness ────────────────────────────────────────────
    completeness = dict(after.get('publication_completeness') or {})
    for field, expected in AFTER_COMPLETENESS.items():
        observed = completeness.get(field)
        if field == 'publication_complete':
            observed = bool(observed)
        _require(f'after_state_completeness_{field}', expected, observed)

    before_completeness = dict(before.get('publication_completeness') or {})
    _require('state_completed_increased_by_five',
             int(before_completeness.get('completed_final_games') or 0) + 5,
             int(completeness.get('completed_final_games') or 0))
    _require('state_unresolved_decreased_by_five',
             int(before_completeness.get('unresolved_final_games') or 0) - 5,
             int(completeness.get('unresolved_final_games') or 0))

    return {
        'completed_before': before_completeness.get('completed_final_games'),
        'completed_after': completeness.get('completed_final_games'),
        'unresolved_before': before_completeness.get('unresolved_final_games'),
        'unresolved_after': completeness.get('unresolved_final_games'),
        'newly_completed_checkpoints': 5,
        'unexpected_games_changed': 0,
    }


# ── Closeout ────────────────────────────────────────────────────────────────


def validate_closeout(
    *, before_state, preflight, write, after_state, replay, write_exit,
) -> dict:
    """The complete R4 decision."""
    authorization = validate_preflight(before_state, preflight)
    write_facts = validate_write(write, write_exit=write_exit)
    transition = validate_state_transition(before_state, after_state)
    replay_facts = _validate_shadow_report(
        replay, phase='replay', require_attempt_one=False,
    )

    # The fingerprint deliberately covers the PLAN, not the checkpoint. Nothing
    # in `plan_fingerprint` reads work-item state, so a converged replay must
    # reproduce the approved value exactly — and that equality is a much
    # stronger convergence proof than "zero mutations" alone.
    _require('replay_fingerprint_matches_the_approved_plan',
             APPROVED_FINGERPRINT, replay_facts['fingerprint'])

    return {
        'result': RESULT_PASS,
        'authorization': authorization,
        'write': write_facts,
        'transition': transition,
        'replay_fingerprint': replay_facts['fingerprint'],
        'replay_suppressed_historical_differences':
            replay_facts['suppressed_rows'],
        'failed_invariant': None,
    }


# ── Reporting ───────────────────────────────────────────────────────────────


TRANSACTION_BOUNDARY = (
    'per_game: the canonical writer commits once per game inside '
    '_process_one_game, so five-game atomicity does not exist and is not '
    'claimed. Partial completion is detected and reported as FAILED.'
)

NEXT_ACTION_PASS = (
    'Implement R5 as one full remaining-window shadow of the remaining 99 '
    'unresolved games. Do not select another small sample.'
)
NEXT_ACTION_FAILED = (
    'Stop Foundation 3C. Do not retry R4 or begin R5 without founder review.'
)


def build_closeout(decision, *, repository_sha, run_id, before, after,
                   preflight, write, replay) -> dict:
    passed = decision['result'] == RESULT_PASS
    authorization = decision.get('authorization') or {}
    transition = decision.get('transition') or {}
    return {
        'result': decision['result'],
        'repository_sha': repository_sha,
        'workflow_run_id': run_id,
        'reference_date': REFERENCE_DATE,
        'approved_game_pks': list(APPROVED_GAME_PKS),
        'approved_fingerprint': APPROVED_FINGERPRINT,
        'stale_contract_3_fingerprint': STALE_CONTRACT_3_FINGERPRINT,
        'stale_contract_3_fingerprint_rejected': True,
        'parity_contract_version': EXPECTED_PARITY_CONTRACT_VERSION,
        'supplied_expected_fingerprint': (write or {}).get(
            'expected_plan_fingerprint'
        ),
        'preflight_observed_fingerprint': authorization.get(
            'observed_fingerprint'
        ),
        'fingerprint_authorization_result': (
            'matched_before_first_mutation' if passed else 'not_proven'
        ),
        'preflight_rows_expected': (preflight or {}).get('rows_expected'),
        'preflight_rows_unchanged': (preflight or {}).get('rows_unchanged'),
        'preflight_ignored_decimal_differences': (preflight or {}).get(
            'derived_companion_differences_ignored'
        ),
        'preflight_mutations_by_target': {
            'game_log': 0, 'pitcher_identity': 0, 'appearance_team': 0,
        },
        'write_exit_result': decision.get('write_exit'),
        'write_games_attempted': (write or {}).get('games_attempted'),
        'write_games_completed': (write or {}).get('games_completed'),
        'write_games_failed': (write or {}).get('games_failed'),
        'write_rows_expected': (write or {}).get('rows_expected'),
        'write_rows_unchanged': (write or {}).get('rows_unchanged'),
        'write_mutations_by_target': {
            'game_log': 0, 'pitcher_identity': 0, 'appearance_team': 0,
        },
        'selected_games_completed': (decision.get('write') or {}).get(
            'completed_games', []
        ),
        'newly_completed_checkpoints': transition.get(
            'newly_completed_checkpoints'
        ),
        'unexpected_games_changed': transition.get('unexpected_games_changed'),
        'completed_final_games_before': transition.get('completed_before'),
        'completed_final_games_after': transition.get('completed_after'),
        'unresolved_final_games_before': transition.get('unresolved_before'),
        'unresolved_final_games_after': transition.get('unresolved_after'),
        'game_log_content_hash_before': (before or {}).get(
            'game_log_content_hash'
        ),
        'game_log_content_hash_after': (after or {}).get(
            'game_log_content_hash'
        ),
        'correction_provenance_hash_before': (before or {}).get(
            'correction_provenance_hash'
        ),
        'correction_provenance_hash_after': (after or {}).get(
            'correction_provenance_hash'
        ),
        'appearance_team_hash_before': (before or {}).get(
            'appearance_team_hash'
        ),
        'appearance_team_hash_after': (after or {}).get('appearance_team_hash'),
        'pitcher_state_hash_before': (before or {}).get('pitcher_state_hash'),
        'pitcher_state_hash_after': (after or {}).get('pitcher_state_hash'),
        'dead_letter_count_before': (before or {}).get('dead_letter_count'),
        'dead_letter_count_after': (after or {}).get('dead_letter_count'),
        'replay_rows_expected': (replay or {}).get('rows_expected'),
        'replay_rows_unchanged': (replay or {}).get('rows_unchanged'),
        'replay_mutations_by_target': {
            'game_log': 0, 'pitcher_identity': 0, 'appearance_team': 0,
        },
        'replay_ignored_decimal_differences': (replay or {}).get(
            'derived_companion_differences_ignored'
        ),
        'replay_complete_reconciliation_fingerprint': decision.get(
            'replay_fingerprint'
        ),
        'transaction_boundary': TRANSACTION_BOUNDARY,
        'partial_completion': not passed and bool(write),
        'publication_complete': False,
        'automated_lane': 'off',
        'baseball_data_rows_changed': False,
        'checkpoint_state_written': passed,
        'authoritative_mode': 'unapproved',
        'next_action': NEXT_ACTION_PASS if passed else NEXT_ACTION_FAILED,
        'failed_invariant': decision.get('failed_invariant'),
    }


def pass_markdown(closeout) -> str:
    return '\n'.join([
        '## FOUNDATION 3C R4 — PASS',
        '',
        '### Authorization',
        '- Approved games: '
        + ', '.join(str(pk) for pk in closeout['approved_game_pks']),
        f"- Parity contract version: {closeout['parity_contract_version']}",
        '- Approved fingerprint:',
        f"  {closeout['approved_fingerprint']}",
        '- Preflight fingerprint matched: yes',
        '- Exact scope: yes',
        '- Stale contract-3 fingerprint rejected: yes',
        '',
        '### Controlled write',
        f"- Games completed: {closeout['write_games_completed']}",
        f"- Games failed: {closeout['write_games_failed']}",
        f"- Appearance rows: {closeout['write_rows_expected']}",
        '- GameLog inserts: 0',
        '- GameLog updates: 0',
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
        '- Newly completed checkpoints/work items: '
        f"{closeout['newly_completed_checkpoints']}",
        f"- Completed final games before: {closeout['completed_final_games_before']}",
        f"- Completed final games after: {closeout['completed_final_games_after']}",
        f"- Unresolved final games before: {closeout['unresolved_final_games_before']}",
        f"- Unresolved final games after: {closeout['unresolved_final_games_after']}",
        f"- Unexpected games changed: {closeout['unexpected_games_changed']}",
        '',
        '### Data integrity',
        '- GameLog data changed: no',
        '- Pitcher data changed: no',
        '- Appearance-team data changed: no',
        '- Correction provenance changed: no',
        '- Dead letters created: 0',
        '',
        '### Immediate replay',
        '- Games completed: 5',
        f"- Rows unchanged: {closeout['replay_rows_unchanged']}",
        '- Mutations across all targets: 0',
        '- Decimal-only differences safely ignored: '
        f"{closeout['replay_ignored_decimal_differences']}",
        '- Replay passed: yes',
        '',
        '### Result',
        '- The contract-4 authorized five-game write completed successfully.',
        '- Only governed checkpoint/work-item state changed.',
        '- No baseball-data rows were changed.',
        '- The immediate replay converged to zero mutations.',
        '- Foundation 3C may proceed directly to R5: one full shadow of the',
        '  remaining 99 unresolved games.',
        '- GAME_DRIVEN_INGESTION_MODE remains off.',
        '- Authoritative mode remains unapproved.',
        '',
    ])


def failed_markdown(summary) -> str:
    return '\n'.join([
        '## FOUNDATION 3C R4 — FAILED',
        '',
        f"- Failed invariant: `{summary.get('failed_invariant')}`",
        f"- Phase: `{summary.get('phase')}`",
        f"- Expected: `{summary.get('expected')}`",
        f"- Observed: `{summary.get('observed')}`",
        '',
        '- Approved games: '
        + ', '.join(str(pk) for pk in APPROVED_GAME_PKS),
        f"- Games completed: {summary.get('write_games_completed')}",
        f"- Games failed: {summary.get('write_games_failed')}",
        f"- Rows expected: {summary.get('write_rows_expected')}",
        f"- Newly completed checkpoints: {summary.get('newly_completed_checkpoints')}",
        f"- Partial completion: {summary.get('partial_completion')}",
        '',
        '- Artifact: `foundation-3c-r4-controlled-write-and-replay`',
        '',
        'This is a rollout stop. Do not retry R4 or begin R5 without founder',
        'review.',
        '',
    ])


def closeout_markdown(closeout) -> str:
    lines = [
        '# Foundation 3C R4 — closeout',
        '',
        f"- Result: **{closeout['result'].upper()}**",
        f"- Reference date: {closeout['reference_date']}",
        '- Games: '
        + ', '.join(str(pk) for pk in closeout['approved_game_pks']),
        f"- Parity contract version: {closeout['parity_contract_version']}",
        f"- Approved fingerprint: `{closeout['approved_fingerprint']}`",
        '- Stale contract-3 fingerprint rejected: yes',
        '',
        '## What changed',
        f"- Newly completed checkpoints: {closeout['newly_completed_checkpoints']}",
        f"- Completed final games: {closeout['completed_final_games_before']} "
        f"-> {closeout['completed_final_games_after']}",
        f"- Unresolved final games: {closeout['unresolved_final_games_before']} "
        f"-> {closeout['unresolved_final_games_after']}",
        f"- Unexpected games changed: {closeout['unexpected_games_changed']}",
        '',
        '## What did not change',
        f"- GameLog content hash: `{closeout['game_log_content_hash_before']}`",
        '- Correction provenance hash: '
        f"`{closeout['correction_provenance_hash_before']}`",
        f"- Appearance-team hash: `{closeout['appearance_team_hash_before']}`",
        f"- Pitcher state hash: `{closeout['pitcher_state_hash_before']}`",
        f"- Dead letters: {closeout['dead_letter_count_before']} "
        f"-> {closeout['dead_letter_count_after']}",
        '',
        '## Replay',
        f"- Rows unchanged: {closeout['replay_rows_unchanged']}",
        '- Mutations across all targets: 0',
        '- Fingerprint: '
        f"`{closeout['replay_complete_reconciliation_fingerprint']}`",
        '',
        '## Contract',
        f"- Transaction boundary: {closeout['transaction_boundary']}",
        f"- Partial completion: {closeout['partial_completion']}",
        f"- Automated lane: {closeout['automated_lane']}",
        f"- Authoritative mode: {closeout['authoritative_mode']}",
        '',
        f"**Next action.** {closeout['next_action']}",
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
        path, json.dumps(payload, indent=2, sort_keys=True, default=str) + '\n',
    )


def _run_preflight(args) -> int:
    try:
        before = _load(args.before_state, 'before_state_file_exists')
        preflight = _load(args.preflight, 'preflight_file_exists')
        validate_preflight(before, preflight)
    except ValidationFailure as failure:
        print(f'R4 preflight refused: {failure.invariant}')
        return EXIT_FAILED
    print('R4 preflight authorized the controlled write.')
    return EXIT_OK


def _run_closeout(args) -> int:
    before = preflight = write = after = replay = None
    try:
        before = _load(args.before_state, 'before_state_file_exists')
        preflight = _load(args.preflight, 'preflight_file_exists')
        write = _load(args.write, 'write_file_exists')
        after = _load(args.after_state, 'after_state_file_exists')
        replay = _load(args.replay, 'replay_file_exists')
        decision = validate_closeout(
            before_state=before, preflight=preflight, write=write,
            after_state=after, replay=replay, write_exit=args.write_exit,
        )
        decision['write_exit'] = args.write_exit
        closeout = build_closeout(
            decision, repository_sha=args.repository_sha, run_id=args.run_id,
            before=before, after=after, preflight=preflight, write=write,
            replay=replay,
        )
        summary = dict(closeout)
        markdown = pass_markdown(closeout)
        exit_code = EXIT_OK
    except ValidationFailure as failure:
        decision = {
            'result': RESULT_FAILED,
            'failed_invariant': failure.invariant,
            'write_exit': args.write_exit,
        }
        closeout = build_closeout(
            decision, repository_sha=args.repository_sha, run_id=args.run_id,
            before=before, after=after, preflight=preflight, write=write,
            replay=replay,
        )
        summary = dict(closeout)
        summary.update({
            'phase': failure.invariant.split('_')[0],
            'expected': failure.expected,
            'observed': failure.observed,
        })
        markdown = failed_markdown(summary)
        exit_code = EXIT_FAILED

    _write_json(args.summary_json, summary)
    _write_text(args.summary_markdown, markdown)
    _write_json(args.closeout_json, closeout)
    _write_text(args.closeout_markdown, closeout_markdown(closeout))
    print(markdown)
    return exit_code


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='Validate the Foundation 3C R4 controlled write.',
    )
    sub = parser.add_subparsers(dest='phase', required=True)

    pre = sub.add_parser('preflight')
    pre.add_argument('--before-state', required=True)
    pre.add_argument('--preflight', required=True)

    close = sub.add_parser('closeout')
    close.add_argument('--before-state', required=True)
    close.add_argument('--preflight', required=True)
    close.add_argument('--write', required=True)
    close.add_argument('--after-state', required=True)
    close.add_argument('--replay', required=True)
    close.add_argument('--write-exit', type=int, required=True)
    close.add_argument('--summary-json', required=True)
    close.add_argument('--summary-markdown', required=True)
    close.add_argument('--closeout-json', required=True)
    close.add_argument('--closeout-markdown', required=True)
    close.add_argument('--repository-sha', default=None)
    close.add_argument('--run-id', default=None)

    args = parser.parse_args(argv)
    if args.phase == 'preflight':
        return _run_preflight(args)
    return _run_closeout(args)


if __name__ == '__main__':
    raise SystemExit(main())
