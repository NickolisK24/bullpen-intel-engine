"""Derived source-readiness diagnostics for internal pipeline health."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
import logging

from sqlalchemy.exc import SQLAlchemyError

from models.dashboard_snapshot import DashboardSnapshot
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.sync_failure import SyncFailure
from models.sync_run import SyncRun
from services import slate_coverage
from utils.db import db


READY = 'ready'
DEGRADED = 'degraded'
STALE = 'stale'
UNAVAILABLE = 'unavailable'
NEVER_FETCHED = 'never_fetched'
UNKNOWN = 'unknown'

FAIL_CLOSED_STATES = frozenset({
    DEGRADED,
    STALE,
    UNAVAILABLE,
    NEVER_FETCHED,
    UNKNOWN,
})

DEFAULT_STALE_AFTER_DAYS = 2

FAMILY_FINALITY_AUTHORITY = 'finality_authority'
FAMILY_STATSAPI_CORE = 'statsapi_core'
FAMILY_GAME_LOGS = 'game_logs'
FAMILY_SLATE_COVERAGE = 'slate_coverage'
FAMILY_DASHBOARD_SNAPSHOTS = 'dashboard_snapshots'
FAMILY_ROSTER_STATUS_CURRENT = 'roster_status_current'

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceReadiness:
    source_family: str
    status: str
    reason_codes: tuple[str, ...] = ()
    last_successful_at: datetime | date | None = None
    last_attempted_at: datetime | date | None = None
    stale_after_days: int | None = None
    data_age_days: int | None = None
    record_count: int | None = None
    dead_letter_count: int = 0
    sync_run_id: int | None = None
    source: str | None = None
    coverage: dict = field(default_factory=dict)
    details: dict = field(default_factory=dict)

    @property
    def fail_closed(self) -> bool:
        return self.status in FAIL_CLOSED_STATES

    def to_dict(self) -> dict:
        return {
            'source_family': self.source_family,
            'status': self.status,
            'fail_closed': self.fail_closed,
            'reason_codes': list(self.reason_codes),
            'last_successful_at': _iso(self.last_successful_at),
            'last_attempted_at': _iso(self.last_attempted_at),
            'stale_after_days': self.stale_after_days,
            'data_age_days': self.data_age_days,
            'record_count': self.record_count,
            'dead_letter_count': self.dead_letter_count,
            'sync_run_id': self.sync_run_id,
            'source': self.source,
            'coverage': self.coverage,
            'details': self.details,
        }


def classify_source_readiness(
    source_family: str,
    *,
    last_successful_at=None,
    last_attempted_at=None,
    stale_after_days: int | None = DEFAULT_STALE_AFTER_DAYS,
    record_count: int | None = None,
    dead_letter_count: int = 0,
    reason_codes=(),
    reference_date: date | None = None,
    sync_run_id: int | None = None,
    source: str | None = None,
    provenance_present: bool = True,
    coverage: dict | None = None,
    details: dict | None = None,
) -> SourceReadiness:
    reasons = list(reason_codes or [])
    data_age_days = _age_days(last_successful_at, reference_date)

    if not provenance_present:
        status = UNAVAILABLE
        reasons.append('provenance_missing')
    elif last_successful_at is None:
        status = NEVER_FETCHED if last_attempted_at is None else UNAVAILABLE
        reasons.append('source_never_fetched' if last_attempted_at is None else 'source_unavailable')
    elif stale_after_days is not None and data_age_days is not None and data_age_days >= stale_after_days:
        status = STALE
        reasons.append('source_stale')
    elif dead_letter_count:
        status = DEGRADED
        reasons.append('dead_letters_unresolved')
    else:
        status = READY

    return SourceReadiness(
        source_family=source_family,
        status=status,
        reason_codes=_dedupe(reasons),
        last_successful_at=last_successful_at,
        last_attempted_at=last_attempted_at,
        stale_after_days=stale_after_days,
        data_age_days=data_age_days,
        record_count=record_count,
        dead_letter_count=dead_letter_count or 0,
        sync_run_id=sync_run_id,
        source=source,
        coverage=coverage or {},
        details=details or {},
    )


def source_readiness_payload(
    *,
    metadata: dict | None = None,
    sync_status: str | None = None,
    slate_coverage_payload: dict | None = None,
    reference_date: date | None = None,
) -> dict:
    families = [
        _safe_family(FAMILY_FINALITY_AUTHORITY, _finality_authority_readiness, reference_date),
        _safe_family(FAMILY_STATSAPI_CORE, _statsapi_core_readiness, reference_date),
        _safe_family(FAMILY_GAME_LOGS, _game_logs_readiness, reference_date, metadata),
        _safe_family(
            FAMILY_SLATE_COVERAGE,
            _slate_coverage_readiness,
            reference_date,
            slate_coverage_payload,
            sync_status,
        ),
        _safe_family(FAMILY_DASHBOARD_SNAPSHOTS, _dashboard_snapshots_readiness, reference_date),
        _safe_family(FAMILY_ROSTER_STATUS_CURRENT, _roster_status_readiness, reference_date),
    ]
    blocking = [family for family in families if family.fail_closed]
    return {
        'overall_status': READY if not blocking else DEGRADED,
        'fail_closed': bool(blocking),
        'blocking_source_families': [family.source_family for family in blocking],
        'families': {family.source_family: family.to_dict() for family in families},
    }


def unknown_source_readiness_payload(reason='readiness_framework_unavailable') -> dict:
    family = SourceReadiness(
        source_family='source_readiness_framework',
        status=UNKNOWN,
        reason_codes=(reason,),
    )
    return {
        'overall_status': UNKNOWN,
        'fail_closed': True,
        'blocking_source_families': [family.source_family],
        'families': {family.source_family: family.to_dict()},
    }


def _finality_authority_readiness(reference_date=None):
    return SourceReadiness(
        source_family=FAMILY_FINALITY_AUTHORITY,
        status=READY,
        reason_codes=('module_loaded',),
        stale_after_days=None,
        details={
            'final_status_requires_code_or_detail': True,
            'abstract_final_alone_allowed': False,
        },
    )


def _statsapi_core_readiness(reference_date=None):
    run = _latest_successful_run(('daily_sync', 'postgame_refresh'))
    attempted = _latest_run(('daily_sync', 'postgame_refresh'))
    failures = _unresolved_failure_count(job_names=('daily_sync', 'postgame_refresh'))
    return classify_source_readiness(
        FAMILY_STATSAPI_CORE,
        last_successful_at=_run_finished_at(run),
        last_attempted_at=_run_started_at(attempted),
        stale_after_days=DEFAULT_STALE_AFTER_DAYS,
        dead_letter_count=failures,
        reference_date=reference_date,
        sync_run_id=getattr(run, 'id', None),
        source=getattr(run, 'source', None),
    )


def _game_logs_readiness(reference_date=None, metadata=None):
    metadata = metadata or {}
    run = _latest_successful_run(('daily_sync', 'postgame_refresh'))
    attempted = _latest_run(('daily_sync', 'postgame_refresh'))
    latest_workload = metadata.get('latest_workload_date') or _max_game_log_date()
    count = metadata.get('game_logs')
    if count is None:
        count = _game_log_count()
    return classify_source_readiness(
        FAMILY_GAME_LOGS,
        last_successful_at=latest_workload,
        last_attempted_at=_run_started_at(attempted),
        stale_after_days=DEFAULT_STALE_AFTER_DAYS,
        record_count=count,
        dead_letter_count=_unresolved_failure_count(entity_types=('pitcher_game_logs', 'game_log_correction_attempt')),
        reference_date=reference_date,
        sync_run_id=getattr(run, 'id', None),
        source=getattr(run, 'source', None),
        provenance_present=run is not None,
        details={'latest_workload_date': _iso(latest_workload)},
    )


def _slate_coverage_readiness(reference_date=None, coverage=None, sync_status=None):
    if not isinstance(coverage, dict):
        return SourceReadiness(
            source_family=FAMILY_SLATE_COVERAGE,
            status=UNKNOWN,
            reason_codes=('slate_coverage_missing',),
        )
    ready = coverage.get('complete_enough_to_publish') is True
    reason_codes = tuple(coverage.get('reason_codes') or ())
    return SourceReadiness(
        source_family=FAMILY_SLATE_COVERAGE,
        status=READY if ready else DEGRADED,
        reason_codes=reason_codes or (('slate_complete',) if ready else ('slate_not_publishable',)),
        stale_after_days=None,
        record_count=coverage.get('games_included') or coverage.get('games_scheduled'),
        coverage={
            'slate_date': coverage.get('slate_date'),
            'complete_enough_to_publish': coverage.get('complete_enough_to_publish'),
            'games_scheduled': coverage.get('games_scheduled'),
            'games_final': coverage.get('games_final'),
            'games_fully_ingested': coverage.get('games_fully_ingested'),
        },
        details={'sync_status': sync_status},
    )


def _dashboard_snapshots_readiness(reference_date=None):
    snapshot = (
        DashboardSnapshot.query
        .filter_by(snapshot_type='bullpen_dashboard', status='ready', is_published=True)
        .order_by(
            DashboardSnapshot.snapshot_generated_at.desc(),
            DashboardSnapshot.id.desc(),
        )
        .first()
    )
    return classify_source_readiness(
        FAMILY_DASHBOARD_SNAPSHOTS,
        last_successful_at=getattr(snapshot, 'snapshot_generated_at', None),
        last_attempted_at=getattr(snapshot, 'snapshot_generated_at', None),
        stale_after_days=DEFAULT_STALE_AFTER_DAYS,
        record_count=1 if snapshot is not None else 0,
        reference_date=reference_date,
        sync_run_id=getattr(snapshot, 'sync_run_id', None),
        source=getattr(snapshot, 'source', None),
        provenance_present=(snapshot is None or getattr(snapshot, 'sync_run_id', None) is not None),
        details={'data_through': _iso(getattr(snapshot, 'data_through', None))},
    )


def _roster_status_readiness(reference_date=None):
    total = db.session.query(db.func.count(Pitcher.id)).scalar() or 0
    with_status = (
        db.session.query(db.func.count(Pitcher.id))
        .filter(Pitcher.roster_status.isnot(None))
        .scalar()
        or 0
    )
    latest = db.session.query(db.func.max(Pitcher.roster_status_updated_at)).scalar()
    if total and with_status == 0:
        return classify_source_readiness(
            FAMILY_ROSTER_STATUS_CURRENT,
            last_successful_at=None,
            last_attempted_at=None,
            stale_after_days=DEFAULT_STALE_AFTER_DAYS,
            record_count=0,
            reference_date=reference_date,
            reason_codes=('roster_status_not_loaded',),
        )
    return classify_source_readiness(
        FAMILY_ROSTER_STATUS_CURRENT,
        last_successful_at=latest,
        last_attempted_at=latest,
        stale_after_days=DEFAULT_STALE_AFTER_DAYS,
        record_count=with_status,
        reference_date=reference_date,
        details={'pitchers_total': int(total), 'pitchers_with_roster_status': int(with_status)},
    )


def _safe_family(family, builder, reference_date=None, *args):
    try:
        return builder(reference_date, *args)
    except SQLAlchemyError as exc:
        db.session.rollback()
        logger.warning('Could not build source readiness for %s: %s', family, exc)
        return SourceReadiness(
            source_family=family,
            status=UNKNOWN,
            reason_codes=('readiness_query_failed',),
        )
    except Exception as exc:  # noqa: BLE001 - health diagnostics fail closed
        logger.warning('Could not build source readiness for %s: %s', family, exc)
        return SourceReadiness(
            source_family=family,
            status=UNKNOWN,
            reason_codes=('readiness_framework_error',),
        )


def _latest_run(job_names):
    return (
        SyncRun.query
        .filter(SyncRun.job_name.in_(tuple(job_names)))
        .order_by(SyncRun.started_at.desc(), SyncRun.id.desc())
        .first()
    )


def _latest_successful_run(job_names):
    return (
        SyncRun.query
        .filter(SyncRun.job_name.in_(tuple(job_names)))
        .filter(SyncRun.status.in_(('success', 'partial')))
        .order_by(SyncRun.completed_at.desc(), SyncRun.started_at.desc(), SyncRun.id.desc())
        .first()
    )


def _unresolved_failure_count(*, job_names=None, entity_types=None):
    query = SyncFailure.query.filter(SyncFailure.resolved.is_(False))
    if job_names:
        query = query.filter(SyncFailure.job_name.in_(tuple(job_names)))
    if entity_types:
        query = query.filter(SyncFailure.entity_type.in_(tuple(entity_types)))
    return int(query.count() or 0)


def _max_game_log_date():
    return db.session.query(db.func.max(GameLog.game_date)).scalar()


def _game_log_count():
    return int(db.session.query(db.func.count(GameLog.id)).scalar() or 0)


def _run_finished_at(run):
    if run is None:
        return None
    return run.completed_at or run.started_at


def _run_started_at(run):
    return getattr(run, 'started_at', None)


def _age_days(value, reference_date=None):
    if value is None:
        return None
    ref = reference_date or date.today()
    value_date = value.date() if isinstance(value, datetime) else value
    if isinstance(value_date, date):
        return (ref - value_date).days
    return None


def _iso(value):
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _dedupe(values):
    seen = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return tuple(seen)
