#!/usr/bin/env python
"""Manual exact-scope real-mutation qualification.

Proves the game-driven ingestion lane can apply ONE reviewed canonical
statistical correction to ONE existing GameLog row in ONE completed game, and
change nothing else.

    python scripts/run_game_driven_real_mutation_qualification.py \
        --game-pk 824969 \
        --expected-head-sha <40 hex> \
        --reviewed-plan-fingerprint <64 hex> \
        --confirmation QUALIFY_REAL_MUTATION_GAME_824969 \
        --artifact-dir artifacts/manual-real-mutation-qualification

Manual only. This script is invoked by one workflow that has only
``workflow_dispatch``, and it re-validates every authorization condition itself
rather than trusting the workflow's gates — a guard that trusts its caller is
not a guard.

Sequence:

    authorize (no database, no network)
      -> application context
      -> production writer guard (the same advisory lock the public sync uses)
      -> work-item precondition: exists AND already completed
      -> SHADOW phase, exclusive to the requested game, reads only
      -> refuse unless the plan is exactly one reviewed statistical correction
      -> refuse unless the operator's reviewed fingerprint is this plan
      -> NO_LONGER_MUTATING when the correction is already applied
      -> pre-execution canonical readback of the target row and its siblings
      -> WRITE phase, exclusive, authorized by the reviewed fingerprint
      -> post-execution readback, realization proof, bookkeeping proof
      -> verdict, evidence artifact, non-zero exit for anything but PASS

Exit codes: 0 PASS, 1 FAILED, 2 UNPROVEN, 3 NO_LONGER_MUTATING.

Post-write failure policy: fail hard, preserve evidence, no automatic
compensating write. If the mutation commits and realization is wrong, the
verdict is FAILED and the artifact records everything needed to act on it. This
script never issues a second write, and it is not a rollback tool.

Output carries counts, digests, fingerprints, safe reason codes, governed field
NAMES and governed baseball integers only — never credentials, connection
strings, headers, raw payloads, filesystem paths, or exception text.
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

from services import real_mutation_qualification as qualification  # noqa: E402


SUMMARY_JSON = 'qualification-summary.json'
SUMMARY_MARKDOWN = 'qualification-summary.md'
METADATA_JSON = 'qualification-metadata.json'


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Manual exact-scope real-mutation qualification.',
    )
    parser.add_argument('--game-pk', required=True)
    parser.add_argument('--expected-head-sha', required=True)
    parser.add_argument('--reviewed-plan-fingerprint', required=True)
    parser.add_argument('--confirmation', required=True)
    parser.add_argument('--operator-note', default='')
    parser.add_argument(
        '--artifact-dir',
        default='artifacts/manual-real-mutation-qualification',
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


def _identity_block(context, *, game_pk, note, reviewed_fingerprint) -> dict:
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
        'reviewed_plan_fingerprint': reviewed_fingerprint,
        'operator_note': note,
    }


def build_app():
    import app as app_module

    return app_module.create_app()


def resolve_reference_date(raw):
    if raw:
        return date.fromisoformat(str(raw).strip())
    return datetime.now(timezone.utc).date()


class _PreflightRefusal(Exception):
    """Internal control flow: refuse before the write phase is entered."""


def run(args) -> dict:
    """Execute the qualification and return its full evidence document."""
    context = event_context(args)
    note = qualification.sanitize_note(args.operator_note)

    # ── Input parsing, before anything is initialised ────────────────────────
    try:
        game_pk = qualification.parse_game_pk(args.game_pk)
    except qualification.QualificationInputError as exc:
        return _refused(context, game_pk=None, note=note, failed=[exc.reason])

    try:
        reviewed_fingerprint = qualification.parse_reviewed_fingerprint(
            args.reviewed_plan_fingerprint
        )
    except qualification.QualificationInputError as exc:
        return _refused(
            context, game_pk=game_pk, note=note, failed=[exc.reason],
        )

    identity = _identity_block(
        context, game_pk=game_pk, note=note,
        reviewed_fingerprint=reviewed_fingerprint,
    )

    # ── Authorization, before any database or network access ────────────────
    authorization_failures = qualification.validate_authorization(
        context, game_pk=game_pk,
    )
    if authorization_failures:
        return _refused(
            context, game_pk=game_pk, note=note,
            failed=authorization_failures,
            reviewed_fingerprint=reviewed_fingerprint,
        )

    reference_date = resolve_reference_date(args.reference_date)

    flask_app = build_app()
    from services import game_driven_ingestion as lane
    from services import game_driven_realization as realization_service
    from services import sync_metadata
    from utils.db import db

    with flask_app.app_context():
        # Writer-guard state is tracked, never assumed. The evidence document is
        # built only AFTER the release attempt, so the artifact can never claim
        # a release that did not happen.
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
                reviewed_fingerprint=reviewed_fingerprint,
            )

        collected: dict = {'write_phase_entered': False}
        try:
            # ── WORK-ITEM PRECONDITION, BEFORE ANYTHING ELSE ─────────────────
            # A qualification for a game with no durable completed work item
            # cannot succeed, so running the shadow lane first would spend an
            # MLB request and a full canonical planning pass to reach a refusal
            # that was already decided.
            bookkeeping_before = qualification.read_lane_bookkeeping(game_pk)
            collected['bookkeeping_before'] = bookkeeping_before
            collected['work_item_precondition_checked'] = (
                bookkeeping_before is not None
            )
            target_before = (bookkeeping_before or {}).get('target') or {}
            collected['target_work_item_present'] = bool(
                bookkeeping_before and bookkeeping_before.get('target_present')
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
            candidate = qualification.evaluate_candidate_plan(
                shadow_report, game_pk=game_pk,
            )
            collected['shadow_candidate'] = candidate
            fingerprint = shadow_report.get('reconciliation_plan_fingerprint')

            preflight_failed: list[str] = []
            preflight_unproven: list[str] = []

            if not candidate['planned_row_count']:
                preflight_unproven.append(
                    qualification.UNPROVEN_SHADOW_PHASE_UNUSABLE
                )

            shadow_scope = qualification.evaluate_scope(
                shadow_report, game_pk=game_pk,
            )
            collected['shadow_scope'] = shadow_scope
            if not shadow_scope['execution_scope_exact_match']:
                preflight_failed.append(qualification.FAILED_SCOPE_NOT_EXACT)
            if shadow_scope['planned_game_count'] != 1:
                preflight_failed.append(
                    qualification.FAILED_GAME_NOT_PLANNABLE
                    if shadow_scope['planned_game_count'] == 0
                    else qualification.FAILED_PLANNED_COUNT_NOT_ONE
                )
            if not fingerprint:
                preflight_unproven.append(
                    qualification.UNPROVEN_PLAN_FINGERPRINT_MISSING
                )

            # ── REPLAY GUARD, before anything can write ──────────────────────
            # The plan this run computed contains no correction. Either a prior
            # qualification already applied it, the legacy writer corrected the
            # row first, or the source revised. None of those is a real-mutation
            # proof, and none of them is a failure.
            if (
                candidate['planned_row_count']
                and not candidate['mutation_present']
                and not preflight_failed
            ):
                collected['preflight_failed'] = []
                collected['preflight_unproven'] = preflight_unproven
                collected['no_longer_mutating'] = True
                raise _PreflightRefusal()

            # ── Candidate contract, before anything can write ────────────────
            preflight_failed.extend(candidate['failed_reasons'])

            # The operator reviewed a specific plan. If this run's shadow plan
            # is a different plan, the human authorized something else — refuse
            # rather than write the plan they did not see.
            if fingerprint and fingerprint != reviewed_fingerprint:
                preflight_failed.append(
                    qualification.FAILED_REVIEWED_FINGERPRINT_MISMATCH
                )

            if preflight_failed or preflight_unproven:
                collected['preflight_failed'] = preflight_failed
                collected['preflight_unproven'] = preflight_unproven
                raise _PreflightRefusal()

            reviewed = candidate['reviewed_mutation']
            collected['reviewed_mutation'] = reviewed

            # ── Pre-execution canonical readback ─────────────────────────────
            collected['before_state'] = qualification.read_target_row_state(
                game_pk=game_pk,
                pitcher_mlb_id=reviewed['pitcher_mlb_id'],
                reviewed_field=reviewed['field'],
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

            # ── Post-execution readback and proofs ───────────────────────────
            collected['after_state'] = qualification.read_target_row_state(
                game_pk=game_pk,
                pitcher_mlb_id=reviewed['pitcher_mlb_id'],
                reviewed_field=reviewed['field'],
            )
            collected['realized_digest'] = (
                qualification.realized_target_digest(
                    game_pk=game_pk,
                    pitcher_mlb_id=reviewed['pitcher_mlb_id'],
                    target_fields=reviewed['target_fields'],
                )
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
            # path reaches here, and a refusal that leaves an open transaction
            # keeps table locks held for as long as the session lives.
            try:
                db.session.rollback()
            except Exception:  # noqa: BLE001
                pass
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
            reviewed_fingerprint=reviewed_fingerprint,
        )

    if 'preflight_failed' in collected:
        decision = qualification.decide({
            'failed_reasons': collected['preflight_failed'],
            'unproven_reasons': (
                list(collected['preflight_unproven'])
                + _guard_reasons(guard_state)
            ),
            'no_longer_mutating': collected.get('no_longer_mutating', False),
        })
        decision['writer_guard'] = dict(guard_state)
        decision['shadow_candidate'] = collected.get('shadow_candidate')
        decision['shadow_scope'] = collected.get('shadow_scope')
        decision['reviewed_mutation'] = (
            collected.get('shadow_candidate') or {}
        ).get('reviewed_mutation')
        decision['field_authority'] = (
            collected.get('shadow_candidate') or {}
        ).get('field_authority')
        decision['shadow_plan_fingerprint'] = (
            collected.get('shadow_report') or {}
        ).get('reconciliation_plan_fingerprint')
        decision['reviewed_plan_fingerprint'] = reviewed_fingerprint
        return _document(
            identity=identity,
            decision=decision,
            shadow_report=collected.get('shadow_report'),
            write_report=None,
            realization=None,
            reference_date=reference_date,
            write_phase_entered=False,
            execution_state=_state_from(collected, game_pk),
        )

    decision = qualification.assess(
        context=context,
        game_pk=game_pk,
        reviewed_fingerprint=reviewed_fingerprint,
        shadow_report=collected.get('shadow_report'),
        write_report=collected.get('write_report'),
        before_state=collected.get('before_state'),
        after_state=collected.get('after_state'),
        realized_digest=collected.get('realized_digest'),
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


def _guard_reasons(guard_state) -> list[str]:
    if not guard_state.get('acquired'):
        return [qualification.UNPROVEN_WRITER_GUARD_UNAVAILABLE]
    if not (
        guard_state.get('release_attempted') and guard_state.get('released')
    ):
        return [qualification.UNPROVEN_WRITER_GUARD_RELEASE_UNPROVEN]
    return []


def _refused(context, *, game_pk, note, failed=(), unproven=(),
             writer_guard=None, reviewed_fingerprint=None) -> dict:
    decision = qualification.decide({
        'failed_reasons': list(failed),
        'unproven_reasons': list(unproven),
        'no_longer_mutating': False,
    })
    decision['writer_guard'] = dict(writer_guard or {
        'acquired': False, 'release_attempted': False, 'released': False,
    })
    decision['reviewed_plan_fingerprint'] = reviewed_fingerprint
    return _document(
        identity=_identity_block(
            context, game_pk=game_pk, note=note,
            reviewed_fingerprint=reviewed_fingerprint,
        ),
        decision=decision,
        shadow_report=None,
        write_report=None,
        realization=None,
        reference_date=None,
        write_phase_entered=False,
    )


def _document(*, identity, decision, shadow_report, write_report, realization,
              reference_date, write_phase_entered, execution_state=None) -> dict:
    state = execution_state or qualification.execution_state()
    shadow_report = shadow_report or {}
    write_report = write_report or {}
    effects = decision.get('execution_effects') or (
        qualification.split_execution_effects(write_report)
    )
    guard_state = decision.get('writer_guard') or {}
    bookkeeping = decision.get('lane_bookkeeping') or {}
    integrity = decision.get('integrity') or {}
    reviewed = decision.get('reviewed_mutation')

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
            'reviewed_plan_fingerprint_valid': (
                qualification.FAILED_REVIEWED_FINGERPRINT_MALFORMED
                not in decision['failed_reasons']
            ),
            'reference_date': (
                reference_date.isoformat() if reference_date else None
            ),
        },
        'game_authority': {
            'source_authority_planner': 'game_ingestion_planner.plan_game_work',
            'work_item_precondition_checked': state[
                'work_item_precondition_checked'
            ],
            'work_item_precondition_passed': state[
                'work_item_precondition_passed'
            ],
            'required_work_item_status_before': (
                qualification.REQUIRED_WORK_ITEM_STATUS_BEFORE
            ),
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
        'reviewed_plan': {
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
            'operator_reviewed_fingerprint': decision.get(
                'reviewed_plan_fingerprint'
            ),
            'plan_fingerprint_before_execution': decision.get(
                'shadow_plan_fingerprint'
            ),
            'plan_fingerprint_authorized_at_execution': decision.get(
                'authorized_plan_fingerprint'
            ),
            'plan_fingerprint_match': decision.get('plan_fingerprint_match'),
            'reviewed_plan_fingerprint_match': decision.get(
                'reviewed_plan_fingerprint_match'
            ),
            'reviewed_mutation': reviewed,
            'field_authority': decision.get('field_authority'),
            'shadow_candidate': decision.get('shadow_candidate'),
            'write_candidate': decision.get('write_candidate'),
            'scope': decision.get('scope'),
            'shadow_scope': decision.get('shadow_scope'),
        },
        'execution': {
            'write_phase_entered': write_phase_entered,
            'mode': write_report.get('mode'),
            'writes_enabled': effects.get('writes_enabled'),
            'publication_authoritative': effects.get(
                'publication_authoritative'
            ),
            'backfill_included': False,
            'expected_baseball_data_effects': effects.get(
                'expected_baseball_data'
            ),
            'baseball_data_effects': effects.get('baseball_data'),
            'unexpected_baseball_data_effects': effects.get(
                'unexpected_baseball_data'
            ),
            'baseball_data_matches_expected': effects.get(
                'baseball_data_matches_expected'
            ),
            'lane_bookkeeping_effects': effects.get('lane_bookkeeping'),
            'transaction_boundary_entered': effects.get(
                'transaction_boundary_entered'
            ),
            'lane_status': write_report.get('status'),
            'writer_guard': 'sync_metadata.acquire_sync_writer_guard',
            'writer_guard_acquired': bool(guard_state.get('acquired')),
            'writer_guard_release_attempted': bool(
                guard_state.get('release_attempted')
            ),
            'writer_guard_released': bool(guard_state.get('released')),
            'elapsed_seconds': write_report.get('elapsed_seconds'),
        },
        'integrity': {
            'target_row_before': integrity.get('target_row_before'),
            'target_row_after': integrity.get('target_row_after'),
            'expected_target_state_digest': integrity.get(
                'expected_target_state_digest'
            ),
            'observed_target_state_digest': integrity.get(
                'observed_target_state_digest'
            ),
            'target_reached_canonical_value': integrity.get(
                'target_reached_canonical_value'
            ),
            'target_row_digest_before': integrity.get(
                'target_row_digest_before'
            ),
            'target_row_digest_after': integrity.get('target_row_digest_after'),
            'target_unreviewed_fields_unchanged': integrity.get(
                'target_unreviewed_fields_unchanged'
            ),
            'other_rows_digest_before': integrity.get(
                'other_rows_digest_before'
            ),
            'other_rows_digest_after': integrity.get('other_rows_digest_after'),
            'other_rows_unchanged': integrity.get('other_rows_unchanged'),
            'realization': _safe_realization(realization),
        },
        'bookkeeping': {
            'lane_bookkeeping_before': bookkeeping.get(
                'lane_bookkeeping_before'
            ),
            'lane_bookkeeping_after': bookkeeping.get('lane_bookkeeping_after'),
            'lane_bookkeeping_changed_fields': bookkeeping.get(
                'lane_bookkeeping_changed_fields'
            ),
            'lane_bookkeeping_allowed_changed_fields': bookkeeping.get(
                'lane_bookkeeping_allowed_changed_fields'
            ),
            'lane_bookkeeping_unexpected_changed_fields': bookkeeping.get(
                'lane_bookkeeping_unexpected_changed_fields'
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
            'expected_correction_count_delta': bookkeeping.get(
                'expected_correction_count_delta'
            ),
            'observed_correction_count_delta': bookkeeping.get(
                'observed_correction_count_delta'
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
            'unrelated_work_item_count': bookkeeping.get(
                'unrelated_work_item_count'
            ),
            'unrelated_bookkeeping_unchanged': bookkeeping.get(
                'unrelated_bookkeeping_unchanged'
            ),
            'target_work_item_present_before': bookkeeping.get(
                'target_work_item_present_before'
            ),
            'target_work_item_present_after': bookkeeping.get(
                'target_work_item_present_after'
            ),
        },
        'verdict': {
            'result': decision['result'],
            'exit_code': decision['exit_code'],
            'failed_reasons': decision['failed_reasons'],
            'unproven_reasons': decision['unproven_reasons'],
            'no_longer_mutating': decision.get('no_longer_mutating', False),
            'explanation': _explain(decision),
            'non_authorization_statement': (
                qualification.NON_AUTHORIZATION_STATEMENT
            ),
        },
    }


def _safe_realization(realization) -> dict:
    """Counts and flags only. The per-row detail stays out of the artifact."""
    realization = realization or {}
    return {
        'available': bool(realization),
        'applicable': realization.get('applicable'),
        'projected_rows': realization.get('projected_rows'),
        'projected_updates': realization.get('projected_updates'),
        'realized_rows': realization.get('realized_rows'),
        'already_matching_rows': realization.get('already_matching_rows'),
        'missing_rows': realization.get('missing_rows'),
        'divergent_rows': realization.get('divergent_rows'),
        'duplicate_rows': realization.get('duplicate_rows'),
        'unresolved_rows': realization.get('unresolved_rows'),
        'prohibited_identity_actions': realization.get(
            'prohibited_identity_actions'
        ),
        'source_revision_match': realization.get('source_revision_match'),
        'all_projected_targets_realized': realization.get(
            'all_projected_targets_realized'
        ),
    }


def _explain(decision) -> str:
    result = decision['result']
    if result == qualification.RESULT_PASS:
        return (
            'The lane applied exactly the reviewed canonical correction to one '
            'existing row in one completed game. The target reached the exact '
            'value the reviewed plan intended, every other governed field on '
            'that row and every other row in the game read back identical, and '
            'no prohibited effect occurred. The lane advanced its own '
            'completion ledger, which is reported separately and is not '
            'baseball data.'
        )
    if result == qualification.RESULT_NO_LONGER_MUTATING:
        return (
            'The reviewed correction is already applied, so this run had '
            'nothing to mutate and mutated nothing. This is not a '
            'real-mutation proof and must never be recorded as one.'
        )
    if result == qualification.RESULT_FAILED:
        return (
            'A governed contract condition was violated. The evidence is '
            'preserved as observed. No compensating write was attempted: any '
            'correction from here uses the canonical governed correction path.'
        )
    return (
        'Trustworthy proof could not be completed. The verdict is UNPROVEN '
        'rather than PASS, and no claim is made about what the lane did.'
    )


def render_markdown(document) -> str:
    identity = document['identity']
    verdict = document['verdict']
    execution = document['execution']
    reviewed = (document['reviewed_plan'] or {}).get('reviewed_mutation') or {}
    integrity = document['integrity']
    bookkeeping = document['bookkeeping']

    lines = [
        '# Manual real-mutation write qualification',
        '',
        f"**Verdict: {verdict['result']}**",
        '',
        '| field | value |',
        '| :--- | :--- |',
        f"| qualification type | `{identity['qualification_type']}` |",
        f"| requested game | {identity.get('requested_game_pk')} |",
        f"| commit | `{identity.get('commit_sha')}` |",
        f"| reviewed field | `{reviewed.get('field')}` |",
        f"| reviewed pitcher | {reviewed.get('pitcher_mlb_id')} |",
        f"| writes enabled | {execution.get('writes_enabled')} |",
        f"| publication authoritative | "
        f"{execution.get('publication_authoritative')} |",
        f"| baseball effects as expected | "
        f"{execution.get('baseball_data_matches_expected')} |",
        f"| target reached canonical value | "
        f"{integrity.get('target_reached_canonical_value')} |",
        f"| other rows unchanged | {integrity.get('other_rows_unchanged')} |",
        f"| correction count delta | "
        f"{bookkeeping.get('observed_correction_count_delta')} |",
        '',
        '**Baseball data effects**',
        '',
        '| counter | expected | observed |',
        '| :--- | ---: | ---: |',
    ]
    expected = execution.get('expected_baseball_data_effects') or {}
    observed = execution.get('baseball_data_effects') or {}
    for key in sorted(expected):
        lines.append(f'| `{key}` | {expected[key]} | {observed.get(key)} |')

    lines.extend([
        '',
        '**Lane completion ledger (not baseball data)**',
        '',
        '| counter | value |',
        '| :--- | ---: |',
    ])
    for key in sorted(execution.get('lane_bookkeeping_effects') or {}):
        lines.append(
            f"| `{key}` | {execution['lane_bookkeeping_effects'][key]} |"
        )

    for reason in verdict['failed_reasons']:
        lines.append(f'\n- FAILED: `{reason}`')
    for reason in verdict['unproven_reasons']:
        lines.append(f'\n- UNPROVEN: `{reason}`')

    lines.extend(['', verdict['non_authorization_statement'], ''])
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
