"""Game-driven incremental appearance ingestion (Foundation 3C).

The daily publication-critical lane, rebuilt around the correct unit of work.

Old critical path (retired by this module):

    every active pitcher  ->  one full-season gameLog request per pitcher
                          ->  filter locally to a 7-day window
                          ->  compare locally
                          ->  restart from zero after interruption

New critical path:

    canonical schedule + finality authority
                          ->  deterministic game work plan
                          ->  fetch each planned game's box score ONCE
                          ->  extract that game's pitcher appearances
                          ->  reconcile canonical GameLog rows idempotently
                          ->  durable per-game completion, transactionally
                              aligned with the appearance writes
                          ->  game-level publication completeness proof

Production evidence that forced the change (read-only diagnostic, 2026-07-29):
854 active pitchers were selected daily; 139 active starters and 13 active
roster non-pitchers had zero relief appearances in the lookback; ~94% of every
returned split was outside the governed window; 100% of the sampled requests
were no-change work; and external request time was 99.8% of the measured cost.
The waste was structural, not incidental — it came from the unit of work.

Modes
-----
``off``            the lane does not run (deployed default; zero change)
``shadow``         plan + fetch + extract + project, WRITES NOTHING
``write``          plan + reconcile + checkpoint; publication authority unchanged
``authoritative``  as ``write``, and the game-level completeness proof drives
                   publication-critical completeness

Rollout is staged deliberately: the mode advances only after each stage's
production evidence passes. Nothing here flips publication authority on merge.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date

from models.game_ingestion_work_item import GameIngestionWorkItem
from models.game_log import GameLog
from models.pitcher import Pitcher
from services import dead_letter
from services import continuous_reliever_ingestion as continuous_impact
from services import game_appearance_extraction as extraction
from services import game_ingestion_planner as planner
from services import game_log_reconciliation as reconciliation
from services import pitcher_identity_reconciliation as pitcher_identity
from services.game_appearance_extraction import AppearanceExtractionError
from utils.db import db
from utils.time import utc_now_naive


logger = logging.getLogger(__name__)

MODE_OFF = 'off'
MODE_SHADOW = 'shadow'
MODE_WRITE = 'write'
MODE_AUTHORITATIVE = 'authoritative'
MODES = (MODE_OFF, MODE_SHADOW, MODE_WRITE, MODE_AUTHORITATIVE)

MODE_ENV_VAR = 'GAME_DRIVEN_INGESTION_MODE'

# Run outcomes that stop before doing any work.
STATUS_SCOPE_MISMATCH = 'scope_mismatch'
STATUS_SCOPE_INVALID = 'scope_invalid'
STATUS_PLAN_AUTHORIZATION_REQUIRED = 'plan_authorization_required'
STATUS_PLAN_FINGERPRINT_MISMATCH = 'plan_fingerprint_mismatch'

SCOPE_ERROR_UNEXPECTED_GAME = 'unexpected_game_in_plan'
SCOPE_ERROR_MISSING_GAME = 'requested_game_not_plannable'
SCOPE_ERROR_FINGERPRINT_REQUIRED = 'reviewed_plan_fingerprint_required'
SCOPE_ERROR_FINGERPRINT_MISMATCH = 'reviewed_plan_fingerprint_mismatch'

_SCOPE_REPORT_FIELDS = (
    'execution_scope_mode',
    'requested_game_pks',
    'requested_game_count',
    'duplicate_requested_count',
    'planned_game_pks',
    'planned_game_count',
    'unexpected_planned_game_pks',
    'missing_requested_game_pks',
    'execution_scope_exact_match',
)

# Counters folded identically from each game's canonical summary into the
# run report. Every mutation target is represented, so a run cannot report
# "no mutations" while one target is unaccounted for.
_IDENTITY_COUNTER_FIELDS = (
    'pitcher_identity_rows_examined',
    'pitcher_identity_mutations',
    'pitcher_identity_unchanged',
    'pitcher_identity_creations',
    'pitcher_identity_reactivations',
    'pitcher_identity_metadata_updates',
    'pitcher_identity_blocked',
    'historical_current_state_changes_suppressed',
    'appearance_team_mutations',
    'complete_mutation_count',
)

_IDENTITY_MUTATING_ACTIONS = frozenset(pitcher_identity.MUTATING_ACTIONS)

GAME_INGESTION_FAILURE_ENTITY_TYPE = 'game_driven_ingestion_game'

RETRY_LIMIT = 3

# ── Failure classes ─────────────────────────────────────────────────────────
# Each declares, in ONE place, whether it is retryable, whether it is
# publication-critical, whether it blocks checkpoint advancement, and whether it
# blocks publication. Nothing is reduced to an opaque dead-letter count.
ERROR_SCHEDULE_AUTHORITY_MISSING = 'schedule_authority_missing'
ERROR_FINALITY_UNRESOLVED = 'finality_unresolved'
ERROR_GAME_FETCH_FAILED = 'game_fetch_failed'
ERROR_PAYLOAD_INVALID = 'payload_invalid'
ERROR_STARTER_IDENTITY_UNRESOLVED = 'starter_identity_unresolved'
ERROR_APPEARANCE_EXTRACTION_FAILED = 'appearance_extraction_failed'
ERROR_PERSISTENCE_FAILED = 'persistence_failed'
ERROR_RECONCILIATION_FAILED = 'reconciliation_failed'
ERROR_CORRECTION_CONFLICT = 'correction_conflict'
ERROR_BUDGET_EXHAUSTED = 'budget_exhausted'
ERROR_UNEXPECTED = 'unexpected_error'

FAILURE_SEMANTICS = {
    ERROR_SCHEDULE_AUTHORITY_MISSING: {
        'retryable': True, 'blocks_checkpoint': True, 'blocks_publication': True,
    },
    ERROR_FINALITY_UNRESOLVED: {
        'retryable': True, 'blocks_checkpoint': True, 'blocks_publication': True,
    },
    ERROR_GAME_FETCH_FAILED: {
        'retryable': True, 'blocks_checkpoint': True, 'blocks_publication': True,
    },
    ERROR_PAYLOAD_INVALID: {
        'retryable': True, 'blocks_checkpoint': True, 'blocks_publication': True,
    },
    ERROR_STARTER_IDENTITY_UNRESOLVED: {
        'retryable': True, 'blocks_checkpoint': True, 'blocks_publication': True,
    },
    ERROR_APPEARANCE_EXTRACTION_FAILED: {
        'retryable': True, 'blocks_checkpoint': True, 'blocks_publication': True,
    },
    ERROR_PERSISTENCE_FAILED: {
        'retryable': True, 'blocks_checkpoint': True, 'blocks_publication': True,
    },
    ERROR_RECONCILIATION_FAILED: {
        'retryable': True, 'blocks_checkpoint': True, 'blocks_publication': True,
    },
    ERROR_CORRECTION_CONFLICT: {
        'retryable': True, 'blocks_checkpoint': True, 'blocks_publication': True,
    },
    # Budget exhaustion is NOT a terminal dead-letter condition. It is an
    # incomplete, resumable run state: the work item stays unresolved and the
    # next run picks it up first.
    ERROR_BUDGET_EXHAUSTED: {
        'retryable': True, 'blocks_checkpoint': True, 'blocks_publication': True,
    },
    # Generic unexpected errors fail closed.
    ERROR_UNEXPECTED: {
        'retryable': True, 'blocks_checkpoint': True, 'blocks_publication': True,
    },
}


def ingestion_mode() -> str:
    raw = str(os.environ.get(MODE_ENV_VAR, MODE_OFF) or MODE_OFF).strip().lower()
    return raw if raw in MODES else MODE_OFF


def enabled() -> bool:
    return ingestion_mode() != MODE_OFF


def writes_enabled(mode: str | None = None) -> bool:
    return (mode or ingestion_mode()) in (MODE_WRITE, MODE_AUTHORITATIVE)


def publication_authoritative(mode: str | None = None) -> bool:
    return (mode or ingestion_mode()) == MODE_AUTHORITATIVE


def run_game_driven_ingestion(
    reference_date: date,
    *,
    mode: str | None = None,
    time_budget_seconds: float | None = None,
    sync_run_id=None,
    job_name: str | None = None,
    explicit_game_pks=None,
    only_game_pks=None,
    expected_plan_fingerprint: str | None = None,
    include_backfill: bool = False,
    max_games: int | None = None,
    process_game=None,
    fetch_boxscore=None,
    plan_game=None,
) -> dict:
    """Run one game-driven ingestion pass and return its full run report.

    ``process_game`` and ``fetch_boxscore`` exist so the lane can be exercised
    without the network; production leaves them ``None`` and the canonical
    ``services.sync`` implementations (and therefore the single canonical MLB
    client) are used.
    """
    mode = (mode or ingestion_mode())
    if mode not in MODES:
        mode = MODE_OFF
    started = time.monotonic()
    report = _empty_report(reference_date, mode)
    if mode == MODE_OFF:
        report['status'] = 'disabled'
        return report

    exclusive = only_game_pks is not None
    planner_started = time.monotonic()
    try:
        plan = planner.plan_game_work(
            reference_date,
            explicit_game_pks=explicit_game_pks,
            only_game_pks=only_game_pks,
            include_backfill=include_backfill,
        )
    except ValueError as exc:
        report['status'] = STATUS_SCOPE_INVALID
        report['scope_error'] = type(exc).__name__
        report['planner_seconds'] = round(time.monotonic() - planner_started, 3)
        return report
    report['planner_seconds'] = round(time.monotonic() - planner_started, 3)
    report['plan'] = {
        key: value for key, value in plan.items() if key != 'items'
    }
    items = list(plan['items'])
    if max_games is not None:
        items = items[: max(int(max_games), 0)]
    report['games_planned'] = len(items)
    report['games_discovered'] = plan['games_discovered']
    report['newly_final_count'] = plan['newly_final_count']
    report['corrected_final_count'] = plan['corrected_final_count']
    report['retry_count'] = plan['retry_count']
    report['schedule_authority_missing'] = len(plan['schedule_authority_missing'])
    report['finality_conflicts'] = len(plan['finality_conflicts'])

    for field in _SCOPE_REPORT_FIELDS:
        report[field] = plan[field]

    # ── Exact-scope preflight ───────────────────────────────────────────────
    # BEFORE any MLB request and before any write. Recomputed here from the
    # items THIS RUN will actually execute rather than trusting the planner's
    # own self-report: a guard that believes the component it guards cannot
    # catch that component being wrong.
    if exclusive:
        executing = sorted({item.game_pk for item in items})
        requested = set(plan['requested_game_pks'])
        unexpected = sorted(set(executing) - requested)
        missing = sorted(requested - set(executing))
        report['planned_game_pks'] = executing
        report['planned_game_count'] = len(executing)
        report['unexpected_planned_game_pks'] = unexpected
        report['missing_requested_game_pks'] = missing
        report['execution_scope_exact_match'] = not unexpected and not missing

        if unexpected or missing:
            report['status'] = STATUS_SCOPE_MISMATCH
            report['scope_error'] = (
                SCOPE_ERROR_UNEXPECTED_GAME if unexpected
                else SCOPE_ERROR_MISSING_GAME
            )
            report['planner_seconds'] = round(
                time.monotonic() - planner_started, 3
            )
            report['plan'] = {
                key: value for key, value in plan.items() if key != 'items'
            }
            return report

    # An exclusive write must apply a plan a human reviewed. Without the
    # reviewed fingerprint there is nothing to compare against, so it refuses
    # before fetching rather than writing something unreviewed.
    if exclusive and writes_enabled(mode) and not expected_plan_fingerprint:
        report['status'] = STATUS_PLAN_AUTHORIZATION_REQUIRED
        report['scope_error'] = SCOPE_ERROR_FINGERPRINT_REQUIRED
        report['planner_seconds'] = round(time.monotonic() - planner_started, 3)
        return report

    handlers = _resolve_handlers(process_game, fetch_boxscore, plan_game)

    # ── Reviewed-plan authorization ─────────────────────────────────────────
    # An exclusive write recomputes the plan from CURRENT database state and
    # CURRENT official evidence, compares it to the fingerprint a human
    # reviewed, and only then applies. A mismatch — whether the stored rows or
    # the official line moved since review — refuses before the first mutation.
    if exclusive and writes_enabled(mode):
        authorization = _authorize_reviewed_plan(
            items, handlers=handlers, report=report,
            expected_plan_fingerprint=expected_plan_fingerprint,
        )
        if not authorization['authorized']:
            report['status'] = STATUS_PLAN_FINGERPRINT_MISMATCH
            report['scope_error'] = SCOPE_ERROR_FINGERPRINT_MISMATCH
            report['expected_plan_fingerprint'] = expected_plan_fingerprint
            report['observed_plan_fingerprint'] = authorization['observed']
            report['planner_seconds'] = round(
                time.monotonic() - planner_started, 3
            )
            db.session.rollback()
            return report
        report['expected_plan_fingerprint'] = expected_plan_fingerprint
        report['authorized_plan_fingerprint'] = authorization['observed']

    for index, item in enumerate(items):
        if _budget_exhausted(started, time_budget_seconds):
            report['budget_stop_triggered'] = True
            remaining = items[index:]
            _record_budget_stop(
                remaining,
                mode=mode,
                reference_date=reference_date,
                sync_run_id=sync_run_id,
                report=report,
            )
            break

        outcome = _process_one_game(
            item,
            mode=mode,
            handlers=handlers,
            sync_run_id=sync_run_id,
            job_name=job_name,
            report=report,
        )
        report['games'].append(outcome)

    if not writes_enabled(mode):
        # Shadow mode reads only. Discard the read transaction explicitly so the
        # lane cannot leave anything pending behind it.
        db.session.rollback()

    report['games_remaining'] = max(
        report['games_planned'] - report['games_attempted'], 0
    )
    for key in (
        'fetch_seconds', 'extraction_seconds', 'persistence_seconds',
        'checkpoint_seconds',
    ):
        report[key] = round(report[key], 3)
    report['changed_fields_counts'] = dict(
        sorted(report['changed_fields_counts'].items())
    )
    report['mutation_category_counts'] = dict(
        sorted(report['mutation_category_counts'].items())
    )
    for mapping in (
        'pitcher_identity_action_counts',
        'pitcher_identity_changed_fields_counts',
        'suppressed_current_state_field_counts',
    ):
        report[mapping] = dict(sorted((report.get(mapping) or {}).items()))
    # Working set, not report content.
    report.pop('_identity_pitcher_ids', None)
    report['affected_pitcher_mlb_ids'] = sorted(
        report.pop('_affected_pitcher_mlb_ids', set())
    )
    report['affected_team_ids'] = sorted(report.pop('_affected_team_ids', set()))
    report['reconciliation_plan_fingerprint'] = reconciliation.plan_fingerprint(
        [row for entry in report['games'] for row in (entry.get('rows') or ())]
    )
    # The run-level identity a reviewer approves. Per-game fingerprints already
    # reached the report; without this the complete plan could only be reviewed
    # game by game, which is not what an R4 write authorization compares against.
    report['complete_reconciliation_fingerprint'] = (
        report['reconciliation_plan_fingerprint']
    )
    report['elapsed_seconds'] = round(time.monotonic() - started, 3)
    report['remaining_budget_seconds'] = (
        None if time_budget_seconds is None
        else round(max(time_budget_seconds - (time.monotonic() - started), 0.0), 3)
    )
    report['status'] = 'complete' if not report['budget_stop_triggered'] else 'incomplete'
    return report


# ── One game ────────────────────────────────────────────────────────────────


def _process_one_game(item, *, mode, handlers, sync_run_id, job_name, report) -> dict:
    game_started = time.monotonic()
    report['games_attempted'] += 1
    outcome = {
        'game_pk': item.game_pk,
        'represented_date': item.represented_date.isoformat()
        if item.represented_date else None,
        'candidate_reason': item.candidate_reason,
        'criticality': item.criticality,
        'attempt_number': (item.attempt_count or 0) + 1,
        'status': None,
        'source_revision': None,
        'appearances_extracted': 0,
        'relief_appearances': 0,
        'inserted': 0,
        'updated': 0,
        'unchanged': 0,
        'blocked': 0,
        'changed_fields_counts': {},
        'mutation_category_counts': {},
        'statistical_corrections': 0,
        'authority_reconciliations': 0,
        'provenance_only_updates': 0,
        'canonical_outs_corrections': 0,
        'derived_companion_fields_applied': 0,
        'derived_companion_differences_ignored': 0,
        'pitcher_identity_rows_examined': 0,
        'pitcher_identity_mutations': 0,
        'pitcher_identity_unchanged': 0,
        'pitcher_identity_creations': 0,
        'pitcher_identity_reactivations': 0,
        'pitcher_identity_metadata_updates': 0,
        'pitcher_identity_blocked': 0,
        'historical_current_state_changes_suppressed': 0,
        'appearance_team_mutations': 0,
        'complete_mutation_count': 0,
        'pitcher_identity_action_counts': {},
        'pitcher_identity_changed_fields_counts': {},
        'suppressed_current_state_field_counts': {},
        'pitcher_identity_unique_pitchers_affected': 0,
        'reconciliation_plan_fingerprint': None,
        'complete_reconciliation_fingerprint': None,
        'rows': [],
        'impact': None,
        'optional_source_domains': {
            'final_play_by_play': {
                'status': 'not_requested',
                'publication_affected': False,
            },
        },
        'elapsed_seconds': 0.0,
        'error_class': None,
    }

    work_item = None
    try:
        if writes_enabled(mode):
            existed = GameIngestionWorkItem.query.filter_by(
                mlb_game_pk=item.game_pk
            ).first() is not None
            work_item = _claim_work_item(item, sync_run_id=sync_run_id)
            _record_effect(
                report, 'work_items_updated' if existed else 'work_items_created',
            )

        fetch_started = time.monotonic()
        game_payload, boxscore = handlers['fetch'](item)
        report['fetch_seconds'] += time.monotonic() - fetch_started
        report['games_fetched'] += 1

        extract_started = time.monotonic()
        appearances = handlers['extract'](item, game_payload, boxscore)
        report['extraction_seconds'] += time.monotonic() - extract_started

        if not appearances:
            raise _IngestionFailure(
                ERROR_APPEARANCE_EXTRACTION_FAILED,
                'final game produced no pitching appearances',
            )

        revision = extraction.appearance_set_fingerprint(appearances)
        outcome['source_revision'] = revision
        outcome['appearances_extracted'] = len(appearances)
        outcome['relief_appearances'] = extraction.relief_appearance_count(appearances)
        report['rows_expected'] += len(appearances)
        outcome['impact'] = continuous_impact.build_game_impact(appearances)
        report.setdefault('_affected_pitcher_mlb_ids', set()).update(
            outcome['impact']['affected_pitcher_mlb_ids']
        )
        report.setdefault('_affected_team_ids', set()).update(
            outcome['impact']['affected_team_ids']
        )

        if not writes_enabled(mode):
            # Shadow asks the canonical planner, through the canonical writer's
            # planning mode, what the writer would do. It is the same code
            # reaching the same verdict — not a second comparator.
            plan_started = time.monotonic()
            projected = handlers['plan'](item, game_payload, boxscore)
            report['persistence_seconds'] += time.monotonic() - plan_started
            _apply_plan_outcome(outcome, report, projected)
            outcome['status'] = 'projected'
            report['games_completed'] += 1
            return outcome

        persist_started = time.monotonic()
        persisted = handlers['persist'](
            item, game_payload, boxscore, sync_run_id=sync_run_id
        )
        report['persistence_seconds'] += time.monotonic() - persist_started
        # Counted from what the writer reported writing, at the moment it wrote.
        persisted_summary = persisted.get('summary') or {}
        _record_effect(
            report, 'game_log_rows_written',
            int(persisted_summary.get('rows_inserted') or 0)
            + int(persisted_summary.get('rows_updated') or 0),
        )
        _record_effect(
            report, 'pitcher_rows_written',
            int(persisted_summary.get('pitcher_identity_mutations') or 0),
        )
        _record_effect(
            report, 'appearance_team_rows_written',
            int(persisted_summary.get('appearance_team_mutations') or 0),
        )
        _record_effect(
            report, 'correction_provenance_rows_written',
            int(persisted_summary.get('provenance_only_updates') or 0)
            + int(persisted_summary.get('statistical_corrections') or 0),
        )

        if handlers.get('process_optional') is not None:
            optional_payload = handlers['fetch_optional'](item)
            outcome['optional_source_domains']['final_play_by_play'] = (
                handlers['process_optional'](
                    item,
                    game_payload,
                    boxscore,
                    optional_payload,
                    sync_run_id=sync_run_id,
                    job_name=job_name,
                )
            )

        reconciled = _verify_game_completeness(item, appearances)
        outcome['impact'] = continuous_impact.build_game_impact(appearances)
        _apply_plan_outcome(outcome, report, persisted)
        if reconciled['reconciled'] != len(appearances):
            raise _IngestionFailure(
                ERROR_RECONCILIATION_FAILED,
                'expected appearance rows did not all reconcile',
            )
        if persisted['unsafe']:
            raise _IngestionFailure(
                ERROR_CORRECTION_CONFLICT,
                'a governed correction could not be applied safely',
            )
        if persisted['unresolved_pitchers']:
            raise _IngestionFailure(
                ERROR_STARTER_IDENTITY_UNRESOLVED,
                'a pitching line could not be resolved to a pitcher',
            )

        checkpoint_started = time.monotonic()
        correction_applied = (
            work_item.source_revision is not None
            and work_item.source_revision != revision
        )
        _complete_work_item(
            work_item,
            revision=revision,
            rows_expected=len(appearances),
            rows_reconciled=reconciled['reconciled'],
            relief_rows=outcome['relief_appearances'],
            correction_applied=correction_applied,
            proof={
                'appearance_rows': len(appearances),
                'reconciled_rows': reconciled['reconciled'],
                'relief_rows': outcome['relief_appearances'],
                'starters': extraction.starter_identity(appearances),
                'inserted': persisted['inserted'],
                'updated': persisted['updated'],
            },
        )
        db.session.commit()
        _record_effect(report, 'work_items_completed')
        _record_effect(report, 'checkpoints_advanced')
        _record_effect(report, 'commits_performed')
        report['checkpoint_seconds'] += time.monotonic() - checkpoint_started

        report['games_completed'] += 1
        if correction_applied:
            report['corrections_applied'] += 1
            outcome['status'] = 'completed_with_correction'
        else:
            outcome['status'] = GameIngestionWorkItem.STATUS_COMPLETED
        return outcome

    except Exception as exc:  # noqa: BLE001 - every failure is classified below
        db.session.rollback()
        error_class = _classify_error(exc)
        outcome['error_class'] = error_class
        outcome['status'] = _record_failure(
            item,
            error_class=error_class,
            mode=mode,
            sync_run_id=sync_run_id,
            job_name=job_name,
            report=report,
        )
        report['games_failed'] += 1
        report['failure_classes'][error_class] = (
            report['failure_classes'].get(error_class, 0) + 1
        )
        if item.criticality != GameIngestionWorkItem.CRITICALITY_BEST_EFFORT:
            report['critical_games_unresolved'] += 1
        else:
            report['best_effort_games_deferred'] += 1
        # The exception text is never logged: it can carry paths and payload
        # fragments. The safe class and the game id are enough to act on.
        logger.warning(
            'Game-driven ingestion failed for game_pk=%s class=%s attempt=%s',
            item.game_pk, error_class, outcome['attempt_number'],
        )
        return outcome
    finally:
        outcome['elapsed_seconds'] = round(time.monotonic() - game_started, 3)


# ── Work-item state machine ─────────────────────────────────────────────────


def _claim_work_item(item, *, sync_run_id) -> GameIngestionWorkItem:
    work_item = GameIngestionWorkItem.query.filter_by(
        mlb_game_pk=item.game_pk
    ).first()
    now = utc_now_naive()
    if work_item is None:
        work_item = GameIngestionWorkItem(
            mlb_game_pk=item.game_pk,
            represented_date=item.represented_date,
        )
        db.session.add(work_item)

    work_item.represented_date = item.represented_date
    work_item.game_date = item.game_date
    work_item.game_type = item.game_type
    work_item.game_datetime = item.game_datetime
    work_item.home_team_id = item.home_team_id
    work_item.away_team_id = item.away_team_id
    work_item.candidate_reason = item.candidate_reason
    work_item.criticality = item.criticality
    work_item.finality_state = item.finality_state
    work_item.source_authority = item.source_authority
    work_item.status = GameIngestionWorkItem.STATUS_IN_PROGRESS
    work_item.attempt_count = (work_item.attempt_count or 0) + 1
    work_item.first_attempted_at = work_item.first_attempted_at or now
    work_item.last_attempted_at = now
    work_item.error_class = None
    work_item.sync_run_id = sync_run_id
    db.session.flush()
    return work_item


def _complete_work_item(
    work_item, *, revision, rows_expected, rows_reconciled, relief_rows,
    correction_applied, proof,
):
    work_item.status = GameIngestionWorkItem.STATUS_COMPLETED
    work_item.completed_at = utc_now_naive()
    work_item.source_revision = revision
    work_item.rows_expected = rows_expected
    work_item.rows_reconciled = rows_reconciled
    work_item.relief_rows_reconciled = relief_rows
    work_item.error_class = None
    if correction_applied:
        work_item.correction_count = (work_item.correction_count or 0) + 1
    work_item.completion_proof = proof
    db.session.add(work_item)
    db.session.flush()


def _record_failure(item, *, error_class, mode, sync_run_id, job_name, report=None) -> str:
    """Persist a failed attempt. Never marks a game complete."""
    if not writes_enabled(mode):
        return 'projection_failed'

    semantics = FAILURE_SEMANTICS.get(error_class, FAILURE_SEMANTICS[ERROR_UNEXPECTED])
    work_item = GameIngestionWorkItem.query.filter_by(
        mlb_game_pk=item.game_pk
    ).first()
    now = utc_now_naive()
    if work_item is None:
        work_item = GameIngestionWorkItem(
            mlb_game_pk=item.game_pk,
            represented_date=item.represented_date,
            game_date=item.game_date,
            game_type=item.game_type,
            home_team_id=item.home_team_id,
            away_team_id=item.away_team_id,
            game_datetime=item.game_datetime,
            candidate_reason=item.candidate_reason,
            criticality=item.criticality,
            finality_state=item.finality_state,
            source_authority=item.source_authority,
            attempt_count=1,
            first_attempted_at=now,
        )
        db.session.add(work_item)
    else:
        # The claiming flush was rolled back with the failed transaction, so the
        # attempt is counted here — otherwise a repeatedly failing game would
        # never reach the retry limit.
        work_item.attempt_count = (work_item.attempt_count or 0) + 1
        work_item.first_attempted_at = work_item.first_attempted_at or now

    attempt_count = work_item.attempt_count or 1
    retryable = semantics['retryable'] and (
        error_class == ERROR_BUDGET_EXHAUSTED or attempt_count < RETRY_LIMIT
    )
    work_item.status = (
        GameIngestionWorkItem.STATUS_RETRYABLE_FAILURE if retryable
        else GameIngestionWorkItem.STATUS_TERMINAL_FAILURE
    )
    work_item.last_attempted_at = now
    work_item.error_class = error_class
    work_item.completed_at = None
    work_item.sync_run_id = sync_run_id
    db.session.add(work_item)
    db.session.commit()
    _record_effect(report or {}, 'work_items_updated')
    _record_effect(report or {}, 'commits_performed')

    if not retryable:
        dead_letter.record_failure(
            GAME_INGESTION_FAILURE_ENTITY_TYPE,
            f'game-driven ingestion retry limit reached: {error_class}',
            entity_ref=item.game_pk,
            payload={
                'game_pk': item.game_pk,
                'represented_date': (
                    item.represented_date.isoformat() if item.represented_date else None
                ),
                'candidate_reason': item.candidate_reason,
                'criticality': item.criticality,
                'error_class': error_class,
                'attempt_count': attempt_count,
                'retry_limit': RETRY_LIMIT,
            },
            sync_run_id=sync_run_id,
            job_name=job_name,
        )
        db.session.commit()
        _record_effect(report or {}, 'dead_letters_created')
        _record_effect(report or {}, 'commits_performed')
    return work_item.status


def _record_budget_stop(remaining, *, mode, reference_date, sync_run_id, report):
    """Budget exhaustion leaves resumable state — it never dead-letters a tail."""
    critical = 0
    best_effort = 0
    for item in remaining:
        if item.criticality == GameIngestionWorkItem.CRITICALITY_BEST_EFFORT:
            best_effort += 1
        else:
            critical += 1
    report['critical_games_unresolved'] += critical
    report['best_effort_games_deferred'] += best_effort
    report['budget_stop'] = {
        'reference_date': reference_date.isoformat(),
        'games_remaining': len(remaining),
        'critical_games_remaining': critical,
        'best_effort_games_remaining': best_effort,
    }

    if not writes_enabled(mode):
        return

    existing = {
        row.mlb_game_pk: row
        for row in (
            GameIngestionWorkItem.query
            .filter(GameIngestionWorkItem.mlb_game_pk.in_(
                [item.game_pk for item in remaining] or [-1]
            ))
            .all()
        )
    }
    for item in remaining:
        work_item = existing.get(item.game_pk)
        if work_item is None:
            work_item = GameIngestionWorkItem(
                mlb_game_pk=item.game_pk,
                represented_date=item.represented_date,
                game_date=item.game_date,
                game_type=item.game_type,
                home_team_id=item.home_team_id,
                away_team_id=item.away_team_id,
                game_datetime=item.game_datetime,
                candidate_reason=item.candidate_reason,
                criticality=item.criticality,
                finality_state=item.finality_state,
                source_authority=item.source_authority,
                attempt_count=0,
            )
            db.session.add(work_item)
        elif work_item.status == GameIngestionWorkItem.STATUS_COMPLETED:
            # A completed game is never demoted by a later run's budget stop.
            continue
        work_item.status = GameIngestionWorkItem.STATUS_PLANNED
        work_item.criticality = item.criticality
        work_item.candidate_reason = item.candidate_reason
        work_item.error_class = ERROR_BUDGET_EXHAUSTED
        _record_effect(report, 'work_items_updated')
    db.session.commit()
    _record_effect(report, 'commits_performed')


# ── Reconciliation ──────────────────────────────────────────────────────────


def _verify_game_completeness(item, appearances) -> dict:
    """Count the canonical GameLog rows that actually reconcile this game."""
    stored = {
        row.pitcher_id: row
        for row in GameLog.query.filter(GameLog.mlb_game_pk == item.game_pk).all()
    }
    if not stored:
        return {'reconciled': 0, 'expected': len(appearances)}
    pitcher_ids = {
        pitcher.mlb_id: pitcher.id
        for pitcher in Pitcher.query.filter(
            Pitcher.id.in_(list(stored) or [-1])
        ).all()
    }
    reconciled = 0
    for record in appearances:
        local_id = pitcher_ids.get(record['pitcher_mlb_id'])
        row = stored.get(local_id) if local_id else None
        if row is None:
            continue
        if int(row.innings_pitched_outs or 0) != int(record['outs_recorded']):
            continue
        reconciled += 1
    return {'reconciled': reconciled, 'expected': len(appearances)}


def _authorize_reviewed_plan(items, *, handlers, report, expected_plan_fingerprint):
    """Recompute the row plan read-only and compare it to the reviewed one.

    Runs the canonical planning path over every item — no writes — and
    fingerprints the result. Returns whether the observed plan is exactly the
    reviewed plan. Nothing is mutated either way; the caller refuses on a
    mismatch before the first write.
    """
    rows = []
    for item in items:
        game_payload, boxscore = handlers['fetch'](item)
        report['games_fetched'] += 1
        projected = handlers['plan'](item, game_payload, boxscore)
        rows.extend(_safe_row_entries(projected.get('plan') or ()))
    db.session.rollback()

    observed = reconciliation.plan_fingerprint(rows)
    return {
        'authorized': observed == expected_plan_fingerprint,
        'observed': observed,
    }


def _apply_plan_outcome(outcome, report, result) -> None:
    """Fold one game's canonical reconciliation result into the run report.

    Shadow and write pass through here identically, so a projected run and an
    applied run are counted by the same code from the same plan shape.
    """
    summary = result.get('summary') or {}
    outcome['inserted'] = int(summary.get('rows_inserted') or 0)
    outcome['updated'] = int(summary.get('rows_updated') or 0)
    outcome['unchanged'] = int(summary.get('rows_unchanged') or 0)
    outcome['blocked'] = int(summary.get('rows_blocked') or 0)
    outcome['changed_fields_counts'] = dict(
        summary.get('changed_fields_counts') or {}
    )
    outcome['mutation_category_counts'] = dict(
        summary.get('mutation_category_counts') or {}
    )
    outcome['statistical_corrections'] = int(
        summary.get('statistical_corrections') or 0
    )
    outcome['authority_reconciliations'] = int(
        summary.get('authority_reconciliations') or 0
    )
    outcome['provenance_only_updates'] = int(
        summary.get('provenance_only_updates') or 0
    )
    outcome['canonical_outs_corrections'] = int(
        summary.get('canonical_outs_corrections') or 0
    )
    outcome['derived_companion_fields_applied'] = int(
        summary.get('derived_companion_fields_applied') or 0
    )
    outcome['derived_companion_differences_ignored'] = int(
        summary.get('derived_companion_differences_ignored') or 0
    )
    outcome['reconciliation_plan_fingerprint'] = summary.get(
        'reconciliation_plan_fingerprint'
    )
    outcome['complete_reconciliation_fingerprint'] = summary.get(
        'complete_reconciliation_fingerprint'
    )
    for field in _IDENTITY_COUNTER_FIELDS:
        outcome[field] = int(summary.get(field) or 0)
    for mapping in (
        'pitcher_identity_action_counts',
        'pitcher_identity_changed_fields_counts',
        'suppressed_current_state_field_counts',
    ):
        outcome[mapping] = dict(summary.get(mapping) or {})
    outcome['pitcher_identity_unique_pitchers_affected'] = int(
        summary.get('pitcher_identity_unique_pitchers_affected') or 0
    )
    outcome['rows'] = _safe_row_entries(result.get('plan') or ())

    report['rows_inserted'] += outcome['inserted']
    report['rows_updated'] += outcome['updated']
    report['rows_unchanged'] += outcome['unchanged']
    report['rows_blocked'] += outcome['blocked']
    report['statistical_corrections'] += outcome['statistical_corrections']
    report['authority_reconciliations'] += outcome['authority_reconciliations']
    report['provenance_only_updates'] += outcome['provenance_only_updates']
    report['canonical_outs_corrections'] += outcome['canonical_outs_corrections']
    report['derived_companion_fields_applied'] += (
        outcome['derived_companion_fields_applied']
    )
    report['derived_companion_differences_ignored'] += (
        outcome['derived_companion_differences_ignored']
    )
    # Same number under the name that says what it PREVENTED. Kept as its own
    # key so an operator reading a report can find it either way.
    report['decimal_only_updates_suppressed'] = (
        report['derived_companion_differences_ignored']
    )
    for field in _IDENTITY_COUNTER_FIELDS:
        report[field] = report.get(field, 0) + outcome[field]
    for mapping in (
        'pitcher_identity_action_counts',
        'pitcher_identity_changed_fields_counts',
        'suppressed_current_state_field_counts',
    ):
        target = report.setdefault(mapping, {})
        for key, count in (outcome[mapping] or {}).items():
            target[key] = target.get(key, 0) + count
    # Counted across the run, not summed per game: one pitcher appearing in
    # three games is one affected pitcher.
    report.setdefault('_identity_pitcher_ids', set()).update(
        row['pitcher_mlb_id'] for row in outcome['rows']
        if row.get('pitcher_identity_action')
        in _IDENTITY_MUTATING_ACTIONS and row.get('pitcher_mlb_id') is not None
    )
    report['pitcher_identity_unique_pitchers_affected'] = len(
        report['_identity_pitcher_ids']
    )
    for field, count in (outcome['changed_fields_counts'] or {}).items():
        report['changed_fields_counts'][field] = (
            report['changed_fields_counts'].get(field, 0) + count
        )
    for category, count in (outcome['mutation_category_counts'] or {}).items():
        report['mutation_category_counts'][category] = (
            report['mutation_category_counts'].get(category, 0) + count
        )


def _safe_row_entries(plan) -> list[dict]:
    """Per-row structured report. Governed baseball fields only.

    Enough to compare a shadow run against a write run field by field, with no
    raw payload, path, credential, or exception text anywhere in it.
    """
    rows = [
        {
            'game_pk': entry.get('game_pk'),
            'pitcher_mlb_id': entry.get('pitcher_mlb_id'),
            'action': entry.get('action'),
            'changed_fields': list(entry.get('changed_fields') or ()),
            'changed_field_count': entry.get('changed_field_count', 0),
            'mutation_categories': list(entry.get('mutation_categories') or ()),
            'is_statistical_correction': bool(
                entry.get('is_statistical_correction')
            ),
            'affects_published_evidence': bool(
                entry.get('affects_published_evidence')
            ),
            'is_provenance_only': bool(entry.get('is_provenance_only')),
            'governed_and_safe': bool(entry.get('governed_and_safe')),
            'blocked_reason': entry.get('blocked_reason'),
            'mutation_digest': entry.get('mutation_digest'),
            'semantic_changed_fields': list(
                entry.get('semantic_changed_fields') or ()
            ),
            'applied_changed_fields': list(
                entry.get('applied_changed_fields') or ()
            ),
            'derived_companion_fields': list(
                entry.get('derived_companion_fields') or ()
            ),
            'derived_companion_differences_ignored': list(
                entry.get('derived_companion_differences_ignored') or ()
            ),
            'appearance_team_reason': entry.get('appearance_team_reason'),
            # Target state, for the realization proof. Field NAMES are governed
            # vocabulary and safe to report; the intended VALUES never leave the
            # process — only their digest does.
            'target_fields': list(entry.get('target_fields') or ()),
            'target_state_digest': entry.get('target_state_digest'),
            'stored_state_digest': entry.get('stored_state_digest'),
            'difference_classifications': list(
                entry.get('difference_classifications') or ()
            ),
            # Fields this source shape could not compare at all. Absence here
            # is not agreement — it is that the lane never looked.
            'uncomparable_fields': list(entry.get('uncomparable_fields') or ()),
            **pitcher_identity.safe_row_entry(entry.get('pitcher_identity')),
        }
        for entry in plan or ()
    ]
    # Deterministic output ordering, independent of payload order.
    rows.sort(key=lambda row: (row['game_pk'] or 0, row['pitcher_mlb_id'] or 0))
    return rows


# ── Handlers (canonical implementations, injectable for tests) ──────────────


def _resolve_handlers(process_game, fetch_boxscore, plan_game=None) -> dict:
    if process_game is not None and fetch_boxscore is not None:
        return {
            'fetch': fetch_boxscore,
            'extract': _default_extract,
            'persist': process_game,
            'plan': plan_game if plan_game is not None else process_game,
        }

    # Lazy import: services.sync imports many services, so importing it at
    # module load would be circular. The canonical MLB client, the canonical
    # box-score parser, and the canonical idempotent GameLog upsert all come
    # from there — this module introduces none of its own.
    from services import sync as sync_service

    def _fetch(item):
        game_payload = _game_payload(item)
        boxscore = sync_service.mlb_client.get_game_boxscore(item.game_pk)
        return game_payload, boxscore

    def _fetch_optional(item):
        try:
            return {
                'play_by_play': sync_service.mlb_client.get_game_play_by_play(
                    item.game_pk
                ),
                'error': None,
            }
        except Exception as exc:  # noqa: BLE001 - optional domain is reported
            return {'play_by_play': None, 'error': exc}

    handlers_map = {}

    def _reconcile(item, game_payload, boxscore, *, sync_run_id=None,
                   plan_only=False):
        result = sync_service.process_completed_game_for_postgame_refresh(
            game_payload,
            schedule_date=item.game_date or item.represented_date,
            sync_run_id=sync_run_id,
            # Reuse the box score already fetched for this item so an authorized
            # write applies the exact evidence its plan was computed from, and
            # so a run makes one request per game rather than two.
            boxscore=boxscore,
            # This lane owns its own completion contract (the work item), so a
            # game inside the correction horizon must be re-read even when the
            # postgame marker already says fully processed. Every write below
            # remains idempotent.
            force=True,
            plan_only=plan_only,
        )
        return {
            'inserted': result.get('logs_added', 0),
            'updated': result.get('logs_corrected', 0),
            'unsafe': result.get('correction_attempts_failed', 0),
            'unresolved_pitchers': result.get('pitcher_resolution_failures', 0),
            'plan': result.get('reconciliation_plan') or [],
            'summary': result.get('reconciliation_summary') or {},
        }

    def _persist(item, game_payload, boxscore, *, sync_run_id=None):
        return _reconcile(
            item, game_payload, boxscore, sync_run_id=sync_run_id,
            plan_only=False,
        )

    def _plan(item, game_payload, boxscore):
        return _reconcile(item, game_payload, boxscore, plan_only=True)

    handlers_map['fetch'] = _fetch
    handlers_map['fetch_optional'] = _fetch_optional
    handlers_map['persist'] = _persist
    handlers_map['plan'] = _plan

    def _process_optional(
        item,
        game_payload,
        boxscore,
        optional_payload,
        *,
        sync_run_id=None,
        job_name=None,
    ):
        from services.play_by_play_foundation import (
            process_final_play_by_play_foundation,
        )

        result = process_final_play_by_play_foundation(
            game_payload,
            boxscore=boxscore,
            play_by_play=optional_payload.get('play_by_play'),
            play_by_play_error=optional_payload.get('error'),
            game_date=item.game_date or item.represented_date,
            sync_run_id=sync_run_id,
            job_name=job_name,
        )
        result['publication_affected'] = False
        return result

    handlers_map['process_optional'] = _process_optional

    handlers_map['extract'] = _default_extract
    return handlers_map


def _default_extract(item, game_payload, boxscore):
    from services import sync as sync_service

    lines = sync_service._extract_pitching_lines_from_boxscore(boxscore)
    order = sync_service._pitcher_order_by_side(boxscore)
    return extraction.extract_game_appearances(
        game=game_payload,
        pitching_lines=lines,
        pitcher_order=order,
        game_date=item.game_date or item.represented_date,
    )


def _game_payload(item) -> dict:
    """The canonical game dict shape the existing postgame path already accepts."""
    return {
        'gamePk': item.game_pk,
        'gameType': item.game_type or 'R',
        'officialDate': (item.game_date or item.represented_date).isoformat(),
        'status': {
            'statusCode': 'F',
            'detailedState': 'Final',
            'abstractGameState': 'Final',
        },
        'teams': {
            'home': {'team': {'id': item.home_team_id}},
            'away': {'team': {'id': item.away_team_id}},
        },
        'source': planner.SOURCE_AUTHORITY_SCHEDULE_LEDGER,
    }


# ── Helpers ─────────────────────────────────────────────────────────────────


class _IngestionFailure(Exception):
    def __init__(self, error_class, message):
        super().__init__(message)
        self.error_class = error_class


def _classify_error(exc) -> str:
    error_class = getattr(exc, 'error_class', None)
    if error_class in FAILURE_SEMANTICS:
        return error_class
    if isinstance(exc, AppearanceExtractionError):
        return ERROR_APPEARANCE_EXTRACTION_FAILED
    name = type(exc).__name__.lower()
    if 'timeout' in name or 'connection' in name or 'http' in name or 'api' in name:
        return ERROR_GAME_FETCH_FAILED
    return ERROR_UNEXPECTED


def _budget_exhausted(started, time_budget_seconds) -> bool:
    if time_budget_seconds is None:
        return False
    return (time.monotonic() - started) >= float(time_budget_seconds)


def _empty_report(reference_date, mode) -> dict:
    return {
        'status': 'planned',
        'mode': mode,
        'reference_date': reference_date.isoformat(),
        'planner_seconds': 0.0,
        'games_discovered': 0,
        'games_planned': 0,
        'games_attempted': 0,
        'games_fetched': 0,
        'games_completed': 0,
        'games_failed': 0,
        'games_remaining': 0,
        'newly_final_count': 0,
        'corrected_final_count': 0,
        'retry_count': 0,
        'critical_games_unresolved': 0,
        'best_effort_games_deferred': 0,
        'schedule_authority_missing': 0,
        'finality_conflicts': 0,
        'fetch_seconds': 0.0,
        'extraction_seconds': 0.0,
        'persistence_seconds': 0.0,
        'checkpoint_seconds': 0.0,
        'rows_expected': 0,
        'rows_inserted': 0,
        'rows_updated': 0,
        'rows_unchanged': 0,
        'rows_blocked': 0,
        'changed_fields_counts': {},
        'mutation_category_counts': {},
        'statistical_corrections': 0,
        'authority_reconciliations': 0,
        'provenance_only_updates': 0,
        'canonical_outs_corrections': 0,
        'derived_companion_fields_applied': 0,
        'derived_companion_differences_ignored': 0,
        'decimal_only_updates_suppressed': 0,
        'pitcher_identity_rows_examined': 0,
        'pitcher_identity_mutations': 0,
        'pitcher_identity_unchanged': 0,
        'pitcher_identity_creations': 0,
        'pitcher_identity_reactivations': 0,
        'pitcher_identity_metadata_updates': 0,
        'pitcher_identity_blocked': 0,
        'historical_current_state_changes_suppressed': 0,
        'appearance_team_mutations': 0,
        'complete_mutation_count': 0,
        'pitcher_identity_unique_pitchers_affected': 0,
        'pitcher_identity_action_counts': {},
        'pitcher_identity_changed_fields_counts': {},
        'suppressed_current_state_field_counts': {},
        'identity_plan_version': pitcher_identity.IDENTITY_PLAN_VERSION,
        'complete_plan_version': reconciliation.COMPLETE_PLAN_VERSION,
        'innings_semantics_version': reconciliation.INNINGS_SEMANTICS_VERSION,
        'corrections_applied': 0,
        'budget_stop_triggered': False,
        'budget_stop': None,
        'failure_classes': {},
        'games': [],
        'plan': {},
        'parity_contract_version': reconciliation.PARITY_CONTRACT_VERSION,
        'reconciliation_plan_version': reconciliation.RECONCILIATION_PLAN_VERSION,
        'elapsed_seconds': 0.0,
        'remaining_budget_seconds': None,
        'execution_effects': _empty_execution_effects(mode),
    }


# ── Actual execution effects ────────────────────────────────────────────────
# Every counter here is incremented at the site where the effect actually
# happens — a work item being claimed, a checkpoint being completed, a commit
# being issued, a dead letter being recorded. None of them is derived from the
# mode name, so "shadow wrote nothing" is a measurement rather than a
# restatement of the configuration. In shadow those sites are unreachable, and
# the same counters go non-zero in write mode, which is what makes the zero
# meaningful.


def _empty_execution_effects(mode) -> dict:
    return {
        'writes_enabled': writes_enabled(mode),
        'publication_authoritative': publication_authoritative(mode),
        'game_log_rows_written': 0,
        'pitcher_rows_written': 0,
        'appearance_team_rows_written': 0,
        'correction_provenance_rows_written': 0,
        'work_items_created': 0,
        'work_items_updated': 0,
        'work_items_completed': 0,
        'checkpoints_advanced': 0,
        'dead_letters_created': 0,
        'commits_performed': 0,
    }


def _record_effect(report, field, amount=1) -> None:
    effects = report.get('execution_effects')
    if effects is None:
        return
    effects[field] = int(effects.get(field) or 0) + int(amount)
