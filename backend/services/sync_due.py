"""Shared due-window coordinator for redundant production schedulers."""

from __future__ import annotations

from datetime import datetime, timezone

from models.dashboard_snapshot import DashboardSnapshot
from models.sync_schedule_attempt import SyncScheduleAttempt
from services import sync as sync_service
from services import sync_metadata
from services import schedule_authority
from services.postgame_recovery import (
    reset_fully_processed_markers_without_appearance_rows,
)
from services.schedule_tonight_refresh import refresh_schedule_and_tonight
from services.sync_execution_context import (
    MODE_DAILY, MODE_MORNING, MODE_POSTGAME, SyncExecutionContext,
)
from services.sync_publication_proof import (
    LEAGUE_PUBLICATION_EXPECTED_PENDING_ACTIVE_SLATE,
    build_candidate_publication_proof,
)
from utils.db import db


OUTCOME_RUNNING = 'running'
OUTCOME_EXECUTED = 'executed'
OUTCOME_ALREADY_SATISFIED = 'already_satisfied'
OUTCOME_BLOCKED = 'blocked'
OUTCOME_FAILED = 'failed'


def _utc_naive(value):
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _latest_snapshot_id():
    row = DashboardSnapshot.query.order_by(DashboardSnapshot.id.desc()).first()
    return row.id if row is not None else None


def _satisfied_attempt(context):
    return (
        SyncScheduleAttempt.query
        .filter_by(
            mode=context.mode,
            intended_window=context.intended_window,
            outcome=OUTCOME_EXECUTED,
        )
        .order_by(SyncScheduleAttempt.completed_at.desc())
        .first()
    )


def _recover_abandoned_attempts():
    rows = SyncScheduleAttempt.query.filter_by(outcome=OUTCOME_RUNNING).all()
    if not rows:
        return
    completed_at = _now()
    for row in rows:
        row.outcome = OUTCOME_FAILED
        row.completed_at = completed_at
        row.failure_reason = 'abandoned_attempt_reclaimed_after_writer_lock_acquired'
    db.session.commit()


def _new_attempt(context, *, outcome=OUTCOME_RUNNING, failure_reason=None):
    attempt = SyncScheduleAttempt(
        mode=context.mode,
        source=context.source,
        intended_window=context.intended_window,
        scheduled_for=_utc_naive(context.scheduled_for),
        started_at=_now(),
        completed_at=_now() if outcome != OUTCOME_RUNNING else None,
        outcome=outcome,
        snapshot_before_id=_latest_snapshot_id(),
        recovery_reason=context.recovery_reason,
        operator=context.operator,
        failure_reason=failure_reason,
    )
    db.session.add(attempt)
    db.session.commit()
    return attempt


def _run_daily(app, context, guard, *, days_back, public_only):
    status = sync_service.run_daily_sync(
        app,
        days_back=days_back,
        source=context.source,
        include_internal_enrichment=not public_only,
        preacquired_writer_guard=guard,
    )
    proof = build_candidate_publication_proof(
        status.get('dashboard_snapshot_id'),
        candidate_required=True,
        publication_critical=status.get('publication_critical'),
        sync_status=status.get('status'),
    )
    tonight = refresh_schedule_and_tonight(source=context.source)
    status['schedule_tonight_refresh'] = tonight
    proof['schedule_tonight_verified'] = tonight.get('status') == 'ok'
    successful = (
        status.get('status') in sync_metadata.SUCCESSFUL_STATUSES
        and proof.get('verified') is True
        and tonight.get('status') == 'ok'
    )
    return status, proof, successful


def _run_postgame(app, context, guard, *, public_only):
    sweep_dates = sync_service.postgame_schedule_dates(context.scheduled_for)
    marker_recovery = reset_fully_processed_markers_without_appearance_rows(
        schedule_dates=sweep_dates,
    )
    status = sync_service.run_postgame_refresh(
        app,
        source=context.source,
        include_internal_enrichment=not public_only,
        preacquired_writer_guard=guard,
        window_time=context.scheduled_for,
    )
    changed_workload = (
        int(status.get('new_logs_added') or 0)
        + int(status.get('logs_corrected') or 0)
    ) > 0
    proof = build_candidate_publication_proof(
        status.get('dashboard_snapshot_id'),
        candidate_required=changed_workload,
    )
    publication_ok = (
        proof.get('verified') is True
        or proof.get('league_publication_status')
        == LEAGUE_PUBLICATION_EXPECTED_PENDING_ACTIVE_SLATE
    )
    tonight = refresh_schedule_and_tonight(source=context.source)
    status['schedule_tonight_refresh'] = tonight
    proof['schedule_tonight_verified'] = tonight.get('status') == 'ok'
    successful = (
        status.get('status') in sync_metadata.SUCCESSFUL_STATUSES
        and publication_ok
        and tonight.get('status') == 'ok'
    )
    status['ledger_marker_recovery'] = marker_recovery
    return status, proof, successful


def _run_morning(context):
    result = refresh_schedule_and_tonight(
        context.scheduled_for.astimezone(schedule_authority.EASTERN).date(),
        source=context.source,
    )
    return result, {'verified': result.get('status') == 'ok'}, result.get('status') == 'ok'


def run_due_sync(app, context: SyncExecutionContext, *, days_back=7, public_only=True):
    """Execute one due window under the shared public-writer advisory lock."""
    job_name = {
        MODE_DAILY: sync_metadata.JOB_DAILY_SYNC,
        MODE_POSTGAME: sync_metadata.JOB_POSTGAME_REFRESH,
        MODE_MORNING: 'morning_schedule_refresh',
    }[context.mode]
    guard = None
    attempt = None
    with app.app_context():
        try:
            guard = sync_metadata.acquire_sync_writer_guard(
                job_name=job_name,
                source=context.source,
                lock_scope=sync_metadata.LOCK_SCOPE_PUBLIC,
            )
        except sync_metadata.SyncWriterConflict as conflict:
            attempt = _new_attempt(
                context,
                outcome=OUTCOME_BLOCKED,
                failure_reason=conflict.reason,
            )
            return {
                'status': OUTCOME_BLOCKED,
                'executed': False,
                'execution': attempt.to_dict(),
                'lock': conflict.to_dict(),
            }

        try:
            _recover_abandoned_attempts()
            satisfied = _satisfied_attempt(context)
            if satisfied is not None:
                attempt = _new_attempt(context, outcome=OUTCOME_ALREADY_SATISFIED)
                attempt.publication_outcome = 'previous_window_execution_verified'
                attempt.snapshot_after_id = _latest_snapshot_id()
                db.session.commit()
                return {
                    'status': OUTCOME_ALREADY_SATISFIED,
                    'executed': False,
                    'satisfied_by_attempt_id': satisfied.id,
                    'execution': attempt.to_dict(),
                }

            attempt = _new_attempt(context)
            if context.mode == MODE_DAILY:
                status, proof, successful = _run_daily(
                    app, context, guard, days_back=days_back, public_only=public_only,
                )
            elif context.mode == MODE_POSTGAME:
                status, proof, successful = _run_postgame(
                    app, context, guard, public_only=public_only,
                )
            else:
                status, proof, successful = _run_morning(context)

            attempt.sync_run_id = status.get('sync_run_id')
            attempt.snapshot_after_id = _latest_snapshot_id()
            attempt.completed_at = _now()
            attempt.outcome = OUTCOME_EXECUTED if successful else OUTCOME_FAILED
            if proof.get('schedule_tonight_verified') is False:
                attempt.publication_outcome = 'schedule_tonight_not_verified'
            else:
                attempt.publication_outcome = (
                    'verified' if proof.get('verified') is True
                    else str(proof.get('league_publication_status') or 'not_verified')
                )
            if not successful:
                attempt.failure_reason = str(status.get('message') or status.get('error') or 'sync_not_verified')
            db.session.commit()
            return {
                'status': attempt.outcome,
                'executed': True,
                'execution': attempt.to_dict(),
                'publication_proof': proof,
                'sync': status,
            }
        except Exception as exc:
            db.session.rollback()
            if attempt is not None:
                attempt = db.session.get(SyncScheduleAttempt, attempt.id)
                attempt.completed_at = _now()
                attempt.outcome = OUTCOME_FAILED
                attempt.failure_reason = str(exc)
                attempt.snapshot_after_id = _latest_snapshot_id()
                db.session.commit()
            raise
        finally:
            if guard is not None:
                guard.release()
