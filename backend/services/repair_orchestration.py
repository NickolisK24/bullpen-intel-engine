"""SP-13 governed repair, bounded backfill, and explicit replay orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
import hashlib
import json
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from models.canonical_impact import CanonicalImpactPlan, CanonicalImpactPlanEntity
from models.daily_closure import BaseballDateClosure
from models.repair_request import RepairRequest, RepairRequestBlocker, RepairRequestChunk
from models.scheduled_game import ScheduledGame
from models.sync_job import SyncJob
from models.sync_run import SyncRun
from services.daily_reconciliation import enqueue_closure_check
from services.roster_transaction_authority import (
    enqueue_roster_reconciliation,
    enqueue_transaction_reconciliation,
)
from services.sync_control_plane import (
    FailureClass, RunStage, RunStatus, RunType, ScopeType, SourceDomain, TriggerType,
    add_scopes, create_run, finalize_run, mark_stage, record_failure, record_outcome,
    start_run,
)
from services.sync_jobs import (
    CANONICAL_ACTIVE_STATUSES, JobScopeType, JobType, STATUS_DEAD,
    STATUS_SUCCEEDED, enqueue_job, heartbeat_job, run_next_job,
)
from utils.db import db
from utils.time import utc_now_naive


REPAIR_SCHEMA_VERSION = 'repair-request-v1'
REPAIR_PLAN_VERSION = 'repair-plan-v1'
REPAIR_CHECK_POLICY_VERSION = 'repair-check-v1'
REPAIR_PAYLOAD_VERSION = 1
REPAIR_RECHECK_SECONDS = 20 * 60
MAX_STANDARD_BACKFILL_DAYS = 31
MAX_EXPLICIT_BACKFILL_DAYS = 366
PRIORITY_REPAIR_ORCHESTRATION = 45
PRIORITY_REPAIR_SOURCE = 55
PRIORITY_REPLAY = 60


class RepairMode(str, Enum):
    TARGETED = 'targeted_repair'
    BACKFILL = 'historical_backfill'
    FULL = 'full_reconciliation'
    METHOD_REPLAY = 'method_replay'
    RULE_REPLAY = 'rule_replay'


class RepairDomain(str, Enum):
    SCHEDULE = 'schedule'
    FINAL_GAME = 'final_game'
    ROSTER = 'roster'
    TRANSACTIONS = 'transactions'
    PREGAME = 'pregame'
    LIVE = 'live'
    DOWNSTREAM = 'downstream'
    MULTI_DOMAIN = 'multi_domain'


TERMINAL_REQUEST_STATUSES = frozenset({
    'completed', 'completed_partial', 'failed', 'cancelled',
})
TERMINAL_CHUNK_STATUSES = frozenset({'succeeded', 'blocked', 'failed', 'cancelled'})


@dataclass(frozen=True)
class RepairSubmission:
    request: RepairRequest
    job: SyncJob | None
    reused_active_request: bool


def _as_date(value, name):
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f'{name} must be an ISO baseball date.') from exc


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), default=str)


def _fingerprint(value):
    return hashlib.sha256(_canonical(value).encode('utf-8')).hexdigest()


def _mode(value):
    try:
        return RepairMode(value.value if isinstance(value, RepairMode) else str(value)).value
    except ValueError as exc:
        raise ValueError(f'Unsupported repair mode: {value!r}.') from exc


def _domain(value):
    try:
        return RepairDomain(value.value if isinstance(value, RepairDomain) else str(value)).value
    except ValueError as exc:
        raise ValueError(f'Unsupported repair domain: {value!r}.') from exc


def _normalize_scope(scope):
    if not isinstance(scope, dict):
        raise ValueError('scope must be a JSON object.')
    normalized = {}
    for key, value in scope.items():
        if value is None:
            continue
        if key in {'game_pk', 'team_id', 'pitcher_id', 'impact_plan_id'}:
            normalized[key] = int(value)
        elif key in {'game_pks', 'team_ids', 'pitcher_ids', 'impact_plan_ids'}:
            normalized[key] = sorted({int(item) for item in value})
        else:
            normalized[key] = value
    return normalized


def _validate_bounds(mode, start_date, end_date, scope, *, allow_large_scope):
    if end_date < start_date:
        raise ValueError('baseball_date_end must be on or after baseball_date_start.')
    days = (end_date - start_date).days + 1
    if mode == RepairMode.TARGETED.value and days != 1:
        raise ValueError('Targeted repair is limited to one baseball date.')
    if days > MAX_EXPLICIT_BACKFILL_DAYS:
        raise ValueError(f'Repair range exceeds the absolute {MAX_EXPLICIT_BACKFILL_DAYS}-day limit.')
    if days > MAX_STANDARD_BACKFILL_DAYS and not allow_large_scope:
        raise ValueError(
            f'Repair range exceeds {MAX_STANDARD_BACKFILL_DAYS} days; explicit broad-scope confirmation is required.'
        )
    if mode in {RepairMode.METHOD_REPLAY.value, RepairMode.RULE_REPLAY.value}:
        if not (scope.get('impact_plan_id') or scope.get('impact_plan_ids')):
            raise ValueError('Replay requires explicit impact_plan_id values.')


def submit_repair_request(
    *, mode, source_domain, baseball_date_start, baseball_date_end=None,
    scope=None, requested_scope_type='baseball_date', reason, requested_by='operator',
    dry_run=True, requested_rules_version=None, requested_method_versions=None,
    allow_large_scope=False, enqueue=True, commit=True,
):
    """Persist an immutable request and enqueue its one-shot planner.

    Dry-run requests are durable and acquire no owner work; the planner only
    records the deterministic plan and expected scope.
    """
    mode = _mode(mode)
    source_domain = _domain(source_domain)
    start_date = _as_date(baseball_date_start, 'baseball_date_start')
    end_date = _as_date(baseball_date_end or start_date, 'baseball_date_end')
    scope = _normalize_scope(scope or {})
    _validate_bounds(mode, start_date, end_date, scope, allow_large_scope=allow_large_scope)
    reason = str(reason or '').strip()
    if not reason:
        raise ValueError('A non-empty repair reason is required.')
    method_versions = dict(requested_method_versions or {})
    if mode == RepairMode.METHOD_REPLAY.value and not method_versions:
        raise ValueError('Method replay requires at least one explicit method version.')
    if mode == RepairMode.RULE_REPLAY.value and not requested_rules_version:
        raise ValueError('Rule replay requires an explicit rules version.')
    material = {
        'schema_version': REPAIR_SCHEMA_VERSION, 'mode': mode,
        'source_domain': source_domain, 'start': start_date, 'end': end_date,
        'scope_type': requested_scope_type, 'scope': scope, 'dry_run': bool(dry_run),
        'requested_rules_version': requested_rules_version,
        'requested_method_versions': method_versions,
    }
    request_fingerprint = _fingerprint(material)
    active_key = f'REPAIR:{request_fingerprint}'
    existing = RepairRequest.query.filter(
        RepairRequest.active_dedupe_key == active_key,
        RepairRequest.status.in_(('planned', 'running', 'blocked')),
    ).one_or_none()
    if existing is not None:
        job = db.session.get(SyncJob, existing.root_job_id) if existing.root_job_id else None
        return RepairSubmission(existing, job, True)

    request = RepairRequest(
        request_key=str(uuid4()), request_fingerprint=request_fingerprint,
        active_dedupe_key=active_key, schema_version=REPAIR_SCHEMA_VERSION,
        plan_version=REPAIR_PLAN_VERSION, mode=mode, status='planned',
        requested_scope_type=str(requested_scope_type), scope_json=scope,
        baseball_date_start=start_date, baseball_date_end=end_date,
        source_domain=source_domain, reason=reason, requested_by=str(requested_by)[:120],
        trigger_type=('backfill' if mode == RepairMode.BACKFILL.value else 'repair'),
        dry_run=bool(dry_run), requested_rules_version=requested_rules_version,
        requested_method_versions_json=method_versions, correlation_id=str(uuid4()),
    )
    try:
        with db.session.begin_nested():
            db.session.add(request)
            db.session.flush()
    except IntegrityError:
        existing = RepairRequest.query.filter(
            RepairRequest.active_dedupe_key == active_key,
            RepairRequest.status.in_(('planned', 'running', 'blocked')),
        ).one()
        job = db.session.get(SyncJob, existing.root_job_id) if existing.root_job_id else None
        return RepairSubmission(existing, job, True)
    job = None
    if enqueue:
        job = enqueue_job(
            job_type=JobType.RUN_REPAIR_REQUEST,
            scope_type=JobScopeType.BASEBALL_DATE,
            scope_key=f'{start_date.isoformat()}:{end_date.isoformat()}',
            product_date=end_date,
            dedupe_key=f'RUN_REPAIR_REQUEST:{request.request_key}',
            priority=PRIORITY_REPAIR_ORCHESTRATION,
            payload_schema_version=REPAIR_PAYLOAD_VERSION,
            payload={'repair_request_id': request.id, 'plan_version': REPAIR_PLAN_VERSION},
            commit=False,
        )
        request.root_job_id = job.id
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return RepairSubmission(request, job, False)


def plan_repair_request(request_id, *, commit=True):
    request = db.session.get(RepairRequest, int(request_id))
    if request is None:
        raise ValueError(f'Repair request {request_id} does not exist.')
    if request.status in TERMINAL_REQUEST_STATUSES:
        return request
    dates = [
        request.baseball_date_start + timedelta(days=offset)
        for offset in range((request.baseball_date_end - request.baseball_date_start).days + 1)
    ]
    plan_material = {
        'plan_version': REPAIR_PLAN_VERSION,
        'request_fingerprint': request.request_fingerprint,
        'dates': [value.isoformat() for value in dates],
        'owner_package': _owner_package(request.source_domain, request.mode),
        'scope': request.scope_json,
        'dry_run': request.dry_run,
    }
    request.plan_fingerprint = _fingerprint(plan_material)
    baseline = {}
    for value in dates:
        closure = BaseballDateClosure.query.filter_by(baseball_date=value).one_or_none()
        baseline[value.isoformat()] = {
            'status': closure.status if closure else None,
            'version': closure.current_version_number if closure else None,
            'fingerprint': closure.closure_fingerprint if closure else None,
        }
        key = f'{request.source_domain}:{value.isoformat()}'
        if not any(row.chunk_key == key for row in request.chunks):
            request.chunks.append(RepairRequestChunk(
                chunk_key=key,
                chunk_order=(value - request.baseball_date_start).days,
                owner_package=_owner_package(request.source_domain, request.mode),
                baseball_date_start=value, baseball_date_end=value,
                scope_json=request.scope_json, status='planned',
            ))
    request.plan_json = {**plan_material, 'closure_baseline': baseline}
    request.estimated_counts_json = _estimate(request, dates)
    request.status = 'running'
    request.started_at = request.started_at or utc_now_naive()
    db.session.flush()
    if request.dry_run:
        for chunk in request.chunks:
            chunk.status = 'succeeded'
            chunk.completed_at = utc_now_naive()
            chunk.outcome_json = {'dry_run': True, 'jobs_dispatched': 0}
        request.status = 'completed'
        request.completed_at = utc_now_naive()
        request.active_dedupe_key = None
        request.outcome_json = {
            'dry_run': True, 'mutations_performed': 0, 'jobs_dispatched': 0,
            'publication_advanced': False, 'closure_changed': False,
        }
    if commit:
        db.session.commit()
    return request


def dispatch_repair_request(request_id, *, parent_job_id=None, lease_fence=None, commit=True):
    request = plan_repair_request(request_id, commit=False)
    if request.dry_run or request.status in TERMINAL_REQUEST_STATUSES:
        if commit:
            db.session.commit()
        return request
    total_jobs = 0
    for chunk in sorted(request.chunks, key=lambda row: row.chunk_order):
        if chunk.status not in {'planned', 'blocked'}:
            continue
        if lease_fence:
            lease_fence()
        jobs = _dispatch_chunk(request, chunk, parent_job_id=parent_job_id)
        chunk.child_job_ids_json = sorted({int(job.id) for job in jobs})
        chunk.status = 'dispatched' if jobs else 'succeeded'
        chunk.started_at = utc_now_naive()
        if not jobs:
            chunk.completed_at = utc_now_naive()
        total_jobs += len(jobs)
    request.outcome_json = {**(request.outcome_json or {}), 'jobs_dispatched': total_jobs}
    check = enqueue_job(
        job_type=JobType.CHECK_REPAIR_REQUEST,
        scope_type=JobScopeType.BASEBALL_DATE,
        scope_key=f'{request.baseball_date_start}:{request.baseball_date_end}',
        product_date=request.baseball_date_end,
        dedupe_key=f'CHECK_REPAIR_REQUEST:{request.request_key}:initial',
        priority=PRIORITY_REPAIR_ORCHESTRATION,
        payload_schema_version=REPAIR_PAYLOAD_VERSION,
        payload={'repair_request_id': request.id, 'policy_version': REPAIR_CHECK_POLICY_VERSION},
        sync_run_id=request.root_sync_run_id, parent_job_id=parent_job_id, commit=False,
    )
    request.check_job_id = check.id
    if commit:
        db.session.commit()
    return request


def _owner_package(domain, mode):
    if mode in {RepairMode.METHOD_REPLAY.value, RepairMode.RULE_REPLAY.value}:
        return 'SP-09/SP-10'
    return {
        RepairDomain.SCHEDULE.value: 'SP-04', RepairDomain.ROSTER.value: 'SP-05',
        RepairDomain.TRANSACTIONS.value: 'SP-05', RepairDomain.PREGAME.value: 'SP-06',
        RepairDomain.FINAL_GAME.value: 'SP-07', RepairDomain.LIVE.value: 'SP-07',
        RepairDomain.DOWNSTREAM.value: 'SP-09', RepairDomain.MULTI_DOMAIN.value: 'SP-04-SP-12',
    }[domain]


def _estimate(request, dates):
    games = _games_for_request(request, dates)
    game_count = len(set(games) | set(_explicit_game_ids(request.scope_json)))
    teams = _team_ids(request.scope_json)
    return {
        'dates': len(dates), 'games': game_count, 'teams': len(teams),
        'source_fetches': _estimated_fetches(request, dates, game_count, teams),
        'maximum_chunks': len(dates),
        'likely_impact_plans': game_count if request.source_domain == 'final_game' else 0,
        'likely_derived_cohorts': game_count if request.source_domain == 'final_game' else 0,
        'likely_closure_dates': len(dates),
    }


def _estimated_fetches(request, dates, game_count, teams):
    if request.source_domain == RepairDomain.ROSTER.value:
        return len(dates) * len(teams)
    if request.source_domain == RepairDomain.FINAL_GAME.value:
        return game_count
    return len(dates)


def _team_ids(scope):
    values = scope.get('team_ids') or ([scope['team_id']] if scope.get('team_id') else [])
    return sorted({int(value) for value in values})


def _games_for_request(request, dates):
    game_values = request.scope_json.get('game_pks') or (
        [request.scope_json['game_pk']] if request.scope_json.get('game_pk') else None
    )
    query = ScheduledGame.query.filter(ScheduledGame.game_date.in_(dates))
    if game_values:
        query = query.filter(ScheduledGame.game_pk.in_(game_values))
    rows = query.order_by(ScheduledGame.game_pk, ScheduledGame.id).all()
    return {row.game_pk: row for row in rows}


def _dispatch_chunk(request, chunk, *, parent_job_id):
    value = chunk.baseball_date_start
    domain = request.source_domain
    if request.mode in {RepairMode.METHOD_REPLAY.value, RepairMode.RULE_REPLAY.value}:
        return _dispatch_replay(request, chunk, parent_job_id=parent_job_id)
    if domain == RepairDomain.FINAL_GAME.value or domain == RepairDomain.LIVE.value:
        if domain == RepairDomain.LIVE.value:
            _replace_blockers(request, [{
                'blocker_type': 'unsupported_historical_context', 'entity_type': 'source_domain',
                'entity_key': 'live', 'retryable': False,
                'details_json': {'reason': 'historical live timing is observational and cannot be reconstructed'},
            }])
        jobs = _dispatch_final_jobs(request, value, parent_job_id)
        if not jobs and not _explicit_game_ids(request.scope_json):
            jobs.append(_enqueue_repair_schedule(request, value, parent_job_id))
        return jobs
    if domain == RepairDomain.ROSTER.value:
        teams = _team_ids(request.scope_json)
        if not teams:
            raise ValueError('Roster repair requires explicit team_id values; no current-team inference is allowed.')
        return [enqueue_roster_reconciliation(
            team_id, value, priority=PRIORITY_REPAIR_SOURCE,
            sync_run_id=request.root_sync_run_id, parent_job_id=parent_job_id, commit=False,
            repair_request_id=request.id,
        ) for team_id in teams]
    if domain == RepairDomain.TRANSACTIONS.value:
        return [enqueue_transaction_reconciliation(
            value, value, team_id=request.scope_json.get('team_id'),
            priority=PRIORITY_REPAIR_SOURCE, sync_run_id=request.root_sync_run_id,
            parent_job_id=parent_job_id, commit=False,
        )]
    if domain == RepairDomain.SCHEDULE.value:
        return [_enqueue_repair_schedule(request, value, parent_job_id)]
    if domain == RepairDomain.PREGAME.value and value < date.today():
        _replace_blockers(request, [{
            'blocker_type': 'unsupported_historical_context', 'entity_type': 'baseball_date',
            'entity_key': value.isoformat(), 'retryable': False,
            'details_json': {'reason': 'historical probable-starter announcement timing is unavailable'},
        }])
        return []
    if domain == RepairDomain.PREGAME.value:
        jobs = []
        for game in _games_for_request(request, [value]).values():
            jobs.append(enqueue_job(
                job_type=JobType.FETCH_PREGAME_CONTEXT,
                scope_type=JobScopeType.GAME, scope_key=str(game.game_pk), product_date=value,
                dedupe_key=f'REPAIR_PREGAME:{game.game_pk}:{value}:v1',
                priority=PRIORITY_REPAIR_SOURCE, sync_run_id=request.root_sync_run_id,
                parent_job_id=parent_job_id, payload_schema_version=1,
                payload={'game_pk': game.game_pk, 'baseball_date': value,
                         'reason': 'sp13_repair', 'policy_version': 'pregame-context-v1',
                         'repair_request_id': request.id}, commit=False,
            ))
        return jobs
    if domain == RepairDomain.MULTI_DOMAIN.value:
        jobs = [_enqueue_repair_schedule(request, value, parent_job_id), enqueue_transaction_reconciliation(
            value, value, priority=PRIORITY_REPAIR_SOURCE,
            sync_run_id=request.root_sync_run_id, parent_job_id=parent_job_id, commit=False,
        )]
        jobs.extend(_dispatch_final_jobs(request, value, parent_job_id))
        for team_id in _team_ids(request.scope_json):
            jobs.append(enqueue_roster_reconciliation(
                team_id, value, priority=PRIORITY_REPAIR_SOURCE,
                sync_run_id=request.root_sync_run_id, parent_job_id=parent_job_id, commit=False,
            ))
        return jobs
    return []


def _dispatch_final_jobs(request, value, parent_job_id):
    jobs = []
    scheduled = _games_for_request(request, [value])
    explicit = _explicit_game_ids(request.scope_json)
    game_ids = explicit or sorted(
        game.game_pk for game in scheduled.values()
        if (game.operational_state or game.status_state) == 'final'
    )
    for game_pk in game_ids:
        game = scheduled.get(game_pk)
        if explicit or (game and (game.operational_state or game.status_state) == 'final'):
            jobs.append(enqueue_job(
                job_type=JobType.RECONCILE_FINAL_GAME,
                scope_type=JobScopeType.GAME, scope_key=str(game_pk), product_date=value,
                dedupe_key=f'REPAIR_FINAL_GAME:{game_pk}:{value}:v1',
                priority=PRIORITY_REPAIR_SOURCE, sync_run_id=request.root_sync_run_id,
                parent_job_id=parent_job_id, payload_schema_version=1,
                payload={'game_pk': game_pk, 'baseball_date': value,
                         'trigger': 'sp13_repair', 'repair_request_id': request.id,
                         'schedule_observation_id': game.source_observation_id if game else None},
                commit=False,
            ))
    return jobs


def _explicit_game_ids(scope):
    values = scope.get('game_pks') or ([scope['game_pk']] if scope.get('game_pk') else [])
    return sorted({int(value) for value in values})


def _enqueue_repair_schedule(request, value, parent_job_id):
    return enqueue_job(
        job_type=JobType.FETCH_SCHEDULE, scope_type=JobScopeType.BASEBALL_DATE,
        scope_key=value.isoformat(), product_date=value,
        dedupe_key=f'REPAIR_SCHEDULE:{value}:v1',
        priority=PRIORITY_REPAIR_SOURCE, sync_run_id=request.root_sync_run_id,
        parent_job_id=parent_job_id,
        payload={'baseball_date': value, 'start_date': value, 'end_date': value,
                 'reason': 'sp13_repair', 'repair_request_id': request.id},
        commit=False,
    )


def _dispatch_replay(request, chunk, *, parent_job_id):
    ids = request.scope_json.get('impact_plan_ids') or [request.scope_json['impact_plan_id']]
    jobs = []
    for source_id in sorted({int(value) for value in ids}):
        source = db.session.get(CanonicalImpactPlan, source_id)
        if source is None:
            raise ValueError(f'Impact plan {source_id} does not exist.')
        if source.baseball_date != chunk.baseball_date_start:
            continue
        material = {
            'repair_request_fingerprint': request.request_fingerprint,
            'source_plan_fingerprint': source.plan_fingerprint,
            'replay_kind': request.mode,
            'rules_version': request.requested_rules_version or source.rules_version,
            'method_versions': request.requested_method_versions_json,
            'publication_mode': 'current' if source.baseball_date >= date.today() else 'historical',
        }
        fingerprint = _fingerprint(material)
        plan = CanonicalImpactPlan.query.filter_by(plan_fingerprint=fingerprint).one_or_none()
        if plan is None:
            plan = CanonicalImpactPlan(
                plan_fingerprint=fingerprint,
                rules_version=request.requested_rules_version or source.rules_version,
                authority_class=source.authority_class, baseball_date=source.baseball_date,
                correlation_id=request.correlation_id,
                affected_game_ids_json=list(source.affected_game_ids_json or []),
                affected_team_ids_json=list(source.affected_team_ids_json or []),
                affected_pitcher_ids_json=list(source.affected_pitcher_ids_json or []),
                affected_domains_json=list(source.affected_domains_json or []),
                source_observation_ids_json=list(source.source_observation_ids_json or []),
                status='planned', sync_run_id=request.root_sync_run_id,
                repair_request_id=request.id, replay_kind=request.mode,
                replay_from_plan_id=source.id,
                method_versions_override_json=dict(request.requested_method_versions_json or {}),
                publication_mode=material['publication_mode'],
            )
            db.session.add(plan)
            db.session.flush()
            for entity in source.entity_refs:
                db.session.add(CanonicalImpactPlanEntity(
                    impact_plan_id=plan.id, entity_type=entity.entity_type,
                    entity_key=entity.entity_key,
                ))
        job = enqueue_job(
            job_type=JobType.PROCESS_DERIVED_INTELLIGENCE,
            scope_type=JobScopeType.BASEBALL_DATE,
            scope_key=source.baseball_date.isoformat(), product_date=source.baseball_date,
            dedupe_key=f'DERIVED_INTELLIGENCE:replay:{fingerprint}',
            priority=PRIORITY_REPLAY, sync_run_id=request.root_sync_run_id,
            parent_job_id=parent_job_id, payload_schema_version=1,
            payload={
                'impact_plan_id': plan.id, 'rules_version': plan.rules_version,
                'authority_class': plan.authority_class, 'baseball_date': plan.baseball_date,
                'repair_request_id': request.id, 'replay_kind': request.mode,
                'publication_mode': plan.publication_mode,
            }, commit=False,
        )
        plan.status = 'dispatched'
        plan.dispatched_job_id = job.id
        plan.dispatched_at = utc_now_naive()
        jobs.append(job)
    return jobs


def _replace_blockers(request, blockers):
    for value in blockers:
        exists = RepairRequestBlocker.query.filter_by(
            repair_request_id=request.id, blocker_type=value['blocker_type'],
            entity_type=value['entity_type'], entity_key=value['entity_key'],
        ).one_or_none()
        if exists is None:
            db.session.add(RepairRequestBlocker(repair_request_id=request.id, **value))


def check_repair_request(request_id, *, parent_job_id=None, lease_fence=None, schedule_recheck=True, commit=True):
    request = db.session.get(RepairRequest, int(request_id))
    if request is None:
        raise ValueError(f'Repair request {request_id} does not exist.')
    _lock_request(request.id)
    db.session.refresh(request)
    if request.status in TERMINAL_REQUEST_STATUSES:
        return request
    pending = failed = succeeded = 0
    for chunk in request.chunks:
        jobs = _job_tree(
            chunk.child_job_ids_json or [],
            correlation_id=request.correlation_id,
            product_date=chunk.baseball_date_start,
        )
        if request.source_domain in {RepairDomain.FINAL_GAME.value, RepairDomain.MULTI_DOMAIN.value}:
            jobs = _expand_final_children(request, chunk, jobs, parent_job_id)
        partial_jobs = _critical_partial_jobs(jobs)
        if partial_jobs:
            for job in partial_jobs:
                _replace_blockers(request, [{
                    'blocker_type': 'source_partial',
                    'entity_type': 'sync_job',
                    'entity_key': str(job.id),
                    'details_json': {
                        'job_name': job.job_name,
                        'product_date': (
                            job.product_date.isoformat() if job.product_date else None
                        ),
                        'completeness': (job.result_json or {}).get('completeness'),
                        'errors': (job.result_json or {}).get('errors', 0),
                    },
                    'retryable': True,
                }])
            chunk.status = 'blocked'
        elif any(job.status == STATUS_DEAD for job in jobs):
            chunk.status = 'failed'
            failed += 1
        elif jobs and all(job.status == STATUS_SUCCEEDED for job in jobs):
            chunk.status = 'succeeded'
            chunk.completed_at = chunk.completed_at or utc_now_naive()
            succeeded += 1
        elif jobs:
            chunk.status = 'running'
            pending += 1
        elif request.blockers:
            chunk.status = 'blocked'
        else:
            chunk.status = 'succeeded'
            succeeded += 1
        if lease_fence:
            lease_fence()
    permanent = [row for row in request.blockers if not row.retryable]
    retryable = [row for row in request.blockers if row.retryable]
    if failed:
        request.status = 'failed'
        request.failure_reason = 'One or more owner-package child jobs exhausted retries.'
        request.completed_at = utc_now_naive()
        request.active_dedupe_key = None
    elif pending:
        request.status = 'running'
        if schedule_recheck:
            _enqueue_recheck(request, parent_job_id)
    elif permanent:
        request.status = 'completed_partial'
        request.completed_at = utc_now_naive()
        request.active_dedupe_key = None
    elif retryable:
        request.status = 'blocked'
        if schedule_recheck:
            _enqueue_recheck(request, parent_job_id)
    else:
        closure_ids = list((request.outcome_json or {}).get('closure_check_job_ids') or [])
        closure_jobs = [db.session.get(SyncJob, int(value)) for value in closure_ids]
        closure_jobs = [job for job in closure_jobs if job is not None]
        if _requires_closure_recheck(request) and not closure_jobs:
            closure_jobs = _enqueue_closure_rechecks(request, parent_job_id)
            request.status = 'running'
            if schedule_recheck:
                _enqueue_recheck(request, parent_job_id)
        elif closure_jobs and (
            any(job.status != STATUS_SUCCEEDED for job in closure_jobs)
            or not _closed_dates_ready(request)
        ):
            request.status = 'running'
            if schedule_recheck:
                _enqueue_recheck(request, parent_job_id)
        else:
            request.status = 'completed'
            request.completed_at = utc_now_naive()
            request.active_dedupe_key = None
    request.outcome_json = {
        **(request.outcome_json or {}), 'chunks_succeeded': succeeded,
        'chunks_pending': pending, 'chunks_failed': failed,
        'blockers': len(request.blockers),
    }
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return request


def _requires_closure_recheck(request):
    baseline = (request.plan_json or {}).get('closure_baseline') or {}
    return any(value.get('status') == 'closed' for value in baseline.values())


def _closed_dates_ready(request):
    baseline = (request.plan_json or {}).get('closure_baseline') or {}
    for raw_date, prior in baseline.items():
        if prior.get('status') != 'closed':
            continue
        closure = BaseballDateClosure.query.filter_by(
            baseball_date=date.fromisoformat(raw_date),
        ).one_or_none()
        if closure is None or closure.status != 'closed':
            return False
    return True


def _enqueue_closure_rechecks(request, parent_job_id):
    baseline = (request.plan_json or {}).get('closure_baseline') or {}
    jobs = []
    for raw_date, prior in baseline.items():
        if prior.get('status') != 'closed':
            continue
        value = date.fromisoformat(raw_date)
        jobs.append(enqueue_closure_check(
            value, sync_run_id=request.root_sync_run_id, parent_job_id=parent_job_id,
            generation=f'repair-{request.id}-{prior.get("version", 0)}', commit=False,
        ))
    request.outcome_json = {
        **(request.outcome_json or {}),
        'closure_check_job_ids': [job.id for job in jobs],
    }
    return jobs


def _job_tree(root_ids, *, correlation_id=None, product_date=None):
    found = {}
    pending_ids = [int(value) for value in root_ids]
    while pending_ids:
        batch = SyncJob.query.filter(SyncJob.id.in_(pending_ids)).all()
        pending_ids = []
        for job in batch:
            if job.id in found:
                continue
            found[job.id] = job
            pending_ids.extend(
                row.id for row in SyncJob.query.filter_by(parent_job_id=job.id).all()
                if row.id not in found
            )
    if correlation_id:
        correlated_query = SyncJob.query.join(
            SyncRun, SyncJob.sync_run_id == SyncRun.id,
        ).filter(
            SyncRun.correlation_id == correlation_id,
            ~SyncJob.job_name.in_((
                JobType.RUN_REPAIR_REQUEST.value,
                JobType.CHECK_REPAIR_REQUEST.value,
                JobType.CHECK_BASEBALL_DATE_CLOSURE.value,
            )),
        )
        if product_date is not None:
            correlated_query = correlated_query.filter(
                SyncJob.product_date == product_date,
            )
        correlated = correlated_query.all()
        found.update({job.id: job for job in correlated})
    return list(found.values())


def _critical_partial_jobs(jobs):
    """Return succeeded owner jobs whose result cannot establish authority."""
    partial = []
    for job in jobs:
        if job.status != STATUS_SUCCEEDED:
            continue
        result = job.result_json or {}
        if job.job_name == JobType.FETCH_TRANSACTIONS.value and (
            result.get('errors', 0)
            or result.get('completeness') in {'partial', 'unknown', 'failed'}
        ):
            partial.append(job)
        elif job.job_name == JobType.FETCH_ROSTER.value and (
            result.get('authoritative') is False
            or any(
                value not in {'complete', 'empty_valid'}
                for value in (result.get('completeness') or {}).values()
            )
        ):
            partial.append(job)
    return partial


def _expand_final_children(request, chunk, jobs, parent_job_id):
    if not any(
        job.job_name == JobType.FETCH_SCHEDULE.value and job.status == STATUS_SUCCEEDED
        for job in jobs
    ):
        return jobs
    existing = {
        int(job.scope_key) for job in jobs
        if job.job_name == JobType.RECONCILE_FINAL_GAME.value
    }
    new_jobs = []
    for game in _games_for_request(request, [chunk.baseball_date_start]).values():
        if (game.operational_state or game.status_state) != 'final' or game.game_pk in existing:
            continue
        new_jobs.append(enqueue_job(
            job_type=JobType.RECONCILE_FINAL_GAME,
            scope_type=JobScopeType.GAME, scope_key=str(game.game_pk),
            product_date=chunk.baseball_date_start,
            dedupe_key=f'REPAIR_FINAL_GAME:{game.game_pk}:{chunk.baseball_date_start}:v1',
            priority=PRIORITY_REPAIR_SOURCE, sync_run_id=request.root_sync_run_id,
            parent_job_id=parent_job_id, payload_schema_version=1,
            payload={'game_pk': game.game_pk, 'baseball_date': chunk.baseball_date_start,
                     'trigger': 'sp13_repair', 'repair_request_id': request.id,
                     'schedule_observation_id': game.source_observation_id},
            commit=False,
        ))
    if new_jobs:
        chunk.child_job_ids_json = sorted(set(chunk.child_job_ids_json or ()) | {job.id for job in new_jobs})
        return _job_tree(
            chunk.child_job_ids_json,
            correlation_id=request.correlation_id,
            product_date=chunk.baseball_date_start,
        )
    return jobs


def _enqueue_recheck(request, parent_job_id):
    when = utc_now_naive() + timedelta(seconds=REPAIR_RECHECK_SECONDS)
    job = enqueue_job(
        job_type=JobType.CHECK_REPAIR_REQUEST,
        scope_type=JobScopeType.BASEBALL_DATE,
        scope_key=f'{request.baseball_date_start}:{request.baseball_date_end}',
        product_date=request.baseball_date_end,
        dedupe_key=f'CHECK_REPAIR_REQUEST:{request.request_key}:{int(when.timestamp())}',
        priority=PRIORITY_REPAIR_ORCHESTRATION, available_at=when,
        sync_run_id=request.root_sync_run_id, parent_job_id=parent_job_id,
        payload_schema_version=REPAIR_PAYLOAD_VERSION,
        payload={'repair_request_id': request.id, 'policy_version': REPAIR_CHECK_POLICY_VERSION},
        commit=False,
    )
    request.check_job_id = job.id


def cancel_repair_request(request_id, *, commit=True):
    request = db.session.get(RepairRequest, int(request_id))
    if request is None:
        raise ValueError(f'Repair request {request_id} does not exist.')
    if request.status in TERMINAL_REQUEST_STATUSES:
        return request
    request.status = 'cancelled'
    request.cancelled_at = utc_now_naive()
    request.completed_at = request.cancelled_at
    request.active_dedupe_key = None
    for chunk in request.chunks:
        if chunk.status in {'planned', 'dispatched'}:
            chunk.status = 'cancelled'
    if commit:
        db.session.commit()
    return request


def execute_repair_request_job(job):
    if job.payload_schema_version != REPAIR_PAYLOAD_VERSION:
        raise ValueError('Unsupported repair request payload version.')
    request = db.session.get(RepairRequest, int(job.details_json['repair_request_id']))
    run = _start_repair_run(request, job)
    request.root_sync_run_id = run.id
    db.session.commit()
    try:
        fence = lambda: heartbeat_job(
            job.id, worker_id=job.worker_id, claim_token=job.claim_token, commit=False,
        )
        mark_stage(run, RunStage.RECONCILE, commit=False)
        request = dispatch_repair_request(
            request.id, parent_job_id=job.id, lease_fence=fence, commit=False,
        )
        fence()
        add_scopes(run, _run_scopes(request), commit=False)
        record_outcome(
            run, downstream_work_created=(request.outcome_json or {}).get('jobs_dispatched', 0),
            canonical_mutations=0 if request.dry_run else None,
            outcome={'repair_request_id': request.id, 'status': request.status,
                     'plan_fingerprint': request.plan_fingerprint,
                     'estimated_counts': request.estimated_counts_json}, commit=False,
        )
        finalize_run(run, RunStatus.SUCCEEDED, commit=False)
        db.session.commit()
        return {'repair_request_id': request.id, 'status': request.status,
                'plan_fingerprint': request.plan_fingerprint}
    except Exception as exc:
        db.session.rollback()
        record_failure(
            run.id, exc, failure_class=FailureClass.INTERNAL,
            stage=RunStage.RECONCILE, retryable=True, commit=False,
        )
        finalize_run(run.id, RunStatus.FAILED, failed_stage=RunStage.RECONCILE)
        raise


def execute_repair_check_job(job):
    if job.payload_schema_version != REPAIR_PAYLOAD_VERSION:
        raise ValueError('Unsupported repair check payload version.')
    request = db.session.get(RepairRequest, int(job.details_json['repair_request_id']))
    fence = lambda: heartbeat_job(
        job.id, worker_id=job.worker_id, claim_token=job.claim_token, commit=False,
    )
    fence()
    request = check_repair_request(
        request.id, parent_job_id=job.id, lease_fence=fence, commit=True,
    )
    return {'repair_request_id': request.id, 'status': request.status,
            'outcome': request.outcome_json}


def _start_repair_run(request, job):
    run_type = {
        RepairMode.TARGETED.value: RunType.TARGETED_REPAIR,
        RepairMode.BACKFILL.value: RunType.BACKFILL,
        RepairMode.FULL.value: RunType.FULL_RECONCILIATION,
        RepairMode.METHOD_REPLAY.value: RunType.TARGETED_REPAIR,
        RepairMode.RULE_REPLAY.value: RunType.TARGETED_REPAIR,
    }[request.mode]
    run = create_run(
        run_type=run_type,
        trigger_type=(TriggerType.BACKFILL if request.mode == RepairMode.BACKFILL.value else TriggerType.REPAIR),
        source='sp13_repair', job_name=JobType.RUN_REPAIR_REQUEST.value,
        baseball_date=request.baseball_date_end, source_domain=SourceDomain.MULTI_DOMAIN,
        correlation_id=request.correlation_id, scopes=(), commit=False,
    )
    job.sync_run_id = run.id
    return start_run(run, commit=False)


def _run_scopes(request):
    scopes = [(ScopeType.SOURCE_DOMAIN, request.source_domain)]
    scopes.extend((ScopeType.GAME, value) for value in request.scope_json.get('game_pks', []))
    if request.scope_json.get('game_pk'):
        scopes.append((ScopeType.GAME, request.scope_json['game_pk']))
    scopes.extend((ScopeType.TEAM, value) for value in _team_ids(request.scope_json))
    return scopes


def _lock_request(request_id):
    if db.session.get_bind().dialect.name == 'postgresql':
        db.session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': 913000000 + int(request_id)})


def run_repair_worker_once(worker_id, *, lease_seconds=300):
    return run_next_job(
        worker_id,
        {
            JobType.RUN_REPAIR_REQUEST.value: execute_repair_request_job,
            JobType.CHECK_REPAIR_REQUEST.value: execute_repair_check_job,
        },
        job_types=[JobType.RUN_REPAIR_REQUEST, JobType.CHECK_REPAIR_REQUEST],
        lease_seconds=lease_seconds,
    )


__all__ = [
    'MAX_EXPLICIT_BACKFILL_DAYS', 'MAX_STANDARD_BACKFILL_DAYS',
    'REPAIR_CHECK_POLICY_VERSION', 'REPAIR_PLAN_VERSION', 'REPAIR_SCHEMA_VERSION',
    'RepairDomain', 'RepairMode', 'cancel_repair_request', 'check_repair_request',
    'dispatch_repair_request', 'execute_repair_check_job', 'execute_repair_request_job',
    'plan_repair_request', 'run_repair_worker_once', 'submit_repair_request',
]
