#!/usr/bin/env python
"""Exact-scope checkpoint repair for MLB game 824487's source revision.

    python scripts/run_game_source_revision_checkpoint_repair.py \
        --operation verify \
        --expected-main-sha <40 hex> \
        --confirmation VERIFY_GAME_824487_SOURCE_REVISION_CHECKPOINT \
        --artifact-dir ../artifacts/game-824487-checkpoint-repair

Two operations and no others:

``verify``  Read-only. Re-observes every precondition live and reports whether
            the single approved change is currently required and currently
            safe. Writes nothing, ever, under any outcome.
``apply``   Performs the ONE approved change — and only after re-observing
            every precondition again against a row it holds a lock on.

Both operations are manual-dispatch only, and each carries its own
confirmation phrase, so a confirmation reviewed for a verify run cannot start
an apply run.

This runner OBSERVES; ``services.game_source_revision_checkpoint_repair``
JUDGES. Every observation comes from the merged audit's own observation
functions, which call the canonical planner, the canonical MLB client, the
canonical box-score parser, the canonical appearance extractor, and the
canonical reconciliation planner. Nothing here is a second pipeline.

Exit codes, three and only three: 0 verified / not required / applied,
1 FAILED (this package broke its own contract), 2 NOT ELIGIBLE — either
UNPROVEN (required evidence unavailable) or REPAIR_REFUSED (a precondition was
positively observed not to hold, which is a correct and safe outcome). A
refused run is not eligible to proceed, so anything reading only the exit code
must treat it exactly as it treats UNPROVEN; the distinction is preserved in
the result name and the reason codes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import sqlalchemy as sa


BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

REPO_ROOT = BACKEND_ROOT.parent

from services import game_source_revision_audit as audit  # noqa: E402
from services import (  # noqa: E402
    game_source_revision_checkpoint_repair as repair,
)
# The merged audit's observation functions, reused verbatim rather than
# reimplemented. They are covered by the audit's own PostgreSQL suite, and a
# second copy of them would be a second answer to the same question.
from scripts import (  # noqa: E402
    run_game_source_revision_audit as audit_runner,
)


_STEM = 'game-824487-source-revision-checkpoint-repair'

SUMMARY_JSON = f'{_STEM}.json'
SUMMARY_MARKDOWN = f'{_STEM}-summary.md'
PROOF_JSON = f'{_STEM}-proof.json'
PRECONDITIONS_JSON = f'{_STEM}-preconditions.json'
FINGERPRINTS_JSON = f'{_STEM}-fingerprints.json'
MUTATION_LEDGER_JSON = f'{_STEM}-mutation-ledger.json'
COMPARISON_JSON = f'{_STEM}-field-comparison.json'

ARTIFACT_FILES = (
    SUMMARY_JSON, SUMMARY_MARKDOWN, PROOF_JSON, PRECONDITIONS_JSON,
    FINGERPRINTS_JSON, MUTATION_LEDGER_JSON, COMPARISON_JSON,
)

MAX_NOTE_LENGTH = 200


class _Halt(Exception):
    """Stop collecting. The verdict is decided from what was proven."""


# ── Authorization ───────────────────────────────────────────────────────────

def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Exact-scope source-revision checkpoint repair.',
    )
    parser.add_argument(
        '--operation', required=True, choices=list(repair.OPERATIONS),
    )
    parser.add_argument('--expected-main-sha', required=True)
    parser.add_argument('--confirmation', required=True)
    parser.add_argument('--operator-note', default='')
    parser.add_argument('--artifact-dir', required=True)
    return parser.parse_args(argv)


def sanitize_note(raw) -> str:
    """Bounded, printable, never interpreted, never decision-relevant."""
    text = str(raw or '')
    safe = ''.join(
        char for char in text if char.isprintable() and char not in '`$\\'
    )
    return safe[:MAX_NOTE_LENGTH]


def event_context(args, environ=None) -> dict:
    import os

    environ = os.environ if environ is None else environ
    return {
        'event_name': environ.get('GITHUB_EVENT_NAME'),
        'repository': environ.get('GITHUB_REPOSITORY'),
        'actor': environ.get('GITHUB_ACTOR'),
        'ref': environ.get('GITHUB_REF'),
        'commit_sha': environ.get('GITHUB_SHA'),
        'workflow_run_id': environ.get('GITHUB_RUN_ID'),
        'workflow_run_attempt': environ.get('GITHUB_RUN_ATTEMPT'),
        'workflow': environ.get('GITHUB_WORKFLOW'),
        'operation': str(args.operation or ''),
        'expected_main_sha': str(args.expected_main_sha or '').strip().lower(),
        'confirmation_supplied': bool(args.confirmation),
    }


def validate_authorization(context, args) -> list[str]:
    """Every precondition, checked positively. Absence is never approval."""
    failures: list[str] = []
    if context.get('event_name') != repair.REQUIRED_EVENT_NAME:
        failures.append(repair.FAILED_EVENT_NOT_WORKFLOW_DISPATCH)
    if context.get('repository') != repair.REQUIRED_REPOSITORY:
        failures.append(repair.FAILED_REPOSITORY_NOT_AUTHORIZED)
    if context.get('actor') != repair.REQUIRED_ACTOR:
        failures.append(repair.FAILED_ACTOR_NOT_AUTHORIZED)
    if context.get('ref') != repair.REQUIRED_REF:
        failures.append(repair.FAILED_REF_NOT_MAIN)

    expected = audit.normalize_sha(context.get('expected_main_sha'))
    if expected is None:
        failures.append(repair.FAILED_EXPECTED_SHA_MALFORMED)
    else:
        resolved = audit.normalize_sha(context.get('commit_sha'))
        if resolved is None or resolved != expected:
            failures.append(repair.FAILED_EXPECTED_SHA_MISMATCH)

    operation = str(args.operation or '')
    if operation not in repair.OPERATIONS:
        failures.append(repair.FAILED_OPERATION_UNKNOWN)
        # An unknown operation has no confirmation to compare against. Falling
        # through to a default phrase would let a typo authorize something.
        failures.append(repair.FAILED_CONFIRMATION_MISMATCH)
        return failures

    # The phrase is matched against THIS operation's phrase only. A verify
    # confirmation can never satisfy an apply run.
    if str(args.confirmation or '') != repair.CONFIRMATIONS[operation]:
        failures.append(repair.FAILED_CONFIRMATION_MISMATCH)
    return failures


def build_app():
    from app import create_app

    return create_app()


# ── Target-row observation ──────────────────────────────────────────────────

def observe_target_row(session=None) -> dict:
    """The single checkpoint row, counted before it is read.

    Counting first matters: ``.first()`` on a two-row result silently picks
    one, and "which one did it pick" is exactly the question a repair must
    never have to ask.
    """
    from models.game_ingestion_work_item import GameIngestionWorkItem

    rows = GameIngestionWorkItem.query.filter(
        GameIngestionWorkItem.mlb_game_pk == repair.GAME_PK
    ).order_by(GameIngestionWorkItem.id.asc()).all()

    row = rows[0] if len(rows) == 1 else None
    return {
        'observed': True,
        'candidate_row_count': len(rows),
        'candidate_row_ids': [item.id for item in rows],
        'work_item': repair.row_snapshot(row) if row is not None else None,
        'work_item_row_id': getattr(row, 'id', None),
    }


# ── The apply transaction ───────────────────────────────────────────────────

def set_post_commit_read_only(session) -> bool:
    """Set the post-commit verification transaction read-only.

    Extracted so the failure path is reachable in a test. A verification pass
    that cannot be proven read-only is not a verification pass this package is
    entitled to rely on.

    A post-commit read-only setup failure is a package CONTRACT failure. The
    durable commit remains disclosed in full, all governed post-commit
    observation stops — the target-row re-read, the scoped fingerprints, and
    the out-of-scope digest alike — and the run returns FAILED at exit 1.
    """
    try:
        session.execute(sa.text('SET TRANSACTION READ ONLY'))
        return True
    except Exception:  # noqa: BLE001 - never leak the database message
        return False


def new_apply_state() -> dict:
    """The apply lifecycle, fully initialised before anything can return.

    Owned by the CALLER and passed in, so an exception escaping anywhere
    leaves the caller holding the same object with whatever was truthfully
    established — rather than a generic replacement that erases it.
    """
    return {
        'attempted': False,
        'row_locked': False,
        'lock_available': None,
        'revalidated': None,
        'revalidation_reason': None,
        'committed': None,
        'commit_attempted': False,
        'commit_count': 0,
        'before_snapshot': None,
        'after_snapshot': None,
        'in_transaction_value': None,
        'in_transaction_value_is_intended': None,
        'guard_observations': None,
        'guard_checks': None,
        'statements': None,
        'affected_row_count': None,
        # ── Post-commit lifecycle, explicit and initialised up front ───────
        'post_commit_verification_attempted': False,
        'post_commit_read_only_attempted': False,
        'post_commit_transaction_read_only': None,
        'post_commit_read_only_reason': None,
        'post_commit_verification_completed': False,
        'post_commit_verification_transaction_rollback_succeeded': None,
        'post_commit_row_count': None,
        'post_commit_value_is_intended': None,
        'failed_reasons': [],
        'unproven_reasons': [],
        'refusal_reasons': [],
    }


def apply_repair(*, target_row_id, observed_snapshot, state=None) -> dict:
    """Perform the ONE approved change, inside its own writable transaction.

    Called only after every precondition has already been satisfied against a
    read-only observation. It re-checks the row-level preconditions AGAIN here,
    against a row it holds a ``FOR UPDATE`` lock on, because the read-only
    observation and this transaction are not the same instant and a checkpoint
    that moved in between is a different row than the one that was approved.
    """
    from models.game_ingestion_work_item import GameIngestionWorkItem
    from utils.db import db

    state = new_apply_state() if state is None else state

    # A fresh transaction. The read-only one this run has been using is over.
    db.session.rollback()

    try:
        locked_rows = GameIngestionWorkItem.query.filter(
            GameIngestionWorkItem.mlb_game_pk == repair.GAME_PK
        ).with_for_update(nowait=True).all()
        state['lock_available'] = True
    except Exception:  # noqa: BLE001 - never leak the database message
        db.session.rollback()
        state['lock_available'] = False
        state['unproven_reasons'].append(
            repair.UNPROVEN_TARGET_ROW_NOT_LOCKABLE
        )
        return state

    if len(locked_rows) != 1:
        db.session.rollback()
        state['revalidated'] = False
        state['revalidation_reason'] = (
            repair.REFUSED_WORK_ITEM_MULTIPLE if locked_rows
            else repair.REFUSED_WORK_ITEM_MISSING
        )
        state['refusal_reasons'].append(state['revalidation_reason'])
        return state

    row = locked_rows[0]
    state['row_locked'] = True
    before = repair.row_snapshot(row)
    state['before_snapshot'] = before

    # Re-validation against the LOCKED row. Every clause is a fact that could
    # have changed since the read-only pass, and each has its own reason code.
    if row.id != target_row_id:
        reason = repair.REFUSED_CONCURRENT_MODIFICATION
    elif before.get('mlb_game_pk') != repair.GAME_PK:
        reason = repair.REFUSED_WRONG_GAME
    elif before.get(repair.TARGET_COLUMN) == repair.INTENDED_SOURCE_REVISION:
        reason = repair.REFUSED_ALREADY_AT_INTENDED_REVISION
    elif before.get(repair.TARGET_COLUMN) != (
        repair.EXPECTED_EXISTING_SOURCE_REVISION
    ):
        reason = repair.REFUSED_EXISTING_REVISION_UNEXPECTED
    elif before.get('status') != repair.REQUIRED_WORK_ITEM_STATUS:
        reason = repair.REFUSED_STATUS_NOT_COMPLETED
    elif observed_snapshot and repair.changed_columns(
        observed_snapshot, before,
    ):
        # Anything at all moved on this row between the read-only observation
        # and this lock. The approved change was reviewed against the row as it
        # was observed, so a row that is no longer that row is refused.
        reason = repair.REFUSED_CONCURRENT_MODIFICATION
    else:
        reason = None

    if reason is not None:
        db.session.rollback()
        state['revalidated'] = False
        state['revalidation_reason'] = reason
        state['refusal_reasons'].append(reason)
        return state

    state['revalidated'] = True
    state['attempted'] = True

    watch = repair.StatementWatch(db.engine).attach()
    guard = repair.MutationScopeGuard(db.session).attach()
    try:
        # THE ONE PERMITTED MUTATION.
        setattr(row, repair.TARGET_COLUMN, repair.INTENDED_SOURCE_REVISION)
        db.session.flush()
        state['guard_observations'] = guard.as_dict()
        state['guard_checks'] = guard.checks(
            target_row_id=target_row_id, expect_mutation=True,
        )
        statements = watch.as_dict()
        state['statements'] = statements
        state['affected_row_count'] = (
            statements.get('target_table_affected_rows')
            if statements.get('target_table_rowcount_observed') else None
        )

        # The IN-TRANSACTION post-state, read back from the database inside
        # the open transaction rather than from the in-memory object. The
        # commit is conditioned on this: a transaction whose row does not
        # already show the intended value, with everything else on it
        # unchanged, is rolled back instead of committed.
        pending = db.session.execute(sa.text(
            'SELECT source_revision FROM game_ingestion_work_items '
            'WHERE id = :row_id'
        ), {'row_id': target_row_id}).scalar()
        state['in_transaction_value'] = pending
        state['in_transaction_value_is_intended'] = (
            pending == repair.INTENDED_SOURCE_REVISION
        )

        # A scope violation observed BEFORE the commit is rolled back rather
        # than committed and reported. This is the last point at which that is
        # still possible, so it is taken.
        checks = state['guard_checks'] or {}
        affected = state['affected_row_count']
        if affected == 0:
            # Zero rows under an exclusive lock this transaction just
            # re-validated against. The safe reading is that the row moved,
            # and a refusal never claims the repair was already applied
            # without a fresh read establishing it.
            db.session.rollback()
            state['committed'] = False
            state['refusal_reasons'].append(
                repair.REFUSED_MUTATION_ROW_COUNT_ZERO
            )
            return state
        if isinstance(affected, int) and affected > 1:
            # Structurally impossible under a UNIQUE constraint and a
            # primary-key predicate, and still guarded.
            db.session.rollback()
            state['committed'] = False
            state['failed_reasons'].append(
                repair.FAILED_MUTATION_ROW_COUNT_MULTIPLE
            )
            return state
        if not all((
            checks.get('no_object_was_created'),
            checks.get('no_object_was_deleted'),
            checks.get('exactly_the_expected_objects_mutated'),
            checks.get('only_the_target_type_mutated'),
            checks.get('only_governed_attributes_changed'),
            statements.get('exactly_one_target_update'),
            statements.get('no_other_write_statement'),
            affected == 1,
            state['in_transaction_value_is_intended'],
        )):
            db.session.rollback()
            state['committed'] = False
            state['failed_reasons'].append(
                repair.FAILED_MUTATION_SCOPE_EXCEEDED
            )
            return state

        state['commit_attempted'] = True
        db.session.commit()
        state['committed'] = True
        state['commit_count'] = 1
    except Exception:  # noqa: BLE001 - never leak the database message
        try:
            db.session.rollback()
        except Exception:  # noqa: BLE001
            pass
        if state.get('committed') is not True:
            # A COMMIT that was reached but did not return leaves the outcome
            # genuinely open — the server may have applied it. One that was
            # never reached leaves it definitively not done. Only the first
            # is "unknown", and only an unknown outcome may say so.
            state['committed'] = (
                None if state.get('commit_attempted') else False
            )
            state['unproven_reasons'].append(
                repair.UNPROVEN_APPLY_OUTCOME_UNKNOWN
            )
        return state
    finally:
        guard.detach()
        watch.detach()

    # ── Post-commit verification ────────────────────────────────────────────
    # The commit has landed and cannot be taken back. From here on, EVERY
    # failure is contained: nothing may escape this function and reach a
    # generic handler that would replace a known durable commit with "outcome
    # unknown". The committed facts recorded above are preserved on every
    # path out.
    state['post_commit_verification_attempted'] = True
    state['post_commit_read_only_attempted'] = True

    if not set_post_commit_read_only(db.session):
        # A failed statement leaves the PostgreSQL transaction ABORTED, so the
        # governed read below would raise rather than answer. It is not
        # attempted. The transaction is cleared so the session is usable
        # again — that rollback discards the failed VERIFICATION transaction
        # and does NOT and cannot reverse the committed repair.
        state['post_commit_transaction_read_only'] = False
        state['post_commit_read_only_reason'] = 'read_only_setup_failed'
        state['failed_reasons'].append(
            repair.FAILED_POST_COMMIT_READ_ONLY_PROOF
        )
        try:
            db.session.rollback()
            state[
                'post_commit_verification_transaction_rollback_succeeded'
            ] = True
        except Exception:  # noqa: BLE001 - never leak the database message
            state[
                'post_commit_verification_transaction_rollback_succeeded'
            ] = False
        state['post_commit_verification_completed'] = False
        # after_snapshot stays None: no governed post-commit read happened,
        # and the intended literal must never be passed off as an observation.
        return state

    state['post_commit_transaction_read_only'] = True
    state['post_commit_read_only_reason'] = 'established'

    try:
        db.session.expire_all()
        final = GameIngestionWorkItem.query.filter(
            GameIngestionWorkItem.mlb_game_pk == repair.GAME_PK
        ).all()
        state['after_snapshot'] = (
            repair.row_snapshot(final[0]) if len(final) == 1 else {}
        )
        state['post_commit_row_count'] = len(final)
        state['post_commit_value_is_intended'] = (
            (state['after_snapshot'] or {}).get(repair.TARGET_COLUMN)
            == repair.INTENDED_SOURCE_REVISION
        )
        state['post_commit_verification_completed'] = True
    except Exception:  # noqa: BLE001 - never leak the database message
        # The read-only transaction was established and the governed read
        # still failed. Contained here for the same reason as above.
        state['post_commit_verification_completed'] = False
        state['failed_reasons'].append(
            repair.FAILED_POST_COMMIT_VERIFICATION_INCOMPLETE
        )
        try:
            db.session.rollback()
            state[
                'post_commit_verification_transaction_rollback_succeeded'
            ] = True
        except Exception:  # noqa: BLE001
            state[
                'post_commit_verification_transaction_rollback_succeeded'
            ] = False
        return state

    if state['post_commit_row_count'] != 1:
        state['failed_reasons'].append(
            repair.FAILED_AFFECTED_ROW_COUNT_NOT_ONE
        )
    elif not state['post_commit_value_is_intended']:
        state['failed_reasons'].append(
            repair.FAILED_POST_STATE_NOT_INTENDED
        )
        state['refusal_reasons'].append(
            repair.REFUSED_POST_COMMIT_VERIFICATION_FAILED
        )
    return state


# ── Orchestration ───────────────────────────────────────────────────────────

def run(args) -> dict:
    context = event_context(args)
    note = sanitize_note(args.operator_note)
    operation = str(args.operation or '')

    failed = validate_authorization(context, args)
    if failed:
        return build_document(
            context=context, note=note, operation=operation, target={},
            official={}, comparison={}, plan={}, expectation={},
            completeness={}, preconditions={}, read_only={}, lock={},
            fingerprints={}, mutation={}, apply_state={}, source_calls={},
            decision=repair.decide(
                operation=operation, failed_reasons=failed,
            ),
        )

    failed_reasons: list[str] = []
    unproven_reasons: list[str] = []
    refusal_reasons: list[str] = []
    collected: dict = {}

    guard_state = {
        'acquire_attempted': False,
        'guard_acquired': False,
        'acquisition_reason': None,
        'guard_release_attempted': False,
        # None means the outcome was never established. Not False, and
        # certainly not True.
        'guard_released': None,
        'release_reason': None,
        'rollback_attempted': False,
        'rollback_succeeded': None,
    }

    budget = audit.SourceCallBudget()
    guard_client = None

    flask_app = build_app()
    from services import sync as sync_service
    from services import sync_metadata
    from sqlalchemy import text
    from utils.db import db

    original_client = sync_service.mlb_client

    with flask_app.app_context():
        lock_guard = None
        try:
            # The SAME advisory-lock identity every public sync writer takes,
            # acquire-only. Contention is UNPROVEN: this package never waits
            # and never queues, so it can never overlap a production writer.
            guard_state['acquire_attempted'] = True
            lock_guard = sync_metadata.acquire_public_sync_read_lock(
                source=sync_metadata.SOURCE_GITHUB_ACTIONS,
            )
            guard_state['guard_acquired'] = lock_guard is not None
            guard_state['acquisition_reason'] = (
                'acquired' if lock_guard is not None else 'not_returned'
            )
        except Exception:  # noqa: BLE001 - a contended lock is UNPROVEN
            lock_guard = None
            guard_state['acquisition_reason'] = 'lock_unavailable_or_contended'

        try:
            if not guard_state['guard_acquired']:
                collected['halt_stage'] = 'advisory_lock'
                raise _Halt()

            # EVERY observation happens inside a proven read-only transaction,
            # including in apply mode. The writable transaction is opened only
            # after every precondition has already been satisfied, and it does
            # exactly one thing.
            try:
                read_only = audit.enforce_read_only(db.session)
            except audit.ReadOnlyProbeViolation as violation:
                collected['read_only_enabled'] = False
                collected['read_only_detail'] = violation.evidence
                collected['halt_stage'] = 'read_only_probe'
                raise _Halt()
            except audit.ReadOnlyNotEnforced:
                collected['read_only_enabled'] = False
                collected['read_only_detail'] = {}
                unproven_reasons.append(repair.UNPROVEN_READ_ONLY_UNAVAILABLE)
                collected['halt_stage'] = 'read_only_transaction'
                raise _Halt()
            collected['read_only_enabled'] = True
            collected['read_only_detail'] = read_only

            stored = audit_runner.observe_stored_state()
            target = observe_target_row()
            collected['stored'] = stored
            collected['target'] = target
            collected['database_observed'] = True

            identities = set(stored['stored_pitcher_mlb_ids'])
            before = audit.scoped_fingerprints(
                db.session, pitcher_mlb_ids=identities,
            )
            collected['before_fingerprints'] = before
            collected['fingerprint_identities'] = sorted(identities)
            if before is None:
                unproven_reasons.append(
                    repair.UNPROVEN_FINGERPRINT_UNAVAILABLE
                )
                collected['halt_stage'] = 'before_fingerprints'
                raise _Halt()

            out_of_scope_before = repair.out_of_scope_fingerprint(db.session)
            collected['out_of_scope_before'] = out_of_scope_before
            if out_of_scope_before is None:
                unproven_reasons.append(
                    repair.UNPROVEN_OUT_OF_SCOPE_FINGERPRINT_UNAVAILABLE
                )

            # One bounded box-score call, through the counting guard, so a
            # duplicate or hidden call is caught rather than assumed away.
            guard_client = audit.CountedMLBClient(original_client, budget)
            sync_service.mlb_client = guard_client
            official = audit_runner.observe_current_source(guard_client)
            collected['official'] = official

            # The canonical projection rolls the session back, which ends the
            # read-only transaction. Re-assert it before reading again.
            try:
                db.session.rollback()
                db.session.execute(text('SET TRANSACTION READ ONLY'))
            except Exception:  # noqa: BLE001
                unproven_reasons.append(repair.UNPROVEN_READ_ONLY_UNAVAILABLE)

            # The AFTER pass covers exactly the scope the BEFORE pass covered.
            collected['after_fingerprints'] = audit.scoped_fingerprints(
                db.session, pitcher_mlb_ids=identities,
            )
            collected['out_of_scope_after_read'] = (
                repair.out_of_scope_fingerprint(db.session)
            )
        except _Halt:
            pass
        except Exception:  # noqa: BLE001 - never leak exception text
            collected['execution_error'] = True
            collected.setdefault('halt_stage', 'observation_error')
            unproven_reasons.append(repair.UNPROVEN_EXECUTION_ERROR)
        finally:
            sync_service.mlb_client = original_client

        # ── Judgement, from what was actually observed ──────────────────────
        stored = collected.get('stored') or {}
        target = collected.get('target') or {}
        official = collected.get('official') or {}
        database_observed = bool(collected.get('database_observed'))

        comparison = repair.build_comparison(official=official, stored=stored)
        expectation = repair.population_expectation(
            work_item=(target or {}).get('work_item'),
            stored_appearance_count=stored.get('stored_appearance_count'),
            database_observed=database_observed,
        )
        completeness = repair.source_completeness(
            official=official,
            comparison=comparison['summary'],
            database_observed=database_observed,
            expectation=expectation,
        )
        plan = official.get('plan') or {}
        preconditions = repair.evaluate_preconditions(
            target=target,
            official=official,
            comparison=comparison,
            plan=plan,
            expectation=expectation,
            completeness=completeness,
            database_observed=database_observed,
            before_fingerprints=collected.get('before_fingerprints'),
        )

        read_changed_tables = repair.changed_fingerprint_tables(
            collected.get('before_fingerprints'),
            collected.get('after_fingerprints'),
        )
        # Everything up to this point was read-only and PROVEN read-only. A
        # governed table that moved during it is either a contract violation by
        # this package or a concurrent writer that the advisory lock was
        # supposed to exclude. Either way it stops the run.
        if read_changed_tables:
            if operation == repair.OPERATION_VERIFY:
                failed_reasons.append(
                    repair.FAILED_MUTATION_ATTEMPTED_IN_VERIFY
                )
            else:
                refusal_reasons.append(repair.REFUSED_SCOPE_MOVED_BEFORE_APPLY)
        if collected.get('before_fingerprints') is not None and (
            collected.get('after_fingerprints') is None
        ):
            unproven_reasons.append(repair.UNPROVEN_FINGERPRINT_UNAVAILABLE)

        apply_state: dict = {}
        mutation: dict = {}
        # The apply gate, stated once and in full. Anything short of every
        # precondition satisfied, on an apply operation, with no earlier
        # problem of any kind, does not open a writable transaction at all.
        # Coverage is re-derived by the same function the verdict reducer uses,
        # so the gate that opens the transaction and the gate that judges the
        # run are one contract rather than two.
        coverage = repair.precondition_coverage(preconditions)
        collected['precondition_coverage'] = coverage
        may_apply = (
            operation == repair.OPERATION_APPLY
            and coverage['coverage_complete']
            and not coverage['violated']
            and not coverage['not_observed']
            and not coverage['unknown_state_ids']
            and not failed_reasons
            and not unproven_reasons
            and not refusal_reasons
            and not read_changed_tables
            and bool(collected.get('read_only_enabled'))
            and guard_state['guard_acquired']
        )
        collected['apply_gate_open'] = bool(may_apply)

        if may_apply:
            # The state object is created HERE and handed in, so an
            # exception escaping apply_repair leaves this frame holding the
            # same object with whatever was truthfully established. The old
            # shape built a replacement dict in the handler, which erased a
            # known durable commit by construction.
            apply_state = new_apply_state()
            try:
                apply_repair(
                    target_row_id=target.get('work_item_row_id'),
                    observed_snapshot=(target or {}).get('work_item'),
                    state=apply_state,
                )
            except Exception:  # noqa: BLE001 - never leak exception text
                apply_state['attempted'] = True
                if apply_state.get('committed') is True:
                    # A commit that already landed is a durable fact. It is
                    # never downgraded to "outcome unknown", and the failure
                    # is reported as this package's own contract violation.
                    incomplete = (
                        repair.FAILED_POST_COMMIT_VERIFICATION_INCOMPLETE
                    )
                    if incomplete not in apply_state['failed_reasons']:
                        apply_state['failed_reasons'].append(incomplete)
                    apply_state['post_commit_verification_completed'] = False
                else:
                    # No commit outcome was ever established, which is the
                    # ONLY situation this reason may describe.
                    apply_state['unproven_reasons'].append(
                        repair.UNPROVEN_APPLY_OUTCOME_UNKNOWN
                    )
            failed_reasons.extend(apply_state.get('failed_reasons') or ())
            unproven_reasons.extend(apply_state.get('unproven_reasons') or ())
            refusal_reasons.extend(apply_state.get('refusal_reasons') or ())

            # THE gate on every governed read that happens after COMMIT. The
            # old condition was `committed is True` alone, which let the whole
            # post-apply fingerprint phase run inside a transaction the
            # package had just failed to prove read-only — the exact thing it
            # promises never to do. Worse, evaluate_mutation() called with the
            # missing after-snapshot did not degrade: it reported every column
            # as changed and manufactured two false accusations about a row
            # that had in fact moved exactly as approved.
            committed = apply_state.get('committed') is True
            post_commit_proven = repair.post_commit_proof_complete(apply_state)
            collected['post_commit_proof_complete'] = post_commit_proven

            if committed and post_commit_proven:
                collected['post_apply_observation_attempted'] = True
                after_fingerprints = audit.scoped_fingerprints(
                    db.session,
                    pitcher_mlb_ids=set(
                        collected.get('fingerprint_identities') or ()
                    ),
                )
                collected['post_apply_fingerprints'] = after_fingerprints
                out_of_scope_after = repair.out_of_scope_fingerprint(
                    db.session
                )
                collected['out_of_scope_after'] = out_of_scope_after
                mutation = repair.evaluate_mutation(
                    before_snapshot=apply_state.get('before_snapshot'),
                    after_snapshot=apply_state.get('after_snapshot'),
                    guard_checks=apply_state.get('guard_checks'),
                    affected_row_count=apply_state.get('affected_row_count'),
                    changed_tables=(
                        repair.changed_fingerprint_tables(
                            collected.get('before_fingerprints'),
                            after_fingerprints,
                        )
                        if collected.get('before_fingerprints') is not None
                        and after_fingerprints is not None else None
                    ),
                    out_of_scope_before=collected.get('out_of_scope_before'),
                    out_of_scope_after=out_of_scope_after,
                    statements=apply_state.get('statements'),
                )
            elif committed:
                # The commit is durable and stays fully disclosed. NOTHING is
                # read: no scoped fingerprints, no out-of-scope digest, no
                # target-row query. Opening another unproven transaction to
                # salvage the evidence would be the same violation twice. A
                # later verify run is the mechanism for observing durable
                # state, and the artifact says so.
                collected['post_apply_observation_attempted'] = False
                mutation = (
                    repair
                    .committed_mutation_evidence_without_post_commit_proof(
                        apply_state
                    )
                )

        # ── Release, always, and record what actually happened ──────────────
        guard_state['rollback_attempted'] = True
        try:
            db.session.rollback()
            guard_state['rollback_succeeded'] = True
        except Exception:  # noqa: BLE001 - never leak exception text
            guard_state['rollback_succeeded'] = False
        if lock_guard is not None:
            guard_state['guard_release_attempted'] = True
            try:
                lock_guard.release()
                guard_state['guard_released'] = True
                guard_state['release_reason'] = 'released'
            except Exception:  # noqa: BLE001 - never leak exception text
                guard_state['guard_released'] = False
                guard_state['release_reason'] = 'release_raised'

    lock = repair.lock_lifecycle(guard_state)
    failed_reasons.extend(lock['failed_reasons'])
    unproven_reasons.extend(lock['unproven_reasons'])

    probe_validation = audit.evaluate_probe_evidence(
        audit.probe_evidence(collected.get('read_only_detail'))
    )
    if collected.get('read_only_enabled') is not None:
        failed_reasons.extend(probe_validation['failed_reasons'])
        if collected.get('read_only_enabled'):
            unproven_reasons.extend(probe_validation['unproven_reasons'])

    source_calls = (
        guard_client.state() if guard_client is not None
        else {
            'calls': [], 'calls_by_kind': {}, 'total_calls_issued': 0,
            'refusals': [], 'errors': [], 'unexpected_methods_refused': [],
            'reported_equals_actual': True,
            'duplicate_boxscore_requests': 0,
            'hidden_call_detected': False,
            'required_call_failed': False,
            'budget': budget.state(),
        }
    )
    if source_calls['hidden_call_detected'] or source_calls[
        'duplicate_boxscore_requests'
    ] or not source_calls['reported_equals_actual']:
        failed_reasons.append(repair.FAILED_MUTATION_SCOPE_EXCEEDED)
    if source_calls['budget'].get('required_call_refused'):
        unproven_reasons.append(repair.UNPROVEN_CURRENT_SOURCE_UNAVAILABLE)

    decision = repair.decide(
        operation=operation,
        preconditions=preconditions,
        mutation=mutation,
        failed_reasons=failed_reasons,
        unproven_reasons=unproven_reasons,
        refusal_reasons=refusal_reasons,
        apply_attempted=bool(apply_state.get('attempted')),
        apply_committed=apply_state.get('committed'),
        post_commit=apply_state,
    )

    return build_document(
        context=context, note=note, operation=operation, target=target,
        official=official, comparison=comparison, plan=plan,
        expectation=expectation, completeness=completeness,
        preconditions=preconditions,
        read_only={
            'read_only_transaction_enabled': collected.get(
                'read_only_enabled'
            ),
            'probe_validation': probe_validation,
            **(collected.get('read_only_detail') or {}),
        },
        lock=lock,
        fingerprints={
            'scope_plan': audit.fingerprint_scope_plan(
                collected.get('fingerprint_identities') or ()
            ),
            'identities': collected.get('fingerprint_identities') or [],
            'before': collected.get('before_fingerprints'),
            'after_read_phase': collected.get('after_fingerprints'),
            'after_apply': collected.get('post_apply_fingerprints'),
            'changed_during_read_phase': read_changed_tables,
            'out_of_scope_before': collected.get('out_of_scope_before'),
            'out_of_scope_after_read': collected.get(
                'out_of_scope_after_read'
            ),
            'out_of_scope_after_apply': collected.get('out_of_scope_after'),
            # Stated positively, so a null `after_apply` is never read as
            # "computed and empty". Absent evidence and observed-nothing are
            # different facts and the artifact must not blur them.
            'post_commit_proof_complete': collected.get(
                'post_commit_proof_complete'
            ),
            'post_apply_fingerprint_collection_attempted': collected.get(
                'post_apply_observation_attempted'
            ),
            'post_apply_fingerprints_observed': (
                collected.get('post_apply_fingerprints') is not None
            ),
            'post_apply_out_of_scope_fingerprint_observed': (
                collected.get('out_of_scope_after') is not None
            ),
            'post_apply_observation_skip_reason': (
                None if collected.get('post_apply_observation_attempted')
                is not False else repair.POST_COMMIT_OBSERVATION_SKIPPED
            ),
        },
        mutation=mutation, apply_state=apply_state,
        source_calls=source_calls, halt_stage=collected.get('halt_stage'),
        apply_gate_open=collected.get('apply_gate_open'),
        decision=decision,
    )


# ── Document ────────────────────────────────────────────────────────────────

def build_document(*, context, note, operation, target, official, comparison,
                   plan, expectation, completeness, preconditions, read_only,
                   lock, fingerprints, mutation, apply_state, source_calls,
                   decision, halt_stage=None, apply_gate_open=None) -> dict:
    summary = (comparison or {}).get('summary') or {}
    return {
        'schema_version': repair.SCHEMA_VERSION,
        'repair_type': repair.REPAIR_TYPE,
        'identity': {
            'operation': operation,
            'event_name': context.get('event_name'),
            'repository': context.get('repository'),
            'actor': context.get('actor'),
            'ref': context.get('ref'),
            'commit_sha': context.get('commit_sha'),
            'workflow': context.get('workflow'),
            'workflow_run_id': context.get('workflow_run_id'),
            'workflow_run_attempt': context.get('workflow_run_attempt'),
            'operator_note': note,
        },
        'scope': {
            'game_pk': repair.GAME_PK,
            'represented_date': repair.REPRESENTED_DATE.isoformat(),
            'target_table': repair.TARGET_TABLE,
            'target_identity_column': repair.TARGET_IDENTITY_COLUMN,
            'target_column': repair.TARGET_COLUMN,
            'expected_existing_source_revision': (
                repair.EXPECTED_EXISTING_SOURCE_REVISION
            ),
            'intended_source_revision': repair.INTENDED_SOURCE_REVISION,
            'expected_appearance_count': repair.EXPECTED_APPEARANCE_COUNT,
            'expected_plan_fingerprint': repair.EXPECTED_PLAN_FINGERPRINT,
            'permitted_changed_columns': sorted(
                repair.PERMITTED_CHANGED_COLUMNS
            ),
            'governed_changed_columns': sorted(
                repair.GOVERNED_CHANGED_COLUMNS
            ),
            'automatic_bookkeeping_columns': sorted(
                repair.AUTOMATIC_BOOKKEEPING_COLUMNS
            ),
            'required_work_item_status': repair.REQUIRED_WORK_ITEM_STATUS,
            'prohibited_mutations': list(repair.PROHIBITED_MUTATIONS),
        },
        'source_revision_semantics': audit.source_revision_semantics(),
        'target_row': target or {},
        'population_expectation': expectation or {},
        'current_source': {
            'available': (official or {}).get('available'),
            'unavailable_reason': (official or {}).get('unavailable_reason'),
            'appearance_count': (official or {}).get('appearance_count'),
            'current_source_revision': (official or {}).get(
                'current_source_revision'
            ),
            'official_pitcher_mlb_ids': (official or {}).get(
                'official_pitcher_mlb_ids'
            ),
            'planner_scope': (official or {}).get('planner_scope'),
        },
        'current_source_completeness': completeness or {},
        'canonical_plan': plan or {},
        'field_comparison_summary': summary,
        'preconditions': preconditions or {},
        'read_only_proof': read_only or {},
        'advisory_lock': lock or {},
        'fingerprints': fingerprints or {},
        'mutation_ledger': build_mutation_ledger(
            apply_state=apply_state, mutation=mutation, target=target,
            apply_gate_open=apply_gate_open, operation=operation,
            context=context, note=note, lock=lock, read_only=read_only,
            decision=decision,
        ),
        'source_call_report': source_calls or {},
        'halt_stage': halt_stage,
        'verdict': decision,
        'explanation': repair.explanation(decision),
        'non_authorization_statement': repair.NON_AUTHORIZATION_STATEMENT,
        'dead_letter_backlog_note': repair.DEAD_LETTER_BACKLOG_NOTE,
        'standing_production_state': dict(repair.STANDING_PRODUCTION_STATE),
        '_comparison_rows': (comparison or {}).get('rows') or [],
    }


def build_mutation_ledger(*, apply_state, mutation, target,
                          apply_gate_open=None, operation=None, context=None,
                          note='', lock=None, read_only=None,
                          decision=None) -> dict:
    """What was written, or the explicit record that nothing was.

    A ledger that exists only on success would make "no ledger" ambiguous
    between "did not run" and "ran and wrote nothing". It always exists, and
    it carries the run's own identity so a reader never has to correlate it
    against another file to know which run wrote it.
    """
    apply_state = apply_state or {}
    mutation = mutation or {}
    context = context or {}
    lock = lock or {}
    read_only = read_only or {}
    decision = decision or {}
    return {
        'schema_version': repair.SCHEMA_VERSION,
        'operation': operation,
        'game_pk': repair.GAME_PK,
        'represented_date': repair.REPRESENTED_DATE.isoformat(),
        'model': 'GameIngestionWorkItem',
        'table': repair.TARGET_TABLE,
        'column': repair.TARGET_COLUMN,
        'target_row_id': (target or {}).get('work_item_row_id'),
        'target_row_identity': {
            'id': (target or {}).get('work_item_row_id'),
            repair.TARGET_IDENTITY_COLUMN: repair.GAME_PK,
            'candidate_row_count': (target or {}).get('candidate_row_count'),
            'candidate_row_ids': (target or {}).get('candidate_row_ids'),
        },
        # ── Run identity ───────────────────────────────────────────────────
        'workflow_run_id': context.get('workflow_run_id'),
        'workflow_run_attempt': context.get('workflow_run_attempt'),
        'main_sha': context.get('commit_sha'),
        'actor': context.get('actor'),
        'operator_note': note,
        # ── Transaction and lock state ─────────────────────────────────────
        'advisory_lock_state': {
            'acquired': lock.get('guard_acquired'),
            'acquisition_reason': lock.get('acquisition_reason'),
            'release_attempted': lock.get('guard_release_attempted'),
            'released': lock.get('guard_released'),
            'release_reason': lock.get('release_reason'),
            'lifecycle_complete': lock.get('lifecycle_complete'),
        },
        'transaction_state': {
            'observation_transaction_read_only': read_only.get(
                'read_only_transaction_enabled'
            ),
            'write_probe_refused': read_only.get('read_only_probe_refused'),
            'row_locked_for_update': apply_state.get('row_locked'),
            'in_transaction_value_is_intended': apply_state.get(
                'in_transaction_value_is_intended'
            ),
            'post_commit_transaction_read_only': apply_state.get(
                'post_commit_transaction_read_only'
            ),
            'post_commit_read_only_reason': apply_state.get(
                'post_commit_read_only_reason'
            ),
            # A cleanup rollback of the POST-COMMIT verification transaction.
            # It is not, and must never be read as, a rollback of the repair:
            # the repair's own COMMIT already returned before this transaction
            # existed. `rollback_performed` below stays False for that reason.
            'post_commit_verification_transaction_rollback_succeeded': (
                apply_state.get(
                    'post_commit_verification_transaction_rollback_succeeded'
                )
            ),
        },
        'commits_performed': (
            apply_state.get('commit_count')
            if apply_state.get('committed') is True else 0
        ),
        'rollback_performed': bool(
            apply_state.get('attempted')
            and apply_state.get('committed') is not True
        ) or apply_state.get('revalidated') is False,
        'mutation_status': decision.get('result'),
        'mutation_performed': decision.get('mutation_performed'),
        'mutation_timestamp': (
            (apply_state.get('after_snapshot') or {}).get('updated_at')
            if apply_state.get('committed') is True else None
        ),
        # ── Post-commit verification lifecycle ─────────────────────────────
        # Reported as a lifecycle, not a single boolean, because "the proof
        # did not happen" and "the proof happened and disagreed" are different
        # facts and a reader must not have to guess which one occurred.
        'post_commit_verification_attempted': apply_state.get(
            'post_commit_verification_attempted'
        ),
        'post_commit_read_only_attempted': apply_state.get(
            'post_commit_read_only_attempted'
        ),
        'post_commit_transaction_read_only': apply_state.get(
            'post_commit_transaction_read_only'
        ),
        'post_commit_read_only_reason': apply_state.get(
            'post_commit_read_only_reason'
        ),
        'post_commit_verification_completed': apply_state.get(
            'post_commit_verification_completed'
        ),
        'post_commit_verification_transaction_rollback_succeeded': (
            apply_state.get(
                'post_commit_verification_transaction_rollback_succeeded'
            )
        ),
        'post_commit_value_is_intended': apply_state.get(
            'post_commit_value_is_intended'
        ),
        'post_commit_row_count': apply_state.get('post_commit_row_count'),
        # The single authoritative predicate, recomputed here from the same
        # state the runner gated its reads on, so the artifact discloses the
        # decision rather than leaving a reader to infer it from six booleans.
        'post_commit_proof_complete': repair.post_commit_proof_complete(
            apply_state
        ),
        'post_apply_scope_evaluation_completed': (
            mutation.get('post_apply_scope_evaluation_completed', True)
            if mutation else None
        ),
        'post_apply_observation_skip_reason': mutation.get(
            'post_apply_observation_skip_reason'
        ) if mutation else None,
        'apply_gate_open': apply_gate_open,
        'apply_attempted': bool(apply_state.get('attempted')),
        'row_locked_for_update': apply_state.get('row_locked'),
        'lock_available': apply_state.get('lock_available'),
        'revalidated_under_lock': apply_state.get('revalidated'),
        'revalidation_reason': apply_state.get('revalidation_reason'),
        'committed': apply_state.get('committed'),
        'old_value': (apply_state.get('before_snapshot') or {}).get(
            repair.TARGET_COLUMN
        ),
        'new_value': (apply_state.get('after_snapshot') or {}).get(
            repair.TARGET_COLUMN
        ),
        'proposed_value': repair.INTENDED_SOURCE_REVISION,
        'intended_value': repair.INTENDED_SOURCE_REVISION,
        'expected_old_value': repair.EXPECTED_EXISTING_SOURCE_REVISION,
        'observed_value_before': (
            apply_state.get('before_snapshot') or {}
        ).get(repair.TARGET_COLUMN),
        'observed_value_after': (
            apply_state.get('after_snapshot') or {}
        ).get(repair.TARGET_COLUMN),
        'in_transaction_value': apply_state.get('in_transaction_value'),
        'before_snapshot': apply_state.get('before_snapshot'),
        'after_snapshot': apply_state.get('after_snapshot'),
        'guard_observations': apply_state.get('guard_observations'),
        'statement_report': apply_state.get('statements'),
        'affected_row_count': apply_state.get('affected_row_count'),
        'scope_evaluation': mutation,
        'permitted_changed_columns': sorted(repair.PERMITTED_CHANGED_COLUMNS),
        'prohibited_mutations': list(repair.PROHIBITED_MUTATIONS),
    }


# The fifteen sections a reviewer is entitled to find, in order. A contract
# test asserts every one of them is present in every rendered summary.
REQUIRED_MARKDOWN_SECTIONS = (
    '# Game 824487 source-revision checkpoint repair',
    '## 1. Authorization',
    '## 2. Operation mode',
    '## 3. Target row',
    '## 4. Current official source',
    '## 5. Canonical storage',
    '## 6. Reconciliation plan',
    '## 7. Checkpoint transition',
    '## 8. Preconditions',
    '## 9. Mutation ledger',
    '## 10. Before/after fingerprints',
    '## 11. Advisory-lock lifecycle',
    '## 12. Transaction proof',
    '## 13. Prohibited-scope verification',
    '## 14. Final result',
    '## 15. Remaining limitations',
)


def _row(label, value):
    return f'| {label} | {value} |'


def _post_apply_observation_narrative(fingerprints) -> list[str]:
    """Why the post-apply rows are blank, when they are.

    A blank fingerprint table invites the reader to fill it in with the
    friendliest available assumption — that nothing moved. It is stated
    instead that nothing was LOOKED AT, and why, and what to do about it.
    """
    if fingerprints.get('post_apply_fingerprint_collection_attempted') is not (
        False
    ):
        return []
    return [
        '> The post-apply fingerprints and the out-of-scope digest were '
        'deliberately **not collected**. The required post-commit read-only '
        'proof did not complete, and this package does not observe governed '
        'state from a transaction it could not prove read-only — collecting '
        'them anyway would be the same violation the proof exists to '
        'prevent. Blank here means UNOBSERVED, not unchanged: no in-scope or '
        'out-of-scope claim is made in either direction. Run `verify` to '
        'establish the current durable state before taking any further '
        'action.',
        '',
    ]


def _post_commit_proof_narrative(ledger) -> list[str]:
    """Say in words what the post-commit row means, when it is unusual.

    The dangerous reading of a committed-but-unproven run is "the write did
    not stick". A reader skimming a table of booleans can land there. So the
    one case where that misreading is possible gets stated outright: the row
    was changed, the change is durable, and what failed was this package's
    own proof obligation afterwards.
    """
    if ledger.get('committed') is not True:
        return []
    if ledger.get('post_commit_verification_completed') is True:
        return []
    if ledger.get('post_commit_transaction_read_only') is True:
        what_failed = (
            'the fresh transaction was proven read-only, and the governed '
            're-read of the row did not complete inside it'
        )
    else:
        what_failed = (
            'it could not establish a read-only transaction to re-read the '
            'row in, so it did not re-read it'
        )
    return [
        '> The repair COMMITTED. The row was updated and that update is '
        f'durable. What failed afterwards is this package\'s own post-commit '
        f'proof obligation: {what_failed}. Nothing was rolled back — the '
        'commit had already returned before that verification transaction '
        'existed. The run is FAILED because the package did not keep a '
        'guarantee it makes, not because the database is in an unknown '
        'state. The next verify run observes the durable value directly.',
        '',
    ]


def render_markdown(document) -> str:
    verdict = document.get('verdict') or {}
    scope = document.get('scope') or {}
    identity = document.get('identity') or {}
    preconditions = document.get('preconditions') or {}
    completeness = document.get('current_source_completeness') or {}
    source = document.get('current_source') or {}
    comparison = document.get('field_comparison_summary') or {}
    plan = document.get('canonical_plan') or {}
    expectation = document.get('population_expectation') or {}
    proof = document.get('read_only_proof') or {}
    lock = document.get('advisory_lock') or {}
    ledger = document.get('mutation_ledger') or {}
    fingerprints = document.get('fingerprints') or {}
    target = document.get('target_row') or {}
    evaluation = ledger.get('scope_evaluation') or {}
    transaction = ledger.get('transaction_state') or {}

    head = ['| field | value |', '| :--- | :--- |']

    lines = [
        '# Game 824487 source-revision checkpoint repair',
        '',
        '## 1. Authorization',
        '',
        *head,
        _row('event', identity.get('event_name')),
        _row('repository', identity.get('repository')),
        _row('actor', identity.get('actor')),
        _row('ref', identity.get('ref')),
        _row('commit', f"`{identity.get('commit_sha')}`"),
        _row('workflow run', identity.get('workflow_run_id')),
        _row('run attempt', identity.get('workflow_run_attempt')),
        _row('operator note length', len(identity.get('operator_note') or '')),
        '',
        'The operator note is informational. It can never affect '
        'authorization or any verdict, and it is sanitized before it is '
        'recorded.',
        '',
        '## 2. Operation mode',
        '',
        f"Operation: `{identity.get('operation')}`.",
        '',
        'A `verify` run writes nothing under any outcome. An `apply` run '
        're-observes every precondition from scratch and never consumes a '
        'cached verification result. Each operation carries its own '
        'confirmation phrase, so a confirmation reviewed for a verify run '
        'cannot start an apply run.',
        '',
        '## 3. Target row',
        '',
        *head,
        _row('candidate rows', target.get('candidate_row_count')),
        _row('candidate ids', target.get('candidate_row_ids')),
        _row('row id', target.get('work_item_row_id')),
        _row('game', scope.get('game_pk')),
        _row('represented date', scope.get('represented_date')),
        _row('table', f"`{scope.get('target_table')}`"),
        _row('column', f"`{scope.get('target_column')}`"),
        _row('required status', scope.get('required_work_item_status')),
        '',
        '## 4. Current official source',
        '',
        *head,
        _row('fetched', source.get('available')),
        _row('unavailable reason', source.get('unavailable_reason')),
        _row('appearances observed', source.get('appearance_count')),
        _row('reviewed count', scope.get('expected_appearance_count')),
        _row(
            'current source revision',
            f"`{source.get('current_source_revision')}`",
        ),
        _row('completeness state',
             f"`{completeness.get('completeness_state')}`"),
        _row('conclusion eligible', completeness.get('conclusion_eligible')),
        '',
        '## 5. Canonical storage',
        '',
        *head,
        _row('stored appearances', expectation.get('stored_appearance_count')),
        _row('checkpoint rows_expected', expectation.get('rows_expected')),
        _row('checkpoint rows_reconciled',
             expectation.get('rows_reconciled')),
        _row('population expectation',
             f"`{expectation.get('expectation_state')}`"),
        _row('membership matches', comparison.get('membership_matches')),
        _row('missing from storage', comparison.get('missing_from_storage')),
        _row('extra in storage', comparison.get('extra_in_storage')),
        _row('duplicate official',
             comparison.get('duplicate_official_identities')),
        _row('duplicate stored',
             comparison.get('duplicate_stored_identities')),
        '',
        '## 6. Reconciliation plan',
        '',
        *head,
        _row('available', plan.get('available')),
        _row('rows', plan.get('row_count')),
        _row('action counts', plan.get('action_counts')),
        _row('proposes mutation', plan.get('proposes_mutation')),
        _row('plan fingerprint',
             f"`{plan.get('reconciliation_plan_fingerprint')}`"),
        _row('reviewed fingerprint',
             f"`{scope.get('expected_plan_fingerprint')}`"),
        '',
        'The plan fingerprint is checked separately from the action counts '
        'and refuses on its own. A plan can report zero inserts, zero '
        'updates, and zero blocked rows while its fingerprint has moved.',
        '',
        '## 7. Checkpoint transition',
        '',
        *head,
        _row('expected old value',
             f"`{scope.get('expected_existing_source_revision')}`"),
        _row('intended new value',
             f"`{scope.get('intended_source_revision')}`"),
        _row('observed before', f"`{ledger.get('observed_value_before')}`"),
        _row('observed after', f"`{ledger.get('observed_value_after')}`"),
        _row('permitted changed columns',
             f"`{scope.get('permitted_changed_columns')}`"),
        '',
        'The permitted changed-column set includes `updated_at` because the '
        'model declares `onupdate=utc_now_naive`, which fires on any UPDATE '
        'of the row. It is an automatic bookkeeping side effect of the one '
        'permitted change, declared rather than hidden, and deliberately not '
        'pinned back to its old value.',
        '',
        '## 8. Preconditions',
        '',
        '| precondition | state | expected | observed |',
        '| :--- | :--- | :--- | :--- |',
    ]
    for check in preconditions.get('preconditions') or ():
        lines.append(
            f"| `{check.get('precondition_id')}` | {check.get('state')} "
            f"| {check.get('expected')} | {check.get('observed')} |"
        )
    lines += [
        '',
        f"All satisfied: {preconditions.get('all_satisfied')}. "
        f"Violated: `{preconditions.get('violated')}`. "
        f"Not observed: `{preconditions.get('not_observed')}`.",
        '',
        '## 9. Mutation ledger',
        '',
        *head,
        _row('apply gate open', ledger.get('apply_gate_open')),
        _row('apply attempted', ledger.get('apply_attempted')),
        _row('row locked FOR UPDATE', ledger.get('row_locked_for_update')),
        _row('revalidated under lock', ledger.get('revalidated_under_lock')),
        _row('revalidation reason', ledger.get('revalidation_reason')),
        _row('affected rows', ledger.get('affected_row_count')),
        _row('commits performed', ledger.get('commits_performed')),
        _row('rollback performed', ledger.get('rollback_performed')),
        _row('committed', ledger.get('committed')),
        _row('mutation status', ledger.get('mutation_status')),
        _row('mutation performed', ledger.get('mutation_performed')),
        _row('mutation timestamp', ledger.get('mutation_timestamp')),
        _row('changed columns',
             f"`{evaluation.get('observed_changed_columns')}`"),
        '',
        '## 10. Before/after fingerprints',
        '',
        *head,
        _row('scopes changed during read phase',
             f"`{fingerprints.get('changed_during_read_phase')}`"),
        _row('tables changed by apply',
             f"`{evaluation.get('changed_fingerprint_tables')}`"),
        _row('expected tables',
             f"`{evaluation.get('expected_changed_fingerprint_tables')}`"),
        _row('unexpected tables',
             f"`{evaluation.get('unexpected_changed_fingerprint_tables')}`"),
        _row('out-of-scope digest unchanged',
             evaluation.get('out_of_scope_unchanged')),
        _row('post-apply collection attempted',
             fingerprints.get(
                 'post_apply_fingerprint_collection_attempted')),
        _row('post-apply fingerprints observed',
             fingerprints.get('post_apply_fingerprints_observed')),
        _row('post-apply out-of-scope digest observed',
             fingerprints.get(
                 'post_apply_out_of_scope_fingerprint_observed')),
        _row('post-apply skip reason',
             fingerprints.get('post_apply_observation_skip_reason')),
        '',
        *_post_apply_observation_narrative(fingerprints),
        '## 11. Advisory-lock lifecycle',
        '',
        *head,
        _row('acquire attempted', lock.get('acquire_attempted')),
        _row('acquired', lock.get('guard_acquired')),
        _row('acquisition reason', lock.get('acquisition_reason')),
        _row('release attempted', lock.get('guard_release_attempted')),
        _row('released', lock.get('guard_released')),
        _row('release reason', lock.get('release_reason')),
        _row('lifecycle complete', lock.get('lifecycle_complete')),
        '',
        'The lock is the same identity every public sync writer takes, and '
        'it is acquire-only: it never creates, reclaims, or updates a '
        'SyncRun row. Contention stops the run rather than queueing it.',
        '',
        '## 12. Transaction proof',
        '',
        *head,
        _row('observation transaction read-only',
             transaction.get('observation_transaction_read_only')),
        _row('bounded write probe refused',
             transaction.get('write_probe_refused')),
        _row('target row locked FOR UPDATE',
             transaction.get('row_locked_for_update')),
        _row('in-transaction value is intended',
             transaction.get('in_transaction_value_is_intended')),
        _row('post-commit verification attempted',
             ledger.get('post_commit_verification_attempted')),
        _row('post-commit read-only attempted',
             ledger.get('post_commit_read_only_attempted')),
        _row('post-commit transaction read-only',
             transaction.get('post_commit_transaction_read_only')),
        _row('post-commit read-only reason',
             ledger.get('post_commit_read_only_reason')),
        _row('post-commit verification completed',
             ledger.get('post_commit_verification_completed')),
        _row('post-commit verification transaction rolled back',
             ledger.get(
                 'post_commit_verification_transaction_rollback_succeeded')),
        _row('post-commit value is intended',
             ledger.get('post_commit_value_is_intended')),
        _row('post-commit row count', ledger.get('post_commit_row_count')),
        '',
        *_post_commit_proof_narrative(ledger),
    ]
    lines += [
        '## 13. Prohibited-scope verification',
        '',
        'This run performed none of the following:',
        '',
    ]
    for prohibited in scope.get('prohibited_mutations') or ():
        lines.append(f'- `{prohibited}`')
    lines += [
        '',
        *head,
        _row('objects created',
             (ledger.get('guard_observations') or {}).get(
                 'created_object_count')),
        _row('objects deleted',
             (ledger.get('guard_observations') or {}).get(
                 'deleted_object_count')),
        _row('write statements issued',
             (ledger.get('statement_report') or {}).get(
                 'write_statement_count')),
        _row('other write statements',
             (ledger.get('statement_report') or {}).get(
                 'other_write_statement_count')),
        _row('source calls issued',
             (document.get('source_call_report') or {}).get(
                 'total_calls_issued')),
        '',
        document.get('dead_letter_backlog_note') or '',
        '',
        '## 14. Final result',
        '',
        f"**{verdict.get('result')}** (exit {verdict.get('exit_code')}), "
        f"operation `{identity.get('operation')}`.",
        '',
        document.get('explanation') or '',
        '',
    ]
    for label, key in (
        ('FAILED', 'failed_reasons'),
        ('UNPROVEN', 'unproven_reasons'),
        ('REFUSED', 'refusal_reasons'),
    ):
        for reason in verdict.get(key) or ():
            lines.append(f'- {label}: `{reason}`')
    lines += [
        '',
        '## 15. Remaining limitations',
        '',
        '- A verify result is evidence for a human decision, not that '
        'decision, and it does not expire into permission. An apply run '
        're-observes everything from scratch.',
        '- One bounded box-score call, no retries. An incomplete or '
        'unavailable payload reduces scope and reports UNPROVEN rather than '
        'widening the call budget.',
        '- The out-of-scope digest covers `game_ingestion_work_items`, the '
        'one table any statement in this package names. Every other governed '
        'table is covered by the in-scope fingerprints for this game.',
        '- No retained audit artifact is consulted. This package makes no '
        'historical claim and cannot corroborate one.',
        f"- Halt stage: `{document.get('halt_stage')}`.",
        '',
        document.get('non_authorization_statement') or '',
        '',
    ]
    return '\n'.join(str(line) for line in lines) + '\n'


def write_artifacts(document, comparison_rows, artifact_dir) -> dict:
    directory = Path(artifact_dir)
    directory.mkdir(parents=True, exist_ok=True)

    written = {}
    payloads = {
        SUMMARY_JSON: document,
        PRECONDITIONS_JSON: {
            'schema_version': repair.SCHEMA_VERSION,
            'game_pk': repair.GAME_PK,
            'precondition_ids': list(repair.PRECONDITION_IDS),
            'precondition_states': list(repair.PRECONDITION_STATES),
            'refusal_reason_by_precondition': dict(
                repair.PRECONDITION_REFUSAL_REASONS
            ),
            'unproven_reason_by_precondition': dict(
                repair.PRECONDITION_UNPROVEN_REASONS
            ),
            'specified_condition_to_reason_code': dict(
                repair.SPECIFIED_REASON_CODES
            ),
            'failed_reasons': list(repair.FAILED_REASONS),
            'unproven_reasons': list(repair.UNPROVEN_REASONS),
            'refusal_reasons': list(repair.REFUSED_REASONS),
            'evaluation': document.get('preconditions') or {},
        },
        PROOF_JSON: {
            'schema_version': repair.SCHEMA_VERSION,
            'game_pk': repair.GAME_PK,
            'operation': (document.get('identity') or {}).get('operation'),
            'read_only_proof': document.get('read_only_proof') or {},
            'advisory_lock': document.get('advisory_lock') or {},
            'source_call_report': document.get('source_call_report') or {},
            'prohibited_mutations': list(repair.PROHIBITED_MUTATIONS),
            'permitted_changed_columns': sorted(
                repair.PERMITTED_CHANGED_COLUMNS
            ),
            'standing_production_state': document.get(
                'standing_production_state'
            ),
            'dead_letter_backlog_note': document.get(
                'dead_letter_backlog_note'
            ),
            'non_authorization_statement': document.get(
                'non_authorization_statement'
            ),
        },
        FINGERPRINTS_JSON: {
            'schema_version': repair.SCHEMA_VERSION,
            'game_pk': repair.GAME_PK,
            'operation': (document.get('identity') or {}).get('operation'),
            'fingerprints': document.get('fingerprints') or {},
            'scope_evaluation': (
                document.get('mutation_ledger') or {}
            ).get('scope_evaluation') or {},
            'out_of_scope_table': repair.OUT_OF_SCOPE_TABLE,
        },
        MUTATION_LEDGER_JSON: document.get('mutation_ledger') or {},
        COMPARISON_JSON: {
            'schema_version': repair.SCHEMA_VERSION,
            'game_pk': repair.GAME_PK,
            'summary': document.get('field_comparison_summary') or {},
            'current_source_completeness': document.get(
                'current_source_completeness'
            ) or {},
            'population_expectation': document.get(
                'population_expectation'
            ) or {},
            'rows': list(comparison_rows or ()),
        },
    }
    for name, payload in payloads.items():
        path = directory / name
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str) + '\n',
            encoding='utf-8',
        )
        written[name] = str(path)

    markdown = directory / SUMMARY_MARKDOWN
    markdown.write_text(render_markdown(document), encoding='utf-8')
    written[SUMMARY_MARKDOWN] = str(markdown)
    return written


def main(argv=None) -> int:
    args = parse_args(argv)
    document = run(args)
    comparison_rows = document.pop('_comparison_rows', None) or []
    try:
        write_artifacts(document, comparison_rows, args.artifact_dir)
    except Exception:  # noqa: BLE001 - never leak the filesystem message
        # A run whose evidence could not be written is not a successful run,
        # whatever its verdict said. Reported as a contract violation with a
        # closed reason code rather than as an uncaught traceback.
        verdict = document.get('verdict') or {}
        print(json.dumps({
            'operation': verdict.get('operation'),
            'result': repair.RESULT_FAILED,
            'exit_code': repair.EXIT_CODES[repair.RESULT_FAILED],
            'failed_reasons': [repair.FAILED_ARTIFACT_GENERATION_FAILED],
            'unproven_reasons': [],
            'refusal_reasons': [],
            'mutation_performed': verdict.get('mutation_performed'),
        }, indent=2, sort_keys=True))
        return repair.EXIT_CODES[repair.RESULT_FAILED]
    verdict = document.get('verdict') or {}
    print(json.dumps({
        'operation': verdict.get('operation'),
        'result': verdict.get('result'),
        'exit_code': verdict.get('exit_code'),
        'failed_reasons': verdict.get('failed_reasons'),
        'unproven_reasons': verdict.get('unproven_reasons'),
        'refusal_reasons': verdict.get('refusal_reasons'),
        'mutation_performed': verdict.get('mutation_performed'),
    }, indent=2, sort_keys=True))
    return int(verdict.get(
        'exit_code', repair.EXIT_CODES[repair.RESULT_UNPROVEN]
    ))


if __name__ == '__main__':
    raise SystemExit(main())
