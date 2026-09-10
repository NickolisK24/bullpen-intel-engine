"""SP-08 provisional live-game bullpen delta orchestration.

Live state is intentionally mutable and provisional. SP-07 final versions are
the only authoritative completed-game record.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from enum import Enum
import hashlib
import json

from sqlalchemy import text

from models.final_game_reconciliation import FinalGameVersion
from models.game_observation_state import GameObservationState
from models.live_game_delta import LiveGameMutation, ProvisionalPitchingAppearanceState
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from models.sync_run import SyncRun
from services import game_change_detection
from services.adaptive_game_state import GameState
from services.sync_control_plane import (
    FailureClass, RunStage, RunStatus, RunType, ScopeType, SourceDomain,
    TriggerType, add_scopes, create_run, finalize_run, mark_stage,
    record_failure, record_outcome, start_run,
)
from services.sync_jobs import JobScopeType, JobType, enqueue_job, heartbeat_job, run_next_job
from utils.db import db
from utils.time import utc_now_naive


LIVE_POLICY_VERSION = 'live-game-delta-poll-v1'
LIVE_PAYLOAD_SCHEMA_VERSION = 1
LIVE_FACT_FINGERPRINT_VERSION = 'live-appearance-v1'
PRIORITY_RESUMED = 5
PRIORITY_LIVE = 10
PRIORITY_DELAYED = 15

ELIGIBLE_STATES = frozenset({GameState.LIVE.value, GameState.DELAYED.value})
COUNTER_FIELDS = ('pitches_thrown', 'outs_recorded', 'batters_faced')


class LiveMutationType(str, Enum):
    LIVE_APPEARANCE_STARTED = 'live_appearance_started'
    LIVE_APPEARANCE_UPDATED = 'live_appearance_updated'
    LIVE_APPEARANCE_COMPLETED = 'live_appearance_completed'
    LIVE_STARTER_EXITED = 'live_starter_exited'
    LIVE_RELIEVER_ENTERED = 'live_reliever_entered'
    LIVE_MULTI_INNING_REACHED = 'live_multi_inning_reached'
    LIVE_APPEARANCE_CORRECTED = 'live_appearance_corrected'


def live_poll_decision(state, *, now=None, resumed=False):
    now = _naive_utc(now or utc_now_naive())
    if resumed:
        seconds, priority = 0, PRIORITY_RESUMED
    elif state == GameState.LIVE.value:
        seconds, priority = 90, PRIORITY_LIVE
    elif state == GameState.DELAYED.value:
        seconds, priority = 150, PRIORITY_DELAYED
    else:
        return None
    return {'next_poll_at': now + timedelta(seconds=seconds), 'interval_seconds': seconds, 'priority': priority, 'policy_version': LIVE_POLICY_VERSION}


def enqueue_live_poll(game_pk, baseball_date, *, available_at=None, priority=PRIORITY_LIVE,
                      reason='live_follow_up', parent_job_id=None, sync_run_id=None,
                      expected_game_state=GameState.LIVE.value, commit=True):
    available_at = _naive_utc(available_at or utc_now_naive())
    generation = available_at.replace(second=0, microsecond=0).isoformat()
    return enqueue_job(
        job_type=JobType.FETCH_LIVE_GAME_DELTA, scope_type=JobScopeType.GAME,
        scope_key=str(int(game_pk)), product_date=baseball_date,
        dedupe_key=(f'LIVE_GAME:{int(game_pk)}:{generation}:{LIVE_POLICY_VERSION}'
                    + (f':after:{parent_job_id}' if parent_job_id is not None else '')),
        priority=priority, available_at=available_at, sync_run_id=sync_run_id,
        parent_job_id=parent_job_id, payload_schema_version=LIVE_PAYLOAD_SCHEMA_VERSION,
        payload={'game_pk': int(game_pk), 'baseball_date': baseball_date,
                 'expected_game_state': expected_game_state, 'reason': reason,
                 'policy_version': LIVE_POLICY_VERSION}, commit=commit,
    )


def plan_live_game_polls(*, now=None, commit=True):
    now = _naive_utc(now or utc_now_naive())
    rows = ScheduledGame.query.filter(ScheduledGame.operational_state.in_(ELIGIBLE_STATES)).order_by(
        ScheduledGame.game_pk, ScheduledGame.id,
    ).all()
    jobs, seen = [], set()
    for row in rows:
        if row.game_pk in seen:
            continue
        seen.add(row.game_pk)
        state = GameObservationState.query.filter_by(mlb_game_pk=row.game_pk).one_or_none()
        if row.operational_state == GameState.DELAYED.value and not _game_has_started(state):
            continue
        if state is not None and state.next_live_poll_at is not None and state.next_live_poll_at > now:
            continue
        decision = live_poll_decision(row.operational_state, now=now)
        jobs.append(enqueue_live_poll(
            row.game_pk, row.game_date, available_at=now,
            priority=decision['priority'], expected_game_state=row.operational_state,
            commit=False,
        ))
    if commit:
        db.session.commit()
    return jobs


def execute_live_game_delta(job, *, now=None, client=None):
    now = _naive_utc(now or utc_now_naive())
    payload = dict(job.details_json or {})
    game_pk = int(payload.get('game_pk') or job.scope_key)
    baseball_date = _date(payload.get('baseball_date')) or job.product_date
    run = _start_run(job, game_pk, baseball_date)
    try:
        current_state = _operational_state(game_pk)
        prior_observation_state = GameObservationState.query.filter_by(mlb_game_pk=game_pk).one_or_none()
        if current_state not in ELIGIBLE_STATES or (
            current_state == GameState.DELAYED.value and not _game_has_started(prior_observation_state)
        ):
            record_outcome(run, source_reads=0, source_changes=0, canonical_mutations=0,
                           affected_games=0, affected_teams=0, affected_pitchers=0,
                           downstream_work_created=0,
                           outcome={'skipped': 'game_not_live', 'operational_state': current_state}, commit=False)
            finalize_run(run, RunStatus.SUCCEEDED, commit=False)
            db.session.commit()
            return {'sync_run_id': run.id, 'skipped': 'game_not_live'}

        mark_stage(run, RunStage.ACQUIRE, commit=False)
        client = client or game_change_detection.mlb_client
        _lock_game(game_pk)
        observed = game_change_detection.observe_game_change(
            game_pk, client=client, commit=False, create_work_obligation=False,
            sync_run_id=run.id, sync_job_id=job.id, require_live_pitching=True,
        )
        if observed.classification == game_change_detection.SOURCE_FAILURE:
            # The failed SP-03 fetch attempt is durable evidence and must
            # survive the job transaction rollback performed before retry.
            db.session.commit()
            raise RuntimeError(observed.reason)
        heartbeat_job(job.id, worker_id=job.worker_id, claim_token=job.claim_token, commit=False)

        mutations = []
        affected_pitchers, affected_teams = set(), set()
        downstream = None
        if observed.accepted and observed.finality_state == 'not_final':
            state_row = GameObservationState.query.filter_by(mlb_game_pk=game_pk).one()
            projection = (state_row.observation or {}).get('live_pitching') or {}
            if projection.get('completeness') == 'complete_for_observation':
                mark_stage(run, RunStage.CANONICALIZE, commit=False)
                mutations, affected_pitchers, affected_teams = _reconcile_projection(
                    state_row, projection.get('appearances') or [], baseball_date,
                    observed.source_observation_id, run.id, now,
                )
                state_row.live_bullpen_fingerprint = _projection_fingerprint(projection)
                if mutations:
                    downstream = _enqueue_impact(
                        game_pk, baseball_date, observed.source_observation_id,
                        mutations, affected_pitchers, affected_teams, run.id, job.id,
                    )

        state_row = GameObservationState.query.filter_by(mlb_game_pk=game_pk).one_or_none()
        operational = _operational_state(game_pk)
        next_job = None
        decision = live_poll_decision(operational, now=now)
        if decision is not None:
            next_job = enqueue_live_poll(
                game_pk, baseball_date, available_at=decision['next_poll_at'],
                priority=decision['priority'], reason='live_follow_up',
                parent_job_id=job.id, expected_game_state=operational, commit=False,
            )
            if state_row is not None:
                state_row.next_live_poll_at = decision['next_poll_at']
                state_row.live_polling_policy_version = LIVE_POLICY_VERSION
        elif state_row is not None:
            state_row.next_live_poll_at = None
            state_row.live_polling_policy_version = LIVE_POLICY_VERSION

        add_scopes(run, [(ScopeType.TEAM, value) for value in affected_teams] +
                   [(ScopeType.PITCHER, value) for value in affected_pitchers], commit=False)
        record_outcome(
            run, source_reads=1, source_changes=int(observed.changed),
            canonical_mutations=len(mutations), affected_games=int(bool(mutations)),
            affected_teams=len(affected_teams), affected_pitchers=len(affected_pitchers),
            downstream_work_created=int(downstream is not None),
            outcome={'authority_state': 'live', 'source_observation_id': observed.source_observation_id,
                     'classification': observed.classification, 'mutation_ids': [m.id for m in mutations],
                     'next_live_poll_at': decision['next_poll_at'] if decision else None,
                     'policy_version': LIVE_POLICY_VERSION}, commit=False,
        )
        finalize_run(run, RunStatus.SUCCEEDED, commit=False)
        heartbeat_job(job.id, worker_id=job.worker_id, claim_token=job.claim_token, commit=False)
        db.session.commit()
        return {'sync_run_id': run.id, 'source_observation_id': observed.source_observation_id,
                'mutations': len(mutations), 'affected_pitchers': sorted(affected_pitchers),
                'affected_teams': sorted(affected_teams),
                'downstream_job_id': downstream.id if downstream else None,
                'next_poll_job_id': next_job.id if next_job else None}
    except Exception as exc:
        db.session.rollback()
        record_failure(run.id, exc, failure_class=FailureClass.SOURCE, stage=RunStage.ACQUIRE,
                       source_domain=SourceDomain.LIVE_FEED, entity_type='game',
                       entity_ref=game_pk, retryable=True, commit=False)
        finalize_run(run.id, RunStatus.FAILED, failed_stage=RunStage.ACQUIRE, commit=False)
        db.session.commit()
        raise


def run_next_live_game_delta(worker_id, *, now=None, client=None, lease_seconds=300):
    return run_next_job(
        worker_id, {JobType.FETCH_LIVE_GAME_DELTA.value: lambda job: execute_live_game_delta(job, now=now, client=client)},
        job_types=[JobType.FETCH_LIVE_GAME_DELTA], lease_seconds=lease_seconds,
    )


def supersede_live_game_with_final(game_pk, final_game_version_id, *, now=None):
    """Close provisional authority after SP-07 succeeds, preserving live evidence."""
    final = db.session.get(FinalGameVersion, final_game_version_id)
    if final is None or final.game_pk != int(game_pk) or not final.is_current:
        raise ValueError('current final game version is required')
    now = _naive_utc(now or utc_now_naive())
    rows = ProvisionalPitchingAppearanceState.query.filter_by(game_pk=int(game_pk), is_current=True).all()
    for row in rows:
        row.is_current = False
        row.superseded_by_final_game_version_id = final.id
        row.superseded_at = now
    state = GameObservationState.query.filter_by(mlb_game_pk=int(game_pk)).one_or_none()
    if state is not None:
        state.next_live_poll_at = None
    return len(rows)


def _reconcile_projection(state_row, appearances, baseball_date, observation_id, run_id, now):
    current = {row.pitcher_mlb_id: row for row in ProvisionalPitchingAppearanceState.query.filter_by(
        game_pk=state_row.mlb_game_pk, is_current=True,
    ).with_for_update().all()}
    mutations, pitchers, teams = [], set(), set()
    for value in appearances:
        mlb_id = int(value['pitcher_mlb_id'])
        pitcher = Pitcher.query.filter_by(mlb_id=mlb_id).one_or_none()
        if pitcher is None:
            pitcher = Pitcher(mlb_id=mlb_id, full_name=value.get('pitcher_name') or f'MLB pitcher {mlb_id}',
                              team_id=None, active=False, position='P')
            db.session.add(pitcher)
            db.session.flush()
        new_state = _state_payload(value)
        fingerprint = _fingerprint(new_state)
        row = current.get(mlb_id)
        if row is not None and row.fact_fingerprint == fingerprint:
            continue
        old_state = _row_payload(row) if row else None
        old_fingerprint = row.fact_fingerprint if row else None
        regression = row is not None and any(
            old_state.get(field) is not None and new_state.get(field) is not None and new_state[field] < old_state[field]
            for field in COUNTER_FIELDS
        )
        if row is None:
            row = ProvisionalPitchingAppearanceState(
                game_pk=state_row.mlb_game_pk, baseball_date=baseball_date,
                pitcher_id=pitcher.id, pitcher_mlb_id=mlb_id,
                first_observation_id=observation_id, first_seen_at=now,
                authority_state='live', is_current=True,
            )
            db.session.add(row)
        _apply_state(row, value, fingerprint, observation_id, state_row.source_observed_at, now)
        mutation_type = _mutation_type(old_state, new_state, regression)
        mutation = LiveGameMutation(
            mutation_key=f'{state_row.mlb_game_pk}:{observation_id}:{mutation_type}:{mlb_id}',
            mutation_type=mutation_type, game_pk=state_row.mlb_game_pk,
            baseball_date=baseball_date, team_id=value.get('team_id'), pitcher_id=pitcher.id,
            pitcher_mlb_id=mlb_id, source_observation_id=observation_id,
            sync_run_id=run_id, old_fingerprint=old_fingerprint,
            new_fingerprint=fingerprint, old_state_json=old_state, new_state_json=new_state,
            authority_state='live', is_correction=regression,
        )
        db.session.add(mutation)
        db.session.flush()
        mutations.append(mutation); pitchers.add(pitcher.id); teams.add(value.get('team_id'))
    return mutations, pitchers, {value for value in teams if value is not None}


def _mutation_type(old, new, regression):
    if old is None:
        if new['appearance_role'] == 'starter' and new['outing_status'] == 'closed':
            return LiveMutationType.LIVE_STARTER_EXITED.value
        return (LiveMutationType.LIVE_RELIEVER_ENTERED.value if new['appearance_role'] == 'reliever'
                else LiveMutationType.LIVE_APPEARANCE_STARTED.value)
    if regression:
        return LiveMutationType.LIVE_APPEARANCE_CORRECTED.value
    if old['outing_status'] == 'active' and new['outing_status'] == 'closed':
        return (LiveMutationType.LIVE_STARTER_EXITED.value if old['appearance_role'] == 'starter'
                else LiveMutationType.LIVE_APPEARANCE_COMPLETED.value)
    if old.get('current_inning') is not None and new.get('current_inning') is not None and new['current_inning'] > old['current_inning'] and new['appearance_role'] == 'reliever':
        return LiveMutationType.LIVE_MULTI_INNING_REACHED.value
    return LiveMutationType.LIVE_APPEARANCE_UPDATED.value


STATE_FIELDS = ('team_id', 'opponent_team_id', 'side', 'appearance_role', 'appearance_order',
                'outing_status', 'pitches_thrown', 'strikes', 'balls', 'outs_recorded',
                'batters_faced', 'hits_allowed', 'runs_allowed', 'earned_runs', 'walks',
                'strikeouts', 'home_runs_allowed', 'current_inning', 'current_half',
                'entry_inning', 'entry_half', 'entry_outs', 'entry_home_score',
                'entry_away_score', 'entry_base_state', 'inherited_runners')


def _state_payload(value):
    return {field: value.get(field) for field in STATE_FIELDS}


def _row_payload(row):
    return {field: getattr(row, 'team_id_at_appearance' if field == 'team_id' else field) for field in STATE_FIELDS}


def _apply_state(row, value, fingerprint, observation_id, observed_at, now):
    for field in STATE_FIELDS:
        setattr(row, 'team_id_at_appearance' if field == 'team_id' else field, value.get(field))
    row.latest_observation_id = observation_id
    row.latest_source_observed_at = observed_at
    row.fact_fingerprint = fingerprint
    row.fingerprint_version = LIVE_FACT_FINGERPRINT_VERSION
    row.completeness = 'complete_for_observation'
    row.latest_seen_at = now


def _enqueue_impact(game_pk, baseball_date, observation_id, mutations, pitcher_ids, team_ids, run_id, parent_job_id):
    return enqueue_job(
        job_type=JobType.PROCESS_CANONICAL_IMPACT, scope_type=JobScopeType.GAME,
        scope_key=str(game_pk), product_date=baseball_date,
        dedupe_key=f'PROCESS_LIVE_IMPACT:{game_pk}:observation:{observation_id}',
        priority=PRIORITY_LIVE, sync_run_id=run_id, parent_job_id=parent_job_id,
        payload_schema_version=1,
        payload={'mutation_family': 'live_appearance', 'authority_class': 'live',
                 'authority_state': 'live', 'game_pk': game_pk, 'baseball_date': baseball_date,
                 'source_observation_id': observation_id,
                 'mutation_ids': [row.id for row in mutations],
                 'pitcher_ids': sorted(pitcher_ids), 'team_ids': sorted(team_ids)}, commit=False,
    )


def _start_run(job, game_pk, baseball_date):
    parent = db.session.get(SyncRun, job.sync_run_id) if job.sync_run_id else None
    if parent is not None and parent.run_type == RunType.LIVE_GAME.value and parent.status not in {'success', 'partial', 'failed', 'cancelled'}:
        return start_run(parent)
    run = create_run(run_type=RunType.LIVE_GAME, trigger_type=TriggerType.GAME_STATUS_CHANGE,
                     source='live_game_delta', job_name=JobType.FETCH_LIVE_GAME_DELTA.value,
                     baseball_date=baseball_date, source_domain=SourceDomain.LIVE_FEED,
                     parent_sync_run_id=parent.id if parent else None,
                     scopes=[(ScopeType.GAME, game_pk)], commit=False)
    job.sync_run_id = run.id
    db.session.commit()
    return start_run(run)


def _operational_state(game_pk):
    row = ScheduledGame.query.filter_by(game_pk=game_pk).order_by(ScheduledGame.id).first()
    return row.operational_state if row else None


def _game_has_started(state_row):
    observation = state_row.observation if state_row is not None and isinstance(state_row.observation, dict) else {}
    play = observation.get('play') or {}
    linescore = observation.get('linescore') or {}
    return bool((play.get('all_play_count') or 0) > 0 or (linescore.get('inning') or 0) > 0)


def _lock_game(game_pk):
    if db.session.get_bind().dialect.name == 'postgresql':
        db.session.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': 508000000000 + int(game_pk)})


def _fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode()).hexdigest()


def _projection_fingerprint(value):
    return _fingerprint(value)


def _date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _naive_utc(value):
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
