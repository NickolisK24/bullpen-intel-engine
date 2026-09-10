"""Canonical synchronization run vocabulary and lifecycle operations.

This module owns execution identity and telemetry only. It deliberately does
not claim jobs, retry work, acquire baseball data, or decide publication.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from uuid import uuid4

from models.sync_failure import SyncFailure
from models.sync_run import SyncRun, SyncRunScope
from utils.db import db
from utils.time import utc_now_naive


class _ValueEnum(str, Enum):
    def __str__(self):
        return self.value


class RunType(_ValueEnum):
    SCHEDULE_GAME_STATE = 'schedule_game_state'
    ROSTER_TRANSACTIONS = 'roster_transactions'
    PREGAME_CONTEXT = 'pregame_context'
    LIVE_GAME = 'live_game'
    FINAL_GAME_RECONCILIATION = 'final_game_reconciliation'
    INCREMENTAL_INTELLIGENCE = 'incremental_intelligence'
    PUBLICATION = 'publication'
    MORNING_RECONCILIATION = 'morning_reconciliation'
    NIGHTLY_FINALIZATION = 'nightly_finalization'
    TARGETED_REPAIR = 'targeted_repair'
    BACKFILL = 'backfill'
    FULL_RECONCILIATION = 'full_reconciliation'


class TriggerType(_ValueEnum):
    SCHEDULED = 'scheduled'
    GAME_STATUS_CHANGE = 'game_status_change'
    GAME_FINAL = 'game_final'
    ROSTER_CHANGE = 'roster_change'
    TRANSACTION = 'transaction'
    SOURCE_CHANGE = 'source_change'
    MANUAL = 'manual'
    REPAIR = 'repair'
    BACKFILL = 'backfill'
    RECONCILIATION = 'reconciliation'
    RETRY = 'retry'
    PARENT_RUN = 'parent_run'


class RunStatus(_ValueEnum):
    PENDING = 'pending'
    RUNNING = 'running'
    SUCCEEDED = 'success'
    PARTIAL = 'partial'
    FAILED = 'failed'
    CANCELLED = 'cancelled'


class RunStage(_ValueEnum):
    PENDING = 'pending'
    STARTED = 'started'
    ACQUIRE = 'acquire'
    NORMALIZE = 'normalize'
    CANONICALIZE = 'canonicalize'
    IMPACT = 'impact'
    DERIVE = 'derive'
    SNAPSHOT = 'snapshot'
    PUBLISH = 'publish'
    RECONCILE = 'reconcile'
    COMPLETE = 'complete'
    # Established stages remain canonical while existing paths converge.
    TEAM_ASSIGNMENTS = 'team_assignments'
    ROSTER_STATUS = 'roster_status'
    TRANSACTIONS = 'transactions'
    SCHEDULE_FINALITY_PREFLIGHT = 'schedule_finality_preflight'
    LOG_INGESTION = 'log_ingestion'
    FATIGUE_RECALCULATION = 'fatigue_recalculation'
    WORKLOAD_EVIDENCE = 'workload_evidence'
    COMPOSED_READS = 'composed_reads'
    LEGACY_READ_RECONCILIATION_AUDIT = 'legacy_read_reconciliation_audit'
    BACKTEST_REFRESH = 'backtest_refresh'
    DASHBOARD_SNAPSHOT = 'dashboard_snapshot'
    PUBLISHED = 'published'
    CONTINUOUS_COMPLETE = 'continuous_complete'
    FAILED = 'failed'


class ScopeType(_ValueEnum):
    LEAGUE = 'league'
    GAME = 'game'
    TEAM = 'team'
    PITCHER = 'pitcher'
    SOURCE_DOMAIN = 'source_domain'


class SourceDomain(_ValueEnum):
    MULTI_DOMAIN = 'multi_domain'
    IDENTITY = 'identity'
    SCHEDULE = 'schedule'
    ROSTER = 'roster'
    TRANSACTIONS = 'transactions'
    PREGAME = 'pregame'
    GAME_FEED = 'game_feed'
    LIVE_FEED = 'live_feed'
    BOXSCORE = 'boxscore'
    PLAY_BY_PLAY = 'play_by_play'
    STATCAST = 'statcast'
    WORKLOAD = 'workload'
    PERFORMANCE = 'performance'
    ORGANIZATIONAL_DEPTH = 'organizational_depth'
    TEAM_STATE = 'team_state'
    READ_MODEL = 'read_model'
    PUBLICATION = 'publication'
    OPERATIONS = 'operations'


class FailureClass(_ValueEnum):
    SOURCE = 'source'
    TIMEOUT = 'timeout'
    RATE_LIMIT = 'rate_limit'
    VALIDATION = 'validation'
    CANONICALIZATION = 'canonicalization'
    DERIVATION = 'derivation'
    PUBLICATION = 'publication'
    DATABASE = 'database'
    CONCURRENCY = 'concurrency'
    INTERNAL = 'internal'


TERMINAL_STATUSES = frozenset({
    RunStatus.SUCCEEDED.value,
    RunStatus.PARTIAL.value,
    RunStatus.FAILED.value,
    RunStatus.CANCELLED.value,
})


def _value(value, enum_type, *, nullable=False):
    if value is None and nullable:
        return None
    raw = value.value if isinstance(value, enum_type) else str(value)
    try:
        return enum_type(raw).value
    except ValueError as exc:
        allowed = ', '.join(item.value for item in enum_type)
        raise ValueError(f'Unsupported {enum_type.__name__} {raw!r}; expected one of: {allowed}') from exc


def trigger_for_source(source, *, fallback=TriggerType.MANUAL):
    if source in {'scheduled', 'github_actions'}:
        return TriggerType.SCHEDULED.value
    if source == 'manual':
        return TriggerType.MANUAL.value
    return _value(fallback, TriggerType)


def _run(run_or_id):
    if isinstance(run_or_id, SyncRun):
        return run_or_id
    run = db.session.get(SyncRun, run_or_id)
    if run is None:
        raise LookupError(f'SyncRun {run_or_id!r} does not exist')
    return run


def _validate_parent(parent_sync_run_id):
    if parent_sync_run_id is None:
        return None
    parent = db.session.get(SyncRun, parent_sync_run_id)
    if parent is None:
        raise ValueError(f'Parent SyncRun {parent_sync_run_id!r} does not exist')
    return parent


def create_run(
    *,
    run_type,
    trigger_type,
    source,
    job_name,
    baseball_date=None,
    source_domain=None,
    parent_sync_run_id=None,
    correlation_id=None,
    status=RunStatus.PENDING,
    stage=RunStage.PENDING,
    started_at=None,
    scopes=(),
    commit=True,
):
    parent = _validate_parent(parent_sync_run_id)
    if parent is not None and correlation_id is None:
        correlation_id = parent.correlation_id
    now = started_at or utc_now_naive()
    run = SyncRun(
        job_name=job_name,
        run_type=_value(run_type, RunType),
        trigger_type=_value(trigger_type, TriggerType),
        baseball_date=baseball_date,
        source_domain=_value(source_domain, SourceDomain, nullable=True),
        parent_sync_run_id=parent_sync_run_id,
        correlation_id=correlation_id or str(uuid4()),
        started_at=now,
        status=_value(status, RunStatus),
        stage=_value(stage, RunStage),
        source=source,
        created_at=now,
    )
    db.session.add(run)
    db.session.flush()
    add_scopes(run, scopes, commit=False)
    if commit:
        db.session.commit()
    return run


def start_run(run_or_id=None, *, commit=True, **create_fields):
    if run_or_id is None:
        return create_run(
            status=RunStatus.RUNNING,
            stage=RunStage.STARTED,
            commit=commit,
            **create_fields,
        )
    run = _run(run_or_id)
    if run.status in TERMINAL_STATUSES:
        return run
    run.status = RunStatus.RUNNING.value
    run.stage = RunStage.STARTED.value
    run.started_at = run.started_at or utc_now_naive()
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return run


def mark_stage(run_or_id, stage, *, commit=True):
    run = _run(run_or_id)
    run.stage = _value(stage, RunStage)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return run


def add_scopes(run_or_id, scopes, *, commit=True):
    run = _run(run_or_id)
    existing = {(row.scope_type, row.scope_key) for row in run.scopes}
    for scope_type, scope_key in scopes or ():
        normalized = (_value(scope_type, ScopeType), str(scope_key))
        if normalized in existing:
            continue
        run.scopes.append(SyncRunScope(
            scope_type=normalized[0],
            scope_key=normalized[1],
        ))
        existing.add(normalized)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return run


def scope_entries(*, league=False, game_pks=(), team_ids=(), pitcher_ids=(), source_domains=()):
    values = []
    if league:
        values.append((ScopeType.LEAGUE, 'mlb'))
    values.extend((ScopeType.GAME, value) for value in game_pks or ())
    values.extend((ScopeType.TEAM, value) for value in team_ids or ())
    values.extend((ScopeType.PITCHER, value) for value in pitcher_ids or ())
    values.extend((ScopeType.SOURCE_DOMAIN, _value(value, SourceDomain)) for value in source_domains or ())
    return tuple(values)


def record_outcome(
    run_or_id,
    *,
    source_reads=None,
    source_changes=None,
    canonical_mutations=None,
    affected_games=None,
    affected_teams=None,
    affected_pitchers=None,
    downstream_work_created=None,
    warnings_count=None,
    publication_id=None,
    outcome=None,
    commit=True,
):
    run = _run(run_or_id)
    fields = {
        'source_reads': source_reads,
        'source_changes': source_changes,
        'canonical_mutations': canonical_mutations,
        'affected_games': affected_games,
        'affected_teams': affected_teams,
        'affected_pitchers': affected_pitchers,
        'downstream_work_created': downstream_work_created,
        'warnings_count': warnings_count,
    }
    for name, value in fields.items():
        if value is not None:
            if int(value) < 0:
                raise ValueError(f'{name} cannot be negative')
            setattr(run, name, int(value))
    if publication_id is not None:
        run.publication_id = str(publication_id)
    if canonical_mutations is not None:
        run.zero_mutation = int(canonical_mutations) == 0
    if outcome is not None:
        merged = dict(run.outcome_json or {})
        merged.update(_json_safe(outcome))
        run.outcome_json = merged
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return run


def finalize_run(
    run_or_id,
    status,
    *,
    stage=None,
    failed_stage=None,
    completed_at=None,
    updates=None,
    commit=True,
):
    run = _run(run_or_id)
    final_status = _value(status, RunStatus)
    if final_status not in TERMINAL_STATUSES:
        raise ValueError(f'Cannot finalize a run as non-terminal status {final_status!r}')
    if run.status in TERMINAL_STATUSES:
        return run
    for name, value in (updates or {}).items():
        if value is not None and hasattr(run, name):
            setattr(run, name, value)
    run.status = final_status
    run.stage = _value(
        stage or (RunStage.FAILED if final_status == RunStatus.FAILED else RunStage.COMPLETE),
        RunStage,
    )
    run.failed_stage = _value(failed_stage, RunStage, nullable=True)
    run.completed_at = completed_at or utc_now_naive()
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return run


def record_failure(
    run_or_id,
    error,
    *,
    failure_class=FailureClass.INTERNAL,
    stage=None,
    source_domain=None,
    entity_type='sync_run',
    entity_ref=None,
    payload=None,
    retryable=None,
    commit=True,
):
    run = _run(run_or_id)
    failure = SyncFailure(
        sync_run_id=run.id,
        job_name=run.job_name,
        entity_type=entity_type,
        entity_ref=str(entity_ref) if entity_ref is not None else None,
        payload=_json_safe(payload),
        error=str(error),
        failure_class=_value(failure_class, FailureClass),
        stage=_value(stage or run.stage, RunStage),
        source_domain=_value(source_domain or run.source_domain, SourceDomain, nullable=True),
        retryable=retryable,
        created_at=utc_now_naive(),
        resolved=False,
    )
    db.session.add(failure)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return failure


def runs_for_scope(scope_type, scope_key):
    return (
        SyncRun.query
        .join(SyncRunScope, SyncRunScope.sync_run_id == SyncRun.id)
        .filter(
            SyncRunScope.scope_type == _value(scope_type, ScopeType),
            SyncRunScope.scope_key == str(scope_key),
        )
    )


def runs_for_baseball_date(baseball_date: date):
    return SyncRun.query.filter(SyncRun.baseball_date == baseball_date)


def _json_safe(value):
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
