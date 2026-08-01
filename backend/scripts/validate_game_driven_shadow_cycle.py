"""Activation-health validator for one automated game-driven shadow cycle.

Permanent activation operations support. It reads the durable summary a
production runner already wrote and decides whether that cycle is safe
evidence. It queries no database, calls no MLB endpoint, runs no ingestion, and
recomputes no game plan — a validator that re-derives the thing it validates
cannot catch that thing being wrong.

The two cycles observe different moments, so they get different contracts.

DAILY — the lane runs BEFORE the legacy pitcher writer. When newly final or
corrected games exist the projection legitimately contains inserts and updates.
Those are *projected reconciliation actions*, never writes performed by shadow.
Failing a daily cycle for finding work would fail every useful day. The daily
question is whether the writer that ran afterwards actually realized the
projected canonical target state.

POSTGAME — the lane runs AFTER the existing completed-game writer. By then the
canonical rows should already be right, so a clean postgame cycle projects
nothing at all. A nonzero postgame projection means the postgame writer left
canonical work behind, and that is an activation-health failure.

Exit codes: ``0`` PASS, ``1`` FAILED, ``2`` the validator could not run.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from services import game_log_reconciliation as reconciliation  # noqa: E402
from services import game_driven_ingestion  # noqa: E402
from services import pitcher_identity_reconciliation as pitcher_identity  # noqa: E402
from services import sync_metadata  # noqa: E402
from services.sync_publication_proof import (  # noqa: E402
    LEAGUE_PUBLICATION_EXPECTED_PENDING_ACTIVE_SLATE,
)


RESULT_PASS = 'PASS'
RESULT_FAILED = 'FAILED'

CYCLE_DAILY = 'daily'
CYCLE_POSTGAME = 'postgame'
CYCLE_KINDS = (CYCLE_DAILY, CYCLE_POSTGAME)

WORK_STATE_NO_CANDIDATES = 'no_candidates'
WORK_STATE_CANDIDATES = 'candidates_planned'

EXIT_PASS = 0
EXIT_FAILED = 1
EXIT_UNUSABLE = 2

_HEX64 = re.compile(r'^[0-9a-f]{64}$')

# Every mutation target the run report accounts for. A postgame cycle must be
# zero on all of them; listing them explicitly is what stops a cycle reporting
# "no mutations" while one target is unaccounted for.
PROJECTED_MUTATION_TARGETS = (
    'pitcher_identity_mutations',
    'pitcher_identity_creations',
    'pitcher_identity_reactivations',
    'pitcher_identity_metadata_updates',
    'pitcher_identity_blocked',
    'appearance_team_mutations',
    'complete_mutation_count',
    'canonical_outs_corrections',
    'statistical_corrections',
    'provenance_only_updates',
    'derived_companion_fields_applied',
)

# Actual database effects. Any nonzero value means the shadow lane itself wrote,
# which is a different and far more serious failure than a projection finding
# work.
EXECUTION_EFFECT_FIELDS = (
    'game_log_rows_written',
    'pitcher_rows_written',
    'appearance_team_rows_written',
    'correction_provenance_rows_written',
    'work_items_created',
    'work_items_updated',
    'work_items_completed',
    'checkpoints_advanced',
    'dead_letters_created',
    'commits_performed',
)

EXPECTED_VERSIONS = {
    'reconciliation_plan_version': reconciliation.RECONCILIATION_PLAN_VERSION,
    'parity_contract_version': reconciliation.PARITY_CONTRACT_VERSION,
    'innings_semantics_version': reconciliation.INNINGS_SEMANTICS_VERSION,
    'complete_plan_version': reconciliation.COMPLETE_PLAN_VERSION,
    'identity_plan_version': pitcher_identity.IDENTITY_PLAN_VERSION,
}


class ValidationError(Exception):
    """The validator could not run at all (exit 2), distinct from FAILED."""


# ── Failure recording ───────────────────────────────────────────────────────


def _fail(failures, invariant, *, expected=None, observed=None, detail=None):
    entry = {'invariant': invariant}
    if expected is not None:
        entry['expected'] = expected
    if observed is not None:
        entry['observed'] = observed
    if detail is not None:
        entry['detail'] = detail
    failures.append(entry)


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


# ── Current production outcome ──────────────────────────────────────────────


def _validate_production_outcome(summary, cycle_kind, runner_exit_code, failures):
    if runner_exit_code != 0:
        _fail(
            failures, 'runner_exit_code',
            expected=0, observed=runner_exit_code,
        )

    status = (summary.get('sync') or {}).get('status') or summary.get('status')
    if status not in sync_metadata.SUCCESSFUL_STATUSES:
        _fail(
            failures, 'sync_status',
            expected=list(sync_metadata.SUCCESSFUL_STATUSES), observed=status,
        )

    proof = summary.get('publication_proof') or {}
    verified = proof.get('verified') is True
    if cycle_kind == CYCLE_DAILY:
        if not verified:
            _fail(
                failures, 'daily_publication_proof',
                expected='verified', observed=proof.get('verified'),
            )
        return

    # Postgame keeps its established two-outcome policy: a verified candidate,
    # or the expected active-slate pending state the runner itself already
    # treats as success. The canonical constant is imported rather than spelled
    # out, so this cannot drift from the runner it mirrors.
    expected_pending = (
        proof.get('league_publication_status')
        == LEAGUE_PUBLICATION_EXPECTED_PENDING_ACTIVE_SLATE
    )
    if not (verified or expected_pending):
        _fail(
            failures, 'postgame_publication_proof',
            expected=f'verified or {LEAGUE_PUBLICATION_EXPECTED_PENDING_ACTIVE_SLATE}',
            observed=proof.get('league_publication_status'),
        )


# ── Shadow identity, versions, planning ─────────────────────────────────────


def _validate_shadow_identity(lane, failures):
    if lane.get('mode') != game_driven_ingestion.MODE_SHADOW:
        _fail(
            failures, 'configured_mode',
            expected=game_driven_ingestion.MODE_SHADOW, observed=lane.get('mode'),
        )
    if lane.get('writes_enabled') is not False:
        _fail(
            failures, 'writes_enabled',
            expected=False, observed=lane.get('writes_enabled'),
        )
    if lane.get('publication_authoritative') is not False:
        _fail(
            failures, 'publication_authoritative',
            expected=False, observed=lane.get('publication_authoritative'),
        )
    for field, expected in sorted(EXPECTED_VERSIONS.items()):
        observed = lane.get(field)
        if str(observed) != str(expected):
            _fail(failures, field, expected=expected, observed=observed)


def _validate_planning(lane, failures):
    if lane.get('status') != 'complete':
        _fail(
            failures, 'report_status', expected='complete',
            observed=lane.get('status'),
        )
    for field in ('schedule_authority_missing', 'finality_conflicts'):
        if _int(lane.get(field)) != 0:
            _fail(failures, field, expected=0, observed=lane.get(field))
    if lane.get('budget_stop_triggered'):
        _fail(failures, 'budget_stop_triggered', expected=False, observed=True)
    failure_classes = lane.get('failure_classes') or {}
    if failure_classes:
        _fail(
            failures, 'failure_classes', expected={},
            observed=sorted(failure_classes),
        )
    # No authorization path may appear in an observation cycle.
    for field in (
        'expected_plan_fingerprint',
        'observed_plan_fingerprint',
        'authorized_plan_fingerprint',
    ):
        if lane.get(field):
            _fail(failures, f'authorization_path_present:{field}', expected=None)


def _validate_game_accounting(lane, failures):
    planned = _int(lane.get('games_planned'))
    for field in ('games_attempted', 'games_fetched', 'games_completed'):
        if _int(lane.get(field)) != planned:
            _fail(failures, field, expected=planned, observed=lane.get(field))
    for field in ('games_failed', 'games_remaining'):
        if _int(lane.get(field)) != 0:
            _fail(failures, field, expected=0, observed=lane.get(field))
    if planned == 0:
        for field in ('rows_expected', 'rows_inserted', 'rows_updated',
                      'rows_unchanged', 'rows_blocked'):
            if _int(lane.get(field)) != 0:
                _fail(
                    failures, f'no_work_cycle:{field}', expected=0,
                    observed=lane.get(field),
                )
    return planned


def _validate_fingerprints(lane, games, planned, failures):
    run_fingerprint = lane.get('reconciliation_plan_fingerprint')
    if planned == 0:
        return
    if not run_fingerprint or not _HEX64.match(str(run_fingerprint)):
        _fail(
            failures, 'run_fingerprint', expected='64 lowercase hex characters',
            observed=run_fingerprint,
        )
    seen = set()
    for game in games:
        game_pk = game.get('game_pk')
        if game_pk in seen:
            _fail(failures, 'duplicate_game', observed=game_pk)
        seen.add(game_pk)
        if not game.get('reconciliation_plan_fingerprint'):
            _fail(failures, 'per_game_fingerprint_missing', observed=game_pk)
        if not game.get('source_revision'):
            _fail(failures, 'source_revision_missing', observed=game_pk)
    if len(seen) != planned:
        _fail(
            failures, 'planned_game_count', expected=planned, observed=len(seen),
        )
    order = [game.get('game_pk') for game in games]
    if order != sorted(order, key=lambda value: (value is None, value)) and \
            order != list(order):
        _fail(failures, 'canonical_processing_order_not_explicit')


def _validate_runtime(lane, planned, failures):
    for field in ('planner_seconds', 'elapsed_seconds'):
        if lane.get(field) is None:
            _fail(failures, f'runtime_missing:{field}')
    if planned > 0 and lane.get('fetch_seconds') is None:
        _fail(failures, 'runtime_missing:fetch_seconds')
    if lane.get('allocated_budget_seconds') is None:
        _fail(failures, 'allocated_budget_missing')
    headroom = lane.get('remaining_budget_seconds')
    if headroom is None:
        _fail(failures, 'budget_headroom_missing')
    elif float(headroom) < 0:
        _fail(failures, 'budget_headroom_negative', observed=headroom)


def _validate_execution_effects(lane, failures):
    effects = lane.get('execution_effects')
    if not isinstance(effects, dict):
        _fail(failures, 'execution_effects_missing')
        return {}
    if effects.get('writes_enabled') is not False:
        _fail(
            failures, 'execution_effects.writes_enabled',
            expected=False, observed=effects.get('writes_enabled'),
        )
    if effects.get('publication_authoritative') is not False:
        _fail(
            failures, 'execution_effects.publication_authoritative',
            expected=False, observed=effects.get('publication_authoritative'),
        )
    for field in EXECUTION_EFFECT_FIELDS:
        if _int(effects.get(field)) != 0:
            _fail(
                failures, f'execution_effects.{field}',
                expected=0, observed=effects.get(field),
            )
    return effects


# ── Cycle-specific contracts ────────────────────────────────────────────────


def _validate_daily(lane, failures):
    # Projected inserts and updates are legitimate here. Blocked rows are not:
    # a blocked plan means the official line could not safely authorize a
    # correction, and it is never a clean cycle.
    if _int(lane.get('rows_blocked')) != 0:
        _fail(
            failures, 'daily_projected_blocked', expected=0,
            observed=lane.get('rows_blocked'),
        )

    realization = lane.get('realization')
    if not isinstance(realization, dict):
        _fail(failures, 'daily_realization_missing')
        return
    if realization.get('available') is False:
        _fail(
            failures, 'daily_realization_unavailable',
            observed=realization.get('reason'),
        )
        return
    if not realization.get('applicable'):
        # No candidates planned: nothing to realize, and that is clean.
        if realization.get('all_projected_targets_realized') is not True:
            _fail(failures, 'daily_realization_no_work_not_clean')
        return

    for field in ('unresolved_rows', 'divergent_rows', 'missing_rows',
                  'duplicate_rows', 'prohibited_identity_actions'):
        if _int(realization.get(field)) != 0:
            _fail(
                failures, f'daily_realization.{field}', expected=0,
                observed=realization.get(field),
            )
    if realization.get('source_revision_match') is not True:
        _fail(failures, 'daily_realization.source_revision_match', expected=True)
    if realization.get('safe_digest_match') is not True:
        _fail(failures, 'daily_realization.safe_digest_match', expected=True)
    if realization.get('all_projected_targets_realized') is not True:
        _fail(
            failures, 'daily_realization.all_projected_targets_realized',
            expected=True, observed=realization.get('all_projected_targets_realized'),
        )


def _validate_postgame(lane, failures):
    # The writer already ran. A clean cycle projects nothing.
    for field in ('rows_inserted', 'rows_updated', 'rows_blocked'):
        if _int(lane.get(field)) != 0:
            _fail(
                failures, f'postgame_projected.{field}', expected=0,
                observed=lane.get(field),
            )
    expected_rows = _int(lane.get('rows_expected'))
    unchanged = _int(lane.get('rows_unchanged'))
    if expected_rows != unchanged:
        _fail(
            failures, 'postgame_rows_all_unchanged',
            expected=expected_rows, observed=unchanged,
        )
    for field in PROJECTED_MUTATION_TARGETS:
        if _int(lane.get(field)) != 0:
            _fail(
                failures, f'postgame_projected.{field}', expected=0,
                observed=lane.get(field),
            )


# ── Entry point ─────────────────────────────────────────────────────────────


def validate_cycle(summary, *, cycle_kind, runner_exit_code) -> dict:
    if cycle_kind not in CYCLE_KINDS:
        raise ValidationError(f'unsupported cycle kind: {cycle_kind!r}')

    failures: list[dict] = []
    _validate_production_outcome(summary, cycle_kind, runner_exit_code, failures)

    lane = ((summary.get('sync') or {}).get('game_driven_ingestion')) or {}
    if not lane:
        _fail(failures, 'game_driven_report_missing')
        return _decision(
            failures, cycle_kind=cycle_kind, lane={},
            runner_exit_code=runner_exit_code, summary=summary,
        )
    if lane.get('status') == 'disabled':
        _fail(
            failures, 'game_driven_lane_disabled',
            expected=game_driven_ingestion.MODE_SHADOW,
            observed=lane.get('mode'),
        )
        return _decision(
            failures, cycle_kind=cycle_kind, lane=lane,
            runner_exit_code=runner_exit_code, summary=summary,
        )
    if cycle_kind == CYCLE_DAILY and lane.get('job_name') == sync_metadata.JOB_POSTGAME_REFRESH:
        _fail(
            failures, 'cycle_kind_mismatch',
            expected=sync_metadata.JOB_DAILY_SYNC, observed=lane.get('job_name'),
        )
    if cycle_kind == CYCLE_POSTGAME and lane.get('job_name') == sync_metadata.JOB_DAILY_SYNC:
        _fail(
            failures, 'cycle_kind_mismatch',
            expected=sync_metadata.JOB_POSTGAME_REFRESH, observed=lane.get('job_name'),
        )

    _validate_shadow_identity(lane, failures)
    _validate_planning(lane, failures)
    planned = _validate_game_accounting(lane, failures)
    games = list(lane.get('games') or (summary.get('sync') or {}).get(
        'game_driven_games'
    ) or ())
    _validate_fingerprints(lane, games, planned, failures)
    _validate_runtime(lane, planned, failures)
    _validate_execution_effects(lane, failures)

    if cycle_kind == CYCLE_DAILY:
        _validate_daily(lane, failures)
    else:
        _validate_postgame(lane, failures)

    return _decision(
        failures, cycle_kind=cycle_kind, lane=lane,
        runner_exit_code=runner_exit_code, summary=summary,
    )


def _decision(failures, *, cycle_kind, lane, runner_exit_code, summary) -> dict:
    planned = _int(lane.get('games_planned'))
    realization = lane.get('realization') if isinstance(
        lane.get('realization'), dict
    ) else {}
    effects = lane.get('execution_effects') if isinstance(
        lane.get('execution_effects'), dict
    ) else {}
    return {
        'result': RESULT_FAILED if failures else RESULT_PASS,
        'cycle_kind': cycle_kind,
        'work_state': (
            WORK_STATE_NO_CANDIDATES if planned == 0 else WORK_STATE_CANDIDATES
        ),
        'runner_exit_code': runner_exit_code,
        'sync_status': (summary.get('sync') or {}).get('status'),
        'publication_proof': {
            'verified': (summary.get('publication_proof') or {}).get('verified'),
            'league_publication_status': (
                (summary.get('publication_proof') or {}).get(
                    'league_publication_status'
                )
            ),
        },
        'configured_mode': lane.get('mode'),
        'writes_enabled': lane.get('writes_enabled'),
        'publication_authoritative': lane.get('publication_authoritative'),
        'parity_contract_version': lane.get('parity_contract_version'),
        'games_discovered': _int(lane.get('games_discovered')),
        'games_planned': planned,
        'games_attempted': _int(lane.get('games_attempted')),
        'games_fetched': _int(lane.get('games_fetched')),
        'games_completed': _int(lane.get('games_completed')),
        'games_failed': _int(lane.get('games_failed')),
        'games_remaining': _int(lane.get('games_remaining')),
        'newly_final_count': _int(lane.get('newly_final_count')),
        'corrected_final_count': _int(lane.get('corrected_final_count')),
        'retry_count': _int(lane.get('retry_count')),
        'projected': {
            'rows_expected': _int(lane.get('rows_expected')),
            'rows_inserted': _int(lane.get('rows_inserted')),
            'rows_updated': _int(lane.get('rows_updated')),
            'rows_unchanged': _int(lane.get('rows_unchanged')),
            'rows_blocked': _int(lane.get('rows_blocked')),
            **{
                field: _int(lane.get(field))
                for field in PROJECTED_MUTATION_TARGETS
            },
        },
        'realization': {
            key: realization.get(key)
            for key in (
                'applicable', 'available', 'work_state', 'projected_rows',
                'projected_inserts', 'projected_updates', 'projected_unchanged',
                'projected_blocked', 'realized_rows', 'realized_inserts',
                'realized_updates', 'already_matching_rows', 'unresolved_rows',
                'divergent_rows', 'missing_rows', 'duplicate_rows',
                'identity_creations_projected', 'identity_creations_realized',
                'prohibited_identity_actions', 'current_state_mutations_refused',
                'appearance_team_actions_projected',
                'appearance_team_actions_realized', 'corrections_projected',
                'corrections_realized', 'source_revision_match',
                'safe_digest_match', 'all_projected_targets_realized',
                'unresolved_identities', 'divergent_identities',
            )
            if key in realization
        },
        'execution_effects': dict(effects),
        'runtime': {
            'planner_seconds': lane.get('planner_seconds'),
            'fetch_seconds': lane.get('fetch_seconds'),
            'persistence_seconds': lane.get('persistence_seconds'),
            'elapsed_seconds': lane.get('elapsed_seconds'),
            'allocated_budget_seconds': lane.get('allocated_budget_seconds'),
            'remaining_budget_seconds': lane.get('remaining_budget_seconds'),
        },
        'run_fingerprint': lane.get('reconciliation_plan_fingerprint'),
        'failed_invariants': failures,
        # Never authorization. Recorded on every cycle, PASS or FAILED, so no
        # reader can mistake an observation for a permission.
        'write_approved': False,
        'future_write_authorized': False,
    }


# ── Rendering ───────────────────────────────────────────────────────────────


def render_markdown(decision) -> str:
    cycle = decision['cycle_kind'].upper()
    if decision['result'] == RESULT_PASS:
        return _render_pass(decision, cycle)
    return _render_failed(decision, cycle)


def _render_pass(decision, cycle) -> str:
    projected = decision['projected']
    effects = decision['execution_effects']
    runtime = decision['runtime']
    lines = [
        f'## GAME-DRIVEN SHADOW ACTIVATION — {cycle} PASS',
        '',
        '### Current production path',
        f"- Sync status: {decision['sync_status']}",
        f"- Runner exit: {decision['runner_exit_code']}",
        f"- Publication proof: {_publication_text(decision)}",
        '- Current publication authority changed: no',
        '',
        '### Shadow identity',
        f"- Configured mode: {decision['configured_mode']}",
        f"- Effective mode: {decision['configured_mode']}",
        '- Writes enabled: no',
        '- Publication authoritative: no',
        f"- Parity contract: {decision['parity_contract_version']}",
        '',
        '### Planning',
        f"- Games discovered: {decision['games_discovered']}",
        f"- Games planned: {decision['games_planned']}",
        f"- Newly final: {decision['newly_final_count']}",
        f"- Corrected final: {decision['corrected_final_count']}",
        f"- Retried: {decision['retry_count']}",
        '- Schedule-authority gaps: 0',
        '- Finality conflicts: 0',
        '- Budget stop: no',
        '',
    ]
    if decision['cycle_kind'] == CYCLE_DAILY:
        realization = decision['realization']
        lines += [
            '### Projection before legacy writer',
            f"- Rows expected: {projected['rows_expected']}",
            f"- Projected inserts: {projected['rows_inserted']}",
            f"- Projected updates: {projected['rows_updated']}",
            f"- Projected unchanged: {projected['rows_unchanged']}",
            '- Projected blocked: 0',
            '',
            '### Realization after legacy writer',
            '- Projected targets realized: yes',
            f"- Realized rows: {realization.get('realized_rows', 0)}",
            '- Missing rows: 0',
            '- Divergent rows: 0',
            '- Duplicate rows: 0',
            '- Source revisions matched: yes',
            '- Safe target digests matched: yes',
            '',
        ]
    else:
        lines += [
            '### Convergence after postgame writer',
            f"- Games planned: {decision['games_planned']}",
            f"- Rows expected: {projected['rows_expected']}",
            f"- Rows unchanged: {projected['rows_unchanged']}",
            '- Projected inserts / updates / blocked: 0 / 0 / 0',
            '- Projected mutation targets: 0',
            '',
        ]
    lines += [
        '### Actual shadow execution effects',
        f"- GameLog rows written: {effects.get('game_log_rows_written', 0)}",
        f"- Pitcher rows written: {effects.get('pitcher_rows_written', 0)}",
        f"- Appearance-team rows written: "
        f"{effects.get('appearance_team_rows_written', 0)}",
        f"- Work items changed: "
        f"{effects.get('work_items_created', 0) + effects.get('work_items_updated', 0)}",
        f"- Checkpoints advanced: {effects.get('checkpoints_advanced', 0)}",
        f"- Game-driven dead letters created: {effects.get('dead_letters_created', 0)}",
        '',
        '### Runtime',
        f"- Planner seconds: {runtime.get('planner_seconds')}",
        f"- Fetch seconds: {runtime.get('fetch_seconds')}",
        f"- Total seconds: {runtime.get('elapsed_seconds')}",
        f"- Budget seconds: {runtime.get('allocated_budget_seconds')}",
        f"- Headroom seconds: {runtime.get('remaining_budget_seconds')}",
        '',
        '### Evidence',
        f"- Run fingerprint: {decision['run_fingerprint'] or 'no-work'}",
        '- Write approved: no',
        '- Future write authorized: no',
        '',
        '### Result',
    ]
    if decision['cycle_kind'] == CYCLE_DAILY:
        lines += [
            '- Daily game-driven shadow ran automatically.',
            '- Projected canonical targets were realized by the current '
            'production writer.',
        ]
    else:
        lines += [
            '- Postgame game-driven shadow ran automatically after the current '
            'writer.',
            '- It converged to zero projected canonical mutations.',
        ]
    lines += [
        '- Shadow itself performed no database write.',
        '- Existing publication authority remained unchanged.',
        '- This cycle does not authorize automated write.',
        '',
    ]
    return '\n'.join(lines)


def _render_failed(decision, cycle) -> str:
    projected = decision['projected']
    effects = decision['execution_effects']
    runtime = decision['runtime']
    lines = [
        f'## GAME-DRIVEN SHADOW ACTIVATION — {cycle} FAILED',
        '',
        f"- Cycle kind: {decision['cycle_kind']}",
        f"- Work state: {decision['work_state']}",
        '',
        '### Failed invariants',
        '',
        '| Invariant | Expected | Observed |',
        '|---|---|---|',
    ]
    for failure in decision['failed_invariants']:
        lines.append(
            f"| `{failure.get('invariant')}` | "
            f"{_cell(failure.get('expected'))} | {_cell(failure.get('observed'))} |"
        )
    lines += [
        '',
        '### Counts',
        f"- Games planned / completed / failed: {decision['games_planned']} / "
        f"{decision['games_completed']} / {decision['games_failed']}",
        f"- Rows expected / unchanged: {projected['rows_expected']} / "
        f"{projected['rows_unchanged']}",
        f"- Projected inserts / updates / blocked: {projected['rows_inserted']} / "
        f"{projected['rows_updated']} / {projected['rows_blocked']}",
        f"- Actual shadow writes: "
        f"{sum(int(effects.get(field) or 0) for field in EXECUTION_EFFECT_FIELDS)}",
        f"- Total seconds / budget / headroom: {runtime.get('elapsed_seconds')} / "
        f"{runtime.get('allocated_budget_seconds')} / "
        f"{runtime.get('remaining_budget_seconds')}",
        '',
    ]
    if decision['realization']:
        realization = decision['realization']
        lines += [
            '### Realization',
            f"- Realized / already matching: {realization.get('realized_rows')} / "
            f"{realization.get('already_matching_rows')}",
            f"- Missing / divergent / duplicate / unresolved: "
            f"{realization.get('missing_rows')} / {realization.get('divergent_rows')} / "
            f"{realization.get('duplicate_rows')} / {realization.get('unresolved_rows')}",
            '',
        ]
    lines += [
        '### Standing',
        '',
        'Current publication authority remains unchanged.',
        'Automated write mode remains prohibited.',
        'Authoritative mode remains prohibited.',
        'Review the activation artifact before promotion or rollback.',
        '',
    ]
    return '\n'.join(lines)


def _publication_text(decision) -> str:
    proof = decision['publication_proof']
    if proof.get('verified') is True:
        return 'verified'
    return str(proof.get('league_publication_status') or 'unverified')


def _cell(value) -> str:
    if value is None:
        return '—'
    return f'`{value}`'


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Validate one automated game-driven shadow cycle from the durable '
            'runner summary. Reads only; never queries a database or MLB.'
        )
    )
    parser.add_argument('--sync-summary', required=True)
    parser.add_argument('--cycle-kind', required=True, choices=CYCLE_KINDS)
    parser.add_argument('--runner-exit-code', required=True, type=int)
    parser.add_argument('--summary-json', required=True)
    parser.add_argument('--summary-markdown', required=True)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    try:
        raw = Path(args.sync_summary).read_text(encoding='utf-8')
    except OSError:
        print('::error::Activation validator could not read the sync summary.')
        return EXIT_UNUSABLE
    try:
        summary = json.loads(raw)
    except json.JSONDecodeError:
        print('::error::Activation validator found a malformed sync summary.')
        return EXIT_UNUSABLE
    if not isinstance(summary, dict):
        print('::error::Activation validator found an unexpected summary shape.')
        return EXIT_UNUSABLE

    try:
        decision = validate_cycle(
            summary,
            cycle_kind=args.cycle_kind,
            runner_exit_code=args.runner_exit_code,
        )
    except ValidationError as exc:
        print(f'::error::Activation validator could not run: {exc}')
        return EXIT_UNUSABLE

    from utils.summary_output import SummaryOutputError, write_summary

    try:
        write_summary(decision, args.summary_json)
        Path(args.summary_markdown).parent.mkdir(parents=True, exist_ok=True)
        Path(args.summary_markdown).write_text(
            render_markdown(decision), encoding='utf-8',
        )
    except (SummaryOutputError, OSError):
        print('::error::Activation validator could not write its artifacts.')
        return EXIT_UNUSABLE

    return EXIT_PASS if decision['result'] == RESULT_PASS else EXIT_FAILED


if __name__ == '__main__':
    raise SystemExit(main())
