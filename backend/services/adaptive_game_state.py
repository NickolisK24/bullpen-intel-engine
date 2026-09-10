"""SP-04 adaptive schedule and game-state orchestration.

This module owns operational game-state vocabulary, meaningful transition
classification, polling policy, and the one-shot ``fetch_schedule`` worker. It
does not reconcile final games or ingest live baseball events.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
import hashlib
import logging

from models.scheduled_game import ScheduledGame
from services.mlb_api import mlb_client
from services.schedule_ingestion import _schedule_source_identity, ingest_games
from services.source_observations import (
    ObservationCompleteness,
    ObservationOutcome,
    PayloadKind,
    canonical_record_collection,
    record_source_fetch_failure,
    record_source_observation,
    stable_json_dumps,
)
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


logger = logging.getLogger(__name__)

POLLING_POLICY_VERSION = 'game-state-poll-v1'
POLL_PAYLOAD_SCHEMA_VERSION = 1
GAME_STATE_FINGERPRINT_VERSION = 'game-state-v1'

PRIORITY_ACTIVE = 10
PRIORITY_NEAR_START = 20
PRIORITY_PREGAME = 25
PRIORITY_NORMAL = 100
PRIORITY_COLD = 300


class GameState(str, Enum):
    SCHEDULED = 'scheduled'
    PREGAME = 'pregame'
    LIVE = 'live'
    DELAYED = 'delayed'
    SUSPENDED = 'suspended'
    POSTPONED = 'postponed'
    CANCELLED = 'cancelled'
    FINAL = 'final'
    UNKNOWN = 'unknown'


class GameStateTransition(str, Enum):
    GAME_DISCOVERED = 'game_discovered'
    GAME_TIME_CHANGED = 'game_time_changed'
    GAME_STATUS_CHANGED = 'game_status_changed'
    GAME_PREGAME = 'game_pregame'
    GAME_STARTED = 'game_started'
    GAME_DELAYED = 'game_delayed'
    GAME_SUSPENDED = 'game_suspended'
    GAME_POSTPONED = 'game_postponed'
    GAME_RESUMED = 'game_resumed'
    GAME_FINAL = 'game_final'
    GAME_FINAL_CORRECTED = 'game_final_corrected'


@dataclass(frozen=True)
class GameStateSnapshot:
    game_pk: int
    baseball_date: date
    scheduled_at: datetime | None
    state: str
    raw_status_code: str | None
    raw_detailed_state: str | None
    raw_abstract_state: str | None
    home_team_id: int | None
    away_team_id: int | None
    home_score: int | None
    away_score: int | None
    game_number: int | None
    doubleheader: str | None
    resumed_from_game_pk: int | None
    resumed_to_game_pk: int | None
    fingerprint: str


@dataclass(frozen=True)
class PollDecision:
    next_poll_at: datetime
    interval_seconds: int
    priority: int
    policy_version: str = POLLING_POLICY_VERSION


def observe_schedule(
    start_date,
    end_date,
    *,
    completeness=ObservationCompleteness.COMPLETE,
    commit=True,
    sync_run_id=None,
    sync_job_id=None,
):
    """Fetch SP-04 schedule evidence without mutating schedule authority.

    The identity builder and source-evidence contract are the established
    schedule/SP-03 implementations. Keeping this wrapper here preserves the
    governed byte-level freeze on the legacy ingestion module.
    """
    start_value = _iso(start_date)
    end_value = _iso(end_date)
    identity = _schedule_source_identity(start_value, end_value)
    fetch_started_at = utc_now_naive()
    try:
        games = list(mlb_client.get_schedule(
            start_date=start_value, end_date=end_value,
        ) or [])
    except Exception as exc:
        try:
            record_source_fetch_failure(
                identity=identity,
                error=exc,
                attempt_started_at=fetch_started_at,
                http_status=getattr(exc, 'status_code', None),
                sync_run_id=sync_run_id,
                sync_job_id=sync_job_id,
                commit=commit,
            )
        except Exception:
            logger.exception('Could not persist failed adaptive schedule fetch evidence')
        raise
    result = record_source_observation(
        identity=identity,
        payload=games,
        fingerprint_payload=canonical_record_collection(games),
        completeness=completeness,
        payload_schema_version=1,
        payload_kind=PayloadKind.NORMALIZED_JSON,
        record_count=len(games),
        empty_valid=not games,
        attempt_started_at=fetch_started_at,
        sync_run_id=sync_run_id,
        sync_job_id=sync_job_id,
        commit=commit,
    )
    return games, result


def normalize_game_state(game_or_status) -> str:
    value = game_or_status or {}
    status = value.get('status') if isinstance(value, dict) and 'status' in value else value
    status = status if isinstance(status, dict) else {}
    code = str(status.get('statusCode') or '').strip().upper()
    detailed = str(status.get('detailedState') or '').strip().lower()
    abstract = str(status.get('abstractGameState') or '').strip().lower()

    if 'postpon' in detailed:
        return GameState.POSTPONED.value
    if 'suspend' in detailed:
        return GameState.SUSPENDED.value
    if 'cancel' in detailed or code == 'C':
        return GameState.CANCELLED.value
    if 'delay' in detailed:
        return GameState.DELAYED.value
    if code in {'F', 'O', 'FR', 'FT'} or detailed in {
        'final', 'game over', 'completed early', 'final: tied',
    } or detailed.startswith('final'):
        return GameState.FINAL.value
    if code == 'I' or abstract == 'live' or 'progress' in detailed or detailed == 'live':
        return GameState.LIVE.value
    if detailed in {'pre-game', 'pregame', 'warmup'} or code in {'P', 'PW', 'PR'}:
        return GameState.PREGAME.value
    if code == 'S' or abstract == 'preview' or detailed == 'scheduled':
        return GameState.SCHEDULED.value
    return GameState.UNKNOWN.value


def snapshot_from_source_game(game) -> GameStateSnapshot | None:
    if not isinstance(game, dict):
        return None
    game_pk = _int(game.get('gamePk'))
    baseball_date = _date(game.get('officialDate') or str(game.get('gameDate') or '')[:10])
    if game_pk is None or baseball_date is None:
        return None
    teams = game.get('teams') or {}
    status = game.get('status') or {}
    home = teams.get('home') or {}
    away = teams.get('away') or {}
    state = normalize_game_state(game)
    meaningful = {
        'version': GAME_STATE_FINGERPRINT_VERSION,
        'game_pk': game_pk,
        'baseball_date': baseball_date.isoformat(),
        'scheduled_at': _datetime(game.get('gameDate')),
        'state': state,
        'status_code': _text(status.get('statusCode')),
        'detailed_state': _text(status.get('detailedState')),
        'abstract_state': _text(status.get('abstractGameState')),
        'home_team_id': _team_id(home),
        'away_team_id': _team_id(away),
        # Schedule score churn is not a game-state transition. Final scores are
        # retained in the projection solely to distinguish later official final
        # corrections without activating live-data semantics in SP-04.
        'home_score': _int(home.get('score')) if state == GameState.FINAL.value else None,
        'away_score': _int(away.get('score')) if state == GameState.FINAL.value else None,
        'game_number': _int(game.get('gameNumber')),
        'doubleheader': _text(game.get('doubleHeader')),
        'resumed_from_game_pk': _int(game.get('resumedFrom') or game.get('resumedFromGamePk')),
        'resumed_to_game_pk': _int(game.get('resumedTo') or game.get('rescheduledGamePk')),
    }
    scheduled_at = meaningful['scheduled_at']
    fingerprint = hashlib.sha256(stable_json_dumps(meaningful).encode('utf-8')).hexdigest()
    return GameStateSnapshot(
        game_pk=game_pk,
        baseball_date=baseball_date,
        scheduled_at=_datetime_value(scheduled_at),
        state=meaningful['state'],
        raw_status_code=meaningful['status_code'],
        raw_detailed_state=meaningful['detailed_state'],
        raw_abstract_state=meaningful['abstract_state'],
        home_team_id=meaningful['home_team_id'],
        away_team_id=meaningful['away_team_id'],
        home_score=meaningful['home_score'],
        away_score=meaningful['away_score'],
        game_number=meaningful['game_number'],
        doubleheader=meaningful['doubleheader'],
        resumed_from_game_pk=meaningful['resumed_from_game_pk'],
        resumed_to_game_pk=meaningful['resumed_to_game_pk'],
        fingerprint=fingerprint,
    )


def snapshot_from_scheduled_game(row) -> GameStateSnapshot:
    state = row.operational_state or _legacy_operational_state(row)
    meaningful = {
        'version': GAME_STATE_FINGERPRINT_VERSION,
        'game_pk': row.game_pk,
        'baseball_date': row.game_date.isoformat(),
        'scheduled_at': row.game_datetime.isoformat() if row.game_datetime else None,
        'state': state,
        'status_code': row.status_code,
        'detailed_state': row.status_detailed_state,
        'abstract_state': row.status_abstract_state,
        'home_team_id': row.team_id if row.home_away == 'home' else row.opponent_team_id,
        'away_team_id': row.team_id if row.home_away == 'away' else row.opponent_team_id,
        # Scores are not canonical schedule columns. The persisted SP-04
        # fingerprint retains their correction sensitivity after first ingest.
        'home_score': None,
        'away_score': None,
        'game_number': row.game_number,
        'doubleheader': row.doubleheader,
        'resumed_from_game_pk': row.resumed_from_game_pk,
        'resumed_to_game_pk': row.resumed_to_game_pk,
    }
    fingerprint = row.game_state_fingerprint or hashlib.sha256(
        stable_json_dumps(meaningful).encode('utf-8')
    ).hexdigest()
    return GameStateSnapshot(
        game_pk=row.game_pk,
        baseball_date=row.game_date,
        scheduled_at=row.game_datetime,
        state=state,
        raw_status_code=row.status_code,
        raw_detailed_state=row.status_detailed_state,
        raw_abstract_state=row.status_abstract_state,
        home_team_id=meaningful['home_team_id'], away_team_id=meaningful['away_team_id'],
        home_score=None, away_score=None, game_number=row.game_number,
        doubleheader=row.doubleheader, resumed_from_game_pk=row.resumed_from_game_pk,
        resumed_to_game_pk=row.resumed_to_game_pk, fingerprint=fingerprint,
    )


def classify_game_state_transition(previous, current):
    if previous is None:
        return GameStateTransition.GAME_DISCOVERED.value
    if previous.state == current.state:
        if previous.state == GameState.FINAL.value and previous.fingerprint != current.fingerprint:
            return GameStateTransition.GAME_FINAL_CORRECTED.value
        if previous.scheduled_at != current.scheduled_at:
            return GameStateTransition.GAME_TIME_CHANGED.value
        return None
    if current.state == GameState.FINAL.value:
        return GameStateTransition.GAME_FINAL.value
    if current.state == GameState.PREGAME.value:
        return GameStateTransition.GAME_PREGAME.value
    if current.state == GameState.LIVE.value:
        if previous.state in {GameState.DELAYED.value, GameState.SUSPENDED.value}:
            return GameStateTransition.GAME_RESUMED.value
        return GameStateTransition.GAME_STARTED.value
    if current.state == GameState.DELAYED.value:
        return GameStateTransition.GAME_DELAYED.value
    if current.state == GameState.SUSPENDED.value:
        return GameStateTransition.GAME_SUSPENDED.value
    if current.state == GameState.POSTPONED.value:
        return GameStateTransition.GAME_POSTPONED.value
    return GameStateTransition.GAME_STATUS_CHANGED.value


def polling_decision(state, scheduled_at, *, now=None, final_reconciled=False):
    now = _naive_utc(now or utc_now_naive())
    scheduled_at = _naive_utc(scheduled_at) if scheduled_at else None
    if state == GameState.LIVE.value:
        seconds, priority = 90, PRIORITY_ACTIVE
    elif state == GameState.DELAYED.value:
        seconds, priority = 120, PRIORITY_ACTIVE
    elif state == GameState.PREGAME.value:
        seconds, priority = 150, PRIORITY_PREGAME
    elif state == GameState.SUSPENDED.value:
        seconds, priority = 1800, PRIORITY_COLD
    elif state == GameState.POSTPONED.value:
        seconds, priority = 21600, PRIORITY_COLD
    elif state == GameState.CANCELLED.value:
        seconds, priority = 86400, PRIORITY_COLD
    elif state == GameState.FINAL.value:
        seconds, priority = ((86400, PRIORITY_COLD) if final_reconciled else (900, PRIORITY_NEAR_START))
    elif state == GameState.SCHEDULED.value and scheduled_at is not None:
        until = (scheduled_at - now).total_seconds()
        if until > 86400:
            seconds, priority = 21600, PRIORITY_COLD
        elif until > 14400:
            seconds, priority = 1800, PRIORITY_NORMAL
        elif until > 3600:
            seconds, priority = 900, PRIORITY_NORMAL
        elif until > 0:
            seconds, priority = 300, PRIORITY_NEAR_START
        else:
            seconds, priority = 120, PRIORITY_NEAR_START
    else:
        seconds, priority = 1800, PRIORITY_NORMAL
    seconds = max(60, min(86400, seconds))
    return PollDecision(now + timedelta(seconds=seconds), seconds, priority)


def empty_schedule_poll_decision(baseball_date, *, now=None):
    now = _naive_utc(now or utc_now_naive())
    delta = (baseball_date - now.date()).days
    seconds = 21600 if delta == 0 else (43200 if delta > 0 else 86400)
    return PollDecision(now + timedelta(seconds=seconds), seconds, PRIORITY_COLD)


def plan_game_state_polls(
    *, now=None, baseball_dates=None, lookback_days=1, lookahead_days=7,
    commit=True,
):
    """Enqueue one due date-grain fetch per baseball date."""
    now = _naive_utc(now or utc_now_naive())
    query = ScheduledGame.query
    if baseball_dates:
        query = query.filter(ScheduledGame.game_date.in_(tuple(baseball_dates)))
    else:
        query = query.filter(
            ScheduledGame.game_date >= now.date() - timedelta(days=lookback_days),
            ScheduledGame.game_date <= now.date() + timedelta(days=lookahead_days),
        )
    rows = query.filter(
        (ScheduledGame.next_poll_at.is_(None)) | (ScheduledGame.next_poll_at <= now)
    ).order_by(ScheduledGame.game_date.asc(), ScheduledGame.game_pk.asc()).all()
    by_date = {}
    for row in rows:
        by_date.setdefault(row.game_date, {})[row.game_pk] = row
    jobs = []
    for baseball_date, games in by_date.items():
        decisions = [polling_decision(
            snapshot_from_scheduled_game(row).state, row.game_datetime, now=now
        ) for row in games.values()]
        priority = min((item.priority for item in decisions), default=PRIORITY_NORMAL)
        jobs.append(_enqueue_poll(
            baseball_date, now, priority=priority,
            reason='due_game_state', game_pks=sorted(games), commit=False,
        ))
    if commit:
        db.session.commit()
    return jobs


def execute_game_state_poll(job, *, now=None, observer=observe_schedule):
    """Execute one claimed date-grain schedule poll; settlement remains SP-02."""
    now = _naive_utc(now or utc_now_naive())
    payload = dict(job.details_json or {})
    baseball_date = _date(payload.get('baseball_date')) or job.product_date
    run = _start_or_attach_run(job, baseball_date)
    try:
        mark_stage(run, RunStage.ACQUIRE)
        games, source_result = observer(
            baseball_date, baseball_date,
            sync_run_id=run.id, sync_job_id=job.id,
        )
        # Fetches may be the longest part of this one-shot worker. Revalidate
        # SP-02 ownership before any canonical mutation; a stale/reclaimed
        # worker is fenced here and again by final settlement.
        heartbeat_job(
            job.id,
            worker_id=job.worker_id,
            claim_token=job.claim_token,
        )
        observation = source_result.observation
        completeness = observation.completeness if observation is not None else None
        authoritative = completeness == ObservationCompleteness.COMPLETE.value
        transitions = []
        canonical_games = 0
        downstream_jobs = []
        snapshots = [value for value in (snapshot_from_source_game(game) for game in games) if value]

        if authoritative and source_result.outcome != ObservationOutcome.UNCHANGED.value:
            previous = {
                row.game_pk: snapshot_from_scheduled_game(row)
                for row in _one_row_per_game([item.game_pk for item in snapshots])
            }
            mark_stage(run, RunStage.CANONICALIZE)
            ingest_games(
                games,
                source='adaptive_game_state',
                source_observation_id=observation.id,
                commit=False,
            )
            for current in snapshots:
                prior = previous.get(current.game_pk)
                transition = classify_game_state_transition(prior, current)
                meaningful_change = prior is None or prior.fingerprint != current.fingerprint
                if meaningful_change:
                    canonical_games += 1
                if transition is not None:
                    transitions.append({'game_pk': current.game_pk, 'transition': transition})
                decision = polling_decision(current.state, current.scheduled_at, now=now)
                _update_operational_rows(
                    current, decision, transition, observation.id, now=now,
                )
                if transition in {
                    GameStateTransition.GAME_FINAL.value,
                    GameStateTransition.GAME_FINAL_CORRECTED.value,
                }:
                    downstream_jobs.append(_enqueue_final_reconciliation(
                        current, observation.id, transition, run.id, job.id,
                    ))
        elif authoritative:
            # An unchanged authoritative fetch still advances durable poll time,
            # but never creates a source version, transition, or canonical work.
            for row in _rows_for_date(baseball_date):
                state = row.operational_state or _legacy_operational_state(row)
                decision = polling_decision(state, row.game_datetime, now=now)
                row.next_poll_at = decision.next_poll_at
                row.polling_policy_version = decision.policy_version

        add_scopes(run, [(ScopeType.GAME, item.game_pk) for item in snapshots], commit=False)
        poll_snapshots = snapshots if authoritative else [
            snapshot_from_scheduled_game(row) for row in _one_row_per_game_for_date(baseball_date)
        ]
        next_decision = _next_date_poll(poll_snapshots, baseball_date, now=now)
        next_job = _enqueue_poll(
            baseball_date,
            next_decision.next_poll_at,
            priority=next_decision.priority,
            reason='adaptive_follow_up',
            game_pks=[item.game_pk for item in poll_snapshots],
            parent_job_id=job.id,
            commit=False,
        )
        record_outcome(
            run,
            source_reads=1,
            source_changes=int(bool(source_result.changed)),
            canonical_mutations=canonical_games,
            affected_games=canonical_games,
            downstream_work_created=len(downstream_jobs),
            warnings_count=int(not authoritative),
            outcome={
                'source_observation_id': observation.id if observation else None,
                'source_observation_outcome': source_result.outcome,
                'completeness': completeness,
                'transitions': transitions,
                'next_poll_at': next_decision.next_poll_at,
                'polling_policy_version': POLLING_POLICY_VERSION,
                'next_poll_job_id': next_job.id,
            },
            commit=False,
        )
        finalize_run(run, RunStatus.SUCCEEDED, commit=False)
        heartbeat_job(
            job.id,
            worker_id=job.worker_id,
            claim_token=job.claim_token,
            commit=False,
        )
        db.session.commit()
        return {
            'sync_run_id': run.id,
            'source_observation_id': observation.id if observation else None,
            'source_outcome': source_result.outcome,
            'canonical_mutations': canonical_games,
            'transitions': transitions,
            'downstream_job_ids': [item.id for item in downstream_jobs],
            'next_poll_job_id': next_job.id,
        }
    except Exception as exc:
        db.session.rollback()
        record_failure(
            run.id, exc, failure_class=FailureClass.SOURCE,
            stage=RunStage.ACQUIRE, source_domain=SourceDomain.SCHEDULE,
            entity_type='baseball_date', entity_ref=baseball_date,
            retryable=True, commit=False,
        )
        finalize_run(
            run.id, RunStatus.FAILED, failed_stage=RunStage.ACQUIRE, commit=False,
        )
        db.session.commit()
        raise


def run_next_game_state_poll(
    worker_id, *, now=None, observer=observe_schedule, lease_seconds=300,
):
    """Claim, execute, and fence exactly one SP-04 job through SP-02."""
    return run_next_job(
        worker_id,
        {
            JobType.FETCH_SCHEDULE.value: lambda job: execute_game_state_poll(
                job, now=now, observer=observer,
            )
        },
        job_types=[JobType.FETCH_SCHEDULE],
        lease_seconds=lease_seconds,
    )


def _start_or_attach_run(job, baseball_date):
    if job.sync_run_id is None:
        run = create_run(
            run_type=RunType.SCHEDULE_GAME_STATE,
            trigger_type=TriggerType.SCHEDULED,
            source='adaptive_game_state',
            job_name=JobType.FETCH_SCHEDULE.value,
            baseball_date=baseball_date,
            source_domain=SourceDomain.SCHEDULE,
            scopes=(), commit=False,
        )
        job.sync_run_id = run.id
        db.session.commit()
    else:
        run = start_run(job.sync_run_id)
    return start_run(run)


def _enqueue_final_reconciliation(snapshot, observation_id, transition, run_id, parent_job_id):
    return enqueue_job(
        job_type=JobType.RECONCILE_FINAL_GAME,
        scope_type=JobScopeType.GAME,
        scope_key=str(snapshot.game_pk),
        product_date=snapshot.baseball_date,
        dedupe_key=f'RECONCILE_FINAL_GAME:{snapshot.game_pk}:observation:{observation_id}',
        priority=PRIORITY_ACTIVE,
        sync_run_id=run_id,
        parent_job_id=parent_job_id,
        payload_schema_version=1,
        payload={
            'game_pk': snapshot.game_pk,
            'baseball_date': snapshot.baseball_date,
            'source_observation_id': observation_id,
            'transition': transition,
        },
        commit=False,
    )


def _enqueue_poll(baseball_date, available_at, *, priority, reason, game_pks=(), parent_job_id=None, commit=True):
    available_at = _naive_utc(available_at)
    generation = available_at.replace(second=0, microsecond=0).isoformat()
    return enqueue_job(
        job_type=JobType.FETCH_SCHEDULE,
        scope_type=JobScopeType.BASEBALL_DATE,
        scope_key=baseball_date.isoformat(),
        product_date=baseball_date,
        dedupe_key=f'GAME_STATE:{baseball_date.isoformat()}:{generation}:{POLLING_POLICY_VERSION}',
        priority=priority,
        available_at=available_at,
        parent_job_id=parent_job_id,
        payload_schema_version=POLL_PAYLOAD_SCHEMA_VERSION,
        payload={
            'baseball_date': baseball_date,
            'game_pks': list(game_pks),
            'reason': reason,
            'policy_version': POLLING_POLICY_VERSION,
        },
        commit=commit,
    )


def _update_operational_rows(snapshot, decision, transition, observation_id, *, now):
    for row in ScheduledGame.query.filter_by(game_pk=snapshot.game_pk).all():
        row.operational_state = snapshot.state
        row.status_detailed_state = snapshot.raw_detailed_state
        row.status_abstract_state = snapshot.raw_abstract_state
        row.game_state_fingerprint = snapshot.fingerprint
        row.next_poll_at = decision.next_poll_at
        row.polling_policy_version = decision.policy_version
        if transition is not None:
            row.last_transition = transition
            row.last_transition_at = now
            row.last_transition_observation_id = observation_id


def _next_date_poll(snapshots, baseball_date, *, now):
    if not snapshots:
        return empty_schedule_poll_decision(baseball_date, now=now)
    decisions = [polling_decision(item.state, item.scheduled_at, now=now) for item in snapshots]
    return min(decisions, key=lambda item: (item.next_poll_at, item.priority))


def _one_row_per_game(game_pks):
    rows = ScheduledGame.query.filter(ScheduledGame.game_pk.in_(game_pks or [-1])).order_by(
        ScheduledGame.game_pk.asc(), ScheduledGame.id.asc()
    ).all()
    result = {}
    for row in rows:
        result.setdefault(row.game_pk, row)
    return list(result.values())


def _rows_for_date(baseball_date):
    return ScheduledGame.query.filter_by(game_date=baseball_date).all()


def _one_row_per_game_for_date(baseball_date):
    rows = ScheduledGame.query.filter_by(game_date=baseball_date).order_by(
        ScheduledGame.game_pk.asc(), ScheduledGame.id.asc()
    ).all()
    result = {}
    for row in rows:
        result.setdefault(row.game_pk, row)
    return list(result.values())


def _legacy_operational_state(row):
    if row.status_state in {
        ScheduledGame.STATE_FINAL, ScheduledGame.STATE_POSTPONED,
        ScheduledGame.STATE_SUSPENDED,
    }:
        return row.status_state
    if row.status_state == ScheduledGame.STATE_SCHEDULED:
        return GameState.SCHEDULED.value
    return normalize_game_state({
        'statusCode': row.status_code,
        'detailedState': row.status_detailed_state,
        'abstractGameState': row.status_abstract_state,
    })


def _team_id(side):
    return _int(((side or {}).get('team') or {}).get('id'))


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value):
    text = str(value).strip() if value is not None else ''
    return text or None


def _date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _datetime(value):
    parsed = _datetime_value(value)
    return parsed.isoformat() if parsed else None


def _datetime_value(value):
    if isinstance(value, datetime):
        return _naive_utc(value)
    if not value:
        return None
    try:
        text = str(value).strip().replace('Z', '+00:00')
        return _naive_utc(datetime.fromisoformat(text))
    except (TypeError, ValueError):
        return None


def _naive_utc(value):
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _iso(value):
    isoformat = getattr(value, 'isoformat', None)
    if callable(isoformat) and not isinstance(value, str):
        return isoformat()
    return value
