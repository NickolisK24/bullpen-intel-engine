"""Bounded production-shadow execution for the completed sync pipeline.

The entrypoint plans current-date acquisition and can plan the SP-12 morning
contract once per baseball date. It consumes only non-publishing SP-04 through
SP-10 work. SP-11 publication and all legacy writers are deliberately outside
this worker registry.
"""

from __future__ import annotations

from datetime import datetime
import os
from zoneinfo import ZoneInfo

from sqlalchemy import func

from models.atomic_publication import AtomicPublicationCurrent
from models.canonical_impact import CanonicalImpactPlan
from models.derived_intelligence import DerivedIntelligenceCohort
from models.final_game_reconciliation import FinalGameMutation
from models.live_game_delta import LiveGameMutation
from models.pregame_context import PregameContextMutation
from models.source_observation import SourceFetchAttempt, SourceObservation
from models.sync_job import SyncJob
from models.sync_run import SyncRun
from services.adaptive_game_state import (
    POLLING_POLICY_VERSION,
    execute_game_state_poll,
)
from services.canonical_impact import execute_canonical_impact_job
from services.daily_reconciliation import plan_morning_reconciliation
from services.derived_intelligence import execute_derived_intelligence_job
from services.final_game_reconciliation import execute_final_game_job
from services.live_game_delta import execute_live_game_delta, plan_live_game_polls
from services.pregame_context import execute_pregame_context_job, plan_pregame_context_polls
from services.roster_transaction_authority import (
    execute_roster_job,
    execute_transaction_job,
)
from services.sync_jobs import (
    CANONICAL_ACTIVE_STATUSES,
    JobScopeType,
    JobType,
    enqueue_job,
    run_next_job,
)
from services.sync_pipeline_certification import (
    ActivationControls,
    EXPECTED_MIGRATION_HEAD,
    validate_activation_controls,
)
from services.migration_authority import (
    MigrationAuthorityError, read_current_heads, require_verify_only, verify_heads,
)
from utils.db import db
from utils.time import utc_now_naive


SHADOW_ENTRYPOINT_VERSION = 'production-shadow-v2'
SHADOW_JOB_FAMILY = 'sync_pipeline_shadow'
DEFAULT_MAX_JOBS = 24
MAX_JOBS_LIMIT = 100
ACQUISITION_JOB_RESERVE = 12
DOWNSTREAM_JOB_RESERVE = 6
SAFE_JOB_TYPES = (
    JobType.FETCH_SCHEDULE,
    JobType.FETCH_ROSTER,
    JobType.FETCH_TRANSACTIONS,
    JobType.FETCH_PREGAME_CONTEXT,
    JobType.FETCH_LIVE_GAME_DELTA,
    JobType.RECONCILE_FINAL_GAME,
    JobType.PROCESS_CANONICAL_IMPACT,
    JobType.PROCESS_DERIVED_INTELLIGENCE,
)
ROSTER_JOB_TYPES = (JobType.FETCH_ROSTER, JobType.FETCH_TRANSACTIONS)
DOWNSTREAM_JOB_TYPES = (
    JobType.PROCESS_CANONICAL_IMPACT,
    JobType.PROCESS_DERIVED_INTELLIGENCE,
)
FORBIDDEN_JOB_TYPES = frozenset({
    JobType.PUBLISH_DERIVED_COHORT.value,
    JobType.HANDOFF_PUBLICATION_CACHE.value,
    JobType.RUN_MORNING_RECONCILIATION.value,
    JobType.CHECK_BASEBALL_DATE_CLOSURE.value,
})


class ShadowConfigurationError(RuntimeError):
    pass


def current_migration_heads():
    return read_current_heads(db.engine)


def validate_shadow_controls(controls):
    violations = list(validate_activation_controls(controls))
    required = {
        'SYNC_PIPELINE_ENABLED': controls.pipeline_enabled,
        'SYNC_PIPELINE_SHADOW_MODE': controls.shadow_mode,
        'BASEBALLOS_LEGACY_PUBLICATION_ENABLED': controls.legacy_publication_enabled,
        'BASEBALLOS_LEGACY_SCHEDULERS_ENABLED': controls.legacy_schedulers_enabled,
    }
    forbidden = {
        'SYNC_PIPELINE_PUBLICATION_ENABLED': controls.publication_enabled,
        'SYNC_PIPELINE_MORNING_ENABLED': controls.morning_enabled,
        'SYNC_PIPELINE_CLOSURE_ENABLED': controls.closure_enabled,
    }
    violations.extend(f'{name}_must_be_true' for name, enabled in required.items() if not enabled)
    violations.extend(f'{name}_must_be_false' for name, enabled in forbidden.items() if enabled)
    return tuple(sorted(set(violations)))


def assert_shadow_ready(*, env=None, migration_head_reader=current_migration_heads):
    env = os.environ if env is None else env
    try:
        require_verify_only(env)
    except MigrationAuthorityError as exc:
        raise ShadowConfigurationError(str(exc)) from exc
    controls = ActivationControls.from_environment(env)
    violations = validate_shadow_controls(controls)
    if violations:
        raise ShadowConfigurationError(','.join(violations))
    try:
        heads = tuple(migration_head_reader())
        verify_heads(heads, EXPECTED_MIGRATION_HEAD)
    except MigrationAuthorityError as exc:
        raise ShadowConfigurationError(str(exc)) from exc
    return controls


def production_shadow_handlers():
    """Return the complete allowlist; publication can never be claimed here."""
    return {
        JobType.FETCH_SCHEDULE.value: execute_game_state_poll,
        JobType.FETCH_ROSTER.value: execute_roster_job,
        JobType.FETCH_TRANSACTIONS.value: execute_transaction_job,
        JobType.FETCH_PREGAME_CONTEXT.value: execute_pregame_context_job,
        JobType.FETCH_LIVE_GAME_DELTA.value: execute_live_game_delta,
        JobType.RECONCILE_FINAL_GAME.value: execute_final_game_job,
        JobType.PROCESS_CANONICAL_IMPACT.value: execute_canonical_impact_job,
        JobType.PROCESS_DERIVED_INTELLIGENCE.value: lambda job: (
            execute_derived_intelligence_job(
                job, publication_candidate_enabled=False,
            )
        ),
    }


def ensure_shadow_morning_plan(baseball_date, *, now=None, client=None):
    """Plan SP-12 once per date without closure or publication authority."""
    existing = (
        SyncRun.query
        .filter_by(
            source='sp12_morning_shadow',
            baseball_date=baseball_date,
            status='success',
        )
        .order_by(SyncRun.id.desc())
        .first()
    )
    if existing is not None:
        return {
            'created': False,
            'run_id': existing.id,
            'outcome': existing.outcome_json or {},
        }
    plan = plan_morning_reconciliation(
        baseball_date,
        client=client,
        now=now,
        shadow_mode=True,
        publication_candidate_enabled=False,
        closure_checks_enabled=False,
    )
    run = db.session.get(SyncRun, plan.run_id)
    return {
        'created': True,
        'run_id': plan.run_id,
        'outcome': run.outcome_json or {},
    }


def ensure_current_date_poll(baseball_date, *, now=None):
    now = now or utc_now_naive()
    active = SyncJob.query.filter(
        SyncJob.job_name == JobType.FETCH_SCHEDULE.value,
        SyncJob.product_date == baseball_date,
        SyncJob.status.in_(CANONICAL_ACTIVE_STATUSES),
    ).order_by(SyncJob.id).first()
    if active is not None:
        return active, False
    generation = now.replace(second=0, microsecond=0).isoformat()
    job = enqueue_job(
        job_type=JobType.FETCH_SCHEDULE,
        scope_type=JobScopeType.BASEBALL_DATE,
        scope_key=baseball_date.isoformat(),
        product_date=baseball_date,
        dedupe_key=(
            f'SHADOW_GAME_STATE:{baseball_date.isoformat()}:{generation}:'
            f'{POLLING_POLICY_VERSION}'
        ),
        priority=10,
        available_at=now,
        payload_schema_version=1,
        payload={
            'baseball_date': baseball_date,
            'game_pks': [],
            'reason': 'production_shadow_current_date',
            'policy_version': POLLING_POLICY_VERSION,
            'shadow_entrypoint_version': SHADOW_ENTRYPOINT_VERSION,
        },
        job_family=SHADOW_JOB_FAMILY,
    )
    return job, True


def shadow_queue_counts():
    relevant = tuple(item.value for item in SAFE_JOB_TYPES)
    rows = (
        db.session.query(SyncJob.job_name, SyncJob.status, func.count(SyncJob.id))
        .filter(SyncJob.job_name.in_(relevant))
        .group_by(SyncJob.job_name, SyncJob.status)
        .all()
    )
    result = {job_type: {} for job_type in relevant}
    for job_name, status, count in rows:
        result[job_name][status] = int(count)
    return result


def shadow_job_type_passes(*, max_jobs, include_morning):
    """Return bounded claim lanes with guaranteed downstream capacity."""
    acquisition_budget = min(max_jobs, ACQUISITION_JOB_RESERVE) if include_morning else 0
    remaining_budget = max_jobs - acquisition_budget
    downstream_budget = min(remaining_budget, DOWNSTREAM_JOB_RESERVE)
    general_budget = remaining_budget - downstream_budget
    passes = [ROSTER_JOB_TYPES] * acquisition_budget
    passes.extend([SAFE_JOB_TYPES] * general_budget)
    passes.extend([DOWNSTREAM_JOB_TYPES] * downstream_budget)
    return tuple(passes)


def run_production_shadow_cycle(
    *, now=None, baseball_date=None, max_jobs=DEFAULT_MAX_JOBS, worker_id=None,
    env=None, migration_head_reader=current_migration_heads, handlers=None,
    include_morning=False, morning_client=None,
):
    """Plan current-date work and drain a bounded, non-public worker allowlist."""
    controls = assert_shadow_ready(env=env, migration_head_reader=migration_head_reader)
    now = now or utc_now_naive()
    baseball_date = baseball_date or datetime.now(ZoneInfo('America/New_York')).date()
    if isinstance(max_jobs, bool) or not 1 <= int(max_jobs) <= MAX_JOBS_LIMIT:
        raise ValueError(f'max_jobs must be between 1 and {MAX_JOBS_LIMIT}.')
    max_jobs = int(max_jobs)
    worker_id = worker_id or f'production-shadow:{os.getpid()}'
    handlers = handlers or production_shadow_handlers()
    if set(handlers).intersection(FORBIDDEN_JOB_TYPES):
        raise ShadowConfigurationError('shadow_worker_contains_forbidden_job_type')
    if set(handlers) != {item.value for item in SAFE_JOB_TYPES}:
        raise ShadowConfigurationError('shadow_worker_allowlist_mismatch')

    started_at = utc_now_naive()
    pointer_before = db.session.get(AtomicPublicationCurrent, 1)
    pointer_before_id = pointer_before.publication_id if pointer_before else None
    queue_before = shadow_queue_counts()
    morning_plan = (
        ensure_shadow_morning_plan(
            baseball_date, now=now, client=morning_client,
        )
        if include_morning else None
    )
    seed_job, seed_created = ensure_current_date_poll(baseball_date, now=now)
    processed = []
    errors = []
    job_type_passes = shadow_job_type_passes(
        max_jobs=max_jobs, include_morning=include_morning,
    )
    for job_types in job_type_passes:
        try:
            settled = run_next_job(
                worker_id,
                handlers,
                job_types=job_types,
                lease_seconds=300,
            )
        except Exception as exc:
            errors.append({'error_type': type(exc).__name__, 'error': str(exc)[:500]})
            continue
        if settled is None:
            if job_types != SAFE_JOB_TYPES:
                settled = run_next_job(
                    worker_id,
                    handlers,
                    job_types=SAFE_JOB_TYPES,
                    lease_seconds=300,
                )
            if settled is None:
                break
        processed.append(settled.id)
        if settled.job_name == JobType.FETCH_SCHEDULE.value:
            plan_pregame_context_polls(
                now=now, baseball_dates=[baseball_date], commit=False,
            )
            plan_live_game_polls(now=now, commit=False)
            db.session.commit()

    pointer_after = db.session.get(AtomicPublicationCurrent, 1)
    pointer_after_id = pointer_after.publication_id if pointer_after else None
    if pointer_after_id != pointer_before_id:
        raise ShadowConfigurationError('shadow_cycle_changed_publication_pointer')

    jobs = SyncJob.query.filter(SyncJob.id.in_(processed or [-1])).order_by(SyncJob.id).all()
    run_ids = sorted({row.sync_run_id for row in jobs if row.sync_run_id is not None})
    observations = SourceObservation.query.filter(
        SourceObservation.sync_job_id.in_(processed or [-1])
    ).order_by(SourceObservation.id).all()
    result = {
        'entrypoint_version': SHADOW_ENTRYPOINT_VERSION,
        'status': 'partial' if errors else 'success',
        'baseball_date': baseball_date.isoformat(),
        'configuration_fingerprint': controls.fingerprint,
        'code_sha': (
            os.environ.get('SYNC_PIPELINE_DEPLOY_SHA')
            or os.environ.get('RENDER_GIT_COMMIT')
            or os.environ.get('GITHUB_SHA')
        ),
        'morning_plan': morning_plan,
        'queue_before': queue_before,
        'queue_after': shadow_queue_counts(),
        'seed_job_id': seed_job.id,
        'seed_job_created': seed_created,
        'processed_job_ids': processed,
        'processed_jobs': [
            {'id': row.id, 'job_type': row.job_name, 'scope_key': row.scope_key,
             'parent_job_id': row.parent_job_id, 'status': row.status,
             'sync_run_id': row.sync_run_id, 'result': row.result_json}
            for row in jobs
        ],
        'sync_run_ids': run_ids,
        'source_observation_ids': [row.id for row in observations],
        'source_observations': [
            {
                'id': row.id,
                'sync_job_id': row.sync_job_id,
                'sync_run_id': row.sync_run_id,
                'source_domain': row.subject.source_domain,
                'subject_type': row.subject.subject_type,
                'subject_key': row.subject.subject_key,
                'version_number': row.version_number,
                'outcome': row.outcome,
                'completeness': row.completeness,
                'observed_at': row.observed_at.isoformat(),
            }
            for row in observations
        ],
        'source_fetch_attempt_ids': [
            row.id for row in SourceFetchAttempt.query.filter(
                SourceFetchAttempt.sync_job_id.in_(processed or [-1])
            ).order_by(SourceFetchAttempt.id).all()
        ],
        'live_mutation_ids': [
            row.id for row in LiveGameMutation.query.filter(
                LiveGameMutation.created_at >= started_at
            ).order_by(LiveGameMutation.id).all()
        ],
        'pregame_mutation_ids': [
            row.id for row in PregameContextMutation.query.filter(
                PregameContextMutation.created_at >= started_at
            ).order_by(PregameContextMutation.id).all()
        ],
        'final_mutation_ids': [
            row.id for row in FinalGameMutation.query.filter(
                FinalGameMutation.created_at >= started_at
            ).order_by(FinalGameMutation.id).all()
        ],
        'impact_plan_ids': [
            row.id for row in CanonicalImpactPlan.query.filter(
                CanonicalImpactPlan.created_at >= started_at
            ).order_by(CanonicalImpactPlan.id).all()
        ],
        'cohort_ids': [
            row.id for row in DerivedIntelligenceCohort.query.filter(
                DerivedIntelligenceCohort.created_at >= started_at
            ).order_by(DerivedIntelligenceCohort.id).all()
        ],
        'publication_pointer_before': pointer_before_id,
        'publication_pointer_after': pointer_after_id,
        'errors': errors,
    }
    return result


__all__ = [
    'ACQUISITION_JOB_RESERVE', 'DEFAULT_MAX_JOBS', 'DOWNSTREAM_JOB_RESERVE',
    'DOWNSTREAM_JOB_TYPES', 'FORBIDDEN_JOB_TYPES', 'ROSTER_JOB_TYPES',
    'SAFE_JOB_TYPES',
    'SHADOW_ENTRYPOINT_VERSION', 'ShadowConfigurationError',
    'assert_shadow_ready', 'ensure_current_date_poll', 'ensure_shadow_morning_plan',
    'production_shadow_handlers', 'run_production_shadow_cycle',
    'shadow_job_type_passes', 'shadow_queue_counts', 'validate_shadow_controls',
]
