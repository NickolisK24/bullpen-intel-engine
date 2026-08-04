#!/usr/bin/env python
"""Manual exact-scope no-op write qualification.

Proves the game-driven ingestion lane can enter its governed write-capable path
for exactly one completed game while mutating no baseball data.

    python scripts/run_game_driven_noop_qualification.py \
        --game-pk 824488 \
        --expected-head-sha <40 hex> \
        --confirmation QUALIFY_NOOP_GAME_824488 \
        --artifact-dir artifacts/manual-noop-write-qualification

Manual only. This script is invoked by one workflow that has only
``workflow_dispatch``, and it re-validates every authorization condition itself
rather than trusting the workflow's gates — a guard that trusts its caller is
not a guard.

Sequence:

    authorize (no database, no network)
      -> application context
      -> production writer guard (the same advisory lock the public sync uses)
      -> SHADOW phase, exclusive to the requested game, reads only
      -> refuse unless every planned row is already matching
      -> pre-execution canonical readback + state digest
      -> WRITE phase, exclusive, authorized by the reviewed fingerprint
      -> post-execution readback + realization proof
      -> verdict, evidence artifact, non-zero exit for FAILED / UNPROVEN

Exit codes: 0 PASS, 1 FAILED, 2 UNPROVEN.

Output carries counts, digests, fingerprints, safe reason codes and governed
field NAMES only — never credentials, connection strings, headers, raw payloads,
filesystem paths, or exception text.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services import noop_write_qualification as qualification  # noqa: E402


SUMMARY_JSON = 'qualification-summary.json'
SUMMARY_MARKDOWN = 'qualification-summary.md'
METADATA_JSON = 'qualification-metadata.json'


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Manual exact-scope no-op write qualification.',
    )
    parser.add_argument('--game-pk', required=True)
    parser.add_argument('--expected-head-sha', required=True)
    parser.add_argument('--confirmation', required=True)
    parser.add_argument('--operator-note', default='')
    parser.add_argument(
        '--artifact-dir',
        default='artifacts/manual-noop-write-qualification',
    )
    parser.add_argument(
        '--reference-date',
        default=None,
        help='Represented baseball date. Defaults to today UTC.',
    )
    return parser.parse_args(argv)


def event_context(args, environ=None) -> dict:
    """Collect the GitHub event metadata this run must be authorized against."""
    env = environ if environ is not None else os.environ
    return {
        'event_name': env.get('GITHUB_EVENT_NAME'),
        'repository': env.get('GITHUB_REPOSITORY'),
        'actor': env.get('GITHUB_ACTOR'),
        'ref': env.get('GITHUB_REF'),
        'github_sha': env.get('GITHUB_SHA'),
        'run_id': env.get('GITHUB_RUN_ID'),
        'run_attempt': env.get('GITHUB_RUN_ATTEMPT'),
        'workflow': env.get('GITHUB_WORKFLOW'),
        'expected_head_sha': args.expected_head_sha,
        'confirmation': args.confirmation,
    }


def _identity_block(context, *, game_pk, note) -> dict:
    return {
        'schema_version': qualification.SCHEMA_VERSION,
        'qualification_type': qualification.QUALIFICATION_TYPE,
        'repository': context.get('repository'),
        'workflow_name': context.get('workflow'),
        'workflow_run_id': context.get('run_id'),
        'workflow_run_attempt': context.get('run_attempt'),
        'commit_sha': qualification.normalize_sha(context.get('github_sha')),
        'ref': context.get('ref'),
        'actor': context.get('actor'),
        'event_name': context.get('event_name'),
        'executed_at': datetime.now(timezone.utc).isoformat(),
        'requested_game_pk': game_pk,
        'operator_note': note,
    }


def build_app():
    import app as app_module

    return app_module.create_app()


def resolve_reference_date(raw):
    if raw:
        return date.fromisoformat(str(raw).strip())
    return datetime.now(timezone.utc).date()


def run(args) -> dict:
    """Execute the qualification and return its full evidence document."""
    context = event_context(args)
    note = qualification.sanitize_note(args.operator_note)

    # ── Input parsing, before anything is initialised ────────────────────────
    try:
        game_pk = qualification.parse_game_pk(args.game_pk)
    except qualification.QualificationInputError as exc:
        return _refused(
            context, game_pk=None, note=note, failed=[exc.reason],
        )

    identity = _identity_block(context, game_pk=game_pk, note=note)

    # ── Authorization, before any database or network access ────────────────
    authorization_failures = qualification.validate_authorization(
        context, game_pk=game_pk,
    )
    if authorization_failures:
        return _refused(
            context, game_pk=game_pk, note=note, failed=authorization_failures,
        )

    reference_date = resolve_reference_date(args.reference_date)

    flask_app = build_app()
    from services import game_driven_ingestion as lane
    from services import game_driven_realization as realization_service
    from services import sync_metadata
    from utils.db import db

    with flask_app.app_context():
        # Writer-guard state is tracked, never assumed. The evidence document
        # is built only AFTER the release attempt, so the artifact can never
        # claim a release that did not happen.
        guard_state = {
            'acquired': False,
            'release_attempted': False,
            'released': False,
        }
        guard = None
        try:
            guard = sync_metadata.acquire_sync_writer_guard(
                job_name=sync_metadata.JOB_DAILY_SYNC,
                source=sync_metadata.SOURCE_GITHUB_ACTIONS,
                lock_scope=sync_metadata.LOCK_SCOPE_PUBLIC,
            )
            guard_state['acquired'] = guard is not None
        except Exception:  # noqa: BLE001 - a contended lock is UNPROVEN
            guard = None

        if not guard_state['acquired']:
            return _refused(
                context, game_pk=game_pk, note=note,
                unproven=[qualification.UNPROVEN_WRITER_GUARD_UNAVAILABLE],
                writer_guard=guard_state,
            )

        # Collected inside the guarded block, finalized outside it.
        collected: dict = {'write_phase_entered': False}
        try:
            # ── WORK-ITEM PRECONDITION, BEFORE ANYTHING ELSE ─────────────────
            # This must come first. A qualification for a game with no durable
            # completed work item cannot succeed, so running the shadow lane
            # first would spend an MLB request and a full canonical planning
            # pass to reach a refusal that was already decided — and would make
            # the evidence claim the planner ran when the outcome never
            # depended on it. Production run 30862655470 refused exactly here.
            bookkeeping_before = qualification.read_lane_bookkeeping(game_pk)
            collected['bookkeeping_before'] = bookkeeping_before
            collected['work_item_precondition_checked'] = (
                bookkeeping_before is not None
            )
            # Present is not the same fact as COMPLETED. The governing
            # contract requires an existing COMPLETED durable item, so a row in
            # any other state must not reach the shadow lane, an MLB request,
            # plan generation, the write-capable path, or the lane ledger.
            target_before = (bookkeeping_before or {}).get('target') or {}
            collected['target_work_item_present'] = bool(
                bookkeeping_before
                and bookkeeping_before.get('target_present')
            )
            collected['target_work_item_status'] = target_before.get('status')
            collected['work_item_precondition_passed'] = bool(
                collected['target_work_item_present']
                and target_before.get('status')
                == qualification.REQUIRED_WORK_ITEM_STATUS_BEFORE
            )

            if bookkeeping_before is None:
                collected['preflight_failed'] = []
                collected['preflight_unproven'] = [
                    qualification.UNPROVEN_BOOKKEEPING_READBACK_UNAVAILABLE
                ]
                raise _PreflightRefusal()
            if not collected['work_item_precondition_passed']:
                # A missing row and a present-but-unfinished row are different
                # facts and get different reasons.
                collected['preflight_failed'] = [
                    qualification.FAILED_TARGET_WORK_ITEM_MISSING
                    if not collected['target_work_item_present']
                    else qualification.FAILED_TARGET_WORK_ITEM_NOT_COMPLETED
                ]
                collected['preflight_unproven'] = []
                raise _PreflightRefusal()

            # ── SHADOW: exclusive, reads only ────────────────────────────────
            # Entered only after the precondition passed. The flag is set
            # immediately before the call so it records an attempt, and the
            # raised/returned distinction is recorded separately.
            collected['planner_phase_entered'] = True
            try:
                shadow_report = lane.run_game_driven_ingestion(
                    reference_date,
                    mode=lane.MODE_SHADOW,
                    only_game_pks=[game_pk],
                )
                collected['planner_returned'] = True
            except Exception:  # noqa: BLE001 - never leak exception text
                collected['planner_raised'] = True
                collected['preflight_failed'] = []
                collected['preflight_unproven'] = [
                    qualification.UNPROVEN_LANE_ERROR
                ]
                raise _PreflightRefusal()

            collected['shadow_report'] = shadow_report
            shadow_governance = qualification.evaluate_plan_governance(
                shadow_report
            )
            shadow_rows = qualification.plan_rows(shadow_report)
            fingerprint = shadow_report.get('reconciliation_plan_fingerprint')

            # ── Refuse BEFORE the writer if anything would mutate ────────────
            preflight_failed: list[str] = []
            preflight_unproven: list[str] = []
            if not shadow_rows:
                preflight_unproven.append(
                    qualification.UNPROVEN_SHADOW_PHASE_UNUSABLE
                )
            if not shadow_governance['all_rows_already_matching'] and shadow_rows:
                preflight_failed.append(
                    qualification.FAILED_PLAN_PROPOSES_MUTATION
                )
            if not fingerprint:
                preflight_unproven.append(
                    qualification.UNPROVEN_PLAN_FINGERPRINT_MISSING
                )
            shadow_scope = qualification.evaluate_scope(
                shadow_report, game_pk=game_pk,
            )
            if not shadow_scope['execution_scope_exact_match']:
                preflight_failed.append(qualification.FAILED_SCOPE_NOT_EXACT)
            if shadow_scope['planned_game_count'] != 1:
                preflight_failed.append(
                    qualification.FAILED_GAME_NOT_PLANNABLE
                    if shadow_scope['planned_game_count'] == 0
                    else qualification.FAILED_PLANNED_COUNT_NOT_ONE
                )

            if preflight_failed or preflight_unproven:
                collected['preflight_failed'] = preflight_failed
                collected['preflight_unproven'] = preflight_unproven
                raise _PreflightRefusal()

            # ── Pre-execution canonical readback ─────────────────────────────
            collected['before_state'] = qualification.read_canonical_state(
                shadow_rows
            )

            # ── WRITE: exclusive, authorized by the reviewed fingerprint ─────
            # The lane re-fetches, re-plans, and refuses before its first
            # mutation if the source revision or the plan moved. That drift
            # check is the lane's own; it is not re-implemented here.
            write_report = lane.run_game_driven_ingestion(
                reference_date,
                mode=lane.MODE_WRITE,
                only_game_pks=[game_pk],
                expected_plan_fingerprint=fingerprint,
            )
            collected['write_report'] = write_report
            collected['write_phase_entered'] = True

            # ── Post-execution readback, bookkeeping, and realization ────────
            collected['after_state'] = qualification.read_canonical_state(
                qualification.plan_rows(write_report) or shadow_rows
            )
            collected['bookkeeping_after'] = (
                qualification.read_lane_bookkeeping(game_pk)
            )
            try:
                collected['realization'] = (
                    realization_service.build_daily_realization(write_report)
                )
            except Exception:  # noqa: BLE001 - absent proof is UNPROVEN
                collected['realization'] = None
        except _PreflightRefusal:
            pass
        except Exception:  # noqa: BLE001 - never leak exception text
            collected['lane_error'] = True
        finally:
            # End the read transaction before releasing the guard. Every exit
            # path reaches here, including the early refusals, and a refusal
            # that leaves an open transaction keeps table locks held for as
            # long as the session lives. The audit runner already does this;
            # the qualification runner did not.
            try:
                db.session.rollback()
            except Exception:  # noqa: BLE001
                pass
            # Release BEFORE the document is built, and record what actually
            # happened. Nothing below hardcodes success.
            if guard is not None:
                guard_state['release_attempted'] = True
                try:
                    guard.release()
                    guard_state['released'] = True
                except Exception:  # noqa: BLE001 - a failed release is UNPROVEN
                    guard_state['released'] = False

    # ── Finalized outside the guarded block ─────────────────────────────────
    if collected.get('lane_error'):
        return _refused(
            context, game_pk=game_pk, note=note,
            unproven=[qualification.UNPROVEN_LANE_ERROR],
            writer_guard=guard_state,
        )

    if 'preflight_failed' in collected:
        decision = qualification.decide({
            'failed_reasons': collected['preflight_failed'],
            'unproven_reasons': (
                list(collected['preflight_unproven'])
                + _guard_reasons(guard_state)
            ),
        })
        decision['writer_guard'] = dict(guard_state)
        return _document(
            identity=identity,
            decision=decision,
            shadow_report=collected.get('shadow_report'),
            write_report=None,
            before_state=None,
            after_state=None,
            realization=None,
            reference_date=reference_date,
            write_phase_entered=False,
            execution_state=_state_from(collected, game_pk),
        )

    decision = qualification.assess(
        context=context,
        game_pk=game_pk,
        shadow_report=collected.get('shadow_report'),
        write_report=collected.get('write_report'),
        before_state=collected.get('before_state'),
        after_state=collected.get('after_state'),
        realization=collected.get('realization'),
        bookkeeping_before=collected.get('bookkeeping_before'),
        bookkeeping_after=collected.get('bookkeeping_after'),
        writer_guard=guard_state,
    )
    return _document(
        identity=identity,
        decision=decision,
        shadow_report=collected.get('shadow_report'),
        write_report=collected.get('write_report'),
        before_state=collected.get('before_state'),
        after_state=collected.get('after_state'),
        realization=collected.get('realization'),
        reference_date=reference_date,
        write_phase_entered=collected.get('write_phase_entered', False),
        execution_state=_state_from(collected, game_pk),
    )


def _state_from(collected, game_pk) -> dict:
    return qualification.execution_state(
        work_item_precondition_checked=collected.get(
            'work_item_precondition_checked', False
        ),
        work_item_precondition_passed=collected.get(
            'work_item_precondition_passed', False
        ),
        planner_phase_entered=collected.get('planner_phase_entered', False),
        planner_returned=collected.get('planner_returned', False),
        planner_raised=collected.get('planner_raised', False),
        shadow_report=collected.get('shadow_report'),
        game_pk=game_pk,
    )


class _PreflightRefusal(Exception):
    """Internal control flow: refuse before the write phase is entered."""


def _guard_reasons(guard_state) -> list[str]:
    if not guard_state.get('acquired'):
        return [qualification.UNPROVEN_WRITER_GUARD_UNAVAILABLE]
    if not (
        guard_state.get('release_attempted') and guard_state.get('released')
    ):
        return [qualification.UNPROVEN_WRITER_GUARD_RELEASE_UNPROVEN]
    return []


def _refused(context, *, game_pk, note, failed=(), unproven=(),
             writer_guard=None) -> dict:
    decision = qualification.decide({
        'failed_reasons': list(failed),
        'unproven_reasons': list(unproven),
    })
    decision['writer_guard'] = dict(writer_guard or {
        'acquired': False, 'release_attempted': False, 'released': False,
    })
    return _document(
        identity=_identity_block(context, game_pk=game_pk, note=note),
        decision=decision,
        shadow_report=None,
        write_report=None,
        before_state=None,
        after_state=None,
        realization=None,
        reference_date=None,
        write_phase_entered=False,
    )


def _document(*, identity, decision, shadow_report, write_report, before_state,
              after_state, realization, reference_date,
              write_phase_entered, execution_state=None) -> dict:
    state = execution_state or qualification.execution_state()
    shadow_report = shadow_report or {}
    write_report = write_report or {}
    effects = decision.get('execution_effects') or (
        qualification.split_execution_effects(write_report)
    )
    guard_state = decision.get('writer_guard') or {}
    bookkeeping = decision.get('lane_bookkeeping') or {}

    return {
        'identity': identity,
        'request': {
            'requested_game_pk': identity.get('requested_game_pk'),
            'requested_game_count': (
                1 if identity.get('requested_game_pk') is not None else 0
            ),
            'confirmation_valid': (
                qualification.FAILED_CONFIRMATION_MISMATCH
                not in decision['failed_reasons']
            ),
            'expected_head_sha_valid': not (
                {
                    qualification.FAILED_EXPECTED_SHA_MALFORMED,
                    qualification.FAILED_EXPECTED_SHA_MISMATCH,
                } & set(decision['failed_reasons'])
            ),
            'reference_date': (
                reference_date.isoformat() if reference_date else None
            ),
        },
        'game_authority': {
            'source_authority_planner': 'game_ingestion_planner.plan_game_work',
            # What actually executed. Never derived from an absent failure.
            'work_item_precondition_checked': state[
                'work_item_precondition_checked'
            ],
            'work_item_precondition_passed': state[
                'work_item_precondition_passed'
            ],
            'planner_phase_entered': state['planner_phase_entered'],
            'planner_returned': state['planner_returned'],
            'planner_raised': state['planner_raised'],
            'finality_check_executed': state['finality_check_executed'],
            'finality_proven_by_planner': state['finality_proven_by_planner'],
            'finality_display': qualification.render_finality(state),
            'source_revisions_before_planning': decision.get(
                'source_revisions_before'
            ) or [],
            'source_revisions_before_execution': decision.get(
                'source_revisions_before_execution'
            ) or [],
            'source_revision_match': decision.get('source_revision_match'),
        },
        'plan': {
            'reconciliation_plan_version': shadow_report.get(
                'reconciliation_plan_version'
            ),
            'parity_contract_version': shadow_report.get(
                'parity_contract_version'
            ),
            'innings_semantics_version': shadow_report.get(
                'innings_semantics_version'
            ),
            'identity_plan_version': shadow_report.get('identity_plan_version'),
            'plan_fingerprint_before_execution': decision.get(
                'shadow_plan_fingerprint'
            ),
            'plan_fingerprint_authorized_at_execution': decision.get(
                'authorized_plan_fingerprint'
            ),
            'plan_fingerprint_match': decision.get('plan_fingerprint_match'),
            'shadow_plan': decision.get('shadow_plan'),
            'write_plan': decision.get('write_plan'),
            'scope': decision.get('scope'),
            'shadow_scope': decision.get('shadow_scope'),
        },
        'pre_execution': {
            'readback_available': bool(
                (before_state or {}).get('available')
            ),
            'state_digest': (before_state or {}).get('digest'),
            'row_count': (before_state or {}).get('row_count'),
            'identity_count': (before_state or {}).get('identity_count'),
        },
        'execution': {
            'write_phase_entered': write_phase_entered,
            'mode': write_report.get('mode'),
            'writes_enabled': effects.get('writes_enabled'),
            'publication_authoritative': effects.get(
                'publication_authoritative'
            ),
            'backfill_included': False,
            'baseball_data_effects': effects.get('baseball_data'),
            'baseball_row_mutation_performed': effects.get(
                'baseball_row_mutation_performed'
            ),
            'lane_bookkeeping_effects': effects.get('lane_bookkeeping'),
            'transaction_boundary_entered': effects.get(
                'transaction_boundary_entered'
            ),
            # Governed shape and scope of the ledger movement.
            'lane_bookkeeping_before': bookkeeping.get(
                'lane_bookkeeping_before'
            ),
            'lane_bookkeeping_after': bookkeeping.get('lane_bookkeeping_after'),
            'lane_bookkeeping_changed_fields': bookkeeping.get(
                'lane_bookkeeping_changed_fields'
            ),
            'lane_bookkeeping_unexpected_changed_fields': bookkeeping.get(
                'lane_bookkeeping_unexpected_changed_fields'
            ),
            'lane_bookkeeping_allowed_changed_fields': bookkeeping.get(
                'lane_bookkeeping_allowed_changed_fields'
            ),
            'lane_bookkeeping_expected_delta': bookkeeping.get(
                'lane_bookkeeping_expected_delta'
            ),
            'lane_bookkeeping_observed_delta': bookkeeping.get(
                'lane_bookkeeping_observed_delta'
            ),
            'lane_bookkeeping_delta_match': bookkeeping.get(
                'lane_bookkeeping_delta_match'
            ),
            'target_work_item_present_before': bookkeeping.get(
                'target_work_item_present_before'
            ),
            'target_work_item_present_after': bookkeeping.get(
                'target_work_item_present_after'
            ),
            'unrelated_work_item_count': bookkeeping.get(
                'unrelated_work_item_count'
            ),
            'unrelated_work_items_digest_before': bookkeeping.get(
                'unrelated_work_items_digest_before'
            ),
            'unrelated_work_items_digest_after': bookkeeping.get(
                'unrelated_work_items_digest_after'
            ),
            'unrelated_checkpoints_digest_before': bookkeeping.get(
                'unrelated_checkpoints_digest_before'
            ),
            'unrelated_checkpoints_digest_after': bookkeeping.get(
                'unrelated_checkpoints_digest_after'
            ),
            'unrelated_bookkeeping_unchanged': bookkeeping.get(
                'unrelated_bookkeeping_unchanged'
            ),
            'lane_bookkeeping_note': (
                'The canonical lane claims and completes its own work item and '
                'advances its checkpoint whenever writes are enabled, '
                'independently of whether the plan mutates anything. These '
                'counters are the lane completion ledger, not baseball data. '
                'They are reported with their real values; no baseball row was '
                'mutated.'
            ),
            'writer_guard': 'sync_metadata.acquire_sync_writer_guard',
            # Measured, never assumed. The document is built only after the
            # release attempt, so these three report what actually happened.
            'writer_guard_acquired': bool(guard_state.get('acquired')),
            'writer_guard_release_attempted': bool(
                guard_state.get('release_attempted')
            ),
            'writer_guard_released': bool(guard_state.get('released')),
            'elapsed_seconds': write_report.get('elapsed_seconds'),
            'budget_stop_triggered': write_report.get('budget_stop_triggered'),
            'lane_status': write_report.get('status'),
        },
        'post_execution': {
            'readback_available': bool((after_state or {}).get('available')),
            'state_digest': (after_state or {}).get('digest'),
            'row_count': (after_state or {}).get('row_count'),
            'state_digest_match': decision.get('state_digest_match'),
            'realization_available': bool(realization),
            'already_matching_rows': (realization or {}).get(
                'already_matching_rows'
            ),
            'divergent_rows': (realization or {}).get('divergent_rows'),
            'missing_rows': (realization or {}).get('missing_rows'),
            'duplicate_rows': (realization or {}).get('duplicate_rows'),
            'unresolved_rows': (realization or {}).get('unresolved_rows'),
            'prohibited_identity_actions': (realization or {}).get(
                'prohibited_identity_actions'
            ),
            'all_projected_targets_realized': (realization or {}).get(
                'all_projected_targets_realized'
            ),
        },
        'verdict': {
            'result': decision['result'],
            'exit_code': decision['exit_code'],
            'failed_reasons': decision['failed_reasons'],
            'unproven_reasons': decision['unproven_reasons'],
            'explanation': _explanation(decision),
            'non_authorization_statement': (
                qualification.NON_AUTHORIZATION_STATEMENT
            ),
        },
    }


def _explanation(decision) -> str:
    result = decision['result']
    if result == qualification.RESULT_PASS:
        return (
            'The lane entered its write-capable path for exactly one completed '
            'game, every planned row was already matching, no baseball row was '
            'mutated, and the canonical state read back identical before and '
            'after. The lane advanced its own completion ledger, which is '
            'reported separately and is not baseball data.'
        )
    if result == qualification.RESULT_FAILED:
        return (
            'A contract condition was violated. The reason codes name each '
            'observed violation. This is a definite negative result, not '
            'absent evidence.'
        )
    return (
        'Trustworthy evidence could not be completed, so the no-op claim is '
        'unproven. UNPROVEN is not a pass and is not a warning: absent '
        'evidence is the state most easily mistaken for success.'
    )


# ── Markdown evidence ───────────────────────────────────────────────────────


def render_markdown(document) -> str:
    identity = document['identity']
    verdict = document['verdict']
    execution = document['execution']
    plan = document['plan']
    scope = plan.get('scope') or {}
    baseball = execution.get('baseball_data_effects') or {}
    bookkeeping = execution.get('lane_bookkeeping_effects') or {}

    lines = [
        '# Manual no-op write qualification',
        '',
        f"**Verdict: {verdict['result']}**",
        '',
        verdict['explanation'],
        '',
        '## Identity',
        '',
        '| field | value |',
        '| :--- | :--- |',
        f"| qualification type | `{identity['qualification_type']}` |",
        f"| schema version | {identity['schema_version']} |",
        f"| repository | {identity.get('repository')} |",
        f"| workflow run | {identity.get('workflow_run_id')} "
        f"(attempt {identity.get('workflow_run_attempt')}) |",
        f"| commit | `{identity.get('commit_sha')}` |",
        f"| ref | {identity.get('ref')} |",
        f"| actor | {identity.get('actor')} |",
        f"| event | {identity.get('event_name')} |",
        f"| requested game | {identity.get('requested_game_pk')} |",
        f"| executed at | {identity.get('executed_at')} |",
        '',
        '## Scope and plan',
        '',
        '| check | value |',
        '| :--- | :--- |',
        f"| requested games | {scope.get('requested_game_pks')} |",
        f"| planned games | {scope.get('planned_game_pks')} |",
        f"| exact scope match | {scope.get('execution_scope_exact_match')} |",
        f"| distinct games fetched | {scope.get('distinct_games_fetched')} |",
        f"| fetch operations | {scope.get('fetch_operations')} |",
        f"| games completed | {scope.get('games_completed')} |",
        f"| plan fingerprint match | {plan.get('plan_fingerprint_match')} |",
        f"| finality | "
        f"{document['game_authority'].get('finality_display')} |",
        f"| source revision match | "
        f"{document['game_authority'].get('source_revision_match')} |",
        f"| planned rows | {(plan.get('write_plan') or {}).get('planned_row_count')} |",
        f"| planned already matching | "
        f"{(plan.get('write_plan') or {}).get('planned_unchanged_count')} |",
        f"| prohibited actions | "
        f"{(plan.get('write_plan') or {}).get('prohibited_actions')} |",
        '',
        '## Baseball data effects (all must be zero)',
        '',
        '| counter | value |',
        '| :--- | ---: |',
    ]
    for field in qualification.BASEBALL_DATA_EFFECT_FIELDS:
        lines.append(f'| `{field}` | {baseball.get(field)} |')

    lines += [
        '',
        '## Lane completion ledger (not baseball data)',
        '',
        execution.get('lane_bookkeeping_note', ''),
        '',
        '| counter | value | expected |',
        '| :--- | ---: | ---: |',
    ]
    for field in qualification.LANE_BOOKKEEPING_EFFECT_FIELDS:
        lines.append(
            f'| `{field}` | {bookkeeping.get(field)} | '
            f'{(execution.get("lane_bookkeeping_expected_delta") or {}).get(field)} |'
        )

    lines += [
        '',
        '### Governed ledger delta',
        '',
        '| check | value |',
        '| :--- | :--- |',
        f"| target work item present before | "
        f"{execution.get('target_work_item_present_before')} |",
        f"| target work item present after | "
        f"{execution.get('target_work_item_present_after')} |",
        f"| changed fields | "
        f"{execution.get('lane_bookkeeping_changed_fields')} |",
        f"| unexpected changed fields | "
        f"{execution.get('lane_bookkeeping_unexpected_changed_fields')} |",
        f"| delta matches expected | "
        f"{execution.get('lane_bookkeeping_delta_match')} |",
        f"| unrelated work items | "
        f"{execution.get('unrelated_work_item_count')} |",
        f"| unrelated work-items digest before | "
        f"`{execution.get('unrelated_work_items_digest_before')}` |",
        f"| unrelated work-items digest after | "
        f"`{execution.get('unrelated_work_items_digest_after')}` |",
        f"| unrelated checkpoints digest before | "
        f"`{execution.get('unrelated_checkpoints_digest_before')}` |",
        f"| unrelated checkpoints digest after | "
        f"`{execution.get('unrelated_checkpoints_digest_after')}` |",
        f"| unrelated bookkeeping unchanged | "
        f"{execution.get('unrelated_bookkeeping_unchanged')} |",
        '',
        '### Writer guard',
        '',
        '| check | value |',
        '| :--- | :--- |',
        f"| acquired | {execution.get('writer_guard_acquired')} |",
        f"| release attempted | "
        f"{execution.get('writer_guard_release_attempted')} |",
        f"| released | {execution.get('writer_guard_released')} |",
    ]

    post = document['post_execution']
    lines += [
        '',
        '## Before / after state',
        '',
        '| check | value |',
        '| :--- | :--- |',
        f"| pre-execution readback | "
        f"{document['pre_execution'].get('readback_available')} |",
        f"| post-execution readback | {post.get('readback_available')} |",
        f"| state digest match | {post.get('state_digest_match')} |",
        f"| already matching rows | {post.get('already_matching_rows')} |",
        f"| divergent rows | {post.get('divergent_rows')} |",
        f"| missing rows | {post.get('missing_rows')} |",
        f"| duplicate rows | {post.get('duplicate_rows')} |",
        f"| unresolved rows | {post.get('unresolved_rows')} |",
        '',
        '## Authority state (unchanged by this run)',
        '',
        f"- writes enabled for this execution only: "
        f"{execution.get('writes_enabled')}",
        f"- publication authoritative: "
        f"{execution.get('publication_authoritative')}",
        '- backfill: off',
        '- daily and postgame lanes: shadow',
        '- legacy sync writer: still production-authoritative',
        '',
    ]

    if verdict['failed_reasons']:
        lines += ['## Failed reasons', '']
        lines += [f'- `{reason}`' for reason in verdict['failed_reasons']]
        lines.append('')
    if verdict['unproven_reasons']:
        lines += ['## Unproven reasons', '']
        lines += [f'- `{reason}`' for reason in verdict['unproven_reasons']]
        lines.append('')

    lines += ['---', '', verdict['non_authorization_statement'], '']
    return '\n'.join(lines)


def write_artifacts(document, artifact_dir) -> dict:
    """Write the evidence artifact. Failure to write is UNPROVEN, never PASS."""
    target = Path(artifact_dir)
    target.mkdir(parents=True, exist_ok=True)

    encoded = json.dumps(document, indent=2, sort_keys=True, default=str)
    (target / SUMMARY_JSON).write_text(encoded + '\n', encoding='utf-8')
    (target / SUMMARY_MARKDOWN).write_text(
        render_markdown(document), encoding='utf-8',
    )
    metadata = {
        'schema_version': qualification.SCHEMA_VERSION,
        'qualification_type': qualification.QUALIFICATION_TYPE,
        'result': document['verdict']['result'],
        'exit_code': document['verdict']['exit_code'],
        'requested_game_pk': document['identity'].get('requested_game_pk'),
        'commit_sha': document['identity'].get('commit_sha'),
        'workflow_run_id': document['identity'].get('workflow_run_id'),
        'summary_filename': SUMMARY_JSON,
        'markdown_filename': SUMMARY_MARKDOWN,
        'non_authorization_statement': (
            qualification.NON_AUTHORIZATION_STATEMENT
        ),
    }
    (target / METADATA_JSON).write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + '\n', encoding='utf-8',
    )
    return metadata


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        document = run(args)
    except Exception:  # noqa: BLE001 - never leak exception text
        document = _refused(
            event_context(args), game_pk=None,
            note=qualification.sanitize_note(args.operator_note),
            unproven=[qualification.UNPROVEN_LANE_ERROR],
        )

    try:
        write_artifacts(document, args.artifact_dir)
    except Exception:  # noqa: BLE001 - an unwritable artifact is UNPROVEN
        document['verdict']['unproven_reasons'] = sorted(set(
            list(document['verdict']['unproven_reasons'])
            + [qualification.UNPROVEN_ARTIFACT_BUILD_FAILED]
        ))
        if document['verdict']['result'] == qualification.RESULT_PASS:
            document['verdict']['result'] = qualification.RESULT_UNPROVEN
            document['verdict']['exit_code'] = qualification.EXIT_UNPROVEN

    print(json.dumps(document, indent=2, sort_keys=True, default=str))
    return int(document['verdict']['exit_code'])


if __name__ == '__main__':
    # Never let a stray auto-sync start from an operator invocation.
    os.environ.setdefault('AUTO_SYNC', 'false')
    raise SystemExit(main())
