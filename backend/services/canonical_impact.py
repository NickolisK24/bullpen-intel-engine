"""SP-09 authority-aware canonical mutation normalization and impact planning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
import hashlib
import json

from sqlalchemy.exc import IntegrityError

from models.canonical_impact import (
    CanonicalImpactPlan,
    CanonicalImpactPlanEntity,
    CanonicalImpactPlanMutation,
)
from models.final_game_reconciliation import FinalGameMutation, FinalGameVersion
from models.live_game_delta import LiveGameMutation
from models.pitcher import Pitcher
from models.pregame_context import PregameContextMutation
from models.roster_membership import PlayerTransactionVersion, RosterMembershipMutation
from models.sync_job import SyncJob
from models.sync_run import SyncRun
from services.sync_control_plane import (
    FailureClass,
    RunStage,
    RunStatus,
    RunType,
    ScopeType,
    SourceDomain,
    TriggerType,
    add_scopes,
    create_run,
    finalize_run,
    mark_stage,
    record_failure,
    record_outcome,
    start_run,
)
from services.sync_jobs import (
    JobScopeType,
    JobType,
    enqueue_job,
    heartbeat_job,
    run_next_job,
)
from utils.db import db
from utils.time import utc_now_naive


IMPACT_RULES_VERSION = 'canonical-impact-v1'
IMPACT_INPUT_PAYLOAD_VERSION = 1
DERIVED_JOB_PAYLOAD_VERSION = 1
PRIORITY_DERIVED_INTELLIGENCE = 60


class AuthorityClass(str, Enum):
    LIVE = 'live'
    FINAL = 'final'
    CORRECTED_FINAL = 'corrected_final'
    ROSTER_AUTHORITATIVE = 'roster_authoritative'
    PREGAME_AUTHORITATIVE = 'pregame_authoritative'


class MutationFamily(str, Enum):
    ROSTER_MEMBERSHIP = 'roster_membership'
    ROSTER_TRANSACTION = 'roster_transaction'
    PREGAME_CONTEXT = 'pregame_context'
    LIVE_APPEARANCE = 'live_appearance'
    FINAL_APPEARANCE = 'final_appearance'
    FINAL_GAME_CONTEXT = 'final_game_context'


class ImpactDomain(str, Enum):
    WORKLOAD = 'workload'
    WORKLOAD_CURRENT = 'workload_current'
    REST = 'rest'
    ARM_READ = 'arm_read'
    TEAM_STATE = 'team_state'
    TEAM_WORKLOAD_CURRENT = 'team_workload_current'
    DEPLOYMENT = 'deployment'
    ROLE_MOVEMENT = 'role_movement'
    PERFORMANCE = 'performance'
    ROTATION_TRANSFER = 'rotation_transfer'
    ROSTER_COMPOSITION = 'roster_composition'
    ORGANIZATIONAL_DEPTH = 'organizational_depth'
    BULLPEN_CHURN = 'bullpen_churn'
    CONCENTRATION = 'concentration'
    CLEAN_OPTIONS = 'clean_options'
    WHAT_CHANGED = 'what_changed'
    PITCHER_SNAPSHOT = 'pitcher_snapshot'
    TEAM_SNAPSHOT = 'team_snapshot'
    GAME_CONTEXT = 'game_context'
    MATCHUP_CONTEXT = 'matchup_context'
    READ_MODELS = 'read_models'


class ImpactPlanStatus(str, Enum):
    PLANNED = 'planned'
    DISPATCHED = 'dispatched'
    SUPERSEDED = 'superseded'


FINAL_CORRECTION_TYPES = frozenset({
    'pitching_line_corrected',
    'appearance_context_corrected',
    'final_play_by_play_corrected',
    'final_game_context_corrected',
})
FINAL_APPEARANCE_TYPES = frozenset({
    'starter_appearance_added',
    'reliever_appearance_added',
    'pitching_line_corrected',
    'appearance_context_corrected',
})
ACTIVE_MEMBERSHIP_TYPES = frozenset({'active_roster'})

FINAL_APPEARANCE_DOMAINS = frozenset({
    ImpactDomain.WORKLOAD, ImpactDomain.REST, ImpactDomain.ARM_READ,
    ImpactDomain.TEAM_STATE, ImpactDomain.DEPLOYMENT,
    ImpactDomain.ROLE_MOVEMENT, ImpactDomain.PERFORMANCE,
    ImpactDomain.ROTATION_TRANSFER, ImpactDomain.CONCENTRATION,
    ImpactDomain.WHAT_CHANGED, ImpactDomain.PITCHER_SNAPSHOT,
    ImpactDomain.TEAM_SNAPSHOT, ImpactDomain.GAME_CONTEXT,
    ImpactDomain.READ_MODELS,
})
LIVE_DOMAINS = frozenset({
    ImpactDomain.WORKLOAD_CURRENT,
    ImpactDomain.TEAM_WORKLOAD_CURRENT,
    ImpactDomain.GAME_CONTEXT,
})
ACTIVE_ROSTER_DOMAINS = frozenset({
    ImpactDomain.ROSTER_COMPOSITION, ImpactDomain.BULLPEN_CHURN,
    ImpactDomain.CLEAN_OPTIONS, ImpactDomain.TEAM_STATE,
    ImpactDomain.TEAM_SNAPSHOT, ImpactDomain.PITCHER_SNAPSHOT,
    ImpactDomain.WHAT_CHANGED, ImpactDomain.READ_MODELS,
})
DEPTH_ROSTER_DOMAINS = frozenset({
    ImpactDomain.ORGANIZATIONAL_DEPTH, ImpactDomain.TEAM_SNAPSHOT,
    ImpactDomain.PITCHER_SNAPSHOT, ImpactDomain.WHAT_CHANGED,
})
PREGAME_DOMAINS = frozenset({
    ImpactDomain.GAME_CONTEXT, ImpactDomain.MATCHUP_CONTEXT,
    ImpactDomain.READ_MODELS,
})


@dataclass(frozen=True)
class NormalizedMutation:
    mutation_id: int
    family: str
    source_type: str
    authority_class: str
    baseball_date: date
    game_pk: int | None = None
    team_id: int | None = None
    pitcher_id: int | None = None
    source_observation_id: int | None = None
    old_fact_identity: str | None = None
    new_fact_identity: str | None = None
    is_correction: bool = False
    membership_type: str | None = None
    team_ids: tuple[int, ...] = ()
    pitcher_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class ImpactPlanningResult:
    plan: CanonicalImpactPlan
    created: bool
    downstream_job: object | None
    stale_live_suppressed: bool


def normalize_mutation_cohort(payload):
    """Load and normalize one source-specific immutable mutation cohort."""
    if not isinstance(payload, dict):
        raise ValueError('Canonical impact payload must be an object.')
    requested_family = payload.get('mutation_family')
    authority = payload.get('authority_class') or payload.get('authority_state')
    ids = (
        payload.get('mutation_ids')
        or payload.get('membership_mutation_ids')
        or payload.get('pregame_context_mutation_ids')
        or payload.get('transaction_version_ids')
        or []
    )
    ids = sorted({int(value) for value in ids})
    if not ids:
        return ()

    if requested_family == MutationFamily.ROSTER_MEMBERSHIP.value or 'membership_mutation_ids' in payload:
        rows = _load_rows(RosterMembershipMutation, ids)
        return tuple(_normalize_roster(row) for row in rows)
    if requested_family == MutationFamily.ROSTER_TRANSACTION.value or 'transaction_version_ids' in payload:
        rows = _load_rows(PlayerTransactionVersion, ids)
        return tuple(_normalize_transaction(row) for row in rows)
    if requested_family == MutationFamily.PREGAME_CONTEXT.value or 'pregame_context_mutation_ids' in payload:
        rows = _load_rows(PregameContextMutation, ids)
        return tuple(_normalize_pregame(row) for row in rows)
    if requested_family == MutationFamily.LIVE_APPEARANCE.value or authority == AuthorityClass.LIVE.value:
        rows = _load_rows(LiveGameMutation, ids)
        return tuple(_normalize_live(row) for row in rows)

    rows = _load_rows(FinalGameMutation, ids)
    corrected = any(row.mutation_type in FINAL_CORRECTION_TYPES for row in rows)
    final_authority = (
        AuthorityClass.CORRECTED_FINAL.value if corrected
        else AuthorityClass.FINAL.value
    )
    return tuple(_normalize_final(row, final_authority) for row in rows)


def plan_canonical_impact(payload, *, sync_run_id=None, correlation_id=None, commit=True):
    mutations = normalize_mutation_cohort(payload)
    if not mutations:
        raise ValueError('Canonical impact payload references no mutations.')
    authority = _cohort_authority(mutations)
    baseball_date = _cohort_date(mutations)
    games = sorted({row.game_pk for row in mutations if row.game_pk is not None})
    teams = sorted(
        {row.team_id for row in mutations if row.team_id is not None}
        | {value for row in mutations for value in row.team_ids}
    )
    pitchers = sorted(
        {row.pitcher_id for row in mutations if row.pitcher_id is not None}
        | {value for row in mutations for value in row.pitcher_ids}
    )
    observation_ids = sorted({
        row.source_observation_id for row in mutations
        if row.source_observation_id is not None
    })
    stale_live = authority == AuthorityClass.LIVE.value and _final_authority_exists(games)
    domains = [] if stale_live else sorted({
        domain.value
        for mutation in mutations
        for domain in impact_domains_for(mutation)
    })
    fingerprint = impact_plan_fingerprint(
        mutations, authority=authority, games=games, teams=teams,
        pitchers=pitchers, domains=domains,
    )
    existing = CanonicalImpactPlan.query.filter_by(plan_fingerprint=fingerprint).one_or_none()
    if existing is not None:
        downstream = db.session.get(SyncJob, existing.dispatched_job_id) if existing.dispatched_job_id else None
        return ImpactPlanningResult(existing, False, downstream, stale_live)

    superseded_live_plan = _latest_live_plan(games) if authority in {
        AuthorityClass.FINAL.value, AuthorityClass.CORRECTED_FINAL.value,
    } else None
    plan = CanonicalImpactPlan(
        plan_fingerprint=fingerprint,
        rules_version=IMPACT_RULES_VERSION,
        authority_class=authority,
        baseball_date=baseball_date,
        correlation_id=correlation_id,
        affected_game_ids_json=games,
        affected_team_ids_json=teams,
        affected_pitcher_ids_json=pitchers,
        affected_domains_json=domains,
        source_observation_ids_json=observation_ids,
        status=(ImpactPlanStatus.SUPERSEDED.value if stale_live else ImpactPlanStatus.PLANNED.value),
        supersedes_live=bool(superseded_live_plan),
        supersedes_plan_id=superseded_live_plan.id if superseded_live_plan else None,
        sync_run_id=sync_run_id,
    )
    try:
        with db.session.begin_nested():
            db.session.add(plan)
            db.session.flush()
            _add_plan_details(plan, mutations, games, teams, pitchers)
            db.session.flush()
    except IntegrityError:
        plan = CanonicalImpactPlan.query.filter_by(plan_fingerprint=fingerprint).one()
        downstream = db.session.get(SyncJob, plan.dispatched_job_id) if plan.dispatched_job_id else None
        return ImpactPlanningResult(plan, False, downstream, stale_live)

    if superseded_live_plan is not None:
        superseded_live_plan.status = ImpactPlanStatus.SUPERSEDED.value

    downstream = None
    if domains and not stale_live:
        downstream = enqueue_job(
            job_type=JobType.PROCESS_DERIVED_INTELLIGENCE,
            scope_type=(JobScopeType.GAME if len(games) == 1 else JobScopeType.BASEBALL_DATE),
            scope_key=(str(games[0]) if len(games) == 1 else baseball_date.isoformat()),
            product_date=baseball_date,
            dedupe_key=f'DERIVED_INTELLIGENCE:impact-plan:{fingerprint}',
            priority=PRIORITY_DERIVED_INTELLIGENCE,
            sync_run_id=sync_run_id,
            payload_schema_version=DERIVED_JOB_PAYLOAD_VERSION,
            payload={
                'impact_plan_id': plan.id,
                'rules_version': IMPACT_RULES_VERSION,
                'authority_class': authority,
                'affected_game_ids': games,
                'affected_team_ids': teams,
                'affected_pitcher_ids': pitchers,
                'affected_domains': domains,
                'baseball_date': baseball_date,
                'correlation_id': correlation_id,
            },
            commit=False,
        )
        plan.status = ImpactPlanStatus.DISPATCHED.value
        plan.dispatched_job_id = downstream.id
        plan.dispatched_at = utc_now_naive()
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return ImpactPlanningResult(plan, True, downstream, stale_live)


def impact_domains_for(mutation):
    if mutation.family == MutationFamily.LIVE_APPEARANCE.value:
        return LIVE_DOMAINS
    if mutation.family == MutationFamily.PREGAME_CONTEXT.value:
        return PREGAME_DOMAINS
    if mutation.family == MutationFamily.ROSTER_MEMBERSHIP.value:
        return (
            ACTIVE_ROSTER_DOMAINS
            if mutation.membership_type in ACTIVE_MEMBERSHIP_TYPES
            else DEPTH_ROSTER_DOMAINS
        )
    if mutation.family == MutationFamily.ROSTER_TRANSACTION.value:
        return frozenset({
            ImpactDomain.ROSTER_COMPOSITION, ImpactDomain.ORGANIZATIONAL_DEPTH,
            ImpactDomain.BULLPEN_CHURN, ImpactDomain.TEAM_SNAPSHOT,
            ImpactDomain.PITCHER_SNAPSHOT, ImpactDomain.WHAT_CHANGED,
        })
    if mutation.family == MutationFamily.FINAL_APPEARANCE.value:
        if mutation.source_type == 'appearance_context_corrected':
            return frozenset({
                ImpactDomain.DEPLOYMENT, ImpactDomain.ROLE_MOVEMENT,
                ImpactDomain.PERFORMANCE, ImpactDomain.GAME_CONTEXT,
                ImpactDomain.PITCHER_SNAPSHOT, ImpactDomain.TEAM_SNAPSHOT,
                ImpactDomain.WHAT_CHANGED, ImpactDomain.READ_MODELS,
            })
        return FINAL_APPEARANCE_DOMAINS
    if mutation.source_type == 'final_game_context_corrected':
        return frozenset({
            ImpactDomain.ROTATION_TRANSFER, ImpactDomain.GAME_CONTEXT,
            ImpactDomain.TEAM_SNAPSHOT, ImpactDomain.WHAT_CHANGED,
            ImpactDomain.READ_MODELS,
        })
    if mutation.source_type == 'final_play_by_play_corrected':
        return frozenset({
            ImpactDomain.DEPLOYMENT, ImpactDomain.ROLE_MOVEMENT,
            ImpactDomain.PERFORMANCE, ImpactDomain.GAME_CONTEXT,
            ImpactDomain.PITCHER_SNAPSHOT, ImpactDomain.TEAM_SNAPSHOT,
            ImpactDomain.WHAT_CHANGED, ImpactDomain.READ_MODELS,
        })
    if mutation.source_type == 'final_game_ingested':
        return frozenset({
            ImpactDomain.ROTATION_TRANSFER, ImpactDomain.GAME_CONTEXT,
            ImpactDomain.TEAM_SNAPSHOT, ImpactDomain.WHAT_CHANGED,
            ImpactDomain.READ_MODELS,
        })
    return frozenset()


def impact_plan_fingerprint(mutations, *, authority, games, teams, pitchers, domains):
    value = {
        'rules_version': IMPACT_RULES_VERSION,
        'authority_class': authority,
        'mutations': sorted(
            (row.family, row.mutation_id, row.source_type) for row in mutations
        ),
        'games': sorted(games),
        'teams': sorted(teams),
        'pitchers': sorted(pitchers),
        'domains': sorted(domains),
    }
    payload = json.dumps(value, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def execute_canonical_impact_job(job):
    payload = dict(job.details_json or {})
    if job.payload_schema_version != IMPACT_INPUT_PAYLOAD_VERSION:
        raise ValueError(f'Unsupported canonical impact payload version: {job.payload_schema_version!r}')
    baseball_date = _as_date(payload.get('baseball_date') or job.product_date)
    run = _start_run(job, baseball_date)
    try:
        mark_stage(run, RunStage.IMPACT, commit=False)
        heartbeat_job(job.id, worker_id=job.worker_id, claim_token=job.claim_token, commit=False)
        result = plan_canonical_impact(
            payload,
            sync_run_id=run.id,
            correlation_id=run.correlation_id,
            commit=False,
        )
        plan = result.plan
        add_scopes(run, [
            *((ScopeType.GAME, value) for value in plan.affected_game_ids_json),
            *((ScopeType.TEAM, value) for value in plan.affected_team_ids_json),
            *((ScopeType.PITCHER, value) for value in plan.affected_pitcher_ids_json),
        ], commit=False)
        heartbeat_job(job.id, worker_id=job.worker_id, claim_token=job.claim_token, commit=False)
        record_outcome(
            run,
            canonical_mutations=len(plan.mutation_refs),
            affected_games=len(plan.affected_game_ids_json),
            affected_teams=len(plan.affected_team_ids_json),
            affected_pitchers=len(plan.affected_pitcher_ids_json),
            downstream_work_created=int(result.downstream_job is not None and result.created),
            outcome={
                'input_mutations': len(plan.mutation_refs),
                'impact_plan_id': plan.id,
                'impact_plan_created': result.created,
                'authority_class': plan.authority_class,
                'affected_domains': plan.affected_domains_json,
                'stale_live_suppressed': result.stale_live_suppressed,
                'downstream_job_id': plan.dispatched_job_id,
                'rules_version': plan.rules_version,
            },
            commit=False,
        )
        finalize_run(run, RunStatus.SUCCEEDED, commit=False)
        db.session.commit()
        return {
            'sync_run_id': run.id,
            'impact_plan_id': plan.id,
            'impact_plan_created': result.created,
            'downstream_job_id': plan.dispatched_job_id,
            'stale_live_suppressed': result.stale_live_suppressed,
        }
    except Exception as exc:
        db.session.rollback()
        record_failure(
            run.id,
            exc,
            failure_class=FailureClass.INTERNAL,
            stage=RunStage.IMPACT,
            retryable=True,
            commit=False,
        )
        finalize_run(run.id, RunStatus.FAILED, failed_stage=RunStage.IMPACT)
        raise


def run_canonical_impact_worker_once(worker_id, *, lease_seconds=300):
    return run_next_job(
        worker_id,
        {JobType.PROCESS_CANONICAL_IMPACT.value: execute_canonical_impact_job},
        job_types=[JobType.PROCESS_CANONICAL_IMPACT],
        lease_seconds=lease_seconds,
    )


def _start_run(job, baseball_date):
    parent = db.session.get(SyncRun, job.sync_run_id) if job.sync_run_id else None
    run = create_run(
        run_type=RunType.INCREMENTAL_INTELLIGENCE,
        trigger_type=TriggerType.PARENT_RUN,
        source='canonical_impact',
        job_name=JobType.PROCESS_CANONICAL_IMPACT.value,
        baseball_date=baseball_date,
        source_domain=SourceDomain.MULTI_DOMAIN,
        parent_sync_run_id=parent.id if parent else None,
        correlation_id=parent.correlation_id if parent else None,
        scopes=(),
        commit=False,
    )
    job.sync_run_id = run.id
    db.session.commit()
    return start_run(run)


def _load_rows(model, ids):
    rows = model.query.filter(model.id.in_(ids)).order_by(model.id).all()
    found = {row.id for row in rows}
    missing = sorted(set(ids) - found)
    if missing:
        raise ValueError(f'Missing {model.__name__} rows: {missing}')
    return rows


def _normalize_roster(row):
    return NormalizedMutation(
        row.id, MutationFamily.ROSTER_MEMBERSHIP.value, row.mutation_type,
        AuthorityClass.ROSTER_AUTHORITATIVE.value, row.baseball_date,
        team_id=row.team_id, pitcher_id=row.pitcher_id,
        source_observation_id=row.source_observation_id,
        old_fact_identity=(str(row.interval_id) if row.mutation_type != 'membership_opened' else None),
        new_fact_identity=(str(row.interval_id) if row.mutation_type != 'membership_closed' else None),
        is_correction=row.mutation_type == 'membership_corrected',
        membership_type=row.membership_type,
    )


def _normalize_pregame(row):
    return NormalizedMutation(
        row.id, MutationFamily.PREGAME_CONTEXT.value, row.mutation_type,
        AuthorityClass.PREGAME_AUTHORITATIVE.value, row.baseball_date,
        game_pk=row.game_pk, team_id=row.team_id,
        source_observation_id=row.source_observation_id,
        old_fact_identity=_optional_text(row.old_probable_pitcher_mlb_id),
        new_fact_identity=_optional_text(row.new_probable_pitcher_mlb_id),
        is_correction=row.mutation_type != 'pregame_context_discovered',
    )


def _normalize_transaction(row):
    fact = dict(row.fact_json or {})
    transaction = row.transaction
    team_ids = tuple(sorted({
        int(value) for value in (fact.get('from_team_id'), fact.get('to_team_id'))
        if value is not None
    }))
    return NormalizedMutation(
        row.id, MutationFamily.ROSTER_TRANSACTION.value,
        fact.get('normalized_category') or fact.get('type_code') or 'transaction_changed',
        AuthorityClass.ROSTER_AUTHORITATIVE.value,
        _as_date(fact.get('effective_date') or fact.get('transaction_date')),
        pitcher_id=transaction.pitcher_id,
        source_observation_id=row.source_observation_id,
        old_fact_identity=_optional_text(row.predecessor_version_id),
        new_fact_identity=str(row.id),
        is_correction=row.predecessor_version_id is not None,
        team_ids=team_ids,
    )


def _normalize_live(row):
    return NormalizedMutation(
        row.id, MutationFamily.LIVE_APPEARANCE.value, row.mutation_type,
        AuthorityClass.LIVE.value, row.baseball_date,
        game_pk=row.game_pk, team_id=row.team_id, pitcher_id=row.pitcher_id,
        source_observation_id=row.source_observation_id,
        old_fact_identity=row.old_fingerprint,
        new_fact_identity=row.new_fingerprint,
        is_correction=bool(row.is_correction),
    )


def _normalize_final(row, authority):
    family = (
        MutationFamily.FINAL_APPEARANCE.value
        if row.mutation_type in FINAL_APPEARANCE_TYPES
        else MutationFamily.FINAL_GAME_CONTEXT.value
    )
    game_version = db.session.get(FinalGameVersion, row.final_game_version_id)
    details = dict(row.details_json or {})
    team_ids = set(details.get('affected_team_ids') or ())
    pitcher_ids = set()
    if family == MutationFamily.FINAL_GAME_CONTEXT.value and game_version is not None:
        team_ids.update((game_version.home_team_id, game_version.away_team_id))
    mlb_ids = [int(value) for value in details.get('affected_pitcher_mlb_ids') or ()]
    if mlb_ids:
        pitcher_ids.update(
            value for (value,) in db.session.query(Pitcher.id).filter(Pitcher.mlb_id.in_(mlb_ids)).all()
        )
    return NormalizedMutation(
        row.id, family, row.mutation_type, authority, row.baseball_date,
        game_pk=row.game_pk, team_id=row.team_id, pitcher_id=row.pitcher_id,
        source_observation_id=row.source_observation_id,
        old_fact_identity=_optional_text(row.old_appearance_version_id),
        new_fact_identity=_optional_text(row.new_appearance_version_id or row.final_game_version_id),
        is_correction=row.mutation_type in FINAL_CORRECTION_TYPES,
        team_ids=tuple(sorted(int(value) for value in team_ids if value is not None)),
        pitcher_ids=tuple(sorted(pitcher_ids)),
    )


def _add_plan_details(plan, mutations, games, teams, pitchers):
    for row in mutations:
        db.session.add(CanonicalImpactPlanMutation(
            impact_plan_id=plan.id,
            mutation_family=row.family,
            source_mutation_id=row.mutation_id,
            source_mutation_type=row.source_type,
            authority_class=row.authority_class,
            game_pk=row.game_pk,
            team_id=row.team_id,
            pitcher_id=row.pitcher_id,
            baseball_date=row.baseball_date,
            source_observation_id=row.source_observation_id,
            old_fact_identity=row.old_fact_identity,
            new_fact_identity=row.new_fact_identity,
            is_correction=row.is_correction,
        ))
    for entity_type, values in (('game', games), ('team', teams), ('pitcher', pitchers)):
        for value in values:
            db.session.add(CanonicalImpactPlanEntity(
                impact_plan_id=plan.id,
                entity_type=entity_type,
                entity_key=str(value),
            ))


def _cohort_authority(mutations):
    values = {row.authority_class for row in mutations}
    if len(values) != 1:
        raise ValueError(f'Mutation cohort mixes authority classes: {sorted(values)}')
    return values.pop()


def _cohort_date(mutations):
    values = {row.baseball_date for row in mutations}
    if len(values) != 1:
        raise ValueError('Mutation cohort spans multiple baseball dates.')
    return values.pop()


def _final_authority_exists(game_ids):
    if not game_ids:
        return False
    count = FinalGameVersion.query.filter(
        FinalGameVersion.game_pk.in_(game_ids),
        FinalGameVersion.is_current.is_(True),
    ).count()
    return count == len(game_ids)


def _latest_live_plan(game_ids):
    if not game_ids:
        return None
    return (
        CanonicalImpactPlan.query
        .join(CanonicalImpactPlanEntity)
        .filter(
            CanonicalImpactPlan.authority_class == AuthorityClass.LIVE.value,
            CanonicalImpactPlanEntity.entity_type == 'game',
            CanonicalImpactPlanEntity.entity_key.in_([str(value) for value in game_ids]),
        )
        .order_by(CanonicalImpactPlan.id.desc())
        .first()
    )


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _optional_text(value):
    return str(value) if value is not None else None


__all__ = [
    'AuthorityClass', 'DERIVED_JOB_PAYLOAD_VERSION', 'IMPACT_INPUT_PAYLOAD_VERSION',
    'IMPACT_RULES_VERSION', 'ImpactDomain', 'ImpactPlanStatus',
    'ImpactPlanningResult', 'MutationFamily', 'NormalizedMutation',
    'execute_canonical_impact_job', 'impact_domains_for',
    'impact_plan_fingerprint', 'normalize_mutation_cohort',
    'plan_canonical_impact', 'run_canonical_impact_worker_once',
]
