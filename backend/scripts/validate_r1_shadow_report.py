#!/usr/bin/env python
"""Validate a Foundation 3C Stage R1 shadow report. Fails closed.

R1 replays the five games the first controlled Foundation 3C write already
reconciled. Before PR #571 that replay projected 14 updates whose only changed
field was the derived decimal innings companion — an applied write that never
converged. R1 proves the repair: the same five games must now replay to zero
mutations, with the 14 companion differences recognised and ignored rather
than treated as official corrections.

This is a rollout gate, not a report. Every invariant below must hold; a
failure is a stop, never a warning. The validator is a separate module rather
than YAML so it can be unit-tested against real report shapes.

It emits only safe structured values — counts, game ids, field names, and the
named invariant that failed. No payload, path, credential, or exception text
reaches its output.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services import pitcher_identity_reconciliation as identity  # noqa: E402


EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_ERROR = 2

REFERENCE_DATE = '2026-07-29'
APPROVED_GAME_PKS = (823518, 824735, 823761, 824083, 824327)

EXPECTED_APPEARANCE_ROWS = 38
EXPECTED_IGNORED_COMPANION_DIFFERENCES = 14
EXPECTED_INNINGS_SEMANTICS_VERSION = '2'

# Every identity action that would write a Pitcher row, plus the two retired
# completed-game write actions. R1 asserts zero of all of them: seeing a retired
# action at all means unrepaired code produced the report.
FORBIDDEN_IDENTITY_ACTIONS = tuple(sorted(
    set(identity.MUTATING_ACTIONS) | set(identity.RETIRED_WRITE_ACTIONS)
))

# Fields whose presence in changed_fields_counts means the repair did not hold
# or a genuine correction appeared that R1 is not authorized to apply.
FORBIDDEN_CHANGED_FIELDS = (
    'innings_pitched',
    'innings_pitched_outs',
    'earned_runs',
    'hits_allowed',
)


class ValidationFailure(Exception):
    """One named invariant did not hold."""

    def __init__(self, invariant, expected, observed):
        super().__init__(invariant)
        self.invariant = invariant
        self.expected = expected
        self.observed = observed


def _require(invariant, expected, observed):
    if observed != expected:
        raise ValidationFailure(invariant, expected, observed)


def validate(report) -> dict:
    """Assert every R1 invariant. Raises ValidationFailure on the first break."""
    if not isinstance(report, dict):
        raise ValidationFailure('report_is_an_object', 'object', type(report).__name__)

    approved = sorted(APPROVED_GAME_PKS)

    # ── Execution identity ──────────────────────────────────────────────────
    _require('status', 'complete', report.get('status'))
    _require('mode', 'shadow', report.get('mode'))
    _require('reference_date', REFERENCE_DATE, report.get('reference_date'))

    # ── Exclusive scope ─────────────────────────────────────────────────────
    _require('execution_scope_mode', 'exclusive', report.get('execution_scope_mode'))
    _require('requested_game_count', 5, report.get('requested_game_count'))
    _require('planned_game_count', 5, report.get('planned_game_count'))
    _require(
        'execution_scope_exact_match', True,
        report.get('execution_scope_exact_match'),
    )
    _require(
        'requested_game_pks', approved,
        sorted(report.get('requested_game_pks') or []),
    )
    _require(
        'planned_game_pks', approved,
        sorted(report.get('planned_game_pks') or []),
    )
    _require(
        'unexpected_planned_game_pks', [],
        list(report.get('unexpected_planned_game_pks') or []),
    )
    _require(
        'missing_requested_game_pks', [],
        list(report.get('missing_requested_game_pks') or []),
    )

    # ── Processing ──────────────────────────────────────────────────────────
    _require('games_attempted', 5, report.get('games_attempted'))
    _require('games_fetched', 5, report.get('games_fetched'))
    _require('games_completed', 5, report.get('games_completed'))
    _require('games_failed', 0, report.get('games_failed'))
    _require('games_remaining', 0, report.get('games_remaining'))

    # ── Row reconciliation ──────────────────────────────────────────────────
    _require('rows_expected', EXPECTED_APPEARANCE_ROWS, report.get('rows_expected'))
    _require('rows_inserted', 0, report.get('rows_inserted'))
    _require('rows_updated', 0, report.get('rows_updated'))
    _require('rows_unchanged', EXPECTED_APPEARANCE_ROWS, report.get('rows_unchanged'))
    _require('rows_blocked', 0, report.get('rows_blocked'))

    # ── Canonical innings semantics (D-008) ─────────────────────────────────
    _require('canonical_outs_corrections', 0, report.get('canonical_outs_corrections'))
    _require(
        'derived_companion_fields_applied', 0,
        report.get('derived_companion_fields_applied'),
    )
    _require(
        'derived_companion_differences_ignored',
        EXPECTED_IGNORED_COMPANION_DIFFERENCES,
        report.get('derived_companion_differences_ignored'),
    )
    _require(
        'decimal_only_updates_suppressed',
        EXPECTED_IGNORED_COMPANION_DIFFERENCES,
        report.get('decimal_only_updates_suppressed'),
    )
    _require(
        'innings_semantics_version', EXPECTED_INNINGS_SEMANTICS_VERSION,
        report.get('innings_semantics_version'),
    )

    # ── Pitcher identity (D-009) ────────────────────────────────────────────
    # The original R1 pass proved GameLog convergence only. These rows also
    # carried identity actions that write mode would have applied, so R1 now
    # requires complete database convergence, not just appearance convergence.
    for counter in (
        'pitcher_identity_mutations',
        'pitcher_identity_creations',
        'pitcher_identity_reactivations',
        'pitcher_identity_metadata_updates',
        'pitcher_identity_blocked',
        'appearance_team_mutations',
        'complete_mutation_count',
    ):
        _require(counter, 0, report.get(counter))
    _require(
        'pitcher_identity_changed_fields_counts', {},
        dict(report.get('pitcher_identity_changed_fields_counts') or {}),
    )
    _require(
        'pitcher_identity_unique_pitchers_affected', 0,
        report.get('pitcher_identity_unique_pitchers_affected'),
    )
    identity_actions = dict(report.get('pitcher_identity_action_counts') or {})
    for action in FORBIDDEN_IDENTITY_ACTIONS:
        if identity_actions.get(action):
            raise ValidationFailure(
                f'pitcher_identity_action_counts_excludes_{action}', 0,
                identity_actions[action],
            )

    # ── Correction safety ───────────────────────────────────────────────────
    _require('statistical_corrections', 0, report.get('statistical_corrections'))
    _require('authority_reconciliations', 0, report.get('authority_reconciliations'))
    _require('provenance_only_updates', 0, report.get('provenance_only_updates'))

    changed_fields = dict(report.get('changed_fields_counts') or {})
    for field in FORBIDDEN_CHANGED_FIELDS:
        if field in changed_fields:
            raise ValidationFailure(
                f'changed_fields_counts_excludes_{field}', 0, changed_fields[field],
            )
    _require('changed_fields_counts_is_empty', {}, changed_fields)

    # ── Per game ────────────────────────────────────────────────────────────
    games = list(report.get('games') or [])
    _require('per_game_result_count', 5, len(games))
    _require(
        'per_game_ids', approved,
        sorted(game.get('game_pk') for game in games),
    )

    row_total = 0
    ignored_total = 0
    suppressed_total = 0
    for game in games:
        label = game.get('game_pk')
        _require(f'game_{label}_status', 'projected', game.get('status'))
        _require(f'game_{label}_inserted', 0, game.get('inserted'))
        _require(f'game_{label}_updated', 0, game.get('updated'))
        _require(f'game_{label}_blocked', 0, game.get('blocked'))
        _require(f'game_{label}_error_class', None, game.get('error_class'))

        rows = list(game.get('rows') or [])
        row_total += len(rows)
        for row in rows:
            pitcher = row.get('pitcher_mlb_id')
            _require(f'row_{label}_{pitcher}_action', 'unchanged', row.get('action'))
            _require(
                f'row_{label}_{pitcher}_changed_field_count', 0,
                row.get('changed_field_count'),
            )
            _require(
                f'row_{label}_{pitcher}_changed_fields', [],
                list(row.get('changed_fields') or []),
            )
            _require(
                f'row_{label}_{pitcher}_governed_and_safe', True,
                row.get('governed_and_safe'),
            )
            _require(
                f'row_{label}_{pitcher}_blocked_reason', None,
                row.get('blocked_reason'),
            )
            action = row.get('pitcher_identity_action')
            if action in FORBIDDEN_IDENTITY_ACTIONS:
                raise ValidationFailure(
                    f'row_{label}_{pitcher}_pitcher_identity_action',
                    identity.ACTION_UNCHANGED, action,
                )
            _require(
                f'row_{label}_{pitcher}_identity_changed_fields', [],
                list(row.get('pitcher_identity_changed_fields') or []),
            )
            _require(
                f'row_{label}_{pitcher}_identity_applied_fields', [],
                list(row.get('pitcher_identity_applied_fields') or []),
            )
            _require(
                f'row_{label}_{pitcher}_identity_mutation_digest', '',
                row.get('pitcher_identity_mutation_digest') or '',
            )
            _require(
                f'row_{label}_{pitcher}_identity_governed_and_safe', True,
                bool(row.get('pitcher_identity_governed_and_safe', True)),
            )
            _require(
                f'row_{label}_{pitcher}_identity_blocked_reason', None,
                row.get('pitcher_identity_blocked_reason'),
            )
            # Suppressed historical differences are expected and allowed: they
            # are refused evidence, not a mutation.
            suppressed_total += len(
                row.get('pitcher_identity_suppressed_fields') or []
            )
            ignored_total += len(
                row.get('derived_companion_differences_ignored') or []
            )

    # The row level must agree with the totals — a passing aggregate over a
    # miscounted set of rows is not a pass.
    _require('per_row_total', EXPECTED_APPEARANCE_ROWS, row_total)
    if ignored_total:
        _require(
            'per_row_ignored_companion_differences',
            EXPECTED_IGNORED_COMPANION_DIFFERENCES, ignored_total,
        )

    return {
        'result': 'PASS',
        'reference_date': REFERENCE_DATE,
        'requested_game_pks': approved,
        'planned_game_pks': approved,
        'execution_scope_exact_match': True,
        'games_completed': report.get('games_completed'),
        'games_failed': report.get('games_failed'),
        'rows_expected': report.get('rows_expected'),
        'rows_inserted': report.get('rows_inserted'),
        'rows_updated': report.get('rows_updated'),
        'rows_unchanged': report.get('rows_unchanged'),
        'rows_blocked': report.get('rows_blocked'),
        'canonical_outs_corrections': report.get('canonical_outs_corrections'),
        'derived_companion_differences_ignored': report.get(
            'derived_companion_differences_ignored'
        ),
        'statistical_corrections': report.get('statistical_corrections'),
        'innings_semantics_version': report.get('innings_semantics_version'),
        'pitcher_identity_mutations': report.get('pitcher_identity_mutations'),
        'pitcher_identity_creations': report.get('pitcher_identity_creations'),
        'pitcher_identity_reactivations': report.get(
            'pitcher_identity_reactivations'
        ),
        'pitcher_identity_metadata_updates': report.get(
            'pitcher_identity_metadata_updates'
        ),
        'pitcher_identity_blocked': report.get('pitcher_identity_blocked'),
        'appearance_team_mutations': report.get('appearance_team_mutations'),
        'complete_mutation_count': report.get('complete_mutation_count'),
        'historical_current_state_changes_suppressed': report.get(
            'historical_current_state_changes_suppressed'
        ),
        'suppressed_current_state_fields_observed': suppressed_total,
        'database_writes': 'none',
        'failed_invariant': None,
    }


def _pass_markdown(summary) -> str:
    return '\n'.join([
        '## FOUNDATION 3C R1 — PASS',
        '',
        '### Scope',
        '- Requested: 5',
        '- Planned: 5',
        '- Exact match: yes',
        '',
        '### Games',
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
        '### Canonical innings',
        '- Decimal-only differences safely ignored: '
        f"{summary['derived_companion_differences_ignored']}",
        f"- Canonical outs corrections: {summary['canonical_outs_corrections']}",
        f"- Statistical corrections: {summary['statistical_corrections']}",
        '',
        '### Mutations by target',
        f"- GameLog: {summary['rows_inserted'] + summary['rows_updated']}",
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
        '### Result',
        '- The original five-game write now replays to zero mutations across '
        'every database target.',
        '- Foundation 3C may proceed to R2 review.',
        '- No database writes were performed.',
        '',
    ])


def _fail_markdown(summary) -> str:
    return '\n'.join([
        '## FOUNDATION 3C R1 — FAILED',
        '',
        f"- Failed invariant: `{summary.get('failed_invariant')}`",
        f"- Expected: `{summary.get('expected')}`",
        f"- Observed: `{summary.get('observed')}`",
        '',
        f"- Requested games: `{summary.get('requested_game_pks')}`",
        f"- Planned games: `{summary.get('planned_game_pks')}`",
        f"- Artifact: `{summary.get('artifact')}`",
        '',
        'This is a rollout stop. R2 must not begin.',
        '',
    ])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='Validate a Foundation 3C R1 shadow report.',
    )
    parser.add_argument('--report', required=True)
    parser.add_argument('--summary-json', required=True)
    parser.add_argument('--summary-markdown', required=True)
    args = parser.parse_args(argv)

    artifact = Path(args.report).name
    report_path = Path(args.report)

    if not report_path.exists():
        summary = {
            'result': 'FAIL',
            'failed_invariant': 'report_file_exists',
            'expected': 'present',
            'observed': 'missing',
            'artifact': artifact,
        }
        exit_code = EXIT_FAIL
    else:
        try:
            report = json.loads(report_path.read_text(encoding='utf-8'))
        except Exception:  # noqa: BLE001 - the parse failure itself is the signal
            summary = {
                'result': 'FAIL',
                'failed_invariant': 'report_is_valid_json',
                'expected': 'json',
                'observed': 'unparsable',
                'artifact': artifact,
            }
            exit_code = EXIT_FAIL
        else:
            try:
                summary = validate(report)
                summary['artifact'] = artifact
                exit_code = EXIT_PASS
            except ValidationFailure as failure:
                summary = {
                    'result': 'FAIL',
                    'failed_invariant': failure.invariant,
                    'expected': failure.expected,
                    'observed': failure.observed,
                    'requested_game_pks': sorted(
                        report.get('requested_game_pks') or []
                    ),
                    'planned_game_pks': sorted(
                        report.get('planned_game_pks') or []
                    ),
                    'artifact': artifact,
                }
                exit_code = EXIT_FAIL

    markdown = (
        _pass_markdown(summary) if summary['result'] == 'PASS'
        else _fail_markdown(summary)
    )
    Path(args.summary_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.summary_json).write_text(
        json.dumps(summary, indent=2, sort_keys=True, default=str) + '\n',
        encoding='utf-8',
    )
    Path(args.summary_markdown).write_text(markdown, encoding='utf-8')
    print(markdown)
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
