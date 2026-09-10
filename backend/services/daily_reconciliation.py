"""SP-12 morning league planning and reopenable baseball-date closure."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from hashlib import sha256
import json

from sqlalchemy import func, text

from models.atomic_publication import AtomicPublication
from models.canonical_impact import CanonicalImpactPlan, CanonicalImpactPlanMutation
from models.daily_closure import (
    BaseballDateClosure, BaseballDateClosureBlocker, BaseballDateClosureVersion,
)
from models.derived_intelligence import DerivedIntelligenceCohort
from models.final_game_reconciliation import FinalGameMutation, FinalGameVersion
from models.player_transaction import PlayerTransactionSyncWindow
from models.roster_status_snapshot import RosterStatusSnapshot
from models.scheduled_game import ScheduledGame
from models.sync_job import SyncJob
from services.mlb_api import mlb_client
from services.pregame_context import plan_pregame_context_polls
from services.roster_transaction_authority import (
    enqueue_roster_reconciliation, enqueue_transaction_reconciliation,
)
from services.sync_control_plane import (
    RunStage, RunStatus, RunType, ScopeType, SourceDomain, TriggerType,
    create_run, finalize_run, mark_stage, record_outcome, start_run,
)
from services.sync_jobs import (
    CANONICAL_ACTIVE_STATUSES, JobScopeType, JobType, STATUS_DEAD,
    enqueue_job, heartbeat_job, run_next_job,
)
from utils.db import db
from utils.time import utc_now_naive


CLOSURE_SCHEMA_VERSION = 'baseball-date-closure-v1'
RECHECK_POLICY_VERSION = 'baseball-date-recheck-v1'
MORNING_PAYLOAD_VERSION = 1
CLOSURE_PAYLOAD_VERSION = 1
EXPECTED_MLB_TEAMS = 30
MORNING_TRANSACTION_LOOKBACK_DAYS = 2
CORRECTION_LOOKBACK_DAYS = 14
RECHECK_SECONDS = 20 * 60
SUSPENDED_RECHECK_SECONDS = 6 * 60 * 60
PRIORITY_ORCHESTRATION = 50
PRIORITY_RECONCILIATION = 20
PRIORITY_BACKGROUND = 100

RESOLVED_STATES = frozenset({'final', 'postponed', 'cancelled'})
BLOCKING_STATES = frozenset({'scheduled', 'pregame', 'live', 'delayed', 'suspended', 'unknown', 'other'})


@dataclass(frozen=True)
class MorningPlan:
    run_id: int
    baseball_date: date
    team_ids: tuple[int, ...]
    child_job_ids: tuple[int, ...]
    pregame_job_ids: tuple[int, ...]
    repair_job_ids: tuple[int, ...]
    suppressed_obligations: tuple[dict, ...] = ()


@dataclass(frozen=True)
class ClosureDecision:
    baseball_date: date
    fingerprint: str
    evidence: dict
    blockers: tuple[dict, ...]
    publication_id: int | None
    source_data_through: datetime | None

    @property
    def closable(self):
        return not self.blockers


def game_resolution_state(row):
    state = str(row.operational_state or row.status_state or 'unknown').lower()
    if state in RESOLVED_STATES:
        return 'resolved'
    return 'blocking'


def _team_ids(client):
    teams = client.get_all_teams()
    raw_values = [int(row['id']) for row in teams if row.get('id') is not None]
    if len(raw_values) != len(set(raw_values)):
        raise RuntimeError('Official MLB team coverage contains duplicate team IDs.')
    values = sorted(set(raw_values))
    if len(values) != EXPECTED_MLB_TEAMS:
        raise RuntimeError(
            f'Official MLB team coverage expected {EXPECTED_MLB_TEAMS}, received {len(values)}.'
        )
    return tuple(values)


def _enqueue_schedule(target_date, run_id, *, parent_job_id=None):
    return enqueue_job(
        job_type=JobType.FETCH_SCHEDULE,
        scope_type=JobScopeType.BASEBALL_DATE,
        scope_key=target_date.isoformat(),
        product_date=target_date,
        dedupe_key=f'MORNING_SCHEDULE:{target_date.isoformat()}:v1',
        payload={
            'baseball_date': target_date,
            'start_date': target_date,
            'end_date': target_date,
            'reason': 'morning_league_reconciliation',
            'policy_version': 'morning-reconciliation-v1',
        },
        priority=PRIORITY_ORCHESTRATION,
        sync_run_id=run_id,
        parent_job_id=parent_job_id,
        commit=False,
    )


def _enqueue_missing_final(game, run_id, *, parent_job_id=None):
    return enqueue_job(
        job_type=JobType.RECONCILE_FINAL_GAME,
        scope_type=JobScopeType.GAME,
        scope_key=str(game.game_pk),
        product_date=game.game_date,
        dedupe_key=f'RECONCILE_FINAL_GAME:{game.game_pk}:closure-bootstrap-v1',
        payload={
            'game_pk': int(game.game_pk),
            'baseball_date': game.game_date,
            'trigger': 'morning_missing_final_authority',
            'schedule_observation_id': game.source_observation_id,
        },
        payload_schema_version=1,
        priority=PRIORITY_RECONCILIATION,
        sync_run_id=run_id,
        parent_job_id=parent_job_id,
        commit=False,
    )


def _repair_orphaned_pipeline(
    target_date,
    run_id,
    *,
    parent_job_id=None,
    publication_candidate_enabled=True,
    suppressed_obligations=None,
):
    jobs = []
    mutations = FinalGameMutation.query.filter_by(baseball_date=target_date).order_by(
        FinalGameMutation.final_game_version_id, FinalGameMutation.id,
    ).all()
    by_version = {}
    for mutation in mutations:
        exists = CanonicalImpactPlanMutation.query.filter_by(
            mutation_family=(
                'final_appearance' if mutation.pitcher_id is not None else 'final_game_context'
            ),
            source_mutation_id=mutation.id,
        ).first()
        if exists is None:
            by_version.setdefault(mutation.final_game_version_id, []).append(mutation)
    for version_id, rows in by_version.items():
        jobs.append(enqueue_job(
            job_type=JobType.PROCESS_CANONICAL_IMPACT,
            scope_type=JobScopeType.GAME,
            scope_key=str(rows[0].game_pk),
            product_date=target_date,
            dedupe_key=f'CANONICAL_IMPACT:final-game:{rows[0].game_pk}:v{version_id}',
            payload={
                'mutation_family': 'final_appearance',
                'authority_class': 'corrected_final' if any(
                    row.mutation_type.endswith('corrected') for row in rows
                ) else 'final',
                'mutation_ids': [row.id for row in rows],
                'baseball_date': target_date,
            },
            priority=40,
            sync_run_id=run_id,
            parent_job_id=parent_job_id,
            commit=False,
        ))
    plans = CanonicalImpactPlan.query.filter_by(baseball_date=target_date).all()
    for plan in plans:
        cohort = DerivedIntelligenceCohort.query.filter_by(impact_plan_id=plan.id).order_by(
            DerivedIntelligenceCohort.id.desc(),
        ).first()
        if cohort is None and plan.affected_domains_json:
            jobs.append(enqueue_job(
                job_type=JobType.PROCESS_DERIVED_INTELLIGENCE,
                scope_type=JobScopeType.BASEBALL_DATE,
                scope_key=target_date.isoformat(),
                product_date=target_date,
                dedupe_key=f'DERIVED_INTELLIGENCE:{plan.plan_fingerprint}',
                payload={
                    'impact_plan_id': plan.id,
                    'rules_version': plan.rules_version,
                    'authority_class': plan.authority_class,
                    'baseball_date': target_date,
                    'correlation_id': plan.correlation_id,
                },
                priority=60,
                sync_run_id=run_id,
                parent_job_id=parent_job_id,
                commit=False,
            ))
        elif cohort is not None and cohort.status == 'complete':
            publication = AtomicPublication.query.filter_by(cohort_id=cohort.id).first()
            if publication is None:
                if publication_candidate_enabled:
                    jobs.append(enqueue_job(
                        job_type=JobType.PUBLISH_DERIVED_COHORT,
                        scope_type=JobScopeType.BASEBALL_DATE,
                        scope_key=target_date.isoformat(),
                        product_date=target_date,
                        dedupe_key=f'PUBLISH_DERIVED_COHORT:{cohort.cohort_fingerprint}',
                        payload={'cohort_id': cohort.id},
                        priority=70,
                        sync_run_id=run_id,
                        parent_job_id=parent_job_id,
                        commit=False,
                    ))
                elif suppressed_obligations is not None:
                    suppressed_obligations.append({
                        'job_type': JobType.PUBLISH_DERIVED_COHORT.value,
                        'cohort_id': cohort.id,
                        'reason': 'shadow_publication_disabled',
                    })
    return jobs


def plan_morning_reconciliation(
    target_date=None,
    *,
    client=None,
    now=None,
    parent_job_id=None,
    commit=True,
    shadow_mode=False,
    publication_candidate_enabled=True,
    closure_checks_enabled=True,
):
    now = now or utc_now_naive()
    target_date = target_date or now.date()
    client = client or mlb_client
    teams = _team_ids(client)
    run = create_run(
        run_type=RunType.MORNING_RECONCILIATION,
        trigger_type=TriggerType.SCHEDULED,
        source=(
            'sp12_morning_shadow'
            if shadow_mode else 'sp12_morning_reconciliation'
        ),
        job_name='run_morning_reconciliation',
        baseball_date=target_date,
        source_domain=SourceDomain.MULTI_DOMAIN,
        scopes=[(ScopeType.LEAGUE, 'mlb'), *((ScopeType.TEAM, value) for value in teams)],
        commit=False,
    )
    start_run(run, commit=False)
    mark_stage(run, RunStage.RECONCILE, commit=False)
    jobs = [_enqueue_schedule(target_date, run.id, parent_job_id=parent_job_id)]
    jobs.extend(
        enqueue_roster_reconciliation(
            team_id, target_date, priority=PRIORITY_BACKGROUND,
            sync_run_id=run.id, parent_job_id=parent_job_id, commit=False,
        ) for team_id in teams
    )
    jobs.append(enqueue_transaction_reconciliation(
        target_date - timedelta(days=MORNING_TRANSACTION_LOOKBACK_DAYS), target_date,
        priority=PRIORITY_BACKGROUND, sync_run_id=run.id,
        parent_job_id=parent_job_id, commit=False,
    ))
    recent_start = target_date - timedelta(days=CORRECTION_LOOKBACK_DAYS)
    games = _games_between(recent_start, target_date)
    final_versions = {
        value for (value,) in db.session.query(FinalGameVersion.game_pk).filter(
            FinalGameVersion.game_pk.in_([row.game_pk for row in games] or [-1]),
            FinalGameVersion.is_current.is_(True),
        ).all()
    }
    for game in games:
        if _state(game) == 'final' and game.game_pk not in final_versions:
            jobs.append(_enqueue_missing_final(game, run.id, parent_job_id=parent_job_id))
    closure_dates = {
        target_date - timedelta(days=1),
        *(
            row.baseball_date for row in BaseballDateClosure.query.filter(
                BaseballDateClosure.baseball_date >= recent_start,
                BaseballDateClosure.baseball_date < target_date,
            ).all()
        ),
    }
    suppressed_obligations = []
    if closure_checks_enabled:
        for closure_date in sorted(closure_dates):
            jobs.append(enqueue_closure_check(
                closure_date, sync_run_id=run.id, parent_job_id=parent_job_id,
                generation=f'morning:{target_date.isoformat()}', commit=False,
            ))
    else:
        suppressed_obligations.extend({
            'job_type': JobType.CHECK_BASEBALL_DATE_CLOSURE.value,
            'baseball_date': closure_date.isoformat(),
            'reason': 'shadow_closure_disabled',
        } for closure_date in sorted(closure_dates))
    pregame = plan_pregame_context_polls(
        now=now, baseball_dates=[target_date], commit=False,
    )
    repairs = []
    for repair_date in sorted({row.game_date for row in games} | {target_date}):
        repairs.extend(_repair_orphaned_pipeline(
            repair_date,
            run.id,
            parent_job_id=parent_job_id,
            publication_candidate_enabled=publication_candidate_enabled,
            suppressed_obligations=suppressed_obligations,
        ))
    record_outcome(
        run,
        affected_games=len({row.game_pk for row in games}),
        affected_teams=len(teams),
        downstream_work_created=len({row.id for row in [*jobs, *pregame, *repairs]}),
        outcome={
            'teams_expected': EXPECTED_MLB_TEAMS,
            'teams_enumerated': len(teams),
            'child_job_ids': sorted({row.id for row in jobs}),
            'pregame_job_ids': sorted({row.id for row in pregame}),
            'repair_job_ids': sorted({row.id for row in repairs}),
            'shadow_mode': bool(shadow_mode),
            'publication_candidate_enabled': bool(publication_candidate_enabled),
            'closure_checks_enabled': bool(closure_checks_enabled),
            'suppressed_obligations': suppressed_obligations,
            'correction_lookback_days': CORRECTION_LOOKBACK_DAYS,
        },
        commit=False,
    )
    finalize_run(run, RunStatus.SUCCEEDED, commit=False)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return MorningPlan(
        run.id, target_date, teams,
        tuple(sorted({row.id for row in jobs})),
        tuple(sorted({row.id for row in pregame})),
        tuple(sorted({row.id for row in repairs})),
        tuple(suppressed_obligations),
    )


def evaluate_date_closure(baseball_date):
    games = _games_on(baseball_date)
    blockers = []
    final_versions = {
        row.game_pk: row for row in FinalGameVersion.query.filter_by(
            baseball_date=baseball_date, is_current=True,
            core_completeness='complete',
        ).all()
    }
    for game in games:
        state = _state(game)
        if state not in RESOLVED_STATES:
            blockers.append(_blocker('unresolved_game', 'game', game.game_pk, state=state))
        elif state == 'final' and game.game_pk not in final_versions:
            blockers.append(_blocker('final_reconciliation_missing', 'game', game.game_pk))

    window = PlayerTransactionSyncWindow.query.filter(
        PlayerTransactionSyncWindow.source_query_start_date <= baseball_date,
        PlayerTransactionSyncWindow.source_query_end_date >= baseball_date,
    ).order_by(PlayerTransactionSyncWindow.attempted_at.desc()).first()
    transaction_completeness = 'unknown' if window is None else window.status
    if window is None or window.status != 'success':
        blockers.append(_blocker(
            'transaction_partial' if window and window.status == 'partial' else 'source_partial',
            'baseball_date', baseball_date,
            status=transaction_completeness,
        ))

    final_mutations = FinalGameMutation.query.filter_by(baseball_date=baseball_date).all()
    refs = CanonicalImpactPlanMutation.query.filter(
        CanonicalImpactPlanMutation.source_mutation_id.in_(
            [row.id for row in final_mutations] or [-1]
        ),
        CanonicalImpactPlanMutation.mutation_family.in_(
            ('final_appearance', 'final_game_context')
        ),
    ).all()
    referenced_ids = {row.source_mutation_id for row in refs}
    for mutation in final_mutations:
        if mutation.id not in referenced_ids:
            blockers.append(_blocker('pending_impact', 'mutation', mutation.id))
    plan_ids = sorted({row.impact_plan_id for row in refs})
    publications = []
    for plan_id in plan_ids:
        plan = db.session.get(CanonicalImpactPlan, plan_id)
        if plan is not None and not plan.affected_domains_json:
            continue
        cohort = DerivedIntelligenceCohort.query.filter_by(
            impact_plan_id=plan_id, status='complete',
        ).order_by(DerivedIntelligenceCohort.id.desc()).first()
        if cohort is None:
            blockers.append(_blocker('pending_derived_cohort', 'impact_plan', plan_id))
            continue
        # A publication that was current and later superseded by a corrected
        # generation remains valid immutable evidence that this plan completed
        # its publication obligation. Requiring status=published here makes a
        # normal correction invalidate the predecessor plan forever and blocks
        # the date from reclosing even though SP-11 preserved its lineage.
        publication = AtomicPublication.query.filter(
            AtomicPublication.cohort_id == cohort.id,
            AtomicPublication.status.in_(('published', 'superseded')),
        ).order_by(AtomicPublication.id.desc()).first()
        if publication is None:
            blockers.append(_blocker('pending_publication', 'cohort', cohort.id))
        else:
            publications.append(publication)

    jobs = SyncJob.query.filter_by(product_date=baseball_date).all()
    pending_jobs = sum(row.status in CANONICAL_ACTIVE_STATUSES for row in jobs)
    failed_jobs = sum(row.status == STATUS_DEAD for row in jobs)
    if failed_jobs:
        blockers.append(_blocker('failed_required_job', 'baseball_date', baseball_date, count=failed_jobs))

    publication = max(publications, key=lambda row: row.id) if publications else None
    source_data_through = max(
        [row.source_data_through for row in publications if row.source_data_through]
        + ([window.successful_at] if window and window.successful_at else [])
        + [datetime.combine(baseball_date, time.min)],
    )
    roster_count = db.session.query(func.count(func.distinct(RosterStatusSnapshot.team_id))).filter(
        RosterStatusSnapshot.snapshot_date == baseball_date,
    ).scalar() or 0
    optional_outstanding = any(
        row.pbp_completeness != 'complete' for row in final_versions.values()
    )
    evidence = {
        'schema_version': CLOSURE_SCHEMA_VERSION,
        'baseball_date': baseball_date.isoformat(),
        'games': [
            {'game_pk': row.game_pk, 'state': _state(row),
             'final_version_id': final_versions.get(row.game_pk).id if row.game_pk in final_versions else None}
            for row in games
        ],
        'expected_games': len(games),
        'resolved_games': sum(_state(row) in RESOLVED_STATES for row in games),
        'final_games': sum(_state(row) == 'final' for row in games),
        'reconciled_final_games': sum(row.game_pk in final_versions for row in games if _state(row) == 'final'),
        'reconciled_rosters': int(roster_count),
        'transaction_window_id': window.id if window else None,
        'transaction_completeness': transaction_completeness,
        'impact_plan_ids': plan_ids,
        'publication_ids': sorted(row.id for row in publications),
        'publication_id': publication.id if publication else None,
        'pending_jobs': pending_jobs,
        'failed_jobs': failed_jobs,
        'optional_enrichment_outstanding': optional_outstanding,
    }
    # Operational queue counts intentionally do not participate. A retry or
    # completed recheck cannot reopen historical truth; only authority inputs do.
    fingerprint = _fingerprint({
        key: evidence[key] for key in (
            'schema_version', 'baseball_date', 'games', 'transaction_window_id',
            'transaction_completeness', 'impact_plan_ids', 'publication_ids',
            'publication_id', 'optional_enrichment_outstanding',
        )
    })
    return ClosureDecision(
        baseball_date, fingerprint, evidence, tuple(_dedupe_blockers(blockers)),
        publication.id if publication else None, source_data_through,
    )


def check_baseball_date_closure(
    baseball_date, *, sync_run_id=None, parent_job_id=None, now=None,
    lease_fence=None, schedule_recheck=True, commit=True,
):
    now = now or utc_now_naive()
    _lock_date(baseball_date)
    closure = BaseballDateClosure.query.filter_by(baseball_date=baseball_date).with_for_update().one_or_none()
    if closure is None:
        closure = BaseballDateClosure(
            baseball_date=baseball_date,
            status='open',
            closure_schema_version=CLOSURE_SCHEMA_VERSION,
            recheck_policy_version=RECHECK_POLICY_VERSION,
        )
        db.session.add(closure)
        db.session.flush()
    prior_status = closure.status
    prior_fingerprint = closure.closure_fingerprint
    decision = evaluate_date_closure(baseball_date)
    if lease_fence:
        lease_fence()
    closure.status = 'checking'
    closure.first_checked_at = closure.first_checked_at or now
    _apply_decision(closure, decision, now, sync_run_id)
    BaseballDateClosureBlocker.query.filter_by(closure_id=closure.id).delete(
        synchronize_session=False,
    )
    for value in decision.blockers:
        db.session.add(BaseballDateClosureBlocker(closure_id=closure.id, **value))

    changed_closed_truth = prior_status == 'closed' and prior_fingerprint != decision.fingerprint
    repair_jobs = _enqueue_closure_repairs(
        decision, sync_run_id=sync_run_id, parent_job_id=parent_job_id,
    )
    if changed_closed_truth:
        closure.status = 'reopened'
        closure.reopened_at = now
        closure.reopened_count += 1
        _append_version(closure, 'reopened', decision, sync_run_id, now)
        closure.next_check_at = now + timedelta(seconds=RECHECK_SECONDS)
        if schedule_recheck:
            enqueue_closure_check(
                baseball_date, available_at=closure.next_check_at,
                sync_run_id=sync_run_id, parent_job_id=parent_job_id,
                generation=f'{closure.current_version_number}:{int(closure.next_check_at.timestamp())}',
                commit=False,
            )
    elif decision.closable:
        closure.status = 'closed'
        closure.closed_at = now
        closure.next_check_at = None
        if prior_status != 'closed' or prior_fingerprint != decision.fingerprint:
            _append_version(closure, 'closed', decision, sync_run_id, now)
    else:
        closure.status = 'reopened' if changed_closed_truth else 'blocked'
        delay = (
            SUSPENDED_RECHECK_SECONDS
            if any(row['blocker_type'] == 'unresolved_game' and row['details_json'].get('state') == 'suspended'
                   for row in decision.blockers)
            else RECHECK_SECONDS
        )
        closure.next_check_at = now + timedelta(seconds=delay)
        if schedule_recheck:
            enqueue_closure_check(
                baseball_date, available_at=closure.next_check_at,
                sync_run_id=sync_run_id, parent_job_id=parent_job_id,
                generation=f'{closure.current_version_number}:{int(closure.next_check_at.timestamp())}',
                commit=False,
            )
    closure.metrics_json['repair_job_ids'] = sorted({row.id for row in repair_jobs})
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return closure, decision


def _enqueue_closure_repairs(decision, *, sync_run_id=None, parent_job_id=None):
    jobs = []
    games = {row.game_pk: row for row in _games_on(decision.baseball_date)}
    for blocker in decision.blockers:
        if blocker['blocker_type'] == 'final_reconciliation_missing':
            game = games.get(int(blocker['entity_key']))
            if game is not None:
                jobs.append(_enqueue_missing_final(
                    game, sync_run_id, parent_job_id=parent_job_id,
                ))
        elif blocker['blocker_type'] in {'transaction_partial', 'source_partial'}:
            jobs.append(enqueue_transaction_reconciliation(
                decision.baseball_date - timedelta(days=MORNING_TRANSACTION_LOOKBACK_DAYS),
                decision.baseball_date,
                priority=PRIORITY_BACKGROUND, sync_run_id=sync_run_id,
                parent_job_id=parent_job_id, commit=False,
            ))
    jobs.extend(_repair_orphaned_pipeline(
        decision.baseball_date, sync_run_id, parent_job_id=parent_job_id,
    ))
    return jobs


def enqueue_morning_reconciliation(target_date, *, available_at=None, commit=True):
    return enqueue_job(
        job_type=JobType.RUN_MORNING_RECONCILIATION,
        scope_type=JobScopeType.LEAGUE,
        scope_key='mlb', product_date=target_date,
        dedupe_key=f'MORNING_RECONCILIATION:{target_date.isoformat()}:v1',
        payload={'baseball_date': target_date}, payload_schema_version=MORNING_PAYLOAD_VERSION,
        priority=PRIORITY_ORCHESTRATION, available_at=available_at, commit=commit,
    )


def enqueue_closure_check(
    baseball_date, *, available_at=None, sync_run_id=None, parent_job_id=None,
    generation='initial', commit=True,
):
    return enqueue_job(
        job_type=JobType.CHECK_BASEBALL_DATE_CLOSURE,
        scope_type=JobScopeType.BASEBALL_DATE,
        scope_key=baseball_date.isoformat(), product_date=baseball_date,
        dedupe_key=f'BASEBALL_DATE_CLOSURE:{baseball_date.isoformat()}:{generation}:v1',
        payload={'baseball_date': baseball_date, 'policy_version': RECHECK_POLICY_VERSION},
        payload_schema_version=CLOSURE_PAYLOAD_VERSION, priority=PRIORITY_ORCHESTRATION,
        available_at=available_at, sync_run_id=sync_run_id,
        parent_job_id=parent_job_id, commit=commit,
    )


def execute_morning_job(job, *, client=None):
    value = (job.details_json or {}).get('baseball_date') or job.product_date
    target_date = value if isinstance(value, date) else date.fromisoformat(str(value))
    return plan_morning_reconciliation(
        target_date, client=client, parent_job_id=job.id,
    ).__dict__


def execute_closure_job(job):
    value = (job.details_json or {}).get('baseball_date') or job.product_date
    target_date = value if isinstance(value, date) else date.fromisoformat(str(value))
    run = create_run(
        run_type=RunType.NIGHTLY_FINALIZATION, trigger_type=TriggerType.SCHEDULED,
        source='sp12_nightly_closure', job_name=JobType.CHECK_BASEBALL_DATE_CLOSURE.value,
        baseball_date=target_date, source_domain=SourceDomain.OPERATIONS,
        scopes=[(ScopeType.LEAGUE, 'mlb')], commit=False,
    )
    job.sync_run_id = run.id
    db.session.commit()
    start_run(run)
    mark_stage(run, RunStage.RECONCILE)
    fence = lambda: heartbeat_job(
        job.id, worker_id=job.worker_id, claim_token=job.claim_token, commit=False,
    )
    closure, decision = check_baseball_date_closure(
        target_date, sync_run_id=run.id, parent_job_id=job.id,
        lease_fence=fence, commit=False,
    )
    record_outcome(
        run, affected_games=decision.evidence['expected_games'],
        affected_teams=EXPECTED_MLB_TEAMS,
        warnings_count=len(decision.blockers),
        downstream_work_created=int(closure.next_check_at is not None),
        outcome={'closure_id': closure.id, 'status': closure.status,
                 'fingerprint': closure.closure_fingerprint,
                 'blockers': list(decision.blockers)}, commit=False,
    )
    finalize_run(run, RunStatus.SUCCEEDED if closure.status == 'closed' else RunStatus.PARTIAL, commit=False)
    db.session.commit()
    return {'closure_id': closure.id, 'status': closure.status, 'blockers': len(decision.blockers)}


def run_reconciliation_worker_once(worker_id, *, client=None, lease_seconds=300):
    return run_next_job(
        worker_id,
        {
            JobType.RUN_MORNING_RECONCILIATION.value: lambda job: execute_morning_job(job, client=client),
            JobType.CHECK_BASEBALL_DATE_CLOSURE.value: execute_closure_job,
        },
        job_types=[JobType.RUN_MORNING_RECONCILIATION, JobType.CHECK_BASEBALL_DATE_CLOSURE],
        lease_seconds=lease_seconds,
    )


def _games_on(value):
    return _games_between(value, value)


def _games_between(start, end):
    rows = ScheduledGame.query.filter(
        ScheduledGame.game_date >= start, ScheduledGame.game_date <= end,
    ).order_by(ScheduledGame.game_date, ScheduledGame.game_pk, ScheduledGame.id).all()
    games = {}
    for row in rows:
        games.setdefault(row.game_pk, row)
    return list(games.values())


def _state(game):
    return str(game.operational_state or game.status_state or 'unknown').lower()


def _blocker(blocker_type, entity_type, entity_key, **details):
    return {
        'blocker_type': blocker_type, 'entity_type': entity_type,
        'entity_key': str(entity_key), 'retryable': True, 'details_json': details,
    }


def _dedupe_blockers(values):
    result = {}
    for row in values:
        key = (row['blocker_type'], row['entity_type'], row['entity_key'])
        result[key] = row
    return [result[key] for key in sorted(result)]


def _fingerprint(value):
    raw = json.dumps(value, sort_keys=True, separators=(',', ':'), default=str)
    return sha256(raw.encode('utf-8')).hexdigest()


def _lock_date(value):
    if db.session.get_bind().dialect.name == 'postgresql':
        db.session.execute(
            text('SELECT pg_advisory_xact_lock(:key)'),
            {'key': 612000000 + int(value.strftime('%Y%m%d'))},
        )


def _apply_decision(closure, decision, now, sync_run_id):
    evidence = decision.evidence
    closure.expected_games = evidence['expected_games']
    closure.resolved_games = evidence['resolved_games']
    closure.final_games = evidence['final_games']
    closure.reconciled_final_games = evidence['reconciled_final_games']
    closure.unresolved_games = evidence['expected_games'] - evidence['resolved_games']
    closure.reconciled_rosters = evidence['reconciled_rosters']
    closure.transaction_completeness = evidence['transaction_completeness']
    closure.pending_jobs = evidence['pending_jobs']
    closure.failed_jobs = evidence['failed_jobs']
    closure.required_publications_complete = not any(
        row['blocker_type'] in {
            'pending_impact', 'pending_derived_cohort', 'pending_publication',
        }
        for row in decision.blockers
    )
    closure.optional_enrichment_outstanding = evidence['optional_enrichment_outstanding']
    closure.source_data_through = decision.source_data_through
    closure.closure_fingerprint = decision.fingerprint
    closure.publication_id = decision.publication_id
    closure.sync_run_id = sync_run_id
    closure.metrics_json = {
        'blocker_count': len(decision.blockers),
        'time_to_closure_seconds': (
            int((now - closure.first_checked_at).total_seconds()) if closure.first_checked_at else 0
        ),
        **evidence,
    }
    closure.updated_at = now


def _append_version(closure, event_type, decision, sync_run_id, now):
    predecessor = BaseballDateClosureVersion.query.filter_by(closure_id=closure.id).order_by(
        BaseballDateClosureVersion.version_number.desc(),
    ).first()
    number = (predecessor.version_number if predecessor else 0) + 1
    db.session.add(BaseballDateClosureVersion(
        closure_id=closure.id, version_number=number,
        predecessor_version_id=predecessor.id if predecessor else None,
        baseball_date=closure.baseball_date, event_type=event_type,
        closure_fingerprint=decision.fingerprint, publication_id=decision.publication_id,
        evidence_json={**decision.evidence, 'blockers': list(decision.blockers)},
        sync_run_id=sync_run_id, created_at=now,
    ))
    closure.current_version_number = number


__all__ = [
    'BLOCKING_STATES', 'CLOSURE_SCHEMA_VERSION', 'ClosureDecision',
    'EXPECTED_MLB_TEAMS', 'MorningPlan', 'RECHECK_POLICY_VERSION',
    'RESOLVED_STATES', 'check_baseball_date_closure', 'enqueue_closure_check',
    'enqueue_morning_reconciliation', 'evaluate_date_closure',
    'game_resolution_state', 'plan_morning_reconciliation',
    'run_reconciliation_worker_once',
]
