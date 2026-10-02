"""Shared due-window coordinator for redundant production schedulers."""

from __future__ import annotations

from datetime import datetime, timezone

from models.dashboard_snapshot import DashboardSnapshot
from models.sync_schedule_attempt import SyncScheduleAttempt
from services import sync as sync_service
from services import dashboard_snapshot as dashboard_snapshot_service
from services import sync_metadata
from services import schedule_authority
from services.distribution_delivery import (
    DistributionDeliveryRequest,
    request_distribution_delivery,
)
from services.postgame_recovery import (
    reset_fully_processed_markers_without_appearance_rows,
)
from services.schedule_tonight_refresh import refresh_schedule
from services.sync_execution_context import (
    MODE_DAILY, MODE_MORNING, MODE_POSTGAME, SOURCE_EXTERNAL_SCHEDULE,
    SOURCE_INCIDENT_RECOVERY, SyncExecutionContext,
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


def _current_published_snapshot():
    return (
        DashboardSnapshot.query
        .filter_by(
            snapshot_type=dashboard_snapshot_service.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
            is_published=True,
            status='ready',
        )
        .order_by(DashboardSnapshot.id.desc())
        .first()
    )


def _distribution_delivery_after_execution(
    context,
    *,
    published_before_id,
    published_after,
):
    """Request distribution only when an external schedule advanced publication.

    This runs after the sync attempt and publication transactions have committed
    and after the public writer lock has been released. Its result is evidence,
    never part of the authoritative sync verdict.
    """
    if context.source != SOURCE_EXTERNAL_SCHEDULE:
        return {
            'status': 'skipped',
            'reason': 'publisher_not_render_external_schedule',
        }
    current = published_after
    if current is None or current.id == published_before_id:
        return {
            'status': 'skipped',
            'reason': 'publication_not_advanced',
            'snapshot_id': current.id if current is not None else None,
        }
    if current.sync_run_id is None or current.data_through is None:
        return {
            'status': 'failed_to_request',
            'reason': 'publication_identity_incomplete',
            'snapshot_id': current.id,
        }
    return request_distribution_delivery(DistributionDeliveryRequest(
        snapshot_id=current.id,
        sync_run_id=current.sync_run_id,
        data_through=current.data_through.isoformat(),
        publication_source=context.source,
        publication_type=context.mode,
    ))


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


def tonight_reference_date(context):
    """The baseball date a governed run presents: its intended window in ET.

    Derived from the execution context's ``scheduled_for`` (never host-local
    time), the same Eastern authority the morning schedule refresh uses.
    """
    return context.scheduled_for.astimezone(schedule_authority.EASTERN).date()


def _ensure_current_tonight_v1(context, *, include_publication_edition=True):
    """Ensure today's immutable tonight_v1 edition for the trusted publication.

    TN-11.8: the current trusted Dashboard snapshot is the bullpen authority,
    and the run's intended ET date is the presented baseball day. They differ
    when the calendar rolls forward while the trusted publication is still
    current (a new day, an off-day), so this ensures the edition for exactly
    ``(tonight_reference_date(context), snapshot)``: reused when stored,
    created once otherwise, never overwritten, and never another date.

    The publication-time edition (bound to the snapshot's own availability
    date by the post-publication hook) is also ensured for lanes that publish,
    and reported under ``publication_edition``. Reported for proof only; it
    never gates sync success (TN-11.7) and never republishes the Dashboard.
    """
    from services.tonight_read_model import (
        ensure_tonight_v1_for_date,
        ensure_tonight_v1_for_publication,
    )

    reference_date = tonight_reference_date(context)
    snapshot = _current_published_snapshot()
    if snapshot is None:
        return {
            'status': 'skipped',
            'reason': 'no_trusted_publication',
            'reference_date': reference_date.isoformat(),
        }
    publication_edition = None
    if include_publication_edition:
        publication_edition = ensure_tonight_v1_for_publication(
            snapshot, source=context.source,
        )
    result = ensure_tonight_v1_for_date(
        snapshot, reference_date, source=context.source,
    )
    if publication_edition is not None:
        result['publication_edition'] = publication_edition
    return result


def _refresh_schedule_proof(proof, status, context):
    """Schedule authority for the run's Tonight handoff and execution proof.

    Preparation barrier (SyncRun 93277): Daily and Postgame refresh the same
    rolling window BEFORE they build the Dashboard candidate. When that
    pre-candidate refresh succeeded for exactly the window this runner
    presents, it is the run's schedule authority and is not repeated: a
    second refresh here, after the candidate was certified, is how a
    postseason game retired too late to reach the slate gate. Only when the
    lane did not prepare the window (disabled, failed, or a different window)
    does the runner refresh it here, as before.
    """
    reference_date = tonight_reference_date(context)
    prepared = status.get('slate_schedule_refresh') or {}
    start_date, end_date = schedule_authority.rolling_window(reference_date)
    if (
        prepared.get('status') == 'ok'
        and prepared.get('start_date') == start_date.isoformat()
        and prepared.get('end_date') == end_date.isoformat()
    ):
        schedule = {
            'status': 'ok',
            'reference_date': reference_date.isoformat(),
            'schedule': prepared,
            'prepared_before_candidate': True,
            'legacy_tonight_v5': 'not_generated',
        }
    else:
        schedule = refresh_schedule(source=context.source)
        schedule['prepared_before_candidate'] = False
    status['schedule_refresh'] = schedule
    proof['schedule_refresh_verified'] = schedule.get('status') == 'ok'
    return schedule


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
    schedule = _refresh_schedule_proof(proof, status, context)
    proof['tonight_v1'] = _ensure_current_tonight_v1(context)
    successful = (
        status.get('status') in sync_metadata.SUCCESSFUL_STATUSES
        and proof.get('verified') is True
        and schedule.get('status') == 'ok'
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
    schedule = _refresh_schedule_proof(proof, status, context)
    proof['tonight_v1'] = _ensure_current_tonight_v1(context)
    successful = (
        status.get('status') in sync_metadata.SUCCESSFUL_STATUSES
        and publication_ok
        and schedule.get('status') == 'ok'
    )
    status['ledger_marker_recovery'] = marker_recovery
    return status, proof, successful


def _run_morning(context):
    """Schedule refresh for the intended ET date, then that date's edition.

    The same path serves the natural morning window and ``recovery_morning``.
    It never ingests, never publishes the Dashboard and never builds tonight_v5:
    the current trusted publication is rolled forward into the edition for the
    refreshed date.
    """
    reference_date = tonight_reference_date(context)
    result = refresh_schedule(reference_date, source=context.source)
    tonight = _ensure_current_tonight_v1(context, include_publication_edition=False)
    result['tonight_edition'] = {
        'schedule_date': reference_date.isoformat(),
        'trusted_snapshot_id': tonight.get('dashboard_snapshot_id'),
        'tonight_publication_id': tonight.get('tonight_publication_id'),
        'reference_date': tonight.get('reference_date'),
        'status': tonight.get('status'),
        'game_count': tonight.get('game_count'),
    }
    proof = {
        'verified': result.get('status') == 'ok',
        'schedule_refresh_verified': result.get('status') == 'ok',
        'tonight_v1': tonight,
    }
    return result, proof, result.get('status') == 'ok'


def run_due_sync(app, context: SyncExecutionContext, *, days_back=7, public_only=True):
    """Execute one due window under the shared public-writer advisory lock."""
    job_name = {
        MODE_DAILY: sync_metadata.JOB_DAILY_SYNC,
        MODE_POSTGAME: sync_metadata.JOB_POSTGAME_REFRESH,
        MODE_MORNING: 'morning_schedule_refresh',
    }[context.mode]
    guard = None
    attempt = None
    published_before_id = None
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
            # A governed morning recovery re-runs the idempotent schedule and
            # Tonight edition reconciliation even when the natural morning
            # window already executed: that run may have preceded the fix it
            # is recovering from. It never ingests or publishes.
            morning_recovery = (
                context.mode == MODE_MORNING
                and context.source == SOURCE_INCIDENT_RECOVERY
            )
            satisfied = None if morning_recovery else _satisfied_attempt(context)
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
            current_before = _current_published_snapshot()
            published_before_id = current_before.id if current_before is not None else None
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
            if proof.get('schedule_refresh_verified') is False:
                attempt.publication_outcome = 'schedule_refresh_not_verified'
            else:
                attempt.publication_outcome = (
                    'verified' if proof.get('verified') is True
                    else str(proof.get('league_publication_status') or 'not_verified')
                )
            if not successful:
                attempt.failure_reason = str(status.get('message') or status.get('error') or 'sync_not_verified')
            db.session.commit()
            current_after = _current_published_snapshot()
            result = {
                'status': attempt.outcome,
                'executed': True,
                'execution': attempt.to_dict(),
                'publication_proof': proof,
                'sync': status,
            }
            # The distribution handoff is deliberately outside both the
            # publication transaction and the public writer lock. Correct
            # baseball truth stays committed even when GitHub is unavailable.
            if guard is not None:
                guard.release()
                guard = None
            if successful:
                result['distribution_delivery'] = _distribution_delivery_after_execution(
                    context,
                    published_before_id=published_before_id,
                    published_after=current_after,
                )
            else:
                result['distribution_delivery'] = {
                    'status': 'skipped',
                    'reason': 'sync_not_successful',
                }
            return result
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
