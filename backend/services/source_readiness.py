"""Derived source-readiness diagnostics for internal pipeline health."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
import logging

from sqlalchemy.exc import SQLAlchemyError

from models.dashboard_snapshot import DashboardSnapshot
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.play_by_play_foundation import GamePlayByPlayEvent, PlayByPlayProcessedGame
from models.player_transaction import PlayerTransaction, PlayerTransactionSyncWindow
from models.roster_status_snapshot import RosterStatusSnapshot
from models.scheduled_game import ScheduledGame
from models.sync_failure import SyncFailure
from models.sync_run import SyncRun
from models.team_game_pitching_split import TeamGamePitchingSplit
from services import slate_coverage
from services.roster_status_sync import (
    ROSTER_STATUS_CONFLICT_ENTITY_TYPE,
    ROSTER_STATUS_FETCH_ENTITY_TYPE,
    ROSTER_STATUS_IDENTITY_ENTITY_TYPE,
    roster_status_cache_divergence_count,
)
from services.transaction_ingestion import (
    TRANSACTION_FAILURE_ENTITY_TYPES,
    TRANSACTION_STALE_AFTER_DAYS,
    WINDOW_STATUS_PARTIAL,
    WINDOW_STATUS_SUCCESS,
)
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
FAMILY_ROSTER_STATUS_SNAPSHOTS = 'roster_status_snapshots'
FAMILY_PLAYER_TRANSACTIONS = 'player_transactions'
FAMILY_FINAL_PLAY_BY_PLAY = 'final_play_by_play'
FAMILY_TEAM_GAME_PITCHING_SPLITS = 'team_game_pitching_splits'
FAMILY_CALENDAR_CONTEXT = 'calendar_context'

ROSTER_SNAPSHOT_STALE_AFTER_DAYS = 1
ROSTER_STATUS_FAILURE_ENTITY_TYPES = (
    ROSTER_STATUS_FETCH_ENTITY_TYPE,
    ROSTER_STATUS_IDENTITY_ENTITY_TYPE,
    ROSTER_STATUS_CONFLICT_ENTITY_TYPE,
)
FINAL_PBP_FAILURE_ENTITY_TYPES = (
    'final_pbp_fetch',
    'final_pbp_shape',
    'final_pbp_reconciliation',
    'final_pbp_identity',
)
TEAM_GAME_PITCHING_SPLIT_FAILURE_ENTITY_TYPES = (
    'team_game_pitching_split_derivation',
)
CURRENT_BLOCKING_SOURCE_FAMILIES = frozenset({
    FAMILY_FINALITY_AUTHORITY,
    FAMILY_STATSAPI_CORE,
    FAMILY_GAME_LOGS,
    FAMILY_SLATE_COVERAGE,
    FAMILY_DASHBOARD_SNAPSHOTS,
    FAMILY_ROSTER_STATUS_SNAPSHOTS,
    FAMILY_PLAYER_TRANSACTIONS,
})

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
        _safe_family(
            FAMILY_ROSTER_STATUS_SNAPSHOTS,
            _roster_status_snapshot_readiness,
            reference_date,
        ),
        _safe_family(
            FAMILY_PLAYER_TRANSACTIONS,
            _player_transaction_readiness,
            reference_date,
        ),
        _safe_family(
            FAMILY_FINAL_PLAY_BY_PLAY,
            _final_play_by_play_readiness,
            reference_date,
        ),
        _safe_family(
            FAMILY_TEAM_GAME_PITCHING_SPLITS,
            _team_game_pitching_split_readiness,
            reference_date,
        ),
        _safe_family(
            FAMILY_CALENDAR_CONTEXT,
            _calendar_context_readiness,
            reference_date,
        ),
    ]
    blocking = [
        family
        for family in families
        if family.fail_closed and family.source_family in CURRENT_BLOCKING_SOURCE_FAMILIES
    ]
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


def roster_status_snapshot_readiness_payload(*, reference_date: date | None = None) -> dict:
    """Public helper for consumers that need the roster source family only."""
    return _safe_family(
        FAMILY_ROSTER_STATUS_SNAPSHOTS,
        _roster_status_snapshot_readiness,
        reference_date,
    ).to_dict()


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
    diagnostics = coverage.get('diagnostics') or {}
    details = {'sync_status': sync_status}
    if diagnostics:
        details.update({
            'failure_domains': diagnostics.get('failure_domains') or [],
            'failed_game_pks': diagnostics.get('failed_game_pks') or [],
            'failed_team_ids': diagnostics.get('failed_team_ids') or [],
            'postgame_blocker_count': diagnostics.get('postgame_blocker_count') or 0,
            'non_final_game_count': diagnostics.get('non_final_game_count') or 0,
        })
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
        details=details,
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


def _roster_status_snapshot_readiness(reference_date=None):
    latest_snapshot = (
        RosterStatusSnapshot.query
        .order_by(
            RosterStatusSnapshot.snapshot_date.desc(),
            RosterStatusSnapshot.updated_at.desc(),
            RosterStatusSnapshot.id.desc(),
        )
        .first()
    )
    latest_failure = _latest_failure(ROSTER_STATUS_FAILURE_ENTITY_TYPES)
    latest_failure_at = getattr(latest_failure, 'created_at', None)
    latest_attempted_at = _latest_datetime(
        getattr(latest_snapshot, 'updated_at', None),
        latest_failure_at,
    )

    active_team_ids = _active_pitcher_team_ids()
    target_date = reference_date or getattr(latest_snapshot, 'snapshot_date', None)
    covered_team_ids = _snapshot_team_ids(target_date) if target_date else set()
    missing_team_ids = sorted(active_team_ids - covered_team_ids)
    record_count = int(db.session.query(db.func.count(RosterStatusSnapshot.id)).scalar() or 0)
    dead_letters = _unresolved_failure_count(entity_types=ROSTER_STATUS_FAILURE_ENTITY_TYPES)
    divergence_count = roster_status_cache_divergence_count()
    latest_snapshot_date = getattr(latest_snapshot, 'snapshot_date', None)
    provenance_present = (
        latest_snapshot is None
        or (
            bool(getattr(latest_snapshot, 'source', None))
            and getattr(latest_snapshot, 'first_seen_at', None) is not None
            and getattr(latest_snapshot, 'sync_run_id', None) is not None
        )
    )
    details = {
        'latest_snapshot_date': _iso(latest_snapshot_date),
        'active_pitcher_team_count': len(active_team_ids),
        'snapshot_cache_divergence_count': divergence_count,
    }
    if latest_failure is not None:
        details['latest_failure_reason'] = (
            (latest_failure.payload or {}).get('reason')
            or latest_failure.error
        )
    coverage = {
        'snapshot_date': _iso(target_date),
        'teams_expected': len(active_team_ids),
        'teams_covered': len(covered_team_ids),
        'teams_missing': missing_team_ids,
    }

    readiness = classify_source_readiness(
        FAMILY_ROSTER_STATUS_SNAPSHOTS,
        last_successful_at=latest_snapshot_date,
        last_attempted_at=latest_attempted_at,
        stale_after_days=ROSTER_SNAPSHOT_STALE_AFTER_DAYS,
        record_count=record_count,
        dead_letter_count=dead_letters,
        reason_codes=('roster_snapshots_missing',) if record_count == 0 else (),
        reference_date=reference_date,
        sync_run_id=getattr(latest_snapshot, 'sync_run_id', None),
        source=getattr(latest_snapshot, 'source', None),
        provenance_present=provenance_present,
        coverage=coverage,
        details=details,
    )
    reason_codes = list(readiness.reason_codes)
    status = readiness.status
    if missing_team_ids:
        status = DEGRADED if status == READY else status
        reason_codes.append('roster_snapshot_team_coverage_incomplete')
    if divergence_count:
        status = DEGRADED
        reason_codes.append('roster_status_cache_divergence')

    return SourceReadiness(
        source_family=readiness.source_family,
        status=status,
        reason_codes=_dedupe(reason_codes),
        last_successful_at=readiness.last_successful_at,
        last_attempted_at=readiness.last_attempted_at,
        stale_after_days=readiness.stale_after_days,
        data_age_days=readiness.data_age_days,
        record_count=readiness.record_count,
        dead_letter_count=readiness.dead_letter_count,
        sync_run_id=readiness.sync_run_id,
        source=readiness.source,
        coverage=coverage,
        details=details,
    )


def _player_transaction_readiness(reference_date=None):
    latest_window = _latest_transaction_window()
    latest_success = _latest_transaction_window(
        statuses=(WINDOW_STATUS_SUCCESS, WINDOW_STATUS_PARTIAL),
    )
    latest_failure = _latest_failure(TRANSACTION_FAILURE_ENTITY_TYPES)
    latest_failure_at = getattr(latest_failure, 'created_at', None)
    latest_attempted_at = _latest_datetime(
        getattr(latest_window, 'attempted_at', None),
        latest_failure_at,
    )
    record_count = int(db.session.query(db.func.count(PlayerTransaction.id)).scalar() or 0)
    dead_letters = _unresolved_failure_count(entity_types=TRANSACTION_FAILURE_ENTITY_TYPES)
    latest_success_at = getattr(latest_success, 'successful_at', None)
    reason_codes = []
    if latest_window and latest_window.status == 'failed':
        reason_codes.append('transaction_fetch_failed')

    details = {
        'latest_window_status': getattr(latest_window, 'status', None),
        'latest_transaction_date': _iso(_max_transaction_date()),
        'unknown_type_count': getattr(latest_success, 'unknown_type_count', 0) or 0,
        'alignment_unknown_count': (
            getattr(latest_success, 'alignment_unknown_count', 0) or 0
        ),
        'alignment_misaligned_count': (
            getattr(latest_success, 'alignment_misaligned_count', 0) or 0
        ),
        'alignment_no_snapshot_count': (
            getattr(latest_success, 'alignment_no_snapshot_count', 0) or 0
        ),
    }
    if latest_window is not None:
        details['latest_window'] = latest_window.to_dict()
    if latest_failure is not None:
        details['latest_failure_reason'] = (
            (latest_failure.payload or {}).get('reason')
            or latest_failure.error
        )

    coverage = {
        'source_query_start_date': _iso(
            getattr(latest_success, 'source_query_start_date', None)
        ),
        'source_query_end_date': _iso(
            getattr(latest_success, 'source_query_end_date', None)
        ),
        'records_fetched': getattr(latest_success, 'records_fetched', None),
        'records_stored': getattr(latest_success, 'records_stored', None),
    }
    provenance_present = (
        latest_success is None
        or (
            bool(getattr(latest_success, 'source', None))
            and getattr(latest_success, 'attempted_at', None) is not None
            and getattr(latest_success, 'successful_at', None) is not None
        )
    )
    readiness = classify_source_readiness(
        FAMILY_PLAYER_TRANSACTIONS,
        last_successful_at=latest_success_at,
        last_attempted_at=latest_attempted_at,
        stale_after_days=TRANSACTION_STALE_AFTER_DAYS,
        record_count=record_count,
        dead_letter_count=dead_letters,
        reason_codes=tuple(reason_codes),
        reference_date=reference_date,
        sync_run_id=getattr(latest_success, 'sync_run_id', None),
        source=getattr(latest_success, 'source', None),
        provenance_present=provenance_present,
        coverage=coverage,
        details=details,
    )
    final_status = readiness.status
    final_reasons = list(readiness.reason_codes)
    if details['unknown_type_count']:
        final_status = DEGRADED if final_status == READY else final_status
        final_reasons.append('unknown_transaction_types_present')
    if (
        details['alignment_unknown_count']
        or details['alignment_misaligned_count']
        or details['alignment_no_snapshot_count']
    ):
        final_status = DEGRADED if final_status == READY else final_status
        final_reasons.append('transaction_roster_alignment_incomplete')

    return SourceReadiness(
        source_family=readiness.source_family,
        status=final_status,
        reason_codes=_dedupe(final_reasons),
        last_successful_at=readiness.last_successful_at,
        last_attempted_at=readiness.last_attempted_at,
        stale_after_days=readiness.stale_after_days,
        data_age_days=readiness.data_age_days,
        record_count=readiness.record_count,
        dead_letter_count=readiness.dead_letter_count,
        sync_run_id=readiness.sync_run_id,
        source=readiness.source,
        coverage=coverage,
        details=details,
    )


def _final_play_by_play_readiness(reference_date=None):
    latest_marker = (
        PlayByPlayProcessedGame.query
        .order_by(
            PlayByPlayProcessedGame.last_attempted_at.desc(),
            PlayByPlayProcessedGame.id.desc(),
        )
        .first()
    )
    latest_success = (
        PlayByPlayProcessedGame.query
        .filter_by(processing_status=PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED)
        .order_by(
            PlayByPlayProcessedGame.processed_at.desc(),
            PlayByPlayProcessedGame.id.desc(),
        )
        .first()
    )
    marker_count = int(db.session.query(db.func.count(PlayByPlayProcessedGame.id)).scalar() or 0)
    event_count = int(db.session.query(db.func.count(GamePlayByPlayEvent.id)).scalar() or 0)
    status_counts = {
        status: _pbp_marker_count(status)
        for status in (
            PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED,
            PlayByPlayProcessedGame.STATUS_INCOMPLETE,
            PlayByPlayProcessedGame.STATUS_FAILED,
            PlayByPlayProcessedGame.STATUS_ABSENT,
            PlayByPlayProcessedGame.STATUS_AMBIGUOUS,
        )
    }
    dead_letters = _unresolved_failure_count(entity_types=FINAL_PBP_FAILURE_ENTITY_TYPES)
    reconciliation_mismatch_count = int(
        db.session.query(
            db.func.coalesce(
                db.func.sum(PlayByPlayProcessedGame.reconciliation_mismatch_count),
                0,
            )
        ).scalar() or 0
    )
    unresolved_pitcher_count = int(
        db.session.query(
            db.func.coalesce(
                db.func.sum(PlayByPlayProcessedGame.unresolved_pitcher_count),
                0,
            )
        ).scalar() or 0
    )
    max_retry_count = int(
        db.session.query(
            db.func.coalesce(db.func.max(PlayByPlayProcessedGame.attempt_count), 0)
        ).scalar() or 0
    )
    reason_codes = []
    if marker_count == 0:
        reason_codes.append('final_pbp_never_attempted')
    if status_counts[PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED] == 0:
        reason_codes.append('final_pbp_no_fully_processed_games')
    if status_counts[PlayByPlayProcessedGame.STATUS_INCOMPLETE]:
        reason_codes.append('final_pbp_incomplete_markers')
    if status_counts[PlayByPlayProcessedGame.STATUS_FAILED]:
        reason_codes.append('final_pbp_failed_markers')
    if status_counts[PlayByPlayProcessedGame.STATUS_ABSENT]:
        reason_codes.append('final_pbp_absent_markers')
    if status_counts[PlayByPlayProcessedGame.STATUS_AMBIGUOUS]:
        reason_codes.append('final_pbp_ambiguous_markers')
    if reconciliation_mismatch_count:
        reason_codes.append('final_pbp_reconciliation_mismatch')
    if unresolved_pitcher_count:
        reason_codes.append('final_pbp_unresolved_pitcher_identity')

    if marker_count == 0:
        status = NEVER_FETCHED if latest_marker is None else UNAVAILABLE
    elif (
        status_counts[PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED] == 0
        or event_count == 0
    ):
        status = UNAVAILABLE
    elif any(
        status_counts[state]
        for state in (
            PlayByPlayProcessedGame.STATUS_INCOMPLETE,
            PlayByPlayProcessedGame.STATUS_FAILED,
            PlayByPlayProcessedGame.STATUS_ABSENT,
            PlayByPlayProcessedGame.STATUS_AMBIGUOUS,
        )
    ) or dead_letters or reconciliation_mismatch_count or unresolved_pitcher_count:
        status = DEGRADED
    else:
        status = READY

    latest_failure = _latest_failure(FINAL_PBP_FAILURE_ENTITY_TYPES)
    details = {
        'latest_marker_status': getattr(latest_marker, 'processing_status', None),
        'latest_marker_reason': getattr(latest_marker, 'incomplete_reason', None),
        'event_count': event_count,
        'max_retry_count': max_retry_count,
        'reconciliation_mismatch_count': reconciliation_mismatch_count,
        'unresolved_pitcher_count': unresolved_pitcher_count,
    }
    if latest_failure is not None:
        details['latest_failure_reason'] = (
            (latest_failure.payload or {}).get('reason')
            or latest_failure.error
        )
    coverage = {
        'final_games_expected': marker_count,
        'games_fully_processed': status_counts[
            PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED
        ],
        'games_incomplete': status_counts[PlayByPlayProcessedGame.STATUS_INCOMPLETE],
        'games_failed': status_counts[PlayByPlayProcessedGame.STATUS_FAILED],
        'games_absent': status_counts[PlayByPlayProcessedGame.STATUS_ABSENT],
        'games_ambiguous': status_counts[PlayByPlayProcessedGame.STATUS_AMBIGUOUS],
    }
    return SourceReadiness(
        source_family=FAMILY_FINAL_PLAY_BY_PLAY,
        status=status,
        reason_codes=_dedupe(reason_codes),
        last_successful_at=getattr(latest_success, 'processed_at', None),
        last_attempted_at=getattr(latest_marker, 'last_attempted_at', None),
        stale_after_days=None,
        record_count=event_count,
        dead_letter_count=dead_letters,
        sync_run_id=getattr(latest_marker, 'sync_run_id', None),
        source=getattr(latest_marker, 'source', None),
        coverage=coverage,
        details=details,
    )


def _team_game_pitching_split_readiness(reference_date=None):
    latest = _latest_team_game_pitching_split()
    latest_success = _latest_team_game_pitching_split(
        split_status=TeamGamePitchingSplit.STATUS_COMPLETE,
    )
    latest_failure = _latest_failure(TEAM_GAME_PITCHING_SPLIT_FAILURE_ENTITY_TYPES)
    latest_failure_at = getattr(latest_failure, 'created_at', None)
    latest_attempted_at = _latest_datetime(
        getattr(latest, 'last_derived_at', None),
        latest_failure_at,
    )
    row_count = int(db.session.query(db.func.count(TeamGamePitchingSplit.id)).scalar() or 0)
    expected_rows = _final_scheduled_team_game_count()
    missing_rows = max(expected_rows - row_count, 0)
    split_status_counts = {
        status: _team_game_pitching_split_count(split_status=status)
        for status in (
            TeamGamePitchingSplit.STATUS_COMPLETE,
            TeamGamePitchingSplit.STATUS_PARTIAL,
            TeamGamePitchingSplit.STATUS_UNKNOWN,
        )
    }
    partial_unknown_count = (
        split_status_counts[TeamGamePitchingSplit.STATUS_PARTIAL]
        + split_status_counts[TeamGamePitchingSplit.STATUS_UNKNOWN]
    )
    dead_letters = _unresolved_failure_count(
        entity_types=TEAM_GAME_PITCHING_SPLIT_FAILURE_ENTITY_TYPES
    )
    reason_counts = _team_game_pitching_split_reason_counts('split_reason_codes')
    reason_codes = []
    if row_count == 0:
        reason_codes.append('team_game_pitching_splits_never_derived')
    if missing_rows:
        reason_codes.append('team_game_pitching_splits_missing')
    if partial_unknown_count:
        reason_codes.append('team_game_pitching_splits_partial_or_unknown')

    readiness = classify_source_readiness(
        FAMILY_TEAM_GAME_PITCHING_SPLITS,
        last_successful_at=getattr(latest_success, 'last_derived_at', None),
        last_attempted_at=latest_attempted_at,
        stale_after_days=None,
        record_count=row_count,
        dead_letter_count=dead_letters,
        reason_codes=tuple(reason_codes),
        reference_date=reference_date,
        sync_run_id=getattr(latest, 'sync_run_id', None),
        source=getattr(latest, 'source', None),
        provenance_present=_team_game_pitching_split_provenance_present(latest),
        coverage={
            'final_games_expected': _final_scheduled_game_count(),
            'team_game_splits_expected': expected_rows,
            'team_game_splits_complete': split_status_counts[
                TeamGamePitchingSplit.STATUS_COMPLETE
            ],
            'team_game_splits_partial': split_status_counts[
                TeamGamePitchingSplit.STATUS_PARTIAL
            ],
            'team_game_splits_unknown': split_status_counts[
                TeamGamePitchingSplit.STATUS_UNKNOWN
            ],
            'team_game_splits_missing': missing_rows,
        },
        details={
            'latest_split_status': getattr(latest, 'split_completeness_status', None),
            'latest_split_reason_codes': list(getattr(latest, 'split_reason_codes', None) or []),
            'split_reason_code_counts': reason_counts,
            'correction_count': _team_game_pitching_split_correction_count(),
            'latest_failure_reason': _failure_reason(latest_failure),
        },
    )
    final_status = readiness.status
    final_reasons = list(readiness.reason_codes)
    if missing_rows or partial_unknown_count:
        final_status = DEGRADED if final_status == READY else final_status
    return SourceReadiness(
        source_family=readiness.source_family,
        status=final_status,
        reason_codes=_dedupe(final_reasons),
        last_successful_at=readiness.last_successful_at,
        last_attempted_at=readiness.last_attempted_at,
        stale_after_days=readiness.stale_after_days,
        data_age_days=readiness.data_age_days,
        record_count=readiness.record_count,
        dead_letter_count=readiness.dead_letter_count,
        sync_run_id=readiness.sync_run_id,
        source=readiness.source,
        coverage=readiness.coverage,
        details=readiness.details,
    )


def _calendar_context_readiness(reference_date=None):
    latest = _latest_team_game_pitching_split()
    latest_success = _latest_team_game_pitching_split(
        calendar_status=TeamGamePitchingSplit.STATUS_COMPLETE,
    )
    latest_failure = _latest_failure(TEAM_GAME_PITCHING_SPLIT_FAILURE_ENTITY_TYPES)
    latest_failure_at = getattr(latest_failure, 'created_at', None)
    latest_attempted_at = _latest_datetime(
        getattr(latest, 'last_derived_at', None),
        latest_failure_at,
    )
    row_count = int(db.session.query(db.func.count(TeamGamePitchingSplit.id)).scalar() or 0)
    expected_rows = _final_scheduled_team_game_count()
    missing_rows = max(expected_rows - row_count, 0)
    calendar_status_counts = {
        status: _team_game_pitching_split_count(calendar_status=status)
        for status in (
            TeamGamePitchingSplit.STATUS_COMPLETE,
            TeamGamePitchingSplit.STATUS_PARTIAL,
            TeamGamePitchingSplit.STATUS_UNKNOWN,
        )
    }
    partial_unknown_count = (
        calendar_status_counts[TeamGamePitchingSplit.STATUS_PARTIAL]
        + calendar_status_counts[TeamGamePitchingSplit.STATUS_UNKNOWN]
    )
    dead_letters = _unresolved_failure_count(
        entity_types=TEAM_GAME_PITCHING_SPLIT_FAILURE_ENTITY_TYPES
    )
    reason_counts = _team_game_pitching_split_reason_counts('calendar_reason_codes')
    reason_codes = []
    if row_count == 0:
        reason_codes.append('calendar_context_never_derived')
    if missing_rows:
        reason_codes.append('calendar_context_missing')
    if partial_unknown_count:
        reason_codes.append('calendar_context_partial_or_unknown')

    readiness = classify_source_readiness(
        FAMILY_CALENDAR_CONTEXT,
        last_successful_at=getattr(latest_success, 'last_derived_at', None),
        last_attempted_at=latest_attempted_at,
        stale_after_days=None,
        record_count=row_count,
        dead_letter_count=dead_letters,
        reason_codes=tuple(reason_codes),
        reference_date=reference_date,
        sync_run_id=getattr(latest, 'sync_run_id', None),
        source=getattr(latest, 'source', None),
        provenance_present=_team_game_pitching_split_provenance_present(latest),
        coverage={
            'final_games_expected': _final_scheduled_game_count(),
            'team_game_calendar_rows_expected': expected_rows,
            'calendar_context_complete': calendar_status_counts[
                TeamGamePitchingSplit.STATUS_COMPLETE
            ],
            'calendar_context_partial': calendar_status_counts[
                TeamGamePitchingSplit.STATUS_PARTIAL
            ],
            'calendar_context_unknown': calendar_status_counts[
                TeamGamePitchingSplit.STATUS_UNKNOWN
            ],
            'calendar_context_missing': missing_rows,
        },
        details={
            'latest_calendar_status': getattr(latest, 'calendar_context_status', None),
            'latest_calendar_reason_codes': list(getattr(latest, 'calendar_reason_codes', None) or []),
            'calendar_reason_code_counts': reason_counts,
            'correction_count': _team_game_pitching_split_correction_count(),
            'latest_failure_reason': _failure_reason(latest_failure),
            'travel_context_inferred': False,
        },
    )
    final_status = readiness.status
    final_reasons = list(readiness.reason_codes)
    if missing_rows or partial_unknown_count:
        final_status = DEGRADED if final_status == READY else final_status
    return SourceReadiness(
        source_family=readiness.source_family,
        status=final_status,
        reason_codes=_dedupe(final_reasons),
        last_successful_at=readiness.last_successful_at,
        last_attempted_at=readiness.last_attempted_at,
        stale_after_days=readiness.stale_after_days,
        data_age_days=readiness.data_age_days,
        record_count=readiness.record_count,
        dead_letter_count=readiness.dead_letter_count,
        sync_run_id=readiness.sync_run_id,
        source=readiness.source,
        coverage=readiness.coverage,
        details=readiness.details,
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


def _pbp_marker_count(status):
    return int(
        PlayByPlayProcessedGame.query
        .filter_by(processing_status=status)
        .count()
        or 0
    )


def _latest_team_game_pitching_split(*, split_status=None, calendar_status=None):
    query = TeamGamePitchingSplit.query
    if split_status:
        query = query.filter_by(split_completeness_status=split_status)
    if calendar_status:
        query = query.filter_by(calendar_context_status=calendar_status)
    return (
        query
        .order_by(
            TeamGamePitchingSplit.last_derived_at.desc(),
            TeamGamePitchingSplit.updated_at.desc(),
            TeamGamePitchingSplit.id.desc(),
        )
        .first()
    )


def _team_game_pitching_split_count(*, split_status=None, calendar_status=None):
    query = TeamGamePitchingSplit.query
    if split_status:
        query = query.filter_by(split_completeness_status=split_status)
    if calendar_status:
        query = query.filter_by(calendar_context_status=calendar_status)
    return int(query.count() or 0)


def _team_game_pitching_split_correction_count():
    return int(
        db.session.query(
            db.func.coalesce(db.func.sum(TeamGamePitchingSplit.correction_count), 0)
        ).scalar()
        or 0
    )


def _team_game_pitching_split_reason_counts(field_name):
    rows = TeamGamePitchingSplit.query.all()
    counts = {}
    for row in rows:
        reasons = getattr(row, field_name, None) or []
        for reason in reasons:
            counts[reason] = counts.get(reason, 0) + 1
    return counts


def _team_game_pitching_split_provenance_present(row):
    if row is None:
        return True
    return bool(row.source) and row.first_seen_at is not None


def _final_scheduled_game_count():
    return int(
        db.session.query(db.func.count(db.distinct(ScheduledGame.game_pk)))
        .filter(ScheduledGame.status_state == ScheduledGame.STATE_FINAL)
        .scalar()
        or 0
    )


def _final_scheduled_team_game_count():
    return int(
        ScheduledGame.query
        .filter(ScheduledGame.status_state == ScheduledGame.STATE_FINAL)
        .count()
        or 0
    )


def _failure_reason(failure):
    if failure is None:
        return None
    return (failure.payload or {}).get('reason') or failure.error


def _active_pitcher_team_ids():
    rows = (
        db.session.query(Pitcher.team_id)
        .filter(Pitcher.active == True)
        .filter(Pitcher.team_id.isnot(None))
        .distinct()
        .all()
    )
    return {row[0] for row in rows}


def _snapshot_team_ids(snapshot_date):
    if snapshot_date is None:
        return set()
    rows = (
        db.session.query(RosterStatusSnapshot.team_id)
        .filter(RosterStatusSnapshot.snapshot_date == snapshot_date)
        .distinct()
        .all()
    )
    return {row[0] for row in rows}


def _latest_transaction_window(statuses=None):
    query = PlayerTransactionSyncWindow.query
    if statuses:
        query = query.filter(PlayerTransactionSyncWindow.status.in_(tuple(statuses)))
    return (
        query
        .order_by(
            PlayerTransactionSyncWindow.attempted_at.desc(),
            PlayerTransactionSyncWindow.id.desc(),
        )
        .first()
    )


def _latest_failure(entity_types):
    return (
        SyncFailure.query
        .filter(SyncFailure.entity_type.in_(tuple(entity_types)))
        .order_by(SyncFailure.created_at.desc(), SyncFailure.id.desc())
        .first()
    )


def _latest_datetime(*values):
    candidates = [value for value in values if isinstance(value, datetime)]
    if not candidates:
        return None
    return max(candidates)


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


def _max_transaction_date():
    return db.session.query(db.func.max(PlayerTransaction.transaction_date)).scalar()


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
