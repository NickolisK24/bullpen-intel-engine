"""SP-06 official probable-starter and pregame-context orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from enum import Enum
import hashlib
import logging

from sqlalchemy import text

from models.pitcher import Pitcher
from models.pregame_context import GamePregameContextVersion, PregameContextMutation
from models.roster_membership import RosterMembershipInterval
from models.scheduled_game import ScheduledGame
from services.adaptive_game_state import GameState
from services.mlb_api import mlb_client
from services.source_observations import (
    ObservationCompleteness,
    PayloadKind,
    SourceProvider,
    SourceSubjectType,
    build_source_identity,
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

PREGAME_POLICY_VERSION = 'pregame-context-poll-v1'
PREGAME_PAYLOAD_SCHEMA_VERSION = 1
PREGAME_CONTEXT_FINGERPRINT_VERSION = 'pregame-context-v1'

PRIORITY_HIGH = 15
PRIORITY_NORMAL = 100
PRIORITY_LOW = 300

_CLOSED_STATES = frozenset({
    GameState.LIVE.value,
    GameState.SUSPENDED.value,
    GameState.FINAL.value,
    GameState.CANCELLED.value,
})


class PregameContextChange(str, Enum):
    PREGAME_CONTEXT_DISCOVERED = 'pregame_context_discovered'
    PROBABLE_STARTER_ADDED = 'probable_starter_added'
    PROBABLE_STARTER_CHANGED = 'probable_starter_changed'
    PROBABLE_STARTER_REMOVED = 'probable_starter_removed'
    PREGAME_CONTEXT_CHANGED = 'pregame_context_changed'


@dataclass(frozen=True)
class PregameContextProjection:
    game_pk: int
    baseball_date: date
    scheduled_at: datetime | None
    home_team_id: int
    away_team_id: int
    home_probable_pitcher_mlb_id: int | None
    away_probable_pitcher_mlb_id: int | None
    home_probable_pitcher_name: str | None
    away_probable_pitcher_name: str | None
    venue_id: int | None
    venue_name: str | None
    game_type: str | None
    game_number: int | None
    doubleheader: str | None
    resumed_from_game_pk: int | None
    fingerprint: str


@dataclass(frozen=True)
class PregamePollDecision:
    next_poll_at: datetime | None
    interval_seconds: int | None
    priority: int | None
    policy_version: str = PREGAME_POLICY_VERSION


@dataclass(frozen=True)
class PregamePersistenceResult:
    version: GamePregameContextVersion
    mutations: tuple[PregameContextMutation, ...]
    created: bool
    roster_discrepancies: tuple[dict, ...]


def pregame_source_identity(game_pk, baseball_date):
    game_pk = _positive_int(game_pk)
    baseball_date = _date(baseball_date)
    return build_source_identity(
        provider=SourceProvider.MLB_STATS_API,
        source_domain=SourceDomain.PREGAME,
        endpoint='/schedule',
        subject_type=SourceSubjectType.GAME,
        subject_key=f'game:{game_pk}',
        request_parameters={
            'sportId': 1,
            'gamePk': game_pk,
            'hydrate': 'team,probablePitcher,venue',
        },
        baseball_date=baseball_date,
    )


def observe_pregame_context(
    game_pk,
    baseball_date,
    *,
    commit=True,
    sync_run_id=None,
    sync_job_id=None,
):
    """Fetch one official MLB game and record SP-03 source evidence."""
    identity = pregame_source_identity(game_pk, baseball_date)
    started_at = utc_now_naive()
    try:
        games = list(mlb_client.get_schedule(
            game_pk=game_pk,
            hydrate='team,probablePitcher,venue',
        ) or [])
    except Exception as exc:
        try:
            record_source_fetch_failure(
                identity=identity,
                error=exc,
                attempt_started_at=started_at,
                http_status=getattr(exc, 'status_code', None),
                sync_run_id=sync_run_id,
                sync_job_id=sync_job_id,
                commit=commit,
            )
        except Exception:
            logger.exception('Could not persist failed pregame fetch evidence')
        raise

    completeness = _pregame_response_completeness(games, game_pk)
    source_result = record_source_observation(
        identity=identity,
        payload=games,
        fingerprint_payload=canonical_record_collection(games),
        completeness=completeness,
        payload_schema_version=1,
        payload_kind=PayloadKind.NORMALIZED_JSON,
        record_count=len(games),
        empty_valid=False,
        attempt_started_at=started_at,
        sync_run_id=sync_run_id,
        sync_job_id=sync_job_id,
        commit=commit,
    )
    game = next(
        (item for item in games if _int((item or {}).get('gamePk')) == int(game_pk)),
        None,
    )
    return game, source_result


def project_pregame_context(game) -> PregameContextProjection | None:
    """Normalize the bounded official fields that have pregame meaning."""
    if not isinstance(game, dict):
        return None
    game_pk = _int(game.get('gamePk'))
    baseball_date = _date(game.get('officialDate'))
    teams = game.get('teams') if isinstance(game.get('teams'), dict) else {}
    home = teams.get('home') if isinstance(teams.get('home'), dict) else {}
    away = teams.get('away') if isinstance(teams.get('away'), dict) else {}
    home_team_id = _team_id(home)
    away_team_id = _team_id(away)
    if None in (game_pk, baseball_date, home_team_id, away_team_id):
        return None

    home_probable = _probable_pitcher(home)
    away_probable = _probable_pitcher(away)
    venue = game.get('venue') if isinstance(game.get('venue'), dict) else {}
    meaningful = {
        'version': PREGAME_CONTEXT_FINGERPRINT_VERSION,
        'game_pk': game_pk,
        'baseball_date': baseball_date,
        'scheduled_at': _datetime(game.get('gameDate')),
        'home_team_id': home_team_id,
        'away_team_id': away_team_id,
        'home_probable_pitcher_mlb_id': home_probable[0],
        'away_probable_pitcher_mlb_id': away_probable[0],
        'home_probable_pitcher_name': home_probable[1],
        'away_probable_pitcher_name': away_probable[1],
        'venue_id': _int(venue.get('id')),
        'venue_name': _text(venue.get('name')),
        'game_type': _text(game.get('gameType')),
        'game_number': _int(game.get('gameNumber')),
        'doubleheader': _text(game.get('doubleHeader')),
        'resumed_from_game_pk': _int(
            game.get('resumedFrom') or game.get('resumedFromGamePk')
        ),
    }
    fingerprint = hashlib.sha256(
        stable_json_dumps(meaningful).encode('utf-8')
    ).hexdigest()
    return PregameContextProjection(
        game_pk=game_pk,
        baseball_date=baseball_date,
        scheduled_at=_datetime_value(meaningful['scheduled_at']),
        home_team_id=home_team_id,
        away_team_id=away_team_id,
        home_probable_pitcher_mlb_id=home_probable[0],
        away_probable_pitcher_mlb_id=away_probable[0],
        home_probable_pitcher_name=home_probable[1],
        away_probable_pitcher_name=away_probable[1],
        venue_id=meaningful['venue_id'],
        venue_name=meaningful['venue_name'],
        game_type=meaningful['game_type'],
        game_number=meaningful['game_number'],
        doubleheader=meaningful['doubleheader'],
        resumed_from_game_pk=meaningful['resumed_from_game_pk'],
        fingerprint=fingerprint,
    )


def pregame_polling_decision(state, scheduled_at, *, now=None):
    """Return the deterministic v1 pregame refresh decision."""
    now = _naive_utc(now or utc_now_naive())
    scheduled_at = _naive_utc(scheduled_at) if scheduled_at else None
    if state in _CLOSED_STATES:
        return PregamePollDecision(None, None, None)
    if state == GameState.POSTPONED.value:
        seconds, priority = 21600, PRIORITY_LOW
    elif state == GameState.PREGAME.value:
        seconds, priority = 90, PRIORITY_HIGH
    elif state == GameState.DELAYED.value:
        seconds, priority = 180, PRIORITY_HIGH
    elif state == GameState.SCHEDULED.value and scheduled_at is not None:
        until = (scheduled_at - now).total_seconds()
        if until > 21600:
            seconds, priority = 21600, PRIORITY_LOW
        elif until > 7200:
            seconds, priority = 1800, PRIORITY_NORMAL
        elif until > 1800:
            seconds, priority = 600, PRIORITY_NORMAL
        else:
            seconds, priority = 120, PRIORITY_HIGH
    else:
        seconds, priority = 1800, PRIORITY_NORMAL
    return PregamePollDecision(now + timedelta(seconds=seconds), seconds, priority)


def classify_pregame_changes(previous, current):
    """Return stable structured changes for one authoritative context revision."""
    if previous is None:
        return ((PregameContextChange.PREGAME_CONTEXT_DISCOVERED.value, 'game', None, None),)
    changes = []
    for side in ('home', 'away'):
        old_id = getattr(previous, f'{side}_probable_pitcher_mlb_id')
        new_id = getattr(current, f'{side}_probable_pitcher_mlb_id')
        if old_id == new_id:
            continue
        if old_id is None:
            event = PregameContextChange.PROBABLE_STARTER_ADDED.value
        elif new_id is None:
            event = PregameContextChange.PROBABLE_STARTER_REMOVED.value
        else:
            event = PregameContextChange.PROBABLE_STARTER_CHANGED.value
        changes.append((event, side, old_id, new_id))
    if not changes and previous.context_fingerprint != current.fingerprint:
        changes.append((
            PregameContextChange.PREGAME_CONTEXT_CHANGED.value,
            'game', None, None,
        ))
    return tuple(changes)


def persist_pregame_context(
    projection,
    *,
    source_observation,
    sync_run_id=None,
    observed_at=None,
    commit=True,
):
    """Persist one complete context revision and update both team projections."""
    if projection is None:
        raise ValueError('projection is required')
    if source_observation is None or source_observation.completeness != 'complete':
        raise ValueError('complete source observation is required')
    observed_at = _naive_utc(observed_at or source_observation.observed_at)
    _lock_game(projection.game_pk)
    schedule_rows = (
        ScheduledGame.query.filter_by(game_pk=projection.game_pk)
        .order_by(ScheduledGame.id.asc()).with_for_update().all()
    )
    if not schedule_rows:
        raise ValueError(f'scheduled game {projection.game_pk} does not exist')

    latest = (
        GamePregameContextVersion.query
        .filter_by(game_pk=projection.game_pk)
        .order_by(GamePregameContextVersion.version_number.desc())
        .with_for_update().first()
    )
    if (
        latest is not None
        and latest.source_observation.source_subject_id
        == source_observation.source_subject_id
        and latest.source_observation.version_number > source_observation.version_number
    ):
        # A slower worker may finish an older fetch after a newer source
        # revision has already become current. Preserve the newer authority.
        return PregamePersistenceResult(latest, (), False, ())
    if latest is not None and latest.context_fingerprint == projection.fingerprint:
        _apply_current_projection(schedule_rows, latest, observed_at)
        if commit:
            db.session.commit()
        else:
            db.session.flush()
        return PregamePersistenceResult(latest, (), False, _roster_discrepancies(projection))

    pitcher_ids = _canonical_pitcher_ids(projection)
    version = GamePregameContextVersion(
        game_pk=projection.game_pk,
        version_number=(latest.version_number + 1) if latest else 1,
        predecessor_version_id=latest.id if latest else None,
        baseball_date=projection.baseball_date,
        scheduled_at=projection.scheduled_at,
        home_team_id=projection.home_team_id,
        away_team_id=projection.away_team_id,
        home_probable_pitcher_mlb_id=projection.home_probable_pitcher_mlb_id,
        away_probable_pitcher_mlb_id=projection.away_probable_pitcher_mlb_id,
        home_probable_pitcher_id=pitcher_ids.get(projection.home_probable_pitcher_mlb_id),
        away_probable_pitcher_id=pitcher_ids.get(projection.away_probable_pitcher_mlb_id),
        home_probable_pitcher_name=projection.home_probable_pitcher_name,
        away_probable_pitcher_name=projection.away_probable_pitcher_name,
        venue_id=projection.venue_id,
        venue_name=projection.venue_name,
        game_type=projection.game_type,
        game_number=projection.game_number,
        doubleheader=projection.doubleheader,
        resumed_from_game_pk=projection.resumed_from_game_pk,
        context_fingerprint=projection.fingerprint,
        fingerprint_version=PREGAME_CONTEXT_FINGERPRINT_VERSION,
        source_observation_id=source_observation.id,
        completeness='complete',
        observed_at=observed_at,
    )
    db.session.add(version)
    db.session.flush()
    mutation_rows = []
    for event, side, old_id, new_id in classify_pregame_changes(latest, projection):
        team_id = (
            projection.home_team_id if side == 'home'
            else projection.away_team_id if side == 'away'
            else None
        )
        mutation = PregameContextMutation(
            context_version_id=version.id,
            game_pk=projection.game_pk,
            baseball_date=projection.baseball_date,
            team_id=team_id,
            side=side,
            mutation_type=event,
            old_probable_pitcher_mlb_id=old_id,
            new_probable_pitcher_mlb_id=new_id,
            source_observation_id=source_observation.id,
            sync_run_id=sync_run_id,
        )
        db.session.add(mutation)
        mutation_rows.append(mutation)
    _apply_current_projection(schedule_rows, version, observed_at)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return PregamePersistenceResult(
        version, tuple(mutation_rows), True, _roster_discrepancies(projection),
    )


def current_pregame_context(game_pk):
    row = ScheduledGame.query.filter_by(game_pk=int(game_pk)).order_by(ScheduledGame.id).first()
    if row is None or row.pregame_context_version_id is None:
        return None
    return db.session.get(GamePregameContextVersion, row.pregame_context_version_id)


def pregame_context_at(game_pk, observed_at):
    observed_at = _naive_utc(observed_at)
    return (
        GamePregameContextVersion.query
        .filter(
            GamePregameContextVersion.game_pk == int(game_pk),
            GamePregameContextVersion.observed_at <= observed_at,
        )
        .order_by(
            GamePregameContextVersion.observed_at.desc(),
            GamePregameContextVersion.version_number.desc(),
        ).first()
    )


def plan_pregame_context_polls(
    *, now=None, baseball_dates=None, lookback_days=0, lookahead_days=2,
    commit=True,
):
    """Enqueue one due SP-06 job per gamePk, never per team/date identity."""
    now = _naive_utc(now or utc_now_naive())
    query = ScheduledGame.query.filter(
        (ScheduledGame.next_pregame_poll_at.is_(None))
        | (ScheduledGame.next_pregame_poll_at <= now)
    )
    if baseball_dates:
        query = query.filter(ScheduledGame.game_date.in_(tuple(baseball_dates)))
    else:
        query = query.filter(
            ScheduledGame.game_date >= now.date() - timedelta(days=lookback_days),
            ScheduledGame.game_date <= now.date() + timedelta(days=lookahead_days),
        )
    rows = query.order_by(ScheduledGame.game_date, ScheduledGame.game_pk, ScheduledGame.id).all()
    games = {}
    for row in rows:
        games.setdefault(row.game_pk, row)
    jobs = []
    for row in games.values():
        decision = pregame_polling_decision(
            _operational_state(row),
            row.game_datetime,
            now=now,
        )
        if decision.next_poll_at is None:
            continue
        jobs.append(_enqueue_pregame_poll(
            row,
            decision.next_poll_at,
            decision.priority,
            reason='due_pregame_context',
            commit=False,
        ))
        for schedule_row in ScheduledGame.query.filter_by(game_pk=row.game_pk).all():
            schedule_row.next_pregame_poll_at = decision.next_poll_at
            schedule_row.pregame_policy_version = decision.policy_version
    if commit:
        db.session.commit()
    return jobs


def execute_pregame_context_job(job, *, now=None, observer=observe_pregame_context):
    """Execute one claimed SP-06 job; SP-02 owns final settlement."""
    now = _naive_utc(now or utc_now_naive())
    payload = dict(job.details_json or {})
    game_pk = _positive_int(payload.get('game_pk') or job.scope_key)
    row = ScheduledGame.query.filter_by(game_pk=game_pk).order_by(ScheduledGame.id).first()
    if row is None:
        raise ValueError(f'scheduled game {game_pk} does not exist')
    run = _start_or_attach_run(job, row)
    state = _operational_state(row)
    if state in _CLOSED_STATES:
        for schedule_row in ScheduledGame.query.filter_by(game_pk=game_pk).all():
            schedule_row.next_pregame_poll_at = None
            schedule_row.pregame_policy_version = PREGAME_POLICY_VERSION
        record_outcome(
            run, source_reads=0, source_changes=0, canonical_mutations=0,
            affected_games=0, downstream_work_created=0,
            outcome={'reason': 'pregame_context_closed', 'game_state': state},
            commit=False,
        )
        finalize_run(run, RunStatus.SUCCEEDED, commit=False)
        db.session.commit()
        return {'sync_run_id': run.id, 'status': 'closed', 'game_pk': game_pk}

    try:
        failure_stage = RunStage.ACQUIRE
        mark_stage(run, failure_stage)
        game, source_result = observer(
            game_pk,
            row.game_date,
            sync_run_id=run.id,
            sync_job_id=job.id,
        )
        heartbeat_job(job.id, worker_id=job.worker_id, claim_token=job.claim_token)
        observation = source_result.observation
        authoritative = bool(observation and observation.completeness == 'complete')
        persistence = None
        if authoritative:
            projection = project_pregame_context(game)
            if projection is None:
                raise ValueError('complete pregame response did not normalize')
            failure_stage = RunStage.CANONICALIZE
            mark_stage(run, failure_stage)
            persistence = persist_pregame_context(
                projection,
                source_observation=observation,
                sync_run_id=run.id,
                commit=False,
            )

        current_row = ScheduledGame.query.filter_by(game_pk=game_pk).order_by(ScheduledGame.id).first()
        decision = pregame_polling_decision(
            _operational_state(current_row),
            current_row.game_datetime,
            now=now,
        )
        next_job = None
        for schedule_row in ScheduledGame.query.filter_by(game_pk=game_pk).all():
            schedule_row.next_pregame_poll_at = decision.next_poll_at
            schedule_row.pregame_policy_version = decision.policy_version
        if decision.next_poll_at is not None:
            next_job = _enqueue_pregame_poll(
                current_row,
                decision.next_poll_at,
                decision.priority,
                reason='adaptive_pregame_follow_up',
                parent_job_id=job.id,
                commit=False,
            )

        created = bool(persistence and persistence.created)
        mutations = tuple(persistence.mutations) if persistence else ()
        discrepancies = tuple(persistence.roster_discrepancies) if persistence else ()
        impact_job = None
        if mutations:
            impact_job = enqueue_job(
                job_type=JobType.PROCESS_CANONICAL_IMPACT,
                scope_type=JobScopeType.GAME,
                scope_key=str(game_pk),
                product_date=persistence.version.baseball_date,
                dedupe_key=(
                    f'CANONICAL_IMPACT:pregame:{game_pk}:'
                    f'context:{persistence.version.id}'
                ),
                priority=PRIORITY_NORMAL,
                sync_run_id=run.id,
                parent_job_id=job.id,
                payload_schema_version=1,
                payload={
                    'mutation_family': 'pregame_context',
                    'authority_class': 'pregame_authoritative',
                    'game_pk': game_pk,
                    'baseball_date': persistence.version.baseball_date,
                    'pregame_context_version_id': persistence.version.id,
                    'pregame_context_mutation_ids': [item.id for item in mutations],
                    'source_observation_id': observation.id if observation else None,
                },
                commit=False,
            )
        add_scopes(run, [
            (ScopeType.GAME, game_pk),
            (ScopeType.TEAM, row.team_id),
            (ScopeType.TEAM, row.opponent_team_id),
        ], commit=False)
        record_outcome(
            run,
            source_reads=1,
            source_changes=int(bool(source_result.changed)),
            canonical_mutations=int(created),
            affected_games=int(created),
            affected_teams=len({item.team_id for item in mutations if item.team_id}),
            downstream_work_created=int(impact_job is not None),
            warnings_count=int(not authoritative) + len(discrepancies),
            outcome={
                'game_pk': game_pk,
                'source_observation_id': observation.id if observation else None,
                'source_observation_outcome': source_result.outcome,
                'completeness': observation.completeness if observation else None,
                'context_version_id': persistence.version.id if persistence else None,
                'context_created': created,
                'mutations': [item.mutation_type for item in mutations],
                'roster_discrepancies': list(discrepancies),
                'next_pregame_poll_at': decision.next_poll_at,
                'pregame_policy_version': PREGAME_POLICY_VERSION,
                'next_job_id': next_job.id if next_job else None,
                'impact_job_id': impact_job.id if impact_job else None,
            },
            commit=False,
        )
        finalize_run(run, RunStatus.SUCCEEDED, commit=False)
        heartbeat_job(
            job.id, worker_id=job.worker_id, claim_token=job.claim_token,
            commit=False,
        )
        db.session.commit()
        return {
            'sync_run_id': run.id,
            'game_pk': game_pk,
            'source_observation_id': observation.id if observation else None,
            'context_version_id': persistence.version.id if persistence else None,
            'context_created': created,
            'mutation_ids': [item.id for item in mutations],
            'next_job_id': next_job.id if next_job else None,
            'impact_job_id': impact_job.id if impact_job else None,
        }
    except Exception as exc:
        db.session.rollback()
        record_failure(
            run.id,
            exc,
            failure_class=FailureClass.SOURCE,
            stage=failure_stage,
            source_domain=SourceDomain.PREGAME,
            entity_type='game',
            entity_ref=game_pk,
            retryable=True,
            commit=False,
        )
        finalize_run(
            run.id, RunStatus.FAILED, failed_stage=failure_stage, commit=False,
        )
        db.session.commit()
        raise


def run_next_pregame_context_job(
    worker_id, *, now=None, observer=observe_pregame_context, lease_seconds=300,
):
    return run_next_job(
        worker_id,
        {
            JobType.FETCH_PREGAME_CONTEXT.value: lambda job: execute_pregame_context_job(
                job, now=now, observer=observer,
            ),
        },
        job_types=[JobType.FETCH_PREGAME_CONTEXT],
        lease_seconds=lease_seconds,
    )


def _start_or_attach_run(job, row):
    if job.sync_run_id is None:
        run = create_run(
            run_type=RunType.PREGAME_CONTEXT,
            trigger_type=TriggerType.SCHEDULED,
            source='pregame_context',
            job_name=JobType.FETCH_PREGAME_CONTEXT.value,
            baseball_date=row.game_date,
            source_domain=SourceDomain.PREGAME,
            scopes=[
                (ScopeType.GAME, row.game_pk),
                (ScopeType.TEAM, row.team_id),
                (ScopeType.TEAM, row.opponent_team_id),
            ],
            commit=False,
        )
        job.sync_run_id = run.id
        db.session.commit()
    else:
        run = start_run(job.sync_run_id)
    return start_run(run)


def _enqueue_pregame_poll(
    row, available_at, priority, *, reason, parent_job_id=None, commit=True,
):
    available_at = _naive_utc(available_at)
    generation = available_at.replace(second=0, microsecond=0).isoformat()
    return enqueue_job(
        job_type=JobType.FETCH_PREGAME_CONTEXT,
        scope_type=JobScopeType.GAME,
        scope_key=str(row.game_pk),
        product_date=row.game_date,
        dedupe_key=(
            f'PREGAME_CONTEXT:{row.game_pk}:{generation}:{PREGAME_POLICY_VERSION}'
        ),
        priority=priority,
        available_at=available_at,
        parent_job_id=parent_job_id,
        payload_schema_version=PREGAME_PAYLOAD_SCHEMA_VERSION,
        payload={
            'game_pk': row.game_pk,
            'baseball_date': row.game_date,
            'reason': reason,
            'policy_version': PREGAME_POLICY_VERSION,
            'game_state_observation_id': row.last_transition_observation_id,
        },
        commit=commit,
    )


def _pregame_response_completeness(games, game_pk):
    matching = [item for item in games if _int((item or {}).get('gamePk')) == int(game_pk)]
    if len(matching) != 1:
        return ObservationCompleteness.UNKNOWN
    game = matching[0]
    teams = game.get('teams') if isinstance(game, dict) else None
    if not isinstance(teams, dict):
        return ObservationCompleteness.PARTIAL
    for side in ('home', 'away'):
        entry = teams.get(side)
        if not isinstance(entry, dict) or _team_id(entry) is None:
            return ObservationCompleteness.PARTIAL
        probable = entry.get('probablePitcher')
        if probable is not None and (
            not isinstance(probable, dict) or _int(probable.get('id')) is None
        ):
            return ObservationCompleteness.PARTIAL
    return ObservationCompleteness.COMPLETE


def _operational_state(row):
    if row.operational_state:
        return row.operational_state
    return {
        ScheduledGame.STATE_SCHEDULED: GameState.SCHEDULED.value,
        ScheduledGame.STATE_FINAL: GameState.FINAL.value,
        ScheduledGame.STATE_POSTPONED: GameState.POSTPONED.value,
        ScheduledGame.STATE_SUSPENDED: GameState.SUSPENDED.value,
    }.get(row.status_state, GameState.UNKNOWN.value)


def _apply_current_projection(rows, version, updated_at):
    for row in rows:
        row.home_probable_pitcher_mlb_id = version.home_probable_pitcher_mlb_id
        row.away_probable_pitcher_mlb_id = version.away_probable_pitcher_mlb_id
        row.home_probable_pitcher_name = version.home_probable_pitcher_name
        row.away_probable_pitcher_name = version.away_probable_pitcher_name
        row.pregame_context_observation_id = version.source_observation_id
        row.pregame_context_version_id = version.id
        row.pregame_context_fingerprint = version.context_fingerprint
        row.pregame_context_version = version.version_number
        row.pregame_context_completeness = version.completeness
        row.pregame_context_updated_at = updated_at


def _canonical_pitcher_ids(projection):
    mlb_ids = {
        value for value in (
            projection.home_probable_pitcher_mlb_id,
            projection.away_probable_pitcher_mlb_id,
        ) if value is not None
    }
    return {
        row.mlb_id: row.id
        for row in Pitcher.query.filter(Pitcher.mlb_id.in_(mlb_ids or {-1})).all()
    }


def _roster_discrepancies(projection):
    discrepancies = []
    for side, team_id, pitcher_mlb_id in (
        ('home', projection.home_team_id, projection.home_probable_pitcher_mlb_id),
        ('away', projection.away_team_id, projection.away_probable_pitcher_mlb_id),
    ):
        if pitcher_mlb_id is None:
            continue
        memberships = RosterMembershipInterval.query.filter_by(
            team_id=team_id,
            membership_type='active_roster',
            effective_end_date=None,
            is_current_version=True,
            is_void=False,
        ).all()
        # An empty projection is not proof of absence. Only report a mismatch
        # when SP-05 has a current active-roster population for the club.
        if memberships and pitcher_mlb_id not in {item.player_mlb_id for item in memberships}:
            discrepancies.append({
                'side': side,
                'team_id': team_id,
                'probable_pitcher_mlb_id': pitcher_mlb_id,
                'action': 'roster_confirmation_deferred',
            })
    return tuple(discrepancies)


def _lock_game(game_pk):
    if db.session.get_bind().dialect.name == 'postgresql':
        db.session.execute(
            text('SELECT pg_advisory_xact_lock(:key)'),
            {'key': 506000000000 + int(game_pk)},
        )


def _team_id(side):
    return _int(((side or {}).get('team') or {}).get('id'))


def _probable_pitcher(side):
    value = (side or {}).get('probablePitcher')
    if not isinstance(value, dict):
        return None, None
    return _int(value.get('id')), _text(value.get('fullName'))


def _positive_int(value):
    parsed = _int(value)
    if parsed is None or parsed <= 0:
        raise ValueError('positive integer required')
    return parsed


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _text(value):
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    return _naive_utc(parsed)


def _datetime_value(value):
    if isinstance(value, datetime):
        return _naive_utc(value)
    return _datetime(value)


def _naive_utc(value):
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value
