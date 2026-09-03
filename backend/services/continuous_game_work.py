"""Durable CU-02 through CU-07 work obligations for accepted final games.

Observation acceptance and canonical execution are deliberately separate
states.  CU-02 records source evidence; this module records the durable
obligation to reconcile an accepted final-game change through the bounded
continuous pipeline. One accepted observation fingerprint has one SyncJob.
An authoritative successor supersedes only predecessor work that has not
committed canonical evidence. A predecessor that still owes downstream or
publication effects remains active until those effects are durable, while
completed jobs remain immutable audit evidence.

SyncJob's repository-native vocabulary maps to the lifecycle here as follows:

* ``pending`` -> planned and eligible for bounded execution;
* ``running`` -> in progress (and reclaimable after a process restart);
* ``failed`` -> retryable until ``max_attempts`` is exhausted, then terminal;
* ``succeeded`` -> the mode's required pipeline boundary completed; and
* ``skipped`` -> explicitly superseded by a newer accepted observation.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import String, and_, cast, exists, literal, or_
from sqlalchemy.orm import aliased

from models.game_observation_state import GameObservationState
from models.game_ingestion_work_item import GameIngestionWorkItem
from models.sync_job import SyncJob
from services import game_finality, sync_jobs
from utils.db import db
from utils.time import utc_now_naive


JOB_NAME = 'continuous_final_game_reconciliation'
JOB_FAMILY = 'continuous_final_game'
MAX_ATTEMPTS = 5
LOCAL_STALE_AFTER_MINUTES = 3

STAGE_CANONICAL_PENDING = 'canonical_pending'
STAGE_DOWNSTREAM_PENDING = 'downstream_pending'
STAGE_PUBLICATION_PENDING = 'publication_pending'
STAGE_PUBLICATION_CACHE_PENDING = 'publication_cache_pending'
STAGE_COMPLETE = 'complete'
STAGE_ORDER = {
    STAGE_CANONICAL_PENDING: 0,
    STAGE_DOWNSTREAM_PENDING: 1,
    STAGE_PUBLICATION_PENDING: 2,
    STAGE_PUBLICATION_CACHE_PENDING: 3,
    STAGE_COMPLETE: 4,
}

WORK_PLANNED = 'planned'
WORK_IN_PROGRESS = 'in_progress'
WORK_RETRYABLE_FAILURE = 'retryable_failure'
WORK_TERMINAL_FAILURE = 'terminal_failure'
WORK_COMPLETED = 'completed'
WORK_SUPERSEDED = 'superseded'

WORK_KIND_ACCEPTED_OBSERVATION = 'accepted_observation'
WORK_KIND_CORRECTION_RECHECK = 'scheduled_correction_recheck'
CORRECTION_RECHECK_REASON = 'bounded_canonical_correction_recheck'

ACTIONABLE_CLASSIFICATIONS = frozenset({'finalized', 'corrected'})
ACTIONABLE_FINALITY_STATES = frozenset({
    game_finality.FINAL_PENDING_DATA,
    game_finality.FINAL_AND_USABLE,
})


def ensure_obligation(change, *, row=None, sync_run_id=None, commit=True):
    """Create one durable obligation for an accepted actionable observation.

    The caller may include this write in the same transaction that advances
    ``GameObservationState``.  Identical calls return the existing job.  A new
    accepted fingerprint supersedes only redundant pre-canonical work for the
    same game before creating its successor. Work that already committed a
    canonical mutation remains independently discoverable until propagation.
    """
    if not _is_actionable(change):
        return None

    game_pk = _positive_int(_get(change, 'game_pk'))
    fingerprint = str(_get(change, 'current_observation_identity') or '').strip()
    if game_pk is None or not fingerprint:
        return None

    row = row or GameObservationState.query.filter_by(mlb_game_pk=game_pk).one_or_none()
    if row is None or row.observation_fingerprint != fingerprint:
        return None

    scope_key = _scope_key(game_pk, fingerprint, row.source_observed_at)
    existing = SyncJob.query.filter_by(
        job_name=JOB_NAME,
        scope_key=scope_key,
    ).one_or_none()
    if existing is not None:
        return existing

    now = utc_now_naive()
    _supersede_unfinished(game_pk, fingerprint, now=now)
    job = SyncJob(
        job_name=JOB_NAME,
        job_family=JOB_FAMILY,
        lane=sync_jobs.LANE_INTERNAL,
        scope_key=scope_key,
        product_date=_product_date(row, now),
        status=sync_jobs.STATUS_PENDING,
        attempts=0,
        max_attempts=MAX_ATTEMPTS,
        sync_run_id=sync_run_id,
        details_json={
            'schema_version': 1,
            'work_kind': WORK_KIND_ACCEPTED_OBSERVATION,
            'work_status': WORK_PLANNED,
            'stage': STAGE_CANONICAL_PENDING,
            'game_pk': game_pk,
            'observation_fingerprint': fingerprint,
            'source_observed_at': (
                row.source_observed_at.isoformat()
                if row.source_observed_at else None
            ),
            'change': _change_payload(change),
        },
        created_at=now,
        updated_at=now,
    )
    db.session.add(job)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return job


def ensure_obligations(changes, *, sync_run_id=None, commit=True):
    jobs = []
    for change in changes or ():
        job = ensure_obligation(
            change,
            sync_run_id=sync_run_id,
            commit=False,
        )
        if job is not None:
            jobs.append(job)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return jobs


def ensure_due_correction_rechecks(
    *, reference_date, correction_days, limit, sync_run_id=None,
):
    """Plan one bounded daily canonical recheck for recently completed games.

    MLB provides no ordering token for a same-timestamp usable-to-usable
    boxscore variant. CU-02 therefore preserves its accepted observation.
    This durable, once-per-day correction-horizon obligation independently
    re-fetches the official boxscore through CU-01's governed correction path.
    """
    bounded = max(0, int(limit or 0))
    if bounded == 0:
        return []
    horizon_start = reference_date - timedelta(
        days=max(0, int(correction_days or 0))
    )
    due_before = datetime.combine(reference_date, time.min)
    daily_suffix = f':correction_recheck:{reference_date.isoformat()}'
    expected_scope = (
        literal('game:')
        + cast(GameIngestionWorkItem.mlb_game_pk, String)
        + literal(daily_suffix)
    )
    already_planned_today = exists().where(and_(
        SyncJob.job_name == JOB_NAME,
        SyncJob.scope_key == expected_scope,
    ))
    active_for_game = aliased(SyncJob)
    unresolved_for_game = exists().where(and_(
        active_for_game.job_name == JOB_NAME,
        active_for_game.details_json['game_pk'].as_integer()
        == GameIngestionWorkItem.mlb_game_pk,
        active_for_game.status.in_((
            sync_jobs.STATUS_PENDING,
            sync_jobs.STATUS_RUNNING,
            sync_jobs.STATUS_FAILED,
        )),
    ))
    items = (
        GameIngestionWorkItem.query
        .filter(
            GameIngestionWorkItem.status
            == GameIngestionWorkItem.STATUS_COMPLETED,
            GameIngestionWorkItem.represented_date >= horizon_start,
            GameIngestionWorkItem.represented_date <= reference_date,
            or_(
                GameIngestionWorkItem.last_attempted_at.is_(None),
                GameIngestionWorkItem.last_attempted_at < due_before,
            ),
            ~already_planned_today,
            ~unresolved_for_game,
        )
        .order_by(
            GameIngestionWorkItem.last_attempted_at.asc(),
            GameIngestionWorkItem.represented_date.asc(),
            GameIngestionWorkItem.mlb_game_pk.asc(),
        )
        .limit(bounded)
        .all()
    )
    now = utc_now_naive()
    jobs = []
    for item in items:
        observation = GameObservationState.query.filter_by(
            mlb_game_pk=item.mlb_game_pk,
        ).one_or_none()
        if not _correction_recheck_observation_is_safe(observation):
            continue
        fingerprint = observation.observation_fingerprint
        source_observed_at = (
            observation.source_observed_at.isoformat()
            if observation.source_observed_at else None
        )
        change = {
            'game_pk': item.mlb_game_pk,
            'classification': 'corrected',
            'changed': True,
            'accepted': True,
            'previous_observation_identity': fingerprint,
            'current_observation_identity': fingerprint,
            'finality_state': observation.finality_state,
            'source_authority': observation.source_authority,
            'source_observed_at': source_observed_at,
            'detected_at': now.isoformat(),
            'differences': {},
            'reason': CORRECTION_RECHECK_REASON,
        }
        job = SyncJob(
            job_name=JOB_NAME,
            job_family=JOB_FAMILY,
            lane=sync_jobs.LANE_INTERNAL,
            scope_key=f'game:{item.mlb_game_pk}{daily_suffix}',
            product_date=item.represented_date,
            status=sync_jobs.STATUS_PENDING,
            attempts=0,
            max_attempts=MAX_ATTEMPTS,
            sync_run_id=sync_run_id,
            details_json={
                'schema_version': 1,
                'work_kind': WORK_KIND_CORRECTION_RECHECK,
                'work_status': WORK_PLANNED,
                'stage': STAGE_CANONICAL_PENDING,
                'game_pk': item.mlb_game_pk,
                'observation_fingerprint': fingerprint,
                'change': change,
                'correction_recheck_date': reference_date.isoformat(),
            },
            created_at=now,
            updated_at=now,
        )
        db.session.add(job)
        jobs.append(job)
    db.session.commit()
    return jobs


def claimable_obligations(*, limit):
    """Return a bounded, starvation-resistant work list.

    Oldest durable work sorts first across pending and retryable states, with
    never-attempted work winning ties. Selection is independent of the current
    MLB candidate scan, so neither new observations nor the slate's first-N
    feed cap can starve an older unresolved game forever.
    """
    bounded = max(0, int(limit or 0))
    if bounded == 0:
        return []
    eligible = or_(
        SyncJob.status == sync_jobs.STATUS_PENDING,
        SyncJob.status == sync_jobs.STATUS_RUNNING,
        and_(
            SyncJob.status == sync_jobs.STATUS_FAILED,
            SyncJob.attempts < SyncJob.max_attempts,
        ),
    )
    predecessor = aliased(SyncJob)
    unfinished_predecessor = exists().where(and_(
        predecessor.job_name == JOB_NAME,
        predecessor.id < SyncJob.id,
        predecessor.details_json['game_pk'].as_integer()
        == SyncJob.details_json['game_pk'].as_integer(),
        predecessor.status.in_((
            sync_jobs.STATUS_PENDING,
            sync_jobs.STATUS_RUNNING,
            sync_jobs.STATUS_FAILED,
        )),
    ))
    return (
        SyncJob.query
        .filter(
            SyncJob.job_name == JOB_NAME,
            eligible,
            ~unfinished_predecessor,
        )
        .order_by(
            SyncJob.updated_at.asc(),
            SyncJob.created_at.asc(),
            SyncJob.attempts.asc(),
            SyncJob.id.asc(),
        )
        .limit(bounded)
        .all()
    )


def unresolved_count():
    return (
        SyncJob.query
        .filter(
            SyncJob.job_name == JOB_NAME,
            or_(
                SyncJob.status.in_((
                    sync_jobs.STATUS_PENDING,
                    sync_jobs.STATUS_RUNNING,
                )),
                and_(
                    SyncJob.status == sync_jobs.STATUS_FAILED,
                    SyncJob.attempts < SyncJob.max_attempts,
                ),
            ),
        )
        .count()
    )


def change_for(job):
    return dict((job.details_json or {}).get('change') or {})


def stage_for(job):
    return (job.details_json or {}).get('stage') or STAGE_CANONICAL_PENDING


def claim(job, *, sync_run_id, exclusive_cycle_lock_held=False):
    current = db.session.get(SyncJob, job.id)
    db.session.refresh(current)
    details = dict(current.details_json or {})
    observation = GameObservationState.query.filter_by(
        mlb_game_pk=details.get('game_pk')
    ).one_or_none()
    if (
        observation is None
        or observation.observation_fingerprint
        != details.get('observation_fingerprint')
    ) and _may_supersede_without_losing_work(current, details):
        details.update({
            'work_status': WORK_SUPERSEDED,
            'superseded_at': utc_now_naive().isoformat(),
            'supersession_reason': (
                'accepted_observation_missing'
                if observation is None
                else 'accepted_observation_superseded'
            ),
            'superseded_by_observation_fingerprint': (
                observation.observation_fingerprint
                if observation is not None
                else None
            ),
        })
        sync_jobs.skip_job(current, result=details)
        return None

    abandoned_work_is_exclusive = (
        exclusive_cycle_lock_held and db.engine.dialect.name == 'postgresql'
    )
    stale_running_checkpoint = sync_jobs._is_stale_running(
        current,
        stale_after_minutes=LOCAL_STALE_AFTER_MINUTES,
    )
    claimed = sync_jobs.claim_job(
        current,
        sync_run_id=sync_run_id,
        stale_after_minutes=LOCAL_STALE_AFTER_MINUTES,
        reclaim_abandoned=(
            abandoned_work_is_exclusive and not stale_running_checkpoint
        ),
    )
    if claimed is None:
        return None
    details = dict(claimed.details_json or {})
    details['work_status'] = WORK_IN_PROGRESS
    details['last_claimed_at'] = utc_now_naive().isoformat()
    details['total_attempts'] = int(details.get('total_attempts') or 0) + 1
    details['stage_attempts'] = int(claimed.attempts or 0)
    claimed.details_json = details
    claimed.updated_at = utc_now_naive()
    db.session.commit()
    return claimed


def checkpoint(job, stage, *, commit=True, **fields):
    current = db.session.get(SyncJob, job.id)
    details = dict(current.details_json or {})
    current_stage = details.get('stage') or STAGE_CANONICAL_PENDING
    next_stage = _furthest_stage(current_stage, stage)
    if next_stage != current_stage:
        _record_stage_attempts(details, current_stage, current.attempts)
        # The claim that reached this checkpoint is the first attempt at the
        # next stage. Retry exhaustion is stage-local so a late failure cannot
        # strand canonical work that already committed.
        current.attempts = 1
    details.update(fields)
    details.update({
        'work_status': WORK_IN_PROGRESS,
        'stage': next_stage,
        'stage_attempts': int(current.attempts or 0),
        'last_heartbeat_at': utc_now_naive().isoformat(),
    })
    current.details_json = details
    current.last_heartbeat_at = utc_now_naive()
    current.updated_at = utc_now_naive()
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return current


def defer(job, *, reason, stage, **fields):
    """Return claimed work to pending without consuming its durable identity."""
    current = db.session.get(SyncJob, job.id)
    details = dict(current.details_json or {})
    current_stage = details.get('stage') or STAGE_CANONICAL_PENDING
    next_stage = _furthest_stage(current_stage, stage)
    if next_stage != current_stage:
        _record_stage_attempts(details, current_stage, current.attempts)
        current.attempts = 0
    elif current.attempts:
        current.attempts -= 1
    details.update(fields)
    details.update({
        'work_status': WORK_PLANNED,
        'stage': next_stage,
        'stage_attempts': int(current.attempts or 0),
        'last_deferral': reason,
        'last_deferred_at': utc_now_naive().isoformat(),
    })
    current.status = sync_jobs.STATUS_PENDING
    current.completed_at = None
    current.error_message = None
    current.error_type = None
    current.details_json = details
    current.updated_at = utc_now_naive()
    db.session.commit()
    return current


def defer_unclaimed(job, *, reason):
    """Rotate an ineligible candidate without consuming an execution attempt."""
    current = db.session.get(SyncJob, job.id)
    details = dict(current.details_json or {})
    details.update({
        'last_deferral': reason,
        'last_deferred_at': utc_now_naive().isoformat(),
    })
    current.details_json = details
    current.updated_at = utc_now_naive()
    db.session.commit()
    return current


def complete(job, *, outcome, **fields):
    current = db.session.get(SyncJob, job.id)
    details = dict(current.details_json or {})
    details.update(fields)
    details.update({
        'work_status': WORK_COMPLETED,
        'stage': STAGE_COMPLETE,
        'outcome': outcome,
    })
    return sync_jobs.complete_job(current, result=details)


def fail(job, error, *, stage, **fields):
    """Persist a safe retryable/terminal failure after rolling back its unit."""
    db.session.rollback()
    current = db.session.get(SyncJob, job.id)
    details = dict(current.details_json or {})
    current_stage = details.get('stage') or STAGE_CANONICAL_PENDING
    next_stage = _furthest_stage(current_stage, stage)
    if next_stage != current_stage:
        _record_stage_attempts(details, current_stage, current.attempts)
        current.attempts = 1
    terminal = (current.attempts or 0) >= (current.max_attempts or 0)
    details.update(fields)
    details.update({
        'work_status': WORK_TERMINAL_FAILURE if terminal else WORK_RETRYABLE_FAILURE,
        'stage': next_stage,
        'stage_attempts': int(current.attempts or 0),
        'last_failure': _error_name(error),
    })
    return sync_jobs.fail_job(
        current,
        _error_name(error),
        result=details,
    )


def _supersede_unfinished(game_pk, successor_fingerprint, *, now):
    prefix = f'game:{game_pk}:observation:'
    rows = (
        SyncJob.query
        .filter(
            SyncJob.job_name == JOB_NAME,
            SyncJob.scope_key.like(f'{prefix}%'),
            SyncJob.status.in_((
                sync_jobs.STATUS_PENDING,
                sync_jobs.STATUS_RUNNING,
                sync_jobs.STATUS_FAILED,
            )),
        )
        .all()
    )
    for job in rows:
        details = dict(job.details_json or {})
        if not _may_supersede_without_losing_work(job, details):
            continue
        details.update({
            'work_status': WORK_SUPERSEDED,
            'superseded_at': now.isoformat(),
            'superseded_by_observation_fingerprint': successor_fingerprint,
        })
        sync_jobs.skip_job(job, result=details, commit=False)


def _may_supersede_without_losing_work(job, details=None):
    details = details or dict(job.details_json or {})
    return (
        job.status != sync_jobs.STATUS_RUNNING
        and (details.get('stage') or STAGE_CANONICAL_PENDING)
        == STAGE_CANONICAL_PENDING
        and not details.get('canonical_impact')
    )


def _furthest_stage(current, requested):
    current = current or STAGE_CANONICAL_PENDING
    requested = requested or STAGE_CANONICAL_PENDING
    if STAGE_ORDER.get(current, -1) >= STAGE_ORDER.get(requested, -1):
        return current
    return requested


def _record_stage_attempts(details, stage, attempts):
    history = dict(details.get('attempts_by_stage') or {})
    history[stage] = max(int(history.get(stage) or 0), int(attempts or 0))
    details['attempts_by_stage'] = history


def _is_actionable(change):
    return (
        _get(change, 'accepted') is True
        and _get(change, 'changed') is True
        and _get(change, 'classification') in ACTIONABLE_CLASSIFICATIONS
        and _get(change, 'finality_state') in ACTIONABLE_FINALITY_STATES
    )


def _change_payload(change):
    fields = (
        'game_pk',
        'classification',
        'changed',
        'accepted',
        'previous_observation_identity',
        'current_observation_identity',
        'finality_state',
        'source_authority',
        'source_observed_at',
        'detected_at',
        'differences',
        'reason',
    )
    return {field: _get(change, field) for field in fields}


def _product_date(row, now):
    raw = (((row.observation or {}).get('identity') or {}).get('official_date'))
    try:
        return date.fromisoformat(raw)
    except (TypeError, ValueError):
        return (row.accepted_at or now).date()


def _correction_recheck_observation_is_safe(row):
    if (
        row is None
        or row.finality_state != game_finality.FINAL_AND_USABLE
        or not row.observation_fingerprint
    ):
        return False
    observation = row.observation or {}
    identity = observation.get('identity') or {}
    try:
        official_date = date.fromisoformat(identity.get('official_date'))
    except (TypeError, ValueError):
        return False
    if identity.get('official_date') != official_date.isoformat():
        return False
    home_team = identity.get('home_team_id')
    away_team = identity.get('away_team_id')
    if (
        not _is_positive_integer(home_team)
        or not _is_positive_integer(away_team)
        or home_team == away_team
    ):
        return False
    linescore = observation.get('linescore') or {}
    return (
        _nonnegative_int((linescore.get('home') or {}).get('runs')) is not None
        and _nonnegative_int((linescore.get('away') or {}).get('runs')) is not None
    )


def _scope_key(game_pk, fingerprint, source_observed_at):
    source_revision = (
        source_observed_at.isoformat(timespec='microseconds')
        if source_observed_at is not None else 'unknown'
    )
    return (
        f'game:{game_pk}:observation:{fingerprint}:'
        f'source_revision:{source_revision}'
    )


def _error_name(error):
    return type(error).__name__ if isinstance(error, BaseException) else str(error)


def _positive_int(value):
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _nonnegative_int(value):
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= 0 else None


def _is_positive_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _get(value, field):
    return value.get(field) if isinstance(value, dict) else getattr(value, field, None)
